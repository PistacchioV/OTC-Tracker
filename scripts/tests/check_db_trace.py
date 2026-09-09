"""O rastro de banco POR REQUEST, e o que ele deixou visível (09/09/2026).

Um Summary que levava minutos na instância aparecia no log como dezenas de
`file_lock_held_slow` de bancos identificados por hash, sem dizer QUE request
os pediu — e o request que não terminava não aparecia em lugar nenhum, porque
o `[slow-request]` só sai no teardown. A pergunta "está carregando ou está
parado?" não tinha resposta no log.

Cobre:
  1. `database_access.DbTrace`: toda operação da camada dentro de um
     `trace_begin`/`trace_end` entra no rastro com o NOME do banco (não o
     hash), o modo e os segundos; fora do rastro nada é gravado; o timeout de
     lock entra como categoria `lock_timeout`; as anotações do `duck_read`
     (queda para o JSON, cura) aparecem no resumo;
  2. `traces_in_flight` vê o rastro enquanto ele está aberto e não depois — é
     o que o laço `slow-request-watch` lê para logar o request ainda em voo;
  3. a linha `[slow-request]` do routes carrega o resumo do rastro;
  4. o lock de arquivo do claim diário é NON_BLOCKING — sem isso o `timeout=15`
     do portalocker não vale nada ("timeout has no effect in blocking mode") e
     a thread do scheduler esperava sem teto pela instância vizinha;
  5. `_latam_all_dates` é memoizada por processo (TTL) e esquecida pelo
     `_latam_save`: era um `os.walk` da raiz inteira do OTM a cada chamada;
  6. os dois laços novos estão REGISTRADOS (`slow-request-watch`,
     `summary-warm`), então sobem com o app e respeitam o kill-switch.
"""
import contextlib
import logging
import os
import shutil
import sys
import tempfile
import warnings
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

os.environ['OTC_DISABLE_SCHEDULERS'] = '1'
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='db-trace-share-'))

TMP = tempfile.mkdtemp(prefix='db-trace-')
DB = os.path.join(TMP, 'rastro', 'Vanilla.db')
os.makedirs(os.path.dirname(DB))

import duckdb                                             # noqa: E402
_c = duckdb.connect(DB)
_c.execute('CREATE TABLE t (a INTEGER)')
_c.execute('INSERT INTO t VALUES (1)')
_c.close()

from apps.pages import database_access as DA              # noqa: E402
from apps.pages.database_access import duckdb_read        # noqa: E402

FAILS = 0


def check(cond, msg):
    global FAILS
    print(('ok    ' if cond else 'FAIL  ') + msg)
    if not cond:
        FAILS += 1


# ── 1. o rastro registra a operação com o nome do banco ─────────────────────
print('\n§1 DbTrace')
check(DA.trace_current() is None, 'fora de um rastro, trace_current() é None')
tr = DA.trace_begin('teste')
with duckdb_read(DB) as con:
    con.execute('SELECT * FROM t').fetchall()
DA.trace_end(tr)
check(len(tr.ops) == 1, 'uma leitura dentro do rastro é UMA operação (%d)' % len(tr.ops))
nome, modo, seg, cat = tr.ops[0] if tr.ops else ('', '', 0, '')
check(nome == 'rastro/Vanilla.db', 'o banco entra pelos dois últimos segmentos do caminho (%r)' % nome)
check(modo == 'read' and cat == 'completed' and seg >= 0,
      'modo, categoria e segundos (%s, %s, %.3f)' % (modo, cat, seg))
resumo = tr.summary()
check('1 abertura(s) de banco em' in resumo and 'rastro/Vanilla.db read' in resumo,
      'o resumo nomeia o banco: %s' % resumo)
check(DA.trace_current() is None, 'trace_end limpa a thread')

# fora do rastro, nada
with duckdb_read(DB) as con:
    con.execute('SELECT 1').fetchall()
check(len(tr.ops) == 1, 'leitura FORA do rastro não entra no rastro encerrado')

# anotações do duck_read
tr3 = DA.trace_begin('notas')
DA.trace_note('json', 'OtherPublisher.db')
DA.trace_note('cura', 'Vanilla.db')
DA.trace_end(tr3)
r3 = tr3.summary()
check('1 leitura(s) servida(s) pelo JSON' in r3 and '1 cura(s) sincrona(s)' in r3,
      'queda para o JSON e cura aparecem no resumo: %s' % r3)
check(DA.DbTrace('vazio').summary() == 'nenhuma abertura de banco',
      'rastro sem operação diz que não abriu banco')

# timeout de lock entra como categoria
held = DA.hold_file_lock(DB, write=True)
tr4 = DA.trace_begin('lock')
estourou = False
try:
    with DA.read_timeout(0.3), duckdb_read(DB) as con:
        con.execute('SELECT 1').fetchall()
except DA.DatabaseLockTimeout:
    estourou = True
finally:
    DA.trace_end(tr4)
    held.release()
check(estourou, 'leitura com a trava exclusiva tomada estoura o teto curto')
check(any(c == 'lock_timeout' for *_r, c in tr4.ops), 'o timeout entra no rastro como lock_timeout')
check('espera(s) de lock estourada(s)' in tr4.summary(), 'e o resumo conta a espera: %s' % tr4.summary())

# ── 2. em voo ───────────────────────────────────────────────────────────────
print('\n§2 traces_in_flight')
tr5 = DA.trace_begin('voo')
check(tr5 in DA.traces_in_flight(0.0), 'o rastro aberto está entre os em voo')
check(tr5 not in DA.traces_in_flight(3600.0), 'o filtro de idade mínima o exclui')
DA.trace_end(tr5)
check(tr5 not in DA.traces_in_flight(0.0), 'encerrado, sai da lista')

# ── 3. a linha do slow-request carrega o resumo ─────────────────────────────
print('\n§3 [slow-request]')
from apps.pages import routes as R                        # noqa: E402
from apps import create_app                               # noqa: E402
from apps.config import DebugConfig                       # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True


class _Captura(logging.Handler):
    def __init__(self):
        super().__init__()
        self.linhas = []

    def emit(self, record):
        self.linhas.append(record.getMessage())


cap = _Captura()
R.log.addHandler(cap)
teto_antes = R._SLOW_REQUEST_SECONDS
R._SLOW_REQUEST_SECONDS = 1e-9
try:
    # Sem `with`: o test client em `with` preserva o contexto e dispara o
    # teardown DUAS vezes — artefato do cliente de teste, não do app.
    app.test_client().get('/sign-in')
finally:
    R._SLOW_REQUEST_SECONDS = teto_antes
    R.log.removeHandler(cap)
lentas = [l for l in cap.linhas if l.startswith('[slow-request]')]
check(len(lentas) == 1, 'um request lento gera UMA linha [slow-request] (%d)' % len(lentas))
check(lentas and ' — ' in lentas[0] and ('abertura' in lentas[0]),
      'a linha traz o resumo do rastro: %s' % (lentas[0] if lentas else ''))
check(DA.traces_in_flight(0.0) == [], 'o teardown encerra o rastro do request')

# ── 4. o lock do claim é NON_BLOCKING ───────────────────────────────────────
print('\n§4 claim lock')
from apps.pages.platform import json_cache as JC          # noqa: E402

src = open(os.path.join(ROOT, 'apps', 'pages', 'platform', 'json_cache.py'), encoding='utf-8').read()
chamadas = src.count('portalocker.Lock(')
check(chamadas == 2, 'json_cache tem os dois locks de claim (%d)' % chamadas)
check(src.count('portalocker.LockFlags.NON_BLOCKING') == 2,
      'os dois levam NON_BLOCKING — sem ele o timeout=15 não vale')
claim_dir = os.path.join(TMP, 'claims')
claim_file = os.path.join(claim_dir, 'teste.json')
with warnings.catch_warnings(record=True) as avisos:
    warnings.simplefilter('always')
    ok1 = JC._claim_daily_slot(claim_file, claim_dir, 'slot-a', 5, 'teste')
    ok2 = JC._claim_daily_slot(claim_file, claim_dir, 'slot-a', 5, 'teste')
check(ok1 is True and ok2 is False, 'o claim reserva uma vez e recusa a segunda')
check(not any('timeout has no effect' in str(a.message) for a in avisos),
      'o portalocker não avisa que o timeout é ignorado')

# ── 5. _latam_all_dates memoizada ───────────────────────────────────────────
print('\n§5 _latam_all_dates')
latam_root = os.path.join(TMP, 'otm')
R.LATAM_JSON_ROOT = latam_root
os.makedirs(os.path.join(latam_root, '2026', '09', '01'))
with open(os.path.join(latam_root, '2026', '09', '01', 'latam-desk-position_20260901.json'),
          'w', encoding='utf-8') as fh:
    fh.write('[]')
varreduras = {'n': 0}
_day_files_real = R._day_files


def _spy(*a, **k):
    varreduras['n'] += 1
    return _day_files_real(*a, **k)


R._day_files = _spy
R._latam_dates_forget()
d1 = R._latam_all_dates()
d2 = R._latam_all_dates()
check(d1 == [datetime(2026, 9, 1)] and d2 == d1, 'a lista sai da árvore: %s' % d1)
check(varreduras['n'] == 1, 'duas chamadas, UMA varredura (%d)' % varreduras['n'])
jp2 = os.path.join(latam_root, '2026', '09', '02', 'latam-desk-position_20260902.json')
with contextlib.suppress(Exception):
    R._latam_save(jp2, [])
d3 = R._latam_all_dates()
check(d3 and d3[0] == datetime(2026, 9, 2), 'o import local esquece o memo: a data nova lidera %s' % d3)
check(varreduras['n'] == 2, 'e custou UMA varredura a mais (%d)' % varreduras['n'])
R._day_files = _day_files_real

# ── 6. os laços novos estão registrados ─────────────────────────────────────
print('\n§6 registro dos laços')
rotulos = [l for l, _f in R._SCHEDULERS]
check('slow-request-watch' in rotulos, 'slow-request-watch sobe com o app')
check('summary-warm' in rotulos, 'summary-warm sobe com o app')
check(R._SUMMARY_WARM_MINUTES == 30.0, 'o aquecimento roda a cada 30 min por padrão')
check(callable(getattr(R, '_summary_warm_once', None)), '_summary_warm_once existe')

shutil.rmtree(TMP, ignore_errors=True)
print('\n%s' % ('ALL OK' if not FAILS else '%d FAIL' % FAILS))
sys.exit(1 if FAILS else 0)
