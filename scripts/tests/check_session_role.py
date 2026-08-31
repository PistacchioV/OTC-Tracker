# -*- coding: utf-8 -*-
"""O papel do CADASTRO alcanca quem ja esta logado.

O `user_role` e gravado na sessao pelo `_set_session`, no login, e nada o relia
depois: com *Keep me signed in* a sessao dura 30 DIAS. Quem fosse promovido a
`BO` continuava sem o botao da mesa e quem fosse despromovido continuava com ele
-- e nos dois sentidos nao ha erro nenhum para ver, so uma tela se comportando
pelo papel de semanas atras. Foi assim que uma pessoa trocada de `ADMIN` para
`BO` seguiu sem conseguir validar o Pending OTC.

O `refresh_session_role` e um `before_request` proprio (e nao uma carona no
`enforce_page_access`, que desiste cedo para `/api/*` -- justamente onde a mesa
valida) e le a linha do usuario pelo MESMO cache por SID que a allowlist do
`Page_Access` ja consultava: o `Role` veio junto na query, sem ida nova ao share.

O que se prende aqui:

  1. a leitura traz as DUAS colunas, e `Role` e da tabela base -- a coluna
     `Page_Access` e que nasceu de um ALTER, entao nenhum banco que responda a
     primeira pode faltar com a segunda;
  2. `None` (banco fora do ar, SID sem linha) NAO mexe na sessao. Fail-open na
     allowlist ja existia e e aceitavel; no papel, seria rebaixar a mesa inteira
     a cada solucao do banco;
  3. `''` MEXE: papel vazio e um papel de verdade, e e assim que se revoga;
  4. MASTER nao e tocado -- nao e papel de banco, e o `_set_session` o grava por
     SID. Sobrescreve-lo com a coluna `Role` rebaixaria o superusuario;
  5. so grava quando MUDA (escrever na sessao reemite o cookie a cada request);
  6. e o efeito de ponta: a pessoa promovida a `BO` passa a validar o Pending
     OTC sem deslogar.

Nao encosta em dado real: o DuckDB e criado em tempfile.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

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
c.execute("INSERT INTO users (SID, Name, Email, Role, Status, Page_Access) "
          "VALUES ('A111111', 'Fulana', 'f@x', 'ADMIN', 'Active', '')")
c.execute("INSERT INTO users (SID, Name, Email, Role, Status, Page_Access) "
          "VALUES ('B222222', 'Sicrano', 's@x', 'MO', 'Active', "
          "'[\"/dashboard\", \"/new-deals-ndf-vanilla\"]')")
c.close()

from apps.pages import routes as R                         # noqa: E402
R.DB_PATH = DB
R.NOTIF_DB_PATH = os.path.join(TMP, 'Notifications_OTCTracker.db')
from apps.pages.platform import authz as A                 # noqa: E402
from apps import create_app                                # noqa: E402
from apps.config import DebugConfig                        # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def set_role(sid, papel):
    con = duckdb.connect(DB)
    con.execute("UPDATE users SET Role = ? WHERE SID = ?", [papel, sid])
    con.close()
    # A invalidacao cobre a escrita feita NESTE processo; o TTL de 30 s cobre a
    # instancia vizinha. Aqui o cadastro e mexido por fora, entao esquecemos a
    # mao -- o teste nao pode ficar 30 s parado esperando o relogio.
    A._page_access_forget(sid)


print('== 1. a leitura traz as duas colunas ==')
check('a linha responde papel e allowlist',
      A._read_user_authz('B222222')[0::2], (True, 'MO'))
check('   e o SID sem linha devolve None (nao "")',
      A._read_user_authz('Z999999'), (False, set(), None))
check('o papel vem NORMALIZADO em maiuscula', A._get_user_role('A111111'), 'ADMIN')
check('   e o cache devolve a mesma resposta', A._get_user_role('A111111'), 'ADMIN')
check('a allowlist antiga continua saindo por `_read_page_access`',
      A._read_page_access('B222222'), (True, {'/dashboard', '/new-deals-ndf-vanilla'}))
check('   e por `_get_page_access` (contrato de 2 itens preservado)',
      len(A._get_page_access('B222222')), 2)


print('\n== 2. o refresh na sessao ==')


def cliente(sid, papel):
    cl = app.test_client()
    with cl.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = sid
        s['user_name'] = sid
        s['user_email'] = sid + '@x'
        s['user_role'] = papel
        s['session_expires_at'] = (datetime.now() + timedelta(days=1)).isoformat()
    return cl


def papel_da_sessao(cl):
    cl.get('/users-profile')
    with cl.session_transaction() as s:
        return s.get('user_role')


# O caso que originou a mudanca: promovida no cadastro, mas a sessao antiga.
cl = cliente('A111111', 'ADMIN')
set_role('A111111', 'BO')
check('promovida no cadastro, a sessao logada acompanha', papel_da_sessao(cl), 'BO')

# E o outro sentido, que e o que importa para o controle: revogar.
set_role('A111111', '')
check('papel APAGADO tambem alcanca (revogar e o sentido que importa)',
      papel_da_sessao(cl), '')
set_role('A111111', 'BO')
check('   e volta quando o cadastro volta', papel_da_sessao(cl), 'BO')

# Falha de leitura nao pode rebaixar ninguem.
_real = A._get_user_role
try:
    A._get_user_role = lambda sid: None
    check('banco mudo NAO mexe na sessao', papel_da_sessao(cl), 'BO')
finally:
    A._get_user_role = _real

# SID sem linha no cadastro: mesma resposta, pela mesma razao.
cl_orfa = cliente('Z999999', 'FO')
check('SID sem linha no cadastro fica como esta', papel_da_sessao(cl_orfa), 'FO')

# Master e por SID e nao sai do cadastro.
_sids = A._MASTER_SIDS
try:
    A._MASTER_SIDS = {'A111111'}
    cl_master = cliente('A111111', 'MASTER')
    check('MASTER nao e rebaixado pela coluna Role', papel_da_sessao(cl_master), 'MASTER')
finally:
    A._MASTER_SIDS = _sids

# Sessao anonima nao consulta banco nenhum.
_chamadas = []
_real = A._get_user_role
try:
    A._get_user_role = lambda sid: _chamadas.append(sid)
    app.test_client().get('/users-profile')
    check('request sem sessao nao consulta o cadastro', _chamadas, [])
finally:
    A._get_user_role = _real

# So grava quando MUDA: escrever na sessao reemite o cookie a cada request.
set_role('B222222', 'MO')
cl_b = cliente('B222222', 'MO')
r = cl_b.get('/users-profile')
check('papel igual nao reemite o cookie de sessao',
      any(h[0].lower() == 'set-cookie' for h in r.headers.items()), False)
set_role('B222222', 'FO')
r = cl_b.get('/users-profile')
check('   e papel diferente reemite', 
      any(h[0].lower() == 'set-cookie' for h in r.headers.items()), True)


print('\n== 3. o efeito de ponta: a mesa volta a assinar ==')
# Sem o refresh, `_mc_can_validate` leria o papel congelado no login. Com ele,
# a troca no cadastro vale no request seguinte -- que e a pergunta que a pessoa
# fez ao trocar o papel e ver que nada mudou.
set_role('A111111', 'BO')
cl = cliente('A111111', 'ADMIN')
check('a sessao aberta como ADMIN passa a dizer BO', papel_da_sessao(cl), 'BO')
with app.test_request_context('/'):
    from flask import session as _s
    _s['user_role'] = papel_da_sessao(cl)
    check('   e `_mc_can_validate` assina o Pending OTC com ela',
          R._mc_can_validate('OTC'), True)
    check('   continuando sem assinar pelo MO', R._mc_can_validate('MO'), False)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
