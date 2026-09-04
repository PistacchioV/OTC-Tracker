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

    A lista é a UNIÃO de duas fontes: os ACTIVE do Subjacente (Index B3) e as
    linhas LITERAIS do próprio cadastro do /mapping. A segunda existe porque o
    de-para aceita rótulo que não é código do Subjacente (`S&P 500 Index` →
    `^GSPC`), e sem ela o mapping recém-criado não aparecia na lista da tela —
    cadastrado, resolvível pela API, e invisível para quem escolhe. Linha de
    PADRÃO (`BO"MY"`) fica de fora: é regra, não instrumento — listada, viraria
    uma opção que a busca literal não resolve.

    O cadastro é lido UMA vez e vira uma FUNÇÃO: em commodities ele tem linhas
    de PADRÃO (`BO"MY"` → `ZL"MY".CBT`), que só se resolvem contra o código
    concreto — um dicionário não daria conta, e reler o cadastro por subjacente
    o percorreria novecentas vezes na mesma tela.
    """
    key = domain.registry_for(kind)
    if not key:
        return []
    rows = _cadastro(key)
    simbolo = motor.symbol_lookup(rows)
    vistos = {}
    por_classe = persistence.active_by_class()
    for classe in domain.classes_for(kind):
        vistos.update(por_classe.get(classe) or {})
    for r in (rows or []):
        rotulo = ' '.join(str(r.get('LABEL') or '').split())
        if not rotulo or not str(r.get('SYMBOL') or '').strip():
            continue
        if motor.has_b3_marker(rotulo):
            continue
        # setdefault: o rótulo que JÁ é código do Subjacente mantém a grafia
        # de lá — duplicar `PETR4` só porque o cadastro o escreveu `petr4`
        # poria o mesmo instrumento duas vezes na lista.
        vistos.setdefault(rotulo.upper(), rotulo)
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
