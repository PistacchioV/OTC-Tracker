"""XML da confirmação de Opção de Câmbio (FXO): valor e valorEstrangeiro.

Regra da mesa (29/09/2026): `valor` = Total Notional × Strike e
`valorEstrangeiro` = Total Notional, as duas colunas da página New Deals FXO.
Antes o FXO usava a regra da mercadoria, e o valorEstrangeiro saía em reais.

E desde 23/10/2026, com várias operações no documento (FXO e NDF Vanilla de
MGT): o valor é o da MAIOR em BRL, não a soma; o vencimento é o mais distante;
e o numeroContrato leva o acronym (`FXO_<data>_<moeda>_<acronym>`), senão dois
clientes no mesmo dia e moeda davam o mesmo número.
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

print('\n== 2. várias operações: o valor é o da MAIOR em BRL, não a soma ==')
# Mesa, 23/10/2026: D2 tem o maior valor em BRL (600 mil × 5,2 = 3,12 mi contra
# 500 mil × 5,0 = 2,5 mi), e o par valor/valorEstrangeiro é o DELA.
grupo = [(deal('D1', '500000', '5.0'), None), (dict(deal('D2', '-600000', '5.2'),
                                                    SettlementDate='15/03/2027'), None),
         (dict(deal('D3', '100000', '5.1'), SettlementDate='10/11/2026'), None)]
with app.test_request_context():
    n2, xml, _w = R._conf_ndf_xml(
        grupo, 'USD', date(2026, 9, 29), tipo='OPTION', prefixo='FXO',
        ccy_field='UnderlyingAsset', warn_no_spot=False, legs_fn=R._conf_fxo_legs,
        acronym='Cliente 1', valor_do_maior=True)
ok(tag(xml, 'valor') == '3120000.00', 'valor = o da maior operação em BRL (%s)' % tag(xml, 'valor'))
ok(tag(xml, 'valorEstrangeiro') == '600000.00', 'valorEstrangeiro = o da MESMA operação')
ok(tag(xml, 'dataVencimento') == '20270315', 'dataVencimento = a mais distante (%s)'
   % tag(xml, 'dataVencimento'))
ok(n2 == 'FXO_20260929_USD_CLIENTE_1', 'numeroContrato = FXO_<data>_<moeda>_<acronym> (%s)' % n2)
with app.test_request_context():
    n3, _x, _w = R._conf_ndf_xml(
        grupo, 'USD', date(2026, 9, 29), tipo='OPTION', prefixo='FXO',
        ccy_field='UnderlyingAsset', warn_no_spot=False, legs_fn=R._conf_fxo_legs,
        acronym='CLIENTE 2', valor_do_maior=True)
ok(n3 != n2, 'dois clientes no mesmo dia e moeda: números diferentes (%s × %s)' % (n2, n3))
with app.test_request_context():
    n1, _x, _w = R._conf_ndf_xml(
        grupo[:1], 'USD', date(2026, 9, 29), tipo='OPTION', prefixo='FXO',
        ccy_field='UnderlyingAsset', warn_no_spot=False, legs_fn=R._conf_fxo_legs,
        acronym='CLIENTE 1', valor_do_maior=True)
ok(n1 == 'D1', 'uma operação só segue com o próprio Deal (%s)' % n1)
with app.test_request_context():
    _n, xml, _w = R._conf_ndf_xml(
        grupo, 'USD', date(2026, 9, 29), tipo='OPTION', prefixo='Opt_Comm',
        ccy_field='UnderlyingAsset', warn_no_spot=False, legs_fn=R._conf_fxo_legs)
ok(tag(xml, 'valor') == '6130000.00' and _n == 'Opt_Comm_20260929_USD',
   'sem as flags (os outros documentos): a soma e o número de sempre')

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
ok("prefixo='FXO'" in src and 'legs_fn=_R()._conf_fxo_legs' in src,
   'o XML do FXO passa o _conf_fxo_legs')
ok(src.count('valor_do_maior=True') == 1 and 'valor_do_maior=vanilla' in src,
   'FXO e NDF Vanilla de MGT pedem o valor da maior operação')
ok("prefixo='NDF' if vanilla else 'NDF_FwdStart'" in src,
   'o NDF Vanilla de MGT numera com o prefixo NDF')

print('\nFALHAS: {}'.format(falhas))
sys.exit(1 if falhas else 0)
