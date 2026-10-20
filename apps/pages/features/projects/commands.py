# -*- coding: utf-8 -*-
"""As escritas do Projects. Cada comando valida pelo `domain`, altera o
documento dentro do `store.mutate` (um ciclo ler → alterar → gravar sob a
trava) e devolve o projeto já GRAVADO; o sino vem DEPOIS da gravação e a falha
dele não desfaz nada.

`actor` = {sid, name} da sessão; `people` = quem pode ser Lead/responsável
(`queries.eligible`), resolvido pelo entrypoint.
"""
import logging

from apps.pages.features.projects import domain
from apps.pages.features.projects.infra import store

log = logging.getLogger('otc_tracker')

PAGE = 'Projects'
# o aviso → a chave da preferência na Settings (`user_home.domain.NOTIFY_KEYS`)
_PREF_KEY = {'Project Lead': 'project_lead', 'Task Assigned': 'task_assigned', 'Task Comment': 'task_comment'}


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
        raise domain.NotFound('project_not_found', 'Project not found.')
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
    _notify(actor, p['lead_sid'], 'Project Lead', p['name'])
    return p


def update_project(actor, project_id, data, people):
    def go(doc):
        p = _project(doc, project_id)
        antes = {'status': p.get('status'), 'lead_sid': p.get('lead_sid')}
        campos = domain.validate_project(data, people, current=p)
        mudou = [k for k, v in campos.items() if p.get(k) != v]
        p.update(campos)
        if 'status' in mudou:
            _event(p, actor, 'status', status=p['status'])
        if any(k != 'status' for k in mudou):
            _event(p, actor, 'edited')
        return p, antes
    p, antes = store.mutate(go)
    if p.get('lead_sid') != antes['lead_sid']:
        _notify(actor, p['lead_sid'], 'Project Lead', p['name'])
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
    campos = domain.validate_task(data, people)

    def go(doc):
        p = _project(doc, project_id)
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
        campos = domain.validate_task(data, people, current=t)
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
        if 'title' in data or 'date' in data:
            campos = domain.validate_milestone({'title': data.get('title', m.get('title')),
                                                'date': data.get('date', m.get('date'))})
            m.update(campos)
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
