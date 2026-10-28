# -*- coding: utf-8 -*-
"""As escritas do Projects. Cada comando valida pelo `domain`, altera o
documento dentro do `store.mutate` (um ciclo ler → alterar → gravar sob a
trava) e devolve o projeto já GRAVADO; o sino vem DEPOIS da gravação e a falha
dele não desfaz nada.

`actor` = {sid, name} da sessão; `people` = quem pode ser Lead/responsável
(`queries.eligible`), resolvido pelo entrypoint.
"""
import logging
import threading
import time
from datetime import datetime

from apps.pages.features.projects import domain
from apps.pages.features.projects.infra import store

log = logging.getLogger('otc_tracker')

# Desde 20/10/2026 a tela diz INITIATIVES: o sino grava a página e o aviso
# com os nomes novos (os três mapas de página têm os dois — o aviso antigo,
# já gravado como 'Projects'/'Project Lead', continua indo para o lugar certo).
# A chave da preferência segue `project_lead`: é o que a Settings já gravou.
PAGE = 'Initiatives'
LEAD_ACTION = 'Initiative Lead'
# Quem entra no TIME da iniciativa (§639) é avisado como o Lead.
MEMBER_ACTION = 'Initiative Member'
# o aviso → a chave da preferência na Settings (`user_home.domain.NOTIFY_KEYS`)
_PREF_KEY = {LEAD_ACTION: 'project_lead', 'Project Lead': 'project_lead',
             MEMBER_ACTION: 'project_member',
             'Task Assigned': 'task_assigned', 'Task Comment': 'task_comment'}


def _notify(actor, target_sid, action, detail):
    """Aviso no sino de UMA pessoa (nunca de quem fez). Melhor esforço; a busca
    é atrasada para o teste poder trocar `routes._create_notification`."""
    target_sid = str(target_sid or '').upper()
    if not target_sid or target_sid == actor['sid']:
        return
    try:
        from apps.pages import routes
        # quem desligou o aviso na Settings não recebe (§632)
        chave = _PREF_KEY.get(action)
        if chave and not routes._user_wants(target_sid, chave):
            return
        routes._create_notification(actor['sid'], actor['name'], action, PAGE, detail,
                                    target_sid=target_sid)
    except Exception:                                    # noqa: BLE001
        log.warning('[projects] aviso "%s" para %s não saiu', action, target_sid, exc_info=True)


def _project(data, project_id):
    p = store.find(data, project_id)
    if p is None:
        raise domain.NotFound('project_not_found', 'Initiative not found.')
    return p


def _child(items, child_id, code, text):
    for it in items or []:
        if it.get('id') == child_id:
            return it
    raise domain.NotFound(code, text)


def _event(project, actor, kind, **params):
    project['updated_at'] = store.now()
    domain.push_activity(project, domain.activity(kind, actor['sid'], actor['name'],
                                                  project['updated_at'], **params))


# ── Projeto ───────────────────────────────────────────────────────────────────

def create_project(actor, data, people):
    campos = domain.validate_project(data, people)

    def go(doc):
        agora = store.now()
        p = dict(campos)
        p.update({'id': store.next_id(doc), 'created_at': agora, 'updated_at': agora,
                  'created_by_sid': actor['sid'], 'created_by_name': actor['name'],
                  'start_date': campos['start_date'] or agora[:10],
                  'tasks': [], 'milestones': [], 'activity': []})
        _event(p, actor, 'created')
        doc['projects'].append(p)
        return p
    p = store.mutate(go)
    log.info('[projects] %s criado por %s', p['id'], actor['sid'])
    _notify(actor, p['lead_sid'], LEAD_ACTION, p['name'])
    for m in p.get('members') or []:
        _notify(actor, m['sid'], MEMBER_ACTION, p['name'])
    return p


def update_project(actor, project_id, data, people):
    def go(doc):
        p = _project(doc, project_id)
        antes = {'status': p.get('status'), 'lead_sid': p.get('lead_sid'),
                 'members': list(p.get('members') or [])}
        campos = domain.validate_project(data, people, current=p)
        mudou = [k for k, v in campos.items() if p.get(k, [] if k == 'members' else None) != v]
        p.update(campos)
        novos = domain.new_members(antes['members'], p.get('members'))
        if 'status' in mudou:
            _event(p, actor, 'status', status=p['status'])
        if novos:
            _event(p, actor, 'members_added', names=', '.join(m['name'] or m['sid'] for m in novos))
        if any(k not in ('status', 'members') for k in mudou) or \
                ('members' in mudou and not novos):
            _event(p, actor, 'edited')
        return p, antes, novos
    p, antes, novos = store.mutate(go)
    if p.get('lead_sid') != antes['lead_sid']:
        _notify(actor, p['lead_sid'], LEAD_ACTION, p['name'])
    for m in novos:
        _notify(actor, m['sid'], MEMBER_ACTION, p['name'])
    return p


def delete_project(actor, project_id, is_admin):
    def go(doc):
        p = _project(doc, project_id)
        if not domain.can_delete(p, actor['sid'], is_admin):
            raise PermissionError('not_allowed')
        doc['projects'] = [x for x in doc['projects'] if x is not p]
        return p
    p = store.mutate(go)
    log.info('[projects] %s apagado por %s', p['id'], actor['sid'])
    return p


# ── Tarefas ───────────────────────────────────────────────────────────────────

def _set_done_at(task, status_antes):
    if task['status'] == domain.DONE and status_antes != domain.DONE:
        task['done_at'] = store.now()
    elif task['status'] != domain.DONE:
        task['done_at'] = ''


def add_task(actor, project_id, data, people):
    def go(doc):
        p = _project(doc, project_id)
        # o responsável sai dos ENVOLVIDOS na iniciativa (§639)
        campos = domain.validate_task(data, domain.assignable(p, people, data))
        t = dict(campos)
        t.update({'id': store.child_id(p, 'tseq', 't'), 'created_at': store.now(),
                  'created_by_sid': actor['sid'], 'created_by_name': actor['name'],
                  'done_at': '', 'subtasks': [], 'comments': []})
        _set_done_at(t, None)
        p.setdefault('tasks', []).append(t)
        _event(p, actor, 'task_added', task=t['title'])
        return p, t
    p, t = store.mutate(go)
    _notify(actor, t.get('assignee_sid'), 'Task Assigned', '%s — %s' % (p['name'], t['title']))
    return p


def update_task(actor, project_id, task_id, data, people):
    def go(doc):
        p = _project(doc, project_id)
        t = _child(p.get('tasks'), task_id, 'task_not_found', 'Task not found.')
        antes = {'status': t.get('status'), 'assignee_sid': t.get('assignee_sid')}
        campos = domain.validate_task(data, domain.assignable(p, people, data, t), current=t)
        t.update(campos)
        _set_done_at(t, antes['status'])
        if t['status'] != antes['status']:
            if t['status'] == domain.DONE:
                _event(p, actor, 'task_done', task=t['title'])
            else:
                _event(p, actor, 'task_moved', task=t['title'], status=t['status'])
        else:
            p['updated_at'] = store.now()
        return p, t, antes
    p, t, antes = store.mutate(go)
    if t.get('assignee_sid') and t.get('assignee_sid') != antes['assignee_sid']:
        _notify(actor, t['assignee_sid'], 'Task Assigned', '%s — %s' % (p['name'], t['title']))
    return p


def delete_task(actor, project_id, task_id):
    def go(doc):
        p = _project(doc, project_id)
        t = _child(p.get('tasks'), task_id, 'task_not_found', 'Task not found.')
        p['tasks'] = [x for x in p['tasks'] if x is not t]
        _event(p, actor, 'task_deleted', task=t['title'])
        return p
    return store.mutate(go)


def add_subtask(actor, project_id, task_id, data):
    titulo = domain.clean_text((data or {}).get('title'), domain.MAX_TITLE)
    if not titulo:
        raise domain.ProjectError('title_required', 'Give the subtask a title.')

    def go(doc):
        p = _project(doc, project_id)
        t = _child(p.get('tasks'), task_id, 'task_not_found', 'Task not found.')
        t.setdefault('subtasks', []).append(
            {'id': store.child_id(t, 'sseq', 's'), 'title': titulo, 'done': False})
        p['updated_at'] = store.now()
        return p
    return store.mutate(go)


def update_subtask(actor, project_id, task_id, sub_id, data):
    data = data or {}

    def go(doc):
        p = _project(doc, project_id)
        t = _child(p.get('tasks'), task_id, 'task_not_found', 'Task not found.')
        s = _child(t.get('subtasks'), sub_id, 'subtask_not_found', 'Subtask not found.')
        if 'done' in data:
            s['done'] = bool(data.get('done'))
        if 'title' in data:
            titulo = domain.clean_text(data.get('title'), domain.MAX_TITLE)
            if not titulo:
                raise domain.ProjectError('title_required', 'Give the subtask a title.')
            s['title'] = titulo
        p['updated_at'] = store.now()
        return p
    return store.mutate(go)


def delete_subtask(actor, project_id, task_id, sub_id):
    def go(doc):
        p = _project(doc, project_id)
        t = _child(p.get('tasks'), task_id, 'task_not_found', 'Task not found.')
        s = _child(t.get('subtasks'), sub_id, 'subtask_not_found', 'Subtask not found.')
        t['subtasks'] = [x for x in t['subtasks'] if x is not s]
        p['updated_at'] = store.now()
        return p
    return store.mutate(go)


def add_comment(actor, project_id, task_id, data):
    texto = domain.clean_block((data or {}).get('text'), domain.MAX_COMMENT)
    if not texto:
        raise domain.ProjectError('comment_required', 'Write the comment first.')

    def go(doc):
        p = _project(doc, project_id)
        t = _child(p.get('tasks'), task_id, 'task_not_found', 'Task not found.')
        t.setdefault('comments', []).append(
            {'id': store.child_id(t, 'cseq', 'c'), 'sid': actor['sid'], 'name': actor['name'],
             'text': texto, 'at': store.now()})
        _event(p, actor, 'commented', task=t['title'])
        return p, t
    p, t = store.mutate(go)
    # quem é responsável pela tarefa fica sabendo do comentário dos outros
    _notify(actor, t.get('assignee_sid'), 'Task Comment', '%s — %s' % (p['name'], t['title']))
    return p


# ── Marcos ────────────────────────────────────────────────────────────────────

def add_milestone(actor, project_id, data):
    campos = domain.validate_milestone(data)

    def go(doc):
        p = _project(doc, project_id)
        m = dict(campos)
        m.update({'id': store.child_id(p, 'mseq', 'm'), 'done': False, 'done_at': ''})
        p.setdefault('milestones', []).append(m)
        _event(p, actor, 'milestone_added', milestone=m['title'])
        return p
    return store.mutate(go)


def update_milestone(actor, project_id, ms_id, data):
    data = data or {}

    def go(doc):
        p = _project(doc, project_id)
        m = _child(p.get('milestones'), ms_id, 'milestone_not_found', 'Milestone not found.')
        # Edição do evento: o que não veio no pedido fica como estava.
        if any(k in data for k in domain.MILESTONE_FIELDS):
            atual = {k: m.get(k) for k in domain.MILESTONE_FIELDS}
            atual.update({k: data[k] for k in domain.MILESTONE_FIELDS if k in data})
            m.update(domain.validate_milestone(atual))
            p['updated_at'] = store.now()
        if 'done' in data:
            novo = bool(data.get('done'))
            if novo != bool(m.get('done')):
                m['done'] = novo
                m['done_at'] = store.now() if novo else ''
                _event(p, actor, 'milestone_done' if novo else 'milestone_reopened',
                       milestone=m['title'])
        return p
    return store.mutate(go)


def delete_milestone(actor, project_id, ms_id):
    def go(doc):
        p = _project(doc, project_id)
        m = _child(p.get('milestones'), ms_id, 'milestone_not_found', 'Milestone not found.')
        p['milestones'] = [x for x in p['milestones'] if x is not m]
        p['updated_at'] = store.now()
        return p
    return store.mutate(go)


# ══════════════════════════════════════════════════════════════════════════
# OS ALERTAS (§701): e-mail + sino, uma vez por alerta. A regra é o
# `domain.alerts`; aqui é quem DISPARA: lê o documento, tira o que já saiu,
# manda UM e-mail por iniciativa (o box Brazil OTC Ops e quem está nela, com
# o Cc do card) e avisa no sino SÓ os envolvidos dela. A chave só é marcada
# com o e-mail entregue — falhou, o próximo disparo tenta de novo, e o sino
# não sai sozinho (sairia de novo junto com o e-mail).
# ══════════════════════════════════════════════════════════════════════════
ALERT_ACTION = 'Initiative Alert'
ALERT_HOUR = 8
_ALERT_TITLE = {'stale': 'No update for {days} business days (last on {since})',
                'due_soon': 'Initiative due in {days} business day(s) — {due}',
                'task_due': 'Task "{task}" due in {days} business day(s) — {due}',
                'ends': 'Initiative deadline: {due}'}
_PREF_KEY[ALERT_ACTION] = 'initiative_alerts'


def _dmy(iso):
    iso = str(iso or '')[:10]
    return '%s/%s/%s' % (iso[8:10], iso[5:7], iso[:4]) if len(iso) == 10 else iso


def alert_text(a):
    """A frase de UM alerta (e-mail e sino), com as datas em dd/mm/aaaa."""
    params = dict(a.get('params') or {})
    for k in ('since', 'due'):
        if k in params:
            params[k] = _dmy(params[k])
    return _ALERT_TITLE.get(a.get('kind'), a.get('kind') or '').format(**params)


def _alert_email(project, lista, today):
    from apps.pages import otc_emails as E
    from apps.pages import routes
    link = routes._otc_app_url('/initiatives/' + str(project.get('id') or ''))
    intro = (E._ep('Hello team,') +
             E._ep('The initiative below needs attention. Open it in the OTC Tracker to update '
                   'the status, the tasks or the deadline.'))
    resumo = E._email_kv('Initiative', [
        ('Name', project.get('name') or ''), ('Category', project.get('category') or ''),
        ('Lead', project.get('lead_name') or project.get('lead_sid') or ''),
        ('Deadline', _dmy(project.get('due_date')) or '—'),
        ('Last update', _dmy(project.get('updated_at')) or '—')])
    linhas = []
    for a in lista:
        p = a.get('params') or {}
        # o dono da linha: o responsável da tarefa; na da iniciativa, o Lead
        quem = p.get('assignee') or project.get('lead_name') or ''
        linhas.append([alert_text(a), quem or '—', _dmy(p.get('due') or p.get('since') or today)])
    tabela = E._email_data_table(['Alert', 'Owner', 'Date'], linhas)
    rodape = E._ep('<a href="%s">%s</a>' % (E._esc(link), E._esc(link)), muted=True)
    corpo = (resumo + '<div style="height:16px;line-height:16px;font-size:0;">&nbsp;</div>' +
             tabela + '<div style="height:12px;line-height:12px;font-size:0;">&nbsp;</div>' + rodape)
    html = E._email_shell('Initiative alert', _dmy(today), intro, corpo,
                          footer_extra='JPMC Internal Use Only', logo='otc')
    assunto = 'Initiative alert — %s — %s' % (project.get('name') or project.get('id'), _dmy(today))
    return assunto, html


def run_alerts(today, to_override=None, cc_override=None):
    """Dispara os alertas devidos em `today` ('YYYY-MM-DD') que ainda não
    saíram. → {'initiatives', 'alerts', 'failed': [(id, motivo)]}. O status do
    card é gravado aqui ('sent:N' / 'empty' / 'no_recipient' / o erro)."""
    from apps.pages import routes as R
    from apps.pages.features.projects.infra import alerts as A

    def biz(a, b):
        return R._anbima_biz_diff(datetime.strptime(a, '%Y-%m-%d'), datetime.strptime(b, '%Y-%m-%d'))

    feitas = A.sent_keys(strict=True)
    rec = A.load_recipients()
    to_box = R._parse_emails(rec['to'] if to_override is None else to_override)
    cc = R._parse_emails(rec['cc'] if cc_override is None else cc_override)
    enviadas, n_ini, falhas, sem_dest = [], 0, [], False
    for p in store.load().get('projects') or []:
        devidos = [a for a in domain.alerts(p, today, biz) if a['key'] not in feitas]
        if not devidos:
            continue
        envolvidos = domain.involved_sids(p)
        emails = A.emails_of(envolvidos)
        para = list(dict.fromkeys(to_box + [emails[s] for s in envolvidos if s in emails]))
        assunto, html = _alert_email(p, devidos, today)
        ok = A.send(assunto, html, para, [c for c in cc if c not in para])
        if ok is not True:
            if ok == 'no_recipient':
                sem_dest = True
            falhas.append((p.get('id'), ok))
            continue
        n_ini += 1
        enviadas += [a['key'] for a in devidos]
        detalhe = '%s · %s' % (p.get('name') or p.get('id'), '; '.join(alert_text(a) for a in devidos))
        for sid in envolvidos:
            try:
                if R._user_wants(sid, 'initiative_alerts'):
                    R._create_notification('SYSTEM', 'OTC Tracker', ALERT_ACTION, PAGE, detalhe,
                                           target_sid=sid)
            except Exception:                               # noqa: BLE001
                log.warning('[initiative-alerts] sino de %s não saiu', sid, exc_info=True)
    if enviadas:
        A.mark_sent(enviadas)
    if falhas and not n_ini:
        A.write_status('no_recipient' if sem_dest and len(falhas) == 1 else
                       'error: ' + '; '.join('%s %s' % f for f in falhas))
    else:
        A.write_status('sent:%d' % n_ini if n_ini else 'empty')
    return {'initiatives': n_ini, 'alerts': len(enviadas), 'failed': falhas}


def alerts_run_once(agora):
    """O disparo automático: dia útil ANBIMA, a partir das 08:00 BRT, uma vez
    por dia entre todas as instâncias (o claim)."""
    from apps.pages import routes as R
    from apps.pages.features.projects.infra import alerts as A
    if agora.hour < ALERT_HOUR or not R._pcx_is_bizday(agora.date()):
        return None
    slot = 'initiative-alerts-%s' % agora.date().isoformat()
    with R._app_context():
        if not A.claim(slot):
            return None
        try:
            return run_alerts(agora.date().isoformat())
        except Exception:
            A.release(slot)
            raise


def alerts_scheduler_loop():
    from apps.pages import routes as R
    while True:
        time.sleep(300)
        try:
            res = alerts_run_once(R._br_now())
            if res is not None:
                log.warning('[initiative-alerts] disparo do dia: %s', res)
        except Exception:                                   # noqa: BLE001
            log.warning('[initiative-alerts] disparo falhou', exc_info=True)


_alerts_started = False
_alerts_lock = threading.Lock()


def start_alerts_scheduler():
    global _alerts_started
    with _alerts_lock:
        if _alerts_started:
            return
        _alerts_started = True
    threading.Thread(target=alerts_scheduler_loop, name='initiative-alerts', daemon=True).start()
