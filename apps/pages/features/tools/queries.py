# -*- coding: utf-8 -*-
"""As leituras das Tools: cada tela recebe daqui o contexto pronto.

Nada aqui grava. O que precisa do `routes` (a posição de swap do Live
Position, os cadastros do /mapping) chega por busca ATRASADA — ver
`features/support/infra/persistence.py`.
"""
import os
from datetime import date, timedelta

from apps.pages.features.tools import domain
from apps.pages.platform import swap_flows as _sf
from apps.pages.precificador import (calendario, cdi, contagem, euribor, liquidacao,
                                     renda_fixa, sofr, term_sofr)
from apps.pages.precificador.calendario import obter_calendario, para_data, soma_meses
from apps.pages.precificador.erros import ErroDeDado
from apps.pages import data_store as _store  # noqa: E402


def _R():
    from apps.pages import routes
    return routes


# ── SOFR Index ──────────────────────────────────────────────────────────────

def compor_sofr(form):
    inicio = para_data(form.get('inicio') or '')
    fim = para_data(form.get('fim') or '')
    lookback = int(domain.numero_do_form(form, 'lookback', 'lookback', 0))
    shift = int(domain.numero_do_form(form, 'shift', 'observation shift', 0))
    for nome, valor in (('lookback', lookback), ('observation shift', shift)):
        if valor < 0 or valor > liquidacao.LIMITE_DEFASAGEM:
            raise domain.ErroFormulario('the {nome} must be between 0 and {teto} business days',
                                        nome=nome, teto=liquidacao.LIMITE_DEFASAGEM)
    # margem para trás: lookback e shift buscam fixings antes do início
    margem = 40 + (lookback + shift) * 2
    fixings = sofr.serie_sofr(inicio - timedelta(days=margem), fim + timedelta(days=1))
    if not fixings:
        raise sofr.ErroFed('the NY Fed returned no fixings for that period')
    resultado = sofr.compor(fixings, inicio, fim, lookback, shift)
    conferencia = None
    try:
        indice = sofr.serie_indice(inicio - timedelta(days=5), fim + timedelta(days=1))
        taxa_indice = sofr.compor_por_indice(indice, inicio, fim)
        conferencia = {'taxa': taxa_indice,
                       'diferenca_bp': (taxa_indice - resultado.taxa_composta) * 10000.0}
    except (sofr.ErroFed, ErroDeDado, ValueError):
        conferencia = None          # o índice não cobre a janela; segue sem conferência
    molde, valores = sofr.convencao(lookback, shift)
    return {'r': resultado, 'conferencia': conferencia,
            'convencao': molde.format(**valores),
            'ultimo_fixing': fixings[-1], 'primeiro_fixing': fixings[0]}


# ── Term SOFR ───────────────────────────────────────────────────────────────

def term_sofr_context(referencia, meses):
    """A tela do Term SOFR: a curva IMPORTADA (1, 3, 6 e 12 meses), no mesmo
    desenho da EURIBOR — taxas vigentes, gráfico e valores publicados.

    A fonte é a base que o dropzone alimenta (`term_sofr_b3.json` e o
    `db/tools/term_sofr_b3.db` do espelho), e não o NY Fed: esta página é a
    curva a termo da CME. O overnight e as médias compostas do Fed são a taxa
    REALIZADA e vivem na tela de SOFR Index, ao lado da composição que as usa —
    as duas juntas aqui davam dois quadros de "valores publicados" na mesma
    página, respondendo a perguntas diferentes.

    Base vazia não é erro: é o estado normal de quem ainda não importou, e a
    tela mostra a área de arrastar em vez de um aviso.
    """
    base = term_sofr.carregar()
    ctx = {'curva': None, 'erro': None, 'tabela': {}, 'campos': term_sofr.CAMPOS,
           'referencia': referencia, 'meses': meses, 'vigente': None, 'taxas_vigentes': {},
           'base': None, 'series': [], 'escala_x': [], 'escala_y': [], 'vazio': base.vazio}
    if base.vazio:
        return ctx
    vigente, taxas = base.em(referencia)
    recorte = base.janela(soma_meses(para_data(referencia), -meses), referencia)
    ctx.update({'curva': recorte, 'tabela': recorte.por_data(), 'vigente': vigente,
                'taxas_vigentes': taxas,
                'base': {'inicio': base.inicio, 'fim': base.fim, 'dias': len(base.datas)}})
    ctx.update(series_term_sofr(recorte))
    return ctx


def sofr_publicados(referencia, meses):
    """O que o NY Fed publica ABERTO — overnight, médias de 30/90/180 dias e o
    SOFR Index —, para a tela de SOFR Index mostrar ao lado da composição.

    Mora aqui e não na tela de Term SOFR porque é a taxa REALIZADA: ela é o que
    a composição da mesma página acumula, e o Term SOFR é a cotada de antemão.
    Falha de fonte devolve o `erro` e a tela segue sem o quadro."""
    ctx = {'historico': None, 'erro': None, 'tabela': {}, 'campos': sofr.CAMPOS,
           'vigente': None, 'taxas_vigentes': {}, 'base': None,
           'series': [], 'escala_x': [], 'escala_y': []}
    try:
        completo = sofr.carregar_historico()
        if not completo.datas:
            raise sofr.ErroFed('the local base is empty and the NY Fed did not answer')
        vigente, taxas = completo.em(referencia)
        recorte = completo.janela(soma_meses(referencia, -meses), referencia)
        ctx.update({'historico': recorte, 'tabela': recorte.por_data(), 'vigente': vigente,
                    'taxas_vigentes': taxas,
                    'base': {'inicio': completo.inicio, 'fim': completo.fim,
                             'dias': len(completo.datas)}})
        ctx.update(series_sofr(recorte))
    except sofr.ErroFed as exc:
        ctx['erro'] = str(exc)
    return ctx


_TENOR_POR_MESES = {1: '1 month', 3: '3 month', 6: '6 month', 12: '12 month'}


def term_sofr_taxa(meses, quando):
    """A taxa importada de um prazo numa data. Delega ao `taxa_do_fixing`: duas
    implementações da mesma consulta divergiriam no primeiro caso de borda."""
    taxa, vigente, _motivo = taxa_do_fixing(
        liquidacao.TERM_SOFR, _TENOR_POR_MESES.get(int(meses or 3), '3 month'),
        para_data(quando))
    return taxa, vigente


# ── EURIBOR ─────────────────────────────────────────────────────────────────

def euribor_context(referencia, meses):
    ctx = {'curva': None, 'erro': None, 'tabela': {}, 'url_fonte': euribor.PAGINA,
           'series': [], 'escala_x': [], 'escala_y': [], 'referencia': referencia,
           'meses': meses, 'vigente': None, 'taxas_vigentes': {}, 'base': None}
    try:
        completa = euribor.carregar()
        if not completa.datas:
            raise euribor.ErroEuribor('the local base is empty and the source did not answer '
                                      '— try again in a moment')
        vigente, taxas = completa.em(referencia)
        recorte = completa.janela(soma_meses(referencia, -meses), referencia)
        ctx.update({'curva': recorte, 'tabela': recorte.por_data(), 'vigente': vigente,
                    'taxas_vigentes': taxas,
                    'base': {'inicio': completa.inicio, 'fim': completa.fim,
                             'dias': len(completa.datas)}})
        ctx.update(series_euribor(recorte))
    except euribor.ErroEuribor as exc:
        ctx['erro'] = str(exc)
    return ctx


# ── gráficos (SVG puro, sem biblioteca no cliente) ──────────────────────────

CORES = ['#0066cc', '#f59e0b', '#ef4444', '#0ea5e9', '#8b5cf6']


def _series(datas, tabela, campos, rotulos, largura=900, altura=320, mx=52, my=34):
    if len(datas) < 2:
        return {'series': [], 'escala_x': [], 'escala_y': []}
    valores = [linha[c] for linha in tabela.values() for c in campos if c in linha]
    if not valores:
        return {'series': [], 'escala_x': [], 'escala_y': []}
    y0, y1 = min(valores), max(valores)
    if y1 == y0:
        y0, y1 = y0 - 0.001, y1 + 0.001
    folga = (y1 - y0) * 0.12
    y0, y1 = max(0.0, y0 - folga) if y0 >= 0 else y0 - folga, y1 + folga

    def px(i):
        return mx + i / (len(datas) - 1) * (largura - 2 * mx)

    def py(v):
        return altura - my - (v - y0) / (y1 - y0) * (altura - 2 * my)

    series = []
    for cor, campo in zip(CORES, campos):
        pontos = [(px(i), py(tabela[d][campo])) for i, d in enumerate(datas) if campo in tabela[d]]
        if len(pontos) < 2:
            continue
        series.append({'tenor': rotulos.get(campo, campo), 'cor': cor,
                       'caminho': 'M ' + ' L '.join('{:.2f},{:.2f}'.format(x, y) for x, y in pontos)})
    escala_x = []
    for i in range(5):
        k = round(i * (len(datas) - 1) / 4)
        escala_x.append({'x': px(k), 'rotulo': datas[k].strftime('%m/%Y')})
    escala_y = [{'y': py(y0 + (y1 - y0) * i / 4),
                 'rotulo': '{:.2f}%'.format((y0 + (y1 - y0) * i / 4) * 100)} for i in range(5)]
    return {'series': series, 'escala_x': escala_x, 'escala_y': escala_y}


def series_euribor(curva):
    return _series(curva.datas, curva.por_data(), curva.tenores, {t: t for t in curva.tenores})


def series_sofr(historico):
    return _series(historico.datas, historico.por_data(), historico.campos, dict(sofr.CAMPOS))


def series_term_sofr(curva):
    """Os quatro prazos do Term SOFR no mesmo par de eixos — cinco séries só
    ficam legíveis com escala compartilhada, e é o que o `_series` faz."""
    rotulos = {campo: rotulo for campo, rotulo, _m in term_sofr.CAMPOS}
    return _series(curva.datas, curva.por_data(), curva.campos, rotulos)


# ── Fixed Income ────────────────────────────────────────────────────────────

def calcular_renda_fixa(form):
    indexador = form.get('indexador') or renda_fixa.CDI_REALIZADO
    valor = domain.numero_do_form(form, 'valor', 'invested amount')
    inicio = para_data(form.get('inicio') or '')
    vencimento = para_data(form.get('vencimento') or '')
    bruto_taxa = domain.numero_do_form(form, 'taxa', 'rate')
    if indexador in (renda_fixa.CDI_PERCENTUAL, renda_fixa.CDI_REALIZADO):
        taxa = bruto_taxa / 100.0 if bruto_taxa > 5 else bruto_taxa
    else:
        taxa = domain.taxa_do_form(form, 'taxa', 'rate')
    arredondar = domain.ligado(form, 'arredondar_di')
    acumulado = None
    fator_pronto = dias_uteis = None
    if indexador in renda_fixa.RETROATIVOS:
        if vencimento > date.today():
            raise domain.ErroFormulario(
                'the accrued CDI is realised, not a projection — the end date cannot be '
                'after today ({hoje})', hoje='{:%d/%m/%Y}'.format(date.today()))
        acumulado = cdi.acumular_do_bcb(inicio, vencimento, percentual=taxa, valor=valor,
                                        arredondar=arredondar)
        fator_pronto, dias_uteis = acumulado.fator, acumulado.dias_uteis
    resultado = renda_fixa.calcular(
        valor=valor, inicio=inicio, vencimento=vencimento, indexador=indexador, taxa=taxa,
        cdi_projetado=domain.taxa_do_form(form, 'cdi', 'projected CDI', 0.0),
        ipca_projetado=domain.taxa_do_form(form, 'ipca', 'projected IPCA', 0.0),
        produto=form.get('produto') or 'cdb', arredondar_di=arredondar,
        fator_pronto=fator_pronto, dias_uteis=dias_uteis)
    comparacao = None
    if indexador == renda_fixa.CDI_REALIZADO and acumulado is not None:
        outro = cdi.acumular([cdi.FixingCDI(d.data, d.taxa) for d in acumulado.dias],
                             acumulado.inicio, acumulado.fim, percentual=taxa, valor=valor,
                             arredondar=not arredondar)
        cheio = acumulado if not arredondar else outro
        truncado = outro if not arredondar else acumulado
        comparacao = {'fator_sem_arredondar': cheio.fator, 'fator_arredondado': truncado.fator,
                      'diferenca_fator': cheio.fator - truncado.fator,
                      'diferenca_reais': (cheio.fator - truncado.fator) * valor}
    elif indexador in (renda_fixa.CDI_PERCENTUAL, renda_fixa.CDI_SPREAD):
        comparacao = renda_fixa.diferenca_arredondamento(
            domain.taxa_do_form(form, 'cdi', 'projected CDI', 0.0), resultado.dias_uteis,
            taxa if indexador == renda_fixa.CDI_PERCENTUAL else 1.0, valor=valor)
    return {'r': resultado, 'comparacao': comparacao, 'indexador': indexador,
            'acumulado': acumulado}


# ── Swap Calculator ─────────────────────────────────────────────────────────

def liquidar(form):
    cal_nome = form.get('calendario') or 'ANBIMA'
    resultado = liquidacao.liquidar(
        data_operacao=para_data(form.get('data_operacao') or ''),
        inicio=para_data(form.get('inicio') or ''), fim=para_data(form.get('fim') or ''),
        nocional=domain.numero_do_form(form, 'nocional', 'remaining notional'),
        ponta_ativa=domain.ponta_do_form(form, 'ativa'),
        ponta_passiva=domain.ponta_do_form(form, 'passiva'),
        vencimento=domain.texto_data(form, 'vencimento'),
        base_ajuste=form.get('base_ajuste') or liquidacao.BASE_AUTOMATICA,
        nocional_original=domain.numero_do_form(form, 'nocional_original', 'original notional', 0.0),
        percentual_amortizacao=domain.taxa_do_form(form, 'amortizacao', 'amortisation', 0.0),
        base_amortizacao=form.get('base_amortizacao') or liquidacao.SOBRE_ORIGINAL,
        calendario=obter_calendario(cal_nome),
        arredondar_di=domain.ligado(form, 'arredondar_di'),
        reter_ir=domain.ligado(form, 'reter_ir'))
    return {'r': resultado,
            'comparacao': contagens_lado_a_lado(resultado.inicio, resultado.fim, cal_nome)}


def contagens_lado_a_lado(inicio, fim, cal_nome='ANBIMA'):
    """Cada convenção no mesmo período: os mesmos seis meses valem 0,4881 de
    ano em BUS/252 e 0,5028 em ACT/360."""
    cal = obter_calendario(cal_nome)
    return [{'codigo': codigo, 'nome': nome, 'dias': contagem.dias(codigo, inicio, fim, cal),
             'base': contagem.base(codigo), 'fracao': contagem.fracao(codigo, inicio, fim, cal)}
            for codigo, nome, _ in contagem.CONVENCOES]


# A leitura da posição e do DFLUXO por contrato — e a amortização de um evento
# — mora na platform (`swap_flows`, §452): o Swap VCP faz a mesma pergunta e
# uma feature não importa outra. Os nomes de sempre ficam como aliases, e o
# pré-preenchimento chama por eles (é onde o teste troca).
_POS = _sf.POS
_FLX = _sf.FLX
_celula = _sf.celula
_iso = _sf.iso
_subpastas_num = _sf.subpastas_num
_swap_day_file = _sf.swap_day_file
_fluxos_do_contrato = _sf.fluxos_do_contrato
_periodo_do_evento = _sf.periodo_do_evento
_amortizacao_do_evento = _sf.amortizacao_do_evento
CAMPOS_PREFILL = ('counterparty', 'data_operacao', 'inicio', 'fim', 'vencimento',
                  'nocional', 'nocional_original', 'amortizacao', 'base_amortizacao',
                  'base_ajuste')


def _data_iso(iso):
    """'AAAA-MM-DD' → date, ou None."""
    try:
        y, m, d = str(iso or '').split('-')
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


def _posicao_swap(b3_id):
    """(linha da posição como lista, source_date) ou (None, None)."""
    R = _R()
    alvo = domain.norm(b3_id).replace(' ', '')
    if not alvo:
        return None, None
    path, dref = _swap_day_file('73760_{}_DPOSICAO-SWAP.json')
    if not path:
        return None, None
    try:
        src = R._db_day_records(path) or []
    except Exception:                                       # noqa: BLE001
        return None, None
    # O `Código Identificador` NÃO é uma chave: na instância ele guarda a LOB
    # (`CEM` em toda operação da mesa). Por isso o Contrato é procurado PRIMEIRO
    # em todas as linhas, e só depois o identificador — casando na ordem do
    # arquivo, um `CEM` de outra operação venceria o contrato que se pediu.
    achado_por_ident = None
    for row in src:
        vals = list(row.values())
        if len(vals) < 120:
            # mock esparso da dev: os poucos campos, resolvidos pelo NOME
            contrato = row.get('Contrato', '')
            ident = row.get('Código Identificador', row.get('Codigo Identificador', ''))
        else:
            contrato = _celula(vals, _POS['contrato'])
            ident = _celula(vals, _POS['identificador'])
        item = (vals if len(vals) >= 120 else None, row)
        if alvo == domain.norm(contrato).replace(' ', ''):
            return item, R._b3_dref_to_iso(dref)
        if achado_por_ident is None and alvo == domain.norm(ident).replace(' ', ''):
            achado_por_ident = item
    if achado_por_ident is not None:
        return achado_por_ident, R._b3_dref_to_iso(dref)
    return None, None


def taxa_do_fixing(indexador, tenor, quando):
    """A taxa a termo do prazo na data, da BASE local — `(taxa, data, motivo)`.

    Term SOFR sai do que o dropzone importou (`term_sofr_b3.db`); EURIBOR, da
    base do Banco da Finlândia. As duas guardam a última publicação ANTERIOR
    quando o dia pedido não tem cotação (fim de semana, feriado), que é a taxa
    que de fato valeria — devolver vazio ali faria a tela dizer que não há dado
    quando há.

    `None` com o motivo quando a base está vazia ou não alcança a data: a tela
    deixa o campo em branco e sinalizado, e o número entra à mão. É o mesmo
    contrato do fixing de moeda — uma taxa chutada muda o ajuste inteiro.
    """
    from apps.pages.precificador import euribor as _eu, term_sofr as _ts
    from apps.pages.precificador import liquidacao as _lq
    try:
        if indexador == _lq.EURIBOR:
            curva = _eu.CurvaEuribor.da_base()
            vigente, linha = curva.em(quando)
            taxa = (linha or {}).get(tenor)
            if taxa is None:
                return None, vigente, 'no EURIBOR {} published up to {:%d/%m/%Y}'.format(
                    tenor, quando)
            return taxa, vigente, ''
        base = _ts.carregar()
        if base.vazio:
            return None, None, 'no Term SOFR imported — drop the B3 report on the Term SOFR page'
        meses = _lq._MESES_DO_TENOR.get(tenor, 3)
        taxa = base.taxa(meses, quando)
        if taxa is None:
            return None, None, 'no {}-month Term SOFR up to {:%d/%m/%Y}'.format(meses, quando)
        return taxa, base.em(quando)[0], ''
    except Exception as exc:                                # noqa: BLE001
        _R().log.warning('[tools] fixing %s %s em %s falhou: %s', indexador, tenor, quando, exc)
        return None, None, str(exc)


def _ptax_do_fixing(moeda, fim_iso, deslocamento):
    """PTAX de VENDA da moeda no fixing: `fim` recuado `deslocamento` dias úteis.

    Devolve `(valor, data, erro)`. Falha de rede ou moeda que o BCB não
    boletina voltam com `valor=None` e o motivo — a tela deixa o campo em
    branco e sinalizado, que é a regra: um fixing chutado muda o ajuste inteiro
    e a conta continua fechando consigo mesma.

    O calendário é o ANBIMA (o mesmo do resto do app). O `ptax_moeda` já anda
    para trás sozinho até dez dias, o que resolve o feriado que o calendário
    não previu e o dia corrente antes das 13h.
    """
    from apps.pages.precificador import cambio
    from apps.pages.precificador.calendario import calendario_anbima
    if not fim_iso:
        return None, None, 'no flow end to count the offset from'
    try:
        base = para_data(fim_iso)
    except ErroDeDado:
        return None, None, 'invalid flow end'
    n = int(deslocamento or 0)
    quando = calendario_anbima().workday(base, -n) if n else base
    if str(moeda).upper() not in liquidacao.MOEDAS_AUTOMATICAS:
        return None, quando, '{} is not published in the BCB bulletin'.format(moeda)
    try:
        return cambio.ptax_moeda(moeda, quando).venda, quando, ''
    except Exception as exc:                                # noqa: BLE001
        _R().log.warning('[tools] PTAX %s em %s falhou: %s', moeda, quando, exc)
        return None, quando, str(exc)


def swap_prefill(b3_id):
    """Tudo que o Swap Calculator consegue puxar da posição para um B3 ID.

    Devolve ``{'found': bool, ..., 'fields': {...}, 'ativa': {...},
    'passiva': {...}, 'flows': [...], 'missing': [...], 'assumed': [...]}``.
    Campo que não veio fica VAZIO e entra em `missing` — a tela o sinaliza;
    `assumed` marca o que veio por aproximação (a data da operação, quando a
    posição não traz a `Data operação termo` e a `Data início` responde por
    ela)."""
    R = _R()
    achado, source_date = _posicao_swap(b3_id)
    if achado is None:
        return {'found': False, 'b3_id': b3_id}
    vals, row = achado
    missing, assumed = [], []
    out = {'found': True, 'b3_id': b3_id, 'source_date': source_date,
           'fields': {}, 'ativa': {}, 'passiva': {}, 'flows': [], 'missing': missing,
           'assumed': assumed}
    if vals is None:
        # a posição esparsa da dev só sabe contrato, contraparte e vencimento
        out['contrato'] = str(row.get('Contrato', '') or '')
        out['identificador'] = str(row.get('Código Identificador', '') or '')
        conta = str(row.get('Contraparte', '') or '')
        nome = R._lp_cpty_by_account(conta)
        out['fields']['counterparty'] = nome
        out['fields']['vencimento'] = _iso(row.get('Data vencimento', row.get('Data Vencimento', '')))
        for c in CAMPOS_PREFILL:
            if not out['fields'].get(c):
                missing.append(c)
        for lado in ('ativa', 'passiva'):
            out[lado] = domain.montar_ponta(None, None, None, 1.0, '', None)[0]
            missing.append(lado + '.indexador')
        return out

    contrato = _celula(vals, _POS['contrato'])
    ident = _celula(vals, _POS['identificador'])
    out['contrato'], out['identificador'] = contrato, ident

    # contraparte: pelo documento (Reference Data), senão pela conta CETIP
    nome = R._lp_cpty_name_by_taxid(_celula(vals, _POS['doc_cp'])) \
        or R._lp_cpty_by_account(_celula(vals, _POS['conta_cp']))
    f = out['fields']
    f['counterparty'] = nome or ''
    if not nome:
        missing.append('counterparty')

    # A data da operação é a `Data operação termo`, que é a data de
    # contratação de verdade. Em branco — o swap que não é a termo —, quem
    # responde é a `Data início`, e aí é APROXIMAÇÃO: entra em `assumed`, porque
    # é dessa data que sai o prazo do IR, e errá-la calada erra a alíquota.
    inicio_swap = _iso(_celula(vals, _POS['inicio']))
    data_termo = _iso(_celula(vals, _POS['data_termo']))
    f['data_operacao'] = data_termo or inicio_swap
    if not data_termo:
        (assumed if inicio_swap else missing).append('data_operacao')
    f['vencimento'] = _iso(_celula(vals, _POS['vencimento']))
    if not f['vencimento']:
        missing.append('vencimento')

    rem = domain.numero_da_posicao(_celula(vals, _POS['remanescente']))
    base_val = domain.numero_da_posicao(_celula(vals, _POS['valor_base']))
    orig = domain.numero_da_posicao(_celula(vals, _POS['valor_inicial'])) or base_val
    f['nocional'] = '{:.2f}'.format(rem if rem else (base_val or 0.0)) if (rem or base_val) else ''
    f['nocional_original'] = '{:.2f}'.format(orig) if orig else ''
    if not f['nocional']:
        missing.append('nocional')
    if not f['nocional_original']:
        missing.append('nocional_original')

    # O `Tipo de Contrato` já diz o que liquida: BULLET só tem o pagamento
    # final, CASHFLOW tem fluxos intermediários. Com bullet a base é sempre o
    # valor futuro; com cashflow ela sai das DATAS (fluxo antes do vencimento é
    # intermediário), que é o `auto` do motor.
    tipo_contrato = domain.tipo_de_contrato(_celula(vals, _POS['tipo_contrato']))
    out['tipo_contrato'] = tipo_contrato
    f['base_ajuste'] = (liquidacao.BASE_VALOR_FUTURO if tipo_contrato == 'Bullet'
                        else liquidacao.BASE_AUTOMATICA)

    # O fluxo: a ÚLTIMA `Data de ocorrência do Evento` até hoje — é o que
    # acabou de liquidar, e é o que se quer calcular. Sem fluxo nenhum (bullet,
    # ou DFLUXO ausente) o fim é HOJE, marcado como assumido: um campo de data
    # vazio não deixa a tela nem abrir a conta.
    fluxos = _fluxos_do_contrato(contrato, ident, _data_iso(source_date))
    out['flows'] = fluxos
    hoje = date.today().isoformat()
    # O período de CADA evento é calculado aqui, e não só o do escolhido: trocar
    # o evento no seletor da tela tem de dar a MESMA resposta que abrir nele, e
    # com a regra escrita duas vezes (uma aqui, outra no `tools.js`) as duas
    # divergiam — o `applyFlow` do navegador tomava o `inicio` do próprio evento
    # primeiro, que é justamente o candidato menos confiável.
    tipo_am_pos = R._swapchar_amort_text(_celula(vals, _POS['tipo_amort']))
    for x in fluxos:
        _periodo_do_evento(fluxos, x, inicio_swap, f['data_operacao'], hoje)
        _amortizacao_do_evento(x, tipo_am_pos)
    passados = [x for x in fluxos if x['evento'] and x['evento'] <= hoje]
    escolhido = passados[-1] if passados else (fluxos[0] if fluxos else None)
    if escolhido:
        f['inicio'] = escolhido['p_inicio']
        f['fim'] = escolhido['p_fim']
        if escolhido['p_assumido']:
            assumed.append('inicio')
        out['flow_event'] = escolhido['evento']
        f['base_amortizacao'] = escolhido['p_base_amort']
        if not f['base_amortizacao']:
            missing.append('base_amortizacao')
        f['amortizacao'] = escolhido['p_amort']
        if not f['amortizacao']:
            missing.append('amortizacao')
    else:
        f['inicio'] = inicio_swap
        base_am = domain.base_da_amortizacao(
            R._swapchar_amort_text(_celula(vals, _POS['tipo_amort'])))
        if tipo_contrato == 'Bullet':
            # O bullet não tem fluxo intermediário: o único fluxo dele termina
            # no VENCIMENTO, e o vencimento está na posição. Terminá-lo em
            # HOJE dava um número que não é liquidação nenhuma — é a marcação
            # de um contrato no meio do caminho — e ainda saía marcado como
            # "assumido", quando a data estava na coluna ao lado. Sem
            # vencimento na posição o hoje volta, aí sim como aproximação.
            f['fim'] = f['vencimento'] or hoje
            if not f['vencimento']:
                assumed.append('fim')
            # E o que termina no vencimento amortiza 100%: é o principal
            # inteiro voltando. Coluna `Tipo de amortização` vazia é
            # **At Maturity**, que diz exatamente isso — não é lacuna, e o '0'
            # de antes deixava o saldo seguinte igual ao notional num contrato
            # que acabou. A base é a At Maturity, e não o original: a 100% as
            # três dão o mesmo número, mas as outras duas descrevem uma PARCELA
            # e afirmariam na tela um cronograma de amortização que o bullet não
            # tem. Por isso ela também não entra em `missing`.
            f['base_amortizacao'] = base_am or liquidacao.AT_MATURITY
            f['amortizacao'] = '100'
        else:
            # Cashflow sem DFLUXO é lacuna de verdade: o fluxo que liquidou não
            # está em lugar nenhum, e a tela tem de dizer isso.
            f['fim'] = hoje
            assumed.append('fim')
            f['base_amortizacao'] = base_am or ''
            if not base_am:
                missing.append('base_amortizacao')
            f['amortizacao'] = ''
            missing.append('amortizacao')
    if not f['inicio']:
        missing.append('inicio')

    # as duas pontas — a classificação do índice é do cadastro `tools-swap-index`
    regras = R._mapping_rows('tools-swap-index')
    for k, lado in enumerate(('ativa', 'passiva')):
        codigo = _celula(vals, _POS['indice'][k])
        nome_curva = R._swapindex_name(codigo) if codigo else ''
        nome_classe = _celula(vals, _POS['nome_classe'][k])
        regra = domain.classificar_indice(regras, nome_curva or codigo, nome_classe)
        pct = domain.numero_da_posicao(_celula(vals, _POS['pct'][k]))
        taxa = domain.numero_da_posicao(_celula(vals, _POS['taxa'][k]))
        sinal = domain.sinal_da_posicao(_celula(vals, _POS['sinal'][k]))
        cot = domain.numero_da_posicao(_celula(vals, _POS['cupom_limpo'][k]))
        desloc = domain.numero_da_posicao(_celula(vals, _POS['data_cotacao'][k]))
        campos, faltando = domain.montar_ponta(regra, pct, taxa, sinal, nome_classe, cot,
                                               deslocamento=None if desloc is None else int(desloc))
        campos['fonte'] = {'codigo': codigo, 'curva': nome_curva, 'classe': nome_classe}
        if not regra:
            # A tela já sinaliza (a nota vermelha da ponta escreve o mesmo),
            # mas o log é o que se lê quando a mesa relata "não puxou": ele
            # separa "a posição veio sem índice" de "falta a linha no
            # cadastro", e diz o valor exato que não casou. É WARNING de
            # propósito — na instância o log de módulo só sai a partir dele.
            R.log.warning('[tools] ponta %s sem regra em tools-swap-index '
                          '(codigo=%r curva=%r classe=%r, %d linhas no cadastro)',
                          lado, codigo, nome_curva, nome_classe, len(regras or []))
        # A PTAX do fixing: a data é o FIM DO FLUXO recuado pelo deslocamento
        # que o contrato manda (a `Data de Cotação`), em dias úteis ANBIMA — e
        # o fim do fluxo é hoje quando não há evento, que é o caso "hoje D-2"
        # da mesa. Vale para dólar e para qualquer moeda do boletim do BCB;
        # o que muda entre elas é o código, não a regra.
        if campos.get('indexador') in liquidacao.COM_MOEDA and campos.get('moeda'):
            valor, quando, erro = _ptax_do_fixing(campos['moeda'], f.get('fim'), desloc)
            if valor is None:
                faltando.append('ptax_final')
                campos['ptax_erro'] = erro
            else:
                campos['ptax_final'] = domain.fx8(valor)
                campos['ptax_data'] = quando.isoformat()
        # Taxa a termo (Term SOFR / EURIBOR): o fixing é D-2 úteis do início do
        # fluxo, e a data vai preenchida para a mesa VER de que dia é a taxa.
        # A TAXA vem junto, da base que o dropzone alimenta — o motor já a
        # buscava para calcular, e o campo em branco fazia a tela parecer que
        # ela precisava ser digitada.
        if campos.get('indexador') in liquidacao.COM_FIXING and f.get('inicio'):
            quando = liquidacao.data_de_fixing(f['inicio'])
            campos['data_fixing'] = quando.isoformat()
            taxa_idx, vigente, motivo = taxa_do_fixing(
                campos['indexador'], campos.get('tenor') or '3 month', quando)
            if taxa_idx is None:
                faltando.append('taxa_indice')
                campos['fixing_erro'] = motivo
            else:
                campos['taxa_indice'] = '{:.8f}'.format(taxa_idx * 100.0)
                campos['fixing_data'] = vigente.isoformat() if vigente else ''
        out[lado] = campos
        missing.extend('{}.{}'.format(lado, c) for c in faltando)
    return out
