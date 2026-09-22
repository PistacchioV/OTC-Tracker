# -*- coding: utf-8 -*-
"""As leituras das Tools: cada tela recebe daqui o contexto pronto.

Nada aqui grava. O que precisa do `routes` (a posição de swap do Live
Position, os cadastros do /mapping) chega por busca ATRASADA — ver
`features/support/infra/persistence.py`.
"""
import os
from datetime import date, datetime, timedelta

from apps.pages.features.tools import domain
from apps.pages.features.tools.infra import memoria_xlsx
from apps.pages.platform import swap_flows as _sf
from apps.pages.platform import settlement as _st
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
    # As duas pontas de ENTRADA voltam no resultado porque a memória de cálculo
    # precisa do que foi CONTRATADO: o `PontaLiquidada` guarda o fator, não a
    # taxa nem o percentual do CDI que o produziram.
    pontas = {liquidacao.ATIVA: domain.ponta_do_form(form, 'ativa'),
              liquidacao.PASSIVA: domain.ponta_do_form(form, 'passiva')}
    regra_ir = regra_ir_do_cliente(form.get('counterparty'))
    resultado = liquidacao.liquidar(
        data_operacao=para_data(form.get('data_operacao') or ''),
        inicio=para_data(form.get('inicio') or ''), fim=para_data(form.get('fim') or ''),
        nocional=domain.numero_do_form(form, 'nocional', 'remaining notional'),
        ponta_ativa=pontas[liquidacao.ATIVA],
        ponta_passiva=pontas[liquidacao.PASSIVA],
        vencimento=domain.texto_data(form, 'vencimento'),
        base_ajuste=form.get('base_ajuste') or liquidacao.BASE_AUTOMATICA,
        nocional_original=domain.numero_do_form(form, 'nocional_original', 'original notional', 0.0),
        percentual_amortizacao=domain.taxa_do_form(form, 'amortizacao', 'amortisation', 0.0),
        base_amortizacao=form.get('base_amortizacao') or liquidacao.SOBRE_ORIGINAL,
        calendario=obter_calendario(cal_nome),
        arredondar_di=domain.ligado(form, 'arredondar_di'),
        reter_ir=domain.ligado(form, 'reter_ir'), regra_ir=regra_ir)
    return {'r': resultado, 'pontas': pontas, 'regra_ir': regra_ir,
            'comparacao': contagens_lado_a_lado(resultado.inicio, resultado.fim, cal_nome)}


def regra_ir_do_cliente(counterparty):
    """A alíquota cadastrada para a contraparte (`swap-ir-client`) e as faixas
    do `swap-ir-term` — a MESMA leitura do Trade Level e do Settlement Advice,
    pelas funções da platform (§479). Sem contraparte não há exceção, e as
    faixas do cadastro valem do mesmo jeito."""
    excecao, cliente = _st._swap_ir_excecao(counterparty or '')
    return liquidacao.RegraIR(excecao=excecao, cliente=cliente,
                              faixas=tuple(_st._swap_ir_faixas()))


def ler_descricao(texto, atuais):
    """A leitura de uma denominação digitada na tela sobre os campos ATUAIS da
    ponta — a mesma função do pré-preenchimento, para a resposta ser a mesma."""
    campos = domain.aplicar_descricao(dict(atuais), texto)
    # O texto colado na tela que diz `100.00% Close 20-Sep-24` busca o
    # fechamento como o pré-preenchimento — a regra é uma só.
    return aplicar_cupom_limpo(campos)


def memoria_de_calculo(form):
    """A memória de cálculo do que a tela acabou de mostrar — `(bytes, nome)`.

    Refaz a conta pela MESMA função da tela, em vez de guardar o resultado
    entre os dois requests: resultado de swap carregado na sessão morre com o
    processo e volta divergente do formulário que foi editado depois de
    calcular. Recalcular é barato — a série do CDI do período já está no memo
    — e o arquivo sai, por construção, igual ao que a tela mostra para o mesmo
    formulário.
    """
    calculo = liquidar(form)
    r = calculo['r']
    conteudo = memoria_xlsx.construir(
        r, calculo['pontas'],
        cetip_id=str(form.get('b3_id') or '').strip(),
        contraparte=str(form.get('counterparty') or '').strip(),
        calendario=form.get('calendario') or 'ANBIMA',
        reter_ir=domain.ligado(form, 'reter_ir'),
        arredondar_di=domain.ligado(form, 'arredondar_di'),
        regra_ir=calculo['regra_ir'])
    return conteudo, domain.nome_memoria(form.get('b3_id'), form.get('counterparty'), r.fim,
                                         produto='Swap')


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


def _preco_da_celula(texto):
    """O fechamento que o `fetch_ohlc` escreveu, de volta a número — ou `None`.

    A linha vem FORMATADA para a tela (`'{:,.6f}'`, o `_num` do `quotes`), então
    um papel acima de mil traz a vírgula de MILHAR: `float('7,656.979800')`
    levanta `ValueError`, e levantava para FORA do prefill inteiro — o laço não
    estava protegido, e a tela dizia "Could not read the swap position" numa
    perna de equity cujo preço passou de 999,99. Abaixo disso a mesma conta
    funcionava, e foi por isso que o defeito pareceu ser "de alguns contratos".
    Foi o ^GSPC a 7.656,98.

    `None` é "esta célula não tem preço", e o chamador segue para a linha
    seguinte: célula ilegível não pode derrubar a busca do fechamento, muito
    menos o pré-preenchimento da tela."""
    s = str(texto or '').strip()
    if not s:
        return None
    try:
        return float(s.replace(',', ''))
    except ValueError:
        return None


def _preco_do_fixing(ativo, fim_iso, deslocamento):
    """FECHAMENTO do papel no fixing: `fim` recuado `deslocamento` dias úteis.

    Devolve `(valor, data, erro)`, o mesmo contrato do `_ptax_do_fixing` e pela
    mesma razão: preço chutado muda o ajuste inteiro e a conta continua
    fechando consigo mesma. Sem preço, o campo fica em branco e SINALIZADO.

    Três coisas que não são óbvias:

    - a coluna é **Close**, não Adj Close. O contrato liquida pelo preço que o
      pregão fechou; o ajustado reescreve a série a cada provento e faria o
      mesmo swap dar resultados diferentes conforme o dia em que se abre a
      tela;
    - o deslocamento é o MESMO da `Data de Cotação` do contrato (02 = D-2), em
      dias úteis ANBIMA — a regra que a PTAX já seguia;
    - o dia do fixing pode não ter pregão (feriado de bolsa que o calendário
      ANBIMA não conhece, papel sem negócio). Vale então o último fechamento
      ANTES dele, dentro de uma janela curta — é o que a mesa faz à mão, e a
      data volta junto para a tela dizer de que dia é o preço.
    """
    from apps.pages import quotes
    from apps.pages.precificador.calendario import calendario_anbima
    codigo = str(ativo or '').strip()
    if not codigo:
        return None, None, 'the position did not say which share'
    if not fim_iso:
        return None, None, 'no flow end to count the offset from'
    try:
        base = para_data(fim_iso)
    except ErroDeDado:
        return None, None, 'invalid flow end'
    n = int(deslocamento or 0)
    quando = calendario_anbima().workday(base, -n) if n else base
    simbolo = quotes.symbol_for(_R()._mapping_rows('quotes-equity'), codigo)
    if not simbolo:
        return None, quando, ('no symbol registered for {} in the quotes-equity '
                              'mapping'.format(codigo))
    try:
        _cols, linhas = quotes.fetch_ohlc(simbolo, quando - timedelta(days=15), quando)
    except Exception as exc:                                # noqa: BLE001
        _R().log.warning('[tools] cotação de %s (%s) em %s falhou: %s',
                         codigo, simbolo, quando, exc)
        return None, quando, str(exc)
    # As linhas vêm da mais recente para a mais antiga: a primeira com
    # fechamento é o último pregão até o fixing.
    for linha in linhas or []:
        fecho = _preco_da_celula(linha[2] if len(linha) > 2 else None)
        if fecho is None:
            continue
        try:
            dia = datetime.strptime(str(linha[0]), '%d/%m/%Y').date()
        except (ValueError, TypeError):
            continue
        if dia <= quando:
            return fecho, dia, ''
    return None, quando, 'no {} close up to {:%d/%m/%Y}'.format(simbolo, quando)


def aplicar_cupom_limpo(campos, faltando=None):
    """Equity cujo preço inicial é um PERCENTUAL DE UM FECHAMENTO (mesa,
    21/09/2026): a denominação diz `Preco in ativo - 100.00% Close 20-Sep-24`, e
    o `Cupom Limpo` da posição é esse percentual — NÃO o preço. O preço inicial
    é o fechamento do papel naquele pregão × o cupom.

    Só age quando a DENOMINAÇÃO declarou o cupom (`cupom_limpo` preenchido por
    ela): sem isso a perna segue como sempre, com o Cupom Limpo da posição no
    preço inicial. Busca o fechamento quando há data; sem data (`% Spot`) ou sem
    cotação, o preço inicial fica em BRANCO e sinalizado — a mesa digita o
    fechamento no campo ao lado e a tela refaz a conta."""
    if campos.get('indexador') != liquidacao.EQUITY or not campos.get('cupom_limpo'):
        return campos
    try:
        cupom = float(str(campos['cupom_limpo']).replace(',', '.'))
    except ValueError:
        cupom = None
    fechamento = None
    if campos.get('cupom_data'):
        valor, quando, erro = _preco_do_fixing(campos.get('ativo'), campos['cupom_data'], 0)
        if valor is None:
            campos['close_erro'] = erro
        else:
            fechamento = valor
            campos['preco_close'] = '{:.6f}'.format(valor)
            campos['close_data'] = quando.isoformat()
    preco = domain.preco_inicial_do_cupom(cupom, fechamento)
    # O que o `montar_ponta` pôs ali era o PERCENTUAL: sai, mesmo sem o preço.
    campos['preco_inicial'] = '' if preco is None else '{:.6f}'.format(preco)
    if faltando is not None:
        if preco is None and 'preco_inicial' not in faltando:
            faltando.append('preco_inicial')
        if preco is not None and 'preco_inicial' in faltando:
            faltando.remove('preco_inicial')
    return campos


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
        # A taxa DO FLUXO vence a da posição (mesa, 22/09/2026): o DFLUXO traz
        # `Taxa de Juros Parte/Contraparte` por EVENTO, e o contrato pode ter
        # um spread diferente em cada fluxo — a posição guarda um número só. No
        # 25C04803529 a posição dizia CDI − 11,95% e o fluxo calculado, − 11,90%:
        # R$ 535 mil de diferença contra a planilha da mesa. Sem taxa no fluxo
        # (ou sem DFLUXO), vale a da posição; o sinal já vem aplicado
        # (`swap_flows.taxa_do_fluxo`).
        taxa_do_fluxo = False
        if escolhido:
            t_fx = (escolhido.get('taxa_juros') or [None, None])[k]
            if t_fx is not None:
                taxa, sinal = abs(t_fx), (-1.0 if t_fx < 0 else 1.0)
                taxa_do_fluxo = True
        cot = domain.numero_da_posicao(_celula(vals, _POS['cupom_limpo'][k]))
        desloc = domain.numero_da_posicao(_celula(vals, _POS['data_cotacao'][k]))
        campos, faltando = domain.montar_ponta(
            regra, pct, taxa, sinal, nome_classe, cot,
            deslocamento=None if desloc is None else int(desloc),
            fixing_ipca_posicao=_celula(vals, _POS['fixing_ipca'][k]))
        campos['fonte'] = {'codigo': codigo, 'curva': nome_curva, 'classe': nome_classe}
        if taxa_do_fluxo:
            campos['fonte']['taxa'] = 'dfluxo'
        # A `Denominação` da curva (VCP) diz o que as colunas não dizem — o
        # multiplicador da taxa, o spread, a contagem, o D-n da PTAX (§479).
        # Lida ANTES das buscas de fixing abaixo, que dependem do que ela diz.
        domain.aplicar_descricao(campos, _celula(vals, _POS['denominacao'][k]), faltando)
        # A tela só mostra descrição e multiplicador na perna cuja curva É
        # VCP (pelo `swap-index`) ou que traz Denominação — na perna comum os
        # dois campos só poluiriam.
        campos['vcp'] = bool(campos.get('descricao')) or domain.norm(nome_curva) == 'vcp'
        if campos.get('ptax_offset'):
            try:
                desloc = int(float(campos['ptax_offset']))
            except ValueError:
                pass
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
            quando = liquidacao.data_de_fixing(f['inicio'], indexador=campos['indexador'])
            campos['data_fixing'] = quando.isoformat()
            taxa_idx, vigente, motivo = taxa_do_fixing(
                campos['indexador'], campos.get('tenor') or '3 month', quando)
            if taxa_idx is None:
                faltando.append('taxa_indice')
                campos['fixing_erro'] = motivo
            else:
                campos['taxa_indice'] = '{:.8f}'.format(taxa_idx * 100.0)
                campos['fixing_data'] = vigente.isoformat() if vigente else ''
        # Equity: o preço FINAL é o fechamento do papel no fixing. O inicial é
        # o do contrato — o Cupom Limpo da posição, posto pelo `montar_ponta` —,
        # SALVO quando a denominação diz que esse cupom é um percentual de um
        # fechamento: aí o preço é fechamento × cupom (`aplicar_cupom_limpo`).
        if campos.get('indexador') == liquidacao.EQUITY:
            aplicar_cupom_limpo(campos, faltando)
            valor, quando, erro = _preco_do_fixing(campos.get('ativo'), f.get('fim'), desloc)
            if valor is None:
                faltando.append('preco_final')
                campos['preco_erro'] = erro
            else:
                campos['preco_final'] = '{:.6f}'.format(valor)
                campos['preco_data'] = quando.isoformat()
        out[lado] = campos
        missing.extend('{}.{}'.format(lado, c) for c in faltando)
    return out


# ── NDF Calculator · Unwind NDF Calculator · Option Calculator ───────────────
# O motor é o `precificador/derivativos.py` (puro). Aqui se lê o formulário e,
# quando o fixing/a paridade vêm em BRANCO, busca-se a PTAX de venda do BCB pela
# MESMA função do Swap Calculator — e a resposta diz de que dia ela é.

def _ptax_ou_digitado(form, campo, rotulo, moeda, data_iso, deslocamento):
    """`(valor, nota)`: o que a mesa digitou, ou a PTAX de venda do dia (D-n úteis
    ANBIMA de `data_iso`). Sem número e sem PTAX é erro com o MOTIVO — fixing
    chutado muda a conta inteira e ela continua fechando consigo mesma.

    **O campo volta PREENCHIDO com a taxa usada** (mesa, 21/09/2026), marcado
    como automático (`<campo>_auto`): é ele que a mesa confere, e a taxa só no
    quadro do resultado obrigava a procurar do outro lado da tela o número que a
    conta usou. Enquanto a marca estiver lá o Calculate REBUSCA — senão trocar o
    vencimento deixaria a PTAX do vencimento anterior no campo, calada; digitar
    no campo apaga a marca (o `tools.js`), e aí vale o digitado.

    **Data de fixing no FUTURO não tem PTAX**: o `ptax_moeda` anda para trás
    sozinho e devolveria a última cotação como se fosse a do fixing."""
    bruto = str(form.get(campo) or '').strip()
    automatico = str(form.get(campo + '_auto') or '').strip() == '1'
    if bruto and not automatico:
        return domain.decimal(bruto, rotulo), ''
    if str(moeda or '').upper() == liquidacao.SEM_CONVERSAO:
        return 1.0, ''
    n = int(deslocamento or 0)
    alvo = para_data(data_iso)
    quando = calendario.calendario_anbima().workday(alvo, -n) if n else alvo
    if quando > date.today():
        raise domain.ErroFormulario(
            '{rotulo}: the fixing date ({quando}) is still in the future — there is no PTAX '
            'for it yet, type the rate', rotulo=rotulo, quando='{:%d/%m/%Y}'.format(quando))
    valor, quando, erro = _ptax_do_fixing(moeda, data_iso, deslocamento)
    if valor is None:
        raise domain.ErroFormulario('{rotulo}: type it in — {motivo}', rotulo=rotulo,
                                    motivo=erro or 'no PTAX for that day')
    return valor, 'PTAX {} {:%d/%m/%Y}'.format(str(moeda).upper(), quando)


def _de_volta_ao_campo(campo, valor, nota):
    """O que o Calculate escreve de volta no formulário: a taxa USADA e a marca
    de automática (só quando ela veio da PTAX)."""
    return {campo: domain.fx8(valor), campo + '_auto': '1' if nota else ''}


def _inteiro(form, campo, padrao):
    bruto = str(form.get(campo) or '').strip()
    if not bruto:
        return padrao
    try:
        return int(float(bruto.replace(',', '.')))
    except ValueError:
        raise domain.ErroFormulario('{campo}: a whole number of business days', campo=campo)


def calcular_ndf(form):
    from apps.pages.precificador import derivativos
    moeda = (form.get('moeda') or 'USD').strip().upper()
    vencimento = para_data(form.get('vencimento') or '')
    offset = _inteiro(form, 'ptax_offset', 1)
    mercadoria = _e_mercadoria(form.get('classe') or '')
    paridade, nota_par, update = 1.0, '', {}
    if mercadoria:
        # O fixing é o PREÇO do ativo (do Quotes, pelo B3 ID) — a PTAX aqui
        # seria a cotação da moeda no lugar do preço da mercadoria. Em branco é
        # erro dizendo de onde ele vem; a PTAX é a PARIDADE, que leva a reais.
        bruto = str(form.get('fixing') or '').strip()
        if not bruto:
            raise domain.ErroFormulario(
                'fixing: for a commodity forward it is the PRICE of the underlying — pull it '
                'with the B3 ID (it comes from Quotes) or type it in')
        fixing, nota = domain.decimal(bruto, 'fixing'), ''
        paridade, nota_par = _ptax_ou_digitado(form, 'paridade', 'FX rate', moeda,
                                               vencimento.isoformat(), offset)
        update = _de_volta_ao_campo('paridade', paridade, nota_par)
    else:
        fixing, nota = _ptax_ou_digitado(form, 'fixing', 'fixing', moeda, vencimento.isoformat(), offset)
        update = _de_volta_ao_campo('fixing', fixing, nota)
    r = derivativos.liquidar_ndf(
        nocional=domain.numero_do_form(form, 'nocional', 'notional'),
        taxa_termo=domain.numero_do_form(form, 'taxa_termo', 'forward rate'),
        fixing=fixing, posicao=form.get('posicao') or '',
        fixo_em_reais=domain.ligado(form, 'fixo_em_reais'),
        isento_ir=domain.ligado(form, 'isento_ir'), paridade=paridade)
    return {'r': r, 'moeda': moeda, 'vencimento': vencimento, 'fixing_nota': nota,
            'paridade_nota': nota_par, 'mercadoria': mercadoria, 'form_update': update}


def calcular_unwind_ndf(form):
    from apps.pages.precificador import derivativos
    moeda = (form.get('moeda') or 'USD').strip().upper()
    liquidacao_dt = para_data(form.get('liquidacao') or '')
    vencimento = para_data(form.get('vencimento') or '')
    # DU em branco OU marcado como automático (`du_auto`) é CONTADO — a marca é o
    # que impede o número de uma data anterior de sobreviver à troca da data. O
    # digitado manda: é como se reproduz o DU do aviso do Athena.
    du_digitado = (str(form.get('du') or '').strip()
                   if str(form.get('du_auto') or '').strip() != '1' else '')
    du = (_inteiro(form, 'du', 0) if du_digitado
          else derivativos.dias_uteis_ate(liquidacao_dt, vencimento))
    original = str(form.get('nocional_original') or '').strip()
    r = derivativos.recomprar_ndf(
        nocional=domain.numero_do_form(form, 'nocional', 'unwound notional'),
        strike=domain.numero_do_form(form, 'strike', 'strike'),
        taxa_recompra=domain.numero_do_form(form, 'taxa_recompra', 'termination rate'),
        taxa_pre=domain.taxa_do_form(form, 'taxa_pre', 'pre rate', 0.0),
        du=du, posicao=form.get('posicao') or '',
        fixo_em_reais=domain.ligado(form, 'fixo_em_reais'),
        nocional_original=domain.decimal(original, 'original notional') if original else None,
        ja_recomprado=domain.numero_do_form(form, 'ja_recomprado', 'unwound before', 0.0))
    return {'r': r, 'moeda': moeda, 'liquidacao': liquidacao_dt, 'vencimento': vencimento,
            'du_contado': not du_digitado,
            'form_update': {'du': str(int(du)), 'du_auto': '' if du_digitado else '1'}}


def calcular_opcao(form):
    from apps.pages.precificador import derivativos
    moeda = (form.get('moeda') or liquidacao.SEM_CONVERSAO).strip().upper()
    exercicio = para_data(form.get('exercicio') or '')
    # Um preço por linha (ou separados por `;`): um é a vanilla, vários a asiática.
    brutos = [b for b in str(form.get('fixings') or '').replace(';', '\n').split('\n') if b.strip()]
    fixings = [domain.decimal(b, 'fixing price') for b in brutos]
    paridade, nota = _ptax_ou_digitado(form, 'paridade', 'FX rate', moeda, exercicio.isoformat(),
                                       _inteiro(form, 'ptax_offset', 1))
    par_premio = str(form.get('paridade_premio') or '').strip()
    r = derivativos.liquidar_opcao(
        tipo=form.get('tipo') or '', lado=form.get('lado') or '',
        strike=domain.numero_do_form(form, 'strike', 'strike'),
        quantidade=domain.numero_do_form(form, 'quantidade', 'quantity'),
        fixings=fixings, paridade=paridade,
        premio_unitario=domain.numero_do_form(form, 'premio_unitario', 'unit premium', 0.0),
        paridade_premio=domain.decimal(par_premio, 'premium FX rate') if par_premio else None)
    return {'r': r, 'moeda': moeda, 'exercicio': exercicio, 'paridade_nota': nota,
            'form_update': (_de_volta_ao_campo('paridade', paridade, nota)
                            if moeda != liquidacao.SEM_CONVERSAO else {})}


# ── B3 ID → a posição preenche a calculadora (NDF, recompra e opção) ─────────
# O mesmo esquema do Swap Calculator: a mesa digita o B3 ID e a posição do último
# dia útil preenche o que sabe. O que não veio fica em BRANCO e vai em `missing`
# (a tela sinaliza em vermelho); o que veio por aproximação vai em `assumed`.
#
# A fonte é o MESMO coletor da tela de Live Position (`_lpndf_collect`,
# `_lpopt_collect`), não uma segunda leitura do arquivo: a calculadora e a
# posição têm de mostrar o mesmo contrato do mesmo jeito. As células vêm
# FORMATADAS para a tela, então número e data são lidos com tolerância.

def _num_tela(texto, taxa=False):
    """Número de uma célula de TELA da posição, ou None — a mesma regra do
    `numero_flex` da vertical de Unwinds (que lê esta MESMA posição): o ÚLTIMO
    separador manda, `587,224.31` e `587.224,31` são o mesmo número, e com um
    separador só três dígitos depois dele é MILHAR (`1,234` = 1234).

    `taxa=True` desliga essa última parte: uma taxa `5.374` tem três casas e é
    5,374 — lida como milhar viraria 5374, e a conta fecharia consigo mesma."""
    t = str(texto or '').strip()
    if not t or t in ('-', '\u2014'):
        return None
    neg = t.startswith('-') or (t.startswith('(') and t.endswith(')'))
    t = t.strip('()').lstrip('+-').replace('%', '').replace(' ', '').strip()
    ult_v, ult_p = t.rfind(','), t.rfind('.')
    if ult_v >= 0 and ult_p >= 0:
        dec = max(ult_v, ult_p)
        t = t[:dec].replace(',', '').replace('.', '') + '.' + t[dec + 1:]
    elif ult_v >= 0 or ult_p >= 0:
        i = max(ult_v, ult_p)
        milhar = (not taxa) and len(t) - i - 1 == 3
        t = (t[:i] + t[i + 1:]) if milhar else (t[:i] + '.' + t[i + 1:])
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _data_tela(texto):
    """`dd/mm/aaaa`, ISO ou `aaaammdd` → ISO; o que não é data → ''."""
    s = str(texto or '').strip()
    if len(s) == 8 and s.isdigit():
        s = '{}-{}-{}'.format(s[:4], s[4:6], s[6:])
    try:
        return para_data(s).isoformat()
    except ErroDeDado:
        return ''


def _linha_da_posicao(coletor, b3_id, chaves):
    """(células por coluna, source_date) da linha cujo valor numa das `chaves`
    é o id pedido — a PRIMEIRA chave em todas as linhas antes da segunda (um
    identificador repetido não pode vencer o contrato que se pediu)."""
    alvo = domain.norm(b3_id).replace(' ', '')
    if not alvo:
        return None, None
    dados = coletor(datetime.now())
    ci = {c: i for i, c in enumerate(dados.get('columns') or [])}
    for chave in chaves:
        i = ci.get(chave)
        if i is None:
            continue
        for row in dados.get('rows') or []:
            if i < len(row) and domain.norm(row[i]).replace(' ', '') == alvo:
                return ({c: (str(row[k] or '').strip() if k < len(row) else '')
                         for c, k in ci.items()}, dados.get('source_date'))
    return None, dados.get('source_date')


_POS_COMPRADO = ('COMPRAD', 'COMPRA', 'LONG')
_POS_VENDIDO = ('VENDED', 'VENDID', 'VENDA', 'SHORT')


def _e_documento(v):
    """A célula é um CPF/CNPJ (cru ou mascarado), e não um nome? O teste é a
    ausência de LETRA — o mesmo `parece_documento` da vertical de Unwinds."""
    t = str(v or '').strip()
    if not t or any(ch not in '0123456789./- ' for ch in t):
        return False
    return 10 <= len(''.join(ch for ch in t if ch.isdigit())) <= 14


def _contraparte_ndf(cel):
    """`(nome, aviso)` da contraparte — a MESMA regra da vertical de Unwinds
    (`contraparte_da_posicao`, §488). Numa conta GUARDA-CHUVA o `Nome da
    Contraparte` é o TITULAR (o banco), e quem identifica o cliente é a coluna
    do CPF/CNPJ, que a tela já troca pelo NOME quando o documento tem cadastro.
    Quem diz se a conta é guarda-chuva é o `b3-accounts` (`_b3_is_omnibus`).
    Sem cadastro o nome fica VAZIO avisando — nunca cai no titular."""
    cru = cel.get('CPF/CNPJ da Contraparte', '')
    titular = cel.get('Nome da Contraparte', '')
    doc = cru if _e_documento(cru) else ''
    nome_cnpj = '' if (doc or not cru) else cru
    try:
        omnibus = bool(_R()._b3_is_omnibus(cel.get('Codigo da Contraparte', '')))
    except Exception:                                       # noqa: BLE001
        omnibus = False
    if omnibus:
        if nome_cnpj:
            return nome_cnpj, None
        return '', {'code': 'cpty_not_registered', 'params': {'taxid': doc}}
    return (titular or nome_cnpj), None


def _datas_de_verificacao_ndf(cel):
    """As datas em que o termo de MERCADORIA verifica o preço: o bloco `Média
    Asiática (data) N`; sem ele, a `Data de Fixing do Ativo Subjacente`; sem
    ela, o vencimento."""
    asiaticas = []
    for coluna, valor in cel.items():
        if domain.norm(coluna).startswith('media asiatica (data)'):
            iso = _data_tela(valor)
            if iso:
                asiaticas.append(para_data(iso))
    if asiaticas:
        return sorted(set(asiaticas))
    for coluna in ('Data de Fixing do Ativo Subjacente', 'Data de Vencimento'):
        iso = _data_tela(cel.get(coluna))
        if iso:
            return [para_data(iso)]
    return []


def _e_mercadoria(classe):
    return 'commodit' in domain.norm(classe)


def _ndf_da_posicao(b3_id):
    from apps.pages.precificador import derivativos
    cel, fonte = _linha_da_posicao(_R()._lpndf_collect, b3_id, ('Contrato', 'Codigo Identificador'))
    if cel is None:
        return None, fonte
    lado = cel.get('Descricao da posicao do Participante', '').upper()
    posicao = (derivativos.COMPRADO if any(t in lado for t in _POS_COMPRADO)
               else derivativos.VENDIDO if any(t in lado for t in _POS_VENDIDO) else '')
    # O SALDO é `Valor Base no registro − Valor Antecipado` (§488): o antecipado
    # é o acumulado JÁ recomprado, em moeda estrangeira; coluna vazia numa
    # posição que existe é "nunca foi recomprado", zero.
    registro = _num_tela(cel.get('Valor Base no registro'))
    antecipado = _num_tela(cel.get('Valor Antecipado')) or 0.0
    contraparte, aviso_cpty = _contraparte_ndf(cel)
    venc = _data_tela(cel.get('Data de Vencimento'))
    fix = _data_tela(cel.get('Data de Fixing da Moeda'))
    offset = None
    if venc and fix:
        try:
            offset = calendario.calendario_anbima().dias_uteis(para_data(fix), para_data(venc))
        except ErroDeDado:
            offset = None
    return {
        'ativo': cel.get('Codigo do Ativo Subjacente', ''),
        'datas_ativo': _datas_de_verificacao_ndf(cel),
        'contrato': cel.get('Contrato', ''), 'contraparte': contraparte,
        'aviso_contraparte': aviso_cpty,
        'emissao': _data_tela(cel.get('Data de Emissao')),
        'classe': cel.get('Classe do Ativo Subjacente', ''),
        'moeda': (_moeda_iso(cel.get('Simbolo da Moeda', ''))
                  or _moeda_iso(_subjacente(cel.get('Codigo do Ativo Subjacente', '')).get('Moeda'))),
        'posicao': posicao,
        'registro': registro, 'antecipado': antecipado,
        'saldo': None if registro is None else max(registro - antecipado, 0.0),
        'taxa': (_num_tela(cel.get('Taxa Forward'), taxa=True)
                 or _num_tela(cel.get('Taxa a Termo em Reais'), taxa=True)),
        'vencimento': venc, 'offset': offset,
    }, fonte


def _do_contrato(pos):
    """O que a tela mostra do CONTRATO, só para leitura: contraparte, data de
    emissão e classe do ativo subjacente (mesa, 21/09/2026)."""
    return {'counterparty': pos['contraparte'], 'data_emissao': pos['emissao'],
            'classe': pos['classe']}


def _moeda_do_form(codigo, faltando, campo='moeda'):
    conhecidas = {m.codigo for m in liquidacao.MOEDAS}
    if codigo in conhecidas and codigo != liquidacao.SEM_CONVERSAO:
        return codigo
    faltando.append(campo)
    return ''


def ndf_prefill(b3_id):
    """NDF Calculator: a liquidação no vencimento do que SOBRA no contrato."""
    pos, fonte = _ndf_da_posicao(b3_id)
    if pos is None:
        return {'found': False, 'b3_id': b3_id, 'source_date': fonte}
    falt, campos = [], {}
    campos['moeda'] = _moeda_do_form(pos['moeda'], falt)
    for campo, valor, fmt in (('nocional', pos['saldo'], '{:.2f}'), ('taxa_termo', pos['taxa'], None)):
        if valor:
            campos[campo] = fmt.format(valor) if fmt else domain.fx8(valor)
        else:
            campos[campo] = ''
            falt.append(campo)
    campos['vencimento'] = pos['vencimento'] or ''
    if not pos['vencimento']:
        falt.append('vencimento')
    campos['posicao'] = pos['posicao']
    if not pos['posicao']:
        falt.append('posicao')
    if pos['offset'] is not None:
        campos['ptax_offset'] = str(int(pos['offset']))
    # a posição da B3 é SEMPRE em moeda estrangeira (o fixo em reais já foi
    # dividido pelo strike no registro — §488)
    campos['fixo_em_reais'] = False
    campos['isento_ir'] = bool(pos['contraparte'] and _R()._ndfc_ir_exempt(pos['contraparte']))
    # O fixing já vem no CAMPO quando a data dele passou (a PTAX de venda do
    # BCB, D-n do vencimento); no futuro fica em branco — ainda não existe.
    campos['fixing'], campos['fixing_auto'] = '', ''
    campos['paridade'], campos['paridade_auto'], campos['ativo'] = '', '', pos['ativo']
    nota_fix = None
    notas_merc = []
    if _e_mercadoria(pos['classe']):
        # Termo de MERCADORIA: o nocional é QUANTIDADE, o fixing é o PREÇO do
        # ativo — do Quotes, × 0,01 quando o Index B3 diz que ele é cotado em
        # centavos —, e a PARIDADE (a PTAX) leva a diferença a reais. Na
        # asiática o fixing é a média da série; série pela metade não é média.
        precos, sem, fonte_q, erro_q = _fixings_do_quotes(pos['classe'], pos['ativo'], pos['datas_ativo'])
        if precos and not sem:
            campos['fixing'] = domain.fx8(sum(p for _d, p, _dia in precos) / len(precos))
            notas_merc.append({'code': 'fixings_from_quotes', 'params': {
                'n': len(precos), 'fonte': fonte_q, 'de': '{:%d/%m/%Y}'.format(precos[0][0]),
                'ate': '{:%d/%m/%Y}'.format(precos[-1][0])}})
            if '\u00d7' in fonte_q:
                notas_merc.append({'code': 'quoted_in_cents', 'params': {'ativo': pos['ativo']}})
        else:
            falt.append('fixing')
            notas_merc.append({'code': 'fixings_missing', 'params': {
                'n': len(sem), 'motivo': erro_q,
                'datas': ', '.join('{:%d/%m/%Y}'.format(d) for d in sem[:6])}})
        if pos['vencimento'] and campos['moeda']:
            n = int(pos['offset']) if pos['offset'] is not None else 1
            alvo = para_data(pos['vencimento'])
            quando = calendario.calendario_anbima().workday(alvo, -n) if n else alvo
            if quando <= date.today():
                valor, quando, erro = _ptax_do_fixing(campos['moeda'], pos['vencimento'], n)
                if valor is not None:
                    campos['paridade'], campos['paridade_auto'] = domain.fx8(valor), '1'
                    notas_merc.append({'code': 'parity_ptax', 'params': {
                        'moeda': campos['moeda'], 'data': '{:%d/%m/%Y}'.format(quando)}})
    elif pos['vencimento'] and campos['moeda']:
        n = int(pos['offset']) if pos['offset'] is not None else 1
        alvo = para_data(pos['vencimento'])
        quando = calendario.calendario_anbima().workday(alvo, -n) if n else alvo
        if quando <= date.today():
            valor, quando, erro = _ptax_do_fixing(campos['moeda'], pos['vencimento'], n)
            if valor is not None:
                campos['fixing'], campos['fixing_auto'] = domain.fx8(valor), '1'
                nota_fix = {'code': 'fixing_ptax', 'params': {
                    'moeda': campos['moeda'], 'data': '{:%d/%m/%Y}'.format(quando)}}
            else:
                falt.append('fixing')
                nota_fix = {'code': 'fixing_failed', 'params': {'motivo': erro}}
    campos.update(_do_contrato(pos))
    notas = ([nota_fix] if nota_fix else []) + notas_merc
    if pos['antecipado']:
        notas.append({'code': 'unwound_before', 'params': {'valor': pos['antecipado']}})
    if pos['aviso_contraparte']:
        notas.append(pos['aviso_contraparte'])
    return {'found': True, 'b3_id': pos['contrato'] or b3_id, 'source_date': fonte,
            'counterparty': pos['contraparte'], 'fields': campos, 'missing': falt, 'assumed': [],
            'notes': notas}


def unwind_ndf_prefill(b3_id):
    """Unwind NDF Calculator: o contrato original. A taxa da recompra e a pré
    são do NEGÓCIO de hoje — não existem na posição e ficam para a mesa."""
    pos, fonte = _ndf_da_posicao(b3_id)
    if pos is None:
        return {'found': False, 'b3_id': b3_id, 'source_date': fonte}
    falt, assumido, campos = [], [], {}
    campos['moeda'] = _moeda_do_form(pos['moeda'], falt)
    campos['strike'] = domain.fx8(pos['taxa']) if pos['taxa'] else ''
    if not pos['taxa']:
        falt.append('strike')
    campos['vencimento'] = pos['vencimento'] or ''
    if not pos['vencimento']:
        falt.append('vencimento')
    campos['posicao'] = pos['posicao']
    if not pos['posicao']:
        falt.append('posicao')
    campos['nocional_original'] = '{:.2f}'.format(pos['registro']) if pos['registro'] else ''
    campos['ja_recomprado'] = '{:.2f}'.format(pos['antecipado'])
    # O nocional recomprado é do negócio; nasce com o SALDO (a recompra total),
    # que é o caso comum — e marcado como aproximação, para a mesa conferir.
    if pos['saldo']:
        campos['nocional'] = '{:.2f}'.format(pos['saldo'])
        assumido.append('nocional')
    else:
        campos['nocional'] = ''
        falt.append('nocional')
    campos['fixo_em_reais'] = False
    # o DU fica em branco AQUI de propósito: a tela o conta na hora (as duas datas
    # acabaram de chegar) pelo `/api/tools/business-days`, com a data de
    # liquidação que está no FORMULÁRIO — que a posição não conhece
    campos['taxa_recompra'], campos['taxa_pre'], campos['du'], campos['du_auto'] = '', '', '', ''
    falt.extend(['taxa_recompra', 'taxa_pre'])
    campos.update(_do_contrato(pos))
    return {'found': True, 'b3_id': pos['contrato'] or b3_id, 'source_date': fonte,
            'counterparty': pos['contraparte'], 'fields': campos, 'missing': falt,
            'assumed': assumido,
            'notes': [pos['aviso_contraparte']] if pos['aviso_contraparte'] else []}


def _moeda_iso(texto):
    """O código ISO de uma moeda como a POSIÇÃO a escreve — o próprio código
    (`USD`), o nome (`DOLAR DOS EUA`) ou o código Sisbacen (`220`). Quem traduz é
    o cadastro `currency-base` (`DESCRICAO DO CAMPO`/`CODIGO DE CADASTRO` →
    `SIMBOLO`): nome de moeda não se fixa no código. '' quando nada responde."""
    bruto = str(texto or '').strip().upper()
    if not bruto:
        return ''
    conhecidas = {m.codigo for m in liquidacao.MOEDAS}
    if bruto in conhecidas:
        return bruto
    if 'REAL' in bruto or bruto in ('R$', 'BRR'):
        return liquidacao.SEM_CONVERSAO
    alvo, digitos = domain.norm(bruto), bruto.lstrip('0')
    try:
        linhas = _R()._mapping_rows('currency-base') or []
    except Exception:                                       # noqa: BLE001
        linhas = []
    for row in linhas:
        simbolo = str(row.get('SIMBOLO') or '').strip().upper()
        if not simbolo:
            continue
        if (domain.norm(row.get('DESCRICAO DO CAMPO', '')) == alvo
                or (bruto.isdigit() and str(row.get('CODIGO DE CADASTRO') or '').strip().lstrip('0') == digitos)):
            return simbolo if simbolo in conhecidas else ''
    return ''


def _subjacente(ativo):
    """A linha do Index B3 (`Subjacente`) do ativo, ou {}."""
    try:
        return _R()._subjacente_by_code().get(str(ativo or '').strip().upper()) or {}
    except Exception:                                       # noqa: BLE001
        return {}


def _fator_de_centavos(ativo):
    """0.01 quando a mercadoria é COTADA EM CENTAVOS — `Fator Conversao` = 0,01
    no Index B3 —, senão 1.0 (mesa, 21/09/2026). É a MESMA regra da casa para o
    strike do booking recap (`_is_cents_factor`: só 0,01 é centavos, e a regra é
    do ATIVO, nunca da moeda): o registro na B3 é em UNIDADE de moeda (o strike
    do CTZ6 é 0,6960 US$/lb) e a bolsa cota em centavos (81,15 ¢/lb) — sem o
    fator a opção sairia cem vezes dentro do dinheiro."""
    from apps.pages import otc_boxparse
    return 0.01 if otc_boxparse._is_cents_factor(_subjacente(ativo).get('Fator Conversao')) else 1.0


def _contraparte_opcao(cel):
    """`(nome, nota)` da contraparte de uma OPÇÃO (mesa, 21/09/2026) — o `Nome
    simplificado` da posição é apelido de conta (`JPMORGANBM`,
    `INTRAGLAWTONFDO`) e não identifica ninguém:

      * conta GUARDA-CHUVA (a 73760.10-2 — quem diz é o `b3-accounts`, pelo
        TIPO, nunca o número no código): o cliente é o `CPF/CNPJ Cliente
        Contraparte`, que a tela já resolve pelo Reference Data. Documento sem
        cadastro deixa o nome VAZIO avisando — o titular ali é o banco;
      * qualquer outra conta: o nome sai do Reference Data pela CONTA CETIP
        (`_lp_cpty_by_account`, que recusa guarda-chuva e conta com mais de um
        nome). Sem cadastro, fica o apelido da posição — AVISANDO que é ele."""
    R = _R()
    conta = cel.get('Contraparte (Conta)', '')
    doc = cel.get('CPF/CNPJ Cliente Contraparte', '')
    apelido = cel.get('Contraparte (Nome simplificado)', '')
    try:
        omnibus = bool(R._b3_is_omnibus(conta))
    except Exception:                                       # noqa: BLE001
        omnibus = False
    if omnibus:
        if doc and not _e_documento(doc):
            return doc, None
        return '', {'code': 'cpty_not_registered', 'params': {'taxid': doc}}
    nome = ''
    try:
        nome = R._lp_cpty_by_account(conta) or ''
    except Exception:                                       # noqa: BLE001
        nome = ''
    if nome:
        return nome, None
    # a coluna do documento, quando a posição a traz resolvida, também responde
    if doc and not _e_documento(doc):
        return doc, None
    return apelido, {'code': 'cpty_short_name', 'params': {'conta': conta, 'apelido': apelido}}


def _fixings_do_quotes(classe, ativo, datas):
    """Os preços de verificação de uma opção, do QUOTES (mesa, 21/09/2026) —
    `(precos, faltando, fonte, erro)`: `precos` = [(data pedida, preço, data do
    pregão)], `faltando` = as datas que ainda não têm preço (futuras ou sem
    pregão até lá).

    A fonte sai da CLASSE do ativo, que é como a tela de Quotes se divide:
    taxa de câmbio → a PTAX de VENDA do BCB da moeda base; commodities → o
    cadastro `quotes-commodity` (com o `"MY"` do vencimento); o resto →
    `quotes-equity`. Nenhum de-para no código: símbolo que falta é CADASTRO.

    UMA chamada para a série inteira (a asiática tem dezenas de datas), e a
    mesma regra do `_preco_do_fixing`: vale o Close — não o Adj Close — do
    pregão da data ou, sem pregão nela, o último ANTES dela."""
    from apps.pages import quotes
    datas = sorted({d for d in datas if d})
    if not datas:
        return [], [], '', 'the position has no verification date'
    hoje = date.today()
    passadas = [d for d in datas if d <= hoje]
    futuras = [d for d in datas if d > hoje]
    if not passadas:
        return [], futuras, '', ''
    ini, fim = passadas[0] - timedelta(days=15), passadas[-1]
    cl = domain.norm(classe)
    try:
        if 'cambio' in cl:
            moeda = str(ativo or '').strip().upper()[:3]
            _cols, linhas = quotes.fetch_ptax(moeda, ini, fim)
            serie, fonte = [(l[0], l[3]) for l in linhas], 'PTAX {} (BCB, ask)'.format(moeda)
        else:
            chave = 'quotes-commodity' if 'commodit' in cl else 'quotes-equity'
            simbolo = quotes.symbol_for(_R()._mapping_rows(chave), ativo)
            if not simbolo:
                return [], datas, '', ('no symbol registered for {} in the {} mapping'
                                       .format(ativo or '(blank)', chave))
            _cols, linhas = quotes.fetch_ohlc(simbolo, ini, fim)
            serie, fonte = [(l[0], l[2] if len(l) > 2 else None) for l in linhas], simbolo
    except Exception as exc:                                # noqa: BLE001
        _R().log.warning('[tools] fixings de %s (%s) falharam: %s', ativo, classe, exc)
        return [], datas, '', str(exc)
    # Commodity cotada em CENTAVOS (Fator Conversão 0,01 no Index B3): o preço do
    # Quotes é multiplicado pelo fator, para ficar na unidade do strike da B3.
    fator = _fator_de_centavos(ativo) if 'commodit' in cl else 1.0
    if fator != 1.0:
        fonte = '{} \u00d7 {:g}'.format(fonte, fator)
    pregoes = []
    for dia_txt, celula in serie:
        preco = _preco_da_celula(celula)
        if preco is not None:
            preco = preco * fator
        try:
            dia = datetime.strptime(str(dia_txt), '%d/%m/%Y').date()
        except (ValueError, TypeError):
            continue
        if preco is not None:
            pregoes.append((dia, preco))
    pregoes.sort(reverse=True)                  # do mais recente ao mais antigo
    precos, sem = [], list(futuras)
    for d in passadas:
        achado = next(((dia, p) for dia, p in pregoes if dia <= d), None)
        if achado is None:
            sem.append(d)
        else:
            precos.append((d, achado[1], achado[0]))
    return precos, sorted(sem), fonte, ''


def _datas_de_verificacao(cel):
    """As datas em que a opção verifica o preço: o bloco `Média Asiática (data)
    N` da posição (a asiática); sem ele, a `Data de fixing do ativo subjacente`;
    sem ela, o vencimento."""
    asiaticas = []
    for coluna, valor in cel.items():
        if domain.norm(coluna).startswith('media asiatica (data)'):
            iso = _data_tela(valor)
            if iso:
                asiaticas.append(para_data(iso))
    if asiaticas:
        return sorted(set(asiaticas))
    for coluna in ('Data de fixing do ativo subjacente', 'Data Vencimento'):
        iso = _data_tela(cel.get(coluna))
        if iso:
            return [para_data(iso)]
    return []


def opcao_prefill(b3_id):
    """Option Calculator: o contrato da posição de opções. Os preços de
    verificação são do mercado e ficam para a mesa."""
    from apps.pages.precificador import derivativos
    cel, fonte = _linha_da_posicao(_R()._lpopt_collect, b3_id,
                                   ('Código IF', 'Combinação de operações'))
    if cel is None:
        return {'found': False, 'b3_id': b3_id, 'source_date': fonte}
    falt, assumido, campos, notas = [], [], {}, []
    tipo = domain.norm(cel.get('Tipo de Opção', ''))
    campos['tipo'] = (derivativos.CALL if ('call' in tipo or 'compra' in tipo)
                      else derivativos.PUT if ('put' in tipo or 'venda' in tipo) else '')
    if not campos['tipo']:
        falt.append('tipo')
    # `Posição da Parte` é a da PARTE do registro. Na posição do banco a parte é
    # o banco — mas num registro de cliente × cliente não é, e o lado decide o
    # SINAL: vai preenchido e marcado como aproximação, com a parte na nota.
    lado = domain.norm(cel.get('Posição da Parte', ''))
    campos['lado'] = (derivativos.TITULAR if 'titular' in lado
                      else derivativos.LANCADOR if ('lancador' in lado or 'lançador' in lado) else '')
    if campos['lado']:
        assumido.append('lado')
        notas.append({'code': 'side_of_party',
                      'params': {'parte': cel.get('Parte (Nome simplificado)', '')}})
    else:
        falt.append('lado')
    strike = _num_tela(cel.get('Strike (valor)'), taxa=True)
    campos['strike'] = domain.fx8(strike) if strike else ''
    if not strike:
        falt.append('strike')
        if _num_tela(cel.get('Strike (percentual)')):
            notas.append({'code': 'strike_in_percent',
                          'params': {'pct': cel.get('Strike (percentual)', '')}})
    qtd = _num_tela(cel.get('Quantidade'))
    antecipada = _num_tela(cel.get('Quantidade Antecipada')) or 0.0
    if qtd:
        campos['quantidade'] = '{:.8f}'.format(max(qtd - antecipada, 0.0)).rstrip('0').rstrip('.')
    else:
        campos['quantidade'] = ''
        falt.append('quantidade')
    campos['exercicio'] = _data_tela(cel.get('Data Vencimento'))
    if not campos['exercicio']:
        falt.append('exercicio')
    premio = _num_tela(cel.get('Prêmio Unitário'), taxa=True)
    campos['premio_unitario'] = domain.fx8(premio) if premio else ''
    # A moeda do PREÇO. Quem diz se o strike já está em reais é a própria
    # posição — `Strike/Limitador/Barreiras em Reais` (S/N): com `S` não há
    # conversão; com `N` o preço é na moeda cotada e a paridade leva a reais.
    em_reais = domain.norm(cel.get('Strike/Limitador/Barreiras em Reais', ''))[:1]
    # O nome da moeda (`DOLAR DOS EUA`) vira código pelo cadastro `currency-base`;
    # coluna vazia, responde a `Moeda` do próprio ativo no Index B3.
    ativo = cel.get('Ativo subjacente / Moeda base', '')
    if em_reais == 's':
        campos['moeda'] = liquidacao.SEM_CONVERSAO
    else:
        campos['moeda'] = (_moeda_iso(cel.get('Moeda do ativo / Moeda cotada', ''))
                           or _moeda_iso(_subjacente(ativo).get('Moeda')))
        if not campos['moeda']:
            falt.append('moeda')
    campos['paridade'], campos['paridade_auto'], campos['paridade_premio'] = '', '', ''
    # A PARIDADE já vem no campo ao buscar (mesa, 21/09/2026): a PTAX de venda da
    # moeda do preço, D-n úteis do exercício — e o `n` sai da própria posição, pela
    # `Data de fixing da moeda do ativo subjacente` (sem ela, o D-1 de costume).
    # Marcada como automática: o Calculate a rebusca se o exercício mudar. Data
    # de fixing no FUTURO fica em branco — essa PTAX ainda não existe.
    if campos['moeda'] and campos['moeda'] != liquidacao.SEM_CONVERSAO and campos['exercicio']:
        n = 1
        fix_moeda = _data_tela(cel.get('Data de fixing da moeda do ativo subjacente'))
        if fix_moeda:
            try:
                n = max(calendario.calendario_anbima().dias_uteis(
                    para_data(fix_moeda), para_data(campos['exercicio'])), 0)
            except ErroDeDado:
                n = 1
        campos['ptax_offset'] = str(int(n))
        alvo = para_data(campos['exercicio'])
        quando = calendario.calendario_anbima().workday(alvo, -n) if n else alvo
        if quando <= date.today():
            valor, quando, erro = _ptax_do_fixing(campos['moeda'], campos['exercicio'], n)
            if valor is not None:
                campos['paridade'], campos['paridade_auto'] = domain.fx8(valor), '1'
                notas.append({'code': 'parity_ptax', 'params': {
                    'moeda': campos['moeda'], 'data': '{:%d/%m/%Y}'.format(quando)}})
            else:
                falt.append('paridade')
                notas.append({'code': 'parity_failed', 'params': {'motivo': erro}})
    # Os preços de verificação vêm do QUOTES: um na vanilla, a série na asiática.
    datas = _datas_de_verificacao(cel)
    precos, sem, fonte_q, erro_q = _fixings_do_quotes(
        cel.get('Classe do ativo subjacente', ''), cel.get('Ativo subjacente / Moeda base', ''), datas)
    campos['fixings'] = '\n'.join(domain.fx8(p) for _d, p, _dia in precos)
    if len(datas) > 1:
        notas.append({'code': 'asian', 'params': {'n': len(datas)}})
    if precos and '\u00d7' in fonte_q:
        notas.append({'code': 'quoted_in_cents', 'params': {'ativo': ativo}})
    if precos:
        notas.append({'code': 'fixings_from_quotes',
                      'params': {'n': len(precos), 'fonte': fonte_q,
                                 'de': '{:%d/%m/%Y}'.format(precos[0][0]),
                                 'ate': '{:%d/%m/%Y}'.format(precos[-1][0])}})
    if sem or not precos:
        # Série pela metade NÃO é média: o campo fica sinalizado e a nota diz
        # quantas datas faltam (futuras, sem pregão) ou por que nada veio.
        falt.append('fixings')
        notas.append({'code': 'fixings_missing',
                      'params': {'n': len(sem), 'motivo': erro_q,
                                 'datas': ', '.join('{:%d/%m/%Y}'.format(d) for d in sem[:6])}})
    if any(_num_tela(cel.get(c)) for c in ('Barreira de KI', 'Barreira de KO')):
        notas.append({'code': 'has_barrier', 'params': {}})
    contraparte, nota_cpty = _contraparte_opcao(cel)
    if nota_cpty:
        notas.append(nota_cpty)
    campos.update({'counterparty': contraparte,
                   'data_emissao': _data_tela(cel.get('Data Registro')),
                   'classe': ' · '.join(x for x in (cel.get('Classe do ativo subjacente', ''),
                                                    cel.get('Ativo subjacente / Moeda base', '')) if x)})
    return {'found': True, 'b3_id': cel.get('Código IF', '') or b3_id, 'source_date': fonte,
            'counterparty': contraparte,
            'fields': campos, 'missing': falt, 'assumed': assumido, 'notes': notas}


# ── Export: a memória de cálculo das três calculadoras ──────────────────────
# A MESMA lógica da do swap (§455): refaz a conta pela função da tela — nada de
# resultado guardado entre dois requests — e o arquivo é FÓRMULA com o valor
# gravado junto. O nome é o do DOCUMENTO: CETIP ID, contraparte e a data.

def _emissao_do_form(form):
    iso = str(form.get('data_emissao') or '').strip()
    try:
        return para_data(iso) if iso else None
    except ErroDeDado:
        return None


def _num_opcional(form, campo):
    bruto = str(form.get(campo) or '').strip()
    return domain.decimal(bruto, campo) if bruto else None


def memoria_ndf(form):
    from apps.pages.features.tools.infra import memoria_derivativos
    c = calcular_ndf(form)
    cetip, cpty = str(form.get('b3_id') or '').strip(), str(form.get('counterparty') or '').strip()
    conteudo = memoria_derivativos.ndf(
        c['r'], c['moeda'], c['vencimento'], cetip_id=cetip, contraparte=cpty,
        classe=str(form.get('classe') or '').strip(), emissao=_emissao_do_form(form),
        nocional_informado=_num_opcional(form, 'nocional'),
        fixo_em_reais=domain.ligado(form, 'fixo_em_reais'),
        fixing_nota=c.get('fixing_nota') or '', paridade_nota=c.get('paridade_nota') or '',
        ativo=str(form.get('ativo') or '').strip() if c.get('mercadoria') else '')
    return conteudo, domain.nome_memoria(cetip, cpty, c['vencimento'], produto='NDF')


def memoria_unwind_ndf(form):
    from apps.pages.features.tools.infra import memoria_derivativos
    c = calcular_unwind_ndf(form)
    cetip, cpty = str(form.get('b3_id') or '').strip(), str(form.get('counterparty') or '').strip()
    conteudo = memoria_derivativos.unwind_ndf(
        c['r'], c['moeda'], c['liquidacao'], c['vencimento'], cetip_id=cetip, contraparte=cpty,
        classe=str(form.get('classe') or '').strip(), emissao=_emissao_do_form(form),
        nocional_informado=_num_opcional(form, 'nocional'),
        fixo_em_reais=domain.ligado(form, 'fixo_em_reais'), du_contado=c['du_contado'],
        original_informado=_num_opcional(form, 'nocional_original'),
        ja_recomprado=_num_opcional(form, 'ja_recomprado') or 0.0)
    return conteudo, domain.nome_memoria(cetip, cpty, c['liquidacao'], produto='Recompra NDF')


def memoria_opcao(form):
    from apps.pages.features.tools.infra import memoria_derivativos
    c = calcular_opcao(form)
    cetip, cpty = str(form.get('b3_id') or '').strip(), str(form.get('counterparty') or '').strip()
    conteudo = memoria_derivativos.opcao(
        c['r'], c['moeda'], c['exercicio'], cetip_id=cetip, contraparte=cpty,
        classe=str(form.get('classe') or '').strip(), emissao=_emissao_do_form(form),
        paridade_nota=c.get('paridade_nota') or '',
        premio_unitario=_num_opcional(form, 'premio_unitario') or 0.0,
        paridade_premio=_num_opcional(form, 'paridade_premio'))
    return conteudo, domain.nome_memoria(cetip, cpty, c['exercicio'], produto='Opção')

