# -*- coding: utf-8 -*-
"""O ID de cada confirmação e o NDF Vanilla do Banco asiático/BRL fixed na
esteira (§703).

A regra da equipe (27/10/2026), a MESMA no Pending Confirmation, na esteira, no
Nº do documento e no FepWeb ID: FWD Start e swaps pelo B3 ID; Vanilla, FXO, NDF
e opção de commodities pelo Deal (Athena ID).

O que se prova:
  1. `_generic_nd_vanilla_conf`: asiático (First ≠ Last Fixing) e BRL fixed
     sim; o Vanilla comum não;
  2. o Vanilla do Banco asiático/BRL fixed ganha `source` NDF VANILLA e nasce
     Pending OTC; o comum segue sem esteira;
  3. o gerador do Banco: FWD Start na família `strike-me`, o Vanilla
     asiático/BRL fixed na `vanilla`, o comum e o MGT fora; o Nº é o B3 ID
     num e o Deal no outro;
  4. `_mc_conf_trade_keys`: a regra para cada produto;
  5. o Pending: Vanilla pelo Deal, FWD Start pelo B3 ID — e o FepWeb ID gravado
     pelas chaves da esteira acha as duas linhas (era o Deal para todos, e o
     FWD Start ficava sem o FepWeb ID);
  6. o Generate do Monitor: NDF VANILLA do Banco abre `/ndf-fwdstart/vanilla`,
     o de MGT segue no editor MGT;
  7. a página `/confirmation/ndf-fwdstart/vanilla`: o Nº é o Deal, as colunas
     do forward start saem "Não Aplicável" e o Save manda a família;
  8. todo `_conf_pc_set_fepweb(` dos Saves passa pelo `_mc_conf_trade_keys`.
"""
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.check-share'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


from apps import create_app                                      # noqa: E402
from apps.config import DebugConfig                              # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True
from apps.pages import routes as R                               # noqa: E402
from apps.pages.platform import confirmations as CF              # noqa: E402
from apps.pages.platform import manual_confirmation as MCP       # noqa: E402
from apps.pages.platform import new_deals as ND                  # noqa: E402
from apps.pages.platform import pending_confirmation as PC       # noqa: E402

R._create_notification = lambda *a, **k: None

BASE = {'Status': 'Success', 'Client': 'CLIENTE X', 'Acronym': 'CLIX', 'LE': 'JPM',
        'QuantityCurrency': 'USD', 'OtherQuantityCurrency': 'BRL', 'Notional': '1000000',
        'Direction': 'BUY', 'TradeDate': '2026-10-27', 'SettlementDate': '2027-01-27',
        'LastFixingDate': '2027-01-25', 'Rate': '5.4'}
ASIAN = dict(BASE, Deal='ATH-ASN', B3_ID='26E00000011', FirstFixingDate='2027-01-04')
BRLF = dict(BASE, Deal='ATH-BRL', B3_ID='26E00000012', IsBRRFixed='YES',
            QuantityCurrency='BRL', OtherQuantityCurrency='USD')
PLAIN = dict(BASE, Deal='ATH-PLN', B3_ID='26E00000013', FirstFixingDate='2027-01-25')
MGT_V = dict(ASIAN, Deal='ATH-MGT', B3_ID='26E00000014', LE='MGT')
FWD = dict(BASE, Deal='ATH-FWD', B3_ID='26E00000015', Rate='', StrikeSetDate='2026-11-27')

print('== 1. _generic_nd_vanilla_conf ==')
check('asiático e BRL fixed sim; o comum não',
      [ND._generic_nd_vanilla_conf(d) for d in (ASIAN, BRLF, PLAIN)], [True, True, False])

print('\n== 2. source e Pending Status ==')
check('source: NDF VANILLA para o asiático, o BRL fixed e o MGT; o comum sem',
      [ND._generic_nd_mc_source('vanilla', d) for d in (ASIAN, BRLF, MGT_V, PLAIN)],
      ['NDF VANILLA', 'NDF VANILLA', 'NDF VANILLA', None])
R._pc_signature_pending_status = lambda *a, **k: 'Pending Original'
check('Pending Status: Pending OTC na esteira; o comum pela assinatura',
      [ND._generic_nd_pending_status('vanilla', d) for d in (ASIAN, BRLF, PLAIN)],
      ['Pending OTC', 'Pending OTC', 'Pending Original'])

print('\n== 3. o gerador do Banco ==')
DIA = {'fwd-start': [FWD, dict(FWD, Deal='ATH-FWDM', B3_ID='26E00000016', LE='MGT')],
       'vanilla': [ASIAN, BRLF, PLAIN, MGT_V]}
CF._conf_load_generic_nd = lambda ref, product: [dict(d) for d in DIA.get(product, [])]
REF = datetime(2026, 10, 27)
grupos, _st, _tot = CF._conf_fwdstart_groups(REF)
check('grupos: FWD Start em strike-me, asiático + BRL fixed em vanilla; sem o comum e sem MGT',
      sorted((g['family'], tuple(sorted(g['trades']))) for g in grupos),
      [('strike-me', ('26E00000015', 'ATH-FWD')),
       ('vanilla', ('26E00000011', '26E00000012', 'ATH-ASN', 'ATH-BRL'))])
pv = CF._conf_pick_fwdstart(REF, 'CLIX', 'USD', 'vanilla')
pf = CF._conf_pick_fwdstart(REF, 'CLIX', 'USD', 'strike-me')
check('Nº: Deal no Vanilla, B3 ID no FWD Start', (CF._conf_num_field(pv), CF._conf_num_field(pf)),
      ('Deal', 'B3_ID'))
w = []
linhas = CF._conf_vanilla_rows(pv, CF._conf_fwdstart_rows(pv, w, num_field=CF._conf_num_field(pv)), w)
check('linhas do Vanilla: o Deal no Nº, sem Verificação da Taxa Forward nem Pontos de Termo',
      sorted((r['num'], r['dtVerifFwd'], r['pontosTermo'], r['taxaFwd']) for r in linhas),
      [('ATH-ASN', 'Não Aplicável', 'Não Aplicável', '5,40000000'),
       ('ATH-BRL', 'Não Aplicável', 'Não Aplicável', '5,40000000')])

print('\n== 4. _mc_conf_trade_keys ==')
check('FWD Start e o Vanilla do Banco no mesmo gerador',
      MCP._mc_conf_trade_keys(pf + pv, 'ndf-fwdstart'), ['26E00000015', 'ATH-ASN', 'ATH-BRL'])
check('MGT: Vanilla pelo Deal, FWD Start pelo B3 ID',
      MCP._mc_conf_trade_keys([(dict(MGT_V, _conf_src='vanilla'), None),
                               (dict(FWD, _conf_src='fwd-start'), None)], 'ndf-mgt'),
      ['ATH-MGT', '26E00000015'])
OP = {'Deal': 'D-1', 'B3_ID': 'B-1'}
check('FXO, NDF e opção de commodities pelo Deal; swap pelo B3 ID',
      [MCP._mc_conf_trade_keys([(OP, None)], p)[0] for p in ('opt-fxo', 'ndf-comm', 'opt-comm', 'swap-edg')],
      ['D-1', 'D-1', 'D-1', 'B-1'])

print('\n== 5. Pending e FepWeb ID ==')
TMP = tempfile.mkdtemp(prefix='ndf-vanilla-conf-')
R._PC_DB_DIR = PC._PC_DB_DIR = TMP
_mc_orig = R._mc_save_from_deal
R._mc_save_from_deal = lambda *a, **k: None
R._pc_is_internal_counterparty = PC._pc_is_internal_counterparty = lambda *a, **k: False
with app.test_request_context():
    ND._generic_nd_pc_trigger('vanilla', ASIAN)
    ND._generic_nd_pc_trigger('fwd-start', FWD)
    check('Trade Number: Vanilla = Deal, FWD Start = B3 ID',
          (PC._pc_find_row('ATH-ASN') is not None, PC._pc_find_row('26E00000015') is not None,
           PC._pc_find_row('ATH-FWD') is None), (True, True, True))
    n = R._conf_pc_set_fepweb(MCP._mc_conf_trade_keys(pf + pv, 'ndf-fwdstart'), 'NDF_X')
    check('o FepWeb ID pelas chaves da esteira acha as duas linhas', n, 2)
    check('   e grava nelas', (PC._pc_find_row('ATH-ASN')['FepWeb ID'],
                               PC._pc_find_row('26E00000015')['FepWeb ID']), ('NDF_X', 'NDF_X'))
R._mc_save_from_deal = _mc_orig

print('\n== 6. o Generate do Monitor ==')
CF._conf_load_ndfmgt = lambda ref: [dict(MGT_V, _conf_src='vanilla')]
linha = {'Produto': 'NDF VANILLA', 'LOB': 'CEM', 'Data Operação': '27/10/2026',
         'Trade ID': 'ATH-ASN', 'Legal Entity': 'BANCO J.P MORGAN S.A'}
url, motivo = MCP._mc_generate_url(linha, [])
check('NDF VANILLA do Banco: o editor do termo de moeda, família vanilla',
      (url.split('?')[0], motivo), ('/confirmation/ndf-fwdstart/vanilla', ''))
url, _m = MCP._mc_generate_url(dict(linha, **{'Trade ID': 'ATH-MGT', 'Legal Entity': 'MGT'}), [])
check('o de MGT segue no editor MGT', url.split('?')[0], '/confirmation/ndf-mgt/vanilla')

print('\n== 7. a página do Vanilla ==')
cl = app.test_client()
with cl.session_transaction() as s:
    s.update(authenticated=True, user_sid='T000001', user_name='T', user_role='BO', session_ip='127.0.0.1',
             session_expires_at=(datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat())
r = cl.get('/confirmation/ndf-fwdstart/vanilla?date=2026-10-27&acronym=CLIX&mercadoria=USD')
html = r.get_data(as_text=True)
check('200, com o Deal e sem o B3 ID no Anexo I',
      (r.status_code, 'ATH-ASN' in html, '26E00000011' in html), (200, True, False))
check('o editor diz NDF Vanilla e o conf leva a família',
      ('NDF Vanilla</h1>' in html, '"family": "vanilla"' in html), (True, True))
r = cl.get('/confirmation/ndf-fwdstart/strike-me?date=2026-10-27&acronym=CLIX&mercadoria=USD')
check('a do FWD Start segue com o B3 ID', (r.status_code, '26E00000015' in r.get_data(as_text=True)),
      (200, True))
tpl = open(os.path.join(ROOT, 'apps', 'templates', 'confirmations', 'ndf-fwdstart-strike-me.html'),
           encoding='utf-8').read()
check('o Save manda a família da página', "family: (__CONF__ && __CONF__.family) || 'strike-me'" in tpl, True)

print('\n== 8. o FepWeb ID dos Saves ==')
ep = open(os.path.join(ROOT, 'apps', 'pages', 'features', 'confirmation', 'entrypoint.py'),
          encoding='utf-8').read()
chamadas = re.findall(r'_conf_pc_set_fepweb\(([^,\n]*)', ep)
check('seis Saves, todos pelo _mc_conf_trade_keys',
      (len(chamadas), all('_mc_conf_trade_keys(picked' in c for c in chamadas)), (6, True))

print('\n== 9. o script do FepWeb ID antigo ==')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import fill_fepweb_ids_fwdstart as FF                            # noqa: E402
_res = R._ei_resolve_client_dir
R._ei_resolve_client_dir = lambda cli, create=False: '/EI/' + cli if cli == 'CLIENTE X' else None
try:
    check('o XML ao lado do PDF do link',
          FF._xml_do_link(R, R._mc_ei_link('CLIENTE X', '/EI/CLIENTE X', '/EI/CLIENTE X/Confirmations/a b.pdf')),
          ('/EI/CLIENTE X/Confirmations/a b.xml', ''))
    check('cliente sem pasta: motivo', bool(FF._xml_do_link(R, '/x?client=OUTRO&rel=a.pdf')[1]), True)
finally:
    R._ei_resolve_client_dir = _res
check('o numeroContrato do XML',
      FF._NUMERO.search('<x><numeroContrato> 26E00000015 </numeroContrato></x>').group(1), '26E00000015')

print(('\nFAIL: %d' % len(fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
