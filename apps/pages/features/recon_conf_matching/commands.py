# -*- coding: utf-8 -*-
"""O Run e o comentário da recon."""
from apps.pages import recon_conf_matching as motor


def run(ref):
    """Roda o batimento e GRAVA o cache do trade date. `ref` já vem parseado
    (ou None = D-1, o default do motor)."""
    res = motor.executar(ref)
    motor.salvar(res)
    return res


def save_comment(key, comment):
    return motor.save_comment(key, comment)
