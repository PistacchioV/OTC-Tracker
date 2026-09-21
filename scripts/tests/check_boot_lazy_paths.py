#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""O IMPORT do app não abre banco no share (21/09/2026).

`data_path()` parece montagem de caminho e não é: ele pergunta ao ARMAZÉM se o
arquivo existe (`_existe` → `data_store.exists`), e isso ABRE UM DUCKDB. Seis
chamadas dele estavam no NÍVEL DE MÓDULO — `VCP_JSON` e `DOMINIO_JSON` no
`routes`, `_MTM_HYB_MAP_PATH` em `features/mtm/infra/mappers`, `API_LINKS_FILE`
no `athena_api` (por dentro do `mapping_file`, sem um `data_path` visível na
linha) e os dois caminhos do `recon_payrec` —, ou seja, dentro do IMPORT, que
na instância acontece durante a subida com o app ainda sem atender.

No share, frio, cada abertura custa de segundos a minutos. Eram os vãos mudos
da subida: dois de 4 e 3,3 minutos sem uma linha de log, porque o farol do
`database_access` só avisa acima de ~5 s por operação e estas ficavam logo
abaixo. Medido com o `scripts/diag_boot_imports.py`, o cronômetro do import
parou mais de um minuto em `apps.pages.features.mtm.infra.mappers`, que foi o
que entregou o diagnóstico.

O defeito é do tipo que volta: escrever `X = data_path('Y.json')` no topo de um
módulo é a coisa natural a fazer, e não dá erro nenhum — só custa minutos de
subida na máquina que ninguém usa para desenvolver (§9: a dev é um macOS com os
dados em disco local; o share é da instância).

O que este guarda prende:

  1. **a MEDIDA**: quem abre banco durante `import apps.pages.routes` é
     NOMEADO, e a lista não pode crescer. Sobrou um: a migração do
     CounterpartyDetails (`_cpd_load`), que é eager de propósito — o modal do
     Reference Data lê o JSON pela rota `static_data_file`, que não passa por
     ela, então adiá-la é decisão de produto e não de desempenho;
  2. nenhum `data_path()`/`mapping_file()` no nível de módulo em `apps/pages`
     — a regressão;
  3. o `__getattr__` do `routes` resolve na primeira leitura, vira atributo de
     verdade e não muda o que `getattr(..., padrão)`/`hasattr` respondem;
  4. o PATCH do atributo continua vencendo — é a razão de ser `__getattr__` e
     não função: o `check_cetip_dominio.py` faz `R.DOMINIO_JSON = base`, e com
     uma função o patch pararia de valer em silêncio, com o teste lendo e
     gravando dado real;
  5. no `mtm` é FUNÇÃO, porque lá o nome é lido de DENTRO do próprio arquivo e
     `__getattr__` de módulo não responde a isso — daria `NameError`.
"""
import ast
import io
import os
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

falhas = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok   ' if ok else '  FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        falhas.append(label)


print('== 1. a MEDIDA: quem abre banco durante o import do routes ==')
# Num subprocesso, porque a contagem tem de começar ANTES do import — neste
# processo o `routes` já está carregado quando o teste roda. E a sonda registra
# o CHAMADOR de cada abertura, não só o total: o número sozinho não diz o que
# entrou, e o que este guarda precisa impedir é que entre um novo.
SONDA = r'''
import os, traceback, duckdb
ROOT = os.getcwd()
FUNDO = ('data_store.py', 'database_access.py', 'duck_read.py',
         'json_to_duckdb.py', 'data_paths.py')
_c = duckdb.connect
def espia(*a, **k):
    pilha = [f for f in traceback.extract_stack()[:-1]
             if f.filename.startswith(ROOT) and not f.filename.endswith(FUNDO)]
    onde = '%s:%d' % (os.path.relpath(pilha[-1].filename, ROOT), pilha[-1].lineno) \
           if pilha else '?'
    print('ABRIU|%s' % onde)
    return _c(*a, **k)
duckdb.connect = espia
import apps.pages.routes          # noqa: F401
print('FIM')
'''
amb = dict(os.environ)
amb['PYTHONPATH'] = ROOT
proc = subprocess.run([sys.executable, '-c', SONDA], cwd=ROOT, env=amb,
                      capture_output=True, text=True)
if 'FIM' not in proc.stdout:
    print(proc.stdout[-2000:])
    print(proc.stderr[-3000:])
    check('a sonda rodou até o fim', False)
    chamadores = ['<a sonda falhou>']
else:
    chamadores = [l.split('|', 1)[1] for l in proc.stdout.splitlines()
                  if l.startswith('ABRIU|')]
for _c in sorted(set(chamadores)):
    print('   abre %dx: %s' % (chamadores.count(_c), _c))

# O ÚNICO que pode abrir banco no import é a migração do CounterpartyDetails,
# que é EAGER de propósito: o modal do Reference Data lê o JSON pela rota
# `static_data_file`, que não passa pelo `_cpd_load` — sem a migração na subida,
# o primeiro acesso ao modal veria o cadastro sem os ids estáveis. Adiá-la é uma
# decisão de produto, não de desempenho, e por isso ela fica aqui NOMEADA em vez
# de proibida: o guarda prende o resto.
#
# `counterparty.py:238` é onde o `_cpd_load` chama o `duck_read.cpd_records`.
PERMITIDOS = {'apps/pages/platform/counterparty.py:238'}
intrusos = sorted({c for c in chamadores if c not in PERMITIDOS})
check('nenhum lugar NOVO abre banco durante o import', intrusos, [])

print('\n== 2. nenhum `data_path()` no nível de módulo em apps/pages ==')
# A regressão: `X = data_path('Y.json')` no topo de um módulo volta a pagar a
# abertura dentro do import. `mapping_file`/`with_fallback` entram na lista
# porque CAEM no `data_path` — foi assim que o `athena_api` pagava a abertura
# sem um `data_path` visível na linha. `data_write()` NÃO entra: ele só monta
# o caminho (`os.path.join` sobre o `Config.DATA_DIR`) e nunca pergunta nada
# ao armazém.
PROIBIDAS = {'data_path', 'mapping_file', 'with_fallback'}
achados = []
for dirpath, _dirs, nomes in os.walk(os.path.join('apps', 'pages')):
    if '__pycache__' in dirpath:
        continue
    for nome in nomes:
        if not nome.endswith('.py') or nome.endswith(' 2.py'):
            continue
        caminho = os.path.join(dirpath, nome)
        try:
            arvore = ast.parse(io.open(caminho, encoding='utf-8').read())
        except SyntaxError:
            continue
        for no in arvore.body:                       # SÓ o nível de módulo
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                               ast.Import, ast.ImportFrom)):
                continue
            for sub in ast.walk(no):
                if not isinstance(sub, ast.Call):
                    continue
                f = sub.func
                alvo = f.id if isinstance(f, ast.Name) else (
                    f.attr if isinstance(f, ast.Attribute) else '')
                if alvo in PROIBIDAS:
                    achados.append('%s:%d' % (caminho, no.lineno))
check('nenhum módulo resolve caminho pelo armazém no import', achados, [])

print('\n== 3. o `__getattr__` do routes: preguiçoso, e vira atributo ==')
from apps.pages import routes as R                                # noqa: E402

# Um módulo recém-importado não pode ter os nomes em `globals()`; como este
# processo pode já tê-los resolvido, a pergunta é feita sobre um nome limpo.
for _n in ('VCP_JSON', 'DOMINIO_JSON'):
    vars(R).pop(_n, None)
check('antes do primeiro acesso, o nome não está no módulo',
      'VCP_JSON' in vars(R), False)
_v = R.VCP_JSON
check('o acesso resolve para um caminho', _v.endswith('VCP.json'), True)
check('   e o nome passa a ser atributo DE VERDADE', 'VCP_JSON' in vars(R), True)
check('   então o segundo acesso não reabre nada', R.VCP_JSON is _v, True)

print('\n== 4. nome desconhecido, e o PATCH do teste ==')
check('getattr com padrão continua devolvendo o padrão',
      getattr(R, '_nome_que_nao_existe', 'PADRAO'), 'PADRAO')
check('hasattr continua False', hasattr(R, '_nome_que_nao_existe'), False)
try:
    getattr(R, '_nome_que_nao_existe')
    _levantou = False
except AttributeError:
    _levantou = True
check('e o acesso cru levanta AttributeError', _levantou, True)
# A razão de ser `__getattr__` e não função: o `check_cetip_dominio.py` aponta
# o teste para um tmp assim. Com função, o patch pararia de valer EM SILÊNCIO.
vars(R).pop('DOMINIO_JSON', None)
R.DOMINIO_JSON = '/tmp/patch-do-teste/Dominio.json'
check('o patch do atributo VENCE o __getattr__',
      R.DOMINIO_JSON, '/tmp/patch-do-teste/Dominio.json')
vars(R).pop('DOMINIO_JSON', None)

print('\n== 5. no mtm é FUNÇÃO (o nome é lido de dentro do próprio arquivo) ==')
from apps.pages.features.mtm.infra import mappers                 # noqa: E402
check('a função existe', callable(getattr(mappers, '_mtm_hyb_map_path', None)), True)
check('   e devolve o caminho',
      mappers._mtm_hyb_map_path().endswith('mapping_swap-hyb.json'), True)
check('a constante antiga não voltou', hasattr(mappers, '_MTM_HYB_MAP_PATH'), False)
# E ninguém ficou lendo o nome antigo: um leitor esquecido daria NameError só
# no request que passasse por ele.
_sobrou = []
for _p in ('apps/pages/features/mtm/infra/mappers.py',
           'apps/pages/features/mtm/entrypoint.py'):
    for _i, _l in enumerate(io.open(_p, encoding='utf-8').read().splitlines(), 1):
        if '_MTM_HYB_MAP_PATH' in _l and not _l.lstrip().startswith(('#', '*')) \
                and 'Era uma constante' not in _l:
            _sobrou.append('%s:%d' % (_p, _i))
check('nenhum leitor do nome antigo sobrou', _sobrou, [])

print()
if falhas:
    for f in falhas:
        print('FAIL ' + f)
    sys.exit(1)
print('TUDO OK')
