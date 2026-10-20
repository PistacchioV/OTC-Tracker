# -*- coding: utf-8 -*-
"""As regras do Projects — puras: não leem sessão, banco nem relógio.

Quem chama passa o `hoje` e a lista de pessoas já resolvidos; é o que deixa o
teste fixar a data e o cadastro sem trocar nada no módulo.

O erro de validação é ESTRUTURADO (`ProjectError(code, params)`): a tela diz a
frase pelo `_TRANS` dela (`e_<code>`) e o `text` em inglês é só o fallback
(CLAUDE.md §2, i18n).
"""
import re
from datetime import date, datetime, timedelta

STATUSES = ['On going', 'On hold', 'Concluded']
DEFAULT_STATUS = 'On going'
TASK_STATUSES = ['To do', 'In progress', 'In review', 'Done']
DONE = 'Done'
PRIORITIES = ['Low', 'Medium', 'High', 'Urgent']
DEFAULT_PRIORITY = 'Medium'

# Cores e ícones são LISTA FECHADA: a cor vira `var(--otc-<cor>)` e o ícone um
# `data-lucide` no HTML — um valor livre seria texto do usuário dentro de CSS.
COLORS = ['blue', 'purple', 'pink', 'orange', 'green', 'teal', 'indigo', 'yellow']
ICONS = ['folder', 'rocket', 'leaf', 'flame', 'layout-grid', 'chart-column', 'sparkles', 'workflow']

# Quem pode liderar (e receber tarefa): a mesa do OTC — BO e Admin (pedido de
# 19/10/2026). O master é admin para todo efeito.
LEAD_ROLES = ('BO', 'ADMIN', 'MASTER')

MAX_NAME = 120
MAX_DESCRIPTION = 600
MAX_TITLE = 200
MAX_COMMENT = 2000
MAX_ACTIVITY = 200
# Burn-up com mais pontos que isto é amostrado (o último dia entra sempre).
MAX_BURNUP_POINTS = 120


class ProjectError(ValueError):
    """Pedido recusado — `code` é a chave da tradução, `params` o que ela usa."""

    def __init__(self, code, text, **params):
        super().__init__(text)
        self.code = code
        self.text = text
        self.params = params


class NotFound(ProjectError):
    """O projeto (ou a tarefa, o marco, a subtarefa) não existe — 404."""


# ── Campos ────────────────────────────────────────────────────────────────────

def clean_text(value, limit):
    return re.sub(r'\s+', ' ', str(value if value is not None else '')).strip()[:limit]


def clean_block(value, limit):
    """Texto de várias linhas (descrição, comentário): mantém as quebras."""
    linhas = [l.rstrip() for l in str(value if value is not None else '').replace('\r', '').split('\n')]
    return '\n'.join(linhas).strip()[:limit]


def iso_date(value, field):
    """'' ou 'AAAA-MM-DD'. Aceita também dd/mm/aaaa (o campo da tela é editável
    e o `isoDay` normaliza, mas o servidor não confia nisso)."""
    s = str(value or '').strip()
    if not s:
        return ''
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(s[:10], fmt).date().isoformat()
        except ValueError:
            continue
    raise ProjectError('bad_date', 'Invalid date in "%s".' % field, field=field)


def _choice(value, options, default, field):
    if value is None or value == '':
        return default
    for o in options:
        if str(value).strip().lower() == o.lower():
            return o
    raise ProjectError('bad_choice', 'Invalid value for "%s".' % field, field=field)


def _person(sid, people, field, required):
    sid = str(sid or '').strip().upper()
    if not sid:
        if required:
            raise ProjectError('lead_required', 'Choose the lead.') if field == 'lead' else \
                ProjectError('bad_choice', 'Invalid value for "%s".' % field, field=field)
        return '', ''
    for p in people:
        if p['sid'] == sid:
            return sid, p['name']
    raise ProjectError('not_eligible', 'This person cannot be chosen for "%s".' % field, field=field)


def validate_project(data, people, current=None):
    """Os campos de um projeto, limpos. `current` = o projeto que está sendo
    editado: só muda o que veio no pedido, e o Lead que já está gravado
    continua válido mesmo que a pessoa tenha saído do BO."""
    data = data or {}
    out = {}
    partial = current is not None

    if not partial or 'name' in data:
        out['name'] = clean_text(data.get('name'), MAX_NAME)
        if not out['name']:
            raise ProjectError('name_required', 'Give the project a name.')
    if not partial or 'description' in data:
        out['description'] = clean_block(data.get('description'), MAX_DESCRIPTION)
    if not partial or 'lead_sid' in data:
        sid = str(data.get('lead_sid') or '').strip().upper()
        if partial and sid and sid == current.get('lead_sid'):
            out['lead_sid'], out['lead_name'] = sid, current.get('lead_name', '')
        else:
            out['lead_sid'], out['lead_name'] = _person(sid, people, 'lead', True)
    if not partial or 'status' in data:
        out['status'] = _choice(data.get('status'), STATUSES, DEFAULT_STATUS, 'status')
    if not partial or 'color' in data:
        out['color'] = _choice(data.get('color'), COLORS, COLORS[0], 'color')
    if not partial or 'icon' in data:
        out['icon'] = _choice(data.get('icon'), ICONS, ICONS[0], 'icon')
    if not partial or 'start_date' in data:
        out['start_date'] = iso_date(data.get('start_date'), 'start_date')
    if not partial or 'due_date' in data:
        out['due_date'] = iso_date(data.get('due_date'), 'due_date')

    start = out.get('start_date', (current or {}).get('start_date', ''))
    due = out.get('due_date', (current or {}).get('due_date', ''))
    if start and due and due < start:
        raise ProjectError('due_before_start', 'The target date is before the start date.')
    return out


def validate_task(data, people, current=None):
    data = data or {}
    out = {}
    partial = current is not None
    if not partial or 'title' in data:
        out['title'] = clean_text(data.get('title'), MAX_TITLE)
        if not out['title']:
            raise ProjectError('title_required', 'Give the task a title.')
    if not partial or 'assignee_sid' in data:
        sid = str(data.get('assignee_sid') or '').strip().upper()
        if partial and sid and sid == current.get('assignee_sid'):
            out['assignee_sid'], out['assignee_name'] = sid, current.get('assignee_name', '')
        else:
            out['assignee_sid'], out['assignee_name'] = _person(sid, people, 'assignee', False)
    if not partial or 'priority' in data:
        out['priority'] = _choice(data.get('priority'), PRIORITIES, DEFAULT_PRIORITY, 'priority')
    if not partial or 'status' in data:
        out['status'] = _choice(data.get('status'), TASK_STATUSES, TASK_STATUSES[0], 'status')
    if not partial or 'due' in data:
        out['due'] = iso_date(data.get('due'), 'due')
    if not partial or 'estimate' in data:
        out['estimate'] = _estimate(data.get('estimate'))
    return out


def _estimate(value):
    s = str(value if value is not None else '').strip().replace(',', '.')
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        raise ProjectError('bad_estimate', 'The estimate must be a number of hours.')
    if v < 0 or v > 10000:
        raise ProjectError('bad_estimate', 'The estimate must be a number of hours.')
    return round(v, 2)


def validate_milestone(data):
    data = data or {}
    title = clean_text(data.get('title'), MAX_TITLE)
    if not title:
        raise ProjectError('title_required', 'Give the milestone a title.')
    return {'title': title, 'date': iso_date(data.get('date'), 'date')}


# ── Quem pode ─────────────────────────────────────────────────────────────────

def can_delete(project, sid, is_admin):
    """Apagar o projeto inteiro é do Lead, de quem o criou e do admin/master —
    o resto da mesa edita tudo, mas não some com o trabalho dos outros."""
    sid = str(sid or '').upper()
    return bool(is_admin or (sid and sid in (project.get('lead_sid'), project.get('created_by_sid'))))


# ── O que as telas mostram ────────────────────────────────────────────────────

def _d(iso):
    try:
        return date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return None


def progress(project):
    """% de tarefas feitas. Sem tarefa: 100 se o projeto está concluído, senão 0
    — "0 de 0" não é meio caminho de nada."""
    tasks = project.get('tasks') or []
    if not tasks:
        return 100 if project.get('status') == 'Concluded' else 0
    done = sum(1 for t in tasks if t.get('status') == DONE)
    return int(round(100.0 * done / len(tasks)))


def next_milestone(project):
    """O primeiro marco em aberto, pela data (sem data vai para o fim)."""
    abertos = [m for m in project.get('milestones') or [] if not m.get('done')]
    abertos.sort(key=lambda m: (m.get('date') or '9999-12-31', m.get('id', '')))
    return abertos[0] if abertos else None


def days_left(project, today):
    due = _d(project.get('due_date'))
    return (due - today).days if due else None


def people(project, directory):
    """O Lead primeiro, depois quem tem tarefa, na ordem em que entrou — cada
    um com as tarefas em aberto. `directory` = {SID: {name, position}}."""
    ordem, vistos = [], set()

    def add(sid, name):
        sid = str(sid or '').upper()
        if sid and sid not in vistos:
            vistos.add(sid)
            info = directory.get(sid) or {}
            ordem.append({'sid': sid, 'name': info.get('name') or name or sid,
                          'position': info.get('position', ''),
                          'is_lead': sid == project.get('lead_sid'),
                          'open_tasks': 0})

    add(project.get('lead_sid'), project.get('lead_name'))
    for t in project.get('tasks') or []:
        add(t.get('assignee_sid'), t.get('assignee_name'))
    abertas = {}
    for t in project.get('tasks') or []:
        if t.get('status') != DONE and t.get('assignee_sid'):
            abertas[t['assignee_sid']] = abertas.get(t['assignee_sid'], 0) + 1
    for p in ordem:
        p['open_tasks'] = abertas.get(p['sid'], 0)
    return ordem


def burnup(project, today):
    """Tarefas feitas × total, dia a dia, do início do projeto até hoje (ou até
    o fim, se ele já passou e o projeto está concluído). Uma tarefa entra no
    total no dia em que foi criada e em `done` no dia em que foi concluída."""
    tasks = project.get('tasks') or []
    inicio = _d(project.get('start_date')) or _d(project.get('created_at')) or today
    criadas = [(_d(t.get('created_at')) or inicio) for t in tasks]
    if criadas:
        inicio = min([inicio] + criadas)
    fim = today
    if inicio > fim:
        fim = inicio
    dias = (fim - inicio).days + 1
    passo = max(1, -(-dias // MAX_BURNUP_POINTS))
    pontos = [inicio + timedelta(days=i) for i in range(0, dias, passo)]
    if pontos[-1] != fim:
        pontos.append(fim)
    feitas = [_d(t.get('done_at')) if t.get('status') == DONE else None for t in tasks]
    return {
        'labels': [p.isoformat() for p in pontos],
        'total': [sum(1 for c in criadas if c <= p) for p in pontos],
        'done': [sum(1 for f in feitas if f and f <= p) for p in pontos],
    }


def summary(project):
    """O cartão da lista."""
    tasks = project.get('tasks') or []
    ms = project.get('milestones') or []
    nxt = next_milestone(project)
    pessoas = people(project, {})
    return {
        'id': project['id'],
        'name': project.get('name', ''),
        'description': project.get('description', ''),
        'status': project.get('status', DEFAULT_STATUS),
        'color': project.get('color', COLORS[0]),
        'icon': project.get('icon', ICONS[0]),
        'lead_sid': project.get('lead_sid', ''),
        'lead_name': project.get('lead_name', ''),
        'start_date': project.get('start_date', ''),
        'due_date': project.get('due_date', ''),
        'progress': progress(project),
        'tasks_total': len(tasks),
        'tasks_done': sum(1 for t in tasks if t.get('status') == DONE),
        'milestones_total': len(ms),
        'milestones_done': sum(1 for m in ms if m.get('done')),
        'next_milestone': {'title': nxt['title'], 'date': nxt.get('date', '')} if nxt else None,
        'people': [{'sid': p['sid'], 'name': p['name']} for p in pessoas],
        'updated_at': project.get('updated_at', ''),
    }


def activity(kind, sid, name, now, **params):
    """Um evento da atividade recente. Vai ESTRUTURADO (tipo + parâmetros): a
    frase é montada na tela, no idioma de quem lê."""
    return {'at': now, 'sid': str(sid or '').upper(), 'name': name or '', 'kind': kind,
            'params': params}


def push_activity(project, event):
    log = project.setdefault('activity', [])
    log.append(event)
    if len(log) > MAX_ACTIVITY:
        del log[:len(log) - MAX_ACTIVITY]
