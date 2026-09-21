# -*- coding: utf-8 -*-
"""Liquidação de swap — quanto de fato se paga, e sobre qual saldo.

Responde a pergunta do dia do caixa: **quanto uma parte paga à outra**.

1. **Índice realizado, não projetado.** O CDI vem da série 4389 do BCB, dia a
   dia, e a variação cambial da PTAX publicada. Por isso o fim do fluxo não
   pode passar de hoje quando alguma ponta é indexada.
2. **A base é o notional remanescente.** Num swap com amortização o que rende
   no fluxo seguinte é o que sobrou — o saldo é campo de entrada, e é ele que
   multiplica o fator das duas pontas.
3. **Só a diferença liquida.** O principal é nocional; quem tem o resultado
   negativo paga.

As três datas são separadas de propósito: data da operação (prazo do IR),
início do fluxo (onde os índices começam), fim do fluxo (a data do ajuste).

    Pré              F = cap(i, τ)
    CDI              F = Π [ 1 + ((1 + DI_k)^(1/252) − 1) · p ] · cap(s, τ)
    Cambial          F = cap(c, τ)
    SOFR composto    F = Π (1 + SOFR_k · n/360) · cap(s, τ)
    Term SOFR        F = cap(fixing + s, τ)
    EURIBOR          F = cap(fixing + s, τ)
    IPCA             F = (NI_final / NI_inicial) · cap(c, τ)   NI final do IBGE (M-1/M-2); só o cupom liquida no fluxo
    Equity           F = (preço_final / preço_inicial) · cap(s, τ)

Uma ponta em moeda estrangeira multiplica tudo pela variação cambial
``fixing_final / fixing_inicial``; as duas metades ficam separadas no
resultado. **Equity é quanto**: liquida em reais sem conversão. O IR só incide
quando o BANCO paga — a retenção é da fonte pagadora.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional

from apps.pages.precificador import cambio, cdi, contagem, euribor, ipca, sofr, term_sofr
from apps.pages.precificador.calendario import (calendario_anbima, calendario_bce,
                                                calendario_sofr, para_data)
from apps.pages.precificador.erros import ErroFerramenta
from apps.pages.precificador.renda_fixa import aliquota_ir

PRE = 'pre'
# UM indexador de CDI, com percentual E spread — não dois mutuamente
# exclusivos. A posição de swap traz as duas colunas na MESMA perna
# (`Percentual` e `Taxa`, com o `Sinal Taxa` ao lado), e `100% do CDI + 1,07%`
# é um contrato comum: com dois índices excludentes ele não tinha como ser
# representado, e a perna entrava pela metade sem nada dizer isso.
CDI = 'cdi'
MOEDA = 'moeda'
CAMBIO = 'cambio'
SOFR = 'sofr'
TERM_SOFR = 'term_sofr'
EURIBOR = 'euribor'
IPCA = 'ipca'
EQUITY = 'equity'
FATOR = 'fator'

INDEXADORES = [
    (PRE, 'Fixed — annual rate'),
    (CDI, 'CDI — % of CDI ± spread, realised'),
    (MOEDA, 'Currency — FX variation only'),
    (CAMBIO, 'FX variation + coupon'),
    (SOFR, 'Compounded SOFR + spread'),
    (TERM_SOFR, 'Term SOFR fixing + spread'),
    (EURIBOR, 'EURIBOR fixing + spread'),
    (IPCA, 'IPCA by index number + real coupon'),
    (EQUITY, 'Equity — share or index, by price change'),
    (FATOR, 'Accrued factor typed in'),
]
INDEXADOR_POR_CODIGO = dict(INDEXADORES)

REALIZADOS = {CDI, MOEDA, CAMBIO, SOFR, EURIBOR}
COM_MOEDA = {MOEDA, CAMBIO, SOFR, TERM_SOFR, EURIBOR}
QUANTO = {EQUITY}
DECLARAM_MOEDA = COM_MOEDA | QUANTO
SEM_TAXA = {MOEDA, FATOR}
LIMITE_DEFASAGEM = 15

CONVENCAO_PADRAO = {
    PRE: (contagem.DU_252, contagem.COMPOSTO),
    CDI: (contagem.DU_252, contagem.COMPOSTO),
    IPCA: (contagem.DU_252, contagem.COMPOSTO),
    EQUITY: (contagem.DU_252, contagem.COMPOSTO),
    FATOR: (contagem.DU_252, contagem.COMPOSTO),
    MOEDA: (contagem.ACT_360, contagem.SIMPLES),
    CAMBIO: (contagem.ACT_360, contagem.SIMPLES),
    SOFR: (contagem.ACT_360, contagem.SIMPLES),
    TERM_SOFR: (contagem.ACT_360, contagem.SIMPLES),
    EURIBOR: (contagem.ACT_360, contagem.SIMPLES),
}


def convencao_padrao(indexador):
    return CONVENCAO_PADRAO.get(indexador, (contagem.DU_252, contagem.COMPOSTO))


MOEDA_DO_INDEXADOR = {SOFR: 'USD', TERM_SOFR: 'USD', EURIBOR: 'EUR'}
SEM_CONVERSAO = 'BRL'


@dataclass(frozen=True)
class MoedaDeFluxo:
    codigo: str
    nome: str
    automatica: bool = True


# As dez do boletim do BCB são a lista fechada do Olinda; fora dela não há
# PTAX pública, e os fixings entram digitados.
MOEDAS = [
    MoedaDeFluxo(SEM_CONVERSAO, 'Real — already in BRL, no conversion'),
    MoedaDeFluxo('USD', 'US dollar'),
    MoedaDeFluxo('EUR', 'Euro'),
    MoedaDeFluxo('GBP', 'Pound sterling'),
    MoedaDeFluxo('JPY', 'Japanese yen'),
    MoedaDeFluxo('CHF', 'Swiss franc'),
    MoedaDeFluxo('CAD', 'Canadian dollar'),
    MoedaDeFluxo('AUD', 'Australian dollar'),
    MoedaDeFluxo('DKK', 'Danish krone'),
    MoedaDeFluxo('NOK', 'Norwegian krone'),
    MoedaDeFluxo('SEK', 'Swedish krona'),
    MoedaDeFluxo('CNH', 'Offshore yuan', False),
    MoedaDeFluxo('CNY', 'Onshore yuan', False),
]
MOEDA_POR_CODIGO = {m.codigo: m for m in MOEDAS}
MOEDAS_AUTOMATICAS = {m.codigo for m in MOEDAS if m.automatica}

TENORES_EURIBOR = list(euribor.TENORES)
_MESES_DO_TENOR = {'1 week': 1, '1 month': 1, '3 month': 3, '6 month': 6, '12 month': 12}

COM_FIXING = {TERM_SOFR, EURIBOR}
DEFASAGEM_FIXING = 2

ATIVA = 'ativa'
PASSIVA = 'passiva'

BASE_JUROS = 'juros'
BASE_VALOR_FUTURO = 'valor_futuro'
BASE_AUTOMATICA = 'auto'

BASES_DE_AJUSTE = [
    (BASE_AUTOMATICA, 'By the dates — interest on an interim flow, future value at maturity'),
    (BASE_JUROS, 'Interest only — interim flow, the principal carries on'),
    (BASE_VALOR_FUTURO, 'Future value of both legs — final settlement'),
]

SOBRE_ORIGINAL = 'original'
SOBRE_REMANESCENTE = 'remanescente'
#  `At Maturity` é a resposta do BULLET e do que a coluna `Tipo de amortização`
#  da posição deixa em branco: não há parcela, há o principal inteiro voltando
#  no vencimento. Como base de CÁLCULO ela é o saldo remanescente — a 100% os
#  dois caminhos dão o mesmo número (`amortizar` devolve `min(saldo, ref×1,0)`)
#  —, mas ela existe como opção própria porque as outras duas descrevem uma
#  PARCELA, e escolher "sobre o valor original" num bullet faz a tela afirmar
#  um cronograma de amortização que aquele contrato não tem.
AT_MATURITY = 'vencimento'
#  `Sem Troca de Amortização` NÃO é o At Maturity. As três bases acima
#  descrevem QUANDO e SOBRE O QUÊ o principal é amortizado; esta diz que ele
#  não é amortizado NUNCA — não há evento de amortização em fluxo nenhum, nem
#  no vencimento. Ela existe como opção própria porque cair no At Maturity faz
#  a tela afirmar uma devolução de principal no encerramento que o contrato não
#  tem, e cair no `Sobre Valor Base Original` afirma um cronograma de parcelas.
#  É a resposta do código 4 do cadastro `swap-amortizacao`, e é a mais comum
#  nos swaps da mesa.
SEM_TROCA = 'sem_troca'

BASES_AMORTIZACAO = [
    (SOBRE_ORIGINAL, 'On the original notional — constant instalment'),
    (SOBRE_REMANESCENTE, 'On the remaining balance — decreasing instalment'),
    (AT_MATURITY, 'At maturity — the whole principal at the end'),
    (SEM_TROCA, 'No amortisation exchange — the notional never amortises'),
]


class ErroLiquidacao(ErroFerramenta, ValueError):
    """Dado que falta ou não fecha para liquidar."""


def amortizar(nocional_original, saldo, percentual, base=SOBRE_ORIGINAL):
    """A amortização acontece no FIM do fluxo: define o saldo do seguinte.

    `AT_MATURITY` calcula sobre o SALDO: o que volta no vencimento é o que
    ainda está de pé, não uma fração do valor registrado — num contrato que já
    amortizou antes, o original é maior que o saldo e a conta pelo original
    seria aparada pelo `min` só por sorte.

    `SEM_TROCA` é zero, e o percentual não é lido: o contrato não amortiza em
    fluxo nenhum. A base VENCE o percentual aqui de propósito — um `100` que
    tenha sobrado no campo (do fluxo anterior, do pré-preenchimento de um
    bullet) devolveria o principal inteiro num swap que não devolve nada."""
    if base == SEM_TROCA:
        return 0.0
    if percentual <= 0:
        return 0.0
    referencia = saldo if base in (SOBRE_REMANESCENTE, AT_MATURITY) else nocional_original
    return min(saldo, referencia * percentual)


@dataclass
class Ponta:
    """``taxa`` sempre decimal: 0,14 para 14% a.a., 1,10 para 110% do CDI."""
    indexador: str
    taxa: float = 0.0            # a taxa contratada — no CDI, o SPREAD
    percentual: float = 1.0      # só no CDI: 1.10 = 110% do CDI
    convencao: str = contagem.DU_252
    regime: str = contagem.COMPOSTO
    moeda: str = 'USD'
    ptax_inicial: Optional[float] = None
    ptax_final: Optional[float] = None
    ni_inicial: Optional[float] = None
    ni_final: Optional[float] = None
    # '' = números digitados; 'm1'/'m2' = buscados no IBGE pela defasagem
    # contada do início (inicial) e do fim (final) do fluxo — `ipca.py`.
    ipca_fixing: str = ''
    fator_manual: Optional[float] = None
    ativo: str = ''
    preco_inicial: Optional[float] = None
    preco_final: Optional[float] = None
    tenor: str = '3 month'
    data_fixing: Optional[date] = None
    taxa_indice: Optional[float] = None
    lookback: int = 0
    shift: int = 0
    # A `Denominação` da curva VCP (§479): o multiplicador incide na taxa anual
    # que capitaliza — `(3M SOFR + 0.75%)*1.1765` é 1,1765 aqui; no CDI, no
    # spread (o % do CDI tem campo próprio). 1,0 = nenhum. O texto fica
    # guardado para a memória de cálculo.
    multiplicador: float = 1.0
    descricao_curva: str = ''


@dataclass(frozen=True)
class DiaDoFator:
    """Um dia do acúmulo, na mesma forma venha do CDI ou do SOFR."""
    data: date
    taxa: float
    fator_dia: float
    fator_acumulado: float
    data_observacao: Optional[date] = None

    @property
    def defasado(self):
        return bool(self.data_observacao and self.data_observacao != self.data)


def _dias_do_cdi(acumulado):
    return [DiaDoFator(d.data, d.taxa, d.fator_dia, d.fator_acumulado) for d in acumulado.dias]


def _dias_do_sofr(composto):
    return [DiaDoFator(d.data_juros, d.taxa, d.fator_dia, d.fator_acumulado, d.data_observacao)
            for d in composto.dias]


@dataclass
class PontaLiquidada:
    indexador: str
    fator: float
    nocional: float
    valor: float
    descricao: tuple = ('', {})
    convencao: Optional[str] = contagem.DU_252
    regime: Optional[str] = contagem.COMPOSTO
    dias_contados: Optional[int] = 0
    fracao_de_ano: Optional[float] = 0.0
    contagem_vale_para_spread: bool = False
    dias_uteis: int = 0
    dias_corridos: int = 0
    moeda: Optional[str] = None
    quanto: bool = False
    fator_cambial: float = 1.0
    fator_do_indice: float = 1.0
    # A correção monetária da perna IPCA (NI_final / NI_inicial). Fica FORA
    # do `fator_do_indice` pelo mesmo motivo do `fator_cambial`: no fluxo
    # intermediário só o CUPOM liquida — a correção fica no principal, que
    # segue corrigido para o fluxo seguinte. A planilha da mesa faz
    # `VBR × correção × (cupom − 1)`, e somar a correção aos juros dava
    # 2,4 milhões a mais num fluxo de 1 bilhão.
    fator_correcao: float = 1.0
    multiplicador: float = 1.0               # o da denominação da curva (§479)
    ptax_inicial: Optional[float] = None
    ptax_final: Optional[float] = None
    data_ptax_inicial: Optional[date] = None
    data_ptax_final: Optional[date] = None
    data_fixing: Optional[date] = None
    taxa_do_fixing: Optional[float] = None
    tenor: Optional[str] = None
    ativo: Optional[str] = None
    preco_inicial: Optional[float] = None
    preco_final: Optional[float] = None
    ni_inicial: Optional[float] = None
    ni_final: Optional[float] = None
    mes_ni_inicial: Optional[str] = None     # '02/2026' — só quando veio do IBGE
    mes_ni_final: Optional[str] = None
    ipca_fixing: str = ''
    defasagem: tuple = ('', {})
    obs_inicio: Optional[date] = None
    obs_fim: Optional[date] = None
    fixings: List[DiaDoFator] = field(default_factory=list)

    @property
    def juros(self):
        """Só o que a TAXA rendeu, sobre o principal corrigido (IPCA) e
        trazido a reais pelo fixing do fim."""
        return (self.nocional * self.fator_cambial * self.fator_correcao
                * (self.fator_do_indice - 1.0))

    def amortizacao_devolvida(self, amortizado):
        """O principal que SAI do swap nesta perna hoje, em reais.

        A amortização é UMA só — o percentual do fluxo sobre o notional —, mas
        o que cada perna entrega por ela não é o mesmo número: a perna IPCA
        devolve o principal CORRIGIDO e a perna em moeda estrangeira devolve o
        principal convertido pelo fixing do fim. Num swap em que as duas pernas
        são nominais em reais os dois valores são iguais e se cancelam na
        subtração — foi por isso que a amortização ficou fora da apuração até
        aqui sem ninguém reparar.

        No fluxo que amortiza, a parte do principal que sai do swap HOJE é caixa
        que liquida, e é a diferença entre o que cada perna entrega que fecha
        com a mesa: num swap DI × IPCA de VBR 254 mi amortizando 0,72%, a perna
        IPCA devolvia R$ 2.441.061,89 contra os R$ 2.049.218,19 da perna DI, e
        os R$ 391.843,70 de diferença eram exatamente o que separava a tela da
        planilha. A parte do principal que NÃO amortiza continua fora: ela segue
        corrigida para o fluxo seguinte, que é a regra do §449."""
        return (amortizado or 0.0) * self.fator_cambial * self.fator_correcao

    @property
    def efeito_cambial(self):
        """O que a moeda fez com o principal —
        ``juros + efeito_cambial + efeito_correcao == valor − nocional``."""
        return self.nocional * (self.fator_cambial - 1.0)

    @property
    def efeito_correcao(self):
        """O que a inflação fez com o principal (perna IPCA), em reais."""
        return self.nocional * self.fator_cambial * (self.fator_correcao - 1.0)

    @property
    def descricao_texto(self):
        molde, valores = self.descricao
        try:
            return molde.format(**valores)
        except (KeyError, IndexError, ValueError):
            return molde


def _numero(valor, casas=4):
    return '{:,.{c}f}'.format(valor, c=casas)


def _ptax_do_dia_anterior(moeda, referencia):
    """PTAX de fechamento do dia útil anterior — a convenção do contrato."""
    return cambio.ptax_moeda(moeda, referencia - timedelta(days=1))


def calendario_do_fixing(indexador):
    """O calendário em que a taxa a termo CONTA os dias até o fixing — é o do
    ÍNDICE, não o do contrato: o Term SOFR é fixado dois *US Government
    Securities business days* antes (o calendário SOFR do Holidays), e a
    EURIBOR dois dias TARGET2. Índice sem calendário próprio cai no ANBIMA."""
    if indexador == TERM_SOFR:
        return calendario_sofr()
    if indexador == EURIBOR:
        return calendario_bce()
    return calendario_anbima()


def data_de_fixing(inicio, calendario=None, defasagem=DEFASAGEM_FIXING, indexador=None):
    """D-2 úteis do início do fluxo — a defasagem padrão da taxa a termo —, no
    calendário do ÍNDICE (`calendario_do_fixing`).

    Contava pelo ANBIMA, e errava em todo feriado americano que não é
    brasileiro: fluxo começando na segunda 22/06/2026 dava D-2 = quinta 18/06,
    quando a sexta 19/06 é Juneteenth — D-1 é a quinta 18 e D-2 a quarta 17. A
    taxa que entrava era a de um dia depois da que o contrato manda, e a conta
    fechava consigo mesma (mesa, 21/09/2026). `calendario` explícito vence."""
    cal = calendario or calendario_do_fixing(indexador)
    return cal.workday(para_data(inicio), -abs(defasagem))


def _fixing_euribor(tenor, quando):
    curva = euribor.carregar()
    data, linha = curva.em(quando)
    if not linha or tenor not in linha:
        raise ErroLiquidacao('there is no EURIBOR {tenor} fixing published up to {data}',
                             tenor=tenor, data='{:%d/%m/%Y}'.format(quando))
    return data, linha[tenor]


def _fator_cambial(ponta, d0, d1):
    """(fator, fixing inicial, fixing final, data inicial, data final)."""
    if ponta.indexador not in COM_MOEDA or ponta.moeda == SEM_CONVERSAO:
        if (ponta.moeda == SEM_CONVERSAO and ponta.indexador in COM_MOEDA
                and ponta.ptax_inicial is not None and ponta.ptax_final is not None):
            raise ErroLiquidacao(
                'both currency fixings are filled in, but the flow currency is BRL, which '
                'does not convert. Pick the foreign currency for the FX variation to count, '
                'or clear the fixings.')
        return 1.0, None, None, None, None
    p0, p1 = ponta.ptax_inicial, ponta.ptax_final
    data0 = data1 = None
    if p0 is None or p1 is None:
        if ponta.moeda not in MOEDAS_AUTOMATICAS:
            faltando = 'initial' if p0 is None else 'final'
            raise ErroLiquidacao(
                'the Central Bank does not publish {moeda}: type in the {qual} fixing. '
                'Both are entered by hand.', moeda=ponta.moeda, qual=faltando)
        b0 = _ptax_do_dia_anterior(ponta.moeda, d0)
        b1 = _ptax_do_dia_anterior(ponta.moeda, d1)
        p0 = p0 if p0 is not None else b0.venda
        p1 = p1 if p1 is not None else b1.venda
        data0, data1 = b0.data, b1.data
    if not p0:
        raise ErroLiquidacao('the initial currency fixing cannot be zero')
    return p1 / p0, p0, p1, data0, data1


def liquidar_ponta(ponta, nocional, inicio, fim, calendario=None, arredondar_di=False):
    """Fator acumulado da ponta no fluxo, aplicado ao notional remanescente."""
    cal = calendario or calendario_anbima()
    d0, d1 = para_data(inicio), para_data(fim)
    tau = contagem.fracao(ponta.convencao, d0, d1, cal)
    fx, p0, p1, data_p0, data_p1 = _fator_cambial(ponta, d0, d1)
    sem_taxa = ponta.indexador in SEM_TAXA
    mult = 1.0 if ponta.multiplicador is None else float(ponta.multiplicador)
    if mult <= 0:
        raise ErroLiquidacao('the rate multiplier must be positive')
    comum = dict(
        indexador=ponta.indexador, nocional=nocional, multiplicador=mult,
        convencao=None if sem_taxa else ponta.convencao,
        regime=None if sem_taxa else ponta.regime,
        dias_contados=None if sem_taxa else contagem.dias(ponta.convencao, d0, d1, cal),
        fracao_de_ano=None if sem_taxa else tau,
        dias_uteis=cal.dias_uteis(d0, d1), dias_corridos=(d1 - d0).days,
        moeda=ponta.moeda if ponta.indexador in DECLARAM_MOEDA else None,
        quanto=ponta.indexador in QUANTO and ponta.moeda != SEM_CONVERSAO,
        fator_cambial=fx, ptax_inicial=p0, ptax_final=p1,
        data_ptax_inicial=data_p0, data_ptax_final=data_p1)

    def capitalizar(taxa):
        # O multiplicador da denominação incide na taxa ANUAL que capitaliza —
        # `(fixing + spread) × 1,1765` —, nunca no fator: (1 + r·k)^τ, não
        # ((1 + r)^τ)·k. É o gross-up de IR escrito no contrato (§479).
        return contagem.fator(taxa * mult, ponta.convencao, ponta.regime, d0, d1, cal)

    def montar(indice, descricao, **extra):
        fator = fx * extra.get('fator_correcao', 1.0) * indice
        if mult != 1.0 and not sem_taxa:
            molde, valores = descricao
            descricao = (molde + ', the rate × {mult}', dict(valores, mult=_numero(mult, 6)))
        return PontaLiquidada(fator=fator, valor=nocional * fator, fator_do_indice=indice,
                              descricao=descricao, **comum, **extra)

    if ponta.indexador == PRE:
        return montar(capitalizar(ponta.taxa),
                      ('{taxa}% p.a. over τ = {tau}',
                       {'taxa': _numero(ponta.taxa * 100), 'tau': _numero(tau, 6)}))

    if ponta.indexador == CDI:
        # O PERCENTUAL incide na taxa DIÁRIA — é a definição do índice, e é por
        # isso que 110% do CDI a 14% dá 15,5031% e não os 15,40% de multiplicar
        # a taxa anual. O SPREAD é multiplicativo e capitaliza sobre τ, na
        # contagem escolhida: (1+CDI)·(1+spread).
        pct = 1.0 if ponta.percentual is None else float(ponta.percentual)
        acumulado = cdi.acumular(cdi.serie(d0, d1), d0, d1, valor=1.0,
                                 percentual=pct, arredondar=arredondar_di)
        indice = acumulado.fator
        com_spread = bool(ponta.taxa)
        if com_spread:
            indice *= capitalizar(ponta.taxa)
            molde = '{pct}% of CDI {sinal} {taxa}% over {du} published business days'
            valores = {'pct': _numero(pct * 100, 2), 'du': acumulado.dias_uteis,
                       'sinal': '+' if ponta.taxa >= 0 else '−',
                       'taxa': _numero(abs(ponta.taxa) * 100)}
        else:
            molde = '{pct}% of CDI over {du} published business days'
            valores = {'pct': _numero(pct * 100, 2), 'du': acumulado.dias_uteis}
        return montar(indice, (molde, valores), fixings=_dias_do_cdi(acumulado),
                      contagem_vale_para_spread=com_spread)

    if ponta.indexador == MOEDA:
        if fx == 1.0 and ponta.moeda == SEM_CONVERSAO:
            raise ErroLiquidacao('a pure currency leg needs a foreign currency — in BRL it '
                                 'would earn nothing')
        return montar(1.0, ('{variacao}% FX variation, no coupon',
                            {'variacao': _numero((fx - 1) * 100)}))

    if ponta.indexador == CAMBIO:
        return montar(capitalizar(ponta.taxa),
                      ('{variacao}% FX variation plus a {taxa}% coupon over τ = {tau}',
                       {'variacao': _numero((fx - 1) * 100), 'taxa': _numero(ponta.taxa * 100),
                        'tau': _numero(tau, 6)}))

    if ponta.indexador == SOFR:
        for nome, valor in (('lookback', ponta.lookback), ('observation shift', ponta.shift)):
            if valor < 0 or valor > LIMITE_DEFASAGEM:
                raise ErroLiquidacao('the {defasagem} must be between 0 and {teto} business days',
                                     defasagem=nome, teto=LIMITE_DEFASAGEM)
        margem = timedelta(days=40 + (ponta.lookback + ponta.shift) * 2)
        composto = sofr.compor(sofr.serie_sofr(d0 - margem, d1 + timedelta(days=1)), d0, d1,
                               lookback=ponta.lookback, shift=ponta.shift,
                               calendario=calendario_sofr())
        # O spread SOMA à taxa composta e as duas capitalizam UMA vez — a mesma
        # composição do Term SOFR e da EURIBOR logo abaixo, que são a mesma
        # figura ("fixing + spread"). Multiplicar os dois fatores acrescenta o
        # termo cruzado `sofr · spread · τ²`, que não existe em contrato nenhum:
        # num swap de meio ano a 3,66% + 1,84% sobre US$ 17,5 mi ele sozinho
        # valia R$ 15,7 mil, e era a planilha da mesa e o sistema do banco
        # discordando do Swap Calculator na terceira casa do resultado. O CDI é
        # o caso diferente e continua multiplicativo de propósito (ver acima): lá
        # o percentual incide na taxa DIÁRIA e o spread é uma capitalização à
        # parte, que é como a B3 apura.
        indice = capitalizar(composto.taxa_composta + ponta.taxa)
        return montar(
            indice,
            ('compounded SOFR of {sofr}% plus a {taxa}% spread over {dc} calendar days',
             {'sofr': _numero(composto.taxa_composta * 100), 'taxa': _numero(ponta.taxa * 100),
              'dc': composto.dias_corridos}),
            fixings=_dias_do_sofr(composto), taxa_do_fixing=composto.taxa_composta,
            defasagem=sofr.convencao(ponta.lookback, ponta.shift),
            obs_inicio=composto.obs_inicio, obs_fim=composto.obs_fim)

    if ponta.indexador in (TERM_SOFR, EURIBOR):
        # o calendário do ÍNDICE, não o `cal` do formulário (que é o da contagem
        # de dias úteis do contrato, ANBIMA por padrão)
        quando = ponta.data_fixing or data_de_fixing(d0, indexador=ponta.indexador)
        if ponta.indexador == EURIBOR:
            quando, taxa_indice = _fixing_euribor(ponta.tenor, quando)
        elif ponta.taxa_indice is None:
            importada = term_sofr.carregar()
            achada = (None if importada.vazio
                      else importada.taxa(_MESES_DO_TENOR.get(ponta.tenor, 3), quando))
            if achada is None:
                raise ErroLiquidacao(
                    'Term SOFR is licensed by CME and has no public source. Type in the '
                    'fixing rate, or import the B3 report on the Term SOFR page.')
            taxa_indice = achada
            quando = importada.em(quando)[0] or quando
        else:
            taxa_indice = ponta.taxa_indice
        indice = capitalizar(taxa_indice + ponta.taxa)
        nome = 'Term SOFR' if ponta.indexador == TERM_SOFR else 'EURIBOR'
        return montar(
            indice,
            ('{nome} {tenor} of {indice}% plus a {taxa}% spread, fixed on {quando}',
             {'nome': nome, 'tenor': ponta.tenor, 'indice': _numero(taxa_indice * 100, 5),
              'taxa': _numero(ponta.taxa * 100), 'quando': '{:%d/%m/%Y}'.format(quando)}),
            data_fixing=quando, taxa_do_fixing=taxa_indice, tenor=ponta.tenor)

    if ponta.indexador == EQUITY:
        if not ponta.preco_inicial or ponta.preco_final is None:
            raise ErroLiquidacao('the equity leg needs the initial and the final price')
        retorno = ponta.preco_final / ponta.preco_inicial
        return montar(
            retorno * capitalizar(ponta.taxa),
            ('{ativo} moved {retorno}% plus a {taxa}% spread, no FX conversion',
             {'ativo': ponta.ativo or 'equity', 'retorno': _numero((retorno - 1) * 100),
              'taxa': _numero(ponta.taxa * 100)}),
            ativo=ponta.ativo or None, preco_inicial=ponta.preco_inicial,
            preco_final=ponta.preco_final)

    if ponta.indexador == IPCA:
        ni0, ni1, mes0, mes1 = ponta.ni_inicial, ponta.ni_final, None, None
        if ponta.ipca_fixing:
            # O fixing diz de que mês é o número FINAL: M-n contado da data
            # de liquidação do fluxo. O INICIAL é do CONTRATO — a cotação
            # inicial que a posição da B3 traz (o pré-preenchimento a põe no
            # campo) ou o que a mesa digitou — e só cai para o IBGE, pela
            # mesma defasagem contada do início do fluxo, quando está em
            # branco. Buscar os dois sobrescrevia o do contrato: num swap
            # fechado em 15/06 a base é maio (o último publicado), e M-2 do
            # início dava abril — 0,58% de correção que não existe.
            m1 = ipca.mes_do_fixing(d1, ponta.ipca_fixing)
            pedidos = [m1]
            m0 = None
            if not ni0:
                m0 = ipca.mes_do_fixing(d0, ponta.ipca_fixing)
                pedidos.append(m0)
            numeros = ipca.numeros_indice(pedidos)
            ni1, mes1 = numeros[m1], ipca.rotulo(*m1)
            if m0:
                ni0, mes0 = numeros[m0], ipca.rotulo(*m0)
        if not ni0 or ni1 is None:
            raise ErroLiquidacao('the IPCA leg needs the initial and the final index number')
        correcao = ni1 / ni0
        if mes1:
            molde = ('{correcao}% inflation adjustment ({de} → {mes1}, IBGE) on the principal '
                     'plus a {taxa}% p.a. real coupon')
        else:
            molde = ('{correcao}% inflation adjustment on the principal plus a {taxa}% p.a. '
                     'real coupon')
        return montar(
            capitalizar(ponta.taxa),
            (molde, {'correcao': _numero((correcao - 1) * 100), 'taxa': _numero(ponta.taxa * 100),
                     'de': mes0 or 'contract', 'mes1': mes1}),
            fator_correcao=correcao,
            ni_inicial=ni0, ni_final=ni1, mes_ni_inicial=mes0, mes_ni_final=mes1,
            ipca_fixing=ponta.ipca_fixing)

    if ponta.indexador == FATOR:
        if ponta.fator_manual is None:
            raise ErroLiquidacao('type in the accrued factor of the leg')
        return montar(ponta.fator_manual, ('factor typed in', {}))

    raise ErroLiquidacao('unknown index: {indexador}', indexador=ponta.indexador)


@dataclass
class ResultadoLiquidacao:
    data_operacao: date
    inicio: date
    fim: date
    vencimento: Optional[date]
    base_de_ajuste: str
    juros_da_ativa: float
    juros_da_passiva: float
    nocional: float
    nocional_original: float
    percentual_amortizacao: float
    base_amortizacao: str
    valor_amortizado: float
    saldo_seguinte: float
    ativa: PontaLiquidada
    passiva: PontaLiquidada
    ajuste_bruto: float
    quem_recebe: str
    dias_corridos: int
    dias_uteis: int
    dias_da_operacao: int
    aliquota_ir: float
    ir: float
    ajuste_liquido: float
    banco_paga: bool
    # O principal que cada perna devolve no fluxo que amortiza — iguais (e sem
    # efeito) quando as duas são nominais em reais. Ver `amortizacao_devolvida`.
    amortizacao_da_ativa: float = 0.0
    amortizacao_da_passiva: float = 0.0
    # De onde saiu a alíquota (§479): 'cliente' = exceção do `swap-ir-client`
    # (e `cliente_ir` diz a linha), 'prazo' = tabela por prazo, '' = sem IR.
    origem_ir: str = ''
    cliente_ir: str = ''

    @property
    def diferenca_de_fator(self):
        if self.base_de_ajuste == BASE_JUROS:
            return (self.juros_da_ativa - self.juros_da_passiva) / self.nocional
        return self.ativa.fator - self.passiva.fator

    @property
    def so_juros(self):
        return self.base_de_ajuste == BASE_JUROS

    @property
    def efeito_cambial_do_principal(self):
        futuro = self.ativa.valor - self.passiva.valor
        return futuro - (self.juros_da_ativa - self.juros_da_passiva)


def base_de_ajuste(fim, vencimento, escolha=BASE_AUTOMATICA):
    """Fluxo que termina ANTES do vencimento é intermediário: só juros."""
    if escolha in (BASE_JUROS, BASE_VALOR_FUTURO):
        return escolha
    if vencimento is None:
        return BASE_VALOR_FUTURO
    return BASE_JUROS if para_data(fim) < para_data(vencimento) else BASE_VALOR_FUTURO


@dataclass
class RegraIR:
    """A alíquota de IR que a MESA cadastra (§479), no lugar da tabela fixa.

    `excecao` é a alíquota do cliente no `swap-ir-client` (fração; `None` = o
    cliente não está lá) e VENCE a direção: é a mesma regra do Trade Level e
    do Settlement Advice (`_ops_swap_ir_rate`, na platform), que responde
    pela exceção antes de perguntar quem paga. `faixas` são as do
    `swap-ir-term` — `(até_dias, alíquota)`, a de `None` valendo acima de
    todas —; vazias, vale a tabela regressiva do motor. Prazo acima da última
    faixa cadastrada sem linha "acima de todas" também cai na do motor: a
    lacuna do cadastro não pode virar 0% de IR."""
    excecao: Optional[float] = None
    cliente: str = ''
    faixas: tuple = ()

    def aliquota_por_prazo(self, dias):
        catch_all = None
        for ate, taxa in sorted(self.faixas, key=lambda x: (x[0] is None, x[0] or 0)):
            if ate is None:
                catch_all = taxa
            elif dias <= ate:
                return taxa
        return aliquota_ir(dias) if catch_all is None else catch_all


def liquidar(data_operacao, inicio, fim, nocional, ponta_ativa, ponta_passiva,
             vencimento=None, base_ajuste=BASE_AUTOMATICA, nocional_original=None,
             percentual_amortizacao=0.0, base_amortizacao=SOBRE_ORIGINAL, calendario=None,
             arredondar_di=False, reter_ir=True, regra_ir=None):
    """Ajuste a pagar entre as duas pontas no fim do fluxo."""
    cal = calendario or calendario_anbima()
    dop = para_data(data_operacao)
    d0, d1 = para_data(inicio), para_data(fim)
    if d1 <= d0:
        raise ErroLiquidacao('the flow end must be later than its start')
    if d0 < dop:
        raise ErroLiquidacao('the flow cannot start ({inicio}) before the trade date ({operacao})',
                             inicio='{:%d/%m/%Y}'.format(d0), operacao='{:%d/%m/%Y}'.format(dop))
    if nocional <= 0:
        raise ErroLiquidacao('the remaining notional must be positive')
    indexadores = {ponta_ativa.indexador, ponta_passiva.indexador}
    if indexadores & REALIZADOS and d1 > date.today():
        raise ErroLiquidacao(
            'the settlement uses realised indices, not projections — the flow end cannot '
            'be after today ({hoje})', hoje='{:%d/%m/%Y}'.format(date.today()))
    original = float(nocional_original) if nocional_original else float(nocional)
    # O remanescente PODE ser maior que o original: swap com atualização de
    # notional (o principal corrigido pelo índice, ou reajustado por aditivo)
    # carrega um saldo acima do valor registrado, e a tela recusava a conta
    # como se fosse erro de digitação. O original é só a base da parcela
    # `Sobre Valor Base Original`; `amortizar` já limita a parcela ao saldo.
    amortizado = amortizar(original, nocional, percentual_amortizacao, base_amortizacao)
    ativa = liquidar_ponta(ponta_ativa, nocional, d0, d1, cal, arredondar_di)
    passiva = liquidar_ponta(ponta_passiva, nocional, d0, d1, cal, arredondar_di)
    dv = para_data(vencimento) if vencimento else None
    base = base_de_ajuste(d1, dv, base_ajuste)
    juros_ativa, juros_passiva = ativa.juros, passiva.juros
    # No fluxo intermediário liquida o diferencial de JUROS **mais** o
    # diferencial do principal que amortiza hoje: ele sai do swap agora, e cada
    # perna o entrega pelo seu próprio valor (corrigido no IPCA, convertido na
    # perna em moeda). Em duas pernas nominais em reais os dois são iguais e a
    # parcela some sozinha. No vencimento não entra: ali o valor de cada ponta
    # já carrega o principal inteiro.
    am_ativa = ativa.amortizacao_devolvida(amortizado)
    am_passiva = passiva.amortizacao_devolvida(amortizado)
    bruto = ((juros_ativa + am_ativa) - (juros_passiva + am_passiva) if base == BASE_JUROS
             else ativa.valor - passiva.valor)
    dias_operacao = (d1 - dop).days
    # a retenção é da FONTE PAGADORA: o banco só retém quando é ele quem paga —
    # salvo a exceção por CLIENTE do cadastro, que responde antes da direção
    # (a ordem do `_ops_swap_ir_rate` da platform, §479).
    banco_paga = bruto < 0
    origem_ir, cliente_ir = '', ''
    if not reter_ir:
        pct_ir = 0.0
    elif regra_ir is not None and regra_ir.excecao is not None:
        pct_ir, origem_ir, cliente_ir = regra_ir.excecao, 'cliente', regra_ir.cliente
    elif banco_paga:
        pct_ir = (regra_ir.aliquota_por_prazo(dias_operacao) if regra_ir is not None
                  else aliquota_ir(dias_operacao))
        origem_ir = 'prazo'
    else:
        pct_ir = 0.0
    ir = abs(bruto) * pct_ir if pct_ir else 0.0
    liquido = (bruto + ir) if bruto < 0 else (bruto - ir)
    return ResultadoLiquidacao(
        data_operacao=dop, inicio=d0, fim=d1, vencimento=dv, base_de_ajuste=base,
        juros_da_ativa=juros_ativa, juros_da_passiva=juros_passiva, nocional=float(nocional),
        nocional_original=original, percentual_amortizacao=percentual_amortizacao,
        base_amortizacao=base_amortizacao, valor_amortizado=amortizado,
        amortizacao_da_ativa=am_ativa, amortizacao_da_passiva=am_passiva,
        saldo_seguinte=nocional - amortizado, ativa=ativa, passiva=passiva,
        ajuste_bruto=bruto, quem_recebe=ATIVA if bruto > 0 else PASSIVA,
        dias_corridos=(d1 - d0).days, dias_uteis=cal.dias_uteis(d0, d1),
        dias_da_operacao=dias_operacao, aliquota_ir=pct_ir, ir=ir, ajuste_liquido=liquido,
        origem_ir=origem_ir, cliente_ir=cliente_ir,
        banco_paga=banco_paga)
