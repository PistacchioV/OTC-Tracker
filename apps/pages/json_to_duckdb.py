# -*- coding: utf-8 -*-
"""O motor da conversão JSON → DuckDB (fase 2 da migração: HANDOFF §324–§326).

Era o corpo do `scripts/convert_json_to_duckdb.py` e virou módulo do app
porque agora ele tem DOIS chamadores: o script (a carga completa, rodada à
mão) e o **espelho vivo** (`apps/pages/duck_mirror.py`), que reconverte na
hora o JSON que acabou de ser gravado. Duplicar a regra nos dois seria criar
duas respostas para "como este JSON vira tabela".

Materializa os dados que hoje vivem em JSON como bancos DuckDB tipados, ao
lado dos próprios JSONs (que continuam sendo a fonte de LEITURA enquanto os
consumidores não forem religados — fase 3). Idempotente e INCREMENTAL: cada
banco guarda um `_manifest` (caminho, mtime, tamanho) e só reconverte o
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
- **`daily_<rotina>.db`** — UM BANCO POR ROTINA de arquivo-dia, seguindo a
  ramificação que `<DATA_DIR>/cache/` já tem (`daily_new_deals.db`,
  `daily_pending_confirmation.db`, `daily_b3_files.db`, …). A subárvore da
  rotina (produto, família B3) vira SCHEMA dentro do banco, e cada dia é UMA
  TABELA (`d_AAAAMMDD[_tag]`). Payload lista-de-objetos vira tabela TIPADA
  por inferência; payload objeto vira uma tabela por lista interna
  (`d_..._summary`) mais uma `_meta` chave→valor. Rotina nova em `cache/`
  ganha o próprio banco sozinha.

A inferência de tipos otimiza a leitura sem trair o dado:

- número só vira BIGINT/DOUBLE quando TODOS os valores da coluna parseiam —
  e **número com zero à esquerda é texto** (Trade ID todo numérico não perde o
  zero); inteiro fora de 64 bits é texto;
- data reconhece ISO (`AAAA-MM-DD`) e o padrão da casa (`dd/mm/aaaa` — a
  convenção do app inteiro, CLAUDE.md §3; nunca mm/dd);
- coluna de texto preserva o valor BYTE A BYTE, espaço no fim incluído (o
  `'C '` dos códigos B3); `''` em coluna tipada vira NULL, em coluna de texto
  fica `''`.

Os caminhos chegam EXPLÍCITOS (`data_dir`, `out_dir`) — quem resolve os
padrões (`Config.DATA_DIR` → `Config.DATABASE_DIR`) é cada chamador; este
módulo não monta caminho de dado por conta própria.

Teste de regressão: `scripts/tests/check_json_to_duckdb.py`.
"""
import datetime
import json
import os
import re
import traceback

import duckdb

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
        # O `_registry` também entra no manifest: é o que permite ao leitor
        # DB-first (`duck_read`, fase 3) provar que a tabela reflete o
        # `holiday-calendars.json` COMO ELE ESTÁ — registro vindo do seed (sem
        # arquivo em disco) fica fora do manifest de propósito, e o leitor cai
        # no caminho JSON, que é quem semeia.
        reg_path = os.path.join(data_dir, REGISTRY_FILE)
        reg_st = os.stat(reg_path) if os.path.isfile(reg_path) else None
        if force or reg_st is None or not manifest_unchanged(con, REGISTRY_FILE, reg_st):
            write_rows_table(con, q('_registry'), registry, force_varchar=True)
            if reg_st is not None:
                manifest_record(con, REGISTRY_FILE, reg_st, ['_registry'])
        else:
            stats['skipped'].append(REGISTRY_FILE)
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

# Versão do FORMATO das tabelas de registro no manifest. O `_raw` (o registro
# original como texto JSON, coluna a mais ao lado das tipadas) é o canal de
# FIDELIDADE do flip de leitura: reconstruir o registro pelas colunas
# adicionaria chave com NULL onde o JSON não tinha chave nenhuma — e o
# `_contacts_norm` do CounterpartyDetails decide "contato legado" justamente
# pela AUSÊNCIA da chave. O `_seq` (posição no arquivo) é a ORDEM: o DuckDB
# não promete ordem de inserção no SELECT, e a lista reconstruída tem de sair
# na ordem do JSON — as telas exibem na ordem do arquivo. Mudou o formato?
# Muda o sufixo: o manifest antigo deixa de casar, o leitor cai no JSON e o
# espelho reconverte no formato novo — upgrade sem script.
_REFDATA_FMT = '#raw2'


def _refdata_manifest_key(arquivo):
    return arquivo + _REFDATA_FMT


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
            chave = _refdata_manifest_key(arquivo)
            try:
                if not os.path.isfile(fp):
                    # Ausente não é falha: o par (RefData × CounterpartyDetails)
                    # nem sempre nasce junto, e o espelho vivo converte os dois
                    # a cada aviso — o que não existe ainda só fica para depois.
                    stats['skipped'].append(arquivo + ' (ausente)')
                    continue
                st = os.stat(fp)
                if not force and manifest_unchanged(con, chave, st):
                    stats['skipped'].append(arquivo)
                    continue
                rows = _load_json(fp) or []
                rows = [r for r in rows if isinstance(r, dict)]
                # `_seq`/`_raw` = ordem e registro EXATOS do JSON — as colunas
                # que o flip de leitura consome; as tipadas ficam para o SQL.
                n = write_rows_table(con, q(tabela), _com_raw(rows), force_varchar=True)
                manifest_record(con, chave, st, [tabela])
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
    for rx in (_FNAME_YMD, _FNAME_ISO):
        mo = rx.search(stem)
        if mo:
            try:
                return datetime.date(int(mo.group(1)), int(mo.group(2)), int(mo.group(3)))
            except ValueError:
                continue
    return None


def _tabela_dia(redundantes, stem, dia):
    """`d_AAAAMMDD[_tag]` — o que sobra do nome depois de tirar a data é a tag
    (distingue DFLUXO de DPOSICAO no mesmo dia); tag que só repete a rotina ou
    o schema (`pending-confirmation_20260827.json` dentro do
    `daily_pending_confirmation.db`) cai."""
    tag = stem
    for tok in (dia.strftime('%Y%m%d'), dia.strftime('%y%m%d'), dia.strftime('%Y-%m-%d')):
        tag = tag.replace(tok, '')
    tag = norm_ident(tag, '')
    if tag in redundantes:
        tag = ''
    return 'd_' + dia.strftime('%Y%m%d') + (('_' + tag) if tag else '')


def _lista_de_objetos(v):
    return isinstance(v, list) and all(isinstance(x, dict) for x in v)


def _com_raw(rows):
    """As linhas com `_seq` (a posição no arquivo — a ordem da reconstrução) e
    `_raw` (o registro EXATO como texto JSON) — os canais do flip de leitura."""
    out = []
    for i, r in enumerate(rows):
        if '_raw' in r:
            out.append(r)
        else:
            out.append({**r, '_seq': i, '_raw': json.dumps(r, ensure_ascii=False)})
    return out


def _convert_daily_payload(con, schema, tabela, payload, raw=False):
    """Grava o payload de UM arquivo-dia; devolve os nomes das tabelas criadas.

    `raw=True` (os DATASETS — cadastros e configs) acrescenta a coluna `_raw`
    em toda tabela lista-de-objetos, para o flip de leitura ter o registro
    exato; os arquivo-dia ficam sem ela de propósito (volume)."""
    alvo = lambda t: '%s.%s' % (q(schema), q(t))               # noqa: E731
    criadas = []
    if _lista_de_objetos(payload):
        write_rows_table(con, alvo(tabela), _com_raw(payload) if raw else payload)
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
                write_rows_table(con, alvo(sub), _com_raw(v) if raw else v)
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


def _daily_db_name(familia):
    return 'daily_' + (norm_ident(familia, 'r') or 'cache') + '.db'


def _daily_rel_target(rel):
    """(família, schema, tabela) de UM caminho relativo de arquivo-dia — ou
    `None` quando o arquivo não é um dia (ponteiros `_last`, configs avulsas).

    A família (1º nível sob `cache/`) nomeia o BANCO; o resto do caminho —
    sem os segmentos de data — é o schema dentro dele."""
    parts = rel.split('/')
    if len(parts) < 2 or parts[0] != 'cache':
        return None
    fname = parts[-1]
    if not fname.endswith('.json') or fname.startswith('_'):
        return None
    stem = fname[:-5]
    dia = _dia_de(parts[1:-1], stem)
    if dia is None:
        return None
    familia = parts[1] if len(parts) >= 3 else 'cache'
    schema = norm_ident(
        '_'.join(p for p in parts[2:-1] if not p.isdigit()), 's') or 'main'
    tabela = _tabela_dia({schema, norm_ident(familia, 'r')}, stem, dia)
    return familia, schema, tabela


def _novo_daily_stats():
    return {'db': 'daily_<rotina>.db (um por rotina)', 'dbs': [],
            'converted': [], 'skipped': [], 'errors': [], 'ignored': []}


def _convert_daily_rels(data_dir, out_dir, rels, force, stats):
    """Converte os caminhos relativos dados (já classificados como arquivo-dia),
    abrindo um banco por família tocada."""
    cons = {}

    def _con_da_familia(familia):
        db = os.path.join(out_dir, _daily_db_name(familia))
        if db not in cons:
            os.makedirs(out_dir, exist_ok=True)
            cons[db] = duckdb.connect(db)
            ensure_manifest(cons[db])
            stats['dbs'].append(db)
        return cons[db]

    try:
        for rel in rels:
            familia, schema, tabela = _daily_rel_target(rel)
            try:
                con = _con_da_familia(familia)
                st = os.stat(os.path.join(data_dir, rel.replace('/', os.sep)))
                if not force and manifest_unchanged(con, rel, st):
                    stats['skipped'].append(rel)
                    continue
                _drop_targets(con, manifest_targets(con, rel))
                if schema != 'main':
                    con.execute('CREATE SCHEMA IF NOT EXISTS %s' % q(schema))
                payload = _load_json(os.path.join(data_dir, rel.replace('/', os.sep)))
                criadas = _convert_daily_payload(con, schema, tabela, payload)
                manifest_record(con, rel, st, criadas)
                stats['converted'].extend(
                    '%s:%s' % (_daily_db_name(familia), c) for c in criadas)
            except Exception:                                  # noqa: BLE001
                stats['errors'].append((rel, traceback.format_exc()))
    finally:
        for con in cons.values():
            con.close()
    return stats


def convert_daily_files(data_dir, out_dir, rels, force=False):
    """Converte SÓ os arquivos-dia dados (caminhos relativos ao `data_dir`).

    É a porta do espelho vivo (`duck_mirror`): o JSON que acabou de ser gravado
    reconverte sozinho, sem varrer a árvore inteira de `cache/` — que no share
    da instância é uma caminhada cara. Caminho que não é arquivo-dia volta em
    `ignored`, nunca em erro."""
    stats = _novo_daily_stats()
    validos = []
    for rel in (rels or []):
        rel = str(rel).replace(os.sep, '/').strip('/')
        (validos if _daily_rel_target(rel) else stats['ignored']).append(rel)
    return _convert_daily_rels(data_dir, out_dir, validos, force, stats)


def convert_daily(data_dir, out_dir, force=False, dry_run=False):
    """UM BANCO POR ROTINA — a ramificação é a que a pasta `cache/` já tem.

    Cada família de primeiro nível (`new deals`, `pending-confirmation`,
    `b3 files`, …) vira o seu `daily_<rotina>.db`; a subárvore dela (produto,
    família B3) vira SCHEMA dentro do banco, e cada dia é uma tabela. Rotina
    nova em `cache/` ganha o próprio banco sozinha, sem tocar aqui."""
    stats = _novo_daily_stats()
    raiz = os.path.join(data_dir, 'cache')
    if not os.path.isdir(raiz):
        stats['errors'].append(('cache', 'pasta cache/ ausente em %s' % data_dir))
        return stats

    # O desenho anterior (um `daily_caches.db` único, com a rotina como
    # schema) sai de cena: dois formatos em disco seriam duas respostas para
    # a mesma pergunta. O arquivo é 100% derivado dos JSONs — recriável.
    legado = os.path.join(out_dir, 'daily_caches.db')
    if not dry_run and os.path.isfile(legado):
        os.remove(legado)
        stats['converted'].append('daily_caches.db legado removido (agora é um DB por rotina)')

    rels = []
    for dirpath, _dirs, files in sorted(os.walk(raiz)):
        for fname in sorted(files):
            if not fname.endswith('.json'):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fname), data_dir).replace(os.sep, '/')
            if _daily_rel_target(rel) is None:
                # Não é arquivo-dia (ponteiros como `_last`, configs avulsas):
                # fica no JSON — some daqui e parece perda.
                stats['ignored'].append(rel)
            else:
                rels.append(rel)

    if dry_run:
        for rel in rels:
            familia, schema, tabela = _daily_rel_target(rel)
            stats['converted'].append('%s:%s.%s <- %s'
                                      % (_daily_db_name(familia), schema, tabela, rel))
        return stats
    return _convert_daily_rels(data_dir, out_dir, rels, force, stats)



# ── 4. os DEMAIS JSONs (mappings, cadastros B3, templates, configs) ─────────

# A mesma versão de formato dos cadastros: os datasets carregam `_seq`/`_raw`
# nas listas de registros, e o leitor DB-first depende dos dois.
_DATASET_FMT = _REFDATA_FMT


def _dataset_manifest_key(rel):
    return rel + _DATASET_FMT


_DATASET_COVERED_TOP = frozenset({'RefData.json', 'CounterpartyDetails.json',
                                  REGISTRY_FILE})
# `db`/`duckdb` são os próprios bancos; `cache` é dos conversores de
# arquivo-dia; `translations` FICA EM JSON de propósito — são os dicionários
# de i18n que o navegador consome e que vivem versionados como código, os
# únicos JSONs que permanecem fora da migração (decisão de 2026-08-27).
_DATASET_SKIP_DIRS = frozenset({'db', 'duckdb', 'cache', 'translations'})


def _holiday_files(data_dir):
    """Os arquivos de calendário do registro — cobertos pelo `convert_holidays`,
    nunca pelos datasets (seriam duas tabelas para o mesmo arquivo)."""
    try:
        rows = _load_json(os.path.join(data_dir, REGISTRY_FILE)) or []
        return {str(r.get('file', '') or '').strip().lower()
                for r in rows if isinstance(r, dict)} - {''}
    except Exception:                                          # noqa: BLE001
        return set()


def _dataset_rel_target(rel, cal_files):
    """(banco, tabela) de um JSON avulso — ou `None` quando ele é de OUTRO
    conversor (RefData/CPD, registro e arquivos de calendário, `cache/`) ou de
    pasta que não é dado (`db/`). A ramificação é a da pasta: raiz →
    `static_data.db`; `mappings/` → `mappings.db`; `file-interpreter/` →
    `file_interpreter.db`; `tickets/`, `translations/`, `control-panel/` idem —
    pasta nova ganha o próprio banco sozinha."""
    parts = rel.split('/')
    fname = parts[-1]
    if not fname.endswith('.json') or fname.startswith('_'):
        return None
    if parts[0] in _DATASET_SKIP_DIRS:
        return None
    if len(parts) == 1:
        if fname in _DATASET_COVERED_TOP or fname.lower() in cal_files:
            return None
        return 'static_data.db', norm_ident(fname[:-5], 't') or 't'
    db = (norm_ident(parts[0], 'd') or 'static_data') + '.db'
    tabela = norm_ident('_'.join(parts[1:])[:-5], 't') or 't'
    return db, tabela


def _novo_dataset_stats():
    return {'db': '<pasta>.db (um por pasta; raiz = static_data.db)', 'dbs': [],
            'converted': [], 'skipped': [], 'errors': [], 'ignored': []}


def _convert_dataset_rels(data_dir, out_dir, rels, force, stats, cal_files):
    cons = {}

    def _con(db):
        path = os.path.join(out_dir, db)
        if path not in cons:
            os.makedirs(out_dir, exist_ok=True)
            cons[path] = duckdb.connect(path)
            ensure_manifest(cons[path])
            stats['dbs'].append(path)
        return cons[path]

    try:
        for rel in rels:
            alvo = _dataset_rel_target(rel, cal_files)
            if alvo is None:
                stats['ignored'].append(rel)
                continue
            db, tabela = alvo
            chave = _dataset_manifest_key(rel)
            try:
                con = _con(db)
                st = os.stat(os.path.join(data_dir, rel.replace('/', os.sep)))
                if not force and manifest_unchanged(con, chave, st):
                    stats['skipped'].append(rel)
                    continue
                _drop_targets(con, manifest_targets(con, chave))
                payload = _load_json(os.path.join(data_dir, rel.replace('/', os.sep)))
                criadas = _convert_daily_payload(con, 'main', tabela, payload, raw=True)
                manifest_record(con, chave, st, criadas)
                stats['converted'].extend('%s:%s' % (db, c) for c in criadas)
            except Exception:                                  # noqa: BLE001
                stats['errors'].append((rel, traceback.format_exc()))
    finally:
        for con in cons.values():
            con.close()
    return stats


def convert_dataset_files(data_dir, out_dir, rels, force=False):
    """Converte SÓ os JSONs dados — a porta do espelho vivo, como a dos
    arquivo-dia. Caminho que é de outro conversor volta em `ignored`."""
    stats = _novo_dataset_stats()
    limpos = [str(r).replace(os.sep, '/').strip('/') for r in (rels or [])]
    return _convert_dataset_rels(data_dir, out_dir, limpos, force, stats,
                                 _holiday_files(data_dir))


def convert_datasets(data_dir, out_dir, force=False, dry_run=False):
    """TODOS os demais JSONs do DATA_DIR — a cobertura total da migração.

    Um banco por PASTA de primeiro nível (a raiz vira `static_data.db`), uma
    tabela por arquivo. Payload lista-de-objetos vira tabela TIPADA com a
    coluna `_raw` (o registro exato — o canal do flip de leitura); payload
    objeto vira as tabelas das listas internas (também com `_raw`) mais a
    `_meta` chave→valor. Fica de fora o que tem conversor próprio (RefData/
    CPD, calendários, `cache/`) e a pasta `db/`."""
    stats = _novo_dataset_stats()
    if not os.path.isdir(data_dir):
        stats['errors'].append(('.', 'pasta de dados ausente: %s' % data_dir))
        return stats
    # A primeira versão desta cobertura convertia `translations/` também; a
    # pasta ficou FORA da migração e o banco derivado sai de cena.
    legado = os.path.join(out_dir, 'translations.db')
    if not dry_run and os.path.isfile(legado):
        os.remove(legado)
        stats['converted'].append('translations.db legado removido (i18n fica em JSON)')
    cal_files = _holiday_files(data_dir)
    rels = []
    # `os.walk` SEM `sorted(...)` por fora: o sorted consumiria o generator
    # inteiro antes da poda de `dirs[:]` fazer efeito, e a árvore de `cache/`
    # — que é dos conversores de arquivo-dia — seria varrida à toa (no share,
    # uma caminhada cara). A ordem determinística vem de ordenar in place.
    for dirpath, dirs, files in os.walk(data_dir):
        rel_dir = os.path.relpath(dirpath, data_dir).replace(os.sep, '/')
        if rel_dir == '.':
            dirs[:] = sorted(d for d in dirs if d not in _DATASET_SKIP_DIRS)
        else:
            dirs.sort()
        for fname in sorted(files):
            if not fname.endswith('.json'):
                continue
            rel = fname if rel_dir == '.' else rel_dir + '/' + fname
            if _dataset_rel_target(rel, cal_files) is None:
                stats['ignored'].append(rel)
            else:
                rels.append(rel)
    if dry_run:
        for rel in rels:
            db, tabela = _dataset_rel_target(rel, cal_files)
            stats['converted'].append('%s:%s <- %s' % (db, tabela, rel))
        return stats
    return _convert_dataset_rels(data_dir, out_dir, rels, force, stats, cal_files)
