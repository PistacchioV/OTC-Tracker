# -*- coding: utf-8 -*-
"""CDI realizado — série diária do Banco Central e acúmulo entre duas datas.

Isto **não** é projeção: é o que o CDI de fato rendeu, dia a dia, como a
calculadora de renda fixa da B3 faz na aba "DI". Por isso a data final não
pode passar de hoje.

Fonte: série 4389 do SGS — "Taxa de juros CDI anualizada base 252".

    fator = Π [ 1 + ((1 + DI_k)^(1/252) − 1) · p ]

com um termo por **dia útil publicado no intervalo [início, fim)** — a taxa
de um dia rende naquele dia, então a do dia final não entra. É isso que faz o
número bater com a calculadora da B3.
"""
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from apps.pages.precificador import rede
from apps.pages.precificador.calendario import para_data
from apps.pages.precificador.erros import ErroDeDado, ErroDeFonte

SGS_CDI = 4389
API = 'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados'


class ErroBCB(ErroDeFonte):
    """Falha ao obter a série do Banco Central."""


@dataclass(frozen=True)
class FixingCDI:
    data: date
    taxa: float          # decimal ao ano, base 252 (0.149 = 14,90%)


def serie(inicio, fim, codigo=SGS_CDI, timeout=40):
    """Série diária do SGS entre as duas datas, em ordem crescente. O BCB
    publica com um dia de defasagem — o acúmulo usa o que existe."""
    d0, d1 = para_data(inicio), para_data(fim)
    if d1 < d0:
        raise ErroDeDado('the end date cannot be earlier than the start date')
    url = ('{}?formato=json&dataInicial={:%d/%m/%Y}&dataFinal={:%d/%m/%Y}'
           .format(API.format(serie=codigo), d0, d1))
    try:
        bruto = rede.obter_json(url, timeout=timeout)
    except rede.ErroRede as exc:
        raise ErroBCB('could not fetch BCB series {codigo}: {motivo}',
                      codigo=codigo, motivo=str(exc)) from exc
    fixings = []
    for linha in bruto or []:
        try:
            fixings.append(FixingCDI(para_data(linha['data']), float(linha['valor']) / 100.0))
        except (KeyError, ValueError, TypeError):
            continue
    return sorted(fixings, key=lambda f: f.data)


@dataclass
class DiaCDI:
    data: date
    taxa: float
    fator_dia: float
    fator_acumulado: float


@dataclass
class ResultadoCDI:
    inicio: date
    fim: date
    percentual: float
    fator: float
    taxa_periodo: float
    taxa_anual_equivalente: float
    valor_base: float
    valor_calculado: float
    dias_uteis: int
    dias_corridos: int
    primeiro: Optional[date]
    ultimo: Optional[date]
    arredondado: bool
    dias: List[DiaCDI]


def acumular(fixings, inicio, fim, percentual=1.0, valor=1000.0, arredondar=False):
    """Acumula o CDI publicado no intervalo [início, fim). ``arredondar=True``
    reproduz o padrão B3/CETIP (fator diário truncado na 8ª casa)."""
    d0, d1 = para_data(inicio), para_data(fim)
    if d1 <= d0:
        raise ErroDeDado('the end date must be later than the start date')
    usados = [f for f in fixings if d0 <= f.data < d1]
    if not usados:
        raise ErroBCB(
            'the Central Bank published no CDI between {inicio} and {fim}. The '
            'series runs one day late and does not cover future dates.',
            inicio='{:%d/%m/%Y}'.format(d0), fim='{:%d/%m/%Y}'.format(d1))
    fator = 1.0
    linhas = []
    for f in usados:
        fator_dia = (1.0 + f.taxa) ** (1.0 / 252.0)
        if arredondar:
            fator_dia = round(fator_dia, 8)
        fator_dia = 1.0 + (fator_dia - 1.0) * percentual
        if arredondar:
            fator_dia = round(fator_dia, 16)
        fator *= fator_dia
        linhas.append(DiaCDI(f.data, f.taxa, fator_dia, fator))
    dias_uteis = len(usados)
    equivalente = fator ** (252.0 / dias_uteis) - 1.0 if dias_uteis else 0.0
    return ResultadoCDI(
        inicio=d0, fim=d1, percentual=percentual, fator=fator, taxa_periodo=fator - 1.0,
        taxa_anual_equivalente=equivalente, valor_base=valor, valor_calculado=valor * fator,
        dias_uteis=dias_uteis, dias_corridos=(d1 - d0).days,
        primeiro=usados[0].data, ultimo=usados[-1].data, arredondado=arredondar, dias=linhas)


def acumular_do_bcb(inicio, fim, percentual=1.0, valor=1000.0, arredondar=False):
    return acumular(serie(inicio, fim), inicio, fim, percentual, valor, arredondar)
