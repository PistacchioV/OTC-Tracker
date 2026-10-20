# -*- coding: utf-8 -*-
"""As regras PURAS da User Home (e das preferências da Settings): o que é
"minha tarefa de hoje", os anéis do dia, a semana do time, a presença dos
colegas e o relógio do foco. Nada de banco, sessão ou COM aqui — quem lê e
grava é o `queries`/`commands`.

Datas e horas são texto ISO na hora LOCAL do Brasil (`YYYY-MM-DDTHH:MM:SS`),
a mesma do Outlook da máquina e a do `_br_now` do app; comparar texto ISO é
comparar instantes.
"""
import re
from datetime import date, datetime, timedelta

DONE = 'Done'
FOCUS_PRESETS = (15, 25, 50)
MAX_SESSIONS_DAYS = 120
_PRIO = {'Urgent': 0, 'High': 1, 'Medium': 2, 'Low': 3}
_STATUS_ORDER = {'On going': 0, 'On hold': 1, 'Concluded': 2}

# As preferências da Settings, com o padrão de quem nunca abriu a tela. Os
# avisos são do sino do app; o foco é o timer da ilha.
DEFAULT_SETTINGS = {
    'focus_minutes': 25,
    'break_minutes': 5,
    'focus_goal_minutes': 120,
    'notify': {
        'task_assigned': True,
        'task_comment': True,
        'project_lead': True,
        'project_member': True,           # entrou no time de uma iniciativa (§639)
        'due_dates': True,
        'focus_finished': True,
    },
}
NOTIFY_KEYS = tuple(DEFAULT_SETTINGS['notify'])


class HomeError(Exception):
    def __init__(self, code, text, **params):
        super().__init__(text)
        self.code, self.text, self.params = code, text, params


# ── Preferências ─────────────────────────────────────────────────────────────

def settings(doc):
    """As preferências gravadas sobre o padrão (chave desconhecida cai fora)."""
    s = (doc or {}).get('settings') or {}
    out = {k: v for k, v in DEFAULT_SETTINGS.items() if k != 'notify'}
    for k in ('focus_minutes', 'break_minutes', 'focus_goal_minutes'):
        if isinstance(s.get(k), int) and not isinstance(s.get(k), bool):
            out[k] = s[k]
    n = dict(DEFAULT_SETTINGS['notify'])
    for k, v in (s.get('notify') or {}).items():
        if k in n and isinstance(v, bool):
            n[k] = v
    out['notify'] = n
    return out


_LIMITS = {'focus_minutes': (5, 120), 'break_minutes': (1, 60), 'focus_goal_minutes': (15, 600)}


def clean_settings(data, current):
    """O pedido da Settings, validado, sobre o que está gravado. Só muda o que
    veio; número fora da faixa é erro com o campo, nunca truncado calado."""
    out = settings({'settings': current})
    data = data or {}
    for k, (lo, hi) in _LIMITS.items():
        if k in data:
            try:
                v = int(data[k])
            except (TypeError, ValueError):
                raise HomeError('bad_number', 'Invalid number.', field=k)
            if v < lo or v > hi:
                raise HomeError('out_of_range', 'Out of range.', field=k, min=lo, max=hi)
            out[k] = v
    for k, v in (data.get('notify') or {}).items():
        if k not in NOTIFY_KEYS or not isinstance(v, bool):
            raise HomeError('bad_choice', 'Invalid value.', field=k)
        out['notify'][k] = v
    return out


def wants(doc, key):
    """A pessoa quer o aviso `key` no sino? (padrão: sim)."""
    return bool(settings(doc)['notify'].get(key, True))


# ── Tarefas e projetos ───────────────────────────────────────────────────────

def _task_item(p, t):
    item = dict(t)
    item.update({'project_id': p['id'], 'project_name': p.get('name', ''),
                 'project_color': p.get('color', 'blue')})
    return item


def my_tasks(projects, sid, today):
    """As minhas tarefas do dia: em aberto com prazo até hoje (as atrasadas
    também) e as que eu concluí hoje. Abertas primeiro, pelo prazo e pela
    prioridade; as feitas no fim, riscadas na tela."""
    sid = str(sid or '').upper()
    abertas, feitas = [], []
    for p in projects or []:
        for t in p.get('tasks') or []:
            if str(t.get('assignee_sid') or '').upper() != sid:
                continue
            if t.get('status') == DONE:
                if str(t.get('done_at') or '')[:10] == today:
                    feitas.append(_task_item(p, t))
            elif t.get('due') and t['due'] <= today:
                abertas.append(_task_item(p, t))
    abertas.sort(key=lambda t: (t.get('due') or '', _PRIO.get(t.get('priority'), 9), t.get('title', '')))
    feitas.sort(key=lambda t: t.get('done_at') or '')
    return abertas + feitas


def open_tasks(projects, sid):
    """Todas as minhas tarefas em aberto (o "Focus on" do foco)."""
    sid = str(sid or '').upper()
    out = []
    for p in projects or []:
        for t in p.get('tasks') or []:
            if str(t.get('assignee_sid') or '').upper() == sid and t.get('status') != DONE:
                out.append(_task_item(p, t))
    out.sort(key=lambda t: (t.get('due') or '9999-12-31', _PRIO.get(t.get('priority'), 9)))
    return out


def overdue(projects, sid, today):
    sid = str(sid or '').upper()
    return sum(1 for p in projects or [] for t in p.get('tasks') or []
               if str(t.get('assignee_sid') or '').upper() == sid and t.get('status') != DONE
               and t.get('due') and t['due'] < today)


def envolvidos(project):
    """(sid, nome) de quem está na iniciativa, na ordem: o Lead, o TIME (§639) e
    quem tem tarefa. É a regra do `projects.domain.people` — repetida aqui
    porque feature não importa feature —, e UMA para o "é minha?", o cartão e
    o time da Home."""
    out = [(project.get('lead_sid'), project.get('lead_name'))]
    out += [(m.get('sid'), m.get('name')) for m in project.get('members') or []]
    out += [(t.get('assignee_sid'), t.get('assignee_name')) for t in project.get('tasks') or []]
    return [(str(s or '').upper(), n) for s, n in out if s]


def is_mine(project, sid):
    sid = str(sid or '').upper()
    return any(s == sid for s, _n in envolvidos(project))


def week(projects, today):
    """O que o TIME concluiu nesta semana, dia a dia (seg → dom), e a variação
    contra a semana passada inteira."""
    d = date.fromisoformat(today)
    seg = d - timedelta(days=d.weekday())
    dias = [(seg + timedelta(days=i)).isoformat() for i in range(7)]
    ant_ini, ant_fim = (seg - timedelta(days=7)).isoformat(), (seg - timedelta(days=1)).isoformat()
    por_dia = dict.fromkeys(dias, 0)
    anterior = 0
    for p in projects or []:
        for t in p.get('tasks') or []:
            if t.get('status') != DONE:
                continue
            dd = str(t.get('done_at') or '')[:10]
            if dd in por_dia:
                por_dia[dd] += 1
            elif ant_ini <= dd <= ant_fim:
                anterior += 1
    total = sum(por_dia.values())
    delta = None if not anterior else int(round(100.0 * (total - anterior) / anterior))
    return {'days': [{'date': x, 'n': por_dia[x]} for x in dias], 'total': total,
            'last': anterior, 'delta_pct': delta, 'today': today}


def recent_activity(projects, n=12):
    out = []
    for p in projects or []:
        for ev in p.get('activity') or []:
            e = dict(ev)
            e.update({'project_id': p['id'], 'project_name': p.get('name', ''),
                      'project_color': p.get('color', 'blue')})
            out.append(e)
    out.sort(key=lambda e: e.get('at') or '', reverse=True)
    return out[:n]


def sort_projects(cards):
    cards.sort(key=lambda c: (_STATUS_ORDER.get(c.get('status'), 9), c.get('due_date') or '9999-12-31',
                              str(c.get('name', '')).lower()))
    return cards


# ── Calendário ────────────────────────────────────────────────────────────────

def day_events(events, today):
    """Os eventos de HOJE: os que começam hoje e os de dia inteiro que cobrem
    hoje. Os de dia inteiro primeiro."""
    out = []
    for e in events or []:
        ini, fim = str(e.get('start') or ''), str(e.get('end') or '')
        if not ini:
            continue
        if e.get('all_day'):
            if ini[:10] <= today < (fim[:10] or ini[:10]) or ini[:10] == today:
                out.append(e)
        elif ini[:10] == today:
            out.append(e)
    out.sort(key=lambda e: (not e.get('all_day'), e.get('start') or ''))
    return out


def zoom_app(url):
    """O link do Zoom para o APLICATIVO (`zoommtg://`): o botão Join abre a
    reunião direto no Zoom, sem passar por uma aba do navegador. Link que não
    é de reunião do Zoom (`/j/<id>`) fica vazio — a tela usa o https."""
    m = re.match(r'https://([\w.-]*zoom\.us)/j/(\d+)(?:\?(.*))?$', str(url or '').strip(), re.I)
    if not m:
        return ''
    host, conf, qs = m.group(1), m.group(2), m.group(3) or ''
    pwd = ''
    for part in qs.split('&'):
        if part.lower().startswith('pwd='):
            pwd = part[4:]
    return 'zoommtg://%s/join?action=join&confno=%s%s' % (host, conf, ('&pwd=' + pwd) if pwd else '')


def with_app_links(events):
    out = []
    for e in events or []:
        e = dict(e)
        e['join_app'] = zoom_app(e.get('join_url'))
        out.append(e)
    return out


def next_event(events_today, now):
    for e in events_today or []:
        if not e.get('all_day') and str(e.get('end') or '') > now:
            return e
    return None


def meetings_ring(events_today, now):
    reais = [e for e in events_today or [] if not e.get('all_day')]
    return {'done': sum(1 for e in reais if str(e.get('end') or '') <= now), 'total': len(reais)}


# ── Foco ──────────────────────────────────────────────────────────────────────

def _dt(iso):
    return datetime.fromisoformat(str(iso)[:19])


def _iso(dt):
    return dt.replace(microsecond=0).isoformat()


def focus_remaining(running, now):
    """Segundos que faltam na sessão em curso (pausada: os que sobraram)."""
    if not running:
        return 0
    if running.get('paused_left') is not None:
        return max(0, int(running['paused_left']))
    try:
        return max(0, int((_dt(running['ends_at']) - _dt(now)).total_seconds()))
    except (KeyError, TypeError, ValueError):
        return 0


def focus_start(focus, now, minutes, task=None):
    if minutes is None:
        minutes = DEFAULT_SETTINGS['focus_minutes']
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        raise HomeError('bad_number', 'Invalid number.', field='minutes')
    if minutes < 1 or minutes > 180:
        raise HomeError('out_of_range', 'Out of range.', field='minutes', min=1, max=180)
    task = task or {}
    n = _dt(now)
    focus['running'] = {
        'started_at': _iso(n), 'ends_at': _iso(n + timedelta(minutes=minutes)), 'minutes': minutes,
        'task_id': str(task.get('task_id') or ''), 'project_id': str(task.get('project_id') or ''),
        'task_title': str(task.get('task_title') or '')[:200], 'paused_left': None, 'focused_s': 0,
        'resumed_at': _iso(n),
    }
    return focus


def _acumula(running, now):
    """Soma ao `focused_s` o trecho desde o último início/retomada."""
    if running.get('paused_left') is None and running.get('resumed_at'):
        try:
            fim = min(_dt(now), _dt(running['ends_at']))
            running['focused_s'] = int(running.get('focused_s') or 0) + max(
                0, int((fim - _dt(running['resumed_at'])).total_seconds()))
        except (TypeError, ValueError):
            pass


def focus_pause(focus, now):
    r = focus.get('running')
    if not r or r.get('paused_left') is not None:
        return focus
    _acumula(r, now)
    r['paused_left'] = focus_remaining(r, now)
    r['ends_at'] = ''
    r['resumed_at'] = ''
    return focus


def focus_resume(focus, now):
    r = focus.get('running')
    if not r or r.get('paused_left') is None:
        return focus
    n = _dt(now)
    r['ends_at'] = _iso(n + timedelta(seconds=int(r['paused_left'])))
    r['paused_left'] = None
    r['resumed_at'] = _iso(n)
    return focus


def focus_end(focus, now):
    """Encerra (pelo botão ou porque o tempo acabou) e registra a sessão — só
    o tempo FOCADO de verdade conta, e menos de um minuto não é sessão."""
    r = focus.get('running')
    if not r:
        return focus, None
    _acumula(r, now)
    minutos = int(round((r.get('focused_s') or 0) / 60.0))
    sessao = None
    if minutos >= 1:
        sessao = {'date': str(r.get('started_at') or now)[:10], 'start': r.get('started_at') or now,
                  'end': now, 'minutes': minutos, 'task_id': r.get('task_id', ''),
                  'project_id': r.get('project_id', ''), 'task_title': r.get('task_title', '')}
        focus.setdefault('sessions', []).append(sessao)
    corte = (_dt(now) - timedelta(days=MAX_SESSIONS_DAYS)).date().isoformat()
    focus['sessions'] = [s for s in focus.get('sessions') or [] if str(s.get('date') or '') >= corte]
    focus['running'] = None
    return focus, sessao


def focus_expired(focus, now):
    r = (focus or {}).get('running')
    return bool(r and r.get('paused_left') is None and r.get('ends_at') and str(r['ends_at']) <= now)


def focus_today(focus, today, now):
    """Minutos focados hoje e quantas sessões — a em curso conta o que já foi."""
    ss = [s for s in (focus or {}).get('sessions') or [] if s.get('date') == today]
    minutos = sum(int(s.get('minutes') or 0) for s in ss)
    r = (focus or {}).get('running')
    if r and str(r.get('started_at') or '')[:10] == today:
        extra = int(r.get('focused_s') or 0)
        if r.get('paused_left') is None and r.get('resumed_at'):
            try:
                fim = min(_dt(now), _dt(r['ends_at']))
                extra += max(0, int((fim - _dt(r['resumed_at'])).total_seconds()))
            except (TypeError, ValueError):
                pass
        minutos += extra // 60
    return {'minutes': minutos, 'sessions': len(ss)}


# ── Presença (Right now) ─────────────────────────────────────────────────────

def presence(doc, now):
    """Em foco (até quando), em reunião (até quando) ou livre. A reunião NÃO
    leva o assunto: o calendário é de cada um, e o título de uma reunião não é
    da conta da mesa inteira."""
    r = ((doc or {}).get('focus') or {}).get('running')
    if r and r.get('paused_left') is None and str(r.get('ends_at') or '') > now:
        return {'state': 'focus', 'until': r['ends_at']}
    for e in (doc or {}).get('events') or []:
        if e.get('all_day') or int(e.get('busy') or 0) < 2:
            continue
        if str(e.get('start') or '') <= now < str(e.get('end') or ''):
            return {'state': 'meeting', 'until': e.get('end')}
    return {'state': 'free', 'until': ''}
