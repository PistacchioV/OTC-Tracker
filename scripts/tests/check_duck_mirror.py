# -*- coding: utf-8 -*-
"""check_duck_mirror.py — o espelho vivo JSON → DuckDB (`apps/pages/duck_mirror.py`).

A fase 2 da migração: toda escrita de JSON coberto atualiza o banco na hora,
por uma fila e uma thread daemon — nunca no caminho da gravação (o funil
`_atomic_write_json` roda sob o `_cache_lock`). O que este script prova:

  1. arquivo-dia gravado pelo funil aparece no `daily_<rotina>.db` da família,
     e a REGRAVAÇÃO do mesmo arquivo atualiza a tabela;
  2. `RefData.json` via `_b3_save` e `CounterpartyDetails.json` via
     `_cpd_save_list` (que gravam FORA do funil) também espelham;
  3. calendário de feriados: o `write_holidays` da vertical avisa explícito
     (o nome do arquivo só o registro conhece) e a tabela acompanha;
  4. JSON sem banco (um mapping) e ponteiro `_last.json` NÃO disparam nada;
  5. os bancos nascem ao lado do dado espelhado (`<raiz>/db` quando a raiz é
     um tmp) — é o que impede um teste de escrever num banco REAL;
  6. kill-switch `OTC_DISABLE_DUCK_MIRROR=1` desliga; e o aviso é à prova de
     exceção — a gravação do JSON nunca falha por causa do espelho.

Tudo em tempfile; não toca em dado real.
"""
import io
import json
import os
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
# O espelho respeita o kill-switch dos schedulers; aqui ele tem de estar VIVO.
os.environ.pop('OTC_DISABLE_SCHEDULERS', None)
os.environ.pop('OTC_DISABLE_DUCK_MIRROR', None)

import duckdb                                               # noqa: E402

from apps.pages import routes as R                          # noqa: E402
from apps.pages import duck_mirror as M                     # noqa: E402
from apps.pages.platform import counterparty as CP          # noqa: E402
from apps.pages.features.holidays.infra import persistence as HP   # noqa: E402

TMP = tempfile.mkdtemp(prefix='otc-mirror-')
R._B3_DATA_DIR = TMP
DBDIR = os.path.join(TMP, 'db')

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def consulta(db, sql):
    # `db` pode ser um CAMINHO relativo: a pasta db/ espelha a árvore de origem.
    con = duckdb.connect(os.path.join(DBDIR, *db.split('/')), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


# ── 1. arquivo-dia pelo funil ───────────────────────────────────────────────
dia = os.path.join(TMP, 'cache', 'new deals', 'NDF', 'Commodities', '2026', '06',
                   '20260615_ndfcomm.json')
os.makedirs(os.path.dirname(dia), exist_ok=True)
R._atomic_write_json(dia, [{'Deal': 'DBH-1AAA', 'TradeDate': '15/06/2026'}])
check('1. flush esvazia a fila', M.flush(20))
check('1. arquivo-dia espelhado no banco do PRODUTO',
      consulta('cache/new deals/NDF/Commodities.db',
               'SELECT "Deal", "TradeDate" FROM main.d_20260615_ndfcomm'),
      [('DBH-1AAA', __import__('datetime').date(2026, 6, 15))])
R._atomic_write_json(dia, [{'Deal': 'DBH-1AAA'}, {'Deal': 'DBH-1BBB'}])
M.flush(20)
check('1. regravacao atualiza a tabela',
      consulta('cache/new deals/NDF/Commodities.db',
               'SELECT count(*) FROM main.d_20260615_ndfcomm'), [(2,)])

# ── 2. RefData e CounterpartyDetails (escritas fora do funil) ───────────────
R._b3_save(os.path.join(TMP, 'RefData.json'),
           [{'COUNTERPARTY': 'ACME LTDA', 'SPN': '007135'}])
M.flush(20)
check('2. RefData via _b3_save espelhado (zero a esquerda intacto)',
      consulta('reference_data.db', 'SELECT "SPN" FROM refdata'), [('007135',)])
CP._cpd_save_list([{'SPN': '007135', 'BANKING': {'ACCOUNTS': []}}])
M.flush(20)
linha = consulta('reference_data.db',
                 'SELECT "BANKING" FROM counterparty_details')[0][0]
check('2. CounterpartyDetails via _cpd_save_list espelhado (aninhado em JSON)',
      json.loads(linha), {'ACCOUNTS': []})

# ── 3. calendário de feriados ───────────────────────────────────────────────
HP.calendars()                       # semeia o registro (via funil → task holidays)
erro = HP.write_holidays('anbima.json',
                         [{'date': '2026-01-01', 'title': 'Confraternização',
                           'calendar': 'ANBIMA'}])
check('3. write_holidays sem erro', erro, None)
M.flush(20)
check('3. tabela do calendario acompanha',
      consulta('holiday_calendars.db', 'SELECT "title" FROM anbima'),
      [('Confraternização',)])
check('3. e o registro virou tabela tambem',
      consulta('holiday_calendars.db',
               'SELECT count(*) FROM _registry')[0][0] >= 11)

# ── 4. a cobertura total: cada mapping tem o SEU banco; ponteiro não dispara ─
os.makedirs(os.path.join(TMP, 'mappings'), exist_ok=True)
R._atomic_write_json(os.path.join(TMP, 'mappings', 'bank-name.json'),
                     [{'BANK': 'ITAU', 'CODE': '341'}])
ponteiro = os.path.join(TMP, 'cache', 'reconciliation', 'payrec', '_last.json')
os.makedirs(os.path.dirname(ponteiro), exist_ok=True)
R._atomic_write_json(ponteiro, {'recon_date': '2026-07-06'})
M.flush(20)
bancos = sorted(os.path.relpath(os.path.join(dp, f), DBDIR).replace(os.sep, '/')
                for dp, _d, fs in os.walk(DBDIR) for f in fs if f.endswith('.db'))
check('4. mapping espelha no banco DELE; _last.json em nada',
      bancos, ['cache/new deals/NDF/Commodities.db', 'holiday_calendars.db',
               'mappings/bank-name.db', 'reference_data.db'])
check('4. a tabela do mapping leva o registro exato (_raw)',
      json.loads(consulta('mappings/bank-name.db',
                          'SELECT "_raw" FROM bank_name')[0][0]),
      {'BANK': 'ITAU', 'CODE': '341'})
# Com um banco por JSON, o `anbima.json` viraria `anbima.db` se o conversor de
# datasets o aceitasse — e aí o calendário teria DUAS tabelas, em dois bancos.
check('4. arquivo de CALENDARIO nao vira dataset (e do holidays)',
      os.path.isfile(os.path.join(DBDIR, 'anbima.db')), False)

# ── 5. os bancos moram ao lado do dado espelhado ────────────────────────────
check('5. raiz trocada espelha em <raiz>/db, nunca no DATABASE_DIR real',
      M._out_dir(TMP), DBDIR)

# ── 6. kill-switch e a prova de exceção ─────────────────────────────────────
os.environ['OTC_DISABLE_DUCK_MIRROR'] = '1'
outro = os.path.join(TMP, 'cache', 'payrec', '2026', '07', '06',
                     'payrec_status_20260706.json')
os.makedirs(os.path.dirname(outro), exist_ok=True)
R._atomic_write_json(outro, [{'x': 1}])
M.flush(5)
check('6. com o kill-switch, nada espelha',
      os.path.isfile(os.path.join(DBDIR, 'daily_payrec.db')), False)
os.environ.pop('OTC_DISABLE_DUCK_MIRROR', None)

_put_original = M._put
M._put = lambda tarefa: (_ for _ in ()).throw(RuntimeError('boom'))
try:
    R._atomic_write_json(dia, [{'Deal': 'DBH-1CCC'}])
    check('6. espelho estourando nao derruba a gravacao do JSON', True)
except Exception as e:                                      # noqa: BLE001
    check('6. espelho estourando nao derruba a gravacao do JSON', str(e), True)
finally:
    M._put = _put_original
check('6. e o JSON foi gravado mesmo assim',
      json.load(open(dia, encoding='utf-8')), [{'Deal': 'DBH-1CCC'}])


# ── 7. o portão ADIA a escrita em vez de queimar a conversão ────────────────
# Leitor em voo no MESMO arquivo: `enter_write` volta False. Conectar ali é
# colher um erro previsível do DuckDB ("different configuration") e mandar o
# arquivo para 5 min de quarentena por causa de uma disputa de segundos — o
# defeito medido na instância em 09/09/2026, com leituras segurando a trava
# por 126–206 s. A tarefa tem de VOLTAR PARA A FILA, e só a última tentativa
# conecta assim mesmo (senão um leitor VAZADO calaria o espelho para sempre).
from apps.pages import database_access as DA                # noqa: E402

alvo = os.path.join(DBDIR, 'portao_teste.db')
os.makedirs(DBDIR, exist_ok=True)
gate = DA.db_gate(alvo)
gate.enter_read(0.0)                       # um leitor em voo, e ele NÃO fecha
try:
    M._forcar_abertura = False
    try:
        M._abrir_com_portao(alvo)
        check('7. portao com leitor aberto ADIA a escrita', 'conectou', 'LeitoresAbertos')
    except M.LeitoresAbertos:
        check('7. portao com leitor aberto ADIA a escrita', True)
    except Exception as e:                                  # noqa: BLE001
        check('7. portao com leitor aberto ADIA a escrita', type(e).__name__,
              'LeitoresAbertos')
    # E o adiamento não pode deixar o portão marcado como "escrevendo": o
    # leitor seguinte esperaria por uma escrita que desistiu.
    check('7. e o adiamento devolve o portao (nenhum escritor pendurado)',
          gate.enter_write(0.0) is False and True, True)
    gate.exit_write()

    # Última tentativa: conecta assim mesmo — a válvula contra leitor vazado.
    M._forcar_abertura = True
    con = None
    try:
        con = M._abrir_com_portao(alvo)
        check('7. na ultima tentativa conecta assim mesmo', True)
    except M.LeitoresAbertos:
        check('7. na ultima tentativa conecta assim mesmo', 'adiou de novo', 'conectou')
    finally:
        if con is not None:
            M._fechar_com_portao(alvo, con)
        M._forcar_abertura = False
finally:
    gate.exit_read()

# O laço repõe a tarefa na fila ANTES do `task_done`, e por isso o `flush()`
# não pode dizer "acabou" no meio de um adiamento.
fonte = io.open(os.path.join(ROOT, 'apps', 'pages', 'duck_mirror.py'),
                encoding='utf-8').read()
i_put = fonte.find('_q.put((kind, data_dir, rel, feito, tentativa + 1))')
i_done = fonte.find('_q.task_done()', i_put)
check('7. a reposicao na fila vem ANTES do task_done',
      i_put > 0 and i_done > i_put, True)
check('7. o teto de adiamentos existe', M._TENTATIVAS_PORTAO >= 1, True)

# E a MESMA regra na outra camada: a trava exclusiva que não vem é outra
# INSTÂNCIA com o banco aberto, e converter sem ela foi o que produziu o
# `IO Error: ... used by another process` de 09/09/2026 — conversão perdida
# mais quarentena, por uma disputa que passa sozinha.
def _trava_nao_vem(path, *a, **k):
    # A exceção REAL, construída como a camada a constrói (path, modo, teto) —
    # um stub com outra assinatura cairia no `except Exception` genérico e o
    # teste passaria a medir o caminho errado.
    raise DA.DatabaseLockTimeout(path, 'write', M._FILE_LOCK_WAIT_SECONDS)

_hold = DA.hold_file_lock
DA.hold_file_lock = _trava_nao_vem
try:
    M._forcar_abertura = False
    try:
        M._abrir_com_portao(os.path.join(DBDIR, 'trava_teste.db'))
        check('7. trava exclusiva ocupada ADIA a escrita', 'converteu', 'TravaOcupada')
    except M.TravaOcupada:
        check('7. trava exclusiva ocupada ADIA a escrita', True)
    except Exception as e:                                  # noqa: BLE001
        check('7. trava exclusiva ocupada ADIA a escrita', type(e).__name__, 'TravaOcupada')
    check('7. e as duas recusas tem o mesmo tratamento no laco',
          issubclass(M.TravaOcupada, M.EscritaAdiada)
          and issubclass(M.LeitoresAbertos, M.EscritaAdiada), True)

    M._forcar_abertura = True
    con = None
    try:
        con = M._abrir_com_portao(os.path.join(DBDIR, 'trava_teste.db'))
        check('7. sem trava, a ultima tentativa converte assim mesmo', True)
    except M.EscritaAdiada:
        check('7. sem trava, a ultima tentativa converte assim mesmo',
              'adiou de novo', 'converteu')
    finally:
        if con is not None:
            M._fechar_com_portao(os.path.join(DBDIR, 'trava_teste.db'), con)
        M._forcar_abertura = False
finally:
    DA.hold_file_lock = _hold

print()
if fails:
    print('FAILED: %d check(s)' % len(fails))
    sys.exit(1)
print('all ok')
sys.exit(0)
