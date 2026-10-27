# -*- coding: utf-8 -*-
"""Owner e backup das tarefas do Intraday Monitor (§701).

O que se prova:
  1. `domain.clean_assignments`: só tarefa do catálogo e LE de `ASSIGN_LES`,
     owner obrigatório, backup ≠ owner, SID fora do cadastro sai, (tarefa,
     produto, LE) repetida vale a última, ordem do catálogo; o PRODUTO (§703)
     só nas três tarefas de zona e só os cards da zona delas;
  2. `domain.assignment_news`: só quem passou a responder (owner ou backup
     novo), não quem já estava;
  3. a rota: GET devolve a lista e `can_edit`; POST é do BO e do admin (o MO
     leva 403), substitui a lista e avisa no sino SÓ o designado novo
     (`target_sid`);
  4. o snapshot do Monitor leva `assignments` e `people`; a página tem o botão,
     o modal no padrão e o rótulo `Intraday Monitor` está nos três mapas;
  5. (§703) só BO, ADMIN e o master podem ser designados; os produtos de
     Confirmations são os cards da zona; Cancel/Save/Remove são squircle.
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
    {'task': 'registration', 'product': '', 'le': 'MGT', 'owner': 'T222222', 'backup': ''},
    {'task': 'confirmation', 'product': '', 'le': 'MGT', 'owner': 'A111111', 'backup': 'T222222'},
    {'task': 'recon-payrec', 'product': '', 'le': '', 'owner': 'T222222', 'backup': ''},
])
got = D.clean_assignments([
    {'task': 'registration', 'product': 'NDF-COMMODITIES', 'owner': 'A111111'},
    {'task': 'registration', 'product': 'ndf-vanilla', 'le': 'MGT', 'owner': 'A111111', 'backup': 'T222222'},
    {'task': 'registration', 'product': 'intrag-ndf', 'owner': 'A111111'},
    {'task': 'intrag', 'product': 'intrag-ndf', 'owner': 'T222222'},
    {'task': 'confirmation', 'product': 'ndf-vanilla', 'owner': 'T222222'},
    {'task': 'confirmation', 'product': 'swap-cem', 'owner': 'T222222'},
    {'task': 'recon-fxo', 'product': 'ndf-vanilla', 'owner': 'A111111'},
], SIDS)
check('produto: o card da zona da tarefa; o de outra zona e a tarefa sem produto saem',
      [(a['task'], a['product'], a['le']) for a in got],
      [('registration', 'ndf-commodities', ''), ('registration', 'ndf-vanilla', 'MGT'),
       ('confirmation', 'ndf-vanilla', ''), ('intrag', 'intrag-ndf', '')])
check('a mesma tarefa em dois produtos são duas linhas',
      len(D.clean_assignments([{'task': 'registration', 'product': 'ndf-vanilla', 'owner': 'A111111'},
                               {'task': 'registration', 'product': 'ndf-commodities', 'owner': 'T222222'}])), 2)
check('lixo é lista vazia', D.clean_assignments('x'), [])

print('\n== 2. assignment_news ==')
antes = [{'task': 'registration', 'product': '', 'le': 'MGT', 'owner': 'A111111', 'backup': ''}]
depois = [{'task': 'registration', 'product': '', 'le': 'MGT', 'owner': 'A111111', 'backup': 'T222222'},
          {'task': 'confirmation', 'product': '', 'le': '', 'owner': 'T222222', 'backup': ''},
          {'task': 'registration', 'product': 'ndf-vanilla', 'le': 'MGT', 'owner': 'A111111', 'backup': ''}]
check('só o que é novo (outro produto é outra linha)', D.assignment_news(antes, depois),
      [('T222222', 'backup', 'registration', '', 'MGT'), ('T222222', 'owner', 'confirmation', '', ''),
       ('A111111', 'owner', 'registration', 'ndf-vanilla', 'MGT')])

print('\n== 3. a rota ==')
GRAVADO = {'v': antes}
P._load_assignments = lambda strict=False: list(GRAVADO['v'])
P._save_assignments = lambda lista: GRAVADO.__setitem__('v', D.clean_assignments(lista))
_PEOPLE_REAL = P._assignable_people
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
check('   avisa só os designados novos, cada um no SEU sino, com o produto',
      sorted((k.get('target_sid'), a[4]) for a, k in AVISOS),
      [('A111111', 'Owner · B3 Registration · NDF Vanilla (MGT)'),
       ('T222222', 'Backup · B3 Registration (MGT)'), ('T222222', 'Owner · Confirmations')])
j = cl.get('/api/intraday-monitor/assignments').get_json()
check('GET: os produtos de cada tarefa de zona',
      (sorted(j['products']), j['products']['confirmation'][2]),
      (['confirmation', 'intrag', 'registration'], {'key': 'ndf-vanilla', 'label': 'NDF Vanilla'}))
check('   na página Intraday Monitor', {a[3] for a, _k in AVISOS}, {'Intraday Monitor'})
r = cl.post('/api/intraday-monitor/assignments', json={'assignments': 'x'})
check('payload ruim: 400', r.status_code, 400)

print('\n== 4. o snapshot, a página e os mapas ==')
from apps.pages.features.deals_monitor import queries as Q      # noqa: E402
_orig = Q._intraday_snapshot
# só o NDF Vanilla (JPM e MGT) se mexeu: Confirmations sem movimento
Q._intraday_snapshot = lambda ref: {'tasks': [], 'kpis': {}, 'conf_cards': [], 'cards': [
    {'key': 'ndf-vanilla', 'total': 3, 'les': [{'le': 'JPM', 'count': 1}, {'le': 'MGT', 'count': 2}]}]}
Q_prev = Q._prev_items
Q._prev_items = lambda ref: {'items': []}
try:
    j = cl.get('/api/intraday-monitor').get_json()
    check('o snapshot leva assignments, people, can_assign e o rótulo dos produtos',
          (bool(j.get('assignments')), sorted(j.get('people') or {}), j['me'].get('can_assign'),
           (j.get('assign_products') or {}).get('intrag-ndf')),
          (True, ['A111111', 'T222222'], True, 'Intrag NDF'))
    check('   só os owners das tarefas e produtos com movimento no dia',
          [(a['task'], a['product'], a['le']) for a in j.get('assignments') or []],
          [(a['task'], a['product'], a['le']) for a in GRAVADO['v'] if a['task'] == 'registration'])
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

print('\n== 5. quem pode ser designado, os produtos e os botões (§703) ==')


class _Con:
    def execute(self, sql, *a):
        class _R:
            def fetchall(_s):
                return [('A111111', 'Ana', 'Active', 'BO'), ('B222222', 'Beto', 'Active', 'ADMIN'),
                        ('C333333', 'Caio', 'Active', 'MO'), ('D444444', 'Duda', 'Inactive', 'BO'),
                        ('E930179', 'Master', 'Active', 'FO'), ('F555555', 'Fê', 'Active', '')]
        return _R()

    def close(self):
        pass


_gdc = R.get_db_connection
R.get_db_connection = lambda readonly=False: _Con()
P._people_memo['rows'] = None
try:
    _ap = _PEOPLE_REAL
    check('só BO, ADMIN e o master, ativos', [p['sid'] for p in _ap()], ['A111111', 'B222222', 'E930179'])
finally:
    R.get_db_connection = _gdc
qsrc = src('apps', 'pages', 'features', 'deals_monitor', 'queries.py')
cards_conf = re.findall(r"'(conf-[a-z0-9-]+)'", qsrc)
check('os produtos de Confirmations são os cards da zona',
      sorted(k for k, _l in D.ASSIGN_CONF_PRODUCTS), sorted({c[5:] for c in cards_conf}))
check('B3 Registration sem Intrag, Intrag só Intrag',
      (any(k.startswith('intrag-') for k, _l in D.assign_products()['registration']),
       all(k.startswith('intrag-') for k, _l in D.assign_products()['intrag'])), (False, True))
modal = tpl[tpl.index('id="imAsgModal"'):tpl.index('{% endblock page_content %}')]
check('Cancel e Save sem rounded-circle, e o squircle no CSS do modal',
      ('rounded-circle' in modal,
       bool(re.search(r'#imAsgModal \.btn-icon \{[^}]*height: 32px !important[^}]*border-radius: 10px !important', tpl))),
      (False, True))
check('a coluna Produto no modal e no card', ('data-lang="im-asg-product"' in tpl, 'IM_PRODUCTS[a.product]' in tpl),
      (True, True))

print('\n== 6. o card só mostra quem tem o que fazer no dia ==')
mov = D.moving_products(
    [{'key': 'ndf-commodities', 'total': 6, 'les': [{'le': 'JPM', 'count': 4}, {'le': 'LAW', 'count': 2}]},
     {'key': 'ndf-vanilla', 'total': 16, 'les': [{'le': 'JPM', 'count': 16}, {'le': 'MGT', 'count': 0}]},
     {'key': 'opt-fxo', 'total': 2, 'les': []},
     {'key': 'ndf-fwdstart', 'total': 0, 'les': [{'le': 'JPM', 'count': 0}]},
     {'key': 'intrag-ndf', 'total': 0}],
    [{'key': 'conf-ndf-vanilla', 'total': 2}, {'key': 'conf-opt-fxo', 'total': 0}])
check('moving_products: por tarefa, o produto e as LEs que se mexeram',
      mov, {'registration': {'ndf-commodities': {'JPM', 'LAW'}, 'ndf-vanilla': {'JPM'}, 'opt-fxo': None},
            'confirmation': {'ndf-vanilla': None}, 'intrag': {}})
A = lambda task, product='', le='': {'task': task, 'product': product, 'le': le, 'owner': 'A111111', 'backup': ''}
lista = [A('registration', 'ndf-commodities'), A('registration', 'ndf-fwdstart'),
         A('registration', 'ndf-vanilla', 'JPM'), A('registration', 'ndf-vanilla', 'MGT'),
         A('registration', 'opt-fxo', 'MGT'), A('registration', '', 'LAW'), A('registration', '', 'MGT'),
         A('confirmation', 'ndf-vanilla', 'MGT'), A('confirmation', 'opt-fxo'),
         A('intrag'), A('intrag', 'intrag-ndf'), A('payrec')]
check('assignments_of_day: produto parado e LE parada saem; tarefa inteira fica se a zona se mexeu',
      [(a['task'], a['product'], a['le']) for a in D.assignments_of_day(lista, mov)],
      [('registration', 'ndf-commodities', ''), ('registration', 'ndf-vanilla', 'JPM'),
       ('registration', 'opt-fxo', 'MGT'), ('registration', '', 'LAW'), ('registration', '', 'MGT'),
       ('confirmation', 'ndf-vanilla', 'MGT'), ('payrec', '', '')])

print(('\nFAIL: %d' % len(fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
