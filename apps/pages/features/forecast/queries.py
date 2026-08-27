# -*- coding: utf-8 -*-
"""As leituras do card."""
from apps.pages.features.forecast.infra import persistence


def recipients():
    return persistence.load_recipients()
