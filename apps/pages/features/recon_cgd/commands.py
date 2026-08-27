# -*- coding: utf-8 -*-
"""O Run, as listas e o e-mail da recon."""
from apps.pages import recon_cgd as motor
from apps.pages.features.recon_cgd import domain
from apps.pages.features.recon_cgd.infra import persistence


def run(ref):
    """Roda o batimento e GRAVA o cache com a data da posição. `ref` já vem
    parseado (ou None = D-1, o default do motor)."""
    res = motor.executar(ref)
    motor.salvar(res)
    return res


def save_recipients(to, cc):
    persistence.save_recipients(to, cc)


def send_email(res):
    """(ok, motivo) — manda o relatório carregado para as listas gravadas."""
    rec = persistence.load_recipients()
    ok, motivo = motor.enviar_email(res, domain.emails(rec['to']), domain.emails(rec['cc']))
    return ok, motivo, rec
