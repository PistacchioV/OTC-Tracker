"""O leitor de arquivo-dia compartilhado: `_day_files` + `_day_json`.

Sete endpoints varriam a arvore do cache com `os.walk` e abriam todo JSON que
casasse com o sufixo — as buscas das cinco telas de New Deals e as tres de
Intrag. Na dev e um SSD com dezenas de arquivos; na instancia do JPM a arvore
esta num share, cada operacao e ida e volta de rede, e tres anos de historico
sao centenas de arquivos por produto.

O que este script prova:

  1. a PODA por intervalo descarta ano e mes inteiros, e nao muda o resultado —
     quem decide continua sendo a data no NOME do arquivo;
  2. o MEMO evita reabrir o que nao mudou, e NAO evita reabrir o que mudou (o
     arquivo-dia de hoje e reescrito a cada importacao, e um amend entra no
     arquivo de um dia antigo);
  3. `mutavel=True` devolve COPIA. Sem ela, quem altera os dicionarios depois de
     ler (o `_generic_nd_reenrich` da busca generica) gravaria a alteracao no
     memo, e o proximo leitor veria o dado de outro request;
  4. arquivo ilegivel devolve vazio e NAO entra no memo — um JSON quebrado
     costuma ser um arquivo sendo escrito naquele instante, e memoizar o vazio
     esconderia o dia ate o processo reiniciar;
  5. a ORDEM e por nome, nos dois niveis: a ordem crua do `scandir` e a do
     sistema de arquivos, e a mesma base renderia listas diferentes no share e
     na dev;
  6. nenhum endpoint voltou a usar `os.walk`.
"""
import ast
import builtins
import io
import json
import os
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


TMP = tempfile.mkdtemp(prefix='daycache-')
SUF = '_teste.json'
DIAS = [datetime(2026, 8, 26), datetime(2026, 8, 3), datetime(2026, 2, 10),
        datetime(2025, 11, 20), datetime(2024, 5, 5)]


def escreve(d, n=2):
    pasta = os.path.join(TMP, d.strftime('%Y'), d.strftime('%m'))
    os.makedirs(pasta, exist_ok=True)
    fp = os.path.join(pasta, d.strftime('%Y%m%d') + SUF)
    with io.open(fp, 'w', encoding='utf-8') as fh:
        json.dump([{'Deal': '%s-%d' % (d.strftime('%Y%m%d'), i)} for i in range(n)], fh)
    return fp


for _d in DIAS:
    escreve(_d)

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


def le(desde=None, ate=None, mutavel=False):
    cont.update(listagens=0, aberturas=0)
    saida = []
    for fp, fname, mtime, size in R._day_files(TMP, SUF, desde, ate):
        saida.append((fname, R._day_json(fp, mtime, size, mutavel=mutavel)))
    return saida


print('== 1. a poda por intervalo ==')
R._daycache_forget()
todos = le()
check('sem intervalo, ve os 5 dias', [n for n, _ in todos],
      ['20240505_teste.json', '20251120_teste.json', '20260210_teste.json',
       '20260803_teste.json', '20260826_teste.json'])
listagens_todos = cont['listagens']
R._daycache_forget()
so2026 = le(datetime(2026, 1, 1), datetime(2026, 12, 31))
check('o intervalo de 2026 ve so 2026', sorted(n[:4] for n, _ in so2026), ['2026'] * 3)
check('   e visita menos diretorios', cont['listagens'] < listagens_todos, True)
R._daycache_forget()
so_ago = le(datetime(2026, 8, 1), datetime(2026, 8, 31))
check('o intervalo de agosto ve so agosto', sorted(n[:6] for n, _ in so_ago), ['202608'] * 2)
check('   e visita ainda menos', cont['listagens'] < 5, True)
# A poda e GROSSA: ela nao pode esconder um arquivo que o chamador filtraria.
R._daycache_forget()
check('um intervalo dentro do mes ainda entrega o mes inteiro',
      len(le(datetime(2026, 8, 10), datetime(2026, 8, 20))), 2)

print('\n== 2. o memo ==')
R._daycache_forget()
le()
check('a primeira leitura abre os 5', cont['aberturas'], 5)
le()
check('a segunda nao abre nenhum', cont['aberturas'], 0)
check('   mas ainda lista os diretorios', cont['listagens'] > 0, True)

print('\n== 3. e o arquivo que MUDA e reaberto ==')
# O arquivo-dia de hoje e reescrito a cada importacao, e um amend entra no
# arquivo do dia da OPERACAO, que pode ser antigo.
alvo = escreve(datetime(2024, 5, 5), n=7)
os.utime(alvo, (0, 0))                                     # mtime diferente, garantido
le()
check('reabre so o que mudou', cont['aberturas'], 1)
check('   e entrega o conteudo novo',
      len([d for n, d in le() if n.startswith('20240505')][0]), 7)

print('\n== 4. mutavel=True devolve COPIA ==')
# Sem isto, o `_generic_nd_reenrich` da busca generica gravaria a alteracao no
# memo e o proximo leitor veria o dado de outro request.
R._daycache_forget()
copia = le(mutavel=True)[0][1]
copia[0]['Deal'] = 'ESTRAGADO'
depois = le()[0][1]
check('alterar a copia nao suja o memo', depois[0]['Deal'] == 'ESTRAGADO', False)
# E sem `mutavel` o objeto e o MESMO — e por isso que quem altera tem de pedir.
a1 = le()[0][1]
a2 = le()[0][1]
check('sem mutavel, o memo devolve o mesmo objeto', a1 is a2, True)

print('\n== 5. arquivo ilegivel nao entra no memo ==')
ruim = os.path.join(TMP, '2026', '08', '20260812' + SUF)
with io.open(ruim, 'w', encoding='utf-8') as fh:
    fh.write('{ isto nao e json')
R._daycache_forget()
check('devolve vazio', [d for n, d in le() if n.startswith('20260812')], [[]])
check('e nao foi memoizado', ruim in R._daycache_memo, False)
os.remove(ruim)

print('\n== 6. a ordem nao depende do sistema de arquivos ==')
R._daycache_forget()
um = [n for n, _ in le()]
R._daycache_forget()
dois = [n for n, _ in le()]
check('duas varreduras dao a mesma ordem', um, dois)
check('e ela e por nome', um, sorted(um))

builtins.open = _open_real
os.scandir = _scandir_real

print('\n== 7. nenhum endpoint voltou ao os.walk ==')
_src = io.open(os.path.join(ROOT, 'apps', 'pages', 'routes.py'), encoding='utf-8').read()
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
# Quem REESCREVE um arquivo-dia tem de esquecer a entrada: o mtime novo ja
# invalidaria, mas contar com isso e contar com a resolucao do relogio do share.
check('a busca generica esquece o arquivo que reescreveu',
      '_daycache_forget(fpath)' in _src, True)

shutil.rmtree(TMP, ignore_errors=True)
print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
