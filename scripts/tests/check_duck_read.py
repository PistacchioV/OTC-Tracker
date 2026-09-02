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
# A prova de que a fonte é o BANCO: adultera a coluna `_raw` — o canal que o
# flip consome (as tipadas ficam para o SQL) — enquanto o JSON continua 007135.
_tamper('reference_data.db',
        'UPDATE refdata SET "_raw" = '
        '\'{"COUNTERPARTY": "ACME LTDA", "SPN": "999999"}\'')
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

# ── 3b. CounterpartyDetails: fidelidade total via _raw ──────────────────────
from apps.pages.platform import counterparty as CP          # noqa: E402
CP._cpd_save_list([{'SPN': '007135', 'COUNTERPARTY': 'ACME LTDA', 'CGD': [],
                    'CONTACTS': [{'name': 'Bob', 'email': 'b@x'}],
                    'BANKING': {'ACCOUNTS': []},
                    'NET': {'value': 'Total Net', 'status': 'Active'}}])
M.flush(20)
# O contato veio SEM 'appr'/'maker' — a semântica de chave-AUSENTE que o
# _contacts_norm lê. O flip só é correto se as duas fontes respondem IGUAL.
via_db = CP._cpd_load()
_orig_cpd = None
try:
    import apps.pages.duck_read as _dr
    _orig_cpd = _dr.cpd_records
    _dr.cpd_records = lambda: None
    M.flush(20)                       # a migração one-shot pode ter regravado
    via_json = CP._cpd_load()
finally:
    _dr.cpd_records = _orig_cpd
check('3b. DB-first e JSON respondem IGUAL (chave-ausente preservada)',
      via_db, via_json)
check('3b. contato legado importado como ja aprovado (a chave AUSENTE foi vista)',
      bool(via_db and via_db[0]['CONTACTS']
           and via_db[0]['CONTACTS'][0].get('appr')))

# ── 3c. o navegador: /static/data servido do banco quando fresco ────────────
M.flush(20)
resp = R._duck_static_json('RefData.json')
check('3c. RefData.json servido do banco',
      resp is not None and json.loads(resp.get_data(as_text=True))[0]['SPN'],
      '135742')
resp = R._duck_static_json('anbima.json')
check('3c. arquivo de calendario servido do banco (via registro)',
      resp is not None and json.loads(resp.get_data(as_text=True))[0]['calendar'],
      'ANBIMA')
check('3c. subpasta fora dos mappings e nao-coberto caem no arquivo (None)',
      (R._duck_static_json('translations/en.json'),
       R._duck_static_json('datatables.json')), (None, None))

# ── 3d. datasets: _mapping_rows, _b3_load e o estático dos mappings ─────────
R._MAPPINGS_DIR = os.path.join(TMP, 'mappings')
os.makedirs(R._MAPPINGS_DIR, exist_ok=True)
# 12 linhas: com o _seq gravado como TEXTO, '10' < '2' — a ordem so sai certa
# porque a leitura ordena por CAST.
linhas_map = [{'BANK': 'B%02d' % i, 'CODE': str(300 + i)} for i in range(12)]
R._atomic_write_json(os.path.join(R._MAPPINGS_DIR, 'bank-name.json'), linhas_map)
M.flush(20)
lidas = DR.dataset_records(os.path.join(R._MAPPINGS_DIR, 'bank-name.json'))
check('3d. dataset_records devolve a LISTA NA ORDEM do arquivo (12 linhas)',
      lidas, linhas_map)
import duckdb as _dd
_con = _dd.connect(os.path.join(DBDIR, 'mappings', 'bank-name.db'))
_con.execute('UPDATE bank_name SET "_raw" = \'{"BANK": "DO BANCO"}\' '
             'WHERE "BANK" = \'B00\'')
_con.close()
check('3d. _mapping_rows veio do banco (a adulteracao aparece)',
      R._mapping_rows('bank-name')[0], {'BANK': 'DO BANCO'})
R._b3_save(os.path.join(TMP, 'Subjacente.json'),
           [{'Codigo': 'AAPL34', 'Classe': 'EQUITY'}])
M.flush(20)
resp = R._duck_static_json('Subjacente.json')
check('3d. cadastro B3 de raiz servido do banco',
      resp is not None and json.loads(resp.get_data(as_text=True))[0]['Codigo'],
      'AAPL34')
check('3d. _b3_load DB-first devolve as linhas e o caminho do JSON',
      (R._b3_load('subj')[0][0]['Classe'],
       R._b3_load('subj')[1].endswith('Subjacente.json')), ('EQUITY', True))
resp = R._duck_static_json('mappings/bank-name.json')
check('3d. mapping servido do banco pelo /static/data',
      resp is not None and json.loads(resp.get_data(as_text=True))[0],
      {'BANK': 'DO BANCO'})

# ── 3e. arquivo-dia: o funil _day_json DB-first ─────────────────────────────
dia = os.path.join(TMP, 'cache', 'new deals', 'NDF', 'Commodities', '2026', '06',
                   '20260618_ndfcomm.json')
os.makedirs(os.path.dirname(dia), exist_ok=True)
R._atomic_write_json(dia, [{'Deal': 'DBH-9AAA'}, {'Deal': 'DBH-9BBB'}])
M.flush(20)
_tamper(os.path.join('cache', 'new deals', 'NDF', 'Commodities.db'),
        'UPDATE main.d_20260618_ndfcomm SET "_raw" = '
        '\'{"Deal": "DO BANCO"}\' WHERE "Deal" = \'DBH-9AAA\'')
lidas = R._day_json(dia, os.path.getmtime(dia), os.path.getsize(dia))
check('3e. _day_json veio do banco, NA ORDEM do arquivo',
      lidas, [{'Deal': 'DO BANCO'}, {'Deal': 'DBH-9BBB'}])
obj = os.path.join(TMP, 'cache', 'reconciliation', 'payrec', '2026-07-08.json')
os.makedirs(os.path.dirname(obj), exist_ok=True)
R._atomic_write_json(obj, {'success': True, 'summary': [{'a': 1}]})
M.flush(20)
lidas = R._day_json(obj, os.path.getmtime(obj), os.path.getsize(obj))
check('3e. payload-objeto continua vindo do JSON (embrulhado em lista)',
      lidas, [{'success': True, 'summary': [{'a': 1}]}])
vazio = os.path.join(TMP, 'cache', 'new deals', 'NDF', 'Commodities', '2026', '06',
                     '20260619_ndfcomm.json')
R._atomic_write_json(vazio, [])
M.flush(20)
check('3e. dia vazio reconstrói como lista vazia',
      R._day_json(vazio, os.path.getmtime(vazio), os.path.getsize(vazio)), [])

# ── 4. banco ausente/ilegível nunca é erro ──────────────────────────────────
os.rename(os.path.join(DBDIR, 'reference_data.db'),
          os.path.join(DBDIR, 'reference_data.db.fora'))
check('4. banco ausente: fallback JSON, sem erro',
      R._refdata_records()[0]['SPN'], '135742')
with open(os.path.join(DBDIR, 'reference_data.db'), 'w') as fh:
    fh.write('nao sou um banco')
check('4. banco ilegivel: fallback JSON, sem erro',
      R._refdata_records()[0]['SPN'], '135742')

# ── 5. o cronômetro do share (era o freio): só TELEMETRIA na leitura DB-only ─
# (HANDOFF §389; endurecido em 2026-09-02) A leitura lenta continua armando a
# janela — mas ela agora é só o silenciador do AVISO no log: com a leitura
# DB-only não existe mais modo só-JSON, e o banco CONTINUA respondendo com o
# cronômetro armado. É a diferença entre "trocar de fonte em silêncio" (o
# comportamento antigo, que servia o JSON) e "avisar que está lento".
import time as _t
from apps.pages import duck_read as DR
os.rename(os.path.join(DBDIR, 'reference_data.db'),
          os.path.join(DBDIR, 'reference_data.db.quebrado'))
os.rename(os.path.join(DBDIR, 'reference_data.db.fora'),
          os.path.join(DBDIR, 'reference_data.db'))
check('5. antes do cronometro, o banco responde',
      DR.refdata_rows() is not None)
DR._freio_mede(DR._FREIO_LIMIAR + 1.0, 'x.db')          # leitura "lenta"
check('5. leitura lenta ARMA a janela do aviso', DR._freio_armado())
check('5. janela armada: table_rows SEGUE respondendo pelo banco',
      DR.refdata_rows() is not None)
check('5. janela armada: o leitor de cima segue servindo pelo BANCO',
      R._refdata_records()[0]['SPN'], '135742')
DR._freio['ate'] = _t.monotonic() - 1                    # expira
check('5. janela expirada: o banco segue respondendo',
      DR.refdata_rows() is not None)
check('5. leitura rapida NAO arma',
      (DR._freio_mede(0.0, 'x.db'), DR._freio_armado())[1], False)

print()
if fails:
    print('FAILED: %d check(s)' % len(fails))
    sys.exit(1)
print('all ok')
sys.exit(0)
