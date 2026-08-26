"""O caminho de LEITURA do banco de usuarios, e o cache da allowlist.

Protege o que fez a instancia do JPM levar minutos para desenhar uma tela com o
banco no share: toda consulta ao DuckDB de usuarios abria uma transacao de
ESCRITA — semaforo de UMA permissao no processo e lock de arquivo EXCLUSIVO
entre processos. O sino da topbar, que consulta por aba aberta, consumia sozinho
essa fila e a pagina pedida esperava atras dela. Ninguem falhava; todo mundo
esperava, e nao havia erro no log.

Cobre tres garantias:
  1. quem so faz SELECT abre em modo COMPARTILHADO;
  2. a allowlist nao vai ao banco em toda navegacao (cache por SID);
  3. e a revogacao feita NESTE processo vale na hora, sem esperar o TTL.
"""
import contextlib
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

TMP = tempfile.mkdtemp(prefix='db-read-path-')
DB = os.path.join(TMP, 'Users_OTCTracker.db')

import duckdb                                             # noqa: E402
c = duckdb.connect(DB)
c.execute("CREATE SEQUENCE IF NOT EXISTS seq_notif_id START 1")
c.execute("""CREATE TABLE notifications (
        id          INTEGER DEFAULT nextval('seq_notif_id') PRIMARY KEY,
        actor_sid   VARCHAR NOT NULL DEFAULT '',
        actor_name  VARCHAR NOT NULL DEFAULT '',
        action      VARCHAR NOT NULL DEFAULT '',
        page        VARCHAR NOT NULL DEFAULT '',
        detail      VARCHAR DEFAULT '',
        target_role VARCHAR DEFAULT '',
        target_sid  VARCHAR DEFAULT '',
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
c.execute("""CREATE TABLE users (
        SID VARCHAR PRIMARY KEY, Name VARCHAR, Email VARCHAR,
        Role_Description VARCHAR, Position VARCHAR, Role VARCHAR,
        Status VARCHAR, IP_Address VARCHAR, Page_Access VARCHAR DEFAULT '')""")
c.execute("INSERT INTO users (SID, Name, Email, Role, Status, Page_Access) "
          "VALUES ('A111111', 'Alice', 'a@x', 'BO', 'Approved', ?)",
          ['["/dashboard", "/reference-data"]'])
c.close()

from apps.pages import database_access as DA              # noqa: E402
from apps.pages import routes as R                        # noqa: E402
R.DB_PATH = DB

# Espiao no contexto de banco: registra o MODO de cada operacao.
ops = []
_real_ctx = DA._database_context


@contextlib.contextmanager
def _spy(path, *, engine, write, operation_id=None, skip_file_lock=False):
    # `skip_file_lock` e o caminho do sino (leitura sem o lock entre processos).
    # O espiao tem de aceita-lo e REPASSA-LO: engolindo o parametro, o teste
    # exercitaria um caminho que a aplicacao nao usa.
    with _real_ctx(path, engine=engine, write=write, operation_id=operation_id,
                   skip_file_lock=skip_file_lock) as conn:
        ops.append(('unlocked ' if skip_file_lock else '') + ('write' if write else 'read'))
        yield conn


DA._database_context = _spy
R.duckdb_write = lambda p, **k: _spy(p, engine='duckdb', write=True, **k)
R.duckdb_read = lambda p, **k: _spy(p, engine='duckdb', write=False, **k)
R.duckdb_read_unlocked = lambda p, **k: _spy(p, engine='duckdb', write=False,
                                             skip_file_lock=True, **k)

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


alice = client_for('A111111', 'BO')
alice.get('/api/notifications')                 # aquece o init preguicoso do schema

print('== 1. o sino nao toma mais a fila de escrita ==')
ops[:] = []
alice.get('/api/notifications')
check('uma operacao por consulta', len(ops), 1)
# Nem compartilhada: o sino le SEM LOCK. Ele e a consulta mais repetida do app
# (uma por aba a cada poucos segundos) e e de MELHOR ESFORCO — a que falha ja
# devolve o sino vazio, e o poll seguinte corrige. Assim ela nao espera nem por
# uma gravacao de notificacao em curso. E o unico ponto do app autorizado a
# isso; quem vigia e o `check_unlocked_reads.py`.
check('e ela nem toma o lock compartilhado', ops, ['unlocked read'])

print('\n== 2. a allowlist nao vai ao banco em toda navegacao ==')
R._page_access_forget()
ops[:] = []
check('a primeira leitura consulta', R._get_page_access('A111111')[1],
      {'/dashboard', '/reference-data'})
primeira = len(ops)
for _ in range(20):
    R._get_page_access('A111111')
check('a primeira foi uma so', primeira, 1)
check('e as 20 seguintes, nenhuma', len(ops) - primeira, 0)

print('\n== 3. o cache devolve COPIA, nao o proprio conjunto ==')
_, urls = R._get_page_access('A111111')
urls.add('/control-panel')
check('mexer no retorno nao concede acesso',
      '/control-panel' in R._get_page_access('A111111')[1], False)

print('\n== 4. revogar vale na hora, sem esperar o TTL ==')
R._get_page_access('A111111')                   # deixa em cache
R._set_page_access('A111111', ['/dashboard'])
check('a allowlist nova ja vale', R._get_page_access('A111111')[1], {'/dashboard'})
check('e a pagina revogada redireciona',
      alice.get('/reference-data').status_code, 302)

print('\n== 5. apagar o usuario tambem esquece ==')
R._get_page_access('A111111')
R._page_access_forget('A111111')
ops[:] = []
R._get_page_access('A111111')
check('volta a consultar o banco', len(ops), 1)

shutil.rmtree(TMP, ignore_errors=True)
print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
