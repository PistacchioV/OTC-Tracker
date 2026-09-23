"""Track Confirmations: a gravação nunca troca a operação por uma CASCA (§546).

O defeito da mesa: linhas na esteira só com Trade ID, Callback Date e FepWeb ID
— sem produto, cliente, datas —, e o Monitor abrindo um card de Pending OTC
vazio ("no PDF in the confirmation folder", Generate). O caminho:

  * a edição em massa do Track manda só `{Trade ID, coluna: valor}`;
  * o `find_row` lia os bancos com a leitura TOLERANTE, que responde `[]`
    quando o banco está ocupado pela instância vizinha;
  * o endpoint fazia `find_row(key) or blank_row()` e o `upsert_row` apagava a
    chave dos dois bancos antes de inserir a casca.

O que se prova:
  1. a leitura de quem grava LEVANTA; a da tela segue tolerante;
  2. com a leitura falhando, o Save do Track não grava nada e a linha fica;
  3. edição de chave que não está na esteira é 404 — só o Add Row (`_new`) cria,
     e `_new` com chave existente é 409;
  4. o `upsert_row` não perde a linha quando o INSERT falha;
  5. o espelho do New Deals não sobrescreve a linha quando não consegue ler;
  6. `is_hollow` reconhece a casca;
  7. o `--repair` do backfill refaz a casca pelo deal e devolve o que ela tinha.

Bancos num diretório temporário; nada de dado real.
"""
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.check-share'))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

from apps.pages import manual_conf as M                          # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


M._DB_DIR = tempfile.mkdtemp(prefix='mc-hollow-db-')
M._MAPPINGS_DIR = tempfile.mkdtemp(prefix='mc-hollow-map-')

CHEIA = {'Trade ID': 'DSYJ-SNT1M', 'Produto': 'NDF COMM', 'LOB': 'CEM',
         'Cliente': 'MONDELEZ', 'Data Operação': '22/09/2026', 'Notional': '1000',
         'Moeda': 'ACUCAR'}
M.upsert_row(M.blank_row(**CHEIA))

from apps import create_app                                       # noqa: E402
from apps.config import DebugConfig                               # noqa: E402
from apps.pages import routes as R                                # noqa: E402
app = create_app(DebugConfig)
cl = app.test_client()
with cl.session_transaction() as s:
    s['authenticated'] = True
    s['user_sid'] = 'T000000'
    s['user_name'] = 'T'
    s['user_role'] = 'ADMIN'
    s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()


class Ocupado(IOError):
    pass


def _leitura_falha():
    orig = M.duckdb_read

    def _falha(*a, **k):
        raise Ocupado('banco ocupado pela instancia vizinha')
    M.duckdb_read = _falha
    return orig


print('== 1. leitura de quem grava levanta; a da tela segue tolerante ==')
orig = _leitura_falha()
try:
    check('load_all() da tela devolve vazio', M.load_all(), [])
    try:
        M.find_row('DSYJ-SNT1M')
        check('find_row levanta', 'não levantou', 'levantou')
    except Ocupado:
        check('find_row levanta', 'levantou', 'levantou')

    print('\n== 2. o caso da mesa: callback em massa com o banco ocupado ==')
    r = cl.post('/api/manual-confirmation/upsert',
                json={'rows': [{'Trade ID': 'DSYJ-SNT1M', 'Data Callback': '22/09/2026'}]})
    check('o Save não responde sucesso', r.status_code != 200, True)
finally:
    M.duckdb_read = orig
linha = M.find_row('DSYJ-SNT1M')
check('   a linha continua inteira', (linha['Produto'], linha['Cliente']), ('NDF COMM', 'MONDELEZ'))
check('   e sem o callback que não foi gravado', linha['Data Callback'], '')

r = cl.post('/api/manual-confirmation/upsert',
            json={'rows': [{'Trade ID': 'DSYJ-SNT1M', 'Data Callback': '22/09/2026'}]})
check('com o banco livre o mesmo Save grava', r.status_code, 200)
linha = M.find_row('DSYJ-SNT1M')
check('   o callback, mantendo a operação',
      (linha['Data Callback'], linha['Produto'], linha['Cliente']),
      ('22/09/2026', 'NDF COMM', 'MONDELEZ'))

print('\n== 3. edição não cria linha; só o Add Row ==')
r = cl.post('/api/manual-confirmation/upsert',
            json={'rows': [{'Trade ID': 'NAO-EXISTE', 'Data Callback': '22/09/2026'}]})
check('editar chave ausente é 404', r.status_code, 404)
check('   com código para a tela traduzir', r.get_json().get('code'), 'mc_row_missing')
check('   e nada é criado', M.find_row('NAO-EXISTE'), None)
r = cl.post('/api/manual-confirmation/upsert',
            json={'rows': [{'Trade ID': 'NOVA-1', 'Produto': 'NDF COMM', 'Cliente': 'X', '_new': True}]})
check('Add Row (_new) cria', (r.status_code, (M.find_row('NOVA-1') or {}).get('Cliente')), (200, 'X'))
r = cl.post('/api/manual-confirmation/upsert',
            json={'rows': [{'Trade ID': 'NOVA-1', 'Cliente': 'Y', '_new': True}]})
check('_new com chave existente é 409', (r.status_code, r.get_json().get('code')), (409, 'mc_row_exists'))
check('   sem sobrescrever', M.find_row('NOVA-1')['Cliente'], 'X')

print('\n== 4. upsert_row não perde a linha quando o INSERT falha ==')
_orig_cols = M.DB_COLUMNS
_alterada = dict(M.find_row('DSYJ-SNT1M'), Cliente='OUTRO')
M.DB_COLUMNS = list(_orig_cols) + ['coluna_que_nao_existe']
try:
    M.upsert_row(_alterada)
finally:
    M.DB_COLUMNS = _orig_cols
check('a linha continua lá, como estava', (M.find_row('DSYJ-SNT1M') or {}).get('Cliente'), 'MONDELEZ')

print('\n== 5. o espelho do New Deals não sobrescreve quando não consegue ler ==')
M.upsert_row(dict(M.find_row('DSYJ-SNT1M'), **{'Conferido OTC': '22/09/2026'}))
orig = _leitura_falha()
try:
    R._mc_save_from_deal({'Deal': 'DSYJ-SNT1M', 'Client': 'MONDELEZ'}, 'NDF COMM')
finally:
    M.duckdb_read = orig
check('a validação carimbada sobrevive', M.find_row('DSYJ-SNT1M')['Conferido OTC'], '22/09/2026')

print('\n== 6. is_hollow ==')
check('linha da operação não é casca', M.is_hollow(M.find_row('DSYJ-SNT1M')), False)
check('Trade ID + callback + FepWeb é casca',
      M.is_hollow({'Trade ID': 'K', 'Data Callback': '22/09/2026', 'Nome fep': '123'}), True)
check('sem chave não é casca (é linha nenhuma)', M.is_hollow({'Data Callback': 'x'}), False)

print('\n== 7. backfill --repair ==')
import importlib.util                                              # noqa: E402
_spec = importlib.util.spec_from_file_location(
    'backfill_mc', os.path.join(ROOT, 'scripts', 'backfill_manual_confirmations.py'))
BF = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BF)
M.upsert_row(M.blank_row(**{'Trade ID': 'H1', 'Data Callback': '22/09/2026', 'Nome fep': '777'}))
_casca = M.find_row('H1')
check('a linha é casca', M.is_hollow(_casca), True)
check('_reparar reconstrói', BF._reparar(R, M, {'Deal': 'H1', 'Client': 'ACME',
                                                'TradeDate': '2026-09-22', 'Notional': '500'},
                                         'NDF COMM', 'H1', _casca), True)
_h1 = M.find_row('H1')
check('   com a operação do deal', (_h1['Cliente'], _h1['Produto'], _h1['Data Operação']),
      ('ACME', 'NDF COMM', '22/09/2026'))
check('   e o callback e o FepWeb ID da casca', (_h1['Data Callback'], _h1['Nome fep']),
      ('22/09/2026', '777'))
check('   deixando de ser casca', M.is_hollow(_h1), False)

print('\n%s' % ('FAIL: %d' % len(fails) if fails else 'all ok'))
sys.exit(1 if fails else 0)
