#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""convert 02_new_deals — a rotina `new deals` de cache/.

Os arquivo-dia do New Deals — NDF (Vanilla, FWD Start, Other
Publisher, Commodities), Opção (Commodities, FXO), Swap e Intrag.
É a maior fatia: um banco por produto, uma tabela por dia.

Versão AUTOCONTIDA: roda em QUALQUER máquina, sem o código do OTC Tracker por
perto. Requisito único:  pip install duckdb

    Origem : I:\Confirmation\Derivativos\OTC Tracker\Application\static\data
    Destino: ...\static\data\db   (a pasta db dentro da origem)

Uso:
    python 02_1_new_deals.py
    python 02_1_new_deals.py --dry-run
    python 02_1_new_deals.py --data-dir "D:\outra\pasta" --out-dir "D:\saida"

O ESCOPO é UMA rotina de cache\: **new deals**.

Os arquivo-dia do New Deals — NDF (Vanilla, FWD Start, Other
Publisher, Commodities), Opção (Commodities, FXO), Swap e Intrag.
É a maior fatia: um banco por produto, uma tabela por dia.

Cada produto vira um banco (o caminho inteiro de cache\ no nome —
daily_new_deals_ndf_vanilla.db, daily_b3_files_swap.db) e cada dia é uma tabela
(d_AAAAMMDD[_tag]), tipada por inferência: dd/mm/aaaa e ISO viram DATE, número
vira BIGINT/DOUBLE, zero à esquerda continua texto, '' vira NULL só em coluna
tipada, e texto sai byte a byte.

Como os bancos são um por produto, este script NÃO escreve em nada que os outros
escrevem: pode rodar ao mesmo tempo que eles.

É IDEMPOTENTE e INCREMENTAL: cada banco guarda um `_manifest` com
caminho/mtime/tamanho e só reconverte o arquivo que mudou — rodar de novo com
nada alterado não reescreve nada. `--force` reconverte tudo; `--dry-run` só
lista. Erro num arquivo não para o resto: sai no resumo do fim.

GERADO por scripts/build_duckdb_standalone.py a partir de
apps/pages/json_to_duckdb.py — não edite à mão: mexer no motor e não regerar
estes arquivos é como eles passam a discordar.
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
    # Sem registro não há o que converter — o arquivo nasce quando alguém
    # abre a tela de calendários no app. (No app este ramo cai no seed da
    # vertical de feriados; aqui não há `apps` para importar.)
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
        reg_chave = _dataset_manifest_key(REGISTRY_FILE)
        reg_st = os.stat(reg_path) if os.path.isfile(reg_path) else None
        if force or reg_st is None or not manifest_unchanged(con, reg_chave, reg_st):
            # `_com_raw`: a ORDEM do registro é a ordem das pills e do sorteio
            # de cores da tela — o leitor remonta pelo `_seq`/`_raw`.
            write_rows_table(con, q('_registry'), _com_raw(registry),
                             force_varchar=True)
            if reg_st is not None:
                manifest_record(con, reg_chave, reg_st, ['_registry'])
        else:
            stats['skipped'].append(REGISTRY_FILE)
        for cal in registry:
            nome = str(cal['name']).strip()
            arquivo = str(cal.get('file', '')).strip()
            tabela = norm_ident(nome, 'cal')
            try:
                fp = os.path.join(data_dir, arquivo) if arquivo else ''
                chave = _dataset_manifest_key(arquivo) if arquivo else ''
                existe = arquivo and os.path.isfile(fp)
                if existe:
                    st = os.stat(fp)
                    if not force and manifest_unchanged(con, chave, st):
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
                # O `_seq` é a ordem do ARQUIVO: dois feriados no mesmo dia têm
                # de voltar como o JSON os guarda — ORDER BY "date" sozinho não
                # promete isso.
                con.execute('CREATE OR REPLACE TABLE %s '
                            '("date" DATE, "title" VARCHAR, "calendar" VARCHAR, '
                            '"_seq" BIGINT)' % q(tabela))
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
                            len(data),
                        ])
                    if data:
                        con.executemany(
                            'INSERT INTO %s VALUES (?, ?, ?, ?)' % q(tabela), data)
                    n = len(data)
                    manifest_record(con, chave, st, [tabela])
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


def _tokens(texto):
    """Os tokens do nome normalizado — a unidade da poda de redundância."""
    return [t for t in norm_ident(texto, '').split('_') if t]


def _sem_data(stem, dia):
    """O nome do arquivo sem a data — o que sobra é a TAG, que é quem diz de
    que arquivo do dia se trata (DFLUXO × DPOSICAO, otm-settlement × cognos)."""
    for tok in (dia.strftime('%Y%m%d'), dia.strftime('%y%m%d'), dia.strftime('%Y-%m-%d')):
        stem = stem.replace(tok, '')
    return stem


def _tabela_dia(banco_toks, stem, dia):
    """`d_AAAAMMDD[_tag]` — a tag entra INTEIRA, ou não entra.

    Ela cai só quando é pura repetição do que o nome do banco já diz: a rotina
    cujo arquivo repete o nome dela (`pending-confirmation_20260827` dentro do
    `daily_pending_confirmation.db`) e a rotina em que a tag foi PROMOVIDA a
    banco (`otm-settlement_20260728` dentro do `daily_settlement_otm.db`). Fora
    esses dois casos ela fica como está.

    O tudo-ou-nada não é estilo: podando TOKEN A TOKEN, o `DPOSICAO-SWAP` do
    `daily_b3_files_swap.db` perderia justamente o `swap` e viraria
    `d_..._dposicao` — indistinguível de um `DPOSICAO` na mesma pasta, que é
    perda de dado sem erro nenhum."""
    tag = _tokens(_sem_data(stem, dia))
    if all(t in banco_toks for t in tag):
        tag = []
    return 'd_' + dia.strftime('%Y%m%d') + (('_' + '_'.join(tag)) if tag else '')


def _colisoes(pares):
    """Os alvos que MAIS DE UM arquivo reivindica — `[(alvo, [rel, rel])]`.

    A poda de nome deixa dois arquivos diferentes caírem na mesma tabela em
    teoria (`otm.json` e `otm-settlement.json` na mesma pasta), e o efeito
    seria a segunda conversão sobrescrevendo a primeira, com o `_drop_targets`
    da rodada seguinte apagando o que sobrou — dado perdido sem erro nenhum.
    A carga completa enxerga a pasta inteira, então é ela que denuncia."""
    por_alvo = {}
    for alvo, rel in pares:
        por_alvo.setdefault(alvo, []).append(rel)
    return [(alvo, rels) for alvo, rels in sorted(por_alvo.items()) if len(rels) > 1]


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


def _daily_db_name(rotina_parts, tag=''):
    """O nome do banco de um produto de arquivo-dia: o caminho de pastas sob
    `cache/` (sem os segmentos de data), mais a tag do nome do arquivo quando
    ela for pedida.

    Dois cuidados que só aparecem no nome: a tag entra PODADA dos tokens que a
    rotina já diz (`payrec` + `payrec_status` → `daily_payrec_status.db`, não
    `daily_payrec_payrec_status.db`), e o prefixo `daily_` não é acrescentado
    à rotina que já se chama `daily …` — senão o Daily Settlement sairia
    `daily_daily_settlement_otm.db`."""
    toks = []
    for parte in rotina_parts:
        toks.extend(_tokens(parte))
    for t in _tokens(tag):
        if t not in toks:
            toks.append(t)
    if not toks:
        toks = ['cache']
    if toks[0] != 'daily':
        toks.insert(0, 'daily')
    return '_'.join(toks) + '.db'


def _daily_rel_target(rel):
    """(banco, schema, tabela) de UM caminho relativo de arquivo-dia — ou
    `None` quando o arquivo não é um dia (ponteiros `_last`, configs avulsas).

    **A quebra é por PRODUTO**: o caminho INTEIRO de pastas sob `cache/`, sem
    os segmentos de data, nomeia o banco — cada produto tem o seu
    (`daily_new_deals_ndf_vanilla.db`, `daily_new_deals_option_fxo.db`,
    `daily_new_deals_intrag_ndf.db`) e cada dia é uma tabela dentro dele.

    Onde a rotina **não se ramifica em pastas**, quem separa os produtos é o
    NOME do arquivo, e então é a TAG dele que nomeia o banco: o Daily
    Settlement grava os dez arquivos do dia (`otm-settlement`, `ndf-cockpit`,
    `cognos`, …) na MESMA pasta, e sem isso os dez cairiam num banco só —
    justamente a rotina em que a quebra por produto é mais útil. O corte é
    pela CONTAGEM de pastas, e não por olhar os vizinhos em disco, porque
    esta função tem de ser pura sobre o caminho: o espelho vivo converte UM
    arquivo por vez e não pode depender de varrer o diretório.

    O schema é sempre `main` — o que era subárvore agora está no nome do
    banco, e um schema além disso repetiria a mesma informação."""
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
    rotina = [p for p in parts[1:-1] if not p.isdigit()] or ['cache']
    banco = _daily_db_name(rotina, _sem_data(stem, dia) if len(rotina) < 2 else '')
    return banco, 'main', _tabela_dia(set(_tokens(banco[:-3])), stem, dia)


def _novo_daily_stats():
    return {'db': 'daily_<produto>.db (um por produto)', 'dbs': [],
            'converted': [], 'skipped': [], 'errors': [], 'ignored': []}


def _convert_daily_rels(data_dir, out_dir, rels, force, stats):
    """Converte os caminhos relativos dados (já classificados como arquivo-dia),
    abrindo um banco por produto tocado."""
    cons = {}

    def _con_do_banco(nome):
        db = os.path.join(out_dir, nome)
        if db not in cons:
            os.makedirs(out_dir, exist_ok=True)
            cons[db] = duckdb.connect(db)
            ensure_manifest(cons[db])
            stats['dbs'].append(db)
        return cons[db]

    try:
        for rel in rels:
            banco, schema, tabela = _daily_rel_target(rel)
            chave = _dataset_manifest_key(rel)
            try:
                con = _con_do_banco(banco)
                st = os.stat(os.path.join(data_dir, rel.replace('/', os.sep)))
                if not force and manifest_unchanged(con, chave, st):
                    stats['skipped'].append(rel)
                    continue
                _drop_targets(con, manifest_targets(con, chave))
                if schema != 'main':
                    con.execute('CREATE SCHEMA IF NOT EXISTS %s' % q(schema))
                payload = _load_json(os.path.join(data_dir, rel.replace('/', os.sep)))
                # `raw=True` desde o flip dos arquivo-dia (§334): o `_day_json`
                # reconstrói a lista pelo `_raw`, na ordem do `_seq`.
                criadas = _convert_daily_payload(con, schema, tabela, payload, raw=True)
                manifest_record(con, chave, st, criadas)
                stats['converted'].extend('%s:%s' % (banco, c) for c in criadas)
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


def _drop_legacy_dbs(out_dir, legados, alvos, stats, motivo):
    """Apaga os bancos do desenho ANTERIOR que a quebra nova não usa mais.

    O nome que continua sendo alvo NÃO é tocado — `daily_pending_confirmation.db`
    é o mesmo banco antes e depois (a rotina nunca se ramificou), com o mesmo
    manifest, e apagá-lo custaria uma reconversão inteira sem motivo. O que
    sobra é 100% derivado dos JSONs e recriável; deixá-lo em disco é que seria
    o problema, porque quem consulta os bancos por fora do app encontraria dois
    formatos e nada dizendo qual deles é o de hoje."""
    for nome in sorted(set(legados) - set(alvos)):
        caminho = os.path.join(out_dir, nome)
        if os.path.isfile(caminho):
            os.remove(caminho)
            stats['converted'].append('%s legado removido (%s)' % (nome, motivo))


def cache_families(data_dir):
    """As rotinas de primeiro nível de `cache/` — `new deals`, `b3 files`,
    `daily settlement`, … É o eixo pelo qual a conversão se REPARTE entre
    pessoas (o standalone dividido), e ele existe aqui para o gerador e os
    scripts não terem cada um a sua lista."""
    raiz = os.path.join(data_dir, 'cache')
    try:
        return sorted(n for n in os.listdir(raiz)
                      if os.path.isdir(os.path.join(raiz, n)))
    except OSError:
        return []


def convert_daily(data_dir, out_dir, force=False, dry_run=False,
                  familias=None, excluir=None):
    """UM BANCO POR PRODUTO — a ramificação é a que a pasta `cache/` já tem.

    Cada caminho de produto (`new deals/NDF/Vanilla`, `new deals/Option/FXO`,
    `new deals/Intrag/NDF`, `b3 files/Swap`) vira o seu banco, e cada dia é
    uma tabela dentro dele; onde a rotina não se ramifica em pastas, o produto
    sai do NOME do arquivo — é o Daily Settlement, dez arquivos por dia na
    mesma pasta. Produto novo em `cache/` ganha o próprio banco sozinho, sem
    tocar aqui.

    `familias` restringe a conversão a rotinas de primeiro nível de `cache/`, e
    `excluir` é o complemento (tudo MENOS as listadas). Os dois existem para a
    carga poder ser REPARTIDA entre pessoas rodando ao mesmo tempo: cada uma
    leva a sua fatia, e como os bancos são um por produto, duas fatias nunca
    escrevem no mesmo arquivo. `excluir` é o que dá ao script "outros" a
    garantia de que rotina NOVA em `cache/` não fica sem conversor.

    Com escopo, a varredura desce SÓ na fatia — no share, onde a caminhada é
    cara, é a diferença entre ler uma rotina e ler o `cache/` inteiro. Duas
    consequências de propósito: a limpeza de bancos legados se restringe às
    famílias da fatia (apagar os de outra seria apagar o trabalho de quem está
    rodando ao lado), e a detecção de colisão só enxerga a fatia — a visão
    completa é a da carga sem escopo.
    """
    stats = _novo_daily_stats()
    raiz = os.path.join(data_dir, 'cache')
    if not os.path.isdir(raiz):
        stats['errors'].append(('cache', 'pasta cache/ ausente em %s' % data_dir))
        return stats

    todas = cache_families(data_dir)
    if familias is not None:
        alvo_fams = [f for f in todas if f in set(familias)]
        faltando = sorted(set(familias) - set(todas))
        if faltando:
            # Rotina pedida que não existe em disco não é erro (a instância pode
            # não ter aquele cache ainda), mas some sem dizer nada se ficar calada.
            stats['ignored'].extend('cache/%s (rotina ausente em disco)' % f
                                    for f in faltando)
    elif excluir is not None:
        alvo_fams = [f for f in todas if f not in set(excluir)]
    else:
        alvo_fams = todas

    rels = []
    for fam in alvo_fams:
        for dirpath, _dirs, files in sorted(os.walk(os.path.join(raiz, fam))):
            for fname in sorted(files):
                if not fname.endswith('.json'):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fname),
                                      data_dir).replace(os.sep, '/')
                if _daily_rel_target(rel) is None:
                    # Não é arquivo-dia (ponteiros como `_last`, configs
                    # avulsas): fica no JSON — some daqui e parece perda.
                    stats['ignored'].append(rel)
                else:
                    rels.append(rel)
    # Os JSONs soltos na RAIZ de `cache/` (sem pasta de rotina) só entram na
    # carga sem escopo: eles não pertencem a fatia nenhuma.
    if familias is None and excluir is None:
        for fname in sorted(os.listdir(raiz)):
            if fname.endswith('.json'):
                rel = 'cache/' + fname
                (rels if _daily_rel_target(rel) else stats['ignored']).append(rel)

    if dry_run:
        for rel in rels:
            banco, schema, tabela = _daily_rel_target(rel)
            stats['converted'].append('%s:%s.%s <- %s' % (banco, schema, tabela, rel))
        return stats

    # Os dois desenhos anteriores saem de cena: o `daily_caches.db` único e o
    # `daily_<rotina>.db` por PRIMEIRO NÍVEL de `cache/` (que trazia o produto
    # como schema). Sem isso ficariam dois formatos em disco, e o velho — que
    # nenhum espelho atualiza mais — envelheceria calado para quem consulta os
    # bancos por fora do app.
    alvos = [(_daily_rel_target(r), r) for r in rels]
    for alvo, colidem in _colisoes(alvos):
        stats['errors'].append(('%s:%s.%s' % alvo,
                                'mais de um arquivo-dia reivindica esta tabela: %s'
                                % ', '.join(colidem)))

    # Sem escopo, a limpeza é a completa. COM escopo ela se restringe às
    # famílias da fatia: o `daily_caches.db` e o banco de OUTRA rotina são
    # trabalho de quem está rodando ao lado, e apagá-los daqui seria desfazer a
    # carga alheia no meio dela.
    if familias is None and excluir is None:
        legados = {'daily_caches.db', 'daily_cache.db'}
        legados.update(_daily_db_name([f]) for f in todas)
    else:
        legados = {_daily_db_name([f]) for f in alvo_fams}
    _drop_legacy_dbs(out_dir, legados, {a[0] for a, _ in alvos},
                     stats, 'agora e um DB por produto')
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
    pasta que não é dado (`db/`).

    **UM BANCO POR ARQUIVO**, com o caminho inteiro no nome: `mappings/mt300.json`
    → `mappings_mt300.db`, `control-panel/mt300_status.json` →
    `control_panel_mt300_status.db`, `file-interpreter/termo.json` →
    `file_interpreter_termo.db`, e o JSON de raiz com o próprio nome
    (`subjacente.db`). A tabela leva o nome do arquivo, então continua legível
    de dentro do banco.

    O desenho anterior juntava a pasta inteira num banco só (`mappings.db`
    com 42 tabelas), e isso custava contenção onde ela não precisa existir: o
    espelho reconvertendo UM mapping fechava a leitura dos outros 41."""
    parts = rel.split('/')
    fname = parts[-1]
    if not fname.endswith('.json') or fname.startswith('_'):
        return None
    if parts[0] in _DATASET_SKIP_DIRS:
        return None
    if len(parts) == 1 and (fname in _DATASET_COVERED_TOP or fname.lower() in cal_files):
        return None
    stem = fname[:-5]
    db = (norm_ident('_'.join(parts[:-1] + [stem]), 'd') or 'd') + '.db'
    return db, norm_ident(stem, 't') or 't'


def _dataset_legacy_dbs(data_dir):
    """Os nomes do desenho ANTERIOR dos datasets: um banco por PASTA de
    primeiro nível, mais o `static_data.db` da raiz e o `translations.db` da
    primeira versão da cobertura (a i18n ficou fora da migração)."""
    legados = {'static_data.db', 'translations.db'}
    try:
        for nome in os.listdir(data_dir):
            if os.path.isdir(os.path.join(data_dir, nome)) \
                    and nome not in _DATASET_SKIP_DIRS:
                legados.add((norm_ident(nome, 'd') or 'static_data') + '.db')
    except OSError:
        pass
    return legados


def _novo_dataset_stats():
    return {'db': '<pasta>_<arquivo>.db (um por JSON)', 'dbs': [],
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

    UM BANCO POR ARQUIVO (`mappings_mt300.db`, `control_panel_mt300_status.db`,
    `file_interpreter_termo.db`), com uma tabela por arquivo. Payload
    lista-de-objetos vira tabela TIPADA com a coluna `_raw` (o registro exato —
    o canal do flip de leitura); payload objeto vira as tabelas das listas
    internas (também com `_raw`) mais a `_meta` chave→valor. Fica de fora o que
    tem conversor próprio (RefData/CPD, calendários, `cache/`) e a pasta
    `db/`."""
    stats = _novo_dataset_stats()
    if not os.path.isdir(data_dir):
        stats['errors'].append(('.', 'pasta de dados ausente: %s' % data_dir))
        return stats
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

    alvos = [(_dataset_rel_target(r, cal_files), r) for r in rels]
    for alvo, colidem in _colisoes(alvos):
        stats['errors'].append(('%s:%s' % alvo,
                                'mais de um JSON reivindica esta tabela: %s'
                                % ', '.join(colidem)))

    # O desenho anterior (um banco por PASTA, e a `translations.db` da primeira
    # versão da cobertura) sai de cena pela mesma razão dos arquivo-dia: o banco
    # que nenhum espelho atualiza mais é o que engana quem o consulta.
    _drop_legacy_dbs(out_dir, _dataset_legacy_dbs(data_dir), {a[0] for a, _ in alvos},
                     stats, 'agora e um DB por JSON')
    return _convert_dataset_rels(data_dir, out_dir, rels, force, stats, cal_files)

# ── CLI (caminhos fixos do share — versão standalone) ───────────────────────
import argparse
import sys

DATA_DIR_PADRAO = r'I:\Confirmation\Derivativos\OTC Tracker\Application\static\data'


def _resumo(nome, stats, houve_erro):
    print('\n== %s -> %s' % (nome, os.path.basename(stats['db'])))
    print('   convertidos: %d | inalterados: %d%s' % (
        len(stats['converted']), len(stats['skipped']),
        ' | fora deste conversor: %d' % len(stats['ignored'])
        if stats.get('ignored') else ''))
    for item in stats['converted']:
        print('   + %s' % item)
    for rel, erro in stats['errors']:
        houve_erro[0] = True
        print('   ERRO %s: %s' % (rel, str(erro).strip().splitlines()[-1]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--data-dir', default=DATA_DIR_PADRAO,
                    help='origem dos JSONs (padrão: o static\\data do share)')
    ap.add_argument('--out-dir', default=None,
                    help='destino dos .db (padrão: a pasta db dentro da origem)')
    ap.add_argument('--force', action='store_true', help='reconverte mesmo sem mudança')
    ap.add_argument('--dry-run', action='store_true', help='só lista o que converteria')
    args = ap.parse_args(argv)

    data_dir = os.path.abspath(args.data_dir)
    out_dir = os.path.abspath(args.out_dir or os.path.join(data_dir, 'db'))
    print('origem : %s' % data_dir)
    print('destino: %s' % out_dir)
    print('escopo : cache/new deals (arquivo-dia)')

    houve_erro = [False]
    _resumo('daily', convert_daily(data_dir, out_dir, force=args.force,
                                   dry_run=args.dry_run, familias=['new deals']),
            houve_erro)
    return 1 if houve_erro[0] else 0


if __name__ == '__main__':
    sys.exit(main())
