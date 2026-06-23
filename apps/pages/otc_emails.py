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
# Data loading / lookups
# ──────────────────────────────────────────────────────────────────────────
def _load_json(name):
    try:
        with open(os.path.join(_DATA_DIR, name), encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return []


def _build_refdata_index():
    """acronym (COMMODITIES ACCRONYM) → ref record."""
    idx = {}
    for r in _load_json('RefData.json'):
        acc = str(r.get('COMMODITIES ACCRONYM', '') or '').strip().upper()
        if acc and acc not in idx:
            idx[acc] = r
    return idx


def _build_cpdetails_index():
    """SPN → counterparty banking/contact record."""
    idx = {}
    for c in _load_json('CounterpartyDetails.json'):
        spn = str(c.get('SPN', '') or '').strip().upper()
        if spn:
            idx[spn] = c
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
def build_premium_emails(deals):
    """D0 premium settlement notice.

    Eligible counterparties: CETIP account (RefData) == 73760.10-2 AND not Lawton,
    restricted to deals whose SpotDate (premium payment date) is today.
    """
    ref = _build_refdata_index()
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

        drafts.append(_premium_cliente_email(items, name, spn, taxid, cpd))

    return drafts


def _premium_apurado(items):
    apurado = sum(_num(d.get('Premium')) * (1 if _is_sell(d.get('Direction')) else -1) for d in items)
    ir = 0.0 if apurado >= 0 else apurado * 0.00005 * -1
    final = apurado + ir if apurado < 0 else apurado
    return apurado, ir, final


def _premium_cliente_email(items, contraparte, spn, taxid, cpd):
    apurado, ir, final = _premium_apurado(items)
    cp = cpd.get(spn, {})
    to_emails = '; '.join(_contacts_emails(cp, _SETTLEMENT_KEYWORDS))

    rows = ''
    for d in items:
        resultado = _num(d.get('Premium')) * (1 if _is_sell(d.get('Direction')) else -1)
        rows += (
            '<tr style="border:1px solid black;">'
            '<td style="border:1px solid black;">{contrato}</td>'
            '<td style="border:1px solid black;">{op}</td>'
            '<td style="border:1px solid black;">{venc}</td>'
            '<td style="border:1px solid black;">{ativo}</td>'
            '<td style="border:1px solid black;">{base}</td>'
            '<td style="border:1px solid black;">{res}</td>'
            '</tr>'
        ).format(
            contrato=d.get('Deal', ''),
            op=_date_br(d.get('TradeDate')),
            venc=_date_br(d.get('SettlementDate')),
            ativo=_asset_label(d),
            base=_br(abs(_num(d.get('TotalNotional')))),
            res=_br_currency(resultado),
        )

    body = (
        '<html><body style="font-family:\'Times New Roman\';font-size:12pt;">'
        '<p>Prezados Senhores,</p>'
        '<p>Vimos confirmar a(s) liquidação(ões) da(s) operação(ões) de derivativos abaixo especificada(s):</p>'
        '<table style="font-family:\'Arial\';font-size:10pt;border-collapse:collapse;width:auto;border:1px solid black;text-align:center;">'
        '<tr style="font-weight:bold;border:1px solid black;">'
        '<td style="border:1px solid black;">Contrato</td>'
        '<td style="border:1px solid black;">Data Operação</td>'
        '<td style="border:1px solid black;">Data Vencimento</td>'
        '<td style="border:1px solid black;">Moeda/Ativo</td>'
        '<td style="border:1px solid black;">Valor Base/Quantidade</td>'
        '<td style="border:1px solid black;">Resultado Final</td>'
        '</tr>' + rows + '</table><br>'
    )

    body += (
        '<table style="font-family:\'Times New Roman\';font-size:12pt;border-collapse:collapse;width:auto;">'
        '<tr><td style="font-weight:bold;">Resultado Apurado:</td><td style="font-weight:bold;">R$ {ap}</td></tr>'
        '<tr><td style="font-weight:bold;">IR (0,005%):</td><td style="font-weight:bold;">R$ {ir}</td></tr>'
        '<tr><td style="font-weight:bold;">Resultado Final:</td><td style="font-weight:bold;">R$ {fi}</td></tr>'
        '</table>'
    ).format(ap=_br_currency(apurado), ir=_br(ir), fi=_br_currency(final))

    if final < 0:
        body += ('<p>Conforme entendimentos mantidos, informamos que providenciaremos nesta data a '
                 'transferência financeira do montante correspondente ao Resultado Final Apurado em vosso favor, '
                 'conforme os dados a seguir, transmitidos por meio da Autorização Permanente para Liquidação '
                 'Financeira e/ou confirmados por ligação telefônica:</p>')
    elif final > 0:
        body += ('<p>Sendo assim, informamos que debitaremos os valores descritos acima da conta corrente do '
                 'Cliente junto ao Banco J.P.Morgan S.A., mediante confirmação de saldo e nos moldes da '
                 'autorização de débito encaminhada pelos Srs. Caso não tenham encaminhado autorização de débito, '
                 'solicitamos que o montante correspondente ao Resultado Final Apurado acima seja transferido em '
                 'favor do Banco J.P Morgan S.A. nesta data, conforme os dados a seguir:</p>')

    # Blank line between the apurado/IR/final values block and the banking block.
    body += '<br><table style="font-family:Times New Roman;font-size:12pt;border-collapse:collapse;width:auto;">'
    if final < 0:
        # JPM is paying the counterparty → use the PAY banking details.
        bank_name, agency, account = _first_bank(cp, 'PAY')
        body += (
            '<tr><td style="font-weight:bold;">Nome e nº do banco:</td><td style="font-weight:bold;">{bank}</td></tr>'
            '<tr><td style="font-weight:bold;">Nº e nome da agência:</td><td style="font-weight:bold;">{ag}</td></tr>'
            '<tr><td style="font-weight:bold;">Conta–corrente nº:</td><td style="font-weight:bold;">{cc}</td></tr>'
            '<tr><td style="font-weight:bold;">CNPJ/MF nº:</td><td style="font-weight:bold;">{cnpj}</td></tr>'
        ).format(
            bank=bank_name or '—',
            ag=agency or '—',
            cc=account or '—',
            cnpj=_fmt_cnpj(taxid),
        )
    else:
        body += (
            '<tr><td style="font-weight:bold;">Nome e nº do banco:</td><td style="font-weight:bold;">BANCO JP MORGAN S/A - 376</td></tr>'
            '<tr><td style="font-weight:bold;">Nº e nome da agência:</td><td style="font-weight:bold;">0011</td></tr>'
            '<tr><td style="font-weight:bold;">Conta–corrente nº:</td><td style="font-weight:bold;">5116003</td></tr>'
            '<tr><td style="font-weight:bold;">CNPJ/MF nº:</td><td style="font-weight:bold;">33.172.537/0001-98</td></tr>'
        )
    body += '</table>'

    body += ('<p>A presente Ficha de Liquidação é parte integrante e inseparável do Contrato e/ou da '
             'Confirmação de Operação de Derivativo em referência.</p>')
    body += FOOTER_HTML + '</body></html>'

    return {
        'subject': '(Pagamento de Prêmio) Liquidação de Operação de Derivativo (Commodities) - {} - {}'.format(_today_br(), contraparte),
        'html': body,
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
    rows = ''
    for d in items:
        fix_ini = _date_br(d.get('FixingStartDate'))
        fix_fim = _date_br(d.get('FixingEndDate'))
        rows += (
            '<tr style="border:1px solid black;">'
            '<td style="border:1px solid black;">{contrato}</td>'
            '<td style="border:1px solid black;">{pos}</td>'
            '<td style="border:1px solid black;">{op}</td>'
            '<td style="border:1px solid black;">{base}</td>'
            '<td style="border:1px solid black;">{strike}</td>'
            '<td style="border:1px solid black;">{ativo}</td>'
            '<td style="border:1px solid black;">{fini}</td>'
            '<td style="border:1px solid black;">{ffim}</td>'
            '<td style="border:1px solid black;">{fccy}</td>'
            '<td style="border:1px solid black;">{venc}</td>'
            '</tr>'
        ).format(
            contrato=d.get('Deal', ''),
            pos='Vendedor' if _is_sell(d.get('Direction')) else 'Comprador',
            op=_date_br(d.get('TradeDate')),
            base=_br(abs(_num(d.get('TotalNotional'))), 0),
            strike=_br_currency(abs(_num(d.get('Strike'))), 4),
            ativo=_asset_label(d),
            fini=fix_ini if fix_ini != fix_fim else 'N/A',
            ffim=fix_fim,
            fccy=_date_br(d.get('FXConvDate')),
            venc=_date_br(d.get('SettlementDate')),
        )

    body = (
        '<html><body style="font-family:\'Calibri\';font-size:11pt;">'
        '<p>Prezados Senhores,</p>'
        '<p>Por gentileza, poderiam confirmar os dados da(s) operação(ões) abaixo?</p>'
        '<p>Conta CETIP {cp}: {b3}</p>'
        '<p>Conta CETIP BANCO JP MORGAN S.A: {jpm}</p>'
        '<table style="font-family:\'Arial\';font-size:10pt;border-collapse:collapse;width:auto;border:1px solid black;text-align:center;">'
        '<tr style="font-weight:bold;border:1px solid black;">'
        '<td style="border:1px solid black;">Contrato</td>'
        '<td style="border:1px solid black;">Posição JPMorgan</td>'
        '<td style="border:1px solid black;">Data Operação</td>'
        '<td style="border:1px solid black;">Valor Base/Quantidade</td>'
        '<td style="border:1px solid black;">Taxa Forward</td>'
        '<td style="border:1px solid black;">Moeda/Ativo</td>'
        '<td style="border:1px solid black;">Inicio Fixing Mercadoria</td>'
        '<td style="border:1px solid black;">Final Fixing Mercadoria</td>'
        '<td style="border:1px solid black;">Fixing Moeda</td>'
        '<td style="border:1px solid black;">Data Vencimento</td>'
        '</tr>'
    ).format(cp=contraparte, b3=b3_account, jpm=JPM_B3_ACCOUNT) + rows + '</table><br>'

    body += FOOTER_HTML + '</body></html>'

    return {
        'subject': 'Confirmação da(s) Operação(ões) Fechada(s) em {} - {} - {}'.format(_today_br(), contraparte, asset_label),
        'html': body,
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
    'liquidacao':        'BRSP_Settlement_Ops; brsp_financial_control; brazil_otc_settlements@jpmorgan.com; joao.hira@jpmorgan.com; latam.mumbai.acc@jpmorgan.com',
    'brazil comm sales': 'Brazil_Comm_Sales',
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
    out = []
    for ch in str(s or ''):
        out.append(ch if (ch.isalnum() or ch in ' -_().[]') else '_')
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
