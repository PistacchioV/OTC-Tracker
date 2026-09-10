"""check_dashboard_walk.py — a varredura do painel (dashboard) sobre o ARMAZÉM
(DB-only, HANDOFF §434).

`_dash_scan_files` enumera os arquivos-dia do New Deals pelo `_manifest` dos
bancos, podando ano/mês pela regra de sempre (`_dash_dir_matters`) aplicada
aos segmentos do CAMINHO; `_dash_file_deals` memoiza a projeção por (mtime,
tamanho). O que se prova, em tempfile:
  1. a poda descarta ano e mês inteiros;
  2. o memo evita reabrir o que não mudou;
  3. e NÃO evita reabrir o que mudou (regravado pelo funil);
  4. a projeção cobre todo campo que o endpoint lê;
  5. o aquecimento do memo sobe com o app e enche o memo;
  6. a ordem não depende do sistema de arquivos.
"""
import ast
import io
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages import routes as R                         # noqa: E402
from apps.pages import data_store as S                     # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


# ── uma arvore com dois anos, dois produtos ─────────────────────────────────
TMP = tempfile.mkdtemp(prefix='dash-walk-')
R._B3_DATA_DIR = TMP
RAIZ = os.path.join(TMP, 'cache', 'new deals')
HOJE = datetime(2026, 8, 26)


def dia(d, produto=('NDF', 'Vanilla'), n=3):
    fp = os.path.join(RAIZ, produto[0], produto[1], d.strftime('%Y'), d.strftime('%m'),
                      d.strftime('%Y%m%d') + '_x.json')
    R._atomic_write_json(fp, [{'Deal': '%s-%02d' % (d.strftime('%Y%m%d'), i), 'Client': 'CLI %d' % (i % 2),
                               'Status': 'Success', 'TradeDate': d.strftime('%d/%m/%Y'), 'LE': 'JPM',
                               'Commodity': '', 'Commodities': '', 'UnderlyingAsset': '',
                               'CampoQueNinguemLe': 'x' * 50}
                              for i in range(n)])
    return fp


DIAS = [HOJE, HOJE - timedelta(days=40), datetime(2025, 3, 10), datetime(2025, 11, 20)]
for _d in DIAS:
    dia(_d)
    dia(_d, ('Option', 'FXO'))

R.NEW_DEALS_CACHE_ROOT = RAIZ

# ── espia as aberturas de banco ─────────────────────────────────────────────
cont = {'aberturas': 0}
_dr_real = S.duckdb_read


class _Conta(object):
    def __init__(self, *a, **k):
        cont['aberturas'] += 1
        self._cm = _dr_real(*a, **k)

    def __enter__(self):
        return self._cm.__enter__()

    def __exit__(self, *a):
        return self._cm.__exit__(*a)


S.duckdb_read = _Conta


def varre(period, now=HOJE):
    cont.update(aberturas=0)
    achados = []
    for fp, fname, mtime, size in R._dash_scan_files(RAIZ, period, now):
        achados.append(fname)
        R._dash_file_deals(fp, fname, mtime, size,
                           datetime.strptime(fname[:8], '%Y%m%d'), 'NDF Vanilla', 'NDF')
    return achados


print('== 1. a poda descarta ano e mes inteiros ==')
R._dash_file_memo.clear()
todos = varre('all')
check('all ve os 8 arquivos', len(todos), 8)
check('e nenhuma pasta existe no disco', os.path.isdir(RAIZ), False)
R._dash_file_memo.clear()
ano = varre('year')
check('year ve so 2026', sorted(set(f[:4] for f in ano)), ['2026'])
R._dash_file_memo.clear()
mes = varre('month')
check('month ve so 2026-08', sorted(set(f[:6] for f in mes)), ['202608'])

print('\n== 2. o memo evita reabrir o que nao mudou ==')
R._dash_file_memo.clear()
S.memo_forget()
varre('all')
check('a primeira passada abre os bancos', cont['aberturas'] >= 2, True)
varre('all')
check('a segunda nao abre nada', cont['aberturas'], 0)

print('\n== 3. e NAO evita reabrir o que mudou ==')
alvo = dia(datetime(2025, 3, 10), n=7)                     # reescreve um dia ANTIGO, pelo funil
S.memo_forget()
varre('all')
check('reabre o produto reescrito (manifest + o dia)', 1 <= cont['aberturas'] <= 2, True)
_fp, _fn = alvo, os.path.basename(alvo)
_st = S.stat(alvo)
check('e o conteudo novo e o que vale',
      len(R._dash_file_deals(_fp, _fn, _st.st_mtime, _st.st_size,
                             datetime(2025, 3, 10), 'NDF Vanilla', 'NDF')), 7)

print('\n== 4. a projecao cobre todo campo que o endpoint le ==')
_src = io.open(os.path.join(ROOT, 'apps', 'pages', 'routes.py'), encoding='utf-8').read()
_tree = ast.parse(_src)
_fn_src = ''
for _n in ast.walk(_tree):
    if isinstance(_n, ast.FunctionDef) and _n.name == 'api_dashboard_stats':
        _fn_src = '\n'.join(_src.split('\n')[_n.lineno - 1:_n.end_lineno])
        break
check('achei a funcao', bool(_fn_src), True)
_INTERNAS = {'_fdate', '_product', '_type', 'period', 'authenticated'}
_lidas = set(re.findall(r"\bd\.get\(\s*'([^']+)'", _fn_src))
_lidas |= set(re.findall(r"\bd\[\s*'([^']+)'\s*\]", _fn_src))
_faltando = sorted(_lidas - _INTERNAS - set(R._DASH_DEAL_FIELDS))
check('nenhum campo lido fica fora de _DASH_DEAL_FIELDS', _faltando, [])
check('e a tupla nao tem campo a mais',
      sorted(set(R._DASH_DEAL_FIELDS) - _lidas), [])

print('\n== 5. o aquecimento do memo ==')
check('o aquecimento sobe com o APP',
      any(l == 'dashboard-warm' for l, _ in R._SCHEDULERS), True)
check('_product_from_path e de modulo', callable(getattr(R, '_product_from_path', None)), True)
check('_type_from_product e de modulo', callable(getattr(R, '_type_from_product', None)), True)
R._dash_file_memo.clear()
R._dash_warm_memo()
check('e ele enche o memo', len(R._dash_file_memo) > 0, True)
cont.update(aberturas=0)
R._dash_warm_memo()
check('   rodar de novo nao reabre nada', cont['aberturas'], 0)

S.duckdb_read = _dr_real

print('\n== 6. a ordem nao depende do sistema de arquivos ==')
R._DASH_TTL = 0
from apps import create_app                                # noqa: E402
from apps.config import DebugConfig                        # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True
cl = app.test_client()
with cl.session_transaction() as s:
    s.update(authenticated=True, user_sid='X1', user_name='X', user_role='BO',
             user_email='x@x', session_expires_at=(datetime.now() + timedelta(days=1)).isoformat())
R._dash_file_memo.clear()
_um = cl.get('/api/dashboard-stats?period=all').get_json()
R._dash_file_memo.clear()
_dois = cl.get('/api/dashboard-stats?period=all').get_json()
check('duas leituras dao o mesmo payload', _um, _dois)
check('top5 sem most_common (desempate por insercao)',
      'most_common(5)' in _fn_src, False)
check('a lista de recentes desempata pelo Deal',
      "d.get('_fdate', ''), d.get('Deal', '')" in _fn_src, True)

shutil.rmtree(TMP, ignore_errors=True)
print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
