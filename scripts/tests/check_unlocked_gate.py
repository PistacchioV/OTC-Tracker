#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_unlocked_gate.py — o portão intra-processo leitor-sem-lock × escritor.

O DuckDB guarda UMA instância por arquivo dentro do processo e recusa a segunda
conexão com outra configuração. O poll do sino abre o banco de notificações
`read_only` SEM lock de arquivo (melhor esforço, CLAUDE.md §4) — e no instante
em que um poll estava aberto, o `duckdb_write` do `_create_notification`
estourava com *"Can't open a connection to same database file with a different
configuration than existing connections"*: a ESCRITA falhava e a notificação se
perdia, em silêncio para quem agiu. O §319 deu retentativa ao leitor; o lado do
escritor continuava desprotegido, e era ele que aparecia como ERROR no log da
instância.

O que este script prova (`_UnlockedReadGate` no `database_access.py`):

  1. a colisão da imagem: com uma leitura `unlocked` ABERTA, a escrita espera o
     leitor fechar e COMPLETA — antes, ConnectionException;
  2. o inverso: leitura `unlocked` pedida durante uma escrita espera um pouco e
     responde com DADO quando a escrita fecha dentro do teto;
  3. o teto do leitor: escrita mais longa que a espera degrada para o
     comportamento antigo (falha capturável, sino vazio) — nunca uma fila;
  4. o teto do escritor: leitor preso não cala as notificações para sempre —
     `enter_write` devolve False e a escrita segue para o connect;
  5. contadores voltam a zero (leitura e escrita pareiam enter/exit mesmo com
     falha) e o ciclo seguinte funciona;
  6. o portão é só do DuckDB — sqlite não passa por ele.

Roda com bancos em tempfile; não toca em dado real.
"""
import os
import sys
import tempfile
import threading
import time

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, 'scripts', 'tests'))

from apps.pages import database_access as da                  # noqa: E402

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


tmp = tempfile.mkdtemp(prefix='otc-gate-')
DB = os.path.join(tmp, 'gate.db')

with da.duckdb_write(DB) as conn:
    conn.execute("CREATE TABLE t (v INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")


def _gate():
    return da._unlocked_gates.get(da.normalize_database_path(DB))


# ── 1. leitura unlocked aberta; a escrita espera e completa ─────────────────
reader_open = threading.Event()
reader_done = threading.Event()
reader_err = []


def leitor_segurando(hold):
    try:
        with da.duckdb_read_unlocked(DB) as conn:
            conn.execute("SELECT * FROM t").fetchall()
            reader_open.set()
            time.sleep(hold)
    except Exception as e:                                    # noqa: BLE001
        reader_err.append(e)
        reader_open.set()
    finally:
        reader_done.set()


th = threading.Thread(target=leitor_segurando, args=(0.8,), daemon=True)
th.start()
reader_open.wait(5)
check('1. leitor unlocked abriu sem erro', not reader_err)
t0 = time.monotonic()
write_err = []
try:
    with da.duckdb_write(DB) as conn:
        conn.execute("INSERT INTO t VALUES (2)")
except Exception as e:                                        # noqa: BLE001
    write_err.append(e)
elapsed = time.monotonic() - t0
th.join(5)
check('1. escrita durante leitura unlocked COMPLETA (era ConnectionException)',
      not write_err)
check('1. a escrita ESPEROU o leitor fechar (não colidiu por sorte)',
      elapsed >= 0.4)
with da.duckdb_read(DB) as conn:
    check('1. a linha gravada esta la',
          conn.execute("SELECT count(*) FROM t").fetchone()[0], 2)

# ── 2. leitura pedida no meio de uma escrita curta: espera e traz dado ──────
writer_open = threading.Event()


def escritor_segurando(hold):
    with da.duckdb_write(DB) as conn:
        conn.execute("INSERT INTO t VALUES (3)")
        writer_open.set()
        time.sleep(hold)


th = threading.Thread(target=escritor_segurando, args=(0.4,), daemon=True)
th.start()
writer_open.wait(5)
t0 = time.monotonic()
read_err = []
rows = None
try:
    with da.duckdb_read_unlocked(DB) as conn:
        rows = conn.execute("SELECT count(*) FROM t").fetchone()[0]
except Exception as e:                                        # noqa: BLE001
    read_err.append(e)
elapsed = time.monotonic() - t0
th.join(5)
check('2. leitura durante escrita curta respondeu com DADO', not read_err)
check('2. e viu o banco depois do commit', rows, 3)
check('2. dentro do teto do leitor (sem fila)', elapsed < 3.0)

# ── 3. escrita mais longa que a espera do leitor: degrada, não enfileira ────
old_read_wait = da._GATE_READ_WAIT_SECONDS
da._GATE_READ_WAIT_SECONDS = 0.2
writer_open.clear()
th = threading.Thread(target=escritor_segurando, args=(1.0,), daemon=True)
th.start()
writer_open.wait(5)
t0 = time.monotonic()
read_err = []
try:
    with da.duckdb_read_unlocked(DB) as conn:
        conn.execute("SELECT count(*) FROM t").fetchone()
except Exception as e:                                        # noqa: BLE001
    read_err.append(e)
elapsed = time.monotonic() - t0
th.join(5)
da._GATE_READ_WAIT_SECONDS = old_read_wait
check('3. leitor degradou em falha CAPTURAVEL (o desfecho antigo do sino)',
      bool(read_err))
check('3. e voltou rapido, sem esperar a escrita inteira', elapsed < 0.9)

# ── 4. teto do escritor: leitor preso não cala a escrita para sempre ────────
g = da._UnlockedReadGate()
g.enter_read(0)                       # leitor "preso": nunca sai
t0 = time.monotonic()
check('4. enter_write devolve False no teto', g.enter_write(0.3), False)
check('4. e espera so o teto', 0.2 <= time.monotonic() - t0 < 2.0)
g.exit_write()
g.exit_read()
check('4. contadores do gate de unidade zerados',
      (g._readers, g._writers), (0, 0))

# ── 5. contadores do banco real voltam a zero e o ciclo seguinte funciona ───
gate = _gate()
check('5. contadores zerados apos tudo',
      (gate._readers, gate._writers), (0, 0))
ok5 = []
try:
    with da.duckdb_write(DB) as conn:
        conn.execute("INSERT INTO t VALUES (4)")
    with da.duckdb_read_unlocked(DB) as conn:
        ok5.append(conn.execute("SELECT count(*) FROM t").fetchone()[0])
except Exception as e:                                        # noqa: BLE001
    ok5.append(e)
# 5 linhas: a inicial + os inserts dos passos 1, 2, 3 e deste.
check('5. ciclo seguinte (escrita + leitura unlocked) limpo', ok5, [5])

# ── 6. sqlite não passa pelo portão ─────────────────────────────────────────
SDB = os.path.join(tmp, 'gate.sqlite3')
with da.sqlite_write(SDB) as conn:
    conn.execute("CREATE TABLE s (v INTEGER)")
check('6. sqlite nao registra gate',
      da.normalize_database_path(SDB) not in da._unlocked_gates._entries)

print()
if fails:
    print('FAILED: %d check(s)' % len(fails))
    sys.exit(1)
print('all ok')
sys.exit(0)
