# -*- coding: utf-8 -*-
"""O registro Counterparty Details (contatos/CGD/banking/net) ponta a ponta.

Cada item entra `Pending` com o MAKER carimbado; quem aprova nao pode ser quem
fez (403 `same_user`); o approve vira `Active` com o checker; o EDIT devolve o
item para Pending e LIMPA o checker — editar depois de aprovado exige nova
aprovacao. SPN sem registro e criado na primeira gravacao (CGD/CONTACTS/
BANKING/NET normalizados).
"""
import io, json, os, sys, tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

TMP = tempfile.mkdtemp()

from apps.pages import routes as R                          # noqa: E402
from apps import create_app                                 # noqa: E402
from apps.config import DebugConfig                         # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

# O arquivo do registro vai para o tmp — `_cpd_path` e plataforma (leitores nos
# summaries/advices) e continua no routes, entao o patch sobrevive a extracao.
CPD_FILE = os.path.join(TMP, 'CounterpartyDetails.json')
io.open(CPD_FILE, 'w', encoding='utf-8').write('[]')
# O armazém mora em platform/counterparty.py (§316): o `_cpd_load` chama o
# `_cpd_path` por DENTRO do módulo, então o stub entra nos dois lugares —
# o alias do routes cobre quem chega de fora.
from apps.pages.platform import counterparty as PCD
R._cpd_path = PCD._cpd_path = lambda: CPD_FILE
NOTIFS = []
R._create_notification = lambda sid, nome, acao, pagina, msg='': NOTIFS.append((acao, pagina))

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def cliente(sid):
    c = app.test_client()
    with c.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = sid
        s['user_name'] = sid
        s['user_role'] = 'BO'
        s['user_email'] = sid + '@x'
        s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    return c


maker, checker, anon = cliente('A111111'), cliente('B222222'), app.test_client()

print('== 1. sem sessao ==')
check('contact/add -> 401',
      anon.post('/api/counterparty-details/contact/add').status_code, 401)
check('banking/account/add -> 401',
      anon.post('/api/counterparty-details/banking/account/add').status_code, 401)

print('\n== 2. o contato entra Pending com o maker ==')
r = maker.post('/api/counterparty-details/contact/add', json={'SPN': '100'})
check('contato vazio e 400', (r.status_code, r.get_json()['error']), (400, 'empty_contact'))
r = maker.post('/api/counterparty-details/contact/add',
               json={'name': 'Fulano', 'email': 'f@x.com'})
check('sem SPN e 400', (r.status_code, r.get_json()['error']), (400, 'missing_spn'))
r = maker.post('/api/counterparty-details/contact/add',
               json={'SPN': '100', 'name': 'Fulano', 'email': 'f@x.com',
                     'rules': ['Confirmation']})
item = r.get_json()['item']
check('entra Pending com maker e sem checker',
      (r.status_code, item['appr'], item['maker'], item['checker']),
      (200, 'Pending', 'A111111', ''))
dados = json.load(io.open(CPD_FILE, encoding='utf-8'))
check('   o SPN novo nasce com as quatro secoes',
      sorted(k for k in dados[0] if k in ('CGD', 'CONTACTS', 'BANKING', 'NET')),
      ['BANKING', 'CGD', 'CONTACTS', 'NET'])

print('\n== 3. quatro olhos ==')
iid = item['id']
r = maker.post('/api/counterparty-details/contact/approve', json={'SPN': '100', 'id': iid})
check('o maker nao aprova (403 same_user)',
      (r.status_code, r.get_json()['error']), (403, 'same_user'))
r = checker.post('/api/counterparty-details/contact/approve', json={'SPN': '100', 'id': iid})
it = r.get_json()['item']
check('outro usuario aprova (Active + checker)',
      (r.status_code, it['appr'], it['checker']), (200, 'Active', 'B222222'))

print('\n== 4. editar devolve para Pending e limpa o checker ==')
r = checker.post('/api/counterparty-details/contact/edit',
                 json={'SPN': '100', 'id': iid, 'name': 'Fulano II', 'email': 'f@x.com'})
it = r.get_json()['item']
check('Pending de novo, maker = quem editou, checker limpo',
      (it['appr'], it['maker'], it['checker']), ('Pending', 'B222222', ''))
r = checker.post('/api/counterparty-details/contact/edit',
                 json={'SPN': '100', 'id': 'nao-existe', 'name': 'X'})
check('id inexistente e 404', r.status_code, 404)

print('\n== 5. a conta bancaria segue o mesmo ciclo ==')
r = maker.post('/api/counterparty-details/banking/account/add',
               json={'SPN': '100', 'bank': 'Itau', 'agency': '1', 'account': '2'})
acc = r.get_json()['account']
check('conta entra Pending', (r.status_code, acc['status'], acc['maker']),
      (200, 'Pending', 'A111111'))
r = maker.post('/api/counterparty-details/banking/account/add', json={'SPN': '100'})
check('   conta vazia e 400', (r.status_code, r.get_json()['error']), (400, 'empty_account'))

print('\n== 6. delete tira o item ==')
r = checker.post('/api/counterparty-details/contact/delete', json={'SPN': '100', 'id': iid})
check('200', r.status_code, 200)
dados = json.load(io.open(CPD_FILE, encoding='utf-8'))
check('   e o contato sumiu do arquivo', dados[0]['CONTACTS'], [])
check('   toda acao avisou no sino (Reference Data)',
      all(p == 'Reference Data' for _, p in NOTIFS), True)

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
