# -*- coding: utf-8 -*-
"""As leituras da tela."""


def data():
    from apps.pages.recon_comitente import load_from_db
    return load_from_db()
