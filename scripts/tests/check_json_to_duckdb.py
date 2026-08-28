#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_json_to_duckdb.py — a conversão JSON → DuckDB (`convert_json_to_duckdb.py`).

O que este script prova, com um DATA_DIR inteiro em tempfile:

  1. **Calendários**: um banco, UMA TABELA POR CALENDÁRIO do registro; `date`
     tipada DATE; calendário sem arquivo vira tabela VAZIA (não erro);
     calendário NOVO no registro ganha tabela na rodada seguinte sem
     reconverter os demais (é a regra "quando for criado um novo, adicionar
     uma nova tabela");
  2. **RefData/CounterpartyDetails**: um banco, duas tabelas; nomes de coluna
     VERBATIM (com espaço); TUDO VARCHAR — o zero à esquerda de SPN/TAX ID é o
     que morreria num BIGINT, em silêncio (CLAUDE.md §7); aninhado vira texto
     JSON com roundtrip fiel;
  3. **Arquivo-dia**: UM BANCO POR ROTINA, seguindo a ramificação que a pasta
     `cache/` já tem (`daily_new_deals.db`, `daily_pending_confirmation.db`,
     …) — a subárvore da rotina vira schema e cada dia é uma tabela; tipos
     inferidos (dd/mm/aaaa → DATE, número → BIGINT/DOUBLE), com o zero à
     esquerda continuando texto e `''` virando NULL só em coluna tipada;
     payload-objeto vira as tabelas das listas internas + `_meta`; o
     `daily_caches.db` do desenho anterior é removido;
  4. **Incremental**: segunda rodada não reconverte nada; arquivo alterado
     reconverte SÓ ele; `_last.json` e afins ficam de fora, avisados. E o
     destino padrão é a pasta `db/` de todos os bancos (`DATABASE_DIR`),
     nunca uma pasta nova.

Tudo em tempfile; não toca em dado real.
"""
import datetime
import importlib.util
import json
import os
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)

import duckdb                                                 # noqa: E402

_spec = importlib.util.spec_from_file_location(
    'convert_json_to_duckdb', os.path.join(ROOT, 'scripts', 'convert_json_to_duckdb.py'))
conv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conv)

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def w(rel, payload):
    path = os.path.join(DATA, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, ensure_ascii=False)
    return path


DATA = tempfile.mkdtemp(prefix='otc-j2d-')
OUT = os.path.join(DATA, 'duckdb')

# ── massa: calendários ──────────────────────────────────────────────────────
w('holiday-calendars.json', [
    {'name': 'ANBIMA', 'file': 'anbima.json', 'class': 'x', 'drag': 'y', 'color': '#0d6efd'},
    {'name': 'PLATTS-ASIA', 'file': 'platts-asia.json', 'class': 'x', 'drag': 'y',
     'color': '#8b5cf6'},
])
w('anbima.json', [
    {'date': '2026-01-01', 'title': 'Confraternização Universal', 'calendar': 'ANBIMA'},
    {'date': '2026-02-16', 'title': 'Carnaval', 'calendar': 'ANBIMA'},
    {'date': '2026-02-17', 'title': 'Carnaval', 'calendar': 'ANBIMA'},
])
# PLATTS-ASIA sem arquivo: tabela vazia, não erro.

# ── massa: cadastros ────────────────────────────────────────────────────────
w('RefData.json', [
    {'STATUS': 'ACTIVE', 'COUNTERPARTY': '3M DO BRASIL LIMITADA',
     'TAX ID': '05.720.854/0001-77', 'SPN': '007135', 'ECI': '0220349472',
     'BANKER': 'Rafaela Negrão', 'COMMODITIES ACCRONYM': None, 'B3 CODE': 'C '},
    {'STATUS': 'ACTIVE', 'COUNTERPARTY': 'ACME LTDA',
     'TAX ID': '45.985.371/0001-08', 'SPN': '135742', 'ECI': '220349472',
     'BANKER': '', 'COMMODITIES ACCRONYM': 'ACM', 'B3 CODE': 'X'},
])
w('CounterpartyDetails.json', [
    {'SPN': '007135', 'COUNTERPARTY': '3M DO BRASIL LIMITADA', 'CGD': [],
     'BANKING': {'ACCOUNTS': [], 'DEFAULT_PAY': {'current': None, 'maker': 'A123456'}},
     'NET': {'value': 'Total Net', 'status': 'Active'}},
    {'SPN': '135742', 'COUNTERPARTY': 'ACME LTDA', 'CGD': ['26C4162177'],
     'BANKING': {'ACCOUNTS': [{'BANK': '341'}]}, 'NET': {'value': 'Gross'}},
])

# ── massa: arquivo-dia ──────────────────────────────────────────────────────
DEALS = [
    {'Deal': 'DBH-1AAA', 'TradeDate': '12/06/2026', 'SettlementDate': '2026-07-21',
     'TotalNotional': '1500000', 'Strike': '5.12345678', 'SPN': '007135',
     'Client': 'ACME LTDA', 'Maker': '', 'Qty': 10},
    {'Deal': 'DBH-1BBB', 'TradeDate': '12/06/2026', 'SettlementDate': '2026-08-05',
     'TotalNotional': '', 'Strike': '4.9', 'SPN': '135742',
     'Client': 'Negrão S.A.', 'Maker': 'A123456', 'Qty': 3},
]
w('cache/new deals/NDF/Commodities/2026/06/20260612_ndfcomm.json', DEALS)
w('cache/pending-confirmation/2026/08/27/pending-confirmation_20260827.json',
  [{'Trade Number': '0012345', 'Aging': '31', 'Client': 'ACME LTDA'}])
w('cache/reconciliation/payrec/2026-07-06.json',
  {'success': True, 'recon_date': '2026-07-06',
   'summary': [{'pay_receive': 'Pay', 'jpm_qty': 3, 'jpm_value': -226846.2276319994},
               {'pay_receive': 'Receive', 'jpm_qty': 7, 'jpm_value': 5133335.27}]})
w('cache/reconciliation/payrec/_last.json', {'recon_date': '2026-07-06'})

# ═══ 1. calendários ═════════════════════════════════════════════════════════
st = conv.convert_holidays(DATA, OUT)
check('1. holidays sem erros', st['errors'], [])
con = duckdb.connect(os.path.join(OUT, 'holiday_calendars.db'), read_only=True)
tabelas = {r[0] for r in con.execute(
    "SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()}
check('1. uma tabela por calendario (+ registro e manifest)',
      tabelas, {'anbima', 'platts_asia', '_registry', '_manifest'})
check('1. date e DATE de verdade',
      con.execute("DESCRIBE anbima").fetchall()[0][:2], ('date', 'DATE'))
check('1. feriados completos e tipados',
      con.execute("SELECT count(*), min(\"date\") FROM anbima").fetchone(),
      (3, datetime.date(2026, 1, 1)))
check('1. acento preservado',
      con.execute("SELECT title FROM anbima ORDER BY \"date\" LIMIT 1").fetchone()[0],
      'Confraternização Universal')
check('1. calendario sem arquivo vira tabela VAZIA',
      con.execute("SELECT count(*) FROM platts_asia").fetchone()[0], 0)
check('1. o registro guarda a cor',
      con.execute("SELECT color FROM _registry WHERE name='ANBIMA'").fetchone()[0],
      '#0d6efd')
con.close()

# calendário NOVO criado "pela tela": só ele converte na rodada seguinte
reg = json.load(open(os.path.join(DATA, 'holiday-calendars.json'), encoding='utf-8'))
reg.append({'name': 'BURSA', 'file': 'bursa.json', 'class': 'x', 'drag': 'y',
            'color': '#198754'})
w('holiday-calendars.json', reg)
w('bursa.json', [{'date': '2026-05-01', 'title': 'Labour Day', 'calendar': 'BURSA'}])
st = conv.convert_holidays(DATA, OUT)
check('1. rodada seguinte: anbima INALTERADO (nao reconverte)',
      'anbima.json' in st['skipped'])
con = duckdb.connect(os.path.join(OUT, 'holiday_calendars.db'), read_only=True)
check('1. calendario novo ganhou tabela',
      con.execute("SELECT count(*) FROM bursa").fetchone()[0], 1)
con.close()

# ═══ 2. RefData + CounterpartyDetails ═══════════════════════════════════════
st = conv.convert_refdata(DATA, OUT)
check('2. refdata sem erros', st['errors'], [])
con = duckdb.connect(os.path.join(OUT, 'reference_data.db'), read_only=True)
desc = con.execute("DESCRIBE refdata").fetchall()
check('2. colunas VERBATIM, na ordem do JSON',
      [d[0] for d in desc][:4], ['STATUS', 'COUNTERPARTY', 'TAX ID', 'SPN'])
check('2. cadastro de identificador e TODO VARCHAR (so o _seq e numero: a ordem)',
      {d[1] for d in desc if d[0] != '_seq'}, {'VARCHAR'})
check('2. _seq presente (a ordem da reconstrucao)',
      any(d[0] == '_seq' for d in desc))
check('2. zero a esquerda sobrevive (SPN e ECI)',
      con.execute("SELECT \"SPN\", \"ECI\" FROM refdata "
                  "WHERE \"COUNTERPARTY\" LIKE '3M%'").fetchone(),
      ('007135', '0220349472'))
check('2. texto byte a byte (o espaco do codigo B3 fica)',
      con.execute("SELECT \"B3 CODE\" FROM refdata "
                  "WHERE \"COUNTERPARTY\" LIKE '3M%'").fetchone()[0], 'C ')
check('2. null continua NULL e vazio continua vazio',
      con.execute("SELECT \"COMMODITIES ACCRONYM\" IS NULL, \"BANKER\" = '' "
                  "FROM refdata ORDER BY \"SPN\"").fetchall(),
      [(True, False), (False, True)])
cru = con.execute("SELECT \"_raw\" FROM refdata "
                  "WHERE \"COUNTERPARTY\" LIKE '3M%'").fetchone()[0]
check('2. _raw guarda o registro EXATO (o canal do flip de leitura)',
      json.loads(cru)['COMMODITIES ACCRONYM'] is None and '_raw' not in json.loads(cru))
bank = con.execute("SELECT \"BANKING\" FROM counterparty_details "
                   "WHERE \"SPN\" = '007135'").fetchone()[0]
check('2. aninhado roundtrip fiel via JSON',
      json.loads(bank), {'ACCOUNTS': [], 'DEFAULT_PAY': {'current': None,
                                                         'maker': 'A123456'}})
check('2. e consultavel por json_extract',
      con.execute("SELECT json_extract_string(\"BANKING\", '$.DEFAULT_PAY.maker') "
                  "FROM counterparty_details WHERE \"SPN\" = '007135'").fetchone()[0],
      'A123456')
con.close()

# ═══ 3. arquivo-dia: um banco POR ROTINA ════════════════════════════════════
# O desenho anterior era um daily_caches.db único: se existir, sai de cena.
open(os.path.join(OUT, 'daily_caches.db'), 'wb').close()
st = conv.convert_daily(DATA, OUT)
check('3. daily sem erros', st['errors'], [])
check('3. _last.json ficou de fora, avisado',
      st['ignored'], ['cache/reconciliation/payrec/_last.json'])
check('3. um banco por rotina, com o nome da ramificacao de cache/',
      sorted(os.path.basename(p) for p in st['dbs']),
      ['daily_new_deals.db', 'daily_pending_confirmation.db', 'daily_reconciliation.db'])
check('3. o daily_caches.db legado foi removido',
      os.path.isfile(os.path.join(OUT, 'daily_caches.db')), False)
con = duckdb.connect(os.path.join(OUT, 'daily_new_deals.db'), read_only=True)
check('3. a subarvore da rotina vira schema dentro do banco dela',
      {r[0] for r in con.execute(
          "SELECT DISTINCT table_schema FROM information_schema.tables "
          "WHERE table_schema NOT IN ('main')").fetchall()},
      {'ndf_commodities'})
nd = 'ndf_commodities.d_20260612_ndfcomm'
tipos = {d[0]: d[1] for d in con.execute("DESCRIBE %s" % nd).fetchall()}
check('3. dd/mm/aaaa e ISO viram DATE',
      (tipos['TradeDate'], tipos['SettlementDate']), ('DATE', 'DATE'))
check('3. numero vira numero (BIGINT/DOUBLE), id com zero fica texto',
      (tipos['TotalNotional'], tipos['Strike'], tipos['Qty'], tipos['SPN']),
      ('BIGINT', 'DOUBLE', 'BIGINT', 'VARCHAR'))
check('3. valores: data real, strike de 8 casas, vazio->NULL so no tipado',
      con.execute("SELECT \"TradeDate\", \"Strike\", \"TotalNotional\", \"Maker\" "
                  "FROM %s ORDER BY \"Deal\"" % nd).fetchall(),
      [(datetime.date(2026, 6, 12), 5.12345678, 1500000, ''),
       (datetime.date(2026, 6, 12), 4.9, None, 'A123456')])
con.close()
con = duckdb.connect(os.path.join(OUT, 'daily_pending_confirmation.db'), read_only=True)
check('3. rotina sem subarvore fica no main, tabela so com o dia',
      con.execute("SELECT \"Trade Number\" FROM main.d_20260827").fetchone()[0], '0012345')
con.close()
con = duckdb.connect(os.path.join(OUT, 'daily_reconciliation.db'), read_only=True)
check('3. payload-objeto: lista interna vira tabela',
      con.execute("SELECT count(*) FROM payrec.d_20260706_summary").fetchone()[0], 2)
meta = dict(con.execute("SELECT key, value FROM payrec.d_20260706__meta").fetchall())
check('3. e o resto vira _meta chave->valor',
      (json.loads(meta['success']), json.loads(meta['recon_date'])),
      (True, '2026-07-06'))
con.close()

# ═══ 4. incremental ═════════════════════════════════════════════════════════
st = conv.convert_daily(DATA, OUT)
check('4. segunda rodada nao reconverte nada',
      (len(st['converted']), len(st['skipped'])), (0, 3))

alterado = w('cache/new deals/NDF/Commodities/2026/06/20260612_ndfcomm.json',
             DEALS + [dict(DEALS[0], Deal='DBH-1CCC')])
os.utime(alterado, (os.path.getmtime(alterado) + 5,) * 2)
st = conv.convert_daily(DATA, OUT)
check('4. arquivo alterado reconverte SO ele',
      (st['converted'], len(st['skipped'])), (['daily_new_deals.db:' + nd], 2))
con = duckdb.connect(os.path.join(OUT, 'daily_new_deals.db'), read_only=True)
check('4. com o conteudo novo',
      con.execute("SELECT count(*) FROM %s" % nd).fetchone()[0], 3)
con.close()

novo = w('cache/new deals/NDF/Commodities/2026/06/20260613_ndfcomm.json', DEALS[:1])
st = conv.convert_daily(DATA, OUT)
check('4. dia novo vira tabela nova, sem tocar nas outras',
      (st['converted'], len(st['skipped'])),
      (['daily_new_deals.db:ndf_commodities.d_20260613_ndfcomm'], 3))
check('4. destino padrao e a pasta db/ de todos os bancos',
      conv._default_out_dir('/x'), os.path.join('/x', 'db'))

# ═══ 5. datasets: TODOS os demais JSONs, um banco por pasta ═════════════════
w('mappings/bank-name.json', [{'BANK': 'ITAU', 'CODE': '341', 'B3': 'C '}])
w('file-interpreter/termo.json', {'name': 'Termo', 'version': 2,
                                  'fields': [{'seq': 1, 'source': 'Fixed'}]})
w('translations/en.json', {'hello': 'Hello', 'bye': 'Bye'})
w('Subjacente.json', [{'Codigo': 'AAPL34', 'Classe': 'EQUITY'}])
# O banco de translations da primeira versão da cobertura tem de SAIR de cena.
open(os.path.join(OUT, 'translations.db'), 'wb').close()
st = conv.convert_datasets(DATA, OUT)
check('5. datasets sem erros', st['errors'], [])
check('5. um banco por pasta, raiz em static_data.db — e translations FORA',
      sorted(os.path.basename(p) for p in st['dbs']),
      ['file_interpreter.db', 'mappings.db', 'static_data.db'])
check('5. i18n fica em JSON: nada de translations.db (o legado foi removido)',
      os.path.isfile(os.path.join(OUT, 'translations.db')), False)
check('5. RefData/CPD/registro/calendarios ficam com os conversores proprios',
      sorted(x for x in st['ignored'] if not x.startswith('cache/')),
      ['CounterpartyDetails.json', 'RefData.json', 'anbima.json', 'bursa.json',
       'holiday-calendars.json'])
con = duckdb.connect(os.path.join(OUT, 'mappings.db'), read_only=True)
check('5. mapping: tipado, byte a byte, com o registro exato em _raw',
      con.execute('SELECT "CODE", "B3", json_extract_string("_raw", \'$.BANK\') '
                  'FROM bank_name').fetchone(), (341, 'C ', 'ITAU'))
con.close()
con = duckdb.connect(os.path.join(OUT, 'file_interpreter.db'), read_only=True)
check('5. payload-objeto: lista interna com _raw + _meta',
      (con.execute('SELECT "seq" FROM termo_fields').fetchone()[0],
       json.loads(dict(con.execute(
           'SELECT key, value FROM termo__meta').fetchall())['version'])), (1, 2))
con.close()
st = conv.convert_datasets(DATA, OUT)
check('5. segunda rodada nao reconverte nada', len(st['converted']), 0)
from apps.pages import json_to_duckdb as core                # noqa: E402
st = core.convert_dataset_files(DATA, OUT, ['mappings/bank-name.json', 'anbima.json'])
check('5. a porta do espelho: so o dado converte, calendario e ignorado',
      (len(st['skipped']), st['ignored']), (1, ['anbima.json']))

print()
if fails:
    print('FAILED: %d check(s)' % len(fails))
    sys.exit(1)
print('all ok')
sys.exit(0)
