"""
Pay/Rec Reconciliation engine — faithful port of the Alteryx "PayRec" workflow,
verified against the ground-truth daily output.

JPM / Cockpit side (3 sources, Union'd):
  settlement.csv      → NDF   (value = Tax Income + Amount, per-Client sum, Settlement Net='TOTAL_NET')
  cashflows_*.xlsx    → COMM TER / SWAP  (per-client NET sum; Owner Legal Entity='0228')
  FXO Detail*.xlsx    → FXO   (value from ATH SET AMT + Direction)

Client side (4 sources, Union'd):
  rlctahis.csv        → SDConta interna  (nHistorico allowlist)
  rlDocTed01.csv      → SDConta externa (TED)
  HistoricoMensagensJPM_*.csv → SPB externa (Descrição Evento contains Derivativos/LMA-COMM-BR; always Pay)
  HistoricoMensagensMGT_*.csv → SPB MGT (same layout; sign of Valor → Pay/Receive; no LMA-COMM)

Match: JPM value ↔ client value, rounded to whole units (value-only join).
Difference = Client - JPM;  Status = Settled if 0 else Pending (SPB tol > -0.50).
"""

import os
import re
import json
import glob
import unicodedata
from datetime import datetime

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
# Working cache (latest run per date + _last).
_CACHE_DIR = os.path.normpath(os.path.join(
    _MODULE_DIR, '..', 'static', 'data', 'cache', 'reconciliation', 'payrec'))
# Finalized-day history (written on End process):
#   static/data/cache/payrec/yyyy/mm/dd/payrec_status_yyyymmdd.json
_HISTORY_BASE = os.path.normpath(os.path.join(
    _MODULE_DIR, '..', 'static', 'data', 'cache', 'payrec'))

# Network folder holding the input files.
_INPUT_BASE = r"I:\Confirmation\Derivativos\OTC Tracker\Reconciliations\Pay_Rec"

# ── E-mail recipients ─────────────────────────────────────────────────────────
_MAILBOX = 'brazil.otc.ops@jpmorgan.com'
# Renato + Danilo in copy — same cc as Settlement Forecast / MTM / Accrual.
_CC = ['renato.montoza@jpmorgan.com', 'danilo.camposfonseca@jpmchase.com']
_SHARED_MAILBOX = 'otc.tracker@jpmorgan.com'
_SMTP_HOST = 'mailhost.jpmchase.net'
_SMTP_PORT = 25

# ── Constants ─────────────────────────────────────────────────────────────────
_TOL_CHECK_VALUE = 1.0        # Summary per-row |diff| < 1 → OK
_TOL_SPB_SETTLED = -0.50      # SPB: diff > -0.50 → Settled
# 0.005% COMM TER fee (IR). Applied to the NETTED value only when the net is a
# Pay (negative) — Alteryx `if Name='Pay' AND New Field='COMM TER'`. A Receive
# net (e.g. Lawton +230,927.66) is untouched; a Pay net (AMG -219,047.36) becomes
# -219,036.41, matching the SPB side. Applying it per-leg (before netting) would
# wrongly hit Lawton's pay leg, so it must run AFTER the per-client sum.
_COMM_TER_FEE = 1 - 0.00005
# Internal exclusive funds are EXEMPT from the COMM TER IR fee (Lawton, Atacama…).
# The fee only hits external corporate clients (e.g. AMG BRASIL).
_IR_EXEMPT_CPTY = ('LAWTON MULTIMERCADO EXCLUSIVO', 'ATACAMA MULTIMERCADO')
_JPM_ENTITIES = ('banco j.p. morgan s.a.', 'jpmorgan chase bank, n.a. - sao paulo')
# rlctahis inclusion allowlist (Alteryx TextInput[175]) — the main row-reducer.
_SDCONTA_HIST_ALLOW = {'9409', '4407', '9410', '4408', '9411', '4419', '9385',
                       '4413', '9386', '4414', '4406', 'AA', '4409'}


# ── Helpers ───────────────────────────────────────────────────────────────────
def _norm(s):
    """Accent/case-insensitive, non-alphanumeric-stripped key for column matching."""
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]', '', s.lower())


def _num(v):
    """Robust BR/US number parse. Handles '12550687,87' (BR), '12550687.87' (US),
    '1.510.500' (BR thousands), '119.400' (BR thousands), '-728,62', '(123)'."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        try:
            return float(v)
        except Exception:
            return 0.0
    s = str(v).strip().replace('R$', '').replace('\xa0', '').replace(' ', '')
    if not s or s in ('-', '.', ','):
        return 0.0
    neg = False
    if s.startswith('(') and s.endswith(')'):
        neg = True; s = s[1:-1]
    if s.endswith('-'):
        neg = True; s = s[:-1]
    if s.startswith('-'):
        neg = True; s = s[1:]
    c, d = s.count(','), s.count('.')
    if c and d:
        if s.rfind(',') > s.rfind('.'):        # BR: 1.234.567,89
            s = s.replace('.', '').replace(',', '.')
        else:                                   # US: 1,234,567.89
            s = s.replace(',', '')
    elif c:                                      # comma only
        if c == 1 and len(s.split(',')[1]) <= 2:
            s = s.replace(',', '.')             # decimal: 728,62 / 12550687,87
        else:
            s = s.replace(',', '')             # US thousands: 1,234,567
    elif d:                                      # dot only
        if d > 1:
            s = s.replace('.', '')             # BR thousands: 1.510.500
        elif len(s.split('.')[1]) == 3:
            s = s.replace('.', '')             # BR thousands: 119.400
        # else keep (US decimal: 12550687.87 / 15000000.0)
    try:
        f = float(s)
    except ValueError:
        return 0.0
    return -f if neg else f


def _fmt_num(v):
    try:
        return '{:,.2f}'.format(float(v))
    except Exception:
        return ''


def _int_key(v):
    """Whole-unit match key (Alteryx ToString(v, 0dp))."""
    try:
        return str(int(round(float(v))))
    except Exception:
        return ''


def _resolve(cols, *names):
    """Actual column whose normalized form matches (exact, then substring)."""
    norm_map = {_norm(c): c for c in cols}
    for name in names:
        n = _norm(name)
        if n in norm_map:
            return norm_map[n]
    for name in names:
        n = _norm(name)
        for kn, orig in norm_map.items():
            if n and n in kn:
                return orig
    return None


def _norm_cpty(name):
    """Collapse the multi-desk counterparty variants to their canonical name."""
    u = str(name or '').upper()
    if 'LAWTON' in u:
        return 'LAWTON MULTIMERCADO EXCLUSIVO'
    if 'ATACAMA' in u:
        return 'ATACAMA MULTIMERCADO'
    if 'BCO J.P' in u or 'BANCO J.P' in u:
        return 'Bco J.P. Morgan S.A.'
    return str(name or '').strip()


# ── Settlement Net Type per counterparty ──────────────────────────────────────
# Drives HOW a counterparty is matched:
#   Total Net → one netted value per group (Pay netted against Receive)  [default]
#   Pay/Rec   → Pay and Receive kept as two separate legs (never netted together)
#   No Net    → every individual trade/cashflow settles on its own (no netting)
# Resolved by joining the recon counterparty NAME → SPN (RefData.json) → NET.value
# (CounterpartyDetails.json). Unconfigured / not-yet-approved → Total Net.
_REFDATA_PATH = os.path.normpath(os.path.join(_MODULE_DIR, '..', 'static', 'data', 'RefData.json'))
_CPD_PATH = os.path.normpath(os.path.join(_MODULE_DIR, '..', 'static', 'data', 'CounterpartyDetails.json'))
_VALID_NET_TYPES = ('Total Net', 'Pay/Rec', 'No Net')


def _load_net_type_map():
    """{normalized counterparty name → net type}. Joins RefData (name→SPN) with
    CounterpartyDetails (SPN→NET.value). Only an Active (approved) net type
    overrides the default; everything else stays 'Total Net' (safe)."""
    name_to_spn = {}
    try:
        for r in json.load(open(_REFDATA_PATH, encoding='utf-8')):
            nm = _norm(r.get('COUNTERPARTY', ''))
            spn = str(r.get('SPN', '') or '').strip()
            if nm and spn and nm not in name_to_spn:
                name_to_spn[nm] = spn
    except Exception:
        return {}
    spn_to_net = {}
    try:
        for r in json.load(open(_CPD_PATH, encoding='utf-8')):
            spn = str(r.get('SPN', '') or '').strip()
            net = r.get('NET') or {}
            val = str(net.get('value', '') or '').strip()
            status = (str(net.get('status', '') or '').strip() or 'Active')
            if spn and val in _VALID_NET_TYPES and status == 'Active':
                spn_to_net[spn] = val
    except Exception:
        pass
    return {nm: spn_to_net.get(spn, 'Total Net') for nm, spn in name_to_spn.items()}


def _net_type_for(net_map, cpty_name):
    """Net type for a counterparty name (defaults to Total Net when unmapped)."""
    return (net_map or {}).get(_norm(cpty_name), 'Total Net')


def _emit_records(product, cpty, values, net_type):
    """Reduce a group's signed values into settlement records per the net type.
      Total Net → 1 record (Pay netted against Receive)
      Pay/Rec   → up to 2 records: Σ receives (>0) and Σ pays (<0), not netted
      No Net    → one record per individual value
    Sign decides Pay/Receive; near-zero results are dropped."""
    cu = str(cpty or '').upper()
    out = []

    def _rec(v):
        return {'product': product, 'cpty': cu, 'value': v,
                'pay_receive': 'Receive' if v > 0 else 'Pay'}

    if net_type == 'No Net':
        for v in values:
            if abs(v) >= 1e-9:
                out.append(_rec(v))
    elif net_type == 'Pay/Rec':
        recv = sum(v for v in values if v > 0)
        pay = sum(v for v in values if v < 0)
        if abs(recv) >= 1e-9:
            out.append(_rec(recv))
        if abs(pay) >= 1e-9:
            out.append(_rec(pay))
    else:  # Total Net (default)
        tot = sum(values)
        if abs(tot) >= 1e-9:
            out.append(_rec(tot))
    return out


# ── File reading ──────────────────────────────────────────────────────────────
def _read_table(src, sheet_hint=None):
    """Read a CSV/XLSX (path or FileStorage) → (list-of-dicts, columns).
    CSVs may be ';'-delimited (Latin-1 statements) or ','-quoted (settlement)."""
    import pandas as pd
    name = getattr(src, 'filename', None) or (src if isinstance(src, str) else '')
    lower = str(name).lower()
    try:
        if lower.endswith(('.xlsx', '.xls')):
            handle = src if isinstance(src, str) else src.stream
            xls = pd.ExcelFile(handle)
            sheet = xls.sheet_names[0]
            if sheet_hint:
                for sn in xls.sheet_names:
                    if _norm(sheet_hint) in _norm(sn):
                        sheet = sn
                        break
            df = xls.parse(sheet, dtype=str)
        else:
            df = _read_csv_any(src)
        df = df.fillna('')
        return df.to_dict('records'), list(df.columns)
    except Exception:
        return [], []


def _read_csv_any(src):
    """Read a CSV trying ';' (BR statements) then ',' (quoted settlement)."""
    import pandas as pd

    def _open():
        if isinstance(src, str):
            return src
        try:
            src.stream.seek(0)
        except Exception:
            pass
        return src.stream

    # Try (delimiter, encoding) combos: ';' Latin-1 / ';' UTF-8 (BR statements),
    # then ',' quoted for the settlement export. UTF-8 first avoids corrupting
    # accented headers when a file happens to be UTF-8.
    best = None
    for sep, quote in ((';', None), (',', '"')):
        for enc in ('utf-8-sig', 'latin-1'):
            try:
                kw = {'dtype': str, 'sep': sep, 'engine': 'python',
                      'encoding': enc, 'on_bad_lines': 'skip'}
                if quote:
                    kw['quotechar'] = quote
                df = pd.read_csv(_open(), **kw)
                if df.shape[1] > 1:
                    return df
                best = df if best is None else best
            except Exception:
                continue
    if best is not None:
        return best
    raise ValueError('unreadable csv')


def _classify_source(name):
    n = _norm(name)
    if n.startswith('cashflows'):
        return 'jpm_cash'
    if 'fxodetail' in n or n.startswith('fxo'):
        return 'jpm_fxo'
    if n.startswith('settlement'):
        return 'settlement'
    if 'historicomensagens' in n:
        # Same layout for JPM and MGT (name differs only by JPM↔MGT). The MGT
        # variant carries both payments and receipts (sign of Valor) and no
        # LMA-COMM, so it gets its own bucket.
        return 'spb_mgt' if 'mgt' in n else 'spb'
    if 'rldocted' in n:
        return 'sdconta_ted'
    if 'rlctahis' in n:
        return 'sdconta_int'
    if 'pagamentosmgt' in n:
        return 'mgt'
    return 'unknown'


# ── JPM / Cockpit side ────────────────────────────────────────────────────────
def _jpm_settlement(rows, cols, net_map=None):
    """settlement.csv → NDF. Per-Client (Tax Income + Amount), keeping only
    Settlement Net = 'TOTAL_NET'/'PAYREC_NET' and non-JPM clients. The per-client
    values are then reduced according to the client's configured net type."""
    c_client = _resolve(cols, 'Client')
    c_amount = _resolve(cols, 'Amount')
    c_tax = _resolve(cols, 'Tax Income')
    c_net = _resolve(cols, 'Settlement Net')
    groups = {}
    for r in rows:
        client = str(r.get(c_client, '') if c_client else '').strip()
        cl = client.lower()
        if not client or any(e in cl for e in _JPM_ENTITIES):
            continue
        if c_net:                                              # keep the netted rows
            sn = _norm(r.get(c_net, ''))
            if sn and sn not in (_norm('TOTAL_NET'), _norm('PAYREC_NET')):
                continue
        result = _num(r.get(c_tax, '') if c_tax else 0) + _num(r.get(c_amount, '') if c_amount else 0)
        groups.setdefault(client, []).append(result)
    out = []
    for client, values in groups.items():
        out += _emit_records('NDF', client, values, _net_type_for(net_map, client))
    return out


def _jpm_cashflows(rows, cols, net_map=None):
    """cashflows → COMM TER / COMM OPT / SWAP, reduced per the client's net type."""
    c_trade = _resolve(cols, 'Trade Id')
    c_amt = _resolve(cols, 'Amount')
    c_cpty = _resolve(cols, 'Cpty Name')
    c_event = _resolve(cols, 'Cashflow Event')
    c_asset = _resolve(cols, 'Asset Class')
    c_owner_le = _resolve(cols, 'Owner Legal Entity')

    recs = []
    for r in rows:
        if c_owner_le:                                         # Filter[195] = 0228
            le = re.sub(r'\D', '', str(r.get(c_owner_le, '')))
            if le and '228' not in le:
                continue
        if c_event and str(r.get(c_event, '')).strip().upper() == 'DELETE':  # Filter[121]
            continue
        recs.append({
            'trade': str(r.get(c_trade, '') if c_trade else '').strip(),
            'cpty': _norm_cpty(r.get(c_cpty, '') if c_cpty else ''),
            'amount': _num(r.get(c_amt, '') if c_amt else 0),
            'asset': str(r.get(c_asset, '') if c_asset else '').strip().upper(),
        })
    # COMM TER when a Trade Id has MORE THAN ONE leg (term structure) so both
    # legs share the product and net together; a singleton is COMM OPT.
    counts = {}
    for rec in recs:
        counts[rec['trade']] = counts.get(rec['trade'], 0) + 1
    for rec in recs:
        if rec['asset'] == 'INTEREST_RATE':
            rec['prod'] = 'SWAP'
        elif rec['asset'] == 'EQUITIES':
            rec['prod'] = 'EQUITIES'
        elif rec['trade'] and counts[rec['trade']] > 1:
            rec['prod'] = 'COMM TER'
        else:
            rec['prod'] = 'COMM OPT'
    # Per-(client, product) contributions (drop Bco J.P. and bilateral bank legs).
    groups = {}
    for rec in recs:
        cl = rec['cpty'].lower()
        if 'bco j.p' in cl or 'banco j.p' in cl:               # Filter[112]
            continue
        if 'banco' in cl:                                       # Filter[114] Bilateral
            continue
        key = (rec['cpty'], rec['prod'])
        groups.setdefault(key, []).append(rec['amount'])
    out = []
    for (cpty, prod), values in groups.items():
        for rec in _emit_records(prod, cpty, values, _net_type_for(net_map, cpty)):
            # 0.005% COMM TER IR fee: only on a Pay leg, and NOT for the exempt
            # internal exclusive funds (Lawton, Atacama…). Applied AFTER the
            # net-type reduction so it hits the aggregated pay, never a raw leg
            # of a netted client.
            if prod == 'COMM TER' and rec['value'] < 0 and cpty.upper() not in _IR_EXEMPT_CPTY:
                rec['value'] *= _COMM_TER_FEE
            out.append(rec)
    return out


def _jpm_fxo(rows, cols, net_map=None):
    """FXO Detail → FXO. Value from ATH SET AMT + Direction, reduced per net type."""
    c_amt = _resolve(cols, 'ATH SET AMT')
    c_dir = _resolve(cols, 'Direction')
    c_cpty = _resolve(cols, 'Counterparty Name')
    groups = {}
    for r in rows:
        cpty = str(r.get(c_cpty, '') if c_cpty else '').strip()
        amt = _num(r.get(c_amt, '') if c_amt else 0)
        direction = str(r.get(c_dir, '') if c_dir else '').strip().upper()
        value = -abs(amt) if direction == 'PAY' else abs(amt)
        if abs(value) < 1e-9:
            continue
        groups.setdefault(cpty, []).append(value)
    out = []
    for cpty, values in groups.items():
        out += _emit_records('FXO', cpty, values, _net_type_for(net_map, cpty))
    return out


# ── Client side ───────────────────────────────────────────────────────────────
def _cli_finalize(val, desc, titular, conta, sistema):
    """Merged SDConta post-processing (Filter[35], Formula[27], Filter[29])."""
    titular = str(titular or '').strip().replace('LMA-COMM-BR ', '').strip()
    if titular == '/OTC DERIVATIVES PRODUCTS':
        return None
    if not sistema:
        sistema = 'SDConta - conta interna'
    if titular == 'LIQS FINANCEIRAS - OPERACOES CAMBIO':
        sistema = 'SDConta - conta externa FX'
    dn = _norm(desc)
    pr = 'Receive' if 'debito' in dn else 'Pay'
    val = -abs(val) if pr == 'Pay' else abs(val)
    if pr == 'Pay' and conta == '0511600-3':
        val = -val
    if 'LAWTON MULTIMERCADO EXCLUSIVO' in titular.upper():
        titular = 'LAWTON MULTIMERCADO EXCLUSIVO'
    if not (val > 1 or val < -1):
        return None
    return {'value': val, 'client': titular, 'sistema': sistema, 'snumconta': str(conta or '').strip(),
            'product': 'NDF', 'pay_receive': pr}


def _cli_rlctahis(rows, cols):
    """SDConta interna — nHistorico allowlist row-reducer."""
    c_val = _resolve(cols, 'nVlrLanc')
    c_desc = _resolve(cols, 'sDescricao')
    c_tit = _resolve(cols, 'sNomeTitular')
    c_conta = _resolve(cols, 'sNumConta')
    c_hist = _resolve(cols, 'nHistorico')
    out = []
    for r in rows:
        hist = str(r.get(c_hist, '') if c_hist else '').strip()
        conta = str(r.get(c_conta, '') if c_conta else '').strip()
        desc = str(r.get(c_desc, '') if c_desc else '')
        if hist == '5347' and conta == '0512026-0':            # Formula[34] remap
            hist = '9409'; desc = 'DEBITO NDF'                 # → Receive (FX transfer row)
        # Join[174] allowlist. (The Alteryx Filter[153]/Join[154] recapture of the
        # 0511600-3 "DEB.TRANSF" entries is only a value-annotation on the TED
        # stream — it produces no display row — so it is intentionally omitted.)
        if hist not in _SDCONTA_HIST_ALLOW:
            continue
        val = _num(r.get(c_val, '') if c_val else 0)
        titular = str(r.get(c_tit, '') if c_tit else '').strip()
        if val < 1:
            titular = 'ZERAGEM DA CONTA'
        rec = _cli_finalize(val, desc, titular, conta, sistema='')
        if rec:
            out.append(rec)
    return out


def _cli_ted(rows, cols):
    """SDConta externa (TED). value=nValor, titular=sNomeEmissor, conta composed."""
    c_val = _resolve(cols, 'nValor', 'nVlrLanc')
    c_tit = _resolve(cols, 'sNomeEmissor', 'sNomeTitular')
    c_banco = _resolve(cols, 'nBancoEmissor')
    c_ag = _resolve(cols, 'nAgDebitada')
    c_cc = _resolve(cols, 'nCcDebitada')
    out = []
    for r in rows:
        val = abs(_num(r.get(c_val, '') if c_val else 0))
        titular = str(r.get(c_tit, '') if c_tit else '').strip()
        conta = '-'.join([str(r.get(c_banco, '')).strip(), str(r.get(c_ag, '')).strip(),
                          str(r.get(c_cc, '')).strip()]).strip('-') if (c_banco and c_ag and c_cc) else ''
        rec = _cli_finalize(val, 'DEBITO NDF', titular, conta, sistema='SDConta - conta externa')
        if rec:
            out.append(rec)
    return out


def _cli_spb(rows, cols, mgt=False):
    """SPB externa — Descrição Evento contains Derivativos/LMA-COMM-BR.

    JPM file (HistoricoMensagensJPM): outgoing settlements only → always Pay
    (value forced negative). MGT file (HistoricoMensagensMGT): carries BOTH
    payments and receipts, so the SIGN of Valor decides direction (negative →
    Pay, positive → Receive) and the value is used as-is. The MGT file has no
    LMA-COMM rows; the 'lma-comm-br' term below is simply never matched there."""
    c_val = _resolve(cols, 'Valor (R$)', 'Valor')
    c_evt = _resolve(cols, 'Descrição Evento', 'Descricao Evento')
    c_conta = _resolve(cols, 'sNumConta')
    sistema = 'SPB - MGT' if mgt else 'SPB - conta externa'
    out = []
    for r in rows:
        evt = str(r.get(c_evt, '') if c_evt else '')
        en = evt.lower()
        if 'derivativos' not in en and 'lma-comm-br' not in en:   # Filter[48]
            continue
        raw = _num(r.get(c_val, '') if c_val else 0)
        val = raw if mgt else -abs(raw)          # MGT: signed (Pay/Receive); JPM: always Pay
        if abs(val) < 1e-9:
            continue
        titular = re.sub(r'(?i)operacao de derivativos-', '', evt).strip()
        titular = titular.replace('LMA-COMM-BR ', '').strip()    # strip the LMA prefix
        conta = str(r.get(c_conta, '') if c_conta else '').strip()
        out.append({'value': val, 'client': titular, 'sistema': sistema,
                    'snumconta': conta, 'product': 'NDF',
                    'pay_receive': 'Pay' if val < 0 else 'Receive'})
    return out


# ── Reconciliation ────────────────────────────────────────────────────────────
def _reconcile(jpm, client):
    buckets = {}
    for c in client:
        buckets.setdefault(_int_key(c['value']), []).append(c)
    details = []
    matched = set()
    for j in jpm:
        pool = buckets.get(_int_key(j['value']), [])
        mate = None
        for c in pool:
            if id(c) not in matched:
                mate = c; matched.add(id(c)); break
        if mate:
            diff = mate['value'] - j['value']
            status = 'Settled' if abs(diff) < 0.005 else 'Pending'   # agree to the cent
            if mate['sistema'] == 'SPB - conta externa' and diff > _TOL_SPB_SETTLED:
                status = 'Settled'
            details.append({
                'product': j['product'] or mate.get('product') or 'NDF',
                'jpm_cpty': j['cpty'], 'client': mate['client'], 'pay_receive': j['pay_receive'],
                'jpm_value': j['value'], 'client_value': mate['value'],
                'sistema': mate['sistema'], 'snumconta': mate['snumconta'],
                'status': status, 'difference': diff})
        else:
            details.append({
                'product': j['product'], 'jpm_cpty': j['cpty'], 'client': '',
                'pay_receive': j['pay_receive'], 'jpm_value': j['value'], 'client_value': '',
                'sistema': '', 'snumconta': '', 'status': 'Pending', 'difference': -j['value']})
    for c in client:
        if id(c) in matched:
            continue
        details.append({
            'product': c.get('product') or 'NDF', 'jpm_cpty': '', 'client': c['client'],
            'pay_receive': c['pay_receive'], 'jpm_value': '', 'client_value': c['value'],
            'sistema': c['sistema'], 'snumconta': c['snumconta'],
            'status': 'Pending', 'difference': c['value']})
    return details, _summary(jpm, client)


def _summary(jpm, client):
    def agg(recs, label):
        return {'qty': sum(1 for r in recs if r['pay_receive'] == label),
                'sum': sum(r['value'] for r in recs if r['pay_receive'] == label)}
    rows = []
    tot = {'jq': 0, 'cq': 0, 'jv': 0.0, 'cv': 0.0}
    for label in ('Pay', 'Receive'):
        j = agg(jpm, label); c = agg(client, label)
        rows.append({
            'pay_receive': label, 'jpm_qty': j['qty'], 'client_qty': c['qty'],
            'check_qty': 'OK' if j['qty'] == c['qty'] else 'Not OK',
            'jpm_value': j['sum'], 'client_value': c['sum'], 'difference': j['sum'] - c['sum'],
            'check_value': 'OK' if abs(j['sum'] - c['sum']) < _TOL_CHECK_VALUE else 'Not OK'})
        tot['jq'] += j['qty']; tot['cq'] += c['qty']; tot['jv'] += j['sum']; tot['cv'] += c['sum']
    rows.append({
        'pay_receive': 'TOTAL', 'jpm_qty': tot['jq'], 'client_qty': tot['cq'],
        'check_qty': 'OK' if tot['jq'] == tot['cq'] else 'Not OK',
        'jpm_value': tot['jv'], 'client_value': tot['cv'], 'difference': tot['jv'] - tot['cv'],
        'check_value': 'OK' if abs(tot['jv'] - tot['cv']) < 0.005 else 'Not OK'})
    return rows


def _split_tables(details):
    pend_pay, pend_rec, settled = [], [], []
    for d in details:
        if d['status'] == 'Settled':
            settled.append(d)
        elif d['pay_receive'] == 'Pay':
            pend_pay.append(d)
        else:
            pend_rec.append(d)
    return pend_pay, pend_rec, settled


# ── Public API ────────────────────────────────────────────────────────────────
def _gather_sources(files, mode):
    srcs = []
    if mode == 'manual' and files:
        items = [(f.filename, f) for f in files if getattr(f, 'filename', '')]
    else:
        if not os.path.isdir(_INPUT_BASE):
            raise FileNotFoundError('Pay/Rec input folder not found: %s' % _INPUT_BASE)
        items = [(os.path.basename(p), p) for p in sorted(glob.glob(os.path.join(_INPUT_BASE, '*.*')))]
    for name, src in items:
        bucket = _classify_source(name)
        sheet = 'data' if bucket == 'jpm_cash' else ('FXO Detail' if bucket == 'jpm_fxo' else None)
        rows, cols = _read_table(src, sheet)
        srcs.append((bucket, rows, cols))
    return srcs


def run_payrec(recon_date, files=None, mode='auto'):
    srcs = _gather_sources(files, mode)
    if not srcs:
        raise FileNotFoundError('No Pay/Rec input files provided or found for this date.')

    # Net type per counterparty (name → SPN → CounterpartyDetails.NET), resolved
    # once and shared by the JPM producers to branch the batimento.
    net_map = _load_net_type_map()

    jpm, client = [], []
    for bucket, rows, cols in srcs:
        if not rows:
            continue
        if bucket == 'settlement':
            jpm += _jpm_settlement(rows, cols, net_map)
        elif bucket == 'jpm_cash':
            jpm += _jpm_cashflows(rows, cols, net_map)
        elif bucket == 'jpm_fxo':
            jpm += _jpm_fxo(rows, cols, net_map)
        elif bucket == 'sdconta_int':
            client += _cli_rlctahis(rows, cols)
        elif bucket == 'sdconta_ted':
            client += _cli_ted(rows, cols)
        elif bucket == 'spb':
            client += _cli_spb(rows, cols)
        elif bucket == 'spb_mgt':
            client += _cli_spb(rows, cols, mgt=True)

    details, summary = _reconcile(jpm, client)
    pend_pay, pend_rec, settled = _split_tables(details)
    payload = {
        'success': True, 'recon_date': recon_date, 'recon_date_fmt': _fmt_date(recon_date),
        'summary': summary, 'pending_payment': pend_pay,
        'pending_receivement': pend_rec, 'settled': settled,
        'meta': '{} JPM · {} client · {} settled · {} pending'.format(
            len(jpm), len(client), len(settled), len(pend_pay) + len(pend_rec)),
    }
    _persist(recon_date, payload)
    return payload


def _fmt_date(recon_date):
    try:
        return datetime.strptime(recon_date[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
    except Exception:
        return recon_date or ''


def _persist(recon_date, payload):
    """Working cache: latest run for the date + _last (overwritten each run)."""
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        key = (recon_date or 'last').replace('/', '-')
        with open(os.path.join(_CACHE_DIR, key + '.json'), 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False)
        with open(os.path.join(_CACHE_DIR, '_last.json'), 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False)
    except Exception:
        pass


def _history_path(recon_date):
    """static/data/cache/payrec/yyyy/mm/dd/payrec_status_yyyymmdd.json for a date."""
    try:
        dt = datetime.strptime((recon_date or '')[:10], '%Y-%m-%d')
    except Exception:
        return None
    return os.path.join(_HISTORY_BASE, dt.strftime('%Y'), dt.strftime('%m'), dt.strftime('%d'),
                        'payrec_status_{}.json'.format(dt.strftime('%Y%m%d')))


def _load_flat(recon_date=''):
    """Read the working cache. With a date → only that date's file (no _last
    fallback, so a day without a run shows empty); without a date → _last."""
    try:
        if recon_date:
            cand = os.path.join(_CACHE_DIR, recon_date.replace('/', '-') + '.json')
        else:
            cand = os.path.join(_CACHE_DIR, '_last.json')
        if os.path.exists(cand):
            with open(cand, encoding='utf-8') as fh:
                return json.load(fh)
    except Exception:
        pass
    return None


def finalize_history(recon_date):
    """On End process: persist the day's result to the dated history path so it
    can be pulled back when the reference date is set to a past day. Returns path."""
    data = _load_flat(recon_date)
    if not data or not (data.get('summary') or data.get('settled')
                        or data.get('pending_payment') or data.get('pending_receivement')):
        return None
    p = _history_path(recon_date)
    if not p:
        return None
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False)
        return p
    except Exception:
        return None


def justify_row(recon_date, table, index, comment):
    """Justify one pending row: set its status to 'Justified' and store the
    operator's comment, then re-persist the working cache so End process (and the
    e-mailed situation) reflect it. `table` is 'pay' or 'rec'. Returns the updated
    payload, or None when the date/row can't be resolved."""
    data = _load_flat(recon_date)
    if not data:
        return None
    key = {'pay': 'pending_payment', 'rec': 'pending_receivement'}.get(table)
    if not key:
        return None
    rows = data.get(key) or []
    try:
        index = int(index)
    except (TypeError, ValueError):
        return None
    if not (0 <= index < len(rows)):
        return None
    rows[index]['status'] = 'Justified'
    rows[index]['comment'] = str(comment or '').strip()
    _persist(recon_date, data)
    return data


def load_last(recon_date=''):
    """For the page: prefer the finalized dated history (browsing past days),
    then the working cache, then an empty shell."""
    if recon_date:
        p = _history_path(recon_date)
        if p and os.path.exists(p):
            try:
                with open(p, encoding='utf-8') as fh:
                    return json.load(fh)
            except Exception:
                pass
    data = _load_flat(recon_date)
    if data:
        return data
    return {'success': True, 'summary': [], 'pending_payment': [],
            'pending_receivement': [], 'settled': []}


# ── E-mail (final situation of the day) ───────────────────────────────────────
def _decorate_rows(rows, total_labels=()):
    out = []
    for r in rows:
        d = dict(r)
        for k in ('jpm_value', 'client_value', 'difference'):
            v = r.get(k, '')
            d[k + '_fmt'] = _fmt_num(v) if v not in ('', None) else ''
            try:
                d[k + '_neg'] = (v not in ('', None)) and float(v) < 0
            except Exception:
                d[k + '_neg'] = False
        d['is_total'] = str(r.get('pay_receive', '')).upper() in total_labels
        out.append(d)
    return out


def send_payrec_email(recon_date):
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.image import MIMEImage
    from flask import render_template, current_app

    data = load_last(recon_date)
    if not data or not (data.get('summary') or data.get('settled')
                        or data.get('pending_payment') or data.get('pending_receivement')):
        return False

    recon_date_fmt = _fmt_date(recon_date) or data.get('recon_date_fmt', '')
    try:
        current_year = datetime.strptime((recon_date or '')[:10], '%Y-%m-%d').year
    except Exception:
        current_year = datetime.now().year

    # Show the Comment column only when the day actually has justifications.
    def _any_comment(rows):
        return any(str((r or {}).get('comment', '') or '').strip() for r in (rows or []))
    has_comments = (_any_comment(data.get('pending_payment', [])) or
                    _any_comment(data.get('pending_receivement', [])))

    html_body = render_template(
        'pages/email-template-recon-payrec.html',
        recon_date_fmt=recon_date_fmt,
        summary=_decorate_rows(data.get('summary', []), total_labels=('TOTAL',)),
        pending_payment=_decorate_rows(data.get('pending_payment', [])),
        pending_receivement=_decorate_rows(data.get('pending_receivement', [])),
        settled=_decorate_rows(data.get('settled', [])),
        has_comments=has_comments,
        current_year=current_year,
    )

    msg = MIMEMultipart('related')
    msg['Subject'] = 'Pay/Rec — OTC Settlement Status - {}'.format(recon_date_fmt)
    msg['From'] = _SHARED_MAILBOX
    msg['To'] = _MAILBOX
    msg['Cc'] = ', '.join(_CC)

    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText('Pay/Rec end-of-day situation for {}. View in an HTML client.'.format(recon_date_fmt), 'plain'))
    alt.attach(MIMEText(html_body, 'html'))
    msg.attach(alt)

    try:
        for lp in [os.path.join(current_app.root_path, 'static', 'images', 'logo.png'),
                   os.path.normpath(os.path.join(current_app.root_path, '..', 'static', 'images', 'logo.png'))]:
            if os.path.exists(lp):
                with open(lp, 'rb') as f:
                    img = MIMEImage(f.read())
                    img.add_header('Content-ID', '<otc_logo>')
                    img.add_header('Content-Disposition', 'inline', filename='logo.png')
                    msg.attach(img)
                break
    except Exception:
        pass

    try:
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as server:
            server.sendmail(_SHARED_MAILBOX, [_MAILBOX] + _CC, msg.as_string())
        return True
    except Exception:
        return False
