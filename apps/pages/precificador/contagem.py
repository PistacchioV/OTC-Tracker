# -*- coding: utf-8 -*-
"""Contagem de dias (day count) e regime de capitalização.

Duas escolhas independentes que a tela costuma tratar como uma só, e não são:
a CONTAGEM define a fração de ano τ entre duas datas; o REGIME define o que se
faz com ela — ``(1+i)^τ`` (composto) ou ``1 + i·τ`` (simples). Um pré
brasileiro é DU/252 composto; um cupom cambial é ACT/360 simples; um bond em
dólar é 30/360 composto. Trocar uma sem trocar a outra dá um número que parece
certo e não é.

Em 181 dias corridos com 125 dias úteis, τ vai de 0,4960 (DU/252) a 0,5028
(ACT/360) — a 14% a.a. são quase R$ 9.500 num notional de 100 milhões.
"""
from calendar import isleap
from datetime import date

from apps.pages.precificador.calendario import calendario_anbima, para_data

DU_252 = 'du_252'
ACT_360 = 'act_360'
ACT_365 = 'act_365'
T30_360 = '30_360'
T30E_360 = '30e_360'
ACT_ACT = 'act_act'

# (código, rótulo, explicação) — em inglês; a tradução é por data-lang na tela
CONVENCOES = [
    (DU_252, 'BUS/252 — business days', 'Brazilian market standard: DI, BRL fixed, IPCA and TR.'),
    (ACT_360, 'ACT/360 — calendar days', 'Onshore USD rate, SOFR and most of the USD market.'),
    (ACT_365, 'ACT/365 — calendar days', 'Sterling market and the ACT/365 fixed basis.'),
    (T30_360, '30/360 — bond basis', 'Every month has 30 days and every year 360; corporate bonds.'),
    (T30E_360, '30E/360 — eurobond', 'Like 30/360, but the end day is also truncated to 30.'),
    (ACT_ACT, 'ACT/ACT — ISDA', 'Each stretch of a year divided by that year\'s actual length.'),
]
CONVENCAO_POR_CODIGO = {codigo: (nome, texto) for codigo, nome, texto in CONVENCOES}

COMPOSTO = 'composto'
SIMPLES = 'simples'

REGIMES = [
    (COMPOSTO, 'Compound — (1 + i) ^ τ'),
    (SIMPLES, 'Simple — 1 + i · τ'),
]

REGIME_PADRAO = {DU_252: COMPOSTO, ACT_360: SIMPLES, ACT_365: SIMPLES,
                 T30_360: COMPOSTO, T30E_360: COMPOSTO, ACT_ACT: COMPOSTO}


def nome_curto(convencao):
    """Só o nome curto: "BUS/252", sem a explicação que vem depois."""
    return CONVENCAO_POR_CODIGO.get(convencao, (convencao, ''))[0].split(' — ')[0]


def _dias_30_360(d0, d1, europeu):
    dia0, dia1 = d0.day, d1.day
    if europeu:
        dia0, dia1 = min(dia0, 30), min(dia1, 30)
    else:
        if dia0 == 31:
            dia0 = 30
        if dia1 == 31 and dia0 == 30:
            dia1 = 30
    return 360 * (d1.year - d0.year) + 30 * (d1.month - d0.month) + (dia1 - dia0)


def _fracao_act_act(d0, d1):
    total = 0.0
    for ano in range(d0.year, d1.year + 1):
        ti = max(d0, date(ano, 1, 1))
        tf = min(d1, date(ano + 1, 1, 1))
        if tf > ti:
            total += (tf - ti).days / (366.0 if isleap(ano) else 365.0)
    return total


def dias(convencao, inicio, fim, calendario=None):
    """O numerador da fração: úteis na DU/252, corridos nas ACT, régua de 30
    nas 30/360."""
    d0, d1 = para_data(inicio), para_data(fim)
    if convencao == DU_252:
        return (calendario or calendario_anbima()).dias_uteis(d0, d1)
    if convencao == T30_360:
        return _dias_30_360(d0, d1, europeu=False)
    if convencao == T30E_360:
        return _dias_30_360(d0, d1, europeu=True)
    return (d1 - d0).days


def base(convencao):
    """O denominador — ``None`` na ACT/ACT, que não tem um fixo."""
    if convencao == DU_252:
        return 252
    if convencao == ACT_365:
        return 365
    if convencao == ACT_ACT:
        return None
    return 360


def fracao(convencao, inicio, fim, calendario=None):
    d0, d1 = para_data(inicio), para_data(fim)
    if convencao == ACT_ACT:
        return _fracao_act_act(d0, d1)
    return dias(convencao, d0, d1, calendario) / float(base(convencao))


def fator(taxa, convencao, regime, inicio, fim, calendario=None):
    """Fator de capitalização da taxa no período, na contagem e no regime."""
    tau = fracao(convencao, inicio, fim, calendario)
    if regime == SIMPLES:
        return 1.0 + taxa * tau
    return (1.0 + taxa) ** tau
