# -*- coding: utf-8 -*-
"""As escritas da User Home e da Settings: o Sync do calendário, o foco e as
preferências — cada uma num ciclo ler → alterar → gravar do documento do
PRÓPRIO usuário (`store.mutate`). E o laço do aviso "vence hoje", às 08:00.
"""
import logging
import threading
import time
from datetime import datetime, timedelta

from apps.pages.features.user_home import domain
from apps.pages.features.user_home.infra import outlook, store

log = logging.getLogger('otc_tracker')

SYNC_DAYS = 8                      # hoje + a semana que vem
PAGE = 'User Home'
DUE_HOUR = 8                       # o aviso das tarefas que vencem hoje (BRT)


def _routes():
    from apps.pages import routes
    return routes


# ── Sync ──────────────────────────────────────────────────────────────────────

def sync(me, now):
    """Traz do Outlook da máquina os eventos de hoje até `SYNC_DAYS` dias e
    SUBSTITUI os gravados (o calendário é a fonte; o que foi desmarcado lá
    some daqui). Levanta `outlook.OutlookUnavailable` fora do Windows."""
    n = datetime.fromisoformat(now[:19])
    ini = n.replace(hour=0, minute=0, second=0)
    eventos = outlook.read_calendar(me.get('email', ''), ini, ini + timedelta(days=SYNC_DAYS))

    def go(doc):
        doc['events'] = eventos
        doc['synced_at'] = now[:19]
        doc['synced_email'] = me.get('email', '')
        return len(eventos)
    total = store.mutate(me['sid'], go)
    log.info('[user-home] %s sincronizou %d evento(s) do Outlook', me['sid'], total)
    return total


# ── Foco ──────────────────────────────────────────────────────────────────────

def _task_ref(projetos, project_id, task_id):
    """O título da tarefa vem do PROJETO, nunca do navegador."""
    for p in projetos or []:
        if p.get('id') == project_id:
            for t in p.get('tasks') or []:
                if t.get('id') == task_id:
                    return {'project_id': project_id, 'task_id': task_id, 'task_title': t.get('title', '')}
    return {}


def focus(me, action, body, now):
    """start | pause | resume | end. Devolve (estado, sessão gravada ou None)."""
    body = body or {}
    ref = {}
    if action == 'start' and body.get('task_id'):
        try:
            ref = _task_ref(_routes()._projects_doc().get('projects'), str(body.get('project_id') or ''),
                            str(body.get('task_id') or ''))
        except Exception:                                # noqa: BLE001
            ref = {}

    def go(doc):
        f = doc.setdefault('focus', {'running': None, 'sessions': []})
        sessao = None
        if action == 'start':
            if f.get('running'):
                f, sessao = domain.focus_end(f, now)
            minutos = body.get('minutes')
            if minutos in (None, ''):
                minutos = domain.settings(doc)['focus_minutes']
            domain.focus_start(f, now, minutos, ref)
        elif action == 'pause':
            domain.focus_pause(f, now)
        elif action == 'resume':
            domain.focus_resume(f, now)
        elif action == 'end':
            f, sessao = domain.focus_end(f, now)
        else:
            raise domain.HomeError('bad_action', 'Unknown action.', action=action)
        doc['focus'] = f
        return sessao, doc
    sessao, doc = store.mutate(me['sid'], go)
    return doc, sessao


# ── Settings ─────────────────────────────────────────────────────────────────

def save_settings(me, data):
    def go(doc):
        doc['settings'] = domain.clean_settings(data, doc.get('settings'))
        return doc['settings']
    return store.mutate(me['sid'], go)


def save_favorites(me, data):
    """Substitui a lista de favoritos (a ordem é a da tela). → a lista gravada."""
    lista = domain.clean_favorites(data)

    def go(doc):
        doc['favorites'] = lista
        return lista
    return store.mutate(me['sid'], go)


def reset_settings(me):
    def go(doc):
        doc['settings'] = {}
        return domain.settings(doc)
    return store.mutate(me['sid'], go)


# ── O aviso das 08:00: "vence hoje" ──────────────────────────────────────────

def due_digest(today):
    """Um aviso no sino de cada pessoa com tarefa em aberto que vence HOJE —
    quem desligou "Due dates" na Settings não recebe. Devolve quantos saíram."""
    R = _routes()
    projetos = R._projects_doc().get('projects') or []
    por_pessoa = {}
    for p in projetos:
        for t in p.get('tasks') or []:
            sid = str(t.get('assignee_sid') or '').upper()
            if sid and t.get('status') != domain.DONE and t.get('due') == today:
                por_pessoa.setdefault(sid, []).append(t.get('title', ''))
    n = 0
    for sid, titulos in por_pessoa.items():
        try:
            if not domain.wants(store.load(sid), 'due_dates'):
                continue
        except Exception:                                # noqa: BLE001
            pass
        detalhe = titulos[0] if len(titulos) == 1 else '%d tasks: %s' % (len(titulos), '; '.join(titulos[:3]))
        try:
            R._create_notification('SYSTEM', 'OTC Tracker', 'Due Today', PAGE, detalhe, target_sid=sid)
            n += 1
        except Exception:                                # noqa: BLE001
            log.warning('[user-home] aviso "vence hoje" para %s não saiu', sid, exc_info=True)
    return n


def _claim(slot):
    import os
    R = _routes()
    return R._claim_daily_slot(os.path.join(R._DAILY_METRIC_DIR, 'user_home_due_sent.json'),
                               R._DAILY_METRIC_DIR, slot, 16, 'user-home-due')


def _release(slot):
    import os
    R = _routes()
    R._release_daily_slot(os.path.join(R._DAILY_METRIC_DIR, 'user_home_due_sent.json'), slot, 'user-home-due')


_started = False
_started_lock = threading.Lock()


def run_once(agora):
    """Uma volta do laço: `None` fora da hora (ou com o dia já reservado),
    senão quantas pessoas foram avisadas. Às 08:00 BRT (ou na primeira volta
    depois, no mesmo dia) reserva o dia no claim em disco — a instância
    vizinha não manda o mesmo aviso — e dispara. Se a leitura dos projetos
    falha (banco ocupado no share), o dia é DEVOLVIDO: reservado e não
    enviado, ninguém tentaria de novo até amanhã. Devolver não duplica: cada
    envio tem o seu `try`, então só a leitura — antes de qualquer envio —
    chega aqui."""
    if agora.hour < DUE_HOUR or agora.weekday() >= 5:
        return None
    slot = 'due-%s' % agora.date().isoformat()
    R = _routes()
    with R._app_context():
        if not _claim(slot):
            return None
        try:
            return due_digest(agora.date().isoformat())
        except Exception:
            _release(slot)
            raise


def scheduler_loop():
    """Confere a cada 5 min (`run_once`)."""
    while True:
        time.sleep(300)
        try:
            n = run_once(_routes()._br_now())
            if n is not None:
                log.info('[user-home] aviso "vence hoje": %d pessoa(s)', n)
        except Exception:                                # noqa: BLE001
            log.warning('[user-home] laço do aviso "vence hoje" falhou (o dia foi devolvido)', exc_info=True)


def start_scheduler():
    global _started
    with _started_lock:
        if _started:
            return
        _started = True
    threading.Thread(target=scheduler_loop, name='user-home-due', daemon=True).start()
