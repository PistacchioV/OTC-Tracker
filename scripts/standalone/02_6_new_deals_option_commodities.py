#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""convert 02_new_deals_option_commodities — a rotina `new deals/Option/Commodities` de cache/.

A opção de mercadoria.

Versão AUTOCONTIDA: roda em QUALQUER máquina, sem o código do OTC Tracker por
perto. Requisito único:  pip install duckdb

    Origem : o static\data do share — o UNC
             (\\Nawest.ad.jpmorganchase.com\lac\BRA\intra\...) ou a letra I:,
             o que existir na máquina. `--data-dir` manda em qualquer caso.
    Destino: ...\static\data\db   (a pasta db dentro da origem)

Uso:
    python 02_6_new_deals_option_commodities.py
    python 02_6_new_deals_option_commodities.py --dry-run
    python 02_6_new_deals_option_commodities.py --data-dir "D:\outra\pasta" --out-dir "D:\saida"

O ESCOPO é UM bloco de cache\: **new deals/Option/Commodities**.

A opção de mercadoria.

Cada produto vira um banco e a pasta db\ ESPELHA a árvore de cache\
(db\cache\new deals\NDF\Vanilla.db, db\cache\b3 files\Swap.db); só
ano/mês/dia não viram pasta — cada dia é uma tabela
(d_AAAAMMDD[_tag]), tipada por inferência: dd/mm/aaaa e ISO viram DATE, número
vira BIGINT/DOUBLE, zero à esquerda continua texto, '' vira NULL só em coluna
tipada, e texto sai byte a byte.

Como os bancos são um por produto, este script NÃO escreve em nada que os outros
escrevem: pode rodar ao mesmo tempo que eles.

Se nesta instância o bloco ainda for grande demais, `--bloco NOME` desce mais um
nível (ex.: `--bloco Vanilla`). Ele SUBSTITUI o escopo desta fatia — não rode a
fatia inteira em paralelo com um bloco dela.

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

def nomes_sql(chaves):
    """Os NOMES de coluna para as chaves do JSON, na ordem, sem colisão.

    **O identificador do DuckDB é insensível a CAIXA, mesmo citado.** A chave do
    JSON é preservada tal e qual — é o contrato com o arquivo de origem —, mas
    duas chaves que só diferem no caso são a MESMA coluna para o banco, e a
    segunda estoura com *"Column with name X already exists"*. Foi o
    `DPOSICAO-SWAP`: o layout da B3 repete nomes por perna e a grafia não é
    estável, então o arquivo tem `PU Inicial` e `Pu inicial`. O `_b3_export_json`
    já desempata o repetido EXATO (`Pu inicial` → `Pu inicial_2`), mas ele
    compara com caixa e por isso deixa passar o par acima.

    A saída é o mesmo `_N` que o app usa para o repetido, com duas regras que
    fazem a diferença:

      - o candidato é conferido contra TODAS as chaves do arquivo, não só
        contra as já emitidas — senão o desempate de `Pu inicial` produziria
        `Pu inicial_2`, que é uma coluna de VERDADE do mesmo arquivo, e a
        colisão voltaria pela outra ponta;
      - **a coluna é RENOMEADA, nunca descartada.** Uma perna do swap sumindo
        da tabela não daria erro nenhum — é a falha que menos parece falha, e o
        `_raw` ao lado ainda a teria, o que faria o banco discordar de si
        mesmo."""
    reservados = {str(k).lower() for k in chaves}
    usados = set()
    nomes = []
    for k in chaves:
        nome = str(k)
        if nome.lower() in usados:
            n = 2
            while ('%s_%d' % (nome, n)).lower() in usados or \
                  ('%s_%d' % (nome, n)).lower() in reservados:
                n += 1
            nome = '%s_%d' % (nome, n)
        usados.add(nome.lower())
        nomes.append(nome)
    return nomes


def write_rows_table(con, qualified, rows, force_varchar=False):
    """`CREATE OR REPLACE` de uma tabela a partir de uma lista de objetos.

    As colunas são a UNIÃO das chaves, na ordem de primeira aparição, com os
    NOMES DO JSON preservados (citados) — só o que colidiria por CAIXA ganha
    sufixo, ver `nomes_sql`. `force_varchar=True` é o modo dos cadastros de
    identificador (RefData/CounterpartyDetails)."""
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
    # A CHAVE continua sendo a do JSON (é por ela que o valor é lido); o que o
    # desempate muda é só o NOME da coluna no banco.
    ddl = ', '.join('%s %s' % (q(n), _SQL_TYPE[kinds[c]])
                    for c, n in zip(cols, nomes_sql(cols)))
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
    que arquivo do dia se trata (DFLUXO × DPOSICAO, otm-settlement × cognos).

    Os separadores que sobram nas pontas caem junto: tirar a data de
    `otm-settlement_20260728` deixa um `_` no fim, e ele viraria o nome de
    arquivo `otm-settlement_.db`."""
    for tok in (dia.strftime('%Y%m%d'), dia.strftime('%y%m%d'), dia.strftime('%Y-%m-%d')):
        stem = stem.replace(tok, '')
    return stem.strip(' _-')


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


def _convert_daily_payload(con, schema, tabela, payload, raw=False,
                           meta_tabela=None):
    """Grava o payload de UM arquivo-dia; devolve os nomes das tabelas criadas.

    `raw=True` (os DATASETS — cadastros e configs) acrescenta a coluna `_raw`
    em toda tabela lista-de-objetos, para o flip de leitura ter o registro
    exato; os arquivo-dia ficam sem ela de propósito (volume).

    `meta_tabela` nomeia a tabela chave→valor de um payload-OBJETO em vez do
    `<tabela>__meta` de sempre. Serve ao arquivo `.meta.json`, que já É
    metadado: sem isso a tabela dele sairia `d_20260826_meta__meta`, gaguejando
    o mesmo nome duas vezes. O nome é PASSADO, e não deduzido do sufixo de
    `tabela` — deduzir faria uma tabela legítima terminada em `_meta` cair na
    mesma regra."""
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
            sub = meta_tabela or (tabela + '__meta')
            write_rows_table(
                con, alvo(sub),
                [{'key': k, 'value': json.dumps(v, ensure_ascii=False)}
                 for k, v in meta.items()], force_varchar=True)
            criadas.append('%s.%s' % (schema, sub))
    else:
        write_rows_table(con, alvo(tabela), [{'value': payload}], force_varchar=True)
        criadas.append('%s.%s' % (schema, tabela))
    return criadas


# Caracteres que o Windows não aceita em nome de arquivo/pasta. O resto do nome
# de origem é PRESERVADO (espaço e hífen inclusive): a pasta `db/` espelha a
# árvore do `DATA_DIR`, e é isso que faz achar o banco de uma tela ser o mesmo
# gesto de achar o JSON dela.
_INVALIDO_NO_NOME = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def _nome_seguro(texto, padrao='sem_nome'):
    """Um segmento de caminho válido, preservando o nome de origem."""
    s = _INVALIDO_NO_NOME.sub('_', str(texto or '')).strip().rstrip('.')
    return s or padrao


# O sufixo do anexo de um arquivo-dia. Ele não é um produto: vai para o banco do
# arquivo que anota, com `_meta` no nome da tabela.
_META_SUFIXO = '.meta'


def _daily_db_name(rotina_parts, tag=''):
    """O CAMINHO do banco de um produto de arquivo-dia, relativo ao `db/`.

    A pasta espelha a árvore de `cache/` e o último segmento vira o ARQUIVO:
    `cache/new deals/NDF/Vanilla` → `cache/new deals/NDF/Vanilla.db`. Antes
    tudo isso era achatado num nome só (`daily_new_deals_ndf_vanilla.db`) e os
    133 bancos caíam soltos na mesma pasta — achar o banco de uma tela virava
    caça ao nome. Com a árvore espelhada, quem sabe onde está o JSON sabe onde
    está o banco.

    Quando a rotina NÃO se ramifica em pastas, quem separa os produtos é a TAG
    do nome do arquivo, e é ela que vira o arquivo dentro da pasta da rotina
    (`cache/daily settlement/otm-settlement.db`). Tag ausente — ou que só
    repete o nome da rotina, como o `pending-confirmation_AAAAMMDD` — não
    ganha pasta própria: seria `cache/pending-confirmation/pending-confirmation.db`,
    uma pasta para um arquivo só."""
    partes = [_nome_seguro(p) for p in rotina_parts if str(p or '').strip()]
    if not partes:
        partes = ['cache']
    tag = str(tag or '').strip()
    if tag and _tokens(tag) != _tokens(partes[-1]):
        # A rotina de um nível só: a tag é quem distingue os produtos, então ela
        # é o arquivo e a rotina é a pasta.
        return '/'.join(partes + [_nome_seguro(tag)]) + '.db'
    return '/'.join(partes) + '.db'


def _daily_rel_target(rel):
    """(caminho do banco, schema, tabela) de UM caminho relativo de arquivo-dia
    — ou `None` quando o arquivo não é um dia (ponteiros `_last`, configs
    avulsas).

    **A quebra é por PRODUTO, e a pasta `db/` espelha a árvore de `cache/`**:
    `cache/new deals/NDF/Vanilla/2026/07/…` vira
    `db/cache/new deals/NDF/Vanilla.db`, com cada dia como uma tabela dentro
    dele. Os segmentos de ANO/MÊS/DIA não viram pasta — eles já são a tabela.

    Onde a rotina **não se ramifica em pastas**, quem separa os produtos é o
    NOME do arquivo, e então é a TAG dele que vira o banco dentro da pasta da
    rotina: o Daily Settlement grava os dez arquivos do dia (`otm-settlement`,
    `ndf-cockpit`, `cognos`, …) na MESMA pasta `AAAA/MM/DD`, e sem isso os dez
    cairiam num banco só — justamente a rotina em que a quebra é mais útil. O
    corte é pela CONTAGEM de pastas, e não por olhar os vizinhos em disco,
    porque esta função tem de ser pura sobre o caminho: o espelho vivo converte
    UM arquivo por vez e não pode depender de varrer o diretório.

    O **`.meta.json` acompanha o arquivo dele**: `cognos_20260826.meta.json` vai
    para o banco do `cognos`, na tabela `d_20260826_meta`. Ele não é um produto
    — é o anexo do arquivo-dia daquele produto —, e num banco separado quem
    consultasse o Cognos teria de juntar dois. Antes ele saía num banco próprio
    e com o nome torto (`cognos_.meta.db`): a data está no MEIO do nome
    (`cognos_20260826.meta`), então tirá-la deixa um `_` que não está na ponta
    e o `strip` das pontas não alcança.

    O schema é sempre `main` — o que era subárvore agora está no CAMINHO, e um
    schema além disso repetiria a mesma informação."""
    parts = rel.split('/')
    if len(parts) < 2 or parts[0] != 'cache':
        return None
    fname = parts[-1]
    if not fname.endswith('.json') or fname.startswith('_'):
        return None
    stem = fname[:-5]
    meta = stem.endswith(_META_SUFIXO)
    if meta:
        stem = stem[:-len(_META_SUFIXO)]
    dia = _dia_de(parts[1:-1], stem)
    if dia is None:
        return None
    rotina = ['cache'] + [p for p in parts[1:-1] if not p.isdigit()]
    banco = _daily_db_name(rotina, _sem_data(stem, dia) if len(rotina) < 3 else '')
    # A tabela deixa de repetir o que o CAMINHO já diz.
    tabela = _tabela_dia(set(_tokens(banco[:-3].replace('/', '_'))), stem, dia)
    return banco, 'main', (tabela + '_meta') if meta else tabela


def dia_do_rel(rel):
    """A DATA de um caminho relativo de arquivo-dia, ou `None`.

    É a mesma leitura que o `_daily_rel_target` faz para montar a tabela, aqui
    exposta sozinha porque a JANELA de conversão precisa dela antes de abrir
    banco nenhum — filtrar por `os.stat` seria filtrar pelo dia em que o
    arquivo foi ESCRITO, e um arquivo-dia antigo reescrito hoje (um backfill,
    uma cópia do share) entraria na janela dizendo respeito a outro ano."""
    parts = rel.split('/')
    if len(parts) < 2 or parts[0] != 'cache':
        return None
    fname = parts[-1]
    if not fname.endswith('.json') or fname.startswith('_'):
        return None
    return _dia_de(parts[1:-1], fname[:-5])


def data_de_corte(meses, hoje=None):
    """O primeiro dia da janela: `meses` meses para trás a partir de hoje.
    `meses` 0 ou negativo = SEM janela (`None`), que é a carga completa.

    O recuo é por MÊS de calendário, não por 30×N dias: pedir 12 meses em
    29/08 tem de dar 29/08 do ano anterior, e não uma data cinco dias adiante
    que deixaria de fora justamente o começo do mês mais antigo."""
    if not meses or int(meses) <= 0:
        return None
    hoje = hoje or datetime.date.today()
    meses = int(meses)
    ano = hoje.year - (meses // 12)
    mes = hoje.month - (meses % 12)
    if mes <= 0:
        ano, mes = ano - 1, mes + 12
    dia = hoje.day
    while dia > 28:                     # 31/03 menos 1 mês não existe em fev.
        try:
            return datetime.date(ano, mes, dia)
        except ValueError:
            dia -= 1
    return datetime.date(ano, mes, dia)


def _novo_daily_stats():
    # `avisos` é o que o resumo IMPRIME sem ser erro — hoje, a rotina pedida que
    # não existe em disco. `ignored` continua sendo contagem (os `_last` e as
    # configs avulsas são muitos e não interessam um a um).
    return {'db': 'daily_<produto>.db (um por produto)', 'dbs': [],
            'converted': [], 'skipped': [], 'errors': [], 'ignored': [],
            'avisos': [], 'antigos': []}


def _convert_daily_rels(data_dir, out_dir, rels, force, stats):
    """Converte os caminhos relativos dados (já classificados como arquivo-dia),
    abrindo um banco por produto tocado."""
    cons = {}

    def _con_do_banco(nome):
        # `nome` é um CAMINHO relativo (`cache/new deals/NDF/Vanilla.db`): a
        # pasta espelha a árvore de origem, então é ela que precisa existir.
        db = os.path.join(out_dir, *nome.split('/'))
        if db not in cons:
            os.makedirs(os.path.dirname(db), exist_ok=True)
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
                # Num arquivo `.meta.json` a tabela chave→valor é a do próprio
                # arquivo: ele já é o metadado, e o `__meta` de sempre repetiria
                # a palavra.
                criadas = _convert_daily_payload(
                    con, schema, tabela, payload, raw=True,
                    meta_tabela=tabela if rel.endswith(_META_SUFIXO + '.json') else None)
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
    """Apaga os bancos dos desenhos ANTERIORES que a quebra nova não usa mais.

    A remoção é por LISTA DE NOMES DERIVADOS, nunca por varredura de `*.db` na
    pasta: o `DATABASE_DIR` é a casa de TODOS os bancos do app — o de usuários,
    o de notificações, os três do Pending Confirmation, os dois da esteira, o
    do Onboarding —, e uma varredura ali apagaria dado que nada recria.

    O nome que continua sendo alvo NÃO é tocado: seria o mesmo banco, com o
    mesmo manifest, e apagá-lo custaria uma reconversão inteira sem motivo. O
    que sobra é 100% derivado dos JSONs e recriável; deixá-lo em disco é que
    seria o problema, porque quem consulta os bancos por fora do app
    encontraria dois formatos e nada dizendo qual deles é o de hoje."""
    # O que decide não é o NOME, é o ARQUIVO. O JSON de raiz passou a manter a
    # caixa do original (`Subjacente.db`) e o nome legado dele era normalizado
    # (`subjacente.db`): em macOS e Windows os dois nomes são o MESMO arquivo, e
    # remover o "legado" apagaria o banco recém-criado — a leitura seguinte
    # cairia no JSON sem ninguém entender por quê. No Linux são dois arquivos de
    # verdade, e aí o antigo TEM de sair, senão fica um banco órfão que nada
    # atualiza. `samefile` responde certo nos dois.
    por_nome = {}
    for a in alvos:
        por_nome.setdefault(str(a).lower(),
                            os.path.join(out_dir, *str(a).split('/')))
    for nome in sorted(set(legados)):
        caminho = os.path.join(out_dir, *nome.split('/'))
        if not os.path.isfile(caminho):
            continue
        gemeo = por_nome.get(str(nome).lower())
        try:
            if gemeo and os.path.isfile(gemeo) and os.path.samefile(gemeo, caminho):
                continue
        except OSError:                                        # noqa: BLE001
            pass
        if str(nome) in {str(a) for a in alvos}:
            continue
        os.remove(caminho)
        stats['converted'].append('%s legado removido (%s)' % (nome, motivo))


def _legacy_flat_name(rel_db):
    """O nome ACHATADO que este banco tinha no desenho anterior — o de quando
    os 133 bancos moravam soltos na raiz do `db/`.

    `cache/new deals/NDF/Vanilla.db` → `daily_new_deals_ndf_vanilla.db`;
    `cache/daily settlement/otm-settlement.db` → `daily_settlement_otm.db`;
    `mappings/mt300.db` → `mappings_mt300.db`. É assim que a carga completa
    sabe o que remover **sem varrer a pasta** — e não varrer é o que protege os
    outros bancos do app, que moram no mesmo `DATABASE_DIR` e que nada recria.
    """
    partes = rel_db[:-3].split('/')
    if partes[0] != 'cache':
        return (norm_ident('_'.join(partes), 'd') or 'd') + '.db'
    # No arquivo-dia, o desenho anterior era `daily_` + os tokens da rotina,
    # mais os da TAG que a rotina ainda não dizia. Quem é tag e quem é rotina
    # sai da PROFUNDIDADE, pela mesma regra que gerou o caminho: com um nível
    # de rotina o último segmento é a tag; com dois ou mais, é rotina.
    corpo, tag = partes[1:], ''
    if len(partes) == 3:
        corpo, tag = partes[1:2], partes[2]
    toks = []
    for p in corpo:
        toks.extend(_tokens(p))
    for t in _tokens(tag):
        if t not in toks:
            toks.append(t)
    if not toks:
        toks = ['cache']
    if toks[0] != 'daily':
        toks.insert(0, 'daily')
    return '_'.join(toks) + '.db'


def chave_familia(nome):
    """A rotina de `cache/` reduzida à sua identidade, para casar o escopo
    pedido com a pasta que está em disco.

    O nome da pasta é escrito por quem criou a árvore, e as instâncias não
    concordam na grafia: a dev tem `b3 files` e o share do JPM tem `B3 Files`.
    Casando por string exata, o `02_2_b3_files.py` não achava a pasta e saía
    dizendo `convertidos: 0` — a fatia inteira ficava de fora sem erro nenhum.
    Pior, o `99_outros` exclui pela MESMA lista: com a comparação exata ele não
    reconhecia a rotina como coberta e a convertia junto, e os dois escreviam no
    mesmo banco se rodassem em paralelo, que é justamente o que a divisão
    promete que não acontece."""
    return '_'.join(_tokens(nome))


# As rotinas que ganham um script PRÓPRIO nos dois splits — o `scripts/convert/`
# (que usa o Config) e o `scripts/standalone/` (que não usa). A lista mora aqui
# porque os dois a consomem: escrita em cada um, uma rotina acrescentada num
# lado ficaria coberta só pelo `99_outros` do outro, e a diferença apareceria
# como uma fatia que demora muito mais do que a irmã — nunca como erro.
# O que NÃO está aqui não fica de fora: o `99_outros` de cada split cobre o
# resto, e é essa a rede que faz esta lista poder envelhecer sem perda.
#
# As duas rotinas grandes — New Deals e B3 Files — entram REPARTIDAS ATÉ O
# PRODUTO, que é a folha da árvore (abaixo dele já vem AAAA/MM/DD) e a unidade
# em que cada banco é escrito. Como bloco único elas eram o gargalo: as outras
# quatro rotinas terminam em minutos e o resto da equipe ficava esperando a
# maior. Repartir só até `new deals/NDF` ainda deixava o Vanilla — o maior
# arquivo-dia do app — junto com os outros três.
#
# Uma pasta de produto que a instância não tenha vira um aviso e sai limpa; e o
# que NÃO estiver nesta lista não fica de fora: o `99_outros` poda por CAMINHO,
# então um produto novo (`new deals/NDF/Asian`) cai nele. Para descer ainda
# mais numa instância específica há o `--bloco`, que não precisa de arquivo
# novo.
ROTINAS_CACHE = (
    ('new deals/NDF/Vanilla', 'O termo de moeda vanilla — costuma ser o maior\n'
                              'arquivo-dia do app inteiro.'),
    ('new deals/NDF/FwdStart', 'O NDF FWD Start. A pasta é SEM espaço — `FWD Start`\n'
                              'é o rótulo da tela, e a pasta com espaço nunca\n'
                              'existiu (se alguma instância a tiver, o 99_outros a\n'
                              'converte, porque a poda é por caminho).'),
    ('new deals/NDF/OtherPublisher', 'O NDF Other Publisher.'),
    ('new deals/NDF/Commodities', 'O termo de mercadoria.'),
    ('new deals/Option/FXO', 'A opção de câmbio.'),
    ('new deals/Option/Commodities', 'A opção de mercadoria.'),
    ('new deals/Swap/Rates', 'Os swaps de taxa.'),
    ('new deals/Swap/Commodities', 'Os swaps de mercadoria.'),
    ('new deals/Intrag/NDF', 'O termo da Intrag.'),
    ('new deals/Intrag/Option', 'A opção da Intrag.'),
    ('new deals/Intrag/Swap', 'O swap da Intrag.'),
    ('b3 files/NDF', 'As posições e fluxos de NDF que a rotina Save CETIP Files\n'
                     'grava (DPOSICAO, DFLUXO). Aqui o produto já é o primeiro\n'
                     'nível: o ano vem logo abaixo, não há o que repartir mais.'),
    ('b3 files/Option', 'Idem, para as opções.'),
    ('b3 files/Swap', 'Idem, para os swaps — costuma ser o maior dos quatro.'),
    ('b3 files/Operations', 'O Operations B3 — a lista de operações registradas.'),
    # O Daily Settlement NÃO se ramifica em pastas: os arquivos do dia convivem
    # em AAAA/MM/DD e quem separa os produtos é o NOME. Por isso o escopo aqui
    # é a TAG do arquivo — cada um vem de uma fonte diferente e é uma fatia.
    # A lista não precisa ser exaustiva: arquivo com tag fora dela cai no
    # `99_outros`, que exclui por tag do mesmo jeito.
    ('daily settlement/otm-settlement', 'O OTM Settlements.'),
    ('daily settlement/ndf-cockpit', 'O NDF Cockpit.'),
    ('daily settlement/operations-b3', 'O arquivo DERIVADO que a página\n'
                                       'Operations B3 lê: o merge das operações\n'
                                       'JPM e MGT (`_ob_src`) mais o que a tela\n'
                                       'edita. Não confundir com os dois\n'
                                       'arquivos de ORIGEM ao lado.'),
    ('daily settlement/operacoes-jpm', 'As operações do Banco J.P. Morgan, como\n'
                                       'importadas — uma das duas origens do\n'
                                       'operations-b3.'),
    ('daily settlement/operacoes-mgt', 'Idem, as da MGT.'),
    ('daily settlement/eventos-swap-jpm', 'Os eventos de swap do Banco.'),
    ('daily settlement/eventos-swap-mgt', 'Idem, os da MGT.'),
    ('daily settlement/latam-desk-position', 'O Latam Desk Position.'),
    ('daily settlement/swap-kapital-hybrids', 'O Swap Kapital Hybrids.'),
    ('daily settlement/cognos', 'O Cognos.'),
    ('daily settlement/br-onshore-settlements', 'O BR Onshore Settlements.'),
    ('daily settlement/other-products-summary', 'O Other Products Summary — e o\n'
                                                'overlay de status do aviso, que\n'
                                                'mora no `.meta` ao lado.'),
    ('pending-confirmation', 'Os snapshots diários do Pending Confirmation.'),
    ('payrec', 'O histórico diário da reconciliação de Pay/Rec.'),
    # Cada reconciliação tem a SUA pasta em `cache/reconciliation/` e o seu
    # banco, então cada uma é uma fatia — `reconciliation` inteira seria o único
    # escopo da lista a produzir mais de um banco, e a fatia que roda três
    # recons em série é a que não termina enquanto duas pessoas esperam. A
    # recon de COMITENTES não está aqui de propósito: ela não tem cache JSON,
    # grava direto no `matching_comitentes.db`.
    ('reconciliation/fxo', 'A reconciliação de FXO (DPOSICAO × Athena EOD).'),
    ('reconciliation/cgd', 'A reconciliação de CGD (lista do FEP × posição da B3).'),
    ('reconciliation/payrec', 'Os caches por data da reconciliação de Pay/Rec —\n'
                              'irmãos do histórico que mora em `cache/payrec`.'),
)


def chave_escopo(caminho):
    """Um escopo de `cache/` como TUPLA de segmentos normalizados.

    O escopo é um CAMINHO (`new deals/NDF`), e não só a rotina de primeiro
    nível: as duas rotinas grandes se repartem por dentro, e sem isso a fatia do
    New Deals seguiria sendo um bloco só enquanto quatro pessoas esperam por
    ela. Comparar por tupla — e não pela string colada — é o que impede
    `new deals/NDF` de casar com uma rotina chamada `new dealsndf`."""
    partes = str(caminho or '').replace('\\', '/').split('/')
    return tuple(chave_familia(p) for p in partes if str(p).strip())


def _subpastas(caminho):
    try:
        return sorted(n for n in os.listdir(caminho)
                      if os.path.isdir(os.path.join(caminho, n)))
    except OSError:
        return []


def tag_do_rel(rel):
    """A TAG de um arquivo-dia, normalizada — o que sobra do NOME depois de
    tirar a data (`otm-settlement_20260826.json` → `otm_settlement`).

    É ela que separa os produtos onde a rotina **não se ramifica em pastas**: o
    Daily Settlement grava os dez arquivos do dia na MESMA `AAAA/MM/DD`, e sem
    a tag os dez seriam um bloco só — justamente a rotina em que repartir mais
    ajuda, porque cada arquivo vem de uma fonte diferente. O `.meta` é podado
    junto: ele acompanha o arquivo que anota, não é um produto."""
    parts = rel.split('/')
    fname = parts[-1]
    if not fname.endswith('.json'):
        return ''
    stem = fname[:-5]
    if stem.endswith(_META_SUFIXO):
        stem = stem[:-len(_META_SUFIXO)]
    dia = _dia_de(parts[1:-1], stem)
    if dia is None:
        return ''
    return '_'.join(_tokens(_sem_data(stem, dia)))


def resolver_escopo(raiz_cache, escopo):
    """(caminho REAL sob `cache/`, tag ou None, None) — ou (None, None, aviso).

    Desce segmento a segmento casando pelo nome NORMALIZADO, porque a grafia da
    pasta é de quem criou a árvore e as instâncias não concordam (a dev tem
    `b3 files`, o share tem `B3 Files`). O caminho devolvido é o que está em
    DISCO, que é o que a pasta `db/` espelha.

    **O último segmento pode ser uma TAG de arquivo em vez de uma pasta**
    (`daily settlement/otm-settlement`), e é assim que a rotina que não se
    ramifica em pastas também se reparte. Um escopo é, então, sempre o CAMINHO
    do banco que ele produz — `db/cache/daily settlement/otm-settlement.db` —,
    o que dispensa uma segunda sintaxe para dizer a mesma coisa.

    O aviso diz o que ele ACHOU **no nível em que parou** — não a listagem da
    raiz. Um escopo de dois segmentos falha quase sempre no segundo, e mostrar
    as rotinas de primeiro nível ali responderia a pergunta errada."""
    partes = [p for p in str(escopo or '').replace('\\', '/').split('/') if p.strip()]
    atual, reais = raiz_cache, []
    for i, p in enumerate(partes):
        alvo = chave_familia(p)
        achou = next((n for n in _subpastas(atual) if chave_familia(n) == alvo), None)
        if achou is None:
            # Último segmento sem pasta correspondente: é TAG de arquivo. Não se
            # valida aqui — só a varredura sabe que tags existem, e validar
            # custaria descer a árvore duas vezes. Tag que não casa com nada vira
            # aviso DEPOIS, com a lista das tags encontradas.
            if i == len(partes) - 1 and reais:
                return '/'.join(reais), alvo, None
            onde = '/'.join(reais) or 'cache'
            return None, None, ('cache/%s: bloco ausente em disco. Dentro de %s há: %s'
                                % (escopo, onde,
                                   ', '.join(_subpastas(atual)) or '(nenhuma pasta)'))
        reais.append(achou)
        atual = os.path.join(atual, achou)
    return '/'.join(reais), None, None


def cache_families(data_dir):
    """As rotinas de primeiro nível de `cache/` — `new deals`, `b3 files`,
    `daily settlement`, … É o eixo pelo qual a conversão se REPARTE entre
    pessoas (os dois splits), e ele existe aqui para o gerador e os
    scripts não terem cada um a sua lista."""
    raiz = os.path.join(data_dir, 'cache')
    try:
        return sorted(n for n in os.listdir(raiz)
                      if os.path.isdir(os.path.join(raiz, n)))
    except OSError:
        return []


def convert_daily(data_dir, out_dir, force=False, dry_run=False,
                  familias=None, excluir=None, desde=None):
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

    **`desde` é a JANELA**: arquivo-dia anterior a essa data não é convertido e
    volta em `stats['antigos']`, que o resumo IMPRIME como contagem. Ela existe
    porque a carga completa no share leva horas de rede, e o dado recente é o
    que a mesa consulta — o histórico antigo entra numa segunda passada, feita
    com `desde=None`. Ela é DECLARADA, nunca implícita: um recorte silencioso
    faria a segunda passada parecer desnecessária.

    A data sai do CAMINHO do arquivo (`dia_do_rel`), não do `mtime`: o mtime é
    quando o arquivo foi escrito, e o dia de 2024 recopiado para o share este
    mês entraria na janela como se fosse recente.
    """
    stats = _novo_daily_stats()
    raiz = os.path.join(data_dir, 'cache')
    if not os.path.isdir(raiz):
        stats['errors'].append(('cache', 'pasta cache/ ausente em %s' % data_dir))
        return stats

    todas = cache_families(data_dir)
    # Os escopos RESOLVIDOS em disco (a grafia real), e as famílias que este run
    # cobre por INTEIRO — que é o que autoriza mexer no banco legado da rotina.
    escopos, fams_inteiras = [], set()
    if familias is not None:
        for pedido in familias:
            real, tag, aviso = resolver_escopo(raiz, pedido)
            if real is None:
                # Bloco pedido que não existe em disco não é erro (a instância
                # pode não ter aquele cache) — mas o aviso vai em `avisos`, que
                # o resumo IMPRIME. Contado só como número, ele saía como um
                # `fora deste conversor: 1` indistinguível de um ponteiro
                # `_last`, e a pessoa lia "não havia nada a fazer" onde a fatia
                # inteira ficou de fora.
                stats['avisos'].append(aviso)
                continue
            escopos.append((real, tag, pedido))
            # A família só é "inteira" quando o escopo é ela e mais nada: com
            # sub-bloco ou com tag, esta passada cobre um pedaço, e o banco
            # legado da rotina guarda também o pedaço dos outros.
            if tag is None and len(chave_escopo(real)) == 1:
                fams_inteiras.add(real)
    elif excluir is not None:
        escopos = None                      # varre o cache/ inteiro, podando
    else:
        # (caminho real, tag, pedido) — a mesma forma do ramo com escopo, para
        # a varredura não ter dois formatos.
        escopos = [(f, None, f) for f in todas]
        fams_inteiras = set(todas)

    rels = []
    fora_tag = set()             # só o `99_outros` a preenche (exclusão por tag)
    if escopos is None:
        # O `99_outros`: desce o `cache/` inteiro PODANDO os escopos cobertos.
        # A poda é por caminho, e é o que faz a rede de segurança funcionar nos
        # dois níveis — uma rotina NOVA (`cache/equity`) e um bloco novo dentro
        # de uma coberta (`cache/new deals/Equity`) caem os dois aqui, enquanto
        # `cache/new deals/NDF`, que tem script próprio, é podado.
        # Os cobertos por PASTA podam a descida; os cobertos por TAG não podem
        # (a pasta é a mesma de todos), então viram um filtro por arquivo.
        fora_dir = set()
        for pedido in excluir:
            real, tag, _av = resolver_escopo(raiz, pedido)
            if real is None:
                # O que não existe nesta instância não precisa ser excluído — e
                # não podar por ele é o que mantém a rede de segurança honesta.
                continue
            if tag is None:
                fora_dir.add(chave_escopo(real))
            else:
                fora_tag.add((chave_escopo(real), tag))
        caminhados = []
        for dirpath, dirs, files in os.walk(raiz):
            rel_dir = os.path.relpath(dirpath, raiz).replace(os.sep, '/')
            base = () if rel_dir == '.' else chave_escopo(rel_dir)
            dirs[:] = [d for d in sorted(dirs)
                       if (base + (chave_familia(d),)) not in fora_dir]
            if rel_dir != '.':
                caminhados.append((dirpath, files))
        andar = caminhados
    else:
        andar = [(dp, fs, e) for e in escopos
                 for dp, _d, fs in sorted(os.walk(os.path.join(raiz, *e[0].split('/'))))]

    vistos_por_tag = {}          # escopo com tag → tags que ele encontrou
    for entrada in andar:
        dirpath, files = entrada[0], entrada[1]
        esc = entrada[2] if len(entrada) > 2 else None
        for fname in sorted(files):
            if not fname.endswith('.json'):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fname),
                                  data_dir).replace(os.sep, '/')
            if _daily_rel_target(rel) is None:
                # Não é arquivo-dia (ponteiros como `_last`, configs
                # avulsas): fica no JSON — some daqui e parece perda.
                stats['ignored'].append(rel)
                continue
            if esc is not None and esc[1] is not None:
                # Escopo por TAG: a pasta é a mesma de todos os produtos, então
                # o corte é por arquivo. As tags vistas ficam guardadas para o
                # aviso — tag que não casa com nada precisa dizer quais existem.
                achada = tag_do_rel(rel)
                vistos_por_tag.setdefault(esc[2], set()).add(achada)
                if achada != esc[1]:
                    continue
            if fora_tag:
                # O diretório do arquivo é o do DIA (`daily settlement/2026/08/26`)
                # e o do escopo é o da rotina (`daily settlement`): a comparação é
                # por PREFIXO. Comparando os dois inteiros, nenhuma exclusão por
                # tag casava — e o `99_outros` reconvertia tudo o que as fatias
                # já tinham feito, dois processos no mesmo banco.
                _d = chave_escopo(os.path.relpath(dirpath, raiz).replace(os.sep, '/'))
                _t = tag_do_rel(rel)
                if any(_t == t and _d[:len(base_esc)] == base_esc
                       for base_esc, t in fora_tag):
                    continue
            if desde and (dia_do_rel(rel) or datetime.date.min) < desde:
                stats['antigos'].append(rel)
            else:
                rels.append(rel)

    for pedido, achadas in sorted(vistos_por_tag.items()):
        alvo = next((e[1] for e in escopos if e[2] == pedido), None)
        if alvo is not None and alvo not in achadas:
            stats['avisos'].append(
                'cache/%s: nenhum arquivo com essa tag. Tags encontradas: %s'
                % (pedido, ', '.join(sorted(t for t in achadas if t)) or '(nenhuma)'))
    # Os JSONs soltos na RAIZ de `cache/` (sem pasta de rotina) só entram na
    # carga sem escopo: eles não pertencem a fatia nenhuma.
    if familias is None and excluir is None:
        for fname in sorted(os.listdir(raiz)):
            if fname.endswith('.json'):
                rel = 'cache/' + fname
                if _daily_rel_target(rel) is None:
                    stats['ignored'].append(rel)
                elif desde and (dia_do_rel(rel) or datetime.date.min) < desde:
                    stats['antigos'].append(rel)
                else:
                    rels.append(rel)

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

    # COM JANELA não se apaga banco nenhum. Todo legado — o `daily_caches.db`,
    # o `daily_<rotina>.db` e o nome ACHATADO por produto — guarda o histórico
    # INTEIRO daquele recorte, e esta passada escreve só doze meses. Apagá-lo
    # aqui trocaria um banco de formato velho e completo por um de formato novo
    # e parcial: uma perda que a segunda passada desfaz, mas só depois das
    # horas em que o histórico não existiria em lugar nenhum. Quem limpa é a
    # passada sem janela, que é a que de fato substitui o que estava lá.
    if desde:
        legados = set()
    else:
        # Sem escopo, a limpeza é a completa. COM escopo ela se restringe às
        # famílias da fatia: o `daily_caches.db` e o banco de OUTRA rotina são
        # trabalho de quem está rodando ao lado, e apagá-los daqui seria
        # desfazer a carga alheia no meio dela.
        #
        # O legado da ROTINA (`daily_b3_files.db`) só sai quando esta passada
        # cobre a família INTEIRA. Numa fatia de sub-bloco (`b3 files/NDF`) ele
        # guarda também o Option, o Swap e o Operations, que quem está rodando
        # ao lado ainda vai converter — apagá-lo daqui é apagar o trabalho
        # deles antes de ele existir no formato novo.
        if familias is None and excluir is None:
            legados = {'daily_caches.db', 'daily_cache.db'}
            legados.update('daily_' + (norm_ident(f, 'r') or 'cache') + '.db'
                           for f in todas)
        else:
            legados = {'daily_' + (norm_ident(f, 'r') or 'cache') + '.db'
                       for f in fams_inteiras}
        # E os nomes ACHATADOS do desenho seguinte, o de quando cada produto já
        # tinha o seu banco mas todos moravam soltos na raiz do `db/`.
        legados.update(_legacy_flat_name(a[0]) for a, _ in alvos)
    _drop_legacy_dbs(out_dir, legados, {a[0] for a, _ in alvos},
                     stats, 'agora a pasta db/ espelha a arvore de origem')
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

    **UM BANCO POR ARQUIVO, na MESMA árvore do JSON**: `mappings/mt300.json` →
    `db/mappings/mt300.db`, `control-panel/mt300_status.json` →
    `db/control-panel/mt300_status.db`, `file-interpreter/termo.json` →
    `db/file-interpreter/termo.db`, `tickets/…` idem, e o JSON de raiz na raiz
    do `db/` (`subjacente.db`). A tabela leva o nome do arquivo, então continua
    legível de dentro do banco.

    Dois desenhos ficaram para trás, e cada um custou uma coisa: juntar a pasta
    inteira num banco só (`mappings.db` com 42 tabelas) criava contenção onde
    ela não precisa existir — o espelho reconvertendo UM mapping fechava a
    leitura dos outros 41 —, e achatar o caminho no nome
    (`mappings_mt300.db`) deixava os 133 bancos soltos na mesma pasta, onde
    achar o de uma tela virava caça ao nome."""
    parts = rel.split('/')
    fname = parts[-1]
    if not fname.endswith('.json') or fname.startswith('_'):
        return None
    if parts[0] in _DATASET_SKIP_DIRS:
        return None
    if len(parts) == 1 and (fname in _DATASET_COVERED_TOP or fname.lower() in cal_files):
        return None
    stem = fname[:-5]
    db = '/'.join([_nome_seguro(p) for p in parts[:-1]] + [_nome_seguro(stem)]) + '.db'
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


def _dataset_fora(rel, cal_files, stats):
    """Onde entra o JSON que este conversor NÃO leva: `cobertos` quando outro
    conversor da mesma rodada o converte (o RefData/CPD e o registro, pelo
    `convert_refdata`/`convert_holidays`; os arquivos de calendário, pelo
    `convert_holidays`), `ignored` quando ninguém o leva.

    A condição é a MESMA do `_dataset_rel_target` — ela decide o mesmo corte,
    aqui só para dizer de que lado dele o arquivo caiu."""
    partes = rel.split('/')
    if len(partes) == 1 and (partes[0] in _DATASET_COVERED_TOP
                             or partes[0].lower() in cal_files):
        stats['cobertos'].append(rel)
    else:
        stats['ignored'].append(rel)


def _novo_dataset_stats():
    # `cobertos` são os JSONs que OUTRO conversor da mesma rodada converte — o
    # RefData/CPD (refdata) e os arquivos de calendário (holidays). Eles saíam
    # no mesmo balde `ignored` dos que ficam de fora de verdade, e o resumo
    # dizia só `fora deste conversor: 15`: um número que se lê como perda
    # quando é exatamente o contrário.
    return {'db': '<pasta>_<arquivo>.db (um por JSON)', 'dbs': [],
            'converted': [], 'skipped': [], 'errors': [], 'ignored': [],
            'cobertos': []}


def _convert_dataset_rels(data_dir, out_dir, rels, force, stats, cal_files):
    cons = {}

    def _con(db):
        # `db` é um CAMINHO relativo (`mappings/mt300.db`) — a pasta espelha a
        # árvore do JSON de origem.
        path = os.path.join(out_dir, *db.split('/'))
        if path not in cons:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            cons[path] = duckdb.connect(path)
            ensure_manifest(cons[path])
            stats['dbs'].append(path)
        return cons[path]

    try:
        for rel in rels:
            alvo = _dataset_rel_target(rel, cal_files)
            if alvo is None:
                _dataset_fora(rel, cal_files, stats)
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
                _dataset_fora(rel, cal_files, stats)
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

    # Os desenhos anteriores saem de cena pela mesma razão dos arquivo-dia: o
    # banco que nenhum espelho atualiza mais é o que engana quem o consulta.
    # São dois — um banco por PASTA (`mappings.db` com 42 tabelas) e o nome
    # ACHATADO na raiz (`mappings_mt300.db`) — mais a `translations.db` da
    # primeira versão da cobertura.
    legados = set(_dataset_legacy_dbs(data_dir))
    legados.update(_legacy_flat_name(a[0]) for a, _ in alvos)
    _drop_legacy_dbs(out_dir, legados, {a[0] for a, _ in alvos},
                     stats, 'agora a pasta db/ espelha a arvore de origem')
    return _convert_dataset_rels(data_dir, out_dir, rels, force, stats, cal_files)

# ── CLI (caminhos fixos do share — versão standalone) ───────────────────────
import argparse
import sys

# O share tem DOIS endereços que apontam para o mesmo lugar: o UNC, que é o que a
# instância do JPM usa (o bloco ENV:PROD do config), e a letra `I:` mapeada, que
# é como a mesa o enxerga. Qual deles existe depende da máquina de quem roda,
# então tenta-se na ordem e vale o primeiro que responder — fixar um só faria o
# script não achar nada na metade das máquinas, e o sintoma seria "não converteu
# nada", não "caminho errado".
DATA_DIR_CANDIDATOS = (
    r'\\Nawest.ad.jpmorganchase.com\lac\BRA\intra\Confirmation\Derivativos\OTC Tracker\Application\static\data',
    r'I:\Confirmation\Derivativos\OTC Tracker\Application\static\data',
)


def _data_dir_padrao():
    for cand in DATA_DIR_CANDIDATOS:
        if os.path.isdir(cand):
            return cand
    return DATA_DIR_CANDIDATOS[0]


def _resumo(nome, stats, houve_erro):
    print('\n== %s -> %s' % (nome, os.path.basename(stats['db'])))
    print('   convertidos: %d | inalterados: %d%s%s%s' % (
        len(stats['converted']), len(stats['skipped']),
        ' | fora da janela: %d' % len(stats['antigos'])
        if stats.get('antigos') else '',
        ' | ja cobertos por outro conversor: %d' % len(stats['cobertos'])
        if stats.get('cobertos') else '',
        ' | fora deste conversor: %d' % len(stats['ignored'])
        if stats.get('ignored') else ''))
    for aviso in stats.get('avisos') or ():
        print('   ! %s' % aviso)
    for item in stats['converted']:
        print('   + %s' % item)
    for rel, erro in stats['errors']:
        houve_erro[0] = True
        print('   ERRO %s: %s' % (rel, str(erro).strip().splitlines()[-1]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--data-dir', default=None,
                    help='origem dos JSONs (padrão: o static\\data do share — o UNC '
                         'ou a letra I:, o que existir na máquina)')
    ap.add_argument('--out-dir', default=None,
                    help='destino dos .db (padrão: a pasta db dentro da origem)')
    ap.add_argument('--bloco', default=None,
                    help='restringe a UMA subpasta desta fatia (ex.: --bloco '
                         'Vanilla). SUBSTITUI o escopo da fatia — nao rode a '
                         'fatia inteira em paralelo com um bloco dela.')
    ap.add_argument('--force', action='store_true', help='reconverte mesmo sem mudança')
    ap.add_argument('--dry-run', action='store_true', help='só lista o que converteria')
    ap.add_argument('--meses', type=int, default=12,
                    help='janela dos arquivo-dia: converte so os dos ultimos '
                         'N meses (padrao 12). Use 0 para o historico INTEIRO '
                         '— e a segunda passada, e e ela que remove os bancos '
                         'de formato antigo.')
    args = ap.parse_args(argv)

    data_dir = os.path.abspath(args.data_dir or _data_dir_padrao())
    out_dir = os.path.abspath(args.out_dir or os.path.join(data_dir, 'db'))
    print('origem : %s' % data_dir)
    print('destino: %s' % out_dir)
    desde = data_de_corte(args.meses)
    # A janela e DECLARADA na tela: o recorte silencioso faria a segunda
    # passada (a do historico) parecer desnecessaria.
    print('janela : %s' % ('arquivo-dia a partir de %s (%d meses)'
                           % (desde.strftime('%d/%m/%Y'), args.meses)
                           if desde else 'historico INTEIRO (--meses 0)'))
    print('escopo : cache/new deals/Option/Commodities (arquivo-dia)')

    houve_erro = [False]
    # `--bloco` SUBSTITUI o escopo desta fatia; nao soma. Rodar a fatia inteira
    # em paralelo com um bloco dela poria dois processos no mesmo banco.
    fatia = 'new deals/Option/Commodities'
    if args.bloco:
        fatia = fatia.rstrip('/') + '/' + args.bloco.strip().strip('/')
        print('escopo : cache/%s (arquivo-dia) [--bloco]' % fatia)
    _resumo('daily', convert_daily(data_dir, out_dir, force=args.force,
                                   dry_run=args.dry_run, familias=[fatia],
                                   desde=desde),
            houve_erro)
    return 1 if houve_erro[0] else 0


if __name__ == '__main__':
    sys.exit(main())
