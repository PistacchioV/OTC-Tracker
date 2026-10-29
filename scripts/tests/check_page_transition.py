# -*- coding: utf-8 -*-
"""A troca de página sem "piscar" (equipe, 29/10/2026, §723).

Relato: ao mudar de página, ela piscava, o menu lateral voltava para o
original e depois ia para o item clicado, e as tabelas se redimensionavam duas,
três vezes. A referência é o Pane: o menu fica parado e só o conteúdo muda.

Executado no Chromium contra o app de verdade (servidor num thread, sessão
assinada), conferindo o estado no `interactive` — o DOM pronto, ANTES dos
handlers do `otc.js` (que roda no `DOMContentLoaded`):

  1. o MENU: a 1ª carga não tem o que restaurar; o clique numa folha deixa a
     página seguinte já com o drill-down, a lente no item clicado e o menu de
     origem escondido, antes do `otc.js`; o retrato vale uma vez só;
  2. o menu DESAFIXADO já está no `<body>` antes do primeiro paint;
  3. o filtro de ACESSO: para quem tem acesso restrito, a página seguinte já
     nasce com o menu filtrado (a última resposta do /api/me/access, guardada
     na aba);
  4. as TABELAS: o contêiner nasce transparente e aparece uma vez, quando as
     larguras assentam (nada fica transparente para sempre);
  5. o CONTEÚDO: a entrada é a do `.content-page` no CSS (no modo opaco, sem
     animação) e a placa já na tela não ganha a entrada do otc.js.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_page_transition.py
"""
import json
import os
import socket
import sys
import tempfile
import threading

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

TMP = tempfile.mkdtemp(prefix='pagetrans-')
DB = os.path.join(TMP, 'Users_OTCTracker.db')
import duckdb                                              # noqa: E402
_c = duckdb.connect(DB)
_c.execute("""CREATE TABLE users (
        SID VARCHAR PRIMARY KEY, Name VARCHAR, Email VARCHAR,
        Role_Description VARCHAR, Position VARCHAR, Role VARCHAR,
        Status VARCHAR, IP_Address VARCHAR, Page_Access VARCHAR DEFAULT '')""")
_c.execute("INSERT INTO users (SID, Name, Email, Position, Role, Status, Page_Access) VALUES "
           "('A111111', 'Ana Lima', 'ana@jpmorgan.com', 'VP', 'BO', 'Active', ''),"
           "('B222222', 'Bia Melo', 'bia@jpmorgan.com', 'VP', 'BO', 'Active', ?)",
           [json.dumps(['/new_deals-opt-fxo', '/new_deals-opt-commodities', '/dashboard'])])
_c.close()

import run                                                 # noqa: E402
from apps.pages import routes as R                         # noqa: E402
R.DB_PATH = DB

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('skip: sem playwright')
    sys.exit(0)

app = run.app
from werkzeug.serving import make_server                   # noqa: E402
_s = socket.socket()
_s.bind(('127.0.0.1', 0))
PORT = _s.getsockname()[1]
_s.close()
srv = make_server('127.0.0.1', PORT, app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:%d' % PORT


def cookie(sid, nome):
    sess = {'authenticated': True, 'user_sid': sid, 'user_name': nome, 'user_email': '',
            'user_role': 'BO', 'user_position': 'VP', 'session_ip': '127.0.0.1'}
    val = app.session_interface.get_signing_serializer(app).dumps(sess)
    return [{'name': app.config.get('SESSION_COOKIE_NAME', 'session'), 'value': val,
             'domain': '127.0.0.1', 'path': '/'}]


# o estado no `interactive`: o DOM pronto, antes dos handlers do otc.js
INIT = """
document.addEventListener('readystatechange', function () {
  if (document.readyState !== 'interactive') return;
  var host = document.querySelector('.sidenav-menu .dd-nav');
  var act = host && host.querySelector('.dd-panel.dd-current a.active');
  window.__boot = {
    dd: !!host, srcHidden: !!document.querySelector('.side-nav.dd-source-hidden'),
    active: act ? act.getAttribute('href') : null,
    unpinned: document.body.classList.contains('otc-nav-unpinned'),
    hiddenItems: document.querySelectorAll('.side-nav:not(.dd-panel) .side-nav-item[hidden]').length
  };
});
window.__settle = [];
document.addEventListener('DOMContentLoaded', function () {
  new MutationObserver(function (ms) { ms.forEach(function (m) {
    var t = m.target;
    if (t.classList && t.classList.contains('dt-container')) window.__settle.push(t.classList.contains('oxf-settling'));
    if (t.classList && t.classList.contains('otc-enter') && t.getBoundingClientRect().top < innerHeight) window.__enterTop = true;
  }); }).observe(document.body, { subtree: true, attributes: true, attributeFilter: ['class'] });
});
"""

with sync_playwright() as p:
    b = p.chromium.launch()

    print('== 1. o menu atravessa a troca de página ==')
    ctx = b.new_context(viewport={'width': 1600, 'height': 1000})
    ctx.add_cookies([dict(c, domain='127.0.0.1') for c in cookie('A111111', 'Ana Lima')])
    ctx.add_init_script(INIT)
    pg = ctx.new_page()
    erros = []
    pg.on('pageerror', lambda e: erros.append(str(e)))
    pg.goto(BASE + '/new_deals-opt-fxo', wait_until='networkidle')
    pg.wait_for_timeout(1200)
    boot = pg.evaluate('window.__boot')
    check('1ª carga: nada a restaurar (o menu de origem até o otc.js)', (boot['dd'], boot['srcHidden']), (False, False))
    with pg.expect_navigation():
        pg.click('.dd-panel.dd-current a.dd-leaf[href="/new_deals-opt-commodities"]')
    pg.wait_for_load_state('networkidle')
    pg.wait_for_timeout(1500)
    boot = pg.evaluate('window.__boot')
    check('depois do clique: drill-down já pintado ANTES do otc.js', (boot['dd'], boot['srcHidden']), (True, True))
    check('   com a lente no item clicado', boot['active'], '/new_deals-opt-commodities')
    check('   o retrato vale uma vez só', pg.evaluate("sessionStorage.getItem('__OTC_NAV_SNAP__')"), None)
    check('   e o otc.js refez o menu no mesmo item',
          pg.evaluate("(document.querySelector('.dd-panel.dd-current a.active')||{}).getAttribute && "
                      "document.querySelector('.dd-panel.dd-current a.active').getAttribute('href')"),
          '/new_deals-opt-commodities')

    print('\n== 4. as tabelas aparecem uma vez ==')
    check('o contêiner nasceu transparente', bool(pg.evaluate('window.__settle')) and pg.evaluate('window.__settle')[0], True)
    check('   e nada ficou transparente', pg.evaluate("document.querySelectorAll('.dt-container.oxf-settling').length"), 0)

    print('\n== 5. o conteúdo ==')
    check('a placa já na tela não ganha a entrada do otc.js', pg.evaluate('!!window.__enterTop'), False)
    # o modo é forçado (o Chromium do teste não tem GPU e cairia sozinho no opaco)
    pg.evaluate("localStorage.setItem('__OTC_TRACKER_FX__', 'full')")
    pg.goto(BASE + '/new_deals-opt-fxo', wait_until='networkidle')
    check('o .content-page entra pelo CSS', pg.evaluate("getComputedStyle(document.querySelector('.content-page')).animationName"),
          'otc-fade-in')
    pg.evaluate("localStorage.setItem('__OTC_TRACKER_FX__', 'reduced')")
    pg.goto(BASE + '/new_deals-opt-fxo', wait_until='networkidle')
    check('   no modo opaco, sem animação', pg.evaluate("getComputedStyle(document.querySelector('.content-page')).animationName"),
          'none')
    pg.evaluate("localStorage.removeItem('__OTC_TRACKER_FX__')")

    print('\n== 2. o menu desafixado antes do primeiro paint ==')
    pg.evaluate("localStorage.setItem('otc_nav_pinned', '0')")
    pg.goto(BASE + '/new_deals-opt-fxo', wait_until='networkidle')
    check('o <body> já nasce desafixado', pg.evaluate('window.__boot.unpinned'), True)
    pg.evaluate("localStorage.removeItem('otc_nav_pinned')")
    check('sem erro de página', erros, [])
    ctx.close()

    print('\n== 3. o filtro de acesso já na primeira pintura ==')
    ctx = b.new_context(viewport={'width': 1600, 'height': 1000})
    ctx.add_cookies([dict(c, domain='127.0.0.1') for c in cookie('B222222', 'Bia Melo')])
    ctx.add_init_script(INIT)
    pg = ctx.new_page()
    # o /api/me/access atrasado 3 s: o que está filtrado no `interactive` veio
    # da resposta GUARDADA, não da que acabou de chegar
    import time as _t
    def _lenta(route):
        _t.sleep(3)
        route.continue_()
    pg.route('**/api/me/access', _lenta)
    pg.goto(BASE + '/new_deals-opt-fxo', wait_until='networkidle')
    pg.wait_for_timeout(500)
    check('1ª carga: o filtro só chega com o /api/me/access', pg.evaluate('window.__boot.hiddenItems'), 0)
    check('   (e chega)', pg.evaluate("document.querySelectorAll('.side-nav:not(.dd-panel) .side-nav-item[hidden]').length") > 0)
    pg.goto(BASE + '/new_deals-opt-commodities', wait_until='networkidle')
    check('a página seguinte JÁ nasce filtrada', pg.evaluate('window.__boot.hiddenItems') > 0)
    ctx.close()
    b.close()

srv.shutdown()
print(('\nFALHAS (%d): %s' % (len(fails), fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
