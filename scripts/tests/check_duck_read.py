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
  9. os cadastros do /mapping e o `static_data_file` respondem pelo banco;
  10. a gravação é ATÔMICA: uma que estoura depois de derrubar as tabelas
     deixa o dado anterior e o carimbo anterior (ROLLBACK desfaz o DDL).
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
_fs_real, _fs_n = S._read_fs_text, []
S._read_fs_text = lambda path: (_fs_n.append(path), _fs_real(path))[1]
check('6. a segunda leitura do legado vem do memo (nao rele o arquivo do share)',
      (DR.day_records(LEG), _fs_n), ([{'Deal': 'LEG-1'}], []))
S._read_fs_text = _fs_real
check('6. a importacao roda FORA do request (thread) e termina', S.import_wait(60), True)
os.remove(LEG)
S.memo_forget()
check('6. importado: responde sem o arquivo', DR.day_records(LEG), [{'Deal': 'LEG-1'}])
check('6. a importacao desiste se o banco ja tem o caminho (so_se_ausente)',
      S.write(LEG, [{'Deal': 'PERDIDO'}], so_se_ausente=True), False)
check('6.   e o que estava no banco fica', DR.day_records(LEG), [{'Deal': 'LEG-1'}])

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
S._forget_db(os.path.join(DBDIR, 'cache', 'new deals', 'NDF', 'Commodities.db'))
check('7. com copia em memoria, isfile responde True sob OCUPADO', S.isfile(OCUP), True)
check('7. e stat responde com o carimbo da copia', S.stat(OCUP).st_size > 0, True)
S.ocupado_forget()
S.memo_forget()
S._forget_db(os.path.join(DBDIR, 'cache', 'new deals', 'NDF', 'Commodities.db'))
try:
    S.read(OCUP)
    check('7. sem copia em memoria, BancoOcupado (nunca "nao ha dado")', False)
except S.BancoOcupado:
    check('7. sem copia em memoria, BancoOcupado (nunca "nao ha dado")', True)
# OCUPADO nunca e "nao existe" (§434, varredura de 10/09): `isfile` sobe
# BancoOcupado — lido como False, o read-modify-write dos handlers gravaria so
# o registro novo por cima do dia inteiro quando a vizinha soltasse a trava.
try:
    S.isfile(OCUP)
    check('7. e isfile sob OCUPADO levanta BancoOcupado (nunca False)', 'nao levantou', True)
except S.BancoOcupado:
    check('7. e isfile sob OCUPADO levanta BancoOcupado (nunca False)', True, True)
# ── 7b. ILEGÍVEL: o .db existe e o DuckDB nao o abre ─────────────────────────
# E a mesma classe do ocupado (§441): lido como vazio, isfile dizia False e a
# enumeracao vinha vazia — um `.wal` de outra versao do duckdb bastava.
S.duckdb_read = _dr_real
S.ocupado_forget()
S.memo_forget()
_DBC = os.path.join(DBDIR, 'cache', 'new deals', 'NDF', 'Commodities.db')
S._forget_db(_DBC)
check('7b. antes, o banco responde', DR.day_payload(OCUP), [{'Deal': 'OC-1'}])
with open(_DBC, 'rb') as fh:
    _cabecalho = fh.read(4096)
with open(_DBC, 'r+b') as fh:
    fh.seek(0)
    fh.write(b'\x00' * 4096)
S._forget_db(_DBC)
check('7b. com copia em memoria, serve a ultima copia boa', DR.day_payload(OCUP), [{'Deal': 'OC-1'}])
S.memo_forget()
S._forget_db(_DBC)
for _nome, _fn in (('read', lambda: S.read(OCUP)), ('isfile', lambda: S.isfile(OCUP)),
                   ('exists', lambda: S.exists(OCUP)), ('stat', lambda: S.stat(OCUP))):
    try:
        _fn()
        check('7b. %s de banco ilegivel levanta BancoIlegivel (nunca "nao ha")' % _nome, 'nao levantou', 'BancoIlegivel')
    except S.BancoIlegivel:
        check('7b. %s de banco ilegivel levanta BancoIlegivel (nunca "nao ha")' % _nome, 'BancoIlegivel', 'BancoIlegivel')
check('7b. e BancoIlegivel e um BancoOcupado (mesmos handlers, mesmo 503)',
      issubclass(S.BancoIlegivel, S.BancoOcupado) and issubclass(S.BancoIlegivel, IOError), True)
with open(_DBC, 'r+b') as fh:
    fh.seek(0)
    fh.write(_cabecalho)
S._forget_db(_DBC)
check('7b. arquivo restaurado, o banco volta a responder', DR.day_payload(OCUP), [{'Deal': 'OC-1'}])
S.duckdb_read = _ocupado

# E o `data_path()` (a queda para a copia do repositorio) le OCUPADO como
# EXISTE: lido como "nao ha", o cadastro editado pela mesa virava a seed do
# repositorio enquanto durasse a trava (§440).
from apps.pages import data_paths as DP                     # noqa: E402
_exists_real = S.exists
S.exists = lambda path: (_ for _ in ()).throw(S.BancoOcupado(path))
try:
    check('7. data_path: OCUPADO conta como existe no DATA_DIR (nao cai para o pacote)',
          DP._existe(OCUP), True)
finally:
    S.exists = _exists_real
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

# ── 10. a gravação é ATÔMICA: falha no meio não perde o dado anterior ───────
# `escrever_payload` começa DERRUBANDO as tabelas do caminho (`_drop_targets`)
# e só depois cria as novas e regrava o manifest. Tudo isso roda dentro da
# transação do `duckdb_write` (BEGIN antes do corpo, ROLLBACK na exceção) — e
# o DuckDB desfaz DDL também. Sem isso, uma gravação que estourasse depois do
# DROP deixaria o caminho sem tabela e o manifest apontando para ela.
ATOM = _p('cache', 'new deals', 'NDF', 'Commodities', '2026', '06', '20260614_ndfcomm.json')
R._atomic_write_json(ATOM, [{'Deal': 'ANTES-1'}, {'Deal': 'ANTES-2'}])
_stamp_antes = (S.stat(ATOM).st_mtime, S.stat(ATOM).st_size)
_escrever_real = S.core.escrever_payload


def _escrever_e_estoura(con, rel, payload, kind, tabela, schema='main', **kw):
    _escrever_real(con, rel, payload, kind, tabela, schema, **kw)   # DROP + CREATE + manifest
    raise RuntimeError('estourou depois de reescrever')


S.core.escrever_payload = _escrever_e_estoura
try:
    R._atomic_write_json(ATOM, [{'Deal': 'DEPOIS-1'}])
    check('10. a gravacao que estoura LEVANTA (nao engole)', False)
except RuntimeError:
    check('10. a gravacao que estoura LEVANTA (nao engole)', True)
finally:
    S.core.escrever_payload = _escrever_real
S.memo_forget()
S._forget_db(os.path.join(DBDIR, 'cache', 'new deals', 'NDF', 'Commodities.db'))
check('10. e o dado ANTERIOR continua la (ROLLBACK desfez o DROP e o manifest)',
      [d['Deal'] for d in S.read(ATOM)], ['ANTES-1', 'ANTES-2'])
check('10. com o carimbo anterior no manifest', (S.stat(ATOM).st_mtime, S.stat(ATOM).st_size), _stamp_antes)
check('10. e o vizinho de banco nao foi tocado', S.read(OCUP), [{'Deal': 'OC-1'}])
R._atomic_write_json(ATOM, [{'Deal': 'DEPOIS-2'}])
check('10. a gravacao seguinte vale normalmente', [d['Deal'] for d in S.read(ATOM)], ['DEPOIS-2'])

print('\n== 11. a sonda do limbo de checkpoint (§442) ==')
# So nomes e tamanhos: e o que o DuckDB deixa no disco quando um checkpoint
# comecou e o processo morreu (.wal.checkpoint) ou quando a abertura em
# escrita fundiu os WALs (.wal.recovery). O `.wal` sozinho e normal ate o teto.
import logging as _logging                                 # noqa: E402
import shutil                                              # noqa: E402
_LB = tempfile.mkdtemp(prefix='limbo-')
_lb = lambda *p: os.path.join(_LB, *p)                     # noqa: E731
os.makedirs(_lb('cache', 'x'))
os.makedirs(_lb(S.RECUPERADO_DIR, '20260910-120000', 'cache'))
for nome, tam in (('cache/x/a.db', 10), ('cache/x/a.db.wal', 100),
                  ('cache/x/b.db', 10), ('cache/x/b.db.wal', 100), ('cache/x/b.db.wal.checkpoint', 0),
                  ('cache/x/c.db', 10), ('cache/x/c.db.wal.recovery', 5),
                  ('cache/x/d.db', 10), ('cache/x/d.db.wal', int(S.WAL_LIMBO_MB * 1e6) + 1),
                  ('cache/x/e.db', 10),
                  (S.RECUPERADO_DIR + '/20260910-120000/cache/z.db', 10),
                  (S.RECUPERADO_DIR + '/20260910-120000/cache/z.db.wal.checkpoint', 0)):
    with open(_lb(*nome.split('/')), 'wb') as fh:
        fh.write(b'\0' * tam)
check('11. .wal pequeno sozinho nao e limbo', S.wal_em_limbo(S.wal_irmaos(_lb('cache', 'x', 'a.db'))), False)
check('11. .wal.checkpoint e limbo (mesmo vazio)', S.wal_em_limbo(S.wal_irmaos(_lb('cache', 'x', 'b.db'))), True)
check('11. .wal.recovery e limbo', S.wal_em_limbo(S.wal_irmaos(_lb('cache', 'x', 'c.db'))), True)
check('11. .wal alem do teto e limbo', S.wal_em_limbo(S.wal_irmaos(_lb('cache', 'x', 'd.db'))), True)
check('11. sem irmao nenhum', S.wal_irmaos(_lb('cache', 'x', 'e.db')), {})
check('11. wal_pendentes lista b, c, d — e nao entra em _recuperado',
      [os.path.basename(d) for d, _i in S.wal_pendentes(_LB)], ['b.db', 'c.db', 'd.db'])


class _Pega(_logging.Handler):
    def __init__(self):
        _logging.Handler.__init__(self)
        self.msgs = []

    def emit(self, rec):
        self.msgs.append(rec.getMessage())


_h = _Pega()
_logging.getLogger('otc_tracker').addHandler(_h)
_db_root_real = S.db_root
S.db_root = lambda raiz=None: _LB
try:
    from apps import _warn_wal_pendente
    _warn_wal_pendente()
finally:
    S.db_root = _db_root_real
    _logging.getLogger('otc_tracker').removeHandler(_h)
_avisos = [m for m in _h.msgs if 'RECUPERAÇÃO DE CHECKPOINT' in m]
check('11. a subida avisa UMA vez por banco em limbo, nomeando o script',
      (len(_avisos), all('recover_duckdb_wal' in m for m in _avisos),
       sorted(os.path.basename(m.split(' — ')[0].split(': ')[-1]) for m in _avisos)),
      (3, True, ['b.db', 'c.db', 'd.db']))

# O OUTRO estado do §442: o WAL que NAO REPLAYA. Nao e limbo (o `.wal` e
# pequeno e esta sozinho) e nenhuma abertura passa dele — o aviso de banco
# ILEGIVEL tem de trazer o comando com o --descartar-wal, senao o log so
# repete o traceback a cada request.
check('11. wal_replay_falhou reconhece o replay que estoura',
      (S.wal_replay_falhou(Exception('Catalog Error: Failure while replaying WAL file '
                                     '"p.db.wal": Table with name "d_20260119" already exists!')),
       S.wal_replay_falhou(Exception('IO Error: Could not move file'))),
      (True, False))
_h2 = _Pega()
_logging.getLogger('otc_tracker').addHandler(_h2)
_db_root_real2 = S.db_root
S.db_root = lambda raiz=None: _LB
try:
    S._ilegivel_aviso.clear()
    S._ilegivel_avisa(_lb('cache', 'x', 'a.db'),
                      Exception('Catalog Error: Failure while replaying WAL file "a.db.wal": '
                                'Table with name "d_20260119" already exists!'))
    S._ilegivel_aviso.clear()
    S._ilegivel_avisa(_lb('cache', 'x', 'e.db'), Exception('database is truncated'))
finally:
    S.db_root = _db_root_real2
    _logging.getLogger('otc_tracker').removeHandler(_h2)
check('11. o aviso do WAL sem replay traz o comando e o --only do banco',
      ('--descartar-wal' in _h2.msgs[0] and 'cache/x/a.db' in _h2.msgs[0],
       '--descartar-wal' in _h2.msgs[1]),
      (True, False))
shutil.rmtree(_LB, ignore_errors=True)

print('\n== 12. o payload-objeto anterior ao __raw (SemCanal, §442) ==')
# O banco converteu o objeto antes de existir a `__raw`: manifest o lista, mas
# não há canal exato. Era um IOError generico engolido pelo leitor ("template
# missing" no File Interpreter). Fabricado aqui derrubando a `__raw` e
# reescrevendo os targets do manifest.
TPL = _p('file-interpreter', 'sem-canal.json')
OBJ_TPL = {'key': 'sem-canal', 'blocks': [{'id': 'registro', 'fields': [{'seq': 1}]}], 'n': 2}
R._atomic_write_json(TPL, OBJ_TPL)
check('12. gravado pelo funil, tem o canal exato', S.tem_raw(TPL), True)
_alvo = S.core.target_of('file-interpreter/sem-canal.json')
_chave = S.core.manifest_key_of('file-interpreter/sem-canal.json', _alvo[3])
_con = duckdb.connect(os.path.join(DBDIR, 'file-interpreter', 'sem-canal.db'))
_tg = [t for t in json.loads(_con.execute('SELECT targets FROM _manifest WHERE path = ?', [_chave]).fetchone()[0])
       if not t.endswith('__raw')]
_con.execute('DROP TABLE %s' % S.core.q(_alvo[2] + '__raw'))
_con.execute('UPDATE _manifest SET targets = ? WHERE path = ?', [json.dumps(_tg), _chave])
_con.close()
S.memo_forget()
check('12. sem a __raw, tem_raw diz False', S.tem_raw(TPL), False)
check('12. e isfile continua True (o manifest o lista)', S.isfile(TPL), True)
try:
    S.read(TPL)
    check('12. read sem disco levanta SemCanal', 'nao levantou', 'SemCanal')
except S.SemCanal as exc:
    check('12. read sem disco levanta SemCanal (um IOError com o motivo)',
          (isinstance(exc, IOError), 'sem-canal.json' in str(exc), '__raw' in str(exc)), (True, True, True))
from apps.pages.platform import file_interpreter as FI    # noqa: E402
_h = _Pega()
_logging.getLogger('otc_tracker').addHandler(_h)
_fi_dir_real = R._FILE_INTERPRETER_DIR
R._FILE_INTERPRETER_DIR = _p('file-interpreter')
try:
    check('12. _fi_load le como ausente MAS avisa no log com o motivo',
          (FI._fi_load('sem-canal'), any('sem-canal' in m and 'ilegível' in m for m in _h.msgs)), (None, True))
finally:
    R._FILE_INTERPRETER_DIR = _fi_dir_real
    _logging.getLogger('otc_tracker').removeHandler(_h)
# o JSON legado ao lado: a leitura responde por ele e a importacao SUBSTITUI
os.makedirs(os.path.dirname(TPL), exist_ok=True)
with open(TPL, 'w', encoding='utf-8') as fh:
    json.dump(OBJ_TPL, fh)
S.memo_forget()
check('12. com o JSON em disco, read responde por ele', S.read(TPL), OBJ_TPL)
S.import_wait()
os.remove(TPL)
S.memo_forget()
check('12. e a importacao substituiu o objeto sem canal (le do banco, sem o disco)',
      (S.tem_raw(TPL), S.read(TPL)), (True, OBJ_TPL))
# a semeadura: objeto do repositorio que o banco tem SEM canal e reimportado
_con = duckdb.connect(os.path.join(DBDIR, 'file-interpreter', 'sem-canal.db'))
_con.execute('DROP TABLE %s' % S.core.q(_alvo[2] + '__raw'))
_con.execute('UPDATE _manifest SET targets = ? WHERE path = ?', [json.dumps(_tg), _chave])
_con.close()
S.memo_forget()
_PK = tempfile.mkdtemp(prefix='packaged-')
os.makedirs(os.path.join(_PK, 'file-interpreter'))
with open(os.path.join(_PK, 'file-interpreter', 'sem-canal.json'), 'w', encoding='utf-8') as fh:
    json.dump(dict(OBJ_TPL, n=99), fh)
with open(os.path.join(_PK, 'file-interpreter', 'lista.json'), 'w', encoding='utf-8') as fh:
    json.dump([{'a': 1}], fh)
R._atomic_write_json(_p('file-interpreter', 'lista.json'), [{'a': 'da tela'}])
from apps import _seed_data_dir                             # noqa: E402
from apps.pages import data_paths as _DP                    # noqa: E402


class _App(object):
    config = {'DATA_DIR': TMP}
    logger = _logging.getLogger('otc_tracker')


_pk_real = _DP.PACKAGED_DIR
_DP.PACKAGED_DIR = _PK
_h = _Pega()
_logging.getLogger('otc_tracker').addHandler(_h)
try:
    _seed_data_dir(_App())
finally:
    _DP.PACKAGED_DIR = _pk_real
    _logging.getLogger('otc_tracker').removeHandler(_h)
S.memo_forget()
check('12. a semeadura reimporta o objeto sem canal da copia do repositorio, avisando',
      (S.read(TPL).get('n'), any('sem-canal' in m and 'reimportado' in m for m in _h.msgs)), (99, True))
check('12.   e NAO sobrescreve a lista que o banco ja tem', S.read(_p('file-interpreter', 'lista.json')),
      [{'a': 'da tela'}])

# Banco ILEGIVEL na semeadura (o WAL que nao replaya, §447): como BancoIlegivel
# e subclasse de BancoOcupado, o ramo do ocupado engolia o caso e dizia "fica
# para a proxima subida" — que nunca chega, porque nenhuma abertura passa do
# replay. Tem de sair como ILEGIVEL, com o banco (do atributo, nao picado da
# mensagem) e o comando do recover.
with open(os.path.join(_PK, 'file-interpreter', 'ilegivel.json'), 'w', encoding='utf-8') as fh:
    json.dump({'x': 1}, fh)                    # o banco nao tem: a semeadura VAI gravar
with open(os.path.join(_PK, 'file-interpreter', 'quebrado.json'), 'w', encoding='utf-8') as fh:
    fh.write('{isso nao e json')               # falha ANTES do banco: e disco
_h = _Pega()
_logging.getLogger('otc_tracker').addHandler(_h)
_write_real = S.write
_ilegivel = S.BancoIlegivel('Catalog Error: Failure while replaying WAL file "x.db.wal": '
                            'Table with name "d_20260119" already exists!')
_ilegivel.db = os.path.join(DBDIR, 'cache', 'x', 'p.db')
_db_root_real3 = S.db_root


def _write_ilegivel(path, payload):
    raise _ilegivel


S.write = _write_ilegivel
S.db_root = lambda raiz=None: DBDIR
_DP.PACKAGED_DIR = _PK
try:
    _seed_data_dir(_App())
finally:
    S.write = _write_real
    S.db_root = _db_root_real3
    _DP.PACKAGED_DIR = _pk_real
    _logging.getLogger('otc_tracker').removeHandler(_h)
_ileg = [m for m in _h.msgs if 'ILEG' in m]
_leitura = [m for m in _h.msgs if 'ler a cópia do repositório' in m]
check('12. a semeadura separa ILEGIVEL de OCUPADO e traz o comando',
      (len(_ileg), bool(_ileg) and '--descartar-wal' in _ileg[0] and 'cache/x/p.db' in _ileg[0],
       any('ocupado por outra' in m for m in _h.msgs)),
      (1, True, False))
# e a falha de LER o arquivo do repositorio nao se disfarca de falha do banco
check('12. JSON do repositorio ilegivel sai como DISCO, com o tipo na linha',
      (len(_leitura), bool(_leitura) and 'quebrado.json' in _leitura[0]
       and 'JSONDecodeError' in _leitura[0]),
      (1, True))
shutil.rmtree(_PK, ignore_errors=True)

print()
print('FAIL: %d' % len(fails) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
