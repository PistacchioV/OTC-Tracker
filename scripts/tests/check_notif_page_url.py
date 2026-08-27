"""Notificacoes: o de-para rotulo -> pagina existe TRES vezes.

O rotulo `page` de uma notificacao decide DUAS coisas:

  * para onde o clique leva — e o mapa vive em tres lugares: `_NOTIF_PAGE_URL`
    no `routes.py`, `PAGE_URL` no `partials/topbar.html` (clique no sino) e
    `PAGE_URL` no `static/js/sw-push.js` (clique no push do sistema);
  * QUEM enxerga a notificacao — `api_get_notifications` filtra pelo acesso a
    pagina que o rotulo aponta.

Duas paginas com o MESMO rotulo e o defeito que este teste nasceu para prender:
o Daily Settlement > NDF > Other Publisher usava o rotulo do New Deals, entao a
notificacao do Send abria a tela de New Deals — e sumia para quem so tem a de
liquidacao liberada. Nada acusava: o aviso aparecia, so levava ao lugar errado.

E os tres mapas divergem em silencio: quando este teste foi escrito, o
`sw-push.js` ja estava sem 'NDF Vanilla' e sem 'Intrag Swap' — um clique no push
desses dois nao ia a lugar nenhum, enquanto o mesmo clique no sino funcionava.

O que se prende aqui:

  1. os tres mapas com as MESMAS chaves e os MESMOS destinos;
  2. todo destino sendo uma pagina que existe no menu;
  3. rotulos distintos para paginas distintas (nenhum destino repetido);
  4. o rotulo do Daily Settlement apontando para a tela de liquidacao, nao para
     a de New Deals.

Nao encosta em dado real: le os tres arquivos.
"""
import io
import json
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding='utf-8', errors='ignore').read()


def js_map(src, marker):
    """{'rotulo': '/url'} do literal JS que segue `marker`. Comentarios de linha
    saem fora — um `// 'X': '/y'` comentado nao e uma entrada."""
    body = src.split(marker, 1)[1].split('};', 1)[0]
    body = re.sub(r'//[^\n]*', '', body)
    return dict(re.findall(r"'([^']+)'\s*:\s*'(/[^']*)'", body))


PY = R._NOTIF_PAGE_URL
TOP = js_map(read('apps/templates/partials/topbar.html'), 'var PAGE_URL = {')
SW = js_map(read('apps/static/js/sw-push.js'), 'var PAGE_URL = {')

print('== 1. os tres mapas concordam ==')
check('routes.py tem entradas', len(PY) > 10, True)
check('topbar tem o mesmo tanto', len(TOP), len(PY))
check('sw-push tem o mesmo tanto', len(SW), len(PY))
check('topbar sem chave a mais/a menos', sorted(set(TOP) ^ set(PY)), [])
check('sw-push sem chave a mais/a menos', sorted(set(SW) ^ set(PY)), [])
check('topbar com os mesmos destinos',
      sorted(k for k in PY if TOP.get(k) != PY[k]), [])
check('sw-push com os mesmos destinos',
      sorted(k for k in PY if SW.get(k) != PY[k]), [])

print('\n== 2. todo destino e uma pagina do menu ==')
NAV = set(re.findall(r'href="(/[^"#?]*)"', read('apps/templates/partials/sidenav.html')))
check('nenhum destino fora do menu', sorted({u for u in PY.values() if u not in NAV}), [])

print('\n== 3. um rotulo por pagina ==')
# Dois rotulos apontando para a MESMA pagina e inofensivo; a mesma pagina com
# dois rotulos, nao — mas o inverso (um rotulo para duas paginas) e impossivel
# num dict. O que se prende aqui e o destino repetido, que sinaliza rotulo
# duplicado sem querer.
#
# Excecao DELIBERADA: rotulo LEGADO de pagina renomeada. O aviso gravado no
# sino carrega o rotulo antigo para sempre, entao ele fica nos mapas ao lado
# do novo — 'File Interface' e o rotulo historico do File Interpreter
# (a pagina mudou de /file-interface para /file-interpreter em 2026-08-21).
LEGACY_ALIASES = {'File Interface'}
vals = [u for k, u in PY.items() if k not in LEGACY_ALIASES]
dupes = sorted({u for u in vals if vals.count(u) > 1})
check('nenhum destino repetido (fora aliases legados)', dupes, [])
check('todo alias legado aponta para pagina que tem rotulo atual',
      sorted({PY[a] for a in LEGACY_ALIASES if a in PY} -
             {u for k, u in PY.items() if k not in LEGACY_ALIASES}), [])

print('\n== 4. o Daily Settlement tem o rotulo dele ==')
check('a constante existe', hasattr(R, '_NOTIF_DS_OTHERPUB'), True)
check('e aponta para a tela de LIQUIDACAO',
      PY.get(R._NOTIF_DS_OTHERPUB), '/ndf-other-publisher')
check('   nao para a de New Deals',
      PY.get(R._NOTIF_DS_OTHERPUB) == PY.get('NDF Other Publisher'), False)
check('o New Deals segue apontando para a dele',
      PY.get('NDF Other Publisher'), '/new_deals-ndf-otherpublisher')
# As quatro notificacoes da tela de liquidacao tem de usar a constante.
# O `routes.py` MAIS as verticais de `apps/pages/features/`. Este guarda casa por
# TEXTO e por AST, entao codigo que sai do routes.py sai da varredura junto — e o
# jeito de isso aparecer nao e uma assercao vermelha, e uma que deixa de existir.
# Concatenar as duas fontes mantem a cobertura a cada extracao, sem editar este
# arquivo de novo. (A Recon FXO foi a primeira a sair: sem isto, o `split` da
# secao 5 estourava com IndexError.)
def _fontes_com_rotas():
    partes = [read('apps/pages/routes.py')]
    # A arvore de platform/ entra pela mesma razao das features: o motor do
    # sino mora la desde a fatia `platform/notifications.py`, e um
    # `_create_notification` chamado de la com rotulo literal tem de passar
    # pela mesma varredura.
    for sub in ('features', 'platform'):
        base = os.path.join(ROOT, 'apps', 'pages', sub)
        for raiz, dirs, arqs in os.walk(base):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for a in sorted(arqs):
                if a.endswith('.py'):
                    partes.append(io.open(os.path.join(raiz, a), encoding='utf-8').read())
    return '\n'.join(partes)


SRC = _fontes_com_rotas()
# A tela mora em features/ndf_other_publisher — o bloco é o entrypoint inteiro.
blk = io.open(os.path.join(ROOT, 'apps', 'pages', 'features', 'ndf_other_publisher',
                           'entrypoint.py'), encoding='utf-8').read()
check('as notificacoes da tela usam a constante', blk.count('_NOTIF_DS_OTHERPUB'), 4)
check('   e nenhuma usa o rotulo do New Deals', "'NDF Other Publisher'," in blk, False)

print('\n== 5. cada notificacao grava o par (acao, pagina) certo ==')
# `page` e o DESTINO do clique, nao o assunto. A Recon FXO gravava
# ('Recon FXO', 'Reconciliation') -- e 'Reconciliation' e a pagina do Pay/Rec,
# entao o sino levava para a recon errada.
# O par da Recon FXO virou constante na vertical (`commands.NOTIF_ACTION` /
# `NOTIF_PAGE`), entao a assercao pergunta pelas constantes e nao pela linha do
# endpoint — o endpoint hoje passa `commands.NOTIF_PAGE`, nao um literal.
from apps.pages.features.reconciliation_fxo import commands as _rfxo_cmd  # noqa: E402
check('a Recon FXO grava a pagina dela',
      (_rfxo_cmd.NOTIF_ACTION, _rfxo_cmd.NOTIF_PAGE), ('Recon Generated', 'Recon FXO'))
check('   e nao a do Pay/Rec', _rfxo_cmd.NOTIF_PAGE == 'Reconciliation', False)
blk = SRC.split("def reconciliation_payrec_run", 1)[1].split('\n@blueprint', 1)[0]
check('o Pay/Rec continua com a dele', "'Reconciliation'," in blk, True)

print('\n== 6. as notificacoes JA GRAVADAS ainda acham a pagina ==')
# O que esta no banco nao se reescreve: a traducao do par antigo tem de existir
# nos TRES lugares, senao o clique do sino, o do push e o filtro de acesso
# discordam sobre a mesma notificacao.
check('routes traduz o par antigo',
      R._notif_page_url('Reconciliation', 'Recon FXO'), '/reconciliation-fxo')
check('   e o Pay/Rec continua no lugar',
      R._notif_page_url('Reconciliation', 'Pay/Rec Reconciliation'), '/reconciliation-payrec')
check('   o par novo tambem resolve', R._notif_page_url('Recon FXO'), '/reconciliation-fxo')
for arq, rot in (('apps/templates/partials/topbar.html', 'o topbar'),
                 ('apps/static/js/sw-push.js', 'o service worker')):
    src = read(arq)
    check('%s traduz o par antigo' % rot,
          "n.page === 'Reconciliation' && n.action === 'Recon FXO'" in src, True)
    check('   e usa a chave traduzida no lookup' if rot == 'o topbar'
          else '   e usa a chave traduzida no lookup ', 'PAGE_URL[nPage]' in src, True)

print('\n== 7. toda notificacao gravada tem destino no mapa ==')
# O buraco pelo qual o TED Release passou: os checks 1-6 provam que os tres
# mapas concordam ENTRE SI, mas nada prendia um `_create_notification` gravando
# um rotulo que nao esta em mapa nenhum — o aviso aparecia no sino e o clique
# nao ia a lugar nenhum (nove paginas estavam assim). Aqui o routes.py inteiro
# e varrido por AST: todo rotulo `page` LITERAL passado a `_create_notification`
# tem de resolver via `_notif_page_url`. Rotulo que vem de expressao
# (cfg['label'], _NOTIF_DS_OTHERPUB, variavel) fica fora — as constantes ja
# sao presas nos checks acima, e as demais expressoes carregam rotulos que o
# proprio mapa lista.
import ast

_pages_sem_mapa = {}
for node in ast.walk(ast.parse(SRC)):
    if not isinstance(node, ast.Call):
        continue
    f = node.func
    if getattr(f, 'id', getattr(f, 'attr', '')) != '_create_notification':
        continue
    if len(node.args) < 4 or not isinstance(node.args[3], ast.Constant):
        continue
    page = node.args[3].value
    if not R._notif_page_url(page):
        _pages_sem_mapa.setdefault(page, []).append(node.lineno)
check('nenhum rotulo gravado fora do mapa',
      sorted('%s (L%s)' % (p, ls[0]) for p, ls in _pages_sem_mapa.items()), [])

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 8. os DOIS caminhos do balao mostram a MESMA marca ==')
# O mesmo aviso sai por dois caminhos — `maybeNativeNotify` (aba aberta e sem
# foco) e o `showNotification` do service worker (aba fechada) —, e cada um
# escrevia o seu icone. O `badge` do topbar ficou apontando para o
# `favicon.ico` do template comprado (so as barras azuis, sem as letras: a
# marca CLARA) enquanto o sw-push ja usava outra, e o mesmo alerta parecia de
# dois aplicativos.
import re                                                    # noqa: E402

_topbar = io.open(os.path.join(ROOT, 'apps', 'templates', 'partials', 'topbar.html'),
                  encoding='utf-8').read()
_swpush = io.open(os.path.join(ROOT, 'apps', 'static', 'js', 'sw-push.js'),
                  encoding='utf-8').read()


def _marcas(fonte):
    """As imagens citadas em `icon:`/`badge:` — literais e por constante."""
    achadas = set()
    for m in re.finditer(r"""(?:icon|badge)\s*:\s*(?:'([^']+)'|([A-Za-z_$][\w$]*))""", fonte):
        literal, nome = m.group(1), m.group(2)
        if literal:
            achadas.add(literal)
        else:
            for v in re.finditer(r"var\s+%s\s*=\s*'([^']+)'" % re.escape(nome), fonte):
                achadas.add(v.group(1))
    # a foto do autor nao e marca do app; ela e o caso COM avatar
    return {a for a in achadas if '/images/' in a}


_do_topbar, _do_sw = _marcas(_topbar), _marcas(_swpush)
check('o topbar usa uma marca so', sorted(_do_topbar), sorted(_do_topbar)[:1])
check('o sw-push tambem', sorted(_do_sw), sorted(_do_sw)[:1])
check('e as duas sao a MESMA', _do_topbar, _do_sw)

for _img in sorted(_do_topbar | _do_sw):
    _abs = os.path.join(ROOT, 'apps', _img.lstrip('/'))
    check('o arquivo existe: ' + _img, os.path.isfile(_abs), True)
    # O balao amplia o icone para ~48px: uma imagem de 16x16 sai lavada.
    try:
        from PIL import Image
        with Image.open(_abs) as _im:
            check('   e nao e pequeno demais (>=64px)', min(_im.size) >= 64, True)
    except ImportError:
        print('  --  Pillow ausente: tamanho nao conferido')

check('o topbar tem queda quando o autor nao tem foto',
      'foto.onerror' in _topbar, True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
