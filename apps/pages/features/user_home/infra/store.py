# -*- coding: utf-8 -*-
"""O documento de CADA usuário: `user-home/<SID>.json` no `DATA_DIR` (no
banco, desde o §434). Guarda o que é dele e de mais ninguém — os eventos do
calendário do Outlook trazidos pelo Sync, o foco (a sessão em curso e as
concluídas) e as preferências da Settings.

    {"sid": "...", "events": [...], "synced_at": "...", "synced_email": "...",
     "focus": {"running": {...} | null, "sessions": [...]},
     "settings": {...}}

Ler → alterar → gravar dentro de `_lock`, como o store do Projects. Ausente é
o documento vazio; ocupado/ilegível SOBE (lido como vazio, o `mutate`
gravaria só a mudança nova por cima do resto, §436).
"""
import os
import re
import threading

_lock = threading.RLock()

# O teste aponta para um tmp trocando este atributo; None = resolver na CHAMADA
# (o import não toca no `DATA_DIR`, §522).
ROOT = None

_SID_RE = re.compile(r'^[A-Z0-9]{1,16}$')


def root():
    if ROOT:
        return ROOT
    from apps.pages.data_paths import data_dir
    return os.path.join(data_dir(), 'user-home')


def path(sid):
    sid = str(sid or '').strip().upper()
    if not _SID_RE.match(sid):
        raise ValueError('bad sid')
    return os.path.join(root(), '%s.json' % sid)


def empty(sid):
    return {'sid': str(sid or '').upper(), 'events': [], 'synced_at': '', 'synced_email': '',
            'focus': {'running': None, 'sessions': []}, 'settings': {}}


def _normaliza(sid, data):
    if not isinstance(data, dict):
        raise ValueError('user-home doc is not an object: %s' % type(data).__name__)
    base = empty(sid)
    base.update(data)
    if not isinstance(base.get('focus'), dict):
        base['focus'] = {'running': None, 'sessions': []}
    base['focus'].setdefault('running', None)
    base['focus'].setdefault('sessions', [])
    if not isinstance(base.get('settings'), dict):
        base['settings'] = {}
    if not isinstance(base.get('events'), list):
        base['events'] = []
    return base


def _read(sid):
    from apps.pages import data_store
    try:
        data = data_store.read(path(sid))
    except FileNotFoundError:
        return empty(sid)
    return _normaliza(sid, data)


def load(sid):
    with _lock:
        return _read(sid)


def load_many(sids):
    """{SID: documento} de várias pessoas (a coluna Right now). Aquece o memo
    com UMA abertura do banco; quem não se lê fica de fora (é só a presença
    dos colegas — melhor esforço)."""
    from apps.pages import data_store
    sids = [str(s or '').upper() for s in sids if _SID_RE.match(str(s or '').upper())]
    try:
        data_store.prefetch([path(s) for s in sids])
    except Exception:                                    # noqa: BLE001
        pass
    out = {}
    for s in sids:
        try:
            out[s] = load(s)
        except Exception:                                # noqa: BLE001
            continue
    return out


def mutate(sid, fn):
    from apps.pages import data_store
    with _lock:
        data = _read(sid)
        result = fn(data)
        data_store.write(path(sid), data)
        return result
