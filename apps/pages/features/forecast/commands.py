# -*- coding: utf-8 -*-
"""As escritas do card: gravar as listas e mandar o relatório."""
from apps.pages.features.forecast.infra import mail, persistence


def save_recipients(to, cc):
    persistence.save_recipients(to, cc)


def send(payload, images, to_list, cc_list):
    return mail.send(payload, images, to_list, cc_list)
