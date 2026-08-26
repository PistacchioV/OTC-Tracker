# -*- coding: utf-8 -*-
"""As leituras do card: a versão lida agora, quem receberia e o último envio."""
from apps.pages.features.appver.infra import persistence


def read_link():
    """(versao, texto_lido, erro) do link.txt."""
    return persistence.read_link()


def link_path():
    """O caminho que o card mostra — é como se confere para ONDE ele olhou."""
    return persistence.LINK_FILE


def active_users():
    return persistence.active_users()


def recipients():
    return persistence.load_recipients()


def status():
    return persistence.read_status()
