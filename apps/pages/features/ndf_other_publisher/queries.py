# -*- coding: utf-8 -*-
"""NDF Other Publisher — leituras da vertical. Hoje: o cenário do Email
Validation de cada linha (a coleta em si segue na plataforma do New Deals,
alcançada por `_R()`)."""
from apps.pages.platform import email_validation as _ev


def _R():
    from apps.pages import routes
    return routes


def validation_by_id(rows):
    """{id da linha → {'scenario', 'funds'}} das linhas de `_ndfop_collect`
    (`[...células, status, maker, checker, id]`), pelas duas CONTAS da linha —
    as já editadas, que são as que o arquivo leva."""
    cols = _R()._NDFOP_COLUMNS
    n, i_p, i_c = len(cols), cols.index('CONTA PARTE'), cols.index('CONTA CONTRAPARTE')
    return {str(r[n + 3]): _ev.scenario(r[i_p], r[i_c]) for r in rows or []}
