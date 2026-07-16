"""
Pay/Rec Reconciliation engine — faithful port of the Alteryx "PayRec" workflow,
verified against the ground-truth daily output.

JPM / Cockpit side (3 sources, Union'd):
  settlement.csv      → NDF   (value = Tax Income + Amount, per-Client sum, Settlement Net='TOTAL_NET')
  cashflows_*.xlsx    → COMM TER / SWAP  (per-client NET sum; Owner Legal Entity='0228')
  FXO Detail*.xlsx    → FXO   (value from ATH SET AMT + Direction)

Client side (Union'd):
  rlctahis.csv        → SDConta interna  (nHistorico allowlist)
  RLDOCREC.csv        → TEDs RECEBIDAS (JPM + MGT). Credited to agência 98 / house
                        account (JPM 5116003, MGT 5181643); LE from nNumEmpresaDestino
                        (39=JPM, 1315=MGT). Every kept row is a Receive.
  HistoricoMensagensJPM_*.csv → SPB externa — TEDs ENVIADAS (pagas) only
                        (Descrição Evento contains Derivativos/LMA-COMM-BR; always Pay)
  HistoricoMensagensMGT_*.csv → SPB MGT — TEDs ENVIADAS (pagas) only (same layout; always Pay)

Received TEDs come exclusively from RLDOCREC; the HistoricoMensagens files are
payments only. (The legacy rlDocTed01 received-TED source has been retired.)

Match: JPM value ↔ client value, rounded to whole units (value-only join).
Difference = Client - JPM;  Status = Settled if 0 else Pending (SPB tol > -0.50).
"""

import os
import re
import json
import glob
import logging
import unicodedata
from datetime import datetime

_LOG = logging.getLogger(__name__)
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
# Working cache (latest run per date + _last).
_CACHE_DIR = os.path.normpath(os.path.join(
    _MODULE_DIR, '..', 'static', 'data', 'cache', 'reconciliation', 'payrec'))
# Finalized-day history (written on End process):
#   static/data/cache/payrec/yyyy/mm/dd/payrec_status_yyyymmdd.json
_HISTORY_BASE = os.path.normpath(os.path.join(
    _MODULE_DIR, '..', 'static', 'data', 'cache', 'payrec'))

# Network folder holding the input files.
_INPUT_BASE = r"I:\Confirmation\Derivativos\OTC Tracker\Reconciliations\payrec"

# ── E-mail recipients ─────────────────────────────────────────────────────────
_MAILBOX = 'brazil.otc.ops@jpmorgan.com'
# Renato + Danilo in copy — same cc as Settlement Forecast / MTM / Accrual.
_CC = ['renato.montoza@jpmorgan.com', 'danilo.camposfonseca@jpmchase.com']
_SHARED_MAILBOX = 'otc.tracker@jpmorgan.com'
_SMTP_HOST = 'mailhost.jpmchase.net'
_SMTP_PORT = 25

# ── Constants ─────────────────────────────────────────────────────────────────
_TOL_CHECK_VALUE = 1.0        # Summary per-row |diff| < 1 → OK
_TOL_SETTLED = 1.0            # Per-row |JPM − client| < R$1 (cents) → Settled. The
                             # IR fee (0.005%) and summing cent-rounded client legs
                             # leave a few centavos of noise; a half-cent threshold
                             # wrongly parked those matched rows in Pending.
_TOL_SPB_SETTLED = -0.50      # SPB: diff > -0.50 → Settled
# COMM OPT (option premiums) settle NET of the ~0.005% IR withheld on the premium,
# so the JPM (gross) and client (net) sides can differ by up to 0.005% plus a small
# rounding slack. Match and settle COMM OPT within 0.005% + 20 cents instead of the
# exact whole-unit key.
_TOL_COMM_OPT_PCT = 0.00005   # 0.005%
_TOL_COMM_OPT_ABS = 0.20      # + 20 cents
# 0.005% COMM TER fee (IR). It is withheld TRADE-LEVEL: the cashflow legs are first
# netted per Trade Id, then the fee is applied to each trade whose net is a Pay
# (negative) — the amount paid drops by |trade-net|·0.005%, so the counterparty's
# total received rises by that much. The fee must NOT be applied per raw leg: a
# term-structure trade has offsetting monthly legs that cancel, and taxing them
# individually grossly over-states the IR. A counterparty whose trades net to a
# positive total still owes the fee on its individual Pay trades. Example: a +100,000
# receive trade and a −20,000 pay trade → gross 80,000, fee 20,000·0.005% = 1.00,
# net 80,001.00. Internal exclusive funds (Lawton, Atacama…) stay exempt.
_COMM_TER_FEE = 1 - 0.00005
# Internal exclusive funds are EXEMPT from the COMM TER IR fee (Lawton, Atacama…).
# The fee only hits external corporate clients (e.g. AMG BRASIL).
_IR_EXEMPT_CPTY = ('LAWTON MULTIMERCADO EXCLUSIVO', 'ATACAMA MULTIMERCADO')
_JPM_ENTITIES = ('banco j.p. morgan s.a.', 'jpmorgan chase bank, n.a. - sao paulo')
# rlctahis inclusion allowlist (Alteryx TextInput[175]) — the main row-reducer.
_SDCONTA_HIST_ALLOW = {'9409', '4407', '9410', '4408', '9411', '4419', '9385',
                       '4413', '9386', '4414', '4406', 'AA', '4409'}
# rlctahis nHistorico codes that are SWAP settlements (not NDF). Everything else
# in the allowlist stays NDF. These flows net against the JPM SWAP side.
_SDCONTA_HIST_SWAP = {'4406', '9385', '4413'}

# RLDOCREC — received-TED report. Keep only rows credited to agência 98 and one of
# the two house accounts (nCtCredtd); the receiving Legal Entity is read from
# nNumEmpresaDestino (falling back to the account when that column is blank).
_RLDOCREC_AG = '98'
_RLDOCREC_CTA_LE = {'5116003': 'JPM', '5181643': 'MGT'}     # nCtCredtd → LE
_RLDOCREC_EMP_LE = {'39': 'JPM', '1315': 'MGT'}             # nNumEmpresaDestino → LE


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


def _digits(v):
    """Digits only, leading zeros stripped, for stable account/agency compares."""
    d = re.sub(r'\D', '', str(v or ''))
    return str(int(d)) if d else ''


def _rec_col(cols, name, idx):
    """Resolve a column by header name, falling back to its 0-based position
    (Excel column letter) when the header doesn't match."""
    c = _resolve(cols, name)
    if c is not None:
        return c
    return cols[idx] if 0 <= idx < len(cols) else None


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


def _is_atacama(name):
    """Atacama counterparty (any name variant)."""
    return 'atacama' in _norm(name)


def _net_type_for(net_map, cpty_name):
    """Net type for a counterparty name (defaults to Total Net when unmapped).
    Atacama is ALWAYS Total Net (business rule), regardless of CounterpartyDetails."""
    if _is_atacama(cpty_name):
        return 'Total Net'
    return (net_map or {}).get(_norm(cpty_name), 'Total Net')


def _le_from_legal_entity(v):
    """Legal Entity column (settlement file) → LE. 'JPMorgan Chase Bank, N.A. -
    São Paulo Branch' → MGT; 'Banco J.P. Morgan S.A.' (and anything else) → JPM."""
    n = _norm(v)
    if 'chasebank' in n or 'saopaulo' in n:
        return 'MGT'
    return 'JPM'


def _emit_records(product, cpty, values, net_type, le='JPM'):
    """Reduce a group's signed values into settlement records per the net type.
      Total Net → 1 record (Pay netted against Receive)
      Pay/Rec   → up to 2 records: Σ receives (>0) and Σ pays (<0), not netted
      No Net    → one record per individual value
    Sign decides Pay/Receive; near-zero results are dropped. `le` (JPM/MGT) is
    carried on every emitted record (JPM for cashflows/FXO; per Legal Entity for
    the settlement file)."""
    cu = str(cpty or '').upper()
    if _is_atacama(cu):
        product = 'EQUITIES'          # Atacama is always EQUITIES (business rule)
    out = []

    def _rec(v):
        return {'product': product, 'cpty': cu, 'value': v,
                'pay_receive': 'Receive' if v > 0 else 'Pay', 'le': le}

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
            # Read the workbook into memory so the on-disk file is only held open
            # for the read itself. pd.ExcelFile keeps its handle open until closed,
            # which on Windows locks the file (can't delete/edit the cashflows
            # export) — so slurp the bytes, then close the ExcelFile explicitly.
            import io
            if isinstance(src, str):
                with open(src, 'rb') as _fh:
                    handle = io.BytesIO(_fh.read())
            else:
                try:
                    src.stream.seek(0)
                except Exception:
                    pass
                handle = io.BytesIO(src.stream.read())
            xls = pd.ExcelFile(handle)
            try:
                sheet = xls.sheet_names[0]
                if sheet_hint:
                    for sn in xls.sheet_names:
                        if _norm(sheet_hint) in _norm(sn):
                            sheet = sn
                            break
                df = xls.parse(sheet, dtype=str)
            finally:
                xls.close()
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
    if 'rldocrec' in n:
        return 'sdconta_rec'                    # received TEDs (JPM + MGT)
    if 'historicomensagens' in n:
        # Same layout for JPM and MGT (name differs only by JPM↔MGT). Both are now
        # payments-only (sent TEDs); received TEDs come from RLDOCREC. MGT still
        # gets its own bucket for its 'SPB - MGT' sistema label / MGT legal entity.
        return 'spb_mgt' if 'mgt' in n else 'spb'
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
    c_le = _resolve(cols, 'Legal Entity')                      # JPM vs MGT (per row)
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
        le = _le_from_legal_entity(r.get(c_le, '')) if c_le else 'JPM'
        groups.setdefault((client, le), []).append(result)     # split per Legal Entity
    out = []
    for (client, le), values in groups.items():
        out += _emit_records('NDF', client, values, _net_type_for(net_map, client), le=le)
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
        if _is_atacama(rec['cpty']):
            rec['prod'] = 'EQUITIES'      # Atacama always EQUITIES → one group, netted together
        elif rec['asset'] == 'INTEREST_RATE':
            rec['prod'] = 'SWAP'
        elif rec['asset'] == 'EQUITIES':
            rec['prod'] = 'EQUITIES'
        elif rec['trade'] and counts[rec['trade']] > 1:
            rec['prod'] = 'COMM TER'
        else:
            rec['prod'] = 'COMM OPT'
    # Per-(client, product) contributions (drop Bco J.P. and bilateral bank legs).
    # COMM TER carries a TRADE-LEVEL 0.005% IR fee, so its legs are first netted per
    # Trade Id and the fee is applied to each NEGATIVE trade-net (never to raw legs
    # that cancel out within a trade); every other product keeps its individual legs.
    groups = {}
    comm_ter = {}                                              # cpty → {trade_id → net}
    for rec in recs:
        cl = rec['cpty'].lower()
        if 'bco j.p' in cl or 'banco j.p' in cl:               # Filter[112]
            continue
        if 'banco' in cl:                                       # Filter[114] Bilateral
            continue
        if rec['prod'] == 'COMM TER':
            per_trade = comm_ter.setdefault(rec['cpty'], {})
            per_trade[rec['trade']] = per_trade.get(rec['trade'], 0.0) + rec['amount']
        else:
            groups.setdefault((rec['cpty'], rec['prod']), []).append(rec['amount'])
    # Fold each COMM TER trade-net into its group. The 0.005% IR is withheld on a
    # trade that nets to a Pay (negative): the amount paid drops by the tax, so the
    # counterparty's total received goes UP by |trade-net|·0.005%. A trade that nets
    # to a Receive (positive) is untouched, as are the exempt exclusive funds
    # (Lawton, Atacama…). Netting per trade first is what keeps the fee off legs that
    # already cancel inside a term structure (per-leg would grossly over-tax).
    for cpty, trades in comm_ter.items():
        exempt = cpty.upper() in _IR_EXEMPT_CPTY
        groups[(cpty, 'COMM TER')] = [
            (tnet * _COMM_TER_FEE if (not exempt and tnet < 0) else tnet)
            for tnet in trades.values()
        ]
    out = []
    for (cpty, prod), values in groups.items():
        out += _emit_records(prod, cpty, values, _net_type_for(net_map, cpty))
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
def _cli_finalize(val, desc, titular, conta, sistema, product='NDF'):
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
            'product': product, 'pay_receive': pr, 'le': 'JPM'}


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
        # nHistorico 4406 / 9385 / 4413 are SWAP flows; the rest of the allowlist is NDF.
        product = 'SWAP' if hist in _SDCONTA_HIST_SWAP else 'NDF'
        rec = _cli_finalize(val, desc, titular, conta, sistema='', product=product)
        if rec:
            out.append(rec)
    return out


def _cli_rec(rows, cols):
    """RLDOCREC — TEDs RECEBIDAS for both JPM and MGT (replaces the receive side
    that used to come from rlDocTed01 / the MGT SPB receipts).

    Keep only rows credited to agência 98 (nAgCredtd, col C) and one of the two
    house accounts (nCtCredtd, col D): JPM 5116003 / MGT 5181643. value = nValor
    (col H) as a Receive (positive); counterparty = sNomeCliDebitado (col N, who
    sent the TED); the sender's bank/agency/account (cols O/P/Q) compose snumconta;
    the receiving Legal Entity is nNumEmpresaDestino (col AB: 39=JPM, 1315=MGT),
    falling back to the credited account when that column is blank."""
    c_ag = _rec_col(cols, 'nAgCredtd', 2)                # col C
    c_cta = _rec_col(cols, 'nCtCredtd', 3)               # col D
    c_val = _rec_col(cols, 'nValor', 7)                  # col H
    c_nome = _rec_col(cols, 'sNomeCliDebitado', 13)      # col N
    c_banco = _rec_col(cols, 'nIdBanco', 14)             # col O
    c_agd = _rec_col(cols, 'nAgDebtd', 15)               # col P
    c_ctd = _rec_col(cols, 'nCtDebtd', 16)               # col Q
    c_emp = _rec_col(cols, 'nNumEmpresaDestino', 27)     # col AB
    out = []
    for r in rows:
        ag = _digits(r.get(c_ag, '') if c_ag else '')
        cta = _digits(r.get(c_cta, '') if c_cta else '')
        if ag != _RLDOCREC_AG or cta not in _RLDOCREC_CTA_LE:
            continue
        val = abs(_num(r.get(c_val, '') if c_val else 0))
        if val <= 1:                                     # drop sub-R$1 noise (as SDConta)
            continue
        emp = _digits(r.get(c_emp, '') if c_emp else '')
        le = _RLDOCREC_EMP_LE.get(emp) or _RLDOCREC_CTA_LE.get(cta, 'JPM')
        titular = str(r.get(c_nome, '') if c_nome else '').strip()
        conta = '-'.join(x for x in [
            _digits(r.get(c_banco, '') if c_banco else ''),
            _digits(r.get(c_agd, '') if c_agd else ''),
            _digits(r.get(c_ctd, '') if c_ctd else '')] if x)
        out.append({'value': val, 'client': titular, 'sistema': 'SDConta - conta externa',
                    'snumconta': conta, 'product': 'NDF',
                    'pay_receive': 'Receive', 'le': le})
    return out


def _cli_spb(rows, cols, mgt=False):
    """SPB externa — TEDs ENVIADAS (pagas) only, for both the JPM
    (HistoricoMensagensJPM) and MGT (HistoricoMensagensMGT) files. Keep only rows
    whose Descrição Evento contains Derivativos/LMA-COMM-BR and force Pay
    (negative). Received TEDs are handled separately by RLDOCREC (_cli_rec)."""
    c_val = _resolve(cols, 'Valor (R$)', 'Valor')
    c_evt = _resolve(cols, 'Descrição Evento', 'Descricao Evento')
    c_conta = _resolve(cols, 'sNumConta')
    sistema = 'SPB - MGT' if mgt else 'SPB - conta externa'
    out = []
    for r in rows:
        evt = str(r.get(c_evt, '') if c_evt else '')
        en = evt.lower()
        if not ('derivativos' in en or 'lma-comm-br' in en):     # Descrição filter (Filter[48])
            continue
        val = -abs(_num(r.get(c_val, '') if c_val else 0))       # sent settlement → Pay (negative)
        if abs(val) < 1e-9:
            continue
        titular = re.sub(r'(?i)operacao de derivativos-', '', evt).strip()
        titular = titular.replace('LMA-COMM-BR ', '').strip()    # strip the LMA prefix
        conta = str(r.get(c_conta, '') if c_conta else '').strip()
        out.append({'value': val, 'client': titular, 'sistema': sistema,
                    'snumconta': conta, 'product': 'NDF',
                    'pay_receive': 'Pay', 'le': 'MGT' if mgt else 'JPM'})
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
        # COMM OPT premiums are settled net of ~0.005% IR, so the exact whole-unit
        # key can miss. Fall back to the nearest unmatched client value within
        # 0.005% of the JPM (gross) value.
        if mate is None and j.get('product') == 'COMM OPT':
            tol = abs(j['value']) * _TOL_COMM_OPT_PCT + _TOL_COMM_OPT_ABS
            best, best_d = None, None
            for c in client:
                if id(c) in matched:
                    continue
                d = abs(c['value'] - j['value'])
                if d <= tol and (best_d is None or d < best_d):
                    best, best_d = c, d
            if best is not None:
                mate = best
                matched.add(id(best))
        # Any product: a cents-level rounding (the COMM TER IR fee, or summing
        # cent-rounded client legs of a netted counterparty) can straddle the .5
        # whole-unit boundary and miss the exact-key bucket. Fall back to the nearest
        # unmatched client value within R$1.
        if mate is None:
            best, best_d = None, None
            for c in client:
                if id(c) in matched:
                    continue
                d = abs(c['value'] - j['value'])
                if d < _TOL_SETTLED and (best_d is None or d < best_d):
                    best, best_d = c, d
            if best is not None:
                mate = best
                matched.add(id(best))
        if mate:
            diff = mate['value'] - j['value']
            status = 'Settled' if abs(diff) < _TOL_SETTLED else 'Pending'   # agree within centavos (< R$1)
            if mate['sistema'] == 'SPB - conta externa' and diff > _TOL_SPB_SETTLED:
                status = 'Settled'
            # COMM OPT: premium net of the ~0.005% IR → settle within 0.005% + 20 cents.
            if j.get('product') == 'COMM OPT' and \
                    abs(diff) <= abs(j['value']) * _TOL_COMM_OPT_PCT + _TOL_COMM_OPT_ABS:
                status = 'Settled'
            details.append({
                # LE is authoritative on the JPM/Cockpit side: settlement carries
                # it from the Legal Entity column; cashflows/FXO are always JPM.
                'le': j.get('le', 'JPM'),
                'product': j['product'] or mate.get('product') or 'NDF',
                'jpm_cpty': j['cpty'], 'client': mate['client'], 'pay_receive': j['pay_receive'],
                'jpm_value': j['value'], 'client_value': mate['value'],
                'sistema': mate['sistema'], 'snumconta': mate['snumconta'],
                'status': status, 'difference': diff})
        else:
            details.append({
                'le': j.get('le', 'JPM'),
                'product': j['product'], 'jpm_cpty': j['cpty'], 'client': '',
                'pay_receive': j['pay_receive'], 'jpm_value': j['value'], 'client_value': '',
                'sistema': '', 'snumconta': '', 'status': 'Pending', 'difference': -j['value']})
    for c in client:
        if id(c) in matched:
            continue
        # MGT receipts have no reliable text filter, so an unmatched one is just
        # SPB noise → drop it instead of listing it as a pending receivement.
        if c.get('drop_if_unmatched'):
            continue
        details.append({
            # No JPM side to match → fall back to the client record's own LE
            # (MGT only for the HistoricoMensagensMGT actuals).
            'le': c.get('le', 'JPM'),
            'product': c.get('product') or 'NDF', 'jpm_cpty': '', 'client': c['client'],
            'pay_receive': c['pay_receive'], 'jpm_value': '', 'client_value': c['value'],
            'sistema': c['sistema'], 'snumconta': c['snumconta'],
            'status': 'Pending', 'difference': c['value']})
    # Atacama is always shown as EQUITIES — enforce on the displayed product for
    # any row facing Atacama (covers unmatched client rows that never pass through
    # _emit_records).
    for d in details:
        if _is_atacama(d.get('jpm_cpty')) or _is_atacama(d.get('client')):
            d['product'] = 'EQUITIES'
    # Unmatched MGT receipts (drop_if_unmatched) are SPB noise → exclude them
    # from the summary too, so the counts stay consistent with the tables.
    client_kept = [c for c in client if id(c) in matched or not c.get('drop_if_unmatched')]
    return details, _summary(jpm, client_kept)


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
def _persist_uploads(files):
    """Save the dropzone uploads into the same folder the 'import from folder'
    button reads from (_INPUT_BASE), so a manual run leaves the input folder in
    the same state as a folder run. Returns [(name, path-or-FileStorage)]: the
    saved on-disk path when the write succeeds, else the in-memory FileStorage so
    the reconciliation still runs even when the folder is unreachable/read-only."""
    items = []
    can_save = False
    try:
        os.makedirs(_INPUT_BASE, exist_ok=True)
        can_save = os.path.isdir(_INPUT_BASE)
    except Exception as e:
        _LOG.warning('[payrec] could not access input folder %s: %s', _INPUT_BASE, e)
    for f in files:
        name = getattr(f, 'filename', '')
        if not name:
            continue
        if can_save:
            try:
                dest = os.path.join(_INPUT_BASE, os.path.basename(name))
                try:
                    f.stream.seek(0)
                except Exception:
                    pass
                with open(dest, 'wb') as out:
                    out.write(f.stream.read())
                items.append((name, dest))          # read back from the saved copy
                continue
            except Exception as e:
                _LOG.warning('[payrec] could not save upload %s: %s', name, e)
                try:
                    f.stream.seek(0)
                except Exception:
                    pass
        items.append((name, f))                     # fall back to the in-memory upload
    return items


def _gather_sources(files, mode):
    srcs = []
    if mode == 'manual' and files:
        items = _persist_uploads(files)
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


def _prev_finalized(recon_date):
    """Most recent finalized-day history strictly BEFORE recon_date.
    Returns (data, 'YYYY-MM-DD') or None."""
    try:
        cur = datetime.strptime((recon_date or '')[:10], '%Y-%m-%d')
    except Exception:
        return None
    best, best_dt = None, None
    pattern = os.path.join(_HISTORY_BASE, '*', '*', '*', 'payrec_status_*.json')
    for p in glob.glob(pattern):
        m = re.search(r'payrec_status_(\d{8})\.json$', os.path.basename(p))
        if not m:
            continue
        try:
            dt = datetime.strptime(m.group(1), '%Y%m%d')
        except Exception:
            continue
        if dt < cur and (best_dt is None or dt > best_dt):
            best_dt, best = dt, p
    if not best:
        return None
    try:
        with open(best, encoding='utf-8') as fh:
            return json.load(fh), best_dt.strftime('%Y-%m-%d')
    except Exception:
        return None


def _apply_carry_forward(recon_date, pend_pay, pend_rec, settled):
    """Bring forward the previous finalized day's items that the operator marked
    as 'Pending Payment' / 'Pending Receivement' (and were NOT justified), so they
    keep showing up until they settle (matched → in today's Settled) or are
    justified. Matching to today's Settled is value-based (same rule as the
    engine's own join), so a carried item that settled today is dropped instead of
    being listed again."""
    prev = _prev_finalized(recon_date)
    if not prev:
        return pend_pay, pend_rec
    data, prev_date = prev
    carried = (data.get('pending_payment') or []) + (data.get('pending_receivement') or [])
    if not carried:
        return pend_pay, pend_rec
    # Value keys already settled today (le + whole-unit value on either side).
    settled_keys = set()
    for s in settled:
        for k in ('jpm_value', 'client_value'):
            v = s.get(k, '')
            if v not in ('', None):
                settled_keys.add((s.get('le', 'JPM'), _int_key(v)))
    for r in carried:
        st = str(r.get('status', '')).strip().lower()
        if st == 'pending payment':
            target, label = pend_pay, 'Pagamento pendente'
        elif st == 'pending receivement':
            target, label = pend_rec, 'Recebimento pendente'
        else:
            continue                                  # plain Pending / Justified / Settled → don't carry
        v = r.get('jpm_value', '')
        if v in ('', None):
            v = r.get('client_value', '')
        key = (r.get('le', 'JPM'), _int_key(v)) if v not in ('', None) else None
        if key and key in settled_keys:
            continue                                  # settled today → represented in Settled
        row = dict(r)
        # Original date = the day it first became a carry-forward pending item;
        # preserved across subsequent carries, falling back on the first carry to
        # the finalized day it came from (the day it was marked).
        origin = row.get('carry_origin') or prev_date
        row['carry_origin'] = origin
        row['carried_from'] = prev_date
        # Auto comment on the following days, e.g. "Recebimento pendente de 10/07/2026".
        row['comment'] = '{} de {}'.format(label, _fmt_date(origin))
        target.append(row)
    return pend_pay, pend_rec


def _net_atacama_client(client):
    """Atacama is Total Net on BOTH sides. The JPM side already emits a single
    netted Atacama value; collapse the client-side Atacama legs into one netted
    record per LE too, so they reconcile against it (e.g. the client legs
    -289,184.94 + 1,520,481.86 net to 1,231,296.92, matching the JPM value)."""
    atk = [c for c in client if _is_atacama(c.get('client'))]
    if not atk:
        return client
    out = [c for c in client if not _is_atacama(c.get('client'))]
    by_le = {}
    for c in atk:
        by_le.setdefault(c.get('le', 'JPM'), []).append(c)
    for le, recs in by_le.items():
        tot = sum(_num(c.get('value', 0)) for c in recs)
        if abs(tot) < 1e-9:
            continue
        rep = recs[0]
        out.append({
            'value': tot, 'client': rep.get('client', ''),
            'sistema': rep.get('sistema', ''), 'snumconta': rep.get('snumconta', ''),
            'product': 'EQUITIES', 'le': le,
            'pay_receive': 'Receive' if tot > 0 else 'Pay',
        })
    return out


def _net_client(client, net_map):
    """Apply each counterparty's settlement net type to its CLIENT-side legs so the
    client side reduces EXACTLY like the JPM side (_emit_records) — the net type is
    honoured for both payments and receipts, on both ends:
      Total Net → one netted record per (counterparty, LE, product)  [Pay netted
                  against Receive]. Makes e.g. Marfrig's two SWAP client legs
                  (107,493,036.20 + 78,616,850.61) net into the single value that
                  reconciles against the JPM SWAP total (subsumes the old Lawton
                  rule: Lawton is Total Net → its SWAP legs still sum to -946,428.52).
      Pay/Rec   → up to two records per group: Σ receives (>0) and Σ pays (<0), kept
                  separate (never netted against each other) — mirroring the JPM
                  Pay/Rec legs so each side settles Pay↔Pay and Receive↔Receive.
      No Net    → every individual leg kept as-is.
    Counterparty-name desk variants are canonicalised (via _norm_cpty) so they group
    together. Atacama is already collapsed to a single EQUITIES record per LE by
    _net_atacama_client (Total Net), so it passes through this grouping unchanged.
    Drop-if-unmatched (SPB noise) legs are left untouched so they can still be
    dropped downstream."""
    passthrough, groups, order = [], {}, []
    for c in client:
        canon = _norm_cpty(c.get('client', ''))
        # No Net (and any leftover drop-if-unmatched noise) keeps its individual
        # legs; Total Net / Pay/Rec are grouped and reduced below.
        if c.get('drop_if_unmatched') or _net_type_for(net_map, canon) == 'No Net':
            passthrough.append(c)
            continue
        key = (_norm(canon), c.get('le', 'JPM'), c.get('product', 'NDF'))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(c)
    out = list(passthrough)
    for key in order:
        recs = groups[key]
        rep = recs[0]
        net_type = _net_type_for(net_map, _norm_cpty(rep.get('client', '')))
        values = [_num(c.get('value', 0)) for c in recs]

        def _mk(v):
            return {'value': v, 'client': rep.get('client', ''),
                    'sistema': rep.get('sistema', ''), 'snumconta': rep.get('snumconta', ''),
                    'product': rep.get('product', 'NDF'), 'le': rep.get('le', 'JPM'),
                    'pay_receive': 'Receive' if v > 0 else 'Pay'}

        if net_type == 'Pay/Rec':
            recv = sum(v for v in values if v > 0)
            pay = sum(v for v in values if v < 0)
            if abs(recv) >= 1e-9:
                out.append(_mk(recv))
            if abs(pay) >= 1e-9:
                out.append(_mk(pay))
        else:  # Total Net (default)
            tot = sum(values)
            if abs(tot) >= 1e-9:
                out.append(_mk(tot))
    return out


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
        elif bucket == 'sdconta_rec':
            client += _cli_rec(rows, cols)        # RLDOCREC — received TEDs (JPM + MGT)
        elif bucket == 'spb':
            client += _cli_spb(rows, cols)
        elif bucket == 'spb_mgt':
            client += _cli_spb(rows, cols, mgt=True)

    client = _net_atacama_client(client)      # Atacama client legs are Total Net too
    client = _net_client(client, net_map)     # apply each cpty's net type to client legs (Pay/Rec split, Total Net collapse)
    details, summary = _reconcile(jpm, client)
    pend_pay, pend_rec, settled = _split_tables(details)
    # Carry forward the previous day's unresolved Pending Payment/Receivement rows
    # (dropping any that settled today) so they persist until settled or justified.
    pend_pay, pend_rec = _apply_carry_forward(recon_date, pend_pay, pend_rec, settled)
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


_CARRY_STATUSES = ('pending payment', 'pending receivement')


def justify_row(recon_date, table, index, comment, status=None):
    """Resolve one pending row from the Edit dialog, then re-persist the working
    cache so End process (and the e-mailed situation) reflect it. `table` is
    'pay' or 'rec'. Status logic:
      • status 'Pending' (or empty) → the row is Justified (comment kept).
      • status 'Pending Payment' / 'Pending Receivement' → the status is kept as
        chosen, so the value carries forward to the next days' reconciliations
        until it settles (OK) or is justified.
    Returns the updated payload, or None when the date/row can't be resolved."""
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
    new_status = (status or '').strip()
    if new_status.lower() in _CARRY_STATUSES:
        rows[index]['status'] = new_status          # keep it as a carry-forward item
    else:
        rows[index]['status'] = 'Justified'         # comment-only on a Pending row
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
