# -*- coding: utf-8 -*-
"""As leituras da User Home. Os projetos chegam pelo `routes._projects_doc()`
(feature não importa feature, CLAUDE.md §3 — o mesmo desenho do
`routes._swap_bullet_engine()`), e o resto é o documento do próprio usuário.
"""
from apps.pages.features.user_home import domain
from apps.pages.features.user_home.infra import store


def _routes():
    from apps.pages import routes
    return routes


def _card(p):
    tasks = p.get('tasks') or []
    feitas = sum(1 for t in tasks if t.get('status') == domain.DONE)
    gente, vistos = [], set()
    for sid, nome in domain.envolvidos(p):
        if sid not in vistos:
            vistos.add(sid)
            gente.append({'sid': sid, 'name': nome or sid})
    return {'id': p['id'], 'name': p.get('name', ''), 'color': p.get('color', 'blue'),
            'icon': p.get('icon', 'folder'), 'status': p.get('status', ''), 'due_date': p.get('due_date', ''),
            'progress': int(round(100.0 * feitas / len(tasks))) if tasks else
            (100 if p.get('status') == 'Concluded' else 0),
            'tasks_total': len(tasks), 'tasks_done': feitas, 'people': gente}


def _team(projects, me_sid, directory, now):
    """Quem trabalha comigo (Lead ou responsável nos MEUS projetos), com a
    presença de agora: em foco, em reunião, livre."""
    vistos, ordem = {me_sid}, []
    for p in projects:
        for sid, nome in domain.envolvidos(p):
            if sid not in vistos:
                vistos.add(sid)
                ordem.append((sid, nome))
    docs = store.load_many([s for s, _n in ordem])
    out = []
    for sid, nome in ordem:
        info = directory.get(sid) or {}
        pres = domain.presence(docs.get(sid), now)
        out.append({'sid': sid, 'name': info.get('name') or nome or sid, 'position': info.get('position', ''),
                    'state': pres['state'], 'until': pres['until']})
    rank = {'focus': 0, 'meeting': 1, 'free': 2}
    out.sort(key=lambda x: (rank.get(x['state'], 9), x['name'].lower()))
    return out


def focus_state(doc, now):
    f = (doc or {}).get('focus') or {}
    r = f.get('running')
    if not r:
        return None
    return {'minutes': r.get('minutes'), 'task_title': r.get('task_title', ''),
            'task_id': r.get('task_id', ''), 'project_id': r.get('project_id', ''),
            'started_at': r.get('started_at', ''), 'ends_at': r.get('ends_at', ''),
            'paused': r.get('paused_left') is not None,
            'remaining': domain.focus_remaining(r, now)}


def home(me, now, can_projects):
    """Tudo o que a tela desenha, numa resposta. `now` é ISO (hora do Brasil);
    sem acesso ao Projects/Tasks as partes de tarefa e projeto vêm vazias — a
    Home é de todo mundo, o trabalho dos projetos não."""
    R = _routes()
    sid = me['sid']
    today = now[:10]
    doc = store.load(sid)
    st = domain.settings(doc)
    projetos = (R._projects_doc().get('projects') or []) if can_projects else []
    mine = [p for p in projetos if domain.is_mine(p, sid)]

    tarefas = domain.my_tasks(projetos, sid, today)
    feitas = sum(1 for t in tarefas if t.get('status') == domain.DONE)
    hoje = domain.with_app_links(domain.day_events(doc.get('events'), today))
    foco = domain.focus_today(doc.get('focus'), today, now)
    directory = R._projects_directory() if can_projects else {}

    return {
        'today': today, 'now': now,
        'me': {'sid': sid, 'name': me.get('name') or sid, 'email': me.get('email', '')},
        'settings': st,
        'can_projects': bool(can_projects),
        'stats': {'done_today': feitas, 'tasks_today': len(tarefas),
                  'focus_minutes': foco['minutes'], 'focus_sessions': foco['sessions'],
                  'overdue': domain.overdue(projetos, sid, today)},
        'rings': {'tasks': {'done': feitas, 'total': len(tarefas)},
                  'focus': {'minutes': foco['minutes'], 'goal': st['focus_goal_minutes']},
                  'meetings': domain.meetings_ring(hoje, now)},
        'events_today': hoje,
        'next_event': domain.next_event(hoje, now),
        'synced_at': doc.get('synced_at', ''),
        'focus': focus_state(doc, now),
        'focus_presets': list(domain.FOCUS_PRESETS),
        'my_tasks': tarefas,
        'open_tasks': [{'task_id': t['id'], 'project_id': t['project_id'], 'title': t.get('title', ''),
                        'project_name': t['project_name']} for t in domain.open_tasks(projetos, sid)],
        'week': domain.week(projetos, today),
        'projects': domain.sort_projects([_card(p) for p in mine])[:6],
        # `involved`: quem pode receber tarefa nela (§639) — o modal de tarefa
        # da Home oferece só essas pessoas
        'projects_all': [{'id': p['id'], 'name': p.get('name', ''), 'color': p.get('color', 'blue'),
                          'involved': list(dict.fromkeys(s for s, _n in domain.envolvidos(p)))}
                         for p in projetos if p.get('status') != 'Concluded'],
        'team': _team(mine, sid, directory, now) if can_projects else [],
        'activity': domain.recent_activity(mine, 15),
    }


def settings(sid):
    return domain.settings(store.load(sid))


def favorites(sid):
    return domain.favorites(store.load(sid))


def wants(sid, key):
    """O aviso `key` vai para `sid`? Falha de leitura = sim (o padrão): um
    banco ocupado não pode calar o sino de ninguém."""
    try:
        return domain.wants(store.load(sid), key)
    except Exception:                                    # noqa: BLE001
        return True
