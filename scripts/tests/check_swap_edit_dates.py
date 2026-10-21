# -*- coding: utf-8 -*-
"""O Edit dos cards de swap: o Trade Date se edita e TODA data tem a máscara
(mesa, 21/10/2026, §656).

Nas três telas de cards (New Deals › Swap › Bullet, Cashflow, Cetes):

  1. o Trade Date do modal de Edit é EDITÁVEL (era `readonly`, com o valor em
     dd/mm/aaaa — o `otcDateField` guarda ISO, e por isso nem a máscara pegava);
  2. todo campo de data do modal — o Trade Date, as datas do deal e as do
     cronograma do Cashflow — é UM picker com a máscara da casa (`inputmode`
     numérico): o clique seleciona a data inteira e digitar só os números
     escreve as barras (`22102026` → 22/10/2026);
  3. o cronograma do Cashflow mostra as datas certas: o `openModal` ligava o
     helper por CLASSE depois de montar os fluxos, pegava também o campo
     visível de cada um (que herda a classe) e fazia dele um SEGUNDO picker, que
     relia "22/10/2026" como ISO e mostrava 01/01/2026 (`_otcMask` no
     `export-advanced.js`);
  4. o Save com o Trade Date novo MUDA a operação de arquivo-dia (o
     `persistence.move_day`): sai do dia antigo, entra no novo — é pelo dia do
     arquivo que a busca, Confirm/Send/Delete e o Monitor a acham.

As páginas são as RENDERIZADAS pelo app (test client, servidas por
`page.route`), com as operações semeadas em diretório temporário.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_swap_edit_dates.py
"""
import os
import sys
import tempfile
from datetime import datetime
from urllib.parse import urlparse

RAIZ = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, RAIZ)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(label, ok):
    print(('  ok  ' if ok else '  FAIL  ') + label)
    if not ok:
        FALHAS.append(label)


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:                                          # pragma: no cover
        print('  (sem playwright: teste pulado)')
        return
    from run import app
    from apps.pages import routes as R
    from apps.pages.features.swap_bullet.infra import persistence as PB
    from apps.pages.features.swap_cashflow.infra import persistence as PC
    from apps.pages.features.swap_cetes.infra import persistence as PT

    tmp = tempfile.mkdtemp(prefix='otc-swap-dates-')
    for nome, P in (('bullet', PB), ('cashflow', PC), ('cetes', PT)):
        P.cache_dir = (lambda n: (lambda: os.path.join(tmp, n)))(nome)
    R._create_notification = lambda *a, **k: None
    d21, d22 = datetime(2026, 10, 21), datetime(2026, 10, 22)
    base = {'Status': 'New', 'LE': 'JPM', 'LOB': 'CEM', 'TradeDate': '2026-10-21', 'StartDate': '2026-10-22',
            'MaturityDate': '2027-04-15', 'Client': 'Lawton', 'Deal': '', 'B3ID': ''}
    PB.upsert(d21, [dict(base, _id='SWB-T1', Type='Bullet', LOB='EDG', PremiumDate='2026-10-23')])
    PC.upsert(d21, [dict(base, _id='SWC-T1', Type='Fluxo de Caixa',
                         CashFlows=[{'StartDate': '2026-10-22', 'PaymentDate': '2027-01-22'}])])
    PT.upsert(d21, [dict(base, _id='CTS-T1', Tranche='111', Block='#9')])

    cl = app.test_client()
    with cl.session_transaction() as s:
        s.update({'authenticated': True, 'user_sid': 'T000000', 'user_name': 'Tester', 'user_role': 'ADMIN',
                  'session_ip': '127.0.0.1'})

    def servir(route):
        req = route.request
        u = urlparse(req.url)
        r = cl.open(u.path + ('?' + u.query if u.query else ''), method=req.method, data=req.post_data_buffer,
                    headers={'Content-Type': req.headers.get('content-type', '')})
        route.fulfill(status=r.status_code, body=r.get_data(),
                      headers={'Content-Type': r.headers.get('Content-Type', 'text/html')})

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for pagina, P, chave in (('/new_deals-swap-bullet', PB, 'SWB-T1'), ('/new_deals-swap-cashflow', PC, 'SWC-T1'),
                                 ('/new_deals-swap-cetes', PT, 'CTS-T1')):
            print('== %s ==' % pagina)
            pg = b.new_page(viewport={'width': 1500, 'height': 1000})
            erros = []
            pg.on('pageerror', lambda e: erros.append(str(e)))
            # "hoje" é 21/10/2026: é o dia que a página abre e em que a operação está
            pg.add_init_script("""(() => { const F = new Date('2026-10-21T12:00:00').getTime(); const D = Date;
                window.Date = class extends D { constructor(...a){ super(...(a.length ? a : [F])); } static now(){ return F; } }; })();""")
            pg.route('http://otc.test/**', servir)
            pg.goto('http://otc.test' + pagina)
            pg.wait_for_selector('.otc-deal-card', timeout=20000)
            pg.click('.otc-deal-card .btn-row-edit')
            pg.wait_for_timeout(800)
            campos = pg.evaluate("""() => [...document.querySelectorAll('#swbEditGrid input.swb-date[data-f], #swbEditGrid input.swb-date[data-cf]')]
                .map(o => { const v = o._flatpickr && o._flatpickr.altInput;
                    return { f: o.getAttribute('data-f') || o.getAttribute('data-cf'), picker: !!v,
                             mascara: v ? v.getAttribute('inputmode') === 'numeric' : false,
                             ro: v ? v.readOnly : o.readOnly, visto: v ? v.value : '' }; })""")
            dobrados = pg.evaluate("() => [...document.querySelectorAll('#swbEditGrid input')].filter(i => i._otcMask && i._flatpickr).length")
            td = [c for c in campos if c['f'] == 'TradeDate']
            check('o Trade Date do Edit é EDITÁVEL, com o dia da operação (%s)' % td,
                  len(td) == 1 and not td[0]['ro'] and td[0]['visto'] == '21/10/2026')
            check('TODA data do modal é um picker com a máscara (%d campos)' % len(campos),
                  campos and all(c['picker'] and c['mascara'] and not c['ro'] for c in campos))
            check('nenhum campo visível virou um SEGUNDO picker', dobrados == 0)
            if pagina.endswith('cashflow'):
                fluxo = [c['visto'] for c in campos if c['f'] in ('StartDate', 'PaymentDate')]
                check('o cronograma mostra as datas dele (era 01/01/2026 com o picker dobrado) %s' % fluxo,
                      fluxo == ['22/10/2026', '22/10/2026', '22/01/2027'])
            alvo = pg.locator('#swbEditGrid #swb-f-TradeDate + input')
            alvo.click()
            sel = pg.evaluate("() => { const a = document.activeElement; return [a.selectionStart, a.selectionEnd, a.value.length]; }")
            check('o clique seleciona a data INTEIRA %s' % sel, sel == [0, 10, 10])
            pg.keyboard.type('22102026')
            pg.wait_for_timeout(200)
            check('digita-se só os números e as barras se escrevem (22102026 → 22/10/2026)',
                  alvo.input_value() == '22/10/2026')
            pg.locator('.modal-header').first.click()
            pg.wait_for_timeout(200)
            pg.click('#swbSaveBtn')
            pg.wait_for_timeout(1500)
            no21 = [P.key_of(e) for e in P.read_day(P.day_path(d21))]
            no22 = [(P.key_of(e), e.get('TradeDate')) for e in P.read_day(P.day_path(d22))]
            check('o Save MUDA a operação de dia: sai do 21/10, entra no 22/10 com o Trade Date novo',
                  chave not in no21 and no22 == [(chave, '2026-10-22')])
            check('sem erro de JS na página %s' % (erros or ''), not erros)
            pg.close()
        b.close()

    print('== o servidor: Trade Date em branco não muda nada ==')
    from apps.pages.features.swap_cetes import commands as CT
    with app.test_request_context():
        d, _m = CT.edit('CTS-T1', '2026-10-22', {'TradeDate': ''}, sid='T000000')
    check('Trade Date em branco fica o anterior, no mesmo dia',
          d is not None and d['TradeDate'] == '2026-10-22'
          and [PT.key_of(e) for e in PT.read_day(PT.day_path(d22))] == ['CTS-T1'])


if __name__ == '__main__':
    main()
    print()
    if FALHAS:
        print('FALHOU: %d' % len(FALHAS))
        sys.exit(1)
    print('TUDO OK')
