# -*- coding: utf-8 -*-
"""O arquivo de destinatários do card."""
import json
import os


def _routes():
    """Busca ATRASADA — ver `features/support/infra/persistence.py`."""
    from apps.pages import routes
    return routes


def metric_dir():
    return _routes()._DAILY_METRIC_DIR


def recipients_file():
    return os.path.join(metric_dir(), 'weekly_escalation_recipients.json')


def load_recipients():
    try:
        with open(recipients_file(), encoding='utf-8') as fh:
            d = json.load(fh)
        if isinstance(d, dict):
            return {'to': d.get('to', '') or '', 'cc': d.get('cc', '') or ''}
    except Exception:                                       # noqa: BLE001
        pass
    return {'to': '', 'cc': ''}


def save_recipients(to, cc):
    os.makedirs(metric_dir(), exist_ok=True)
    with open(recipients_file(), 'w', encoding='utf-8') as fh:
        json.dump({'to': to or '', 'cc': cc or ''}, fh, ensure_ascii=False, indent=2)
