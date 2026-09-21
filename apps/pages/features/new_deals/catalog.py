# -*- coding: utf-8 -*-
"""O CATALOGO das paginas de New Deals que sao UMA tela so.

`pages/new_deals-product.html` e o molde do Swap Bullet (dropzone, import em
dry-run -> duplicatas -> `/cache/batch`, filtro inteligente, modal de edicao)
com o contrato vindo daqui: colunas, selects, defaults do Add Row, o que o
dropzone aceita. Pagina nova e uma ENTRADA aqui, nunca uma copia do template.

So dado puro — sem Flask, sem banco, sem import de camada nenhuma.

A cabeca da grade e FIXA e nao esta nas colunas: Status, LE, LOB, Deal, B3 ID,
Trade Date (as mesmas do Swap Bullet). **A LOB e o que encaixa CEM e EDG na
mesma pagina** (mesa, 21/09/2026): nao existe "Swap CEM" como tela — o swap da
CEM e bullet ou cashflow, e a mesa que o booka vai na coluna.

Tipos de coluna: `text` · `date` · `money` (#,##0.00) · `number` (taxa/percentual:
as casas que tem, mas o filtro inteligente a trata como numero).
"""

# As colunas do SWAP sao as do Swap Bullet (`swap_bullet.domain.SWB_COLUMNS`),
# COPIADAS: feature nao importa feature. Quem prende a paridade e o
# `check_new_deals_catalog.py` — coluna nova no Bullet sem entrar aqui reprova.
_SWAP = (
    ('Type', 'Swap Type', 'text'),
    ('Client', 'Client', 'text'),
    ('ClientDT', 'Client (Deal Ticket)', 'text'),
    ('SPN', 'SPN', 'text'),
    ('ClientAccount', 'Client B3 Account', 'text'),
    ('ClientTaxId', 'Client Tax ID', 'text'),
    ('StartDate', 'Start Date', 'date'),
    ('MaturityDate', 'Maturity Date', 'date'),
    ('Currency', 'Currency', 'text'),
    ('Notional', 'Notional', 'money'),
    ('FXStart', 'FX Start', 'number'),
    ('NotionalFC', 'Notional (Foreign Ccy)', 'money'),
    ('Adhesion', 'Adhesion', 'text'),
    ('Functionality', 'Functionality', 'text'),
    ('PremiumSchedule', 'Premium Schedule', 'text'),
    ('PremiumDate', 'Premium Date', 'date'),
    ('PremiumPayer', 'Premium Payer', 'text'),
    ('PremiumAmount', 'Premium Amount', 'money'),
    ('Reset', 'Reset', 'text'),
    ('NotionalIndex', 'Notional Update Index', 'text'),
    ('NotionalObsDate', 'Notional Observation Date', 'date'),
    ('NotionalDescription', 'Notional Update Description', 'text'),
    ('VcpHolder', 'VCP Holder', 'text'),
    ('VanillaHolder', 'Vanilla Holder', 'text'),
    ('CurveACategory', 'Curve A Category', 'text'),
    ('CurveAPct', 'Curve A Pct', 'number'),
    ('CurveA', 'Curve A', 'text'),
    ('CurveASign', 'Curve A Sign', 'text'),
    ('CurveARate', 'Curve A Rate', 'number'),
    ('CurveACap', 'Curve A Cap', 'number'),
    ('CurveAFloor', 'Curve A Floor', 'number'),
    ('CurveAQuote', 'Curve A Quote', 'text'),
    ('CurveADCC', 'Curve A DCC', 'text'),
    ('CurveACleanCoupon', 'Curve A Clean Coupon', 'text'),
    ('CurveBCategory', 'Curve B Category', 'text'),
    ('CurveBPct', 'Curve B Pct', 'number'),
    ('CurveB', 'Curve B', 'text'),
    ('CurveBSign', 'Curve B Sign', 'text'),
    ('CurveBRate', 'Curve B Rate', 'number'),
    ('CurveBCap', 'Curve B Cap', 'number'),
    ('CurveBFloor', 'Curve B Floor', 'number'),
    ('CurveBQuote', 'Curve B Quote', 'text'),
    ('CurveBDCC', 'Curve B DCC', 'text'),
    ('CurveBCleanCoupon', 'Curve B Clean Coupon', 'text'),
    ('VcpCurve', 'VCP Curve', 'text'),
    ('VcpCode', 'VCP Code', 'text'),
    ('VcpCategory', 'VCP Category', 'text'),
    ('VcpDescription', 'VCP Description', 'text'),
    ('InitialPrice', 'Initial Price', 'text'),
    ('InfoSource', 'Info Source', 'text'),
    ('QuoteDate', 'Quote Date', 'date'),
    ('QuoteDateCode', 'Quote Date D-n', 'text'),
    ('Denomination1', 'Denomination 1', 'text'),
    ('Denomination2', 'Denomination 2', 'text'),
    ('Denomination3', 'Denomination 3', 'text'),
    ('VcpText', 'VCP Text', 'text'),
    ('Observations', 'Observations', 'text'),
)
_MAKER = (('Maker', 'Maker', 'text'), ('Checker', 'Checker', 'text'))

# O que o CASHFLOW tem a mais que o bullet: o cronograma. O tipo de
# amortizacao e cadastro (`swap-amortizacao`), nunca lista no codigo.
_CASHFLOW = (
    ('AmortizationType', 'Amortization', 'text'),
    ('Flows', 'Flows', 'text'),
)

# O CRONOGRAMA do cashflow (a tabela "Cash Flow" do Deal Ticket): uma linha por
# fluxo, editada no modal e guardada na lista `CashFlows` do deal. Na grade ele
# aparece como a CONTAGEM (`Flows`), que por isso não se digita.
_SCHEDULE = (
    ('StartDate', 'Start Date', 'date'),
    ('PaymentDate', 'Payment Date', 'date'),
    ('AmortizationPct', 'Amortization %', 'number'),
    ('BusinessDays', 'Business Days (BD/252)', 'number'),
    ('CalendarDays', 'Calendar Days (Act/360)', 'number'),
    ('FixingDate', 'Fixing Date (SOFR / EURIBOR)', 'date'),
)

# Opcao flexivel sobre EQUITY (a mesa EDG). As colunas sao as da pagina de FXO
# onde o conceito e o mesmo, com a identidade da contraparte do Swap Bullet
# (Client/SPN/conta/documento — e por esses nomes que o lookup da SPN preenche).
_OPT_EDG = (
    ('Client', 'Client', 'text'),
    ('SPN', 'SPN', 'text'),
    ('ClientAccount', 'Client B3 Account', 'text'),
    ('ClientTaxId', 'Client Tax ID', 'text'),
    ('TradeType', 'Trade Type', 'text'),
    ('Underlying', 'Underlying Asset', 'text'),
    ('OptionType', 'Call / Put', 'text'),
    ('Style', 'Style', 'text'),
    ('Direction', 'Direction', 'text'),
    ('Quantity', 'Quantity', 'money'),
    ('Strike', 'Strike', 'number'),
    ('StrikeCurrency', 'Strike Currency', 'text'),
    ('Premium', 'Premium', 'money'),
    ('PremiumPerUnit', 'Premium Per Unit', 'number'),
    ('PremiumCurrency', 'Premium Currency', 'text'),
    ('PremiumDate', 'Premium Date', 'date'),
    ('MaturityDate', 'Maturity Date', 'date'),
    ('SettlementDate', 'Settlement Date', 'date'),
    ('Adhesion', 'Adhesion', 'text'),
)

_SEL_COMUM = {'LE': ['JPM', 'ATACAMA'], 'LOB': ['EDG', 'CEM'],
              'Adhesion': ['CGD', 'CSA', 'CGD/CSA', 'SEM ADESAO']}
_SEL_SWAP = dict(_SEL_COMUM, **{
    'PremiumSchedule': ['Sim', 'Não'], 'Reset': ['Não', 'Sim'],
    'CurveACategory': ['JUROS', 'JUROS INTERNACIONAIS', 'VCP'],
    'CurveBCategory': ['JUROS', 'JUROS INTERNACIONAIS', 'VCP'],
    'CurveASign': ['+', '-'], 'CurveBSign': ['+', '-'], 'Currency': ['BRL', 'USD', 'EUR'],
})


def _page(slug, group, product, columns, **kw):
    nome = (group + ' ' + product).strip()
    p = {
        'path': '/new_deals-' + slug,
        'api': '/api/new-deals/' + slug,
        'slug': 'new_deals-' + slug,
        'name': nome,
        'title': 'New Deals — ' + nome,
        'label': nome,                       # o rotulo `page` das notificacoes (§8)
        'export_name': 'New-Deals-' + nome.replace(' ', '-'),
        'group': group, 'product': product,
        'group_lang': '', 'product_lang': '',
        'columns': [list(c) for c in columns],
        'hidden': [], 'readonly': ['Maker', 'Checker'],
        'selects': {}, 'selects_from_mapping': {}, 'defaults': {},
        'accept': ['xlsx', 'xlsm', 'pdf', 'msg', 'eml', 'htm', 'html'],
        'preview_hint': '', 'send_text': '',
        'schedule': [], 'schedule_field': 'CashFlows',
    }
    p.update(kw)
    return p


PAGES = dict((p['path'], p) for p in (
    _page('swap-cashflow', 'Swap', 'Cashflow', _SWAP + _CASHFLOW + _MAKER,
          group_lang='nav-swap', product_lang='nav-cashflow',
          hidden=['ClientDT', 'ClientTaxId', 'Reset', 'VcpHolder', 'VanillaHolder',
                  'Denomination2', 'Maker', 'Checker'],
          readonly=['Maker', 'Checker', 'Type', 'Flows'],
          schedule=[list(c) for c in _SCHEDULE],
          selects=_SEL_SWAP,
          selects_from_mapping={'AmortizationType': 'swap-amortizacao'},
          defaults={'Type': 'Fluxo de Caixa', 'LE': 'JPM', 'LOB': 'CEM', 'Currency': 'BRL',
                    'Adhesion': 'CGD', 'Functionality': 'N/A', 'PremiumSchedule': 'Não',
                    'Reset': 'Não', 'CurveACategory': 'JUROS', 'CurveAPct': '100.00',
                    'CurveASign': '+', 'CurveARate': '0.0000', 'CurveBCategory': 'JUROS',
                    'CurveBPct': '100.00', 'CurveBSign': '+', 'CurveBRate': '0.0000'},
          preview_hint='Double-click a row to preview the B3 files.',
          send_text='The swap contract and cash flow files are written to Batch Conecta › New.'),
    _page('opt-edg', 'Options', 'EDG', _OPT_EDG + _MAKER,
          group_lang='nav-options', product_lang='nav-edg',
          hidden=['ClientTaxId', 'Maker', 'Checker'],
          selects=dict(_SEL_COMUM, **{
              'OptionType': ['Call', 'Put'], 'Style': ['European', 'American'],
              'Direction': ['Buy', 'Sell'], 'TradeType': ['Vanilla', 'Asian', 'Barrier'],
              'StrikeCurrency': ['BRL', 'USD'], 'PremiumCurrency': ['BRL', 'USD']}),
          defaults={'LE': 'JPM', 'LOB': 'EDG', 'Adhesion': 'CGD', 'TradeType': 'Vanilla',
                    'Style': 'European', 'StrikeCurrency': 'BRL', 'PremiumCurrency': 'BRL'},
          preview_hint='Double-click a row to preview the B3 file.',
          send_text='The option registration file is written to Batch Conecta › New.'),
))


def page(path):
    """A entrada do catalogo para o caminho da PAGINA (`/new_deals-...`)."""
    return PAGES.get('/' + str(path or '').strip('/'))


def page_by_api(sub):
    """A entrada cujo prefixo de API e o primeiro segmento de `sub`."""
    slug = str(sub or '').strip('/').split('/')[0]
    return PAGES.get('/new_deals-' + slug)


def fields(p):
    return [c[0] for c in p['columns']]


def labels(p):
    return [c[1] for c in p['columns']]
