# -*- coding: utf-8 -*-
"""As regras puras do Intrag — as duas contas do par intragrupo (JPM × Lawton),
o nome do participante de cada lado e a chave de casamento do retorno da B3.

Puro: nada aqui importa `routes`, Flask ou disco.
"""
import re


# Os delimitadores que chegam no Publisher do deal (`PTAX|BRR|PTAX`,
# `PTAX BRR[PTAX`): o cadastro publisher-ndf separa os match tokens por `|`,
# e o texto cru ainda pode trazer colchete/chave/parêntese. No arquivo e na
# tela o publisher sai com ESPAÇO ("PTAX BRR PTAX") — nunca com o separador
# do cadastro.
_INFO_SOURCE_SEPARADORES = re.compile(r'[|\[\]{}()<>;\\]+')


def _intrag_info_source(text):
    """Information Source legível: todo separador vira espaço, espaços
    repetidos colapsam. Valor que não é texto volta como veio."""
    if not isinstance(text, str):
        return text
    return re.sub(r'\s+', ' ', _INFO_SOURCE_SEPARADORES.sub(' ', text)).strip()


_INTRAG_OPT_JPM_ACC    = '73760.00-9'


_INTRAG_OPT_LAWTON_ACC = '00041.00-7'


_INTRAG_OPT_JPM_NAME    = 'BANCO J.P MORGAN S.A'


_INTRAG_OPT_LAWTON_NAME = 'LAWTON MULTIMERCADO-FI'


def _intrag_opt_name_for(acc):
    if acc == _INTRAG_OPT_JPM_ACC:
        return _INTRAG_OPT_JPM_NAME
    if acc == _INTRAG_OPT_LAWTON_ACC:
        return _INTRAG_OPT_LAWTON_NAME
    return ''


def _intrag_b3_key(v):
    """B3 ID match key — stripped, leading zeros dropped (both sides)."""
    s = str(v or '').strip()
    return s.lstrip('0') or s


# ── DCE Option — o extrato ITAUDataExtract de FX Option do bob-reports ───────
# As 28 colunas da grade e do arquivo gerado, NA ORDEM da tela. A chave é o
# nome do campo no JSON-dia; o rótulo mora no template da página (e a lista
# do template tem de ficar nesta ordem — é o contrato entre as duas pontas).
_DCE_OPT_FIELDS = (
    'option_type', 'trade_id', 'portfolio_code', 'trade_date', 'operation_type',
    'holder_writer_party', 'holder_writer_counterparty', 'counterparty',
    'base_currency', 'commodity', 'quoted_currency', 'maturity_date',
    'strike_price', 'strike_price_brl', 'unit_price', 'premium',
    'premium_settlement_date', 'base_value_quantity', 'exercise_type',
    'asian_option_average', 'initial_verification_date',
    'final_verification_date', 'information_source', 'quote_for_maturity',
    'quote_for_currency', 'fixing_date', 'bonus', 'premium_holder',
)


# Cabeçalho do extrato → campo. O casamento é por NOME NORMALIZADO (caixa
# alta, pontuação → espaço), nunca por POSIÇÃO: uma coluna nova no relatório
# desloca tudo num mapa posicional em silêncio; por nome ela só fica de fora,
# contada em `unknown`. 'SETTLEMENT DATE' aparece como sinônimo porque o
# cabeçalho real pode trazer o prêmio e a data como colunas separadas.
_DCE_OPT_HEADER_MAP = {
    'OPTION TYPE': 'option_type',
    'TRADE ID': 'trade_id',
    'PORTFOLIO CODE': 'portfolio_code',
    'TRADE DATE': 'trade_date',
    'OPERATION TYPE': 'operation_type',
    'HOLDER OR WRITER PARTY': 'holder_writer_party',
    'HOLDER OR WRITER COUNTERPARTY': 'holder_writer_counterparty',
    'COUNTERPARTY': 'counterparty',
    'BASE CURRENCY STOCKS INDEX': 'base_currency',
    'BASE CURRENCY': 'base_currency',
    'COMMODITY': 'commodity',
    'QUOTED CURRENCY': 'quoted_currency',
    'MATURITY DATE': 'maturity_date',
    'STRIKE PRICE': 'strike_price',
    'STRIKE PRICE IN BRL': 'strike_price_brl',
    'UNIT PRICE': 'unit_price',
    'PREMIUM': 'premium',
    'PREMIUM SETTLEMENT DATE': 'premium_settlement_date',
    'SETTLEMENT DATE': 'premium_settlement_date',
    'BASE VALUE QUANTITY': 'base_value_quantity',
    'EXERCISE TYPE': 'exercise_type',
    'ASIAN OPTION AVERAGE': 'asian_option_average',
    'INITIAL VERIFICATION DATE': 'initial_verification_date',
    'FINAL VERIFICATION DATE': 'final_verification_date',
    'INFORMATION SOURCE': 'information_source',
    'QUOTE FOR MATURITY': 'quote_for_maturity',
    'QUOTE FOR CURRENCY': 'quote_for_currency',
    'FIXING DATE': 'fixing_date',
    'BONUS': 'bonus',
    'PREMIUM HOLDER': 'premium_holder',
}


def _dce_norm_header(name):
    """Nome de coluna do extrato na forma canônica: caixa alta, tudo que não é
    letra/dígito vira espaço, espaços colapsam."""
    s = re.sub(r'[^A-Z0-9]+', ' ', str(name or '').upper())
    return re.sub(r'\s+', ' ', s).strip()


def _dce_parse_report(text):
    """Linhas do extrato DCE de FX Option → (rows, unknown_headers).

    A primeira linha é o CABEÇALHO e é ela que dá o significado de cada
    posição; o separador é detectado nela (`;` do extrato ITAU, `|` de outros
    bob-reports). Cada linha vira um dict com as chaves de `_DCE_OPT_FIELDS`
    (coluna ausente = ''); cabeçalho que o mapa não conhece volta em
    `unknown_headers`, para o chamador AVISAR em vez de descartar calado.
    """
    lines = [ln for ln in str(text or '').splitlines() if ln.strip()]
    if not lines:
        return [], []
    header_line = lines[0]
    sep = ';' if header_line.count(';') >= header_line.count('|') else '|'
    headers = [_dce_norm_header(h) for h in header_line.split(sep)]
    unknown = [h for h in headers if h and h not in _DCE_OPT_HEADER_MAP]
    idx_to_key = {i: _DCE_OPT_HEADER_MAP[h]
                  for i, h in enumerate(headers) if h in _DCE_OPT_HEADER_MAP}
    rows = []
    for ln in lines[1:]:
        cells = ln.split(sep)
        row = {k: '' for k in _DCE_OPT_FIELDS}
        for i, cell in enumerate(cells):
            k = idx_to_key.get(i)
            if k and not row[k]:
                row[k] = cell.strip()
        if any(row.values()):
            rows.append(row)
    return rows, unknown
