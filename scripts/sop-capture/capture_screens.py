#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capturador de telas do OTC Tracker para o SOP (dados FICTÍCIOS via mock).

Percorre o menu lateral (sidenav), renderiza cada rota desenvolvida no Chromium
headless e salva os PNGs em docs/sop-screenshots/. As chamadas /api/** são
interceptadas e respondidas com dados fictícios (ver mockgen.py), reaproveitando
as colunas reais de cada endpoint — nenhum dado real de produção é exibido.

PRÉ-REQUISITOS (passo manual — NÃO versionado):
  1. Suba o app em modo dev com uma sessão AUTENTICADA, usando um launcher
     que popula a sessão. Use o template devrun.example.py:
         cp scripts/sop-capture/devrun.example.py devrun.py   # devrun.py é gitignored
         python devrun.py                                     # sobe em :8050
  2. Instale as dependências de captura:
         pip install playwright python-docx
  3. Rode este script:
         python scripts/sop-capture/capture_screens.py

Config por variáveis de ambiente (opcionais):
  SOP_BASE_URL   (default http://127.0.0.1:8050)
  SOP_LOGIN_PATH (default /dev-login)
  SOP_CHROME     (default detecta em /opt/pw-browsers ou usa o do Playwright)
"""
import os
import re
import sys
import json
import glob
import http.cookiejar
import urllib.request
from urllib.parse import urlparse

# rodar direto no localhost, sem passar pelo proxy corporativo
for _k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy'):
    os.environ.pop(_k, None)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import mockgen  # noqa: E402

BASE = os.environ.get('SOP_BASE_URL', 'http://127.0.0.1:8050')
LOGIN = os.environ.get('SOP_LOGIN_PATH', '/dev-login')
SIDENAV = os.path.join(ROOT, 'apps/templates/partials/sidenav.html')
# Destino das capturas. Sai por variável para a rodada de conferência poder
# gravar num diretório à parte e só então sobrescrever as telas do guia — uma
# captura ruim (página vazia, modal aberto) não pode apagar a boa.
OUT = os.environ.get('SOP_OUT_DIR') or os.path.join(ROOT, 'docs/sop-screenshots')
os.makedirs(OUT, exist_ok=True)

# endpoints de dados a mockar (o mockgen decide o formato: tabela/cards/dashboard).
# O mockgen fabrica linhas a partir das COLUNAS da resposta real, então um
# endpoint preso à data que devolve rows vazias (a dev sem o arquivo do dia)
# ainda rende uma tela populada — é por isso que a lista cobre também as
# páginas de swap e os settlement advices.
DATA_EPS = [
    '/api/live-position-ndf/data', '/api/live-position-option/data',
    '/api/live-position-swap-characteristics/data', '/api/otm-settlements/data',
    '/api/ndf-cockpit/data', '/api/cognos/data', '/api/operations-b3/data',
    '/api/other-products-summary/data', '/api/dashboard-stats', '/api/ndf-summary/cards',
    '/api/live-position-swap-cashflow/data', '/api/live-position-swap-premium/data',
    '/api/ndf-other-publisher/data',
    '/api/other-products-ndf-settlement-advice/data',
    '/api/other-products-option-settlement-advice/data',
    '/api/other-products-swap-athena/data', '/api/other-products-swap-events/data',
    '/api/other-products-swap-kapital-hybrids/data',
    '/api/other-products-swap-settlement-advice/data',
    '/api/other-products-swap-vcp/data',
    # O Monitor é uma TABELA por zona e na dev vem com os 26 cards zerados: sem
    # mock a captura sai com as três zonas dizendo "nothing imported today".
    '/api/new-deals/monitor',
]

# Aparência das capturas. Desde o rebranding no visual do Pane (§630) o guia é
# CLARO sobre o papel de parede Aurora (o padrão de quem abre é o Ash, cinza,
# que nos prints apagava o vidro). O `<head>` lê `__OTC_TRACKER_UI__` antes do
# primeiro paint (partials/head-css.html) — não há parâmetro de URL.
THEME = os.environ.get('SOP_THEME', 'light')
WALL = os.environ.get('SOP_WALL', 'aurora')
# O Chromium headless não tem GPU: sem `full` o otc.js liga o modo OPACO
# (`is-solid`) e o print sai sem vidro nenhum (§7, Modo opaco).
SEED_JS = ("try { localStorage.setItem('__OTC_TRACKER_UI__', JSON.stringify("
           "{theme: '%s', wall: '%s', accent: 'blue', glass: 'tinted'}));"
           " localStorage.setItem('__OTC_TRACKER_FX__', 'full');"
           " localStorage.setItem('__OTC_TRACKER_LANG__', 'en'); } catch (e) {}" % (THEME, WALL))
# Relógio do NAVEGADOR nos prints (o do servidor é o do launcher): as telas que
# contam "em 20 min", "há 1 h" e o dia de hoje saem coerentes entre si.
CLOCK = os.environ.get('SOP_CLOCK', '2026-10-20T10:40:05')
# PNG de 3200 px com 2x é grande demais para o Word: reduz a 1920 de largura e
# quantiza (256 cores + dither) — sem banding visível e ~1/5 do tamanho (§401).
SHRINK = os.environ.get('SOP_SHRINK', '1') != '0'


def shrink(path):
    if not SHRINK:
        return
    try:
        from PIL import Image
        im = Image.open(path).convert('RGB')
        if im.width > 1920:
            im = im.resize((1920, round(im.height * 1920 / im.width)), Image.LANCZOS)
        im = im.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
        im.save(path, optimize=True)
    except Exception as e:                                   # noqa: BLE001
        print('     (sem shrink: %s)' % str(e)[:60])


def new_context(browser, logged=True):
    """Contexto com a aparência e o relógio das capturas."""
    from datetime import datetime
    ctx = browser.new_context(viewport={'width': 1600, 'height': 1000}, device_scale_factor=2)
    ctx.add_init_script(SEED_JS)
    return ctx


def install_clock(pg):
    from datetime import datetime
    try:
        pg.clock.install(time=datetime.fromisoformat(CLOCK))
    except Exception as e:                                   # noqa: BLE001
        print('     (sem relógio fixo: %s)' % str(e)[:60])

# Teto da altura do print (px de CSS). O painel inicial passa dos 2600 e o
# último gráfico (Settlements by Entity) saía cortado: SOP_MAX_H=3200 para ele.
MAX_H = int(os.environ.get('SOP_MAX_H') or 2600)

# Refazer UMA tela (uma rota redesenhada) não pode custar as outras 60: a
# rodada inteira reescreve o diretório todo, e uma captura ruim no meio dela
# apaga uma boa. SOP_ONLY é a lista (vírgula) de rotas a percorrer.
ONLY = [r.strip() for r in (os.environ.get('SOP_ONLY') or '').split(',') if r.strip()]


def find_chrome():
    if os.environ.get('SOP_CHROME'):
        return os.environ['SOP_CHROME']
    for pat in ('/opt/pw-browsers/chromium-*/chrome-linux/chrome',
                os.path.expanduser('~/.cache/ms-playwright/chromium-*/chrome-linux/chrome')):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None  # deixa o Playwright resolver o default


def sidebar_routes():
    """Rotas de página na ordem do sidebar, ignorando o boilerplate de template."""
    html = open(SIDENAV, encoding='utf-8').read().split('\n')
    stop = next((i for i, l in enumerate(html) if 'components-title' in l), len(html))
    seen, out = set(), []
    skip = ('/users-profile', '/auth', '/logout', '/dashboard-2')
    for l in html[:stop]:
        m = re.search(r'href="(/[^"#]+)"', l)
        if not m:
            continue
        h = m.group(1)
        if h in seen or h.startswith(skip):
            continue
        seen.add(h)
        out.append(h)
    return out


def prefetch_mocks():
    """Loga via LOGIN e monta os payloads fictícios a partir das colunas reais."""
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                     urllib.request.ProxyHandler({}))
    op.open(BASE + LOGIN).read()
    payloads = {ep: json.dumps(fn()) for ep, fn in mockgen.STATIC.items()}
    for ep in DATA_EPS:
        try:
            obj = json.loads(op.open(BASE + ep, timeout=20).read())
            changed, newobj = mockgen.transform(obj)
            if changed:
                payloads[ep] = json.dumps(newobj)
                print('mock ', ep)
            else:
                print('skip ', ep)
        except Exception as e:
            print('errf ', ep, str(e)[:60])
    return payloads


def main():
    from playwright.sync_api import sync_playwright
    routes = ONLY or sidebar_routes()
    payloads = prefetch_mocks()
    chrome = find_chrome()

    def handle_api(route):
        path = urlparse(route.request.url).path
        if path in payloads:
            return route.fulfill(status=200, content_type='application/json', body=payloads[path])
        return route.continue_()

    ok, err = [], []
    with sync_playwright() as p:
        launch = {'args': ['--no-sandbox', '--no-proxy-server']}
        if chrome:
            launch['executable_path'] = chrome
        b = p.chromium.launch(**launch)
        ctx = new_context(b)
        ctx.route('**/api/**', handle_api)
        pg = ctx.new_page()
        install_clock(pg)
        pg.set_default_timeout(18000)
        pg.goto(BASE + LOGIN, wait_until='commit')
        pg.wait_for_timeout(1200)
        for route in routes:
            name = route.strip('/').replace('/', '_')
            try:
                resp = pg.goto(BASE + route, wait_until='domcontentloaded')
                # a entrada em gotas (§9 do otc.js) e a contagem dos números
                # precisam terminar antes do clique da câmera
                pg.wait_for_timeout(int(os.environ.get('SOP_WAIT_MS') or 3200))
                code = resp.status if resp else 0
                if code == 200:
                    # NUNCA full_page=True: o rodapé é FIXO e o compositor o
                    # carimba no meio do conteúdo (HANDOFF §394). O certo é
                    # medir o documento, esticar o viewport até lá (com teto)
                    # e fotografar a janela.
                    h = pg.evaluate('document.body.scrollHeight') or 1000
                    h = max(1000, min(int(h), MAX_H))
                    pg.set_viewport_size({'width': 1600, 'height': h})
                    pg.wait_for_timeout(600)
                    pg.screenshot(path=os.path.join(OUT, name + '.png'))
                    shrink(os.path.join(OUT, name + '.png'))
                    pg.set_viewport_size({'width': 1600, 'height': 1000})
                    ok.append((route, code))
                    print('OK  ', code, name)
                else:
                    err.append((route, code))
                    print('skip', code, name, '(rota não desenvolvida)')
            except Exception as e:
                err.append((route, str(e)[:60]))
                print('ERR ', name, str(e)[:60])
        b.close()
    print('\nDONE  capturadas=%d  ignoradas=%d  ->  %s' % (len(ok), len(err), OUT))
    print('Agora rode:  python scripts/build_sop_docx.py')


if __name__ == '__main__':
    main()
