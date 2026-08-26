# -*- coding: utf-8 -*-
"""O que é um "tipo" de cotação. Puro — sem I/O, sem Flask.

As opções de Equities e Commodities são as MESMAS do Index B3 › Ativo
Subjacente (`Subjacente.json`), separadas pelo campo `Classe`. Só a lista de
moedas da PTAX é fixa, e ela **não é cadastro**: é o domínio do endpoint do BCB.
"""

# tipo → (cadastro do /mapping, classes do Subjacente que o alimentam)
KINDS = {
    'equity':    ('quotes-equity',
                  ('AÇÕES', 'AÇÕES INTERNACIONAIS', 'INDICES', 'INDICES INTERNACIONAIS')),
    'commodity': ('quotes-commodity', ('COMMODITIES',)),
}


def is_known(kind):
    """Tipo fora da lista é 404 na tela, e não um `KeyError` virando 500."""
    return kind in KINDS


def registry_for(kind):
    """O cadastro do /mapping de onde o símbolo daquele tipo sai."""
    return KINDS.get(kind, ('', ()))[0]


def classes_for(kind):
    """As classes do Subjacente que alimentam aquele tipo."""
    return KINDS.get(kind, ('', ()))[1]
