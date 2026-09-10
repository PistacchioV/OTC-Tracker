"""check_daycache.py — o leitor único dos arquivos-dia (§7), agora sobre o
ARMAZÉM (DB-only, HANDOFF §434).

O `_day_files` enumera a árvore pelo `_manifest` dos bancos — nenhuma pasta
é listada — e o `_day_json` serve do memo por (mtime, tamanho) o que não
mudou, indo ao banco só no que mudou. O que se prova, em tempfile:
  1. a poda por intervalo é pela DATA do caminho;
  2. o memo: a primeira leitura abre o banco, a segunda não abre nada;
  3. o arquivo que MUDA (regravado pelo funil) é reaberto, e traz o novo;
  4. `mutavel=True` devolve cópia; sem ele, o mesmo objeto;
  5. payload ilegível no banco devolve vazio e NÃO entra no memo;
  6. a ordem é por caminho, sempre a mesma;
  7. nenhum endpoint voltou ao `os.walk`;
  8. o prefetch: UMA abertura de banco para o produto inteiro (a sonda).
"""
import ast
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

import duckdb                                              # noqa: E402
from apps.pages import routes as R                         # noqa: E402
from apps.pages import data_store as S                     # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


TMP = tempfile.mkdtemp(prefix='daycache-')
R._B3_DATA_DIR = TMP
RAIZ = os.path.join(TMP, 'cache', 'teste')
SUF = '_teste.json'
DIAS = [datetime(2026, 8, 26), datetime(2026, 8, 3), datetime(2026, 2, 10),
        datetime(2025, 11, 20), datetime(2024, 5, 5)]


def escreve(d, n=2):
    fp = os.path.join(RAIZ, d.strftime('%Y'), d.strftime('%m'), d.strftime('%Y%m%d') + SUF)
    R._atomic_write_json(fp, [{'Deal': '%s-%d' % (d.strftime('%Y%m%d'), i)} for i in range(n)])
    return fp


for _d in DIAS:
    escreve(_d)

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


def le(desde=None, ate=None, mutavel=False):
    cont.update(aberturas=0)
    saida = []
    for fp, fname, mtime, size in R._day_files(RAIZ, SUF, desde, ate):
        saida.append((fname, R._day_json(fp, mtime, size, mutavel=mutavel)))
    return saida


print('== 1. a poda por intervalo ==')
R._daycache_forget()
todos = le()
check('sem intervalo, ve os 5 dias', [n for n, _ in todos],
      ['20240505_teste.json', '20251120_teste.json', '20260210_teste.json',
       '20260803_teste.json', '20260826_teste.json'])
check('e nenhuma pasta existe no disco', os.path.isdir(RAIZ), False)
so2026 = le(datetime(2026, 1, 1), datetime(2026, 12, 31))
check('o intervalo de 2026 ve so 2026', sorted(n[:4] for n, _ in so2026), ['2026'] * 3)
so_ago = le(datetime(2026, 8, 1), datetime(2026, 8, 31))
check('o intervalo de agosto ve so agosto', sorted(n[:6] for n, _ in so_ago), ['202608'] * 2)
check('um intervalo dentro do mes poda pela DATA do caminho',
      [n for n, _ in le(datetime(2026, 8, 10), datetime(2026, 8, 20))], [])

print('\n== 2. o memo ==')
R._daycache_forget()
S.memo_forget()
le()
check('a primeira leitura abre o banco', cont['aberturas'] >= 1, True)
le()
check('a segunda nao abre nenhum', cont['aberturas'], 0)

print('\n== 3. e o arquivo que MUDA e reaberto ==')
alvo = escreve(datetime(2024, 5, 5), n=7)
S.memo_forget()
le()
check('reabre so o que mudou (manifest + o dia)', cont['aberturas'] <= 2, True)
check('   e entrega o conteudo novo',
      len([d for n, d in le() if n.startswith('20240505')][0]), 7)

print('\n== 4. mutavel=True devolve COPIA ==')
R._daycache_forget()
copia = le(mutavel=True)[0][1]
copia[0]['Deal'] = 'ESTRAGADO'
depois = le()[0][1]
check('alterar a copia nao suja o memo', depois[0]['Deal'] == 'ESTRAGADO', False)
a1 = le()[0][1]
a2 = le()[0][1]
check('sem mutavel, o memo devolve o mesmo objeto', a1 is a2, True)

print('\n== 5. payload ilegivel nao entra no memo ==')
ruim = escreve(datetime(2026, 8, 12))
S.duckdb_read = _dr_real
con = duckdb.connect(os.path.join(TMP, 'db', 'cache', 'teste.db'))
con.execute('UPDATE main.d_20260812 SET "_raw" = \'{ isto nao e json\'')
con.close()
S.duckdb_read = _Conta
R._daycache_forget()
S.memo_forget()
check('devolve vazio', [d for n, d in le() if n.startswith('20260812')], [[]])
check('e nao foi memoizado', ruim in R._daycache_memo, False)
S.remove(ruim)

print('\n== 6. a ordem nao depende do sistema de arquivos ==')
R._daycache_forget()
um = [n for n, _ in le()]
R._daycache_forget()
dois = [n for n, _ in le()]
check('duas varreduras dao a mesma ordem', um, dois)
check('e ela e por nome', um, sorted(um))

S.duckdb_read = _dr_real

print('\n== 7. nenhum endpoint voltou ao os.walk ==')
_src = (io.open(os.path.join(ROOT, 'apps', 'pages', 'routes.py'), encoding='utf-8').read()
        + io.open(os.path.join(ROOT, 'apps/pages/features/new_deals/entrypoint.py'), encoding='utf-8').read())
_tree = ast.parse(_src)
_sobrou = []
for _n in ast.walk(_tree):
    if not isinstance(_n, ast.FunctionDef):
        continue
    _seg = '\n'.join(_src.split('\n')[_n.lineno - 1:_n.end_lineno])
    if 'os.walk(' not in _seg:
        continue
    _rotas = [ast.literal_eval(d.args[0]) for d in _n.decorator_list
              if isinstance(d, ast.Call) and getattr(d.func, 'attr', '') == 'route' and d.args]
    if _rotas:
        _sobrou.append(_rotas[0])
check('nenhuma rota varre a arvore com os.walk', sorted(_sobrou), [])
check('a busca generica esquece o arquivo que reescreveu',
      '_daycache_forget(fpath)' in _src, True)

print('\n== 8. o prefetch: UMA abertura de banco para o produto inteiro ==')
import subprocess                                          # noqa: E402

_PRE = os.path.join(ROOT, 'scripts', 'tests', '_daycache_prefetch_probe.py')
_env = dict(os.environ)
_env['OTC_DISABLE_SCHEDULERS'] = '1'
_out = subprocess.run([sys.executable, _PRE], capture_output=True, text=True, env=_env)
_linhas = [l for l in _out.stdout.split('\n') if l.startswith('PROBE ')]
if not _linhas:
    check('a sonda rodou', _out.stdout[-400:] + _out.stderr[-400:], 'PROBE ...')
else:
    _d = json.loads(_linhas[-1][6:])
    check('sem prefetch, uma abertura por dia', _d['solo_abre'], _d['dias'] - 1)
    check('com prefetch, uma abertura so', _d['lote_abre'], 1)
    check('e o conteudo e o mesmo', _d['solo_regs'] == _d['lote_regs'] and _d['solo_regs'] > 0, True)
    check('memo quente: o prefetch nao abre nada', _d['quente_abre'], 0)
    check('dia fora do banco (legado em disco) continua sendo lido', _d['sem_banco_regs'] > 0, True)

shutil.rmtree(TMP, ignore_errors=True)
print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
