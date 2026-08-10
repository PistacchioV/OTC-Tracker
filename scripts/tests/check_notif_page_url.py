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
dupes = sorted({u for u in PY.values() if list(PY.values()).count(u) > 1})
check('nenhum destino repetido', dupes, [])

print('\n== 4. o Daily Settlement tem o rotulo dele ==')
check('a constante existe', hasattr(R, '_NOTIF_DS_OTHERPUB'), True)
check('e aponta para a tela de LIQUIDACAO',
      PY.get(R._NOTIF_DS_OTHERPUB), '/ndf-other-publisher')
check('   nao para a de New Deals',
      PY.get(R._NOTIF_DS_OTHERPUB) == PY.get('NDF Other Publisher'), False)
check('o New Deals segue apontando para a dele',
      PY.get('NDF Other Publisher'), '/new_deals-ndf-otherpublisher')
# As quatro notificacoes da tela de liquidacao tem de usar a constante.
SRC = read('apps/pages/routes.py')
blk = SRC.split("@blueprint.route('/api/ndf-other-publisher/data')", 1)[1] \
         .split('#  Cognos', 1)[0]
check('as notificacoes da tela usam a constante', blk.count('_NOTIF_DS_OTHERPUB'), 4)
check('   e nenhuma usa o rotulo do New Deals', "'NDF Other Publisher'," in blk, False)

print('\n== 5. cada notificacao grava o par (acao, pagina) certo ==')
# `page` e o DESTINO do clique, nao o assunto. A Recon FXO gravava
# ('Recon FXO', 'Reconciliation') -- e 'Reconciliation' e a pagina do Pay/Rec,
# entao o sino levava para a recon errada.
blk = SRC.split("def reconciliation_fxo_run", 1)[1].split('\n@blueprint', 1)[0]
check('a Recon FXO grava a pagina dela', "'Recon Generated', 'Recon FXO'" in blk, True)
check('   e nao a do Pay/Rec', "'Reconciliation'," in blk, False)
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

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
