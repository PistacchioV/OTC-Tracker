"""User Home e Settings (Intraday › User Home, §632) ponta a ponta: as regras
puras do dia (minhas tarefas, semana do time, foco, presença, o link do Zoom),
a API (a Home, o foco, as preferências, o CSV, o Sync fora do Windows), o
Projects calando o aviso que a pessoa desligou, e as duas páginas pessoais
sempre liberadas.

Os dois armazéns vão para um tmp (`store.FILE`/`store.ROOT`), o cadastro é um
stub e o sino é um espião: nada encosta em dado real.
"""
import os
import sys
import tempfile
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

TMP = tempfile.mkdtemp()

from apps.pages.features.projects.infra import people, store as pstore     # noqa: E402
from apps.pages.features.user_home.infra import store as ustore            # noqa: E402
pstore.FILE = os.path.join(TMP, 'projects', 'projects.json')
ustore.ROOT = os.path.join(TMP, 'user-home')

USERS = [
    {'sid': 'B111111', 'name': 'Bia Lead', 'position': 'Associate', 'role': 'BO', 'status': 'ACTIVE'},
    {'sid': 'A222222', 'name': 'Ana Admin', 'position': 'VP', 'role': 'ADMIN', 'status': 'ACTIVE'},
]
people.users = lambda: USERS

from apps.pages import routes as R                                          # noqa: E402
from apps import create_app                                                 # noqa: E402
from apps.config import DebugConfig                                         # noqa: E402
from apps.pages.features.user_home import domain                            # noqa: E402

NOTIFS = []
R._create_notification = lambda actor_sid, actor_name, action, page, detail='', \
    target_role='', target_sid='': NOTIFS.append({'action': action, 'page': page, 'sid': target_sid})
NOW = datetime(2026, 10, 20, 10, 40, 0)
R._br_now = lambda *a, **k: NOW

app = create_app(DebugConfig)
app.config['TESTING'] = True
fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def client_for(sid, name, role, page_access=None):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update({'authenticated': True, 'user_sid': sid, 'user_name': name, 'user_role': role,
                  'user_email': '%s@example.com' % sid.lower(), 'session_ip': '127.0.0.1'})
    return c


def call(c, method, url, body=None):
    r = getattr(c, method)(url, json=body) if body is not None else getattr(c, method)(url)
    return r.status_code, (r.get_json(silent=True) or {})


T = '2026-10-20'
print('== 1. domínio puro ==')
projs = [{'id': 'PRJ-0001', 'name': 'P1', 'color': 'blue', 'lead_sid': 'A222222', 'lead_name': 'Ana', 'tasks': [
    {'id': 't1', 'title': 'late', 'assignee_sid': 'B111111', 'status': 'To do', 'due': '2026-10-18', 'priority': 'Low'},
    {'id': 't2', 'title': 'today', 'assignee_sid': 'B111111', 'status': 'In progress', 'due': T, 'priority': 'Urgent'},
    {'id': 't3', 'title': 'future', 'assignee_sid': 'B111111', 'status': 'To do', 'due': '2026-10-30'},
    {'id': 't4', 'title': 'done today', 'assignee_sid': 'B111111', 'status': 'Done', 'due': '2026-10-25', 'done_at': T + ' 09:00:00'},
    {'id': 't5', 'title': 'done monday', 'assignee_sid': 'A222222', 'status': 'Done', 'done_at': '2026-10-19 09:00:00'},
    {'id': 't6', 'title': 'done last week', 'assignee_sid': 'A222222', 'status': 'Done', 'done_at': '2026-10-14 09:00:00'},
]}]
check('minhas tarefas do dia: atrasada, a de hoje e a feita hoje (no fim)',
      [t['id'] for t in domain.my_tasks(projs, 'B111111', T)], ['t1', 't2', 't4'])
check('atrasadas', domain.overdue(projs, 'B111111', T), 1)
w = domain.week(projs, T)
check('semana: seg 1, ter 1, total 2 contra 1 da anterior (+100%)',
      ([d['n'] for d in w['days']][:2], w['total'], w['last'], w['delta_pct']), ([1, 1], 2, 1, 100))
f = {'running': None, 'sessions': []}
domain.focus_start(f, T + 'T10:00:00', 25, {'task_title': 'x'})
check('foco começa com 25 min', domain.focus_remaining(f['running'], T + 'T10:00:00'), 1500)
domain.focus_pause(f, T + 'T10:10:00')
check('pausado guarda o que falta (15 min)', domain.focus_remaining(f['running'], T + 'T10:30:00'), 900)
domain.focus_resume(f, T + 'T10:30:00')
f, sess = domain.focus_end(f, T + 'T10:35:00')
check('encerrar grava SÓ o tempo focado (10 + 5 = 15 min)', (sess or {}).get('minutes'), 15)
check('e o foco do dia soma a sessão', domain.focus_today(f, T, T + 'T11:00:00'), {'minutes': 15, 'sessions': 1})
f2 = {'running': None, 'sessions': []}
domain.focus_start(f2, T + 'T10:00:00', 25)
check('menos de um minuto não é sessão', domain.focus_end(f2, T + 'T10:00:20')[1], None)
doc = {'focus': {'running': {'ends_at': T + 'T11:30:00', 'paused_left': None}},
       'events': [{'start': T + 'T10:00:00', 'end': T + 'T11:00:00', 'busy': 2, 'title': 'segredo'}]}
check('presença: em foco vence a reunião', domain.presence(doc, T + 'T10:40:00')['state'], 'focus')
doc['focus']['running'] = None
pr = domain.presence(doc, T + 'T10:40:00')
check('presença: em reunião, SEM o assunto', (pr['state'], 'title' in pr, pr['until']), ('meeting', False, T + 'T11:00:00'))
check('o Zoom abre no aplicativo', domain.zoom_app('https://x.zoom.us/j/123?pwd=abc'),
      'zoommtg://x.zoom.us/join?action=join&confno=123&pwd=abc')
check('link que não é reunião do Zoom não vira app', domain.zoom_app('https://teams.microsoft.com/l/x'), '')
try:
    domain.clean_settings({'focus_minutes': 500}, {})
    check('sessão fora da faixa é erro', False, True)
except domain.HomeError as e:
    check('sessão fora da faixa é erro com o campo', (e.code, e.params.get('field')), ('out_of_range', 'focus_minutes'))

print('\n== 2. API da Home ==')
bia = client_for('B111111', 'Bia Lead', 'BO')
ana = client_for('A222222', 'Ana Admin', 'ADMIN')
st, d = call(ana, 'post', '/api/projects', {'name': 'Proj', 'lead_sid': 'A222222'})
pid = d['project']['id']
call(ana, 'post', '/api/projects/%s/tasks' % pid, {'title': 'Hoje', 'assignee_sid': 'B111111', 'due': T, 'priority': 'High'})
st, d = call(bia, 'get', '/api/user-home')
check('GET /api/user-home', st, 200)
check('a tarefa de hoje está em My tasks', [t['title'] for t in d['my_tasks']], ['Hoje'])
check('o projeto em que ela tem tarefa aparece', [p['name'] for p in d['projects']], ['Proj'])
check('a Ana está no Right now, livre', [(p['sid'], p['state']) for p in d['team']], [('A222222', 'free')])
check('meta do Projects (pessoas, status) vem junto', 'people' in d.get('meta', {}), True)

print('\n== 3. foco pela API, e o colega vê ==')
st, d = call(ana, 'post', '/api/user-home/focus', {'action': 'start', 'minutes': 50})
check('a Ana começa 50 min', (st, d['focus']['minutes'], d['focus']['remaining']), (200, 50, 3000))
st, d = call(bia, 'get', '/api/user-home')
check('a Bia vê a Ana em foco até 11:30', [(p['state'], p['until'][11:16]) for p in d['team']], [('focus', '11:30')])
st, d = call(ana, 'post', '/api/user-home/focus', {'action': 'nada'})
check('ação desconhecida: 400 bad_action', (st, d.get('code')), (400, 'bad_action'))
call(ana, 'post', '/api/user-home/focus', {'action': 'end'})

print('\n== 4. Sync fora do Windows ==')
st, d = call(bia, 'post', '/api/user-home/sync')
check('sem Outlook: 503 outlook_unavailable', (st, d.get('code')), (503, 'outlook_unavailable'))

print('\n== 5. Settings ==')
st, d = call(bia, 'get', '/api/settings')
check('GET /api/settings traz o padrão', (st, d['settings']['focus_minutes'], d['settings']['notify']['task_assigned']), (200, 25, True))
st, d = call(bia, 'post', '/api/settings', {'focus_minutes': 30, 'notify': {'task_assigned': False}})
check('grava a sessão e o aviso', (st, d['settings']['focus_minutes'], d['settings']['notify']['task_assigned']), (200, 30, False))
st, d = call(bia, 'post', '/api/settings', {'break_minutes': 0})
check('pausa fora da faixa: 400', (st, d.get('code'), d.get('params', {}).get('field')), (400, 'out_of_range', 'break_minutes'))
st, d = call(bia, 'post', '/api/settings', {'notify': {'inventado': True}})
check('aviso desconhecido: 400', (st, d.get('code')), (400, 'bad_choice'))

print('\n== 6. o Projects respeita o aviso desligado ==')
NOTIFS.clear()
call(ana, 'post', '/api/projects/%s/tasks' % pid, {'title': 'Outra', 'assignee_sid': 'B111111'})
check('a Bia desligou "Task assigned": o sino não toca', [n for n in NOTIFS if n['action'] == 'Task Assigned'], [])
call(bia, 'post', '/api/settings', {'notify': {'task_assigned': True}})
call(ana, 'post', '/api/projects/%s/tasks' % pid, {'title': 'Mais uma', 'assignee_sid': 'B111111'})
check('religou: o sino toca para ela', [n['sid'] for n in NOTIFS if n['action'] == 'Task Assigned'], ['B111111'])
st, d = call(bia, 'post', '/api/settings', {'reset': True})
check('reset volta ao padrão', (st, d['settings']['focus_minutes']), (200, 25))

print('\n== 7. o aviso das 08:00 ("vence hoje") ==')
from apps.pages.features.user_home import commands                          # noqa: E402
NOTIFS.clear()
with app.app_context():
    n = commands.due_digest(T)
check('um aviso para a Bia, com a página User Home', (n, [(x['sid'], x['page']) for x in NOTIFS]), (1, [('B111111', 'User Home')]))
call(bia, 'post', '/api/settings', {'notify': {'due_dates': False}})
NOTIFS.clear()
with app.app_context():
    n = commands.due_digest(T)
check('com "Due dates" desligado, nada', n, 0)

print('\n== 8. CSV das minhas tarefas ==')
r = bia.get('/api/settings/export-tasks')
txt = r.data.decode('utf-8')
check('CSV da casa: BOM, `;` e três tarefas', (r.status_code, txt.startswith('﻿'), txt.count('\r\n') - 1, ';' in txt.split('\r\n')[0]),
      (200, True, 3, True))

print('\n== 9. páginas pessoais ==')
check('user-home e settings são sempre liberadas', {'/user-home', '/settings'} <= R._ALWAYS_ALLOWED_PATHS, True)
check('GET /user-home', bia.get('/user-home').status_code, 200)
check('GET /settings', bia.get('/settings').status_code, 200)
anon = app.test_client()
check('sem sessão: 401 na API', anon.get('/api/user-home').status_code, 401)
check('o rótulo do sino existe nos três mapas', all(
    "'User Home'" in open(p, encoding='utf-8').read() for p in
    ('apps/pages/platform/notifications.py', 'apps/templates/partials/topbar.html', 'apps/static/js/sw-push.js')), True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
