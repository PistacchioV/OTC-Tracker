# -*- coding: utf-8 -*-
"""A família de liquidação do Other Products — o motor compartilhado.

Movido VERBATIM do `routes.py` (fase platform/ — CLAUDE.md §10):
`_ops_trade_rows(settle_ref)` é o ÚNICO lugar que sabe quais famílias de
produto existem (SWAP + NDF Commodities + Option), e dele leem o Settlement
Summary, o Trade Level, as duas telas de Settlement Advice, os cards de
reconciliação e o e-mail de TED (§199). O `routes.py` mantém os nomes como
ALIAS, então features e testes seguem alcançando por `routes.<nome>`.

O que ainda é do `routes` — os leitores de arquivo-dia (`_opb3_*`, `_otm_*`,
`_latam_*`, forecast), o Reference Data (`_ndfsum_*`), o Counterparty Details
(`_cpd_*`) e os coletores de advice — é alcançado por import ATRASADO
(`from apps.pages import routes` dentro da função), andaime declarado até cada
camada ter a própria fatia. É o que mantém válidos os testes que trocam esses
atributos no `routes` (`R.OTM_JSON_ROOT = tmp`, `R._cpd_load = fake`).

O ESTADO de request-cache dos dois loaders pesados (`_ops_swap_pos_terms`,
`_ops_equity_link`) continua no `@_req_cached` — o decorador vem do
`request_cache.py`, módulo próprio, e o import aqui é DIRETO como no routes.
"""
import base64
import json
import logging
import os
import re
import traceback
from datetime import datetime, timedelta


# Cache de leitura por request — módulo próprio (apps/pages/request_cache.py),
# o MESMO objeto que o routes importa: o decorador não é superfície de patch.
from apps.pages.request_cache import req_cached as _req_cached

log = logging.getLogger('otc_tracker')

# ── Other Products Summary (Settlement Batch) ────────────────────────────────
#  Counts operations SETTLING on the reference date, reusing the Settlement
#  Forecast JSON sources (position files from Save CETIP Files). Each forecast
#  source maps to a product family + sub-event; options also settle on the
#  premium date (date2), swaps split flow/premium/maturity across the 3 files.
_OPS_SRC_MAP = {
    'swap_pos': ('swap', 'maturity'),   # DPOSICAO-SWAP (tipo 2, maturity)
    'swap_flx': ('swap', 'flow'),       # DFLUXO (event date)
    'swap_prm': ('swap', 'premium'),    # DAGENDAPREMIOS (premium settlement = col F)
    'opc':      ('option', 'maturity'), # OPC maturity; date2 → premium
    'ndf':      ('ndf', 'maturity'),    # TER maturity
}

# Como achar o CÓDIGO DO CONTRATO em cada um dos dois arquivos de swap. É a
# chave que liga a posição ao fluxo, e ela tem nomes diferentes nos dois:
# 'Contrato' na DPOSICAO-SWAP, 'Código do contrato' na DFLUXO.
_OPS_SWAP_JOIN_TOKENS = {
    'swap_pos': ['contrato'],
    'swap_flx': ['codigo do contrato', 'código do contrato', 'codigo contrato'],
}


def _ops_src_latest_path(src, max_back=10):
    """Cascata para a versão cacheada — o `src` é um dict (inhashável para a
    chave do cache), então a memoização é pela `key` dele. A sondagem custa
    até 10 `isfile` no share POR FONTE, e a tela pergunta pelas cinco."""
    return _ops_src_latest_path_cached(str(src.get('key', '')), max_back)


@_req_cached
def _ops_src_latest_path_cached(src_key, max_back=10):
    from apps.pages import routes
    src = next((s for s in routes._FORECAST_SOURCES
                if s.get('key') == src_key), None)
    if src is None:
        return None, None
    return _ops_src_latest_path_uncached(src, max_back)


def _ops_src_latest_path_uncached(src, max_back=10):
    """Newest existing snapshot (path, dref) for ONE forecast source, walking back
    from D-1 ANBIMA. Each product folder is saved independently and the dates can
    drift a day apart (e.g. the NDF TER file lands after the SWAP files, or the
    Save-CETIP routine ran for one family but not another). Resolving the ref
    PER SOURCE — instead of a single shared `pos_ref` — keeps a family from
    silently counting zero just because its file is missing on the shared date."""
    from apps.pages import routes
    ref = routes._prev_anbima_bizday(datetime.now())
    for _ in range(max_back):
        dref = ref.strftime('%y%m%d')
        path = os.path.join(routes.B3_JSON_ROOT, src['category'], routes._b3_date_subpath(dref), src['file'](dref))
        if os.path.isfile(path):
            return path, dref
        ref = routes._prev_anbima_bizday(ref)
    return None, None


def _ops_settlement_counts(settle_ref, pos_ref):
    """Count operations settling on `settle_ref` (date) by product family +
    sub-event, reading each family's OWN latest position JSON. Missing files /
    no data → zeros (graceful, and logged so a silent zero is diagnosable)."""
    from apps.pages import routes
    fams = {'swap':   {'total': 0, 'flow': 0, 'premium': 0, 'maturity': 0},
            # `fx` e `comm` separam Opção de taxa de câmbio de Opção de
            # commodities: são mesas e conferências diferentes, e o card somado
            # não dizia de quem era o número.
            'option': {'total': 0, 'maturity': 0, 'premium': 0, 'fx': 0, 'comm': 0},
            'ndf':    {'total': 0, 'maturity': 0},
            'coe':    {'total': 0}}
    # A tipo-2 swap is a bullet contract: its single settlement is on its own
    # maturity date, and that same final payment can also surface in DFLUXO as an
    # event. It must be counted as MATURITY, not Flow. So we collect the "Código
    # Identificador" of every contract maturing on `settle_ref` (from
    # DPOSICAO-SWAP, tipo 2) and then EXCLUDE those ids from the DFLUXO Flow
    # count — a flow event only counts as Flow when its contract's maturity is
    # NOT the picker date. swap_pos is processed before swap_flx in
    # _FORECAST_SOURCES, so the set is fully populated by the time Flow is read.
    #
    # A junção é pelo CÓDIGO DO CONTRATO — não pelo "Código Identificador", que
    # no arquivo real é o LOB ('CEM') e se repete em todas as linhas do dia.
    # Usá-lo como chave fazia UM swap bullet vencendo hoje apagar TODO cashflow
    # de 'CEM' da contagem: o card mostrava Cashflow 0 · Maturity 1 com um evento
    # de fluxo liquidando na mesma data, e nada acusava porque o zero parece
    # "não teve fluxo hoje".
    swap_mat_ids = set()
    for src in routes._FORECAST_SOURCES:
        mapping = _OPS_SRC_MAP.get(src['key'])
        if not mapping:
            continue
        fam, primary_sub = mapping
        if fam == 'ndf':
            continue   # handled below via _forecast_collect (verbatim index logic)
        path, dref = _ops_src_latest_path(src)   # files are named yymmdd (e.g. 260703)
        if path is None:
            log.warning("[ops] %s (%s): no snapshot found in last 10 biz days; card counts 0",
                        src['key'], fam)
            continue
        try:
            with open(path, encoding='utf-8') as fh:
                rows = json.load(fh)
        except Exception:
            continue
        if not rows:
            continue
        keys = list(rows[0].keys())
        date_key = routes._fcst_resolve_key(keys, src['date'])
        if date_key is None and src.get('date_index') is not None and 0 <= src['date_index'] < len(keys):
            date_key = keys[src['date_index']]
        date2_key = routes._fcst_resolve_key(keys, src['date2']) if src.get('date2') else None
        if date2_key is None and src.get('date2_index') is not None and 0 <= src['date2_index'] < len(keys):
            date2_key = keys[src['date2_index']]
        cw = src.get('count_where')
        cw_key = routes._fcst_resolve_key(keys, cw[0]) if cw else None
        cw_allowed = cw[1] if cw else None
        # Chave de junção posição × fluxo: 'Contrato' na DPOSICAO-SWAP e 'Código
        # do contrato' na DFLUXO. O filtro do 'tipo de contrato' é o mesmo de
        # `_ops_swap_pos_terms`: sem ele o fallback por substring casaria com a
        # coluna do TIPO, que é '1'/'2' e junta tudo com tudo.
        id_key = routes._fcst_resolve_key(
            [k for k in keys if routes._fcst_norm(k) != 'tipo de contrato'],
            _OPS_SWAP_JOIN_TOKENS.get(src['key'], []))
        if src['key'] in _OPS_SWAP_JOIN_TOKENS and id_key is None:
            # Sem a chave, a dedupe não roda — e a escolha é contar a mais em vez
            # de contar a menos: um Cashflow sobrando aparece na tela e alguém
            # pergunta; um Cashflow faltando passa por "não teve fluxo hoje".
            log.warning("[ops] %s: sem coluna de contrato (%s); a dedupe "
                        "posição × fluxo não roda hoje", src['key'], path)
        # Classe do ativo subjacente — só a posição de OPÇÃO precisa, para
        # separar câmbio de commodities dentro do mesmo card.
        classe_key = (routes._fcst_resolve_key(keys, ['classe do ativo subjacente',
                                               'classe do ativo', 'classe'])
                      if src['key'] == 'opc' else None)
        # Comparação por TOKEN, não igualdade: o arquivo de opção escreve
        # 'TAXA DE CAMBIO' (singular) e o de NDF escreve 'TAXAS DE CAMBIO'.
        # Igualdade exata deixaria o balde de FX permanentemente em zero — e um
        # zero não parece defeito, parece "não teve opção de câmbio hoje".
        for row in rows:
            if cw_key is not None:
                cwv = str(row.get(cw_key, '') or '').strip()
                if cwv.endswith('.0'):
                    cwv = cwv[:-2]
                if cwv.isdigit():            # leading zeros: '02' → '2', '01' → '1'
                    cwv = str(int(cwv))
                if cwv not in cw_allowed:
                    continue
            # `_fcst_norm_contract` + caixa alta: os dois arquivos escrevem o
            # mesmo contrato com espaço sobrando ou com o rabo '.0' de número.
            cid = routes._fcst_norm_contract(row.get(id_key, '')).upper() if id_key else ''
            # Flow event whose contract matures on the picker date → it's the
            # maturity payment (already counted via swap_pos), not a Flow.
            if src['key'] == 'swap_flx' and cid and cid in swap_mat_ids:
                continue
            # A classe vale para as DUAS datas da opção (vencimento e prêmio):
            # a quebra é do contrato, não do evento.
            def _bump_class():
                if not classe_key:
                    return
                cl = routes._fcst_norm(str(row.get(classe_key, '') or ''))
                if 'cambio' in cl:
                    fams['option']['fx'] += 1
                elif 'commodit' in cl:
                    fams['option']['comm'] += 1
            if date_key and routes._fcst_parse_date(row.get(date_key, '')) == settle_ref:
                fams[fam]['total'] += 1
                fams[fam][primary_sub] += 1
                _bump_class()
                if src['key'] == 'swap_pos' and cid:
                    swap_mat_ids.add(cid)
            if date2_key and routes._fcst_parse_date(row.get(date2_key, '')) == settle_ref:
                fams[fam]['total'] += 1
                if fam == 'option':
                    fams[fam]['premium'] += 1
                    _bump_class()

    # NDF Commodities — reuse the Settlement Forecast (index.html) computation
    # VERBATIM so the two cards can never disagree: same TER file, same "Data de
    # Vencimento" field, same "Classe do Ativo Subjacente" → NDF Commodities
    # mapping. Single-day spine at the settlement date; read that day's slot.
    if pos_ref is not None:
        f_by_product, _, _ = routes._forecast_collect(pos_ref.strftime('%y%m%d'), [settle_ref])
        ndf_c = (f_by_product.get('NDF Commodities') or [0])[0]
        fams['ndf']['total'] = ndf_c
        fams['ndf']['maturity'] = ndf_c
    return fams


# ── Other Products › Summary › Trade Level: SWAP ─────────────────────────────
#  Uma linha por SWAP liquidando na data, montada a partir de CINCO fontes que
#  não se conhecem — o join é todo por código, e cada perna tem a sua chave:
#
#    Operations B3 ──Título──> B3 ID, LOB (coluna derivada Type), Settlement B3
#          │
#          └─Título = CETIP ID─> Swap Athena ──> Internal ID (Kapital ID),
#                                                Counterparty, Direction
#          │                          │
#          │                          └─Kapital ID = Trade Id─> OTM Settlements
#          │                                                    ──> Settlement
#          ├─Título = Código do Contrato─> Swap Events ──> Type (VCP × Calculado)
#          └─Título = Contrato──────────> Posição SWAP ──> prazo (para o IR)
#
#  O MESMO swap aparece no Operations B3 uma vez por Tipo Operação (amortização,
#  juros, prêmio). A linha é UMA só por Título — daí o dedup — mas o Settlement
#  B3 soma TODAS as linhas daquele Título, inclusive as que o filtro descartou:
#  o que se concilia é o caixa do dia, não o evento.
_OPS_TRADE_COLS = ('lob', 'counterparty', 'internal_id', 'id_b3', 'product', 'type',
                   'settlement', 'settlement_b3', 'tax_income', 'difference')

def _swadv_indexador(cod, nome):
    """Indexador de uma perna do swap, para o aviso de liquidação.

    O `Código índice` da posição é um CÓDIGO (`C00`, `PRE`, `DI1`), não o nome —
    por isso ele passa **primeiro** pelo cadastro `swap-index`, o mesmo que a
    tela do Live Position › Swap usa para mostrar a curva em vez do código.
    Comparar o código cru com 'VCP' nunca casava: o VCP é `C00`.

    Traduzido, é o nome do indexador na maioria dos casos (CDI, PRE, IPCA). A
    exceção é **VCP** — variação cambial —, que não diz qual moeda: aí o
    indexador de verdade está no `Nome Tipo/Classe` da mesma perna, e vai em
    CAIXA ALTA. Imprimir 'VCP' no aviso do cliente não informa nada."""
    from apps.pages import routes
    nome_curva = routes._swapindex_name(cod)
    if routes._fcst_norm(nome_curva) == 'vcp':
        return str(nome or '').strip().upper()
    return nome_curva


@_req_cached
def _ops_swap_pos_terms(ref):
    """{Contrato → {'op', 'venc', 'idx_banco', 'idx_cliente'}} da posição
    DPOSICAO-SWAP mais recente até D-1 ANBIMA de `ref` (mesmo walk-back de 10
    pregões do Operations B3).

    A data de operação é a do XLOOKUP da planilha: **Data operação termo** e, só
    quando ela vem vazia, **Data início**. É o que faz um forward start pagar IR
    pelo prazo desde o TRADE, não desde o início do swap — usar a data de início
    encurtaria o prazo e subiria a alíquota.

    Índices posicionais de `_SWAPCHAR_LABELS` (2=Contrato, 11=Data início,
    12=Data vencimento, 25=Data operação termo) — batem coluna a coluna com o
    C/L/M/Z da planilha. Os indexadores saem das DUAS pernas simétricas do
    arquivo: `Código índice` em **40** (banco) e **50** (cliente), `Nome
    Tipo/Classe` em **69** e **74**. São exatamente a 1ª e a 2ª de cada uma na
    tela do Live Position › Swap; no arquivo cru há um `Nome Tipo/Classe` ANTES
    (índice 30), que é do bloco do Termo e não de perna nenhuma — pegá-lo pela
    ordem do arquivo daria a classe errada sem erro nenhum.

    O arquivo real tem 146 campos com nomes repetidos, então ler por nome
    perderia metade; o `len(vals) >= 120` é o mesmo teste que
    `_swap_contract_cpty_map` usa para distinguir o arquivo real do mock esparso.
    Fora do caminho posicional os indexadores saem vazios — nomes repetidos não
    permitem dizer qual é a 1ª e qual é a 2ª.
    """
    from apps.pages import routes
    probe = routes._prev_anbima_bizday(ref)
    rows = None
    for _ in range(10):
        dref = probe.strftime('%y%m%d')
        p = os.path.join(routes.B3_JSON_ROOT, 'Swap', routes._b3_date_subpath(dref),
                         '73760_{}_DPOSICAO-SWAP.json'.format(dref))
        if os.path.isfile(p):
            try:
                with open(p, encoding='utf-8') as fh:
                    rows = json.load(fh) or []
            except Exception:
                log.warning("[ops-trade] posição SWAP ilegível (%s):\n%s", p, traceback.format_exc())
                rows = []
            break
        probe = routes._prev_anbima_bizday(probe)
    out = {}
    if not rows:
        return out
    keys = list(rows[0].keys())
    k_contr = routes._fcst_resolve_key([k for k in keys if routes._fcst_norm(k) != 'tipo de contrato'],
                                ['contrato'])
    k_ini = routes._fcst_resolve_key(keys, ['data inicio', 'data início'])
    k_venc = routes._fcst_resolve_key(keys, ['data vencimento', 'data de vencimento'])
    k_termo = routes._fcst_resolve_key(keys, ['data operacao termo', 'data operação termo'])
    for r in rows:
        vals = list(r.values())
        full = len(vals) >= 120
        idx_banco = idx_cliente = base = ''
        if full:
            contrato = vals[2]
            d_ini, d_venc, d_termo = vals[11], vals[12], vals[25]
            idx_banco = _swadv_indexador(vals[40], vals[69])
            idx_cliente = _swadv_indexador(vals[50], vals[74])
            base = vals[14]                              # 'Valor base' (coluna O)
        else:
            contrato = r.get(k_contr, '') if k_contr else ''
            d_ini = r.get(k_ini, '') if k_ini else ''
            d_venc = r.get(k_venc, '') if k_venc else ''
            d_termo = r.get(k_termo, '') if k_termo else ''
        c = routes._fcst_norm_contract(contrato).upper()
        if not c:
            continue
        op = routes._fcst_parse_date(str(d_termo or '')) or routes._fcst_parse_date(str(d_ini or ''))
        out.setdefault(c, {'op': op, 'venc': routes._fcst_parse_date(str(d_venc or '')),
                           'idx_banco': idx_banco, 'idx_cliente': idx_cliente,
                           'valor_base': base})
    return out


def _ops_swap_ir_rate(client, prazo_days, cpty_receives):
    """Alíquota de IR do swap em FRAÇÃO (0.15 = 15%), ou None quando não dá para
    afirmar. Porte da fórmula da planilha, na mesma ordem:

      1. exceção por cliente (`swap-ir-client`) — bancos e as duas entidades JPM;
      2. fora das exceções, só há IR quando **quem recebe é a contraparte**;
      3. tabela regressiva por prazo (`swap-ir-term`).

    None ≠ 0%: sem prazo na posição não há como escolher a faixa, e imprimir 0%
    ali seria afirmar isenção que ninguém verificou. A célula fica vazia, que é o
    pedido de conferência.

    A planilha tem um vão em 721 (`E12>721` deixa o prazo 721 exato sem resposta,
    devolvendo FALSE). A tabela por faixas fecha isso: acima da última faixa
    registrada vale a linha sem limite.
    """
    from apps.pages import routes
    cn = routes._fcst_norm(client).strip()
    if not cn:
        return None
    for row in routes._mapping_rows('swap-ir-client'):
        pat = routes._fcst_norm(row.get('CLIENT', '')).strip()
        if not pat:
            continue
        hit = cn.startswith(pat) if 'starts' in routes._fcst_norm(row.get('MATCH', '')) else cn == pat
        if hit:
            r = routes._conf_to_float(row.get('RATE'))
            return None if r is None else r / 100.0
    if cpty_receives is None:      # direção desconhecida ≠ "não é ela que recebe"
        return None
    if not cpty_receives:
        return 0.0
    if prazo_days is None:
        return None
    brackets, catch_all = [], None
    for row in routes._mapping_rows('swap-ir-term'):
        rate = routes._conf_to_float(row.get('RATE'))
        if rate is None:
            continue
        upto = routes._conf_to_float(row.get('UP TO DAYS'))
        if upto is None:
            catch_all = rate / 100.0
        else:
            brackets.append((upto, rate / 100.0))
    for upto, rate in sorted(brackets):
        if prazo_days <= upto:
            return rate
    return catch_all


def _ops_cpty_receives(direction, settlement):
    """Quem recebe é a contraparte?

    Preferimos o texto: a coluna Direction do Athena é a que a planilha lê em
    `O12="Counterparty receives"`. Quando ela vem vazia (ou com um vocabulário
    que não conhecemos) sobra o SINAL do settlement — negativo é o banco pagando,
    logo é a contraparte recebendo, que é a convenção do Resultado Bruto entre
    parênteses no aviso. Sem texto e sem valor, None: não dá para afirmar, e o
    IR sai em branco em vez de sair zero."""
    from apps.pages import routes
    d = routes._fcst_norm(direction)
    if 'counterparty' in d and 'receiv' in d:
        return True
    if d and 'receiv' in d:            # 'Owner receives'/'JPM receives' → não é ela
        return False
    if settlement is None:
        return None
    return settlement < 0


# Tolerância de conciliação do Other Products, em BRL. Vale para as DUAS leituras
# da mesma diferença: o status OK/Check de cada linha do Trade Level e o
# `matched` (a luz) dos cards de reconciliação. Números iguais têm de acender a
# mesma cor nos dois lugares — com duas tolerâncias, uma linha sairia verde
# embaixo de um card âmbar e ninguém saberia em qual acreditar.
#
# 20,00 é o pedido do time: abaixo disso é arredondamento de curva entre o B3 e o
# interno, não divergência a investigar. Fica aqui, longe do card, porque quem lê
# a linha do Trade Level precisa achar o número.
_OPS_RECON_TOL = 20.0


def _ops_swap_settling(opb3):
    """(titulos, by_titulo) do Operations B3: quais SWAPs liquidam no dia.

    `titulos` = [(Título, linha), …] com **UMA entrada por swap**, na ordem de
    chegada: Tipo Título = SWAP e a linha aprovada pelo cadastro `opb3-events`.
    O mesmo swap chega uma vez por Tipo Operação (amortização, juros, prêmio) e
    viraria linhas repetidas na tela.

    `by_titulo` = {Título → as linhas daquele título}, sujeitas AOS MESMOS dois
    filtros. É delas que sai o Settlement B3 do Trade Level e, por consequência,
    o lado B3 do card de Swap. Somar todas as linhas do Título (que é o que se
    fazia até aqui) trazia para o valor eventos que a tabela não mostra — o card
    fechava num número que nenhuma linha da tela explicava.

    É a definição do universo de swaps liquidando, e vale para as duas telas
    (Trade Level e Settlement Advice). Duplicá-la deixaria uma tela mostrando um
    swap que a outra não mostra, sem erro em lugar nenhum."""
    from apps.pages import routes
    rules = routes._opb3_event_rules()
    titulos, seen, by_titulo = [], set(), {}
    for rec in (opb3 or []):
        titulo = str(rec.get('Título', '') or '').strip()
        if not titulo:
            continue
        if 'swap' not in routes._fcst_norm(rec.get('Tipo Título', '')):
            continue
        if not routes._opb3_settle_ok(rec, rules):
            continue
        by_titulo.setdefault(titulo.upper(), []).append(rec)
        if titulo.upper() in seen:
            continue
        seen.add(titulo.upper())
        titulos.append((titulo, rec))
    return titulos, by_titulo


def _ops_swap_trade_rows(settle_ref):
    """Linhas de SWAP do Trade Level para a data de liquidação `settle_ref`."""
    from apps.pages import routes
    ref_dt = datetime(settle_ref.year, settle_ref.month, settle_ref.day)
    _jp, opb3 = routes._opb3_load(ref_dt)
    if not opb3:
        return []
    titulos, by_titulo = _ops_swap_settling(opb3)
    if not titulos:
        return []

    # Fontes auxiliares — lidas UMA vez cada, não por linha.
    tipo_maps = routes._opb3_tipo_maps(ref_dt)                       # Título → identificador (LOB)
    terms = _ops_swap_pos_terms(ref_dt)                       # Contrato → (dt op, dt venc)

    # Mesma coleta da página Swap Athena e do aviso, com o CounterParty já
    # resolvido pelo SPN — aqui ele é o ÚLTIMO recurso do nome (o Cpty SPN do OTM
    # vem antes), e mesmo assim tem de ser o nome do cadastro: é por ele que a
    # alíquota de IR é procurada no `swap-ir-client`.
    athena = routes._athena_settlements(ref_dt)
    ai = {c: i for i, c in enumerate(athena.get('columns') or [])}
    by_cetip = {}
    for row in athena.get('rows') or []:
        cet = str(row[ai['CETIP ID']] if 'CETIP ID' in ai else '').strip().upper()
        if cet:
            by_cetip.setdefault(cet, row)

    events = routes._ds_display_collect(ref_dt, 'eventos-swap-jpm', routes._EVENTS_COLUMNS)
    ei = {c: i for i, c in enumerate(events.get('columns') or [])}
    by_contract = {}
    for row in events.get('rows') or []:
        k = str(row[ei['Código do Contrato']] if 'Código do Contrato' in ei else '').strip().upper()
        if k:
            by_contract.setdefault(k, []).append(row)

    # O que substitui o Athena nas operações de EQUITY: o Swap Athena é só de
    # CEM, e sem isto a linha de equity sai com o nome curto da B3 e sem valor.
    eqlink = _ops_equity_link(ref_dt)

    _ojp, otm = routes._otm_load(ref_dt)
    otm_by_trade, otm_spn_by_trade = {}, {}
    for rec in (otm or []):
        tid = str(rec.get('Trade Id', '') or '').strip().upper()
        amt = routes._conf_to_float(rec.get('Amount'))
        if tid and amt is not None:
            otm_by_trade[tid] = otm_by_trade.get(tid, 0.0) + amt
        # Cpty SPN: o identificador da contraparte na PRÓPRIA linha do fluxo. O
        # primeiro não vazio vale — as várias linhas de um trade são do mesmo
        # cliente, e uma delas vir sem SPN não pode apagar o nome.
        if tid and routes._spn_key(rec.get('Cpty SPN', '')) and tid not in otm_spn_by_trade:
            otm_spn_by_trade[tid] = str(rec.get('Cpty SPN', '') or '').strip()

    def _cell(row, idx_map, name):
        i = idx_map.get(name)
        return '' if i is None or i >= len(row) else str(row[i] or '').strip()

    out = []
    for titulo, rec in titulos:
        key = titulo.upper()
        arow = by_cetip.get(key)
        # Equity: o Título casou com um `CLEARING_TRD_ID_*` do Latam e de lá se
        # chegou ao Trade Id do OTM. É o lado que o Athena daria para um swap de
        # CEM — Internal ID, contraparte, valor e curvas.
        eq = eqlink.get(key) or {}
        internal_id = (_cell(arow, ai, 'Kapital ID') if arow else '') or eq.get('internal_id', '')
        # Counterparty: o **Cpty SPN** do OTM resolvido pelo `le-spn` e pelo
        # Reference Data (`_otm_cpty_name`) — um identificador, não um texto
        # livre. O nome do Athena vem depois, porque é a razão social que o
        # cadastro de IR espera; o Nome Simplificado do B3 ('INTRAGMGTFDO') é um
        # apelido de conta e nunca casaria com "BANCO ..." nem com as entidades
        # JPM, então fica só como último recurso para a linha não sair anônima.
        #
        # É o MESMO nome que vai para o cadastro de IR logo abaixo: mostrar um
        # nome e casar a alíquota por outro deixaria quem edita o `swap-ir-client`
        # cadastrando o texto que vê e sem efeito nenhum.
        counterparty = (routes._otm_cpty_name(otm_spn_by_trade.get(internal_id.strip().upper(), '')) or
                        (_cell(arow, ai, 'CounterParty') if arow else '') or
                        eq.get('counterparty', '') or
                        str(rec.get('Contraparte (Nome Simpl.)', '') or '').strip())

        # Type: VCP quando QUALQUER uma das duas pontas do evento indexa em VCP.
        vcp = False
        for erow in by_contract.get(key, []):
            for col in ('PARTE / Indexador', 'CONTRAPARTE / Indexador'):
                if 'vcp' in routes._fcst_norm(_cell(erow, ei, col)):
                    vcp = True
        # Em equity o Type é o ATIVO SUBJACENTE — é ele que distingue uma
        # operação da outra na tela, do jeito que VCP/Calculado distingue os
        # swaps e a mercadoria distingue os termos. VCP/Calculado sai do arquivo
        # de eventos, que não tem essas operações: sem a troca, toda linha de
        # equity apareceria como 'Calculado', que é uma afirmação errada.
        stype = eq.get('underlying', '') if eq else ('VCP' if vcp else 'Calculado')

        settlement = otm_by_trade.get(internal_id.strip().upper()) if internal_id else None
        # Settlement B3: soma das linhas do Título que ENTRAM no universo — os
        # linhas aprovadas pelo `opb3-events`. O mesmo Título costuma
        # trazer outros eventos no arquivo; somá-los dava um total que nenhuma
        # linha da tela explicava, e o card de Swap herdava a diferença.
        # A visão do Operations B3 já vem filtrada para um lado (banco ou MGT),
        # então não há par simétrico se anulando — se aparecer, a soma dá zero e
        # é sinal de que o arquivo veio com as duas pontas.
        vals = [routes._conf_to_float(r.get('Valor')) for r in by_titulo.get(key, [])]
        vals = [v for v in vals if v is not None]
        settlement_b3 = sum(vals) if vals else None

        # Prazo do IR = do TRADE até ESTA liquidação, não até o vencimento do
        # swap: o imposto incide sobre o pagamento que está saindo hoje, e o
        # período que conta é o decorrido até ele. Usar o vencimento alongaria o
        # prazo de um diferencial no meio da vida do swap e BAIXARIA a alíquota.
        # É a mesma conta do Settlement Advice — as duas telas têm de imprimir a
        # mesma alíquota para o mesmo swap no mesmo dia.
        #
        # Em equity o prazo sai do **Trade_Date do Latam**: a posição de swap não
        # tem essas operações, e sem data de operação não há prazo — logo não há
        # alíquota, e a coluna de IR sairia vazia numa liquidação que paga IR.
        op_dt = ((terms.get(routes._fcst_norm_contract(titulo).upper()) or {}).get('op')
                 or eq.get('trade_date'))
        prazo = (settle_ref - op_dt).days if op_dt else None
        rate = _ops_swap_ir_rate(counterparty, prazo,
                                 _ops_cpty_receives(_cell(arow, ai, 'Direction') if arow else '',
                                                    settlement))
        tax = None if (rate is None or settlement is None) else abs(settlement) * rate

        diff = None if (settlement is None or settlement_b3 is None) else settlement - settlement_b3
        out.append({
            'status': 'OK' if (diff is not None and abs(diff) <= _OPS_RECON_TOL) else 'Check',
            # LOB = o TOKEN (EDG · CEM · CEMHYB), não o Código Identificador
            # inteiro que a coluna Type do Operations B3 carrega
            # ('CEM-2026-3184'). É o mesmo vocabulário do Settlement Summary
            # logo acima e do Accrual/Forecast — duas colunas chamadas LOB na
            # mesma página falando línguas diferentes seria o defeito.
            # Sem token reconhecido a célula fica VAZIA (regra do _fcst_lob):
            # pede cadastro em vez de chutar uma LOB.
            # Equity não tem token de LOB no Código Identificador: sem o
            # fallback a coluna ficaria vazia e nada na tela diria que aquela
            # linha é de equity — o cadastro continua vencendo quando responde.
            'lob': routes._fcst_lob(routes._opb3_tipo_for(rec, tipo_maps)) or ('EQUITIES' if eq else ''),
            'counterparty': counterparty,
            'internal_id': internal_id,
            'id_b3': titulo,
            # A B3 registra a operação de equity como SWAP, e é dessa linha que
            # sai o Settlement B3 — trocar o rótulo aqui tiraria essas operações
            # do card de Swap sem colocá-las em card nenhum.
            'product': 'SWAP',
            'type': stype,
            'settlement': _ops_fmt_amt(settlement),
            'settlement_b3': _ops_fmt_amt(settlement_b3),
            'tax_income': _ops_fmt_amt(tax),
            'difference': _ops_fmt_amt(diff),
            # Números CRUS para o Settlement Summary somar. Ele parte destas
            # mesmas linhas, não de uma segunda leitura dos arquivos: reler
            # deixaria as duas tabelas da página livres para se contradizerem.
            # Reformatar o texto de volta para float seria pior ainda — perde o
            # branco de "não deu para calcular", que vira 0 na soma.
            '_settle_n': settlement,
            '_tax_n': tax,
            '_b3_n': settlement_b3,
            # Entidade legal: o e-mail de TED separa BANCO e MGT em dois blocos.
            '_legal': (_cell(arow, ai, 'Owner Legal Entity') if arow else '') or eq.get('legal', ''),
            # Perna interna não gera aviso: ela FICA no Trade Level (é uma
            # operação de verdade, e tirá-la esconderia metade do par) e SAI do
            # Settlement Summary, que é a fonte do documento que vai ao cliente.
            #
            # Só para EQUITY, de propósito. A regra é geral, mas o swap de CEM já
            # roda assim há tempo e ligar o corte para ele aqui apagaria da tela
            # linhas que a mesa usa hoje — é uma decisão de negócio, não um
            # efeito colateral desta correção.
            '_no_advice': bool(eq) and _ops_is_internal_cpty(counterparty, eq.get('spn', '')),
        })
    return out


# ── Other Products › Summary: cards de reconciliação B3 × Interno ────────────
#  Porte dos cards do NDF Summary. A regra que faz um card de reconciliação valer
#  alguma coisa: ele conta EXATAMENTE o que a tabela de baixo mostra. Por isso os
#  dois lados saem das linhas já montadas do Trade Level (`_b3_n` e `_settle_n`),
#  e não de uma segunda varredura do Operations B3 — que traria linhas que a
#  tabela não mostra e deixaria o card e a tabela discordando na tela.
#
#  Consequência a entender: o lado B3 do card de Swap cobre só as linhas que o
#  cadastro `opb3-events` aprova (é o universo do Trade Level). Registrar mais
#  um evento lá faz o card e a tabela crescerem JUNTOS — que é o ponto.
#
#  Família sem Trade Level ainda (hoje só COE) volta `na: True`:
#  a tela mostra um traço em vez de um "Check" âmbar, porque não há divergência —
#  há conta que ainda não é feita. Pintar de âmbar leria como erro de dado.


def _ops_recon(trade_rows):
    """{família → {b3_count, b3_value, int_count, int_value, diff_value, matched,
    na}} + 'total'. SWAP, NDF Commodities e Option têm lado interno; as demais
    famílias entram marcadas como `na` até as suas linhas do Trade Level
    existirem."""
    from apps.pages import routes
    fams = ('swap', 'option', 'ndf', 'coe')
    acc = {k: {'b3_count': 0, 'b3_value': 0.0, 'int_count': 0, 'int_value': 0.0}
           for k in fams + ('total',)}
    by_product = {'SWAP': 'swap', 'OPTION': 'option', 'COE': 'coe',
                  # O Trade Level chama o Termo de Mercadoria de TERMO; o card se
                  # chama NDF Commodities. Mesma família.
                  'TERMO': 'ndf', 'NDF COMMODITIES': 'ndf'}
    seen = set()
    for r in trade_rows:
        fam = by_product.get(str(r.get('product', '') or '').strip().upper())
        if not fam:
            continue
        seen.add(fam)
        b3, internal = r.get('_b3_n'), r.get('_settle_n')
        for k in (fam, 'total'):
            if b3 is not None:
                acc[k]['b3_count'] += 1
                acc[k]['b3_value'] += b3
            if internal is not None:
                acc[k]['int_count'] += 1
                acc[k]['int_value'] += internal
    out = {}
    for k, a in acc.items():
        na = (k != 'total') and (k not in seen)
        out[k] = {
            'b3_count': a['b3_count'], 'b3_value': routes._ndfsum_money(a['b3_value']),
            'int_count': a['int_count'], 'int_value': routes._ndfsum_money(a['int_value']),
            'diff_value': routes._ndfsum_money(a['int_value'] - a['b3_value']),
            # Bate quando a CONTAGEM e o VALOR concordam. Só o valor não basta:
            # duas operações que se anulam dariam zero e passariam por conciliadas.
            'matched': (a['b3_count'] == a['int_count']
                        and abs(a['b3_value'] - a['int_value']) <= _OPS_RECON_TOL),
            'na': na,
        }
    return out


def _ops_ndfc_trade_rows(settle_ref):
    """Linhas de NDF COMMODITIES do Trade Level.

    Saem das MESMAS linhas do Settlement Advice de NDF (`_ndfadv_collect`), e não
    de uma segunda leitura: a tabela e o aviso têm de mostrar o mesmo valor para
    o mesmo contrato. O que muda é só o recorte das colunas.

    Produto **TERMO**, LOB **COMMODITIES**, Type = a commodity do subjacente,
    Internal ID = o identificador do Athena (Nº da Confirmação) e B3 ID = o
    Título do Operations B3.
    """
    from apps.pages import routes
    ref_dt = datetime(settle_ref.year, settle_ref.month, settle_ref.day)
    out = []
    for r in routes._ndfadv_collect(ref_dt):
        internal, b3 = r.get('apurado'), r.get('b3')
        diff = None if (internal is None or b3 is None) else internal - b3
        out.append({
            'status': 'OK' if (diff is not None and abs(diff) <= _OPS_RECON_TOL) else 'Check',
            'lob': 'COMMODITIES',
            'counterparty': r.get('counterparty', ''),
            'internal_id': r.get('internal_id', ''),
            'id_b3': r.get('b3_id', ''),
            'product': 'TERMO',
            'type': r.get('commodity', ''),
            'settlement': _ops_fmt_amt(internal),
            'settlement_b3': _ops_fmt_amt(b3),
            'tax_income': _ops_fmt_amt(r.get('ir')),
            'difference': _ops_fmt_amt(diff),
            '_settle_n': internal,
            '_tax_n': r.get('ir'),
            '_b3_n': b3,
            '_legal': r.get('legal', ''),
        })
    return out


def _ops_opt_trade_rows(settle_ref):
    """Linhas de OPTION do Trade Level.

    Saem das MESMAS linhas do Settlement Advice de Opção (`_optadv_items`, já com
    as correções manuais do dia), pela mesma razão do termo: a tabela e o aviso
    têm de mostrar o mesmo valor para o mesmo contrato. O que muda é só o
    recorte das colunas.

    Produto **OPTION** — é o que faz o card de reconciliação de Option deixar de
    ser `na` e passar a contar. LOB = a classe do subjacente (COMMODITIES,
    EQUITIES, MOEDA), Type = o ativo subjacente, Internal ID = o Nº da
    Confirmação e B3 ID = o Código IF do Operations B3.
    """
    from apps.pages import routes
    ref_dt = datetime(settle_ref.year, settle_ref.month, settle_ref.day)
    out = []
    for r in routes._optadv_items(ref_dt):
        internal, b3 = r.get('apurado'), r.get('b3')
        diff = None if (internal is None or b3 is None) else internal - b3
        out.append({
            'status': 'OK' if (diff is not None and abs(diff) <= _OPS_RECON_TOL) else 'Check',
            'lob': r.get('lob', ''),
            'counterparty': r.get('counterparty', ''),
            'internal_id': r.get('internal_id', ''),
            'id_b3': r.get('b3_id', ''),
            'product': 'OPTION',
            'type': r.get('underlying', ''),
            'settlement': _ops_fmt_amt(internal),
            'settlement_b3': _ops_fmt_amt(b3),
            'tax_income': _ops_fmt_amt(r.get('ir')),
            'difference': _ops_fmt_amt(diff),
            '_settle_n': internal,
            '_tax_n': r.get('ir'),
            '_b3_n': b3,
            '_legal': r.get('legal', ''),
        })
    return out


# ── Other Products › a operação de EQUITY: o lado que o Athena não tem ───────
#  A B3 registra essas operações como SWAP, então elas JÁ entram no Trade Level e
#  no Settlement Advice pelo Operations B3 (`_ops_swap_settling`). O que falta
#  nelas é o outro lado: o **Swap Athena é só de CEM** e não tem linha nenhuma
#  para equity. Sem ele a linha saía com o nome curto da B3 (`SAFRABM`,
#  `INTRAGATACAMAFDO`), sem Internal ID, sem Settlement e sem as curvas — e, sem
#  Settlement, ficava fora do Settlement Summary, que é a fonte do aviso.
#
#  A rota que substitui o Athena para equity tem três paradas:
#
#      Operations B3  --Título-->  Latam Desk Position  --Deal_Ref-->  OTM Settlements
#                                  CLEARING_TRD_ID_INT                 270WI<Deal_Ref>
#                                  CLEARING_TRD_ID_CLNT                270WC<Deal_Ref>
#
#  O mesmo `Deal_Ref` cobre DUAS operações — a de contra o cliente externo e a de
#  contra a nossa entidade (Safra × Atacama) —, e é por isso que o relatório traz
#  os dois identificadores da B3 na mesma linha. Qual das duas pernas é a do
#  Título em mãos sai de QUAL COLUNA casou: `CLEARING_TRD_ID_INT` é a perna
#  interna e leva ao Trade Id `270WI…`; `CLEARING_TRD_ID_CLNT` é a do cliente e
#  leva ao `270WC…`. Partir do Título (e não do OTM) é o que mantém a operação em
#  UMA linha: montar uma família própria a partir do OTM criava uma segunda linha
#  para o mesmo trade, ao lado da que o Operations B3 já produzia.
#
#  Do OTM saem os três valores do aviso, e a regra é a que a mesa usa:
#  **Curva Banco = os fluxos positivos, Curva Cliente = os negativos, Resultado
#  Bruto = a soma dos dois.**
_OPS_EQ_LEG_PREFIX = (('CLEARING_TRD_ID_INT', '270WI'),
                      ('CLEARING_TRD_ID_CLNT', '270WC'))


def _ops_eq_ref_key(v):
    """Chave do de-para Deal_Ref × Trade Id: só os dígitos, sem zeros à esquerda.

    Os dois lados são o mesmo número escrito por sistemas diferentes — um deles
    zera à esquerda conforme a largura do campo — e comparar o texto casaria
    silenciosamente nada (o mesmo tropeço que o `_spn_key` já resolveu)."""
    d = re.sub(r'\D', '', str(v or ''))
    return d.lstrip('0') or d


def _ops_eq_trade_key(trade_id):
    """`270WI0012345` → `('270WI', '12345')`; `(None, '')` fora do padrão.

    O prefixo faz parte da resposta: ele é o que diz QUAL perna do `Deal_Ref` é
    aquele Trade Id. Trade Id sem um dos prefixos conhecidos não vira chave — o
    identificador de outra família não pode casar por acidente com um `Deal_Ref`
    que não é dele."""
    s = str(trade_id or '').strip().upper()
    for _col, pref in _OPS_EQ_LEG_PREFIX:
        if s.startswith(pref):
            return pref, _ops_eq_ref_key(s[len(pref):])
    return None, ''


def _latam_equity_b3_index():
    """{Título da B3 → (Deal_Ref, prefixo do Trade Id, linha do Latam)}.

    Lê o ÚLTIMO Latam Desk Position disponível, não o da data de liquidação: o
    relatório não é diário e a própria página abre no último JSON que existe
    (`_latam_latest_ref`). Procurando o do dia, o de-para ficaria vazio em todo
    dia sem posição nova e a linha sairia sem nome e sem valor, sem que nada na
    tela dissesse por quê.

    As DUAS colunas de clearing entram, cada uma apontando para o seu prefixo de
    Trade Id — é isso que distingue a perna interna da perna do cliente sem
    precisar adivinhar. Primeiro registro vence: o relatório repete a linha por
    vencimento, e os identificadores são do trade, não da parcela."""
    from apps.pages import routes
    ref = routes._latam_latest_ref()
    if ref is None:
        return {}
    _jp, data = routes._latam_load(ref)
    idx = {}
    for rec in (data or []):
        deal_ref = _ops_eq_ref_key(rec.get('Deal_Ref', ''))
        if not deal_ref:
            continue
        for col, pref in _OPS_EQ_LEG_PREFIX:
            b3 = str(rec.get(col, '') or '').strip().upper()
            if b3:
                idx.setdefault(b3, (deal_ref, pref, rec))
    return idx


@_req_cached
def _ops_equity_link(ref):
    """{Título da B3 → o que o Swap Athena teria dito, se tivesse equity}.

    Cada valor traz `internal_id`, `counterparty`, `spn`, `settlement`,
    `curva_banco`, `curva_cliente`, `underlying`, `trade_date` e `legal` — os
    mesmos campos que `_ops_swap_trade_rows` e `_swadv_collect` leem da linha do
    Athena. Montado uma vez por request e passado pronto, porque as duas telas
    fazem exatamente a mesma pergunta.

    Vazio quando não há Latam ou não há OTM: aí a linha continua como estava
    (nome curto da B3, valores em branco), que é melhor do que inventar o par."""
    from apps.pages import routes
    latam = _latam_equity_b3_index()
    if not latam:
        return {}
    _jp, otm = routes._otm_load(ref)
    if not otm:
        return {}

    # Agrupa o OTM por (prefixo, Deal_Ref) — o Trade Id é a identidade do trade e
    # o arquivo traz uma linha por FLUXO de caixa.
    grupos = {}
    for rec in otm:
        pref, chave = _ops_eq_trade_key(rec.get('Trade Id', ''))
        if not pref or not chave:
            continue
        g = grupos.setdefault((pref, chave), {
            'trade_id': str(rec.get('Trade Id', '') or '').strip(),
            'pos': 0.0, 'neg': 0.0, 'tem_valor': False,
            'spn': '', 'name': '', 'legal': '', 'underlying': ''})
        amt = routes._conf_to_float(rec.get('Amount'))
        if amt is not None:
            g['tem_valor'] = True
            if amt >= 0:
                g['pos'] += amt
            else:
                g['neg'] += amt
        # Primeiro não vazio vence em cada campo de identidade: os vários fluxos
        # de um trade são do mesmo cliente, e um deles vir sem SPN não pode
        # apagar o que os outros já disseram.
        for campo, chave_g in (('Cpty SPN', 'spn'), ('Cpty Name', 'name'),
                               ('Owner Legal Entity', 'legal'), ('Underlying', 'underlying')):
            if not g[chave_g]:
                g[chave_g] = str(rec.get(campo, '') or '').strip()

    out = {}
    for b3, (deal_ref, pref, rec_lt) in latam.items():
        g = grupos.get((pref, deal_ref))
        if not g:
            continue
        # O nome vem do REFERENCE DATA pelo Cpty SPN (`_otm_cpty_name`: cadastro
        # `le-spn` quando é entidade nossa, Reference Data quando é cliente). É o
        # mesmo nome que a página OTM Settlements mostra e que o Settlement
        # Summary usa para agrupar — o `SAFRABM` da B3 é um apelido de conta e
        # nunca casaria com o cadastro.
        nome = routes._otm_cpty_name(g['spn']) or g['name']
        out[b3] = {
            'internal_id': g['trade_id'],
            'counterparty': nome,
            'spn': g['spn'],
            'settlement': (g['pos'] + g['neg']) if g['tem_valor'] else None,
            'curva_banco': g['pos'] if g['tem_valor'] else None,
            'curva_cliente': g['neg'] if g['tem_valor'] else None,
            # Ativo subjacente: o que identifica a operação de equity na tela, do
            # jeito que o Type diz VCP no swap e a mercadoria no termo.
            #
            # A cadeia é longa porque NENHUMA das fontes preenche sempre. As duas
            # primeiras colunas do Latam são as de derivativo SOBRE um ativo
            # (opção, barreira) e vêm vazias no swap de equity, onde o próprio
            # INSTRUMENTO é a ação — foi assim que as linhas de EDG apareceram
            # com o Type em branco mesmo já tendo Internal ID e valor. A ordem é
            # do mais específico para o mais genérico, e o `Instrument_ID` fica
            # por último porque é código, não nome. Tudo vazio deixa a célula
            # vazia: pede o cadastro/arquivo, não inventa um subjacente.
            'underlying': (str(rec_lt.get('Underlying_Name', '') or '').strip()
                           or str(rec_lt.get('UNDERLYING_RIC', '') or '').strip()
                           or g['underlying']
                           or str(rec_lt.get('Instrument_Name', '') or '').strip()
                           or str(rec_lt.get('RIC', '') or '').strip()
                           or str(rec_lt.get('Instrument_ID', '') or '').strip()),
            # Data da operação para o PRAZO do IR: a posição de swap não tem
            # essas operações, e sem prazo a alíquota não sai.
            'trade_date': _latam_trade_dt(rec_lt),
            'legal': g['legal'],
        }
    return out


def _latam_trade_dt(rec):
    """Trade_Date do Latam como `date` (None quando não dá para ler). O relatório
    mistura '2026-01-16 00:00:00.0' com '20260108' — `_fcst_parse_date` já
    entende os dois, e a data-sentinela do epoch é descartada como no import."""
    from apps.pages import routes
    d = routes._fcst_parse_date(rec.get('Trade_Date', ''))
    if d is None or (d.year, d.month, d.day) in routes._LATAM_EPOCH:
        return None
    return d.date() if hasattr(d, 'date') else d


def _ops_le_name_keys():
    """(nomes exatos, tokens de LE) das entidades do cadastro `le-spn`.

    É o cadastro que já responde 'esta contraparte é nossa?' no resto da página
    (`_otm_cpty_name` resolve o nome por ele). Uma segunda lista de entidades
    aqui envelheceria sozinha no dia em que a mesa registrasse mais uma.

    O TOKEN existe porque o cadastro nasce com o `Reference Data Name` VAZIO em
    algumas entidades (a ATACAMA é assim no seed), e o nome que chega dos
    arquivos é o da conta por extenso ('ATACAMA FUNDO DE INVESTIMENTO'). Sem ele,
    a perna interna só seria reconhecida depois de alguém preencher a razão
    social na tela — e até lá geraria aviso. Só tokens de 4+ caracteres entram
    como palavra dentro do nome: 'JPM' e 'MGT' são curtos demais para isso e
    apareceriam no meio de um nome de cliente por acaso."""
    from apps.pages import routes
    exatos, tokens = set(), set()
    for r in routes._mapping_rows('le-spn'):
        for campo in ('NAME', 'LE'):
            v = re.sub(r'\s+', ' ', routes._fcst_norm(r.get(campo, ''))).strip()
            if v:
                exatos.add(v)
        le = re.sub(r'[^a-z0-9]+', '', routes._fcst_norm(r.get('LE', '')))
        if len(le) >= 4:
            tokens.add(le)
    return exatos, tokens


def _ops_is_internal_cpty(name, spn=''):
    """A contraparte é perna interna (entidade nossa ou banco do grupo)?

    Não sai aviso de liquidação para ela: o aviso é o documento que se manda ao
    CLIENTE, e a perna de dentro não tem a quem ser avisada.

    Duas fontes, e **nenhuma delas é "o nome começa em BANCO"**. Essa regra é a
    que se enuncia falando, mas ela derrubaria BANCO SAFRA, BANCO BRADESCO e
    BANCO SANTANDER — clientes de verdade, que ficariam sem aviso em silêncio. O
    que se quer dizer com "banco" é o banco DO GRUPO:

      1. cadastro **`le-spn`** — por SPN e por nome. É a lista das nossas
         entidades, e é ela que o resto da página já usa para a mesma pergunta;
      2. **`_pc_is_internal_counterparty`** — o Reference Data
         (`ECONOMIC GROUP = INTERNAL`, por SPN e depois por nome) com o teste de
         intragrupo como último recurso (`banco` **e** `morgan` no nome). É a
         resposta que o Pending Confirmation já dá para decidir o que é operação
         de cliente; uma segunda definição aqui divergiria da primeira.
    """
    from apps.pages import routes
    k = routes._spn_key(spn)
    if k:
        for r in routes._mapping_rows('le-spn'):
            if routes._spn_key(r.get('SPN', '')) == k:
                return True
    n = re.sub(r'\s+', ' ', routes._fcst_norm(name)).strip()
    if not n:
        return False
    exatos, tokens = _ops_le_name_keys()
    if n in exatos:
        return True
    if any(re.search(r'\b%s\b' % re.escape(t), n) for t in tokens):
        return True
    try:
        return bool(routes._pc_is_internal_counterparty(name, spn))
    except Exception:
        return routes._pc_is_intragroup(name)


def _ops_trade_rows(settle_ref):
    """TODAS as linhas do Trade Level da data — hoje SWAP + NDF Commodities +
    OPTION.

    É o único lugar que sabe quais famílias existem. A tela, os cards de
    reconciliação e o e-mail de TED chamam esta função; quando o Trade Level
    ganhou o NDF Commodities, o e-mail de TED continuou montando só o swap porque
    reconstruía a lista por conta própria — e a TED da contraparte de commodities
    simplesmente não era pedida, sem erro nenhum. Uma família nova entra aqui e
    aparece nos três de uma vez.

    Cada família em `try` próprio: uma fonte malformada não pode apagar as linhas
    que as outras já montaram.
    """
    rows = []
    for label, fn in (('swap', _ops_swap_trade_rows),
                      ('NDF commodities', _ops_ndfc_trade_rows),
                      ('option', _ops_opt_trade_rows)):
        try:
            rows += fn(settle_ref)
        except Exception:
            log.error("[ops-trade] falha montando as linhas de %s:\n%s",
                      label, traceback.format_exc())
    return rows


def _ops_fmt_amt(v):
    """#,##0.00 — None vira '' (célula vazia = 'não deu para calcular'), que é
    diferente de 0,00 ('calculei e deu zero')."""
    return '' if v is None else '{:,.2f}'.format(v)


# ── Other Products › Summary › Settlement Summary ────────────────────────────
#  Porte do Settlement Summary do NDF. As regras de Receive/Pay, Settlement Net,
#  Direction, Account e Observation são as MESMAS e vêm das MESMAS funções
#  (`_ndfsum_net_type`, `_ndfsum_account_fmt`, `_ndfsum_obs_auto`) — recopiá-las
#  aqui criaria a segunda cópia de uma regra de dinheiro, que é exatamente o
#  jeito de as duas páginas divergirem sem ninguém perceber.
#
#  A única diferença: no NDF a linha é a CONTRAPARTE; aqui é
#  **contraparte × LOB × produto**, porque a página cobre vários produtos e as
#  colunas Product e LOB existem justamente para separá-los. Consequência a
#  entender: um cliente Total Net com swap e opção sai em DUAS linhas — o net é
#  por produto, não por cliente, que é o recorte do aviso de liquidação.
_OPSSUM_COLS = ('counterparty', 'lob', 'product', 'receive', 'pay', 'net_type',
                'direction', 'account', 'obs')


def _opssum_meta_path(ref):
    """Overlay do dia — a ÚNICA coisa que esta tabela persiste (a observação
    digitada). Fica ao lado dos JSONs do batch de liquidação, na pasta da data."""
    from apps.pages import routes
    return os.path.join(routes.OTM_JSON_ROOT, ref.strftime('%Y'), ref.strftime('%m'), ref.strftime('%d'),
                        'other-products-summary_{}.json'.format(ref.strftime('%Y%m%d')))


def _opssum_meta_load(ref):
    path = _opssum_meta_path(ref)
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        return path, (data if isinstance(data, dict) else {})
    except Exception:
        return path, {}


def _opssum_key(cpty, lob, product):
    """Chave do overlay: contraparte × LOB × produto, normalizada (caixa, acento
    e espaço — `_fcst_norm` cuida dos dois primeiros, o `\\s+` colapsa o espaço
    duplo) para a observação não se perder quando o nome vier grafado diferente
    no dia seguinte."""
    from apps.pages import routes
    return '|'.join(re.sub(r'\s+', ' ', routes._fcst_norm(p)).strip() for p in (cpty, lob, product))


def _opssum_status(meta, cpty, lob, product):
    """Status da linha no overlay do dia: New → Generated → Sent.

    A MESMA chave das duas telas (contraparte × LOB × produto). O Settlement
    Advice mostra o status do contrato pela linha do Settlement Summary a que ele
    pertence — é o mesmo aviso, e duas contagens de estado para o mesmo aviso
    seria o defeito."""
    return (meta.get(_opssum_key(cpty, lob, product)) or {}).get('status') or 'New'


def _opssum_set_status(ref, triples, status):
    """Grava `status` para cada (contraparte, LOB, produto) no overlay do dia."""
    # `session` pelo routes, não pelo import direto: é superfície de patch —
    # o check_swap_advice troca `R.session` por um dict para carimbar o maker.
    from apps.pages import routes
    path, meta = _opssum_meta_load(ref)
    sid = routes.session.get('user_sid', '')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    n = 0
    for cpty, lob, product in triples:
        key = _opssum_key(cpty, lob, product)
        if not key.strip('|'):
            continue
        entry = meta.get(key) or {}
        entry.update({'status': status, 'maker': sid, 'at': now})
        meta[key] = entry
        n += 1
    if n:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        routes._atomic_write_json(path, meta)   # funil: atômico + espelho (§335)
    return n


def _opssum_rows(trade_rows, ref):
    """Linhas do Settlement Summary, netadas a partir das linhas JÁ MONTADAS do
    Trade Level (`_settle_n`/`_tax_n`). Linha sem contraparte ou sem valor fica
    de fora: não há o que liquidar, e entrar com zero inventaria um aviso."""
    from apps.pages import routes
    spn_by_name = routes._ndfsum_refdata_spn()
    cpd = routes._cpd_load()
    _, meta = _opssum_meta_load(ref)
    groups, order = {}, []
    for r in trade_rows:
        s = r.get('_settle_n')
        cpty = str(r.get('counterparty', '') or '').strip()
        if not cpty or s is None:
            continue
        # Perna interna ENTRA aqui e sai só do documento. Esta tabela é a visão
        # de LIQUIDAÇÃO do dia — a perna interna liquida, o dinheiro se move e o
        # total tem de fechar com o Trade Level; cortá-la daqui fazia a operação
        # da entidade nossa (a ATACAMA do par) sumir da tela sem uma palavra.
        # O que não sai é o AVISO: `_swadv_collect` continua pulando a linha
        # marcada, e o e-mail de TED também, porque não se transfere dinheiro
        # para si mesmo. A marca vem de quem monta a linha
        # (`_ops_is_internal_cpty`): repetir o teste aqui criaria uma segunda
        # resposta para a pergunta.
        key = (cpty, str(r.get('lob', '') or ''), str(r.get('product', '') or ''))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((s, abs(r.get('_tax_n') or 0.0), str(r.get('_legal', '') or ''),
                            bool(r.get('_no_advice'))))

    out = []
    for key in sorted(order, key=lambda k: (routes._fcst_norm(k[0]), k[2], k[1])):
        cpty, lob, product = key
        ref_rec = spn_by_name.get(routes._fcst_norm(cpty), {})
        spn = ref_rec.get('spn', '')
        rec_cpd = routes._cpd_find(cpd, spn) if spn else None
        net_type = routes._ndfsum_net_type(rec_cpd)
        # Caixa por trade já líquido de IR: o imposto retido sempre ENCOLHE o
        # valor que se movimenta, qualquer que seja o sinal (regra do NDF).
        vals = [(s - t if s >= 0 else s + t) for s, t, _le, _in in groups[key]]
        recv = sum(v for v in vals if v > 0)
        pay = sum(v for v in vals if v < 0)
        total = recv + pay
        if net_type == 'Total Net':
            recv, pay = (total, 0.0) if total >= 0 else (0.0, total)
        direction = 'RECEIVE' if total >= 0 else 'PAY'
        # Linha que NETA ZERO sai com **0,00 no Receive**, não com as duas
        # células vazias. Vazio se lê como "não deu para calcular", e aqui o zero
        # é o resultado: a operação liquida por valores que se anulam. Fica no
        # Receive porque é o lado que a Direction aponta (`total >= 0` →
        # RECEIVE); pôr nos dois diria que a mesma linha paga e recebe zero.
        zerado = not recv and not pay
        banking = routes._bank_norm((rec_cpd or {}).get('BANKING'))
        entry = meta.get(_opssum_key(cpty, lob, product)) or {}
        out.append({
            # New → Generated (Print Advice do Settlement Advice) → Sent (botão
            # Confirm). O mesmo overlay serve as duas telas.
            'status': _opssum_status(meta, cpty, lob, product),
            'counterparty': cpty,
            'lob': lob,
            'product': product,
            'receive': '{:,.2f}'.format(recv) if (recv or zerado) else '',
            'pay': '{:,.2f}'.format(pay) if pay else '',
            'net_type': net_type,
            'direction': direction,
            # Primeira entidade legal não vazia do grupo — é o bloco (BANCO × MGT)
            # em que a linha entra no e-mail de liberação de TED.
            'legal': next((le for _s, _t, le, _in in groups[key] if le), ''),
            # Perna interna: a linha aparece (liquida), mas não gera aviso nem
            # TED. A tela marca com um selo ao lado do nome — sem ele, a única
            # explicação para a linha nunca sair do `New` seria adivinhação.
            'internal': all(i for _s, _t, _le, i in groups[key]),
            'account': routes._ndfsum_account_fmt(banking, direction),
            # Observação digitada prevalece; sem ela, a classificação automática
            # Internal/External das contas default do cliente.
            'obs': entry.get('obs') or routes._ndfsum_obs_auto(banking),
        })
    return out


# ── Other Products › Summary: por que a tabela está vazia ────────────────────
#  Os widgets leem a posição MAIS RECENTE (com walk-back de pregões); as duas
#  tabelas leem o batch DA DATA escolhida, sem walk-back — a data de liquidação é
#  uma data real, e mostrar o movimento de outro dia sob o rótulo de hoje seria
#  pior do que mostrar nada.
#
#  A consequência é uma tela que se contradiz em silêncio: o card diz "2 swaps
#  liquidando" e as duas tabelas ficam vazias, sem uma palavra sobre o motivo. Foi
#  exatamente assim que a página pareceu quebrada. Este bloco transforma o vazio
#  numa frase — QUAL arquivo falta e qual foi o último dia com batch.
_OPS_SOURCES = (
    # (json_key, rótulo, é indispensável?)
    ('operations-b3',          'Operations B3',   True),    # sem ele, zero linhas SEMPRE
    ('otm-settlement',         'OTM Settlements',  False),  # Settlement (e todo o Settlement Summary)
    ('br-onshore-settlements', 'Swap Athena',      False),  # Internal ID, Counterparty, IR
    ('eventos-swap-jpm',       'Swap Events',      False),  # Type (VCP × Calculado)
)


def _ops_pos_swap_found(ref):
    """A posição DPOSICAO-SWAP existe para `ref`? Mesmo walk-back de
    `_ops_swap_pos_terms` — reusa a função (e o cache do request) em vez de
    varrer os arquivos de novo só para checar existência.

    Ela é quem dá prazo, LOB e, por tabela, o IR. A página que consome este
    diagnóstico já chamou `_ops_swap_pos_terms`, então aqui a resposta sai do
    cache e os até dez `isfile` no share não acontecem.

    A pergunta mudou de "o arquivo está lá" para "o arquivo RENDE alguma
    posição", e é de propósito: um arquivo presente que não devolve contrato
    nenhum (ilegível, vazio, ou num layout que não é o de 146 campos) não dá
    prazo, nem LOB, nem IR — dizer que a fonte está lá mandaria alguém procurar
    o defeito em toda parte menos no arquivo.
    """
    return bool(_ops_swap_pos_terms(ref))


@_req_cached
def _ops_batch_status(ref):
    """Diagnóstico das fontes do dia: o que falta e onde tem batch.

    `@_req_cached` (2026-09-01): o `last_batch` sonda até SESSENTA `isfile`
    dia a dia no share, por request. O dia do `ref` entra na chave, então a
    gravação de um arquivo-dia invalida na hora (bump_cache_gen no funil);
    fora isso o TTL de 5 s cobre refresh/polling.

    `last_batch` procura para trás o dia mais recente com Operations B3 (60 dias
    corridos, teto arbitrário mas suficiente para um mês de férias) — sem essa
    dica a pessoa fica trocando data às cegas até acertar."""
    from apps.pages import routes
    missing, required_missing = [], False
    for key, label, required in _OPS_SOURCES:
        if not os.path.isfile(routes._ds_display_json_path(ref, key)):
            missing.append(label)
            required_missing = required_missing or required
    if not _ops_pos_swap_found(ref):
        missing.append('Posição SWAP (B3)')

    last_batch = None
    probe = ref - timedelta(days=1)
    for _ in range(60):
        if os.path.isfile(routes._ds_display_json_path(probe, 'operations-b3')):
            last_batch = probe.strftime('%Y-%m-%d')
            break
        probe -= timedelta(days=1)

    # Arquivo presente e mesmo assim zero linhas: a pergunta deixa de ser "que
    # arquivo falta" e passa a ser "por que nenhuma linha passou". As duas únicas
    # respostas possíveis são o Tipo Título e o Tipo Operação, então o
    # diagnóstico devolve os NÚMEROS de cada peneira e os valores que estão no
    # arquivo — é o que permite cadastrar a variação em vez de abrir um chamado.
    events = None
    if not required_missing:
        _jp, opb3 = routes._opb3_load(ref)
        rows = opb3 or []
        swap_rows = [r for r in rows if 'swap' in routes._fcst_norm(r.get('Tipo Título', ''))]
        matched, _bt = _ops_swap_settling(rows)
        if swap_rows and not matched:
            found = sorted({str(r.get('Tipo Operação', '') or '').strip()
                            for r in swap_rows if str(r.get('Tipo Operação', '') or '').strip()})
            events = {'rows': len(rows), 'swap_rows': len(swap_rows), 'found': found}
        elif not swap_rows and rows:
            events = {'rows': len(rows), 'swap_rows': 0, 'found': []}
    return {'missing': missing, 'blocking': required_missing,
            'last_batch': last_batch, 'events': events}


# Rótulo do produto no e-mail de TED. UMA constante para o assunto, o cabeçalho
# ao lado do logo e a frase do corpo — três lugares que já nasceram divergindo no
# aviso de NDF (o assunto dizia NDF e o corpo também, mas nada obrigava).
_OPS_TED_LABEL = 'Swap/Opção/Commodities'


# ── Print Advice do Settlement Summary: as TRÊS famílias de uma vez ──────────
#  O Summary é a visão de liquidação do dia inteiro, e o aviso é o documento que
#  sai dela. Gerar um produto de cada vez obrigava a abrir as três telas de
#  Settlement Advice e clicar em três botões na mesma data — e bastava esquecer
#  uma para o cliente ficar sem o aviso daquele produto, sem nada na tela dizendo.
#
#  Cada família reusa EXATAMENTE as funções que o botão da própria tela chama
#  (montagem das linhas, gerador do e-mail, escrita do status): a regra continua
#  morando num lugar só, e este endpoint é só o laço. Uma família que falhar não
#  derruba as outras — o dia costuma ter as três, e perder as duas boas por causa
#  de uma fonte ilegível seria pior do que entregar o que dá.
_OPSADV_FAMILIES = ('swap', 'ndf', 'option')
_OPSADV_LABEL = {'swap': 'Swap', 'ndf': 'NDF Commodities', 'option': 'Option'}

# ── O BLOCKER: valor não identificado não vira aviso ─────────────────────────
#  As colunas de RESULTADO são o aviso. Quando a fonte não devolve o valor, a
#  célula sai em branco — e um aviso de liquidação com o valor em branco é pior
#  do que aviso nenhum: ele é o documento pelo qual o cliente paga ou recebe, e
#  em branco ele não diz quanto, mas parece completo.
#
#  O corte é pela CONTRAPARTE inteira, e não pela linha: o aviso é netado por
#  contraparte (e por commodity, para quem está no `ndfc-advice-split`), então
#  tirar só a linha furada mandaria um total que não fecha com as operações do
#  cliente — o que é exatamente o erro que ninguém percebe.
#
#  As duas colunas por família são o resultado BRUTO e o LÍQUIDO. O IR fica de
#  fora de propósito: ele é derivado, e zero é um valor legítimo.
_OPSADV_REQUIRED = {
    'ndf':    ('Resultado Apurado (R$)', 'Resultado Líquido (R$)'),
    'option': ('Resultado Apurado (R$)', 'Resultado Líquido (R$)'),
    # As duas variantes de cabeçalho do swap (com Vencimento / com Pagamento de
    # Prêmio) têm estas colunas no MESMO lugar, então o índice de qualquer uma
    # das duas serve.
    'swap':   ('Resultado Bruto', 'Valor Líquido'),
}


def _opsadv_block_incomplete(family, rows, headers):
    """(linhas_que_ficam, [bloqueadas]) — tira do aviso as contrapartes com valor
    não identificado.

    `bloqueadas` é `[{counterparty, product, columns, rows}]`, e é o que a tela
    mostra no disclaimer: uma contraparte que some do aviso sem dizer por quê é
    uma contraparte que ninguém vai cobrar."""
    from apps.pages import routes
    faltando = {}
    idx = []
    for nome in _OPSADV_REQUIRED.get(family, ()):
        try:
            idx.append((nome, headers.index(nome)))
        except ValueError:
            # Cabeçalho renomeado: o blocker não pode inventar um índice e cortar
            # a contraparte errada. Avisa e deixa passar, como era antes.
            log.warning('[ops-advice] %s: coluna %r não está no cabeçalho do aviso — '
                        'o blocker não confere essa coluna', family, nome)
    for r in rows:
        cells = r.get('cells') or []
        vazias = [nome for nome, i in idx
                  if i >= len(cells) or not str(cells[i] or '').strip()]
        if not vazias:
            continue
        cp = str(r.get('counterparty', '') or '').strip()
        ent = faltando.setdefault(routes._fcst_norm(cp), {
            'counterparty': cp, 'product': _OPSADV_LABEL.get(family, family),
            'columns': [], 'rows': 0})
        ent['rows'] += 1
        for nome in vazias:
            if nome not in ent['columns']:
                ent['columns'].append(nome)
    if not faltando:
        return rows, []
    kept = [r for r in rows
            if routes._fcst_norm(str(r.get('counterparty', '') or '')) not in faltando]
    for ent in faltando.values():
        log.warning('[ops-advice] %s: aviso de %r BLOQUEADO — %d linha(s) com %s em branco',
                    family, ent['counterparty'], ent['rows'], ', '.join(ent['columns']))
    return kept, list(faltando.values())


def _opsadv_blocked_header(blocked):
    """O disclaimer para a resposta binária (.zip). Base64 de propósito: nome de
    contraparte tem acento, e cabeçalho HTTP é latin-1."""
    return base64.b64encode(json.dumps(blocked, ensure_ascii=False).encode('utf-8')).decode('ascii')


def _opsadv_family_drafts(family, ref):
    """Rascunhos de uma família + a escrita do status.
    Devolve (drafts, erro, bloqueadas)."""
    from apps.pages import routes
    from apps.pages import otc_emails
    try:
        if family == 'swap':
            rows = routes._swadv_email_rows(ref)
            rows, blocked = _opsadv_block_incomplete(family, rows, routes._swadv_email_headers(False))
            drafts = otc_emails.build_swap_settlement_emails(
                rows, routes._swadv_email_headers(False), routes._swadv_email_headers(True),
                ref.strftime('%d/%m/%Y'))
            produto = 'SWAP'
        elif family == 'ndf':
            rows = routes._ndfadv_email_rows(ref)
            rows, blocked = _opsadv_block_incomplete(family, rows, routes._ndfadv_email_headers())
            drafts = otc_emails.build_ndfc_settlement_emails(
                rows, routes._ndfadv_email_headers(), ref.strftime('%d/%m/%Y'),
                split_commodity=routes._ndfc_split_by_commodity)
            # O aviso de NDF Commodities não carimba Generated — nem aqui nem no
            # botão da própria tela. Fazer diferente pelo Summary criaria duas
            # respostas para a mesma pergunta, dependendo de onde se clicou.
            produto = None
        else:
            rows = routes._optadv_email_rows(ref)
            rows, blocked = _opsadv_block_incomplete(family, rows, routes._optadv_email_headers())
            drafts = otc_emails.build_ndfc_settlement_emails(
                rows, routes._optadv_email_headers(), ref.strftime('%d/%m/%Y'),
                split_commodity=routes._ndfc_split_by_commodity, product_label='Opção')
            produto = 'OPTION'
    except Exception:
        log.error('[ops-advice] %s: falha montando os avisos:\n%s', family, traceback.format_exc())
        return [], _OPSADV_LABEL[family], []
    if drafts and produto:
        # Best-effort DE PROPÓSITO, como nos botões das telas: os rascunhos já
        # foram produzidos, e uma falha aqui não pode transformar uma geração
        # bem-sucedida em erro.
        try:
            done = {routes._fcst_norm(d.get('counterparty', '')) for d in drafts}
            with routes._cache_lock:
                _opssum_set_status(ref, [(r['counterparty'], r.get('lob', ''), produto)
                                         for r in rows
                                         if routes._fcst_norm(r.get('counterparty', '')) in done],
                                   'Generated')
        except Exception:
            log.error('[ops-advice] %s: generated-status save failed:\n%s',
                      family, traceback.format_exc())
    return drafts, None, blocked
