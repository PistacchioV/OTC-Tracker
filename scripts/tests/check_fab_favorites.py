# -*- coding: utf-8 -*-
"""check_fab_favorites.py — o botão flutuante de favoritos da casca (§658).

O "AssistiveTouch" do iPad no OTC Tracker: um "+" por cima de toda página do
layout, que a pessoa ARRASTA para onde quiser e que, aberto, favorita a página
atual e lista os favoritos. Prende:

  1. a regra PURA (`user_home.domain.clean_favorites`): só caminho deste app
     (nada de `//host`, `http:`, `javascript:`, `/api/`), sem repetir, até 24,
     rótulo enxuto; o que não é lista é recusado com código;
  2. a API (`/api/user-home/favorites`): o documento do SID, sem sessão é 401;
  3. no Chromium, com as páginas RENDERIZADAS pelo app (o `otc.js` e o
     `otc.css` de verdade): o botão nasce à esquerda da barra do topo (o
     painel abre abaixo dele), abre o painel,
     favorita a página (gravando no SERVIDOR), mostra o nome e o caminho do
     menu DONO (Option é Intrag › DCE, não o atalho de New Deals), remove com
     Undo, fecha no Esc e no clique fora, ARRASTA para QUALQUER lugar e fica
     onde foi solto (§659; o clique do arrasto não abre o painel), lembra o
     lugar depois do reload (e converte o formato antigo, de borda), agrupa os
     favoritos nos BLOCOS do menu lateral, na ordem dele (§659), esmaece
     parado, fala português e, no modo opaco, o painel é SÓLIDO.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_fab_favorites.py
"""
import os
import sys
import tempfile
from urllib.parse import urlparse

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(label, ok, extra=''):
    print(('  ok  ' if ok else '  FAIL  ') + label + (('  — ' + str(extra)) if (not ok and extra) else ''))
    if not ok:
        FALHAS.append(label)


def main():
    from apps.config import DebugConfig
    from apps import create_app
    from apps.pages.features.user_home import domain as D
    from apps.pages.features.user_home.infra import store

    print('== 1. a regra dos favoritos ==')
    lixo = [{'url': '/new_deals-swap-cetes', 'label': '  Swap   Cetes '}, {'url': '//evil.com/x'},
            {'url': 'http://evil.com'}, {'url': 'javascript:alert(1)'}, {'url': '/api/settings'},
            {'url': '/new_deals-swap-cetes', 'label': 'dup'}, {'url': '/intrag-swap#topo', 'label': 'Intrag'},
            {'url': '/a b'}, {'url': '/x"y'}, 'nao-e-dict']
    check('so caminho deste app, sem repetir, rotulo enxuto, sem o #',
          D.clean_favorites(lixo) == [{'url': '/new_deals-swap-cetes', 'label': 'Swap Cetes'},
                                      {'url': '/intrag-swap', 'label': 'Intrag'}], D.clean_favorites(lixo))
    check('teto de %d' % D.MAX_FAVORITES,
          len(D.clean_favorites([{'url': '/p%d' % i} for i in range(40)])) == D.MAX_FAVORITES)
    try:
        D.clean_favorites('x')
        check('o que nao e lista e recusado com codigo', False)
    except D.HomeError as e:
        check('o que nao e lista e recusado com codigo', e.code == 'favorites_invalid')
    check('documento antigo (sem a chave) e lista vazia', D.favorites({'sid': 'X'}) == [])

    print('== 2. a API ==')
    store.ROOT = tempfile.mkdtemp(prefix='otc-fab-')
    app = create_app(DebugConfig)
    app.config['TESTING'] = True
    check('sem sessao e 401', app.test_client().get('/api/user-home/favorites').status_code == 401)
    cl = app.test_client()
    with cl.session_transaction() as s:
        s.update({'authenticated': True, 'user_sid': 'T000000', 'user_name': 'Tester', 'user_role': 'ADMIN',
                  'session_ip': '127.0.0.1'})
    check('GET de quem nunca favoritou: vazio', cl.get('/api/user-home/favorites').get_json() == {'success': True, 'favorites': []})
    r = cl.post('/api/user-home/favorites', json={'favorites': lixo})
    check('POST grava a lista LIMPA no documento do SID',
          r.status_code == 200 and [f['url'] for f in r.get_json()['favorites']] == ['/new_deals-swap-cetes', '/intrag-swap']
          and [f['url'] for f in store.load('T000000')['favorites']] == ['/new_deals-swap-cetes', '/intrag-swap'])
    r = cl.post('/api/user-home/favorites', json={'favorites': 'x'})
    check('POST que nao e lista: 400 com codigo', r.status_code == 400 and r.get_json().get('code') == 'favorites_invalid')
    cl.post('/api/user-home/favorites', json={'favorites': []})

    print('== 3. no Chromium ==')
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:                                          # pragma: no cover
        print('  (sem playwright: secao pulada)')
        return

    def servir(route):
        req = route.request
        u = urlparse(req.url)
        resp = cl.open(u.path + ('?' + u.query if u.query else ''), method=req.method, data=req.post_data_buffer,
                       headers={'Content-Type': req.headers.get('content-type', '')})
        route.fulfill(status=resp.status_code, body=resp.get_data(),
                      headers={'Content-Type': resp.headers.get('Content-Type', 'text/html')})

    def fab_box(pg):
        return pg.evaluate("() => { const r = document.querySelector('.otc-fab').getBoundingClientRect(); "
                           "return [Math.round(r.left), Math.round(r.top), innerWidth, innerHeight]; }")

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        ctx = b.new_context(viewport={'width': 1440, 'height': 900}, reduced_motion='reduce')
        pg = ctx.new_page()
        erros = []
        pg.on('pageerror', lambda e: erros.append(str(e)))
        pg.route('http://otc.test/**', servir)

        pg.goto('http://otc.test/intrag-dce-option')
        pg.wait_for_selector('.otc-fab__btn', timeout=15000)
        x, y, w, h = fab_box(pg)
        tb = pg.evaluate("() => { const r = document.querySelector('.app-topbar').getBoundingClientRect(); return [r.left, r.top, r.height]; }")
        check('sem lugar gravado, nasce a ESQUERDA da barra do topo, no meio da altura dela',
              abs(x - (tb[0] - 12 - 52)) <= 1 and abs(y - (tb[1] + (tb[2] - 52) / 2)) <= 1, (x, y, tb))
        pg.click('.otc-fab__btn')
        pg.wait_for_timeout(400)            # a entrada do painel (escala .96 -> 1)
        pr = pg.evaluate("() => { const p = document.querySelector('.otc-fab__panel').getBoundingClientRect(), "
                         "b = document.querySelector('.otc-fab').getBoundingClientRect(); return [p.top, b.bottom, p.right, b.right]; }")
        check('la em cima, o painel abre ABAIXO do botao, alinhado a ele', pr[0] >= pr[1] and abs(pr[2] - pr[3]) <= 1, pr)
        check('o clique abre o painel, vazio, com "Add this page"',
              pg.is_visible('.otc-fab__panel') and pg.is_visible('.otc-fab__empty')
              and pg.inner_text('.otc-fab__star').strip() == 'Add this page')
        pg.click('.otc-fab__star')
        pg.wait_for_timeout(600)
        check('favoritar grava no SERVIDOR (o documento do SID)',
              [f['url'] for f in cl.get('/api/user-home/favorites').get_json()['favorites']] == ['/intrag-dce-option'])
        item = pg.inner_text('.otc-fab__list').replace('\n', ' ')
        check('o item diz o nome e o caminho do menu DONO (Intrag › DCE), com o icone do menu',
              'Option' in item and 'Intrag' in item and 'New Deals' not in item
              and pg.locator('.otc-fab__list .otc-fab__ico svg, .otc-fab__list .otc-fab__ico i').count() == 1, item)
        check('a estrela fica ACESA ("In favorites")',
              'is-on' in pg.get_attribute('.otc-fab__star', 'class') and pg.inner_text('.otc-fab__star').strip() == 'In favorites')
        pg.keyboard.press('Escape')
        check('o Esc fecha', not pg.is_visible('.otc-fab__panel'))

        pg.goto('http://otc.test/new_deals-swap-cetes')
        pg.wait_for_selector('.otc-fab__btn')
        pg.click('.otc-fab__btn')
        check('em outra pagina a lista ja esta la (a copia do navegador)', pg.locator('.otc-fab__item').count() == 1)
        pg.click('.otc-fab__star')
        pg.wait_for_timeout(600)
        check('dois favoritos, na ORDEM DO MENU (New Deals antes de Intrag), nao na de entrada',
              [i.get_attribute('href') for i in pg.locator('.otc-fab__item').all()] == ['/new_deals-swap-cetes', '/intrag-dce-option'])
        pg.hover('.otc-fab__item[href="/intrag-dce-option"]')
        pg.click('.otc-fab__del[data-url="/intrag-dce-option"]')
        pg.wait_for_timeout(600)
        check('o x remove (e grava)', pg.locator('.otc-fab__item').count() == 1
              and [f['url'] for f in cl.get('/api/user-home/favorites').get_json()['favorites']] == ['/new_deals-swap-cetes'])
        check('com o aviso da casa e o Undo', pg.is_visible('.otc-toast .otc-toast__undo'))
        pg.click('.otc-toast .otc-toast__undo')
        pg.wait_for_timeout(600)
        check('o Undo devolve o favorito', [f['url'] for f in cl.get('/api/user-home/favorites').get_json()['favorites']]
              == ['/intrag-dce-option', '/new_deals-swap-cetes'])
        pg.mouse.click(700, 450)
        check('o clique fora fecha', not pg.is_visible('.otc-fab__panel'))

        # o ARRASTO: para o MEIO da pagina, e ele fica ali (sem encostar)
        x, y, w, h = fab_box(pg)
        pg.mouse.move(x + 26, y + 26)
        pg.mouse.down()
        for k in range(1, 11):
            pg.mouse.move(x + 26 - k * (x - 700) / 10, y + 26 - k * (y - 400) / 10)
        pg.mouse.up()
        pg.wait_for_timeout(500)
        x2, y2, _, _ = fab_box(pg)
        check('solto no MEIO da pagina, fica onde foi solto (nao encosta na borda)',
              abs(x2 - 700) <= 2 and abs(y2 - 400) <= 2, (x2, y2))
        check('o clique do arrasto NAO abre o painel', not pg.is_visible('.otc-fab__panel'))
        pg.click('.otc-fab__btn')
        pr = pg.evaluate("() => { const r = document.querySelector('.otc-fab__panel').getBoundingClientRect(); return [r.left, r.right, r.top, r.bottom, innerWidth, innerHeight]; }")
        check('aberto no meio, o painel cabe na janela', pr[0] >= 0 and pr[1] <= pr[4] and pr[2] >= 0 and pr[3] <= pr[5], pr)
        pg.keyboard.press('Escape')
        pg.reload()
        pg.wait_for_selector('.otc-fab__btn')
        x3, y3, _, _ = fab_box(pg)
        check('o lugar e lembrado depois do reload', abs(x3 - x2) <= 2 and abs(y3 - y2) <= 2, (x3, y3))
        pg.evaluate("localStorage.setItem('__OTC_FAB_POS__', JSON.stringify({side: 'left', y: 0.5}))")
        pg.reload()
        pg.wait_for_selector('.otc-fab__btn')
        x4, _, _, _ = fab_box(pg)
        check('a posicao no formato antigo (encostada na borda) e convertida', x4 == 14, x4)

        # os BLOCOS do menu: Data Base depois de Products, e dentro de Products a
        # ORDEM do menu (New Deals antes de Intrag), nao a ordem em que entraram;
        # o que nao esta no menu vai em Others, no fim
        cl.post('/api/user-home/favorites', json={'favorites': [
            {'url': '/initiatives/PRJ-0001', 'label': 'PRJ-0001 Painel'}, {'url': '/mapping'},
            {'url': '/intrag-dce-option'}, {'url': '/new_deals-swap-cetes'}]})
        pg.goto('http://otc.test/intrag-swap')
        pg.wait_for_selector('.otc-fab__btn')
        pg.click('.otc-fab__btn')
        pg.wait_for_timeout(700)
        ordem = pg.evaluate("() => [...document.querySelectorAll('.otc-fab__list > li')].map(li => "
                            "li.classList.contains('otc-fab__group') ? '#' + li.textContent.trim() : li.querySelector('a').getAttribute('href'))")
        check('os favoritos em BLOCOS, como o menu lateral, na ordem dele',
              ordem == ['#Products', '/new_deals-swap-cetes', '/intrag-dce-option', '#Data Base', '/mapping',
                        '#Others', '/initiatives/PRJ-0001'], ordem)
        tit = pg.evaluate("() => getComputedStyle(document.querySelector('.otc-fab__group')).textTransform")
        check('o titulo do bloco no desenho do titulo do menu (caixa alta)', tit == 'uppercase', tit)
        pg.keyboard.press('Escape')
        pg.mouse.move(5, 5)
        pg.wait_for_timeout(3800)
        check('parado, ele esmaece', 'is-idle' in pg.get_attribute('.otc-fab', 'class'))
        check('sem erro de JS', not erros, erros)
        ctx.close()

        # portugues e modo opaco
        ctx = b.new_context(viewport={'width': 1440, 'height': 900}, reduced_motion='reduce')
        ctx.add_init_script("localStorage.setItem('__OTC_TRACKER_LANG__','br'); localStorage.setItem('__OTC_TRACKER_FX__','reduced');")
        pg = ctx.new_page()
        pg.route('http://otc.test/**', servir)
        pg.goto('http://otc.test/intrag-swap')
        pg.wait_for_selector('.otc-fab__btn')
        pg.click('.otc-fab__btn')
        check('em portugues: "Favoritos" e "Favoritar esta pagina"',
              pg.inner_text('.otc-fab__title') == 'Favoritos' and pg.inner_text('.otc-fab__star').strip() == 'Favoritar esta página')
        bg = pg.evaluate("() => { const s = getComputedStyle(document.querySelector('.otc-fab__panel')); "
                         "return [s.backdropFilter, s.backgroundColor]; }")
        check('no modo opaco o painel e SOLIDO (sem desfoque, sem alfa)',
              bg[0] in ('none', '') and (bg[1].startswith('rgb(') or bg[1].endswith(', 1)')), bg)
        ctx.close()
        b.close()


if __name__ == '__main__':
    main()
    print()
    if FALHAS:
        print('FALHOU: %d' % len(FALHAS))
        sys.exit(1)
    print('TUDO OK')
