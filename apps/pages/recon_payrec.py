"""
Pay/Rec Reconciliation engine.

Ports the Alteryx "PayRec" workflow: matches JPM's internal ledger (Cockpit —
cashflows + FXO) against the client bank-statement ledger (SDConta + SPB) and
produces the Summary / Pending Payment / Pending Receivement / Settled views.

Input files (dropped in the page or read from the network Pay_Rec folder, matched
by prefix/glob — names carry timestamps):
  JPM (Cockpit):  cashflows_*.xlsx (sheet 'data'),  FXO Detail*.xlsx (sheet 'FXO Detail')
  Client SPB:     HistoricoMensagensJPM_*.csv        → 'SPB - conta externa'
  Client SDConta: rlctahis*.csv (interna), rlDocTed01*.csv (externa TED), settlement*.csv
  Client MGT:     Pagamentos MGT*.xlsx               → 'MGT - conta externa'

Business rules (from the Alteryx spec):
  - JPM Value: PAY → negative, else positive (from Direction/ATH SET AMT, or sign of Amount).
  - Client Value: 'DEBITO' → Receive; Pay → negative sign.
  - Match key: value rounded to whole currency units (ToString(v, 0dp)).
  - Difference = Client - JPM;  Status = Pending if Difference != 0 else Settled.
  - SPB settled tolerance: Difference > -0.50 → Settled.
  - Summary per-row Check Value tolerance: |JPM sum - Client sum| < 1.00 → OK.
  - Exclude JPM-internal counterparties ("Bco J.P.") and Cashflow Event == DELETE.
"""

import os
import re
import json
import glob
import unicodedata
from datetime import datetime

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE_DIR = os.path.normpath(os.path.join(
    _MODULE_DIR, '..', 'static', 'data', 'cache', 'reconciliation', 'payrec'))

# Network folder holding the input files (second image in the request).
_INPUT_BASE = r"I:\Confirmation\Derivativos\OTC Tracker\Reconciliations\Pay_Rec"

# ── E-mail recipients ─────────────────────────────────────────────────────────
_MAILBOX = 'brazil.otc.ops@jpmorgan.com'
# Renato + Danilo in copy — same cc as the Settlement Forecast / MTM Swap /
# Accrual Swap end-process e-mails (routes._ACC_ENDPROC_CC).
_CC = ['renato.montoza@jpmorgan.com', 'danilo.camposfonseca@jpmchase.com']
_SHARED_MAILBOX = 'otc.tracker@jpmorgan.com'
_SMTP_HOST = 'mailhost.jpmchase.net'
_SMTP_PORT = 25

# ── Tolerances / constants ────────────────────────────────────────────────────
_TOL_CHECK_VALUE = 1.0      # Summary per-row |diff| < 1 → OK
_TOL_SPB_SETTLED = -0.50    # SPB: diff > -0.50 → Settled

_JPM_EXCLUDE = ('bco j.p.', 'banco j.p. morgan', 'jpmorgan chase bank, n.a. - sao paulo')


# ── Small helpers ─────────────────────────────────────────────────────────────
def _norm(s):
    """Accent/case-insensitive, non-alphanumeric-stripped key for column matching."""
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]', '', s.lower())


def _to_num(v):
    """Parse a BR/US number string to float. Handles '1.234,56', '1234.56',
    '(123)'/'123-' negatives. Returns 0.0 on failure."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        try:
            return float(v)
        except Exception:
            return 0.0
    s = str(v).strip()
    if not s or s in ('-', '.', ','):
        return 0.0
    neg = False
    if s.startswith('(') and s.endswith(')'):
        neg = True
        s = s[1:-1]
    if s.endswith('-'):
        neg = True
        s = s[:-1]
    s = s.replace('R$', '').replace(' ', '').strip()
    # Decide decimal separator: if both present, the LAST one is the decimal.
    if ',' in s and '.' in s:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        f = float(s)
    except ValueError:
        return 0.0
    return -f if neg else f


def _fmt_num(v):
    """US thousands, 2 dp — '-1,139,646.53'."""
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
    """Return the actual column whose normalized form matches (exact, then substring)."""
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


# ── File reading (uploaded FileStorage or path) ───────────────────────────────
def _read_table(src, sheet_hint=None):
    """Read a CSV/XLSX (path or werkzeug FileStorage) into a list-of-dicts.
    sheet_hint: substring of the desired Excel sheet name."""
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
            handle = src if isinstance(src, str) else src.stream
            # Sniff delimiter; BR exports are frequently ';'.
            df = pd.read_csv(handle, dtype=str, sep=None, engine='python',
                             encoding='latin-1', on_bad_lines='skip')
        df = df.fillna('')
        return df.to_dict('records'), list(df.columns)
    except Exception:
        return [], []


def _classify_source(name):
    """Map a filename to its source bucket."""
    n = _norm(name)
    if n.startswith('cashflows'):
        return 'jpm_cash'
    if 'fxodetail' in n or n.startswith('fxo'):
        return 'jpm_fxo'
    if 'historicomensagens' in n:
        return 'spb'
    if 'rldocted' in n:
        return 'sdconta_ted'
    if 'rlctahis' in n:
        return 'sdconta_int'
    if n.startswith('settlement'):
        return 'settlement'
    if 'pagamentosmgt' in n:
        return 'mgt'
    if 'pagamentosseparados' in n:
        return 'sep'
    return 'unknown'


# ── Normalisation into JPM / client record lists ──────────────────────────────
def _norm_jpm(rows, cols, is_fxo):
    """→ list of {value, cpty, product, pay_receive}."""
    out = []
    c_amount = _resolve(cols, 'ATH SET AMT', 'Amount')
    c_dir = _resolve(cols, 'Direction')
    c_cpty = _resolve(cols, 'Counterparty', 'Cpty Name')
    c_prod = _resolve(cols, 'POG', 'Product', 'Asset Class')
    c_event = _resolve(cols, 'Cashflow Event')
    c_asset = _resolve(cols, 'Asset Class')
    for r in rows:
        cpty = str(r.get(c_cpty, '') if c_cpty else '').strip()
        if any(x in cpty.lower() for x in _JPM_EXCLUDE):
            continue
        if c_event and str(r.get(c_event, '')).strip().upper() == 'DELETE':
            continue
        amt = _to_num(r.get(c_amount, '') if c_amount else 0)
        direction = str(r.get(c_dir, '') if c_dir else '').strip().upper()
        if direction == 'PAY':
            value = -abs(amt)
        elif direction in ('RECEIVE', 'REC'):
            value = abs(amt)
        else:
            value = amt  # sign of Amount already carries direction
        pay_receive = 'Pay' if value < 0 else 'Receive'
        product = str(r.get(c_prod, '') if c_prod else '').strip()
        asset = str(r.get(c_asset, '') if c_asset else '').strip().upper()
        if not product:
            product = {'INTEREST_RATE': 'SWAP', 'EQUITIES': 'EQUITIES'}.get(asset, 'FXO' if is_fxo else 'NDF')
        if value == 0:
            continue
        out.append({'value': value, 'cpty': cpty.upper(), 'product': product or 'NDF',
                    'pay_receive': pay_receive})
    return out


def _norm_client(rows, cols, source):
    """→ list of {value, client, sistema, snumconta, product, pay_receive, status_hint}."""
    out = []
    c_val = _resolve(cols, 'Valor (R$)', 'nVlrLanc', 'Valor', 'Amount', 'Value')
    c_desc = _resolve(cols, 'sDescricao', 'Descricao', 'Descrição')
    c_evt = _resolve(cols, 'Descrição Evento', 'Descricao Evento')
    c_tit = _resolve(cols, 'sNomeTitular', 'Titular', 'Client')
    c_conta = _resolve(cols, 'sNumConta')
    c_banco = _resolve(cols, 'nBancoEmissor')
    c_ag = _resolve(cols, 'nAgDebitada')
    c_cc = _resolve(cols, 'nCcDebitada')

    sistema = {'spb': 'SPB - conta externa', 'sdconta_ted': 'SDConta - conta externa',
               'sdconta_int': 'SDConta - conta interna', 'mgt': 'MGT - conta externa',
               'settlement': 'SDConta - conta externa', 'sep': 'MGT - conta externa'}.get(source, '')

    for r in rows:
        # SPB filter: only derivatives / LMA-COMM-BR events.
        if source == 'spb' and c_evt:
            ev = str(r.get(c_evt, '')).lower()
            if 'derivativos' not in ev and 'lma-comm-br' not in ev:
                continue
        raw = _to_num(r.get(c_val, '') if c_val else 0)
        desc = str(r.get(c_desc, '') if c_desc else '')
        # sDescricao → Pay/Receive
        if 'debito' in _norm(desc):
            pay_receive = 'Receive'
        else:
            pay_receive = 'Pay'
        if source in ('sdconta_int',):
            value = abs(raw)
            pay_receive = 'Receive' if value >= 0 else 'Pay'
        else:
            value = -abs(raw) if pay_receive == 'Pay' else abs(raw)
        titular = str(r.get(c_tit, '') if c_tit else '').strip()
        titular = titular.replace('LMA-COMM-BR ', '').strip()
        conta = str(r.get(c_conta, '') if c_conta else '').strip()
        if source == 'sdconta_ted' and c_banco and c_ag and c_cc:
            conta = '-'.join([str(r.get(c_banco, '')).strip(), str(r.get(c_ag, '')).strip(),
                              str(r.get(c_cc, '')).strip()]).strip('-')
        tl = titular.lower()
        if any(x in tl for x in _JPM_EXCLUDE):
            continue
        if abs(value) < 1:
            continue
        s = sistema
        if source == 'sdconta_int' and 'liqs financeiras' in tl and 'operacoes cambio' in tl:
            s = 'SDConta - conta externa FX'
        out.append({'value': value, 'client': titular, 'sistema': s, 'snumconta': conta,
                    'product': '', 'pay_receive': pay_receive})
    return out


# ── Core reconciliation ───────────────────────────────────────────────────────
def _reconcile(jpm, client):
    """Match JPM ↔ client on integer value key (greedy one-to-one). Returns
    (detail_rows, summary_rows)."""
    # Index client records by whole-unit key for matching.
    buckets = {}
    for c in client:
        buckets.setdefault(_int_key(c['value']), []).append(c)

    details = []
    matched_client = set()
    for j in jpm:
        key = _int_key(j['value'])
        pool = buckets.get(key, [])
        mate = None
        for c in pool:
            if id(c) not in matched_client:
                mate = c
                matched_client.add(id(c))
                break
        if mate:
            diff = mate['value'] - j['value']
            status = 'Settled' if abs(diff) < 1e-9 else 'Pending'
            if mate['sistema'] == 'SPB - conta externa' and diff > _TOL_SPB_SETTLED:
                status = 'Settled'
            details.append({
                'product': j['product'] or mate.get('product') or 'NDF',
                'jpm_cpty': j['cpty'], 'client': mate['client'],
                'pay_receive': j['pay_receive'],
                'jpm_value': j['value'], 'client_value': mate['value'],
                'sistema': mate['sistema'], 'snumconta': mate['snumconta'],
                'status': status, 'difference': diff})
        else:
            details.append({
                'product': j['product'], 'jpm_cpty': j['cpty'], 'client': '',
                'pay_receive': j['pay_receive'], 'jpm_value': j['value'], 'client_value': '',
                'sistema': '', 'snumconta': '', 'status': 'Pending', 'difference': -j['value']})
    # Unmatched client records → pending on the client side.
    for c in client:
        if id(c) in matched_client:
            continue
        details.append({
            'product': c.get('product') or 'NDF', 'jpm_cpty': '', 'client': c['client'],
            'pay_receive': c['pay_receive'], 'jpm_value': '', 'client_value': c['value'],
            'sistema': c['sistema'], 'snumconta': c['snumconta'],
            'status': 'Pending', 'difference': c['value']})

    summary = _summary(jpm, client)
    return details, summary


def _summary(jpm, client):
    """Aggregate by Pay/Receive with Check Qty / Check Value flags + TOTAL."""
    def agg(recs, label):
        return {'qty': sum(1 for r in recs if r['pay_receive'] == label),
                'sum': sum(r['value'] for r in recs if r['pay_receive'] == label)}

    rows = []
    tot = {'jq': 0, 'cq': 0, 'jv': 0.0, 'cv': 0.0}
    for label in ('Pay', 'Receive'):
        j = agg(jpm, label)
        c = agg(client, label)
        diff = abs(j['sum'] - c['sum'])
        rows.append({
            'pay_receive': label, 'jpm_qty': j['qty'], 'client_qty': c['qty'],
            'check_qty': 'OK' if j['qty'] == c['qty'] else 'Not OK',
            'jpm_value': j['sum'], 'client_value': c['sum'],
            'difference': j['sum'] - c['sum'],
            'check_value': 'OK' if diff < _TOL_CHECK_VALUE else 'Not OK'})
        tot['jq'] += j['qty']; tot['cq'] += c['qty']; tot['jv'] += j['sum']; tot['cv'] += c['sum']
    rows.append({
        'pay_receive': 'TOTAL', 'jpm_qty': tot['jq'], 'client_qty': tot['cq'],
        'check_qty': 'OK' if tot['jq'] == tot['cq'] else 'Not OK',
        'jpm_value': tot['jv'], 'client_value': tot['cv'],
        'difference': tot['jv'] - tot['cv'],
        'check_value': 'OK' if abs(tot['jv'] - tot['cv']) < 1e-9 else 'Not OK'})
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
    """Yield (source_bucket, rows, cols) from uploaded files or the network folder."""
    srcs = []
    if mode == 'manual' and files:
        for f in files:
            if not getattr(f, 'filename', ''):
                continue
            bucket = _classify_source(f.filename)
            sheet = 'data' if bucket == 'jpm_cash' else ('FXO Detail' if bucket == 'jpm_fxo' else None)
            rows, cols = _read_table(f, sheet)
            srcs.append((bucket, rows, cols))
    else:
        if not os.path.isdir(_INPUT_BASE):
            err = FileNotFoundError('Pay/Rec input folder not found: %s' % _INPUT_BASE)
            raise err
        for path in sorted(glob.glob(os.path.join(_INPUT_BASE, '*.*'))):
            bucket = _classify_source(os.path.basename(path))
            sheet = 'data' if bucket == 'jpm_cash' else ('FXO Detail' if bucket == 'jpm_fxo' else None)
            rows, cols = _read_table(path, sheet)
            srcs.append((bucket, rows, cols))
    return srcs


def run_payrec(recon_date, files=None, mode='auto'):
    """Process the Pay/Rec inputs and return the response payload (also persisted)."""
    srcs = _gather_sources(files, mode)
    if not srcs:
        raise FileNotFoundError('No Pay/Rec input files provided or found for this date.')

    jpm, client = [], []
    used = 0
    for bucket, rows, cols in srcs:
        if not rows:
            continue
        if bucket in ('jpm_cash', 'jpm_fxo'):
            jpm += _norm_jpm(rows, cols, is_fxo=(bucket == 'jpm_fxo')); used += 1
        elif bucket in ('spb', 'sdconta_ted', 'sdconta_int', 'settlement', 'mgt', 'sep'):
            client += _norm_client(rows, cols, bucket); used += 1

    details, summary = _reconcile(jpm, client)
    pend_pay, pend_rec, settled = _split_tables(details)

    payload = {
        'success': True,
        'recon_date': recon_date,
        'recon_date_fmt': _fmt_date(recon_date),
        'summary': summary,
        'pending_payment': pend_pay,
        'pending_receivement': pend_rec,
        'settled': settled,
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
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        key = (recon_date or 'last').replace('/', '-')
        with open(os.path.join(_CACHE_DIR, key + '.json'), 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False)
        with open(os.path.join(_CACHE_DIR, '_last.json'), 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False)
    except Exception:
        pass


def load_last(recon_date=''):
    """Return the persisted result for a date (or the most recent), else empty."""
    try:
        key = (recon_date or '').replace('/', '-')
        cand = os.path.join(_CACHE_DIR, (key + '.json') if key else '_last.json')
        if not os.path.exists(cand):
            cand = os.path.join(_CACHE_DIR, '_last.json')
        if os.path.exists(cand):
            with open(cand, encoding='utf-8') as fh:
                return json.load(fh)
    except Exception:
        pass
    return {'success': True, 'summary': [], 'pending_payment': [],
            'pending_receivement': [], 'settled': []}


# ── E-mail (final situation of the day) ───────────────────────────────────────
def _decorate_rows(rows, total_labels=()):
    """Add *_fmt / *_neg display fields for the e-mail template."""
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
    """E-mail the persisted end-of-day situation to OTC Ops (Danilo & Renato in cc)."""
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

    html_body = render_template(
        'pages/email-template-recon-payrec.html',
        recon_date_fmt=recon_date_fmt,
        summary=_decorate_rows(data.get('summary', []), total_labels=('TOTAL',)),
        pending_payment=_decorate_rows(data.get('pending_payment', [])),
        pending_receivement=_decorate_rows(data.get('pending_receivement', [])),
        settled=_decorate_rows(data.get('settled', [])),
        current_year=current_year,
    )

    msg = MIMEMultipart('related')
    msg['Subject'] = '[OTC Tracker] Pay/Rec — Status das liquidações de OTC - {}'.format(recon_date_fmt)
    msg['From'] = _SHARED_MAILBOX
    msg['To'] = _MAILBOX
    msg['Cc'] = ', '.join(_CC)

    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText('Pay/Rec end-of-day situation for {}. View in an HTML client.'.format(recon_date_fmt), 'plain'))
    alt.attach(MIMEText(html_body, 'html'))
    msg.attach(alt)

    # Inline logo (best-effort).
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
        recipients = [_MAILBOX] + _CC
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT) as server:
            server.sendmail(_SHARED_MAILBOX, recipients, msg.as_string())
        return True
    except Exception:
        return False
