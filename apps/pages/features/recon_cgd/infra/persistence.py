# -*- coding: utf-8 -*-
"""O arquivo de destinatários do e-mail da recon."""
import json
import os


def _routes():
    """Busca ATRASADA — ver `features/support/infra/persistence.py`."""
    from apps.pages import routes
    return routes


def recipients_file():
    return os.path.join(_routes()._DAILY_METRIC_DIR, 'cgd_recon_recipients.json')


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
    R = _routes()
    os.makedirs(R._DAILY_METRIC_DIR, exist_ok=True)
    R._atomic_write_json(recipients_file(),
                         {'to': str(to or '').strip(), 'cc': str(cc or '').strip()})
