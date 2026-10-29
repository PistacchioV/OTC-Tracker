# -*- coding: utf-8 -*-
"""RED Clients: quem está marcado e a última rodada (§730).

A lista é horizontal (`platform/red_clients`): as telas de liquidação também
perguntam. Aqui fica só a fachada da vertical.
"""
from apps.pages.platform import red_clients as _red
from apps.pages.features.red_clients.infra import persistence


def flagged():
    return _red.flagged()


def status():
    return persistence.read_status()
