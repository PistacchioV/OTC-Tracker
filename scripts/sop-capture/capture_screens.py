#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capturador de telas do OTC Tracker para o SOP (dados FICTÍCIOS via mock).

Percorre o menu lateral (sidenav), renderiza cada rota desenvolvida no Chromium
headless e salva os PNGs em docs/sop-screenshots/. As chamadas /api/** são
interceptadas e respondidas com dados fictícios (ver mockgen.py), reaproveitando
as colunas reais de cada endpoint — nenhum dado real de produção é exibido.

PRÉ-REQUISITOS (passo manual — NÃO versionado):
  1. Suba o app localmente em modo dev com uma sessão AUTENTICADA. O modo mais
     simples é um launcher local que faz stub da lib interna `awmpy` e adiciona
     uma rota /dev-login que popula a sessão. Use o template devrun.example.py:
         cp scripts/sop-capture/devrun.example.py devrun.py   # devrun.py é gitignored
         python devrun.py                                     # sobe em :8050
     ⚠️  NUNCA comite o bypass de /dev-login dentro de apps/ (HANDOFF, pitfall #11).
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
OUT = os.path.join(ROOT, 'docs/sop-screenshots')
os.makedirs(OUT, exist_ok=True)

# endpoints de dados a mockar (o mockgen decide o formato: tabela/cards/dashboard)
DATA_EPS = [
    '/api/live-position-ndf/data', '/api/live-position-option/data',
    '/api/live-position-swap-characteristics/data', '/api/otm-settlements/data',
    '/api/ndf-cockpit/data', '/api/cognos/data', '/api/operations-b3/data',
    '/api/other-products-summary/data', '/api/dashboard-stats', '/api/ndf-summary/cards',
]


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
    payloads = {}
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
    routes = sidebar_routes()
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
        ctx = b.new_context(viewport={'width': 1600, 'height': 1000}, device_scale_factor=2)
        ctx.route('**/api/**', handle_api)
        pg = ctx.new_page()
        pg.set_default_timeout(18000)
        pg.goto(BASE + LOGIN, wait_until='commit')
        pg.wait_for_timeout(1200)
        for route in routes:
            name = route.strip('/').replace('/', '_')
            try:
                resp = pg.goto(BASE + route, wait_until='domcontentloaded')
                pg.wait_for_timeout(2200)
                code = resp.status if resp else 0
                if code == 200:
                    pg.screenshot(path=os.path.join(OUT, name + '.png'), full_page=True)
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
