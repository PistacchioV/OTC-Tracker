"""notifications.target_sid contra o DuckDB de verdade (copia em tmp).

Cobre a migracao (ALTER numa tabela que ja existia SEM a coluna), o filtro do
feed e a compatibilidade: notificacao antiga, com target_sid NULL, tem de
continuar visivel para todo mundo.
"""
import os, shutil, sys, tempfile
from datetime import datetime, timedelta

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))   # scripts/tests/ -> raiz do repo
sys.path.insert(0, ROOT)
os.chdir(ROOT)

TMP = tempfile.mkdtemp()
DB = os.path.join(TMP, 'Users_OTCTracker.db')

# Cria o banco com o schema ANTIGO (sem target_sid) para exercitar a migracao.
import duckdb                                            # noqa: E402
c = duckdb.connect(DB)
c.execute("CREATE SEQUENCE IF NOT EXISTS seq_notif_id START 1")
c.execute("""
    CREATE TABLE notifications (
        id          INTEGER DEFAULT nextval('seq_notif_id') PRIMARY KEY,
        actor_sid   VARCHAR NOT NULL DEFAULT '',
        actor_name  VARCHAR NOT NULL DEFAULT '',
        action      VARCHAR NOT NULL DEFAULT '',
        page        VARCHAR NOT NULL DEFAULT '',
        detail      VARCHAR DEFAULT '',
        target_role VARCHAR DEFAULT '',
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
c.execute("""CREATE TABLE users (
        SID VARCHAR PRIMARY KEY, Name VARCHAR, Email VARCHAR,
        Role_Description VARCHAR, Position VARCHAR, Role VARCHAR,
        Status VARCHAR, IP_Address VARCHAR, Page_Access VARCHAR DEFAULT '')""")
# Uma notificacao ANTIGA, gravada antes da coluna existir.
c.execute("INSERT INTO notifications (actor_sid, action, page, detail) "
          "VALUES ('X000000', 'Legacy', 'Users', 'antes da migracao')")
c.close()

from apps.pages import routes as R                        # noqa: E402
R.DB_PATH = DB
from apps import create_app                               # noqa: E402
from apps.config import DebugConfig                       # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

fails = []
def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)

def client_for(sid, role):
    cl = app.test_client()
    with cl.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = sid
        s['user_name'] = sid
        s['user_role'] = role
        s['user_email'] = sid + '@x'
        s['session_expires_at'] = (datetime.now() + timedelta(days=1)).isoformat()
    return cl

master = client_for('E930179', 'MASTER')
alice  = client_for('A111111', 'BO')
bob    = client_for('B222222', 'BO')

def feed(cl):
    d = cl.get('/api/notifications').get_json() or {}
    return [(n['action'], n['detail']) for n in d.get('notifications', [])]

print('\n== 1. a migracao adiciona target_sid numa tabela existente ==')
with app.app_context():
    conn = R.get_db_connection()
    try:
        cols = [x[0] for x in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='notifications'").fetchall()]
    finally:
        conn.close()
check('coluna criada', 'target_sid' in cols, True)

print('\n== 2. notificacao legada (target_sid NULL) continua visivel ==')
check('master ve a legada', ('Legacy', 'antes da migracao') in feed(master), True)
check('alice ve a legada', ('Legacy', 'antes da migracao') in feed(alice), True)

print('\n== 3. target_sid isola para UM usuario ==')
with app.app_context():
    R._create_notification('E930179', 'Master', 'Ticket Updated', 'Support',
                           'so para alice', target_sid='A111111')
check('alice ve', ('Ticket Updated', 'so para alice') in feed(alice), True)
check('bob NAO ve', ('Ticket Updated', 'so para alice') in feed(bob), False)
check('master NAO ve (nem ele burla)', ('Ticket Updated', 'so para alice') in feed(master), False)

print('\n== 4. target_role=MASTER isola para o master ==')
with app.app_context():
    R._create_notification('A111111', 'Alice', 'New Ticket', 'Support',
                           'so para o master', target_role='MASTER')
check('master ve', ('New Ticket', 'so para o master') in feed(master), True)
check('alice NAO ve', ('New Ticket', 'so para o master') in feed(alice), False)
check('bob NAO ve', ('New Ticket', 'so para o master') in feed(bob), False)

print('\n== 5. sem alvo = todo mundo ==')
with app.app_context():
    R._create_notification('E930179', 'Master', 'Broadcast', 'Users', 'para todos')
for who, cl in (('master', master), ('alice', alice), ('bob', bob)):
    check('%s ve o broadcast' % who, ('Broadcast', 'para todos') in feed(cl), True)

print('\n== 6. o SID e normalizado (case-insensitive) ==')
with app.app_context():
    R._create_notification('E930179', 'Master', 'Ticket Updated', 'Support',
                           'sid minusculo', target_sid='a111111')
check('alice ve mesmo com sid minusculo',
      ('Ticket Updated', 'sid minusculo') in feed(alice), True)
check('bob continua sem ver', ('Ticket Updated', 'sid minusculo') in feed(bob), False)

shutil.rmtree(TMP, ignore_errors=True)
print('\n%s' % ('TUDO OK' if not fails else 'FALHAS: %r' % fails))
sys.exit(1 if fails else 0)
