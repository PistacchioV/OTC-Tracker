# -*- coding: utf-8 -*-
"""As leituras das Cotações: as opções da tela e as séries das fontes."""
from apps.pages import quotes as motor
from apps.pages.features.quotes import domain
from apps.pages.features.quotes.infra import persistence


def _cadastro(key):
    """As linhas do cadastro do /mapping. Busca ATRASADA — ver o `support`."""
    from apps.pages import routes
    return routes._mapping_rows(key)


def underlyings(kind):
    """[[código, símbolo cadastrado]] de um tipo, em ordem alfabética.

    O símbolo vai JUNTO porque a tela mostra `AAPL34 → AAPL34.SA` na lista: sem
    ele, quem escolhe não distingue o que está cadastrado do que ainda vai
    falhar pedindo cadastro.

    O cadastro é lido UMA vez e vira uma FUNÇÃO: em commodities ele tem linhas
    de PADRÃO (`BO"MY"` → `ZL"MY".CBT`), que só se resolvem contra o código
    concreto — um dicionário não daria conta, e reler o cadastro por subjacente
    o percorreria novecentas vezes na mesma tela.
    """
    key = domain.registry_for(kind)
    if not key:
        return []
    simbolo = motor.symbol_lookup(_cadastro(key))
    vistos = {}
    por_classe = persistence.active_by_class()
    for classe in domain.classes_for(kind):
        vistos.update(por_classe.get(classe) or {})
    return [[code, simbolo(code)] for _k, code in sorted(vistos.items())]


def currencies():
    """As moedas da PTAX como `[código, símbolo]`, iguais às outras duas listas.

    A tela trata as três do mesmo jeito; na PTAX o código É o símbolo.
    """
    return [[c, c] for c in motor.PTAX_CURRENCIES]


def symbol_of(kind, label):
    """O símbolo de mercado do instrumento escolhido, ou `''`."""
    return motor.symbol_for(_cadastro(domain.registry_for(kind)), label)


def ptax(currency, start, end):
    return motor.fetch_ptax(currency, start, end)


def ohlc(symbol, start, end):
    return motor.fetch_ohlc(symbol, start, end)
