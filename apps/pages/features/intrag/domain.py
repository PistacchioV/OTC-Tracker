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
    'strike_price', 'strike_price_brl', 'unit_price',
    'premium_settlement_date', 'base_value_quantity', 'exercise_type',
    'asian_option_average', 'initial_verification_date',
    'final_verification_date', 'information_source', 'quote_for_maturity',
    'quote_for_currency', 'fixing_date', 'remarks', 'premium_holder',
)
# 27 campos, a contagem do extrato. Já foram 28: havia um `premium` entre o
# `unit_price` e o `premium_settlement_date`, e um `bonus` onde o relatório traz
# REMARKS. O extrato NÃO tem coluna PREMIUM — o valor unitário do prêmio é o
# `UNIT PRICE` —, então aquela coluna nascia vazia em toda linha; e o REMARKS
# caía em `unknown_headers` enquanto a tela mostrava um "Bonus" que nunca
# preenchia. Como o casamento é por NOME, nada disso deslocava coluna: eram
# duas células vazias e um dado descartado.


# Cabeçalho do extrato → campo. O casamento é por NOME NORMALIZADO (caixa
# alta, pontuação → espaço), nunca por POSIÇÃO: uma coluna nova no relatório
# desloca tudo num mapa posicional em silêncio; por nome ela só fica de fora,
# contada em `unknown`. 'SETTLEMENT DATE' aparece como sinônimo porque nem todo
# extrato escreve 'PREMIUM SETTLEMENT DATE' por extenso.
#
# Cabeçalho que este mapa não conhece é AVISADO, e é por isso que tirar uma
# entrada daqui é seguro: um extrato que volte a trazer PREMIUM ou BONUS não
# some em silêncio — ele aparece em `unknown_headers` e a tela reclama.
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
    'REMARKS': 'remarks',
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


# ── DCE Swap — as duas tabelas do extrato de swap (características e fluxos) ─
# A página Intrag › DCE › Swap nasce de uma PLANILHA solta no dropzone (o
# NewDealsAndCashflowDetails.xlsx da Athena), não do bob-report. A planilha
# traz DUAS tabelas ligadas pelo Deal Name: a de CARACTERÍSTICAS (uma linha por
# perna — Pay e Rec) e a de FLUXOS (uma linha por cupom de cada perna). O
# arquivo da Intrag é UMA linha por deal, montada do par Pay + Rec — a regra
# é a do script `translate_athena_intrag_swap.py` da mesa, portado VERBATIM
# em `_dce_swap_intrag_fields` (o teste `check_intrag_dce_swap.py` prende a
# linha byte a byte contra a saída daquele script).
#
# Como no DCE Option, o casamento das colunas é por NOME normalizado, nunca
# por posição: coluna nova na planilha não desloca nada, só sai em `unknown`.

_DCE_SWAP_LEG_FIELDS = (
    'deal_name', 'leg_name', 'counterparty', 'spn', 'trading_entity',
    'inst_leg_name', 'direction', 'quantity', 'rates_spread', 'currency',
    'start_date', 'end_date', 'pay_freq', 'initial_exchange', 'final_exchange',
    'dcc', 'acc_adj', 'pay_adj', 'pay_rel_to', 'notional_exch_date_adj',
    'comp_freq', 'comp_meth', 'compounding_formula', 'index_name', 'index_tenor',
    'reset_adj', 'leverage', 'index_start_value', 'index_start_date',
    'index_end_date', 'notional_pay_date', 'roll_convention', 'roll_day',
    'initial_stub_method', 'initial_interp_tenor', 'final_stub_method',
    'final_interp_tenor', 'custom_rt', 'settlement_ccy', 'fx_reset_anchor',
    'fx_fix_date_adj', 'fx_fix_pub',
)

# Rótulos da planilha, na ordem das colunas — o mesmo contrato da tela
# (`DCES_LEG_COLS`) e das `linked_pages.columns` do template do File
# Interpreter. A chave é o campo do JSON-dia.
_DCE_SWAP_LEG_LABELS = (
    'Deal Name', 'Leg Name', 'Counterparty', 'SPN', 'Trading Entity',
    'Inst Leg Name', 'Direction', 'Quantity', 'Rates/Spread', 'Currency',
    'Start Date', 'End Date', 'Pay Freq', 'Initial Exchange', 'Final Exchange',
    'DCC', 'Acc Adj', 'Pay Adj', 'Pay Rel To', 'Notional Exch Date Adj',
    'Comp Freq', 'Comp Meth', 'Compounding Formula', 'Index Name', 'Index Tenor',
    'Reset Adj', 'Leverage', 'Index Start Value', 'Index Start Date',
    'Index End Date', 'Notional Pay Date', 'Roll Convention', 'Roll Day',
    'Initial Stub Method', 'Initial Interp Tenor', 'Final Stub Method',
    'Final Interp Tenor', 'Custom Rt(%)', 'Settlement Ccy', 'FX Reset Anchor',
    'FX Fix Date Adj', 'FX Fix Pub',
)

_DCE_SWAP_FLOW_FIELDS = (
    'deal_name', 'leg_name', 'inst_leg_name', 'coupon', 'settlement_date',
    'accrual_start_date', 'accrual_end_date', 'adj_rate_value', 'spread',
    'dcf_fraction', 'adj_start', 'adj_end', 'notional_absolute', 'notional_pct',
)

_DCE_SWAP_FLOW_LABELS = (
    'Deal Name', 'Leg Name', 'Inst Leg Name', 'Coupon', 'Settlement Date',
    'Accrual Start Date', 'Accrual End Date', '(Adj)RateValue(%)', 'Spread(%)',
    'DCF Fraction', 'Adj Start', 'Adj End', 'Notional(Absolute)', 'Notional(%)',
)

_DCE_SWAP_LEG_HEADER_MAP = {_dce_norm_header(lbl): key
                            for lbl, key in zip(_DCE_SWAP_LEG_LABELS, _DCE_SWAP_LEG_FIELDS)}
_DCE_SWAP_FLOW_HEADER_MAP = {_dce_norm_header(lbl): key
                             for lbl, key in zip(_DCE_SWAP_FLOW_LABELS, _DCE_SWAP_FLOW_FIELDS)}

# O que identifica cada cabeçalho dentro da grade: as duas tabelas começam
# por `Deal Name`, e é a coluna que só uma delas tem que diz qual é.
_DCE_SWAP_LEG_SIGNATURE = ('DEAL NAME', 'DIRECTION')
_DCE_SWAP_FLOW_SIGNATURE = ('DEAL NAME', 'COUPON')


def _dce_swap_header_kind(cells):
    """'legs', 'flows' ou None para uma linha da grade."""
    names = {_dce_norm_header(c) for c in cells}
    if all(s in names for s in _DCE_SWAP_FLOW_SIGNATURE):
        return 'flows'
    if all(s in names for s in _DCE_SWAP_LEG_SIGNATURE):
        return 'legs'
    return None


def _dce_swap_parse_grid(grid):
    """Grade de células (lista de linhas, cada uma lista de textos) →
    (deals, unknown_headers).

    A grade pode ser UMA aba com as duas tabelas (separadas por linha em
    branco ou coladas), ou a concatenação de várias abas — o que decide onde
    cada tabela começa é o CABEÇALHO (`_dce_swap_header_kind`), e as linhas
    seguintes pertencem a ele até a próxima linha-cabeçalho. Linha sem Deal
    Name é ignorada. `deals` é um dict ordenado `deal_name → {'legs': [...],
    'flows': [...]}` na ordem de aparição; cada perna/fluxo é um dict com as
    chaves de `_DCE_SWAP_*_FIELDS` (coluna ausente = '')."""
    deals = {}
    unknown = []
    kind, idx_to_key = None, {}
    for cells in (grid or []):
        cells = ['' if c is None else str(c) for c in cells]
        if not any(c.strip() for c in cells):
            continue
        k = _dce_swap_header_kind(cells)
        if k:
            kind = k
            hmap = _DCE_SWAP_LEG_HEADER_MAP if k == 'legs' else _DCE_SWAP_FLOW_HEADER_MAP
            headers = [_dce_norm_header(c) for c in cells]
            for h in headers:
                if h and h not in hmap and h not in unknown:
                    unknown.append(h)
            idx_to_key = {i: hmap[h] for i, h in enumerate(headers) if h in hmap}
            continue
        if not kind:
            continue
        fields = _DCE_SWAP_LEG_FIELDS if kind == 'legs' else _DCE_SWAP_FLOW_FIELDS
        row = {f: '' for f in fields}
        for i, cell in enumerate(cells):
            key = idx_to_key.get(i)
            if key and not row[key]:
                row[key] = cell.strip()
        deal = row.get('deal_name') or ''
        if not deal:
            continue
        deals.setdefault(deal, {'legs': [], 'flows': []})[kind].append(row)
    return deals, unknown


# ── A linha da Intrag (porte do translate_athena_intrag_swap.py) ────────────
# Comp Meth → índice (pernas fixas viram FIXED).
_DCE_SWAP_COMP_METH_MAP = {
    'StdFixedXccyLeg':   'FIXED',
    'StdFixedXccyLegND': 'FIXED',
    'StdIRSFixedLeg':    'FIXED',
    'IRFixedLeg':        'FIXED',
}

# Os 48 campos do arquivo, na ordem — nomes do layout da Intrag. É o contrato
# com o template `intrag-dce-swap` do File Interpreter (seq 1..48) e com o
# preview de duplo clique da página.
_DCE_SWAP_FILE_FIELDS = (
    'File Code', 'Trade Number', 'Portfolio Code', 'Counterparty Code',
    'Contract Number', 'Trade Date', 'Start Date', 'Maturity Date',
    'Notional Value',
    'Index (Party)', 'Percentage (Party)', 'FX Rate (Party)', 'Rate (Party)',
    'Base (Party)', 'Interest Type (Party)', 'Accrual (Party)', 'Days (Party)',
    'Pay Frequency (Party)', 'Accrual Adjust (Party)', 'Payment Adjust (Party)',
    'Custom Rate (Party)', 'Initial Stub Method (Party)',
    'Initial Interp Tenor (Party)', 'Final Stub Method (Party)',
    'Final Interp Tenor (Party)', 'Observation (Party)',
    'Index (Cpty)', 'Percentage (Cpty)', 'FX Rate (Cpty)', 'Rate (Cpty)',
    'Base (Cpty)', 'Interest Type (Cpty)', 'Accrual (Cpty)', 'Days (Cpty)',
    'Pay Frequency (Cpty)', 'Accrual Adjust (Cpty)', 'Payment Adjust (Cpty)',
    'Custom Rate (Cpty)', 'Initial Stub Method (Cpty)',
    'Initial Interp Tenor (Cpty)', 'Final Stub Method (Cpty)',
    'Final Interp Tenor (Cpty)', 'Observation (Cpty)',
    'Settlement Date', 'Settlement Ccy', 'FX Fixing Date', 'FX Fixing Adjust',
    'FX Fixing Publisher',
)


def _dces_vazio(v):
    return v is None or str(v).strip() == '' or str(v).strip().lower() == 'nan'


def _dces_to_num(v):
    if _dces_vazio(v):
        return None
    s = str(v).strip()
    if ',' in s and '.' not in s:          # padrão BR: 1.166.207,02
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def _dces_fmt_num_br(v, casas=2):
    if v is None:
        return ''
    return (('%.' + str(casas) + 'f') % v).replace('.', ',')


def _dces_fmt_data(v):
    """Data em qualquer forma da planilha → AAAAMMDD ('' quando não parseia)."""
    s = str(v or '').strip()
    if not s:
        return ''
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        return m.group(1) + m.group(2) + m.group(3)
    m = re.match(r'^(\d{2})/(\d{2})/(\d{4})', s)
    if m:
        return m.group(3) + m.group(2) + m.group(1)
    m = re.match(r'^(\d{8})$', s)
    if m:
        return s
    return ''


def _dces_base_from_dcc(dcc):
    """act/360 -> 360 ; 30/360 -> 360"""
    if _dces_vazio(dcc):
        return ''
    return str(dcc).split('/')[-1].strip()


def _dces_stub(v):
    """DefaultRate ou vazio -> '' (campo vazio, sem espaço)."""
    if _dces_vazio(v) or str(v).strip() == 'DefaultRate':
        return ''
    return str(v).strip()


def _dces_custom_rate(v):
    """Custom Rt(%) vazio -> '0'."""
    return '0' if _dces_vazio(v) else str(v).strip()


def _dces_resolve_index(index_name, currency, comp_meth):
    """Índice de uma perna (Rec ou Pay): Index Name vazio → Currency + ' ' +
    Comp Meth, com as pernas fixas mapeadas para FIXED."""
    if _dces_vazio(index_name):
        comp = _DCE_SWAP_COMP_METH_MAP.get(str(comp_meth).strip(), str(comp_meth).strip())
        return (str(currency).strip() + ' ' + comp)
    return str(index_name).strip()


def _dces_g(row, key):
    v = (row or {}).get(key)
    return '' if _dces_vazio(v) else str(v).strip()


def _dces_pay_ou_rec(pay, rec, key, default=''):
    """Pega da Pay; se vazio, olha na Rec; se ambos vazios, usa default."""
    vp = _dces_g(pay, key)
    if vp:
        return vp
    vr = _dces_g(rec, key)
    if vr:
        return vr
    return default


def _dce_swap_legs(entry):
    """(pay, rec) de um deal — a primeira perna de cada direção. Falta uma
    → ValueError dizendo qual (o script da mesa PULAVA o deal com aviso; na
    tela o deal fica, e é o preview/send que reclama)."""
    pay = rec = None
    for leg in (entry or {}).get('legs') or []:
        d = str(leg.get('direction') or '').strip().lower()
        if d == 'pay' and pay is None:
            pay = leg
        elif d in ('rec', 'receive', 'recv') and rec is None:
            rec = leg
    if pay is None or rec is None:
        faltam = [n for n, l in (('Pay', pay), ('Rec', rec)) if l is None]
        raise ValueError('leg missing: ' + ' and '.join(faltam))
    return pay, rec


def _dce_swap_intrag_fields(entry, trade_date_yyyymmdd=''):
    """Os 48 campos da linha da Intrag para UM deal (par Pay + Rec).

    Porte campo a campo do `montar_operacao` do script da mesa — inclusive as
    excentricidades (o Base da perna Pay lê o DCC da REC "conforme template";
    o Notional sai com o sinal da Quantity da Pay). Quem quiser mudar a regra
    muda aqui E no teste, que compara com a saída do script."""
    pay, rec = _dce_swap_legs(entry)
    qtd_pay = _dces_to_num(_dces_g(pay, 'quantity'))
    qtd_rec = _dces_to_num(_dces_g(rec, 'quantity'))
    fx_rate = ''
    if qtd_pay not in (None, 0) and qtd_rec is not None:
        fx_rate = _dces_fmt_num_br(qtd_rec / qtd_pay, 6)      # 12: calculado
    td = trade_date_yyyymmdd or _dces_fmt_data((entry or {}).get('trade_date'))

    campos = [
        '13',                                           # 1  File Code (fixo)
        '0',                                            # 2  Trade Number (fixo)
        'GCCN',                                         # 3  Portfolio Code (fixo)
        'JPM',                                          # 4  Counterparty Code (fixo)
        _dces_g(pay, 'deal_name'),                      # 5  Contract Number
        td,                                             # 6  Trade Date
        _dces_fmt_data(_dces_g(pay, 'start_date')),     # 7  Start Date (Pay)
        _dces_fmt_data(_dces_g(pay, 'end_date')),       # 8  Maturity Date (Pay)
        _dces_fmt_num_br(qtd_pay, 2),                   # 9  Notional Value (Pay)
        # --- Leg 1 (Party) = Rec leg ---
        _dces_resolve_index(_dces_g(rec, 'index_name'), _dces_g(rec, 'currency'),
                            _dces_g(rec, 'comp_meth')), # 10 Index (Rec)
        '100',                                          # 11 Percentage (fixo)
        fx_rate,                                        # 12 FX Rate = Qtd Rec / Qtd Pay
        _dces_g(rec, 'rates_spread'),                   # 13 Rate (Rec)
        _dces_base_from_dcc(_dces_g(rec, 'dcc')),       # 14 Base (Rec)
        'E',                                            # 15 Interest Type (fixo)
        'E',                                            # 16 Accrual (fixo)
        'C',                                            # 17 Days (fixo)
        _dces_g(rec, 'pay_freq'),                       # 18 Pay Frequency (Rec)
        _dces_g(rec, 'acc_adj'),                        # 19 Accrual Adjust (Rec)
        _dces_g(rec, 'pay_adj'),                        # 20 Payment Adjust (Rec)
        _dces_custom_rate(_dces_g(rec, 'custom_rt')),   # 21 Custom Rate (Rec) vazio->0
        _dces_stub(_dces_g(rec, 'initial_stub_method')),  # 22
        _dces_g(rec, 'initial_interp_tenor'),           # 23
        _dces_stub(_dces_g(rec, 'final_stub_method')),  # 24
        _dces_g(rec, 'final_interp_tenor'),             # 25
        '',                                             # 26 Observation
        # --- Leg 2 (Counterparty) = Pay leg ---
        _dces_resolve_index(_dces_g(pay, 'index_name'), _dces_g(pay, 'currency'),
                            _dces_g(pay, 'comp_meth')), # 27 Index (Pay)
        '100',                                          # 28 Percentage (fixo)
        '',                                             # 29 FX Rate (vazio)
        _dces_g(pay, 'rates_spread'),                   # 30 Rate (Pay)
        _dces_base_from_dcc(_dces_g(rec, 'dcc')),       # 31 Base (Rec, conforme template)
        'E',                                            # 32 Interest Type (fixo)
        'E',                                            # 33 Accrual (fixo)
        'C',                                            # 34 Days (fixo)
        _dces_g(pay, 'pay_freq'),                       # 35 Pay Frequency (Pay)
        _dces_g(pay, 'acc_adj'),                        # 36 Accrual Adjust (Pay)
        _dces_g(pay, 'pay_adj'),                        # 37 Payment Adjust (Pay)
        _dces_custom_rate(_dces_g(pay, 'custom_rt')),   # 38 Custom Rate (Pay) vazio->0
        _dces_stub(_dces_g(pay, 'initial_stub_method')),  # 39
        _dces_g(pay, 'initial_interp_tenor'),           # 40
        _dces_stub(_dces_g(pay, 'final_stub_method')),  # 41
        _dces_g(pay, 'final_interp_tenor'),             # 42
        '',                                             # 43 Observation
        # --- Settlement ---
        _dces_fmt_data(_dces_g(pay, 'end_date')),                        # 44 Settlement Date (Pay)
        _dces_pay_ou_rec(pay, rec, 'settlement_ccy', default='DSW'),     # 45 Settl. Ccy
        _dces_pay_ou_rec(pay, rec, 'fx_reset_anchor'),                   # 46 FX Fixing Date
        _dces_pay_ou_rec(pay, rec, 'fx_fix_date_adj'),                   # 47 FX Fixing Adjust
        _dces_pay_ou_rec(pay, rec, 'fx_fix_pub'),                        # 48 FX Fixing Publisher
    ]
    # .strip() em todos → vazios saem como '' (sem espaço), como no script.
    return [str(c).strip() for c in campos]


def _dce_swap_apply_fixed(fields, tpl_fields):
    """Os literais `Fixed` do template do File Interpreter vencem o gerador
    (a regra da casa: editar um Fixed pela tela muda o arquivo sem código).
    `tpl_fields` são dicts com `seq`/`source`/`source_detail`; seq fora de
    1..48 é ignorado."""
    out = list(fields)
    for f in (tpl_fields or []):
        if str((f or {}).get('source', '') or '').strip().lower() != 'fixed':
            continue
        try:
            i = int(str(f.get('seq', '')).strip()) - 1
        except ValueError:
            continue
        if 0 <= i < len(out):
            out[i] = str(f.get('source_detail', '') or '').strip()
    return out
