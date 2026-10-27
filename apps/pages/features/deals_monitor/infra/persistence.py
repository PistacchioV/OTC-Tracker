# -*- coding: utf-8 -*-
"""Os arquivos do aviso de pendências — destinatários, claim de slot (cross-
process) e o status do último disparo. Os caminhos são módulo-level de
propósito (mesmo contrato do engine que isto substitui): o teste os rebinda
para um tmp, e todo leitor deste módulo resolve pelo atributo na chamada.
"""
import json
import os
import threading
import time
import traceback

from apps.pages.features.deals_monitor import domain
from apps.pages import data_store as _store  # noqa: E402


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
        d = _store.read(_NDM_PENDING_RECIPIENTS_FILE)
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


# ── Intraday Monitor: a agenda das tarefas (card `intradaytasks`, §567) ──────
_INTRADAY_TASKS_FILE = os.path.join(_R()._DAILY_METRIC_DIR, 'intraday_tasks.json')


def _load_intraday_tasks(strict=False):
    """A agenda SALVA (`{task_id: {days, deadline}}`), crua — quem aplica o
    padrão é o `domain.task_config`. Nada salvo é `{}`.

    `strict=True` é a leitura do Control Panel: banco ocupado ou ilegível SOBE
    (§548). Lida como `{}`, a tela mostraria os padrões e o Save seguinte
    gravaria os padrões por cima da agenda da mesa. A tolerante é a do Monitor:
    falha vira padrão, com a causa no log."""
    try:
        d = _store.read(_INTRADAY_TASKS_FILE)
    except FileNotFoundError:
        return {}
    except Exception:
        if strict:
            raise
        _R().log.warning('[intraday-monitor] agenda ilegível — valendo o padrão:\n%s',
                         traceback.format_exc())
        return {}
    return d if isinstance(d, dict) else {}


def _save_intraday_tasks(cfg):
    """Grava a agenda INTEIRA (o card manda todas as tarefas de uma vez), já
    normalizada pelo `domain.task_config` — o arquivo nunca guarda o que a
    leitura não saberia interpretar."""
    _R()._atomic_write_json(_INTRADAY_TASKS_FILE, domain.task_config(cfg))


# ── Owner e backup das tarefas (§701) ────────────────────────────────────────
_ASSIGN_FILE = os.path.join(_R()._DAILY_METRIC_DIR, 'intraday_assignments.json')


def _load_assignments(strict=False):
    """A lista SALVA de owner/backup, já limpa pelo `domain.clean_assignments`.
    `strict=True` é a leitura de quem vai GRAVAR (o POST compara com o
    anterior para avisar só os designados novos): ocupado SOBE, nunca vira
    lista vazia — senão todo mundo seria avisado de novo."""
    try:
        d = _store.read(_ASSIGN_FILE)
    except FileNotFoundError:
        return []
    except Exception:
        if strict:
            raise
        _R().log.warning('[intraday-monitor] owners ilegíveis:\n%s', traceback.format_exc())
        return []
    return domain.clean_assignments(d)


def _save_assignments(lista):
    _R()._atomic_write_json(_ASSIGN_FILE, domain.clean_assignments(lista))


_people_memo = {'at': 0.0, 'rows': None}
_people_lock = threading.Lock()


# Quem pode ser owner/backup: as tarefas do Monitor são do OTC Ops (equipe,
# 27/10/2026, §703) — BO, ADMIN e o master, nunca MO/FO/HUB.
_ASSIGN_ROLES = ('BO', 'ADMIN')


def _assignable_people():
    """Quem pode ser owner/backup: o cadastro com Status ACTIVE e papel BO ou
    ADMIN, mais o master (por SID, `authz._MASTER_SIDS`), em ordem alfabética,
    com a foto (`user_photos`). Uma leitura a cada 5 min (o snapshot do Monitor
    pede a cada minuto); falha devolve a última lista boa."""
    from apps.pages.platform import authz, user_photos
    with _people_lock:
        if _people_memo['rows'] is not None and time.time() - _people_memo['at'] < 300:
            return _people_memo['rows']
    try:
        conn = _R().get_db_connection(readonly=True)
        try:
            linhas = conn.execute('SELECT SID, Name, Status, Role FROM users').fetchall()
        finally:
            conn.close()
    except Exception:                                       # noqa: BLE001
        _R().log.warning('[intraday-monitor] não li o cadastro de usuários', exc_info=True)
        with _people_lock:
            return _people_memo['rows'] or []
    rows = sorted(({'sid': str(sid or '').strip().upper(), 'name': (nome or '').strip() or str(sid).upper(),
                    'photo': user_photos.url(str(sid or '').strip().upper())}
                   for sid, nome, st, papel in linhas
                   if str(sid or '').strip() and str(st or '').strip().upper() == 'ACTIVE'
                   and (str(papel or '').strip().upper() in _ASSIGN_ROLES
                        or str(sid).strip().upper() in authz._MASTER_SIDS)),
                  key=lambda p: p['name'].lower())
    with _people_lock:
        _people_memo['at'], _people_memo['rows'] = time.time(), rows
    return rows
