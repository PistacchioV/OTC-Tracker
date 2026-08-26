# -*- coding: utf-8 -*-
"""As leituras do card: o que o anexo teria, as listas e o último desfecho."""
from apps.pages.features.bacc import domain
from apps.pages.features.bacc.infra import persistence


def rows():
    """As linhas que o anexo teria AGORA — a mesma esteira do Track
    Confirmations, com os dois cortes do `domain.pending`."""
    from apps.pages import manual_conf
    return domain.pending(manual_conf.load_all(), manual_conf.STATUS_OK)


def recipients():
    return persistence.load_recipients()


def status():
    return persistence.read_status()


def send_time():
    """(hh, mm) do disparo em BRT."""
    return domain.time_of(persistence.TIME_RAW)
