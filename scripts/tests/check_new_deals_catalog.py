# -*- coding: utf-8 -*-
"""check_new_deals_catalog.py — as paginas de New Deals que saem do CATALOGO.

Swap Cashflow e Options EDG sao UMA tela (`pages/new_deals-product.html`, o
molde do Swap Bullet) com o contrato vindo de `features/new_deals/catalog.py`.
O que este teste prende:

  1. catalogo x rota x menu: pagina do catalogo sem rota estatica cai no
     catch-all (que renderiza sem a variavel `page`), e sem link ninguem a acha;
  2. as colunas de SWAP sao as do Swap Bullet — a copia existe porque feature
     nao importa feature, e coluna nova no Bullet sem entrar aqui reprova;
  3. o contrato: campo sem repeticao, tipo conhecido, escondida/readonly/select
     que existem, a cabeca fixa (Status, LE, LOB, Deal, B3 ID, Trade Date)
     FORA das colunas — e a LOB com CEM e EDG, que e o que encaixa as duas
     mesas na mesma pagina (no Bullet tambem);
  4. toda pagina abre com a tabela, o dropzone, o filtro e os quatro botoes, e
     o select que e CADASTRO chega resolvido pela tela /mapping;
  5. a carga (`cache/search`) devolve vazio com o contrato, toda acao responde
     501 em JSON com CODIGO, e as rotas dos outros produtos nao foram
     sombreadas.
"""
import io
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []
CABECA = ('Status', 'LE', 'LOB', 'Deal', 'B3ID', 'TradeDate')


def check(nome, cond, extra=''):
    print(('  ok  ' if cond else ' FAIL ') + nome + (('  — ' + str(extra)) if (not cond and extra) else ''))
    if not cond:
        FALHAS.append(nome)


def main():
    from run import app
    from apps.pages import routes as R
    from apps.pages.features.new_deals import catalog
    from apps.pages.features.swap_bullet import domain as bullet

    print('== 1. catalogo x rota x menu ==')
    regras = set(str(r) for r in app.url_map.iter_rules())
    menu = io.open(os.path.join(ROOT, 'apps', 'templates', 'partials', 'sidenav.html'),
                   encoding='utf-8').read()
    for path in sorted(catalog.PAGES):
        check(path + ': tem rota estatica', path in regras)
        api = catalog.PAGES[path]['api']
        check(path + ': e a API tem prefixo ESTATICO (as genericas <product> nao a engolem)',
              api in regras and (api + '/<path:resto>') in regras)
        check(path + ': tem link no menu', ('href="%s"' % path) in menu)
    check('nenhum placeholder sobrou no menu para elas',
          'href="#swapcashflow"' not in menu and 'href="#edg"' not in menu)

    print('\n== 2. as colunas de swap sao as do Swap Bullet ==')
    cash = catalog.PAGES['/new_deals-swap-cashflow']
    pares = [(c[0], c[1]) for c in cash['columns']]
    do_bullet = [c for c in bullet.SWB_COLUMNS if c[0] not in ('Maker', 'Checker')]
    check('o cashflow COMECA pelas colunas do Bullet, na ordem',
          pares[:len(do_bullet)] == do_bullet,
          [x for x in do_bullet if x not in pares])
    check('e termina em Maker/Checker', [p[0] for p in pares[-2:]] == ['Maker', 'Checker'])
    check('com a amortizacao e a contagem de fluxos entre os dois',
          [p[0] for p in pares[-4:-2]] == ['AmortizationType', 'Flows'])
    # O Deal Ticket da CEM (mesa, 21/09/2026): o que ele traz e o Bullet nao
    # tinha entra nas DUAS paginas — os limitadores ja estavam la.
    do_dt = ('FXStart', 'NotionalFC', 'CurveAQuote', 'CurveADCC', 'CurveACleanCoupon',
             'CurveBQuote', 'CurveBDCC', 'CurveBCleanCoupon', 'NotionalIndex',
             'NotionalObsDate', 'NotionalDescription', 'Observations',
             'CurveACap', 'CurveAFloor', 'CurveBCap', 'CurveBFloor')
    check('o que o Deal Ticket da CEM traz esta no Bullet', all(f in bullet.SWB_FIELDS for f in do_dt),
          [f for f in do_dt if f not in bullet.SWB_FIELDS])
    check('e no Cashflow', all(f in [p[0] for p in pares] for f in do_dt))
    check('o cronograma e a tabela Cash Flow do Deal Ticket, na ordem',
          [c[0] for c in cash['schedule']] == ['StartDate', 'PaymentDate', 'AmortizationPct',
                                               'BusinessDays', 'CalendarDays', 'FixingDate'])
    check('a contagem de fluxos nao se digita', 'Flows' in cash['readonly'])
    check('e so o Cashflow tem cronograma', catalog.PAGES['/new_deals-opt-edg']['schedule'] == [])
    tpl_b = io.open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'new_deals-swap-bullet.html'),
                    encoding='utf-8').read()
    js = re.search(r'var SWB_COLS = \[(.*?)\];', tpl_b, re.S).group(1)
    check('a copia do contrato na tela do Bullet esta na ordem do dominio',
          re.findall(r"\['([A-Za-z0-9]+)'", js) == list(bullet.SWB_FIELDS))

    print('\n== 3. o contrato ==')
    for path, p in sorted(catalog.PAGES.items()):
        campos = catalog.fields(p)
        check(path + ': campo sem repeticao', len(campos) == len(set(campos)))
        check(path + ': tipos conhecidos',
              all(c[2] in ('text', 'date', 'money', 'number') for c in p['columns']))
        check(path + ': a cabeca fixa esta FORA das colunas', not (set(CABECA) & set(campos)))
        check(path + ': escondida e readonly que existem',
              all(f in campos for f in p['hidden'] + p['readonly']))
        check(path + ': select de campo que existe',
              all(f in campos or f in CABECA
                  for f in list(p['selects']) + list(p['selects_from_mapping'])))
        check(path + ': default de campo que existe',
              all(f in campos or f in CABECA for f in p['defaults']))
        check(path + ': a LOB oferece CEM e EDG', set(p['selects'].get('LOB') or []) == {'CEM', 'EDG'})
        check(path + ': cadastro que existe',
              all(k in R._MAPPING_DEFS for k in p['selects_from_mapping'].values()))
    tpl_bullet = io.open(os.path.join(ROOT, 'apps', 'templates', 'pages',
                                      'new_deals-swap-bullet.html'), encoding='utf-8').read()
    check('e o Swap Bullet tambem (CEM e EDG na mesma pagina)',
          re.search(r"LOB:\s*\['EDG',\s*'CEM'\]", tpl_bullet) is not None)

    cl = app.test_client()
    with cl.session_transaction() as ss:
        ss['authenticated'] = True
        ss['user_sid'] = 'T000000'
        ss['user_name'] = 'Teste'
        ss['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()

    print('\n== 4. toda pagina abre ==')
    R._mapping_rows = lambda k: [{'CODE': '9', 'LABEL': 'Do Cadastro'}] if k == 'swap-amortizacao' else []
    for path, p in sorted(catalog.PAGES.items()):
        r = cl.get(path)
        corpo = r.data.decode('utf-8')
        check(path + ': 200', r.status_code == 200, r.status_code)
        check(path + ': tabela, dropzone, filtro e o contrato',
              'id="swb-table"' in corpo and 'myAwesomeDropzone' in corpo
              and 'id="smartFilter"' in corpo and ('"api": "%s"' % p['api']) in corpo)
        check(path + ': os quatro botoes da casa',
              all(c in corpo for c in ('btn-row-confirm', 'btn-row-edit',
                                       'btn-row-delete', 'btn-row-send')))
    corpo = cl.get('/new_deals-swap-cashflow').data.decode('utf-8')
    check('o select de amortizacao vem do CADASTRO', '"AmortizationType": ["Do Cadastro"]' in corpo)
    check('e o catalogo nao foi mutado pelo request',
          'AmortizationType' not in catalog.PAGES['/new_deals-swap-cashflow']['selects'])
    bul = cl.get('/new_deals-swap-bullet').data.decode('utf-8')
    check('o Swap Bullet continua no template dele', 'var SWB_COLS = [' in bul and 'var PAGE = ' not in bul)

    print('\n== 5. a carga devolve o contrato; a acao responde 501 com codigo ==')
    p = catalog.PAGES['/new_deals-opt-edg']
    busca = cl.post(p['api'] + '/cache/search', json={'filters': []}).get_json()
    check('cache/search: vazio com o contrato',
          busca.get('success') and busca['deals'] == [] and busca['fields'] == catalog.fields(p))
    for verbo, url in (('POST', p['api'] + '/import-file?dry_run=1'), ('POST', p['api'] + '/send-conecta'),
                       ('GET', p['api'] + '/preview?deal_id=x'), ('POST', p['api'] + '/add')):
        r = cl.open(url, method=verbo)
        j = r.get_json(silent=True) or {}
        check('%s %s: 501 JSON com codigo' % (verbo, url),
              r.status_code == 501 and j.get('code') == 'nd_backend_pending', (r.status_code, j))
    check('o que nao e do catalogo segue 404',
          cl.post('/api/new-deals/nada/cache/search', json={}).status_code == 404)
    outro = cl.post('/api/new-deals/swap-bullet/cache/search', json={'filters': []}).get_json()
    check('a API do Swap Bullet nao foi sombreada', outro.get('success') and 'backend' not in outro)
    check('sem sessao e 401', app.test_client().post(p['api'] + '/cache/search').status_code == 401)

    print('\n%s' % ('TUDO OK' if not FALHAS else '%d FALHA(S): %s' % (len(FALHAS), FALHAS)))
    return 1 if FALHAS else 0


if __name__ == '__main__':
    sys.exit(main())
