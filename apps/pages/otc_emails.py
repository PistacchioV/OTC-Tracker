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
import base64
import hashlib
import logging
import zipfile
import unicodedata
from apps.pages.data_paths import data_dir, data_path, data_write, mapping_file, mapping_write
from datetime import datetime

_LOG = logging.getLogger(__name__)
from email.header import Header

_DATA_DIR = data_dir()

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
# Outlook/Gmail render it reliably. One Action-Blue accent, hairline tables,
# generous spacing. Shared by the client-facing drafts.
#
# The header carries the J.P.Morgan wordmark as an inline (CID) image. It is NOT
# a data: URI and NOT a remote URL: Outlook desktop refuses to render data: URIs
# outright, and a remote src would both need the intranet server reachable from
# the reader's machine and land behind Outlook's "download pictures" block. A
# multipart/related part with a Content-ID renders unconditionally.
# ──────────────────────────────────────────────────────────────────────────
_E_LOGO_CID  = 'jpmwordmark'
# Trimmed derivative of images/LogoJPMorgan.png. The source is a 400x400 canvas
# with the wordmark occupying only its middle 318x66 — pasted as-is it would put
# ~80px of empty space above and below the logo in the header, so the transparent
# margin is cropped off. Rendered at 140x29, i.e. ~2.3x pixel density for
# high-DPI screens, matching the footprint of the wordmark it replaces.
_E_LOGO_FILE = os.path.normpath(os.path.join(
    os.path.dirname(__file__), '..', 'static', 'images', 'LogoJPMorgan-email.png'))
_E_LOGO_W, _E_LOGO_H = 140, 29

_E_BLUE  = '#0066cc'
_E_NAVY  = '#243b53'
_E_INK   = '#1d1d1f'
_E_MUTED = '#8a8a8f'
_E_FONT  = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _esc(s):
    s = '' if s is None else str(s)
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _ep(html, muted=False):
    """A body paragraph. Justified: these are dense legal/settlement paragraphs
    that wrap over several lines, and a flush right edge reads noticeably
    tidier. Single-line paragraphs ('Prezados Senhores,') are unaffected."""
    color = '#6c6c72' if muted else '#333333'
    return ('<p style="margin:0 0 12px;font-size:14px;line-height:1.62;text-align:justify;color:' + color +
            ';font-family:' + _E_FONT + ';">' + html + '</p>')


def _email_data_table(headers, rows):
    """A clean hairline table with a navy header and zebra rows, fully centred.

    border-collapse is COLLAPSE, deliberately. With 'separate', Outlook's Word
    engine draws the table-level border around every cell as well as the cell's
    own border-top, so each boundary shows two hairlines side by side — very
    visible on the white zebra rows, invisible on the grey ones. Collapsing
    merges adjacent borders into the single line the design intends. The cost is
    border-radius, which collapse disables — Outlook never honoured it anyway."""
    th = ''.join(
        '<th align="center" style="padding:9px 11px;text-align:center;font-size:10.5px;font-weight:600;'
        'text-transform:uppercase;letter-spacing:.04em;color:#ffffff;white-space:nowrap;">' + _esc(h) + '</th>'
        for h in headers)
    body = ''
    for i, r in enumerate(rows):
        bg = '#ffffff' if i % 2 == 0 else '#f6f7f9'
        tds = ''.join(
            '<td align="center" style="padding:8px 11px;font-size:12px;color:#1d1d1f;text-align:center;'
            'border-top:1px solid #edeef1;white-space:nowrap;">' + _esc(c) + '</td>' for c in r)
        body += '<tr style="background:' + bg + ';">' + tds + '</tr>'
    return ('<table role="presentation" cellpadding="0" cellspacing="0" width="100%" '
            'style="border-collapse:collapse;width:100%;border:1px solid #e6e6ea;'
            'font-family:' + _E_FONT + ';">'
            '<tr style="background:' + _E_NAVY + ';">' + th + '</tr>' + body + '</table>')


def _split_currency(value):
    """'R$ 1.234,56' -> ('R$', '1.234,56'). Anything without a leading currency
    token comes back as ('', value), so the caller can pass plain numbers too."""
    s = str(value or '').strip()
    for sym in ('R$', 'US$', 'USD', '$'):
        if s.startswith(sym):
            return sym, s[len(sym):].strip()
    return '', s


def _email_summary(pairs):
    """Highlighted totals panel. pairs: list of (label, value, is_total).

    The currency symbol gets its own column so every 'R$' lands on the same
    vertical line: right-aligning the whole 'R$ 1.234,56' string only aligns the
    last character, and a negative rendered as '(1.234,56)' then drags its 'R$'
    a full parenthesis to the left of the row above it."""
    rows = ''
    for i, (label, value, is_total) in enumerate(pairs):
        top = '' if i == 0 else 'border-top:1px solid #dbe6f3;'
        lblc = _E_INK if is_total else '#4a4a4f'
        valc = _E_BLUE if is_total else _E_INK
        wt = '700' if is_total else '600'
        fs = '15px' if is_total else '13px'
        cur, num = _split_currency(value)
        rows += ('<tr><td style="padding:8px 14px;font-size:' + fs + ';font-weight:' + wt +
                 ';color:' + lblc + ';' + top + '">' + _esc(label) + '</td>'
                 '<td align="right" style="padding:8px 2px 8px 14px;font-size:' + fs +
                 ';font-weight:700;color:' + valc + ';white-space:nowrap;' + top + '">' +
                 _esc(cur) + '</td>'
                 # 6px left padding: the total row is a size larger, so without a
                 # floor the wider glyphs would butt straight up against the 'R$'.
                 '<td align="right" style="padding:8px 14px 8px 6px;font-size:' + fs +
                 ';font-weight:700;color:' + valc + ';white-space:nowrap;' + top + '">' +
                 _esc(num) + '</td></tr>')
    return ('<table role="presentation" cellpadding="0" cellspacing="0" '
            'style="border-collapse:collapse;background:#f3f6fb;border:1px solid #dbe6f3;'
            'font-family:' + _E_FONT + ';min-width:280px;">' + rows + '</table>')


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
            'style="border-collapse:collapse;background:#ffffff;border:1px solid #e6e6ea;'
            'font-family:' + _E_FONT + ';min-width:320px;">' + rows + '</table>')


def _email_notice(html):
    """A bordered 'Importante:' callout — used for the TED/PIX warning that sits
    above the banking details whenever the client is the one transferring."""
    return ('<table role="presentation" cellpadding="0" cellspacing="0" width="100%" '
            'style="border-collapse:collapse;width:100%;border:1px solid #d9d9de;background:#ffffff;'
            'font-family:' + _E_FONT + ';">'
            '<tr><td style="padding:9px 13px;font-size:12.5px;line-height:1.55;color:#1d1d1f;">'
            '<span style="font-weight:700;">Importante:</span> ' + html + '</td></tr></table>')


def _email_shell(title, ref_date, intro_html, body_html, footer_extra=''):
    """Corporate card: J.P. Morgan wordmark, Action-Blue accent, title, body, footer.
    `footer_extra`: linha adicional no fim da assinatura (ex.: a classificação
    "JPMC Internal Use Only" dos e-mails internos de mensageria)."""
    return (
        # bgcolor ATTRIBUTES alongside the inline styles: Outlook (Word engine and
        # outlook.com) drops style backgrounds on body/table in some render paths,
        # which left the area right of the 640px card WHITE when the window is
        # wider than the card — the attribute form renders everywhere, so the grey
        # canvas now covers the full viewport.
        '<!doctype html>'
        '<html xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">'
        '<head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        '<body style="margin:0;padding:0;background:#f4f4f6;" bgcolor="#f4f4f6">'
        # Word (Outlook desktop, and especially the COMPOSE view these X-Unsent
        # drafts open in) sizes a width:100% table to its fixed page width, not
        # the window — wider windows showed a white strip to the right of the
        # grey canvas, and bgcolor on body/table cannot fix that because the
        # strip lies OUTSIDE the document's page box. The VML <v:background>
        # paints the whole canvas at the renderer level, which is the one
        # mechanism Word applies edge to edge. Other clients skip the MSO
        # conditional and keep using the body/table background.
        '<!--[if gte mso 9]><v:background xmlns:v="urn:schemas-microsoft-com:vml" fill="t">'
        '<v:fill type="tile" color="#f4f4f6"/></v:background><![endif]-->'
        '<table role="presentation" cellpadding="0" cellspacing="0" width="100%" bgcolor="#f4f4f6" '
        'style="background:#f4f4f6;width:100%;">'
        '<tr><td align="center" bgcolor="#f4f4f6" style="padding:26px 12px;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" width="640" '
        'style="width:640px;max-width:640px;background:#ffffff;border:1px solid #e6e6ea;border-radius:14px;'
        'font-family:' + _E_FONT + ';">'
        # header
        '<tr><td style="padding:24px 34px 0;">'
        '<table role="presentation" width="100%"><tr>'
        '<td style="font-size:16px;font-weight:700;letter-spacing:.16em;color:#1d1d1f;">'
        '<img src="cid:' + _E_LOGO_CID + '" alt="J.P.Morgan" '
        'width="' + str(_E_LOGO_W) + '" height="' + str(_E_LOGO_H) + '" '
        'style="display:block;border:0;outline:none;text-decoration:none;'
        'width:' + str(_E_LOGO_W) + 'px;height:' + str(_E_LOGO_H) + 'px;"></td>'
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
        'Ouvidoria JPMorgan: 0800 – 7700847 &middot; ouvidoria.jp.morgan@jpmorgan.com' +
        (('<div style="margin-top:8px;font-weight:600;color:#8a8a8f;">' + _esc(footer_extra) + '</div>')
         if footer_extra else '') +
        '</td></tr>'
        '</table></td></tr></table></body></html>')


# ──────────────────────────────────────────────────────────────────────────
# Data loading / lookups
# ──────────────────────────────────────────────────────────────────────────
def _load_json(name):
    try:
        with open(data_path(name), encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return []


def _refdata():
    """As linhas do Reference Data — DB-first (fase 3), JSON de fallback."""
    try:
        from apps.pages import duck_read
        rows = duck_read.refdata_rows(expected_path=data_path('RefData.json'))
    except Exception:                                       # noqa: BLE001
        rows = None
    return rows if rows is not None else _load_json('RefData.json')


def _build_refdata_index(key='COMMODITIES ACCRONYM'):
    """acronym → ref record. `key` selects which RefData accronym column to index
    by: 'COMMODITIES ACCRONYM' (commodities) or 'FX CASH ACCRONYM' (FXO)."""
    idx = {}
    for r in _refdata():
        acc = str(r.get(key, '') or '').strip().upper()
        if acc and acc not in idx:
            idx[acc] = r
    return idx


def _build_refdata_spn_index():
    """SPN normalizado → ref record. O accronym é opcional no Reference Data (há
    contraparte cadastrada com a coluna em branco), o SPN não é — por isso ele é
    a chave confiável para achar a conta B3 e o nome da contraparte."""
    idx = {}
    for r in _refdata():
        k = _norm_spn(r.get('SPN'))
        if k and k not in idx:
            idx[k] = r
    return idx


def _ref_for_deal(by_acronym, by_spn, deal):
    """Registro do Reference Data de um deal: pelo accronym e, quando ele não
    resolve, pelo SPN. Só o accronym não basta — uma contraparte cadastrada sem
    accronym some do e-mail sem erro nenhum, que é como as operações de prêmio
    D0 deixaram de ser geradas mesmo com a Spot Date de hoje."""
    acr = str((deal or {}).get('Acronym', '') or '').strip().upper()
    rec = by_acronym.get(acr) if acr else None
    return rec or by_spn.get(_norm_spn((deal or {}).get('SPN'))) or {}


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


def _brl(value, dec=2):
    """BR amount WITH the R$ symbol; negatives wrap symbol and all: (R$ 2.500,00)."""
    if value < 0:
        return '(R$ ' + _br(abs(value), dec) + ')'
    return 'R$ ' + _br(value, dec)


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


def _subject_cpty(contraparte, taxid):
    """`'NOME 12.345.678/0001-99'` — a contraparte como ela vai no ASSUNTO.

    O CNPJ entra porque o nome sozinho não identifica: o mesmo grupo tem várias
    entidades com nomes quase iguais ("Mondelez Brasil" × "Mondelez Brasil Norte
    Nordeste"), e quem arquiva o aviso casa pelo cadastro, que é por CNPJ.

    Só entra MASCARADO: `_fmt_cnpj` devolve o texto cru quando não são 14
    dígitos, e um assunto terminando num pedaço de número seria pior do que não
    ter o número. Sem CNPJ utilizável, o assunto fica como sempre foi.
    """
    nome = str(contraparte or '').strip()
    doc = _fmt_cnpj(taxid)
    # A máscara é a prova de que o documento foi reconhecido — `_fmt_cnpj` só a
    # aplica com os 14 dígitos.
    if doc and '/' in doc and '.' in doc:
        return (nome + ' ' + doc).strip()
    return nome


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
    """Um grupo por contraparte (× commodity) = um e-mail. Sem accronym a chave
    cai para o SPN: agrupar por accronym vazio juntaria contrapartes diferentes
    num grupo só, e sairia um único e-mail com os deals de todo mundo, endereçado
    a quem calhasse de estar em primeiro."""
    groups = {}
    for d in deals:
        acr = str(d.get('Acronym', '') or '').strip().upper()
        key = (acr or ('SPN:' + _norm_spn(d.get('SPN'))),
               str(d.get('Commodities', '') or '').strip().upper())
        groups.setdefault(key, []).append(d)
    return groups


# ──────────────────────────────────────────────────────────────────────────
# PREMIUM (D0) — SpotDate == today
# ──────────────────────────────────────────────────────────────────────────
def build_premium_emails(deals, asset_label='Commodities', ref_key='COMMODITIES ACCRONYM',
                         cc_comm_sales=True):
    """D0 premium settlement notice.

    Eligible counterparties: CETIP account (RefData) == 73760.10-2 AND not Lawton,
    restricted to deals whose SpotDate (premium payment date) is today.

    `asset_label` is the asset-class token shown in the subject line
    (e.g. 'Commodities' for opt-commodities, 'Taxas de Câmbio' for opt-fxo).
    `ref_key` selects the RefData accronym column used to resolve each deal's
    Acronym → ref record: 'COMMODITIES ACCRONYM' (default) or 'FX CASH ACCRONYM'
    (FXO deals carry the FX cash accronym, not the commodities one).
    `cc_comm_sales` copies the Brazil Comm Sales desk — they own the commodities
    flow, so the FXO page turns it off and copies Liquidação only.
    """
    ref = _build_refdata_index(ref_key)
    ref_spn = _build_refdata_spn_index()
    cpd = _build_cpdetails_index()
    today = _today_br()

    todays = [d for d in deals if _date_br(d.get('SpotDate')) == today]
    drafts = []

    for _key, items in _group_by_acronym_commodity(todays).items():
        acronym = str(items[0].get('Acronym', '') or '').strip().upper()
        rec   = _ref_for_deal(ref, ref_spn, items[0])
        b3    = str(rec.get('B3 ACCOUNT', '') or '').strip()
        name  = rec.get('COUNTERPARTY', '') or items[0].get('Client', '') or acronym
        spn   = str(items[0].get('SPN', '') or rec.get('SPN', '') or '').strip().upper()
        taxid = rec.get('TAX ID', '') or items[0].get('TaxID', '')

        if b3 != PREMIUM_CLIENT_B3:          # only the 73760.10-2 bucket
            continue
        if _is_lawton(name, acronym):        # never Lawton
            continue

        drafts.append(_premium_cliente_email(items, name, spn, taxid, cpd, asset_label,
                                             cc_comm_sales=cc_comm_sales))

    return drafts


def _premium_apurado(items):
    apurado = sum(_num(d.get('Premium')) * (1 if _is_sell(d.get('Direction')) else -1) for d in items)
    ir = 0.0 if apurado >= 0 else apurado * 0.00005 * -1
    final = apurado + ir if apurado < 0 else apurado
    return apurado, ir, final


def _premium_cliente_email(items, contraparte, spn, taxid, cpd, asset_label='Commodities',
                           cc_comm_sales=True):
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
    # `notice` is the TED-only warning: it only makes sense when the CLIENT is the
    # one transferring (final > 0, JPMorgan receives). When JPMorgan pays, or when
    # the result nets to zero and nobody transfers anything, it is left out.
    notice = ''
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
        if final > 0:
            notice = _email_notice('Não são aceitas transferências via PIX. As transferências devem ser '
                                   'realizadas exclusivamente por meio de TED.')
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
        ((_gap(16) + instr) if instr else '') +
        ((_gap(2) + notice + _gap(12)) if notice else _gap(6)) + bank + _gap(16) +
        _ep('A presente Ficha de Liquidação é parte integrante e inseparável do Contrato e/ou da '
            'Confirmação de Operação de Derivativo em referência.', muted=True))

    intro = (_ep('Prezados Senhores,') +
             _ep('Vimos confirmar a(s) liquidação(ões) da(s) operação(ões) de derivativos abaixo especificada(s):'))

    html = _email_shell('Liquidação de Operação de Derivativo', _today_br(), intro, body_html)

    return {
        'subject': '(Pagamento de Prêmio) Liquidação de Operação de Derivativo ({}) - {} - {}'.format(asset_label, _today_br(), contraparte),
        'html': html,
        'cc': 'Liquidação; Brazil Comm Sales' if cc_comm_sales else 'Liquidação',
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
# NDF SETTLEMENT NOTICES (Daily Settlement › NDF › Summary "Generate")
# Same visual template as the D0 premium notice; the data table carries the
# summary-page fields instead of the deal blotter ones.
# ──────────────────────────────────────────────────────────────────────────
def _ndf_legal_class(legal):
    """'MGT' for the JPMORGAN CHASE legal entity (ex-Morgan Guaranty Trust),
    'JPM' for BANCO J.P. MORGAN. Punctuation/spacing-insensitive."""
    l = ''.join(ch for ch in str(legal or '').upper() if ch.isalnum())
    return 'MGT' if l.startswith('JPMORGANCHASE') else 'JPM'


def _ndf_liquido(t):
    """Resultado Líquido of one trade. The IR withheld always SHRINKS the cash
    actually moving, so it is subtracted from a positive result and added to a
    negative one (same sign-aware rule as the NDF Summary net): e.g. a −20,000.00
    result with 1.00 of tax nets to −19,999.00, not −20,001.00."""
    s = float(t.get('settlement') or 0.0)
    tax = float(t.get('tax') or 0.0)
    return s - tax if s >= 0 else s + tax


def build_ndf_settlement_emails(trades, ref_date=None):
    """NDF settlement notice drafts from the NDF Summary trade rows.

    `trades`: dicts built by routes._ndfsum_collect — counterparty, legal,
    athena, trade_date, notional_fc, settlement, tax, net_type, spn, taxid.

    Grouped per (counterparty, legal entity) — different legal entities never
    net together and carry different subjects. Each group then splits by its
    net type: Total Net → one netted notice; Pay/Rec → one notice per direction
    (sign of the trade's Resultado Líquido); No Net → one notice per trade.
    """
    cpd = _build_cpdetails_index()
    ref_date = ref_date or _today_br()

    groups = {}
    for t in trades:
        name = str(t.get('counterparty', '') or '').strip()
        if not name or _is_lawton(name) or _is_jpmorgan(name):
            continue
        groups.setdefault((name, _ndf_legal_class(t.get('legal'))), []).append(t)

    drafts = []
    for (name, le), items in sorted(groups.items()):
        nt = str(items[0].get('net_type', '') or 'Total Net')
        if nt == 'No Net':
            batches = [[t] for t in items]
        elif nt == 'Pay/Rec':
            recv = [t for t in items if _ndf_liquido(t) >= 0]
            pay = [t for t in items if _ndf_liquido(t) < 0]
            batches = [b for b in (recv, pay) if b]
        else:                                   # Total Net (and the safe default)
            batches = [items]
        for batch in batches:
            drafts.append(_ndf_settlement_email(batch, name, le, ref_date, cpd))
    return drafts


# ── Ficha de Liquidação em PDF (NDF de Moeda) ─────────────────────────────
# Para estas contrapartes o aviso de liquidação leva ANEXO um PDF com o mesmo
# conteúdo do cartão branco do e-mail (logo, data, título, tabela, totais,
# instrução, aviso TED, dados bancários e assinatura).
#
# Quem manda hoje é o cadastro `ndf-pdf-cpty` da tela /mapping. Esta tupla
# continua aqui como SEMENTE e como socorro: é o que `_ndf_pdf_set` usa enquanto
# o arquivo do mapping não existe na instância. Os valores são os da macro
# legada (CommodiXchange) e têm de seguir idênticos aos do seed em routes.py.
_NDF_PDF_COUNTERPARTIES = (
    'ABB AUTOMACAO LTDA',
    'ABB ELETRIFICACAO LTDA - FILIAL 0003',
    'ABB ELETRIFICACAO LTDA',
    'HITACHI ENERGY BRASIL LTDA',
    'PHINIA DO BRASIL PRODUTOS AUTOMOTIVOS LTDA',
    'VEOLIA WATER TECHNOLOGIES AND SOLUTIONS BRASIL TRATAMENTO DE AGUAS LTDA',
)


def _ndf_pdf_norm(name):
    """Nome → chave de comparação (sem acento, caixa alta, traços e espaços
    normalizados) — tolera diferenças de grafia entre RefData e a lista."""
    s = str(name or '').replace('–', '-').replace('—', '-')
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(s.upper().split())


def _ndf_pdf_set():
    """Contrapartes que levam a Ficha em PDF, do cadastro `ndf-pdf-cpty`.

    Lido do disco a cada chamada, de propósito: edição na tela /mapping vale no
    próximo aviso gerado, sem restart — é o mesmo contrato dos outros mappings.

    Cadastro VAZIO é uma resposta legítima ("ninguém leva PDF") e é respeitada.
    A lista histórica só volta quando o arquivo NÃO EXISTE ou não abre — o caso
    da instância em que ninguém abriu a tela de mappings ainda, onde cair para
    zero contraparte tiraria o anexo de quem sempre recebeu.
    """
    try:
        with open(mapping_file('ndf-pdf-cpty', _DATA_DIR + '/mappings'),
                  encoding='utf-8') as fh:
            rows = json.load(fh)
    except Exception:
        return {_ndf_pdf_norm(n) for n in _NDF_PDF_COUNTERPARTIES}
    return {_ndf_pdf_norm(r.get('COUNTERPARTY')) for r in rows
            if isinstance(r, dict) and str(r.get('COUNTERPARTY') or '').strip()}


def _ndf_settlement_pdf(ref_date, headers, data_rows, summary_pairs,
                        instr_text, notice_text, bank_title, bank_pairs):
    """Ficha de Liquidação em PDF — réplica do cartão branco do e-mail.
    Retorna os bytes do PDF, ou None quando o reportlab não está instalado
    (o e-mail sai sem o anexo em vez de falhar)."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                        Table, TableStyle, Image, HRFlowable)
    except ImportError:
        return None

    BLUE  = colors.HexColor(_E_BLUE)
    NAVY  = colors.HexColor(_E_NAVY)
    INK   = colors.HexColor(_E_INK)
    MUTED = colors.HexColor(_E_MUTED)
    HAIR  = colors.HexColor('#e6e6ea')
    ZEBRA = colors.HexColor('#f6f7f9')

    body_style = ParagraphStyle('body', fontName='Helvetica', fontSize=9.5,
                                leading=14.5, textColor=colors.HexColor('#333333'),
                                alignment=4)          # 4 = justify
    muted_style = ParagraphStyle('muted', parent=body_style,
                                 textColor=colors.HexColor('#6c6c72'))
    title_style = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=15,
                                 leading=19, textColor=INK)
    kv_head_style = ParagraphStyle('kvhead', fontName='Helvetica-Bold', fontSize=7.5,
                                   leading=10, textColor=MUTED)
    foot_style = ParagraphStyle('foot', fontName='Helvetica', fontSize=7.5,
                                leading=12, textColor=MUTED)

    story = []

    # Cabeçalho: logo à esquerda, data à direita (mesma proporção do e-mail)
    try:
        logo = Image(_E_LOGO_FILE, width=110, height=110.0 * _E_LOGO_H / _E_LOGO_W)
    except Exception:
        logo = Paragraph('<b>J.P.Morgan</b>', title_style)
    date_p = Paragraph(str(ref_date or ''), ParagraphStyle(
        'date', fontName='Helvetica-Bold', fontSize=8, textColor=MUTED, alignment=2))
    head = Table([[logo, date_p]], colWidths=[300, 215])
    head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                              ('LEFTPADDING', (0, 0), (-1, -1), 0),
                              ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    story.append(head)
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width=33, thickness=2.5, color=BLUE, hAlign='LEFT'))
    story.append(Spacer(1, 10))
    story.append(Paragraph('Liquidação de Operação de Derivativo', title_style))
    story.append(Spacer(1, 12))
    story.append(Paragraph('Prezados Senhores,', body_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph('Vimos confirmar a(s) liquidação(ões) da(s) operação(ões) '
                           'de derivativos abaixo especificada(s):', body_style))
    story.append(Spacer(1, 12))

    # Tabela de operações — cabeçalho navy, zebra, hairlines (como no e-mail).
    # Cabeçalhos como Paragraph para os títulos longos quebrarem linha em vez
    # de invadirem a coluna vizinha.
    head_cell = ParagraphStyle('thead', fontName='Helvetica-Bold', fontSize=6.5,
                               leading=8.5, textColor=colors.white, alignment=1)
    tbl = Table([[Paragraph(str(h).upper(), head_cell) for h in headers]] +
                [[str(c) for c in r] for r in data_rows],
                colWidths=[515.0 / len(headers)] * len(headers), repeatRows=1)
    zebra_cmds = [('BACKGROUND', (0, i), (-1, i), ZEBRA)
                  for i in range(2, len(data_rows) + 1, 2)]
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 7.5),
        ('TEXTCOLOR', (0, 1), (-1, -1), INK),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 0.5, HAIR),
        ('LINEBELOW', (0, 0), (-1, -2), 0.5, colors.HexColor('#edeef1')),
    ] + zebra_cmds))
    story.append(tbl)
    story.append(Spacer(1, 14))

    # Painel de totais (última linha em azul, como no e-mail)
    sum_rows = [[lbl, val] for lbl, val, _tot in summary_pairs]
    sums = Table(sum_rows, colWidths=[140, 110], hAlign='LEFT')
    sum_cmds = [
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f3f6fb')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#dbe6f3')),
        ('LINEABOVE', (0, 1), (-1, -1), 0.5, colors.HexColor('#dbe6f3')),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]
    for i, (_lbl, _val, is_total) in enumerate(summary_pairs):
        sum_cmds += [('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'),
                     ('FONTSIZE', (0, i), (-1, i), 10.5 if is_total else 8.5),
                     ('TEXTCOLOR', (1, i), (1, i), BLUE if is_total else INK)]
    sums.setStyle(TableStyle(sum_cmds))
    story.append(sums)

    if instr_text:
        story.append(Spacer(1, 14))
        story.append(Paragraph(instr_text, body_style))
    if notice_text:
        story.append(Spacer(1, 6))
        notice = Table([[Paragraph('<b>Importante:</b> ' + notice_text,
                                   ParagraphStyle('notice', parent=body_style,
                                                  fontSize=8.5, leading=12.5,
                                                  alignment=0))]],
                       colWidths=[515])
        notice.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#d9d9de')),
            ('TOPPADDING', (0, 0), (-1, -1), 7),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10)]))
        story.append(notice)
    story.append(Spacer(1, 12))

    # Dados bancários (título + tabela chave/valor, como no e-mail)
    story.append(Paragraph(str(bank_title or '').upper(), kv_head_style))
    story.append(Spacer(1, 4))
    kv = Table([[lbl, val] for lbl, val in bank_pairs],
               colWidths=[150, 190], hAlign='LEFT')
    kv.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, HAIR),
        ('LINEABOVE', (0, 1), (-1, -1), 0.5, colors.HexColor('#ececf0')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#6c6c72')),
        ('TEXTCOLOR', (1, 0), (1, -1), INK),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10)]))
    story.append(kv)
    story.append(Spacer(1, 14))
    story.append(Paragraph('A presente Ficha de Liquidação é parte integrante e inseparável do '
                           'Contrato e/ou da Confirmação de Operação de Derivativo em referência.',
                           muted_style))

    # Assinatura (rodapé do cartão)
    story.append(Spacer(1, 18))
    story.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#ececf0')))
    story.append(Spacer(1, 8))
    story.append(Paragraph('<b>Atenciosamente,</b>', foot_style))
    story.append(Paragraph('Banco J.P. Morgan S.A. &nbsp;|&nbsp; Av. Brigadeiro Faria Lima, 3729 '
                           '– 15º andar – São Paulo – SP<br/>'
                           'T: 55 11 4950 6717 &nbsp;|&nbsp; brsp_otc_derivatives_ops@jpmorgan.com '
                           '&nbsp;|&nbsp; jpmorgan.com<br/>'
                           'Ouvidoria JPMorgan: 0800 – 7700847 &middot; '
                           'ouvidoria.jp.morgan@jpmorgan.com', foot_style))

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=40, rightMargin=40,
                      topMargin=36, bottomMargin=36,
                      title='Liquidação de Operação de Derivativo').build(story)
    return buf.getvalue()


def _ndf_settlement_email(items, contraparte, le_class, ref_date, cpd):
    apurado = sum(float(t.get('settlement') or 0.0) for t in items)
    ir = sum(float(t.get('tax') or 0.0) for t in items)
    # Sign-aware net (see _ndf_liquido): the IR shrinks the cash moving, so on a
    # negative Resultado Apurado it is added back rather than subtracted — final
    # is the sum of the per-trade líquidos, not simply apurado − ir.
    final = sum(_ndf_liquido(t) for t in items)
    cp = cpd.get(_norm_spn(items[0].get('spn')), {})
    taxid = items[0].get('taxid', '')
    to_emails = '; '.join(_contacts_emails(cp, _SETTLEMENT_KEYWORDS))

    data_rows = [[
        t.get('athena', ''),
        t.get('trade_date', '') or '—',
        ((str(t.get('ccy', '') or '').strip().upper() + ' ') if str(t.get('ccy', '') or '').strip() else '')
        + _br(abs(float(t.get('notional_fc') or 0.0))),
        _brl(float(t.get('settlement') or 0.0)),
        _brl(float(t.get('tax') or 0.0)),
        _brl(_ndf_liquido(t)),
    ] for t in items]

    table = _email_data_table(
        ['Nº da Confirmação', 'Data de Início da Operação', 'Notional Original da Operação',
         'Resultado Apurado', 'IR (0,005%)', 'Resultado Líquido'],
        data_rows)

    summary_pairs = [
        ('Resultado Apurado', 'R$ ' + _br_currency(apurado), False),
        ('IR (0,005%)',       'R$ ' + _br(ir),               False),
        ('Resultado Final',   'R$ ' + _br_currency(final),   True),
    ]
    summary = _email_summary(summary_pairs)

    # Same settlement-instruction / banking logic as the premium notice: the
    # sign of the final result decides who transfers (negative → JPMorgan pays
    # into the client's default PAY account; positive → debit / TED-only note
    # with JPMorgan's own details; zero → nobody transfers). Which JPMorgan
    # details depends on the legal entity: the Chase entity (MGT) collects in
    # its own Brasil account, not the Banco's.
    _JPM_BANK_KV = [
        ('Nome e nº do banco', 'BANCO JP MORGAN S/A - 376'),
        ('Nº e nome da agência', '0011'),
        ('Conta-corrente nº', '5116003'),
        ('CNPJ/MF nº', '33.172.537/0001-98'),
    ] if le_class != 'MGT' else [
        ('Nome e nº do banco', 'JPMORGAN CHASE BANK (BRASIL) - 488'),
        ('Nº e nome da agência', '0001'),
        ('Conta-corrente nº', '985181643'),
        ('CNPJ/MF nº', '46.518.205/0001-64'),
    ]
    notice_text = ''
    if final < 0:
        instr_text = ('Conforme entendimentos mantidos, informamos que providenciaremos nesta data a '
                      'transferência financeira do montante correspondente ao Resultado Final Apurado em vosso favor, '
                      'conforme os dados a seguir, transmitidos por meio da Autorização Permanente para Liquidação '
                      'Financeira e/ou confirmados por ligação telefônica:')
        bank_name, agency, account = _first_bank(cp, 'PAY')   # JPM pays → PAY details
        bank_title = 'Dados para pagamento'
        bank_pairs = [
            ('Nome e nº do banco', bank_name or '—'),
            ('Nº e nome da agência', agency or '—'),
            ('Conta-corrente nº', account or '—'),
            ('CNPJ/MF nº', _fmt_cnpj(taxid)),
        ]
    else:
        instr_text = ('Sendo assim, informamos que debitaremos os valores descritos acima da conta corrente do '
                      'Cliente junto ao Banco J.P.Morgan S.A., mediante confirmação de saldo e nos moldes da '
                      'autorização de débito encaminhada pelos Srs. Caso não tenham encaminhado autorização de débito, '
                      'solicitamos que o montante correspondente ao Resultado Final Apurado acima seja transferido em '
                      'favor do Banco J.P Morgan S.A. nesta data, conforme os dados a seguir:') if final > 0 else ''
        if final > 0:
            notice_text = ('Não são aceitas transferências via PIX. As transferências devem ser '
                           'realizadas exclusivamente por meio de TED.')
        bank_title = 'Dados bancários'
        bank_pairs = list(_JPM_BANK_KV)
    instr = _ep(instr_text) if instr_text else ''
    notice = _email_notice(notice_text) if notice_text else ''
    bank = _email_kv(bank_title, bank_pairs)

    def _gap(h):
        return '<div style="height:' + str(h) + 'px;line-height:' + str(h) + 'px;font-size:0;">&nbsp;</div>'

    body_html = (
        table + _gap(18) + summary +
        ((_gap(16) + instr) if instr else '') +
        ((_gap(2) + notice + _gap(12)) if notice else _gap(6)) + bank + _gap(16) +
        _ep('A presente Ficha de Liquidação é parte integrante e inseparável do Contrato e/ou da '
            'Confirmação de Operação de Derivativo em referência.', muted=True))

    intro = (_ep('Prezados Senhores,') +
             _ep('Vimos confirmar a(s) liquidação(ões) da(s) operação(ões) de derivativos abaixo especificada(s):'))

    html = _email_shell('Liquidação de Operação de Derivativo', ref_date, intro, body_html)

    subject = 'Liquidação de Operação de Derivativo (Termo de Moeda) - {} - {}'.format(
        ref_date, _subject_cpty(contraparte, taxid))
    if le_class == 'MGT':
        subject += ' x JPMORGAN CHASE'

    draft = {
        'subject': subject,
        'html': html,
        'cc': 'Liquidação',                    # FX flow — Comm Sales isn't copied
        'to': to_emails,
        'counterparty': contraparte,           # for the caller's per-cpty count; not emitted in the .eml
    }

    # Contrapartes que exigem a Ficha de Liquidação também em PDF anexo (mesmo
    # conteúdo do cartão branco do e-mail). Nome do anexo: "<cpty> - <yyyymmdd>".
    if _ndf_pdf_norm(contraparte) in _ndf_pdf_set():
        try:
            ymd = datetime.strptime(ref_date, '%d/%m/%Y').strftime('%Y%m%d')
        except ValueError:
            ymd = datetime.now().strftime('%Y%m%d')
        pdf = _ndf_settlement_pdf(
            ref_date=ref_date,
            headers=['Nº da Confirmação', 'Data de Início da Operação',
                     'Notional Original da Operação', 'Resultado Apurado',
                     'IR (0,005%)', 'Resultado Líquido'],
            data_rows=data_rows, summary_pairs=summary_pairs,
            instr_text=instr_text, notice_text=notice_text,
            bank_title=bank_title, bank_pairs=bank_pairs)
        if pdf:
            draft['attachments'] = [{
                'filename': _safe_filename('{} - {}'.format(contraparte, ymd)) + '.pdf',
                'mime': 'application/pdf', 'data': pdf}]
    return draft


# ──────────────────────────────────────────────────────────────────────────
# AVISO DE LIQUIDAÇÃO — SWAP (Other Products › Swap › Settlement Advice)
# ──────────────────────────────────────────────────────────────────────────
#  Mesmo documento do aviso de NDF — mesma casca, mesma tabela, mesmo painel de
#  totais, mesma regra de instrução/dados bancários pelo sinal do resultado. O
#  que muda é a TABELA, que são as colunas da tela de Settlement Advice de Swap,
#  e o assunto.
#
#  As colunas chegam prontas de `routes._swadv_email_rows` (já em BR): esta
#  função não sabe a ordem delas nem precisa saber — reconstruí-la aqui criaria a
#  segunda cópia da ordem das colunas, que é justamente o que já deu problema no
#  Trade Level.
def build_swap_settlement_emails(rows, headers, headers_premium, ref_date=None):
    """Avisos de liquidação de SWAP.

    `rows`: dicts de `routes._swadv_email_rows` — cells (já formatadas, na ordem
    de `headers`), counterparty, legal, spn, taxid, premium, bruto/ir/liquido.

    Um aviso por (contraparte × entidade legal × prêmio). Entidades legais
    diferentes nunca netam juntas e levam assuntos diferentes — é a regra do
    aviso de NDF. O prêmio separa por um motivo próprio: ele muda o assunto E o
    nome de uma coluna, então misturar os dois num documento só imprimiria uma
    das duas versões para as duas coisas.
    """
    cpd = _build_cpdetails_index()
    ref_date = ref_date or _today_br()

    groups = {}
    for r in rows:
        name = str(r.get('counterparty', '') or '').strip()
        if not name or _is_lawton(name) or _is_jpmorgan(name):
            continue
        groups.setdefault((name, _ndf_legal_class(r.get('legal')), bool(r.get('premium'))),
                          []).append(r)

    drafts = []
    for (name, le, premium), items in sorted(groups.items()):
        drafts.append(_swap_settlement_email(
            items, name, le, premium, ref_date, cpd,
            headers_premium if premium else headers))
    return drafts


def _swap_settlement_email(items, contraparte, le_class, premium, ref_date, cpd, headers):
    bruto = sum(float(t.get('bruto') or 0.0) for t in items)
    ir = sum(float(t.get('ir') or 0.0) for t in items)
    final = sum(float(t.get('liquido') or 0.0) for t in items)
    cp = cpd.get(_norm_spn(items[0].get('spn')), {})
    taxid = items[0].get('taxid', '')
    to_emails = '; '.join(_contacts_emails(cp, _SETTLEMENT_KEYWORDS))

    table = _email_data_table(headers, [t.get('cells') or [] for t in items])
    summary_pairs = [
        ('Resultado Bruto',  'R$ ' + _br_currency(bruto), False),
        ('IR',               'R$ ' + _br(ir),             False),
        ('Resultado Final',  'R$ ' + _br_currency(final), True),
    ]
    summary = _email_summary(summary_pairs)

    # Instrução e dados bancários: MESMA regra do aviso de NDF (o sinal do
    # resultado final decide quem transfere), reaproveitada verbatim para os dois
    # documentos não divergirem em instrução de pagamento.
    _JPM_BANK_KV = [
        ('Nome e nº do banco', 'BANCO JP MORGAN S/A - 376'),
        ('Nº e nome da agência', '0011'),
        ('Conta-corrente nº', '5116003'),
        ('CNPJ/MF nº', '33.172.537/0001-98'),
    ] if le_class != 'MGT' else [
        ('Nome e nº do banco', 'JPMORGAN CHASE BANK (BRASIL) - 488'),
        ('Nº e nome da agência', '0001'),
        ('Conta-corrente nº', '985181643'),
        ('CNPJ/MF nº', '46.518.205/0001-64'),
    ]
    notice_text = ''
    if final < 0:
        instr_text = ('Conforme entendimentos mantidos, informamos que providenciaremos nesta data a '
                      'transferência financeira do montante correspondente ao Resultado Final Apurado em vosso favor, '
                      'conforme os dados a seguir, transmitidos por meio da Autorização Permanente para Liquidação '
                      'Financeira e/ou confirmados por ligação telefônica:')
        bank_name, agency, account = _first_bank(cp, 'PAY')   # JPM paga → dados de PAY
        bank_title = 'Dados para pagamento'
        bank_pairs = [
            ('Nome e nº do banco', bank_name or '—'),
            ('Nº e nome da agência', agency or '—'),
            ('Conta-corrente nº', account or '—'),
            ('CNPJ/MF nº', _fmt_cnpj(taxid)),
        ]
    else:
        instr_text = ('Sendo assim, informamos que debitaremos os valores descritos acima da conta corrente do '
                      'Cliente junto ao Banco J.P.Morgan S.A., mediante confirmação de saldo e nos moldes da '
                      'autorização de débito encaminhada pelos Srs. Caso não tenham encaminhado autorização de débito, '
                      'solicitamos que o montante correspondente ao Resultado Final Apurado acima seja transferido em '
                      'favor do Banco J.P Morgan S.A. nesta data, conforme os dados a seguir:') if final > 0 else ''
        if final > 0:
            notice_text = ('Não são aceitas transferências via PIX. As transferências devem ser '
                           'realizadas exclusivamente por meio de TED.')
        bank_title = 'Dados bancários'
        bank_pairs = list(_JPM_BANK_KV)
    instr = _ep(instr_text) if instr_text else ''
    notice = _email_notice(notice_text) if notice_text else ''
    bank = _email_kv(bank_title, bank_pairs)

    def _gap(h):
        return '<div style="height:' + str(h) + 'px;line-height:' + str(h) + 'px;font-size:0;">&nbsp;</div>'

    body_html = (
        table + _gap(18) + summary +
        ((_gap(16) + instr) if instr else '') +
        ((_gap(2) + notice + _gap(12)) if notice else _gap(6)) + bank + _gap(16) +
        _ep('A presente Ficha de Liquidação é parte integrante e inseparável do Contrato e/ou da '
            'Confirmação de Operação de Derivativo em referência.', muted=True))

    intro = (_ep('Prezados Senhores,') +
             _ep('Vimos confirmar a(s) liquidação(ões) da(s) operação(ões) de derivativos abaixo especificada(s):'))
    html = _email_shell('Liquidação de Operação de Derivativo', ref_date, intro, body_html)

    subject = 'Liquidação de Operação de Derivativo (Swap) - {} - {}'.format(
        ref_date, _subject_cpty(contraparte, taxid))
    if premium:
        subject = '(Pagamento de Prêmio) ' + subject
    if le_class == 'MGT':
        subject += ' x JPMORGAN CHASE'

    return {'subject': subject, 'html': html, 'cc': 'Liquidação', 'to': to_emails,
            'counterparty': contraparte}


# ──────────────────────────────────────────────────────────────────────────
# AVISO DE LIQUIDAÇÃO — NDF COMMODITIES (Termo de Mercadoria)
# ──────────────────────────────────────────────────────────────────────────
#  Mesmo documento do aviso de NDF de moeda: mesma casca, mesma tabela, mesmo
#  painel de totais, mesma regra de instrução/dados bancários pelo sinal do
#  resultado, e o MESMO anexo em PDF (`_ndf_settlement_pdf`), para as duas
#  fichas não divergirem. O que muda são as colunas e o assunto.
#
#  A QUEBRA em avisos, que é o ponto delicado:
#    · net type Total Net → um aviso;
#    · Pay/Rec           → um por SENTIDO do resultado líquido;
#    · No Net            → um por trade;
#    · e, para as contrapartes marcadas no cadastro `ndfc-advice-split`
#      (Mondelez), cada um dos acima ainda quebra POR COMMODITY.
def build_ndfc_settlement_emails(rows, headers, ref_date=None, split_commodity=None,
                                 product_label='Termo de Commodities'):
    """Avisos de liquidação de Termo de Mercadoria — e de OPÇÃO.

    `rows`: dicts de `routes._ndfadv_email_rows` (ou `_optadv_email_rows`) —
    cells (já em BR, na ordem de `headers`), counterparty, legal, spn, taxid,
    net_type, commodity, liquido.
    `split_commodity`: callable(nome) → bool; None = ninguém quebra por commodity.
    `product_label`: o que vai entre parênteses no ASSUNTO — o DEFAULT do lote.
    Uma linha pode trazer o seu próprio em `product_label`, e é assim que a
    opção resolve o rótulo pela classe do subjacente ('Opção de Commodities',
    'Opção de Taxas de Câmbio', 'Opção de <classe>'). O rótulo entra na CHAVE do
    agrupamento: um assunto por documento, então classes diferentes nunca netam
    no mesmo aviso — senão um dos dois rótulos mentiria.

    `premium` por linha: prefixa `(Pagamento de Prêmio)` no assunto e também
    separa o aviso, exatamente como no de Swap. Pagamento de prêmio e liquidação
    da operação são caixas diferentes, e chamar o conjunto de prêmio esconderia o
    outro.

    Corpo, quebras, dados bancários, ficha em PDF e cadastro de destinatários são
    os MESMOS do termo — duplicar a função para trocar quatro palavras no assunto
    criaria duas fichas de liquidação para manter.
    """
    cpd = _build_cpdetails_index()
    ref_date = ref_date or _today_br()
    split_commodity = split_commodity or (lambda _n: False)

    groups = {}
    for r in rows:
        name = str(r.get('counterparty', '') or '').strip()
        if not name or _is_lawton(name) or _is_jpmorgan(name):
            continue
        groups.setdefault((name, _ndf_legal_class(r.get('legal')),
                           bool(r.get('premium')),
                           str(r.get('product_label') or product_label)), []).append(r)

    drafts = []
    for (name, le, premium, label), items in sorted(groups.items()):
        nt = str(items[0].get('net_type', '') or 'Total Net')
        if nt == 'No Net':
            batches = [[t] for t in items]
        elif nt == 'Pay/Rec':
            recv = [t for t in items if float(t.get('liquido') or 0.0) >= 0]
            pay = [t for t in items if float(t.get('liquido') or 0.0) < 0]
            batches = [b for b in (recv, pay) if b]
        else:
            batches = [items]
        if split_commodity(name):
            # A quebra por commodity é a ÚLTIMA: ela subdivide o que o net type
            # já separou, então um Pay/Rec do Mondelez sai por sentido E por
            # commodity, que foi o pedido.
            split = []
            for b in batches:
                per = {}
                for t in b:
                    per.setdefault(str(t.get('commodity', '') or ''), []).append(t)
                split.extend([per[k] for k in sorted(per)])
            batches = split
        for batch in batches:
            drafts.append(_ndfc_settlement_email(batch, name, le, ref_date, cpd, headers,
                                                 label, premium))
    return drafts


def _ndfc_settlement_email(items, contraparte, le_class, ref_date, cpd, headers,
                           product_label='Termo de Commodities', premium=False):
    apurado = sum(float(t.get('apurado') or 0.0) for t in items)
    ir = sum(float(t.get('ir') or 0.0) for t in items)
    final = sum(float(t.get('liquido') or 0.0) for t in items)
    cp = cpd.get(_norm_spn(items[0].get('spn')), {})
    taxid = items[0].get('taxid', '')
    to_emails = '; '.join(_contacts_emails(cp, _SETTLEMENT_KEYWORDS))

    # ── Aviso de PRÊMIO de opção: a tabela não leva IR nem Resultado Líquido ──
    # O imposto da opção é do NET, não da operação (§310): por linha ele não
    # existe, e as duas colunas mostravam um rateio que não é fato do contrato —
    # o Resultado Líquido de cada linha repetia o Apurado com alguns centavos a
    # menos, sem que aquela operação tivesse sofrido retenção nenhuma. Ele passa
    # a aparecer uma vez só, no quadro de baixo, e só quando há o que reter.
    #
    # Vale para as TRÊS classes de subjacente (mercadoria, câmbio e equity): o
    # que decide é o par `premium` × `family`, não o rótulo do produto. O aviso
    # de EXERCÍCIO/RECOMPRA e o termo de mercadoria seguem com as colunas.
    so_apurado = bool(premium) and str(items[0].get('family') or '') == 'option'
    headers = list(headers)
    data_rows = [list(t.get('cells') or []) for t in items]
    if so_apurado:
        corta = {i for i, h in enumerate(headers)
                 if h in ('IR 0,005% (R$)', 'Resultado Líquido (R$)')}
        if corta:
            headers = [h for i, h in enumerate(headers) if i not in corta]
            data_rows = [[cel for i, cel in enumerate(r) if i not in corta]
                         for r in data_rows]

    table = _email_data_table(headers, data_rows)
    summary_pairs = [('Resultado Apurado', 'R$ ' + _br_currency(apurado), False)]
    # Sem retenção não há linha de IR no quadro do prêmio: `R$ 0,00` num aviso
    # que já não tem a coluna diria que o imposto foi calculado e deu zero, e a
    # pergunta que ele levanta ("por que zero?") não tem resposta no documento.
    # O Resultado Final fica sempre — é o valor que o parágrafo de instrução
    # manda transferir.
    if ir or not so_apurado:
        summary_pairs.append(('IR (0,005%)', 'R$ ' + _br(ir), False))
    summary_pairs.append(('Resultado Final', 'R$ ' + _br_currency(final), True))
    summary = _email_summary(summary_pairs)

    _JPM_BANK_KV = [
        ('Nome e nº do banco', 'BANCO JP MORGAN S/A - 376'),
        ('Nº e nome da agência', '0011'),
        ('Conta-corrente nº', '5116003'),
        ('CNPJ/MF nº', '33.172.537/0001-98'),
    ] if le_class != 'MGT' else [
        ('Nome e nº do banco', 'JPMORGAN CHASE BANK (BRASIL) - 488'),
        ('Nº e nome da agência', '0001'),
        ('Conta-corrente nº', '985181643'),
        ('CNPJ/MF nº', '46.518.205/0001-64'),
    ]
    notice_text = ''
    if final < 0:
        instr_text = ('Conforme entendimentos mantidos, informamos que providenciaremos nesta data a '
                      'transferência financeira do montante correspondente ao Resultado Final Apurado em vosso favor, '
                      'conforme os dados a seguir, transmitidos por meio da Autorização Permanente para Liquidação '
                      'Financeira e/ou confirmados por ligação telefônica:')
        bank_name, agency, account = _first_bank(cp, 'PAY')
        bank_title = 'Dados para pagamento'
        bank_pairs = [
            ('Nome e nº do banco', bank_name or '—'),
            ('Nº e nome da agência', agency or '—'),
            ('Conta-corrente nº', account or '—'),
            ('CNPJ/MF nº', _fmt_cnpj(taxid)),
        ]
    else:
        instr_text = ('Sendo assim, informamos que debitaremos os valores descritos acima da conta corrente do '
                      'Cliente junto ao Banco J.P.Morgan S.A., mediante confirmação de saldo e nos moldes da '
                      'autorização de débito encaminhada pelos Srs. Caso não tenham encaminhado autorização de débito, '
                      'solicitamos que o montante correspondente ao Resultado Final Apurado acima seja transferido em '
                      'favor do Banco J.P Morgan S.A. nesta data, conforme os dados a seguir:') if final > 0 else ''
        if final > 0:
            notice_text = ('Não são aceitas transferências via PIX. As transferências devem ser '
                           'realizadas exclusivamente por meio de TED.')
        bank_title = 'Dados bancários'
        bank_pairs = list(_JPM_BANK_KV)
    instr = _ep(instr_text) if instr_text else ''
    notice = _email_notice(notice_text) if notice_text else ''
    bank = _email_kv(bank_title, bank_pairs)

    def _gap(h):
        return '<div style="height:' + str(h) + 'px;line-height:' + str(h) + 'px;font-size:0;">&nbsp;</div>'

    body_html = (
        table + _gap(18) + summary +
        ((_gap(16) + instr) if instr else '') +
        ((_gap(2) + notice + _gap(12)) if notice else _gap(6)) + bank + _gap(16) +
        _ep('A presente Ficha de Liquidação é parte integrante e inseparável do Contrato e/ou da '
            'Confirmação de Operação de Derivativo em referência.', muted=True))
    intro = (_ep('Prezados Senhores,') +
             _ep('Vimos confirmar a(s) liquidação(ões) da(s) operação(ões) de derivativos abaixo especificada(s):'))
    html = _email_shell('Liquidação de Operação de Derivativo', ref_date, intro, body_html)

    subject = 'Liquidação de Operação de Derivativo ({}) - {} - {}'.format(
        product_label, ref_date, _subject_cpty(contraparte, taxid))
    # Um aviso por commodity precisa se distinguir na caixa de entrada: três
    # assuntos idênticos no mesmo dia são três anexos que ninguém sabe separar.
    commodities = {str(t.get('commodity', '') or '') for t in items}
    if len(commodities) == 1 and commodities != {''}:
        subject += ' - ' + commodities.pop()
    # Prefixo, e não sufixo: o assunto é lido da esquerda numa lista de e-mails, e
    # é aí que "isto é prêmio, não é a liquidação" precisa aparecer. Mesma regra e
    # mesmo texto do aviso de Swap.
    if premium:
        subject = '(Pagamento de Prêmio) ' + subject
    if le_class == 'MGT':
        subject += ' x JPMORGAN CHASE'

    draft = {'subject': subject, 'html': html, 'cc': 'Liquidação', 'to': to_emails,
             'counterparty': contraparte}

    # Ficha em PDF: MESMO gerador do aviso de NDF de moeda e MESMO cadastro de
    # quem recebe (`ndf-pdf-cpty`) — "vale para aqui também".
    if _ndf_pdf_norm(contraparte) in _ndf_pdf_set():
        try:
            ymd = datetime.strptime(ref_date, '%d/%m/%Y').strftime('%Y%m%d')
        except ValueError:
            ymd = datetime.now().strftime('%Y%m%d')
        pdf = _ndf_settlement_pdf(
            ref_date=ref_date, headers=headers, data_rows=data_rows,
            summary_pairs=summary_pairs, instr_text=instr_text, notice_text=notice_text,
            bank_title=bank_title, bank_pairs=bank_pairs)
        if pdf:
            draft['attachments'] = [{
                'filename': _safe_filename('{} - {}'.format(contraparte, ymd)) + '.pdf',
                'mime': 'application/pdf', 'data': pdf}]
    return draft


# ──────────────────────────────────────────────────────────────────────────
# ECONOMIC AFFIRMATION (D0 trade date, against Financial Institutions)
# ──────────────────────────────────────────────────────────────────────────
def build_economic_affirmation_emails(deals, asset_label='Termo de Mercadoria'):
    """IF affirmation: TradeDate == today, against Financial Institutions only.

    Eligible counterparties are those that are NOT Lawton, NOT Banco JP Morgan, and
    whose CETIP account (RefData) is none of 73760.00-9 / 73760.10-2 / 00041.00-7.
    """
    ref = _build_refdata_index()
    ref_spn = _build_refdata_spn_index()
    today = _today_br()
    drafts = []

    def _eligible(d):
        if _date_br(d.get('TradeDate')) != today:
            return False
        acronym = str(d.get('Acronym', '') or '').strip().upper()
        # Pelo SPN também: cadastro sem accronym deixava a conta B3 em branco, e
        # com ela em branco a contraparte não caía em EXCLUDED_B3_AFFIRMATION —
        # ou seja, um cliente passava por instituição financeira e recebia uma
        # afirmação que não é para ele.
        rec = _ref_for_deal(ref, ref_spn, d)
        b3 = str(rec.get('B3 ACCOUNT', '') or '').strip()
        name = str(rec.get('COUNTERPARTY', '') or d.get('Client', '') or '').upper()
        if b3 in EXCLUDED_B3_AFFIRMATION:
            return False
        if _is_lawton(name, acronym) or _is_jpmorgan(name):
            return False
        return True

    eligible = [d for d in deals if _eligible(d)]

    for _key, items in _group_by_acronym_commodity(eligible).items():
        acronym = str(items[0].get('Acronym', '') or '').strip().upper()
        rec  = _ref_for_deal(ref, ref_spn, items[0])
        b3   = str(rec.get('B3 ACCOUNT', '') or '').strip()
        name = rec.get('COUNTERPARTY', '') or items[0].get('Client', '') or acronym
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


_LOGO_CACHE = {}


def _logo_bytes():
    """The inline wordmark PNG, read once. Returns None if the asset is missing —
    the draft is then built without the image part rather than failing."""
    if 'data' not in _LOGO_CACHE:
        try:
            with open(_E_LOGO_FILE, 'rb') as fh:
                _LOGO_CACHE['data'] = fh.read()
        except Exception:
            _LOGO_CACHE['data'] = None
    return _LOGO_CACHE['data']


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
    bcc = _resolve_recipients(draft.get('bcc'))
    if bcc:
        lines.append('Bcc: ' + bcc)
    lines.append('X-Unsent: 1')                 # → opens as editable draft in Outlook
    html = draft.get('html', '') or ''
    attachments = [a for a in (draft.get('attachments') or []) if a.get('data')]

    def _b64_wrap(data):
        b64 = base64.b64encode(data).decode('ascii')
        return '\r\n'.join(b64[i:i + 76] for i in range(0, len(b64), 76))

    logo = _logo_bytes() if ('cid:' + _E_LOGO_CID) in html else None
    md5 = hashlib.md5(subj.encode('utf-8')).hexdigest()[:16]

    # Conteúdo "visível" (sem os headers top-level): single-part html, ou
    # multipart/related (html + wordmark inline) — o related é o que faz o
    # Outlook renderizar o logo no corpo em vez de pendurá-lo como anexo.
    if logo:
        rel = '=_otctracker_related_' + md5
        inner_ct = 'multipart/related; type="text/html"; boundary="' + rel + '"'
        inner_lines = [
            '--' + rel,
            'Content-Type: text/html; charset=utf-8',
            'Content-Transfer-Encoding: 8bit',
            '',
            html,
            '--' + rel,
            'Content-Type: image/png',
            'Content-Transfer-Encoding: base64',
            'Content-ID: <' + _E_LOGO_CID + '>',
            'Content-Disposition: inline; filename="' + os.path.basename(_E_LOGO_FILE) + '"',
            '',
            _b64_wrap(logo),
            '--' + rel + '--',
        ]
    else:
        # No inline image (or the asset is missing) — simple single-part html.
        # The header cell still carries the styled alt text, so a draft built
        # without the logo reads as the old wordmark rather than breaking.
        inner_ct = 'text/html; charset=utf-8'
        inner_lines = None

    if not attachments:
        lines.append('Content-Type: ' + inner_ct)
        if inner_lines is None:
            lines.append('Content-Transfer-Encoding: 8bit')
            return ('\r\n'.join(lines) + '\r\n\r\n' + html).encode('utf-8')
        return ('\r\n'.join(lines) + '\r\n\r\n' + '\r\n'.join(inner_lines) + '\r\n').encode('utf-8')

    # Com anexos (ex.: Ficha de Liquidação em PDF): multipart/mixed envolvendo
    # o conteúdo visível + um part base64 por anexo.
    mixed = '=_otctracker_mixed_' + md5
    lines.append('Content-Type: multipart/mixed; boundary="' + mixed + '"')
    out = ['\r\n'.join(lines), '', '--' + mixed, 'Content-Type: ' + inner_ct]
    if inner_lines is None:
        out.append('Content-Transfer-Encoding: 8bit')
        out.append('')
        out.append(html)
    else:
        out.append('')
        out.extend(inner_lines)
    for a in attachments:
        fn = _safe_filename(a.get('filename') or 'attachment')
        out.append('--' + mixed)
        out.append('Content-Type: ' + (a.get('mime') or 'application/octet-stream') +
                   '; name="' + fn + '"')
        out.append('Content-Transfer-Encoding: base64')
        out.append('Content-Disposition: attachment; filename="' + fn + '"')
        out.append('')
        out.append(_b64_wrap(a['data']))
    out.append('--' + mixed + '--')
    out.append('')
    return '\r\n'.join(out).encode('utf-8')


def build_drafts_download(drafts, sender_email=None, zip_name=None):
    """Package drafts for the browser to download.

    Returns (filename, mimetype, data_bytes). A single draft → one .eml; several
    → a .zip of .eml files (named `zip_name` when given — sanitized, '.zip'
    appended if missing). Returns (None, None, None) when there are no drafts.
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
    if zip_name:
        zname = _safe_filename(zip_name)
        if not zname.lower().endswith('.zip'):
            zname += '.zip'
    else:
        zname = 'otc_email_drafts.zip'
    return zname, 'application/zip', buf.getvalue()


# ──────────────────────────────────────────────────────────────────────────
# OPERATIONS B3 — MENSAGERIA (time do piloto)
# Um e-mail por quebra (Tipo × Contraparte × Tipo Operação) das operações do
# dia com Modalidade de Liquidação Bilateral*/Bruta*. Mesmo shell/assinatura
# dos avisos de NDF de Moeda.
# ──────────────────────────────────────────────────────────────────────────
_MSG_TABLE_HEADERS = ['Participante (Nome Simpl.)', 'Conta', 'Tipo Operação', 'C/V', 'Título',
                      'Tipo Título', 'Valor', 'Sistema', 'Modalidade Liquidação', 'Status',
                      'Contraparte (Nome Simpl.)', 'Conta Contraparte']


def _msg_highlight(text, bg):
    return ('<div style="display:inline-block;background:' + bg + ';padding:5px 12px;'
            'font-size:13.5px;font-weight:700;color:#1d1d1f;font-family:' + _E_FONT + ';">' +
            _esc(text) + '</div>')


def _msg_flow_phrase(total, cpty):
    """'Banco recebe do(a) X R$ v' (total ≥ 0) / 'Banco paga X R$ v'."""
    if total >= 0:
        return 'Banco recebe do(a) {} R$ {}'.format(cpty, _br(abs(total)))
    return 'Banco paga {} R$ {}'.format(cpty, _br(abs(total)))


def opb3_msg_is_swap_venc(tipo_titulo, tipo_operacao):
    """O evento de SWAP é um VENCIMENTO (pagamento de diferencial)?

    Verdade para tudo que é SWAP e não é prêmio — hoje `PAGAMENTO DE DIF.
    AMORTIZACAO` e `PAGAMENTO DE DIF. DE JUROS`, e qualquer diferencial que a B3
    passe a mandar amanhã cai junto sem precisar de manutenção.

    Ela decide DUAS coisas que não podem se separar: o assunto ("Vencimento
    Swap") e o agrupamento (amortização e juros da mesma contraparte saem num
    e-mail só). Se o assunto dissesse "vencimento" e o agrupamento continuasse
    por Tipo Operação, a contraparte receberia dois e-mails com o mesmo assunto e
    valores parciais — e a única forma de isso não acontecer é os dois lados
    lerem esta função. Por isso ela mora aqui e o `routes` a importa, em vez de
    cada lado ter a sua cópia."""
    return (_fcst_norm_local(tipo_titulo).startswith('swap')
            and _fcst_norm_local(tipo_operacao) != 'pagamento de premio')


def build_opb3_mensageria_email(group):
    """One Mensageria draft. `group`:
      tipo, tipo_titulo, tipo_operacao, cpty (nome p/ subject/frases),
      ref_date (dd/mm/yyyy), rows ([[12 células]] na ordem _MSG_TABLE_HEADERS),
      total (float, soma B3 — positivo = Banco recebe),
      internal (float|None — batimento interno; None = sem fonte p/ comparar),
      to, cc.
    """
    tipo_op = str(group.get('tipo_operacao') or '').strip()
    tit = _fcst_norm_local(group.get('tipo_titulo'))
    cpty = group.get('cpty') or '—'
    ref_date = group.get('ref_date') or ''
    total = float(group.get('total') or 0.0)

    tit_label = {'swap': 'Swap', 'ter': 'NDF', 'opc': 'Opção'}.get(tit, group.get('tipo_titulo') or '')
    opn = _fcst_norm_local(tipo_op)
    if opn == 'pagamento de premio':
        base = 'Prêmio ' + tit_label
    elif opb3_msg_is_swap_venc(group.get('tipo_titulo'), tipo_op):
        # O grupo já vem com amortização e juros juntos: nomear o assunto pelo
        # Tipo Operação da primeira linha ("Pagamento De Dif. Amortizacao Swap")
        # descreveria metade do que o e-mail cobra.
        base = 'Vencimento Swap'
    elif opn == 'resgate' and tit == 'ter':
        # Nomenclatura da macro atual: resgate de TER é "Vencimento de Termo"
        base = 'Vencimento de Termo'
    elif opn == 'exercicio opcao':
        # O Tipo Operação da B3 já nomeia o produto; concatenar tit_label sairia
        # "Exercicio Opcao Opção". O arquivo também vem sem acento.
        base = 'Exercício Opção'
    else:
        base = (tipo_op.title() + (' ' + tit_label if tit_label else '')).strip()
    subject = '{} - Liquidação Banco x {} - {}'.format(base, cpty, ref_date)

    intro = (_ep('Bom dia,') +
             _ep('Favor acatar a mensagem abaixo:') +
             _ep('Obrigado(a)!'))

    def _gap(h):
        return '<div style="height:' + str(h) + 'px;line-height:' + str(h) + 'px;font-size:0;">&nbsp;</div>'

    body = _msg_highlight(_msg_flow_phrase(total, cpty), '#fff3a0') + _gap(12)
    body += _email_data_table(_MSG_TABLE_HEADERS, group.get('rows') or [])

    internal = group.get('internal')
    # Comparação ao centavo: qualquer divergência ≥ R$ 0,01 entre a somatória
    # interna (Banco) e a da B3 mostra o "Favor considerar" — o arredondamento
    # só filtra ruído de float abaixo de um centavo.
    if internal is not None and round(abs(float(internal)), 2) != round(abs(total), 2):
        body += _gap(14) + (
            '<span style="font-size:13.5px;color:#333;font-family:' + _E_FONT + ';">Favor considerar:&nbsp;&nbsp;</span>' +
            _msg_highlight(_msg_flow_phrase(float(internal), cpty), '#d9efd9'))

    html = _email_shell('Mensageria de Liquidação', ref_date, intro, body,
                        footer_extra='JPMC Internal Use Only')
    return {
        'subject': subject,
        'html': html,
        'to': group.get('to') or '',
        'cc': group.get('cc') or '',
        'bcc': group.get('bcc') or '',
        'counterparty': cpty,
    }


def _fcst_norm_local(s):
    """Normalização local (minúsculas, sem acento) — espelha routes._fcst_norm sem
    importar de routes (evita import circular)."""
    s = str(s or '').strip().lower()
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


# ──────────────────────────────────────────────────────────────────────────
# Manual Confirmations — reject de MO/FO
# ──────────────────────────────────────────────────────────────────────────
MC_REJECT_TO = 'brazil.otc.ops@jpmorgan.com'


def build_mc_reject_email(row, stage, sid, comment):
    """O aviso de que uma confirmação foi rejeitada e voltou para o OTC.

    O comentário é o conteúdo do e-mail — é ele que diz o que refazer —, por
    isso vai num bloco próprio e não numa linha da tabela de identificação, onde
    um texto de três frases quebraria o alinhamento e seria lido por último.
    """
    ident = [
        ('Trade ID', str(row.get('Trade ID', '') or '')),
        ('Cliente', str(row.get('Cliente', '') or '')),
        ('Produto', str(row.get('Produto', '') or '')),
        ('LOB', str(row.get('LOB', '') or '')),
        ('Data da operação', str(row.get('Data Operação', '') or '')),
        ('Cetip ID', str(row.get('Cetip ID', '') or '')),
    ]
    ident = [(k, v) for k, v in ident if v]

    intro = _ep('A confirmação abaixo foi <b>rejeitada pelo ' + _esc(stage) +
                '</b> e voltou para o status <b>Pending OTC</b>. As validações já '
                'registradas foram limpas, porque o documento será refeito.')
    body = (_email_kv('Confirmação', ident) +
            '<div style="height:14px;line-height:14px;font-size:0;">&nbsp;</div>' +
            _email_notice('<b>Motivo apontado por ' + _esc(sid or '—') + ':</b><br>' +
                          _esc(comment).replace('\n', '<br>')))

    subject = 'Confirmação rejeitada pelo {} — {}{}'.format(
        stage, str(row.get('Cliente', '') or 'Confirmação'),
        ' · ' + str(row.get('Trade ID', '')) if row.get('Trade ID') else '')
    html = _email_shell('Confirmação rejeitada', _today_br(), intro, body,
                        footer_extra='JPMC Internal Use Only')
    return {'subject': subject, 'html': html, 'to': MC_REJECT_TO}


def send_mc_reject_email(row, stage, sid, comment):
    """Envia o aviso pelo relay interno. Retorna True/False — o reject em si já
    foi gravado, então uma falha de SMTP não pode derrubar a chamada: a
    confirmação PRECISA voltar para o OTC mesmo que o e-mail não saia."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.image import MIMEImage

    draft = build_mc_reject_email(row, stage, sid, comment)
    msg = MIMEMultipart('related')
    msg['Subject'] = draft['subject']
    msg['From'] = 'otc.tracker@jpmorgan.com'
    msg['To'] = draft['to']

    alt = MIMEMultipart('alternative')
    alt.attach(MIMEText('Confirmação rejeitada pelo {}. Veja em um cliente HTML.'.format(stage), 'plain'))
    alt.attach(MIMEText(draft['html'], 'html'))
    msg.attach(alt)

    logo = _logo_bytes()
    if logo:
        img = MIMEImage(logo)
        img.add_header('Content-ID', '<' + _E_LOGO_CID + '>')
        img.add_header('Content-Disposition', 'inline', filename=os.path.basename(_E_LOGO_FILE))
        msg.attach(img)

    try:
        with smtplib.SMTP('mailhost.jpmchase.net', 25, timeout=20) as server:
            server.sendmail('otc.tracker@jpmorgan.com', [draft['to']], msg.as_string())
        return True
    except Exception:
        _LOG.warning('[manual-conf] não consegui enviar o aviso de reject')
        return False
