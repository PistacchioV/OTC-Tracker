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
print('\n== 7. quem conta como DEAL, e quem e a perna do banco ==')
# Dois defeitos que tiravam operacao REAL de todos os contadores, do Top 5 e
# do Deal Flow, sem nada acusar na tela.
import re as _re

_jpm_re = _re.compile(r'J\.?P\.?\s*MORGAN', _re.IGNORECASE)


def _is_bank(d):
    return bool(_jpm_re.search(d.get('Client') or ''))


# (a) linha SEM `Deal`: o Swap Bullet nasce assim (§480) — a chave e o `_id`
#     interno e o B3 ID e coluna propria. O painel mostrava `Swap Deals = 0`
#     com as operacoes na tela ao lado.
fp_swb = os.path.join(RAIZ, 'Swap', 'Bullet', '2026', '09', '20260917_swapbullet.json')
R._atomic_write_json(fp_swb, [
    {'_id': 'SWB-a1', 'Deal': '', 'B3ID': '26I04812345', 'Client': 'BANCO SAFRA S.A.',
     'LE': 'JPM', 'Status': 'Sent', 'TradeDate': '17/09/2026'},
    {'_id': 'SWB-a2', 'Deal': '', 'B3ID': '26I04812346', 'Client': 'ATACAMA FUNDO DE INVESTIMENTO',
     'LE': 'ATACAMA', 'Status': 'Sent', 'TradeDate': '17/09/2026'},
    {'_id': '', 'Deal': '', 'B3ID': '', 'Client': 'LINHA VAZIA', 'LE': 'JPM', 'Status': ''},
])
R._dash_file_memo.clear()
st = S.stat(fp_swb)
linhas = R._dash_file_deals(fp_swb, os.path.basename(fp_swb), st.st_mtime, st.st_size,
                            datetime(2026, 9, 17), 'Swap Bullet', 'SWAP')
check('linha sem Deal mas COM B3 ID conta', len(linhas), 2)
check('e o B3 ID vai projetado (e o identificador de quem nao tem Deal)',
      sorted(l.get('B3ID') for l in linhas), ['26I04812345', '26I04812346'])
check('linha sem identificador nenhum continua fora',
      [l for l in linhas if l.get('Client') == 'LINHA VAZIA'], [])
check('o caminho classifica como SWAP',
      R._type_from_product(R._product_from_path(fp_swb.replace(RAIZ, R.NEW_DEALS_CACHE_ROOT))), 'SWAP')

# (b) `_is_bank`: a perna a descartar e a do J.P. MORGAN, nao "o nome tem
#     banco". A regra antiga derrubava BANCO SAFRA, BANCO BRADESCO e BANCO
#     SANTANDER — clientes de verdade.
for nome in ('BANCO SAFRA S.A.', 'BANCO BRADESCO S.A.', 'BANCO SANTANDER (BRASIL) S.A.',
             'ATACAMA FUNDO DE INVESTIMENTO', 'LAWTON FIF MULTIMERCADO'):
    check('cliente de verdade NAO e a perna do banco: ' + nome,
          _is_bank({'Client': nome}), False)
for nome in ('BANCO J.P. MORGAN S/A', 'J.P. MORGAN', 'JP MORGAN', 'JPMORGAN CHASE BANK',
             'banco j.p. morgan s/a'):
    check('a perna do J.P. Morgan E descartada: ' + nome,
          _is_bank({'Client': nome}), True)
# A grafia real do arquivo da B3 leva ponto depois do P: era ela que o teste
# cru por 'j.p morgan' NAO pegava, e por isso o 'banco' solto tinha virado o
# unico que pegava a perna do banco.
check("a grafia com ponto ('J.P.') era a que escapava dos literais antigos",
      ('j.p morgan' in 'BANCO J.P. MORGAN S/A'.lower()
       or 'jp morgan' in 'BANCO J.P. MORGAN S/A'.lower()
       or 'jpmorgan' in 'BANCO J.P. MORGAN S/A'.lower()), False)

# E o fonte tem de carregar as duas correcoes — este guarda varre o routes.py
# para a regra nao voltar num refactor.
_src = io.open(os.path.join(ROOT, 'apps', 'pages', 'routes.py'), encoding='utf-8').read()
# Ate a proxima `def` do mesmo nivel: parar na primeira linha em branco cai
# DENTRO do docstring, entre paragrafos.
_corpo = _re.search(r'\n    def _is_bank\(d\):\n(.*?)\n    def ', _src, _re.DOTALL)
check('o _is_bank do painel existe', bool(_corpo), True)
if _corpo:
    # A prosa do docstring CITA a regra velha para explicar o defeito; o que
    # nao pode voltar e o teste em si, e ele mora depois das aspas triplas.
    _codigo = _corpo.group(1).split('\"\"\"')[-1]
    check("o corpo nao testa mais `'banco' in cl`", "'banco' in" in _codigo, False)
    check('e usa o _jpm_re', '_jpm_re.search' in _codigo, True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
