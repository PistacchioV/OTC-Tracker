#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""As capturas do Guia que o `capture_screens.py` não tira: o menu lateral
aberto, os menus Columns/Export abertos e a edição em massa do Tracking Docs.

Cada uma precisa de um clique antes do print, e algumas são RECORTES — o
menu lateral inteiro tem ~30 itens e, fotografado de ponta a ponta, virava uma
tira de 2600 px que o Word esticava para uma página só de menu. Aqui ele sai
recortado no alto (os primeiros grupos): o mapa completo é a tabela do 3.5.

Mesmo pré-requisito do capturador principal (app de pé com o `/dev-login`):

    SOP_BASE_URL=http://127.0.0.1:5005 SOP_OUT_DIR=/tmp/shot \\
      python scripts/sop-capture/capture_extras.py

`SOP_ONLY` escolhe as capturas por nome (vírgula): menu-lateral,
padrao-columns-menu, padrao-export-menu, padrao-edicao-massa.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capture_screens as cs  # noqa: E402

ONLY = [r.strip() for r in (os.environ.get('SOP_ONLY') or '').split(',') if r.strip()]
TABLE_PAGE = os.environ.get('SOP_TABLE_PAGE', '/live-position-ndf')


def _menu(pg):
    pg.goto(cs.BASE + '/dashboard', wait_until='domcontentloaded')
    pg.wait_for_timeout(1500)
    pg.evaluate("document.body.classList.add('vr-nav-open')")
    pg.wait_for_timeout(900)
    box = pg.locator('.sidenav-menu').bounding_box()
    # Recorte: a largura do drawer e só o alto (Main, Apps e o começo de
    # Reconciliations) — o suficiente para mostrar o alfinete, os grupos e o ›.
    return {'clip': {'x': box['x'], 'y': box['y'], 'width': box['width'],
                     'height': min(box['height'], 618)}}


def _open_toolbar_menu(pg, label, page=TABLE_PAGE):
    pg.goto(cs.BASE + page, wait_until='domcontentloaded')
    pg.wait_for_timeout(2500)
    btn = pg.locator('button:visible', has_text=label).first
    btn.click()
    pg.wait_for_timeout(700)
    b = btn.bounding_box()
    return {'clip': {'x': max(0, b['x'] - 40), 'y': max(0, b['y'] - 30),
                     'width': 900, 'height': 560}}


def _columns(pg):
    return _open_toolbar_menu(pg, 'Columns')


def _export(pg):
    # O menu COMPLETO (Copy · CSV · Excel · Print · PDF · Advanced): o do Live
    # Position é um dos que ainda estão pela metade (check_export_padrao).
    return _open_toolbar_menu(pg, 'Export', '/new_deals-ndf-vanilla')


def _bulk(pg):
    pg.goto(cs.BASE + '/onboarding/tracking-docs', wait_until='domcontentloaded')
    pg.wait_for_timeout(3000)
    cb = pg.locator('table.dataTable tbody input[type=checkbox]:visible').first
    cb.check()
    pg.wait_for_timeout(500)
    head = pg.locator('table.dataTable thead:visible').first.bounding_box()
    return {'clip': {'x': 0, 'y': max(0, head['y'] - 70), 'width': 1600,
                     'height': 70 + head['height'] + 60}}


SHOTS = [('menu-lateral', _menu), ('padrao-columns-menu', _columns),
         ('padrao-export-menu', _export), ('padrao-edicao-massa', _bulk)]


def main():
    from playwright.sync_api import sync_playwright
    payloads = cs.prefetch_mocks()

    def handle_api(route):
        from urllib.parse import urlparse
        path = urlparse(route.request.url).path
        if path in payloads:
            return route.fulfill(status=200, content_type='application/json',
                                 body=payloads[path])
        return route.continue_()

    with sync_playwright() as p:
        b = p.chromium.launch(args=['--no-sandbox', '--no-proxy-server'])
        ctx = b.new_context(viewport={'width': 1600, 'height': 1000}, device_scale_factor=2)
        ctx.add_init_script(
            "localStorage.setItem('__OTCTRACKER_CONFIG__', JSON.stringify("
            "{skin: 'default', monochrome: false, theme: '%s',"
            " layout: {position: 'fixed', dir: 'ltr'},"
            " topbar: {color: '%s'}, menu: {color: '%s'},"
            " sidenav: {size: 'default', user: false}}));"
            % (cs.THEME, cs.THEME, cs.THEME))
        ctx.route('**/api/**', handle_api)
        pg = ctx.new_page()
        pg.set_default_timeout(18000)
        pg.goto(cs.BASE + cs.LOGIN, wait_until='commit')
        pg.wait_for_timeout(1200)
        for name, fn in SHOTS:
            if ONLY and name not in ONLY:
                continue
            try:
                opts = fn(pg)
                pg.screenshot(path=os.path.join(cs.OUT, name + '.png'), **opts)
                print('OK  ', name)
            except Exception as e:                            # noqa: BLE001
                print('ERR ', name, str(e)[:120])
        b.close()


if __name__ == '__main__':
    main()
