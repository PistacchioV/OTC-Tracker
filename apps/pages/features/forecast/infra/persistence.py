# -*- coding: utf-8 -*-
"""O arquivo de destinatários do card."""
import json
import os


def _routes():
    """Busca ATRASADA — ver `features/support/infra/persistence.py`."""
    from apps.pages import routes
    return routes


def recipients_file():
    return os.path.join(_routes()._DAILY_METRIC_DIR, 'settlement_forecast_recipients.json')


def load_recipients():
    try:
        with open(recipients_file(), encoding='utf-8') as fh:
            d = json.load(fh)
        if isinstance(d, dict):
            return {'to': d.get('to', '') or '', 'cc': d.get('cc', '') or ''}
    except Exception:
        pass
    return {'to': '', 'cc': ''}


def save_recipients(to, cc):
    os.makedirs(_routes()._DAILY_METRIC_DIR, exist_ok=True)
    _routes()._atomic_write_json(recipients_file(),
                                 {'to': to or '', 'cc': cc or ''})

