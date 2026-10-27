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

# A CATEGORIA da iniciativa (mesa, 20/10/2026 — o Projects virou Initiatives
# na tela e "Projects" é uma das categorias). Lista fechada, gravada em inglês
# como o status e traduzida na tela (`cat_<valor>`). Criar exige; iniciativa
# de antes não tem e aparece sem categoria até alguém editá-la — e aí a
# edição pede uma.
CATEGORIES = ['Process Review', 'Tech Issue', 'Projects', 'B3 - Improvements', 'Stomp/Red']

# Quem pode liderar (e receber tarefa): a mesa do OTC — BO e Admin (pedido de
# 19/10/2026). O master é admin para todo efeito.
LEAD_ROLES = ('BO', 'ADMIN', 'MASTER')

# O MARCO é o EVENTO da iniciativa (mesa, 21/10/2026): nasce do "New event"
# da página, com hora, duração, tipo e local — só o título é obrigatório. Tipo
# e duração são LISTA FECHADA (o tipo é gravado em inglês e traduzido na tela,
# `ev_<tipo>`); a duração, em minutos, só existe com hora.
EVENT_TYPES = ['Milestone', 'Meeting', 'Deadline', 'Review', 'Go-live']
DEFAULT_EVENT_TYPE = 'Milestone'
EVENT_LENGTHS = [15, 30, 45, 60, 90, 120, 180, 240]
DEFAULT_EVENT_LENGTH = 30
MAX_WHERE = 200

MAX_NAME = 120
MAX_DESCRIPTION = 600
MAX_TITLE = 200
MAX_COMMENT = 2000
MAX_ACTIVITY = 200
# O TIME da iniciativa (mesa, 20/10/2026): os envolvidos além do Lead, mesmo
# sem tarefa. Mesmas pessoas que podem liderar (`LEAD_ROLES`).
MAX_MEMBERS = 30
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
            raise ProjectError('name_required', 'Give the initiative a name.')
    if not partial or 'description' in data:
        out['description'] = clean_block(data.get('description'), MAX_DESCRIPTION)
    if not partial or 'lead_sid' in data:
        sid = str(data.get('lead_sid') or '').strip().upper()
        if partial and sid and sid == current.get('lead_sid'):
            out['lead_sid'], out['lead_name'] = sid, current.get('lead_name', '')
        else:
            out['lead_sid'], out['lead_name'] = _person(sid, people, 'lead', True)
    if not partial or 'category' in data:
        if not str(data.get('category') or '').strip():
            raise ProjectError('category_required', 'Choose the category.')
        out['category'] = _choice(data.get('category'), CATEGORIES, None, 'category')
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

    if not partial or 'member_sids' in data:
        lead = out.get('lead_sid', (current or {}).get('lead_sid', ''))
        out['members'] = _members(data.get('member_sids'), people, current, lead)

    start = out.get('start_date', (current or {}).get('start_date', ''))
    due = out.get('due_date', (current or {}).get('due_date', ''))
    if start and due and due < start:
        raise ProjectError('due_before_start', 'The target date is before the start date.')
    return out


def _members(sids, people, current, lead_sid):
    """O time, limpo: [{sid, name}] sem repetir e sem o Lead (ele já está na
    iniciativa como Lead). Quem JÁ estava no time continua válido mesmo que
    tenha saído do BO — a mesma regra do Lead gravado; quem entra agora tem de
    ser elegível."""
    if sids is None or sids == '':
        sids = []
    if not isinstance(sids, (list, tuple)):
        raise ProjectError('bad_choice', 'Invalid value for "members".', field='members')
    ja = {m.get('sid'): m.get('name', '') for m in (current or {}).get('members') or []}
    out, vistos = [], set()
    for sid in sids:
        sid = str(sid or '').strip().upper()
        if not sid or sid in vistos or sid == str(lead_sid or '').upper():
            continue
        vistos.add(sid)
        if sid in ja:
            out.append({'sid': sid, 'name': ja[sid]})
        else:
            sid, nome = _person(sid, people, 'members', False)
            out.append({'sid': sid, 'name': nome})
    if len(out) > MAX_MEMBERS:
        raise ProjectError('too_many_members', 'At most %d people in the team.' % MAX_MEMBERS,
                           max=MAX_MEMBERS)
    return out


def new_members(before, after):
    """Quem ENTROU no time (para o aviso no sino): os SIDs de `after` que
    não estavam em `before`."""
    antes = {m.get('sid') for m in before or []}
    return [m for m in after or [] if m.get('sid') not in antes]


def involved_sids(project):
    """Os SIDs de quem está na iniciativa — o Lead, o time e quem já tem
    tarefa (a lista de `people`)."""
    return [p['sid'] for p in people(project, {})]


def assignable(project, people_list, data, current=None):
    """As pessoas que podem receber ESTA tarefa: o responsável da tarefa é
    escolhido entre os ENVOLVIDOS na iniciativa (mesa, 20/10/2026) — e continua
    tendo de ser elegível (BO/Admin ativo). Responsável escolhido fora do time
    recusa com o código próprio, que diz o que fazer: incluir a pessoa no time
    da iniciativa primeiro. O responsável que a tarefa JÁ tem é mantido."""
    dentro = set(involved_sids(project))
    sid = str((data or {}).get('assignee_sid') or '').strip().upper()
    if sid and sid not in dentro and sid != (current or {}).get('assignee_sid'):
        if any(p['sid'] == sid for p in people_list or []):
            raise ProjectError('assignee_not_in_team',
                               'Add this person to the initiative team before giving them a task.')
    return [p for p in people_list or [] if p['sid'] in dentro]


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


MILESTONE_FIELDS = ('title', 'date', 'time', 'length', 'type', 'where')


def validate_milestone(data):
    """O marco — o EVENTO da iniciativa. Sem hora ele é do dia inteiro, e aí
    não tem duração; com hora e sem duração, vale a padrão (30 min)."""
    data = data or {}
    title = clean_text(data.get('title'), MAX_TITLE)
    if not title:
        raise ProjectError('title_required', 'Give the milestone a title.')
    hora = _hhmm(data.get('time'))
    return {'title': title, 'date': iso_date(data.get('date'), 'date'),
            'time': hora,
            'length': _event_length(data.get('length')) if hora else None,
            'type': _choice(data.get('type'), EVENT_TYPES, DEFAULT_EVENT_TYPE, 'type'),
            'where': clean_text(data.get('where'), MAX_WHERE)}


def _hhmm(value):
    s = str(value or '').strip()
    if not s:
        return ''
    m = re.match(r'^(\d{1,2}):(\d{2})$', s)
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ProjectError('bad_time', 'Invalid time in "time" — use hh:mm.', field='time')
    return '%02d:%02d' % (int(m.group(1)), int(m.group(2)))


def _event_length(value):
    if value is None or str(value).strip() == '':
        return DEFAULT_EVENT_LENGTH
    try:
        n = int(str(value).strip())
    except ValueError:
        n = None
    if n not in EVENT_LENGTHS:
        raise ProjectError('bad_choice', 'Invalid value for "length".', field='length')
    return n


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


def milestone_order(m):
    """Pela data e, no mesmo dia, pela hora (o do dia inteiro vem antes); sem
    data vai para o fim."""
    return (m.get('date') or '9999-12-31', m.get('time') or '', m.get('id', ''))


def next_milestone(project):
    """O primeiro marco em aberto, pela data (sem data vai para o fim)."""
    abertos = [m for m in project.get('milestones') or [] if not m.get('done')]
    abertos.sort(key=milestone_order)
    return abertos[0] if abertos else None


def days_left(project, today):
    due = _d(project.get('due_date'))
    return (due - today).days if due else None


def people(project, directory):
    """O Lead primeiro, depois o TIME (§639) e quem tem tarefa, na ordem em que
    entrou — cada um com as tarefas em aberto. `directory` = {SID: {name,
    position}}. A User Home tem a mesma regra (`user_home.domain.envolvidos`):
    feature não importa feature."""
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
    for m in project.get('members') or []:
        add(m.get('sid'), m.get('name'))
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
        'category': project.get('category', ''),
        'color': project.get('color', COLORS[0]),
        'icon': project.get('icon', ICONS[0]),
        'lead_sid': project.get('lead_sid', ''),
        'lead_name': project.get('lead_name', ''),
        'members': [{'sid': m.get('sid', ''), 'name': m.get('name', '')}
                    for m in project.get('members') or []],
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


def calendar_events(projects):
    """As datas dos projetos para o Calendar: a data-alvo do projeto, os marcos
    e o prazo das tarefas EM ABERTO (tarefa feita não ocupa o dia de ninguém).
    Derivadas na leitura — o calendário nunca guarda cópia, e a data mudada
    no projeto aparece lá na próxima carga."""
    out = []
    for p in projects or []:
        base = {'project_id': p['id'], 'project_name': p.get('name', ''),
                'color': p.get('color', COLORS[0])}
        if p.get('due_date'):
            out.append(dict(base, kind='project', date=p['due_date'], title=p.get('name', ''),
                            status=p.get('status', DEFAULT_STATUS)))
        for m in p.get('milestones') or []:
            if m.get('date'):
                out.append(dict(base, kind='milestone', date=m['date'], title=m.get('title', ''),
                                id=m.get('id', ''), done=bool(m.get('done')), time=m.get('time', '')))
        for t in p.get('tasks') or []:
            if t.get('due') and t.get('status') != DONE:
                out.append(dict(base, kind='task', date=t['due'], title=t.get('title', ''),
                                id=t.get('id', ''), status=t.get('status', ''),
                                priority=t.get('priority', ''), assignee_name=t.get('assignee_name', '')))
    out.sort(key=lambda e: (e['date'], e['project_name'].lower(), e['kind']))
    return out


# ══════════════════════════════════════════════════════════════════════════
# OS ALERTAS DAS INICIATIVAS (§701)
# --------------------------------------------------------------------------
# Um e-mail (box Brazil OTC Ops + quem está na iniciativa, Cc do card do
# Control Panel) e o sino de cada envolvido, em três casos:
#   · `stale`     — nenhuma atualização há MAIS de 5 dias úteis ANBIMA (o
#                   `updated_at`, que toda gravação carimba — inclusive as que
#                   não viram atividade);
#   · `due_soon`  — faltam 2 dias úteis (ou menos) para o prazo da iniciativa;
#   · `task_due`  — idem, para o prazo de uma tarefa ainda não Done;
#   · `ends`      — o prazo da iniciativa é HOJE (ou passou há até 7 dias e o
#                   aviso não saiu: o dia era feriado, o app estava parado).
# Só a iniciativa `On going`: a que está On hold parou de propósito, e a
# Concluded acabou. Cada alerta tem uma CHAVE (iniciativa, caso, data de
# referência) e sai uma vez só — quem deduplica é quem envia; aqui é só a regra.
ALERT_STALE_BIZDAYS = 5
ALERT_WARN_BIZDAYS = 2
ALERT_ENDS_GRACE_DAYS = 7


def _iso(v):
    v = str(v or '').strip()[:10]
    return v if re.match(r'^\d{4}-\d{2}-\d{2}$', v) else ''


def alerts(project, today, biz_between):
    """Os alertas devidos de UMA iniciativa em `today` ('YYYY-MM-DD'):
    [{key, kind, params}]. `biz_between(a, b)` = dias úteis ANBIMA em (a, b],
    com `a`/`b` em 'YYYY-MM-DD' — injetado: o domain é puro."""
    p = project or {}
    if p.get('status') != DEFAULT_STATUS:
        return []
    pid = p.get('id') or ''
    out = []
    upd = _iso(p.get('updated_at')) or _iso(p.get('created_at'))
    if upd and upd < today:
        n = biz_between(upd, today)
        if n > ALERT_STALE_BIZDAYS:
            out.append({'key': '%s:stale:%s' % (pid, str(p.get('updated_at') or upd)),
                        'kind': 'stale', 'params': {'since': upd, 'days': n}})
    due = _iso(p.get('due_date'))
    if due:
        if due > today:
            n = biz_between(today, due)
            if 0 < n <= ALERT_WARN_BIZDAYS:
                out.append({'key': '%s:due:%s' % (pid, due), 'kind': 'due_soon',
                            'params': {'due': due, 'days': n}})
        else:
            atraso = (date.fromisoformat(today) - date.fromisoformat(due)).days
            if atraso <= ALERT_ENDS_GRACE_DAYS:
                out.append({'key': '%s:ends:%s' % (pid, due), 'kind': 'ends',
                            'params': {'due': due, 'late': atraso}})
    for tk in p.get('tasks') or []:
        tdue = _iso(tk.get('due'))
        if not tdue or tk.get('status') == DONE or tdue <= today:
            continue
        n = biz_between(today, tdue)
        if 0 < n <= ALERT_WARN_BIZDAYS:
            out.append({'key': '%s:%s:due:%s' % (pid, tk.get('id') or '', tdue), 'kind': 'task_due',
                        'params': {'task': tk.get('title') or '', 'due': tdue, 'days': n,
                                   'assignee': tk.get('assignee_name') or ''}})
    return out
