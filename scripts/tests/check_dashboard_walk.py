"""A varredura do painel: poda, memo e ORDEM estavel.

O painel varria a arvore inteira do cache de New Deals DUAS vezes (uma para os
totais, outra para os contadores por mes) e abria todo JSON do periodo. Na dev e
um SSD com dezenas de arquivos; na instancia do JPM a arvore esta num share,
cada operacao e ida e volta de rede, e dois anos de historico sao milhares de
arquivos — a tela fica em "Carregando os dados do painel..." por minutos, sem
erro nenhum, porque nada falhou: o servidor esta lendo.

O que este script prova:

  1. a PODA por periodo descarta ano e mes inteiros, e nao muda o resultado — o
     filtro que decide continua sendo a data no NOME do arquivo;
  2. o MEMO evita reabrir o que nao mudou, e NAO evita reabrir o que mudou (o
     arquivo-dia de hoje e reescrito a cada importacao, e um amend entra no
     arquivo de um dia antigo);
  3. as duas passadas compartilham o memo — o mesmo arquivo nao e lido duas
     vezes na mesma tela;
  4. a projecao `_DASH_DEAL_FIELDS` cobre TODO campo que o endpoint le do deal.
     Campo de fora volta `None` sem erro nenhum, e o painel mostraria zero;
  5. a ORDEM e estavel. O desempate dos Top 5 e da lista de recentes vinha da
     ordem de leitura da arvore, que e a do sistema de arquivos: a mesma base
     rendia listas diferentes no share e na dev.
"""
import ast
import builtins
import io
import json
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

from apps.pages import routes as R                         # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


# ── uma arvore com dois anos, dois produtos ─────────────────────────────────
TMP = tempfile.mkdtemp(prefix='dash-walk-')
HOJE = datetime(2026, 8, 26)


def dia(d, produto=('NDF', 'Vanilla'), n=3):
    pasta = os.path.join(TMP, produto[0], produto[1], d.strftime('%Y'), d.strftime('%m'))
    os.makedirs(pasta, exist_ok=True)
    fp = os.path.join(pasta, d.strftime('%Y%m%d') + '_x.json')
    with io.open(fp, 'w', encoding='utf-8') as fh:
        json.dump([{'Deal': '%s-%02d' % (d.strftime('%Y%m%d'), i), 'Client': 'CLI %d' % (i % 2),
                    'Status': 'Success', 'TradeDate': d.strftime('%d/%m/%Y'), 'LE': 'JPM',
                    'Commodity': '', 'Commodities': '', 'UnderlyingAsset': '',
                    'CampoQueNinguemLe': 'x' * 50}
                   for i in range(n)], fh)
    return fp


DIAS = [HOJE, HOJE - timedelta(days=40), datetime(2025, 3, 10), datetime(2025, 11, 20)]
for _d in DIAS:
    dia(_d)
    dia(_d, ('Option', 'FXO'))

R.NEW_DEALS_CACHE_ROOT = TMP

# ── espia as idas ao disco ──────────────────────────────────────────────────
cont = {'listagens': 0, 'aberturas': 0}
_scandir_real, _open_real = os.scandir, builtins.open


class _Scan(object):
    def __init__(self, p):
        self.p = p

    def __enter__(self):
        cont['listagens'] += 1
        self.it = _scandir_real(self.p)
        return self.it

    def __exit__(self, *a):
        self.it.close()
        return False


def _abre(p, *a, **k):
    if isinstance(p, str) and p.endswith('.json') and TMP in p:
        cont['aberturas'] += 1
    return _open_real(p, *a, **k)


os.scandir = lambda p: _Scan(p)
builtins.open = _abre


def varre(period, now=HOJE):
    cont.update(listagens=0, aberturas=0)
    achados = []
    for fp, fname, mtime, size in R._dash_scan_files(TMP, period, now):
        achados.append(fname)
        R._dash_file_deals(fp, fname, mtime, size,
                           datetime.strptime(fname[:8], '%Y%m%d'), 'NDF Vanilla', 'NDF')
    return achados


print('== 1. a poda descarta ano e mes inteiros ==')
R._dash_file_memo.clear()
todos = varre('all')
check('all ve os 8 arquivos', len(todos), 8)
lista_all = cont['listagens']
R._dash_file_memo.clear()
ano = varre('year')
check('year ve so 2026', sorted(set(f[:4] for f in ano)), ['2026'])
check('e visita menos diretorios', cont['listagens'] < lista_all, True)
R._dash_file_memo.clear()
mes = varre('month')
check('month ve so 2026-08', sorted(set(f[:6] for f in mes)), ['202608'])

print('\n== 2. o memo evita reabrir o que nao mudou ==')
R._dash_file_memo.clear()
varre('all')
check('a primeira passada abre tudo', cont['aberturas'], 8)
varre('all')
check('a segunda nao abre nada', cont['aberturas'], 0)
check('mas ainda lista os diretorios', cont['listagens'] > 0, True)

print('\n== 3. e NAO evita reabrir o que mudou ==')
# O arquivo-dia de hoje e reescrito a cada importacao, e um amend entra no
# arquivo do dia da OPERACAO, que pode ser antigo. Pelo caminho sozinho o painel
# mostraria o dia congelado na primeira leitura do processo.
alvo = dia(datetime(2025, 3, 10), n=7)                     # reescreve um dia ANTIGO
os.utime(alvo, (0, 0))                                     # mtime diferente, garantido
varre('all')
check('reabre o arquivo reescrito', cont['aberturas'], 1)
_fp, _fn = alvo, os.path.basename(alvo)
_st = os.stat(alvo)
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
# `d.get('X')` e `d['X']` dentro da funcao. As chaves internas (`_fdate`,
# `_product`, `_type`) sao postas pela leitura; `period`/`authenticated` sao do
# request, nao do deal.
_INTERNAS = {'_fdate', '_product', '_type', 'period', 'authenticated'}
_lidas = set(re.findall(r"\bd\.get\(\s*'([^']+)'", _fn_src))
_lidas |= set(re.findall(r"\bd\[\s*'([^']+)'\s*\]", _fn_src))
_faltando = sorted(_lidas - _INTERNAS - set(R._DASH_DEAL_FIELDS))
check('nenhum campo lido fica fora de _DASH_DEAL_FIELDS', _faltando, [])
check('e a tupla nao tem campo a mais',
      sorted(set(R._DASH_DEAL_FIELDS) - _lidas), [])

builtins.open = _open_real
os.scandir = _scandir_real

print('\n== 5. o aquecimento do memo ==')
# A instancia reinicia varias vezes ao dia e o memo volta a zero: sem aquecer,
# QUEM ABRIR O PAINEL PRIMEIRO paga a leitura inteira da arvore, e e quase
# sempre alguem. A thread faz essa leitura fora do request.
check('o aquecimento sobe com o APP',
      any(l == 'dashboard-warm' for l, _ in R._SCHEDULERS), True)
# `_product_from_path` e `_type_from_product` tem de ser de MODULO: o memo grava
# o `_product`/`_type` junto de cada deal, e aninhadas no endpoint o
# aquecimento nao as alcanca — ele morria com `NameError` e nada aparecia na
# tela (o painel seguia certo, so voltava a pagar a leitura).
check('_product_from_path e de modulo', callable(getattr(R, '_product_from_path', None)), True)
check('_type_from_product e de modulo', callable(getattr(R, '_type_from_product', None)), True)
R._dash_file_memo.clear()
R._dash_warm_memo()
check('e ele enche o memo', len(R._dash_file_memo) > 0, True)
cont.update(listagens=0, aberturas=0)
_antes = dict(R._dash_file_memo)
R._dash_warm_memo()
check('   rodar de novo nao reabre nada', cont['aberturas'], 0)

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
# O desempate dos Top 5 e por nome, e o dos recentes leva o Deal junto.
check('top5 sem most_common (desempate por insercao)',
      'most_common(5)' in _fn_src, False)
check('a lista de recentes desempata pelo Deal',
      "d.get('_fdate', ''), d.get('Deal', '')" in _fn_src, True)

shutil.rmtree(TMP, ignore_errors=True)
print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
