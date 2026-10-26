# -*- coding: utf-8 -*-
"""As regras PURAS da página New Deals › Swap › Cashflow.

O swap de FLUXO NÃO CONSTANTE — é onde mora o swap da CEM (mesa, 21/09/2026:
não existe página "Swap CEM"; bullet e cashflow são formato de contrato, e a
coluna LOB encaixa CEM e EDG na mesma tela). O Deal Ticket é o MESMO do Swap
Bullet, lido pela horizontal `platform/swap_deal_ticket.py`; o que o cashflow
tem a mais mora aqui:

* a tabela **Cash Flow** do Deal Ticket — o cronograma, que vira a lista
  `CashFlows` do deal (`SCHEDULE_FIELDS`, as colunas `_SCHEDULE` do
  catálogo). **Não há amostra de DT de cashflow da CEM no repositório**: o
  formato da tabela é SUPOSIÇÃO, e ela está inteira em `_CF_HEADERS` /
  `_cf_field_of` (quais cabeçalhos a tabela usa) e em `_CEM_LABELS` (os
  rótulos que o DT da CEM traz e o da EDG não). Chegou a planilha da mesa, é
  ali que se ajusta;
* o **Registro de Contrato Fluxo Não Constante** (código 0301, layout 00003,
  seção 4.2.7 do manual — template `swap-fluxo-nao-constante-v3`, 2021
  caracteres). As regras das pernas são as do 0301 de Pagamento Final do
  Bullet (só a JUROS leva Sinal/Juros; só a VCP leva PU 1.00000000,
  Tipo/Classe, Cupom Limpo e Data de Cotação; a Denominação só na VCP da
  PARTE), em POSIÇÕES diferentes: o layout não tem funcionalidade nem
  terceira curva, e o prêmio vai só no 0897;
* o **Registro de Fluxo de Contrato Não Constante** (código 0034, seção
  4.2.8 — template `swap-fluxo-contrato-nao-constante`): o cronograma, uma
  linha por evento, com o Tipo de Amortização do cadastro `swap-amortizacao`.

Sem Flask, sem arquivo, sem rede, sem `routes`: as linhas dos cadastros
chegam por argumento.
"""
import re

from apps.pages.platform import swap_deal_ticket as dtk

# ── Colunas da página ────────────────────────────────────────────────────────
# As do Bullet (a horizontal), mais o tipo de amortização e a CONTAGEM de
# fluxos, antes de Maker/Checker — é o contrato do catálogo
# (`new_deals/catalog.py`, que não se importa daqui: feature não importa
# feature). O `check_swap_cashflow.py` prende a paridade.
SWC_COLUMNS = tuple(c for c in dtk.SWB_COLUMNS if c[0] not in ('Maker', 'Checker')) + (
    ('AmortizationType', 'Amortization'),
    ('Flows', 'Flows'),
    ('Maker', 'Maker'),
    ('Checker', 'Checker'),
)
SWC_FIELDS = tuple(k for k, _ in SWC_COLUMNS)
SWC_LABELS = tuple(lbl for _, lbl in SWC_COLUMNS)
SWC_DATE_FIELDS = dtk.SWB_DATE_FIELDS

# O cronograma: uma linha por fluxo, na lista `CashFlows` do deal.
SCHEDULE_FIELD = 'CashFlows'
SCHEDULE_FIELDS = ('StartDate', 'PaymentDate', 'AmortizationPct', 'BusinessDays', 'CalendarDays',
                   'FixingDate')
SCHEDULE_DATE_FIELDS = ('StartDate', 'PaymentDate', 'FixingDate')
MAX_FLOWS = 360                     # manual 4.2.8: "permitido até 360 fluxos"

STATUS_SENDABLE = dtk.STATUS_SENDABLE
ID_PREFIX = 'SWC-'

CONTRACT_RECORD_LENGTH = 2021       # a última posição do layout 4.2.7 v00003
FLOW_HEADER_LENGTH = 38
FLOW_REGISTRO_LENGTH = 62
FLOW_LINE_LENGTH = 194


# ── A tabela Cash Flow do Deal Ticket (SUPOSIÇÃO) ────────────────────────────
# Cabeçalho normalizado (`dtk.norm`) → campo do cronograma. É a ÚNICA coisa
# que diz como a tabela chega; não há DT de cashflow da CEM no repositório, e
# estes são os nomes das colunas da tela (`_SCHEDULE` do catálogo) em inglês e
# em português, com as variantes de planilha mais comuns. Cabeçalho novo é
# uma linha aqui.
_CF_HEADERS = {
    'StartDate': ('STARTDATE', 'START', 'DATAINICIO', 'DATADEINICIO', 'INICIO', 'INICIODOPERIODO',
                  'INICIOPERIODO', 'DATAINICIAL', 'ACCRUALSTART', 'ACCRUALSTARTDATE'),
    'PaymentDate': ('PAYMENTDATE', 'PAYMENT', 'PAYDATE', 'DATAPAGAMENTO', 'DATADEPAGAMENTO',
                    'PAGAMENTO', 'DATAFIM', 'DATAFINAL', 'FIM', 'FIMDOPERIODO', 'DATALIQUIDACAO',
                    'DATADELIQUIDACAO', 'LIQUIDACAO', 'DATAEVENTO', 'DATADOEVENTO', 'ENDDATE',
                    'ACCRUALEND', 'ACCRUALENDDATE'),
    'AmortizationPct': ('AMORTIZATION', 'AMORTIZATIONPCT', 'AMORTIZACAO', 'AMORTIZACAOPCT',
                        'PCTAMORTIZACAO', 'TAXAAMORTIZACAO', 'TAXADEAMORTIZACAO', 'AMORT',
                        'PERCENTUALAMORTIZACAO', 'PERCENTUALDEAMORTIZACAO', 'AMORTIZACAOPERCENTUAL'),
    'BusinessDays': ('BUSINESSDAYS', 'BUSINESSDAYSBD252', 'BD', 'BD252', 'DU', 'DU252', 'DIASUTEIS',
                     'DIASUTEIS252'),
    'CalendarDays': ('CALENDARDAYS', 'CALENDARDAYSACT360', 'CD', 'DC', 'ACT360', 'DIASCORRIDOS',
                     'DIASCORRIDOS360'),
    'FixingDate': ('FIXINGDATE', 'FIXINGDATESOFREURIBOR', 'FIXING', 'DATAFIXING', 'DATADEFIXING',
                   'DATADOFIXING', 'DATAFIXACAO', 'DATADEFIXACAO'),
}
_CF_ALIAS = dict((a, f) for f, aliases in _CF_HEADERS.items() for a in aliases)
# O TÍTULO do bloco (opcional): sai da grade junto com a tabela.
_CF_TITLES = {'CASHFLOW', 'CASHFLOWS', 'FLUXODECAIXA', 'FLUXOSDECAIXA', 'CRONOGRAMA',
              'CRONOGRAMADEFLUXOS', 'CRONOGRAMADEPAGAMENTOS', 'TABELADEFLUXOS', 'FLUXOS'}


def _cf_field_of(cell):
    """O campo do cronograma que o cabeçalho `cell` nomeia, ou None. Exato
    primeiro; depois o prefixo mais longo com 5+ letras ('Amortização (%)
    s/ VB' → AmortizationPct). É a regra da SUPOSIÇÃO acima."""
    n = dtk.norm(cell)
    if not n:
        return None
    if n in _CF_ALIAS:
        return _CF_ALIAS[n]
    best = None
    for alias, f in _CF_ALIAS.items():
        if len(alias) >= 5 and n.startswith(alias) and (best is None or len(alias) > len(best[0])):
            best = (alias, f)
    return best[1] if best else None


def _is_date_cell(v):
    return bool(str(v or '').strip()) and dtk.parse_date(v) is not None and \
        re.search(r'\d', str(v or '')) is not None


def _flow_value(field, raw):
    """O valor de UMA célula do cronograma como o deal o guarda: data em ISO,
    percentual com até 5 casas (a taxa de amortização vai com cinco no 0034),
    dias como inteiro."""
    s = str(raw or '').strip()
    if not s:
        return ''
    if field in SCHEDULE_DATE_FIELDS:
        return dtk.iso(dtk.parse_date(s))
    v = dtk.parse_number(s)
    if v is None:
        return ''
    if field == 'AmortizationPct':
        return ('%.5f' % v).rstrip('0').rstrip('.') or '0'
    return str(int(round(v)))


def normalize_flow(fl):
    """Uma linha do cronograma vinda da TELA ou do DT → só as chaves do
    cronograma, cada uma no formato do deal. Linha inteira em branco → None."""
    out = {}
    for f in SCHEDULE_FIELDS:
        out[f] = _flow_value(f, (fl or {}).get(f, ''))
    return out if any(out.values()) else None


def normalize_schedule(flows):
    out = []
    for fl in flows or []:
        if isinstance(fl, dict):
            n = normalize_flow(fl)
            if n:
                out.append(n)
    return out


def split_cashflow_grid(grid):
    """(grade SEM a tabela, [fluxos]) — acha a tabela Cash Flow numa aba do
    DT. O cabeçalho é a linha com DOIS ou mais cabeçalhos conhecidos
    (`_cf_field_of`), NENHUMA data e com uma data de fluxo na linha seguinte
    — é o que a separa de uma linha do topo do DT como 'Inicio | 15/09 |
    Vencimento | 07/06', onde os rótulos também seriam cabeçalhos. As linhas
    de dados vão até a primeira sem data nenhuma nas colunas da tabela. A
    tabela (e o título logo acima, se houver) sai da grade devolvida só nas
    COLUNAS dela, para o parser do Deal Ticket não ler cabeçalho de fluxo
    como rótulo — e o que estiver ao lado segue lá."""
    rows = [list(r) for r in (grid or [])]
    for ri, row in enumerate(rows):
        cols = {}
        for ci, cell in enumerate(row):
            f = _cf_field_of(cell)
            if f and f not in cols.values():
                cols[ci] = f
        if len(cols) < 2 or any(_is_date_cell(c) for c in row):
            continue
        date_cols = [ci for ci, f in cols.items() if f in ('PaymentDate', 'StartDate')]
        if not date_cols or ri + 1 >= len(rows):
            continue
        nxt = rows[ri + 1]
        if not any(ci < len(nxt) and _is_date_cell(nxt[ci]) for ci in date_cols):
            continue
        flows, fim = [], ri + 1
        for rj in range(ri + 1, len(rows)):
            r = rows[rj]
            if not any(ci < len(r) and _is_date_cell(r[ci]) for ci in date_cols):
                break
            fl = normalize_flow(dict((f, r[ci] if ci < len(r) else '') for ci, f in cols.items()))
            if fl:
                flows.append(fl)
            fim = rj + 1
        lo, hi = min(cols), max(cols)
        apagar = list(range(ri, fim))
        if ri > 0 and any(dtk.norm(c) in _CF_TITLES for c in rows[ri - 1]):
            apagar.insert(0, ri - 1)
        for rk in apagar:
            for ci in range(lo, min(hi + 1, len(rows[rk]))):
                rows[rk][ci] = ''
            if rk == ri - 1:
                rows[rk] = ['' if dtk.norm(c) in _CF_TITLES else c for c in rows[rk]]
        return rows, flows
    return rows, []


def _cf_headers_in_line(line):
    """Os campos do cronograma cujos cabeçalhos aparecem na linha, na ORDEM
    em que aparecem — o alias mais longo primeiro, sem sobreposição e só
    como palavra inteira ('DC' não casa dentro de 'DCC')."""
    ocupado, achados = [], []
    for alias in sorted(_CF_ALIAS, key=len, reverse=True):
        f = _CF_ALIAS[alias]
        if f in [x[1] for x in achados]:
            continue
        rx = re.compile(r'(?<![A-Za-z0-9])' + dtk._label_regex(alias) + r'(?![A-Za-z])', re.I)
        for m in rx.finditer(line):
            if any(a < m.end() and m.start() < b for a, b in ocupado):
                continue
            ocupado.append((m.start(), m.end()))
            achados.append((m.start(), f))
            break
    return [f for _p, f in sorted(achados)]


_DATE_TOKEN = re.compile(r'\b(\d{1,2}[/.\-][A-Za-z]{3}[A-Za-z]*[/.\-]\d{2,4}|\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}'
                         r'|\d{4}-\d{2}-\d{2})\b')
_NUM_TOKEN = re.compile(r'[-+]?\d[\d.,]*%?')


def split_cashflow_text(text):
    """(texto SEM a tabela, [fluxos]) — a tabela Cash Flow num DT em PDF. O
    texto vem sem coluna, então a ORDEM dos cabeçalhos na linha de cabeçalho
    diz a ordem dos valores: as datas de cada linha vão, na ordem, para os
    cabeçalhos de data; os números, para os numéricos. SUPOSIÇÃO como a da
    grade (sem amostra); sem linha de cabeçalho reconhecível, nenhum fluxo."""
    lines = str(text or '').replace('\r', '\n').split('\n')
    cabecalhos, inicio = [], 0
    for li, line in enumerate(lines):
        if _DATE_TOKEN.search(line):
            continue
        achados = _cf_headers_in_line(line)
        if len(achados) >= 2:
            cabecalhos, inicio = achados, li
            break
    if not cabecalhos:
        return text, []
    datas_f = [f for f in cabecalhos if f in SCHEDULE_DATE_FIELDS]
    nums_f = [f for f in cabecalhos if f not in SCHEDULE_DATE_FIELDS]
    flows, fim = [], inicio + 1
    for lj in range(inicio + 1, len(lines)):
        line = lines[lj]
        datas = _DATE_TOKEN.findall(line)
        if not datas:
            if line.strip():
                break
            continue
        resto = _DATE_TOKEN.sub(' ', line)
        nums = _NUM_TOKEN.findall(resto)
        fl = {}
        for f, v in zip(datas_f, datas):
            fl[f] = v
        for f, v in zip(nums_f, nums):
            fl[f] = v
        fl = normalize_flow(fl)
        if fl:
            flows.append(fl)
        fim = lj + 1
    ini = inicio - 1 if inicio > 0 and dtk.norm(lines[inicio - 1]) in _CF_TITLES else inicio
    return '\n'.join(lines[:ini] + lines[fim:]), flows


# ── O que o DT da CEM traz e o da EDG não (SUPOSIÇÃO) ────────────────────────
# Rótulo normalizado → campo do deal. Os do topo saem direto; os de PERNA
# ('leg') saem pelo bloco (Curva VCP / Curva Vanilla) e depois para a Curva A
# ou B pela MESMA regra do `deal_from_raw` (quem é "ativo" na curva). O
# catálogo já tinha as colunas (FXStart, NotionalFC, Cotação/DCC/Cupom Limpo
# por curva, Atualização de Notional, Observations) — faltava quem as lesse.
_CEM_LABELS = {
    'PARIDADEINICIAL': ('top', 'FXStart'), 'TAXADECAMBIOINICIAL': ('top', 'FXStart'),
    'CAMBIOINICIAL': ('top', 'FXStart'), 'FXSTART': ('top', 'FXStart'), 'PTAXINICIAL': ('top', 'FXStart'),
    'VALORBASEME': ('top', 'NotionalFC'), 'VALORBASEMOEDAESTRANGEIRA': ('top', 'NotionalFC'),
    'NOTIONALFC': ('top', 'NotionalFC'), 'VALORBASEUSD': ('top', 'NotionalFC'),
    'TIPODEAMORTIZACAO': ('top', 'AmortizationType'), 'TIPOAMORTIZACAO': ('top', 'AmortizationType'),
    'AMORTIZACAO': ('top', 'AmortizationType'),
    'INDICEDEATUALIZACAODONOTIONAL': ('top', 'NotionalIndex'), 'INDICEATUALIZACAO': ('top', 'NotionalIndex'),
    'DATADEOBSERVACAO': ('top', 'NotionalObsDate'), 'DATAOBSERVACAO': ('top', 'NotionalObsDate'),
    'DESCRICAODAATUALIZACAO': ('top', 'NotionalDescription'),
    'OBSERVACOES': ('top', 'Observations'), 'OBSERVACAO': ('top', 'Observations'),
    'LOB': ('top', 'LOB'), 'MESA': ('top', 'LOB'),
    'COTACAO': ('leg', 'Quote'), 'DCC': ('leg', 'DCC'), 'BASE': ('leg', 'DCC'),
    'CONVENCAODECONTAGEM': ('leg', 'DCC'), 'CUPOMLIMPO': ('leg', 'CleanCoupon'),
}


def cem_extras_grid(grid):
    """Os campos de `_CEM_LABELS` numa aba do DT: {campo: texto} para o topo
    e {'vcp_<X>'/'vanilla_<X>': texto} para as pernas, pelo bloco cuja
    coluna de cabeçalho é a mais próxima à esquerda (a regra do parser da
    horizontal). Valor = as células à direita do rótulo."""
    out = {}
    header_cols = {}
    rows = [list(r) for r in (grid or [])]
    for row in rows:
        for ci, cell in enumerate(row):
            n = dtk.norm(cell)
            if n in ('CURVAVANILLA',) or (n == 'CURVAVCP' and not dtk._value_right(row, ci)):
                header_cols[ci] = dtk._DT_BLOCK_HEADERS[n]
    for row in rows:
        for ci, cell in enumerate(row):
            lab = _CEM_LABELS.get(dtk.norm(cell))
            if not lab:
                continue
            bloco, chave = lab
            v = dtk._value_right(row, ci)
            if not v:
                continue
            if bloco == 'leg':
                perna = dtk._nearest_block(header_cols, ci)
                if perna in ('vcp', 'vanilla'):
                    out.setdefault(perna + '_' + chave, v)
            else:
                out.setdefault(chave, v)
    return out


def cem_extras_text(text):
    """Os campos do TOPO de `_CEM_LABELS` num DT em PDF, linha a linha
    ('Paridade Inicial 5,4321'); os de perna não se separam sem coluna e
    ficam para a mesa."""
    out = {}
    for line in str(text or '').split('\n'):
        for lab_norm, (bloco, chave) in _CEM_LABELS.items():
            if bloco != 'top' or chave in out:
                continue
            m = re.match(r'^\s*' + dtk._label_regex(lab_norm) + r'\s*:?\s*(\S.*)$', line, re.I)
            if m:
                out[chave] = m.group(1).strip()
    return out


def apply_cem_extras(deal, raw, extras):
    """Põe no deal o que `cem_extras_*` leu, só onde o deal está em branco. A
    perna vai para a Curva A ou B pela mesma pergunta do `deal_from_raw`: o
    Banco é o 'Ativo VCP' → A = VCP."""
    vcp_holder = str(raw.get('VcpHolder') or '')
    van_holder = str(raw.get('VanillaHolder') or '')
    a_is_vcp = dtk._is_ours(vcp_holder) and not dtk._is_ours(van_holder)
    lado = {'vcp': 'A' if a_is_vcp else 'B', 'vanilla': 'B' if a_is_vcp else 'A'}
    for k, v in (extras or {}).items():
        v = str(v or '').strip()
        if not v:
            continue
        if k.startswith(('vcp_', 'vanilla_')):
            perna, chave = k.split('_', 1)
            campo = 'Curve' + lado[perna] + chave
        else:
            campo = k
        if campo == 'FXStart':
            n = dtk.parse_number(v)
            v = '' if n is None else (('%.8f' % n).rstrip('0').rstrip('.'))
        elif campo == 'NotionalFC':
            n = dtk.parse_number(v)
            v = '' if n is None else ('%.2f' % n)
        elif campo == 'LOB':
            v = dtk.norm(v) if dtk.norm(v) in ('CEM', 'EDG') else ''
        elif campo == 'NotionalObsDate':
            v = dtk.iso(dtk.parse_date(v))
        if v and not str(deal.get(campo) or '').strip():
            deal[campo] = v
    return deal


# ── Do DT ao deal ────────────────────────────────────────────────────────────

def deal_from_raw(raw, flows, trade_date_iso, extras=None):
    """O deal do cashflow: o do Bullet (`swap_deal_ticket.deal_from_raw`, o
    MESMO parser), com o tipo `Fluxo de Caixa`, a chave `SWC-…`, o
    cronograma e o que o DT da CEM traz a mais."""
    deal = dtk.deal_from_raw(raw, trade_date_iso)
    deal['Type'] = 'Fluxo de Caixa'
    # A LOB NÃO é chutada: o `deal_from_raw` da horizontal escreve EDG (é o
    # Deal Ticket do Bullet), e aqui mora o swap da CEM. Sem o DT dizer, fica
    # em branco e é lacuna — o Monitor mostra `Swap/Cashflow/No LOB` em vez de
    # somar na mesa errada (§517).
    deal['LOB'] = ''
    deal[SCHEDULE_FIELD] = normalize_schedule(flows)
    deal['Flows'] = str(len(deal[SCHEDULE_FIELD]))
    deal.setdefault('AmortizationType', '')
    apply_cem_extras(deal, raw, extras or {})
    deal['_id'] = make_deal_id(deal)
    return deal


# ── Do Trade Recap (corpo do e-mail) ao deal (§555) ─────────────────────────

def recap_parts(section):
    """Uma seção do recap (`swap_deal_ticket.parse_trade_recap`) → (raw,
    flows, extras) na MESMA forma do Deal Ticket, para o deal nascer pelo
    `deal_from_raw` de sempre.

    Quem é Parte A: a NOSSA perna é a que o banco RECEBE — a que o cliente
    PAGA ('Vibra Pays CDI + 0.15%'). Valor base = o notional em BRL (a B3
    registra em reais); o da moeda vai em Notional (Foreign Ccy) e a paridade
    em FX Start. Amortização 'At maturity' põe 100% no último fluxo."""
    f = section.get('fields') or {}
    pa, pb = f.get('PartyA', ''), f.get('PartyB', '')
    # `Party B: Boticario … (CNPJ: 11.137.051/0001-86)` (§697): o nome sem o
    # parêntese; o CNPJ identifica a contraparte quando o e-mail não traz SPN.
    pb = re.sub(r'\s*\(\s*CNPJ\b.*$', '', pb, flags=re.I).strip() or pb
    pa = re.sub(r'\s*\(\s*CNPJ\b.*$', '', pa, flags=re.I).strip() or pa
    nosso, cliente = (pa, pb) if dtk._is_ours(pa) or not dtk._is_ours(pb) else (pb, pa)
    legs = section.get('legs') or []

    def banco_recebe(leg):
        return (leg['dir'] == 'PAY') != dtk._is_ours(leg['who'])

    rec = next((lg for lg in legs if banco_recebe(lg)), None)
    pag = next((lg for lg in legs if lg is not rec), None)
    a, b = dtk.recap_leg(rec['text'] if rec else ''), dtk.recap_leg(pag['text'] if pag else '')
    brl = next((v for ccy, v in section.get('notionals') or [] if ccy == 'BRL'), None)
    fc = next(((ccy, v) for ccy, v in section.get('notionals') or [] if ccy != 'BRL'), None)
    # O FX de BOOKING (`FX: 5.40 (just to booking)`, §697) faz o Valor Base:
    # FX × o notional na moeda (equipe, 26/10/2026) — a linha "BRL Notional" do
    # e-mail é a mesma conta, e quando o Initial FX é uma fixação futura
    # (`PTAX-V 06-Nov-2026`) ele é o único número que existe hoje.
    fx_book = _numero_solto(f.get('FX'))
    if fx_book is not None and fc:
        brl = round(fx_book * fc[1], 2)
    notional = brl if brl is not None else (fc[1] if fc else None)
    ini, fim = dtk.recap_date(f.get('Effective')), dtk.recap_date(f.get('Maturity'))
    raw = {
        '_title': section.get('title', ''),
        'Client': cliente or section.get('client', ''),
        'SPN': section.get('spn', ''),
        'StartDate': dtk.iso(ini) if ini else '',
        'MaturityDate': dtk.iso(fim) if fim else '',
        'Notional': '' if notional is None else ('BRL %.2f' % notional if brl is not None
                                                 else '%s %.2f' % (fc[0], notional)),
        # O banco "segura" a perna que recebe: é o que o `deal_from_raw` lê
        # para pôr essa perna na Curva A.
        'VanillaHolder': nosso or 'Banco J.P.Morgan',
        'VcpHolder': cliente,
        'PremiumSchedule': 'Não',
    }
    for pref, leg in (('vanilla_', a), ('vcp_', b)):
        raw[pref + 'Curve'] = leg['curve']
        raw[pref + 'Category'] = '-'     # quem diz é o cadastro, no `enrich`
        raw[pref + 'Pct'] = leg['pct']
        raw[pref + 'Sign'] = leg['sign']
        raw[pref + 'Rate'] = leg['rate']
    amort = f.get('Amortization', '')
    no_venc = 'MATURITY' in dtk.norm(amort) or 'VENCIMENTO' in dtk.norm(amort)
    pares = section.get('flows') or []
    # A coluna Amortization da tabela (quando o e-mail a traz) vence a regra
    # do "At maturity".
    pct_tab = section.get('flow_amort') or {}

    def _amort(k):
        if k in pct_tab and pct_tab[k] is not None:
            return ('%.5f' % pct_tab[k]).rstrip('0').rstrip('.')
        return ('100' if k == len(pares) - 1 else '0') if no_venc else ''
    flows = [{'StartDate': dtk.iso(i), 'PaymentDate': dtk.iso(p), 'AmortizationPct': _amort(k)}
             for k, (i, p) in enumerate(pares)]
    extras = {'vanilla_DCC': a['dcc'], 'vcp_DCC': b['dcc'], 'AmortizationType': amort,
              'Adhesion': f.get('Agreement', '')}
    if fc:
        extras['NotionalFC'] = '%.2f' % fc[1]
    fx = _numero_solto(f.get('InitialFX'))
    if fx_book is not None:
        extras['FXStart'] = str(fx_book)
    elif fx is not None:
        extras['FXStart'] = str(fx)
    # `Initial FX: PTAX-V 06-Nov-2026` não é número: é a ATUALIZAÇÃO DE
    # NOTIONAL — o Valor Base em reais será corrigido pela PTAX daquele dia
    # (o contrato a termo dos campos 19-24/99 do 0301, §697).
    if fx is None and f.get('InitialFX'):
        obs = dtk.recap_date(f.get('InitialFX'))
        if obs:
            indice = _RECAP_DATE_ANY.split(str(f.get('InitialFX')))[0].strip(' :-')
            extras['NotionalIndex'] = indice or str(f.get('InitialFX')).strip()
            extras['NotionalObsDate'] = dtk.iso(obs)
    # A perna de fórmula (`(6M TERM SFR + 0.60%)* 1.17647`) vai como VCP, com
    # o texto do e-mail na Denominação (sem acento e sem a sigla VCP, como a
    # macro da mesa).
    formula = next((leg.get('formula') for leg in (a, b) if leg.get('formula')), '')
    if formula:
        extras['VcpText'] = re.sub(r'\bVCP\b', '', dtk.strip_accents(formula)).strip()
    # `Fixings: PTAX-Ask T-1` → a Data de Cotação D-1 da perna VCP.
    mfix = re.search(r'\b[TD]\s*-\s*(\d)\b', str(f.get('Fixings') or ''), re.I)
    if mfix and int(mfix.group(1)) <= 5:
        extras['QuoteDateCode'] = '%02d' % int(mfix.group(1))
    return raw, flows, extras


_RECAP_DATE_ANY = re.compile(r'\b\d{1,2}[-/ ](?:[A-Za-z]{3,9}|\d{1,2})[-/ ]\d{2,4}\b')


def _numero_solto(v):
    """O número quando o campo É um número (`5.40`, `[5.1150]`,
    `5.40 ( just to booking)`) — `PTAX-V 06-Nov-2026` não é."""
    m = re.match(r'^\s*\[?\s*(\d[\d.,]*)\s*\]?\s*(?:\(.*\))?\s*$', str(v or ''))
    return dtk.parse_number(m.group(1)) if m else None


def deal_from_recap(section, trade_date_iso):
    """A seção Onshore Swap do recap → o deal do cashflow. As categorias das
    pernas nascem em BRANCO: o `enrich` as tira dos cadastros (curva → código
    B3 → categoria no Swap Index); sem cadastro, lacuna `swc_no_category`."""
    raw, flows, extras = recap_parts(section)
    adesao = extras.pop('Adhesion', '')
    vcp_text = extras.pop('VcpText', '')
    quote = extras.pop('QuoteDateCode', '')
    deal = deal_from_raw(raw, flows, trade_date_iso, extras)
    cnpj = dtk.recap_cnpj((section.get('fields') or {}).get('PartyB'))
    if cnpj and not str(deal.get('ClientTaxId') or '').strip():
        deal['ClientTaxId'] = cnpj          # o `enrich` acha a contraparte por ele (§697)
    for side, pref in (('A', 'vanilla_'), ('B', 'vcp_')):
        cat = raw[pref + 'Category']
        deal['Curve' + side + 'Category'] = '' if cat == '-' else cat
    if 'VCP' not in (deal['CurveACategory'], deal['CurveBCategory']):
        deal['VcpCurve'] = ''
        deal['VcpText'] = ''
    # Depois da limpeza acima: a categoria da perna de fórmula ainda está em
    # branco (sai do cadastro no `enrich`, C00 → VCP), e o texto dela é o do
    # e-mail. O `enrich` o apaga se a perna não virar VCP.
    if vcp_text:
        deal['VcpText'] = vcp_text
    if quote:
        deal['QuoteDateCode'] = quote
    if adesao:
        deal['Adhesion'] = adesao.strip().upper()
    deal['Source'] = 'Trade Recap'
    return deal


def make_deal_id(deal):
    return dtk.make_deal_id(deal, prefix=ID_PREFIX)


def amortization_label(rows, text):
    """O LABEL do cadastro `swap-amortizacao` que casa com `text` (a grafia
    do cadastro é a que o select da tela mostra); sem casamento, o texto
    como veio — e a lacuna diz que não há código."""
    t = str(text or '').strip()
    if not t:
        return ''
    alvo = dtk.norm(t)
    toks = dtk._tokens(t)
    for r in rows or []:
        lab = str(r.get('LABEL') or '').strip()
        if lab and (dtk.norm(lab) == alvo or (dtk._tokens(lab) and dtk._tokens(lab) == toks)):
            return lab
    return t


def amortization_code(rows, text):
    """O código B3 (9(02)) do tipo de amortização pelo cadastro; '' = lacuna."""
    return dtk.code_by_label(rows, text)


# ── O registro 0301 de Fluxo Não Constante (layout 00003) ────────────────────

def _blank(n):
    return ' ' * n


def contract_header_values(participant, today_ymd):
    return {'1': 'SWAP ', '2': '0', '3': '0301', '4': str(participant or '').ljust(20)[:20],
            '5': today_ymd, '6': '00003'}


def fx_clean_coupon(deal, side):
    """A cotação inicial da perna de moeda: o Clean Coupon da curva, ou o FX
    Start do deal (o `Initial FX` do recap). → número ou None."""
    v = dtk.parse_number(deal.get('Curve%sCleanCoupon' % side))
    return v if v is not None else dtk.parse_number(deal.get('FXStart'))


def fx_quote_code(deal, side):
    """A Data de Cotação da perna de moeda, no código do layout (00 = D0 …
    05 = D-5), lida da coluna `Curve X Quote` ('D-1', '1', '01'). Fora de 0-5 →
    ''. O recap NÃO a diz: em branco é lacuna, nunca um D-1 presumido."""
    s = str(deal.get('Curve%sQuote' % side) or '').strip().upper().replace(' ', '')
    m = re.fullmatch(r'D?-?0?(\d)', s)
    if not m or int(m.group(1)) > 5:
        return ''
    return '%02d' % int(m.group(1))


# ── O contrato a TERMO (FWD Start com Atualização de Notional, §697) ──────────
# O swap pactuado hoje cujo Valor Base em reais só se fixa depois (`Initial FX:
# PTAX-V 06-Nov-2026`): o 0301 o registra a termo — Data da operação (19), o
# Índice Termo (20) que corrige o Valor Base, Percentual 100% (21) e a Data de
# Cotação Final do índice de moeda (99, D-n da fixação ao início). Índice 00
# (VCP: a fixação no próprio dia do início — a regra da macro da mesa) leva PU
# Inicial, Tipo/Classe e Denominação (22-24) em vez do D-n. E com o Valor Base
# a ser corrigido, o Cupom Limpo das curvas (47/49) vai em BRANCO (equipe,
# 26/10/2026).
TERMO_PERCENT = 100


def is_termo(deal):
    """O deal é a termo? — tem a Atualização de Notional (índice e data)."""
    return bool(str((deal or {}).get('NotionalIndex') or '').strip()
                and dtk.parse_date((deal or {}).get('NotionalObsDate')))


def termo_row(rows, text):
    """A linha do cadastro `swap-termo-index` do índice escrito (`PTAX-V`):
    `Exact` vence `Contains`, entre os `Contains` o mais longo. → dict ou None."""
    alvo = dtk.norm(text)
    if not alvo:
        return None
    exato, contem = None, (None, -1)
    for r in rows or []:
        pat = dtk.norm((r or {}).get('INDEX'))
        if not pat or not str((r or {}).get('CODE') or '').strip():
            continue
        if dtk.norm((r or {}).get('MATCH', 'Exact')) == 'CONTAINS':
            if pat in alvo and len(pat) > contem[1]:
                contem = (r, len(pat))
        elif pat == alvo:
            exato = r
    return exato if exato is not None else contem[0]


def termo_codes(deal, rows, biz_diff):
    """{'termo_index', 'termo_class', 'termo_quote'} do deal a termo (vazio
    fora dele). `biz_diff(a, b)` conta os dias úteis ANBIMA em (a, b] — a
    `NetworkDays − 1` da macro. Fixação no dia do início → índice 00 (VCP),
    com o Tipo/Classe da linha; senão o D-n da fixação até o início."""
    if not is_termo(deal):
        return {}
    obs = dtk.parse_date(deal.get('NotionalObsDate'))
    ini = dtk.parse_date(deal.get('StartDate'))
    r = termo_row(rows, deal.get('NotionalIndex'))
    if obs and ini and obs == ini:
        return {'termo_index': '00', 'termo_class': dtk._digits((r or {}).get('VCP CLASS')),
                'termo_quote': ''}
    code = str((r or {}).get('CODE') or '').strip()
    n = biz_diff(obs, ini) if (obs and ini) else None
    return {'termo_index': code.zfill(2) if code.isdigit() else code, 'termo_class': '',
            'termo_quote': ('%02d' % n) if n is not None and 0 <= n <= 5 else ''}


def termo_denomination(deal):
    """A Denominação do VCP a termo (24), no texto da macro, sem acento."""
    fx = dtk.parse_number(deal.get('FXStart'))
    obs = dtk.parse_date(deal.get('NotionalObsDate'))
    t = 'Valor base convertido pelo FX Inicial: %s e sera atualizado em %s pelo indice %s' % (
        ('%.7f' % fx) if fx is not None else '', obs.strftime('%d/%m/%Y') if obs else '',
        str(deal.get('NotionalIndex') or '').strip())
    return re.sub(r'\bVCP\b', '', dtk.strip_accents(t)).strip()


def contract_record_values(deal, view, accounts, codes, my_number):
    """Os 117 campos do registro tipo 1 do 4.2.7 v00003, por seq, JÁ na
    largura do manual. As regras das pernas são as do Bullet
    (`swap_bullet.domain.swap_record_values`) nas posições deste layout;
    `codes` é o mesmo dicionário do `codes_for`."""
    parte, contra = dtk.view_sides(deal, view, accounts)
    d = dtk._digits
    vals = {}
    vals['1'] = 'SWAP '
    vals['2'] = '1'
    vals['3'] = '0301'
    vals['4'] = d(my_number).zfill(10)[-10:]
    vals['5'] = parte['account'].zfill(8)[-8:] if parte['account'] else _blank(8)
    vals['6'] = (parte['taxid'] or '').ljust(14)[:14]
    vals['7'] = _blank(10)
    vals['8'] = contra['account'].zfill(8)[-8:] if contra['account'] else _blank(8)
    vals['9'] = (contra['taxid'] or '').ljust(14)[:14]
    vals['10'] = _blank(10)
    vals['11'] = dtk.ymd(deal.get('StartDate')).ljust(8)
    vals['12'] = dtk.ymd(deal.get('MaturityDate')).ljust(8)
    vals['13'] = (codes.get('adhesion') or '').rjust(2, '0') if codes.get('adhesion') else _blank(2)
    vals['14'] = dtk.b3_num(deal.get('Notional'), 14, 2) or _blank(16)
    vals['15'] = _blank(2)
    prem = dtk.norm(deal.get('PremiumSchedule')) in ('SIM', 'YES', 'S', 'Y')
    vals['16'] = codes.get('premium_schedule') or ('00' if prem else '01')
    vals['17'] = _blank(2)
    vals['18'] = _blank(100)            # Observação: opcional, não vai (como no Bullet)
    # 19-24: contrato a TERMO (FWD Start com Atualização de Notional, §697);
    # o swap registrado em D0 os deixa em branco.
    for seq, w in ((19, 8), (20, 2), (21, 5), (22, 22), (23, 5), (24, 320), (25, 42)):
        vals[str(seq)] = _blank(w)
    termo = is_termo(deal)
    if termo:
        vals['19'] = dtk.ymd(deal.get('TradeDate')).ljust(8)
        vals['20'] = (codes.get('termo_index') or '').rjust(2)[:2] or _blank(2)
        vals['21'] = dtk.b3_num(TERMO_PERCENT, 3, 2)
        if codes.get('termo_index') == '00':
            vals['22'] = dtk.b3_num(dtk.parse_number(deal.get('FXStart')), 14, 8) or _blank(22)
            vals['23'] = d(codes.get('termo_class')).zfill(5)[-5:] if d(codes.get('termo_class')) else _blank(5)
            vals['24'] = termo_denomination(deal)[:320].ljust(320)
    # Curva para Atualização: 26-32 Parte, 33-39 Contraparte (as mesmas do Bullet).
    for base, side in ((26, parte), (33, contra)):
        c = dtk._curve(deal, side['curve'])
        juros = c['category'] != 'VCP'
        vals[str(base)] = dtk.b3_num(c['pct'], 3, 2) or _blank(5)
        vals[str(base + 1)] = (codes.get('curve' + side['curve']) or '').ljust(3)[:3]
        vals[str(base + 2)] = _blank(8)
        vals[str(base + 3)] = (codes.get('sign' + side['curve']) or '00') if juros else _blank(2)
        vals[str(base + 4)] = (dtk.b3_num(c['rate'], 3, 4) or '0000000') if juros else _blank(7)
        vals[str(base + 5)] = dtk.b3_num(c['floor'], 8, 8) or _blank(16)
        vals[str(base + 6)] = dtk.b3_num(c['cap'], 8, 8) or _blank(16)
    vals['40'] = _blank(35)             # Terceira curva: não se usa.
    # Se curva(s) = VCP: 41-43 Parte, 44-46 Contraparte; Cupom Limpo 47-48 / 49-50.
    price = dtk.parse_number(deal.get('InitialPrice'))
    text = str(deal.get('VcpText') or '').strip() or dtk.vcp_text(deal)
    # A Denominação vai na curva VCP da PARTE; e na da CONTRAPARTE quando a
    # Parte não é VCP e o cliente está na conta guarda-chuva — a regra da macro
    # da mesa (§697: o Term SOFR que o CLIENTE recebe).
    parte_vcp = dtk._curve(deal, parte['curve'])['category'] == 'VCP'
    contra_desc = (view == 'client' and not parte_vcp
                   and dtk.norm(deal.get('ClientAccountNote')) == 'OMNIBUS')
    for base, cl_base, side in ((41, 47, parte), (44, 49, contra)):
        c = dtk._curve(deal, side['curve'])
        if dtk.is_fx_category(c['category']):
            # Perna de MOEDA (§555): o Cupom Limpo é a COTAÇÃO inicial da moeda
            # ("Cotação Cupom Limpo Curva Moeda ou VCP", 47/49) e a Data de
            # Cotação é a defasagem D-n (48/50); os blocos VCP ficam em branco.
            lado = side['curve']
            vals[str(base)] = _blank(22)
            vals[str(base + 1)] = _blank(5)
            vals[str(base + 2)] = _blank(320)
            vals[str(cl_base)] = ((dtk.b3_num(fx_clean_coupon(deal, lado), 8, 7) or _blank(15))
                                  if not termo else _blank(15))
            vals[str(cl_base + 1)] = fx_quote_code(deal, lado) or _blank(2)
        elif c['category'] == 'VCP':
            vals[str(base)] = dtk.b3_num(1, 14, 8)
            vals[str(base + 1)] = d(deal.get('VcpCode')).zfill(5)[-5:] if d(deal.get('VcpCode')) else _blank(5)
            com_texto = side is parte or (side is contra and contra_desc)
            vals[str(base + 2)] = text[:320].ljust(320) if com_texto else _blank(320)
            vals[str(cl_base)] = (dtk.b3_num(price, 8, 7) or _blank(15)) if not termo else _blank(15)
            vals[str(cl_base + 1)] = (str(deal.get('QuoteDateCode') or '').zfill(2)
                                      if str(deal.get('QuoteDateCode') or '').strip() else _blank(2))
        else:
            vals[str(base)] = _blank(22)
            vals[str(base + 1)] = _blank(5)
            vals[str(base + 2)] = _blank(320)
            vals[str(cl_base)] = _blank(15)
            vals[str(cl_base + 1)] = _blank(2)
    # 51-70 Libor, 71-86 TJMI, 87-94 Commodity: não se aplicam.
    widths = {51: 2, 52: 2, 53: 2, 54: 2, 55: 5, 56: 2, 57: 10, 58: 8, 59: 8, 60: 8,
              61: 2, 62: 2, 63: 2, 64: 2, 65: 5, 66: 2, 67: 10, 68: 8, 69: 8, 70: 8,
              71: 7, 72: 2, 73: 2, 74: 5, 75: 10, 76: 8, 77: 8, 78: 8,
              79: 7, 80: 2, 81: 2, 82: 5, 83: 10, 84: 8, 85: 8, 86: 8,
              87: 10, 88: 15, 89: 2, 90: 2, 91: 10, 92: 15, 93: 2, 94: 2,
              95: 110, 96: 11, 97: 1}
    for seq, w in widths.items():
        vals[str(seq)] = _blank(w)
    # O Código Identificador leva a LOB, como o 116 do Bullet (a mesma posição).
    vals['98'] = str(deal.get('LOB') or '').strip()[:14].rjust(14)
    # 99-101 (termo, fixing IPCA), 102 branco, 103-117 (Overnight e TERM SOFR):
    # não gerados — perna JUROS INTERNACIONAIS é recusada (`missing_for_send`).
    for seq, w in ((99, 2), (100, 2), (101, 2), (102, 24), (103, 2), (104, 15), (105, 2), (106, 2),
                   (107, 2), (108, 8), (109, 15), (110, 2), (111, 2), (112, 2), (113, 8),
                   (114, 2), (115, 15), (116, 2), (117, 15)):
        vals[str(seq)] = _blank(w)
    if termo and codes.get('termo_index') != '00' and codes.get('termo_quote'):
        vals['99'] = codes['termo_quote']   # D-n do índice de moeda (fixação → início)
    return vals


# ── O registro 0034 (o cronograma) ───────────────────────────────────────────

def flow_values(deal, view, accounts, contract_my_number, flow_my_number, amort_code, participant,
                today_ymd):
    """(header, registro, [linhas de fluxo]) do 0034 — cada um {seq: valor na
    largura}. Papel = a PONTA da Parte pela conta MENOR (o critério do 0897,
    manual 4.2.12 — SUPOSIÇÃO: a 4.2.8 não o repete). As duas pontas levam a
    mesma data e a mesma taxa de amortização: o cronograma do DT é um só."""
    parte, contra = dtk.view_sides(deal, view, accounts)
    flows = normalize_schedule(deal.get(SCHEDULE_FIELD))
    header = {'1': 'SWAP ', '2': '0', '3': '0034', '4': str(participant or '').ljust(20)[:20],
              '5': today_ymd}
    reg = {'1': 'SWAP ', '2': '1', '3': '0034',
           '4': str(len(flows)).zfill(4)[-4:],
           '5': dtk._digits(contract_my_number).zfill(10)[-10:],
           '6': dtk._digits(flow_my_number).zfill(10)[-10:],
           '7': parte['account'].zfill(8)[-8:] if parte['account'] else _blank(8),
           '8': contra['account'].zfill(8)[-8:] if contra['account'] else _blank(8),
           '9': dtk._ponta(parte['account'], parte['account'], contra['account']),
           '10': str(amort_code or '').zfill(2)[-2:] if str(amort_code or '').strip() else _blank(2),
           '11': _blank(8)}
    linhas = []
    for fl in flows:
        data = dtk.ymd(fl.get('PaymentDate')).ljust(8)
        amort = dtk.b3_num(dtk.parse_number(fl.get('AmortizationPct')) or 0, 3, 5)
        linha = {'1': data, '2': _blank(2), '3': _blank(7), '4': _blank(16), '5': _blank(16), '6': amort,
                 '7': data, '8': _blank(2), '9': _blank(7), '10': _blank(16), '11': _blank(16), '12': amort}
        for seq in range(13, 23):
            linha[str(seq)] = _blank(8)
        linhas.append(linha)
    return header, reg, linhas


# ── Lacunas: o que o Send recusa ─────────────────────────────────────────────

def lacuna(code, text, **params):
    """Uma lacuna ESTRUTURADA (§486): a tela diz pelo `_TRANS` (`w_<code>`),
    o `text` é só o fallback."""
    return {'code': code, 'params': params, 'text': text}


def missing_for_send(deal, codes, accounts, amort_code):
    """As lacunas do cashflow: as do Bullet (as mesmas perguntas sobre datas,
    notional, códigos, contas e contraparte), mais o cronograma e o tipo de
    amortização. Cada item é `lacuna(...)`; vazia = pode enviar."""
    termo = is_termo(deal)
    # A termo, o Cupom Limpo vai em BRANCO (§697): o Preço Inicial do VCP não
    # é pedido.
    out = [lacuna('swc_missing', t, field=t) for t in dtk.missing_for_send(deal, codes, accounts)
           if not (termo and t == 'Initial Price')]
    if termo:
        if not str(codes.get('termo_index') or '').strip():
            out.append(lacuna('swc_termo_index', 'Forward start: index %r has no Índice Termo code in '
                              '/mapping › Swap — Forward-start Index' % deal.get('NotionalIndex'),
                              index=str(deal.get('NotionalIndex') or '')))
        elif codes.get('termo_index') == '00':
            if not str(codes.get('termo_class') or '').strip():
                out.append(lacuna('swc_termo_class', 'Forward start fixing on the start date (VCP): the '
                                  'Tipo/Classe of index %r — /mapping › Swap — Forward-start Index'
                                  % deal.get('NotionalIndex'), index=str(deal.get('NotionalIndex') or '')))
            if dtk.parse_number(deal.get('FXStart')) is None:
                out.append(lacuna('swc_fx_coupon', 'Forward start (VCP): FX Start', side='-'))
        elif not str(codes.get('termo_quote') or '').strip():
            out.append(lacuna('swc_termo_quote', 'Forward start: the fixing date (%s) must be D0 to D-5 '
                              'business days before the Start Date' % deal.get('NotionalObsDate'),
                              date=str(deal.get('NotionalObsDate') or '')))
    flows = normalize_schedule(deal.get(SCHEDULE_FIELD))
    if not flows:
        out.append(lacuna('swc_no_flows', 'Cash Flow schedule (no flow)'))
    elif len(flows) > MAX_FLOWS:
        out.append(lacuna('swc_too_many_flows', 'Cash Flow schedule (%d flows; the B3 accepts up to %d)'
                          % (len(flows), MAX_FLOWS), n=len(flows), max=MAX_FLOWS))
    ini = dtk.parse_date(deal.get('StartDate'))
    fim = dtk.parse_date(deal.get('MaturityDate'))
    anterior = None
    for i, fl in enumerate(flows, 1):
        pg = dtk.parse_date(fl.get('PaymentDate'))
        if not pg:
            out.append(lacuna('swc_flow_no_date', 'Flow %d: Payment Date' % i, n=i))
            continue
        if (ini and pg <= ini) or (fim and pg > fim):
            out.append(lacuna('swc_flow_out_of_range', 'Flow %d: Payment Date %s outside the contract '
                              '(Start → Maturity)' % (i, dtk.iso(pg)), n=i, date=dtk.iso(pg)))
        if anterior and pg <= anterior:
            out.append(lacuna('swc_flow_order', 'Flow %d: Payment Date %s is not after the previous one'
                              % (i, dtk.iso(pg)), n=i, date=dtk.iso(pg)))
        anterior = pg
    if flows and fim and dtk.parse_date(flows[-1].get('PaymentDate')) not in (None, fim):
        out.append(lacuna('swc_last_flow_maturity', 'The last flow must pay on the Maturity Date (%s)'
                          % dtk.iso(fim), date=dtk.iso(fim)))
    if not str(deal.get('AmortizationType') or '').strip():
        out.append(lacuna('swc_no_amortization', 'Amortization type'))
    elif not str(amort_code or '').strip():
        out.append(lacuna('swc_amortization_code', 'Amortization %r has no B3 code in /mapping › Swap — '
                          'Tipo de Amortização' % deal.get('AmortizationType'),
                          value=str(deal.get('AmortizationType'))))
    if dtk.norm(deal.get('LOB')) not in ('CEM', 'EDG'):
        out.append(lacuna('swc_no_lob', 'LOB (CEM or EDG)'))
    for side in ('A', 'B'):
        if dtk.is_fx_category(deal.get('Curve' + side + 'Category')):
            if fx_clean_coupon(deal, side) is None:
                out.append(lacuna('swc_fx_coupon', 'Curve %s (currency): initial FX quote — FX Start or '
                                  'Clean Coupon' % side, side=side))
            if not fx_quote_code(deal, side):
                out.append(lacuna('swc_fx_quote', 'Curve %s (currency): Quote date D-n (D0 to D-5)'
                                  % side, side=side))
        if not str(deal.get('Curve' + side + 'Category') or '').strip():
            out.append(lacuna('swc_no_category', 'Curve %s category (%s) — register the curve in /mapping '
                              '› Swap Bullet Curve (its B3 code gives the category in Swap Index)'
                              % (side, deal.get('Curve' + side) or '?'), side=side,
                              curve=str(deal.get('Curve' + side) or '')))
    for side in ('A', 'B'):
        if dtk.norm(deal.get('Curve' + side + 'Category')) == 'JUROSINTERNACIONAIS':
            out.append(lacuna('swc_intl_curve', 'Curve %s is JUROS INTERNACIONAIS — the SOFR / TERM SOFR '
                              'fields of the B3 file are not generated yet' % side, side=side))
    return out


def lacuna_texts(lacunas):
    return [x['text'] if isinstance(x, dict) else str(x) for x in lacunas or []]
