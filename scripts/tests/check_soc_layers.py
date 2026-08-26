# -*- coding: utf-8 -*-
"""As regras de separacao das VERTICAIS (`apps/pages/features/`).

O `routes.py` tem 39 mil linhas porque toda funcionalidade nasceu nele. A saida
e levar uma feature de cada vez para `features/<nome>/`, e este script e o que
impede a arvore nova de virar a mesma bola de barro com pastas.

Ele prende as regras da skill `separation-of-concerns` (SoC-002/003/004) mais
uma que e especifica deste repositorio e e a que causa perda SILENCIOSA:

  **Modulo de feature nunca importa NOME do `routes`, so o MODULO.**

  Sessenta e um dos setenta e nove scripts de `scripts/tests/` trocam atributos
  no `routes` para nao encostar em dado real: `R.DB_PATH = tmp`,
  `R._create_notification = espiao`, `R.OTM_JSON_ROOT = tmp`. Um
  `from apps.pages.routes import get_db_connection` no topo de um modulo de
  feature CONGELA o valor no import: o teste troca o atributo, o modulo continua
  com o original, e o teste passa a ler o banco de VERDADE — passando. E a
  producao herda o mesmo problema pelo outro lado, porque o `routes` reatribui
  varias dessas constantes na subida.

  O jeito certo e a busca ATRASADA: `from apps.pages import routes` DENTRO da
  funcao, e `routes.X` no ponto de uso. De quebra isso resolve a circularidade,
  ja que o `routes` importa os entrypoints no fim do proprio arquivo.

E a regra que nao esta na skill mas mata a feature em silencio: **entrypoint que
o `routes.py` nao importa e rota que nao existe.** Em Flask o decorador so roda
quando o modulo e importado; sem o import, a pagina responde 404 e a subida nao
diz nada.
"""
import ast
import io
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
FEAT = os.path.join(ROOT, 'apps', 'pages', 'features')

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def modulos():
    for raiz, dirs, arqs in os.walk(FEAT):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for a in arqs:
            if a.endswith('.py'):
                yield os.path.join(raiz, a)


def rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, '/')


def camada(p):
    return os.path.splitext(os.path.basename(p))[0]


def feature_de(p):
    r = rel(p).split('/')
    return r[3] if len(r) > 3 else ''


ARQS = sorted(modulos())
check('a pasta das verticais existe e tem modulo', bool(ARQS), True)
if not ARQS:
    sys.exit(1)

arvores = {p: ast.parse(io.open(p, encoding='utf-8').read()) for p in ARQS}


def imports_de(arv):
    """(modulo, [nomes]) de cada import, com o nivel de `from .` resolvido."""
    out = []
    for n in ast.walk(arv):
        if isinstance(n, ast.ImportFrom):
            out.append((n.module or '', [a.name for a in n.names], n))
        elif isinstance(n, ast.Import):
            for a in n.names:
                out.append((a.name, [], n))
    return out


print('\n== 1. modulo de feature nunca importa NOME do routes ==')
maus = []
for p in ARQS:
    for mod, nomes, no in imports_de(arvores[p]):
        if mod == 'apps.pages.routes' and nomes:
            maus.append('%s:%d importa %s' % (rel(p), no.lineno, ', '.join(nomes)))
check('nenhum `from apps.pages.routes import <nome>`', maus, [])

print('\n== 2. e o import do routes e ATRASADO (dentro da funcao) ==')
# No topo do modulo ele fecharia o ciclo: o routes importa os entrypoints no fim
# do proprio arquivo, entao neste ponto ele ainda esta a meio de executar.
topo = []
for p in ARQS:
    for n in arvores[p].body:                       # so o corpo do modulo
        for mod, _nomes, no in imports_de(ast.Module(body=[n], type_ignores=[])):
            if mod in ('apps.pages.routes',) or mod.endswith('.routes'):
                topo.append('%s:%d' % (rel(p), no.lineno))
check('nenhum import de routes no corpo do modulo', topo, [])

print('\n== 3. o dominio nao faz I/O (SoC-004) ==')
# Dominio e regra pura: o que ele precisa saber do mundo chega por parametro.
PROIBIDO_NO_DOMINIO = ('flask', 'duckdb', 'smtplib', 'requests', 'sqlite3',
                       'shutil', 'apps.pages.routes', 'apps.config')
sujos = []
for p in ARQS:
    if camada(p) != 'domain':
        continue
    for mod, _n, no in imports_de(arvores[p]):
        if any(mod == x or mod.startswith(x + '.') for x in PROIBIDO_NO_DOMINIO):
            sujos.append('%s:%d importa %s' % (rel(p), no.lineno, mod))
check('nenhum dominio importa I/O', sujos, [])

print('\n== 4. as dependencias apontam para dentro (SoC-002) ==')
# domain nao conhece quem o usa; queries nao conhecem commands.
PROIBIDO_POR_CAMADA = {
    'domain':  ('entrypoint', 'commands', 'queries', 'infra'),
    'queries': ('entrypoint', 'commands'),
    'commands': ('entrypoint',),
}
invertidas = []
for p in ARQS:
    proib = PROIBIDO_POR_CAMADA.get(camada(p))
    if not proib:
        continue
    for mod, nomes, no in imports_de(arvores[p]):
        alvo = set(mod.split('.')) | set(nomes)
        for x in proib:
            if x in alvo:
                invertidas.append('%s:%d -> %s' % (rel(p), no.lineno, x))
check('nenhuma dependencia para cima', sorted(set(invertidas)), [])

print('\n== 5. features nao se importam entre si (SoC-003) ==')
cruzados = []
for p in ARQS:
    minha = feature_de(p)
    for mod, _n, no in imports_de(arvores[p]):
        if not mod.startswith('apps.pages.features.'):
            continue
        outra = mod.split('.')[3] if len(mod.split('.')) > 3 else ''
        if outra and minha and outra != minha:
            cruzados.append('%s:%d -> %s' % (rel(p), no.lineno, outra))
check('nenhuma feature importa outra', cruzados, [])

print('\n== 6. todo entrypoint e importado pelo routes.py ==')
# Em Flask, rota que ninguem importa e rota que nao existe: o decorador so roda
# no import. Sem esta linha, a pagina responde 404 e a subida nao diz nada.
rotas_py = io.open(os.path.join(ROOT, 'apps', 'pages', 'routes.py'), encoding='utf-8').read()
faltando = []
for p in ARQS:
    if camada(p) != 'entrypoint':
        continue
    mod = rel(p)[:-3].replace('/', '.')             # apps/pages/... -> apps.pages...
    pacote, _sep, _nome = mod.rpartition('.')
    if ('import %s' % mod) not in rotas_py and \
       ('from %s import entrypoint' % pacote) not in rotas_py:
        faltando.append(mod)
check('nenhum entrypoint orfao', faltando, [])

print('\n== 7. as rotas realmente existem no app ==')
# O teste acima le o texto; este SOBE o app e pergunta ao Flask. Um import
# escrito e um import que executou sao coisas diferentes.
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from apps import create_app                                  # noqa: E402
from apps.config import DebugConfig                          # noqa: E402
app = create_app(DebugConfig)
regras = {str(r) for r in app.url_map.iter_rules()}
check('/api/tickets registrada', '/api/tickets' in regras, True)
check('/api/tickets/<ticket_id> registrada',
      '/api/tickets/<ticket_id>' in regras, True)
check('/api/tickets/<ticket_id>/comment registrada',
      '/api/tickets/<ticket_id>/comment' in regras, True)
for r in ('/reconciliation-fxo', '/reconciliation-fxo/data',
          '/reconciliation-fxo/run', '/reconciliation-fxo/comment',
          '/onboarding', '/onboarding/tracking-docs', '/cgd',
          '/api/onboarding/overview', '/api/onboarding/docs',
          '/api/onboarding/docs/save', '/api/onboarding/docs/delete'):
    check('%s registrada' % r, r in regras, True)

print('\n== 8. o que saiu do routes.py nao ficou nele ==')
# Codigo duplicado nos dois lugares e a falha classica de uma extracao pela
# metade: os dois divergem, e a que vale e a que o decorador registrou.
for morto in ('_tk_roles_by_sid', '_tk_can_view', '_tk_public',
              '_tk_send_closed_email', 'def api_tickets_list',
              '_cgd_form_ctx', '_cgd_db_ready', 'def api_onboarding_docs',
              'def reconciliation_fxo_run', 'def reconciliation_fxo_comment'):
    check('%s saiu do routes.py' % morto, morto in rotas_py, False)

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
