# -*- coding: utf-8 -*-
"""Intrag NDF de moeda: a Settlement Parity sai do PAR, não fixa em BRL.

Um NDF EUR/USD fluía para a Intrag com Settlement Parity BRL — o valor era um
literal no `_save_intrag_ndf_moeda_entry`. Com BRL no par a paridade é BRL; no
cross sem BRL é a moeda de cotação (USD no EUR/USD e no USD/CNH).

  1. a regra pura (`domain.paridade_liquidacao`);
  2. a entrada gravada pelo comando, com a persistência espiada.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

FAILS = []


def check(nome, obtido, esperado):
    ok = obtido == esperado
    print(('  ok  ' if ok else '  FAIL ') + nome + ('' if ok else '  → {!r} != {!r}'.format(obtido, esperado)))
    if not ok:
        FAILS.append(nome)


from apps import create_app  # noqa: E402
from apps.config import config_dict  # noqa: E402

app = create_app(config_dict['Debug'])
from apps.pages.features.intrag import commands, domain  # noqa: E402
from apps.pages.features.intrag.infra import persistence  # noqa: E402

print('\n== 1. a regra ==')
P = domain.paridade_liquidacao
check('USD/BRL → BRL', P('USD', 'BRL'), 'BRL')
check('BRL na quantidade → BRL', P('BRL', 'EUR'), 'BRL')
check('EUR/USD → USD', P('EUR', 'USD'), 'USD')
check('EUR/USD bookado na perna USD → USD', P('USD', 'EUR'), 'USD')
check('USD/CNH → USD', P('CNH', 'USD'), 'USD')
check('EUR/GBP (sem BRL nem USD) → a outra perna', P('EUR', 'GBP'), 'GBP')
check('par ilegível → BRL', P('EUR', ''), 'BRL')

print('\n== 2. a entrada gravada ==')
gravadas = []
orig = persistence._intrag_ndf_persist
persistence._intrag_ndf_persist = lambda entry, td: gravadas.append(entry)
try:
    with app.app_context():
        base = {'Deal': 'T1', 'Client': 'LAWTON', 'Direction': 'SELL', 'TradeDate': '30/09/2026',
                'SettlementDate': '17/11/2026', 'LastFixingDate': '13/11/2026',
                'Rate': '1.1712', 'Notional': '1,000,000.00', 'Publisher': 'PTAX|BRR[PTAX'}
        commands._save_intrag_ndf_moeda_entry(dict(base, QuantityCurrency='EUR', OtherQuantityCurrency='USD'))
        commands._save_intrag_ndf_moeda_entry(dict(base, Deal='T2', Rate='5.40',
                                                   QuantityCurrency='USD', OtherQuantityCurrency='BRL'))
finally:
    persistence._intrag_ndf_persist = orig
check('EUR/USD: Settlement Parity USD', gravadas[0]['strike_currency'], 'USD')
check('... e a moeda continua EUR', gravadas[0]['currency'], 'EUR')
check('USD/BRL: Settlement Parity BRL', gravadas[1]['strike_currency'], 'BRL')

print('\nFALHAS: {}'.format(len(FAILS)))
sys.exit(1 if FAILS else 0)
