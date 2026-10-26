# -*- coding: utf-8 -*-
"""check_wht.py — Regulatory › WHT (Withholding Tax): o IR do decêndio, OTC × HUB.

  1. o decêndio: 01–10, 11–20, 21–fim; o recolhimento no 1º dia útil depois;
  2. a QUEBRA do piso de R$ 1,00 do mês, nos três cenários da equipe
     (0,60 + 0,35 + 0,10): tudo num decêndio; as duas primeiras num e a que
     passa do piso no seguinte; a primeira num e as outras duas no seguinte —
     e o mês que não alcança o piso, e o swap, que não tem piso;
  3. o código pelo cadastro `wht-codes` (seed): produto × tributação ×
     residência, LOB e evento como coringa, o mais específico vence;
  4. o documento de 18 caracteres e o casamento com o Docto do HUB (o id
     cortado do sistema e o prefixo do arquivo do OTC Tracker);
  5. o arquivo que vai ao HUB, BYTE A BYTE com o exemplo da planilha auxiliar
     (as quatro linhas da primeira operação: 60/233/84/85 posições);
  6. o relatório do HUB ("Posição de Tributos"): blocos por empresa, a coluna
     do nome sem rótulo, número e CNPJ gravados como número;
  7. ponta a ponta no armazém real (tmp): Import Settlements (NDF Summary e
     Other Products de mentira), Import HUB com dois arquivos (o 5557 num, o
     5273 noutro), os quatro status com o Partial dizendo os campos, o resumo
     por código, o arquivo do HUB com o que ele não tem, a reimportação que
     substitui, o fluxo vindo do NDF Summary e a coleta vazia que não cria dia;
  8. menu, cadastros na tela /mapping e as três traduções.

Roda em tmp: DATA_DIR/DATABASE_DIR próprios, fontes de liquidação stub.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_wht.py
"""
import io
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
RAIZ = tempfile.mkdtemp(prefix='otc-wht-')
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


def _bizday(d):
    return d.weekday() < 5


def secao_dominio():
    from apps.pages.features.wht import domain as D

    print('== 1. o decêndio ==')
    check('dia 10 é o 1º, 11 o 2º, 21 o 3º',
          [D.decendio_n(date(2026, 10, x)) for x in (1, 10, 11, 20, 21, 31)] == [1, 1, 2, 2, 3, 3])
    check('limites do 3º decêndio de fevereiro', D.decendio_bounds(2026, 2, 3) == (date(2026, 2, 21), date(2026, 2, 28)))
    check('recolhimento: 1º dia útil depois (20/10 terça → 21/10)',
          D.payment_date(date(2026, 10, 20), _bizday) == date(2026, 10, 21))
    check('recolhimento pula o fim de semana (10/10 sábado → 12/10)',
          D.payment_date(date(2026, 10, 10), _bizday) == date(2026, 10, 12))

    print('== 2. a quebra do piso de R$ 1,00 ==')

    def cen(*ops):
        rows = [{'id': i, 'bucket': 'A', 'date': d, 'devido': v, 'floor': True, 'seq': i}
                for i, (d, v) in enumerate(ops)]
        return [D.allocate(rows)[i] for i in range(len(ops))]
    c1 = cen((date(2026, 10, 2), .60), (date(2026, 10, 5), .35), (date(2026, 10, 9), .10))
    check('1º cenário: tudo no 1º decêndio → cada uma com o seu imposto', c1 == [.60, .35, .10], c1)
    c2 = cen((date(2026, 10, 2), .60), (date(2026, 10, 5), .35), (date(2026, 10, 15), .10))
    check('2º cenário: as duas do 1º zeradas, a do 2º com o total (1,05)', c2 == [0.0, 0.0, 1.05], c2)
    c3 = cen((date(2026, 10, 2), .60), (date(2026, 10, 11), .35), (date(2026, 10, 15), .10))
    check('3º cenário: a do 1º zerada; no 2º, 0,35 e 0,10 + 0,60 levados', c3 == [0.0, .35, .70], c3)
    c4 = cen((date(2026, 10, 2), .30), (date(2026, 10, 25), .40))
    check('mês que não alcança o piso: tudo zero', c4 == [0.0, 0.0], c4)
    c5 = cen((date(2026, 10, 2), .60), (date(2026, 10, 12), .50), (date(2026, 10, 22), .05))
    check('depois do piso, o decêndio seguinte informa o próprio imposto', c5 == [0.0, 1.10, .05], c5)
    sw = D.allocate([{'id': 'x', 'bucket': 'A', 'date': date(2026, 10, 2), 'devido': 0.37, 'floor': False}])
    check('swap (sem piso) informa o próprio imposto', sw == {'x': 0.37}, sw)
    dois = D.allocate([{'id': 1, 'bucket': 'A', 'date': date(2026, 10, 2), 'devido': .60, 'floor': True},
                       {'id': 2, 'bucket': 'B', 'date': date(2026, 10, 3), 'devido': .60, 'floor': True}])
    check('o piso é POR CONTRAPARTE', dois == {1: 0.0, 2: 0.0}, dois)

    print('== 3. o código pelo cadastro ==')
    from apps.pages import routes as R
    seed = R._MAPPING_DEFS['wht-codes']['seed']

    def cod(*a):
        r = D.resolve_code(seed, *a)
        return (r or {}).get('CODE'), (r or {}).get('TRIBUTO')
    check('NDF tributável residente', cod('NDF', '', 'MATURITY', True, True) == ('5557MT12050', '55571'))
    check('NDF isento', cod('NDF', '', 'MATURITY', False, True) == ('5557ME12050', '5557E'))
    check('NDF não residente → 5286', cod('NDF', '', '', True, False) == ('5286MT12050', '52861'))
    check('termo de mercadoria tributável', cod('NDF COMM', 'COMMODITIES', '', True, True) == ('5557PT12050', '55571'))
    check('opção de mercadoria isenta', cod('OPTION COMM', 'COMMODITIES', 'EXERCISE', False, True) == ('5557RE12050', '5557E'))
    check('swap tributável', cod('SWAP', 'CEM', 'CASHFLOW', True, True) == ('5273OT12046', '52731'))
    check('swap de COMMODITIES (LOB) vence o genérico', cod('SWAP', 'COMMODITIES', '', False, True) == ('5273QE12046', '5273E'))
    check('swap: o evento DIVIDEND vence o genérico', cod('SWAP', 'EDG', 'DIVIDEND', False, True) == ('5273OE12001', '5273E'))
    check('produto fora do cadastro → None', D.resolve_code(seed, 'COE', '', '', True, True) is None)
    check('piso só no 5557', {r['CODE']: r['MONTHLY FLOOR'] for r in seed}['5557NT12050'] == 'Yes'
          and {r['CODE']: r['MONTHLY FLOOR'] for r in seed}['5273OT12046'] == 'No')

    print('== 4. documento e casamento ==')
    check('documento com prefixo, 18 caracteres',
          D.doc_number('NDF', 'STP-3AL-JMZEK4-0-0') == 'NDF-STP-3AL-JMZEK4' and len(D.doc_number('NDF', 'X' * 40)) == 18)
    check('Docto com prefixo do arquivo casa com o id', D.doc_matches('SWP-270RI70427368', '', '270RI70427368'))
    check('Docto cortado pelo sistema casa com o id inteiro',
          D.doc_matches('STP-4T6-3LS149D-0-', '', 'STP-4T6-3LS149D-0-0'))
    check('...e não com o irmão da mesma família',
          not D.doc_matches('STP-4T6-3LS149D-0-', '', 'STP-4T6-3LS149D-1-0'))
    check('Docto do arquivo cortado casa pelo começo do id',
          D.doc_matches('NDF-STP-3AL-JMZEK4', '', 'STP-3AL-JMZEK4-0-0'))

    print('== 5. o arquivo do HUB, byte a byte com o exemplo ==')
    linhas = D.hub_file_lines([{'empresa': '00001', 'filial': '0001', 'cnpj': '04.885.503/0001-42',
                                'doc': 'SWP-270RI70427368', 'date': date(2026, 10, 20),
                                'code': '5273OT12046', 'gross': 8816844.15, 'ir': 0.0, 'rate': 0.0}],
                              date(2026, 10, 22))
    z = '0' * 17
    v = '00000000881684415'
    esperado = [
        '00001000104885503000142SWP-270RI70427368 201020265273OT12046',
        v + z * 6 + v + z * 2 + v + z * 2 + '0' * 12,
        '0' * 68 + ' ' * 8 + '22102026',
        '0' * 85,
    ]
    check('as quatro linhas da 1ª operação do exemplo', linhas == esperado,
          '\n'.join(repr(x) for x in linhas))
    check('larguras 60/233/84/85', [len(x) for x in linhas] == [60, 233, 84, 85], [len(x) for x in linhas])
    l2 = D.hub_file_lines([{'empresa': '1', 'filial': '1', 'cnpj': '1', 'doc': 'X', 'date': date(2026, 10, 1),
                            'code': 'C', 'gross': 100.0, 'ir': 15.0, 'rate': 15.0}], date(2026, 10, 2))[1]
    check('IRRF no campo k e alíquota no t', l2[4 * 17:5 * 17] == '00000000000001500' and l2[221:225] == '1500', l2)

    print('== 6. o relatório do HUB ==')
    rows = [['Easy-Way do Brasil - Consultores - EasyTributos Versão 6.20j', None, None],
            [None, 'Posição de Tributos'],
            ['Empresa: 00001 - Banco J.P. Morgan S.A.'],
            ['Contribuinte', None, 'Filial', 'Emissão', 'T.Oper.', 'Docto.', 'No.Aux.', 'Vlr. Lançado',
             'Rend.Tribut.', 'Tributo', 'Fato Ger.', 'Vcto.', 'Pagto.', 'Vlr.Tributo', 'NDocRec', 'Sis'],
            [5592116000180.0, 'LAWTON EXCLUSIV', '0001', '13/10/2026', '5273OT12046', 'SWP-0507060161188',
             None, '57.541.431,37', '57.541.431,37', '52731', '13/10/2026', '23/10/2026', None, None, None, '60'],
            ['07175725000160', 'WEG EQUIPAMENT', '0001', datetime(2026, 10, 13), '5557MT12050',
             'STP-3AL-JMZEK4-0-0', None, 632610.0, 632610.0, '55571', datetime(2026, 10, 13),
             '23/10/2026', '30/11/2026', 31.63, '00111298', '60'],
            ['Empresa: 00017 - JPMorgan Chase Bank'],
            ['Contribuinte', None, 'Filial', 'Emissão', 'T.Oper.', 'Docto.', 'No.Aux.', 'Vlr. Lançado',
             'Rend.Tribut.', 'Tributo', 'Fato Ger.', 'Vcto.', 'Pagto.', 'Vlr.Tributo', 'NDocRec', 'Sis'],
            ['33172537000198', 'BANCO J P MORGA', '0001', '15/10/2026', '5557ME12050', 'D5VL-2H3Z00',
             None, '803.439,00', '0,00', '5557E', '15/10/2026', '23/10/2026', '23/10/2026', None, None, '60'],
            ['Total', None, None]]
    recs, info = D.parse_hub_report(rows, 'hub.xls')
    check('três operações, duas empresas', len(recs) == 3 and info['empresas'] == ['00001', '00017'], (recs, info))
    check('CNPJ gravado como número volta com o zero', recs[0]['cnpj'] == '05592116000180', recs[0]['cnpj'])
    check('o nome é a coluna sem rótulo', recs[0]['name'] == 'LAWTON EXCLUSIV')
    check('valor BR e número de planilha', recs[0]['gross'] == 57541431.37 and recs[1]['gross'] == 632610.0)
    check('Fato Gerador como data (texto e datetime)',
          recs[0]['date'] == date(2026, 10, 13) and recs[1]['date'] == date(2026, 10, 13))
    check('Vlr.Tributo vazio é zero; preenchido é o valor', recs[0]['ir'] == 0.0 and recs[1]['ir'] == 31.63)
    check('a empresa de cada bloco', [r['empresa'] for r in recs] == ['00001', '00001', '00017'])


# ── 7. ponta a ponta ────────────────────────────────────────────────────────
def _ndf(cpty, s, athena, b3, taxid='', legal='BANCO J.P. MORGAN S.A.'):
    return {'counterparty': cpty, 'settlement': s, 'athena': athena, 'b3': b3, 'taxid': taxid,
            'legal': legal, 'settle_type': 'MATURITY'}


NDF = {
    date(2026, 10, 2): [_ndf('CLIENTE A SA', -12000.0, 'STP-AAA-0000001-0-0', '26J00000001', '11.111.111/0001-11')],
    date(2026, 10, 13): [_ndf('CLIENTE A SA', -7000.0, 'STP-AAA-0000002-0-0', '26J00000002', '11.111.111/0001-11'),
                         _ndf('CLIENTE A SA', 5000.0, 'STP-AAA-0000099-0-0', '26J00000099', '11.111.111/0001-11')],
    date(2026, 10, 14): [_ndf('CLIENTE C SA', -280978.51, 'STP-CCC-0000009-0-0', '26J00000009', '33.333.333/0001-33')],
    date(2026, 10, 15): [_ndf('CLIENTE A SA', -2000.0, 'STP-AAA-0000003-0-0', '26J00000003', '11.111.111/0001-11'),
                         _ndf('BANCO SAFRA S.A.', -50000.0, 'STP-BBB-0000004-0-0', '26J00000004', '58.160.789/0001-28')],
}
OPS = {
    date(2026, 10, 16): [
        {'product': 'SWAP', 'lob': 'CEM', 'settle_type': 'CASHFLOW', 'internal_id': '270RI70427368',
         'id_b3': '22J00000001', 'counterparty': 'CLIENTE D LTDA', '_settle_n': -8816844.15,
         '_tax_n': 1322526.62, '_legal': 'BANCO J.P. MORGAN S.A.'},
        {'product': 'TERMO', 'lob': 'COMMODITIES', 'settle_type': 'MATURITY', 'internal_id': '85101H-1OKXWV',
         'id_b3': '26J00000777', 'counterparty': 'LAWTONMULTIME', '_settle_n': -112610.32,
         '_tax_n': 0.0, '_legal': 'BANCO J.P. MORGAN S.A.'},
    ],
}

HEADER = ['Contribuinte', None, 'Filial', 'Emissão', 'T.Oper.', 'Docto.', 'No.Aux.', 'Vlr. Lançado',
          'Rend.Tribut.', 'Tributo', 'Fato Ger.', 'Vcto.', 'Pagto.', 'Vlr.Tributo', 'NDocRec', 'Sis']


def _xlsx(blocos):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['Easy-Way do Brasil - Consultores - EasyTributos Versão 6.20j'])
    for empresa, linhas in blocos:
        ws.append(['Empresa: %s' % empresa])
        ws.append(HEADER)
        for ln in linhas:
            ws.append(ln)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _hub(cnpj, nome, code, docto, bruto, trib, fato, ir):
    return [cnpj, nome, '0001', fato, code, docto, None, bruto, bruto, trib, fato, '23/10/2026', None, ir, None, '60']


def secao_api():
    print('== 7. ponta a ponta ==')
    from apps import create_app
    from apps.config import DebugConfig
    app = create_app(DebugConfig)
    from apps.pages import routes as R
    from apps.pages.features.wht import queries as Q
    from apps.pages.features.wht.infra import store

    R._br_now = lambda: datetime(2026, 10, 22, 10, 0)
    R._pcx_is_bizday = _bizday
    R._prev_anbima_bizday = lambda d: d - timedelta(days=1)
    chamadas = []

    def ndfsum(ref):
        chamadas.append(('ndf', ref.date()))
        return {'email_trades': [dict(t) for t in NDF.get(ref.date(), [])], 'trade': [], 'summary': []}

    def ops(d):
        chamadas.append(('ops', d))
        return [dict(t) for t in OPS.get(d, [])]
    R._ndfsum_collect = ndfsum
    R._ops_trade_rows = ops
    Q._refdata_index = lambda: {'CLIENTEDLTDA': '04.885.503/0001-42'}

    cl = app.test_client()
    with cl.session_transaction() as ss:
        ss['authenticated'] = True
        ss['user_sid'] = 'A000001'
        ss['user_name'] = 'Teste'
        ss['session_ip'] = '127.0.0.1'
        ss['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()

    pg = cl.get('/regulatory/wht')
    check('página 200 em /regulatory/wht', pg.status_code == 200, pg.status_code)
    html = pg.data.decode('utf-8')
    check('a tabela nomeia o export', 'data-export-name="WHT"' in html)

    d0 = cl.get('/api/wht/data?date=2026-10-20').get_json()
    check('decêndio vazio responde', d0['success'] and d0['rows'] == [] and d0['decendio']['n'] == 2, d0.get('error'))
    check('...e avisa os dias sem liquidação', any(w['code'] == 'missing_days' for w in d0['warnings']))
    check('recolhimento do 2º decêndio = 21/10', d0['decendio']['payment'] == '21/10/2026')

    r = cl.post('/api/wht/import-settlements', json={'date': '2026-10-20'}).get_json()
    check('Import Settlements', r['success'], r.get('error'))
    im = r['imported']
    check('recoleta os dias do decêndio e os dias do 1º que faltam',
          '2026-10-12' in im['days'] and '2026-10-20' in im['days'] and '2026-10-02' in im['days']
          and '2026-10-21' not in im['days'], im['days'])
    check('só as liquidações em que o banco PAGA (a positiva ficou de fora)', im['rows'] == 7, im)
    check('sem aviso de dia faltando depois do import', not any(w['code'] in ('missing_days', 'missing_prev')
                                                               for w in r['warnings']), r['warnings'])
    por_id = {x['Internal ID']: x for x in r['rows']}
    a2, a3 = por_id['STP-AAA-0000002-0-0'], por_id['STP-AAA-0000003-0-0']
    check('3º cenário de verdade: 0,35 e 0,10 + 0,60 do 1º decêndio',
          a2['OTC_IR'] == 0.35 and a3['OTC_IR'] == 0.70 and a3['Devido'] == 0.10, (a2['OTC_IR'], a3['OTC_IR']))
    check('o 1º decêndio não entra na tela do 2º', 'STP-AAA-0000001-0-0' not in por_id)
    check('código do isento (banco)', por_id['STP-BBB-0000004-0-0']['OTC_id'] == '5557ME12050')
    sw = por_id['270RI70427368']
    check('swap: imposto da tabela, código OT, sem piso',
          sw['OTC_IR'] == 1322526.62 and sw['OTC_id'] == '5273OT12046' and sw['Product'] == 'SWAP', sw)
    check('termo de mercadoria do Lawton: isento, código PE',
          por_id['85101H-1OKXWV']['OTC_id'] == '5557PE12050' and por_id['85101H-1OKXWV']['OTC_IR'] == 0.0)
    check('tudo Unmatched OTC antes do HUB', {x['status'] for x in r['rows']} == {'Unmatched OTC'})

    f5557 = _xlsx([('00001 - Banco J.P. Morgan S.A.', [
        _hub('11111111000111', 'CLIENTE A SA', '5557MT12050', 'STP-AAA-0000002-0-', 7000.0, '55571', '13/10/2026', 0.0),
        _hub('11111111000111', 'CLIENTE A SA', '5557MT12050', 'STP-AAA-0000003-0-', 2000.0, '55571', '15/10/2026', 1.05),
        _hub('33333333000133', 'CLIENTE C SA', '5557MT12050', 'STP-CCC-0000009-0-', 280978.51, '55571', '14/10/2026', 14.05),
        _hub('99999999000199', 'SO NO HUB SA', '5557MT12050', 'STP-ZZZ-9999999-0-', 1000.0, '55571', '16/10/2026', 0.05),
    ]), ('00017 - JPMorgan Chase Bank', [
        _hub('05592116000180', 'LAWTON EXCLUSIVO FIF', '5557PE12050', '85101H-1OKXWV', 112610.32, '5557E', '16/10/2026', 0.0),
    ])])
    f5273 = _xlsx([('00001 - Banco J.P. Morgan S.A.', [
        _hub('99999999000199', 'OUTRO SO NO HUB', '5273OT12046', 'SWP-0000000000001', 500.0, '52731', '19/10/2026', 75.0),
    ])])
    r = cl.post('/api/wht/hub-import', data={'files': [(io.BytesIO(f5557), 'hub_5557.xlsx'),
                                                       (io.BytesIO(f5273), 'hub_5273.xlsx')],
                                             'date': '2026-10-20'},
                content_type='multipart/form-data').get_json()
    check('Import HUB com dois arquivos', r['success'] and [f['rows'] for f in r['hub']['files']] == [5, 1], r.get('hub') or r)
    st = {x['Internal ID']: x for x in r['rows']}
    check('Matched (C)', st['STP-CCC-0000009-0-0']['status'] == 'Matched', st['STP-CCC-0000009-0-0']['Status'])
    check('Partial lista o campo: o HUB informou 0,00 na de 0,35',
          st['STP-AAA-0000002-0-0']['Status'] == 'Partial - Tax', st['STP-AAA-0000002-0-0']['Status'])
    check('...e 1,05 na que deveria ter 0,70', st['STP-AAA-0000003-0-0']['Status'] == 'Partial - Tax'
          and st['STP-AAA-0000003-0-0']['HUB_IR'] == 1.05)
    lw = st['85101H-1OKXWV']
    check('Partial do Lawton: contraparte (acrônimo × nome) e entidade (JPM × 00017)',
          lw['Status'] == 'Partial - Counterparty, Legal Entity' and lw['Check_IR'] is True
          and lw['Check_LE'] is False and lw['HUB_LE'] == 'MGT', lw['Status'])
    check('Unmatched OTC: o isento e o swap', st['STP-BBB-0000004-0-0']['status'] == 'Unmatched OTC'
          and st['270RI70427368']['status'] == 'Unmatched OTC')
    check('Unmatched HUB: as duas que o OTC não tem',
          sum(1 for x in r['rows'] if x['status'] == 'Unmatched HUB') == 2)
    check('o que pede ação vem primeiro', r['rows'][0]['status'] == 'Unmatched HUB')
    c = r['counts']
    check('contagem dos cards', (c['Unmatched HUB'], c['Unmatched OTC'], c['Partial'], c['Matched'], c['total'])
          == (2, 2, 3, 1, 8), c)
    sm = {s['code']: s for s in r['summary']}
    check('resumo por código: 5557MT dos dois lados',
          sm['5557MT12050']['otc_n'] == 3 and sm['5557MT12050']['hub_n'] == 4
          and sm['5557MT12050']['otc_ir'] == round(0.35 + 0.70 + 14.05, 2)
          and sm['5557MT12050']['hub_ir'] == round(0.0 + 1.05 + 14.05 + 0.05, 2), sm.get('5557MT12050'))
    check('resumo: o 5273OT só do lado OTC e o do HUB', sm['5273OT12046']['otc_n'] == 1
          and sm['5273OT12046']['hub_n'] == 1)
    check('os dois arquivos do HUB aparecem no decêndio', len(r['hub_files']) == 2)

    # Reenviar o 5557 corrigido SUBSTITUI só o 5557 da empresa 00001 (o 5273 fica).
    f5557b = _xlsx([('00001 - Banco J.P. Morgan S.A.', [
        _hub('11111111000111', 'CLIENTE A SA', '5557MT12050', 'STP-AAA-0000002-0-', 7000.0, '55571', '13/10/2026', 0.35),
        _hub('11111111000111', 'CLIENTE A SA', '5557MT12050', 'STP-AAA-0000003-0-', 2000.0, '55571', '15/10/2026', 0.70),
        _hub('33333333000133', 'CLIENTE C SA', '5557MT12050', 'STP-CCC-0000009-0-', 280978.51, '55571', '14/10/2026', 14.05),
    ])])
    r = cl.post('/api/wht/hub-import', data={'files': [(io.BytesIO(f5557b), 'hub_5557_v2.xlsx')], 'date': '2026-10-20'},
                content_type='multipart/form-data').get_json()
    st = {x['Internal ID']: x for x in r['rows']}
    check('reimportação corrigida: as duas do A batem',
          st['STP-AAA-0000002-0-0']['status'] == 'Matched' and st['STP-AAA-0000003-0-0']['status'] == 'Matched')
    check('...a que o HUB tirou sai, e o 5273 e a empresa 00017 ficam',
          'STP-ZZZ-9999999-0-' not in st and 'SWP-0000000000001' in st and '85101H-1OKXWV' in st)

    hf = cl.post('/api/wht/hub-file', json={'date': '2026-10-20'})
    corpo = hf.data.decode('cp1252')
    check('arquivo do HUB: só as Unmatched OTC (o isento e o swap)', hf.status_code == 200
          and hf.headers.get('X-WHT-Count') == '2' and corpo.count('\r\n') == 8, (hf.status_code, corpo[:300]))
    check('nome pelo decêndio', hf.headers.get('X-WHT-Name') == 'WHT_HUB_20261011_20261020.txt')
    check('a linha do swap com o CNPJ do Reference Data, o prefixo e a data de liquidação',
          '00001000104885503000142SWP-270RI70427368 161020265273OT12046\r\n' in corpo, corpo[:200])
    check('o isento com o prefixo NDF e o código ME',
          '00001000158160789000128NDF-STP-BBB-000000151020265557ME12050' in corpo, corpo)
    ks = [x['key'] for x in r['rows'] if x['Internal ID'] == 'STP-CCC-0000009-0-0']
    hf2 = cl.post('/api/wht/hub-file', json={'date': '2026-10-20', 'keys': ks})
    check('linhas marcadas: só elas', hf2.headers.get('X-WHT-Count') == '1'
          and 'NDF-STP-CCC-000000' in hf2.data.decode('cp1252'), (ks, hf2.status_code, hf2.data[:300]))
    vazio = cl.post('/api/wht/hub-file', json={'date': '2026-10-05', 'keys': ['nada']})
    check('sem operação: recusa por código', vazio.status_code == 400
          and vazio.get_json()['error_code'] == 'hub_file_empty', vazio.get_json())

    print('== 7b. o fluxo das telas de liquidação ==')
    NDF[date(2026, 10, 19)] = [_ndf('CLIENTE E SA', -40000.0, 'STP-EEE-0000005-0-0', '26J00000005')]
    j = cl.get('/api/ndf-summary/data?date=2026-10-19').get_json()
    check('o NDF Summary responde sem as linhas internas', j.get('success') and 'email_trades' not in j, j)
    doc = store.load('202610')
    check('...e o dia fluiu para o WHT', [x['internal_id'] for x in doc['otc']['2026-10-19']['ndf']['rows']]
          == ['STP-EEE-0000005-0-0'], doc['otc'].get('2026-10-19'))
    cl.get('/api/ndf-summary/data?date=2026-10-23')
    check('coleta VAZIA de um dia sem fatia não cria o dia', '2026-10-23' not in store.load('202610')['otc'])
    from apps.pages.features.wht import commands as C
    check('a recoleta em background respeita o kill-switch dos testes', C.refresh_async(date(2026, 10, 19)) is False)


def secao_tela():
    print('== 8. menu, cadastros e traduções ==')
    nav = open(os.path.join(ROOT, 'apps', 'templates', 'partials', 'sidenav.html'), encoding='utf-8').read()
    check('o item Regulatory › WHT aponta para a página', 'href="/regulatory/wht"' in nav)
    mp = open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'mapping.html'), encoding='utf-8').read()
    for k in ('wht-codes', 'wht-company', 'wht-non-resident'):
        check('/mapping tem a aba %s' % k, "key: '%s'" % k in mp)
    tela = open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'wht.html'), encoding='utf-8').read()
    import re
    chaves = set(re.findall(r'data-lang="([^"]+)"', tela)) | {'map-tab-wht-codes', 'map-tab-wht-company',
                                                              'map-tab-wht-nonres'}
    for lg in ('en', 'br', 'es'):
        tr = json.load(open(os.path.join(ROOT, 'apps', 'static', 'data', 'translations', lg + '.json'),
                            encoding='utf-8'))
        falta = sorted(k for k in chaves if k not in tr)
        check('traduções %s completas' % lg, not falta, falta)


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
