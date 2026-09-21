# -*- coding: utf-8 -*-
"""check_unwind_products.py — o BACKEND das onze recompras do catalogo.

As paginas `pages/unwinds-product.html` (Swap CEM/EDG, NDF Commodities, Options
FXO/Commodities/EDG, COE, DCE x4) tem UM servidor, dirigido pelo catalogo
(`features/unwinds/catalog.py` + `features/unwinds/product/`). O que se prende:

  1. a API e UMA regra: produto de um OU dois segmentos, acao desconhecida e
     404 JSON com codigo;
  2. o import le a PLANILHA pelos rotulos OU nomes de campo (cego a caixa e
     acento), pelo CONTEUDO (xlsx e csv), e o e-mail responde por CODIGO que o
     formato ainda nao existe;
  3. NDF Commodities com B3 ID: a posicao completa contraparte (guarda-chuva ->
     CPF/CNPJ), saldo e strike; o Check refaz o termo e FECHA; o TER 0014 tem 133;
  4. Options FXO SEM B3 ID: casa por caracteristicas so com candidato UNICO;
     ambiguo NAO chuta e o Check fica '-' (nunca OK por omissao);
  5. Swap CEM: papel pela conta nossa, antecipacao parcial exige Mantem Premios,
     o SWAP 0014 tem a largura que o template soma;
  6. dry-run -> duplicatas, sem gravar e sem sino; 4-olhos (Pending, o proprio
     nao aprova, Pending nao se envia); Send grava no Batch Conecta e vira Sent;
     enviada nao se apaga nem se sobrescreve no re-import;
  7. COE/DCE nao tem arquivo da B3: preview e send respondem com codigo;
  8. o sino: rotulo = `label` do catalogo, nos TRES mapas; toda acao que grava
     notifica, o dry-run nao;
  9. o Monitor tem card para toda pasta do catalogo (swap soma nos cards de
     swap pela LOB) e o painel conta a linha pelo `_id`.

Roda em tmp: a arvore de recompras, o Batch Conecta e as posicoes sao stubs —
nao encosta em dado real.
"""
import io
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(nome, cond, extra=''):
    print(('  ok  ' if cond else ' FAIL ') + nome + (('  — ' + str(extra)) if (not cond and extra) else ''))
    if not cond:
        FALHAS.append(nome)


def _digitos(v):
    return ''.join(c for c in str(v or '') if c.isdigit())


# ── as posicoes (stubs pela porta dos coletores de Live Position) ────────────
NDF_COLS = ['Contrato', 'Codigo da Parte', 'Codigo da Contraparte', 'Nome da Contraparte',
            'CPF/CNPJ da Contraparte', 'Valor Base no registro', 'Valor Antecipado',
            'Taxa Forward', 'Data de Emissao', 'Data de Vencimento',
            'Codigo do Ativo Subjacente', 'Simbolo da Moeda',
            'Descricao da posicao do Participante']
NDF_POS = {'Contrato': '26G00000001', 'Codigo da Parte': '73760.00-9',
           # a guarda-chuva: o titular e o banco, o cliente e o CPF/CNPJ
           'Codigo da Contraparte': '73760.10-2', 'Nome da Contraparte': 'BANCO J.P. MORGAN S/A',
           'CPF/CNPJ da Contraparte': 'USINA ALTO ALEGRE SA',
           'Valor Base no registro': '1,000.00', 'Valor Antecipado': '200.00',
           'Taxa Forward': '4.50', 'Data de Emissao': '01/06/2026',
           'Data de Vencimento': '15/12/2026', 'Codigo do Ativo Subjacente': 'CTZ6',
           'Simbolo da Moeda': 'USD', 'Descricao da posicao do Participante': 'COMPRADOR'}

OPT_COLS = ['Código IF', 'Tipo de Opção', 'Posição da Parte', 'Parte (Conta)',
            'Contraparte (Conta)', 'Contraparte (Nome simplificado)',
            'CPF/CNPJ Cliente Contraparte', 'Strike (valor)', 'Quantidade',
            'Quantidade Antecipada', 'Data Vencimento', 'Data Registro',
            'Ativo subjacente / Moeda base', 'Modalidade de liquidação do prêmio',
            'Prêmio Unitário', 'Média Asiática']
OPT_A = {'Código IF': 'OPC000A', 'Tipo de Opção': 'Call', 'Posição da Parte': 'Titular',
         'Parte (Conta)': '73760009', 'Contraparte (Conta)': '12345678',
         'Contraparte (Nome simplificado)': 'CLIENTEX', 'CPF/CNPJ Cliente Contraparte': '',
         'Strike (valor)': '5.20000000', 'Quantidade': '1,000,000.00',
         'Quantidade Antecipada': '0.00', 'Data Vencimento': '15/12/2026',
         'Data Registro': '01/06/2026', 'Ativo subjacente / Moeda base': 'USD',
         'Modalidade de liquidação do prêmio': 'Bruta', 'Prêmio Unitário': '0.05000000',
         'Média Asiática': ''}
OPT_B = dict(OPT_A, **{'Código IF': 'OPC000B', 'Tipo de Opção': 'Put',
                       'Strike (valor)': '5.50000000'})

SWAP_ROW = {'Contrato': 'SWP0001', 'Participante': '73760009', 'Contraparte': '55555005',
            'CPF/CNPJ Cliente Contraparte': '11222333000181', 'Data início': '10/01/2026',
            'Data vencimento': '10/01/2027', 'Valor base': '1000000,00',
            'Valor Antecipado': '0', 'Código Identificador': 'CEM'}


def _collect(cols, rows):
    return lambda ref, exact=False: {'columns': cols, 'source_date': '2026-09-18',
                                     'rows': [[r.get(c, '') for c in cols] for r in rows]}


def _xlsx(header, linhas):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['Unwinds export'])            # titulo em cima: o cabecalho e achado abaixo
    ws.append(header)
    for l in linhas:
        ws.append(l)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def main():
    from run import app
    from apps.pages import routes as R
    from apps.pages.features.unwinds import catalog
    from apps.pages.features.unwinds import queries as fase1_queries
    from apps.pages.features.unwinds.infra import persistence, product_store
    from apps.pages.features.unwinds.product import commands as PC
    from apps.pages.features.unwinds.product import domain as PD
    from apps.pages.features.unwinds.product import queries as PQ
    from apps.pages.platform import notifications as NOTIF
    from apps.pages.platform import swap_flows as SF
    from apps.pages.features.deals_monitor import domain as NDM

    tmp = tempfile.mkdtemp(prefix='otc-unwprod-')
    raiz = os.path.join(tmp, 'unwinds')
    # As DUAS portas da arvore de recompras (a das paginas do catalogo e a da
    # Fase 1, que o painel varre): trocando so uma, o teste CONTA a arvore real.
    product_store.cache_root = lambda: raiz
    persistence.cache_root = lambda: raiz
    R.CONECTA_NEW_PATH = os.path.join(tmp, 'conecta')

    CONTAS = {'73760009': 'JPM', '73760102': 'JPM'}
    R._b3_account_le = lambda a: CONTAS.get(_digitos(a).zfill(8), '')
    R._b3_is_omnibus = lambda a: _digitos(a).zfill(8) == '73760102'
    R._b3_participant_name = lambda le: 'JPMORGANBM' if le == 'JPM' else ''
    R._lp_cpty_by_account = lambda a: {'12345678': 'CLIENTE X SA',
                                       '55555005': 'EMPRESA Y SA'}.get(_digitos(a), '')
    R._lp_cpty_name_by_taxid = lambda d: ''
    R._refdata_by_name = lambda *a, **k: {R._pc_norm('USINA ALTO ALEGRE SA'):
                                          {'TAX ID': '12.345.678/0001-90'}}
    R._lpndf_collect = _collect(NDF_COLS, [NDF_POS])
    R._lpopt_collect = _collect(OPT_COLS, [OPT_A, OPT_B])
    SF.swap_day_file = lambda tpl, ref=None: ('/nao/existe.json', '260918')
    R._db_day_records = lambda p: [dict(SWAP_ROW)]
    PC._hoje = lambda: date(2026, 9, 21)

    sino = []
    R._create_notification = lambda *a, **k: sino.append(a)

    cl = app.test_client()

    def _login(sid):
        with cl.session_transaction() as ss:
            ss['authenticated'] = True
            ss['user_sid'] = sid
            ss['user_name'] = 'Teste ' + sid
            ss['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    _login('A000001')

    def _up(api, nome, dados, dry=False, dia='2026-09-21'):
        form = {'file': (io.BytesIO(dados), nome), 'date': dia}
        if dry:
            form['dry_run'] = '1'
        r = cl.post(api + '/import-file', data=form, content_type='multipart/form-data')
        return r.status_code, (r.get_json(silent=True) or {})

    def _post(url, body):
        r = cl.post(url, data=json.dumps(body), content_type='application/json')
        return r.status_code, (r.get_json(silent=True) or {})

    print('== 1. a API e UMA regra, dirigida pelo catalogo ==')
    check('produto de dois segmentos + acao',
          catalog.page_and_action('swap/cem/import-file')[1] == 'import-file'
          and catalog.page_and_action('swap/cem/import-file')[0]['path'] == '/unwinds/swap/cem')
    check('produto de um segmento (COE) + acao',
          catalog.page_and_action('coe/delete')[0]['path'] == '/unwinds/coe'
          and catalog.page_and_action('coe/delete')[1] == 'delete')
    check('produto fora do catalogo', catalog.page_and_action('nada/x')[0] is None)
    r = cl.post('/api/unwinds/options/fxo/nada')
    check('acao desconhecida: 404 JSON com codigo',
          r.status_code == 404 and (r.get_json() or {}).get('code') == 'unwind_unknown_action')
    g = cl.get('/api/unwinds/options/fxo?date=2026-09-21').get_json()
    check('GET: backend ligado, contrato do catalogo',
          g.get('success') and g.get('backend') is True and g['entries'] == []
          and g['fields'] == catalog.fields(catalog.PAGES['/unwinds/options/fxo']))
    check('a Fase 1 continua na rota dela', 'backend' not in (cl.get('/api/unwinds/ndf/fx?date=2026-09-21').get_json() or {}))

    print('\n== 2. o que o import aceita — e o que recusa POR CODIGO ==')
    pg_opt = catalog.PAGES['/unwinds/options/fxo']
    st, j = _up(pg_opt['api'], 'aviso.eml',
                b'MIME-Version: 1.0\r\nSubject: Unwind\r\nContent-Type: text/html\r\n\r\n<table></table>')
    check('e-mail: formato pendente, por codigo', st == 400 and j.get('code') == 'unwind_email_format_pending', (st, j))
    st, j = _up(pg_opt['api'], 'lixo.csv', b'foo;bar\n1;2\n')
    check('planilha sem as colunas da pagina: cabecalho desconhecido',
          st == 400 and j.get('code') == 'unwind_sheet_header_unknown', (st, j))
    check('nada disso tocou o sino', sino == [], sino)
    linhas, _av = PD.linhas_da_planilha([['counter party', 'UNWOUND_NOTIONAL', 'Unwind Date'],
                                         ['X', '1.234,50', '21/09/2026']], pg_opt)
    check('rotulo ou campo, cego a caixa/acento/separador',
          linhas and linhas[0].get('Counterparty') == 'X'
          and linhas[0].get('UnwoundNotional') == 1234.5
          and linhas[0].get('UnwindDate') == '2026-09-21', linhas)

    print('\n== 3. NDF Commodities com B3 ID ==')
    pg_ndf = catalog.PAGES['/unwinds/ndf/commodities']
    res = 300 * (5.0 - 4.5) * 1 * 5.4 / ((1 + 14.0 / 100) ** (60 / 252.0))
    csv_ndf = ('B3 ID;Unwound Quantity;Termination Price;FX Rate;Pre FWD Rate;DU;Result;Unwind Date\n'
               '26G00000001;300;5.00;5.40;14.00;60;%.6f;21/09/2026\n' % res).encode('utf-8')
    st, dry = _up(pg_ndf['api'], 'recompra.csv', csv_ndf, dry=True)
    check('dry-run le e nao grava', st == 200 and dry.get('success') and dry['duplicates'] == []
          and PQ.entries(pg_ndf, '2026-09-21') == [], (st, dry))
    check('   e nao toca o sino', sino == [])
    st, j = _up(pg_ndf['api'], 'recompra.csv', csv_ndf)
    l = (j.get('rows') or [{}])[0]
    check('import 200', st == 200 and j.get('success'), (st, j))
    check('guarda-chuva: a contraparte e o CPF/CNPJ, nunca o titular',
          l.get('Counterparty') == 'USINA ALTO ALEGRE SA', l.get('Counterparty'))
    check('e o CNPJ sai do Reference Data', l.get('TaxID') == '12.345.678/0001-90', l.get('TaxID'))
    check('saldo e strike da posicao',
          (l.get('OriginalNotional'), l.get('UnwoundBefore'), l.get('Strike')) == (1000.0, 200.0, 4.5), l)
    check('mercadoria e moeda da posicao', (l.get('Commodity'), l.get('Currency')) == ('CTZ6', 'USD'))
    check('o Check refaz o termo e FECHA', l.get('Check') == 'OK', l.get('Warnings'))
    check('direcao pelo SINAL do resultado', l.get('Direction') == 'RECEIVE')
    check('nasce Imported com _id e Nº de controle', l.get('Status') == 'Imported'
          and l.get('_id') and len(str(l.get('MyNumber'))) == 10)
    check('o import tocou o sino com o rotulo da pagina',
          sino and sino[-1][2:4] == ('Deals Imported', 'Unwind NDF Commodities'), sino[-1:])
    check('gravou no arquivo-dia do produto',
          os.path.isfile(os.path.join(raiz, 'NDF', 'Commodities', '2026', '09',
                                      '20260921_unwindndfcommodities.json')))
    rid_ndf = l['_id']
    r = cl.get(pg_ndf['api'] + '/preview?id=%s&date=2026-09-21' % rid_ndf)
    pj = r.get_json() or {}
    check('preview 200', r.status_code == 200 and pj.get('success'), pj)
    rec = ((pj.get('files') or [{}])[0].get('records') or [''])[0]
    check('TER 0014 com 133 caracteres', len(rec) == 133, len(rec))
    check('campo 6 papel COMPRADO', rec[28:29] == '0', rec[28:29])
    check('campo 7 a guarda-chuva', rec[29:37] == '73760102', rec[29:37])
    check('campo 9 a QUANTIDADE recomprada', rec[48:64] == '0000000000030000', rec[48:64])
    check('campo 14 a paridade (taxa termo fora de BRL)', rec[110:122] == '000540000000', rec[110:122])
    check('nome do arquivo com o produto',
          pj['files'][0]['file_name'] == 'UNWIND_NDF_COMMODITIES_BANCO.txt')

    print('\n== 4. Options FXO sem B3 ID: casa so com candidato UNICO ==')
    hdr = ['Counterparty', 'Call / Put', 'Maturity Date', 'Unwound Quantity', 'Unit Premium',
           'Settlement Amount', 'Premium Payer']
    x = _xlsx(hdr, [['Cliente X SA', 'Call', date(2026, 12, 15), 400000, 0.04, 16000, 'Titular'],
                    ['Cliente X SA', '', date(2026, 12, 15), 100000, 0.04, 4000, 'Titular']])
    st, j = _up(pg_opt['api'], 'opcoes.xlsx', x)
    rows = j.get('rows') or []
    check('xlsx lido pelo conteudo (duas linhas)', st == 200 and len(rows) == 2, (st, j))
    a, b = (rows + [{}, {}])[:2]
    check('unica: o contrato veio da posicao', a.get('Contract') == 'OPC000A', a.get('Contract'))
    check('   e a conferencia fecha (saldo + premio)', a.get('Check') == 'OK', a.get('Warnings'))
    check('ambigua: NAO chuta o contrato', not b.get('Contract'))
    check('   e o Check e "-", nunca OK por omissao', b.get('Check') == '-', b.get('Check'))
    cods = {w.get('code') for w in j.get('warnings') or []}
    check('   e o aviso diz que era ambiguo',
          'unwind_match_ambiguous' in cods and 'unwind_matched_by_characteristics' in cods, cods)
    r = cl.get(pg_opt['api'] + '/preview?id=%s&date=2026-09-21' % a['_id'])
    pj = r.get_json() or {}
    reg = (((pj.get('files') or [{}])[0].get('records') or [''])[0]).split(';')
    check('OPC 0014 delimitado', r.status_code == 200 and len(reg) >= 15, (r.status_code, pj))
    if len(reg) >= 15:
        check('contrato, contas do REGISTRO e Meu Numero',
              reg[2] == 'OPC000A' and reg[3] == '73760009' and reg[4] == '12345678'
              and len(reg[5]) == 10, reg[:6])
        check('quantidade, premio e financeiro com virgula',
              (reg[6], reg[8], reg[9]) == ('400000,00000000', '0,04000000', '16000,00'), reg[6:10])
        check('modalidade Bruta (da posicao) e pagador Titular', (reg[11], reg[13]) == ('2', '1'))
    r = cl.get(pg_opt['api'] + '/preview?id=%s&date=2026-09-21' % b['_id'])
    check('a ambigua nao gera arquivo: 422 dizendo o que falta',
          r.status_code == 422 and (r.get_json() or {}).get('code') == 'unwind_b3_missing',
          r.get_json())

    print('\n== 5. Swap CEM: papel pela conta nossa, parcial pede Mantem Premios ==')
    pg_swap = catalog.PAGES['/unwinds/swap/cem']
    csv_sw = (b'B3 ID;Unwound Notional;Unwind Amount;Unwind Date\n'
              b'SWP0001;400000;12345.67;21/09/2026\n')
    st, j = _up(pg_swap['api'], 'swap.csv', csv_sw)
    s = (j.get('rows') or [{}])[0]
    check('import 200', st == 200, j)
    check('papel Ponta 1 (a Participante e nossa), LOB e contraparte pela conta',
          (s.get('Role'), s.get('LOB'), s.get('Counterparty')) == ('Ponta 1', 'CEM', 'EMPRESA Y SA'), s)
    check('saldo da posicao e Check do saldo',
          s.get('OriginalNotional') == 1000000.0 and s.get('Check') == 'OK', s.get('Warnings'))
    r = cl.get(pg_swap['api'] + '/preview?id=%s&date=2026-09-21' % s.get('_id'))
    check('parcial sem Mantem Premios: recusa com codigo',
          r.status_code == 422 and 'Mantém Prêmios' in ((r.get_json() or {}).get('params') or {}).get('campos', ''),
          r.get_json())
    st, e = _post(pg_swap['api'] + '/edit', {'id': s.get('_id'), 'date': '2026-09-21',
                                             'fields': {'KeepPremium': 'Sim'}})
    check('edicao -> Pending com maker', st == 200 and e['row']['Status'] == 'Pending'
          and e['row']['Maker'] == 'A000001', (st, e))
    r = cl.get(pg_swap['api'] + '/preview?id=%s&date=2026-09-21' % s.get('_id'))
    pj = r.get_json() or {}
    rec = ((pj.get('files') or [{}])[0].get('records') or [''])[0]
    larg = PC._largura_do_bloco('swap-antecipacao', 'registro')
    check('SWAP 0014 na largura que o TEMPLATE soma', r.status_code == 200 and len(rec) == larg,
          (r.status_code, len(rec), larg, pj))
    check('contrato, papel 00, valor e mantem premios 00',
          rec[10:21] == 'SWP0001    ' and rec[21:23] == '00' and rec[85:101] == '0000000001234567'
          and rec[101:103] == '00', rec)
    st, j = _post(pg_swap['api'] + '/send-conecta', {'items': [{'id': s['_id']}], 'date': '2026-09-21'})
    check('Pending NAO e enviavel', st == 400 and j.get('code') == 'unwind_nothing_sent', (st, j))
    st, j = _post(pg_swap['api'] + '/approve', {'id': s['_id'], 'date': '2026-09-21'})
    check('o proprio maker nao aprova: 403', st == 403 and j.get('code') == 'unwind_maker_is_checker', (st, j))
    _login('B000002')
    st, j = _post(pg_swap['api'] + '/approve', {'id': s['_id'], 'date': '2026-09-21'})
    check('outro usuario aprova', st == 200 and j['row']['Status'] == 'Approved'
          and j['row']['Checker'] == 'B000002', (st, j))
    _login('A000001')

    print('\n== 6. Send, duplicatas, enviada nao se apaga ==')
    st, j = _post(pg_ndf['api'] + '/send-conecta', {'items': [{'id': rid_ndf}], 'date': '2026-09-21'})
    check('send 200 grava no Batch Conecta', st == 200 and j['count'] == 1
          and j['files'][0]['filename'] == 'UNWIND_NDF_COMMODITIES_BANCO.txt', (st, j))
    escrito = io.open(os.path.join(R.CONECTA_NEW_PATH, 'UNWIND_NDF_COMMODITIES_BANCO.txt'),
                      encoding='utf-8').read().split('\n')
    check('header + um registro de 133', len(escrito) == 2 and len(escrito[1]) == 133)
    linha = [e for e in PQ.entries(pg_ndf, '2026-09-21') if e['_id'] == rid_ndf][0]
    check('virou Sent', linha['Status'] == 'Sent' and linha['SentFiles'])
    st, j = _post(pg_ndf['api'] + '/delete', {'id': rid_ndf, 'date': '2026-09-21'})
    check('enviada nao se apaga: 409', st == 409 and j.get('code') == 'unwind_already_sent', (st, j))
    st, dry = _up(pg_ndf['api'], 'recompra.csv', csv_ndf, dry=True)
    check('dry-run acha a duplicata pela chave natural', len(dry.get('duplicates') or []) == 1, dry)
    st, j = _up(pg_ndf['api'], 'recompra.csv', csv_ndf)
    check('re-import nao sobrescreve a enviada', j.get('skipped') == 1 and j['rows'] == []
          and len(PQ.entries(pg_ndf, '2026-09-21')) == 1, j)
    st, j = _post(pg_opt['api'] + '/delete', {'id': b['_id'], 'date': '2026-09-21'})
    check('delete da ambigua', st == 200 and j.get('success'))
    check('   e ela saiu do arquivo-dia',
          [e['_id'] for e in PQ.entries(pg_opt, '2026-09-21')] == [a['_id']])

    print('\n== 7. COE e DCE nao tem arquivo da B3 ==')
    pg_coe = catalog.PAGES['/unwinds/coe']
    st, j = _up(pg_coe['api'], 'coe.csv',
                b'B3 ID;Unwound Quantity;Unit Price;Settlement Amount;Original Quantity;Unwound Before\n'
                b'COE123;10;100.5;1005;50;0\n')
    c = (j.get('rows') or [{}])[0]
    check('COE importa (sem posicao) e confere saldo + valor', st == 200 and c.get('Check') == 'OK',
          (st, c.get('Warnings')))
    r = cl.get(pg_coe['api'] + '/preview?id=%s&date=2026-09-21' % c.get('_id'))
    check('preview: 422 unwind_no_b3_file',
          r.status_code == 422 and (r.get_json() or {}).get('code') == 'unwind_no_b3_file')
    st, j = _post(pg_coe['api'] + '/send-conecta', {'items': [{'id': c.get('_id')}], 'date': '2026-09-21'})
    check('send: 422 unwind_no_b3_file', st == 422 and j.get('code') == 'unwind_no_b3_file', (st, j))

    print('\n== 8. o sino: o rotulo do catalogo nos TRES mapas ==')
    txt_top = io.open(os.path.join(ROOT, 'apps', 'templates', 'partials', 'topbar.html'), encoding='utf-8').read()
    txt_sw = io.open(os.path.join(ROOT, 'apps', 'static', 'js', 'sw-push.js'), encoding='utf-8').read()
    for p in catalog.PAGES.values():
        check('%s -> %s' % (p['label'], p['path']),
              NOTIF._NOTIF_PAGE_URL.get(p['label']) == p['path']
              and ("'%s'" % p['label']) in txt_top and ("'%s'" % p['label']) in txt_sw)
    acoes = [x[2] for x in sino]
    check('import, edicao, aprovacao, envio e delete tocaram o sino',
          all(a_ in acoes for a_ in ('Deals Imported', 'Deal Updated', 'Status Updated',
                                     'Sent to B3', 'Deal Deleted')), acoes)

    print('\n== 9. Monitor e painel ==')
    dirs = {d for c in NDM._NDM_CARDS for d in c['dirs']}
    for p in catalog.PAGES.values():
        check('card no Monitor para Unwind/%s' % p['dir'], NDM.PREFIXO_UNWIND + p['dir'] in dirs)
    with app.test_request_context():
        dash = fase1_queries.dashboard_counts('all', datetime(2026, 9, 21))
    rot = {x['label']: x['total'] for x in dash['products']}
    check('o painel conta as linhas do catalogo pelo _id',
          rot.get('Unwind NDF Commodities') == 1 and rot.get('Unwind Options FXO') == 1
          and rot.get('Unwind Swap CEM') == 1 and rot.get('Unwind COE') == 1, rot)

    print('\n%s' % ('TUDO OK' if not FALHAS else '%d FALHA(S): %s' % (len(FALHAS), FALHAS)))
    return 1 if FALHAS else 0


if __name__ == '__main__':
    sys.exit(main())
