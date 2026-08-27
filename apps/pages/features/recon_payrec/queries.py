# -*- coding: utf-8 -*-
"""As leituras da tela."""


def last(recon_date):
    from apps.pages.recon_payrec import load_last
    return load_last(recon_date)
