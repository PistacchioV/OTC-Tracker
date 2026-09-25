# -*- coding: utf-8 -*-
"""Os destinatários do card Branch Settlement Reverse Approval (Control Panel).

Moram ao lado dos outros cards do painel (`_DAILY_METRIC_DIR`), gravados pelo
funil — é o mesmo desenho do MT300."""
import os

from apps.pages import data_store as _store  # noqa: E402


def _routes():
    """Busca ATRASADA: `_DAILY_METRIC_DIR` e o funil moram no `routes`, e os
    testes trocam atributos lá."""
    from apps.pages import routes
    return routes


def recipients_file():
    return os.path.join(_routes()._DAILY_METRIC_DIR, 'branch_settlement_recipients.json')


def load_recipients():
    try:
        d = _store.read(recipients_file())
        if isinstance(d, dict):
            return {'to': str(d.get('to', '') or ''), 'cc': str(d.get('cc', '') or '')}
    except FileNotFoundError:
        pass
    return {'to': '', 'cc': ''}


def save_recipients(d):
    os.makedirs(os.path.dirname(recipients_file()), exist_ok=True)
    atual = load_recipients()
    # Merge, não substituição: uma tela que não conhecesse uma das chaves
    # apagaria aquela lista ao gravar.
    for k in ('to', 'cc'):
        if k in (d or {}):
            atual[k] = str((d or {}).get(k) or '').strip()
    _routes()._atomic_write_json(recipients_file(), atual)
