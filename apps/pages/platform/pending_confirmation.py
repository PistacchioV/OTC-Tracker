# -*- coding: utf-8 -*-
"""O motor do Pending Confirmation — os três DuckDBs (pending/ok/exception),
a derivação de linha, as regras de Pending Status (§7 do CLAUDE.md: assinatura/
prazo, esteira, vencido), a manutenção diária das 11:30 e o snapshot.

Movido VERBATIM do `routes.py` (fase platform/ — CLAUDE.md §10). É horizontal:
o New Deals grava aqui a cada mapeamento (`_pc_save_from_deal` — que dispara a
esteira via `_mc_save_from_deal`), o PCX lê os snapshots, e
`_pc_is_internal_counterparty` responde "é perna interna?" para a família de
liquidação e o backfill da esteira.

O `routes.py` mantém os nomes como ALIAS. O **`_PC_DB_DIR` e o `_B3_DATA_DIR`
FICAM no `routes`** (superfícies de patch dos check_pc_*/check_ei_metrics), e
`_fxo_refdata_by_spn`, `duckdb_read`/`duckdb_write`, `_mc_save_from_deal` e o
calendário são alcançados por busca atrasada `routes.<nome>` — é o que mantém
os espiões dos testes interceptando. O REGISTRO do scheduler
(`_schedule_on_start`-style) continua no wiring do routes; a feature/platform
só expõe o laço. O estado `_pc_scheduler_started` (rebindado) mora AQUI.
"""
import io
import json
import logging
import os
import re
import threading
import time
import traceback
from datetime import datetime, timedelta

from apps.pages.data_paths import data_dir

log = logging.getLogger('otc_tracker')

def _pc_refdata_lookup(r, by_spn, by_name):
    """RefData.json record for a pending row (by SPN first, then counterparty name)."""
    from apps.pages import routes
    spn = r.get('SPN', '')
    rec = by_spn.get(routes._norm_spn(spn)) if spn else None
    if rec is None:
        rec = by_name.get(_pc_norm(r.get('Client', '')))
    return rec or {}

_PC_DBS = {
    'backlog': 'pending-confirmation-backlog.db',
    'pending': 'pending-confirmation-pending.db',
    'ok':      'pending-confirmation-ok.db',
}
_PC_TABLE = 'pending_confirmation'
_PC_COLUMNS = [
    'Status', 'LOB', 'SPN', 'Client', 'Aging', 'Product Type', 'Trade Date',
    'Maturity Date', 'Trade Number', 'Pending Status', 'Owner', 'EA', 'Send Date',
    'Return Date', 'Break Reason', 'Comments', 'Economic Group', 'Signature Type',
    'FepWeb ID', 'Pendência',
]
# Daily JSON snapshots of the pending DB (YYYY/MM/DD), for a future metrics page.
_PC_SNAPSHOT_DIR = os.path.join(data_dir(),
                                'cache', 'pending-confirmation')


def _pc_norm(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]', '', s.lower())


def _pc_category_from_filters(filters):
    """The Status chip selects which DB. Default 'pending'."""
    for f in (filters or []):
        if _pc_norm(f.get('field', '')) == 'status':
            v = _pc_norm(f.get('value', ''))
            if 'backlog' in v:
                return 'backlog'
            if v == 'ok':
                return 'ok'
            return 'pending'
    return 'pending'


def _pc_ensure_db(path):
    """Create an empty pending_confirmation DB (schema only) if the file is
    missing, so the page works before the first spreadsheet import runs."""
    from apps.pages import routes
    if os.path.isfile(path):
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # O `with` fecha a conexão e solta o lock em QUALQUER saída, inclusive na
        # exceção. Era `connect` + `finally: close()` escrito à mão: uma conexão
        # vazada segura o lock de escrita do DuckDB pela vida do processo, e aí a
        # página some para TODOS, não só para quem tropeçou no erro.
        with routes.duckdb_write(path) as con:
            cols = ', '.join('"{}" VARCHAR'.format(c) for c in _PC_COLUMNS)
            con.execute('CREATE TABLE IF NOT EXISTS {} ({})'.format(_PC_TABLE, cols))
        log.info('[pending-confirmation] created empty DB %s', path)
    except Exception:
        log.warning('[pending-confirmation] could not create %s', path)


def _pc_load_rows(category):
    from apps.pages import routes
    path = os.path.join(routes._PC_DB_DIR, _PC_DBS.get(category, _PC_DBS['pending']))
    _pc_ensure_db(path)
    if not os.path.isfile(path):
        return []
    try:
        # `duckdb_read`: lock de arquivo COMPARTILHADO (as leituras não se
        # excluem entre si) e fechamento garantido na saída do bloco.
        with routes.duckdb_read(path) as con:
            cols = ', '.join('"{}"'.format(c) for c in _PC_COLUMNS)
            rows = con.execute('SELECT {} FROM {}'.format(cols, _PC_TABLE)).fetchall()
        out = [dict(zip(_PC_COLUMNS, r)) for r in rows]
        for r in out:                       # keep Aging/Status current at read time
            _pc_refresh_aging_status(r)
        return out
    except Exception:
        log.warning('[pending-confirmation] query failed for %s:\n%s', path, traceback.format_exc())
        return []


#  Colunas DERIVADAS do Pending Confirmation: as que a tela não deixa editar
#  porque saem de outra coisa. Owner / Economic Group / Signature Type vêm do
#  Reference Data pelo SPN (ou pelo nome); Aging e Status saem do Trade Date; e o
#  Pending Status sai do PRAZO (Maturity − Trade) pela regra do Pending Update.
_PC_DERIVED_COLUMNS = ('Owner', 'Economic Group', 'Signature Type', 'Aging',
                       'Status', 'Pending Status')


def _pc_derive_row(src):
    """Campos derivados de UMA linha do Pending Confirmation.

    Existe para que a atualização em massa da tela não tenha uma segunda cópia
    das regras. Elas já vivem aqui — `_pc_refdata_lookup`, `_pc_aging_band_label`
    e `_pc_signature_status` são as MESMAS que a importação do Pending Update
    usa. Uma cópia em JavaScript faria a mesma operação sair com um Pending
    Status pelo arquivo e outro por uma edição na tela, sem nada acusando.

    `src` traz o que o usuário tem em mãos (SPN, Client, Trade Date, Maturity
    Date) **e o Pending Status atual da linha** — sem ele, mexer na data de uma
    confirmação que está em `Pending MO` a devolveria para `Pending Original` e
    ela sumiria da fila da mesa. A resposta traz as seis colunas derivadas — quem
    chama decide quais aplicar, porque isso depende de QUAL coluna foi alterada."""
    from apps.pages import routes
    rec = _pc_refdata_lookup({'SPN': str(src.get('SPN', '') or ''),
                              'Client': str(src.get('Client', '') or '')},
                             routes._fxo_refdata_by_spn(), _pc_refdata_by_name())
    trade_dt = routes._parse_date_any(str(src.get('Trade Date', '') or ''))
    mat_dt = routes._parse_date_any(str(src.get('Maturity Date', '') or ''))
    pending_status, status = _pc_signature_status(
        rec, trade_dt, mat_dt, str(src.get('Pending Status', '') or ''))
    aging = (datetime.now().date() - trade_dt).days if trade_dt else None
    return {
        # SPN e Client saem juntos: escolher um preenche o outro, como no modal.
        'SPN': str(rec.get('SPN', '') or '') or str(src.get('SPN', '') or ''),
        'Client': str(rec.get('COUNTERPARTY', '') or '') or str(src.get('Client', '') or ''),
        'Owner': str(rec.get('BANKER', '') or ''),
        'Economic Group': str(rec.get('ECONOMIC GROUP', '') or ''),
        'Signature Type': str(rec.get('SIGNATURE TYPE', '') or ''),
        'Aging': '' if aging is None else str(aging),
        'Status': status,
        'Pending Status': pending_status,
    }


# ── Pending Update — bulk upsert from the "Pending Update" xlsx ────────────────
# Sheet columns:
#   LOB; End Counterparty Desc; Aging; Status; Product Type; Booking Date;
#   Settlement Date; Deal Name; Pending Status
# Mapping to page columns: End Counterparty Desc → Client (+ SPN via RefData name),
# Booking Date → Trade Date, Settlement Date → Maturity Date, Deal Name → Trade
# Number, Product Type as-is. Status/Pending Status são DERIVADOS por
# `_pc_signature_status` — a linha já em etapa da esteira mantém a etapa; o resto
# cai na regra de prazo (≤ 60 dias → Exception FepWeb) e tipo de assinatura.
_PC_UPDATE_HEADERS = {
    'lob': 'LOB',
    'endcounterpartydesc': 'Client',
    'producttype': 'Product Type',
    'bookingdate': 'Trade Date',
    'settlementdate': 'Maturity Date',
    'dealname': 'Trade Number',
}

def _pc_signature_pending_status(rec, trade_dt, maturity_dt):
    """Pending Status pelo PRAZO e pelo TIPO DE ASSINATURA.

    Esta é a regra de **NDF Vanilla e NDF Other Publisher** — os únicos produtos
    que não passam pela esteira de validação. Todo o resto entra na esteira e o
    Pending Status dele é a ETAPA (ver `_pc_is_esteira_status`), que prazo e
    assinatura não têm o que opinar.

      * prazo (Settlement − Trade) ≤ 60 dias corridos → `Exception FepWeb`;
      * senão, pelo SIGNATURE TYPE da contraparte no Reference Data:
        Internal → `Exception Digital Fep Web`, Digital → `Pending Digital
        Signature`, Manual **e não cadastrado** → `Pending Original`.

    É a MESMA função que o New Deals chama (`_generic_nd_pending_status`). Eram
    duas cópias, e elas divergiam em duas coisas em silêncio: o prazo curto saía
    `Exception Digital Fep Web` por um caminho e `Exception FepWeb` pelo outro, e
    o ramo `internal` só existia no lado do New Deals — a mesma contraparte
    recebia respostas diferentes conforme a linha ter vindo do arquivo ou da tela.
    """
    if trade_dt and maturity_dt and (maturity_dt - trade_dt).days <= 60:
        return _PC_TENOR_EXCEPTION
    sig = _pc_norm((rec or {}).get('SIGNATURE TYPE', ''))
    if sig == 'internal':
        return _PC_INTERNAL_EXCEPTION
    if sig == 'digital':
        return 'Pending Digital Signature'
    return 'Pending Original'


def _pc_signature_status(rec, trade_dt, maturity_dt, current=''):
    """(Pending Status, Status) de uma linha do Pending Confirmation.

    `current` é o Pending Status que a linha JÁ TEM. Quando ele é uma etapa da
    esteira, ele fica: quem decide o estágio de uma confirmação em validação é o
    Confirmations Monitor, e recalcular por prazo/assinatura aqui trocaria um
    `Pending MO` por `Pending Original` — a linha sumiria da fila da mesa sem
    ninguém ter validado nada. Sem etapa (NDF Vanilla / Other Publisher, ou linha
    nova), vale a regra de prazo e assinatura.

    O Status acompanha o Pending Status: `Ok` quando ele é resolvido, senão a
    faixa de aging.
    """
    if _pc_is_esteira_status(current):
        pending_status = str(current).strip()
    else:
        pending_status = _pc_signature_pending_status(rec, trade_dt, maturity_dt)
    if _pc_is_ok_status(pending_status):
        return pending_status, 'Ok'
    aging = (datetime.now().date() - trade_dt).days if trade_dt else None
    return pending_status, _pc_aging_band_label(aging)


def _pc_import_update(raw_bytes):
    """Parse the Pending Update xlsx and upsert each operation. Returns
    {updated, skipped}."""
    from apps.pages import routes
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header = next(rows_iter)
    except StopIteration:
        return {'updated': 0, 'skipped': 0}
    # normalized header name → column index
    col_idx = {}
    for i, h in enumerate(header):
        n = _pc_norm(h)
        if n and n not in col_idx:
            col_idx[n] = i
    # page-column → sheet column index (resolved once)
    pc_to_i = {}
    for norm, pc in _PC_UPDATE_HEADERS.items():
        if norm in col_idx:
            pc_to_i[pc] = col_idx[norm]

    def cell(row, page_col):
        i = pc_to_i.get(page_col)
        if i is None or i >= len(row):
            return ''
        v = row[i]
        if v is None:
            return ''
        # openpyxl com data_only=True devolve o valor EM CACHE da fórmula; quando a
        # fórmula está com erro, o que chega é o TEXTO '#NULL!' / '#N/A' / '#REF!'.
        # Isso não é dado: entrava no banco, aparecia na tela e saía na planilha
        # como #NULL!. Vira vazio — e no Trade Number, que é a chave da linha, a
        # linha passa a ser pulada pela regra que já existe para número vazio (uma
        # chave '#NULL!' ainda colidia com todas as outras linhas quebradas).
        if isinstance(v, str) and v.strip().upper() in routes._XL_ERROR_TEXT:
            return ''
        return v

    # RefData maps built once: SPN + signature type by counterparty name.
    by_name = _pc_refdata_by_name()
    # Pending Status que cada Trade Number JÁ TEM. A importação é um upsert: a
    # linha que está numa etapa da esteira tem de sair dela com a etapa intacta,
    # senão o arquivo do dia devolve para `Pending Original` toda confirmação que
    # as mesas estão conferindo. Lido UMA vez — por linha seriam N leituras dos
    # três DuckDBs.
    atual = {}
    for _cat in ('backlog', 'pending', 'ok'):
        for _r in _pc_load_rows(_cat):
            _tn = str(_r.get('Trade Number', '') or '').strip()
            if _tn and _tn not in atual:
                atual[_tn] = str(_r.get('Pending Status', '') or '')

    updated, skipped = 0, 0
    for row in rows_iter:
        if row is None or not any(v not in (None, '') for v in row):
            continue
        client = str(cell(row, 'Client') or '').strip()
        tn = str(cell(row, 'Trade Number') or '').strip()
        if tn.endswith('.0'):
            tn = tn[:-2]
        if not tn:
            skipped += 1
            continue
        rec = by_name.get(_pc_norm(client))
        spn = str((rec or {}).get('SPN', '') or '').strip()
        trade_dt = routes._parse_date_any(cell(row, 'Trade Date'))
        maturity_dt = routes._parse_date_any(cell(row, 'Maturity Date'))
        pending_status, status = _pc_signature_status(rec, trade_dt, maturity_dt,
                                                      atual.get(tn, ''))
        aging = (datetime.now().date() - trade_dt).days if trade_dt else None
        r = {c: '' for c in _PC_COLUMNS}
        r['LOB'] = str(cell(row, 'LOB') or '').strip()
        r['SPN'] = spn
        r['Client'] = client
        r['Aging'] = str(aging) if aging is not None else ''
        r['Product Type'] = str(cell(row, 'Product Type') or '').strip()
        r['Trade Date'] = trade_dt.strftime('%d/%m/%Y') if trade_dt else ''
        r['Maturity Date'] = maturity_dt.strftime('%d/%m/%Y') if maturity_dt else ''
        r['Trade Number'] = tn
        r['Status'] = status
        r['Pending Status'] = pending_status
        r['Owner'] = _pc_banker_for_spn(spn)
        _pc_refdata_enrich(r)        # Economic Group / Signature Type do RefData
        _pc_upsert_row(r)
        updated += 1
    try:
        wb.close()
    except Exception:
        pass
    return {'updated': updated, 'skipped': skipped}

def _pc_is_intragroup(client):
    cl = str(client or '').lower()
    return 'banco' in cl and 'morgan' in cl


def _pc_refdata_by_name():
    """{normalized COUNTERPARTY name -> RefData record}, for economic-group /
    signature-type lookups by counterparty name."""
    from apps.pages import routes
    out = {}
    try:
        with open(os.path.join(routes._B3_DATA_DIR, 'RefData.json'), encoding='utf-8') as fh:
            data = json.load(fh)
        for rec in (data if isinstance(data, list) else []):
            nm = _pc_norm(rec.get('COUNTERPARTY', ''))
            if nm and nm not in out:
                out[nm] = rec
    except (IOError, json.JSONDecodeError):
        pass
    return out


def _pc_is_internal_counterparty(client, spn=''):
    """True when the deal's counterparty is an INTERNAL leg (Banco J.P. Morgan or
    Lawton) — identified by ECONOMIC GROUP == 'INTERNAL' in RefData (by SPN first,
    then by name). Only external clients should flow to Pending Confirmation, so
    these bank/Lawton legs are skipped."""
    from apps.pages import routes
    rec = None
    key = routes._norm_spn(spn)
    if key:
        rec = routes._fxo_refdata_by_spn().get(key)
    if rec is None:
        rec = _pc_refdata_by_name().get(_pc_norm(client))
    if rec is not None:
        return _pc_norm(rec.get('ECONOMIC GROUP', '')) == 'internal'
    # No RefData hit → fall back to the intragroup name check (Banco JP Morgan).
    return _pc_is_intragroup(client)


def _pc_aging_band_label(days):
    """Same aging-band label the page computes on Add Row (arAgingStatus)."""
    if days is None:
        return ''
    if days < 10:
        return '< 10 dias de pendência'
    if days < 20:
        return '>= 10 e < 20 dias de pendência'
    if days < 30:
        return '>= 20 e < 30 dias de pendência'
    if days < 60:
        return '>= 30 e < 60 dias de pendência'
    if days < 90:
        return '>= 60 e < 90 dias de pendência'
    return '>= 90 dias de pendência'


def _pc_banker_for_spn(spn):
    """Owner = the RefData BANKER for this deal's SPN ('' when unknown)."""
    from apps.pages import routes
    try:
        rec = routes._fxo_refdata_by_spn().get(routes._norm_spn(spn))
        return str((rec or {}).get('BANKER', '') or '').strip()
    except Exception:
        return ''


# Pending Status values that mean the confirmation is RESOLVED → the row moves to
# the 'ok' DB. (Concluded = Mark Concluded; plus the digitally-resolved states.)
_PC_OK_STATUSES = {'concluded', 'signeddigitally', 'exceptiondigitalfepweb'}
# Pending Status do vencido (a regra universal) e do prazo curto (≤ 60 dias):
# são a MESMA situação — a confirmação se resolve pelo FepWeb — e o mesmo rótulo.
_PC_PASTDUE_STATUS = 'Exception FepWeb'
_PC_TENOR_EXCEPTION = _PC_PASTDUE_STATUS
# O `Internal` do SIGNATURE TYPE tem rótulo próprio: não é a mesma situação, é
# contraparte que assina por dentro.
_PC_INTERNAL_EXCEPTION = 'Exception Digital Fep Web'

# As etapas da esteira de validação (§254). Uma linha em qualquer uma delas está
# sendo conferida pelas mesas, e é a esteira quem manda no Pending Status dela —
# prazo e tipo de assinatura não entram. Só NDF Vanilla e NDF Other Publisher não
# passam pela esteira; todo o resto passa.
_PC_ESTEIRA_STATUSES = {'pendinglegal', 'pendingotc', 'pendingmo', 'pendingfo',
                        'pendingmofo', 'pendingfepweb'}


def _pc_is_esteira_status(v):
    return _pc_norm(v) in _PC_ESTEIRA_STATUSES


def _pc_is_ok_status(v):
    # ANY "Exception *" status (Exception, Exception FepWeb, Exception Digital Fep
    # Web, …) counts as resolved/OK — it is NOT an outstanding confirmation, so it
    # must not feed the pending metrics. Kept alongside the explicit resolved set.
    n = _pc_norm(v)
    return n.startswith('exception') or n in _PC_OK_STATUSES


def _pc_cutoff_date():
    """Trade dates strictly before this go to the 12-month backlog."""
    from dateutil.relativedelta import relativedelta
    return datetime.now().date() - relativedelta(months=12)


def _pc_apply_auto_rules(row):
    """Mantém a linha em dia: (1) recalcula o Aging (hoje − Trade Date) e a faixa
    do Status; (2) aplica a regra do VENCIDO.

    A regra do vencido é a **única que vale para todo produto e todo estágio** —
    esteira inclusive. Chegada a data de vencimento com a confirmação em qualquer
    status que não seja resolvido, ela vira `Exception FepWeb` e o Status vira
    `Ok`: não há mais o que confirmar de uma operação que já liquidou. As DUAS
    colunas mudam juntas, e é isso que tira a linha da fila e a move para o DB ok.

    O teste é `not _pc_is_ok_status(...)`, e não "começa com Pending": status como
    *Abonado via PDF* ou *Client Treasury Allowance* também são pendências — não
    começam com "Pending" e ficavam de fora da regra, envelhecendo para sempre
    numa operação já vencida.
    """
    from apps.pages import routes
    td = routes._parse_date_any(row.get('Trade Date', ''))
    if td:
        row['Aging'] = str((datetime.now().date() - td).days)
    md = routes._parse_date_any(row.get('Maturity Date', ''))
    if md and md <= datetime.now().date() and not _pc_is_ok_status(row.get('Pending Status', '')):
        row['Pending Status'] = _PC_PASTDUE_STATUS
    # Status column: 'Ok' once the confirmation is resolved (an ok Pending Status),
    # otherwise the aging-band label.
    if _pc_is_ok_status(row.get('Pending Status', '')):
        row['Status'] = 'Ok'
    elif td:
        row['Status'] = _pc_aging_band_label((datetime.now().date() - td).days)
    return row


# Back-compat alias (older call sites).
_pc_refresh_aging_status = _pc_apply_auto_rules


def _pc_target_category(row):
    """The DB a row belongs to NOW: backlog if Trade Date > 12 months; ok if its
    Pending Status is resolved; otherwise pending."""
    from apps.pages import routes
    td = routes._parse_date_any(row.get('Trade Date', ''))
    if td and td < _pc_cutoff_date():
        return 'backlog'
    if _pc_is_ok_status(row.get('Pending Status', '')):
        return 'ok'
    return 'pending'


def _pc_write_exec(category, ops):
    """Run (sql, params) operations in one shared exclusive transaction."""
    from apps.pages import routes
    path = os.path.join(routes._PC_DB_DIR, _PC_DBS[category])
    _pc_ensure_db(path)
    try:
        # O retry/backoff que estava escrito aqui à mão passou a ser do
        # `duckdb_write`, num lugar só e para todos os bancos.
        with routes.duckdb_write(path) as con:
            for sql, params in ops:
                con.execute(sql, params)
        return True
    except Exception:
        log.warning('[pending-confirmation] write failed on %s:\n%s', category, traceback.format_exc())
        return False


def _pc_delete_tn(category, tn):
    if not tn:
        return
    _pc_write_exec(category, [('DELETE FROM {} WHERE "Trade Number" = ?'.format(_PC_TABLE), [tn])])


def _pc_insert_into(category, row):
    # INSERT com colunas explícitas: funciona também num DB ainda não migrado
    # (colunas legadas extras ficam NULL) — o VALUES posicional quebraria.
    cols = ', '.join('"{}"'.format(c) for c in _PC_COLUMNS)
    placeholders = ', '.join('?' for _ in _PC_COLUMNS)
    _pc_write_exec(category, [('INSERT INTO {} ({}) VALUES ({})'.format(_PC_TABLE, cols, placeholders),
                              [row.get(c, '') for c in _PC_COLUMNS])])


def _pc_upsert_row(row):
    """Persist one row: refresh aging/status, remove its Trade Number from ALL
    three DBs, then insert it into the DB it now belongs to (this is what moves a
    row pending→ok when confirmed, or →backlog past 12 months). Returns the
    target category."""
    _pc_refresh_aging_status(row)
    tn = str(row.get('Trade Number', '') or '')
    target = _pc_target_category(row)
    for cat in ('backlog', 'pending', 'ok'):
        _pc_delete_tn(cat, tn)
    _pc_insert_into(target, row)
    return target


def _pc_rewrite_db(category, rows):
    """Replace a DB's contents with `rows` (used by the daily re-route)."""
    from apps.pages import routes
    path = os.path.join(routes._PC_DB_DIR, _PC_DBS[category])
    _pc_ensure_db(path)
    cols_ddl = ', '.join('"{}" VARCHAR'.format(c) for c in _PC_COLUMNS)
    try:
        # DROP + CREATE + INSERT numa transação só: aqui o `with` importa mais do
        # que nos outros, porque uma falha no meio deixaria o banco SEM a tabela
        # que acabou de ser derrubada — a página abriria vazia.
        with routes.duckdb_write(path) as con:
            con.execute('DROP TABLE IF EXISTS {}'.format(_PC_TABLE))
            con.execute('CREATE TABLE {} ({})'.format(_PC_TABLE, cols_ddl))
            if rows:
                ph = ', '.join('?' for _ in _PC_COLUMNS)
                con.executemany('INSERT INTO {} VALUES ({})'.format(_PC_TABLE, ph),
                                [[r.get(c, '') for c in _PC_COLUMNS] for r in rows])
        return True
    except Exception:
        log.warning('[pending-confirmation] rewrite failed on %s:\n%s', category, traceback.format_exc())
        return False


def _pc_snapshot_pending(rows_pending):
    """Write a JSON photo of the pending DB under cache/pending-confirmation/
    YYYY/MM/DD (year/month/day like the other caches) for a metrics page."""
    today = datetime.now()
    out_dir = os.path.join(_PC_SNAPSHOT_DIR, today.strftime('%Y'), today.strftime('%m'), today.strftime('%d'))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'pending-confirmation_{}.json'.format(today.strftime('%Y%m%d')))
    from apps.pages import routes
    routes._atomic_write_json(path, rows_pending)   # funil: atômico + espelho (§335)
    return path


def _pc_run_daily_maintenance(snapshot=True):
    """Re-route every row across the three DBs (refresh aging/status; backlog past
    12 months; ok when resolved; else pending), rewrite the DBs, and save the
    pending snapshot. Shared by the in-app 11:30 scheduler and the standalone
    script. Idempotent."""
    seen, all_rows = set(), []
    for cat in ('backlog', 'pending', 'ok'):
        for r in _pc_load_rows(cat):
            tn = str(r.get('Trade Number', '') or '')
            key = tn or ('#' + str(len(all_rows)))
            if key in seen:
                continue
            seen.add(key)
            all_rows.append(r)
    buckets = {'backlog': [], 'pending': [], 'ok': []}
    for r in all_rows:
        buckets[_pc_target_category(r)].append(r)
    for cat in ('backlog', 'pending', 'ok'):
        _pc_rewrite_db(cat, buckets[cat])
    snap = _pc_snapshot_pending(buckets['pending']) if snapshot else None
    log.info('[pending-confirmation] daily maintenance: %d backlog / %d pending / %d ok%s',
             len(buckets['backlog']), len(buckets['pending']), len(buckets['ok']),
             (' + snapshot ' + os.path.basename(snap)) if snap else '')
    return buckets


# In-app daily scheduler — runs _pc_run_daily_maintenance at a fixed local time
# (default 11:30). Self-contained (no OS Task Scheduler needed); the maintenance
# is idempotent so an occasional double-run is harmless.
_PC_DAILY_TIME = os.getenv('PC_DAILY_TIME', '11:30')

_pc_scheduler_started = False
_pc_scheduler_lock = threading.Lock()


def _pc_scheduler_loop():
    from apps.pages import routes
    try:
        hh, mm = (int(x) for x in _PC_DAILY_TIME.split(':')[:2])
    except Exception:
        hh, mm = 11, 30
    last_run = None
    while True:
        try:
            now = routes._br_now()
            target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            time.sleep(max(1.0, (target - now).total_seconds()))
            today = routes._br_now().date()
            if today != last_run:          # once per calendar day
                last_run = today
                _pc_run_daily_maintenance(snapshot=True)
        except Exception:
            log.error('[pending-confirmation] scheduler error:\n%s', traceback.format_exc())
            time.sleep(60)


def _pc_start_scheduler():
    global _pc_scheduler_started
    with _pc_scheduler_lock:
        if _pc_scheduler_started:
            return
        _pc_scheduler_started = True
    threading.Thread(target=_pc_scheduler_loop, name='pc-daily-scheduler', daemon=True).start()
    log.info('[pending-confirmation] daily scheduler started (runs at %s)', _PC_DAILY_TIME)

def _pc_refdata_enrich(row):
    """Preenche Economic Group / Signature Type da linha a partir do RefData
    (chave: SPN; fallback: nome do Client) quando ainda estão vazios — todo
    feed que insere linha no Pending Confirmation passa por aqui."""
    from apps.pages import routes
    rec = routes._fxo_refdata_by_spn().get(routes._norm_spn(row.get('SPN', '')))
    if rec is None:
        rec = _pc_refdata_by_name().get(_pc_norm(row.get('Client', '')))
    if not rec:
        return
    if not str(row.get('Economic Group', '') or '').strip():
        row['Economic Group'] = str(rec.get('ECONOMIC GROUP', '') or '').strip()
    if not str(row.get('Signature Type', '') or '').strip():
        row['Signature Type'] = str(rec.get('SIGNATURE TYPE', '') or '').strip()

def _pc_save_from_deal(deal, product_type, pending_status=None, trade_number=None,
                       source=None):
    """Build and insert a pending row from a Success+mapped New Deals deal.
    product_type: 'NDF COMM' (NDF Comm), 'OPTION COMM' (Opt Comm), 'OPTION' (FXO),
    'NDF FWD START' / 'NDF OTHER PUB' / 'NDF VANILLA' (generic NDF pages).
    pending_status overrides the default 'Pending OTC' (signature-type rules);
    trade_number overrides the Deal id (FWD Start rows are keyed by B3 ID).
    `source` distingue as três páginas genéricas de NDF, que gravam o MESMO
    Product Type — sem ele o FWD Start não se separa de Vanilla/Other Publisher."""
    from apps.pages import routes
    try:
        client = str(deal.get('Client', '') or '')
        if _pc_is_internal_counterparty(client, deal.get('SPN', '')):
            return          # bank / Lawton / intragroup leg → not a client confirmation
        td = routes._parse_date_any(deal.get('TradeDate', ''))
        md = routes._parse_date_any(deal.get('SettlementDate', ''))
        aging = (datetime.now().date() - td).days if td else None
        row = {c: '' for c in _PC_COLUMNS}
        row['Status'] = _pc_aging_band_label(aging)
        # A LOB acompanha o produto: mercadoria é COMMODITY, o resto é CEM.
        row['LOB'] = routes._lob_for_source(source or product_type)
        row['SPN'] = str(deal.get('SPN', '') or '')
        row['Client'] = client
        row['Aging'] = str(aging) if aging is not None else ''
        row['Product Type'] = product_type
        row['Trade Date'] = td.strftime('%d/%m/%Y') if td else str(deal.get('TradeDate', '') or '')
        row['Maturity Date'] = md.strftime('%d/%m/%Y') if md else str(deal.get('SettlementDate', '') or '')
        row['Trade Number'] = str(trade_number or deal.get('Deal', '') or '')
        row['Pending Status'] = pending_status or 'Pending OTC'
        row['Owner'] = _pc_banker_for_spn(deal.get('SPN', ''))
        _pc_refdata_enrich(row)      # Economic Group / Signature Type do RefData
        _pc_upsert_row(row)          # routes to pending (or backlog if >12 months)
        # A MESMA operação entra na esteira de validação da confirmação — só os
        # produtos que geram documento (ver _MC_CONFIRMATION_SOURCES).
        routes._mc_save_from_deal(deal, source or product_type, trade_number=row['Trade Number'])
    except Exception:
        log.warning('[pending-confirmation] save-from-deal failed:\n%s', traceback.format_exc())

# ============================================================================
#  METRICS — Pending Confirmation
#  Dashboard for confirmations pending > 30 days. Offenders (bankers / clients /
#  economic groups) come from the daily pending-confirmation snapshot JSON ("photo
#  of the day"); the >30d volume history is seeded from the external report
#  (static/data/pending-confirmation-metrics-history.json) until enough internal
#  snapshots accumulate. Owner holds one or more banker names separated by ';'.
# ============================================================================
_PC_METRICS_AGING_THRESHOLD = 30
_PC_METRICS_HISTORY_FILE = os.path.join(
    data_dir(), 'pending-confirmation-metrics-history.json')


def _pc_metrics_int(v):
    try:
        return int(float(str(v).strip()))
    except Exception:
        return None


def _pc_latest_snapshot_rows():
    """Pending-confirmation rows for the metric e-mails (daily metric / weekly
    escalation). Lê DIRETO do DB pending (Aging e Status são recalculados na
    leitura por _pc_load_rows → informação 100% atual no momento do envio); o
    snapshot diário mais recente fica só como fallback se o DB não abrir.
    Returns (rows, source_label)."""
    def _pending_only(rows):
        # Defensive: rows whose Pending Status is now considered OK (any
        # Exception*) may still sit in the pending DB/snapshot until the daily
        # re-route. Drop them so the metrics never count a resolved confirmation.
        return [r for r in rows if not _pc_is_ok_status(r.get('Pending Status', ''))]
    try:
        rows = _pc_load_rows('pending')
        if rows:
            return _pending_only(rows), 'live'
    except Exception:
        log.warning('[pc-metrics] live DB read failed:\n%s', traceback.format_exc())
    try:
        for back in range(0, 40):
            d = datetime.now() - timedelta(days=back)
            p = os.path.join(_PC_SNAPSHOT_DIR, d.strftime('%Y'), d.strftime('%m'), d.strftime('%d'),
                             'pending-confirmation_{}.json'.format(d.strftime('%Y%m%d')))
            if os.path.isfile(p):
                with open(p, encoding='utf-8') as fh:
                    rows = json.load(fh)
                if isinstance(rows, list):
                    return _pending_only(rows), d.strftime('%Y-%m-%d')
    except Exception:
        log.warning('[pc-metrics] snapshot scan failed:\n%s', traceback.format_exc())
    return [], 'none'


def _pc_metrics_offenders(rows):
    """Top-5 offenders among rows aging > 30 days (each row = one contract):
      • bankers       → # of pending contracts (confirmations)
      • clients       → # of pending contracts (confirmations)
      • economic grp  → # of pending contracts (confirmations)
    Owner is a fixed banker GROUP (e.g. "A; B; C") — treated as a single name, not
    split per person, since the group is the same team across a client's deals.
    """
    gt30 = [r for r in rows
            if (_pc_metrics_int(r.get('Aging')) or 0) > _PC_METRICS_AGING_THRESHOLD]

    banker_count, client_count, egroup_count = {}, {}, {}
    for r in gt30:
        client = str(r.get('Client', '') or '').strip()
        egroup = str(r.get('Economic Group', '') or '').strip()
        banker = str(r.get('Owner', '') or '').strip()     # whole Owner group = one name
        if banker:
            banker_count[banker] = banker_count.get(banker, 0) + 1
        if client:
            client_count[client] = client_count.get(client, 0) + 1
        if egroup:
            egroup_count[egroup] = egroup_count.get(egroup, 0) + 1

    def top5(d):
        return [{'label': k, 'value': v}
                for k, v in sorted(d.items(), key=lambda kv: (-kv[1], kv[0].lower()))[:5]]

    return {
        'bankers':    top5(banker_count),
        'clients':    top5(client_count),
        'egroups':    top5(egroup_count),
        'gt30_total': len(gt30),
        'all_total':  len(rows),
    }


def _pc_metrics_history():
    """>30d volume history: seed (external report) merged with any internal daily
    snapshots. Returns {gt30:{monthly,daily}, all:{monthly,daily}} where each point
    is {period|date, volume, pct} (pct = MoM/DoD change vs the previous point)."""
    seed = {}
    try:
        with open(_PC_METRICS_HISTORY_FILE, encoding='utf-8') as fh:
            seed = json.load(fh)
    except Exception:
        log.warning('[pc-metrics] could not read history seed')
    seed_gt30 = (seed.get('gt30') or {})
    seed_monthly = list(seed_gt30.get('monthly') or [])
    seed_daily   = list(seed_gt30.get('daily') or [])

    internal_gt30, internal_all = {}, {}     # day 'YYYY-MM-DD' -> volume
    try:
        if os.path.isdir(_PC_SNAPSHOT_DIR):
            for root, _dirs, files in os.walk(_PC_SNAPSHOT_DIR):
                for fn in files:
                    if not fn.endswith('.json'):
                        continue
                    m = re.search(r'(\d{4})(\d{2})(\d{2})', fn)
                    if not m:
                        continue
                    day = '{}-{}-{}'.format(*m.groups())
                    try:
                        with open(os.path.join(root, fn), encoding='utf-8') as fh:
                            rows = json.load(fh)
                    except Exception:
                        continue
                    if not isinstance(rows, list):
                        continue
                    # Snapshots taken under older rules may still carry rows whose
                    # Pending Status is now considered OK (any Exception*). Exclude
                    # them so the >30d history never counts a resolved confirmation.
                    rows = [r for r in rows if not _pc_is_ok_status(r.get('Pending Status', ''))]
                    internal_gt30[day] = sum(
                        1 for r in rows
                        if (_pc_metrics_int(r.get('Aging')) or 0) > _PC_METRICS_AGING_THRESHOLD)
                    internal_all[day] = len(rows)
    except Exception:
        log.warning('[pc-metrics] internal snapshot scan failed:\n%s', traceback.format_exc())

    def merge_daily(seed_list, internal):
        by = {d['date']: d['volume'] for d in seed_list}
        by.update(internal)                     # internal overrides seed for same day
        return [{'date': k, 'volume': by[k]} for k in sorted(by)]

    def monthly_last(internal):                 # last snapshot value of each month
        by_month = {}
        for day in sorted(internal):
            by_month[day[:7]] = internal[day]
        return by_month

    gt30_daily   = merge_daily(seed_daily, internal_gt30)
    gt30_month   = {m['period']: m['volume'] for m in seed_monthly}
    gt30_month.update(monthly_last(internal_gt30))
    gt30_monthly = [{'period': k, 'volume': gt30_month[k]} for k in sorted(gt30_month)]

    all_daily    = [{'date': k, 'volume': internal_all[k]} for k in sorted(internal_all)]
    all_month    = monthly_last(internal_all)
    all_monthly  = [{'period': k, 'volume': all_month[k]} for k in sorted(all_month)]

    def with_pct(series, key):
        out, prev = [], None
        for pt in series:
            vol = pt['volume']
            pct = None if prev in (None, 0) else round((vol - prev) * 100.0 / prev)
            out.append({key: pt[key], 'volume': vol, 'pct': pct})
            prev = vol
        return out

    return {
        'gt30': {'monthly': with_pct(gt30_monthly, 'period'), 'daily': with_pct(gt30_daily, 'date')},
        'all':  {'monthly': with_pct(all_monthly, 'period'),  'daily': with_pct(all_daily, 'date')},
    }
