# -*- coding: utf-8 -*-
"""O loader cacheado por MTIME nao pode dar um `stat` por LINHA.

O cache por mtime evita reler o ARQUIVO. Ele nao evita o `os.path.getmtime`
que decide se o arquivo mudou -- e esse stat fica dentro do laco de linhas
quando o loader e consultado por linha.

Em disco local o stat e um syscall e some no ruido: e por isso que o defeito
nao aparece na maquina de desenvolvimento. No share do JPM cada stat e ida e
volta de rede. As cinco telas de Live Position resolvem o nome da contraparte
pelo `RefData.json` uma vez por LINHA (`_lp_cpty_by_taxid` ->
`_lp_taxid_names` -> `_refdata_by_taxid`): medido, 1,00 stat por linha. Uma
posicao de vinte mil linhas pagava vinte mil idas a rede pelo MESMO arquivo, e
a tela levava minutos -- sem erro nenhum, nem no log, porque ninguem falhou.

A correcao e o `@once_per_request`: memoiza dentro de UM request e nao memoiza
nada fora dele (scheduler, script), onde a rotina longa tem de continuar
enxergando o arquivo mudar embaixo dela. De proposito sem TTL entre requests --
com ele, editar o cadastro e recarregar deixaria de valer no request seguinte.

Este guarda mede o comportamento, e nao o texto: monta um arquivo-dia
sintetico, espiona o `os.path.getmtime` e conta.
"""
import collections
import json
import os
import sys
import tempfile
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

from apps.pages import routes as R                          # noqa: E402
from apps.pages.request_cache import once_per_request       # noqa: E402
from apps import create_app                                 # noqa: E402
from apps.config import DebugConfig                         # noqa: E402

falhas = []


def check(rotulo, ok):
    print(('  ok  ' if ok else ' FAIL ') + rotulo)
    if not ok:
        falhas.append(rotulo)


LINHAS = 400
TMP = tempfile.mkdtemp()
_col = sorted(R._LPNDF_CPTY_NAME_COLS)[0]
_rec = dict((c, '') for c in R._LPNDF_COLUMNS)
_rec[_col] = '45985371000108'
_dia = os.path.join(TMP, 'dia.json')
json.dump([dict(_rec) for _ in range(LINHAS)], open(_dia, 'w'), ensure_ascii=False)
R._ndf_ter_path = lambda ref, exact=False: (_dia, ref)

app = create_app(DebugConfig)
app.config['TESTING'] = True
_real_getmtime = os.path.getmtime


def conta(dentro_de_request):
    contador = collections.Counter()

    def espiao(path):
        contador[os.path.basename(str(path))] += 1
        return _real_getmtime(path)

    os.path.getmtime = espiao
    try:
        if dentro_de_request:
            with app.test_request_context('/api/live-position-ndf/data'):
                saida = R._lpndf_collect(datetime(2026, 8, 28))
        else:
            saida = R._lpndf_collect(datetime(2026, 8, 28))
    finally:
        os.path.getmtime = _real_getmtime
    return len(saida.get('rows', [])), contador


print('== 1. dentro de um request, o stat NAO acompanha as linhas ==')
n, c = conta(True)
check('a coleta devolveu as %d linhas do arquivo' % LINHAS, n == LINHAS)
check('o RefData.json e statado no MAXIMO uma vez (foi %d, para %d linhas)'
      % (c.get('RefData.json', 0), n), c.get('RefData.json', 0) <= 1)
# O teto vale para o arquivo INTEIRO de stats, nao so o RefData: qualquer
# loader novo que entre no laco de linhas cai aqui.
total = sum(c.values())
check('e nenhum outro arquivo e statado por linha (%d stats no total)' % total,
      total <= 12)


print('\n== 2. fora de um request, nada e memoizado ==')
# A rotina agendada e longa e tem de continuar enxergando o arquivo mudar
# embaixo dela. Memoizar ali trocaria um defeito de lentidao por um de dado
# velho, que e pior porque nao se ve.
n2, c2 = conta(False)
check('a mesma coleta funciona fora de request', n2 == LINHAS)
check('   e ali o loader volta a perguntar ao disco',
      c2.get('RefData.json', 0) > 1)


print('\n== 3. o decorador em si ==')
chamadas = {'n': 0}


@once_per_request
def _quantas():
    chamadas['n'] += 1
    return chamadas['n']


with app.test_request_context('/'):
    check('duas chamadas no mesmo request rodam a funcao uma vez',
          (_quantas(), _quantas()) == (1, 1))
with app.test_request_context('/'):
    check('   e o request SEGUINTE roda de novo (nao ha TTL)', _quantas() == 2)
chamadas['n'] = 0
check('fora de request nao memoiza', (_quantas(), _quantas()) == (1, 2))


print('\n== 4. quem ja esta protegido ==')
# A lista e o registro do que foi medido — se um deles perder o decorador, a
# tela volta a ficar lenta em silencio.
for mod, nome in (('apps.pages.routes', '_refdata_by_taxid'),
                  ('apps.pages.manual_conf', 'sla_days'),
                  # 2026-09-01: o Trade Level pagava ~11 stats por LINHA via
                  # _mapping_rows (memo proprio, testado abaixo) e estes dois
                  ('apps.pages.routes', '_refdata_by_spn'),
                  ('apps.pages.routes', '_subjacente_map'),
                  # e os finders dos bulks do New Deals refaziam o os.walk da
                  # arvore inteira POR LINHA selecionada — a listagem e uma
                  # por request
                  ('apps.pages.platform.new_deals', '_optcomm_file_list'),
                  ('apps.pages.platform.new_deals', '_optfxo_file_list')):
    __import__(mod)
    fn = getattr(sys.modules[mod], nome)
    check('%s.%s esta memoizado por request' % (mod.split('.')[-1], nome),
          getattr(fn, '__wrapped__', None) is not None)

# _mapping_rows tem memo proprio (chaveado por caminho, invalidado pelo funil
# _atomic_write_json): mede-se o comportamento, nao o texto. O _MAPPINGS_DIR
# vai para um tmp — o seed recria o arquivo la, e nada de dado real e tocado.
_tmpmap = tempfile.mkdtemp()
_dir_real = R._MAPPINGS_DIR
R._MAPPINGS_DIR = _tmpmap
try:
    with app.test_request_context('/'):
        _stats = []
        _orig = os.path.getmtime
        os.path.getmtime = lambda p: (_stats.append(str(p)), _orig(p))[1]
        try:
            R._mapping_rows('bank-name')
            R._mapping_rows('bank-name')
            n = len([p for p in _stats if 'bank-name' in p])
            check('_mapping_rows: 1 stat por request (veio %d)' % n, n == 1)
            R._atomic_write_json(R._mapping_path('bank-name'),
                                 list(R._mapping_rows('bank-name')))
            R._mapping_rows('bank-name')
            n = len([p for p in _stats if 'bank-name' in p])
            check('_mapping_rows: escrita pelo funil derruba o memo (%d stats)' % n,
                  n >= 2)
        finally:
            os.path.getmtime = _orig
finally:
    R._MAPPINGS_DIR = _dir_real
    R._mapping_cache.pop('bank-name', None)

print('\n%s' % ('TUDO OK' if not falhas else 'FALHAS (%d)' % len(falhas)))
sys.exit(1 if falhas else 0)
