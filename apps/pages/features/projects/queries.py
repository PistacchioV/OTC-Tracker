# -*- coding: utf-8 -*-
"""As leituras do Projects e o payload que as duas telas desenham."""
from apps.pages.features.projects import domain
from apps.pages.features.projects.infra import people, store
from apps.pages.platform import user_photos

_STATUS_ORDER = {s: i for i, s in enumerate(domain.STATUSES)}
_TASK_ORDER = {s: i for i, s in enumerate(domain.TASK_STATUSES)}
_PRIO_ORDER = {p: i for i, p in enumerate(reversed(domain.PRIORITIES))}


def eligible(me):
    """Quem pode ser Lead ou responsável: o cadastro Active com papel BO ou
    ADMIN, mais a própria sessão quando ela é BO/Admin/master — o admin que
    não está no cadastro (o master, a dev) também lidera. `me` = {sid, name,
    role}. Ordem alfabética. Cada um leva a `photo` (URL, ou '' sem arquivo):
    é por ela que o avatar de Lead, responsável, comentário e atividade mostra
    a foto em vez das iniciais."""
    out, vistos = [], set()
    for u in people.users():
        if u['role'] in domain.LEAD_ROLES and u['status'] == 'ACTIVE' and u['sid'] not in vistos:
            vistos.add(u['sid'])
            out.append({'sid': u['sid'], 'name': u['name'] or u['sid'], 'position': u['position'],
                        'photo': user_photos.url(u['sid'])})
    sid = str((me or {}).get('sid') or '').upper()
    if sid and sid not in vistos and str(me.get('role') or '').upper() in domain.LEAD_ROLES:
        out.append({'sid': sid, 'name': me.get('name') or sid, 'position': '', 'photo': user_photos.url(sid)})
    out.sort(key=lambda p: p['name'].lower())
    return out


def directory():
    return {u['sid']: {'name': u['name'], 'position': u['position']} for u in people.users()}


def list_projects():
    """Os cartões, na ordem da tela: On going → On hold → Concluded, e dentro
    de cada um pela data-alvo (sem data no fim)."""
    projetos = store.load()['projects']
    cards = [domain.summary(p) for p in projetos]
    cards.sort(key=lambda c: (_STATUS_ORDER.get(c['status'], 9), c['due_date'] or '9999-12-31',
                              c['name'].lower()))
    return cards


def get(project_id):
    return store.find(store.load(), project_id)


def detail(project, today, dir_=None):
    """A página do projeto: o projeto inteiro mais o que se calcula dele."""
    dir_ = directory() if dir_ is None else dir_
    tarefas = sorted(project.get('tasks') or [], key=lambda t: (
        _TASK_ORDER.get(t.get('status'), 9), _PRIO_ORDER.get(t.get('priority'), 9),
        t.get('due') or '9999-12-31', t.get('id', '')))
    marcos = sorted(project.get('milestones') or [], key=domain.milestone_order)
    nxt = domain.next_milestone(project)
    feitas = sum(1 for t in tarefas if t.get('status') == domain.DONE)
    out = dict(domain.summary(project))
    out.update({
        'created_at': project.get('created_at', ''),
        'created_by_sid': project.get('created_by_sid', ''),
        'created_by_name': project.get('created_by_name', ''),
        'tasks': tarefas,
        'milestones': marcos,
        'next_milestone_id': nxt['id'] if nxt else None,
        'open_tasks': len(tarefas) - feitas,
        'days_left': domain.days_left(project, today),
        'people': domain.people(project, dir_),
        'burnup': domain.burnup(project, today),
        'activity': list(reversed(project.get('activity') or []))[:30],
    })
    return out


def all_tasks():
    """A Tasks: toda tarefa de todo projeto, com o projeto ao lado (nome, cor,
    status) — o quadro agrupa por status e filtra por projeto, pessoa e
    prioridade no navegador. Devolve `(tarefas, projetos)`; os projetos vêm com
    as tarefas em aberto (o menu "All projects")."""
    tarefas, projetos = [], []
    for p in store.load()['projects']:
        abertas = 0
        for t in p.get('tasks') or []:
            item = dict(t)
            item.update({'project_id': p['id'], 'project_name': p.get('name', ''),
                         'project_color': p.get('color', domain.COLORS[0]),
                         'project_status': p.get('status', domain.DEFAULT_STATUS)})
            tarefas.append(item)
            if t.get('status') != domain.DONE:
                abertas += 1
        projetos.append({'id': p['id'], 'name': p.get('name', ''), 'color': p.get('color', domain.COLORS[0]),
                         'status': p.get('status', domain.DEFAULT_STATUS), 'open': abertas,
                         # quem pode receber tarefa nela (§639)
                         'involved': domain.involved_sids(p)})
    tarefas.sort(key=lambda t: (_PRIO_ORDER.get(t.get('priority'), 9), t.get('due') or '9999-12-31',
                                t.get('project_id', ''), t.get('id', '')))
    projetos.sort(key=lambda p: (_STATUS_ORDER.get(p['status'], 9), p['name'].lower()))
    return tarefas, projetos


def calendar_events():
    """As datas de todos os projetos, para o Calendar (`domain.calendar_events`)."""
    return domain.calendar_events(store.load()['projects'])
