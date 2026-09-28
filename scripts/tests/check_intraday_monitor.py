#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_intraday_monitor.py — o Intraday Monitor (ex-New Deals Monitor, §567).

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_intraday_monitor.py

O que prende:
  1. a agenda (`domain.task_config`): o padrão de cada tarefa, valor ruim de
     UMA tarefa caindo no padrão DELA, lista vazia de dias = "nunca";
  2. o estado (`domain.avalia`): feita / atrasada / em andamento / a fazer,
     feriado e dia fora da agenda não devidos, feita depois do prazo;
  3. a Intrag desde o import (`domain.intrag_destino`): as três regras do
     espelho, e `Success` saindo daqui (quem conta é a linha real da Intrag);
  4. ponta a ponta com o app num DATA_DIR tmp: o card do Control Panel grava e
     lê a agenda, o snapshot põe a recon como feita pelo registro de execuções
     (com o `End process` como selo), a Comitente só é devida na terça, e a
     operação importada contra o Banco aparece na zona Intrag como
     `Awaiting B3 ID` — e some de lá quando vira `Success`;
  5. o endereço antigo redireciona e a allowlist antiga continua valendo.
"""
import os
import sys
import tempfile
from datetime import date, datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

RAIZ = tempfile.mkdtemp(prefix='intraday-monitor-')
os.environ['OTC_DATA_DIR'] = RAIZ
os.environ['OTC_DATABASE_DIR'] = os.path.join(RAIZ, 'db')
os.environ.setdefault('SECRET_KEY', 'x')
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


from apps.pages.features.deals_monitor import domain as D     # noqa: E402

print('== 1. a agenda ==')
cfg = D.task_config({})
check('sete tarefas', sorted(cfg), sorted(D.TASK_IDS))
check('Pay/Rec: diária (seg-sex) até 20:00', cfg['recon-payrec'], {'days': [0, 1, 2, 3, 4], 'deadline': '20:00'})
check('Comitente: toda terça', cfg['recon-comitente']['days'], [1])
check('CGD: toda sexta', cfg['recon-cgd']['days'], [4])
check('FXO: diária', cfg['recon-fxo']['days'], [0, 1, 2, 3, 4])
for z in ('registration', 'confirmation', 'intrag'):
    check('%s: diária' % z, cfg[z]['days'], [0, 1, 2, 3, 4])
ruim = D.task_config({'recon-fxo': {'days': [1, 9, 'x', 3], 'deadline': '25:00'},
                      'recon-cgd': {'days': [], 'deadline': '17:30'}})
check('dia fora de 0..6 some', ruim['recon-fxo']['days'], [1, 3])
check('horário inválido cai no padrão DA TAREFA', ruim['recon-fxo']['deadline'], '20:00')
check('lista vazia é "nunca"', ruim['recon-cgd']['days'], [])
check('horário válido fica', ruim['recon-cgd']['deadline'], '17:30')
check('as outras tarefas não são tocadas', ruim['recon-payrec'], cfg['recon-payrec'])

print('\n== 2. o estado ==')
c = {'days': [0, 1, 2, 3, 4], 'deadline': '20:00'}
ter = date(2026, 9, 22)                     # terça
antes, depois = datetime(2026, 9, 22, 15, 0), datetime(2026, 9, 22, 21, 0)
check('feita', D.avalia(c, ter, antes, False, True, False)['state'], 'done')
check('a fazer', D.avalia(c, ter, antes, False, False, False)['state'], 'todo')
check('em andamento', D.avalia(c, ter, antes, False, False, True)['state'], 'in_progress')
check('atrasada', D.avalia(c, ter, depois, False, False, True)['state'], 'late')
check('feita depois do prazo marca late_done',
      D.avalia(c, ter, depois, False, True, False, datetime(2026, 9, 22, 20, 30))['late_done'], True)
check('feita no prazo não', D.avalia(c, ter, depois, False, True, False,
                                     datetime(2026, 9, 22, 19, 0))['late_done'], False)
check('minutos até o prazo', D.avalia(c, ter, antes, False, False, False)['minutes_left'], 300)
check('feriado não é devido', D.avalia(c, ter, antes, True, False, False)['due'], False)
check('sábado fora da agenda', D.avalia(c, date(2026, 9, 26), antes, False, False, False)['due'], False)

print('\n== 3. a Intrag desde o import ==')
BJ = 'BANCO J.P. MORGAN S.A.'
check('NDF Commodities contra o Banco → Intrag NDF',
      D.intrag_destino('NDF/Commodities', {'Client': BJ, 'Status': 'New'}), 'Intrag/NDF')
check('... contra cliente, não', D.intrag_destino('NDF/Commodities', {'Client': 'CARGILL', 'Status': 'New'}), None)
check('Commodities Options contra o Banco → Intrag Option',
      D.intrag_destino('Option/Commodities', {'Client': BJ, 'Status': 'Pending'}), 'Intrag/Option')
check('FX Options contra o Banco → Intrag Option',
      D.intrag_destino('Option/FXO', {'Client': BJ, 'Status': 'Approved'}), 'Intrag/Option')
check('NDF Vanilla contra o Lawton → Intrag NDF',
      D.intrag_destino('NDF/Vanilla', {'Client': 'LAWTON FIM', 'Status': 'New'}), 'Intrag/NDF')
check('NDF Other Publisher contra o Lawton → Intrag NDF',
      D.intrag_destino('NDF/OtherPublisher', {'Client': 'Lawton', 'Status': 'Sent'}), 'Intrag/NDF')
check('FWD Start fica fora (o espelho também)',
      D.intrag_destino('NDF/FwdStart', {'Client': 'LAWTON', 'Status': 'New'}), None)
check('Swap B2B → Intrag Swap', D.intrag_destino('Swap/Bullet', {'LE': 'ATACAMA', 'Status': 'New'}), 'Intrag/Swap')
check('Swap contra cliente, não', D.intrag_destino('Swap/Cashflow', {'LE': 'JPM', 'Status': 'New'}), None)
check('Success sai (a linha real da Intrag conta)',
      D.intrag_destino('NDF/Commodities', {'Client': BJ, 'Status': 'Success'}), None)
check('Success sem caixa também', D.intrag_destino('NDF/Commodities', {'Client': BJ, 'status': 'success'}), None)
check('Canceled não conta', D.intrag_destino('NDF/Commodities', {'Client': BJ, 'Status': 'Canceled'}), None)

print('\n== 4. ponta a ponta ==')
from apps.config import DebugConfig                           # noqa: E402
from apps import create_app                                   # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True
cl = app.test_client()
with cl.session_transaction() as s:
    s.update({'authenticated': True, 'user_sid': 'T000000', 'user_name': 'Tester',
              'user_role': 'ADMIN', 'session_ip': '127.0.0.1'})

from apps.pages import routes as R                            # noqa: E402
from apps.pages.platform import task_runs                     # noqa: E402

r = cl.get('/api/control-panel/intraday-tasks')
j = r.get_json() or {}
check('GET da agenda: 200', r.status_code, 200)
check('uma linha por tarefa', [t['id'] for t in j.get('tasks', [])], list(D.TASK_IDS))
r = cl.post('/api/control-panel/intraday-tasks',
            json={'tasks': {'recon-fxo': {'days': [0, 2], 'deadline': '18:30'}}})
check('POST da agenda: 200', r.status_code, 200)
fxo = [t for t in cl.get('/api/control-panel/intraday-tasks').get_json()['tasks'] if t['id'] == 'recon-fxo'][0]
check('a agenda salva volta', (fxo['days'], fxo['deadline']), ([0, 2], '18:30'))
check('tarefa desconhecida é 400',
      cl.post('/api/control-panel/intraday-tasks', json={'tasks': {'x': {}}}).status_code, 400)
cl.post('/api/control-panel/intraday-tasks', json={'tasks': {}})       # volta ao padrão

# A terça passada: a Comitente é devida, a CGD não. A Pay/Rec rodou e foi
# finalizada; a FXO não rodou.
task_runs.record('recon-payrec', 'T000000', 'Tester', '2026-09-22', {'open': 3},
                 now=datetime(2026, 9, 22, 14, 5))
task_runs.record('recon-payrec', 'T000000', 'Tester', '2026-09-22', event='end',
                 now=datetime(2026, 9, 22, 18, 0))
task_runs.record('recon-comitente', 'T000001', 'Outra', '', {'open': 0},
                 now=datetime(2026, 9, 22, 20, 45))

# Uma operação de NDF Commodities contra o Banco, importada e ainda sem B3 ID.
dia_nd = os.path.join(R.NEW_DEALS_CACHE_ROOT, 'NDF', 'Commodities', '2026', '09',
                      '20260922_ndfcomm.json')
R._atomic_write_json(dia_nd, [{'Deal': '111', 'Client': BJ, 'Status': 'New'},
                              {'Deal': '222', 'Client': 'CARGILL', 'Status': 'New'}])

snap = cl.get('/api/intraday-monitor?date=2026-09-22').get_json()
tk = {t['id']: t for t in snap['tasks']}
check('Pay/Rec feita pelo registro', tk['recon-payrec']['state'], 'done')
check('... com a hora da primeira execução', tk['recon-payrec']['ran_at'], '14:05')
check('... as quebras em aberto do registro', tk['recon-payrec']['open'], 3)
check('... e o End process como selo', tk['recon-payrec']['ended'], True)
check('Comitente devida na terça', tk['recon-comitente']['due'], True)
check('Comitente feita, mas depois do prazo', (tk['recon-comitente']['state'],
                                               tk['recon-comitente']['late_done']), ('done', True))
check('CGD não é devida na terça', tk['recon-cgd']['due'], False)
check('FXO (dia passado, não rodou) atrasada', tk['recon-fxo']['state'], 'late')
check('atividade do dia, do mais novo ao mais velho',
      [(a['task'], a['event']) for a in snap['activity']],
      [('recon-comitente', 'run'), ('recon-payrec', 'end'), ('recon-payrec', 'run')])
check('KPIs somam as devidas', snap['kpis']['due'],
      sum(1 for t in snap['tasks'] if t['due']))

intrag = [c for c in snap['cards'] if c['key'] == 'intrag-ndf'][0]
check('a operação do Banco já conta na Intrag, antes do B3 ID',
      intrag['statuses'].get(D.AWAITING_B3), 1)
check('a do cliente não', intrag['total'], 1)
check('e a Intrag fica em aberto no quadro', (tk['intrag']['total'], tk['intrag']['open']), (1, 1))

R._atomic_write_json(dia_nd, [{'Deal': '111', 'Client': BJ, 'Status': 'Success', 'B3_ID': '9'},
                              {'Deal': '222', 'Client': 'CARGILL', 'Status': 'New'}])
snap = cl.get('/api/intraday-monitor?date=2026-09-22').get_json()
intrag = [c for c in snap['cards'] if c['key'] == 'intrag-ndf'][0]
check('no Success sai daqui (quem conta é o espelho)', intrag['statuses'].get(D.AWAITING_B3), None)

print('\n== 5. o endereço antigo ==')
r = cl.get('/new-deals-monitor')
check('/new-deals-monitor redireciona', (r.status_code, r.headers.get('Location', '').endswith('/intraday-monitor')),
      (302, True))
r = cl.get('/intraday-monitor')
check('a página nova abre', r.status_code, 200)
check('com o nome novo', 'Intraday Monitor' in r.data.decode('utf-8'), True)


class _Con(object):
    def execute(self, *a):
        return self

    def fetchone(self):
        return ('["/new-deals-monitor"]', 'BO')

    def close(self):
        pass


_orig = R.get_db_connection
R.get_db_connection = lambda readonly=False: _Con()
try:
    from apps.pages.platform import authz
    check('a allowlist antiga vale para a página nova',
          '/intraday-monitor' in authz._read_user_authz('T000009')[1], True)
finally:
    R.get_db_connection = _orig

print('\nFALHAS: %d' % len(fails))
sys.exit(1 if fails else 0)
