"""O Import do NDF Cockpit puxa da API (getTradesBySettle), nao do SETTLEMENT.xlsx.

Daily Settlement > NDF: o que era lido do arquivo do Cockpit passou a vir do
`getTradesBySettle?product=NDF&date=AAAAMMDD` da Athena — as operacoes que
LIQUIDAM na data. O que este script prende (HANDOFF §421):

  1. O de-para registro da API → colunas do Cockpit: Deal Name, Cetip ID, datas
     em ISO (o `_ndfc_fmt_date` tenta m/d/yyyy PRIMEIRO — dd/mm gravado viraria
     outro mes), perna em BRL = LC e a outra = FC (nas DUAS ordens), notional em
     modulo, Strike e o Spot do bloco `settlement`, LEGAL pela razao social da LE
     e NM_COUNTERPARTY pelo Reference Data.
  2. O valor de liquidacao e o ForwardCashflow com DUAS casas, half-up.
  3. Par com moeda fraca inverte strike e spot (como o Rate do New Deals).
  4. Cancelado e perna interna ficam de fora; deal repetido no payload entra UMA vez.
  5. O endereco sai do cadastro `api-links` (uso Daily Settlement) — sem linha, o
     fallback — e a data e reescrita; erro de rede volta como erro, nunca como
     JSON vazio.
  6. O import grava o JSON do dia pedido e o entrypoint passa a data do picker.

Nao toca em dado real: o JSON vai para um tempfile, a sessao HTTP e stub e os
cadastros (moeda, LE, Reference Data) sao trocados por funcoes fixas.
"""
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='otc-share-'))

from apps.pages import athena_api as A                        # noqa: E402
from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


# O registro da captura de 08/09/2026 (STP-4T6-3BBUB26-0-0), campo a campo.
REC = {
    "Orig Entry Time": "Wed Jun 10 20:16:46 2026", "Entry Time": "Wed Jun 10 20:16:46 2026",
    "Trade Date": "2026-06-10", "Deal Name": "STP-4T6-3BBUB26-0-0", "Type": "Buy",
    "FX Pair": "/BRR-USB", "Trader Rate": "5.2805", "Strike": 5.2806, "StrikeOffset": "",
    "StrikeSetDate": "", "SPN": "0089652", "End Counterparty": "FMCDOBRA",
    "End Counterparty SPN": "0089652",
    "End Counterparty Description": "FMC QUIMICA DO BRASIL LIMITADA - FILIAL 0002 CNPJ 04.136.367/0002-79",
    "Instrument Type": "FXCashSettledForward", "Broker Fees Broker": "FXL",
    "Trading Book": "LM-FXECOMBRR FXC", "Other Book": "FMCDOBRA-BR",
    "Quantity Currency": "BRR", "Quantity": 28000000.0, "Other Quantity": -5302427.754421847,
    "Other Quantity Units": "USD", "Settlement Date": "2026-09-08", "Total VC": 768.8520243911678,
    "Source System": "FXALL", "Settlement Location": "BRAZIL", "External Account ID": "FMCDOBRA FXL",
    "Last Event": "Settle", "Counterparty Type": "C", "Settlement Currency": "BRR",
    "isCancelled": False, "isDead": True, "Publisher": "PTAX", "Expiration Date": "2026-09-04",
    "Expiration Settlement Date": "2026-09-08", "FIRST_FIXING_DATE": "", "LAST_FIXING_DATE": "",
    "NUM_FIXINGS": "", "PRODUCT": "FXD", "TRADER_NAME": "armin.tobaccowala", "INSTRUMENT": "USB/BRR",
    "Pay CCY": "USD", "Rec CCY": "BRR", "Frequency": "", "Trader": "armin.tobaccowala", "Comment": "",
    "Cetip ID": "26F02602138",
    "settlement": {"Event Name": "E5VL-3HW92EE", "Open Event Type": "Buy", "Quantity": 28000000.0,
                   "Quantity Currency": "BRR", "Spot": 5.1253, "ForwardCashflow": 823467.0302617104,
                   "FundableCashBalance": None},
}

# ── cadastros trocados por funcoes fixas ──────────────────────────────────
CCY = {'BRR': 'BRL', 'USB': 'USD', 'MXN': 'MXN'}
WEAK = set()
R._fxo_ccy = lambda c: CCY.get(str(c or '').strip().upper(), str(c or '').strip().upper())
R._ndf_weak_leg = lambda a, b: next((c for c in (a, b) if c in WEAK), None)
R._ndf_le_from_location = lambda loc: {'BRAZIL': 'JPM', 'MGT': 'MGT'}.get(loc)
R._ndf_le_row = lambda le: {'JPM': {'NAME': 'BANCO J.P MORGAN S.A'}}.get(le, {})
R._ndf_le_from_accronym = lambda acr: None
# O interbook NAO e stub: e a regra de verdade (`_ndf_is_interbook`) lendo o
# cadastro `interbook-ndf` do /mapping — trocado aqui por linhas fixas para o
# teste nao depender do arquivo. Perna interbook nao liquida contra cliente e
# nao pode entrar no Cockpit.
_INTERBOOK = [{'FIELD A': 'OTHER BOOK', 'VALUE A': 'LM-FXECOMBRR FXC',
               'FIELD B': 'SETTLEMENT LOCATION', 'VALUE B': 'BRAZIL', 'BOTH WAYS': ''},
              {'FIELD A': 'END COUNTERPARTY', 'VALUE A': 'DERIV NDF BJPM FXC',
               'FIELD B': 'TRADING BOOK', 'VALUE B': 'GN NDF BJPM', 'BOTH WAYS': 'YES'}]
R._mapping_rows = lambda key: list(_INTERBOOK) if key == 'interbook-ndf' else []
REF = {'FMCDOBRA': {'COUNTERPARTY': 'FMC QUIMICA DO BRASIL LTDA', 'SPN': '0089652', 'TAX ID': '04136367000279'}}
R._fxo_refdata_by_spn = lambda: {}
R._fxo_refdata_by_accronym = lambda spn=None: REF
R._ndf_ref_by_accronym = lambda rm, acr, le=None, rs=None, api_spn='': rm.get(str(acr).upper(), {})

tmp = tempfile.mkdtemp(prefix='otc-ndfc-')
R.NDFC_JSON_ROOT = tmp
calls = {'url': None, 'payload': None}
A.build_session = lambda: object()


def _get_json_url(session, url, params=None, timeout=None):
    # `timeout` na assinatura porque ele esta na REAL: um stub mais estreito que
    # a funcao que ele imita transforma o argumento novo em TypeError, e o teste
    # reprova por um motivo que nao e o que ele mede.
    calls['url'] = url
    calls['timeout'] = timeout
    if isinstance(calls['payload'], Exception):
        raise calls['payload']
    return calls['payload']


A.get_json_url = _get_json_url
orig_links = A.API_LINKS_FILE
A.API_LINKS_FILE = os.path.join(tmp, 'api-links.json')     # sem linha → fallback

try:
    print('\n== 1. de-para registro → colunas do Cockpit ==')
    row, why = R._ndfc_rec_from_api(REC, REF, {})
    check('registro entra', why, None)
    check('LEGAL = razao social da LE da Settlement Location', row['LEGAL'], 'BANCO J.P MORGAN S.A')
    check('NM_COUNTERPARTY = Reference Data pelo accronym', row['NM_COUNTERPARTY'], 'FMC QUIMICA DO BRASIL LTDA')
    check('ID_SOURCE_DEAL = Deal Name', row['ID_SOURCE_DEAL'], 'STP-4T6-3BBUB26-0-0')
    check('ID_DEAL = Event Name da liquidacao', row['ID_DEAL'], 'E5VL-3HW92EE')
    check('CD_CETIP_RETURN = Cetip ID', row['CD_CETIP_RETURN'], '26F02602138')
    check('DT_DEAL em ISO', row['DT_DEAL'], '2026-06-10')
    check('DT_SETTLEMENT em ISO', row['DT_SETTLEMENT'], '2026-09-08')
    check('ISO passa pelo _ndfc_fmt_date como dd/mm', R._ndfc_fmt_date(row['DT_DEAL']), '10/06/2026')
    check('LC = a perna em BRL', (row['CCY_NOTIONAL_LC'], row['VL_NOTIONAL_LC']), ('BRL', '28000000.00'))
    check('FC = a outra perna, em modulo', (row['CCY_NOTIONAL_FC'], row['VL_NOTIONAL_FC']), ('USD', '5302427.75'))
    check('VL_STRIKE_PRICE = Strike, as casas da API', row['VL_STRIKE_PRICE'], '5.2806')
    check('VL_FORWARD_RATE = Spot do bloco settlement', row['VL_FORWARD_RATE'], '5.1253')
    check('PUBLISHER', row['PUBLISHER'], 'PTAX')
    check('o que a API nao traz fica em branco',
          [row[c] for c in ('VL_TAX_INCOME', 'NB_BANK', 'CD_BRANCH', 'CD_BANK_ACCOUNT')], ['', '', '', ''])
    check('todas as colunas do Cockpit, e so elas', sorted(row), sorted(R._NDFC_COLUMNS))
    check('o strike do Cockpit fecha com o registro (fixing + |settle|/notional)',
          round(5.1253 + 823467.03 / 5302427.75, 4), 5.2806)

    print('\n== 2. valor de liquidacao = ForwardCashflow com duas casas, half-up ==')
    check('823467.0302617104 → 823467.03', row['[PROD] Cockpit.SETTLEMENT'], '823467.03')
    check('0.125 arredonda para cima (dinheiro)', R._ndfc_api_money(0.125), '0.13')
    check('negativo preserva o sinal', R._ndfc_api_money(-1234.565), '-1234.57')
    check('sem cashflow fica em branco', R._ndfc_api_money(None), '')
    check('o _ndfc_num le o que foi gravado', R._ndfc_num(row['[PROD] Cockpit.SETTLEMENT']), 823467.03)

    print('\n== 3. pernas e moeda fraca ==')
    rec2 = dict(REC, **{'Quantity Currency': 'USB', 'Quantity': 1000.0,
                        'Other Quantity Units': 'BRR', 'Other Quantity': -5300.0})
    row2, _ = R._ndfc_rec_from_api(rec2, REF, {})
    check('legs trocadas: LC continua sendo a de BRL',
          (row2['CCY_NOTIONAL_LC'], row2['VL_NOTIONAL_LC'], row2['CCY_NOTIONAL_FC'], row2['VL_NOTIONAL_FC']),
          ('BRL', '5300.00', 'USD', '1000.00'))
    rec3 = dict(REC, **{'Quantity Currency': 'USB', 'Quantity': 100.0,
                        'Other Quantity Units': 'MXN', 'Other Quantity': -1800.0})
    row3, _ = R._ndfc_rec_from_api(rec3, REF, {})
    check('cross sem BRL: LC = Quantity, FC = Other', (row3['CCY_NOTIONAL_LC'], row3['CCY_NOTIONAL_FC']), ('USD', 'MXN'))
    WEAK.add('MXN')
    rec4 = dict(REC, **{'Quantity Currency': 'BRR', 'Other Quantity Units': 'MXN', 'Strike': 3.2,
                        'settlement': dict(REC['settlement'], Spot=3.33)})
    row4, _ = R._ndfc_rec_from_api(rec4, REF, {})
    check('moeda fraca inverte strike e spot, 8 casas',
          (row4['VL_STRIKE_PRICE'], row4['VL_FORWARD_RATE']), ('0.31250000', '0.30030030'))
    WEAK.clear()

    print('\n== 4. quem fica de fora ==')
    check('cancelado', R._ndfc_rec_from_api(dict(REC, isCancelled=True), REF, {}), (None, 'cancelled'))
    check('sem Deal Name', R._ndfc_rec_from_api(dict(REC, **{'Deal Name': ''}), REF, {}), (None, 'invalid'))
    check('holding book', R._ndfc_rec_from_api(dict(REC, **{'End Counterparty': 'GLOBAL_HOLDING_BOOK'}), REF, {}),
          (None, 'internal'))
    check('interbook pelo cadastro (Other Book x Settlement Location)',
          R._ndfc_rec_from_api(dict(REC, **{'Other Book': 'LM-FXECOMBRR FXC'}), REF, {}), (None, 'internal'))
    check('interbook casa cego a hifen/espaco, como no New Deals',
          R._ndfc_rec_from_api(dict(REC, **{'Other Book': 'LM FXECOMBRR FXC'}), REF, {}), (None, 'internal'))
    check('interbook BOTH WAYS (End Counterparty x Trading Book, invertido)',
          R._ndfc_rec_from_api(dict(REC, **{'End Counterparty': 'GN NDF BJPM',
                                            'Trading Book': 'DERIV NDF BJPM FXC'}), REF, {}), (None, 'internal'))
    check('o registro da captura (FMCDOBRA-BR) NAO e interbook e entra',
          R._ndfc_rec_from_api(REC, REF, {})[1], None)
    nocad = dict(REC, **{'End Counterparty': 'XYZ', 'Settlement Location': 'LONDON'})
    rown, _ = R._ndfc_rec_from_api(nocad, REF, {})
    check('sem cadastro: descricao da API e a location crua',
          (rown['NM_COUNTERPARTY'][:30], rown['LEGAL']), ('FMC QUIMICA DO BRASIL LIMITADA', 'LONDON'))

    print('\n== 5. endereco, data e erro de rede ==')
    ref = datetime(2026, 9, 8)
    check('sem linha cadastrada, o fallback com a data',
          R._ndfc_api_url(ref), R._NDFC_API_URL_FALLBACK.replace('YYYYMMDD', '20260908'))
    with io.open(A.API_LINKS_FILE, 'w', encoding='utf-8') as fh:
        fh.write(json.dumps([{'USE': 'Daily Settlement', 'PRODUCT': 'NDF',
                              'URL': 'https://athena-app.jpmchase.net/x/getTradesBySettle?product=NDF&date=YYYYMMDD'}]))
    check('linha cadastrada vence o fallback', R._ndfc_api_url(ref),
          'https://athena-app.jpmchase.net/x/getTradesBySettle?product=NDF&date=20260908')
    calls['payload'] = RuntimeError('boom')
    res = R._ndfc_import(ref)
    check('erro de rede volta como erro', (res['success'], 'boom' in res['error']), (False, True))

    # O tempo de leitura: este endpoint varre o LIVRO INTEIRO da data de
    # liquidacao — e o dia em que ele herdou os 30 s do `getTrades` de UM produto
    # estourou `ReadTimeout` no meio do replay do ADFS, com o traceback do
    # urllib3 chegando a tela.
    check('o Import pede o timeout de RELATORIO, nao o de getTrades',
          (calls['timeout'], calls['timeout'] == A.REPORT_TIMEOUT,
           A.REPORT_TIMEOUT > A.REQUEST_TIMEOUT), (A.REPORT_TIMEOUT, True, True))
    # E o estouro tem mensagem PROPRIA: o repr do urllib3 nao diz quanto se
    # esperou nem o que fazer, e o que se faz aqui e diferente de um 401 de SSO.
    import requests as _rq
    calls['payload'] = _rq.exceptions.ReadTimeout('read timed out')
    res = R._ndfc_import(ref)
    check('timeout diz os segundos e o remedio, sem repr de urllib3',
          (res['success'], str(A.REPORT_TIMEOUT) + 's' in res['error'],
           'ATHENA_REPORT_TIMEOUT' in res['error'], 'HTTPSConnectionPool' in res['error']),
          (False, True, True, False))
    check('e nao grava JSON nenhum', os.path.isfile(R._ndfc_json_path(ref)), False)

    print('\n== 6. o import grava o JSON do dia pedido ==')
    calls['payload'] = {'trades': [REC, dict(REC, isCancelled=True, **{'Deal Name': 'CANC-1'}),
                                   REC, dict(REC, **{'Other Book': 'LM-FXECOMBRR FXC', 'Deal Name': 'IB-1'})]}
    res = R._ndfc_import(ref)
    check('sucesso com a data pedida', (res['success'], res['date'], res['rows']), (True, '2026-09-08', 1))
    check('a URL chamada e a cadastrada', calls['url'].endswith('date=20260908'), True)
    check('cancelado e interbook contados fora', res['skipped'], {'cancelled': 1, 'internal': 1, 'invalid': 0})
    jp = R._ndfc_json_path(ref)
    check('JSON no caminho do dia', jp.endswith(os.path.join('2026', '09', '08', 'ndf-cockpit_20260908.json')), True)
    data = json.load(io.open(jp, encoding='utf-8'))
    check('deal repetido no payload entra uma vez', len(data), 1)
    check('meta do maker/checker carimbada OK', (data[0]['_nc_status'], bool(data[0]['_nc_id'])), ('OK', True))
    check('o timestamp do import fica ao lado', bool(R._ds_read_updated(jp)), True)

    src = io.open('apps/pages/features/ndf_cockpit/entrypoint.py', encoding='utf-8').read()
    check('o entrypoint passa a data do picker ao import',
          "_ndfc_import(_R()._api_ref_date(p.get('date')))" in src, True)
    js = io.open('apps/static/js/pages/ndf-cockpit.js', encoding='utf-8').read()
    check('e o JS manda a data no POST', "body: JSON.stringify({ date: currentDate() })" in js, True)
finally:
    A.API_LINKS_FILE = orig_links
    shutil.rmtree(tmp, ignore_errors=True)

print('\nTUDO OK' if not fails else '\n%d FAIL' % len(fails))
sys.exit(1 if fails else 0)
