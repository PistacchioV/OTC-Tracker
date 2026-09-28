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
from apps.config import Config as _Cfg                      # noqa: E402
_Cfg.FOUR_EYES = True   # prova a trava da PROD; na dev o maker/checker e desligado (§553)
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
            'Descricao da posicao do Participante', 'Codigo Identificador']
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
    R._b3_participant_name = lambda le: {'JPM': 'JPMORGANBM', 'LAWTON': 'INTRAGLAWTONFDO'}.get(le, '')
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
    check('e-mail sem a tabela da pagina: recusa por codigo',
          st == 400 and j.get('code') == 'unwind_email_table_unknown', (st, j))
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
    # A MESMA tabela colada do Excel no corpo do e-mail (a marcacao do Outlook:
    # <p class=MsoNormal><span>, &nbsp;, cabecalho quebrado em duas linhas), com
    # uma tabela de assinatura ANTES dela e a data como o Excel a cola.
    def _td(v):
        return '<td nowrap><p class=MsoNormal><span style="font-size:9pt">%s</span></p></td>' % v
    cab = ['B3 ID', 'Unwound<br>Quantity', 'Termination&nbsp;Price', 'FX Rate', 'Pre FWD Rate',
           'DU', 'Result', 'Unwind Date']
    val = ['26G00000001', '300', '5.00', '5.40', '14.00', '60', '%.6f' % res, '21-Sep-26']
    corpo = ('<html><body><table><tr><td>Mesa OTC</td></tr></table><p>Segue:</p>'
             '<table border=0 cellpadding=0><tr>%s</tr><tr>%s</tr></table></body></html>'
             % (''.join(_td(c) for c in cab), ''.join(_td(v) for v in val)))
    eml = ('MIME-Version: 1.0\r\nSubject: Unwind NDF Comm\r\nContent-Type: text/html; '
           'charset=utf-8\r\n\r\n' + corpo).encode('utf-8')
    st, dm = _up(pg_ndf['api'], 'Unwind NDF Comm.eml', eml, dry=True)
    _sem = lambda rs: [{k: v for k, v in r.items() if k not in ('_id', 'MyNumber', 'ImportedAt',
                                                               'SourceFile')} for r in rs]
    check('e-mail com a tabela colada do Excel: as MESMAS linhas da planilha',
          st == 200 and _sem(dm.get('rows') or []) == _sem(dry.get('rows') or []), (st, dm))
    txt = ('MIME-Version: 1.0\r\nSubject: x\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n'
           'Segue:\r\n' + '\t'.join(c.replace('<br>', ' ').replace('&nbsp;', ' ') for c in cab)
           + '\r\n' + '\t'.join(val) + '\r\n').encode('utf-8')
    st, dt = _up(pg_ndf['api'], 'x.eml', txt, dry=True)
    check('   e o e-mail em texto puro (TAB do Excel) tambem',
          st == 200 and _sem(dt.get('rows') or []) == _sem(dry.get('rows') or []), (st, dt))
    check('   sem gravar nem tocar o sino', PQ.entries(pg_ndf, '2026-09-21') == [] and sino == [])
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
    # E se REENVIA (mesa, 28/09/2026, §579): o arquivo novo nao sobrescreve o
    # que ja esta na pasta (`_unique_filepath`).
    st, j = _post(pg_ndf['api'] + '/send-conecta', {'items': [{'id': rid_ndf}], 'date': '2026-09-21'})
    check('linha Sent se envia de novo', st == 200 and j.get('count') == 1, (st, j))
    st, j = _post(pg_ndf['api'] + '/delete', {'id': rid_ndf, 'date': '2026-09-21'})
    check('enviada nao se apaga: 409', st == 409 and j.get('code') == 'unwind_already_sent', (st, j))
    st, dry = _up(pg_ndf['api'], 'recompra.csv', csv_ndf, dry=True)
    check('dry-run acha a duplicata pela chave natural', len(dry.get('duplicates') or []) == 1, dry)
    st, j = _up(pg_ndf['api'], 'recompra.csv', csv_ndf)
    check('re-import nao sobrescreve a enviada', j.get('skipped') == 1 and j['rows'] == []
          and len(PQ.entries(pg_ndf, '2026-09-21')) == 1, j)
    st, j = _post(pg_ndf['api'] + '/edit', {'id': rid_ndf, 'date': '2026-09-21',
                                           'fields': {'Counterparty': 'EDITADA APOS ENVIO'}})
    check('enviada SE edita e volta a Pending', st == 200 and j.get('row', {}).get('Status') == 'Pending'
          and j['row'].get('Counterparty') == 'EDITADA APOS ENVIO', (st, j))
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

    print('\n== 10. O Reference Data e montado UMA vez por coleta ==')
    # Montado a cada linha da posicao, o indice relia o cadastro e normalizava
    # todos os nomes por linha: no NDF da instancia, o import nao terminava.
    chamadas = []
    _por_nome = R._refdata_by_name
    R._refdata_by_name = lambda *a, **k: chamadas.append(1) or _por_nome()
    R._lpndf_collect = _collect(NDF_COLS, [dict(NDF_POS, Contrato='26G%08d' % i) for i in range(50)])
    try:
        with app.test_request_context():
            pos, _src = PQ.posicoes(catalog.page('ndf/commodities'), datetime(2026, 9, 21))
    finally:
        R._refdata_by_name = _por_nome
    got = (len(pos), len(chamadas), pos[0]['taxid'] if pos else '')
    check('50 posicoes, uma montagem do indice', got == (50, 1, '12.345.678/0001-90'), got)

    print('\n== 11. O e-mail de recompra de NDF Commodities (uma tabela por perna) ==')
    # O modelo da mesa (28/09/2026), como o Outlook guarda o trecho colado do
    # Excel: cabecalho quebrado em <br>, o Fixing em duas linhas, o numero como
    # a celula EXIBE (96.85 e 5.2087 no Client valem 96,84626 e 5,20867).
    def _td(v):
        return '<td><p class=MsoNormal><span>%s</span></p></td>' % v

    def _tab(cab, linhas):
        return ('<table class=MsoNormalTable>' + '<tr>' + ''.join(_td(c) for c in cab) + '</tr>'
                + ''.join('<tr>' + ''.join(_td(c) for c in l) + '</tr>' for l in linhas)
                + '</table><p class=MsoNormal>&nbsp;</p>')
    cab_cli = ['Leg', 'Trade Date', 'Fixing', 'Risk Deal ID', 'Original<br>Position',
               'Original<br>Volume (MT)', 'Original Strike<br>(USD/MT)', 'Unwind<br>Volume (MT)',
               'Unwind Strike', 'FV USD', 'FX Rate', 'PV BRL', 'Direction', 'Unwind']
    cab_bco = ['Leg', 'Trade Date', 'Fixing', 'Original<br>Position', 'Original<br>Volume',
               'Original<br>Strike', 'Unwind<br>Volume', 'Unwind<br>Strike', 'FV USD', 'FX Rate',
               'PV BRL']
    cab_occ = ['Leg', 'Trade Date', 'Fixing', 'Original<br>Position', 'Original<br>Volume',
               'Original<br>Strike', 'Unwind<br>Volume', 'Unwind<br>Strike', 'FV USD', 'PV USD']
    fix = '01-Sep-26/30-<br>Sep-26'
    corpo = ('<html><body><p class=MsoNormal>Hi all,</p><p class=MsoNormal>We have closed the '
             'followings full unwinds for CSN:</p><p class=MsoNormal><u>CSNMINER</u><br>'
             '<u>Trade IDs: D5NQ-HMNV</u></p>'
             + _tab(cab_cli, [['Client', '13-May-26', fix, 'D5NQ-HMNV', 'Client Sells', '100,000',
                               '108.885', '100,000', '96.85', '1,203,874.00', '5.2087',
                               '6,270,582.12', 'Client<br>Receives', 'Full']])
             + _tab(cab_bco, [['Banco', '13-May-26', fix, 'BJPM Sells', '100,000', '108.985',
                               '100,000', '96.85', '1,213,500.00', '5.2087', '6,321,326.69']])
             + _tab(cab_occ, [['JPMOCC', '13-May-26', fix, 'JPMOCC Sells', '100,000', '108.985',
                               '100,000', '96.85', '1,213,500.00', '1,213,236.00']])
             + '</body></html>')
    eml = ('MIME-Version: 1.0\r\nSubject: CSN unwind\r\nContent-Type: text/html; charset=utf-8'
           '\r\n\r\n' + corpo).encode('utf-8')
    pos_cli = dict(NDF_POS, Contrato='26E00000CLI', **{'Taxa Forward': '108.885',
                                                      'Valor Base no registro': '100,000.00',
                                                      'Valor Antecipado': '0.00',
                                                      'Codigo Identificador': 'D5NQ-HMNV-CLI'})
    # A perna Banco e Banco x Lawton (73760009 x 00041007), e o Live Position
    # traz o MESMO contrato nas duas visoes — a do Lawton com a conta `41007`.
    pos_bco = dict(NDF_POS, Contrato='26E00000BCO', **{
        'Taxa Forward': '108.985', 'Valor Base no registro': '100,000.00', 'Valor Antecipado': '0.00',
        'Codigo da Contraparte': '41007', 'Nome da Contraparte': 'LAWTON FIM',
        'CPF/CNPJ da Contraparte': '', 'Descricao da posicao do Participante': 'VENDEDOR',
        'Codigo Identificador': 'D5NQ-HMNV-BCO'})
    pos_law = dict(pos_bco, **{'Codigo da Parte': '41007', 'Codigo da Contraparte': '73760.00-9',
                               'Nome da Contraparte': 'BANCO J.P. MORGAN S/A',
                               'Descricao da posicao do Participante': 'COMPRADOR'})
    CONTAS['00041007'] = 'LAWTON'
    R._lpndf_collect = _collect(NDF_COLS, [pos_cli, pos_law, pos_bco])
    n_sino = len(sino)
    st, j = _up(pg_ndf['api'], 'CSN unwind.eml', eml, dry=True)
    rows = j.get('rows') or []
    check('le as duas pernas (Client e Banco), a JPMOCC fica de fora',
          st == 200 and len(rows) == 2, (st, j.get('code'), len(rows)))
    cli, bco = (rows + [{}, {}])[:2]
    check('Deal ID = o Codigo Identificador da posicao (nunca o Risk Deal ID)',
          (cli.get('DealID'), bco.get('DealID')) == ('D5NQ-HMNV-CLI', 'D5NQ-HMNV-BCO'),
          (cli.get('DealID'), bco.get('DealID')))
    check('B3 ID de cada perna pelo Live Position (strike + original)',
          (cli.get('Contract'), bco.get('Contract')) == ('26E00000CLI', '26E00000BCO'),
          (cli.get('Contract'), bco.get('Contract')))
    check('   Banco x Lawton nas duas visoes: um contrato so, na visao do Banco',
          (bco.get('PartyAccount'), bco.get('Comprado')) == ('73760009', False),
          (bco.get('PartyAccount'), bco.get('Comprado'), bco.get('Warnings')))
    # O B2B: as DUAS pontas sao nossas, e cada uma lanca a sua visao na B3
    # (mesa, 28/09/2026) — sem o arquivo do Lawton a antecipacao fica pela metade.
    fs = PC.arquivos(pg_ndf, dict(bco, MyNumber='1234567890'), '20260928')
    check('B2B Banco x Lawton: gera a visao do Banco E a do Lawton',
          [f['file_name'] for f in fs] == ['UNWIND_NDF_COMMODITIES_BANCO.txt',
                                           'UNWIND_NDF_COMMODITIES_LAWTON.txt'],
          [f['file_name'] for f in fs])
    if len(fs) == 2:
        _v = {f['view']: {c['field']: c['value'] for c in f['fields']} for f in fs}
        _papel = [k for k in _v['JPM'] if k.startswith('Papel')]
        _parte = [k for k in _v['JPM'] if k.startswith('Lançamento do Participante')]
        check('   na visao do Lawton as contas trocam e o lado inverte',
              (_v['LAWTON'][_parte[0]], _v['LAWTON']['Contraparte'],
               _v['LAWTON'][_papel[0]] != _v['JPM'][_papel[0]])
              == (_v['JPM']['Contraparte'], _v['JPM'][_parte[0]], True),
              (_v['JPM'], _v['LAWTON']))
        check('   e o header e do participante Lawton',
              'INTRAGLAWTONFDO' in fs[1]['header'], fs[1]['header'])
    fc = PC.arquivos(pg_ndf, dict(cli, MyNumber='1234567890'), '20260928')
    check('contra cliente (conta que nao e nossa): um arquivo so', len(fc) == 1,
          [f['file_name'] for f in fc])
    _omni = dict(bco, MyNumber='1234567890', CptyAccount='73760102')
    check('conta GUARDA-CHUVA na contraparte nao vira espelho',
          len(PC.arquivos(pg_ndf, _omni, '20260928')) == 1)
    check('Pre FWD Rate = 0 e as datas do e-mail',
          cli.get('PreFWDRate') == 0.0 and cli.get('TradeDate') == '2026-05-13', cli)
    # A grade mostra o numero do E-MAIL (mesa, 28/09/2026): refeito pelo FV USD
    # e pelo PV BRL, ela dizia 96,84626 e 5,20887 onde o e-mail diz 96.85 e 5.2087.
    check('Unwind Strike e FX Rate como vieram no e-mail (96.85, 5.2087)',
          (cli.get('TerminationRate'), cli.get('FXRate')) == (96.85, 5.2087),
          (cli.get('TerminationRate'), cli.get('FXRate')))
    check('Client Receives: o banco PAGA, resultado negativo',
          (cli.get('Result'), cli.get('Direction')) == (-6270582.12, 'PAY'),
          (cli.get('Result'), cli.get('Direction')))
    # 100.000 x (96,85 - 108,885) x 5,2087 = -6.268.670,45 contra o PV de
    # -6.270.582,12: nao fecha, e a coluna do OTC Tracker diz a conta dele.
    check('   conta com os numeros do e-mail nao fecha: Check NOK e o calculado na coluna',
          cli.get('Check') == 'NOK' and cli.get('CalcResult') == -6268670.45,
          (cli.get('Check'), cli.get('CalcResult')))
    check('Banco vendeu e o preco caiu: RECEBE',
          (bco.get('Result'), bco.get('Direction')) == (6321326.69, 'RECEIVE'),
          (bco.get('Result'), bco.get('Direction')))
    # 1.213.500 x 5,2087 = 6.320.757,45: o PV do e-mail pede FX 5,20917, que NAO
    # arredonda para o 5.2087 exibido. A celula vence e a linha diz que nao fecha.
    check('   FX que nao arredonda para o exibido: fica o exibido, e o Check acusa',
          bco.get('FXRate') == 5.2087 and bco.get('Check') == 'NOK'
          and bco.get('CalcResult') == 6320757.45,
          (bco.get('FXRate'), bco.get('Check'), bco.get('CalcResult')))
    check('dry-run do e-mail nao toca o sino', len(sino) == n_sino)
    # O trecho colado como UMA tabela, um cabecalho `Leg` por perna: a perna
    # Banco nao tem o Risk Deal ID, e lida pelo cabecalho do Client saia com as
    # colunas deslocadas (strike, quantidade e FX errados).
    uma = ('<table>' + ''.join(
        '<tr>' + ''.join(_td(c) for c in l) + '</tr>' for l in (
            [cab_cli, ['Client', '13-May-26', fix, 'D5NQ-HMNV', 'Client Sells', '100,000',
                       '108.885', '100,000', '96.85', '1,203,874.00', '5.2087',
                       '6,270,582.12', 'Client<br>Receives', 'Full'], [''],
             cab_bco, ['Banco', '13-May-26', fix, 'BJPM Sells', '100,000', '108.985',
                       '100,000', '96.85', '1,213,500.00', '5.2087', '6,321,326.69'], [''],
             cab_occ, ['JPMOCC', '13-May-26', fix, 'JPMOCC Sells', '100,000', '108.985',
                       '100,000', '96.85', '1,213,500.00', '1,213,236.00']])) + '</table>')
    eml1 = ('MIME-Version: 1.0\r\nContent-Type: text/html; charset=utf-8\r\n\r\n'
            '<html><body>' + uma + '</body></html>').encode('utf-8')
    st, j1 = _up(pg_ndf['api'], 'uma-tabela.eml', eml1, dry=True)
    b1 = ((j1.get('rows') or [{}, {}]) + [{}, {}])[1]
    check('uma tabela so: a perna Banco le o SEU cabecalho',
          (b1.get('Strike'), b1.get('UnwoundNotional'), b1.get('FXRate'), b1.get('Result'))
          == (108.985, 100000.0, 5.2087, 6321326.69),
          (b1.get('Strike'), b1.get('UnwoundNotional'), b1.get('FXRate'), b1.get('Result')))
    # O strike registrado da perna Banco tem mais casas do que o Excel exibe
    # (108.98537 aparece 108.985): comparado exato, "nenhum contrato casa".
    pos_bco5 = dict(pos_bco, **{'Taxa Forward': '108.98537'})
    pos_law5 = dict(pos_law, **{'Taxa Forward': '108.98537'})
    R._lpndf_collect = _collect(NDF_COLS, [pos_cli, pos_law5, pos_bco5])
    st, j5 = _up(pg_ndf['api'], 'uma-tabela.eml', eml1, dry=True)
    b5 = ((j5.get('rows') or [{}, {}]) + [{}, {}])[1]
    check('strike ARREDONDADO no e-mail casa com o da posicao (candidato unico)',
          b5.get('Contract') == '26E00000BCO',
          (b5.get('Contract'), b5.get('Strike'), b5.get('Warnings')))
    check('   e a grade fica com o strike e a Unwind Strike do E-MAIL',
          (b5.get('Strike'), b5.get('TerminationRate')) == (108.985, 96.85),
          (b5.get('Strike'), b5.get('TerminationRate')))
    check('   sem marca interna na linha', '_shown' not in b5 and '_recap' not in b5,
          sorted(k for k in b5 if k.startswith('_')))
    pos_bco9 = dict(pos_bco, **{'Taxa Forward': '109.40'})
    pos_law9 = dict(pos_law, **{'Taxa Forward': '109.40'})
    R._lpndf_collect = _collect(NDF_COLS, [pos_cli, pos_law9, pos_bco9])
    st, j9 = _up(pg_ndf['api'], 'uma-tabela.eml', eml1, dry=True)
    perto = [w for w in j9.get('warnings') or [] if w.get('code') == 'unwind_match_none_near']
    check('sem contrato: o aviso diz o MAIS PERTO e o valor dos dois lados',
          len(perto) == 1 and perto[0]['params'].get('contrato') == '26E00000CLI'
          and perto[0]['params'].get('campo') == 'Strike'
          and perto[0]['params'].get('planilha') == '108.985'
          and perto[0]['params'].get('posicao') == '108.885',
          perto or [w.get('code') for w in j9.get('warnings') or []])
    R._lpndf_collect = _collect(NDF_COLS, [pos_cli, pos_law, pos_bco])
    so_occ = ('MIME-Version: 1.0\r\nContent-Type: text/html\r\n\r\n<html><body>'
              + _tab(cab_occ, [['JPMOCC', '13-May-26', fix, 'JPMOCC Sells', '100,000', '108.985',
                                '100,000', '96.85', '1,213,500.00', '1,213,236.00']])
              + '</body></html>').encode('utf-8')
    st, j = _up(pg_ndf['api'], 'so-occ.eml', so_occ, dry=True)
    check('so a perna JPMOCC: recusa por codigo',
          st == 400 and j.get('code') == 'unwind_recap_no_legs', (st, j.get('code')))

    # O Edit que muda dado ECONOMICO refaz as contas (mesa, 28/09/2026): o
    # Result pela formula do termo e a Direction pelo sinal; Result digitado
    # no mesmo Save vence, e o Check confere.
    kinds = catalog.column_kinds(pg_ndf)
    l_ed = dict(cli, TerminationRate=96.84626, FXRate=6270582.12 / 1203874)
    PC._refazer_calculos(pg_ndf, l_ed, {'TerminationRate', 'FXRate'}, kinds)
    check('edit economico: Result e Direction refeitos',
          (l_ed.get('Result'), l_ed.get('Direction')) == (-6270582.12, 'PAY'),
          (l_ed.get('Result'), l_ed.get('Direction')))
    l_ed2 = dict(cli, Result=-1.0, TerminationRate=110.0)
    PC._refazer_calculos(pg_ndf, l_ed2, {'TerminationRate', 'Result'}, kinds)
    check('   Result digitado no mesmo Save vence', l_ed2.get('Result') == -1.0, l_ed2.get('Result'))
    l_ed3 = dict(cli, Result=-1.0)
    PC._refazer_calculos(pg_ndf, l_ed3, {'Counterparty'}, kinds)
    check('   campo nao economico nao refaz nada', l_ed3.get('Result') == -1.0, l_ed3.get('Result'))
    check('   mesmo_valor: 100000 gravado = 100,000.00 do Save',
          PD.mesmo_valor(100000.0, '100,000.00') and not PD.mesmo_valor(96.85, 96.84626))

    print('\n== 12. NDF Commodities: esteira, Termo e liquidacao (a regra da Fase 1) ==')
    from apps.pages.features.unwinds import commands as F1C
    from apps.pages.features.unwinds import queries as F1Q
    from apps.pages.features.unwinds import domain as F1D
    pc_salvos, mc_apagados = [], []

    class _MC:                              # a esteira, sem banco
        TYPE_FOLDER = getattr(R._mc_mod, 'TYPE_FOLDER', {})
        find_row = staticmethod(lambda k: None)
        row_untouched = staticmethod(lambda k: True)
        delete_row = staticmethod(lambda k: mc_apagados.append(k))
    mc_orig, pcsave_orig = R._mc_mod, R._pc_save_from_deal
    pcdel_orig = R._pc_delete_trade_number
    R._mc_mod = _MC
    R._pc_save_from_deal = lambda deal, *a, **k: pc_salvos.append((deal, a, k))
    R._pc_delete_trade_number = lambda k: None
    # A perna do fundo vai para a Intrag > Unwind no IMPORT (mesa, 28/09/2026:
    # nem toda recompra e registrada na B3 pelo OTC Tracker), pela porta da
    # Fase 1; a do cliente nao.
    intrag_salvas = []

    class _IE:
        @staticmethod
        def _save_intrag_unwind_entry(**kw):
            intrag_salvas.append(kw)
            return {'_deal': kw.get('deal')}, []
    ie_orig = R._intrag_engine
    R._intrag_engine = lambda: _IE
    try:
        st, j = _up(pg_ndf['api'], 'CSN unwind.eml', eml)
        rows = j.get('rows') or []
        check('import grava as duas pernas', st == 200 and len(rows) == 2, (st, j.get('code')))
        check('   a perna do fundo vai para a Intrag JA NO IMPORT, com o Deal ID e o LAWTON',
              [(k.get('deal'), k.get('fundo')) for k in intrag_salvas]
              == [('D5NQ-HMNV-BCO', 'LAWTON')],
              [(k.get('deal'), k.get('fundo')) for k in intrag_salvas])
        k0 = intrag_salvas[0] if intrag_salvas else {}
        check('   Banco recebe -> o fundo PAGA; valores do contrato; dia da recompra',
              (k0.get('credor'), k0.get('b3_id'), k0.get('valor_base_recomprado'),
               k0.get('valor_liquidacao'), str(k0.get('data_recompra'))[:10])
              == (False, '26E00000BCO', 100000.0, 6321326.69, '2026-09-21'), k0)
        fontes = [(d.get('Deal'), a[0] if a else '') for d, a, _k in pc_salvos]
        # Termo e Pending Confirmation so contra o CLIENTE (mesa, 28/09/2026,
        # §580): a perna Banco x Lawton (o B2B) nao entra na esteira.
        check('   a perna do fundo, que nao estava na esteira, nao dispara delete la',
              'D5NQ-HMNV-BCO' not in mc_apagados, mc_apagados)
        check('Pending Confirmation + esteira no IMPORT, so a perna do CLIENTE',
              fontes == [('D5NQ-HMNV-CLI', 'UNWIND NDF COMM')], fontes)
        d0 = pc_salvos[0][0] if pc_salvos else {}
        check('   deal: B3 ID, mercadoria no eixo, reais e FX para o XML',
              (d0.get('B3_ID'), d0.get('Currency'), d0.get('UnwoundBRL'), d0.get('XmlCcy'))
              == ('26E00000CLI', 'CTZ6', 6270582.12, 'USD'), d0)
        deals = F1C.confirmation_deals('2026-09-21')
        check('a segregacao do Monitor le a recompra do cliente, nao a do fundo',
              'D5NQ-HMNV-CLI' in {d.get('Deal') for d in deals}
              and 'D5NQ-HMNV-BCO' not in {d.get('Deal') for d in deals},
              [d.get('Deal') for d in deals])
        grupo = F1Q.termo_grupo('2026-09-21', '', 'CTZ6')
        trs, _av = F1D.termo_rows(grupo)
        # (a recompra da secao 3 esta no mesmo dia, sem Deal ID: vale o `_id`)
        check('Termo: o grupo pela mercadoria, Nº da Confirmacao = Deal ID, sem o fundo',
              'D5NQ-HMNV-CLI' in {r['numConf'] for r in trs}
              and 'D5NQ-HMNV-BCO' not in {r['numConf'] for r in trs},
              [r.get('numConf') for r in trs])
        cli_tr = next((r for r in trs if r['numConf'] == 'D5NQ-HMNV-CLI'), {})
        check('   Total, valor em modulo e pagador pelo sinal (o banco paga -> Parte A)',
              (cli_tr.get('resilicao'), cli_tr.get('valorResilicao'), cli_tr.get('pagador'))
              == (F1D.RESILICAO_TOTAL, 'R$ 6.270.582,12', F1D.PAGADOR_PARTE_A), cli_tr)
        check('   Valor Base Liquidado so com o numero (sem o codigo da commodity)',
              cli_tr.get('valorBaseLiq') == '100.000,00', cli_tr.get('valorBaseLiq'))
        _cli_l = next(l for l in grupo if l.get('AthenaID') == 'D5NQ-HMNV-CLI')
        _parc = dict(_cli_l, OriginalNotional=300000.0, UnwoundBefore=0.0, Balance=300000.0)
        _pr, _ = F1D.termo_linha(_parc)
        check('   Novo Valor Base da parcial tambem so com o numero',
              (_pr.get('resilicao'), _pr.get('novoValorBase'))
              == (F1D.RESILICAO_PARCIAL, '200.000,00'), (_pr.get('resilicao'), _pr.get('novoValorBase')))
        F1C.termo_carimbar(['D5NQ-HMNV-CLI'], '2026-09-21', '/x/t.doc', '/x/t.pdf', 'lnk', 'A000001')
        e_cli = next((e for e in PQ.entries(pg_ndf, '2026-09-21')
                      if e.get('DealID') == 'D5NQ-HMNV-CLI'), {})
        check('o Termo salvo carimba a linha do catalogo', e_cli.get('TermoPdf') == '/x/t.pdf',
              e_cli.get('TermoPdf'))
        liq = F1C.commodity_settlement_rows('2026-09-21')
        check('liquidacao do dia: as duas, no sinal do Summary',
              sorted((u['_chave'], u['_settlement']) for u in liq
                     if u['_chave'].startswith('D5NQ'))
              == [('D5NQ-HMNV-BCO', 6321326.69), ('D5NQ-HMNV-CLI', -6270582.12)],
              [(u.get('_chave'), u.get('_settlement')) for u in liq])
        R._opb3_settle_rows = lambda ref: []
        R._ndfadv_otm_by_suffix = lambda ref: ({}, {})
        R._ndfsum_refdata_spn = lambda: {}
        R._cpd_load = lambda: []
        with app.test_request_context():
            adv = R._ndfadv_collect(datetime(2026, 9, 21), with_ir=False)
        u_adv = [r for r in adv if r.get('unwind') and r['internal_id'].startswith('D5NQ')]
        check('Settlement Advice (e com ele Trade Level, Summary e TED): UNWIND',
              len(u_adv) == 2 and all(r['settle_type'] == 'UNWIND' for r in u_adv)
              and {r['internal_id'] for r in u_adv} == {'D5NQ-HMNV-CLI', 'D5NQ-HMNV-BCO'},
              [(r.get('internal_id'), r.get('settle_type')) for r in u_adv])
        a_cli = next((r for r in u_adv if r['internal_id'] == 'D5NQ-HMNV-CLI'), {'cells': []})
        check('   o aviso diz o FX, o preco e a quantidade da recompra',
              a_cli['cells'][5:8] == ['5.2087', '96.85', '100,000.00']
              and a_cli.get('apurado') == -6270582.12, a_cli['cells'])
        # O Print Advice do Other Products: a recompra passa pelo bloqueador de
        # linha incompleta e sai no aviso da contraparte (o NDF Summary a tirava
        # do lote e respondia "Nothing to Generate" — §568).
        from apps.pages import otc_emails as _oe
        hdr = R._ndfadv_email_headers()
        em = [dict(r, cells=R._ndfadv_unwind_email_cells(r),
                   headers=list(R._NDFADV_UNWIND_EMAIL_HEADERS)) for r in u_adv]
        vivas, bloq = R._opsadv_block_incomplete('ndf', em, hdr)
        drafts = _oe.build_ndfc_settlement_emails(vivas, hdr, '21/09/2026')
        d_cli = next((d for d in drafts if d.get('counterparty') == a_cli.get('counterparty')), {})
        check('   e gera o aviso do Other Products (nao bloqueia, nao some)',
              not bloq and bool(d_cli), (bloq, [d.get('counterparty') for d in drafts]))
        subj = d_cli.get('subject', '')
        check('   aviso da recompra: (Recompra) no inicio e + Callback depois do produto',
              subj.startswith('(Recompra) Liquidação de Operação de Derivativo '
                              '(Termo de Commodities) + Callback - 21/09/2026'), subj)
        check('   em alta prioridade no .eml',
              d_cli.get('importance') == 'high'
              and b'Importance: High' in _oe.build_eml_bytes(d_cli), d_cli.get('importance'))
        html = d_cli.get('html', '')
        check('   tabela com quantidade recomprada, taxa pre e taxa de recompra',
              all(h in html for h in ('Quantidade Recomprada', 'Taxa Pré', 'Taxa de Recompra',
                                      '100,000.00', '96.85'))
              and 'Cotação Mercadoria' not in html, subj)
        # O Send NAO grava a Intrag de novo: ela nasceu no import.
        del intrag_salvas[:]
        e_bco = next((e for e in PQ.entries(pg_ndf, '2026-09-21')
                      if e.get('DealID') == 'D5NQ-HMNV-BCO'), {})
        st, j = _post(pg_ndf['api'] + '/send-conecta',
                      {'items': [{'id': e_bco.get('_id')}], 'date': '2026-09-21'})
        check('send da perna do fundo', st == 200, (st, j))
        check('   e o Send nao toca a Intrag', intrag_salvas == [], intrag_salvas)
        # Reimport com a perna do fundo JA ENVIADA: a linha e mantida como esta,
        # e mesmo assim vai a Intrag — era o caso da instancia (a recompra
        # enviada antes da regra do import nunca chegava la).
        st, j = _up(pg_ndf['api'], 'CSN unwind.eml', eml)
        check('reimport com a perna do fundo Sent: mantida e vai a Intrag',
              st == 200 and j.get('skipped') == 1
              and [k.get('deal') for k in intrag_salvas] == ['D5NQ-HMNV-BCO'],
              (st, j.get('skipped'), [k.get('deal') for k in intrag_salvas]))
        rid = e_cli.get('_id')
        st, j = _post(pg_ndf['api'] + '/delete', {'id': rid, 'date': '2026-09-21'})
        check('delete tira da esteira e do Pending Confirmation',
              st == 200 and 'D5NQ-HMNV-CLI' in mc_apagados, (st, j, mc_apagados))
    finally:
        R._intrag_engine = ie_orig
        R._mc_mod, R._pc_save_from_deal = mc_orig, pcsave_orig
        R._pc_delete_trade_number = pcdel_orig

    print('\n== 13. Mapping B3 ID: retorno com SUCESSO + B3 ID vira Success ==')
    ret = os.path.join(tmp, 'Return')
    os.makedirs(ret, exist_ok=True)
    ret_orig = R.RETURN_PATH
    R.RETURN_PATH = ret
    try:
        # O layout REAL do retorno (exemplo da mesa, 28/09/2026): cabecalho,
        # B3 ID no Codigo IF, status EXECUCAO OK e o TER 0014 ecoado.
        HDR = 'Numero da Linha Original;Codigo IF;Cod. Oper. Cetip;Descricao da Mensagem;Texto da Linha Original\n'
        ANT = 'TER  1001414636617479737600091737601022602277343000000000003000020260928\n'
        REG = 'TER  1000314636617479737600091737601022602277343000000000003000020260928\n'
        f_ok = os.path.join(ret, 'retorno_unwind.txt')
        with open(f_ok, 'w', encoding='cp1252') as fh:
            fh.write(HDR + '00000000000002;26E00000BCO;2026092821484501;EXECUCAO OK;' + ANT)
        f_outro = os.path.join(ret, 'retorno_misto.txt')
        with open(f_outro, 'w', encoding='cp1252') as fh:
            fh.write(HDR + '00000000000002;26E00000BCO;2026092821484501;EXECUCAO OK;' + ANT
                     + '00000000000003;26E99999999;2026092821484502;EXECUCAO OK;' + REG)
        f_quase = os.path.join(ret, 'retorno_registro.txt')
        with open(f_quase, 'w', encoding='cp1252') as fh:
            fh.write(HDR + '00000000000002;26E00000BCOX;2026092821484501;EXECUCAO OK;' + ANT)
        from apps.pages.features.unwinds import domain as _UD
        check('o parser: registro (0003) NAO e antecipacao; 0014 e',
              (_UD.e_antecipacao(REG), _UD.e_antecipacao(ANT)) == (False, True))
        check('   linha com erro da B3 nao conta; cabecalho nao e dado',
              _UD.b3_ids_com_sucesso(HDR + '00000000000002;26E1;x;CAMPO 9 INVALIDO;' + ANT
                                     + '00000000000003;26E2;x;EXECUCAO OK;' + REG,
                                     ['26E1', '26E2'])[0] == set())
        from apps.pages.features.new_deals import entrypoint as _NDE
        check('o Mapping do New Deals ignora a linha de antecipacao (nao apaga o retorno)',
              (_NDE._e_antecipacao('00000000000002;26E1;x;EXECUCAO OK;' + ANT),
               _NDE._e_antecipacao('00000000000002;26E1;x;EXECUCAO OK;' + REG)) == (True, False))
        st, j = _post(pg_ndf['api'] + '/mapping-b3', {'date': '2026-09-22'})
        check('mapping responde e vira UMA recompra', st == 200
              and [m['contract'] for m in j.get('mapped') or []] == ['26E00000BCO'], (st, j))
        e_bco2 = next((e for e in PQ.entries(pg_ndf, '2026-09-21')
                       if e.get('DealID') == 'D5NQ-HMNV-BCO'), {})
        check('   a linha fica Success', e_bco2.get('Status') == 'Success', e_bco2.get('Status'))
        check('   o retorno todo nosso e apagado; o que tem linha de outro fica',
              not os.path.exists(f_ok) and os.path.exists(f_outro), os.listdir(ret))
        check('   B3 ID parecido nao casa (o arquivo fica)', os.path.exists(f_quase))
        st, j = _post(pg_ndf['api'] + '/mapping-b3', {'date': '2026-09-22'})
        check('   segunda passada nao remapeia', st == 200 and not j.get('mapped'), j)
        st, j = _post(pg_ndf['api'] + '/delete', {'id': e_bco2.get('_id'), 'date': '2026-09-21'})
        check('   Success nao se apaga (e registro na B3)', st == 409, (st, j))
        st, j = _post('/api/unwinds/ndf/fx/mapping-b3', {'date': '2026-09-22'})
        check('a rota da NDF FX tambem mapeia', st == 200 and j.get('success'), (st, j))
        R.RETURN_PATH = os.path.join(tmp, 'nao-existe')
        st, j = _post(pg_ndf['api'] + '/mapping-b3', {})
        check('pasta de retorno ausente responde com codigo',
              st == 400 and j.get('code') == 'unwind_return_folder_missing', (st, j))
    finally:
        R.RETURN_PATH = ret_orig

    print('\n%s' % ('TUDO OK' if not FALHAS else '%d FALHA(S): %s' % (len(FALHAS), FALHAS)))
    return 1 if FALHAS else 0


if __name__ == '__main__':
    sys.exit(main())
