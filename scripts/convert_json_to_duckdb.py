#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""convert_json_to_duckdb.py — converte os JSONs do DATA_DIR em bancos DuckDB.

Primeiro passo da migração JSON → DuckDB: materializa os dados que hoje vivem
em JSON como bancos DuckDB tipados, ao lado dos próprios JSONs (que continuam
sendo a fonte enquanto o app não for religado). Idempotente e INCREMENTAL:
cada banco guarda um `_manifest` (caminho, mtime, tamanho) e só reconverte o
arquivo que mudou — rodar de novo com nada mudado não reescreve nada, e um
calendário/dia novo vira tabela nova sem tocar nas existentes.

Três bancos, no desenho pedido:

- **`holiday_calendars.db`** — UMA TABELA POR CALENDÁRIO (nome vindo do
  registro `holiday-calendars.json`; calendário criado pela tela ganha a
  tabela na rodada seguinte). Colunas tipadas: `date DATE`, `title`,
  `calendar`. A tabela `_registry` guarda o próprio registro (cores/CSS).
- **`reference_data.db`** — duas tabelas: `refdata` (RefData.json) e
  `counterparty_details` (CounterpartyDetails.json). TUDO VARCHAR de
  propósito: é cadastro de IDENTIFICADOR (SPN, ECI, TAX ID, conta B3), e 158
  dos 553 documentos começam com zero — um BIGINT aqui perderia o zero à
  esquerda e a chave deixaria de casar em silêncio (CLAUDE.md §7). O que é
  aninhado (CGD, CONTACTS, BANKING, NET) vira texto JSON na coluna, legível
  por `json_extract` de quem consultar.
- **`daily_caches.db`** — um banco único para as rotinas de arquivo-dia
  (`<DATA_DIR>/cache/**`), com um SCHEMA por rotina (o caminho da pasta, sem
  os segmentos de data) e UMA TABELA POR DIA (`d_AAAAMMDD[_tag]`). Payload
  lista-de-objetos vira tabela TIPADA por inferência; payload objeto vira uma
  tabela por lista interna (`d_..._summary`) mais uma `_meta` chave→valor.

A inferência de tipos otimiza a leitura sem trair o dado:

- número só vira BIGINT/DOUBLE quando TODOS os valores da coluna parseiam —
  e **número com zero à esquerda é texto** (Trade ID todo numérico não perde o
  zero); inteiro fora de 64 bits é texto;
- data reconhece ISO (`AAAA-MM-DD`) e o padrão da casa (`dd/mm/aaaa` — a
  convenção do app inteiro, CLAUDE.md §3; nunca mm/dd);
- coluna de texto preserva o valor BYTE A BYTE, espaço no fim incluído (o
  `'C '` dos códigos B3); `''` em coluna tipada vira NULL, em coluna de texto
  fica `''`.

Caminhos: a origem é o `Config.DATA_DIR` (na instância do JPM, o
`...\\Application\\static\\data` do share — nada de letra de unidade fixa no
código, CLAUDE.md §8); fora do app o fallback é o `apps/static/data` do repo.
Os `.db` saem em `<DATA_DIR>/duckdb/` por padrão (`--out-dir` muda).

Uso:
    python scripts/convert_json_to_duckdb.py [--only holidays|refdata|daily]
        [--data-dir X] [--out-dir Y] [--force] [--dry-run]

Teste de regressão: `scripts/tests/check_json_to_duckdb.py`.
"""
import argparse
import datetime
import json
import os
import re
import sys
import traceback

import duckdb

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

REGISTRY_FILE = 'holiday-calendars.json'


# ── identificadores ─────────────────────────────────────────────────────────

def norm_ident(text, prefix='t'):
    """Nome seguro de tabela/schema: `[a-z0-9_]`, nunca começando em dígito."""
    s = re.sub(r'[^0-9A-Za-z]+', '_', str(text or '').strip()).strip('_').lower()
    s = re.sub(r'_+', '_', s)
    if not s:
        return ''
    if s[0].isdigit():
        s = prefix + '_' + s
    return s


def q(ident):
    """Identificador citado — nome de COLUNA fica verbatim (com espaço, com
    acento): é o contrato com o JSON de origem, só a citação é nossa."""
    return '"' + str(ident).replace('"', '""') + '"'


# ── inferência de tipos ─────────────────────────────────────────────────────

_INT_RE = re.compile(r'^-?\d+$')
_FLOAT_RE = re.compile(r'^-?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?$|^-?\d+[eE][+-]?\d+$')
_ISO_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_BR_DATE_RE = re.compile(r'^\d{2}/\d{2}/\d{4}$')
_ISO_TS_RE = re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$')
_BR_TS_RE = re.compile(r'^\d{2}/\d{2}/\d{4} \d{2}:\d{2}(:\d{2})?$')

_SQL_TYPE = {'int': 'BIGINT', 'float': 'DOUBLE', 'bool': 'BOOLEAN',
             'date': 'DATE', 'ts': 'TIMESTAMP', 'json': 'VARCHAR', 'str': 'VARCHAR'}


def _parse_date(s):
    try:
        if _ISO_DATE_RE.match(s):
            return datetime.datetime.strptime(s, '%Y-%m-%d').date()
        if _BR_DATE_RE.match(s):
            return datetime.datetime.strptime(s, '%d/%m/%Y').date()
    except ValueError:
        return None
    return None


def _parse_ts(s):
    for rx, fmts in ((_ISO_TS_RE, ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S',
                                   '%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M')),
                     (_BR_TS_RE, ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M'))):
        if rx.match(s):
            base = s.split('.')[0]
            for fmt in fmts:
                try:
                    return datetime.datetime.strptime(base, fmt)
                except ValueError:
                    continue
    return None


def kind_of(v):
    """A que tipo este VALOR pertence — `None` = não opina (vazio)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return 'bool'
    if isinstance(v, int):
        return 'int' if -2 ** 63 <= v < 2 ** 63 else 'str'
    if isinstance(v, float):
        return 'float'
    if isinstance(v, (dict, list)):
        return 'json'
    if not isinstance(v, str):
        return 'str'
    s = v.strip()
    if s == '':
        return None
    if _INT_RE.match(s):
        corpo = s.lstrip('-')
        # Zero à esquerda é IDENTIFICADOR, não número: '007' → texto.
        if len(corpo) > 1 and corpo.startswith('0'):
            return 'str'
        try:
            n = int(s)
        except ValueError:
            return 'str'
        return 'int' if -2 ** 63 <= n < 2 ** 63 else 'str'
    if _FLOAT_RE.match(s):
        return 'float'
    if _parse_date(s) is not None:
        return 'date'
    if _parse_ts(s) is not None:
        return 'ts'
    return 'str'


def resolve_kind(kinds):
    """O tipo da COLUNA a partir dos tipos vistos. Mistura vira texto — a
    coluna com um valor fora do padrão não pode perder os demais."""
    ks = set(kinds) - {None}
    if not ks:
        return 'str'
    if ks == {'int'}:
        return 'int'
    if ks <= {'int', 'float'}:
        return 'float'
    if ks == {'bool'}:
        return 'bool'
    if ks == {'date'}:
        return 'date'
    if ks <= {'date', 'ts'}:
        return 'ts'
    if ks == {'json'}:
        return 'json'
    return 'str'


def coerce(v, kind):
    """Converte um valor para o tipo da coluna. `''` em coluna tipada é NULL
    (ausência); em coluna de texto fica `''` — e texto sai BYTE A BYTE."""
    if v is None:
        return None
    if kind == 'str':
        if isinstance(v, str):
            return v
        if isinstance(v, bool):
            return 'true' if v else 'false'
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return str(v)
    if kind == 'json':
        return json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
    if isinstance(v, str) and v.strip() == '':
        return None
    if kind == 'int':
        return int(str(v).strip()) if not isinstance(v, bool) else int(v)
    if kind == 'float':
        return float(str(v).strip()) if not isinstance(v, bool) else float(v)
    if kind == 'bool':
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in ('1', 'true', 'yes')
    if kind == 'date':
        if isinstance(v, str):
            return _parse_date(v.strip())
        return v
    if kind == 'ts':
        if isinstance(v, str):
            return _parse_ts(v.strip())
        return v
    return v


# ── escrita de tabela ───────────────────────────────────────────────────────

def write_rows_table(con, qualified, rows, force_varchar=False):
    """`CREATE OR REPLACE` de uma tabela a partir de uma lista de objetos.

    As colunas são a UNIÃO das chaves, na ordem de primeira aparição, com os
    NOMES DO JSON preservados (citados). `force_varchar=True` é o modo dos
    cadastros de identificador (RefData/CounterpartyDetails)."""
    cols = []
    vistos = set()
    for r in rows:
        for k in r:
            if k not in vistos:
                vistos.add(k)
                cols.append(k)
    if not cols:
        con.execute('CREATE OR REPLACE TABLE %s ("_empty" VARCHAR)' % qualified)
        return 0
    kinds = {}
    for c in cols:
        if force_varchar:
            kinds[c] = 'json' if any(isinstance(r.get(c), (dict, list)) for r in rows) else 'str'
        else:
            kinds[c] = resolve_kind(kind_of(r.get(c)) for r in rows)
    ddl = ', '.join('%s %s' % (q(c), _SQL_TYPE[kinds[c]]) for c in cols)
    con.execute('CREATE OR REPLACE TABLE %s (%s)' % (qualified, ddl))
    data = [[coerce(r.get(c), kinds[c]) for c in cols] for r in rows]
    if data:
        con.executemany(
            'INSERT INTO %s VALUES (%s)' % (qualified, ', '.join('?' * len(cols))), data)
    return len(data)


# ── manifest (o que torna a rodada incremental) ─────────────────────────────

def ensure_manifest(con):
    con.execute("CREATE TABLE IF NOT EXISTS _manifest ("
                "path VARCHAR PRIMARY KEY, mtime DOUBLE, fsize BIGINT, targets VARCHAR)")


def manifest_unchanged(con, rel, st):
    row = con.execute("SELECT mtime, fsize FROM _manifest WHERE path = ?", [rel]).fetchone()
    return bool(row) and abs(row[0] - st.st_mtime) < 1e-6 and row[1] == st.st_size


def manifest_targets(con, rel):
    row = con.execute("SELECT targets FROM _manifest WHERE path = ?", [rel]).fetchone()
    try:
        return json.loads(row[0]) if row and row[0] else []
    except ValueError:
        return []


def manifest_record(con, rel, st, targets):
    con.execute("INSERT OR REPLACE INTO _manifest VALUES (?, ?, ?, ?)",
                [rel, st.st_mtime, st.st_size, json.dumps(targets)])


def _drop_targets(con, targets):
    """As tabelas da conversão ANTERIOR deste arquivo: sem o drop, uma lista
    interna que saiu do payload ficaria no banco como tabela fantasma."""
    for t in targets:
        parts = [p for p in t.split('.') if p]
        con.execute('DROP TABLE IF EXISTS %s' % '.'.join(q(p) for p in parts))


# ── 1. calendários de feriado ───────────────────────────────────────────────

def _load_json(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def _holiday_registry(data_dir):
    path = os.path.join(data_dir, REGISTRY_FILE)
    if os.path.isfile(path):
        rows = _load_json(path) or []
        return [r for r in rows if isinstance(r, dict) and str(r.get('name', '')).strip()]
    # Instância que nunca abriu a tela: o registro ainda não foi semeado.
    # O seed do app é a mesma lista que a tela usaria — importado só aqui,
    # e só neste caso.
    try:
        from apps.pages.features.holidays import domain
        return [dict(r) for r in domain.CAL_SEED]
    except Exception:                                          # noqa: BLE001
        return []


def convert_holidays(data_dir, out_dir, force=False, dry_run=False):
    stats = {'db': os.path.join(out_dir, 'holiday_calendars.db'),
             'converted': [], 'skipped': [], 'errors': []}
    registry = _holiday_registry(data_dir)
    if not registry:
        stats['errors'].append((REGISTRY_FILE, 'registro de calendarios ausente/vazio'))
        return stats
    if dry_run:
        for cal in registry:
            stats['converted'].append('tabela %s <- %s' % (norm_ident(cal['name']),
                                                           cal.get('file', '')))
        return stats
    os.makedirs(out_dir, exist_ok=True)
    con = duckdb.connect(stats['db'])
    try:
        ensure_manifest(con)
        write_rows_table(con, q('_registry'), registry, force_varchar=True)
        for cal in registry:
            nome = str(cal['name']).strip()
            arquivo = str(cal.get('file', '')).strip()
            tabela = norm_ident(nome, 'cal')
            try:
                fp = os.path.join(data_dir, arquivo) if arquivo else ''
                existe = arquivo and os.path.isfile(fp)
                if existe:
                    st = os.stat(fp)
                    if not force and manifest_unchanged(con, arquivo, st):
                        stats['skipped'].append(arquivo)
                        continue
                elif con.execute(
                        "SELECT count(*) FROM information_schema.tables "
                        "WHERE table_schema = 'main' AND table_name = ?",
                        [tabela]).fetchone()[0]:
                    # Calendário ainda sem arquivo de feriados: a tabela vazia
                    # já nasceu numa rodada anterior — recriá-la a cada rodada
                    # só faria o resumo dizer "convertido" sem nada ter mudado.
                    stats['skipped'].append(arquivo or nome)
                    continue
                con.execute('CREATE OR REPLACE TABLE %s '
                            '("date" DATE, "title" VARCHAR, "calendar" VARCHAR)' % q(tabela))
                n = 0
                if existe:
                    feriados = _load_json(fp) or []
                    data = []
                    for h in feriados:
                        if not isinstance(h, dict):
                            continue
                        data.append([
                            _parse_date(str(h.get('date', '')).strip()),
                            str(h.get('title', h.get('name', '')) or ''),
                            str(h.get('calendar', '') or nome),
                        ])
                    if data:
                        con.executemany(
                            'INSERT INTO %s VALUES (?, ?, ?)' % q(tabela), data)
                    n = len(data)
                    manifest_record(con, arquivo, st, [tabela])
                stats['converted'].append('%s (%d feriados)' % (tabela, n))
            except Exception:                                  # noqa: BLE001
                stats['errors'].append((arquivo or nome, traceback.format_exc()))
    finally:
        con.close()
    return stats


# ── 2. RefData + CounterpartyDetails ────────────────────────────────────────

_REFDATA_TABLES = (('RefData.json', 'refdata'),
                   ('CounterpartyDetails.json', 'counterparty_details'))


def convert_refdata(data_dir, out_dir, force=False, dry_run=False):
    stats = {'db': os.path.join(out_dir, 'reference_data.db'),
             'converted': [], 'skipped': [], 'errors': []}
    if dry_run:
        stats['converted'] = ['tabela %s <- %s' % (t, f) for f, t in _REFDATA_TABLES]
        return stats
    os.makedirs(out_dir, exist_ok=True)
    con = duckdb.connect(stats['db'])
    try:
        ensure_manifest(con)
        for arquivo, tabela in _REFDATA_TABLES:
            fp = os.path.join(data_dir, arquivo)
            try:
                if not os.path.isfile(fp):
                    stats['errors'].append((arquivo, 'arquivo ausente'))
                    continue
                st = os.stat(fp)
                if not force and manifest_unchanged(con, arquivo, st):
                    stats['skipped'].append(arquivo)
                    continue
                rows = _load_json(fp) or []
                rows = [r for r in rows if isinstance(r, dict)]
                n = write_rows_table(con, q(tabela), rows, force_varchar=True)
                manifest_record(con, arquivo, st, [tabela])
                stats['converted'].append('%s (%d linhas)' % (tabela, n))
            except Exception:                                  # noqa: BLE001
                stats['errors'].append((arquivo, traceback.format_exc()))
    finally:
        con.close()
    return stats


# ── 3. rotinas de arquivo-dia ───────────────────────────────────────────────

_FNAME_YMD = re.compile(r'(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)')
_FNAME_ISO = re.compile(r'(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)')


def _dia_de(rel_parts, stem):
    """A DATA de um arquivo-dia: primeiro o caminho `AAAA/MM/DD`, depois o
    `AAAAMMDD`/`AAAA-MM-DD` do nome. `None` = não é arquivo-dia."""
    for i in range(len(rel_parts) - 2):
        a, m, d = rel_parts[i:i + 3]
        if (len(a), len(m), len(d)) == (4, 2, 2) and (a + m + d).isdigit():
            try:
                return datetime.date(int(a), int(m), int(d))
            except ValueError:
                pass
    for rx, monta in ((_FNAME_YMD, None), (_FNAME_ISO, None)):
        mo = rx.search(stem)
        if mo:
            try:
                return datetime.date(int(mo.group(1)), int(mo.group(2)), int(mo.group(3)))
            except ValueError:
                continue
    return None


def _tabela_dia(schema, stem, dia):
    """`d_AAAAMMDD[_tag]` — o que sobra do nome depois de tirar a data é a tag
    (distingue DFLUXO de DPOSICAO no mesmo dia); tag que repete o schema cai."""
    tag = stem
    for tok in (dia.strftime('%Y%m%d'), dia.strftime('%y%m%d'), dia.strftime('%Y-%m-%d')):
        tag = tag.replace(tok, '')
    tag = norm_ident(tag, '')
    if tag == schema:
        tag = ''
    return 'd_' + dia.strftime('%Y%m%d') + (('_' + tag) if tag else '')


def _lista_de_objetos(v):
    return isinstance(v, list) and all(isinstance(x, dict) for x in v)


def _convert_daily_payload(con, schema, tabela, payload):
    """Grava o payload de UM arquivo-dia; devolve os nomes das tabelas criadas."""
    alvo = lambda t: '%s.%s' % (q(schema), q(t))               # noqa: E731
    criadas = []
    if _lista_de_objetos(payload):
        write_rows_table(con, alvo(tabela), payload)
        criadas.append('%s.%s' % (schema, tabela))
    elif isinstance(payload, list):
        write_rows_table(con, alvo(tabela),
                         [{'value': v} for v in payload], force_varchar=True)
        criadas.append('%s.%s' % (schema, tabela))
    elif isinstance(payload, dict):
        meta = {}
        for k, v in payload.items():
            if _lista_de_objetos(v) and v:
                sub = '%s_%s' % (tabela, norm_ident(k, 'k'))
                write_rows_table(con, alvo(sub), v)
                criadas.append('%s.%s' % (schema, sub))
            else:
                meta[k] = v
        if meta:
            sub = tabela + '__meta'
            write_rows_table(
                con, alvo(sub),
                [{'key': k, 'value': json.dumps(v, ensure_ascii=False)}
                 for k, v in meta.items()], force_varchar=True)
            criadas.append('%s.%s' % (schema, sub))
    else:
        write_rows_table(con, alvo(tabela), [{'value': payload}], force_varchar=True)
        criadas.append('%s.%s' % (schema, tabela))
    return criadas


def convert_daily(data_dir, out_dir, force=False, dry_run=False):
    stats = {'db': os.path.join(out_dir, 'daily_caches.db'),
             'converted': [], 'skipped': [], 'errors': [], 'ignored': []}
    raiz = os.path.join(data_dir, 'cache')
    if not os.path.isdir(raiz):
        stats['errors'].append(('cache', 'pasta cache/ ausente em %s' % data_dir))
        return stats
    con = None
    if not dry_run:
        os.makedirs(out_dir, exist_ok=True)
        con = duckdb.connect(stats['db'])
        ensure_manifest(con)
    try:
        for dirpath, _dirs, files in sorted(os.walk(raiz)):
            for fname in sorted(files):
                if not fname.endswith('.json'):
                    continue
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, data_dir).replace(os.sep, '/')
                parts = rel.split('/')
                stem = fname[:-5]
                dia = None if fname.startswith('_') else _dia_de(parts[1:-1], stem)
                if dia is None:
                    # Não é arquivo-dia (ponteiros como `_last`, configs
                    # avulsas): fica no JSON — some daqui e parece perda.
                    stats['ignored'].append(rel)
                    continue
                # O schema é a ROTINA: o caminho sem `cache/` e sem os
                # segmentos de data.
                schema = norm_ident(
                    '_'.join(p for p in parts[1:-1] if not p.isdigit()), 's') or 'cache'
                tabela = _tabela_dia(schema, stem, dia)
                if dry_run:
                    stats['converted'].append('%s.%s <- %s' % (schema, tabela, rel))
                    continue
                try:
                    st = os.stat(full)
                    if not force and manifest_unchanged(con, rel, st):
                        stats['skipped'].append(rel)
                        continue
                    _drop_targets(con, manifest_targets(con, rel))
                    con.execute('CREATE SCHEMA IF NOT EXISTS %s' % q(schema))
                    payload = _load_json(full)
                    criadas = _convert_daily_payload(con, schema, tabela, payload)
                    manifest_record(con, rel, st, criadas)
                    stats['converted'].extend(criadas)
                except Exception:                              # noqa: BLE001
                    stats['errors'].append((rel, traceback.format_exc()))
    finally:
        if con is not None:
            con.close()
    return stats


# ── CLI ─────────────────────────────────────────────────────────────────────

def _default_data_dir():
    try:
        sys.path.insert(0, ROOT)
        from apps.config import Config
        return Config.DATA_DIR
    except Exception:                                          # noqa: BLE001
        # Fora do app (ex.: macOS sem OTC_SHARED_DRIVE_ROOT): a pasta do repo.
        return os.path.join(ROOT, 'apps', 'static', 'data')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--data-dir', default=None, help='origem dos JSONs (padrão: Config.DATA_DIR)')
    ap.add_argument('--out-dir', default=None, help='destino dos .db (padrão: <data-dir>/duckdb)')
    ap.add_argument('--only', choices=('holidays', 'refdata', 'daily'), default=None)
    ap.add_argument('--force', action='store_true', help='reconverte mesmo sem mudança')
    ap.add_argument('--dry-run', action='store_true', help='só lista o que converteria')
    args = ap.parse_args(argv)

    data_dir = os.path.abspath(args.data_dir or _default_data_dir())
    out_dir = os.path.abspath(args.out_dir or os.path.join(data_dir, 'duckdb'))
    print('origem : %s' % data_dir)
    print('destino: %s' % out_dir)

    conversores = {'holidays': convert_holidays, 'refdata': convert_refdata,
                   'daily': convert_daily}
    escolhidos = [args.only] if args.only else list(conversores)
    houve_erro = False
    for nome in escolhidos:
        stats = conversores[nome](data_dir, out_dir, force=args.force, dry_run=args.dry_run)
        print('\n== %s -> %s' % (nome, os.path.basename(stats['db'])))
        print('   convertidos: %d | inalterados: %d%s' % (
            len(stats['converted']), len(stats['skipped']),
            ' | fora do padrão-dia: %d' % len(stats['ignored'])
            if stats.get('ignored') else ''))
        for item in stats['converted']:
            print('   + %s' % item)
        for rel, erro in stats['errors']:
            houve_erro = True
            print('   ERRO %s: %s' % (rel, erro.strip().splitlines()[-1]))
    return 1 if houve_erro else 0


if __name__ == '__main__':
    sys.exit(main())
