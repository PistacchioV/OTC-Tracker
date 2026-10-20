#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""As capturas do Guia que o `capture_screens.py` não tira: as que precisam de
um clique antes do print (menu do usuário, menus Columns/Export, as janelas de
edição, de chamado e de nova solicitação, a gaveta da tarefa), a tela de login
(sem sessão) e as páginas que não estão no menu (a de um projeto).

Algumas são RECORTES — o menu lateral inteiro, fotografado de ponta a ponta,
virava uma tira que o Word esticava para uma página só de menu.

Mesmo pré-requisito do capturador principal (app de pé com o `/dev-login`):

    SOP_BASE_URL=http://127.0.0.1:5005 SOP_OUT_DIR=/tmp/shot \\
      python scripts/sop-capture/capture_extras.py

`SOP_ONLY` escolhe as capturas por nome (vírgula): login, topbar, menu-lateral,
padrao-columns-menu, padrao-export-menu, padrao-advanced-export,
padrao-linha-edicao, padrao-edicao-massa, ticket-create,
onboarding-new-request, projects-detail, tasks-drawer.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capture_screens as cs  # noqa: E402

ONLY = [r.strip() for r in (os.environ.get('SOP_ONLY') or '').split(',') if r.strip()]
TABLE_PAGE = os.environ.get('SOP_TABLE_PAGE', '/live-position-ndf')
PROJECT = os.environ.get('SOP_PROJECT', 'PRJ-0002')


def _go(pg, path, wait=3200):
    pg.goto(cs.BASE + path, wait_until='domcontentloaded')
    pg.wait_for_timeout(wait)


def _menu(pg):
    _go(pg, '/dashboard', 2200)
    box = pg.locator('.sidenav-menu').bounding_box()
    # Recorte: o painel inteiro do menu (no Pane ele é FIXO, não gaveta), com
    # a margem do vidro em volta.
    return {'clip': {'x': max(0, box['x'] - 8), 'y': max(0, box['y'] - 8), 'width': box['width'] + 16,
                     'height': min(box['height'] + 16, 900)}}


def _topbar(pg):
    _go(pg, '/dashboard', 2200)
    pg.locator('#simple-user-dropdown [data-bs-toggle="dropdown"]').click()
    pg.wait_for_timeout(700)
    bar = pg.locator('.otc-toolbar').bounding_box()
    menu = pg.locator('#simple-user-dropdown .dropdown-menu').bounding_box()
    x = max(0, bar['x'] - 12)
    return {'clip': {'x': x, 'y': max(0, bar['y'] - 12), 'width': 1600 - x,
                     'height': (menu['y'] + menu['height']) - bar['y'] + 30}}


def _open_toolbar_menu(pg, label, page=TABLE_PAGE):
    _go(pg, page)
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


def _advanced(pg):
    _open_toolbar_menu(pg, 'Export', '/new_deals-ndf-vanilla')
    pg.locator('.dt-button-collection :is(button, a)', has_text='Advanced').first.click()
    pg.wait_for_timeout(1400)
    return {}


def _edit_row(pg):
    _go(pg, '/pending-confirmation', 4500)
    pg.locator('#pending-confirmation-table tbody .ar-edit').first.click()
    pg.wait_for_timeout(1400)
    return {}


def _bulk(pg):
    _go(pg, '/onboarding/tracking-docs', 3500)
    cb = pg.locator('table.dataTable tbody input[type=checkbox]:visible').first
    cb.check()
    pg.wait_for_timeout(600)
    head = pg.locator('table.dataTable thead:visible').first.bounding_box()
    return {'clip': {'x': 0, 'y': max(0, head['y'] - 90), 'width': 1600,
                     'height': 90 + head['height'] + 80}}


def _ticket(pg):
    _go(pg, '/tickets-list')
    pg.locator('button:visible', has_text='New Ticket').first.click()
    pg.wait_for_timeout(1400)
    return {}


def _ob_request(pg):
    _go(pg, '/onboarding')
    pg.locator('#ob-new-request').click()
    pg.wait_for_timeout(1400)
    return {}


def _project(pg):
    _go(pg, '/projects/' + PROJECT, 3800)
    h = pg.evaluate('document.body.scrollHeight') or 1000
    pg.set_viewport_size({'width': 1600, 'height': max(1000, min(int(h), cs.MAX_H))})
    pg.wait_for_timeout(700)
    return {'_reset': True}


def _drawer(pg):
    _go(pg, '/tasks', 3500)
    pg.locator('.tk-col-panel[data-col="In review"] .tk-card .tk-card__title').first.click()
    pg.wait_for_timeout(1200)
    return {}


SHOTS = [('login', None), ('topbar', _topbar), ('menu-lateral', _menu),
         ('padrao-columns-menu', _columns), ('padrao-export-menu', _export),
         ('padrao-advanced-export', _advanced), ('padrao-linha-edicao', _edit_row),
         ('padrao-edicao-massa', _bulk), ('ticket-create', _ticket),
         ('onboarding-new-request', _ob_request), ('projects-detail', _project),
         ('tasks-drawer', _drawer)]


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
        # o login sai de um contexto SEM sessão
        if not ONLY or 'login' in ONLY:
            c0 = cs.new_context(b)
            p0 = c0.new_page()
            cs.install_clock(p0)
            p0.goto(cs.BASE + '/auth-2-sign-in', wait_until='domcontentloaded')
            p0.wait_for_timeout(2500)
            out = os.path.join(cs.OUT, 'login.png')
            p0.screenshot(path=out)
            cs.shrink(out)
            print('OK   login')
            c0.close()
        ctx = cs.new_context(b)
        ctx.route('**/api/**', handle_api)
        pg = ctx.new_page()
        cs.install_clock(pg)
        pg.set_default_timeout(18000)
        pg.goto(cs.BASE + cs.LOGIN, wait_until='commit')
        pg.wait_for_timeout(1200)
        for name, fn in SHOTS:
            if fn is None or (ONLY and name not in ONLY):
                continue
            try:
                opts = fn(pg)
                reset = opts.pop('_reset', False)
                out = os.path.join(cs.OUT, name + '.png')
                pg.screenshot(path=out, **opts)
                cs.shrink(out)
                if reset:
                    pg.set_viewport_size({'width': 1600, 'height': 1000})
                pg.keyboard.press('Escape')
                pg.wait_for_timeout(300)
                print('OK  ', name)
            except Exception as e:                            # noqa: BLE001
                print('ERR ', name, str(e)[:160])
        b.close()


if __name__ == '__main__':
    main()
