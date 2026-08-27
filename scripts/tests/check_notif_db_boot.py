# -*- coding: utf-8 -*-
"""O banco de notificacoes se prepara na SUBIDA, e o sino nunca o cria.

O `_ensure_notif_db` abre o banco em modo READ-WRITE e, na primeira vez, migra o
banco antigo — no share isso segurou o lock exclusivo por 9,4 segundos. Ele era
chamado no topo do `get_notif_connection`, entao quem pagava essa conta era o
poll do sino: a consulta mais repetida do app, declarada de MELHOR ESFORCO e a
unica autorizada a abrir sem lock nenhum.

O DuckDB nao deixa isso passar em silencio. Um handle read-only aberto — outra
aba, outra thread, a outra instancia que enxerga o mesmo share — BLOQUEIA a
abertura read-write, e o open estoura com *"the process cannot access the file
because it is being used by another process"*. Como o flag so era marcado no
fim, a falha o deixava em False e TODO poll seguinte tentava de novo: um 500 por
aba a cada 8 segundos, cada um custando uma tentativa de lock exclusivo no
share.

Este script prende as quatro decisoes que consertam isso:

  1. a SUBIDA cria o schema (e a falha dela nao derruba o app);
  2. o caminho de LEITURA nunca abre para escrita — nem quando o flag esta em
     False, que e justamente o estado em que a tempestade acontecia;
  3. a sonda de leitura (`_notif_schema_pronto`) evita a abertura read-write
     quando nao ha nada a fazer, que e o caso normal;
  4. o ensure que falha ESPERA antes de tentar de novo, e o sino que nao
     consegue abrir devolve vazio em vez de 500.
"""
import os, sys, tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

TMP = tempfile.mkdtemp()

from apps.pages import routes as R                        # noqa: E402
# O ESTADO da subida do banco de notificacoes mora na platform/ (fatia
# `platform/notifications.py`): flag, espera e sonda trocam-se LA. Os
# caminhos e as primitivas (NOTIF_DB_PATH, duckdb_read/write) continuam
# trocados no routes — e a platform os alcanca por busca atrasada.
from apps.pages.platform import notifications as NP       # noqa: E402

R.DB_PATH = os.path.join(TMP, 'Users_OTCTracker.db')
R.NOTIF_DB_PATH = os.path.join(TMP, 'Notifications_OTCTracker.db')

from apps import create_app                               # noqa: E402
from apps.config import DebugConfig                       # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


# ── 1. a subida prepara o banco ─────────────────────────────────────────────
app = create_app(DebugConfig)
app.config['TESTING'] = True

check('a subida deixa o banco de notificacoes pronto', NP._notif_db_done, True)
check('e o arquivo existe', os.path.isfile(R.NOTIF_DB_PATH), True)

import duckdb                                             # noqa: E402
con = duckdb.connect(R.NOTIF_DB_PATH, read_only=True)
tabs = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
con.close()
check('com as duas tabelas', {'notifications', 'push_subscriptions'} <= tabs, True)


# ── as aberturas do banco de NOTIFICACOES passam a ser contadas ─────────────
NOTIF_BASE = os.path.basename(R.NOTIF_DB_PATH)
contas = {'write': 0, 'read': 0}
_write_falha = [False]
_dw, _dr = R.duckdb_write, R.duckdb_read


def duckdb_write(path, **kw):
    if os.path.basename(str(path)) == NOTIF_BASE:
        contas['write'] += 1
        if _write_falha[0]:
            # O erro exato do share: outro processo com o arquivo aberto.
            raise IOError('Cannot open file: being used by another process')
    return _dw(path, **kw)


def duckdb_read(path, **kw):
    if os.path.basename(str(path)) == NOTIF_BASE:
        contas['read'] += 1
    return _dr(path, **kw)


R.duckdb_write, R.duckdb_read = duckdb_write, duckdb_read


def zera():
    contas['write'] = contas['read'] = 0


# ── 2. o caminho de LEITURA nunca abre para escrita ─────────────────────────
for rotulo, kw in (('o poll do sino (unlocked)', {'readonly': True, 'unlocked': True}),
                   ('a leitura com lock', {'readonly': True})):
    zera()
    conn = R.get_notif_connection(**kw)
    conn.close()
    check(rotulo + ' nao abre para escrita', contas['write'], 0)

# E o que importa de verdade: mesmo com o flag em False — o estado de um
# processo cuja subida falhou — a leitura continua sem escrever. Era aqui que
# cada poll de cada aba tentava a migracao de novo.
NP._notif_db_done = False
zera()
conn = R.get_notif_connection(readonly=True, unlocked=True)
conn.close()
check('nem com o ensure pendente (o caso da tempestade)', contas['write'], 0)
check('e o flag continua como estava (o leitor nao decide isso)',
      NP._notif_db_done, False)


# ── 3. a sonda evita a abertura read-write ──────────────────────────────────
NP._notif_db_done = False
NP._notif_db_retry_at = 0.0
zera()
R._ensure_notif_db()
check('o ensure com o schema pronto nao abre para escrita', contas['write'], 0)
check('so le', contas['read'] >= 1, True)
check('e marca o banco como pronto', NP._notif_db_done, True)


# ── 4. o ensure que falha ESPERA antes de tentar de novo ────────────────────
_write_falha[0] = True
NP._notif_db_done = False
NP._notif_db_retry_at = 0.0
_sonda = NP._notif_schema_pronto
NP._notif_schema_pronto = lambda: False          # como se o schema faltasse
zera()
try:
    R._ensure_notif_db()
    subiu = False
except Exception:
    subiu = True
check('o ensure que falha relanca (quem grava tem de saber)', subiu, True)
check('tentou abrir uma vez', contas['write'], 1)
check('e armou a espera', NP._notif_db_retry_at > R.time.monotonic(), True)

zera()
try:
    R._ensure_notif_db()
    subiu = False
except Exception:
    subiu = True
check('a chamada seguinte, dentro da espera, nao tenta de novo', contas['write'], 0)
check('e nao estoura', subiu, False)

# Passada a espera, ele volta a tentar — a outra ponta pode ter soltado.
NP._notif_db_retry_at = 0.0
zera()
try:
    R._ensure_notif_db()
except Exception:
    pass
check('passada a espera, tenta de novo', contas['write'], 1)

NP._notif_schema_pronto = _sonda
_write_falha[0] = False
NP._notif_db_done = True


# ── 5. o sino que nao abre devolve vazio, nunca 500 ─────────────────────────
_gnc = R.get_notif_connection


def explode(*a, **kw):
    raise IOError('Cannot open file: being used by another process')


R.get_notif_connection = explode
cli = app.test_client()
with cli.session_transaction() as s:
    s['authenticated'] = True
    s['user_sid'] = 'E930179'
    s['user_role'] = 'ADMIN'
    s['user_name'] = 'Teste'
    s['user_email'] = 'x@x'
    # UTC, e nao o relogio local: a sessao expira comparando com o UTC, entao
    # uma data local em fuso negativo nasce vencida e o endpoint responde 401 —
    # que se le como autenticacao quebrada quando e so fuso.
    s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
resp = cli.get('/api/notifications')
R.get_notif_connection = _gnc

check('o sino que nao abre responde 200', resp.status_code, 200)
corpo = resp.get_json()
check('com a lista vazia', corpo.get('notifications'), [])
check('e com a MESMA forma da resposta de sucesso',
      sorted(corpo.keys()), ['notifications', 'success', 'total_today'])


print(('FAIL: %d' % len(fails)) if fails else 'ok')
sys.exit(1 if fails else 0)
