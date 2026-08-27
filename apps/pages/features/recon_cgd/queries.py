# -*- coding: utf-8 -*-
"""As leituras da tela."""
from apps.pages import recon_cgd as motor
from apps.pages.features.recon_cgd.infra import persistence


def load(ref):
    return motor.carregar(ref or None)


def empty_payload(ref):
    """O corpo da tela vazia: diz de que dia seria a recon que ninguém rodou —
    e NÃO roda sozinha: um GET que varre o share é um GET que trava."""
    dia = motor.dia_util_anterior()
    return {'success': True, 'empty': True,
            'ref': (ref or dia.strftime('%Y-%m-%d')),
            'ref_fmt': motor._fmt_date(motor._parse_date(ref) or dia),
            'rows': [], 'counts': {}, 'warnings': []}


def recipients():
    return persistence.load_recipients()
