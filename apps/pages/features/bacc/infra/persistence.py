# -*- coding: utf-8 -*-
"""Os três arquivos do card (destinatários, claim do dia, status), em disco."""
import json
import os
import traceback

# O horário do disparo. Fica aqui — e não no domain — porque ler variável de
# ambiente é configuração; quem PARSEIA (com a queda para 16:00) é o
# `domain.time_of`.
TIME_RAW = os.getenv('BACC_EA_METRICS_TIME', '16:00')     # BRT


def _routes():
    """Busca ATRASADA — ver `features/support/infra/persistence.py`.

    `_DAILY_METRIC_DIR` (a pasta dos cards do Control Panel), o claim de slot
    diário, o `_atomic_write_json` e o `log` são plataforma e moram no
    `routes`; e os testes trocam atributos lá.
    """
    from apps.pages import routes
    return routes


def metric_dir():
    return _routes()._DAILY_METRIC_DIR


def recipients_file():
    return os.path.join(metric_dir(), 'bacc_ea_metrics_recipients.json')


def claim_file():
    return os.path.join(metric_dir(), 'bacc_ea_metrics_sent.json')


def status_file():
    return os.path.join(metric_dir(), 'bacc_ea_metrics_status.json')


def load_recipients():
    """As duas listas do card. TO e CC são públicos diferentes: o TO é quem
    responde pela métrica, o CC é quem acompanha."""
    vazio = {'to': '', 'cc': ''}
    try:
        with open(recipients_file(), encoding='utf-8') as fh:
            d = json.load(fh)
        if not isinstance(d, dict):
            return vazio
        return {k: str(d.get(k, '') or '') for k in vazio}
    except Exception:                                       # noqa: BLE001
        return vazio


def save_recipients(d):
    os.makedirs(metric_dir(), exist_ok=True)
    payload = {k: str((d or {}).get(k, '') or '').strip() for k in ('to', 'cc')}
    with open(recipients_file(), 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def claim_slot(slot):
    """Reserva o disparo do dia EM DISCO — a instância reinicia várias vezes ao
    dia e o catch-up precisa saber o que já saiu, senão o mesmo e-mail vai
    embora a cada subida."""
    R = _routes()
    return R._claim_daily_slot(claim_file(), metric_dir(), slot, 16, 'bacc-ea')


def release_slot(slot):
    """Devolve o slot quando o envio falhou (SMTP fora do ar): o catch-up da
    próxima volta tenta de novo. Sem isto uma falha transitória custava o
    relatório do dia inteiro."""
    _routes()._release_daily_slot(claim_file(), slot, 'bacc-ea')


def write_status(slot, result, when):
    R = _routes()
    try:
        os.makedirs(metric_dir(), exist_ok=True)
        R._atomic_write_json(status_file(), {
            'slot': slot, 'result': result,
            'at': when.strftime('%d/%m/%Y %H:%M:%S')})
    except Exception:                                       # noqa: BLE001
        R.log.warning('[bacc-ea] não consegui gravar o status:\n%s', traceback.format_exc())


def read_status():
    try:
        with open(status_file(), encoding='utf-8') as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:                                       # noqa: BLE001
        return {}
