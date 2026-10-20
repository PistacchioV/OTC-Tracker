"""Projects (Apps › Projects) ponta a ponta, por HTTP: criação, quem pode ser
Lead, tarefas, subtarefas, comentários, marcos, progresso, burn-up, o sino, a
trava de acesso e quem apaga.

O armazém vai para um tmp (`store.FILE`), o cadastro de usuários é um stub
(`people.users`) e o sino é um espião (`routes._create_notification`): nada
encosta em dado real.
"""
import io
import os
import sys
import tempfile
from datetime import date, datetime, timedelta

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

TMP = tempfile.mkdtemp()

from apps.pages.features.projects.infra import people, store      # noqa: E402
store.FILE = os.path.join(TMP, 'projects', 'projects.json')

USERS = [
    {'sid': 'B111111', 'name': 'Bia Lead', 'position': 'Associate', 'role': 'BO', 'status': 'ACTIVE'},
    {'sid': 'A222222', 'name': 'Ana Admin', 'position': 'VP', 'role': 'ADMIN', 'status': 'ACTIVE'},
    {'sid': 'M333333', 'name': 'Mo Middle', 'position': '', 'role': 'MO', 'status': 'ACTIVE'},
    {'sid': 'B444444', 'name': 'Beto Inativo', 'position': '', 'role': 'BO', 'status': 'INACTIVE'},
]
people.users = lambda: USERS

from apps.pages import routes as R                                  # noqa: E402
from apps import create_app                                         # noqa: E402
from apps.config import DebugConfig                                 # noqa: E402
from apps.pages.features.projects import domain                     # noqa: E402

NOTIFS = []
R._create_notification = lambda actor_sid, actor_name, action, page, detail='', \
    target_role='', target_sid='': NOTIFS.append(
        {'actor': actor_sid, 'action': action, 'page': page, 'detail': detail, 'sid': target_sid})

app = create_app(DebugConfig)
app.config['TESTING'] = True

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def client_for(sid, name, role):
    c = app.test_client()
    with c.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = sid
        s['user_name'] = name
        s['user_role'] = role
        s['user_email'] = 'x@jpmorgan.com'
        s['session_ip'] = '127.0.0.1'
    return c


bia = client_for('B111111', 'Bia Lead', 'BO')
mo = client_for('M333333', 'Mo Middle', 'MO')
ana = client_for('A222222', 'Ana Admin', 'ADMIN')


def call(c, method, url, body=None):
    r = getattr(c, method)(url, json=body) if body is not None else getattr(c, method)(url)
    return r.status_code, (r.get_json(silent=True) or {})


print('\n== 1. quem pode ser Lead: BO e Admin ATIVOS (+ a sessão BO/Admin) ==')
st, d = call(bia, 'get', '/api/projects')
check('GET 200', st, 200)
check('lista vazia', d.get('projects'), [])
check('Lead = BO e Admin ativos', [p['sid'] for p in d['people']], ['A222222', 'B111111'])
check('status do filtro', d['statuses'], ['On going', 'On hold', 'Concluded'])
st, d = call(mo, 'get', '/api/projects')
check('sessão MO não entra na lista', [p['sid'] for p in d['people']], ['A222222', 'B111111'])
dev = client_for('A000000', 'Dev User', 'ADMIN')
st, d = call(dev, 'get', '/api/projects')
check('admin fora do cadastro entra (a dev, o master)', 'A000000' in [p['sid'] for p in d['people']], True)
# a foto: a mesma `images/users/<sid>.jpg` da barra, só quando o arquivo existe
# (é dela que o avatar de Lead, responsável, comentário e atividade sai)
USERS.append({'sid': 'E930179', 'name': 'Com Foto', 'position': '', 'role': 'BO', 'status': 'ACTIVE'})
fotos = {p['sid']: p['photo'] for p in call(bia, 'get', '/api/projects')[1]['people']}
USERS.pop()
check('quem tem o arquivo leva a foto', fotos.get('E930179'), '/static/images/users/e930179.jpg')
check('quem não tem leva vazio (ficam as iniciais)', fotos.get('B111111'), '')
check('o avatar acha a foto pelo SID na lista de pessoas',
      'photo = photoOf(sid, name)' in open('apps/static/js/pages/projects-common.js', encoding='utf-8').read(), True)

print('\n== 2. criação ==')
st, d = call(bia, 'post', '/api/projects', {'name': '  Recon  revamp ', 'description': 'Faster recons',
                                            'lead_sid': 'A222222', 'color': 'purple', 'icon': 'rocket',
                                            'due_date': '31/12/2026', 'status': 'On hold',
                                            'category': 'process review'})
check('POST 200', st, 200)
P1 = d['project']['id']
check('id sequencial', P1, 'PRJ-0001')
check('nome limpo', d['project']['name'], 'Recon revamp')
check('data dd/mm vira ISO', d['project']['due_date'], '2026-12-31')
check('status escolhido', d['project']['status'], 'On hold')
check('início = hoje quando não vem', d['project']['start_date'], R._br_now().date().isoformat())
check('categoria pela lista fechada (sem caixa)', d['project']['category'], 'Process Review')
# desde 20/10/2026 a tela diz Initiatives — o sino grava os nomes novos
check('Lead avisado no sino', [(n['action'], n['sid'], n['page']) for n in NOTIFS],
      [('Initiative Lead', 'A222222', 'Initiatives')])
check('   e a página nova está nos três mapas',
      all("'Initiatives'" in open(p_, encoding='utf-8').read() for p_ in
          ('apps/pages/platform/notifications.py', 'apps/templates/partials/topbar.html', 'apps/static/js/sw-push.js')), True)

st, d = call(bia, 'post', '/api/projects', {'name': 'X', 'lead_sid': 'M333333'})
check('Lead MO recusado', (st, d.get('code')), (400, 'not_eligible'))
st, d = call(bia, 'post', '/api/projects', {'name': 'X', 'lead_sid': 'B444444'})
check('Lead inativo recusado', (st, d.get('code')), (400, 'not_eligible'))
st, d = call(bia, 'post', '/api/projects', {'name': '', 'lead_sid': 'B111111'})
check('sem nome -> name_required', (st, d.get('code')), (400, 'name_required'))
st, d = call(bia, 'post', '/api/projects', {'name': 'X'})
check('sem Lead -> lead_required', (st, d.get('code')), (400, 'lead_required'))
st, d = call(bia, 'post', '/api/projects', {'name': 'X', 'lead_sid': 'B111111'})
check('sem categoria -> category_required', (st, d.get('code')), (400, 'category_required'))
st, d = call(bia, 'post', '/api/projects', {'name': 'X', 'lead_sid': 'B111111', 'category': 'Marketing'})
check('categoria fora da lista recusada', (st, d.get('code'), d.get('params')), (400, 'bad_choice', {'field': 'category'}))
st, d = call(bia, 'post', '/api/projects', {'name': 'X', 'lead_sid': 'B111111', 'category': 'Projects', 'color': 'red;}'})
check('cor fora da lista recusada', (st, d.get('code'), d.get('params')), (400, 'bad_choice', {'field': 'color'}))
st, d = call(bia, 'post', '/api/projects', {'name': 'X', 'lead_sid': 'B111111', 'category': 'Projects',
                                            'start_date': '2026-10-10', 'due_date': '2026-10-01'})
check('alvo antes do início', d.get('code'), 'due_before_start')

st, d = call(bia, 'post', '/api/projects', {'name': 'Second', 'lead_sid': 'B111111', 'category': 'Stomp/Red'})
P2 = d['project']['id']
check('segundo id', P2, 'PRJ-0002')
check('Lead = quem criou: sem aviso', len(NOTIFS), 1)
st, d = call(bia, 'get', '/api/projects')
check('o cartão da lista traz a categoria', sorted((p['id'], p['category']) for p in d['projects']),
      [('PRJ-0001', 'Process Review'), ('PRJ-0002', 'Stomp/Red')])
check('o meta traz a lista fechada', d.get('categories'),
      ['Process Review', 'Tech Issue', 'Projects', 'B3 - Improvements', 'Stomp/Red'])
st, d = call(bia, 'patch', '/api/projects/%s' % P2, {'category': 'B3 - Improvements'})
check('editar troca a categoria', (st, d['project']['category']), (200, 'B3 - Improvements'))
st, d = call(bia, 'patch', '/api/projects/%s' % P2, {'category': ''})
check('editar não apaga a categoria', (st, d.get('code')), (400, 'category_required'))
st, d = call(bia, 'patch', '/api/projects/%s' % P2, {'name': 'Second'})
check('editar SEM mexer na categoria passa (a de antes não tem)', st, 200)

print('\n== 3. tarefas, progresso e o sino ==')
st, d = call(bia, 'post', '/api/projects/%s/tasks' % P1, {'title': 'Map columns', 'assignee_sid': 'B111111',
                                                         'priority': 'High', 'due': '2026-11-05', 'estimate': '2,5'})
check('tarefa criada', st, 200)
t1 = d['project']['tasks'][0]
check('estimativa com vírgula', t1['estimate'], 2.5)
check('status padrão To do', t1['status'], 'To do')
check('progresso 0%', d['project']['progress'], 0)
st, d = call(bia, 'post', '/api/projects/%s/tasks' % P1, {'title': 'Write tests', 'assignee_sid': 'A222222'})
t2 = [t for t in d['project']['tasks'] if t['title'] == 'Write tests'][0]
check('aviso de tarefa para quem recebeu', NOTIFS[-1]['action'], 'Task Assigned')
check('...com projeto e tarefa', NOTIFS[-1]['detail'], 'Recon revamp — Write tests')
n_antes = len(NOTIFS)
st, d = call(bia, 'patch', '/api/projects/%s/tasks/%s' % (P1, t1['id']), {'status': 'Done'})
check('marcar feita', st, 200)
t1d = [t for t in d['project']['tasks'] if t['id'] == t1['id']][0]
check('done_at gravado', bool(t1d['done_at']), True)
check('progresso 50%', d['project']['progress'], 50)
check('open_tasks 1', d['project']['open_tasks'], 1)
check('mudar status não avisa ninguém', len(NOTIFS), n_antes)
st, d = call(bia, 'patch', '/api/projects/%s/tasks/%s' % (P1, t1['id']), {'status': 'In review'})
t1r = [t for t in d['project']['tasks'] if t['id'] == t1['id']][0]
check('reabrir limpa done_at', t1r['done_at'], '')
st, d = call(bia, 'patch', '/api/projects/%s/tasks/%s' % (P1, t1['id']), {'status': 'Archived'})
check('status de tarefa inválido', d.get('code'), 'bad_choice')
st, d = call(bia, 'patch', '/api/projects/%s/tasks/t999' % P1, {'status': 'Done'})
check('tarefa inexistente 404', (st, d.get('code')), (404, 'task_not_found'))

print('\n== 4. subtarefas e comentários ==')
st, d = call(bia, 'post', '/api/projects/%s/tasks/%s/subtasks' % (P1, t2['id']), {'title': 'Draft'})
sub = [t for t in d['project']['tasks'] if t['id'] == t2['id']][0]['subtasks']
check('subtarefa criada', [s['title'] for s in sub], ['Draft'])
st, d = call(bia, 'patch', '/api/projects/%s/tasks/%s/subtasks/%s' % (P1, t2['id'], sub[0]['id']), {'done': True})
sub = [t for t in d['project']['tasks'] if t['id'] == t2['id']][0]['subtasks']
check('subtarefa marcada', sub[0]['done'], True)
st, d = call(bia, 'post', '/api/projects/%s/tasks/%s/comments' % (P1, t2['id']), {'text': 'Looks good\nship it'})
com = [t for t in d['project']['tasks'] if t['id'] == t2['id']][0]['comments']
check('comentário com quebra de linha', com[0]['text'], 'Looks good\nship it')
check('autor da sessão', com[0]['name'], 'Bia Lead')
check('responsável avisado do comentário', NOTIFS[-1]['action'], 'Task Comment')
st, d = call(bia, 'post', '/api/projects/%s/tasks/%s/comments' % (P1, t2['id']), {'text': '   '})
check('comentário vazio recusado', d.get('code'), 'comment_required')
st, d = call(bia, 'delete', '/api/projects/%s/tasks/%s/subtasks/%s' % (P1, t2['id'], sub[0]['id']))
check('subtarefa apagada', [t for t in d['project']['tasks'] if t['id'] == t2['id']][0]['subtasks'], [])

print('\n== 5. marcos ==')
st, d = call(bia, 'post', '/api/projects/%s/milestones' % P1, {'title': 'Go live', 'date': '2026-12-15'})
st, d = call(bia, 'post', '/api/projects/%s/milestones' % P1, {'title': 'Spec signed', 'date': '2026-11-01'})
ms = d['project']['milestones']
check('marcos pela data', [m['title'] for m in ms], ['Spec signed', 'Go live'])
check('próximo marco = o mais cedo em aberto', d['project']['next_milestone']['title'], 'Spec signed')
st, d = call(bia, 'patch', '/api/projects/%s/milestones/%s' % (P1, ms[0]['id']), {'done': True})
check('marco concluído -> próximo é o seguinte', d['project']['next_milestone']['title'], 'Go live')
check('atividade registra o marco', d['project']['activity'][0]['kind'], 'milestone_done')
check('atividade é ESTRUTURADA', d['project']['activity'][0]['params'], {'milestone': 'Spec signed'})
st, d = call(bia, 'post', '/api/projects/%s/milestones' % P1, {'title': ''})
check('marco sem título', d.get('code'), 'title_required')

print('\n== 6. edição do projeto ==')
st, d = call(mo, 'patch', '/api/projects/%s' % P1, {'status': 'On going'})
check('qualquer um com acesso edita', (st, d['project']['status']), (200, 'On going'))
check('Lead mantido (não veio no pedido)', d['project']['lead_sid'], 'A222222')
st, d = call(bia, 'patch', '/api/projects/%s' % P1, {'lead_sid': 'B111111'})
check('troca de Lead', d['project']['lead_name'], 'Bia Lead')

print('\n== 7. lista e cartão ==')
st, d = call(bia, 'get', '/api/projects')
card = [p for p in d['projects'] if p['id'] == P1][0]
check('tarefas no cartão', (card['tasks_done'], card['tasks_total']), (0, 2))
check('pessoas: Lead primeiro', [p['sid'] for p in card['people']][:1], ['B111111'])
check('marcos no cartão', (card['milestones_done'], card['milestones_total']), (1, 2))

print('\n== 8. burn-up (puro) ==')
proj = {'start_date': '2026-10-01', 'status': 'On going', 'tasks': [
    {'created_at': '2026-10-01 09:00:00', 'status': 'Done', 'done_at': '2026-10-03 10:00:00'},
    {'created_at': '2026-10-02 09:00:00', 'status': 'To do', 'done_at': ''}]}
b = domain.burnup(proj, date(2026, 10, 4))
check('um ponto por dia', b['labels'], ['2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04'])
check('total acumula pela criação', b['total'], [1, 2, 2, 2])
check('feitas pela conclusão', b['done'], [0, 0, 1, 1])
longo = domain.burnup({'start_date': '2025-01-01', 'tasks': []}, date(2026, 10, 4))
check('projeto longo é amostrado', len(longo['labels']) <= domain.MAX_BURNUP_POINTS + 1, True)
check('...e termina hoje', longo['labels'][-1], '2026-10-04')
check('sem tarefa: concluído = 100%', domain.progress({'status': 'Concluded', 'tasks': []}), 100)

print('\n== 8b. a Tasks reúne as tarefas de todos os projetos ==')
st, d = call(bia, 'get', '/api/tasks')
check('GET /api/tasks 200', st, 200)
check('tarefa traz o projeto ao lado', sorted({(t['project_id'], t['project_name']) for t in d['tasks']}),
      [(P1, 'Recon revamp')])
check('projetos com as abertas (menu do filtro)', {p['id']: p['open'] for p in d['projects']}, {P1: 2, P2: 0})
real_tasks = R._user_can_access_page
R._user_can_access_page = lambda url: url == '/tasks'
st, d = call(bia, 'patch', '/api/projects/%s/tasks/%s' % (P1, t2['id']), {'status': 'In progress'})
check('quem só tem a Tasks também move a tarefa', st, 200)
R._user_can_access_page = real_tasks

print('\n== 8c. as datas vão para o Calendar ==')
st, d = call(bia, 'get', '/api/projects/calendar')
kinds = sorted({(e['kind'], e['title']) for e in d['events'] if e['project_id'] == P1})
check('alvo do projeto, marcos e tarefa EM ABERTO com prazo', kinds,
      [('milestone', 'Go live'), ('milestone', 'Spec signed'), ('project', 'Recon revamp'), ('task', 'Map columns')])
check('marco feito vai marcado', [e['done'] for e in d['events'] if e.get('title') == 'Spec signed'], [True])
evs = domain.calendar_events([{'id': 'X', 'name': 'N', 'due_date': '', 'tasks': [
    {'id': 't1', 'title': 'Aberta', 'due': '2026-11-01', 'status': 'To do'},
    {'id': 't2', 'title': 'Feita', 'due': '2026-11-02', 'status': 'Done'},
    {'id': 't3', 'title': 'Sem prazo', 'due': '', 'status': 'To do'}]}])
check('tarefa feita e tarefa sem prazo ficam fora', [e['title'] for e in evs], ['Aberta'])
real_cal = R._user_can_access_page
R._user_can_access_page = lambda url: False
st, d = call(bia, 'get', '/api/projects/calendar')
check('sem Projects/Tasks: lista vazia, não 403 (o Calendar abre igual)', (st, d.get('events')), (200, []))
R._user_can_access_page = real_cal

print('\n== 9. acesso e quem apaga ==')
st, d = call(mo, 'delete', '/api/projects/%s' % P1)
check('MO que não é Lead nem criador não apaga', (st, d.get('code')), (403, 'not_allowed'))
real = R._user_can_access_page
R._user_can_access_page = lambda url: False
st, d = call(bia, 'get', '/api/projects')
check('sem a página Projects: 403', (st, d.get('code')), (403, 'not_allowed'))
r = bia.get('/initiatives/%s' % P1)
check('página da iniciativa sem acesso volta para /initiatives', (r.status_code, r.headers.get('Location', '')),
      (302, '/initiatives'))
R._user_can_access_page = real
r = bia.get('/initiatives/%s' % P1)
check('página da iniciativa abre', r.status_code, 200)
r = bia.get('/initiatives/PRJ-9999')
check('iniciativa inexistente volta para a lista', r.status_code, 302)
# O endereço é /initiatives (§638): o antigo redireciona — favoritos, e-mails e
# avisos já enviados chegam à MESMA iniciativa, com o `?task=` junto.
r = bia.get('/projects')
check('/projects redireciona para /initiatives', (r.status_code, r.headers.get('Location', '')),
      (302, '/initiatives'))
r = bia.get('/projects/%s?task=t3' % P1)
check('/projects/<id>?task= redireciona para a mesma iniciativa e tarefa',
      (r.status_code, r.headers.get('Location', '')), (302, '/initiatives/%s?task=t3' % P1))
r = bia.get('/initiatives')
check('a lista abre em /initiatives', r.status_code, 200)
_navs = io.open('apps/templates/partials/sidenav.html', encoding='utf-8').read()
check('o menu leva a /initiatives', ('href="/initiatives"' in _navs, 'href="/projects"' in _navs), (True, False))


class _Con(object):
    def execute(self, *a):
        return self

    def fetchone(self):
        return ('["/projects"]', 'BO')

    def close(self):
        pass


_orig_conn = R.get_db_connection
R.get_db_connection = lambda readonly=False: _Con()
try:
    from apps.pages.platform import authz as _authz_mod
    check('quem tem /projects gravado no acesso entra em /initiatives',
          '/initiatives' in _authz_mod._read_user_authz('T000009')[1], True)
finally:
    R.get_db_connection = _orig_conn
st, d = call(ana, 'delete', '/api/projects/%s' % P2)
check('admin apaga', st, 200)
st, d = call(bia, 'delete', '/api/projects/%s' % P1)
check('Lead apaga', st, 200)
st, d = call(bia, 'get', '/api/projects')
check('lista vazia de novo', d['projects'], [])
st, d = call(bia, 'post', '/api/projects', {'name': 'Third', 'lead_sid': 'B111111', 'category': 'Tech Issue'})
check('id não reaproveita apagado', d['project']['id'], 'PRJ-0003')
anon = app.test_client()
st, d = call(anon, 'get', '/api/projects')
check('sem sessão: 401', st, 401)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
