# -*- coding: utf-8 -*-
"""Os arquivos do aviso de pendências — destinatários, claim de slot (cross-
process) e o status do último disparo. Os caminhos são módulo-level de
propósito (mesmo contrato do engine que isto substitui): o teste os rebinda
para um tmp, e todo leitor deste módulo resolve pelo atributo na chamada.
"""
import json
import os
import traceback

from apps.pages.features.deals_monitor import domain


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


_NDM_PENDING_RECIPIENTS_FILE = os.path.join(_R()._DAILY_METRIC_DIR,
                                            'deals_monitor_pending_recipients.json')

_NDM_PENDING_SENT_FILE = os.path.join(_R()._DAILY_METRIC_DIR, 'deals_monitor_pending_sent.json')

_NDM_PENDING_STATUS_FILE = os.path.join(_R()._DAILY_METRIC_DIR, 'deals_monitor_pending_status.json')


def _load_ndm_pending_recipients():
    """TO/CC do aviso, do card Deals Monitor do Control Panel. Sem nada salvo
    vale o default da mesa — assim a rotina já funciona no pull, antes de
    alguém abrir o Control Panel."""
    try:
        with open(_NDM_PENDING_RECIPIENTS_FILE, encoding='utf-8') as fh:
            d = json.load(fh)
        if isinstance(d, dict) and (d.get('to') or d.get('cc')):
            return {'to': d.get('to', '') or '', 'cc': d.get('cc', '') or ''}
    except Exception:
        pass
    return {'to': domain._NDM_PENDING_DEFAULT_TO, 'cc': ''}


def _save_ndm_pending_recipients(to, cc):
    os.makedirs(_R()._DAILY_METRIC_DIR, exist_ok=True)
    _R()._atomic_write_json(_NDM_PENDING_RECIPIENTS_FILE,
                            {'to': to or '', 'cc': cc or ''})


def _ndm_pending_claim_slot(slot):
    """Reserva um disparo ('YYYY-MM-DD 19:00') EM DISCO. True = ninguém tinha
    reservado e o e-mail pode sair; False = já foi. Cross-process: duas
    instâncias do app não podem reservar o mesmo slot (ver `_claim_daily_slot`)."""
    return _R()._claim_daily_slot(_NDM_PENDING_SENT_FILE, _R()._DAILY_METRIC_DIR, slot, 16, 'deals-monitor')


def _ndm_pending_release_slot(slot):
    """Devolve um slot reivindicado, para que ele possa ser tentado de novo.

    Existe porque a reserva é feita ANTES do envio (é o que impede dois
    processos de mandarem o mesmo aviso). Se o envio falha — SMTP fora do ar,
    rede caindo, o que for — e o slot fica reservado, o aviso daquele horário
    está perdido para sempre: nem o próximo restart o recupera, porque o
    catch-up também consulta esta lista. Uma falha transitória virava um dia sem
    aviso, sem nada na tela para explicar."""
    _R()._release_daily_slot(_NDM_PENDING_SENT_FILE, slot, 'deals-monitor')


def _ndm_pending_status_write(slot, result, when):
    """Grava o desfecho do último disparo, para a tela poder responder "o aviso
    das 19h saiu?". O log do servidor tinha a resposta e ninguém o lê."""
    try:
        os.makedirs(_R()._DAILY_METRIC_DIR, exist_ok=True)
        _R()._atomic_write_json(_NDM_PENDING_STATUS_FILE, {
            'slot': slot, 'result': result,
            'at': when.strftime('%d/%m/%Y %H:%M:%S'),
        })
    except Exception:                                       # noqa: BLE001
        _R().log.warning('[deals-monitor] não consegui gravar o status do disparo:\n%s',
                    traceback.format_exc())
