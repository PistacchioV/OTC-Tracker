# -*- coding: utf-8 -*-
"""Acesso TOTAL no /page-access vale para a página que nasce DEPOIS.

O toggle "Full access" marcava todas as caixas e o Save gravava a LISTA daquele
dia; a página que entrava no menu depois não estava nela, e quem tinha acesso
total perdia a tela nova sem ninguém ter mexido — admin, master ou não (pedido
da equipe, 26/10/2026). Agora a lista que cobre tudo vira o marcador `["*"]`,
que a leitura expande para as páginas controláveis do momento.

O que se prende aqui:

  1. Save com todas as páginas grava o marcador, não a lista;
  2. a página NOVA (que entrou no menu depois do Save) já vale para ele;
  3. Save com uma página a menos continua sendo uma lista — e a página nova
     NÃO entra para ele;
  4. quem já tinha todas as páginas é convertido pela subida
     (`page_access_upgrade_full`), uma vez, e quem não tinha fica como está;
  5. sem a lista de páginas (o sidenav não leu) nada vira acesso total;
  6. a API GET devolve todas as páginas (o toggle aparece ligado).

Não encosta em dado real: o DuckDB é criado em tempfile.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

TMP = tempfile.mkdtemp()
DB = os.path.join(TMP, 'Users_OTCTracker.db')

import duckdb                                              # noqa: E402
c = duckdb.connect(DB)
c.execute("""CREATE TABLE users (
        SID VARCHAR PRIMARY KEY, Name VARCHAR, Email VARCHAR,
        Role_Description VARCHAR, Position VARCHAR, Role VARCHAR,
        Status VARCHAR, IP_Address VARCHAR, Page_Access VARCHAR DEFAULT '')""")
for sid, role in (('A111111', 'BO'), ('B222222', 'MO'), ('C333333', 'FO'), ('D444444', 'BO')):
    c.execute("INSERT INTO users (SID, Name, Email, Role, Status, Page_Access) "
              "VALUES (?, ?, 'x@x', ?, 'Active', '')", [sid, sid, role])
c.close()

from apps.pages import routes as R                         # noqa: E402
R.DB_PATH = DB
R.NOTIF_DB_PATH = os.path.join(TMP, 'Notifications_OTCTracker.db')
from apps.pages.platform import authz as A                 # noqa: E402

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def gravado(sid):
    con = duckdb.connect(DB, read_only=True)
    try:
        return con.execute("SELECT Page_Access FROM users WHERE SID = ?", [sid]).fetchone()[0]
    finally:
        con.close()


def grava_cru(sid, urls):
    con = duckdb.connect(DB)
    con.execute("UPDATE users SET Page_Access = ? WHERE SID = ?", [json.dumps(sorted(urls)), sid])
    con.close()
    A._page_access_forget(sid)


TODAS = A._controllable_urls()
check('há páginas controláveis (o sidenav foi lido)', len(TODAS) > 10)
uma = sorted(TODAS)[0]

print('== 1. Save com todas as páginas grava o marcador ==')
A._set_page_access('A111111', sorted(TODAS))
check('gravado como ["*"]', json.loads(gravado('A111111')), ['*'])
conf, urls = A._read_page_access('A111111')
check('a leitura expande para todas', (conf, urls == TODAS), (True, True))

print('== 2. a página NOVA já vale para o acesso total ==')
A._set_page_access('B222222', sorted(TODAS - {uma}))
NOVA = '/pagina-nova-de-teste'
_orig_nav = A._NAV_URLS
A._NAV_URLS = set(_orig_nav) | {NOVA}
try:
    A._page_access_forget()
    check('quem tem acesso total ganha a página nova', NOVA in A._read_page_access('A111111')[1])

    print('== 3. a lista com uma a menos continua lista ==')
    check('gravado como lista', '*' not in json.loads(gravado('B222222')))
    check('e a página nova NÃO entra para ele', NOVA in A._read_page_access('B222222')[1], False)
finally:
    A._NAV_URLS = _orig_nav
    A._page_access_forget()

print('== 4. a subida converte quem já tinha tudo ==')
grava_cru('C333333', TODAS)                      # gravado antes desta mudança: a lista inteira
grava_cru('D444444', TODAS - {uma})
convertidos = A.page_access_upgrade_full()
check('converte só quem tinha todas', convertidos, ['C333333'])
check('C333333 agora é ["*"]', json.loads(gravado('C333333')), ['*'])
check('D444444 continua lista', '*' not in json.loads(gravado('D444444')))
check('segunda passada não faz nada (idempotente)', A.page_access_upgrade_full(), [])

print('== 5. sem a lista de páginas nada vira acesso total ==')
_orig_nav, _orig_cp = A._NAV_URLS, A._CP_CARD_TOKENS
A._NAV_URLS, A._CP_CARD_TOKENS = set(), set()
try:
    A._set_page_access('D444444', [uma])
    check('gravado como a lista pedida', json.loads(gravado('D444444')), [uma])
    check('e a conversão não converte ninguém', A.page_access_upgrade_full(), [])
finally:
    A._NAV_URLS, A._CP_CARD_TOKENS = _orig_nav, _orig_cp
    A._page_access_forget()

print('== 6. a API devolve todas as páginas para o acesso total ==')
from apps import create_app                                # noqa: E402
from apps.config import DebugConfig                        # noqa: E402
app = create_app(DebugConfig)
app.config['TESTING'] = True
cl = app.test_client()
with cl.session_transaction() as s:
    s.update(authenticated=True, user_sid='E930179', user_name='M', user_role='MASTER',
             session_ip='127.0.0.1')
r = cl.get('/api/page-access/A111111')
d = r.get_json() or {}
check('GET 200, configurado', (r.status_code, d.get('configured')), (200, True))
check('com todas as páginas (o toggle aparece ligado)', set(d.get('pages') or []) == TODAS)
r = cl.post('/api/page-access/B222222', json={'pages': sorted(TODAS)})
check('POST com todas → marcador', (r.status_code, json.loads(gravado('B222222'))), (200, ['*']))

print()
if fails:
    print('%d FALHA(S)' % len(fails))
    sys.exit(1)
print('TUDO OK')
