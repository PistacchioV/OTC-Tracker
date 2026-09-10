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
  3. **Arquivo-dia**: UM BANCO POR PRODUTO, com o caminho INTEIRO de `cache/`
     no nome (`daily_new_deals_ndf_commodities.db`,
     `daily_new_deals_option_fxo.db`) e cada dia como uma tabela; onde a
     rotina não se ramifica em pastas, o produto sai do NOME do arquivo (o
     Daily Settlement, dez arquivos na mesma pasta → dez bancos); tipos
     inferidos (dd/mm/aaaa → DATE, número → BIGINT/DOUBLE), com o zero à
     esquerda continuando texto e `''` virando NULL só em coluna tipada;
     payload-objeto vira as tabelas das listas internas + `_meta`; os bancos
     dos desenhos anteriores (`daily_caches.db` e o `daily_<rotina>.db` por
     primeiro nível) são removidos, e o que ainda é alvo NÃO é tocado;
  4. **Incremental**: segunda rodada não reconverte nada; arquivo alterado
     reconverte SÓ ele; `_last.json` e afins ficam de fora, avisados. E o
     destino padrão é a pasta `db/` de todos os bancos (`DATABASE_DIR`),
     nunca uma pasta nova.
  5. **Datasets**: UM BANCO POR JSON (`mappings_bank_name.db`,
     `file_interpreter_termo.db`, `subjacente.db` na raiz); `translations/`
     fica em JSON; e os bancos por PASTA do desenho anterior são removidos.
  6. **Os headers REAIS da B3**, varridos ponta a ponta: os arquivos da família
     SWAP chegam SEM cabeçalho e os nomes vêm do `_B3_SWAP_HEADERS_RAW`, com o
     `swap_position` repetindo 38 dos seus 170 nomes. Cobra que nenhuma CHAVE
     de JSON e nenhuma COLUNA de banco colidam, em nenhum dos quatro layouts —
     e que os dois desempates tenham a igualdade certa: a chave distingue a
     caixa (são dois campos), a coluna não (o identificador do DuckDB não
     distingue).

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
# A seção 6 importa o `routes` para varrer os headers REAIS da B3, e o Config
# recusa subir com um `SHARED_DRIVE_ROOT` relativo (o `I:\` do default fora do
# Windows). É o mesmo default de dev dos outros guardas.
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)

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
w('cache/new deals/Option/FXO/2026/06/20260612_optfxo.json', DEALS[:1])
w('cache/pending-confirmation/2026/08/27/pending-confirmation_20260827.json',
  [{'Trade Number': '0012345', 'Aging': '31', 'Client': 'ACME LTDA'}])
# Daily Settlement: a rotina que NÃO se ramifica em pastas — os arquivos do dia
# convivem na mesma pasta, e é o NOME de cada um que diz o produto.
w('cache/daily settlement/2026/07/28/otm-settlement_20260728.json',
  [{'Trade Id': '0099', 'Curve': 'PRE'}])
w('cache/daily settlement/2026/07/28/ndf-cockpit_20260728.json',
  [{'Trade Id': '0100', 'Curve': 'DOL'}])
# O `.meta` de um arquivo-dia: ele ANOTA o arquivo, não é um produto.
w('cache/daily settlement/2026/07/28/otm-settlement_20260728.meta.json',
  {'source_date': '2026-07-28', 'rows': 1})
# O DPOSICAO-SWAP: o layout da B3 repete nomes por PERNA e a grafia não é
# estável, então o arquivo tem `PU Inicial` e `Pu inicial` — chaves diferentes
# no JSON, a MESMA coluna para o DuckDB, que é insensível a caixa mesmo com o
# nome citado. E `Pu inicial_2` já existe (o desempate do exato que o
# `_b3_export_json` faz), então o sufixo tem de pular por cima dela.
w('cache/b3 files/Swap/2026/06/10/73760_260610_DPOSICAO-SWAP.json',
  [{'Contrato': 'CEMHYB-1', 'PU Inicial': '100', 'Pu inicial': '200',
    'Pu inicial_2': '300', 'Tipo/Classe': 'A', 'tipo/classe': 'B'}])
# E os irmãos dele na MESMA pasta do dia: posição, fluxo e agenda de prêmios.
# É por isso que o B3 Files nomeia os bancos pelo ARQUIVO — num banco só, os
# três dias iguais seriam três tabelas do mesmo produto.
w('cache/b3 files/Swap/2026/06/10/73760_260610_DFLUXO.json',
  [{'Contrato': 'CEMHYB-1', 'Valor': '10'}])
w('cache/b3 files/Swap/2026/06/10/73760_260610_DAGENDAPREMIOS.json',
  [{'Contrato': 'CEMHYB-1', 'Premio': '5'}])
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

# ═══ 3. arquivo-dia: um banco POR PRODUTO ═══════════════════════════════════
# Os dois desenhos anteriores — o daily_caches.db único e o daily_<rotina>.db
# por primeiro nível de cache/ — saem de cena se existirem.
# Os desenhos anteriores: o daily_caches.db único, o daily_<rotina>.db por
# primeiro nível e o nome ACHATADO na raiz (quando cada produto já tinha o seu
# banco, mas todos moravam soltos na mesma pasta).
os.makedirs(OUT, exist_ok=True)
for _legado in ('daily_caches.db', 'daily_new_deals.db', 'daily_reconciliation.db',
                'daily_new_deals_ndf_commodities.db', 'daily_settlement_otm.db'):
    open(os.path.join(OUT, _legado), 'wb').close()
st = conv.convert_daily(DATA, OUT)
check('3. daily sem erros', st['errors'], [])
check('3. _last.json ficou de fora, avisado',
      st['ignored'], ['cache/reconciliation/payrec/_last.json'])
# A pasta `db/` espelha a árvore de origem: o caminho de `cache/` vira PASTA e
# o produto vira o arquivo. Os segmentos de ano/mês/dia não viram pasta — eles
# já são a tabela.
check('3. a pasta db/ espelha a arvore de cache/, um banco por PRODUTO',
      sorted(os.path.relpath(p, OUT).replace(os.sep, '/') for p in st['dbs']),
      ['cache/b3 files/Swap/73760_DAGENDAPREMIOS.db',
       'cache/b3 files/Swap/73760_DFLUXO.db',
       'cache/b3 files/Swap/73760_DPOSICAO-SWAP.db',
       'cache/daily settlement/ndf-cockpit.db',
       'cache/daily settlement/otm-settlement.db',
       'cache/new deals/NDF/Commodities.db',
       'cache/new deals/Option/FXO.db',
       'cache/pending-confirmation.db',
       'cache/reconciliation/payrec.db'])
check('3. e ano/mes/dia NAO viram pasta',
      any('/2026/' in os.path.relpath(p, OUT).replace(os.sep, '/') for p in st['dbs']),
      False)
check('3. os bancos dos desenhos anteriores foram removidos',
      [os.path.isfile(os.path.join(OUT, f))
       for f in ('daily_caches.db', 'daily_new_deals.db', 'daily_reconciliation.db',
                 'daily_new_deals_ndf_commodities.db', 'daily_settlement_otm.db')],
      [False] * 5)
# `daily_pending_confirmation.db` é o mesmo nome nos dois desenhos (a rotina
# nunca se ramificou): apagá-lo como legado custaria uma reconversão inteira à
# toa. A marca provaria isso — se o banco tivesse sido apagado e recriado, ela
# não estaria lá.
_PC = os.path.join(OUT, 'cache', 'pending-confirmation.db')
_marca = duckdb.connect(_PC)
_marca.execute('CREATE TABLE _marca AS SELECT 1 AS x')
_marca.close()
conv.convert_daily(DATA, OUT)
_marca = duckdb.connect(_PC, read_only=True)
check('3. o banco que continua sendo alvo NAO e apagado nem recriado',
      _marca.execute('SELECT x FROM _marca').fetchone()[0], 1)
_marca.close()
# O B3 Files também nomeia os bancos pelo ARQUIVO: a pasta do dia guarda
# posição, fluxo e agenda de prêmios lado a lado. A decisão é DECLARADA
# (`_ROTINAS_POR_ARQUIVO`) e não contada da profundidade — `daily settlement`
# tem um nível de rotina e `b3 files/Swap` tem dois, e os dois misturam.
check('3. B3 Files: um banco por ARQUIVO, dentro da pasta do produto',
      sorted(os.path.relpath(p, OUT).replace(os.sep, '/') for p in st['dbs']
             if '/b3 files/' in os.path.relpath(p, OUT).replace(os.sep, '/')),
      ['cache/b3 files/Swap/73760_DAGENDAPREMIOS.db',
       'cache/b3 files/Swap/73760_DFLUXO.db',
       'cache/b3 files/Swap/73760_DPOSICAO-SWAP.db'])
check('3.    e a tabela e so o dia: a tag ja esta no nome do banco',
      os.path.isfile(os.path.join(OUT, 'cache', 'b3 files', 'Swap',
                                  '73760_DPOSICAO-SWAP.db')))
# O `_` duplo que a data deixa NO MEIO do nome cai junto: sem isso o banco
# sairia `73760__DPOSICAO-SWAP.db`. No Daily Settlement a data está no FIM e o
# strip das pontas bastava — foi por isso que ninguém viu antes.
from apps.pages import json_to_duckdb as _mot                 # noqa: E402
check('3.    a data sai do MEIO do nome sem deixar separador dobrado',
      _mot._sem_data('73760_260610_DPOSICAO-SWAP', datetime.date(2026, 6, 10)),
      '73760_DPOSICAO-SWAP')
# O banco da ROTINA INTEIRA, de antes da quebra por arquivo, tem de SAIR: nada
# mais o escreve e nada mais o lê, e quem consulta por fora encontraria dois.
_ORF = os.path.join(OUT, 'cache', 'b3 files', 'Swap.db')
duckdb.connect(_ORF).close()
conv.convert_daily(DATA, OUT)
check('3.    e o banco da rotina inteira, de antes da quebra, e removido',
      os.path.isfile(_ORF), False)
# O DPOSICAO-SWAP: chaves que só diferem na CAIXA (`PU Inicial` × `Pu
# inicial`) são duas pernas do swap. A tabela-dia é só o canal cru (§437), e
# o `_raw` guarda o registro byte a byte — as duas pernas voltam distintas,
# sem o desempate de coluna que a tabela tipada precisava.
from apps.pages import json_to_duckdb as _motor               # noqa: E402
_SW = duckdb.connect(os.path.join(OUT, 'cache', 'b3 files', 'Swap', '73760_DPOSICAO-SWAP.db'), read_only=True)
_cur = _SW.execute('SELECT * FROM main.d_20260610')
check('3. a tabela-dia do layout de 170 colunas e so _seq/_raw',
      [d[0] for d in _cur.description], ['_seq', '_raw'])
_sw_rec = _motor.ler_payload(_SW, 'cache/b3 files/Swap/2026/06/10/73760_260610_DPOSICAO-SWAP.json',
                             _motor.KIND_DAILY, 'd_20260610')[0]
check('3.    e as pernas que so diferem na CAIXA continuam distintas no _raw',
      (_sw_rec['PU Inicial'], _sw_rec['Pu inicial'], _sw_rec['Pu inicial_2']), ('100', '200', '300'))
# O `_raw` guarda a chave ORIGINAL: o sufixo é do banco, não do arquivo.
check('3.    e o _raw mantem a chave do JSON, sem sufixo nenhum',
      json.loads(_SW.execute('SELECT "_raw" FROM main.d_20260610').fetchone()[0])
      ['Pu inicial'], '200')
_SW.close()
# O desempate pula o nome que já é de OUTRA coluna do mesmo arquivo — senão
# `Pu inicial` viraria `Pu inicial_2`, que existe, e a colisão voltaria.
check('3.    o sufixo pula por cima de uma coluna que ja existe',
      _motor.nomes_sql(['PU Inicial', 'Pu inicial', 'Pu inicial_2']),
      ['PU Inicial', 'Pu inicial_3', 'Pu inicial_2'])
# O Daily Settlement é o caso do pedido: mesma pasta, um banco por arquivo.
check('3. rotina sem pastas: o produto sai do NOME, dentro da pasta da rotina',
      [os.path.isfile(os.path.join(OUT, 'cache', 'daily settlement', f)) for f in
       ('otm-settlement.db', 'ndf-cockpit.db')], [True, True])
con = duckdb.connect(os.path.join(OUT, 'cache', 'daily settlement', 'otm-settlement.db'),
                     read_only=True)
check('3. e a tabela e so o dia: a tag ja esta no nome do banco',
      con.execute('SELECT json_extract_string("_raw", \'$.Curve\') FROM main.d_20260728').fetchone()[0], 'PRE')
# O `.meta` vai para o banco do arquivo que ele anota, com `_meta` na tabela.
# Num banco próprio ele sairia como `otm-settlement_.meta.db` — a data está no
# MEIO do nome, então tirá-la deixa um `_` que o strip das pontas não alcança —
# e quem consultasse o produto teria de juntar dois bancos.
check('3. o .meta acompanha o arquivo dele, no MESMO banco',
      sorted(r[0] for r in con.execute(
          "SELECT table_name FROM information_schema.tables "
          "WHERE table_schema='main' AND table_name LIKE 'd_%'").fetchall()),
      ['d_20260728', 'd_20260728_meta__raw'])
con.close()
check('3. e nao sobra um banco com o nome torto',
      os.path.isfile(os.path.join(OUT, 'cache', 'daily settlement',
                                  'otm-settlement_.meta.db')), False)
_NDFC = os.path.join(OUT, 'cache', 'new deals', 'NDF', 'Commodities.db')
con = duckdb.connect(_NDFC, read_only=True)
check('3. o caminho vai para o NOME do banco: nada de schema extra',
      {r[0] for r in con.execute(
          "SELECT DISTINCT table_schema FROM information_schema.tables "
          "WHERE table_schema NOT IN ('main')").fetchall()},
      set())
nd = 'main.d_20260612_ndfcomm'
# Arquivo-dia é SÓ o canal cru (§437): as colunas tipadas do layout eram
# catálogo que o DuckDB lê inteiro a cada abertura — minutos no share.
check('3. arquivo-dia e so _seq/_raw: nada de coluna tipada no catalogo',
      [d[:2] for d in con.execute("DESCRIBE %s" % nd).fetchall()],
      [('_seq', 'BIGINT'), ('_raw', 'VARCHAR')])
check('3. e o dia volta EXATO pelo _raw (zero a esquerda, vazio, acento)',
      _motor.ler_payload(con, 'cache/new deals/NDF/Commodities/2026/06/20260612_ndfcomm.json',
                         _motor.KIND_DAILY, 'd_20260612_ndfcomm'), DEALS)
con.close()
con = duckdb.connect(_PC, read_only=True)
check('3. tag que so repete o nome do banco cai: a tabela e so o dia',
      con.execute("SELECT json_extract_string(\"_raw\", '$.\"Trade Number\"') FROM main.d_20260827").fetchone()[0], '0012345')
con.close()
con = duckdb.connect(os.path.join(OUT, 'cache', 'reconciliation', 'payrec.db'),
                     read_only=True)
check('3. payload-objeto de arquivo-dia: SO a __raw (sem sub-tabela nem __meta)',
      sorted(r[0] for r in con.execute(
          "SELECT table_name FROM information_schema.tables "
          "WHERE table_schema='main' AND table_name LIKE 'd_20260706%'").fetchall()),
      ['d_20260706__raw'])
check('3. e o objeto volta exato',
      _motor.ler_payload(con, 'cache/reconciliation/payrec/2026-07-06.json',
                         _motor.KIND_DAILY, 'd_20260706')['summary'][1]['jpm_value'], 5133335.27)
con.close()

# ═══ 4. incremental ═════════════════════════════════════════════════════════
st = conv.convert_daily(DATA, OUT)
check('4. segunda rodada nao reconverte nada',
      (len(st['converted']), len(st['skipped'])), (0, 10))

alterado = w('cache/new deals/NDF/Commodities/2026/06/20260612_ndfcomm.json',
             DEALS + [dict(DEALS[0], Deal='DBH-1CCC')])
os.utime(alterado, (os.path.getmtime(alterado) + 5,) * 2)
st = conv.convert_daily(DATA, OUT)
check('4. arquivo alterado reconverte SO ele',
      (st['converted'], len(st['skipped'])),
      (['cache/new deals/NDF/Commodities.db:' + nd], 9))
con = duckdb.connect(_NDFC, read_only=True)
check('4. com o conteudo novo',
      con.execute("SELECT count(*) FROM %s" % nd).fetchone()[0], 3)
con.close()

novo = w('cache/new deals/NDF/Commodities/2026/06/20260613_ndfcomm.json', DEALS[:1])
st = conv.convert_daily(DATA, OUT)
check('4. dia novo vira tabela nova, sem tocar nas outras',
      (st['converted'], len(st['skipped'])),
      (['cache/new deals/NDF/Commodities.db:main.d_20260613_ndfcomm'], 10))
check('4. destino padrao e a pasta db/ de todos os bancos',
      conv._default_out_dir('/x'), os.path.join('/x', 'db'))

# ═══ 5. datasets: TODOS os demais JSONs, UM BANCO POR JSON ══════════════════
w('mappings/bank-name.json', [{'BANK': 'ITAU', 'CODE': '341', 'B3': 'C '}])
w('mappings/mt300.json', [{'COUNTERPARTY': 'ACME LTDA', 'SPN': '135742'}])
w('control-panel/mt300_status.json', {'last': '2026-08-27', 'sent': 12})
w('file-interpreter/termo.json', {'name': 'Termo', 'version': 2,
                                  'fields': [{'seq': 1, 'source': 'Fixed'}]})
w('translations/en.json', {'hello': 'Hello', 'bye': 'Bye'})
w('Subjacente.json', [{'Codigo': 'AAPL34', 'Classe': 'EQUITY'}])
# Os bancos por PASTA do desenho anterior (e o translations.db da primeira
# versão da cobertura) têm de SAIR de cena.
for _legado in ('translations.db', 'mappings.db', 'file_interpreter.db',
                'static_data.db', 'mappings_mt300.db',
                'control_panel_mt300_status.db'):
    open(os.path.join(OUT, _legado), 'wb').close()
st = conv.convert_datasets(DATA, OUT)
check('5. datasets sem erros', st['errors'], [])
check('5. UM BANCO POR JSON, na MESMA arvore do JSON — e translations FORA',
      sorted(os.path.relpath(p, OUT).replace(os.sep, '/') for p in st['dbs']),
      ['Subjacente.db', 'control-panel/mt300_status.db',
       'file-interpreter/termo.db', 'mappings/bank-name.db',
       'mappings/mt300.db'])
check('5. os bancos dos desenhos anteriores foram removidos',
      [os.path.isfile(os.path.join(OUT, f)) for f in
       ('translations.db', 'mappings.db', 'file_interpreter.db', 'static_data.db',
        'mappings_mt300.db', 'control_panel_mt300_status.db')],
      [False] * 6)
# Eles saem em `cobertos`, não em `ignored`: outro conversor da MESMA rodada os
# leva, e contá-los como "fora" fazia o resumo parecer perda.
check('5. RefData/CPD/registro/calendarios ficam com os conversores proprios',
      sorted(x for x in st['cobertos'] if not x.startswith('cache/')),
      ['CounterpartyDetails.json', 'RefData.json', 'anbima.json', 'bursa.json',
       'holiday-calendars.json'])
check('5. e nada sobra como fora de todo conversor', st['ignored'], [])
con = duckdb.connect(os.path.join(OUT, 'mappings', 'bank-name.db'), read_only=True)
check('5. mapping: tipado, byte a byte, com o registro exato em _raw',
      con.execute('SELECT "CODE", "B3", json_extract_string("_raw", \'$.BANK\') '
                  'FROM bank_name').fetchone(), (341, 'C ', 'ITAU'))
con.close()
con = duckdb.connect(os.path.join(OUT, 'file-interpreter', 'termo.db'), read_only=True)
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
      (len(st['skipped']), st['cobertos'], st['ignored']),
      (1, ['anbima.json'], []))
check('5. cada JSON tem o SEU banco, na pasta do JSON',
      core._dataset_rel_target('mappings/mt300.json', set()),
      ('mappings/mt300.db', 'mt300'))

# ═══ 6. os headers REAIS da B3, ponta a ponta ═══════════════════════════════
# Os arquivos da família SWAP chegam SEM cabeçalho: os nomes vêm do
# `_B3_SWAP_HEADERS_RAW`, escrito à mão na ordem do arquivo. O `swap_position`
# tem 170 colunas e repete 38 nomes — é o layout que mais tenta quebrar as duas
# pontas do desempate. A varredura é o teste: em vez de assertar o `Pu inicial`,
# ela cobra que NENHUMA chave e NENHUMA coluna colidam, em nenhum dos layouts.
print()
from apps.pages import routes as R                            # noqa: E402
for _key, _raw in sorted(R._B3_SWAP_HEADERS_RAW.items()):
    _hs = [h for h in _raw.split(';') if h != '']
    _js = core.nomes_unicos(_hs, chave=lambda s: s)     # as chaves do JSON
    _sq = core.nomes_sql(_js)                           # as colunas do banco
    check('6. %s: %d colunas viram %d chaves de JSON distintas'
          % (_key, len(_hs), len(_hs)), len(set(_js)), len(_hs))
    check('6. %s: e %d colunas de banco distintas (cego a caixa)'
          % (_key, len(_hs)), len({s.lower() for s in _sq}), len(_hs))
# O desempate da CHAVE é sensível a caixa de propósito: no JSON `PU Inicial` e
# `Pu inicial` são dois campos, e igualá-los apagaria um deles.
check('6. a chave do JSON distingue a CAIXA',
      core.nomes_unicos(['PU Inicial', 'Pu inicial'], chave=lambda s: s),
      ['PU Inicial', 'Pu inicial'])
check('6.    e a coluna do banco NAO, porque o DuckDB nao distingue',
      core.nomes_sql(['PU Inicial', 'Pu inicial']),
      ['PU Inicial', 'Pu inicial_2'])
# O caso que o desempate por CONTAGEM perdia: `X` duas vezes mais uma coluna
# chamada `X_2` davam duas chaves `X_2`, e no dicionário a segunda apaga a
# primeira — uma coluna do arquivo somindo sem erro nenhum.
check('6. o sufixo pula por cima de uma coluna que ja se chama assim',
      core.nomes_unicos(['X', 'X', 'X_2'], chave=lambda s: s),
      ['X', 'X_3', 'X_2'])

# ═══ 7. slim_duckdb.py: o banco JA existente vai para a mesma forma, no lugar ═
# O motor passou a gravar as tabelas-dia só com `_seq`/`_raw` (§437); o banco
# da instância tem meses na forma antiga (tipada + _raw, e o payload-objeto
# com sub-tabelas + __meta + __raw). O script copia do PRÓPRIO banco — nunca
# do JSON do disco, que está velho desde o cutover — e troca o arquivo.
print()
import subprocess                                             # noqa: E402
_VELHO = os.path.join(OUT, 'cache', 'velho.db')
_con = duckdb.connect(_VELHO)
core.ensure_manifest(_con)
_ROWS = [{'Deal': 'A', 'TradeDate': '12/06/2026', 'SPN': '007', 'Qty': 1},
         {'Deal': 'B', 'TradeDate': '13/06/2026', 'SPN': '135742', 'Qty': 2}]
_REL1 = 'cache/velho/2026/01/20260101_velho.json'
core.write_rows_table(_con, 'main.d_20260101', core._com_raw(_ROWS))
core.manifest_record(_con, core.manifest_key_of(_REL1, core.KIND_DAILY),
                     core._Stamp(1.0, 10), ['main.d_20260101'])
_OBJ = {'ok': True, 'recon_date': '2026-01-02', 'summary': [{'a': 1}, {'a': 2}]}
_REL2 = 'cache/velho/2026/01/20260102_velho.json'
_criadas = core._convert_daily_payload(_con, 'main', 'd_20260102', _OBJ, raw=True)
core.write_rows_table(_con, 'main.d_20260102__raw',
                      [{'_seq': 0, '_raw': json.dumps(_OBJ)}], force_varchar=True)
core.manifest_record(_con, core.manifest_key_of(_REL2, core.KIND_DAILY),
                     core._Stamp(2.0, 20), _criadas + ['main.d_20260102__raw'])
_con.close()
check('7. o banco velho tem a forma antiga (tipada + _raw; objeto com sub-tabela e __meta)',
      len(_criadas) >= 2 and len(duckdb.connect(_VELHO, read_only=True).execute('DESCRIBE main.d_20260101').fetchall()) > 2, True)
_p = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'slim_duckdb.py'), '--db-dir', OUT],
                    capture_output=True, text=True, env=dict(os.environ))
check('7. o script roda (rc 0)', (_p.returncode, 'velho.db' in _p.stdout), (0, True))
if _p.returncode:
    print(_p.stdout[-800:], _p.stderr[-800:])
_con = duckdb.connect(_VELHO, read_only=True)
check('7. a lista ficou so _seq/_raw',
      [d[:2] for d in _con.execute('DESCRIBE main.d_20260101').fetchall()],
      [('_seq', 'BIGINT'), ('_raw', 'VARCHAR')])
check('7. o objeto ficou so com a __raw; sub-tabela e __meta sumiram',
      sorted(r[0] for r in _con.execute(
          "SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()),
      ['_manifest', 'd_20260101', 'd_20260102__raw'])
check('7. o manifest aponta so para a __raw',
      core.manifest_targets(_con, core.manifest_key_of(_REL2, core.KIND_DAILY)), ['main.d_20260102__raw'])
check('7. e os dois voltam EXATOS',
      (core.ler_payload(_con, _REL1, core.KIND_DAILY, 'd_20260101'),
       core.ler_payload(_con, _REL2, core.KIND_DAILY, 'd_20260102')), (_ROWS, _OBJ))
_con.close()
_con = duckdb.connect(os.path.join(OUT, 'reference_data.db'), read_only=True)
check('7. o reference_data.db (dataset, fora de cache/) continua tipado',
      len(_con.execute('DESCRIBE refdata').fetchall()) > 2, True)
_con.close()
_p = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'slim_duckdb.py'), '--db-dir', OUT],
                    capture_output=True, text=True, env=dict(os.environ))
check('7. rodar de novo pula o que ja esta magro', 'já magro' in _p.stdout, True)
check('7. e nao deixa .slim para tras', os.path.isfile(_VELHO + '.slim'), False)

# O banco emagrecido continua GRAVÁVEL. O slim copiava toda tabela com
# `CREATE TABLE … AS SELECT`, que leva os dados e DEIXA A PRIMARY KEY para trás
# — e sem ela o `INSERT OR REPLACE` do `manifest_record` estoura em
# `Binder Error: There are no UNIQUE/PRIMARY KEY constraints` (§443). O banco
# virava somente-leitura sem aviso nenhum: o Delete do New Deals tirava o deal
# da tela e morria no banco, e o Index B3 dizia "Added!" sem gravar.
_con = duckdb.connect(_VELHO)
try:
    core.manifest_record(_con, core.manifest_key_of(_REL1, core.KIND_DAILY),
                         core._Stamp(9.0, 90), ['main.d_20260101'])
    _erro_grav = ''
except Exception as _exc:                                     # noqa: BLE001
    _erro_grav = '%s: %s' % (type(_exc).__name__, _exc)
_linhas_man = _con.execute('SELECT count(*), max(mtime) FROM _manifest WHERE path = ?',
                           [core.manifest_key_of(_REL1, core.KIND_DAILY)]).fetchall()
_con.close()
check('7. o banco emagrecido continua GRAVAVEL (o _manifest guardou a chave)', _erro_grav, '')
check('7.   e o registro foi TROCADO, nao duplicado', _linhas_man, [(1, 9.0)])
check('7.   a PRIMARY KEY do _manifest sobreviveu ao slim',
      bool(duckdb.connect(_VELHO, read_only=True).execute(
          "SELECT count(*) FROM information_schema.table_constraints "
          "WHERE table_name='_manifest' AND constraint_type='PRIMARY KEY'").fetchone()[0]), True)

# ═══ 8. recover_duckdb_wal.py: o banco em LIMBO de checkpoint sai dele fora do share ═
# O estado da instância (§442): `.wal.checkpoint` ao lado do `.db` — um
# checkpoint começou e o processo morreu — e toda abertura refazendo o replay
# pelo share. Aqui o limbo é FABRICADO num subprocesso: escrita concorrente
# durante um checkpoint que o `debug_checkpoint_abort` interrompe, e o
# processo sai sem fechar. Fica `.db` + `.wal` + `.wal.checkpoint`.
print()
import io                                                     # noqa: E402
import shutil                                                 # noqa: E402
import tempfile                                               # noqa: E402
_LIMBO_DIR = os.path.join(OUT, 'cache', 'limbo')
os.makedirs(_LIMBO_DIR, exist_ok=True)
_LIMBO = os.path.join(_LIMBO_DIR, 'preso.db')
_REL3 = 'cache/limbo/2026/02/20260201_preso.json'
_FAB = os.path.join(OUT, '_fabrica_limbo.py')
with io.open(_FAB, 'w', encoding='utf-8') as _fh:
    _fh.write('''import os, sys, threading, time, json
sys.path.insert(0, %r)
import duckdb
from apps.pages import json_to_duckdb as core
db = %r
con = duckdb.connect(db)
core.ensure_manifest(con)
rows = [{'Deal': 'L%%d' %% i, 'SPN': '00%%d' %% i, 'Qty': i} for i in range(3000)]
core.write_rows_table(con, 'main.d_20260201', core._com_raw(rows))
core.manifest_record(con, core.manifest_key_of(%r, core.KIND_DAILY), core._Stamp(3.0, 30), ['main.d_20260201'])
con.execute('CHECKPOINT')
con.execute("CREATE TABLE main.lastro AS SELECT range i, repeat('x', 200) s FROM range(200000)")
con.execute("SET debug_checkpoint_abort='before_header'")
def escreve():
    k = con.cursor()
    for i in range(40):
        try:
            k.execute("INSERT INTO main.lastro VALUES (%%d, 'z')" %% (900000 + i))
        except Exception:
            return
        time.sleep(0.02)
th = threading.Thread(target=escreve); th.start()
time.sleep(0.1)
try:
    con.execute('CHECKPOINT')
except Exception:
    pass
th.join(5)
# O `.wal.checkpoint` nasce quando uma gravacao concorrente COMMITA durante o
# checkpoint (`WALStartCheckpoint` o cria vazio e lazy); num SSD o checkpoint
# acaba antes do commit seguinte, entao o arquivo e posto aqui, VAZIO — o
# estado exato que o DuckDB deixa quando o processo morre entre o inicio do
# checkpoint e a primeira gravacao concorrente (provado a mao: o rw open o
# consome). O `.wal` ao lado e REAL, do checkpoint abortado.
open(db + '.wal.checkpoint', 'wb').close()
print('FAB', json.dumps(sorted(os.path.basename(f) for f in os.listdir(os.path.dirname(db)))), flush=True)
os._exit(0)
''' % (ROOT, _LIMBO, _REL3))
_p = subprocess.run([sys.executable, _FAB], capture_output=True, text=True, env=dict(os.environ))
_irm = core_store_irmaos = None
from apps.pages import data_store as _S                       # noqa: E402
_irm = _S.wal_irmaos(_LIMBO)
check('8. a fabrica deixou o banco em limbo (.wal.checkpoint ao lado)',
      ('.wal.checkpoint' in _irm, _S.wal_em_limbo(_irm)), (True, True))
if '.wal.checkpoint' not in _irm:
    print(_p.stdout[-600:], _p.stderr[-600:])
check('8. wal_pendentes lista so ele',
      [os.path.basename(d) for d, _i in _S.wal_pendentes(OUT)], ['preso.db'])
_p = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'slim_duckdb.py'), '--db-dir', OUT],
                    capture_output=True, text=True, env=dict(os.environ))
check('8. o slim RECUSA o banco em limbo apontando o recover (rc 1)',
      (_p.returncode, 'recover_duckdb_wal' in _p.stdout, 'preso.db' in _p.stdout), (1, True, True))
check('8.   e nao deixa .slim para tras', os.path.isfile(_LIMBO + '.slim'), False)
check('8.   nem o resto do slim (velho.db segue magro)', 'já magro' in _p.stdout, True)
_WORK = tempfile.mkdtemp(prefix='recover-work-')
_p = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'recover_duckdb_wal.py'),
                     '--db-dir', OUT, '--work-dir', _WORK, '--dry-run'],
                    capture_output=True, text=True, env=dict(os.environ))
check('8. --dry-run lista o banco e os MB sem tocar em nada',
      (_p.returncode, 'preso.db' in _p.stdout, '.wal.checkpoint' in _p.stdout,
       '.wal.checkpoint' in _S.wal_irmaos(_LIMBO)), (0, True, True, True))
# Com alguem VIVO segurando o arquivo (a instancia de pe, ou o `store-import`
# preso meia hora dentro do duckdb.connect) a trava exclusiva nao vem: o banco
# e PULADO com um recado de uma linha, nao com traceback, e nada e tocado.
from apps.pages import database_access as _DA                 # noqa: E402
_trava_teste = _DA.hold_file_lock(_LIMBO, write=True, timeout_seconds=10)
try:
    _p = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'recover_duckdb_wal.py'),
                         '--db-dir', OUT, '--work-dir', _WORK, '--lock-seconds', '1'],
                        capture_output=True, text=True, env=dict(os.environ))
finally:
    _trava_teste.release()
check('8. banco preso por outro processo e PULADO com recado, sem traceback (rc 1)',
      (_p.returncode, 'EM USO' in _p.stdout, 'pare TODAS as instâncias' in _p.stdout,
       'Traceback' in _p.stdout), (1, True, True, False))
check('8.   e o banco preso ficou como estava',
      ('.wal.checkpoint' in _S.wal_irmaos(_LIMBO), os.path.isfile(_LIMBO + '.novo')), (True, False))

# O arquivo do share pode vir SOMENTE-LEITURA, e o `copy2` leva o atributo para a
# copia local: ai o rename com que o DuckDB funde os WALs morre em `Could not move
# file: Access is denied` DENTRO da copia, com a trava do share na mao. A copia tem
# de perder o atributo antes de abrir.
for _s in ('',) + _S.WAL_SUFIXOS:
    if os.path.isfile(_LIMBO + _s):
        os.chmod(_LIMBO + _s, 0o444)
# Pasta de trabalho que nao deixa RENOMEAR (politica, %LOCALAPPDATA% redirecionado)
# e dita ANTES de copiar 1,2 GB pelo share, com o remedio, e sem traceback.
_TRAVADA = tempfile.mkdtemp(prefix='recover-ro-')
os.chmod(_TRAVADA, 0o555)
try:
    _p = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'recover_duckdb_wal.py'),
                         '--db-dir', OUT, '--work-dir', _TRAVADA],
                        capture_output=True, text=True, env=dict(os.environ))
finally:
    os.chmod(_TRAVADA, 0o755)
check('8. pasta de trabalho sem renome e recusada ANTES da copia, com o remedio',
      (_p.returncode, 'NÃO deixa renomear' in _p.stdout, '--work-dir' in _p.stdout,
       'Traceback' in _p.stdout, 'copiado' in _p.stdout), (1, True, True, False, False))
shutil.rmtree(_TRAVADA, ignore_errors=True)
# E o acesso negado passageiro (o antivirus lendo os MB recem-escritos) e RETENTADO.
_prova = subprocess.run([sys.executable, '-c', """
import os, sys, duckdb
sys.path.insert(0, os.path.join(%r, 'scripts'))
import recover_duckdb_wal as R
db = os.path.join(%r, 'retry.db')
duckdb.connect(db).close()
real, chamadas = duckdb.connect, []
def falso(*a, **k):
    chamadas.append(1)
    if len(chamadas) == 1:
        raise duckdb.IOException('IO Error: Could not move file: Access is denied.')
    return real(*a, **k)
duckdb.connect = falso
R._recupera_local(db, tentativas=3, espera=0)
print('TENTATIVAS', len(chamadas))
""" % (ROOT, _WORK)], capture_output=True, text=True, env=dict(os.environ))
check('8. acesso negado na copia local e RETENTADO, nao mata o banco',
      (_prova.returncode, 'TENTATIVAS 2' in _prova.stdout,
       'acesso negado na cópia local' in _prova.stdout), (0, True, True))

_p = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'recover_duckdb_wal.py'),
                     '--db-dir', OUT, '--work-dir', _WORK],
                    capture_output=True, text=True, env=dict(os.environ))
check('8. o recover roda (rc 0)', _p.returncode, 0)
if _p.returncode:
    print(_p.stdout[-1200:], _p.stderr[-1200:])
check('8. nenhum WAL sobrou ao lado do .db', _S.wal_irmaos(_LIMBO), {})
check('8. o banco abre e o dia volta EXATO (com o que estava so no WAL)',
      core.ler_payload(duckdb.connect(_LIMBO, read_only=True), _REL3, core.KIND_DAILY, 'd_20260201')[:2],
      [{'Deal': 'L0', 'SPN': '000', 'Qty': 0}, {'Deal': 'L1', 'SPN': '001', 'Qty': 1}])
_con = duckdb.connect(_LIMBO, read_only=True)
check('8. e saiu MAGRO de caminho (a tabela-dia so _seq/_raw)',
      [d[:2] for d in _con.execute('DESCRIBE main.d_20260201').fetchall()],
      [('_seq', 'BIGINT'), ('_raw', 'VARCHAR')])
check('8. o lastro gravado durante o checkpoint interrompido esta la',
      _con.execute('SELECT count(*) FROM main.lastro').fetchone()[0] >= 200000, True)
_con.close()
_guarda = os.path.join(OUT, _S.RECUPERADO_DIR)
_guardados = sorted(f for _d, _ds, fs in os.walk(_guarda) for f in fs)
check('8. o .db velho e os WALs foram para db/_recuperado/<carimbo>/cache/limbo',
      (_guardados[:1], any(f.endswith('.wal.checkpoint') for f in _guardados),
       os.path.isdir(os.path.join(_guarda, os.listdir(_guarda)[0], 'cache', 'limbo'))),
      (['preso.db'], True, True))
check('8. wal_pendentes nao ve mais nada (e nao entra na pasta do recover)', _S.wal_pendentes(OUT), [])
_p = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'recover_duckdb_wal.py'),
                     '--db-dir', OUT, '--work-dir', _WORK],
                    capture_output=True, text=True, env=dict(os.environ))
check('8. rodar de novo nao acha nada', (_p.returncode, '0 banco(s)' in _p.stdout), (0, True))
_p = subprocess.run([sys.executable, os.path.join(ROOT, 'scripts', 'slim_duckdb.py'), '--db-dir', OUT],
                    capture_output=True, text=True, env=dict(os.environ))
check('8. e o slim passa a pular o recuperado como ja magro (e nao entra em _recuperado)',
      (_p.returncode, _p.stdout.count('já magro') >= 2, '_recuperado' in _p.stdout), (0, True, False))
shutil.rmtree(_WORK, ignore_errors=True)

print()
if fails:
    print('FAILED: %d check(s)' % len(fails))
    sys.exit(1)
print('all ok')
sys.exit(0)
