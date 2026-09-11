# -*- coding: utf-8 -*-
"""Confirmacao de NDF da JPMORGAN CHASE (MGT) contra cliente — Vanilla e FWD
Start no documento proprio da MGT (HANDOFF §453).

O que este teste prende, e por que cada coisa nao daria erro sozinha:

  1. a FAMILIA: so deals com LE = MGT entram (`_conf_load_ndfmgt`), vindos das
     DUAS paginas, e o FWD Start do BANCO deixa de listar os de MGT — senao a
     mesma operacao geraria dois papeis, um por card;
  2. o EIXO: um grupo por contraparte x moeda x PRODUTO (vanilla / fwd-start),
     porque a pasta do Electronic Inventory e o tipo da confirmacao;
  3. as colunas do Anexo I: no Vanilla a Taxa Forward e o Rate e as duas
     colunas do forward start saem "Nao Aplicavel"; no FWD Start tudo como no
     documento do BANCO;
  4. a Parte A FIXA na filial brasileira da JPMORGAN CHASE, e o cliente nas
     tres assinaturas — o template e o da mesa, com as lacunas preenchidas;
  5. o Generate do Monitor: a linha da esteira com Legal Entity da MGT (Vanilla
     ou FWD Start) abre o editor MGT, e a do BANCO segue no editor de sempre;
  6. o save: Word + PDF na pasta do TIPO da familia (NDF VANILLA / NDF FWD
     START), o PDF saindo do MESMO HTML do .doc.

Nao encosta em dado real: os day-files vao para tempfiles, o CGD/Inventory/
FepWeb/esteira sao stubs e as raizes do modulo voltam no finally.
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages import routes as R                                       # noqa: E402
from apps.pages.platform import confirmations as PC                      # noqa: E402
from apps.pages.platform import manual_confirmation as MC                # noqa: E402

fails = []
OUT = os.environ.get('MGT_CONF_OUT', '')                                  # PDF para conferência visual


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


VAN_MGT = {
    'Status': 'Success', 'Deal': 'V1', 'B3_ID': '26G09999901', 'LE': 'MGT',
    'TradeDate': '05/08/2026', 'SettlementDate': '05/11/2026', 'SPN': '1',
    'Acronym': 'SUZANO', 'Client': 'SUZANO SA', 'TaxID': '16404287000155',
    'FirstFixingDate': '04/11/2026', 'LastFixingDate': '04/11/2026',
    'Direction': 'SELL', 'QuantityCurrency': 'USD', 'OtherQuantityCurrency': 'BRL',
    'Notional': '1,000,000.00', 'Rate': '5.4321',
}
VAN_JPM = dict(VAN_MGT, Deal='V2', B3_ID='26G09999902', LE='JPM', Acronym='RAIZEN', Client='RAIZEN SA')
FWD_MGT = {
    'Status': 'Success', 'Deal': 'F1', 'B3_ID': '26G04736337', 'LE': 'MGT',
    'TradeDate': '05/08/2026', 'SettlementDate': '28/08/2026', 'SPN': '1',
    'Acronym': 'SUZANO', 'Client': 'SUZANO SA', 'TaxID': '16404287000155',
    'FirstFixingDate': '27/08/2026', 'LastFixingDate': '27/08/2026',
    'StrikeSetDate': '30/07/2026', 'StrikeSetOffset': '0,0337',
    'Direction': 'SELL', 'QuantityCurrency': 'USD', 'OtherQuantityCurrency': 'BRL',
    'Notional': '198,723,470.91', 'Rate': '',
}
FWD_JPM = dict(FWD_MGT, Deal='F2', B3_ID='26G04736338', LE='JPM')

TMP = tempfile.mkdtemp(prefix='mgtconf-')
EI = os.path.join(TMP, 'ei')
cfg_v, cfg_f = R._GENERIC_ND_PRODUCTS['vanilla'], R._GENERIC_ND_PRODUCTS['fwd-start']
real = (cfg_v['dir'], cfg_f['dir'], PC._conf_cgd_lookup, R._ei_resolve_client_dir,
        R._conf_pc_set_fepweb, R._mc_stamp_generated, R._create_notification)


def _write(deals, cfg, suffix):
    d = os.path.join(cfg['dir'], '2026', '08')
    os.makedirs(d, exist_ok=True)
    with io.open(os.path.join(d, '20260805' + suffix), 'w', encoding='utf-8') as fh:
        json.dump(deals, fh, ensure_ascii=False)


def outs(html):
    return dict(re.findall(r'id="out_(\w+)">([^<]*)<', html))


def cells(html):
    return dict(re.findall(r'data-k="(\w+)">([^<]*)<', html))


try:
    cfg_v['dir'] = os.path.join(TMP, 'van')
    cfg_f['dir'] = os.path.join(TMP, 'fwd')
    _write([VAN_MGT, VAN_JPM], cfg_v, '_ndfvanilla.json')
    _write([FWD_MGT, FWD_JPM], cfg_f, '_ndffwdstart.json')
    R._conf_cgd_lookup = PC._conf_cgd_lookup = lambda first: '28 de Maio de 2008'
    R._ei_resolve_client_dir = lambda name, create=False: os.path.join(EI, name)
    R._conf_pc_set_fepweb = lambda deals, num: 0
    stamped = []
    R._mc_stamp_generated = lambda picked, product, link='': stamped.append((product, len(picked), link))
    R._create_notification = lambda *a, **k: None

    REF = datetime(2026, 8, 5)
    print('== 1. a familia: so MGT, das duas paginas ==')
    loaded = R._conf_load_ndfmgt(REF)
    check('dois deals de MGT (um de cada pagina)', sorted((d['Deal'], d['_conf_src']) for d in loaded),
          [('F1', 'fwd-start'), ('V1', 'vanilla')])
    check('o FWD Start do BANCO nao lista mais o de MGT',
          [d['Deal'] for d in R._conf_load_ndffwdstart(REF)], ['F2'])

    print('\n== 2. o eixo: contraparte x moeda x produto ==')
    groups, _st, _tot = R._conf_mgt_groups(REF)
    check('um grupo por produto', [(g['acronym'], g['mercadoria'], g['family']) for g in groups],
          [('SUZANO', 'USD', 'fwd-start'), ('SUZANO', 'USD', 'vanilla')])

    from apps import create_app
    from apps.config import DebugConfig
    app = create_app(DebugConfig)
    cl = app.test_client()
    with cl.session_transaction() as s:
        s['authenticated'] = True; s['user_sid'] = 'T000000'; s['user_name'] = 'T'
        s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    api = (cl.get('/api/new-deals/ndf-mgt/confirmations?date=2026-08-05').get_json() or {}).get('groups') or []
    check('a API do Monitor lista os dois grupos com o link do editor',
          sorted((g['family'], g['url'].split('?')[0]) for g in api),
          [('fwd-start', '/confirmation/ndf-mgt/fwd-start'), ('vanilla', '/confirmation/ndf-mgt/vanilla')])
    api_fwd = (cl.get('/api/new-deals/ndf-fwdstart/confirmations?date=2026-08-05').get_json() or {}).get('groups') or []
    check('e o card do FWD Start do BANCO fica so com o do BANCO', [g['count'] for g in api_fwd], [1])

    print('\n== 3. as colunas do Anexo I ==')
    hv = cl.get('/confirmation/ndf-mgt/vanilla?date=2026-08-05&acronym=SUZANO&mercadoria=USD').data.decode('utf-8')
    cv = cells(hv)
    check('Vanilla: Taxa Forward e o Rate', cv.get('taxaFwd'), '5,43210000')
    check('Vanilla: sem Data de Verificacao da Taxa Forward', cv.get('dtVerifFwd'), 'Não Aplicável')
    check('Vanilla: sem Pontos de Termo', cv.get('pontosTermo'), 'Não Aplicável')
    check('Vanilla: No = B3 ID, Data Efetiva = Trade Date, vencimento', (cv.get('num'), cv.get('dtEfetiva'), cv.get('dtVenc')),
          ('26G09999901', '05/08/2026', '05/11/2026'))
    hf = cl.get('/confirmation/ndf-mgt/fwd-start?date=2026-08-05&acronym=SUZANO&mercadoria=USD').data.decode('utf-8')
    cf = cells(hf)
    check('FWD Start: as tres colunas do forward start', (cf.get('pontosTermo'), cf.get('dtVerifFwd'), cf.get('taxaFwd')),
          ('0,0337', '30/07/2026', 'Não Aplicável'))
    r404 = cl.get('/confirmation/ndf-mgt/strike-me?date=2026-08-05&acronym=SUZANO&mercadoria=USD')
    check('familia desconhecida e 404', r404.status_code, 404)

    print('\n== 4. a Parte A fixa e o cliente nas assinaturas ==')
    o = outs(hv)
    check('Parte A = JPMORGAN CHASE filial brasileira', o.get('partea_nome'), 'J.P. Morgan Chase Bank, N.A. – Filial Brasileira')
    check('CNPJ da Parte A', o.get('partea_cnpj'), '46.518.205/0001-64')
    check('Parte B e o cliente, com CNPJ formatado', (o.get('parteb_nome'), o.get('parteb_cnpj')), ('SUZANO SA', '16.404.287/0001-55'))
    check('o cliente vai para a assinatura', o.get('parteb_nome_assin'), 'SUZANO SA')
    check('Data de Negociacao, extenso e CGD', (o.get('data_neg'), o.get('data_extenso'), o.get('cgd_date')),
          ('05/08/2026', '05 de Agosto de 2026', '28 de Maio de 2008'))
    check('a clausula do BANCO como agente esta no documento', 'como agente\nde registro' in hv or 'agente de registro' in hv.replace('\n', ' '), True)
    check('o editor diz a familia', 'Editor MGT' in hv and 'NDF Vanilla' in hv, True)
    check('as tres assinaturas', all(x in hv for x in ('MORGAN CHASE BANK, N.A.', 'BANCO J.P. MORGAN S.A.', 'out_parteb_nome_assin')), True)

    print('\n== 5. o Generate do Monitor escolhe o editor pela entidade ==')
    LE_MGT = 'JPMORGAN CHASE BANK, N.A. - SAO PAULO BRANCH'
    url, why = R._mc_generate_url({'Produto': 'NDF VANILLA', 'LOB': 'CEM', 'Legal Entity': LE_MGT,
                                   'Data Operação': '05/08/2026', 'Trade ID': 'V1'}, ['V1'])
    check('Vanilla MGT abre o editor MGT', url.split('?')[0], '/confirmation/ndf-mgt/vanilla')
    url, why = R._mc_generate_url({'Produto': 'NDF FWD START', 'LOB': 'CEM', 'Legal Entity': LE_MGT,
                                   'Data Operação': '05/08/2026', 'Trade ID': '26G04736337'}, ['26G04736337'])
    check('FWD Start MGT tambem (chave = B3 ID)', url.split('?')[0], '/confirmation/ndf-mgt/fwd-start')
    url, why = R._mc_generate_url({'Produto': 'NDF FWD START', 'LOB': 'CEM', 'Legal Entity': 'BANCO J.P MORGAN S.A',
                                   'Data Operação': '05/08/2026', 'Trade ID': '26G04736338'}, ['26G04736338'])
    check('FWD Start do BANCO segue no editor de sempre', url.split('?')[0], '/confirmation/ndf-fwdstart/strike-me')
    check('as chaves da esteira: Deal no Vanilla, B3 ID no FWD Start',
          MC._mc_conf_trade_keys([(dict(VAN_MGT, _conf_src='vanilla'), None), (dict(FWD_MGT, _conf_src='fwd-start'), None)], 'ndf-mgt'),
          ['V1', '26G04736337'])

    print('\n== 6. o save: Word + PDF na pasta do tipo ==')
    fields = {k: o.get(k, '') for k in ('num_conf', 'cgd_date', 'partea_nome', 'partea_cnpj', 'parteb_nome', 'parteb_cnpj', 'data_neg', 'data_extenso')}
    rows = json.loads(re.search(r'id="conf-data">(.*?)</script>', hv, re.S).group(1))['rows']
    res = cl.post('/api/confirmation/ndf-mgt/save', json={
        'family': 'vanilla', 'date': '2026-08-05', 'acronym': 'SUZANO', 'mercadoria': 'USD',
        'fields': fields, 'rows': rows}).get_json()
    check('salvou', res.get('success'), True)
    files = res.get('files') or []
    check('na pasta NDF VANILLA do cliente',
          all(os.sep + 'NDF VANILLA' + os.sep in f for f in files[:2]) and files[0].endswith('.doc') and files[1].endswith('.pdf'), True)
    check('os arquivos existem', all(os.path.isfile(f) for f in files[:2]), True)
    check('a esteira foi carimbada pela familia MGT', stamped and stamped[-1][0] == 'ndf-mgt', True)
    check('a validacao e da familia MGT', (res.get('validate_url') or '').startswith('/confirmation/ndf-mgt/validate?'), True)
    if OUT and len(files) > 1:
        shutil.copy(files[1], os.path.join(OUT, 'mgt-vanilla.pdf'))
    doc = io.open(files[0], encoding='utf-8').read()
    check('o .doc e o documento sem o painel', '<div id="editor-panel">' not in doc and 'SUZANO SA' in doc, True)
    res2 = cl.post('/api/confirmation/ndf-mgt/save', json={
        'family': 'fwd-start', 'date': '2026-08-05', 'acronym': 'SUZANO', 'mercadoria': 'USD',
        'fields': fields, 'rows': json.loads(re.search(r'id="conf-data">(.*?)</script>', hf, re.S).group(1))['rows']}).get_json()
    check('o FWD Start MGT vai para a pasta NDF FWD START',
          res2.get('success') and all(os.sep + 'NDF FWD START' + os.sep in f for f in (res2.get('files') or [])[:2]), True)
    val = cl.get(res.get('validate_url') or '/x')
    check('a janela de validacao abre', val.status_code, 200)
finally:
    (cfg_v['dir'], cfg_f['dir'], PC._conf_cgd_lookup, R._ei_resolve_client_dir,
     R._conf_pc_set_fepweb, R._mc_stamp_generated, R._create_notification) = real
    R._conf_cgd_lookup = PC._conf_cgd_lookup
    shutil.rmtree(TMP, ignore_errors=True)

print()
print('FALHAS: %d' % len(fails) if fails else 'tudo ok')
sys.exit(1 if fails else 0)
