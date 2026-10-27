# -*- coding: utf-8 -*-
"""Owner e backup das tarefas do Intraday Monitor (§701).

O que se prova:
  1. `domain.clean_assignments`: só tarefa do catálogo e LE de `ASSIGN_LES`,
     owner obrigatório, backup ≠ owner, SID fora do cadastro sai, (tarefa, LE)
     repetida vale a última, ordem do catálogo;
  2. `domain.assignment_news`: só quem passou a responder (owner ou backup
     novo), não quem já estava;
  3. a rota: GET devolve a lista e `can_edit`; POST é do BO e do admin (o MO
     leva 403), substitui a lista e avisa no sino SÓ o designado novo
     (`target_sid`);
  4. o snapshot do Monitor leva `assignments` e `people`; a página tem o botão,
     o modal no padrão e o rótulo `Intraday Monitor` está nos três mapas.
"""
import os
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.check-share'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


from apps import create_app                                      # noqa: E402
from apps.config import DebugConfig                              # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True
from apps.pages import routes as R                               # noqa: E402
from apps.pages.features.deals_monitor import domain as D        # noqa: E402
from apps.pages.features.deals_monitor.infra import persistence as P   # noqa: E402

print('== 1. clean_assignments ==')
SIDS = {'A111111', 'T222222'}
got = D.clean_assignments([
    {'task': 'confirmation', 'le': 'mgt', 'owner': 'a111111', 'backup': 't222222'},
    {'task': 'registration', 'le': 'MGT', 'owner': 'A111111', 'backup': 'A111111'},
    {'task': 'nao-existe', 'owner': 'A111111'},
    {'task': 'intrag', 'le': 'XYZ', 'owner': 'A111111'},
    {'task': 'recon-fxo', 'owner': ''},
    {'task': 'recon-cgd', 'owner': 'Z999999'},
    {'task': 'recon-payrec', 'owner': 'T222222', 'backup': 'Z999999'},
    {'task': 'registration', 'le': 'MGT', 'owner': 'T222222'},
], SIDS)
check('limpa, ordena pelo catálogo e a repetida vale a última', got, [
    {'task': 'registration', 'le': 'MGT', 'owner': 'T222222', 'backup': ''},
    {'task': 'confirmation', 'le': 'MGT', 'owner': 'A111111', 'backup': 'T222222'},
    {'task': 'recon-payrec', 'le': '', 'owner': 'T222222', 'backup': ''},
])
check('lixo é lista vazia', D.clean_assignments('x'), [])

print('\n== 2. assignment_news ==')
antes = [{'task': 'registration', 'le': 'MGT', 'owner': 'A111111', 'backup': ''}]
depois = [{'task': 'registration', 'le': 'MGT', 'owner': 'A111111', 'backup': 'T222222'},
          {'task': 'confirmation', 'le': '', 'owner': 'T222222', 'backup': ''}]
check('só o que é novo', D.assignment_news(antes, depois),
      [('T222222', 'backup', 'registration', 'MGT'), ('T222222', 'owner', 'confirmation', '')])

print('\n== 3. a rota ==')
GRAVADO = {'v': antes}
P._load_assignments = lambda strict=False: list(GRAVADO['v'])
P._save_assignments = lambda lista: GRAVADO.__setitem__('v', D.clean_assignments(lista))
P._assignable_people = lambda: [{'sid': 'A111111', 'name': 'Augusto', 'photo': ''},
                                {'sid': 'T222222', 'name': 'Theodoro', 'photo': ''}]
AVISOS = []
R._create_notification = lambda *a, **k: AVISOS.append((a, k))
cl = app.test_client()


def como(papel):
    with cl.session_transaction() as s:
        s.update(authenticated=True, user_sid='E000001', user_name='T', user_role=papel, session_ip='127.0.0.1',
                 session_expires_at=(datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat())


como('MO')
j = cl.get('/api/intraday-monitor/assignments').get_json()
check('GET: a lista, as pessoas e can_edit falso para o MO',
      (j['assignments'], len(j['people']), j['can_edit'], j['les']), (antes, 2, False, ['', 'JPM', 'MGT', 'LAW']))
r = cl.post('/api/intraday-monitor/assignments', json={'assignments': depois})
check('POST do MO: 403', (r.status_code, (r.get_json() or {}).get('code')), (403, 'assign_not_allowed'))
check('   nada gravado', GRAVADO['v'], antes)
como('BO')
r = cl.post('/api/intraday-monitor/assignments', json={'assignments': depois})
check('POST do BO: grava', (r.status_code, GRAVADO['v']), (200, D.clean_assignments(depois)))
check('   avisa só os designados novos, cada um no SEU sino',
      sorted((k.get('target_sid'), a[4]) for a, k in AVISOS),
      [('T222222', 'Backup · B3 Registration (MGT)'), ('T222222', 'Owner · Confirmations')])
check('   na página Intraday Monitor', {a[3] for a, _k in AVISOS}, {'Intraday Monitor'})
r = cl.post('/api/intraday-monitor/assignments', json={'assignments': 'x'})
check('payload ruim: 400', r.status_code, 400)

print('\n== 4. o snapshot, a página e os mapas ==')
from apps.pages.features.deals_monitor import queries as Q      # noqa: E402
_orig = Q._intraday_snapshot
Q._intraday_snapshot = lambda ref: {'tasks': [], 'kpis': {}}
Q_prev = Q._prev_items
Q._prev_items = lambda ref: {'items': []}
try:
    j = cl.get('/api/intraday-monitor').get_json()
    check('o snapshot leva assignments, people e can_assign',
          (j.get('assignments') == GRAVADO['v'], sorted(j.get('people') or {}), j['me'].get('can_assign')),
          (True, ['A111111', 'T222222'], True))
finally:
    Q._intraday_snapshot, Q._prev_items = _orig, Q_prev


def src(*rel):
    return open(os.path.join(ROOT, *rel), encoding='utf-8').read()


tpl = src('apps', 'templates', 'pages', 'intraday-monitor.html')
check('a página: botão, modal liquid-glass e o card com os donos',
      ('id="im-owners-btn"' in tpl, bool(re.search(r'id="imAsgModal"[\s\S]{0,300}modal-content liquid-glass', tpl)),
       'donos(tk)' in tpl), (True, True, True))
check('o rótulo nos três mapas de notificação',
      ("'Intraday Monitor': '/intraday-monitor'" in src('apps', 'pages', 'platform', 'notifications.py'),
       "'Intraday Monitor': '/intraday-monitor'" in src('apps', 'static', 'js', 'sw-push.js'),
       bool(re.search(r"'Intraday Monitor':\s+'/intraday-monitor'", src('apps', 'templates', 'partials', 'topbar.html')))),
      (True, True, True))

print(('\nFAIL: %d' % len(fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
