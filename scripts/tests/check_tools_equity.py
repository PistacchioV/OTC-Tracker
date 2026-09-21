# -*- coding: utf-8 -*-
"""check_tools_equity.py — a perna de EQUITY do Swap Calculator: a curva que se
identifica pelo próprio nome e o preço final que vem do fechamento do pregão.

A posição da B3 traz o ativo na convenção do Bloomberg (`FLRY3 BZ Equity`), e
não há de-para a fazer aí — o "índice" É a ação. Antes, sem uma linha no
`tools-swap-index` para aquele papel, a ponta saía em branco: a mesa fecharia
um swap sobre uma ação nova e o Calculator não identificaria a curva.

O que este teste prende, e por que cada coisa quebraria em silêncio:

  1. `e_curva_equity` / `ativo_de_equity`: o sufixo de CLASSE sai (`Equity` e o
     código de país de duas letras antes dele) e o que sobra é o TICKER —
     mantendo o rótulo inteiro, a busca no `quotes-equity` não casa nada e o
     preço final fica vazio sem dizer por quê;
  2. a inferência é ÚLTIMA INSTÂNCIA: o cadastro continua vencendo. Uma linha
     que mande a curva para outro índice tem de ser respeitada, senão o
     cadastro deixaria de ser a palavra final — que é justamente o que ele é
     em todo o resto do app;
  3. o preço final é o **Close**, não o Adj Close: o contrato liquida pelo
     preço que o pregão fechou, e o ajustado reescreve a série a cada provento
     — o mesmo swap daria resultados diferentes conforme o dia em que a tela
     fosse aberta;
  4. o deslocamento é o da `Data de Cotação` do contrato (02 = D-2), em dias
     ÚTEIS ANBIMA — a mesma regra que a PTAX já seguia. Contado em dias
     corridos, D-1 de uma segunda-feira cairia no domingo;
  5. dia sem pregão vale o último fechamento ANTES dele, e a DATA volta junto:
     preço sem procedência é um número que ninguém consegue conferir;
  6. o que não resolve fica VAZIO e sinalizado — símbolo fora do cadastro
     `quotes-equity` diz qual papel falta, nunca devolve um preço chutado;
  7. o preço INICIAL segue sendo o do contrato (o Cupom Limpo da posição):
     buscar os dois sobrescreveria a base contratada, que é o mesmo cuidado
     que a perna de IPCA já toma com o número-índice.

Nada sai da máquina: o Yahoo é um stub e o resultado é conferido no número.
"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

falhas = []


def check(rotulo, obtido, esperado):
    ok = obtido == esperado
    print(('  ok  ' if ok else ' FAIL ') + rotulo +
          ('' if ok else '\n        got=%r\n        exp=%r' % (obtido, esperado)))
    if not ok:
        falhas.append(rotulo)


from apps.pages import quotes, routes as R                            # noqa: E402
from apps.pages.precificador import liquidacao                        # noqa: E402
from apps.pages.features.tools import domain, queries                 # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
print('== 1. a curva se identifica pelo nome ==')
check('EQUITY no Nome Tipo/Classe', domain.e_curva_equity('VCP', 'FLRY3 BZ EQUITY'), True)
check('caixa não importa', domain.e_curva_equity('', 'Flry3 bz Equity'), True)
check('curva de juros não é equity', domain.e_curva_equity('DI', 'PREFIXADO 252D'), False)
check('nome vazio não é equity', domain.e_curva_equity('', ''), False)

print('\n== 2. o ticker sai do rótulo do Bloomberg ==')
check('FLRY3 BZ Equity', domain.ativo_de_equity('FLRY3 BZ Equity'), 'FLRY3')
check('maiúsculas', domain.ativo_de_equity('PETR4 BZ EQUITY'), 'PETR4')
check('sem país', domain.ativo_de_equity('AAPL Equity'), 'AAPL')
check('espaço repetido', domain.ativo_de_equity('  VALE3   BZ   Equity '), 'VALE3')
# Sem o sufixo de classe nada é removido: o rótulo já É o código.
check('sem sufixo, passa direto', domain.ativo_de_equity('IBOV Index'), 'IBOV INDEX')
check('vazio', domain.ativo_de_equity(''), '')

print('\n== 3. a inferência é ÚLTIMA instância — o cadastro vence ==')
regra = domain.classificar_indice([], 'VCP', 'FLRY3 BZ EQUITY')
check('sem cadastro, a curva vira equity', (regra or {}).get('INDEX'), liquidacao.EQUITY)
check('e liquida em reais, sem conversão', (regra or {}).get('CURRENCY'), liquidacao.SEM_CONVERSAO)
cad = [{'MATCH': 'FLRY3 BZ EQUITY', 'MODE': 'Exact', 'INDEX': liquidacao.PRE}]
check('cadastro mandando para outro índice é respeitado',
      domain.classificar_indice(cad, 'VCP', 'FLRY3 BZ EQUITY').get('INDEX'), liquidacao.PRE)
check('curva que não é equity e não tem regra segue sem índice',
      domain.classificar_indice([], 'C03', 'PREFIXADO 252D'), None)

print('\n== 4. montar_ponta: ticker limpo + preço inicial do contrato ==')
campos, faltando = domain.montar_ponta(regra, None, 0.5, 1.0, 'FLRY3 BZ EQUITY', 20.5,
                                       deslocamento=2)
check('o ativo é o TICKER, não o rótulo', campos['ativo'], 'FLRY3')
check('o preço inicial é o Cupom Limpo da posição', campos['preco_inicial'], '20.500000')
check('o preço final não é inventado aqui', campos['preco_final'], '')
check('sem cotação inicial, o campo é sinalizado',
      domain.montar_ponta(regra, None, 0.5, 1.0, 'FLRY3 BZ EQUITY', None)[1], ['preco_inicial'])

print('\n== 5. o fechamento do pregão no fixing ==')
# A série como o Yahoo devolve: mais recente primeiro. 12 e 13/09/2026 são
# fim de semana — é o que faz o deslocamento ter de ser em dias ÚTEIS.
#
# As celulas sao STRINGS FORMATADAS, como o `fetch_ohlc` de verdade devolve
# (`_num`, '{:,.6f}') — nao floats crus. A fixture antiga usava numeros, e por
# isso nao via o defeito: acima de 999,99 o formato traz a virgula de MILHAR e
# o `float('7,656.979800')` levantava, para FORA do prefill inteiro. A tela
# dizia "Could not read the swap position" numa perna de equity cujo preco
# passou de mil, e abaixo disso a mesma conta funcionava — parecia defeito "de
# alguns contratos". Stub que nao tem a forma do real nao prende nada.
def _cel(v, dec=6):
    return '' if v is None else '{:,.{d}f}'.format(v, d=dec)


SERIE = [
    ['14/09/2026', _cel(21.080000), _cel(21.080000), _cel(21.139998), _cel(20.660000), _cel(20.740000), _cel(181000.0, 2)],
    ['11/09/2026', _cel(21.059999), _cel(21.059999), _cel(21.370001), _cel(20.980000), _cel(21.139998), _cel(5439300.0, 2)],
    ['10/09/2026', _cel(20.959998), _cel(20.959999), _cel(21.180000), _cel(20.110001), _cel(20.120003), _cel(4414200.0, 2)],
]
_rows_real, _ohlc_real = R._mapping_rows, quotes.fetch_ohlc
R._mapping_rows = lambda k: ([{'LABEL': 'FLRY3', 'SYMBOL': 'FLRY3.SA'}]
                             if k == 'quotes-equity' else [])
quotes.fetch_ohlc = lambda sym, ini, fim: (list(quotes.OHLC_COLUMNS), list(SERIE))
try:
    v, quando, erro = queries._preco_do_fixing('FLRY3', '2026-09-14', 0)
    check('D-0 é o próprio fim do fluxo', (v, quando.isoformat(), erro),
          (21.080000, '2026-09-14', ''))
    v, quando, erro = queries._preco_do_fixing('FLRY3', '2026-09-14', 1)
    check('D-1 pula o fim de semana', (v, quando.isoformat()), (21.059999, '2026-09-11'))
    v, quando, erro = queries._preco_do_fixing('FLRY3', '2026-09-14', 2)
    # É o Close (20.959999), NÃO o Adj Close (20.959998) da mesma linha.
    check('D-2 é o Close, não o Adj Close', (v, quando.isoformat()),
          (20.959999, '2026-09-10'))
    v, quando, erro = queries._preco_do_fixing('FLRY3', '2026-09-14', 3)
    check('sem pregão até o fixing: vazio, com o motivo', (v, bool(erro)), (None, True))

    # O indice acima de MIL: a celula vem '7,656.979800' e o `float` cru
    # levantava dali para fora do prefill inteiro (o laco nao estava protegido).
    quotes.fetch_ohlc = lambda sym, ini, fim: (
        list(quotes.OHLC_COLUMNS),
        [['14/09/2026', _cel(7656.979800), _cel(7656.979800), _cel(7700.0),
          _cel(7600.0), _cel(7650.0), _cel(1234567.0, 2)]])
    v, quando, erro = queries._preco_do_fixing('FLRY3', '2026-09-14', 0)
    check('preço acima de mil (a vírgula de MILHAR) volta como número',
          (v, erro), (7656.9798, ''))
    check('   e a célula ilegível é pulada, nunca derruba a busca',
          (queries._preco_da_celula('x'), queries._preco_da_celula(''),
           queries._preco_da_celula('1,234,567.890000')),
          (None, None, 1234567.89))
    quotes.fetch_ohlc = lambda sym, ini, fim: (list(quotes.OHLC_COLUMNS), list(SERIE))

    print('\n== 6. o que não resolve fica vazio e DIZ o que falta ==')
    v, _q, erro = queries._preco_do_fixing('PETR4', '2026-09-14', 2)
    check('papel fora do quotes-equity não devolve preço', v, None)
    check('e o motivo nomeia o papel e o cadastro',
          ('PETR4' in erro and 'quotes-equity' in erro), True)
    v, _q, erro = queries._preco_do_fixing('FLRY3 BZ Equity', '2026-09-14', 2)
    check('o rótulo CRU não casa — é por isso que o ticker é limpo antes', v, None)
    v, _q, erro = queries._preco_do_fixing('', '2026-09-14', 2)
    check('posição sem ativo é dito, não presumido', (v, bool(erro)), (None, True))
    v, _q, erro = queries._preco_do_fixing('FLRY3', '', 2)
    check('sem fim de fluxo não há de onde contar o deslocamento',
          (v, bool(erro)), (None, True))

    def _explode(*a, **k):
        raise RuntimeError('sem rede')
    quotes.fetch_ohlc = _explode
    v, _q, erro = queries._preco_do_fixing('FLRY3', '2026-09-14', 2)
    check('falha de rede vira campo vazio com o motivo, nunca um preço',
          (v, 'sem rede' in erro), (None, True))

    print('\n== 7. o Cupom Limpo que é PERCENTUAL de um fechamento (21/09/2026) ==')
    # A denominação diz `Preco in ativo - 100.00% Close 20-Sep-24`: o Cupom Limpo
    # da posição é esse percentual, NÃO o preço. A tela mostrava `100.0000` como
    # preço inicial do GLD — o percentual no lugar do preço, e a conta fechava
    # consigo mesma. O preço inicial é o fechamento daquele pregão × o cupom.
    quotes.fetch_ohlc = lambda sym, ini, fim: (list(quotes.OHLC_COLUMNS), list(SERIE))
    DEN = ('GLD UP EQUITY : Indices Internacionais Codigo 10473 \u2016 Descricao: SPDR GOLD SHARES '
           '\u2016 Preco Inicial: 100.00% \u2016 Fonte de informacao: Bloomberg \u2016 Data de cotacao: '
           '17-set-2026 - Cupom limpo = Strike - Preco in ativo - {CUPOM} Close 14-Sep-26 - '
           'Denominacao: Quanto (ausencia variacao cambial)')
    campos, falt = domain.montar_ponta(regra, None, 0.0, 1.0, 'FLRY3 BZ EQUITY', 100.0, deslocamento=0)
    check('antes da denominação, o montar_ponta ainda põe o cupom no preço (a perna comum)',
          campos['preco_inicial'], '100.000000')
    domain.aplicar_descricao(campos, DEN.replace('{CUPOM}', '100.00%'), falt)
    check('a denominação diz o cupom e a data do pregão',
          (campos['cupom_limpo'], campos['cupom_data']), ('100.0000', '2026-09-14'))
    check('e nada dela fica "não entendido"', campos['nao_lido'], [])
    queries.aplicar_cupom_limpo(campos, falt)
    check('o fechamento é o do pregão da denominação', (campos['preco_close'], campos['close_data']),
          ('21.080000', '2026-09-14'))
    check('100% do fechamento É o fechamento', campos['preco_inicial'], '21.080000')
    check('e o preço inicial não fica sinalizado', 'preco_inicial' in falt, False)

    c2, f2 = domain.montar_ponta(regra, None, 0.0, 1.0, 'FLRY3 BZ EQUITY', 150.0, deslocamento=0)
    domain.aplicar_descricao(c2, DEN.replace('{CUPOM}', '1.5'), f2)       # sem o `%`: é o FATOR
    queries.aplicar_cupom_limpo(c2, f2)
    check('`1.5 Close` é 150%: preço inicial = fechamento × 1,5',
          (c2['cupom_limpo'], c2['preco_inicial']), ('150.0000', '31.620000'))

    # `% Spot` não traz data: não há de onde puxar — BRANCO e sinalizado, nunca
    # o percentual no lugar do preço.
    c3, f3 = domain.montar_ponta(regra, None, 0.0, 1.0, 'FLRY3 BZ EQUITY', 100.0, deslocamento=0)
    domain.aplicar_descricao(c3, 'Preco Inicial: 100.00% Spot', f3)
    queries.aplicar_cupom_limpo(c3, f3)
    check('Spot sem data: preço inicial em BRANCO e sinalizado',
          (c3['preco_inicial'], 'preco_inicial' in f3, c3['preco_close']), ('', True, ''))

    quotes.fetch_ohlc = _explode
    c4, f4 = domain.montar_ponta(regra, None, 0.0, 1.0, 'FLRY3 BZ EQUITY', 100.0, deslocamento=0)
    domain.aplicar_descricao(c4, DEN.replace('{CUPOM}', '100.00%'), f4)
    queries.aplicar_cupom_limpo(c4, f4)
    check('cotação fora do ar: branco, sinalizado e com o MOTIVO',
          (c4['preco_inicial'], 'preco_inicial' in f4, 'sem rede' in c4.get('close_erro', '')),
          ('', True, True))

    # Sem denominação que declare o cupom, a perna segue como sempre.
    c5, f5 = domain.montar_ponta(regra, None, 0.5, 1.0, 'FLRY3 BZ EQUITY', 20.5, deslocamento=2)
    queries.aplicar_cupom_limpo(c5, f5)
    check('perna sem cupom declarado não muda', (c5['preco_inicial'], c5['cupom_limpo']),
          ('20.500000', ''))
    check('e o percentual num índice que NÃO é equity é só informação',
          [i['estado'] for i in domain.aplicar_descricao(
              {'indexador': liquidacao.PRE}, '100.00% Close 14-Sep-26')['leitura']],
          ['info', 'info'])
finally:
    R._mapping_rows, quotes.fetch_ohlc = _rows_real, _ohlc_real

print('\nFALHAS: %d' % len(falhas))
if falhas:
    for f in falhas:
        print('  - %s' % f)
sys.exit(1 if falhas else 0)
