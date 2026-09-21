# -*- coding: utf-8 -*-
"""check_tools_calculators.py — NDF Calculator, Unwind NDF Calculator e Option
Calculator (Tools), e a ordem ALFABETICA do menu.

O que este teste prende:

  1. o menu de Tools esta em ordem alfabetica pelo rotulo em ingles, com as
     tres paginas novas, e cada link tem rota (link sem rota e 404 calado);
  2. NDF no vencimento: o sinal e a POSICAO do banco, o IR de 0,005% so quando
     o banco PAGA, isento nao paga, e o nocional fixo em reais divide pela taxa;
  3. recompra de NDF: a MESMA formula que a pagina de Unwinds confere — as tres
     operacoes REAIS do check_unwind_notification fecham aqui tambem, e o motor
     puro bate com `unwinds.domain.conferir_apuracao` (duas copias da conta que
     divergem sao dois numeros para a mesma recompra);
  4. o saldo da recompra sao TRES parcelas, e o total diz Zero;
  5. opcao: call/put, titular/lancador, a media da asiatica, o premio separado
     do exercicio, fora do dinheiro nao exerce;
  6. as tres paginas de ponta a ponta: abrem, calculam, o erro sai em frase (e
     nao em 500), e o fixing em branco busca a PTAX dizendo de que dia e.
"""
import io
import os
import re
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(nome, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + nome + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        FALHAS.append(nome)


def main():
    from run import app
    from apps.pages.precificador import derivativos as D
    from apps.pages.features.tools import queries
    from apps.pages.features.unwinds import domain as unw

    print('== 1. o menu de Tools: ordem alfabetica e link com rota ==')
    menu = io.open(os.path.join(ROOT, 'apps', 'templates', 'partials', 'sidenav.html'),
                   encoding='utf-8').read()
    bloco = menu.split('id="toolsSection"', 1)[1].split('</ul>', 1)[0]
    itens = re.findall(r'href="([^"]+)"[^>]*>\s*<span class="menu-text"[^>]*>\s*([^<]+?)\s*</span>', bloco)
    rotulos = [r for _h, r in itens]
    check('em ordem alfabetica', rotulos, sorted(rotulos, key=lambda s: s.lower()))
    check('com as tres paginas novas',
          [r for r in rotulos if r in ('NDF Calculator', 'Option Calculator', 'Unwind NDF Calculator')],
          ['NDF Calculator', 'Option Calculator', 'Unwind NDF Calculator'])
    regras = set(str(r) for r in app.url_map.iter_rules())
    check('todo link do menu de Tools tem rota', [h for h, _r in itens if h not in regras], [])

    print('\n== 2. NDF no vencimento ==')
    r = D.liquidar_ndf(1000000.0, 5.20, 5.35, D.COMPRADO)
    check('comprado e o fixing ACIMA do termo: o banco recebe',
          (r.liquidacao, r.direcao, r.ir, r.liquido_cliente), (150000.0, 'RECEIVE', 0.0, None))
    r = D.liquidar_ndf(1000000.0, 5.20, 5.35, D.VENDIDO)
    check('vendido: o mesmo numero, o banco PAGA — e ai ha IR de 0,005%',
          (r.liquidacao, r.direcao, r.ir, r.liquido_cliente), (-150000.0, 'PAY', 7.5, 149992.5))
    check('contraparte isenta nao paga IR',
          D.liquidar_ndf(1000000.0, 5.20, 5.35, D.VENDIDO, isento_ir=True).ir, 0.0)
    r = D.liquidar_ndf(5200000.0, 5.20, 5.35, D.COMPRADO, fixo_em_reais=True)
    check('fixo em reais: o nocional divide pela taxa a termo',
          (round(r.nocional_me, 2), r.liquidacao), (1000000.0, 150000.0))
    check('fixing igual ao termo: nada liquida, sem direcao',
          (D.liquidar_ndf(1e6, 5.2, 5.2, D.COMPRADO).liquidacao,
           D.liquidar_ndf(1e6, 5.2, 5.2, D.COMPRADO).direcao), (0.0, ''))
    for nome, args in (('posicao em branco', (1e6, 5.2, 5.3, '')), ('fixing zero', (1e6, 5.2, 0, D.COMPRADO)),
                       ('nocional negativo', (-1, 5.2, 5.3, D.COMPRADO))):
        try:
            D.liquidar_ndf(*args)
            check(nome + ' e recusado', 'passou')
        except D.ErroDerivativo:
            check(nome + ' e recusado', True)

    print('\n== 3. recompra: a MESMA formula da pagina de Unwinds, nas tres operacoes reais ==')
    CASOS = [('USD 10/09/2026', 42227.42, 5.3748, 5.109, 13.75, 14, False, False, 11144.00, 42227.42),
             ('BRL fixed #1', 59999.98, 5.2039, 5.2077, 13.93, 45, True, True, 42.80, 11529.81),
             ('BRL fixed #2', 750000.01, 5.2039, 5.2067, 13.81, 23, True, True, 398.81, 144122.68)]
    for rot, noc, strike, term, pre, du, fixo, comprado, esperado, me in CASOS:
        r = D.recomprar_ndf(noc, strike, term, pre / 100.0, du,
                            D.COMPRADO if comprado else D.VENDIDO, fixo_em_reais=fixo)
        check('%s: resultado e nocional ME' % rot, (r.resultado, round(r.nocional_me, 2)), (esperado, me))
        ref = unw.conferir_apuracao({'Strike': str(strike)},
                                    {'Unwound Amount': str(noc), 'Termination Rate': str(term),
                                     'Pre FWD Rate': str(pre), 'DU': str(du),
                                     'Input Termination Fee': str(esperado)},
                                    brl_fixed=fixo, comprado=comprado)
        check('%s: bate com o conferir_apuracao da vertical' % rot,
              (r.resultado, r.direcao), (round(ref['resultado_calc'], 2), ref['direcao_calc']))
    check('os dias uteis sao ANBIMA, da liquidacao ao vencimento',
          D.dias_uteis_ate(date(2026, 9, 21), date(2026, 9, 28)), 5)
    try:
        D.dias_uteis_ate(date(2026, 9, 28), date(2026, 9, 21))
        check('vencimento antes da liquidacao e recusado', 'passou')
    except D.ErroDerivativo:
        check('vencimento antes da liquidacao e recusado', True)

    print('\n== 4. o saldo sao TRES parcelas ==')
    r = D.recomprar_ndf(300000.0, 5.2, 5.3, 0.13, 10, D.COMPRADO,
                        nocional_original=1000000.0, ja_recomprado=200000.0)
    check('original - ja recomprado - recomprado agora', (r.saldo, r.total), (500000.0, False))
    r = D.recomprar_ndf(800000.0, 5.2, 5.3, 0.13, 10, D.COMPRADO,
                        nocional_original=1000000.0, ja_recomprado=200000.0)
    check('zerou: recompra TOTAL', (r.saldo, r.total), (0.0, True))
    check('sem o original nao se afirma nem total nem parcial',
          (D.recomprar_ndf(1e5, 5.2, 5.3, 0.13, 10, D.COMPRADO).saldo,
           D.recomprar_ndf(1e5, 5.2, 5.3, 0.13, 10, D.COMPRADO).total), (None, None))
    try:
        D.recomprar_ndf(900000.0, 5.2, 5.3, 0.13, 10, D.COMPRADO,
                        nocional_original=1000000.0, ja_recomprado=200000.0)
        check('recomprar mais do que sobra e recusado', 'passou')
    except D.ErroDerivativo:
        check('recomprar mais do que sobra e recusado', True)

    print('\n== 5. opcao no exercicio ==')
    r = D.liquidar_opcao(D.CALL, D.TITULAR, 5.20, 1000000.0, [5.35], premio_unitario=0.05)
    check('call titular dentro do dinheiro: recebe o exercicio e PAGOU o premio',
          (r.payoff, r.direcao_exercicio, r.premio, r.direcao_premio, r.resultado),
          (150000.0, 'RECEIVE', 50000.0, 'PAY', 100000.0))
    r = D.liquidar_opcao(D.CALL, D.LANCADOR, 5.20, 1000000.0, [5.35], premio_unitario=0.05)
    check('o lancador e o espelho', (r.direcao_exercicio, r.direcao_premio, r.resultado),
          ('PAY', 'RECEIVE', -100000.0))
    r = D.liquidar_opcao(D.PUT, D.TITULAR, 5.20, 1000000.0, [5.35])
    check('put com o preco acima do strike: fora do dinheiro, nao exerce',
          (r.exercida, r.payoff, r.direcao_exercicio), (False, 0.0, ''))
    r = D.liquidar_opcao(D.PUT, D.TITULAR, 80.0, 1000.0, [70.0, 72.0, 74.0], paridade=5.0)
    check('asiatica: a media dos precos, e a paridade leva a reais',
          (r.fixing, r.intrinseco, r.payoff), (72.0, 8.0, 40000.0))
    r = D.liquidar_opcao(D.CALL, D.TITULAR, 80.0, 1000.0, [90.0], paridade=5.0,
                         premio_unitario=2.0, paridade_premio=4.0)
    check('o premio usa a paridade do dia DELE', (r.payoff, r.premio), (50000.0, 8000.0))
    try:
        D.liquidar_opcao(D.CALL, D.TITULAR, 80.0, 1000.0, [])
        check('sem preco de verificacao e recusado', 'passou')
    except D.ErroDerivativo:
        check('sem preco de verificacao e recusado', True)

    print('\n== 6. as tres paginas, de ponta a ponta ==')
    cl = app.test_client()
    with cl.session_transaction() as ss:
        ss['authenticated'] = True
        ss['user_sid'] = 'T000000'
        ss['user_name'] = 'Teste'
        ss['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    for url in ('/tools/ndf-calculator', '/tools/unwind-ndf-calculator', '/tools/option-calculator'):
        check(url + ' abre', cl.get(url).status_code, 200)
        check(url + ' sem sessao redireciona', app.test_client().get(url).status_code in (301, 302))
    h = cl.post('/tools/ndf-calculator', data={
        'posicao': 'vendido', 'moeda': 'USD', 'nocional': '1,000,000.00', 'taxa_termo': '5.2000',
        'fixing': '5.3500', 'vencimento': '2026-09-21', 'ptax_offset': '1'}).data.decode('utf-8')
    check('NDF: o numero e a direcao na tela', ('150,000.00' in h, '>PAY<' in h, '149,992.50' in h),
          (True, True, True))
    # Fixing em branco: a PTAX do BCB, pela MESMA funcao do Swap Calculator.
    real = queries._ptax_do_fixing
    queries._ptax_do_fixing = lambda moeda, fim, n: (5.4321, date(2026, 9, 18), '')
    try:
        h = cl.post('/tools/ndf-calculator', data={
            'posicao': 'comprado', 'moeda': 'USD', 'nocional': '1000000', 'taxa_termo': '5.2',
            'fixing': '', 'vencimento': '2026-09-21', 'ptax_offset': '1'}).data.decode('utf-8')
        check('fixing em branco busca a PTAX e DIZ de que dia', 'PTAX USD 18/09/2026' in h)
        queries._ptax_do_fixing = lambda moeda, fim, n: (None, None, 'sem rede')
        h = cl.post('/tools/ndf-calculator', data={
            'posicao': 'comprado', 'moeda': 'USD', 'nocional': '1000000', 'taxa_termo': '5.2',
            'fixing': '', 'vencimento': '2026-09-21'}).data.decode('utf-8')
        check('sem PTAX e sem numero: erro em FRASE com o motivo, nunca um fixing chutado',
              ('sem rede' in h, 'alert-danger' in h, 'Settlement at maturity' in h), (True, True, False))
    finally:
        queries._ptax_do_fixing = real
    h = cl.post('/tools/unwind-ndf-calculator', data={
        'posicao': 'vendido', 'moeda': 'USD', 'nocional': '42,227.42', 'strike': '5.3748',
        'taxa_recompra': '5.109', 'taxa_pre': '13.75', 'du': '14',
        'liquidacao': '2026-09-10', 'vencimento': '2026-09-30'}).data.decode('utf-8')
    check('recompra: a operacao real fecha na tela (R$ 11.144,00, RECEIVE)',
          ('11,144.00' in h, '>RECEIVE<' in h), (True, True))
    h = cl.post('/tools/unwind-ndf-calculator', data={
        'posicao': 'vendido', 'moeda': 'USD', 'nocional': '1000', 'strike': '5.3', 'taxa_recompra': '5.1',
        'taxa_pre': '13.75', 'du': '', 'liquidacao': '2026-09-21', 'vencimento': '2026-09-28'}).data.decode('utf-8')
    check('DU em branco e CONTADO (ANBIMA), e a tela diz isso', 'counted, ANBIMA' in h)
    h = cl.post('/tools/option-calculator', data={
        'tipo': 'put', 'lado': 'titular', 'moeda': 'BRL', 'strike': '80', 'quantidade': '1000',
        'fixings': '70\n72;74', 'exercicio': '2026-09-21', 'premio_unitario': '2'}).data.decode('utf-8')
    check('opcao asiatica: media de 3, payoff 8.000 e premio 2.000',
          ('average of' in h, '8,000.00' in h, '2,000.00' in h, '6,000.00' in h), (True, True, True, True))
    h = cl.post('/tools/option-calculator', data={
        'tipo': 'call', 'lado': 'titular', 'moeda': 'BRL', 'strike': '', 'quantidade': '1000',
        'fixings': '70', 'exercicio': '2026-09-21'}).data.decode('utf-8')
    check('campo obrigatorio vazio vira frase, nao 500', 'alert-danger' in h)

    print('\n%s' % ('TUDO OK' if not FALHAS else '%d FALHA(S): %s' % (len(FALHAS), FALHAS)))
    return 1 if FALHAS else 0


if __name__ == '__main__':
    sys.exit(main())
