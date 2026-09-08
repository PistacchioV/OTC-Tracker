# -*- coding: utf-8 -*-
"""Calculadora de renda fixa — prefixado, CDI e IPCA+.

Cobre o terreno da calculadora da B3, com uma diferença deliberada no DI,
explicada em ``fator_di``. Juros em dias úteis, base 252; IR regressivo sobre
o rendimento; IOF regressivo em resgate com menos de 30 dias corridos; LCI,
LCA, CRI, CRA, LIG e debênture incentivada isentos de IR para pessoa física.
"""
from dataclasses import dataclass

from apps.pages.precificador.calendario import calendario_anbima, para_data
from apps.pages.precificador.erros import ErroDeDado

PREFIXADO = 'prefixado'
CDI_PERCENTUAL = 'cdi_percentual'
CDI_SPREAD = 'cdi_spread'
IPCA_MAIS = 'ipca_mais'
CDI_REALIZADO = 'cdi_realizado'

INDEXADORES = [
    (CDI_REALIZADO, '% of CDI — realised, accrued from BCB'),
    (CDI_PERCENTUAL, '% of CDI — projected'),
    (CDI_SPREAD, 'CDI + spread — projected'),
    (PREFIXADO, 'Fixed rate (% p.a., BUS/252)'),
    (IPCA_MAIS, 'IPCA + real rate'),
]

RETROATIVOS = {CDI_REALIZADO}       # olham para trás: o fim não passa de hoje

ISENTOS = {'lci', 'lca', 'cri', 'cra', 'lig', 'debenture_incentivada', 'poupanca'}

PRODUTOS_RF = [
    ('cdb', 'CDB / RDB', False),
    ('lci', 'LCI / LCA', True),
    ('cri', 'CRI / CRA', True),
    ('debenture', 'Plain debenture', False),
    ('debenture_incentivada', 'Incentivised debenture', True),
    ('tesouro', 'Tesouro Direto', False),
    ('lig', 'LIG', True),
]

_IOF = [96, 93, 90, 86, 83, 80, 76, 73, 70, 66, 63, 60, 56, 53, 50, 46,
        43, 40, 36, 33, 30, 26, 23, 20, 16, 13, 10, 6, 3, 0]


def aliquota_ir(dias_corridos):
    """Tabela regressiva do IR sobre o rendimento."""
    if dias_corridos <= 180:
        return 0.225
    if dias_corridos <= 360:
        return 0.20
    if dias_corridos <= 720:
        return 0.175
    return 0.15


def aliquota_iof(dias_corridos):
    if dias_corridos < 1:
        return 0.96
    if dias_corridos >= 30:
        return 0.0
    return _IOF[dias_corridos - 1] / 100.0


def fator_di(taxa_anual, dias_uteis, percentual=1.0, spread=0.0, arredondar=False):
    """fator_dia = (1 + DI)^(1/252); % do CDI incide na taxa DIÁRIA.

    O padrão B3/CETIP arredonda o fator diário na 8ª casa antes de acumular;
    aqui o padrão é precisão plena (``arredondar=False``)."""
    if dias_uteis <= 0:
        return 1.0
    if spread:
        return ((1.0 + taxa_anual) * (1.0 + spread)) ** (dias_uteis / 252.0)
    fator_dia = (1.0 + taxa_anual) ** (1.0 / 252.0)
    if arredondar:
        fator_dia = round(fator_dia, 8)
    diario = 1.0 + (fator_dia - 1.0) * percentual
    if arredondar:
        diario = round(diario, 16)
    return diario ** dias_uteis


def fator_prefixado(taxa_anual, dias_uteis):
    return (1.0 + taxa_anual) ** (dias_uteis / 252.0)


@dataclass
class ResultadoRendaFixa:
    valor_aplicado: float
    valor_bruto: float
    rendimento_bruto: float
    iof: float
    ir: float
    aliquota_ir: float
    aliquota_iof: float
    valor_liquido: float
    rendimento_liquido: float
    dias_corridos: int
    dias_uteis: int
    fator: float
    taxa_periodo: float
    taxa_anual_equivalente: float
    taxa_liquida_anual: float
    isento: bool


def calcular(valor, inicio, vencimento, indexador, taxa, cdi_projetado=0.0,
             ipca_projetado=0.0, produto='cdb', arredondar_di=False, calendario=None,
             fator_pronto=None, dias_uteis=None):
    """``taxa`` em decimal: 0,14 para 14% a.a.; 1,10 para 110% do CDI; 0,02
    para CDI+2%; 0,06 para IPCA+6%. ``fator_pronto`` curto-circuita o fator —
    é como entra o CDI realizado."""
    cal = calendario or calendario_anbima()
    d0, d1 = para_data(inicio), para_data(vencimento)
    if d1 <= d0:
        raise ErroDeDado('the maturity must be later than the investment date')
    dc = (d1 - d0).days
    du = dias_uteis if dias_uteis is not None else cal.dias_uteis(d0, d1)
    if fator_pronto is not None:
        fator = fator_pronto
    elif indexador == PREFIXADO:
        fator = fator_prefixado(taxa, du)
    elif indexador == CDI_PERCENTUAL:
        fator = fator_di(cdi_projetado, du, percentual=taxa, arredondar=arredondar_di)
    elif indexador == CDI_SPREAD:
        fator = fator_di(cdi_projetado, du, spread=taxa, arredondar=arredondar_di)
    elif indexador == IPCA_MAIS:
        fator = ((1.0 + ipca_projetado) ** (dc / 365.0)) * ((1.0 + taxa) ** (du / 252.0))
    else:
        raise ErroDeDado('unknown index: {indexador}', indexador=indexador)
    bruto = valor * fator
    rendimento = bruto - valor
    isento = produto in ISENTOS
    pct_iof = aliquota_iof(dc)
    iof = rendimento * pct_iof if rendimento > 0 else 0.0
    pct_ir = 0.0 if isento else aliquota_ir(dc)
    ir = (rendimento - iof) * pct_ir if rendimento > 0 else 0.0
    liquido = bruto - iof - ir
    anos_uteis = du / 252.0 if du else (dc / 365.0)
    equivalente = fator ** (1.0 / anos_uteis) - 1.0 if anos_uteis > 0 else 0.0
    liquida = ((liquido / valor) ** (1.0 / anos_uteis) - 1.0) if anos_uteis > 0 else 0.0
    return ResultadoRendaFixa(
        valor_aplicado=valor, valor_bruto=bruto, rendimento_bruto=rendimento, iof=iof, ir=ir,
        aliquota_ir=pct_ir, aliquota_iof=pct_iof, valor_liquido=liquido,
        rendimento_liquido=liquido - valor, dias_corridos=dc, dias_uteis=du, fator=fator,
        taxa_periodo=fator - 1.0, taxa_anual_equivalente=equivalente,
        taxa_liquida_anual=liquida, isento=isento)


def diferenca_arredondamento(taxa_anual, dias_uteis, percentual=1.0, valor=1_000_000.0):
    """Quanto o arredondamento na 8ª casa custa, em reais, no prazo dado."""
    cheio = fator_di(taxa_anual, dias_uteis, percentual, arredondar=False)
    truncado = fator_di(taxa_anual, dias_uteis, percentual, arredondar=True)
    return {'fator_sem_arredondar': cheio, 'fator_arredondado': truncado,
            'diferenca_fator': cheio - truncado, 'diferenca_reais': (cheio - truncado) * valor}
