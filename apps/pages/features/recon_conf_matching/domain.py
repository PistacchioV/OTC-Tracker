# -*- coding: utf-8 -*-
"""As regras da casca — puras."""


def error_text(exc):
    """`Tipo: mensagem` (§476): a frase é a única coisa que a mesa vê, e "não
    deu" não distingue SSO recusado de relatório que não chegou no box."""
    return '{}: {}'.format(type(exc).__name__, exc)
