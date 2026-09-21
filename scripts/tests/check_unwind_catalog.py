# -*- coding: utf-8 -*-
"""check_unwind_catalog.py — as paginas de recompra que saem do CATALOGO.

A pagina da Fase 1 (`/unwinds/ndf/fx`) tem template proprio. As outras onze sao
UMA tela (`pages/unwinds-product.html`) com o contrato vindo de
`features/unwinds/catalog.py`. O que este teste prende:

  1. o catalogo e o MENU dizem as mesmas paginas — link no menu sem entrada no
     catalogo e 404, e entrada sem link e pagina que ninguem acha;
  2. o contrato de colunas: Status PRIMEIRO (§7), a cabeca de identidade na
     ordem fixa (a largura das colunas e por posicao), campo sem repeticao,
     tipo conhecido, coluna escondida que existe;
  3. toda pagina abre, com a tabela, o dropzone e os QUATRO botoes da casa;
  4. a pagina da Fase 1 continua sendo a DELA (a regra com variavel nao a
     sombreia), e o que o catalogo nao conhece e 404;
  5. o GET devolve o contrato com o dia vazio, e toda acao responde 501 em
     JSON com CODIGO — nunca a pagina 404 em HTML (`Unexpected token '<'`).
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


def check(nome, cond, extra=''):
    print(('  ok  ' if cond else ' FAIL ') + nome + (('  — ' + str(extra)) if (not cond and extra) else ''))
    if not cond:
        FALHAS.append(nome)


def main():
    from run import app
    from apps.pages.features.unwinds import catalog

    print('== 1. o catalogo e o menu dizem as mesmas paginas ==')
    menu = io.open(os.path.join(ROOT, 'apps', 'templates', 'partials', 'sidenav.html'),
                   encoding='utf-8').read()
    do_menu = set(re.findall(r'href="(/unwinds/[^"]+)"', menu)) - {'/unwinds/ndf/fx'}
    check('menu == catalogo', do_menu == set(catalog.PAGES),
          sorted(do_menu ^ set(catalog.PAGES)))
    check('a Fase 1 nao esta no catalogo', '/unwinds/ndf/fx' not in catalog.PAGES)

    print('\n== 2. o contrato de colunas ==')
    cabeca = ['Status', 'DealID', 'Contract', 'Counterparty', 'TaxID']
    for path, p in sorted(catalog.PAGES.items()):
        campos = catalog.fields(p)
        check(path + ': cabeca fixa, Status primeiro', campos[:5] == cabeca, campos[:5])
        check(path + ': campo sem repeticao', len(campos) == len(set(campos)))
        check(path + ': tipos conhecidos',
              all(c[2] in ('text', 'date', 'money', 'rate', 'status', 'check') for c in p['columns']))
        check(path + ': escondida que existe', all(h in campos for h in p['hidden']))
        check(path + ': termina no Check', campos[-1] == 'Check')
        check(path + ': a chave nao e coluna de tela', p['key'] not in campos)
    slugs = [p['slug'] for p in catalog.PAGES.values()]
    check('slug unico por pagina', len(slugs) == len(set(slugs)))

    cl = app.test_client()
    with cl.session_transaction() as ss:
        ss['authenticated'] = True
        ss['user_sid'] = 'T000000'
        ss['user_name'] = 'Teste'
        ss['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()

    print('\n== 3. toda pagina abre ==')
    for path, p in sorted(catalog.PAGES.items()):
        r = cl.get(path)
        corpo = r.data.decode('utf-8')
        check(path + ': 200', r.status_code == 200, r.status_code)
        check(path + ': tabela, dropzone e o contrato',
              'id="unw-table"' in corpo and 'myAwesomeDropzone' in corpo
              and ('"api": "%s"' % p['api']) in corpo)
        check(path + ': os quatro botoes da casa',
              all(c in corpo for c in ('btn-row-approve', 'btn-row-edit',
                                       'btn-row-delete', 'btn-row-send')))

    print('\n== 4. a Fase 1 e o que o catalogo nao conhece ==')
    fx = cl.get('/unwinds/ndf/fx').data.decode('utf-8')
    check('ndf/fx continua no template dela', 'var UNW_COLS = [' in fx and 'var PAGE = ' not in fx)
    check('pagina fora do catalogo e 404', cl.get('/unwinds/ndf/nada').status_code == 404)
    check('e grupo fora do catalogo tambem', cl.get('/unwinds/nada').status_code == 404)

    print('\n== 5. o GET devolve o contrato; a acao responde 501 com codigo ==')
    p = catalog.PAGES['/unwinds/options/fxo']
    api = cl.get(p['api'] + '?date=2026-09-21').get_json()
    check('GET: dia vazio com o contrato',
          api.get('success') and api['entries'] == []
          and api['fields'] == catalog.fields(p) and api['labels'] == catalog.labels(p))
    coe = cl.get('/api/unwinds/coe').get_json()
    check('GET do COE (dois segmentos)', coe.get('success') and coe['fields'][0] == 'Status')
    for verbo, url in (('POST', p['api'] + '/import-file'), ('POST', p['api'] + '/send-conecta'),
                       ('GET', p['api'] + '/preview?id=x'), ('POST', '/api/unwinds/coe/delete')):
        r = cl.open(url, method=verbo)
        j = r.get_json(silent=True) or {}
        check('%s %s: 501 JSON com codigo' % (verbo, url),
              r.status_code == 501 and j.get('code') == 'unwind_backend_pending', (r.status_code, j))
    fase1 = cl.get('/api/unwinds/ndf/fx?date=2026-09-21').get_json()
    check('a API da Fase 1 nao foi sombreada', fase1.get('success') and 'backend' not in fase1)
    sem = app.test_client().get(p['api'])
    check('sem sessao e 401', sem.status_code == 401)

    print('\n%s' % ('TUDO OK' if not FALHAS else '%d FALHA(S): %s' % (len(FALHAS), FALHAS)))
    return 1 if FALHAS else 0


if __name__ == '__main__':
    sys.exit(main())
