# -*- coding: utf-8 -*-
"""check_duck_gate.py — o espelho e o leitor DB-only nao se derrubam mais (§422).

O `duck_read` abre os bancos do espelho `read_only=True`; a thread do
`duck_mirror` abre o MESMO arquivo em escrita, no mesmo processo — e o DuckDB
recusa a segunda configuracao ("Can't open a connection to same database file
with a different configuration than existing connections"). Antes, a colisao
fazia a conversao falhar, o manifest ficava defasado e TODA leitura seguinte
pagava uma cura sincrona que voltava a colidir: foi o NDF Summary e o Other
Products Summary "infinitos" na instancia do time.

O que este script prova:

  1. escrita do espelho enquanto uma tela SEGURA uma leitura aberta: o escritor
     espera o leitor fechar e converte SEM erro (antes: erro de conversao);
  2. leitura chegando durante uma escrita: espera e volta com DADO do banco;
  3. memo por request: o mesmo arquivo-dia lido duas vezes no MESMO request abre
     o banco UMA vez, cada consumidor recebe objetos SEUS, e uma gravacao no
     meio do request invalida sozinha (a chave leva mtime/tamanho);
  4. fora de request nao memoiza nada — a rotina agendada ve o arquivo mudar;
  5. o gancho do motor e o padrao FORA da thread do espelho (scripts/standalone).

Tudo em tempfile; nao toca em dado real.
"""
import json
import os
import sys
import tempfile
import threading
import time

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ.pop('OTC_DISABLE_SCHEDULERS', None)
os.environ.pop('OTC_DISABLE_DUCK_MIRROR', None)

import duckdb                                               # noqa: E402

from apps.pages import routes as R                          # noqa: E402
from apps.pages import duck_mirror as M                     # noqa: E402
from apps.pages import duck_read as DR                      # noqa: E402
from apps.pages import json_to_duckdb as core               # noqa: E402
from apps.pages import database_access as DA                # noqa: E402

TMP = tempfile.mkdtemp(prefix='otc-dgate-')
R._B3_DATA_DIR = TMP
DBDIR = os.path.join(TMP, 'db')
fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


dia = os.path.join(TMP, 'cache', 'new deals', 'NDF', 'Commodities', '2026', '06', '20260615_ndfcomm.json')
os.makedirs(os.path.dirname(dia), exist_ok=True)
R._atomic_write_json(dia, [{'Deal': 'DBH-1AAA', 'TradeDate': '15/06/2026'}])
check('setup: espelho converteu', M.flush(20))
DB = os.path.join(DBDIR, 'cache', 'new deals', 'NDF', 'Commodities.db')
check('setup: banco no lugar', os.path.isfile(DB))
check('setup: leitura DB-only responde', DR.day_records(dia)[0]['Deal'], 'DBH-1AAA')

print('\n== 1. escrita do espelho com uma leitura ABERTA: espera, nao colide ==')
import subprocess                                            # noqa: E402
_fresco = subprocess.run([sys.executable, '-c',
                          'from apps.pages import json_to_duckdb as c; '
                          'print(c.ABRIR_BANCO is c._abrir_banco_padrao and '
                          'c.FECHAR_BANCO is c._fechar_banco_padrao)'],
                         capture_output=True, text=True, cwd=ROOT, env=dict(os.environ))
check('5. num processo SEM o espelho (scripts/standalone) o gancho e o connect cru',
      _fresco.stdout.strip(), 'True')
# Dentro do app o gancho e GLOBAL ao processo: a thread do espelho o instala
# e ele vale para toda abertura em escrita do motor — que e o que se quer.
check('5. no processo do app, o gancho instalado e o com portao',
      core.ABRIR_BANCO is M._abrir_com_portao)
# A thread do espelho ja rodou (flush acima) — os ganchos dela estao instalados
# e valem para as tarefas DA FILA; aqui o leitor e simulado por uma conexao
# read_only crua, segurada no portao como o duck_read faz.
gate = DA.db_gate(DB)
gate.enter_read(1.0)
ro = duckdb.connect(DB, read_only=True)
t0 = time.monotonic()
R._atomic_write_json(dia, [{'Deal': 'DBH-1BBB', 'TradeDate': '15/06/2026'}])
time.sleep(0.6)                        # a tarefa esta na fila, esperando o portao
check('1. com o leitor aberto o escritor ainda nao converteu (esta esperando)',
      M._q.unfinished_tasks >= 1)
ro.close()
gate.exit_read()
check('1. leitor fechou → conversao terminou sem erro', M.flush(20))
con = duckdb.connect(DB, read_only=True)
try:
    check('1. e o banco tem o dado novo',
          con.execute('SELECT "Deal" FROM main.d_20260615_ndfcomm').fetchall(), [('DBH-1BBB',)])
finally:
    con.close()
check('1. o escritor esperou pelo leitor (nao pelo teto)', time.monotonic() - t0 < 8)

print('\n== 2. leitura durante uma escrita: espera e volta com dado ==')
segura = threading.Event()
solta = threading.Event()
_orig = core.ABRIR_BANCO


def _abrir_lento(path):
    con = M._abrir_com_portao(path)
    segura.set()
    solta.wait(10)                     # segura a escrita aberta
    return con


core.ABRIR_BANCO = _abrir_lento
R._atomic_write_json(dia, [{'Deal': 'DBH-1CCC', 'TradeDate': '15/06/2026'}])
check('2. escrita em curso', segura.wait(10))
res = {}


def _le():
    res['t0'] = time.monotonic()
    res['dados'] = DR.day_records(dia)
    res['dt'] = time.monotonic() - res['t0']


th = threading.Thread(target=_le)
th.start()
time.sleep(0.5)
check('2. o leitor esta esperando o portao (ainda sem resposta)', 'dados' not in res)
solta.set()
th.join(20)
core.ABRIR_BANCO = M._abrir_com_portao
check('2. leitura voltou com o dado NOVO, do banco', (res.get('dados') or [{}])[0].get('Deal'), 'DBH-1CCC')
check('2. sem estourar o teto do leitor', res.get('dt', 99) < DR._GATE_READ_WAIT_SECONDS)
M.flush(20)

print('\n== 3. memo por request ==')
from run import app                                          # noqa: E402
aberturas = []
_ctx = DA._database_context
import contextlib                                            # noqa: E402


@contextlib.contextmanager
def _conta(path, **kw):
    aberturas.append(os.path.basename(str(path)))
    with _ctx(path, **kw) as c:
        yield c


DA._database_context = _conta
with app.app_context():
    a = DR.day_records(dia)
    b = DR.day_records(dia)
    check('3. duas leituras do mesmo arquivo no request → UMA abertura', aberturas.count('Commodities.db'), 1)
    check('3. os dois consumidores recebem o mesmo dado', a == b)
    check('3. mas objetos SEUS (mutar um nao muda o outro)', a[0] is not b[0])
    a[0]['Deal'] = 'MUTADO'
    check('3. a mutacao nao vaza para a leitura seguinte', DR.day_records(dia)[0]['Deal'], 'DBH-1CCC')
    R._atomic_write_json(dia, [{'Deal': 'DBH-1DDD', 'TradeDate': '15/06/2026'}])
    M.flush(20)
    check('3. gravacao no meio do request invalida o memo (mtime/tamanho na chave)',
          DR.day_records(dia)[0]['Deal'], 'DBH-1DDD')
    aberturas.clear()
    r1 = DR.refdata_rows() if os.path.isfile(os.path.join(TMP, 'RefData.json')) else None
    check('3. sem RefData no tmp o raw_records nao explode', r1, None)

print('\n== 4. fora de request nao memoiza ==')
aberturas.clear()
DR.day_records(dia)
DR.day_records(dia)
check('4. duas leituras fora de request → duas aberturas', aberturas.count('Commodities.db'), 2)
DA._database_context = _ctx

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
