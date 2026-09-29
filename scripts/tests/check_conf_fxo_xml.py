"""XML da confirmação de Opção de Câmbio (FXO): valor e valorEstrangeiro.

Regra da mesa (29/09/2026): `valor` = Total Notional × Strike e
`valorEstrangeiro` = Total Notional, as duas colunas da página New Deals FXO.
Antes o FXO usava a regra da mercadoria, e o valorEstrangeiro saía em reais.
"""
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

from apps import create_app  # noqa: E402
from apps.config import config_dict  # noqa: E402

app = create_app(config_dict['Debug'])
from apps.pages import routes as R  # noqa: E402

falhas = 0


def ok(cond, msg):
    global falhas
    print(('  ok  ' if cond else '  FAIL ') + msg)
    if not cond:
        falhas += 1


def tag(xml, nome):
    m = re.search(r'<{0}>(.*?)</{0}>'.format(nome), xml)
    return m.group(1) if m else None


def deal(n, notional, strike):
    return {'Deal': n, 'TradeDate': '29/09/2026', 'SettlementDate': '29/12/2026',
            'UnderlyingAsset': 'USD', 'TotalNotional': notional, 'Strike': strike,
            'TaxID': '12.345.678/0001-90', 'Client': 'CLIENTE TESTE'}


print('\n== 1. uma operação ==')
with app.test_request_context():
    _n, xml, _w = R._conf_ndf_xml(
        [(deal('D1', '1,000,000.00', '5.123400'), None)], 'USD', date(2026, 9, 29),
        tipo='OPTION', prefixo='Opt_FXO', ccy_field='UnderlyingAsset',
        warn_no_spot=False, legs_fn=R._conf_fxo_legs)
ok(tag(xml, 'valor') == '5123400.00', 'valor = Total Notional × Strike')
ok(tag(xml, 'valorEstrangeiro') == '1000000.00', 'valorEstrangeiro = Total Notional')

print('\n== 2. várias operações somam ==')
with app.test_request_context():
    _n, xml, _w = R._conf_ndf_xml(
        [(deal('D1', '1000000', '5.0'), None), (deal('D2', '-500000', '5.2'), None)],
        'USD', date(2026, 9, 29), tipo='OPTION', prefixo='Opt_FXO',
        ccy_field='UnderlyingAsset', warn_no_spot=False, legs_fn=R._conf_fxo_legs)
ok(tag(xml, 'valor') == '7600000.00', 'valor soma notional × strike de cada uma')
ok(tag(xml, 'valorEstrangeiro') == '1500000.00', 'valorEstrangeiro soma os notionals')

print('\n== 3. sem strike fica de fora avisando ==')
with app.test_request_context():
    _n, xml, w = R._conf_ndf_xml(
        [(deal('D1', '1000000', ''), None)], 'USD', date(2026, 9, 29),
        tipo='OPTION', prefixo='Opt_FXO', ccy_field='UnderlyingAsset',
        warn_no_spot=False, legs_fn=R._conf_fxo_legs)
ok(any('D1' in x for x in w), 'avisa a operação sem strike')

print('\n== 4. o Save da confirmação FXO usa a regra ==')
src = open(os.path.join(os.path.dirname(__file__), '..', '..', 'apps', 'pages', 'features',
                        'confirmation', 'entrypoint.py'), encoding='utf-8').read()
ok("prefixo='Opt_FXO'" in src and 'legs_fn=_R()._conf_fxo_legs' in src,
   'o XML do Opt_FXO passa o _conf_fxo_legs')

print('\nFALHAS: {}'.format(falhas))
sys.exit(1 if falhas else 0)
