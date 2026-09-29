# -*- coding: utf-8 -*-
"""As regras do relatório — puras."""

LOBS = ['CEM', 'EDG']

# LOB da linha (normalizada pelo `_pc_norm`: minúsculas, sem pontuação) → bloco
# do relatório. O report de CEM cobra também as de COMMODITY (mesa, 29/09/2026):
# a mercadoria é da mesa da CEM, e o Pending Confirmation a grava com LOB
# própria (`_lob_for_source`) — fora deste mapa ela sumia do e-mail calada.
LOB_BLOCK = {'cem': 'CEM', 'commodity': 'CEM', 'commodities': 'CEM', 'comm': 'CEM',
             'edg': 'EDG'}


def lob_block(lob_norm):
    """O bloco (CEM/EDG) de uma LOB normalizada, ou None (fica fora do report)."""
    return LOB_BLOCK.get(lob_norm or '')


def subject(ref_fmt):
    return 'Pending Confirmation - Weekly Escalation - CEM/EDG {}'.format(ref_fmt)
