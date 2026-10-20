# -*- coding: utf-8 -*-
"""A foto de cada usuário: `<static>/images/users/<sid>.jpg`, o padrão da barra
do topo (que tenta o arquivo e cai nas iniciais).

Quem pergunta por uma LISTA de pessoas (o Lead e os responsáveis das
Initiatives, a User Home) não pode pagar um `stat` por pessoa: na instância o
código roda do share, e cada `stat` é uma ida e volta de rede (CLAUDE.md §4).
Por isso a pasta é LISTADA uma vez e o resultado vale por um minuto — foto nova
aparece no minuto seguinte, sem restart.
"""
import os
import re
import threading
import time

from flask import current_app

_TTL_SECONDS = 60.0
_SID = re.compile(r'[a-z0-9]+')
_lock = threading.Lock()
_memo = {'at': None, 'root': None, 'names': frozenset()}


def _names():
    root = os.path.join(current_app.static_folder, 'images', 'users')
    agora = time.monotonic()
    with _lock:
        if _memo['root'] == root and _memo['at'] is not None and agora - _memo['at'] < _TTL_SECONDS:
            return _memo['names']
    try:
        with os.scandir(root) as it:
            # minúsculas dos dois lados: a URL é `<sid minúsculo>.jpg` (a da
            # barra) e o Windows da instância não distingue caixa
            nomes = frozenset(e.name.lower() for e in it if e.is_file())
    except OSError:
        nomes = frozenset()
    with _lock:
        _memo.update(at=agora, root=root, names=nomes)
    return nomes


def url(sid):
    """A URL da foto do `sid`, ou '' quando o arquivo não existe (a tela fica
    com as iniciais)."""
    sid = str(sid or '').strip().lower()
    if not _SID.fullmatch(sid):
        return ''
    try:
        if sid + '.jpg' not in _names():
            return ''
        return '%s/images/users/%s.jpg' % (current_app.config.get('ASSETS_ROOT', '/static'), sid)
    except RuntimeError:                                 # fora do app context
        return ''
