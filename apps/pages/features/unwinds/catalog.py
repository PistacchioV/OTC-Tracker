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

import re

KEY_FIELD = '_id'

# A chave NATURAL da recompra — o upsert do re-import e a pergunta das
# duplicatas: o contrato na B3 e a data da antecipacao (o mesmo contrato antecipa
# mais de uma vez, em dias diferentes). Sem contrato (FXO e NDF/Opcao de
# Commodities chegam sem identificador) vale o Deal ID do sistema de origem; sem
# nenhum dos dois a linha e sempre NOVA — nao ha o que casar.
NATURAL_KEY = (('Contract', 'UnwindDate'), ('DealID', 'UnwindDate'))

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


# De onde sai a POSICAO que completa a linha (o Live Position do produto). `None`
# e produto sem posicao na B3 lida aqui (COE, DCE): a linha vale pelo que a
# planilha trouxe.
POS_SWAP, POS_OPCAO, POS_NDF = 'swap', 'option', 'ndf'

# As conferencias do veredito de TRES estados (`product/domain.conferir`):
#   `balance` — o recomprado cabe no saldo (original − ja recomprado);
#   `termo`   — o resultado refeito pela formula do termo (a mesma da Fase 1);
#   `premio`  — o valor financeiro = quantidade x premio (ou preco) unitario.
# OK so sai quando TODAS rodaram e fecharam; uma que nao rodou e '-'.
_CK_SWAP = ('balance',)
_CK_TERMO = ('balance', 'termo')
_CK_PREMIO = ('balance', 'premio')

# E-MAIL de recompra destes produtos: o aviso do Athena que a Fase 1 le (`BRL
# NDF Unwind Notification`) e o UNICO formato que esta casa conhece, e nenhum
# dos onze tem amostra. O import de .msg/.eml responde
# `unwind_email_format_pending` em vez de adivinhar um parser; so a PLANILHA
# (rotulos ou campos das colunas abaixo) entra.


def _page(path, group, product, columns, b3=None, group_lang='', product_lang='',
          position=None, checks=_CK_SWAP):
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
        # A pasta do arquivo-dia sob `cache/unwinds/`: os dois niveis que o New
        # Deals Monitor le como produto (§454, pkey `Unwind/<dir>`) e que o
        # painel le como rotulo — `Unwind <grupo> <produto>`, o mesmo `label`.
        'dir': '/'.join(x for x in (group, product) if x),
        'suffix': '_unwind' + re.sub(r'[^a-z0-9]', '', nome.lower()) + '.json',
        'position': position,
        'checks': list(checks),
        'backend': True,
    }


# Na ORDEM do menu (`partials/sidenav.html`). `ndf/fx` nao esta aqui de
# proposito: e a pagina da Fase 1.
PAGES = dict((p['path'], p) for p in (
    _page('swap/cem', 'Swap', 'CEM', _COLS_SWAP, _B3_SWAP, 'nav-swap',
          position=POS_SWAP, checks=_CK_SWAP),
    _page('swap/edg', 'Swap', 'EDG', _COLS_SWAP, _B3_SWAP, 'nav-swap', 'nav-edg',
          position=POS_SWAP, checks=_CK_SWAP),
    _page('ndf/commodities', 'NDF', 'Commodities', _COLS_TERMO_COMM, _B3_TERMO, 'nav-ndf',
          'nav-commodities', position=POS_NDF, checks=_CK_TERMO),
    _page('options/fxo', 'Options', 'FXO', _COLS_OPCAO, _B3_OPCAO, 'nav-options', 'nav-fxo',
          position=POS_OPCAO, checks=_CK_PREMIO),
    _page('options/commodities', 'Options', 'Commodities', _COLS_OPCAO, _B3_OPCAO, 'nav-options',
          'nav-commodities', position=POS_OPCAO, checks=_CK_PREMIO),
    _page('options/edg', 'Options', 'EDG', _COLS_OPCAO, _B3_OPCAO, 'nav-options', 'nav-edg',
          position=POS_OPCAO, checks=_CK_PREMIO),
    _page('coe', 'COE', '', _COLS_COE, None, 'nav-coe', checks=_CK_PREMIO),
    _page('dce/deliverable-forward', 'DCE', 'Deliverable Forward', _COLS_TERMO_FX, None, 'nav-dce',
          'nav-deliverable-forward', checks=_CK_TERMO),
    _page('dce/ndf', 'DCE', 'NDF', _COLS_TERMO_FX, None, 'nav-dce', 'nav-ndf', checks=_CK_TERMO),
    _page('dce/option', 'DCE', 'Option', _COLS_OPCAO, None, 'nav-dce', checks=_CK_PREMIO),
    _page('dce/swap', 'DCE', 'Swap', _COLS_SWAP, None, 'nav-dce', 'nav-swap', checks=_CK_SWAP),
))


def page(path):
    """A entrada do catalogo para `/unwinds/<path>`, ou `None`."""
    return PAGES.get('/unwinds/' + str(path or '').strip('/'))


def page_and_action(sub):
    """`'options/fxo/import-file'` -> (pagina, 'import-file'); `'coe'` -> (pagina, '').

    A API das onze paginas e UMA regra (`/api/unwinds/<path:sub>`), e o caminho
    do produto tem UM ou DOIS segmentos (`coe` x `swap/cem`): quem separa o
    produto da acao e o catalogo, pelo prefixo mais longo que ele conhece."""
    partes = [x for x in str(sub or '').strip('/').split('/') if x]
    for n in range(min(len(partes), 2), 0, -1):
        p = page('/'.join(partes[:n]))
        if p is not None:
            return p, '/'.join(partes[n:])
    return None, ''


def column_kinds(p):
    """{campo: tipo} das colunas da pagina."""
    return dict((c[0], c[2]) for c in p['columns'])


def fields(p):
    return [c[0] for c in p['columns']]


def labels(p):
    return [c[1] for c in p['columns']]
