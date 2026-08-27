# -*- coding: utf-8 -*-
"""As regras puras do Intrag — as duas contas do par intragrupo (JPM × Lawton),
o nome do participante de cada lado e a chave de casamento do retorno da B3.

Puro: nada aqui importa `routes`, Flask ou disco.
"""


_INTRAG_OPT_JPM_ACC    = '73760.00-9'


_INTRAG_OPT_LAWTON_ACC = '00041.00-7'


_INTRAG_OPT_JPM_NAME    = 'BANCO J.P MORGAN S.A'


_INTRAG_OPT_LAWTON_NAME = 'LAWTON MULTIMERCADO-FI'


def _intrag_opt_name_for(acc):
    if acc == _INTRAG_OPT_JPM_ACC:
        return _INTRAG_OPT_JPM_NAME
    if acc == _INTRAG_OPT_LAWTON_ACC:
        return _INTRAG_OPT_LAWTON_NAME
    return ''


def _intrag_b3_key(v):
    """B3 ID match key — stripped, leading zeros dropped (both sides)."""
    s = str(v or '').strip()
    return s.lstrip('0') or s
