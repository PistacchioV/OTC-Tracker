"""
check_session_ip.py -- a sessao so cai se o IP mudar (mesa, 24/09/2026).

Nao ha mais prazo (5 h sem "Keep me signed in", 30 dias com), nem auto-lock
por inatividade, nem o checkbox. A unica verificacao continua e o IP:

  1. login com IP igual ao cadastro entra direto, sessao permanente e sem prazo;
  2. a mesma sessao segue valendo no mesmo IP, mesmo com o prazo antigo vencido;
  3. IP diferente no meio da sessao a encerra;
  4. login com IP diferente do cadastro vai para o codigo por e-mail;
  5. sessao anterior a regra (sem `session_ip`) e carimbada, nao derrubada;
  6. o checkbox e o auto-lock sairam das telas.

Nao encosta em dado real: o DuckDB e criado em tempfile e o e-mail e stub.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

TMP = tempfile.mkdtemp()
DB = os.path.join(TMP, 'Users_OTCTracker.db')

import duckdb                                              # noqa: E402
c = duckdb.connect(DB)
c.execute("""CREATE TABLE users (
        SID VARCHAR PRIMARY KEY, Name VARCHAR, Email VARCHAR,
        Role_Description VARCHAR, Position VARCHAR, Role VARCHAR,
        Status VARCHAR, IP_Address VARCHAR, Page_Access VARCHAR DEFAULT '')""")
c.execute("INSERT INTO users (SID, Name, Email, Role, Status, IP_Address, Page_Access) "
          "VALUES ('A111111', 'Fulana', 'f@x', 'ADMIN', 'Active', '10.0.0.1', '')")
c.close()

from apps.pages import routes as R                         # noqa: E402
R.DB_PATH = DB
R.NOTIF_DB_PATH = os.path.join(TMP, 'Notifications_OTCTracker.db')
from apps import create_app                                # noqa: E402
from apps.config import DebugConfig                        # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

enviados = []
R._initiate_2fa = lambda sid, email, name: (enviados.append(sid), R.redirect('/auth-2-two-factor'))[1]

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def sessao(cl):
    with cl.session_transaction() as s:
        return dict(s)


print('== 1. login com o IP do cadastro ==')
cl = app.test_client()
r = cl.post('/login', data={'sid': 'A111111'}, environ_base={'REMOTE_ADDR': '10.0.0.1'})
s = sessao(cl)
check('entra direto (vai ao dashboard)', r.status_code == 302 and '/dashboard' in r.location, True)
check('   sessao autenticada', s.get('authenticated'), True)
check('   carimbada com o IP', s.get('session_ip'), '10.0.0.1')
check('   sem prazo gravado', 'session_expires_at' in s, False)
check('   sem remember_me', 'remember_me' in s, False)
check('   sessao permanente', s.get('_permanent'), True)
check('nenhum codigo enviado', enviados, [])

print('\n== 2. mesma sessao, mesmo IP ==')
with cl.session_transaction() as sx:
    # o prazo antigo, vencido: nao pode mais derrubar ninguem
    sx['session_expires_at'] = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
cl.get('/users-profile', environ_base={'REMOTE_ADDR': '10.0.0.1'})
check('segue logada com o prazo antigo vencido', sessao(cl).get('authenticated'), True)

print('\n== 3. o IP muda no meio da sessao ==')
cl.get('/users-profile', environ_base={'REMOTE_ADDR': '10.0.0.2'})
check('a sessao e encerrada', sessao(cl).get('authenticated'), None)

print('\n== 4. login com IP diferente do cadastro ==')
cl2 = app.test_client()
r = cl2.post('/login', data={'sid': 'A111111'}, environ_base={'REMOTE_ADDR': '10.0.0.9'})
check('vai para o codigo por e-mail', enviados, ['A111111'])
check('   sem sessao autenticada ainda', sessao(cl2).get('authenticated'), None)
check('   IP novo so pendente', sessao(cl2).get('pending_ip'), '10.0.0.9')

print('\n== 5. sessao anterior a regra ==')
cl3 = app.test_client()
with cl3.session_transaction() as sx:
    sx.update(authenticated=True, user_sid='A111111', user_name='Fulana',
              user_email='f@x', user_role='ADMIN')
cl3.get('/users-profile', environ_base={'REMOTE_ADDR': '10.0.0.1'})
s = sessao(cl3)
check('nao e derrubada', s.get('authenticated'), True)
check('   e ganha o carimbo do IP', s.get('session_ip'), '10.0.0.1')

print('\n== 6. as telas ==')
signin = open(os.path.join(ROOT, 'apps/templates/pages/auth-2-sign-in.html'), encoding='utf-8').read()
topbar = open(os.path.join(ROOT, 'apps/templates/partials/topbar.html'), encoding='utf-8').read()
check('sign-in sem o "Keep me signed in"', 'remember_me' in signin or 'auth-keep-signed' in signin, False)
check('topbar sem o auto-lock por inatividade', 'otc_last_activity' in topbar, False)
check('o Lock Screen manual continua no menu', 'href="/lock"' in topbar, True)

print('\n%s' % ('FAIL: %d' % len(fails) if fails else 'OK'))
sys.exit(1 if fails else 0)
