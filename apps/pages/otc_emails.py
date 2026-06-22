"""
OTC settlement / confirmation e-mail builders for the New Deals pages.

Ports the legacy CommodiXchange `email_Premio` (premium settlement, D0) and
`email_if` (economic affirmation against Financial Institutions) logic into the
web app. Each builder returns a list of draft dicts; `open_outlook_drafts`
opens them in Outlook for manual review via win32com (Windows/JPM only — it
fails gracefully elsewhere, like the rest of the Outlook-bound features).

Counterparty static data comes from two JSON files under static/data:
  - RefData.json           → B3 ACCOUNT, COUNTERPARTY, TAX ID, SPN by acronym
  - CounterpartyDetails.json → CGD / banking / contacts indexed by SPN

Field mapping (legacy tkinter index → web deal field):
  item[1]  TradeDate          item[2]  Market(+Commodities)   item[3]  Direction
  item[4]  Instrument         item[6]  Strike                 item[9]  TotalNotional
  item[10] SettlementDate     item[15] FXConvDate (fixing FX) item[16] FixingStartDate
  item[17] FixingEndDate      item[18] Acronym                item[19] Premium
  item[22] SpotDate           item[23] Contract
"""

import os
import json
from datetime import datetime

_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'static', 'data'))

JPM_B3_ACCOUNT   = '73760.00-9'           # JPMorgan's own CETIP account
PREMIUM_CLIENT_B3 = '73760.10-2'          # premium "cliente" bucket (Lawton-style internal)
FOOTER_HTML = (
    '<p>Atenciosamente,</p>'
    '<p>Banco J.P. Morgan S.A. | Av. Brigadeiro Faria Lima, 3729 - 15º andar - São Paulo - SP | '
    'T: 55 11 4950 6717 | F: 55 11 4950 3557 |<br>'
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


def _asset_label(deal):
    mkt = str(deal.get('Market', '') or '').strip()
    com = str(deal.get('Commodities', '') or '').strip()
    return '{}({})'.format(mkt, com) if com else mkt


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

        cliente     = [d for d in items if b3 == PREMIUM_CLIENT_B3]
        participante = [d for d in items if b3 != PREMIUM_CLIENT_B3]

        if cliente:
            drafts.append(_premium_cliente_email(cliente, name, spn, taxid, cpd))
        if participante:
            drafts.append(_premium_participante_email(participante, name, b3))

    return drafts


def _premium_apurado(items):
    apurado = sum(_num(d.get('Premium')) * (1 if _is_sell(d.get('Direction')) else -1) for d in items)
    ir = 0.0 if apurado >= 0 else apurado * 0.00005 * -1
    final = apurado + ir if apurado < 0 else apurado
    return apurado, ir, final


def _premium_cliente_email(items, contraparte, spn, taxid, cpd):
    apurado, ir, final = _premium_apurado(items)

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
            contrato=d.get('Contract', ''),
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

    body += '<table style="font-family:Times New Roman;font-size:12pt;border-collapse:collapse;width:auto;">'
    if final < 0:
        cp = cpd.get(spn, {})
        body += (
            '<tr><td>Nome e nº do banco:</td><td style="font-weight:bold;">{bank}</td></tr>'
            '<tr><td>Nº e nome da agência:</td><td style="font-weight:bold;">{ag}</td></tr>'
            '<tr><td>Conta–corrente nº:</td><td style="font-weight:bold;">{cc}</td></tr>'
            '<tr><td>CNPJ/MF nº:</td><td style="font-weight:bold;">{cnpj}</td></tr>'
        ).format(
            bank=cp.get('BANK', '') or '—',
            ag=cp.get('AGENCY', '') or '—',
            cc=cp.get('ACCOUNT', '') or '—',
            cnpj=_fmt_cnpj(taxid),
        )
    else:
        body += (
            '<tr><td>Nome e nº do banco:</td><td style="font-weight:bold;">BANCO JP MORGAN S/A - 376</td></tr>'
            '<tr><td>Nº e nome da agência:</td><td style="font-weight:bold;">0011</td></tr>'
            '<tr><td>Conta–corrente nº:</td><td style="font-weight:bold;">985116003</td></tr>'
            '<tr><td>CNPJ/MF nº:</td><td style="font-weight:bold;">33.172.537/0001-98</td></tr>'
        )
    body += '</table>'

    body += ('<p>A presente Ficha de Liquidação é parte integrante e inseparável do Contrato e/ou da '
             'Confirmação de Operação de Derivativo em referência.</p>')
    body += FOOTER_HTML + '</body></html>'

    return {
        'subject': '(Pagamento de Prêmio) Liquidação de Operação de Derivativo (Commodities) - {} - {}'.format(_today_br(), contraparte),
        'html': body,
        'cc': 'Liquidação',
        'to': '',
    }


def _premium_participante_email(items, contraparte, b3_account):
    apurado, _ir, _final = _premium_apurado(items)

    rows = ''
    for d in items:
        sell = _is_sell(d.get('Direction'))
        resultado = _num(d.get('Premium')) * (1 if sell else -1)
        contrato = d.get('Contract', '') if sell else 'Mnemonico Lançador'
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
    """IF affirmation: TradeDate == today, B3 account != JPM account, not Lawton."""
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
        return b3 != JPM_B3_ACCOUNT and 'LAWTON' not in name and acronym != 'LAWTON'

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
        'cc': 'brazil.otc.ops@jpmorgan.com',
        'to': '',
    }


# ──────────────────────────────────────────────────────────────────────────
# Outlook draft opener (Windows/JPM only)
# ──────────────────────────────────────────────────────────────────────────
def open_outlook_drafts(drafts):
    """Open each draft in Outlook for manual review. Returns (opened, error)."""
    if not drafts:
        return 0, None
    try:
        import win32com.client as _win32
    except Exception:
        return 0, 'win32com não disponível. A geração de e-mails requer Windows com Outlook instalado.'

    opened = 0
    try:
        outlook = _win32.Dispatch('Outlook.Application')
        for d in drafts:
            mail = outlook.CreateItem(0)
            mail.To = d.get('to', '') or ''
            mail.CC = d.get('cc', '') or ''
            mail.Subject = d.get('subject', '')
            mail.HTMLBody = d.get('html', '')
            mail.Display()
            opened += 1
    except Exception as exc:
        return opened, str(exc)
    return opened, None
