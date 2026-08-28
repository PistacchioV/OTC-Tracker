# -*- coding: utf-8 -*-
"""Os três arquivos do card (listas, claim, status)."""
import json
import os
import traceback

from apps.pages.features.conf_escalation import domain

# O horário do disparo — configuração, com o parse (e a queda para 17:00) no
# `domain.time_of`.
TIME_RAW = os.getenv('CONF_ESCALATION_TIME', '17:00')       # BRT


def _routes():
    """Busca ATRASADA — ver `features/support/infra/persistence.py`."""
    from apps.pages import routes
    return routes


def metric_dir():
    return _routes()._DAILY_METRIC_DIR


def recipients_file():
    return os.path.join(metric_dir(), 'confirmations_escalation_recipients.json')


def claim_file():
    return os.path.join(metric_dir(), 'confirmations_escalation_sent.json')


def status_file():
    return os.path.join(metric_dir(), 'confirmations_escalation_status.json')


def load_recipients():
    """As listas do card. Cada uma é um público diferente."""
    vazio = {k: '' for k in domain.REC_KEYS}
    try:
        with open(recipients_file(), encoding='utf-8') as fh:
            d = json.load(fh)
        if not isinstance(d, dict):
            return vazio
        out = {k: str(d.get(k, '') or '') for k in domain.REC_KEYS}
        # `fo_to` era UMA lista para o Front Office inteiro, antes de os
        # destinatários passarem a mudar por produto. Ela vale como padrão do
        # grupo que ainda não tem lista própria — senão quem já tinha preenchido
        # o campo antigo veria a cobrança do FO parar de sair sem aviso.
        legado = str(d.get('fo_to', '') or '')
        if legado:
            for g in domain.FO_GROUPS:
                out[g['rec']] = out[g['rec']] or legado
        return out
    except Exception:                                       # noqa: BLE001
        return vazio


def save_recipients(d):
    os.makedirs(metric_dir(), exist_ok=True)
    payload = {k: str((d or {}).get(k, '') or '').strip() for k in domain.REC_KEYS}
    _routes()._atomic_write_json(recipients_file(), payload)


def claim_slot(slot):
    """Reserva um disparo EM DISCO (mesma mecânica do Deals Monitor: a trava em
    memória não impede que dois processos mandem o mesmo e-mail)."""
    R = _routes()
    return R._claim_daily_slot(claim_file(), metric_dir(), slot, 24, 'conf-escalation')


def release_slot(slot):
    """Devolve o slot quando o envio falhou, para o catch-up da próxima volta
    tentar de novo — senão uma queda de SMTP às 17h custa a cobrança do dia."""
    _routes()._release_daily_slot(claim_file(), slot, 'conf-escalation')


def write_status(mode, slot, result, when):
    """Desfecho do último disparo de cada modo. O log do servidor tem a resposta
    e ninguém o lê — é isto que faz o card responder "a cobrança saiu?"."""
    R = _routes()
    with R._cache_lock:
        try:
            with open(status_file(), encoding='utf-8') as fh:
                d = json.load(fh)
            if not isinstance(d, dict):
                d = {}
        except (IOError, OSError, json.JSONDecodeError):
            d = {}
        d[mode] = {'slot': slot, 'result': result,
                   'at': when.strftime('%d/%m/%Y %H:%M:%S')}
        try:
            os.makedirs(metric_dir(), exist_ok=True)
            R._atomic_write_json(status_file(), d)
        except Exception:                                   # noqa: BLE001
            R.log.warning('[conf-escalation] não consegui gravar o status:\n%s',
                          traceback.format_exc())


def read_status():
    try:
        with open(status_file(), encoding='utf-8') as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (IOError, OSError, json.JSONDecodeError):
        return {}
