# -*- coding: utf-8 -*-
"""Os três arquivos do card e a leitura do arquivo-dia do NDF Vanilla."""
import json
import os
import traceback

from apps.pages.features.mt300 import domain


def _routes():
    """Busca ATRASADA — ver `features/support/infra/persistence.py`.

    `_DAILY_METRIC_DIR`, o claim de slot diário, o `_atomic_write_json`, o
    `_generic_nd_cfg` e o `log` são plataforma e moram no `routes`; e os testes
    trocam atributos lá.
    """
    from apps.pages import routes
    return routes


def metric_dir():
    return _routes()._DAILY_METRIC_DIR


def recipients_file():
    return os.path.join(metric_dir(), 'mt300_recipients.json')


def status_file():
    return os.path.join(metric_dir(), 'mt300_status.json')


def claim_file():
    return os.path.join(metric_dir(), 'mt300_sent.json')


def load_recipients():
    try:
        with open(recipients_file(), encoding='utf-8') as fh:
            d = json.load(fh)
        if isinstance(d, dict):
            return {'to': str(d.get('to', '') or ''),
                    'cc': str(d.get('cc', domain.CC_DEFAULT) or '')}
    except Exception:                                       # noqa: BLE001
        pass
    return {'to': '', 'cc': domain.CC_DEFAULT}


def save_recipients(d):
    os.makedirs(metric_dir(), exist_ok=True)
    atual = load_recipients()
    # Merge, não substituição: uma tela que não conhecesse uma das chaves
    # apagaria aquela lista ao gravar.
    for k in ('to', 'cc'):
        if k in (d or {}):
            atual[k] = str((d or {}).get(k) or '').strip()
    _routes()._atomic_write_json(recipients_file(), atual)


def load_day(ref):
    """As linhas cruas do arquivo-dia do NDF Vanilla, ou [] quando ele não
    existe/não parseia — o card não pode cair por um dia sem arquivo."""
    R = _routes()
    cfg = R._generic_nd_cfg('vanilla')
    path = os.path.join(cfg['dir'], ref.strftime('%Y'), ref.strftime('%m'),
                        ref.strftime('%Y%m%d') + cfg['suffix'])
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (IOError, OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def claim_slot(slot):
    """Reserva o disparo EM DISCO: a instância reinicia várias vezes ao dia, e o
    catch-up precisa saber o que já saiu."""
    R = _routes()
    return R._claim_daily_slot(claim_file(), metric_dir(), slot, 16, 'mt300')


def release_slot(slot):
    """Devolve o slot quando o envio falhou: uma queda transitória do SMTP não
    pode custar o e-mail do dia."""
    _routes()._release_daily_slot(claim_file(), slot, 'mt300')


def write_status(result, when):
    R = _routes()
    try:
        os.makedirs(metric_dir(), exist_ok=True)
        R._atomic_write_json(status_file(),
                             {'result': result, 'at': when.strftime('%d/%m/%Y %H:%M:%S')})
    except Exception:                                       # noqa: BLE001
        R.log.warning('[mt300] não consegui gravar o status:\n%s', traceback.format_exc())


def read_status():
    try:
        with open(status_file(), encoding='utf-8') as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:                                       # noqa: BLE001
        return {}
