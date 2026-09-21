# -*- coding: utf-8 -*-
"""O CATALOGO das paginas de recompra (unwind) — uma entrada por produto.

A pagina da Fase 1 (`/unwinds/ndf/fx`) tem template e rotas PROPRIOS e nao
passa por aqui. As outras sao a MESMA tela (`pages/unwinds-product.html`) com
outro contrato de colunas, e e este modulo que diz qual: pagina nova e uma
entrada aqui, nao um template novo.

So dado puro — sem Flask, sem banco, sem import de camada nenhuma.

Os nomes de CAMPO que descrevem o mesmo conceito da Fase 1 sao os dela
(`Contract`, `Counterparty`, `OriginalNotional`, `UnwoundBefore`,
`UnwoundNotional`, `Result`, `Direction`, `SettlementDate`...): e por esses
nomes que a Intrag, o Termo de Resilicao e a esteira leem a recompra, e o
produto novo entra pela mesma porta sem de-para. O que muda por produto e o
ROTULO (num termo de mercadoria o "notional" e quantidade).

A chave da linha e o `_id` interno, e nao o id do sistema de origem: NDF/Opcao
de Commodities e FXO chegam SEM identificador, e a operacao se acha por
casamento de caracteristicas contra o Live Position.

Tipos de coluna: `text` · `date` · `money` (#,##0.00) · `rate` (as casas que
tem — taxa nao e valor) · `status` · `check`.
"""

KEY_FIELD = '_id'

_HEAD = (
    ('Status', 'Status', 'status'),
    ('DealID', 'Deal ID', 'text'),
    ('Contract', 'B3 ID', 'text'),
    ('Counterparty', 'Counterparty', 'text'),
    ('TaxID', 'Tax ID', 'text'),
)
_TAIL = (
    ('Direction', 'Direction', 'text'),
    ('UnwindDate', 'Unwind Date', 'date'),
    ('SettlementDate', 'Settlement Date', 'date'),
    ('TradeDate', 'Trade Date', 'date'),
    ('MaturityDate', 'Maturity Date', 'date'),
    ('Check', 'Check', 'check'),
)
_HIDDEN = ('TaxID', 'TradeDate', 'MaturityDate')

# Termo de MOEDA (o mesmo contrato de colunas da Fase 1, sem o Athena ID).
_COLS_TERMO_FX = _HEAD + (
    ('Currency', 'Ccy', 'text'),
    ('OriginalNotional', 'Original Notional', 'money'),
    ('UnwoundBefore', 'Unwound Before', 'money'),
    ('UnwoundNotional', 'Unwound Notional', 'money'),
    ('Strike', 'Strike', 'rate'),
    ('TerminationRate', 'Termination Rate', 'rate'),
    ('PreFWDRate', 'Pre FWD Rate', 'rate'),
    ('DU', 'DU', 'text'),
    ('Result', 'Result', 'money'),
) + _TAIL

# Termo de MERCADORIA: o "notional" e a quantidade, e o preco e na moeda da
# cotacao — o resultado em reais pede a paridade.
_COLS_TERMO_COMM = _HEAD + (
    ('Commodity', 'Commodity', 'text'),
    ('Currency', 'Ccy', 'text'),
    ('OriginalNotional', 'Original Quantity', 'money'),
    ('UnwoundBefore', 'Unwound Before', 'money'),
    ('UnwoundNotional', 'Unwound Quantity', 'money'),
    ('Strike', 'Strike', 'rate'),
    ('TerminationRate', 'Termination Price', 'rate'),
    ('FXRate', 'FX Rate', 'rate'),
    ('PreFWDRate', 'Pre FWD Rate', 'rate'),
    ('DU', 'DU', 'text'),
    ('Result', 'Result', 'money'),
) + _TAIL

# Opcao flexivel — as colunas sao os campos do OPC 0014 (`antecipacao-opcao`):
# quantidade (7), valor base (8), premio unitario (9), valor financeiro (10),
# pagador do premio (14) e, na asiatica, as datas de verificacao (15).
_COLS_OPCAO = _HEAD + (
    ('Underlying', 'Underlying', 'text'),
    ('OptionType', 'Call / Put', 'text'),
    ('Side', 'Position', 'text'),
    ('Strike', 'Strike', 'rate'),
    ('OriginalNotional', 'Original Quantity', 'money'),
    ('UnwoundBefore', 'Unwound Before', 'money'),
    ('UnwoundNotional', 'Unwound Quantity', 'money'),
    ('UnwoundBase', 'Unwound Base Value', 'money'),
    ('UnitPremium', 'Unit Premium', 'rate'),
    ('Result', 'Settlement Amount', 'money'),
    ('PremiumPayer', 'Premium Payer', 'text'),
    ('FixingDates', 'Fixing Dates', 'text'),
) + _TAIL

# Swap — os campos do SWAP 0014 (`swap-antecipacao`): papel (5), fator de cada
# ponta (7/8), valor para antecipacao (11) e mantem premios (12).
_COLS_SWAP = _HEAD + (
    ('LOB', 'LOB', 'text'),
    ('OurCurve', 'Our Curve', 'text'),
    ('CptyCurve', 'Cpty Curve', 'text'),
    ('Role', 'Role', 'text'),
    ('OriginalNotional', 'Original Notional', 'money'),
    ('UnwoundBefore', 'Unwound Before', 'money'),
    ('UnwoundNotional', 'Unwound Notional', 'money'),
    ('FactorLeg1', 'Factor Leg 1', 'rate'),
    ('FactorLeg2', 'Factor Leg 2', 'rate'),
    ('Result', 'Unwind Amount', 'money'),
    ('KeepPremium', 'Keep Premium', 'text'),
) + _TAIL

_COLS_COE = _HEAD + (
    ('Underlying', 'Underlying', 'text'),
    ('OriginalNotional', 'Original Quantity', 'money'),
    ('UnwoundBefore', 'Unwound Before', 'money'),
    ('UnwoundNotional', 'Unwound Quantity', 'money'),
    ('UnitPrice', 'Unit Price', 'rate'),
    ('Result', 'Settlement Amount', 'money'),
) + _TAIL

_B3_TERMO = {'layout': 'antecipacao-termo-multiclasses', 'label': 'TER 0014', 'length': 133}
_B3_OPCAO = {'layout': 'antecipacao-opcao', 'label': 'OPC 0014', 'length': 149}
_B3_SWAP = {'layout': 'swap-antecipacao', 'label': 'SWAP 0014', 'length': 99}


def _page(path, group, product, columns, b3=None, group_lang='', product_lang=''):
    slug = path.strip('/').replace('/', '-')
    nome = (group + ' ' + product).strip()
    return {
        'path': '/unwinds/' + path,
        'api': '/api/unwinds/' + path,
        'slug': 'unwinds-' + slug,
        'title': 'Unwinds — ' + nome,
        'label': 'Unwind ' + nome,          # o rotulo `page` das notificacoes (§8)
        'export_name': 'Unwinds-' + nome.replace(' ', '-'),
        'group': group, 'group_lang': group_lang,
        'product': product, 'product_lang': product_lang,
        'columns': [list(c) for c in columns],
        'hidden': list(_HIDDEN),
        'key': KEY_FIELD,
        'b3': b3,
    }


# Na ORDEM do menu (`partials/sidenav.html`). `ndf/fx` nao esta aqui de
# proposito: e a pagina da Fase 1.
PAGES = dict((p['path'], p) for p in (
    _page('swap/cem', 'Swap', 'CEM', _COLS_SWAP, _B3_SWAP, 'nav-swap'),
    _page('swap/edg', 'Swap', 'EDG', _COLS_SWAP, _B3_SWAP, 'nav-swap', 'nav-edg'),
    _page('ndf/commodities', 'NDF', 'Commodities', _COLS_TERMO_COMM, _B3_TERMO, 'nav-ndf', 'nav-commodities'),
    _page('options/fxo', 'Options', 'FXO', _COLS_OPCAO, _B3_OPCAO, 'nav-options', 'nav-fxo'),
    _page('options/commodities', 'Options', 'Commodities', _COLS_OPCAO, _B3_OPCAO, 'nav-options', 'nav-commodities'),
    _page('options/edg', 'Options', 'EDG', _COLS_OPCAO, _B3_OPCAO, 'nav-options', 'nav-edg'),
    _page('coe', 'COE', '', _COLS_COE, None, 'nav-coe'),
    _page('dce/deliverable-forward', 'DCE', 'Deliverable Forward', _COLS_TERMO_FX, None, 'nav-dce', 'nav-deliverable-forward'),
    _page('dce/ndf', 'DCE', 'NDF', _COLS_TERMO_FX, None, 'nav-dce', 'nav-ndf'),
    _page('dce/option', 'DCE', 'Option', _COLS_OPCAO, None, 'nav-dce'),
    _page('dce/swap', 'DCE', 'Swap', _COLS_SWAP, None, 'nav-dce', 'nav-swap'),
))


def page(path):
    """A entrada do catalogo para `/unwinds/<path>`, ou `None`."""
    return PAGES.get('/unwinds/' + str(path or '').strip('/'))


def fields(p):
    return [c[0] for c in p['columns']]


def labels(p):
    return [c[1] for c in p['columns']]
