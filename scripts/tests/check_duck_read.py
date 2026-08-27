# -*- coding: utf-8 -*-
"""check_duck_read.py — o flip de leitura DB-first com contrato de frescor (fase 3).

O `apps/pages/duck_read.py` só responde pelo banco quando o `_manifest` prova
que a tabela reflete o JSON COMO ELE ESTÁ em disco; senão devolve `None`, o
chamador cai no JSON de sempre e o espelho é avisado para se curar. O que este
script prova, nos dois pilotos religados:

  1. **RefData** (`_refdata_records` + os três índices derivados): com o banco
     FRESCO, a resposta vem DO BANCO — provado adulterando a tabela e vendo a
     adulteração na resposta (o JSON diz outra coisa);
  2. **frescor**: editado o JSON por FORA do app (sem aviso), o manifest não
     casa mais, a leitura cai no JSON — dado velho do banco nunca vence — e o
     espelho se cura sozinho (a leitura seguinte volta a ser do banco);
  3. **feriados**: `calendars()` e `load_holidays` DB-first com a data
     voltando como STRING ISO (a forma que o JSON sempre teve), e o fallback
     JSON + seed intactos quando não há banco nenhum;
  4. banco ausente/ilegível nunca é erro: é `None` e o comportamento de ontem.

Tudo em tempfile; não toca em dado real.
"""
import json
import os
import sys
import tempfile

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
from apps.pages.features.holidays.infra import persistence as HP   # noqa: E402

TMP = tempfile.mkdtemp(prefix='otc-dread-')
R._B3_DATA_DIR = TMP
DBDIR = os.path.join(TMP, 'db')

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def _tamper(db, sql):
    con = duckdb.connect(os.path.join(DBDIR, db))
    try:
        con.execute(sql)
    finally:
        con.close()


# ── 1. RefData: com o banco fresco, a resposta vem DO banco ─────────────────
R._b3_save(os.path.join(TMP, 'RefData.json'),
           [{'COUNTERPARTY': 'ACME LTDA', 'SPN': '007135',
             'TAX ID': '45.985.371/0001-08'}])
check('1. espelho alcancou o banco', M.flush(20))
check('1. sem banco adulterado, DB e JSON dizem o mesmo',
      DR.refdata_rows()[0]['SPN'], '007135')
# A prova de que a fonte é o BANCO: adultera a tabela (o JSON continua 007135).
_tamper('reference_data.db', "UPDATE refdata SET \"SPN\" = '999999'")
check('1. a leitura veio do banco (a adulteracao aparece)',
      R._refdata_records()[0]['SPN'], '999999')
R._REFDATA_TRIPLE_CACHE['mtime'] = None
check('1. e o indice derivado a herdou',
      R._refdata_triples()[0]['spn'], '999999')

# ── 2. frescor: JSON editado POR FORA cai no JSON e o espelho se cura ───────
with open(os.path.join(TMP, 'RefData.json'), 'w', encoding='utf-8') as fh:
    json.dump([{'COUNTERPARTY': 'BETA SA', 'SPN': '135742'}], fh)
check('2. manifest defasado: a resposta e o JSON (dado velho nunca vence)',
      R._refdata_records()[0]['SPN'], '135742')
check('2. e o espelho se curou sozinho', M.flush(20))
check('2. leitura seguinte volta a ser do banco (agora fresco)',
      DR.refdata_rows()[0]['COUNTERPARTY'], 'BETA SA')

# ── 3. feriados: calendars() e load_holidays DB-first ───────────────────────
regs = HP.calendars()                    # sem banco: semeia o JSON (fallback)
check('3. seed intacto no fallback', len(regs) >= 11)
M.flush(20)
check('3. depois do espelho, o registro vem do banco',
      HP._calendars_db() is not None)
erro = HP.write_holidays('anbima.json',
                         [{'date': '2026-01-01', 'title': 'Confraternização',
                           'calendar': 'ANBIMA'}])
check('3. write ok', erro, None)
M.flush(20)
_tamper('holiday_calendars.db', "UPDATE anbima SET \"title\" = 'DO BANCO'")
lidas = HP.load_holidays('anbima.json')
check('3. load_holidays veio do banco, data como STRING ISO',
      lidas, [{'date': '2026-01-01', 'title': 'DO BANCO', 'calendar': 'ANBIMA'}])

# ── 4. banco ausente/ilegível nunca é erro ──────────────────────────────────
os.rename(os.path.join(DBDIR, 'reference_data.db'),
          os.path.join(DBDIR, 'reference_data.db.fora'))
check('4. banco ausente: fallback JSON, sem erro',
      R._refdata_records()[0]['SPN'], '135742')
with open(os.path.join(DBDIR, 'reference_data.db'), 'w') as fh:
    fh.write('nao sou um banco')
check('4. banco ilegivel: fallback JSON, sem erro',
      R._refdata_records()[0]['SPN'], '135742')

print()
if fails:
    print('FAILED: %d check(s)' % len(fails))
    sys.exit(1)
print('all ok')
sys.exit(0)
