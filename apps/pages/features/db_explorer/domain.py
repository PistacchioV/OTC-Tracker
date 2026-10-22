# -*- coding: utf-8 -*-
"""As regras puras do Database Explorer (só o master): que coluna se edita,
como o valor vai e volta da tela, a impressão digital da linha e o caminho
do banco.

Puro de propósito: não abre banco, não importa `routes` nem Flask.
"""
import hashlib
import json
import math
import os
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal

# Quantas linhas a tela pede por vez, e o teto. A grade é do navegador (o funil
# e o Export trabalham sobre o que veio), e um dia do DPOSICAO-TER com o `_raw`
# passa de cem mil linhas: sem teto, um clique trava a aba de quem pediu.
LIMITS = (500, 1000, 5000, 20000)
DEFAULT_LIMIT = 1000
MAX_LIMIT = 50000

# Extensões de banco DuckDB do app; o resto da pasta (`.lock`, `.wal`, as
# cópias `.corrupt-*`) não é banco que se abra.
DB_EXTS = ('.db', '.duckdb')
# Onde o `recover_duckdb_wal.py` deixa o que substituiu: cópia de segurança,
# não banco vivo.
SKIP_DIRS = ('_recuperado',)
DUCK_MAGIC = b'DUCK'          # bytes 8-11 de todo arquivo DuckDB

# A tabela que marca um banco do ARMAZÉM (§434). O app lê esses bancos pelo
# canal `_raw` e memoriza pelo carimbo do `_manifest`: editar a coluna tipada
# por aqui não muda nada do que as telas mostram, e a memória serviria o valor
# antigo até o restart. Por isso o banco do armazém abre SÓ LEITURA.
STORE_MARK = '_manifest'

TEXT_TYPES = {'VARCHAR', 'CHAR', 'BPCHAR', 'TEXT', 'STRING'}
INT_TYPES = {'TINYINT', 'SMALLINT', 'INTEGER', 'INT', 'BIGINT', 'HUGEINT',
             'UTINYINT', 'USMALLINT', 'UINTEGER', 'UBIGINT', 'UHUGEINT'}
FLOAT_TYPES = {'FLOAT', 'REAL', 'DOUBLE'}
TIMESTAMP_TYPES = {'TIMESTAMP', 'DATETIME', 'TIMESTAMP_S', 'TIMESTAMP_MS', 'TIMESTAMP_NS'}
# Tipo que se escreve no CAST: só nome simples, com precisão opcional. Lista,
# STRUCT, MAP, UNION e ENUM trazem parênteses, aspas ou colchetes e ficam como
# só leitura — o tipo entra no SQL como texto, e só entra o que este padrão
# deixa passar (ele vem do catálogo do próprio banco, nunca do request).
_CASTABLE = re.compile(r'^[A-Z][A-Z0-9_ ]*(\(\d+(\s*,\s*\d+)?\))?$')

_SAFE_INT = 2 ** 53           # acima disso o JavaScript arredonda o número


class ExplorerError(Exception):
    """Erro com CÓDIGO para a tela dizer no idioma de quem vê (§486):
    `{code, params, error}`, com o texto só de fallback."""

    def __init__(self, code, text, status=400, **params):
        super().__init__(text)
        self.code = code
        self.text = text
        self.status = status
        self.params = params

    def payload(self):
        return {'success': False, 'code': self.code, 'params': self.params, 'error': self.text}


def quote_ident(name):
    """O identificador entre aspas duplas, com a aspa interna dobrada. Só se
    aplica a nome que veio do CATÁLOGO do banco (a conferência é antes)."""
    return '"' + str(name).replace('"', '""') + '"'


def qualified(schema, table):
    return quote_ident(schema) + '.' + quote_ident(table)


def kind_of(data_type):
    """A família do tipo, que decide o campo da tela e se a coluna se edita.
    `None` = só leitura (BLOB, lista, STRUCT, MAP, tipo que não se escreve
    num CAST)."""
    t = str(data_type or '').strip().upper()
    if not _CASTABLE.match(t):
        return None
    base = t.split('(')[0].strip()
    if base in TEXT_TYPES:
        return 'text'
    if base == 'JSON':
        return 'json'
    if base in INT_TYPES:
        return 'int'
    if base in FLOAT_TYPES:
        return 'float'
    if base in ('DECIMAL', 'NUMERIC'):
        return 'decimal'
    if base in ('BOOLEAN', 'BOOL', 'LOGICAL'):
        return 'bool'
    if base == 'DATE':
        return 'date'
    if base in TIMESTAMP_TYPES:
        return 'timestamp'
    if base in ('BLOB', 'BYTEA', 'BINARY', 'VARBINARY', 'BIT', 'BITSTRING'):
        return None
    # TIME, INTERVAL, UUID, TIMESTAMP WITH TIME ZONE…: texto no CAST
    return 'other'


def cell(v):
    """O valor do banco como a tela o recebe (e como entra na impressão
    digital). Data em ISO (a tela desenha dd/mm/aaaa), DECIMAL como texto
    (exato), inteiro acima de 2^53 como texto (o JavaScript arredondaria)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v if abs(v) <= _SAFE_INT else str(v)
    if isinstance(v, float):
        return v if math.isfinite(v) else str(v)
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat(sep=' ')
    if isinstance(v, (date, time)):
        return v.isoformat()
    if isinstance(v, timedelta):
        return str(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return '\\x' + bytes(v).hex()
    if isinstance(v, (list, tuple, dict)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v)


def row_hash(values):
    """A impressão digital da linha INTEIRA, na ordem das colunas. A gravação
    a confere sob a trava: linha que mudou (ou que outra instância apagou)
    entre a leitura e o Save é recusada, nunca sobrescrita."""
    txt = json.dumps([cell(v) for v in values], ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha1(txt.encode('utf-8')).hexdigest()[:20]


def readonly_reason(is_store, kind, columns):
    """Por que a tabela não se edita (`None` = edita). Coluna que se chama
    `rowid` esconde a pseudo-coluna do DuckDB, que é por onde a linha é
    achada — editar por ela acharia a linha errada."""
    if is_store:
        return 'store'
    if kind != 'table':
        return 'view'
    if any(str(c).lower() == 'rowid' for c in columns):
        return 'rowid_column'
    return None


def clamp_limit(raw):
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(n, MAX_LIMIT))


_DMY = re.compile(r'^(\d{1,2})/(\d{1,2})/(\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2})(\.\d+)?)?)?$')


def _dmy_to_iso(text, with_time):
    m = _DMY.match(text)
    if not m:
        return text
    d, mo, y, hh, mi, ss, frac = m.groups()
    out = '%s-%02d-%02d' % (y, int(mo), int(d))
    if with_time and hh is not None:
        out += ' %02d:%s:%s%s' % (int(hh), mi, ss or '00', frac or '')
    elif with_time:
        out += ' 00:00:00'
    return out


def input_value(kind, raw, is_null):
    """O valor digitado → o parâmetro do `?`. NULL só pelo seletor da tela; o
    campo vazio é NULL nas colunas que não são texto (não existe número
    vazio) e texto vazio nas de texto. Data aceita dd/mm/aaaa ou ISO. O
    resto vai como texto para o CAST do próprio banco, que é quem diz se o
    valor serve (e o erro dele volta para a tela)."""
    if is_null:
        return None
    s = '' if raw is None else str(raw)
    if kind == 'text':
        return s
    s = s.strip()
    if s == '':
        return None
    if kind == 'date':
        return _dmy_to_iso(s, False)
    if kind == 'timestamp':
        return _dmy_to_iso(s, True)
    if kind == 'bool':
        low = s.lower()
        if low in ('true', 't', 'yes', 'y', 'sim', 's', '1'):
            return 'true'
        if low in ('false', 'f', 'no', 'n', 'nao', 'não', '0'):
            return 'false'
        return s
    return s


def set_clause(columns_meta, values):
    """O `SET` do UPDATE e os parâmetros dele. `columns_meta`: nome → (tipo,
    kind) do CATÁLOGO; `values`: nome → {value, null} da tela. Coluna fora do
    catálogo, ou só leitura, recusa o pedido inteiro."""
    if not values:
        raise ExplorerError('nothing_to_change', 'No column to change')
    partes, params = [], []
    for nome, spec in values.items():
        meta = columns_meta.get(nome)
        if meta is None:
            raise ExplorerError('bad_column', 'Unknown column: %s' % nome, column=nome)
        tipo, kind = meta
        if kind is None:
            raise ExplorerError('readonly_column', 'Column %s cannot be edited here' % nome, column=nome)
        spec = spec if isinstance(spec, dict) else {'value': spec}
        val = input_value(kind, spec.get('value'), bool(spec.get('null')))
        if kind == 'text':
            partes.append('%s = ?' % quote_ident(nome))
        else:
            partes.append('%s = CAST(? AS %s)' % (quote_ident(nome), tipo))
        params.append(val)
    return ', '.join(partes), params


# ── JSON em colunas ─────────────────────────────────────────────────────────
# No armazém o dado mora como JSON (o `_raw` de cada registro, o `value` da
# `__meta`, o objeto inteiro no `__raw`), e o texto cru numa célula não se lê
# nem se filtra. A visão EXPANDIDA abre o JSON em linhas e colunas: objeto de
# objetos vira uma linha por chave (com a chave numa coluna), lista de
# registros uma linha por item, e o objeto aninhado dentro do registro vira
# colunas `a.b`. É só leitura: uma linha da tela já não é uma linha do banco.

EXPAND_DEPTH = 3              # níveis de "objeto de objetos" abertos em linhas
JSON_SAMPLE = 50              # valores olhados para dizer que a coluna é JSON
# Colunas que não dizem nada fora do JSON: com só elas ao lado, a tabela do
# armazém abre já expandida (`_seq` é a ordem, `key` a chave da `__meta`).
_BOOKKEEPING = {'_seq', 'key'}
_ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def parse_json(v):
    """O valor como objeto/lista, ou None se não é JSON."""
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if s[:1] in ('{', '['):
            try:
                return json.loads(s)
            except ValueError:
                return None
    return None


def json_columns(names, rows):
    """As colunas cujos valores (os primeiros `JSON_SAMPLE` não nulos) são
    todos objeto ou lista JSON — as que a tela oferece expandir."""
    out = []
    for i, nome in enumerate(names):
        vistos, ok = 0, True
        for r in rows:
            v = r[i]
            if v is None:
                continue
            if parse_json(v) is None:
                ok = False
                break
            vistos += 1
            if vistos >= JSON_SAMPLE:
                break
        if ok and vistos:
            out.append(nome)
    return out


def default_expand(names, candidates, is_store):
    """A coluna que o banco do ARMAZÉM abre expandida: só quando, fora do
    JSON, a tabela não tem nada além de ordem e chave (`_seq`/`_raw`, a
    `__meta`, o `__raw`). Dataset com colunas tipadas já se lê como está."""
    if not is_store or not candidates:
        return None
    if set(names) - set(candidates) - _BOOKKEEPING:
        return None
    for pref in ('_raw', 'value'):
        if pref in candidates:
            return pref
    return candidates[0]


def _flat(d, prefix=''):
    out = {}
    for k, x in d.items():
        nome = prefix + str(k)
        if isinstance(x, dict) and x:
            out.update(_flat(x, nome + '.'))
        elif isinstance(x, (dict, list)):
            out[nome] = json.dumps(x, ensure_ascii=False) if x else None
        else:
            out[nome] = x
    return out


def _records(v, depth=0):
    """(chaves do caminho, registro achatado) de cada linha que `v` vira."""
    if depth < EXPAND_DEPTH and isinstance(v, dict) and v and all(isinstance(x, dict) for x in v.values()):
        for k, sub in v.items():
            for keys, rec in _records(sub, depth + 1):
                yield [k] + keys, rec
        return
    if isinstance(v, list):
        if v and all(isinstance(x, dict) for x in v):
            for x in v:
                yield [], _flat(x)
        else:
            yield [], ({'value': json.dumps(v, ensure_ascii=False)} if v else {})
        return
    if isinstance(v, dict):
        yield [], _flat(v)
        return
    yield [], ({} if v is None else {'value': v})


def infer_kind(values):
    """A família de uma coluna que saiu do JSON, pelos valores dela."""
    vs = [v for v in values if v is not None and v != '']
    if not vs:
        return 'text'
    if all(isinstance(v, bool) for v in vs):
        return 'bool'
    if all(isinstance(v, int) and not isinstance(v, bool) for v in vs):
        return 'int'
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vs):
        return 'float'
    if all(isinstance(v, str) and _ISO_DATE.match(v) for v in vs):
        return 'date'
    return 'text'


def expand(names, rows, idx, cap=MAX_LIMIT):
    """A visão expandida da coluna `idx`: (nomes, linhas, cortou?). As outras
    colunas da linha vão na frente (menos o `_seq`, que é só a ordem), depois
    as chaves do caminho (`<coluna> › key`) e os campos do registro, na ordem
    em que aparecem. Campo com o nome de outra coluna leva o prefixo da
    coluna expandida. Objeto vazio (o dia sem lançamento do ledger) não vira
    linha: era uma fileira de NULL para cada dia parado, e o que se procura
    na visão expandida são os registros."""
    alvo = names[idx]
    outros = [i for i, n in enumerate(names) if i != idx and n != '_seq']
    linhas, campos, vistos, nivel, cortou = [], [], set(), 0, False
    for r in rows:
        v = parse_json(r[idx])
        for keys, rec in _records(v if v is not None else r[idx]):
            if not rec:
                continue
            if len(linhas) >= cap:
                cortou = True
                break
            linhas.append(([r[i] for i in outros], keys, rec))
            nivel = max(nivel, len(keys))
            for f in rec:
                if f not in vistos:
                    vistos.add(f)
                    campos.append(f)
        if cortou:
            break
    nomes = [names[i] for i in outros]
    usados = set(nomes)
    for j in range(nivel):
        nome = '%s › key' % alvo if nivel == 1 else '%s › key %d' % (alvo, j + 1)
        nomes.append(nome)
        usados.add(nome)
    rotulos = []
    for f in campos:
        rot = f if f not in usados else '%s.%s' % (alvo, f)
        usados.add(rot)
        rotulos.append(rot)
    nomes += rotulos
    saida = [base + keys + [None] * (nivel - len(keys)) + [rec.get(f) for f in campos]
             for base, keys, rec in linhas]
    return nomes, saida, cortou


def resolve_db(root, rel):
    """O caminho absoluto de `rel` DENTRO de `root`, ou erro. `rel` vem do
    navegador: `..`, caminho absoluto e extensão de não-banco são recusados
    antes de qualquer abertura."""
    rel = str(rel or '').strip().replace('\\', '/')
    if not rel or rel.startswith('/') or re.match(r'^[A-Za-z]:', rel):
        raise ExplorerError('bad_db', 'Invalid database path')
    partes = [p for p in rel.split('/') if p not in ('', '.')]
    if any(p == '..' for p in partes) or any(p in SKIP_DIRS for p in partes[:-1]):
        raise ExplorerError('bad_db', 'Invalid database path')
    if not partes or not partes[-1].lower().endswith(DB_EXTS):
        raise ExplorerError('bad_db', 'Invalid database path')
    raiz = os.path.normpath(os.path.abspath(root))
    alvo = os.path.normpath(os.path.join(raiz, *partes))
    if os.path.commonpath([raiz, alvo]) != raiz:
        raise ExplorerError('bad_db', 'Invalid database path')
    return alvo
