# -*- coding: utf-8 -*-
"""check_efinanceira.py — Regulatory › E-financeira: as quatro páginas e o
arquivo mensal (equipe, 30/10/2026).

  1. a página de cada operação (a tabela da equipe): ATHENA-FXO = opção FX e de
     commodities, ATHENA-NDF = NDF FX e de commodities, KAPITAL = swap
     CEM/CEMHYB, PYRAMID = tudo da EDG; o produto/LOB das telas de liquidação;
  2. os eventos (o Settlement Type das telas), quem é o titular do prêmio e o
     que encerra a operação (recompra só a total; fluxo de swap só o do
     vencimento);
  3. as CINCO linhas do exemplo da equipe montadas a partir dos eventos:
     Total Crédito/Débito, Saldo, Pagamento Acumulado, Data de Encerramento;
  4. o arquivo: o cabeçalho e a linha do exemplo, byte a byte (com o
     `num_ente_declarado` e o `conta_reportpais` em branco — a especificação
     diz "não preencher", o exemplo os trazia); `pag_tp` 999 sem pagamento;
  5. ponta a ponta no armazém real (tmp): o Import Settlements do mês (as três
     fontes stub), as quatro páginas com as linhas DELAS, o intragrupo e a
     entidade fora do cadastro de fora, o Valor Interno × Valor B3, a data do
     CGD pelo Tracking Docs, o arquivo que recusa linha incompleta e correção
     pendente, o Edit com o 4-olhos, o arquivo gravado no share com o nome e o
     conteúdo, o status Generated, o Delete e o Add Row;
  6. menu, cadastro, ganchos nas telas de liquidação, sino e traduções.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_efinanceira.py
"""
import io
import json
import os
import re
import sys
import tempfile
import time
import types
from datetime import date, datetime, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
RAIZ = tempfile.mkdtemp(prefix='otc-efin-')
os.environ['OTC_DATA_DIR'] = RAIZ
os.environ['OTC_DATABASE_DIR'] = os.path.join(RAIZ, 'db')
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(nome, cond, extra=''):
    print(('  ok  ' if cond else ' FAIL ') + nome + (('  — ' + str(extra)) if (not cond and extra) else ''))
    if not cond:
        FALHAS.append(nome)


def ev(day, kinds, value=None, **kw):
    e = {'day': day, 'source': kw.pop('source', 'ops'), 'seq': 0, 'le': kw.pop('le', 'JPM'),
         'kinds': kinds, 'value': value, 'b3_value': kw.pop('b3_value', None)}
    e.update(kw)
    return e


def secao_dominio():
    from apps.pages.features.efinanceira import domain as D

    print('== 1. a página de cada operação ==')
    check('opção FX e de commodities → ATHENA-FXO',
          D.page_of('OPTION', 'CEM') == 'athena-fxo' and D.page_of('OPTION', 'COMMODITIES') == 'athena-fxo')
    check('NDF FX e de commodities → ATHENA-NDF',
          D.page_of('NDF', 'CEM') == 'athena-ndf' and D.page_of('NDF', 'COMMODITIES') == 'athena-ndf')
    check('swap CEM/CEMHYB → KAPITAL', D.page_of('SWAP', 'CEM') == 'kapital' and D.page_of('SWAP', 'CEMHYB') == 'kapital')
    check('tudo da EDG → PYRAMID', all(D.page_of(p, 'EDG') == 'pyramid' for p in D.PRODUCTS))
    check('quatro páginas, quatro arquivos', [D.file_name(p, '202609') for p in D.PAGE_ORDER] == [
        'KAPITAL_SWAP_EFINAN_202609.csv', 'ATHENA_NDF_EFINAN_202609.csv', 'ATHENA_FXO_EFINAN_202609.csv',
        'PYRAMID_202609.csv'])
    check('termo de mercadoria do Trade Level → NDF × COMMODITIES', D.produto_lob('TERMO', 'COMMODITIES') == ('NDF', 'COMMODITIES'))
    check('classe MOEDA da opção → CEM; EQUITIES → EDG',
          D.produto_lob('OPTION', 'MOEDA') == ('OPTION', 'CEM') and D.produto_lob('OPTION', 'EQUITIES') == ('OPTION', 'EDG'))
    check('swap EQUITIES (o elo de equity) → EDG', D.produto_lob('SWAP', 'EQUITIES') == ('SWAP', 'EDG'))
    check('NDF do Cockpit sem LOB → CEM; swap sem LOB fica sem', D.produto_lob('NDF', '', 'ndf') == ('NDF', 'CEM')
          and D.produto_lob('SWAP', '') == ('SWAP', ''))

    print('== 2. eventos, titular e encerramento ==')
    check('Premium · Maturity → os dois', D.kinds_of('Premium · Maturity') == ['PREMIUM', 'MATURITY'])
    check('a recompra é UNWIND, sempre', D.kinds_of('MATURITY', unwind=True) == ['UNWIND'])
    check('texto sem tipo → SETTLEMENT', D.kinds_of('') == ['SETTLEMENT'])
    check('TITULAR paga o prêmio, LANCADOR recebe; códigos 11/12',
          (D.holder_of('TITULAR'), D.holder_of('Lançador'), D.holder_of('11'), D.holder_of('12'), D.holder_of(''))
          == (True, False, True, False, None))
    check('termo: PARTE paga, CONTRAPARTE não', (D.holder_of('PARTE'), D.holder_of('CONTRAPARTE')) == (True, False))
    check('vencimento/exercício/expiração encerram',
          all(D.closes({'kinds': [k]}) for k in ('MATURITY', 'EXERCISE', 'EXPIRY')))
    check('recompra: só a TOTAL encerra', D.closes({'kinds': ['UNWIND'], 'closes': True})
          and not D.closes({'kinds': ['UNWIND'], 'closes': False}) and not D.closes({'kinds': ['UNWIND'], 'closes': None}))
    check('fluxo de swap: só o do vencimento encerra',
          D.closes({'kinds': ['CASHFLOW'], 'day': '2026-09-30', 'maturity': '2026-09-30'})
          and not D.closes({'kinds': ['CASHFLOW'], 'day': '2026-09-10', 'maturity': '2028-01-01'}))

    print('== 3. as cinco linhas do exemplo da equipe ==')
    evs = [
        # 1. NDF CEM da MGT: o banco paga na liquidação e encerra
        ev('2026-09-15', ['MATURITY'], -16395.26, le='MGT', source='ndf', internal_id='D5VL-2L2V0F',
           b3_id='26J02791770', product='NDF', lob='CEM', counterparty='GE CELMA LTDA',
           taxid='33.435.231/0001-87', trade_date='2026-08-05', maturity='2026-09-15'),
        # 2. swap EDG × Banco Safra: o banco RECEBE o prêmio (titular NO)
        ev('2026-09-28', ['PREMIUM'], 81192.50, internal_id='758662', b3_id='26J08689634', product='SWAP',
           lob='EDG', counterparty='BANCO SAFRA S.A', trade_date='2026-09-27', maturity='2031-10-28'),
        # 3. o B2B × Atacama: o banco PAGA o prêmio (titular YES)
        ev('2026-09-28', ['PREMIUM'], -81192.50, internal_id='758662', b3_id='26J08689635', product='SWAP',
           lob='EDG', counterparty='ATACAMA', trade_date='2026-09-27', maturity='2031-10-28'),
        # 4. opção de commodities lançada em 2021 que venceu sem caixa
        ev('2026-09-16', ['EXPIRY'], None, source='exp', internal_id='XPTO-4', b3_id='OPC4', product='OPTION',
           lob='COMMODITIES', counterparty='XPTO', trade_date='2021-10-10', maturity='2026-09-16',
           premium=50000.0, premium_date='2021-10-10', holder=False),
        # 5. opção CEM lançada em 2021 exercida contra o banco
        ev('2026-09-16', ['EXERCISE'], -63000.0, internal_id='XPTO-5', b3_id='OPC5', product='OPTION',
           lob='CEM', counterparty='XPTO', trade_date='2021-10-10', maturity='2026-09-16',
           premium=40000.0, premium_date='2021-10-10', holder=False),
    ]
    ops = {o['b3_id']: D.finish(o) for o in D.aggregate(evs).values()}
    o1, o2, o3, o4, o5 = (ops[k] for k in ('26J02791770', '26J08689634', '26J08689635', 'OPC4', 'OPC5'))
    check('1: Pagamento Acumulado 16.395,26, encerra em 15/09, sem saldo',
          (o1['payment'], o1['closing'], o1['balance'], o1['tot_credit'], o1['pag_tp'])
          == (16395.26, '2026-09-15', 0.0, 0.0, 'FATCA504'), o1)
    check('2: Total Crédito 81.192,50, titular NO, não encerra, pag 999',
          (o2['tot_credit'], o2['tot_debit'], o2['payment'], o2['holder'], o2['closing'], o2['pag_tp'])
          == (81192.50, 0.0, 0.0, False, '', '999'), o2)
    check('3: Total Débito e Pagamento Acumulado 81.192,50, titular YES',
          (o3['tot_debit'], o3['payment'], o3['holder'], o3['tot_credit']) == (81192.50, 81192.50, True, 0.0), o3)
    check('4: Saldo 50.000 (o prêmio recebido na vida), encerra em 16/09, sem pagamento',
          (o4['balance'], o4['closing'], o4['payment'], o4['tot_credit'], o4['premium'], o4['pag_tp'])
          == (50000.0, '2026-09-16', 0.0, 0.0, 50000.0, '999'), o4)
    check('5: Saldo 40.000 e Pagamento Acumulado 63.000, encerra em 16/09',
          (o5['balance'], o5['payment'], o5['closing']) == (40000.0, 63000.0, '2026-09-16'), o5)
    check('as páginas: 1 ATHENA-NDF, 2 e 3 PYRAMID, 4 e 5 ATHENA-FXO',
          [o['page'] for o in (o1, o2, o3, o4, o5)] == ['athena-ndf', 'pyramid', 'pyramid', 'athena-fxo', 'athena-fxo'])
    check('o Evento no vocabulário da equipe', (D.row_of(o2)['Event'], D.row_of(o5)['Event'])
          == ('Premium Payment', 'Settlement (Exercise)'), (D.row_of(o2)['Event'], D.row_of(o5)['Event']))
    check('Titular Prêmio YES/NO na tela', (D.row_of(o2)['Premium Holder'], D.row_of(o3)['Premium Holder']) == ('NO', 'YES'))

    # prêmio recebido E vencimento no MESMO mês: o prêmio vai em Total Crédito e no Saldo
    o6 = D.finish(list(D.aggregate([
        ev('2026-09-02', ['PREMIUM'], 1000.0, b3_id='OPC6', product='OPTION', lob='CEM'),
        ev('2026-09-29', ['EXERCISE'], -300.0, b3_id='OPC6', product='OPTION', lob='CEM'),
        ev('2026-09-29', ['EXPIRY'], None, source='exp', b3_id='OPC6', product='OPTION', lob='CEM',
           premium=1000.0, holder=False)]).values())[0])
    check('prêmio recebido e vencimento no mesmo mês: Crédito E Saldo; a expiração some ao lado do exercício',
          (o6['tot_credit'], o6['balance'], o6['payment'], o6['kinds']) == (1000.0, 1000.0, 300.0, ['PREMIUM', 'EXERCISE']), o6)
    o7 = D.finish(list(D.aggregate([ev('2026-09-10', ['UNWIND'], -10.0, b3_id='U1', product='NDF', closes=None)]).values())[0])
    check('recompra sem saber se é total: sem encerramento, marcada', o7['closing'] == '' and o7['unwind_unknown'])
    o8 = D.finish(list(D.aggregate([ev('2026-09-10', ['PREMIUM', 'MATURITY'], -10.0, b3_id='M1', product='OPTION')]).values())[0])
    check('prêmio e liquidação no mesmo caixa: vai como liquidação, marcado',
          o8['mixed'] and o8['tot_debit'] == 0.0 and o8['payment'] == 10.0 and o8['closing'] == '2026-09-10')
    o9 = D.finish(list(D.aggregate([ev('2026-09-10', ['MATURITY'], -100.0, source='ndf', b3_value=-104.0, b3_id='T1',
                                       product='NDF'),
                                    ev('2026-09-11', ['MATURITY'], -100.0, b3_value=-121.0, b3_id='T2', product='NDF',
                                       lob='COMMODITIES')]).values())[0])
    check('Interno × B3 pela tolerância da tela de origem (NDF Summary 5,00)',
          o9['difference'] == 4.0 and o9['b3_check'] == 'OK', o9)

    print('== 4. o arquivo ==')
    exemplo_hdr = ('num_ente_declarante;cnpjdeclarante;num_ente_declarado;declarado_ni;anomescaixa;conta_tp;'
                   'conta_subtp;conta_tpnum;conta_agencia;conta_num;conta_reportpais;conta_notitulares;'
                   'conta_tprelacdecla;conta_dtencerr;fl_primeiro_titular;balanco_totcred;balanco_totdeb;'
                   'balanco_totcreditu;balanco_totdebitu;balanco_vlrultdia;pag_tp;pag_totpgacum;cambio_totcomp;'
                   'cambio_totvend;cambio_tottransf;fundo_giin;fundo_cnpj;inter_giin;inter_ni;prop_ni;conta_dtabertu')
    check('o cabeçalho é o do exemplo', ';'.join(D.HEADER) == exemplo_hdr)
    o = D.finish({'key': 'k', 'le': 'JPM', 'b3_id': '26C04666450', 'taxid': '05.592.116/0001-80',
                  'payment': 22256669.26, 'closing': '', 'cgd_date': '2015-06-03', 'sources': []})
    linha = ';'.join(D.file_record(o, {'ente': '39', 'cnpj': '33172537000198'}, '202609'))
    # o exemplo: 39;33172537000198;22244;…;26C04666450;BR;;1;… — os dois "não preencher" vão vazios
    esperado = '39;33172537000198;;05592116000180;202609;2;203;OECD605;;26C04666450;;;1;;S;0;0;;;0;FATCA504;22256669,26;;;;;;;;;03/06/2015'
    check('a linha do exemplo, byte a byte', linha == esperado, linha)
    o = D.finish({'key': 'k', 'le': 'JPM', 'b3_id': 'X', 'taxid': '1', 'tot_credit': 81192.5, 'closing': '2026-09-16',
                  'premium': 50000, 'holder': False, 'sources': []})
    r = D.file_record(o, {'ente': '39', 'cnpj': '1'}, '202609')
    check('sem pagamento: pag_tp 999 e o valor 0; encerramento dd/mm/aaaa; vírgula decimal',
          (r[13], r[15], r[19], r[20], r[21]) == ('16/09/2026', '81192,50', '50000,00', '999', '0'), r)
    check('o arquivo termina em CRLF', D.file_text([['a', 'b']]) == ';'.join(D.HEADER) + '\r\na;b\r\n')


# ── Ponta a ponta ───────────────────────────────────────────────────────────
NDF, OPS, CLOSE = {}, {}, {}


def _ndf(cpty, s, athena, b3, legal='BANCO J.P MORGAN S.A', b3v=None, **kw):
    r = {'counterparty': cpty, 'legal': legal, 'athena': athena, 'b3': b3, 'settle_type': 'MATURITY',
         'trade_date': '05/08/2026', 'maturity': kw.pop('maturity', ''), 'settlement': s,
         'b3_value': s if b3v is None else b3v, 'taxid': kw.pop('taxid', '')}
    r.update(kw)
    return r


def _op(product, lob, st, iid, b3, cpty, s, legal='BANCO J.P MORGAN S.A', **kw):
    r = {'product': product, 'lob': lob, 'settle_type': st, 'internal_id': iid, 'id_b3': b3,
         'counterparty': cpty, '_settle_n': s, '_b3_n': kw.pop('b3n', s), '_legal': legal}
    r.update(kw)
    return r


def _pos_row(cols, **v):
    return [v.get(c, '') for c in cols]


def secao_api():
    print('== 5. ponta a ponta ==')
    from apps import create_app
    from apps.config import Config, DebugConfig
    app = create_app(DebugConfig)
    from apps.pages import routes as R
    from apps.pages.features.efinanceira import commands as C, domain as D, queries as Q
    from apps.pages.features.efinanceira.infra import store

    check('a tolerância de cada fonte é a da tela', D.TOL_BY_SOURCE == {'ndf': R._NDFSUM_TOL, 'ops': R._OPS_RECON_TOL})

    R._br_now = lambda: datetime(2026, 10, 5, 10, 0)
    R._pcx_is_bizday = lambda d: d.weekday() < 5
    share = tempfile.mkdtemp(prefix='otc-efin-share-')
    C.ROOT = share

    d15, d16, d28 = date(2026, 9, 15), date(2026, 9, 16), date(2026, 9, 28)
    NDF[d15] = [
        _ndf('GE CELMA LTDA', -16395.26, 'D5VL-2L2V0F', '26J02791770', legal='JPMORGAN CHASE BANK, N.A.',
             maturity='15/09/2026', taxid='33.435.231/0001-87'),
        # intragrupo: o Banco do outro lado da MGT
        _ndf('BANCO J.P MORGAN S.A', -500.0, 'INTRA-1', '26J0INTRA01', legal='JPMORGAN CHASE BANK, N.A.'),
    ]
    NDF[date(2026, 9, 10)] = [_ndf('CLIENTE U SA', 700.0, 'UNW-P', '26J0UNW0001', unwind=True, taxid='44.444.444/0001-44')]
    NDF[date(2026, 9, 11)] = [_ndf('CLIENTE U SA', -900.0, 'UNW-T', '26J0UNW0002', unwind=True, taxid='44.444.444/0001-44')]
    CLOSE[date(2026, 9, 10)] = {'26J0UNW0001': False}
    CLOSE[date(2026, 9, 11)] = {'26J0UNW0002': True}
    OPS[d28] = [
        _op('SWAP', 'EDG', 'Premium', '758662', '26J08689634', 'BANCO SAFRA S.A', 81192.50,
            _trade_date=date(2026, 9, 27), _maturity=date(2031, 10, 28)),
        _op('SWAP', 'EDG', 'Premium', '758662', '26J08689635', 'ATACAMA', -81192.50, b3n=-81150.0,
            _trade_date=date(2026, 9, 27), _maturity=date(2031, 10, 28)),
    ]
    OPS[d16] = [
        _op('OPTION', 'MOEDA', 'Exercise', 'XPTO-5', 'OPC0000005', 'XPTO FX SA', -63000.0, legal='JPMORGANBM',
            _party_account='73760.00-9', _trade_date='10/10/2021', _maturity='16/09/2026', _premium='40,000.00',
            _premium_date='10/10/2021', _premium_side='LANCADOR', _taxid='55.555.555/0001-55'),
    ]
    OPS[date(2026, 9, 10)] = [
        _op('SWAP', 'CEM', 'Cashflow', 'K-1', '26S0000001', 'CLIENTE K SA', -1000.0,
            _maturity=date(2028, 1, 1), _taxid='66.666.666/0001-66'),
        _op('SWAP', '', 'Cashflow', 'K-2', '26S0000002', 'CLIENTE K SA', 20.0, _taxid='66.666.666/0001-66'),
        # a visão do fundo (o Lawton do nosso lado) não é declarante
        _op('NDF COMMODITIES', 'COMMODITIES', 'Maturity', 'L-1', '26T0LAWTON1', 'CLIENTE L SA', -5.0,
            legal='LAWTON MULTIMERCADO EXCLUSIVO'),
    ]
    OPS[date(2026, 9, 30)] = [
        _op('SWAP', 'CEMHYB', 'Cashflow', 'H-1', '26S0000003', 'CLIENTE K SA', -2000.0,
            _maturity=date(2026, 9, 30), _taxid='66.666.666/0001-66'),
    ]
    cols = list(R._LPOPT_COLUMNS)
    POS = {'columns': cols, 'rows': [
        _pos_row(cols, **{'Código IF': 'OPC0000004', 'Combinação de operações': 'XPTO-4', 'Posição da Parte': 'LANCADOR',
                          'Parte (Conta)': '73760.00-9', 'Parte (Nome simplificado)': 'JPMORGANBM',
                          'Contraparte (Conta)': '12345.00-1', 'CPF/CNPJ Cliente Contraparte': 'XPTO COMMODITIES SA',
                          'Data Início': '10/10/2021', 'Data Vencimento': '16/09/2026',
                          'Classe do ativo subjacente': 'COMMODITIES', 'Valor financeiro total do prêmio': '50,000.00',
                          'Data de Liquidação do Prêmio': '10/10/2021'}),
        # a exercida também está na posição do dia: a expiração some ao lado do exercício
        _pos_row(cols, **{'Código IF': 'OPC0000005', 'Combinação de operações': 'XPTO-5', 'Posição da Parte': 'LANCADOR',
                          'Parte (Conta)': '73760.00-9', 'Contraparte (Conta)': '12345.00-2',
                          'CPF/CNPJ Cliente Contraparte': 'XPTO FX SA', 'Data Vencimento': '16/09/2026',
                          'Classe do ativo subjacente': 'TAXA DE CAMBIO', 'Valor financeiro total do prêmio': '40,000.00'}),
        # o banco TITULAR, vencida sem exercício: encerra, sem saldo
        _pos_row(cols, **{'Código IF': 'OPC0000006', 'Combinação de operações': 'XPTO-6', 'Posição da Parte': 'TITULAR',
                          'Parte (Conta)': '73760.00-9', 'Contraparte (Conta)': '12345.00-3',
                          'CPF/CNPJ Cliente Contraparte': '77.777.777/0001-77', 'Data Vencimento': '16/09/2026',
                          'Classe do ativo subjacente': 'COMMODITIES', 'Valor financeiro total do prêmio': '9,000.00'}),
    ]}
    R._ndfsum_collect = lambda ref: {'email_trades': [dict(t) for t in NDF.get(ref.date(), [])]}
    R._ops_trade_rows = lambda d: [dict(t) for t in OPS.get(d, [])]
    R._lpopt_collect = lambda ref, exact=False: POS
    R._unwind_engine = lambda: types.SimpleNamespace(encerramentos=lambda d: dict(CLOSE.get(d, {})))
    Q._refdata_index = lambda: {'BANCOSAFRASA': '58.160.789/0001-28', 'ATACAMA': '11.111.111/0001-11',
                                'XPTOCOMMODITIESSA': '22.222.222/0001-22'}

    # a data do CGD: o Tracking Docs de verdade, com o load_all de mentira
    from apps.pages import cgd_docs
    cgd_docs.load_all = lambda path=None: [
        {'Doc Type': 'CGD', 'Status': 'Active', 'Legal Entity': 'MGT', 'CNPJ': '33.435.231/0001-87',
         'Signature Date': '03/06/2015'},
        {'Doc Type': 'CGD', 'Status': 'Active', 'Legal Entity': 'JPM', 'CNPJ': '11.111.111/0001-11; 22.222.222/0001-22',
         'Signature Date': '', 'Emissão': '01/02/2019'},
        {'Doc Type': 'CGD', 'Status': 'Active', 'Legal Entity': 'JPM', 'CNPJ': '22.222.222/0001-22',
         'Signature Date': '05/05/2020'},
        {'Doc Type': 'CGD', 'Status': 'Cancelled', 'Legal Entity': 'JPM', 'CNPJ': '58.160.789/0001-28',
         'Signature Date': '01/01/2010'},
        {'Doc Type': 'CSA', 'Status': 'Active', 'Legal Entity': 'JPM', 'CNPJ': '58.160.789/0001-28',
         'Signature Date': '01/01/2011'},
        {'Doc Type': 'CGD', 'Status': 'Active', 'Legal Entity': 'JPM',
         'CNPJ': '44.444.444/0001-44;55.555.555/0001-55;66.666.666/0001-66;77.777.777/0001-77',
         'Signature Date': '10/10/2018'},
    ]
    idx = Q.cgd_index()
    check('CGD: a assinatura, senão a emissão; o mais antigo; cancelado e CSA de fora',
          (Q.cgd_of(idx, 'MGT', '33435231000187'), Q.cgd_of(idx, 'JPM', '22.222.222/0001-22'),
           Q.cgd_of(idx, 'JPM', '58.160.789/0001-28')) == ('2015-06-03', '2019-02-01', ''),
          (Q.cgd_of(idx, 'MGT', '33435231000187'), Q.cgd_of(idx, 'JPM', '22.222.222/0001-22')))

    cl = app.test_client()

    def sessao(sid):
        with cl.session_transaction() as ss:
            ss['authenticated'] = True
            ss['user_sid'] = sid
            ss['user_name'] = 'Teste ' + sid
            ss['session_ip'] = '127.0.0.1'
    sessao('A000001')

    for p in D.PAGE_ORDER:
        pg = cl.get('/regulatory/e-financeira/' + p)
        check('página %s: 200, nomeia o export' % p, pg.status_code == 200
              and ('data-export-name="E-Financeira %s"' % D.PAGES[p]['label']) in pg.data.decode('utf-8'))
    check('página que não existe: 404', cl.get('/regulatory/e-financeira/xpto').status_code == 404)
    html = cl.get('/regulatory/e-financeira/kapital').data.decode('utf-8')
    check('a data nasce no último dia do mês anterior', 'autocomplete="off" value="2026-09-30"' in html)

    d0 = cl.get('/api/efinanceira/kapital/data?date=2026-09-15').get_json()
    check('mês vazio responde e avisa os dias sem import', d0['success'] and d0['rows'] == []
          and any(w['code'] == 'missing_days' for w in d0['warnings']), d0.get('error'))

    j = cl.post('/api/efinanceira/import-settlements', json={'date': '2026-09-15'}).get_json()
    dias = sum(1 for i in range(30) if date(2026, 9, 1 + i).weekday() < 5)
    check('Import Settlements: o trabalho do MÊS em segundo plano', j['success'] and j['job']['state'] == 'running'
          and j['job']['total'] == dias and j['job']['key'] == '202609', j)
    j2 = cl.post('/api/efinanceira/import-settlements', json={'date': '2026-09-02'}).get_json()
    check('...o segundo clique devolve o MESMO trabalho', j2['job']['started'] == j['job']['started'])
    limite = time.time() + 90
    while time.time() < limite:
        job = cl.get('/api/efinanceira/import-status?date=2026-09-15').get_json()['job']
        if job['state'] == 'done':
            break
        time.sleep(0.1)
    check('o trabalho termina com todos os dias e sem falha', job['state'] == 'done' and job['done'] == dias
          and not job['failed'] and not job['error'], job)

    def pagina(p):
        r = cl.get('/api/efinanceira/%s/data?date=2026-09-15' % p).get_json()
        return r, {x['B3 ID']: x for x in r['rows']}
    r, ndf = pagina('athena-ndf')
    check('ATHENA-NDF: o NDF da MGT e as duas recompras; o intragrupo de fora',
          sorted(ndf) == ['26J02791770', '26J0UNW0001', '26J0UNW0002'], sorted(ndf))
    check('...e avisa o intragrupo', any(w['code'] == 'intragroup' for w in r['warnings']))
    check('...e a entidade fora do cadastro (o Lawton)', any(w['code'] == 'not_declarant'
                                                            and 'LAWTON' in w['text'] for w in r['warnings']),
          r['warnings'])
    g = ndf['26J02791770']
    check('GE CELMA: LE MGT, Pagamento 16.395,26, encerramento e data do CGD',
          (g['LE'], g['Accumulated Payment'], g['Closing Date'], g['CGD Date'], g['Settlement Date'])
          == ('MGT', 16395.26, '15/09/2026', '03/06/2015', '15/09/2026'), g)
    check('recompra parcial não encerra; a total encerra na data dela',
          ndf['26J0UNW0001']['Closing Date'] == '' and ndf['26J0UNW0002']['Closing Date'] == '11/09/2026')

    r, py = pagina('pyramid')
    check('PYRAMID: os dois swaps da EDG', sorted(py) == ['26J08689634', '26J08689635'], sorted(py))
    sf, at = py['26J08689634'], py['26J08689635']
    check('Banco Safra: Total Crédito, titular NO, sem CGD (o cancelado não vale) → incompleta',
          sf['Total Credit'] == 81192.50 and sf['Premium Holder'] == 'NO' and sf['missing'] == ['CGD Date'], sf)
    check('Atacama: Total Débito e Pagamento, titular YES, Interno × B3 a conferir (42,50 > 20)',
          (at['Total Debit'], at['Accumulated Payment'], at['Premium Holder'], at['Difference'], at['b3_check'])
          == (81192.50, 81192.50, 'YES', -42.5, 'Check'), at)
    check('cards: 2 contas, 1 incompleta, 1 a conferir, 1 com pagamento',
          (r['counts']['total'], r['counts']['missing'], r['counts']['b3_check'], r['counts']['payments'])
          == (2, 1, 1, 1), r['counts'])

    r, fx = pagina('athena-fxo')
    check('ATHENA-FXO: a de commodities que venceu, a exercida e a do banco titular',
          sorted(fx) == ['OPC0000004', 'OPC0000005', 'OPC0000006'], sorted(fx))
    o4, o5, o6 = fx['OPC0000004'], fx['OPC0000005'], fx['OPC0000006']
    check('expirada sem caixa: Saldo 50.000, LE pela CONTA (o apelido JPMORGANBM), contraparte pela posição',
          (o4['Balance'], o4['Closing Date'], o4['LE'], o4['Counterparty'], o4['Tax ID'], o4['LOB'])
          == (50000.0, '16/09/2026', 'JPM', 'XPTO COMMODITIES SA', '22.222.222/0001-22', 'COMMODITIES'), o4)
    check('exercida: Saldo 40.000 e Pagamento 63.000; a expiração não duplica',
          (o5['Balance'], o5['Accumulated Payment'], o5['Event'], o5['LOB'])
          == (40000.0, 63000.0, 'Settlement (Exercise)', 'CEM'), o5)
    check('banco titular, vencida: encerra sem saldo; o CNPJ vem da posição',
          (o6['Balance'], o6['Closing Date'], o6['Tax ID'], o6['Premium Holder']) == (0.0, '16/09/2026',
                                                                                     '77.777.777/0001-77', 'YES'), o6)

    r, kp = pagina('kapital')
    check('KAPITAL: os swaps CEM/CEMHYB e o sem LOB', sorted(kp) == ['26S0000001', '26S0000002', '26S0000003'], sorted(kp))
    check('fluxo no meio da vida: pagamento sem encerramento', (kp['26S0000001']['Accumulated Payment'],
                                                                kp['26S0000001']['Closing Date']) == (1000.0, ''))
    check('fluxo do vencimento encerra', kp['26S0000003']['Closing Date'] == '30/09/2026')
    check('swap sem LOB avisa', any(w['code'] == 'no_lob' for w in r['warnings']))
    r, _fx = pagina('athena-fxo')
    check('cada página avisa só o que saiu DELA (o intragrupo e o Lawton são do NDF)',
          not any(w['code'] in ('intragroup', 'not_declarant') for w in r['warnings']), r['warnings'])

    print('== 5b. o arquivo, a correção e o 4-olhos ==')
    nada = cl.post('/api/efinanceira/pyramid/generate', json={'date': '2026-09-15'})
    check('arquivo com linha incompleta: recusa dizendo qual e o que falta', nada.status_code == 400
          and nada.get_json()['error_code'] == 'file_missing' and '26J08689634 (CGD Date)' in nada.get_json()['error'],
          nada.get_json())
    e = cl.post('/api/efinanceira/pyramid/edit', json={'date': '2026-09-15', 'items': [
        {'key': sf['key'], 'changes': {'CGD Date': '2012-04-02'}}]}).get_json()
    sf2 = {x['B3 ID']: x for x in e['rows']}['26J08689634']
    check('Edit: a data do CGD corrigida, a linha Pending, completa', e['success'] and sf2['Status'] == 'Pending'
          and sf2['CGD Date'] == '02/04/2012' and sf2['missing'] == [] and sf2['edited'] == ['CGD Date'], sf2)
    ruim = cl.post('/api/efinanceira/pyramid/edit', json={'date': '2026-09-15', 'items': [
        {'key': sf['key'], 'changes': {'Total Credit': 'abc'}}]})
    check('Edit com número inválido: 400 por código', ruim.status_code == 400
          and ruim.get_json()['error_code'] == 'edit_bad_number')
    sumiu = cl.post('/api/efinanceira/pyramid/edit', json={'date': '2026-09-15', 'items': [
        {'key': 'JPM|NADA', 'changes': {'CGD Date': '2012-04-02'}}]})
    check('linha que não existe: 409', sumiu.status_code == 409)
    pend = cl.post('/api/efinanceira/pyramid/generate', json={'date': '2026-09-15'})
    check('arquivo com correção pendente: recusa', pend.status_code == 400
          and pend.get_json()['error_code'] == 'file_pending', pend.get_json())
    Config.FOUR_EYES = True
    try:
        own = cl.post('/api/efinanceira/pyramid/approve', json={'date': '2026-09-15', 'items': [{'key': sf['key']}]})
        check('quem editou não confirma (403)', own.status_code == 403 and own.get_json()['error_code'] == 'approve_own')
        sessao('B000002')
        ok = cl.post('/api/efinanceira/pyramid/approve', json={'date': '2026-09-15', 'items': [{'key': sf['key']}]}).get_json()
        check('outro usuário confirma', ok['success'] and {x['B3 ID']: x for x in ok['rows']}['26J08689634']['Status']
              == 'Approved', ok.get('error'))
    finally:
        Config.FOUR_EYES = False
    arq = cl.post('/api/efinanceira/pyramid/generate', json={'date': '2026-09-15'})
    corpo = arq.data.decode('cp1252')
    caminho = os.path.join(share, '2026', '09. September', 'PYRAMID_202609.csv')
    check('arquivo: 200, o nome do mês, duas contas', arq.status_code == 200
          and arq.headers.get('X-EFIN-Name') == 'PYRAMID_202609.csv' and arq.headers.get('X-EFIN-Count') == '2',
          (arq.status_code, corpo[:300]))
    check('...gravado no share em AAAA\\MM. Month', os.path.isfile(caminho)
          and open(caminho, 'rb').read() == arq.data and arq.headers.get('X-EFIN-Path') == caminho)
    linhas = corpo.split('\r\n')
    check('...com o cabeçalho e as duas linhas, CRLF', linhas[0] == ';'.join(D.HEADER) and len(linhas) == 4
          and linhas[-1] == '', linhas)
    safra = [l for l in linhas if '26J08689634' in l][0].split(';')
    check('...a linha do Banco Safra: declarante JPM, CNPJ, crédito, 999, CGD',
          (safra[0], safra[1], safra[3], safra[4], safra[9], safra[15], safra[16], safra[19], safra[20],
           safra[21], safra[30]) == ('39', '33172537000198', '58160789000128', '202609', '26J08689634',
                                     '81192,50', '0', '0', '999', '0', '02/04/2012'), safra)
    r, py = pagina('pyramid')
    check('depois do arquivo, as linhas dele ficam Generated', {x['Status'] for x in r['rows']} == {'Generated'}
          and r['last_file']['name'] == 'PYRAMID_202609.csv' and r['last_file']['n'] == 2, r['last_file'])

    dl = cl.post('/api/efinanceira/athena-ndf/delete', json={'date': '2026-09-15', 'items': [
        {'key': ndf['26J0UNW0001']['key']}]}).get_json()
    check('Delete: a conta sai do mês', dl['success'] and '26J0UNW0001' not in {x['B3 ID'] for x in dl['rows']})
    C.import_settlements(date(2026, 9, 15), workers=1, contexto=lambda: app.test_request_context('/'))
    r, ndf2 = pagina('athena-ndf')
    check('...e um novo Import não a traz de volta', '26J0UNW0001' not in ndf2 and '26J0UNW0002' in ndf2)

    sem = cl.post('/api/efinanceira/kapital/add', json={'date': '2026-09-15', 'items': [{'fields': {'LE': 'JPM'}}]})
    check('Add Row sem o obrigatório: 400 por código', sem.status_code == 400
          and sem.get_json()['error_code'] == 'add_missing')
    ad = cl.post('/api/efinanceira/kapital/add', json={'date': '2026-09-15', 'items': [{'fields': {
        'LE': 'JPM', 'B3 ID': '26s0manual1', 'Counterparty': 'CLIENTE M SA', 'Tax ID': '88.888.888/0001-88',
        'Product': 'SWAP', 'LOB': 'CEM', 'Accumulated Payment': '1.234,56', 'Closing Date': '2026-09-20',
        'CGD Date': '2019-01-02'}}]}).get_json()
    m = {x['B3 ID']: x for x in ad['rows']}.get('26S0MANUAL1') or {}
    check('Add Row: a conta entra Pending, com o pagamento digitado e o 999 virando FATCA504',
          ad['success'] and m.get('Status') == 'Pending' and m.get('Accumulated Payment') == 1234.56
          and m.get('PAG_TP') == 'FATCA504' and m.get('Event') == 'Manual' and m.get('missing') == [], m)
    doc = store.load('202609')
    check('o armazém do mês guarda as três fontes por dia', set(doc['days']['2026-09-16']) == {'ndf', 'ops', 'exp'})


def secao_tela():
    print('== 6. menu, cadastro, ganchos, sino e traduções ==')
    nav = open(os.path.join(ROOT, 'apps', 'templates', 'partials', 'sidenav.html'), encoding='utf-8').read()
    for p in ('kapital', 'athena-ndf', 'athena-fxo', 'pyramid'):
        check('o menu tem a página %s' % p, 'href="/regulatory/e-financeira/%s"' % p in nav)
    mp = open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'mapping.html'), encoding='utf-8').read()
    check('/mapping tem a aba efin-declarant', "key: 'efin-declarant'" in mp)
    from apps.pages import routes as R
    seed = {r['LE']: (r['ENTE'], r['CNPJ']) for r in R._MAPPING_DEFS['efin-declarant']['seed']}
    check('declarantes da equipe: JPM 39 e MGT 1315', seed == {'JPM': ('39', '33172537000198'),
                                                              'MGT': ('1315', '46518205000164')}, seed)
    rs = open(os.path.join(ROOT, 'apps', 'pages', 'routes.py'), encoding='utf-8').read()
    st = open(os.path.join(ROOT, 'apps', 'pages', 'platform', 'settlement.py'), encoding='utf-8').read()
    check('o NDF Summary leva o vencimento e o valor B3 no email_trades',
          "'maturity': settle_date," in rs and "'b3_value': b3_n," in rs)
    check('a opção e o termo de mercadoria levam prêmio, vencimento e conta da parte',
          rs.count("'party_account': _lcell(lrow,") == 2 and "'position_side': _lcell(lrow, 'Posição da Parte')" in rs)
    check('o Trade Level passa adiante (opção, termo e o vencimento do swap)',
          st.count("'_premium_side':") == 2 and "'_maturity': venc," in st)
    from apps.pages.platform import notifications as N
    for p in ('KAPITAL', 'ATHENA-NDF', 'ATHENA-FXO', 'PYRAMID'):
        check('o sino de %s leva à página' % p, N._NOTIF_PAGE_URL.get('E-Financeira ' + p)
              == '/regulatory/e-financeira/' + p.lower())
    tela = open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'efinanceira.html'), encoding='utf-8').read()
    chaves = {k for k in re.findall(r'data-lang="([^"]+)"', tela) if '{' not in k} | set(
        re.findall(r"'lang': '([^']+)'", tela)) | {'map-tab-efin-declarant'}
    for lg in ('en', 'br', 'es'):
        tr = json.load(io.open(os.path.join(ROOT, 'apps', 'static', 'data', 'translations', lg + '.json'),
                               encoding='utf-8'))
        falta = sorted(k for k in chaves if k not in tr)
        check('traduções %s completas' % lg, not falta, falta)
    # todo aviso e erro que o servidor manda por código tem a frase nas três línguas
    from apps.pages.features.efinanceira import commands as C, domain as D, queries as Q
    fonte = open(Q.__file__, encoding='utf-8').read() + open(C.__file__, encoding='utf-8').read() + \
        open(D.__file__, encoding='utf-8').read()
    avisos = set(re.findall(r"aviso\('(\w+)'", fonte)) | set(re.findall(r"\(\s*'(\w+)',\s*'\w+',\s*'\{n\}", fonte))
    erros = set(re.findall(r"EfinError\('(\w+)'", fonte))
    fim = {'en': '        br: {', 'br': '        es: {', 'es': '\n    };'}
    for lg in ('en', 'br', 'es'):
        ini = '        %s: {' % lg
        bloco = tela.split(ini, 1)[1].split(fim[lg], 1)[0] if ini in tela else ''
        falta = sorted(['w_' + a for a in avisos if ('w_' + a + ':') not in bloco] +
                       ['e_' + e for e in erros if ('e_' + e + ':') not in bloco])
        check('_TRANS %s diz todo aviso e erro' % lg, bloco and not falta, falta)


def main():
    secao_dominio()
    secao_api()
    secao_tela()
    print()
    if FALHAS:
        print('FALHOU (%d):' % len(FALHAS))
        for f in FALHAS:
            print('  -', f)
        sys.exit(1)
    print('TUDO OK')


if __name__ == '__main__':
    main()
