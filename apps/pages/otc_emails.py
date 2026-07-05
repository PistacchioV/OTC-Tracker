"""
OTC settlement / confirmation e-mail builders for the New Deals pages.

Ports the legacy CommodiXchange `email_Premio` (premium settlement, D0) and
`email_if` (economic affirmation against Financial Institutions) logic into the
web app. Each builder returns a list of draft dicts; `build_drafts_download`
packages them as downloadable .eml files (single) or a .zip (several) with the
`X-Unsent: 1` header, so the file opens as an editable draft in the ACTING
user's own Outlook — the app runs on a shared server, so server-side Outlook
automation would only ever open a draft on the server, never on the user.

Counterparty static data comes from two JSON files under static/data:
  - RefData.json           → B3 ACCOUNT, COUNTERPARTY, TAX ID, SPN by acronym
  - CounterpartyDetails.json → CGD / banking / contacts indexed by SPN

E-mail column sources (New Deals Opt/NDF deal fields):
  - "Contrato"     → Deal               (deal['Deal'])
  - "Moeda/Ativo"  → Underlying Asset (+ Commodities)   (deal['UnderlyingAsset'] / ['Commodities'])

Eligibility:
  - Premium (D0):            B3 ACCOUNT == 73760.10-2, not Lawton, SpotDate == today
  - Economic Affirmation:    TradeDate == today, not Lawton, not Banco JP Morgan,
                             B3 ACCOUNT not in {73760.00-9, 73760.10-2, 00041.00-7}
"""

import os
import io
import json
import zipfile
import unicodedata
from datetime import datetime
from email.header import Header

_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'static', 'data'))

JPM_B3_ACCOUNT   = '73760.00-9'           # JPMorgan's own CETIP account
PREMIUM_CLIENT_B3 = '73760.10-2'          # premium "cliente" bucket — only these get the D0 premium notice
# Economic Affirmation is sent to Financial-Institution counterparties only:
# everyone whose CETIP account is NOT one of these (and that isn't Lawton/JPMorgan).
EXCLUDED_B3_AFFIRMATION = {'73760.00-9', '73760.10-2', '00041.00-7'}
FOOTER_HTML = (
    '<p>Atenciosamente,</p>'
    '<p>Banco J.P. Morgan S.A. | Av. Brigadeiro Faria Lima, 3729 - 15º andar - São Paulo - SP | '
    'T: 55 11 4950 6717 |<br>'
    'brsp_otc_derivatives_ops@jpmorgan.com | jpmorgan.com | Ouvidoria JPMorgan: '
    'Tel.: 0800 – 7700847 / E-mail: ouvidoria.jp.morgan@jpmorgan.com</p>'
)

# ──────────────────────────────────────────────────────────────────────────
# HTML e-mail design (corporate, Emil/Apple) — table-based + inline styles so
# Outlook/Gmail render it reliably. No images: a text wordmark, one Action-Blue
# accent, hairline tables, generous spacing. Shared by the client-facing drafts.
# ──────────────────────────────────────────────────────────────────────────
_E_BLUE  = '#0066cc'
_E_NAVY  = '#243b53'
_E_INK   = '#1d1d1f'
_E_MUTED = '#8a8a8f'
_E_FONT  = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _esc(s):
    s = '' if s is None else str(s)
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _ep(html, muted=False):
    """A body paragraph."""
    color = '#6c6c72' if muted else '#333333'
    return ('<p style="margin:0 0 12px;font-size:14px;line-height:1.62;color:' + color +
            ';font-family:' + _E_FONT + ';">' + html + '</p>')


def _email_data_table(headers, rows):
    """A clean hairline table with a navy header and zebra rows."""
    th = ''.join(
        '<th style="padding:9px 11px;text-align:left;font-size:10.5px;font-weight:600;'
        'text-transform:uppercase;letter-spacing:.04em;color:#ffffff;white-space:nowrap;">' + _esc(h) + '</th>'
        for h in headers)
    body = ''
    for i, r in enumerate(rows):
        bg = '#ffffff' if i % 2 == 0 else '#f6f7f9'
        tds = ''.join(
            '<td style="padding:8px 11px;font-size:12px;color:#1d1d1f;border-top:1px solid #edeef1;'
            'white-space:nowrap;">' + _esc(c) + '</td>' for c in r)
        body += '<tr style="background:' + bg + ';">' + tds + '</tr>'
    return ('<table role="presentation" cellpadding="0" cellspacing="0" width="100%" '
            'style="border-collapse:separate;border-spacing:0;width:100%;border:1px solid #e6e6ea;'
            'border-radius:10px;overflow:hidden;font-family:' + _E_FONT + ';">'
            '<tr style="background:' + _E_NAVY + ';">' + th + '</tr>' + body + '</table>')


def _email_summary(pairs):
    """Highlighted totals panel. pairs: list of (label, value, is_total)."""
    rows = ''
    for i, (label, value, is_total) in enumerate(pairs):
        top = '' if i == 0 else 'border-top:1px solid #dbe6f3;'
        lblc = _E_INK if is_total else '#4a4a4f'
        valc = _E_BLUE if is_total else _E_INK
        wt = '700' if is_total else '600'
        fs = '15px' if is_total else '13px'
        rows += ('<tr><td style="padding:8px 14px;font-size:' + fs + ';font-weight:' + wt +
                 ';color:' + lblc + ';' + top + '">' + _esc(label) + '</td>'
                 '<td align="right" style="padding:8px 14px;font-size:' + fs + ';font-weight:700;color:' +
                 valc + ';white-space:nowrap;' + top + '">' + _esc(value) + '</td></tr>')
    return ('<table role="presentation" cellpadding="0" cellspacing="0" '
            'style="border-collapse:separate;border-spacing:0;background:#f3f6fb;border:1px solid #dbe6f3;'
            'border-radius:10px;overflow:hidden;font-family:' + _E_FONT + ';min-width:280px;">' + rows + '</table>')


def _email_kv(title, pairs):
    """A titled key/value block (e.g. banking details)."""
    head = ('<div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;'
            'color:' + _E_MUTED + ';margin:0 0 8px;font-family:' + _E_FONT + ';">' + _esc(title) + '</div>')
    rows = ''
    for i, (label, value) in enumerate(pairs):
        top = '' if i == 0 else 'border-top:1px solid #ececf0;'
        rows += ('<tr><td style="padding:7px 14px;font-size:12.5px;color:#6c6c72;white-space:nowrap;' + top + '">' +
                 _esc(label) + '</td>'
                 '<td style="padding:7px 14px;font-size:12.5px;font-weight:600;color:#1d1d1f;' + top + '">' +
                 _esc(value) + '</td></tr>')
    return (head + '<table role="presentation" cellpadding="0" cellspacing="0" '
            'style="border-collapse:separate;border-spacing:0;background:#ffffff;border:1px solid #e6e6ea;'
            'border-radius:10px;overflow:hidden;font-family:' + _E_FONT + ';min-width:320px;">' + rows + '</table>')


def _email_shell(title, ref_date, intro_html, body_html):
    """Corporate card: J.P. Morgan wordmark, Action-Blue accent, title, body, footer."""
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        '<body style="margin:0;padding:0;background:#f4f4f6;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background:#f4f4f6;">'
        '<tr><td align="center" style="padding:26px 12px;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" width="640" '
        'style="width:640px;max-width:640px;background:#ffffff;border:1px solid #e6e6ea;border-radius:14px;'
        'font-family:' + _E_FONT + ';">'
        # header
        '<tr><td style="padding:24px 34px 0;">'
        '<table role="presentation" width="100%"><tr>'
        '<td style="font-size:16px;font-weight:700;letter-spacing:.16em;color:#1d1d1f;">J.P.MORGAN</td>'
        '<td align="right" style="font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:' +
        _E_MUTED + ';">' + _esc(ref_date) + '</td>'
        '</tr></table></td></tr>'
        '<tr><td style="padding:14px 34px 0;"><div style="height:3px;width:44px;background:' + _E_BLUE +
        ';border-radius:2px;font-size:0;line-height:0;">&nbsp;</div></td></tr>'
        '<tr><td style="padding:13px 34px 0;"><div style="font-size:20px;font-weight:600;letter-spacing:-.3px;'
        'color:#1d1d1f;line-height:1.25;">' + _esc(title) + '</div></td></tr>'
        # intro + body
        '<tr><td style="padding:16px 34px 2px;">' + intro_html + '</td></tr>'
        '<tr><td style="padding:4px 34px 26px;">' + body_html + '</td></tr>'
        # footer
        '<tr><td style="padding:20px 34px;background:#fafafb;border-top:1px solid #ececf0;font-size:11px;'
        'line-height:1.7;color:' + _E_MUTED + ';">'
        '<div style="font-weight:600;color:#555;margin-bottom:2px;">Atenciosamente,</div>'
        'Banco J.P. Morgan S.A. &nbsp;|&nbsp; Av. Brigadeiro Faria Lima, 3729 – 15º andar – São Paulo – SP<br>'
        'T: 55 11 4950 6717 &nbsp;|&nbsp; brsp_otc_derivatives_ops@jpmorgan.com &nbsp;|&nbsp; jpmorgan.com<br>'
        'Ouvidoria JPMorgan: 0800 – 7700847 &middot; ouvidoria.jp.morgan@jpmorgan.com'
        '</td></tr>'
        '</table></td></tr></table></body></html>')


# ──────────────────────────────────────────────────────────────────────────
# Data loading / lookups
# ──────────────────────────────────────────────────────────────────────────
def _load_json(name):
    try:
        with open(os.path.join(_DATA_DIR, name), encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return []


def _build_refdata_index(key='COMMODITIES ACCRONYM'):
    """acronym → ref record. `key` selects which RefData accronym column to index
    by: 'COMMODITIES ACCRONYM' (commodities) or 'FX CASH ACCRONYM' (FXO)."""
    idx = {}
    for r in _load_json('RefData.json'):
        acc = str(r.get(key, '') or '').strip().upper()
        if acc and acc not in idx:
            idx[acc] = r
    return idx


def _norm_spn(value):
    """SPN match key: drop a trailing '.0' and leading zeros (both sides), matching
    the project-wide convention so a deal SPN like '0135742' resolves to the
    CounterpartyDetails record stored as '135742'."""
    s = str(value or '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    s = s.lstrip('0')
    return s or ('0' if value not in (None, '') else '')


def _build_cpdetails_index():
    """SPN (leading-zeros/'.0' stripped) → counterparty banking/contact record."""
    idx = {}
    for c in _load_json('CounterpartyDetails.json'):
        spn = _norm_spn(c.get('SPN'))
        if spn:
            idx.setdefault(spn, c)
    return idx


# ──────────────────────────────────────────────────────────────────────────
# Formatting helpers
# ──────────────────────────────────────────────────────────────────────────
def _num(val):
    """Parse a display number (US thousands ',' / decimal '.') to float."""
    if val is None:
        return 0.0
    t = str(val).strip().replace('R$', '').replace(' ', '')
    if not t:
        return 0.0
    try:
        return float(t.replace(',', ''))
    except ValueError:
        try:                                    # fallback: BR format
            return float(t.replace('.', '').replace(',', '.'))
        except ValueError:
            return 0.0


def _br(value, dec=2):
    """Format a number in Brazilian notation (1.234,56)."""
    s = ('{:,.' + str(dec) + 'f}').format(value)
    return s.replace(',', ' ').replace('.', ',').replace(' ', '.')


def _br_currency(value, dec=2):
    """BR number, negatives in parentheses: (1.234,56)."""
    if value < 0:
        return '(' + _br(abs(value), dec) + ')'
    return _br(value, dec)


def _date_br(s):
    """Normalise a date string to dd/mm/yyyy (accepts dd/mm/yyyy, yyyy-mm-dd, dd-Mon-yyyy)."""
    if not s:
        return ''
    s = str(s).strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%b-%Y', '%d/%m/%y'):
        try:
            return datetime.strptime(s, fmt).strftime('%d/%m/%Y')
        except ValueError:
            continue
    return s


def _fmt_cnpj(raw):
    digits = ''.join(ch for ch in str(raw or '') if ch.isdigit())
    if len(digits) != 14:
        return str(raw or '')
    return '{}.{}.{}/{}-{}'.format(digits[:2], digits[2:5], digits[5:8], digits[8:12], digits[12:])


def _today_br():
    return datetime.today().strftime('%d/%m/%Y')


def _is_sell(direction):
    return 'SELL' in str(direction or '').upper()


def _is_put(instrument):
    return 'PUT' in str(instrument or '').upper()


def _is_lawton(name, acronym=''):
    return 'LAWTON' in str(name or '').upper() or 'LAWTON' in str(acronym or '').upper()


def _is_jpmorgan(name):
    n = str(name or '').upper()
    return 'JPMORGAN' in n or 'JP MORGAN' in n or 'J.P. MORGAN' in n


def _first_bank(cp, prefer='PAY'):
    """Return (bank, agency, account) from a CounterpartyDetails record.

    Uses the ACCOUNTS model: the account flagged as the approved default for the
    `prefer` side (DEFAULT_PAY/RECEIVE.current). Falls back to the other side's
    default, then the first active (else any) account, then the legacy
    PAY/RECEIVE lists, then the flat BANK/AGENCY/ACCOUNT fields.
    """
    def _tuple(a):
        return a.get('bank', ''), a.get('agency', ''), a.get('account', '')

    bk = cp.get('BANKING') or {}
    accounts = bk.get('ACCOUNTS')
    if isinstance(accounts, list) and accounts:
        by_id = {a.get('id'): a for a in accounts if isinstance(a, dict)}
        for kind in (prefer, 'RECEIVE' if prefer == 'PAY' else 'PAY'):
            slot = bk.get('DEFAULT_' + kind) or {}
            acc = by_id.get(slot.get('current'))
            if acc:
                return _tuple(acc)
        active = [a for a in accounts if str(a.get('status', '')).lower() == 'active']
        return _tuple((active or accounts)[0])

    # legacy shapes
    for key in (prefer, 'RECEIVE' if prefer == 'PAY' else 'PAY'):
        lst = bk.get(key) or []
        if lst:
            b = lst[0] or {}
            return b.get('bank', ''), b.get('agency', ''), b.get('account', '')
    return cp.get('BANK', ''), cp.get('AGENCY', ''), cp.get('ACCOUNT', '')


def _contacts_emails(cp, keywords):
    """E-mails of a counterparty's contacts whose rules match any keyword
    (substring, case-insensitive), de-duplicated, in order."""
    out, seen = [], set()
    for c in (cp.get('CONTACTS') or []):
        rules = c.get('rules') or c.get('RULES') or []
        rl = ' '.join(str(r).lower() for r in rules)
        if any(k in rl for k in keywords):
            em = str(c.get('email') or c.get('EMAIL') or '').strip()
            if em and em.lower() not in seen:
                seen.add(em.lower())
                out.append(em)
    return out


# Settlement contacts: rules containing Settlement / Settlement Advice / Repurchase
_SETTLEMENT_KEYWORDS = ('settlement', 'repurchase')


def _asset_label(deal):
    """Moeda/Ativo column = Underlying Asset (+ Commodities) from the New Deals page."""
    ua  = str(deal.get('UnderlyingAsset', '') or '').strip()
    com = str(deal.get('Commodities', '') or '').strip()
    if ua and com:
        return '{}({})'.format(ua, com)
    return ua or com


# ──────────────────────────────────────────────────────────────────────────
# Grouping
# ──────────────────────────────────────────────────────────────────────────
def _group_by_acronym_commodity(deals):
    groups = {}
    for d in deals:
        key = (str(d.get('Acronym', '') or '').strip().upper(),
               str(d.get('Commodities', '') or '').strip().upper())
        groups.setdefault(key, []).append(d)
    return groups


# ──────────────────────────────────────────────────────────────────────────
# PREMIUM (D0) — SpotDate == today
# ──────────────────────────────────────────────────────────────────────────
def build_premium_emails(deals, asset_label='Commodities', ref_key='COMMODITIES ACCRONYM'):
    """D0 premium settlement notice.

    Eligible counterparties: CETIP account (RefData) == 73760.10-2 AND not Lawton,
    restricted to deals whose SpotDate (premium payment date) is today.

    `asset_label` is the asset-class token shown in the subject line
    (e.g. 'Commodities' for opt-commodities, 'Taxas de Câmbio' for opt-fxo).
    `ref_key` selects the RefData accronym column used to resolve each deal's
    Acronym → ref record: 'COMMODITIES ACCRONYM' (default) or 'FX CASH ACCRONYM'
    (FXO deals carry the FX cash accronym, not the commodities one).
    """
    ref = _build_refdata_index(ref_key)
    cpd = _build_cpdetails_index()
    today = _today_br()

    todays = [d for d in deals if _date_br(d.get('SpotDate')) == today]
    drafts = []

    for (acronym, _commodity), items in _group_by_acronym_commodity(todays).items():
        rec   = ref.get(acronym, {})
        b3    = str(rec.get('B3 ACCOUNT', '') or '').strip()
        name  = rec.get('COUNTERPARTY', '') or acronym
        spn   = str(items[0].get('SPN', '') or rec.get('SPN', '') or '').strip().upper()
        taxid = rec.get('TAX ID', '')

        if b3 != PREMIUM_CLIENT_B3:          # only the 73760.10-2 bucket
            continue
        if _is_lawton(name, acronym):        # never Lawton
            continue

        drafts.append(_premium_cliente_email(items, name, spn, taxid, cpd, asset_label))

    return drafts


def _premium_apurado(items):
    apurado = sum(_num(d.get('Premium')) * (1 if _is_sell(d.get('Direction')) else -1) for d in items)
    ir = 0.0 if apurado >= 0 else apurado * 0.00005 * -1
    final = apurado + ir if apurado < 0 else apurado
    return apurado, ir, final


def _premium_cliente_email(items, contraparte, spn, taxid, cpd, asset_label='Commodities'):
    apurado, ir, final = _premium_apurado(items)
    cp = cpd.get(_norm_spn(spn), {})
    to_emails = '; '.join(_contacts_emails(cp, _SETTLEMENT_KEYWORDS))

    data_rows = []
    for d in items:
        resultado = _num(d.get('Premium')) * (1 if _is_sell(d.get('Direction')) else -1)
        data_rows.append([
            d.get('Deal', ''),
            _date_br(d.get('TradeDate')),
            _date_br(d.get('SettlementDate')),
            _asset_label(d),
            _br(abs(_num(d.get('TotalNotional')))),
            _br_currency(resultado),
        ])

    table = _email_data_table(
        ['Contrato', 'Data Operação', 'Data Vencimento', 'Moeda/Ativo', 'Valor Base/Quantidade', 'Resultado Final'],
        data_rows)

    summary = _email_summary([
        ('Resultado Apurado', 'R$ ' + _br_currency(apurado), False),
        ('IR (0,005%)',       'R$ ' + _br(ir),               False),
        ('Resultado Final',   'R$ ' + _br_currency(final),   True),
    ])

    # Settlement instruction + banking block depend on the sign of the result.
    if final < 0:
        instr = _ep('Conforme entendimentos mantidos, informamos que providenciaremos nesta data a '
                    'transferência financeira do montante correspondente ao Resultado Final Apurado em vosso favor, '
                    'conforme os dados a seguir, transmitidos por meio da Autorização Permanente para Liquidação '
                    'Financeira e/ou confirmados por ligação telefônica:')
        bank_name, agency, account = _first_bank(cp, 'PAY')   # JPM pays → PAY details
        bank = _email_kv('Dados para pagamento', [
            ('Nome e nº do banco', bank_name or '—'),
            ('Nº e nome da agência', agency or '—'),
            ('Conta-corrente nº', account or '—'),
            ('CNPJ/MF nº', _fmt_cnpj(taxid)),
        ])
    else:
        instr = _ep('Sendo assim, informamos que debitaremos os valores descritos acima da conta corrente do '
                    'Cliente junto ao Banco J.P.Morgan S.A., mediante confirmação de saldo e nos moldes da '
                    'autorização de débito encaminhada pelos Srs. Caso não tenham encaminhado autorização de débito, '
                    'solicitamos que o montante correspondente ao Resultado Final Apurado acima seja transferido em '
                    'favor do Banco J.P Morgan S.A. nesta data, conforme os dados a seguir:') if final > 0 else ''
        bank = _email_kv('Dados bancários', [
            ('Nome e nº do banco', 'BANCO JP MORGAN S/A - 376'),
            ('Nº e nome da agência', '0011'),
            ('Conta-corrente nº', '5116003'),
            ('CNPJ/MF nº', '33.172.537/0001-98'),
        ])

    def _gap(h):
        return '<div style="height:' + str(h) + 'px;line-height:' + str(h) + 'px;font-size:0;">&nbsp;</div>'

    body_html = (
        table + _gap(18) + summary +
        ((_gap(16) + instr) if instr else '') + _gap(6) + bank + _gap(16) +
        _ep('A presente Ficha de Liquidação é parte integrante e inseparável do Contrato e/ou da '
            'Confirmação de Operação de Derivativo em referência.', muted=True))

    intro = (_ep('Prezados Senhores,') +
             _ep('Vimos confirmar a(s) liquidação(ões) da(s) operação(ões) de derivativos abaixo especificada(s):'))

    html = _email_shell('Liquidação de Operação de Derivativo', _today_br(), intro, body_html)

    return {
        'subject': '(Pagamento de Prêmio) Liquidação de Operação de Derivativo ({}) - {} - {}'.format(asset_label, _today_br(), contraparte),
        'html': html,
        'cc': 'Liquidação; Brazil Comm Sales',
        'to': to_emails,
    }


# NOTE: as of the current spec the premium notice is only generated for the
# 73760.10-2 ("cliente") bucket, so this participante variant is no longer wired
# into build_premium_emails. Kept for reference / possible future reuse.
def _premium_participante_email(items, contraparte, b3_account):
    apurado, _ir, _final = _premium_apurado(items)

    rows = ''
    for d in items:
        sell = _is_sell(d.get('Direction'))
        resultado = _num(d.get('Premium')) * (1 if sell else -1)
        contrato = d.get('Deal', '') if sell else 'Mnemonico Lançador'
        titular  = b3_account if sell else JPM_B3_ACCOUNT
        rows += (
            '<tr style="border:1px solid black;">'
            '<td style="border:1px solid black;">{contrato}</td>'
            '<td style="border:1px solid black;">{tipo}</td>'
            '<td style="border:1px solid black;">{titular}</td>'
            '<td style="border:1px solid black;">{op}</td>'
            '<td style="border:1px solid black;">{venc}</td>'
            '<td style="border:1px solid black;">EUROPEIA</td>'
            '<td style="border:1px solid black;">{ativo}</td>'
            '<td style="border:1px solid black;">{fix_ccy}</td>'
            '<td style="border:1px solid black;">{fix_merc}</td>'
            '<td style="border:1px solid black;">{base}</td>'
            '<td style="border:1px solid black;">{res}</td>'
            '<td style="border:1px solid black;">{pgto}</td>'
            '</tr>'
        ).format(
            contrato=contrato,
            tipo='Put' if _is_put(d.get('Instrument')) else 'Call',
            titular=titular,
            op=_date_br(d.get('TradeDate')),
            venc=_date_br(d.get('SettlementDate')),
            ativo=_asset_label(d),
            fix_ccy=_date_br(d.get('FXConvDate')),
            fix_merc=_date_br(d.get('FixingEndDate')),
            base=_br(abs(_num(d.get('TotalNotional')))),
            res=_br_currency(resultado),
            pgto=_date_br(d.get('SpotDate')),
        )

    body = (
        '<html><body style="font-family:\'Times New Roman\';font-size:12pt;">'
        '<p>Prezados Senhores,</p>'
        '<p>Por gentileza, poderiam confirmar os dados da(s) operação(ões) abaixo?</p>'
        '<p>Conta CETIP {cp}: {b3}</p>'
        '<p>Conta CETIP BANCO JP MORGAN S.A: {jpm}</p>'
        '<table style="font-family:\'Arial\';font-size:10pt;border-collapse:collapse;width:auto;border:1px solid black;text-align:center;">'
        '<tr style="font-weight:bold;border:1px solid black;">'
        '<td style="border:1px solid black;">Contrato</td>'
        '<td style="border:1px solid black;">Tipo Opção</td>'
        '<td style="border:1px solid black;">Titular</td>'
        '<td style="border:1px solid black;">Data Operação</td>'
        '<td style="border:1px solid black;">Data Vencimento</td>'
        '<td style="border:1px solid black;">Exercício</td>'
        '<td style="border:1px solid black;">Moeda/Ativo</td>'
        '<td style="border:1px solid black;">Fixing Moeda</td>'
        '<td style="border:1px solid black;">Fixing Mercadoria</td>'
        '<td style="border:1px solid black;">Valor Base/Quantidade</td>'
        '<td style="border:1px solid black;">Resultado Final</td>'
        '<td style="border:1px solid black;">Data Pagamento Prêmio</td>'
        '</tr>'
    ).format(cp=contraparte, b3=b3_account, jpm=JPM_B3_ACCOUNT) + rows + '</table><br>'

    body += (
        '<table style="font-family:\'Times New Roman\';font-size:12pt;border-collapse:collapse;width:auto;">'
        '<tr><td style="font-weight:bold;">Resultado Apurado:</td><td style="font-weight:bold;">R$ {ap}</td></tr>'
        '<tr><td style="font-weight:bold;">IR (0,005%):</td><td style="font-weight:bold;">R$ 0,00</td></tr>'
        '<tr><td style="font-weight:bold;">Resultado Final:</td><td style="font-weight:bold;">R$ {ap}</td></tr>'
        '</table>'
    ).format(ap=_br_currency(apurado))

    body += FOOTER_HTML + '</body></html>'

    return {
        'subject': 'Confirmação das Operações Fechadas em {} - {} - Opção Mercadoria'.format(_today_br(), contraparte),
        'html': body,
        'cc': 'brazil.otc.ops@jpmorgan.com',
        'to': '',
    }


# ──────────────────────────────────────────────────────────────────────────
# ECONOMIC AFFIRMATION (D0 trade date, against Financial Institutions)
# ──────────────────────────────────────────────────────────────────────────
def build_economic_affirmation_emails(deals, asset_label='Termo de Mercadoria'):
    """IF affirmation: TradeDate == today, against Financial Institutions only.

    Eligible counterparties are those that are NOT Lawton, NOT Banco JP Morgan, and
    whose CETIP account (RefData) is none of 73760.00-9 / 73760.10-2 / 00041.00-7.
    """
    ref = _build_refdata_index()
    today = _today_br()
    drafts = []

    def _eligible(d):
        if _date_br(d.get('TradeDate')) != today:
            return False
        acronym = str(d.get('Acronym', '') or '').strip().upper()
        rec = ref.get(acronym, {})
        b3 = str(rec.get('B3 ACCOUNT', '') or '').strip()
        name = str(rec.get('COUNTERPARTY', '') or d.get('Client', '') or '').upper()
        if b3 in EXCLUDED_B3_AFFIRMATION:
            return False
        if _is_lawton(name, acronym) or _is_jpmorgan(name):
            return False
        return True

    eligible = [d for d in deals if _eligible(d)]

    for (acronym, _commodity), items in _group_by_acronym_commodity(eligible).items():
        rec  = ref.get(acronym, {})
        b3   = str(rec.get('B3 ACCOUNT', '') or '').strip()
        name = rec.get('COUNTERPARTY', '') or acronym
        drafts.append(_economic_affirmation_email(items, name, b3, asset_label))

    return drafts


def _economic_affirmation_email(items, contraparte, b3_account, asset_label):
    data_rows = []
    for d in items:
        fix_ini = _date_br(d.get('FixingStartDate'))
        fix_fim = _date_br(d.get('FixingEndDate'))
        data_rows.append([
            d.get('Deal', ''),
            'Vendedor' if _is_sell(d.get('Direction')) else 'Comprador',
            _date_br(d.get('TradeDate')),
            _br(abs(_num(d.get('TotalNotional'))), 0),
            _br_currency(abs(_num(d.get('Strike'))), 4),
            _asset_label(d),
            fix_ini if fix_ini != fix_fim else 'N/A',
            fix_fim,
            _date_br(d.get('FXConvDate')),
            _date_br(d.get('SettlementDate')),
        ])

    accounts = _email_kv('Contas CETIP', [
        (contraparte, b3_account),
        ('Banco J.P. Morgan S.A.', JPM_B3_ACCOUNT),
    ])
    table = _email_data_table(
        ['Contrato', 'Posição JPMorgan', 'Data Operação', 'Valor Base/Quantidade', 'Taxa Forward',
         'Moeda/Ativo', 'Início Fixing Mercadoria', 'Final Fixing Mercadoria', 'Fixing Moeda', 'Data Vencimento'],
        data_rows)

    intro = (_ep('Prezados Senhores,') +
             _ep('Por gentileza, poderiam confirmar os dados da(s) operação(ões) abaixo?'))
    body_html = accounts + '<div style="height:16px;line-height:16px;font-size:0;">&nbsp;</div>' + table

    html = _email_shell('Confirmação de Operação de Derivativo', _today_br(), intro, body_html)

    return {
        'subject': 'Confirmação da(s) Operação(ões) Fechada(s) em {} - {} - {}'.format(_today_br(), contraparte, asset_label),
        'html': html,
        'cc': 'brazil.otc.ops@jpmorgan.com; Brazil Comm Sales',
        'to': '',
    }


# ──────────────────────────────────────────────────────────────────────────
# Draft delivery — .eml download (works on the ACTING user's machine)
# ──────────────────────────────────────────────────────────────────────────
# The Flask app runs on a shared server, so server-side Outlook automation
# (win32com) would only ever open a draft on the SERVER's machine — never on the
# remote user's. Instead we build a standard .eml per draft and let the user's
# browser download it; double-clicking it opens an editable draft in *their*
# Outlook. The `X-Unsent: 1` header is what makes Outlook open it in compose
# (draft) mode rather than as a received message. The From is the acting user's
# e-mail (looked up from their SID at login → session['user_email']).
# Outlook distribution-list display names → recipients Outlook can resolve from
# an .eml. A bare/accented DL display name does NOT resolve when Outlook opens an
# .eml (it shows mojibake or unresolved text), so we substitute the actual SMTP
# addresses / GAL aliases. Keys are matched accent-insensitively, lower-cased.
# NOTE: keys must be ASCII-folded + lower-case (that's how lookups are normalized).
_RECIPIENT_ALIASES = {
    'liquidacao':        'BRSP_Settlement_Ops@jpmchase.com; brsp_financial_control@restricted.chase.com; brazil_otc_settlements@jpmorgan.com; joao.hira@jpmorgan.com; latam.mumbai.acc@jpmorgan.com',
    'brazil comm sales': 'brazil_comm_sales@jpmorgan.com',
}


def _fold_ascii(s):
    """NFKD + drop combining marks → ASCII (keeps letters, loses accents)."""
    return unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode('ascii')


def _resolve_recipients(value):
    """Expand known DL display names in a ';'-separated recipient string to the
    SMTP addresses / aliases Outlook resolves; pass real addresses through."""
    out = []
    for tok in str(value or '').replace('\r', ' ').replace('\n', ' ').split(';'):
        t = tok.strip()
        if not t:
            continue
        out.append(_RECIPIENT_ALIASES.get(_fold_ascii(t).strip().lower(), t))
    return '; '.join(out)


def _safe_filename(s):
    # Transliterate accents to ASCII (ê→e, ç→c, ã→a…) so the resulting name is
    # pure ASCII. A non-ASCII Content-Disposition filename can be dropped or 500
    # under a strict WSGI server (gunicorn), leaving the browser to download the
    # error page as a blank .eml under the generic 'otc_email_draft.eml' name.
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    out = []
    for ch in s:
        out.append(ch if (ch.isascii() and (ch.isalnum() or ch in ' -_().[]')) else '_')
    name = ''.join(out).strip()
    return (name[:120] or 'draft')


def build_eml_bytes(draft, sender_email=None):
    """Render one draft dict to RFC-822 .eml bytes that Outlook opens as a draft.

    Built by hand for full control of the encoding:
    - Subject is RFC-2047 encoded (Outlook decodes it reliably).
    - To/Cc are run through _resolve_recipients: distribution-list display names
      (e.g. "Liquidação", "Brazil Comm Sales") become the real SMTP addresses /
      aliases Outlook resolves; everything ends up ASCII, so no mojibake and no
      unresolved MIME words.
    - Body is single-part text/html, Content-Transfer-Encoding: 8bit, so the
      HTML is byte-for-byte intact (quoted-printable would mangle the tables).
    """
    def _clean(s):
        return str(s or '').replace('\r', ' ').replace('\n', ' ').strip()

    subj = _clean(draft.get('subject'))
    lines = ['MIME-Version: 1.0']
    lines.append('Subject: ' + (Header(subj, 'utf-8').encode() if subj else ''))
    if sender_email:
        lines.append('From: ' + _fold_ascii(_clean(sender_email)))
    to = _resolve_recipients(draft.get('to'))
    if to:
        lines.append('To: ' + to)
    cc = _resolve_recipients(draft.get('cc'))
    if cc:
        lines.append('Cc: ' + cc)
    lines.append('X-Unsent: 1')                 # → opens as editable draft in Outlook
    lines.append('Content-Type: text/html; charset=utf-8')
    lines.append('Content-Transfer-Encoding: 8bit')
    header = '\r\n'.join(lines)
    html = draft.get('html', '') or ''
    return (header + '\r\n\r\n' + html).encode('utf-8')


def build_drafts_download(drafts, sender_email=None):
    """Package drafts for the browser to download.

    Returns (filename, mimetype, data_bytes). A single draft → one .eml; several
    → a .zip of .eml files. Returns (None, None, None) when there are no drafts.
    """
    if not drafts:
        return None, None, None
    if len(drafts) == 1:
        d = drafts[0]
        fname = _safe_filename(d.get('subject', 'draft')) + '.eml'
        return fname, 'message/rfc822', build_eml_bytes(d, sender_email)

    buf = io.BytesIO()
    seen = {}
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for d in drafts:
            base = _safe_filename(d.get('subject', 'draft'))
            n = seen.get(base, 0)
            seen[base] = n + 1
            entry = base if n == 0 else '{}_{}'.format(base, n + 1)
            zf.writestr(entry + '.eml', build_eml_bytes(d, sender_email))
    return 'otc_email_drafts.zip', 'application/zip', buf.getvalue()
