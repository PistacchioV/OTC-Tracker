"""check_duck_read.py — o ARMAZÉM DB-only (HANDOFF §434): escrita e leitura
só nos bancos, sem espelho e sem JSON.

O `data_store` apresenta o `DATA_DIR` como um sistema de arquivos virtual
sobre os DuckDB de sempre. O que este script prova, em tempfile:
  1. o FUNIL (`_atomic_write_json`) grava no banco e NÃO escreve JSON; a
     leitura vem DO BANCO (provado adulterando a tabela);
  2. a gravação seguinte vale na hora (memo invalidado pelo stat do .db);
  3. RefData/CPD e os índices derivados do routes leem do banco;
  4. calendários: registro e arquivos de feriado pelo banco, data ISO;
  5. payload-OBJETO (recon, `.meta.json`, ponteiro `_last`) volta EXATO;
  6. caminho ausente: `read` levanta FileNotFoundError, `day_payload` dá
     None, `isfile` False — e o JSON LEGADO em disco é importado na primeira
     leitura (uma vez);
  7. OCUPADO: a disputa persistente serve a última cópia em memória e, sem
     cópia, levanta BancoOcupado; a janela pula o banco; leitura boa limpa;
  8. enumeração pelo banco: `isdir`, `listdir`, `walk`, `day_files` e o
     `_day_files` do daycache; `remove` apaga tabela e manifest;
  9. os cadastros do /mapping e o `static_data_file` respondem pelo banco.
Nada aqui toca em dado real.
"""
import json
import os
import sys
import tempfile
import time

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

import duckdb                                               # noqa: E402
from apps.pages import routes as R                          # noqa: E402
from apps.pages import data_store as S                      # noqa: E402
from apps.pages import duck_read as DR                      # noqa: E402
from apps.pages import database_access as DA                # noqa: E402
from apps.pages.features.holidays.infra import persistence as HP   # noqa: E402

TMP = tempfile.mkdtemp(prefix='otc-store-')
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


def _p(*parts):
    return os.path.join(TMP, *parts)


# ── 1. o funil grava no banco, e a leitura vem dele ─────────────────────────
REF = _p('RefData.json')
R._atomic_write_json(REF, [{'COUNTERPARTY': 'ACME LTDA', 'SPN': '007135',
                            'TAX ID': '45.985.371/0001-08'}])
check('1. nenhum JSON foi escrito no disco', os.path.exists(REF), False)
check('1. o banco nasceu', os.path.isfile(os.path.join(DBDIR, 'reference_data.db')))
check('1. a leitura responde', DR.refdata_rows()[0]['SPN'], '007135')
_tamper('reference_data.db',
        'UPDATE refdata SET "_raw" = \'{"COUNTERPARTY": "ACME LTDA", "SPN": "999999"}\'')
S.memo_forget()
check('1. a leitura veio DO BANCO (a adulteracao aparece)', DR.refdata_rows()[0]['SPN'], '999999')
check('1. isfile pelo manifest', S.isfile(REF), True)
check('1. stat pelo manifest (mtime recente)', abs(S.getmtime(REF) - time.time()) < 60)

# ── 2. a gravação seguinte vale na hora ─────────────────────────────────────
R._atomic_write_json(REF, [{'COUNTERPARTY': 'ACME LTDA', 'SPN': '111111', 'TAX ID': '1'}])
check('2. regravado, a leitura muda sem restart', DR.refdata_rows()[0]['SPN'], '111111')
R._REFDATA_TRIPLE_CACHE['mtime'] = None
check('2. o indice derivado do routes le do banco',
      R._refdata_records()[0]['SPN'], '111111')

# ── 3. CounterpartyDetails ──────────────────────────────────────────────────
CPD = _p('CounterpartyDetails.json')
R._cpd_save_list([{'SPN': '111111', 'NET': 'Total Net', 'CONTACTS': [{'name': 'x'}]}])
check('3. CPD pelo banco, chave ausente preservada',
      DR.cpd_records(), [{'SPN': '111111', 'NET': 'Total Net', 'CONTACTS': [{'name': 'x'}]}])
check('3. sem JSON em disco', os.path.exists(CPD), False)

# ── 4. calendários ──────────────────────────────────────────────────────────
HP._cache['mtime'] = None
regs = HP.calendars()
check('4. registro sem banco = seed', bool(regs) and 'name' in regs[0])
R._atomic_write_json(HP.registry_path(), [{'name': 'ANBIMA', 'file': 'anbima.json', 'color': '#111'},
                                          {'name': 'TESTE', 'file': 'teste-cal.json', 'color': '#222'}])
S._cal_forget()
check('4. registro pelo banco', [r['name'] for r in HP.calendars()], ['ANBIMA', 'TESTE'])
HP.write_holidays('teste-cal.json', [{'date': '2026-12-25', 'title': 'Natal', 'calendar': 'TESTE'},
                                     {'date': '2026-12-25', 'title': 'Natal 2', 'calendar': 'TESTE'}])
check('4. feriados pelo banco, data ISO e ordem do arquivo',
      HP.load_holidays('teste-cal.json'),
      [{'date': '2026-12-25', 'title': 'Natal', 'calendar': 'TESTE'},
       {'date': '2026-12-25', 'title': 'Natal 2', 'calendar': 'TESTE'}])
check('4. calendar_dates', DR.calendar_dates(_p('teste-cal.json')), {'2026-12-25'})
check('4. a tabela do calendario e TIPADA (date DATE)',
      duckdb.connect(os.path.join(DBDIR, 'holiday_calendars.db'), read_only=True)
      .execute('SELECT typeof("date") FROM %s LIMIT 1'
               % S.core.q(S.core.norm_ident('TESTE', 'cal'))).fetchone()[0], 'DATE')

# ── 5. payload-objeto volta exato ───────────────────────────────────────────
REC = _p('cache', 'reconciliation', 'fxo', '2026', '06', 'recon-fxo_20260612.json')
obj = {'meta': {'date': '2026-06-12', 'n': 3}, 'rows': [{'a': 1}, {'a': 2}], 'vazio': [], 'x': None}
R._atomic_write_json(REC, obj)
check('5. objeto volta EXATO (chaves, ordem, vazio, None)', S.read(REC), obj)
META = _p('cache', 'daily settlement', '2026', '06', '12', 'cognos_20260612.meta.json')
R._atomic_write_json(META, {'updated': '10:00:00', 'source': 'x.xlsx'})
check('5. .meta.json volta exato', S.read(META), {'updated': '10:00:00', 'source': 'x.xlsx'})
LAST = _p('cache', 'new deals', 'NDF', '_last.json')
R._atomic_write_json(LAST, {'date': '2026-06-12'})
check('5. ponteiro _last vira dataset e volta', S.read(LAST), {'date': '2026-06-12'})
check('5. objetos NOVOS a cada leitura', S.read(REC) is not S.read(REC))

# ── 6. ausente, e o legado em disco ─────────────────────────────────────────
NADA = _p('cache', 'new deals', 'NDF', 'Commodities', '2026', '06', '20260613_ndfcomm.json')
check('6. day_payload de caminho ausente = None', DR.day_payload(NADA), None)
check('6. isfile False', S.isfile(NADA), False)
try:
    S.read(NADA)
    check('6. read ausente levanta FileNotFoundError', False)
except FileNotFoundError:
    check('6. read ausente levanta FileNotFoundError', True)
LEG = _p('cache', 'new deals', 'NDF', 'Commodities', '2026', '06', '20260611_ndfcomm.json')
os.makedirs(os.path.dirname(LEG), exist_ok=True)
with open(LEG, 'w', encoding='utf-8') as fh:
    json.dump([{'Deal': 'LEG-1'}], fh)
check('6. isfile ve o legado em disco', S.isfile(LEG), True)
check('6. a primeira leitura serve e IMPORTA', DR.day_records(LEG), [{'Deal': 'LEG-1'}])
os.remove(LEG)
S.memo_forget()
check('6. importado: responde sem o arquivo', DR.day_records(LEG), [{'Deal': 'LEG-1'}])

# ── 7. OCUPADO ──────────────────────────────────────────────────────────────
OCUP = _p('cache', 'new deals', 'NDF', 'Commodities', '2026', '06', '20260612_ndfcomm.json')
R._atomic_write_json(OCUP, [{'Deal': 'OC-1'}])
check('7. antes, o banco responde', DR.day_payload(OCUP), [{'Deal': 'OC-1'}])
_dr_real = S.duckdb_read
_chamadas = []


def _ocupado(path, **kw):
    _chamadas.append(os.path.basename(str(path)))
    raise DA.DatabaseLockTimeout(str(path), 'read', 0.1)


S.duckdb_read = _ocupado
S.ocupado_forget()
S._ocupado_aviso['ate'] = 0.0
# manifest esquecido e a copia (agora "velha") ainda no memo: a leitura tenta o
# banco, perde a disputa (com a retentativa) e serve a ultima copia boa
S._forget_db(os.path.join(DBDIR, 'cache', 'new deals', 'NDF', 'Commodities.db'))
check('7. banco ocupado: serve a ultima copia em memoria', DR.day_payload(OCUP), [{'Deal': 'OC-1'}])
check('7. com UMA retentativa antes de desistir', _chamadas.count('Commodities.db'), 2)
_chamadas[:] = []
check('7. dentro da janela o banco nem e tentado', (DR.day_payload(OCUP), len(_chamadas)), ([{'Deal': 'OC-1'}], 0))
check('7. a janela e curta e configuravel', 0 < S._OCUPADO_JANELA <= 300)
S.ocupado_forget()
S.memo_forget()
S._forget_db(os.path.join(DBDIR, 'cache', 'new deals', 'NDF', 'Commodities.db'))
try:
    S.read(OCUP)
    check('7. sem copia em memoria, BancoOcupado (nunca "nao ha dado")', False)
except S.BancoOcupado:
    check('7. sem copia em memoria, BancoOcupado (nunca "nao ha dado")', True)
check('7. e isfile responde False sem estourar', S.isfile(OCUP), False)
S.duckdb_read = _dr_real
S.ocupado_forget()
check('7. passada a disputa, o banco volta a responder', DR.day_payload(OCUP), [{'Deal': 'OC-1'}])
check('7. e a leitura que deu certo limpa a marca',
      S._ocupado_marcado(os.path.join(DBDIR, 'cache', 'new deals', 'NDF', 'Commodities.db')), False)

# ── 8. enumeração e remoção ─────────────────────────────────────────────────
RAIZ = _p('cache', 'new deals', 'NDF', 'Commodities')
check('8. isdir pelo banco (sem pasta no disco)', S.isdir(RAIZ) and not os.path.isdir(_p('cache', 'new deals', 'NDF', 'Commodities', '2026', '07')))
dias = list(R._day_files(RAIZ, '_ndfcomm.json'))
check('8. _day_files do daycache enumera pelo banco',
      [t[1] for t in dias], ['20260611_ndfcomm.json', '20260612_ndfcomm.json'])
check('8. day_files leva mtime e tamanho', all(t[2] > 0 and t[3] > 0 for t in dias))
check('8. listdir', S.listdir(_p('cache', 'new deals', 'NDF', 'Commodities', '2026', '06')),
      ['20260611_ndfcomm.json', '20260612_ndfcomm.json'])
check('8. listdir da raiz de dados inclui RefData e o registro',
      {'RefData.json', 'holiday-calendars.json', 'cache'} <= set(S.listdir(TMP)))
arv = list(S.walk(RAIZ))
check('8. walk top-down', (os.path.basename(arv[0][0]), arv[0][1], arv[-1][2]),
      ('Commodities', ['2026'], ['20260611_ndfcomm.json', '20260612_ndfcomm.json']))
S.remove(LEG)
check('8. remove tira do banco', S.isfile(LEG), False)
check('8. e da enumeracao', [t[1] for t in R._day_files(RAIZ, '_ndfcomm.json')], ['20260612_ndfcomm.json'])
check('8. prefetch aquece em lote', R._day_prefetch(list(R._day_files(RAIZ))) >= 0)

# ── 9. mappings e o /static/data ────────────────────────────────────────────
R._MAPPINGS_DIR = _p('mappings')
R._mapping_cache.clear()
R._atomic_write_json(_p('mappings', 'le-spn.json'), [{'LE': 'JPM', 'SPN': '1', 'NAME': 'BANCO'}])
check('9. _mapping_rows le do banco (o upgrade completa as LEs do seed)',
      [r for r in R._mapping_rows('le-spn') if r.get('LE') == 'JPM'], [{'LE': 'JPM', 'SPN': '1', 'NAME': 'BANCO'}])
from apps import create_app                                 # noqa: E402
from apps.config import DebugConfig                         # noqa: E402
app = create_app(DebugConfig)
app.config['TESTING'] = True
with app.test_request_context('/static/data/mappings/le-spn.json'):
    resp = R._duck_static_json('mappings/le-spn.json')
check('9. /static/data/<mapping>.json sai do banco',
      json.loads(resp.get_data(as_text=True)) if resp is not None else None,
      [{'LE': 'JPM', 'SPN': '1', 'NAME': 'BANCO'}])
with app.test_request_context('/'):
    resp = R._duck_static_json('translations/en.json')
check('9. translations fica no disco', resp, None)

print()
print('FAIL: %d' % len(fails) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
