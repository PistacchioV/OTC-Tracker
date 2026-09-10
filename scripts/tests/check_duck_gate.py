"""check_duck_gate.py — o PORTÃO leitor × escritor do armazém (DB-only, §434).

O leitor abre `read_only` e o escritor (o funil, agora síncrono) abre o MESMO
arquivo em escrita no mesmo processo — e o DuckDB recusa a segunda
configuração. Quem coordena os dois em memória é o `db_gate` do
`database_access`: leitor entra antes de abrir, escritor entra antes do
connect (pelo `duckdb_write`). O que se prova, em tempfile:
  1. escrita com uma leitura ABERTA: espera, não colide, e grava;
  2. leitura durante uma escrita: espera e volta com o dado novo;
  3. memo por REQUEST: o mesmo arquivo-dia abre o banco UMA vez por tela,
     objetos SEUS por consumidor, gravação no meio invalida;
  4. fora de request: o memo de PROCESSO, por mtime/tamanho do manifest;
  5. a trava de arquivo: outro PROCESSO com a trava exclusiva bloqueia a
     leitura (BancoOcupado sem cópia em memória) e a escrita espera.
"""
import contextlib
import os
import sys
import tempfile
import threading
import time

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages import routes as R                          # noqa: E402
from apps.pages import data_store as S                      # noqa: E402
from apps.pages import duck_read as DR                      # noqa: E402
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
R._atomic_write_json(dia, [{'Deal': 'DBH-1AAA', 'TradeDate': '15/06/2026'}])
DB = os.path.join(DBDIR, 'cache', 'new deals', 'NDF', 'Commodities.db')
check('setup: banco no lugar', os.path.isfile(DB))
check('setup: leitura DB-only responde', DR.day_records(dia)[0]['Deal'], 'DBH-1AAA')

print('\n== 1. escrita com uma leitura ABERTA: espera, nao colide ==')
aberto = threading.Event()
solta = threading.Event()


def _leitor():
    # o leitor do armazem entra no portao antes de abrir (`_com_leitura`)
    g = DA.db_gate(DB)
    g.enter_read(10)
    try:
        with DA.duckdb_read(DB) as con:
            con.execute('SELECT 1').fetchall()
            aberto.set()
            solta.wait(5)
    finally:
        g.exit_read()


t = threading.Thread(target=_leitor, daemon=True)
t.start()
aberto.wait(5)
gate = DA.db_gate(DB)
check('1. o portao sabe do leitor em voo', gate._readers >= 1)
t0 = time.monotonic()
threading.Timer(0.8, solta.set).start()
R._atomic_write_json(dia, [{'Deal': 'DBH-1BBB', 'TradeDate': '15/06/2026'}])
esperou = time.monotonic() - t0
t.join(5)
check('1. o escritor esperou o leitor fechar (%.2fs)' % esperou, esperou >= 0.7)
check('1. e gravou sem colidir', DR.day_records(dia)[0]['Deal'], 'DBH-1BBB')

print('\n== 2. leitura durante uma escrita: espera e volta com dado ==')
escrevendo = threading.Event()
fim_escrita = threading.Event()


def _escritor():
    with DA.duckdb_write(DB) as con:
        escrevendo.set()
        fim_escrita.wait(5)
        con.execute('CREATE OR REPLACE TABLE _probe AS SELECT 1 AS x')


t2 = threading.Thread(target=_escritor, daemon=True)
t2.start()
escrevendo.wait(5)
check('2. o portao sabe da escrita em voo', gate._writers >= 1)
threading.Timer(0.8, fim_escrita.set).start()
S.memo_forget()
t0 = time.monotonic()
lido = DR.day_records(dia)
esperou = time.monotonic() - t0
t2.join(5)
check('2. o leitor esperou a escrita fechar (%.2fs)' % esperou, esperou >= 0.7)
check('2. e voltou com dado', lido[0]['Deal'], 'DBH-1BBB')

print('\n== 3. memo por request ==')
from run import app                                          # noqa: E402
aberturas = []
_ctx = DA._database_context


@contextlib.contextmanager
def _conta(path, **kw):
    aberturas.append(os.path.basename(str(path)))
    with _ctx(path, **kw) as c:
        yield c


DA._database_context = _conta
S.memo_forget()
with app.app_context():
    a = DR.day_records(dia)
    n1 = aberturas.count('Commodities.db')
    b = DR.day_records(dia)
    check('3. a primeira leitura abre (manifest + dia), a segunda NAO abre',
          (1 <= n1 <= 2, aberturas.count('Commodities.db') - n1), (True, 0))
    check('3. os dois consumidores recebem o mesmo dado', a == b)
    check('3. mas objetos SEUS (mutar um nao muda o outro)', a[0] is not b[0])
    a[0]['Deal'] = 'MUTADO'
    check('3. a mutacao nao vaza para a leitura seguinte', DR.day_records(dia)[0]['Deal'], 'DBH-1BBB')
    R._atomic_write_json(dia, [{'Deal': 'DBH-1DDD', 'TradeDate': '15/06/2026'}])
    check('3. gravacao no meio do request invalida o memo (mtime/tamanho na chave)',
          DR.day_records(dia)[0]['Deal'], 'DBH-1DDD')
    r1 = DR.refdata_rows()
    check('3. sem RefData no tmp o raw_records nao explode', r1, None)

print('\n== 4. fora de request: o memo de PROCESSO, por mtime/tamanho ==')
S.memo_forget()
aberturas.clear()
a = DR.day_records(dia)
b = DR.day_records(dia)
check('4. duas leituras fora de request → UMA abertura', aberturas.count('Commodities.db'), 1)
check('4. e objetos SEUS a cada chamada', a == b and a[0] is not b[0])
R._atomic_write_json(dia, [{'Deal': 'DBH-1EEE', 'TradeDate': '15/06/2026'}])
aberturas.clear()
check('4. arquivo reescrito: reabre (manifest + dia) e traz o novo',
      (DR.day_records(dia)[0]['Deal'], 1 <= aberturas.count('Commodities.db') <= 2), ('DBH-1EEE', True))
aberturas.clear()
DR.day_records(dia)
check('4. e a leitura seguinte volta a nao abrir', aberturas.count('Commodities.db'), 0)
DA._database_context = _ctx

print('\n== 5. a trava de arquivo: outro PROCESSO com a trava exclusiva ==')
# A trava exclusiva de arquivo e o que vale ENTRE instancias sobre o mesmo
# db/ do share. Tomada por fora (como faria a instancia vizinha), a leitura
# com teto curto estoura, e sem copia em memoria o armazem diz BancoOcupado.
trava = DA.hold_file_lock(DB, write=True)
S.memo_forget()
S.ocupado_forget()
S._forget_db(DB)
t0 = time.monotonic()
try:
    with DA.read_timeout(0.3):
        S.read(dia)
    check('5. leitura com a trava presa por outro processo levanta BancoOcupado', False)
except S.BancoOcupado:
    check('5. leitura com a trava presa por outro processo levanta BancoOcupado', True)
check('5. e desiste rapido (%.1fs)' % (time.monotonic() - t0), time.monotonic() - t0 < 5)
trava.release()
S.ocupado_forget()
check('5. solta a trava, o banco volta a responder', DR.day_records(dia)[0]['Deal'], 'DBH-1EEE')

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
