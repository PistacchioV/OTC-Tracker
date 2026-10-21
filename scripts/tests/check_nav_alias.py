# -*- coding: utf-8 -*-
"""A mesma página em DOIS lugares do menu acende o item CLICADO (mesa, 21/10/2026).

As telas da Intrag › DCE (Option, Swap, NDF, DFW) têm atalho em New Deals ›
DCE, com o MESMO endereço (`/intrag-dce-*`). O menu (`otc.js`, `findActive`)
acendia a PRIMEIRA folha com o endereço da página — a de New Deals, que vem
antes no menu —, e quem clicava em Intrag › DCE › Option via New Deals › DCE
› Option aberto. Em 15/09 o NDF chegou a sair de New Deals por isso
(`74a04fd1`), e a página "sumiu" para quem a procurava lá.

Prende:
  1. no sidenav, todo endereço repetido na árvore tem UM dono sem
     `data-nav-alias` (as outras cópias são atalho), e New Deals › DCE tem os
     quatro atalhos — DFW, NDF, Option, Swap;
  2. no Chromium, com o sidenav e o `otc.js` DE VERDADE (a página renderizada
     pelo app): aberta direto, a tela acende o menu DONO (Intrag › DCE);
     clicada em New Deals › DCE, acende New Deals; clicada em Intrag › DCE,
     volta a acender Intrag. E o ladrilho do título procura o link dono.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_nav_alias.py
"""
import os
import re
import sys
from urllib.parse import urlparse

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
STATIC = os.path.join(ROOT, 'apps', 'static')
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

FALHAS = []


def check(label, ok):
    print(('  ok  ' if ok else '  FAIL  ') + label)
    if not ok:
        FALHAS.append(label)


print('== 1. o sidenav: um dono por endereço, os atalhos marcados ==')
with open(os.path.join(ROOT, 'apps', 'templates', 'partials', 'sidenav.html'), encoding='utf-8') as fh:
    SIDENAV = fh.read()
links = re.findall(r'<a\s+href="(/[^"#?]*)"\s+class="side-nav-link"([^>]*)>', SIDENAV)
por_href = {}
for href, resto in links:
    por_href.setdefault(href, []).append('data-nav-alias' in resto)
repetidos = {h: v for h, v in por_href.items() if len(v) > 1}
check('as quatro telas da Intrag › DCE estão nos dois menus',
      sorted(repetidos) == ['/intrag-dce-dfw', '/intrag-dce-ndf', '/intrag-dce-option', '/intrag-dce-swap'])
check('cada endereço repetido tem EXATAMENTE um dono (sem data-nav-alias)',
      all(v.count(False) == 1 for v in repetidos.values()))
bloco = SIDENAV[SIDENAV.index('id="newDealsDCE"'):]
bloco = bloco[:bloco.index('</ul>')]
check('New Deals › DCE: os quatro são atalho (DFW, NDF, Option, Swap)',
      re.findall(r'href="(/intrag-dce-[a-z]+)" class="side-nav-link" data-nav-alias', bloco)
      == ['/intrag-dce-dfw', '/intrag-dce-ndf', '/intrag-dce-option', '/intrag-dce-swap'])
with open(os.path.join(STATIC, 'js', 'otc.js'), encoding='utf-8') as fh:
    OTCJS = fh.read()
check('o otc.js lembra o item clicado e prefere o dono',
      'NAV_PICK' in OTCJS and "hasAttribute('data-nav-alias')" in OTCJS)
with open(os.path.join(ROOT, 'apps', 'templates', 'layouts', 'vertical.html'), encoding='utf-8') as fh:
    VERTICAL = fh.read()
# as telas da DCE desenham o próprio ícone no h4 (o ladrilho automático não
# entra nelas); a regra vale para a próxima página que estiver em dois menus
check('o ladrilho do título procura primeiro o link DONO (:not([data-nav-alias]))',
      "sel + ':not([data-nav-alias])'" in VERTICAL)


print('== 2. no Chromium, com o sidenav e o otc.js de verdade ==')
try:
    from playwright.sync_api import sync_playwright
except ImportError:                                              # pragma: no cover
    sync_playwright = None
    print('  (sem playwright: seção pulada)')

if sync_playwright:
    from apps.config import DebugConfig
    from apps import create_app

    app = create_app(DebugConfig)
    app.config['TESTING'] = True
    cl = app.test_client()
    with cl.session_transaction() as s:
        s.update({'authenticated': True, 'user_sid': 'T000000', 'user_name': 'Tester',
                  'user_role': 'ADMIN', 'session_ip': '127.0.0.1'})
    paginas = {}
    for p in ('/intrag-dce-option', '/intrag-dce-ndf'):
        r = cl.get(p)
        check('%s renderiza (200)' % p, r.status_code == 200)
        paginas[p] = r.get_data(as_text=True)

    def servir(route):
        u = urlparse(route.request.url)
        if u.path in paginas:
            return route.fulfill(status=200, content_type='text/html; charset=utf-8', body=paginas[u.path])
        if u.path.startswith('/static/'):
            arq = os.path.join(STATIC, u.path[len('/static/'):])
            if os.path.isfile(arq):
                tipo = {'.js': 'application/javascript', '.css': 'text/css', '.svg': 'image/svg+xml',
                        '.json': 'application/json'}.get(os.path.splitext(arq)[1], 'application/octet-stream')
                with open(arq, 'rb') as fh:
                    return route.fulfill(status=200, content_type=tipo, body=fh.read())
            return route.fulfill(status=404, body='')
        return route.fulfill(status=200, content_type='application/json', body='{}')

    def trilha(pg):
        # o caminho aberto no menu: as migalhas (Menu › …) + o rótulo do voltar
        pg.wait_for_selector('.dd-nav .dd-panel.dd-current', timeout=15000)
        return pg.evaluate("""() => {
            const c = [...document.querySelectorAll('.dd-nav .dd-crumbs .dd-crumb')].map(b => b.textContent.trim());
            const back = document.querySelector('.dd-nav .dd-panel.dd-current .dd-back-link');
            const ativo = document.querySelector('.dd-nav .dd-panel.dd-current a.dd-leaf.active');
            return {crumbs: c, back: back ? back.textContent.trim() : '', ativo: ativo ? ativo.textContent.trim() : ''};
        }""")

    def clicar(pg, *rotulos):
        # do topo do menu até a folha, pelo rótulo de cada nível
        pg.locator('.dd-nav .dd-crumbs .dd-crumb').first.click()
        for r in rotulos:
            alvo = pg.locator('.dd-nav .dd-panel.dd-current > li > a', has_text=re.compile(r'^\s*%s\s*$' % re.escape(r)))
            alvo.first.wait_for(timeout=10000)
            alvo.first.click()
            pg.wait_for_timeout(250)

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(reduced_motion='reduce')
        pg = ctx.new_page()
        pg.route('http://otc.test/**', servir)

        pg.goto('http://otc.test/intrag-dce-option')
        t = trilha(pg)
        check('aberta DIRETO, acende o dono: Intrag › DCE › Option (era New Deals) %s' % t,
              'Intrag' in t['crumbs'] and 'New Deals' not in t['crumbs'] and t['back'] == 'DCE' and t['ativo'] == 'Option')
        with pg.expect_navigation():
            clicar(pg, 'New Deals', 'DCE', 'Option')
        t = trilha(pg)
        check('clicada em New Deals › DCE › Option, acende New Deals %s' % t,
              'New Deals' in t['crumbs'] and t['back'] == 'DCE' and t['ativo'] == 'Option')

        with pg.expect_navigation():
            clicar(pg, 'Intrag', 'DCE', 'Option')
        t = trilha(pg)
        check('clicada em Intrag › DCE › Option, volta a acender Intrag %s' % t,
              'Intrag' in t['crumbs'] and 'New Deals' not in t['crumbs'] and t['ativo'] == 'Option')

        with pg.expect_navigation():
            clicar(pg, 'New Deals', 'DCE', 'NDF')
        t = trilha(pg)
        check('o NDF voltou a New Deals › DCE e acende lá quando clicado ali %s' % t,
              'New Deals' in t['crumbs'] and t['ativo'] == 'NDF')
        b.close()

print()
if FALHAS:
    print('FALHOU: %d' % len(FALHAS))
    sys.exit(1)
print('TUDO OK')
