"""O Import do NDF Cockpit puxa da API (getTradesBySettle), nao do SETTLEMENT.xlsx.

Daily Settlement > NDF: o que era lido do arquivo do Cockpit passou a vir do
`getTradesBySettle?product=NDF&date=AAAAMMDD` da Athena — as operacoes que
LIQUIDAM na data. O que este script prende (HANDOFF §421):

  1. O de-para registro da API → colunas do Cockpit: Deal Name, Cetip ID, datas
     em ISO (o `_ndfc_fmt_date` tenta m/d/yyyy PRIMEIRO — dd/mm gravado viraria
     outro mes), perna em BRL = LC e a outra = FC (nas DUAS ordens), notional em
     modulo, Strike e o Spot do bloco `settlement`, LEGAL pela razao social da LE
     e NM_COUNTERPARTY pelo Reference Data.
  2. O valor de liquidacao e o PRIMEIRO `Rolled Positions`, DUAS casas half-up.
  3. Par com moeda fraca inverte strike e spot (como o Rate do New Deals).
  4. Cancelado e perna interna ficam de fora; deal repetido no payload entra UMA vez.
  5. So entra quem TEM `settlement` (a lista, nao um objeto) e cujo Trade Date
     nao seja hoje; um trade com varios eventos vira uma linha por evento.
  6. O `VL_TAX_INCOME` e CALCULADO no import (§423) e o Delete all esvazia o dia
     sem apagar o arquivo.
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
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='otc-share-'))

from apps.pages import athena_api as A                        # noqa: E402
from apps.pages import routes as R                            # noqa: E402

fails = []


def _boom(*a, **k):
    raise RuntimeError('ledger indisponivel')


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
    # A forma REAL da API: `settlement` e uma LISTA, e o valor de liquidacao e o
    # PRIMEIRO item de `Rolled Positions` (o caixa em BRL; o segundo e o
    # notional da moeda). O fixture usava um objeto com `ForwardCashflow`, que
    # nao existe no payload de producao — e por isso o de-para lia dict e a
    # lista caia fora calada, deixando ID_DEAL, Spot e valor VAZIOS na tela.
    "settlement": [{"Event Name": "E5VL-3HW92EE", "Open Event Type": "Buy", "Quantity": 28000000.0,
                    "Quantity Currency": "BRR", "Spot": 5.1253,
                    "Rolled Positions": [823467.0302617104, -28000000.0],
                    "FundableCashBalance": None}],
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
# O ledger mensal do IR pende do `_B3_DATA_DIR`, e o import ESCREVE nele (§423).
# Sem esta linha o teste gravaria o imposto das operacoes do fixture no ledger
# de VERDADE, e o acumulado do mes passaria a contar liquidacoes que nao
# existem — sem erro nenhum, e so no mes seguinte alguem notaria.
R._B3_DATA_DIR = tmp
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
    # O imposto nasce vazio AQUI de proposito: o piso de R$ 1,00 e por
    # CONTRAPARTE no mes, e nao da para decidir olhando uma operacao de cada
    # vez. Quem o escreve e o `_ndfc_apply_ir`, com o dia inteiro montado.
    check('todas as colunas do Cockpit, e so elas', sorted(row), sorted(R._NDFC_COLUMNS))
    check('o strike do Cockpit fecha com o registro (fixing + |settle|/notional)',
          round(5.1253 + 823467.03 / 5302427.75, 4), 5.2806)

    print('\n== 2. valor de liquidacao = 1o Rolled Positions, duas casas half-up ==')
    check('823467.0302617104 → 823467.03', row['[PROD] Cockpit.SETTLEMENT'], '823467.03')
    check('0.125 arredonda para cima (dinheiro)', R._ndfc_api_money(0.125), '0.13')
    check('negativo preserva o sinal', R._ndfc_api_money(-1234.565), '-1234.57')
    check('sem cashflow fica em branco', R._ndfc_api_money(None), '')
    check('o _ndfc_num le o que foi gravado', R._ndfc_num(row['[PROD] Cockpit.SETTLEMENT']), 823467.03)

    # O PRIMEIRO item e o caixa em BRL; o segundo e o notional da moeda, e ele
    # e MAIOR — pegar o maior, ou somar, daria o notional no lugar da
    # liquidacao. O primeiro item que seja NUMERO: a lista chega com um rotulo
    # na frente em parte dos eventos.
    def rolled(*vals):
        return R._ndfc_api_rolled(R._ndf_api_norm({'Rolled Positions': list(vals)}))
    check('o primeiro item vence o notional ao lado', rolled(-33273.4, -28000000.0), -33273.4)
    check('rotulo na frente nao conta como valor', rolled('BRL', -33273.4), -33273.4)
    check('lista vazia nao tem valor', rolled(), None)
    # Plano B: o payload que ja esta gravado em disco tem `ForwardCashflow` e
    # nao tem `Rolled Positions`. Ele continua valendo, senao reabrir um dia
    # antigo mostraria a coluna vazia.
    check('sem Rolled, o ForwardCashflow antigo ainda responde',
          R._ndfc_api_rolled(R._ndf_api_norm({'ForwardCashflow': -100.005})), -100.005)

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
                        'settlement': [dict(REC['settlement'][0], Spot=3.33)]})
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
    check('cancelado e interbook contados fora',
          {k: v for k, v in res['skipped'].items() if v},
          {'cancelled': 1, 'internal': 1})

    print('\n== 6b. so entra quem TEM settlement, e nao foi bookado hoje ==')
    HOJE = R._br_now().date().isoformat()
    # A resposta do getTradesBySettle traz tambem o trade que ainda NAO
    # liquidou, com `settlement: []`. Ele viraria uma linha do Cockpit sem
    # evento, sem fixing e sem valor — uma liquidacao que nao existe, somando
    # zero no Summary e aparecendo no aviso ao cliente.
    vazio = dict(REC, **{'Deal Name': 'SEM-STL', 'settlement': []})
    check('settlement vazio fica de fora', R._ndfc_rec_from_api(vazio, REF, {}),
          (None, 'no_settlement'))
    sem_chave = {k: v for k, v in REC.items() if k != 'settlement'}
    sem_chave['Deal Name'] = 'SEM-CHAVE'
    check('e sem a chave tambem', R._ndfc_rec_from_api(sem_chave, REF, {})[1], 'no_settlement')
    # O trade bookado HOJE aparece porque a data de liquidacao dele cai na data
    # pedida, mas o evento ainda nao ocorreu.
    hoje_rec = dict(REC, **{'Deal Name': 'HOJE-1', 'Trade Date': HOJE})
    check('bookado hoje fica de fora', R._ndfc_rec_from_api(hoje_rec, REF, {})[1], 'booked_today')
    check('   e ontem entra', R._ndfc_rec_from_api(
        dict(REC, **{'Trade Date': '2026-01-02'}), REF, {})[1], None)
    jp = R._ndfc_json_path(ref)
    check('JSON no caminho do dia', jp.endswith(os.path.join('2026', '09', '08', 'ndf-cockpit_20260908.json')), True)
    data = json.load(io.open(jp, encoding='utf-8'))
    check('deal repetido no payload entra uma vez', len(data), 1)
    check('meta do maker/checker carimbada OK', (data[0]['_nc_status'], bool(data[0]['_nc_id'])), ('OK', True))
    check('o timestamp do import fica ao lado', bool(R._ds_read_updated(jp)), True)

    # Um trade pode liquidar em mais de um EVENTO na mesma data (as rolagens):
    # ficar no primeiro perderia os demais, e a chave de dedupe ja e
    # deal x evento — o modelo sempre esperou varios.
    dois = dict(REC, **{'Deal Name': 'MULTI-1', 'settlement': [
        dict(REC['settlement'][0]),
        dict(REC['settlement'][0], **{'Event Name': 'E5VL-SEGUNDO',
                                      'Rolled Positions': [-100.005, -28000000.0]})]})
    calls['payload'] = {'trades': [dois]}
    res = R._ndfc_import(ref)
    linhas = json.load(io.open(R._ndfc_json_path(ref), encoding='utf-8'))
    check('um trade com DOIS eventos vira duas linhas', res['rows'], 2)
    check('   com o evento e o valor de cada um',
          sorted((l['ID_DEAL'], l['[PROD] Cockpit.SETTLEMENT']) for l in linhas),
          [('E5VL-3HW92EE', '823467.03'), ('E5VL-SEGUNDO', '-100.01')])

    src = io.open('apps/pages/features/ndf_cockpit/entrypoint.py', encoding='utf-8').read()
    check('o entrypoint passa a data do picker ao import',
          "_ndfc_import(_R()._api_ref_date(p.get('date')))" in src, True)
    js = io.open('apps/static/js/pages/ndf-cockpit.js', encoding='utf-8').read()
    check('e o JS manda a data no POST', "body: JSON.stringify({ date: currentDate() })" in js, True)

    print('\n== 7. o VL_TAX_INCOME e CALCULADO no import (§423) ==')
    # A API nao traz o imposto — ele era uma coluna do SETTLEMENT.xlsx. Quem o
    # escreve e o `_ndfc_apply_ir`, com o DIA INTEIRO montado, porque o piso de
    # R$ 1,00 e por contraparte dentro do mes e nao da para decidir olhando uma
    # operacao de cada vez.
    R._ndfc_ir_exempt = lambda nome: False
    def _linha(nm, valor, legal='BANCO J.P MORGAN S.A'):
        return {'NM_COUNTERPARTY': nm, 'LEGAL': legal,
                '[PROD] Cockpit.SETTLEMENT': valor, 'VL_TAX_INCOME': ''}
    linhas = [_linha('ACME', '-33273.40'), _linha('TINY', '-10.00'),
              _linha('PLUS', '50000.00')]
    R._ndfc_apply_ir(datetime(2026, 9, 8), linhas)
    check('0,005% de quem o banco PAGA', linhas[0]['VL_TAX_INCOME'], '1.66')
    # 0,005% de 10,00 = R$ 0,0005: abaixo do piso, o cliente recebe o BRUTO e o
    # valor fica guardado contra a contraparte ate alcancar R$ 1,00 no mes.
    check('abaixo de R$ 1,00 retem zero e acumula', linhas[1]['VL_TAX_INCOME'], '0.00')
    check('quem RECEBE nao paga imposto', linhas[2]['VL_TAX_INCOME'], '0.00')
    exentos = [_linha('ACME', '-33273.40')]
    R._ndfc_ir_exempt = lambda nome: True
    R._ndfc_apply_ir(datetime(2026, 9, 8), exentos)
    check('o cadastro ndfc-ir-exempt zera a retencao', exentos[0]['VL_TAX_INCOME'], '0.00')
    R._ndfc_ir_exempt = lambda nome: False
    # A celula e um INSTANTANEO e a falha nao pode inventar zero: vazio pede
    # conferencia, um zero AFIRMARIA que nao ha imposto.
    _for_day, R._ndfsum_ir_for_day = R._ndfsum_ir_for_day, _boom
    quebrado = [_linha('ACME', '-33273.40')]
    R._ndfc_apply_ir(datetime(2026, 9, 8), quebrado)
    check('IR que nao calcula deixa a coluna VAZIA', quebrado[0]['VL_TAX_INCOME'], '')
    R._ndfsum_ir_for_day = _for_day
    # E o import escreve a coluna sozinho, sem ninguem chamar nada.
    calls['payload'] = {'trades': [REC]}
    R._ndfc_import(ref)
    gravado = json.load(io.open(R._ndfc_json_path(ref), encoding='utf-8'))
    check('e o import ja grava a celula preenchida',
          bool(gravado and gravado[0]['VL_TAX_INCOME']), True)

    print('\n== 8. o Delete all esvazia o dia sem apagar o arquivo ==')
    # O endpoint e casca (sessao → _ndfc_load → _ndfc_save), mas os TRES
    # desfechos dele sao a regra: apagou N, ja estava vazio, dia sem arquivo.
    from apps import create_app                                    # noqa: E402
    from apps.config import DebugConfig                             # noqa: E402
    app = create_app(DebugConfig)
    app.config['WTF_CSRF_ENABLED'] = False
    cli = app.test_client()
    with cli.session_transaction() as ss:
        # UTC, nao o relogio local: em BRT a sessao le como VENCIDA e o cliente
        # recebe a tela de login no lugar do JSON.
        ss.update(authenticated=True, user_sid='X1', user_name='t', user_role='ADMIN',
                  session_expires_at=(datetime.now(timezone.utc).replace(tzinfo=None)
                                      + timedelta(hours=1)).isoformat())
    R._create_notification = lambda *a, **k: None
    r = cli.post('/api/ndf-cockpit/rows/delete-all', json={'date': '2026-09-08'})
    check('devolve quantas linhas sairam', (r.status_code, r.get_json()['removed']), (200, 1))
    jp = R._ndfc_json_path(ref)
    # O ARQUIVO fica: o dia continua importado, com zero linhas. Apagado, a tela
    # cairia no fallback de "dia sem arquivo", que se le como "ainda nao
    # importaram" e nao como "esvaziaram de proposito".
    check('o arquivo do dia continua la, vazio',
          (os.path.isfile(jp), json.load(io.open(jp, encoding='utf-8'))), (True, []))
    r2 = cli.post('/api/ndf-cockpit/rows/delete-all', json={'date': '2026-09-08'})
    check('dia ja vazio: sucesso com zero', (r2.status_code, r2.get_json()['removed']), (200, 0))
    r3 = cli.post('/api/ndf-cockpit/rows/delete-all', json={'date': '2026-09-04'})
    check('dia sem arquivo nenhum: 404', r3.status_code, 404)
    r4 = app.test_client().post('/api/ndf-cockpit/rows/delete-all', json={'date': '2026-09-08'})
    check('sem sessao: 401', r4.status_code, 401)
    tpl = io.open('apps/templates/pages/ndf-cockpit.html', encoding='utf-8').read()
    check('o botao Delete all esta na barra, em vermelho',
          ('ndfcDeleteAllBtn' in tpl and 'btn-danger' in tpl and
           'data-lang="ndfc-delete-all"' in tpl), True)
    # Esvaziar o dia nao tem desfazer: o clique passa por uma confirmacao que
    # diz o numero de linhas e a data.
    check('e o clique confirma antes de chamar o endpoint',
          ("ndfcDeleteAllBtn" in js and "'/api/ndf-cockpit/rows/delete-all'" in js
           and 'Swal.fire' in js), True)
finally:
    A.API_LINKS_FILE = orig_links
    shutil.rmtree(tmp, ignore_errors=True)

print('\nTUDO OK' if not fails else '\n%d FAIL' % len(fails))
sys.exit(1 if fails else 0)
