# -*- coding: utf-8 -*-
"""As leituras da tela."""
from apps.pages import recon_cgd as cgd
from apps.pages import recon_conf_matching as motor


def parse_date(v):
    return cgd._parse_date(v)


def load(ref):
    return motor.carregar(ref or None)


def empty_payload(ref):
    """O corpo da tela vazia: diz de que dia seria a recon que ninguém rodou —
    e NÃO roda sozinha: um GET que abre o Outlook e chama a Athena é um GET
    que trava."""
    dia = cgd._parse_date(ref) or cgd.dia_util_anterior()
    return {'success': True, 'empty': True,
            'ref': dia.strftime('%Y-%m-%d'), 'ref_fmt': cgd._fmt_date(dia),
            'columns': list(motor.COLUMNS), 'rows': [], 'counts': motor.contar([]), 'warnings': []}
