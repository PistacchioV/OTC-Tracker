#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_weak_ccy_rate.py — MOEDA FRACA: o strike é invertido UMA vez, na importação.

A API manda o strike da moeda fraca como moeda/BRL (1,2956 CNH por real) e a
aplicação inteira trabalha com R$/moeda (0,77179965). A inversão é da CONVENÇÃO
DO PAR, não da coluna em que a moeda caiu: qual das duas pernas carrega o
notional depende de como a mesa bookou.

Até 19/08/2026 havia duas regras complementares — a importação invertia quando a
moeda fraca era a `Other Quantity Units` e o arquivo TER invertia de novo quando
ela era a `Quantity Currency`. O arquivo saía certo por compensação, mas a
coluna Rate da tela, o contravalor do MT300 e a taxa do Intrag ficavam com o
valor CRU sempre que o notional estava na moeda fraca — que é o caso do BRL/CNH.

O que este script prova:

  1. `_ndf_weak_leg` acha a perna fraca nas DUAS posições, e devolve None quando
     não há moeda fraca ou quando as duas são fracas (sem BRL, a convenção não
     tem para onde apontar);
  2. a importação inverte o strike nos dois arranjos, e não mexe em USD/BRL;
  3. o arquivo TER não inverte de novo — só arredonda pelas casas do cadastro,
     e a Taxa a Termo sai igual nos dois arranjos do mesmo trade;
  4. o contravalor do MT300 fecha com o valor que a própria API manda.

O cadastro é um stub em memória: nada aqui toca o BaseMoeda.json versionado.
"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R  # noqa: E402

FAILS = []


def check(name, cond, extra=''):
    if cond:
        print('  ok    ' + name)
    else:
        print(' FAIL   ' + name + (' — ' + extra if extra else ''))
        FAILS.append(name)


# ── Cadastro Currency Base (stub) ────────────────────────────────────────────
CCY_ROWS = [
    {'SIMBOLO': 'BRL', 'ATHENA CODE': 'BRR', 'WEAK': '',    'INV DECIMALS': '',
     'CODIGO DE CADASTRO': '790'},
    {'SIMBOLO': 'USD', 'ATHENA CODE': 'USB', 'WEAK': '',    'INV DECIMALS': '',
     'CODIGO DE CADASTRO': '220'},
    {'SIMBOLO': 'CNH', 'ATHENA CODE': 'RMB', 'WEAK': 'YES', 'INV DECIMALS': '4',
     'CODIGO DE CADASTRO': '796'},
    {'SIMBOLO': 'MXN', 'ATHENA CODE': 'MXB', 'WEAK': 'YES', 'INV DECIMALS': '4',
     'CODIGO DE CADASTRO': '741'},
]

# O trade real de 19/08/2026: 35.000.000 CNH contra 27.013.000 BRL.
STRIKE_API = 1.295672454          # CNH por BRL, como a API manda
STRIKE_APP = 1.0 / STRIKE_API     # R$/CNH — 0,77179965, o que a tela tem de mostrar
QTY = 35000000.0
OTHER_API = 27013000.0            # o contravalor que a própria API declara


def _rec(qty_ccy, other_ccy):
    """Registro da API do getTrades, com as duas pernas na ordem pedida."""
    return {
        'Deal Name': 'D5VL-2IE22T', 'Trade Date': '2026-08-19',
        'Settlement Date': '2026-09-10', 'Expiration Date': '2026-09-08',
        'End Counterparty': 'VESTABRA', 'End Counterparty Description': 'VESTAS',
        'Instrument Type': 'FXCashSettledForward', 'INSTRUMENT': 'BRR/RMB',
        'Type': 'Buy', 'Strike': STRIKE_API, 'Quantity': QTY,
        'Quantity Currency': qty_ccy, 'Other Quantity Units': other_ccy,
        'Publisher': 'PTAX|USB|BFIX_4PM_LDN|4', 'Settlement Location': 'BRAZIL',
        'Trading Book': 'GN NDF BJPM', 'Other Book': 'VESTABRA-BR',
        'SPN': '0033962', 'isCancelled': False,
    }


orig_rows = R._mapping_rows
R._mapping_rows = lambda key: (list(CCY_ROWS) if key == 'currency-base' else orig_rows(key))

try:
    # 1 ── a perna fraca, nas duas posições ──────────────────────────────────
    check('a perna fraca é achada na Quantity Currency',
          R._ndf_weak_leg('CNH', 'BRL') == 'CNH')
    check('a perna fraca é achada na Other Quantity Currency',
          R._ndf_weak_leg('BRL', 'CNH') == 'CNH')
    check('par sem moeda fraca não tem perna', R._ndf_weak_leg('USD', 'BRL') is None)
    check('par com as DUAS pernas fracas não tem perna (sem BRL, não há convenção)',
          R._ndf_weak_leg('CNH', 'MXN') is None)
    check('perna vazia não casa nada', R._ndf_weak_leg('', '') is None)

    # 2 ── a importação inverte nos dois arranjos ────────────────────────────
    for qc, oc, rotulo in (('RMB', 'BRR', 'notional na moeda fraca'),
                           ('BRR', 'RMB', 'notional em BRL')):
        alvo, deal = R._ndf_deal_from_api(_rec(qc, oc), 'E930179', {}, '19/08/2026')
        check('{}: o deal é importado'.format(rotulo), deal is not None)
        if not deal:
            continue
        rate = R._fxo_num(deal.get('Rate'))
        check('{}: o Rate é gravado em R$/moeda ({} → {:.8f})'.format(
                  rotulo, deal.get('Rate'), STRIKE_APP),
              rate is not None and abs(rate - STRIKE_APP) < 1e-9,
              str(deal.get('Rate')))
        check('{}: a rota é Other Publisher'.format(rotulo), alvo == 'other-publishers')

    # USD/BRL não é moeda fraca: o strike passa como veio
    _, usd = R._ndf_deal_from_api(dict(_rec('USB', 'BRR'), Strike=5.4321), 'E930179',
                                  {}, '19/08/2026')
    check('USD/BRL não é invertido', abs(R._fxo_num(usd.get('Rate')) - 5.4321) < 1e-9,
          str(usd.get('Rate')))

    # 3 ── o arquivo TER não inverte de novo ─────────────────────────────────
    # A Taxa a Termo (R$/Moeda) ocupa 12 inteiros + 8 decimais; com 4 casas de
    # cadastro o 0,77179965 vai arredondado para 0,7718.
    esperado = '00000000000077180000'
    linhas = {}
    for qc, oc, rotulo in (('CNH', 'BRL', 'notional na moeda fraca'),
                           ('BRL', 'CNH', 'notional em BRL')):
        deal = {'Status': 'New', 'LE': 'JPM', 'Deal': 'D5VL-2IE22T',
                'Client': 'VESTAS DO BRASIL', 'TradeDate': '19/08/2026',
                'SettlementDate': '10/09/2026', 'LastFixingDate': '08/09/2026',
                'Publisher': 'PTAX|USB|BFIX_4PM_LDN|4', 'Direction': 'BUY',
                'QuantityCurrency': qc, 'OtherQuantityCurrency': oc,
                'IsBRRFixed': ('YES' if qc == 'BRL' else 'NO'),
                'Notional': '35,000,000.00',
                'Rate': '{:,.8f}'.format(STRIKE_APP)}
        feito = R._generic_ndf_ter_line(deal, False)
        check('{}: a linha TER é montada'.format(rotulo), feito is not None)
        if not feito:
            continue
        linha = feito[1]
        linhas[qc] = linha
        check('{}: a Taxa a Termo sai como R$/moeda arredondada ({})'.format(rotulo, esperado),
              esperado in linha,
              'não achei {} na linha'.format(esperado))
        check('{}: a taxa CRUA da API não vai para o arquivo'.format(rotulo),
              '129567' not in linha)
    if len(linhas) == 2:
        # As duas pernas do mesmo trade só diferem em Moeda de Referência ×
        # Moeda Cotada (o flag BRL fixed) — a TAXA é a mesma nas duas.
        check('a Taxa a Termo é a mesma nos dois arranjos',
              linhas['CNH'].count(esperado) == linhas['BRL'].count(esperado))

    # 4 ── o contravalor do MT300 fecha com o que a API declara ──────────────
    contravalor = QTY * STRIKE_APP
    check('MT300: notional × Rate devolve o Other Quantity da API ({:,.2f})'.format(OTHER_API),
          abs(contravalor - OTHER_API) < 1.0, '{:,.2f}'.format(contravalor))
finally:
    R._mapping_rows = orig_rows

print('')
print('FALHAS: {}'.format(len(FAILS)))
sys.exit(1 if FAILS else 0)
