#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_payrec_branch.py — Branch Settlement Control no Pay/Rec (G&O, passos 7-15).

Mesa, 25/09/2026. A fonte é o OPERATIONS B3 do dia, pelas contas:
  B2B      = 73760.00-9 (Banco própria) × 04880.00-6 (MGT própria);
  CLIENTE  = 73760.20-5 (guarda-chuva do Banco p/ o cliente da MGT) × 04880.00-6,
             cada perna com um B2B de MESMO valor e sinal INVERTIDO;
  LEGADO   = 04880.00-6 × 04880.10-9, a rota antiga — só AVISADA.
A recon ganha DUAS linhas: a de todos os B2B e a da REVERSÃO (net das pernas
de cliente × −1), que é o valor e a direção do e-mail do VP.

Prova: o pareamento e as visões espelhadas (sem dobrar), as duas linhas e o
casamento só com o interbancário, o rascunho .eml (contas, lista, avisos, sem
"Dear VP", tabela sem quebra) e o card/botão. Não encosta em dado real.
"""
import base64
import email
import email.header
import io
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages import recon_payrec as RP                       # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


BANCO = 'BANCO J.P MORGAN S.A'
MGT = 'JPMORGAN CHASE BANK, N.A. - SAO PAULO BRANCH'
ACC = {'bank_own': '73760.00-9', 'mgt_own': '04880.00-6',
       'bank_client': '73760.20-5', 'mgt_client': '04880.10-9'}


def ck(legal, cpty, settle, ir='', deal='D1', b3=''):
    return {'LEGAL': legal, 'NM_COUNTERPARTY': cpty, 'ID_SOURCE_DEAL': deal,
            'CD_CETIP_RETURN': b3, '[PROD] Cockpit.SETTLEMENT': settle, 'VL_TAX_INCOME': ir}


def ob(titulo, conta, ccp, valor, tipo='Resgate'):
    return {'Título': titulo, 'Conta': conta, 'Conta Contraparte': ccp,
            'Valor': valor, 'Tipo Operação': tipo}


DIA = [
    ck(BANCO, 'CLIENTE A', '-1000.00', '0.05', 'N1'),
    ck(MGT, 'CLIENTE X', '-50000.00', '2.50', 'M1', '26E001'),
    ck(MGT, 'CLIENTE Y', '20000.00', '', 'M2', '26E002'),
]
OPS = [
    # perna de cliente X: visão do Banco (205) E a espelhada da MGT — não dobra
    ob('26E001', '73760.20-5', '04880.00-6', '50000,00'),
    ob('26E001', '04880.00-6', '73760.20-5', '-50000,00'),
    # perna de cliente Y: só a visão da MGT → entra com o sinal virado
    ob('26E002', '04880.00-6', '73760.20-5', '20000,00'),
    # os B2B: mesmo valor, sinal invertido
    ob('26B001', '73760.00-9', '04880.00-6', '-50000,00'),
    ob('26B002', '73760.00-9', '04880.00-6', '20000,00'),
    ob('26B002', '04880.00-6', '73760.00-9', '-20000,00'),
    # rota antiga
    ob('26L001', '04880.00-6', '04880.10-9', '-700,00'),
    # outra conta qualquer — fora
    ob('26Z001', '73760.10-2', '04880.00-6', '999,00'),
]

print('\n== 1. branch_settlement ==')
b = RP.branch_settlement(OPS, ACC, DIA)
check('ha liquidacao com a Branch', b['has_settlement'], True)
check('B2B sem dobrar a visao espelhada', [(r['titulo'], r['value']) for r in b['b2b']],
      [('26B001', -50000.0), ('26B002', 20000.0)])
check('net do B2B', b['b2b_net'], -30000.0)
check('pernas de cliente na visao da 73760.20-5',
      [(t['b3_id'], t['value']) for t in b['trades']], [('26E001', 50000.0), ('26E002', -20000.0)])
check('reversao = net das pernas de cliente x -1', (b['client_b3_net'], b['reversal_net']),
      (30000.0, -30000.0))
check('direcao da reversao', b['pay_receive'], 'Pay')
check('cada perna de cliente pareada com o B2B de sinal invertido',
      [(t['b3_id'], t['b2b_id']) for t in b['trades']], [('26E001', '26B001'), ('26E002', '26B002')])
check('Cockpit enriquece pelo B3 ID', [(t['counterparty'], t['ir']) for t in b['trades']],
      [('CLIENTE X', 2.5), ('CLIENTE Y', 0.0)])
check('B2B x reversao fecham', b['difference'], 0.0)
check('rota antiga avisada, fora da conta', (len(b['legacy']), b['legacy_net']), (1, -700.0))
b2 = RP.branch_settlement([ob('26E001', '73760.20-5', '04880.00-6', '100,00'),
                           ob('26B009', '73760.00-9', '04880.00-6', '-90,00')], ACC)
check('sem B2B de mesmo valor: perna sem par e B2B sobrando',
      (len(b2['unmatched_client']), len(b2['unmatched_b2b'])), (1, 1))
check('sem as contas no cadastro o controle nao roda',
      RP.branch_settlement(OPS, {'mgt_own': '04880.00-6'})['has_settlement'], False)
check('dia sem MGT nao tem liquidacao',
      RP.branch_settlement([ob('X', '73760.00-9', '12345.00-1', '10')], ACC)['has_settlement'], False)
check('LEGAL da MGT pela grafia do Cockpit', RP._entity_side('JPMORGAN CHASE BANK N.A. SAO PAULO'), 'MGT')
check('Banco sem o ponto do P', RP._entity_side(BANCO), 'JPM')
check('cliente nao e entidade', RP._entity_side('BANCO SAFRA S/A'), None)

print('\n== 2. perna intragrupo nao e cliente no lado JPM ==')
_net = RP._net_type_for
RP._net_type_for = lambda m, c: 'Total Net'
try:
    cps = sorted(r['cpty'] for r in RP._jpm_cockpit(DIA, {}))
finally:
    RP._net_type_for = _net
check('so os clientes (nenhum Banco/MGT)', cps, ['CLIENTE A', 'CLIENTE X', 'CLIENTE Y'])

print('\n== 3. o Run cria as duas linhas ==')
_stubs = (RP._gather_sources, RP._persist, RP._load_net_type_map, RP._apply_carry_forward,
          RP._net_type_for, RP._settlement_exception_for, RP._is_bank_cpty)


def run(ops, client_rows=(), ndf=DIA):
    RP._gather_sources = lambda files, mode: [('spb', list(client_rows), ['x'])] if client_rows else []
    RP._persist = lambda d, p, strict=False: None
    RP._load_net_type_map = lambda: {}
    RP._apply_carry_forward = lambda d, pp, pr, st: (pp, pr)
    RP._net_type_for = lambda m, c: 'Total Net'
    RP._settlement_exception_for = lambda c: None
    RP._is_bank_cpty = lambda n: False
    return RP.run_payrec('2026-09-25', ndf_rows=ndf, ops_rows=ops, branch_accounts=ACC)


_cli_spb = RP._cli_spb
try:
    out = run(OPS)
    linhas = sorted((r['branch'], r['jpm_value'], r['pay_receive'])
                    for r in out['pending_payment'] + out['pending_receivement'] if r.get('branch'))
    check('uma linha dos B2B e uma da reversao', linhas,
          [('b2b', -30000.0, 'Pay'), ('reversal', -30000.0, 'Pay')])
    check('as duas no Pending Payment (net negativo)',
          sorted(r['branch'] for r in out['pending_payment'] if r.get('branch')), ['b2b', 'reversal'])
    check('JPM cpty e a Branch, LE JPM',
          {(r['jpm_cpty'], r['le']) for r in out['pending_payment'] if r.get('branch')}, {(MGT, 'JPM')})
    check('o resultado grava o bloco da Branch', out['branch']['reversal_net'], -30000.0)
    check('dia sem MGT nao cria linha',
          [r for r in run([])['pending_payment'] if r.get('branch')], [])

    RP._cli_spb = lambda rows, cols, mgt=False: list(rows)
    interb = {'value': -30000.0, 'client': '', 'sistema': 'SPB - outros bancos', 'snumconta': '',
              'product': 'NDF', 'pay_receive': 'Pay', 'le': 'JPM', 'bank': True, 'tol': 20.0,
              'drop_if_unmatched': True}
    fechou = run(OPS, [interb])
    check('interbancario no mesmo sentido casa UMA das linhas',
          len([r for r in fechou['settled'] if r.get('branch')]), 1)
    cliente = {'value': -30000.0, 'client': 'CLIENTE Z', 'sistema': 'SPB - conta externa',
               'snumconta': '', 'product': 'NDF', 'pay_receive': 'Pay', 'le': 'JPM'}
    nao = run(OPS, [cliente])
    check('perna de cliente de mesmo valor NAO fecha nenhuma',
          [r for r in nao['settled'] if r.get('branch')], [])
finally:
    (RP._gather_sources, RP._persist, RP._load_net_type_map, RP._apply_carry_forward,
     RP._net_type_for, RP._settlement_exception_for, RP._is_bank_cpty) = _stubs
    RP._cli_spb = _cli_spb

print('\n== 5. o rascunho .eml ==')
from apps import create_app                                     # noqa: E402
from apps.config import DebugConfig                             # noqa: E402
from apps.pages import routes as R                              # noqa: E402
from apps.pages.features.recon_payrec.infra import persistence as P   # noqa: E402

app = create_app(DebugConfig)
cl = app.test_client()
with cl.session_transaction() as s:
    s['authenticated'] = True
    s['user_sid'] = 'T000000'
    s['user_name'] = 'T'
    s['user_role'] = 'ADMIN'
    s['session_ip'] = '127.0.0.1'
    s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()

gravado = {'branch': RP.branch_settlement(OPS, ACC, DIA)}
CPD = [
    {'SPN': '96096', 'COUNTERPARTY': BANCO, 'BANKING': {
        'ACCOUNTS': [{'id': 'a1', 'bank': '376', 'agency': '0001', 'account': '111-1'}],
        'DEFAULT_PAY': {'current': 'a1'}, 'DEFAULT_RECEIVE': {'current': 'a1'}}},
    {'SPN': '55555', 'COUNTERPARTY': MGT, 'BANKING': {
        'ACCOUNTS': [{'id': 'm1', 'bank': '488', 'agency': '0002', 'account': '222-2'}],
        'DEFAULT_PAY': {'current': 'm1'}, 'DEFAULT_RECEIVE': {'current': 'm1'}}},
]
saved = {'to': 'vp@jpmorgan.com', 'cc': 'ops@jpmorgan.com'}
_orig = (RP._load_flat, R._cpd_load, R._mapping_rows, R._create_notification, P.load_recipients)
RP._load_flat = lambda d, strict=False: gravado
R._cpd_load = lambda: CPD
R._mapping_rows = lambda key, strict=False: (
    [{'LE': 'JPM', 'NAME': BANCO, 'SPN': '96096'}, {'LE': 'MGT', 'NAME': MGT, 'SPN': '55555'}]
    if key == 'le-spn' else [])
R._create_notification = lambda *a, **k: None
P.load_recipients = lambda: dict(saved)
try:
    r = cl.post('/reconciliation-payrec/branch-email', json={'recon_date': '2026-09-25'})
    j = r.get_json() or {}
    check('POST responde 200', r.status_code, 200)
    check('nome do arquivo', j.get('filename'), 'Branch_Settlement_Reverse_Approval_25092026.eml')
    msg = email.message_from_bytes(base64.b64decode(j.get('b64', '')))
    check('TO e CC do card', (msg['To'], msg['Cc']), ('vp@jpmorgan.com', 'ops@jpmorgan.com'))
    check('abre como rascunho', msg['X-Unsent'], '1')
    html = ''.join(p.get_payload(decode=True).decode('utf-8') for p in msg.walk()
                   if p.get_content_type() == 'text/html')
    check('origem = conta de pagamento do Banco (a reversao e um Pay)',
          html.index('BCO: 376 | AG: 0001 | CC: 111-1') < html.index('BCO: 488 | AG: 0002 | CC: 222-2'), True)
    check('lista as pernas de cliente e o B2B de cada uma',
          all(x in html for x in ('CLIENTE X', 'CLIENTE Y', '26B001', '26B002')), True)
    check('valor da reversao no assunto',
          'BRL 30,000.00' in str(email.header.make_header(email.header.decode_header(msg['Subject']))), True)
    check('sem "Dear VP"', 'Dear VP' in html, False)
    check('tabela larga e sem quebra de linha', ('width="1080"' in html, 'white-space:nowrap' in html),
          (True, True))
    check('a rota antiga vai no corpo e no aviso',
          ('04880.10-9' in html, [w['code'] for w in j.get('warnings', [])]),
          (True, ['branch_legacy_route']))

    CPD[1]['BANKING']['DEFAULT_RECEIVE'] = {'current': None}
    j = cl.post('/reconciliation-payrec/branch-email', json={'recon_date': '2026-09-25'}).get_json()
    check('conta faltando avisa por codigo',
          [(w['code'], w['params'].get('slot')) for w in j.get('warnings', [])],
          [('branch_no_account', 'DEFAULT_RECEIVE'), ('branch_legacy_route', None)])

    saved['to'] = ''
    r = cl.post('/reconciliation-payrec/branch-email', json={'recon_date': '2026-09-25'})
    check('sem TO recusa com codigo', (r.status_code, (r.get_json() or {}).get('code')),
          (400, 'branch_no_recipient'))
    saved['to'] = 'vp@jpmorgan.com'
    gravado['branch'] = RP.branch_settlement([], ACC)
    r = cl.post('/reconciliation-payrec/branch-email', json={'recon_date': '2026-09-25'})
    check('dia sem Branch recusa', (r.get_json() or {}).get('code'), 'branch_none')
    gravado['branch'] = RP.branch_settlement([ob('26B001', '73760.00-9', '04880.00-6', '-10')], ACC)
    r = cl.post('/reconciliation-payrec/branch-email', json={'recon_date': '2026-09-25'})
    check('so B2B, sem perna de cliente: nao ha reversao', (r.get_json() or {}).get('code'),
          'branch_no_reversal')
finally:
    (RP._load_flat, R._cpd_load, R._mapping_rows, R._create_notification, P.load_recipients) = _orig

print('\n== 6. card e botao ==')
CP = io.open('apps/templates/pages/control-panel.html', encoding='utf-8').read()
check('card no registro', any(c['id'] == 'branchsettlement' for c in R._CONTROL_PANEL_CARDS), True)
check('card no template com TO e CC',
      ('data-cp-card="branchsettlement"' in CP, 'id="cp-branch-to"' in CP, 'id="cp-branch-cc"' in CP),
      (True, True, True))
check('endpoint dos destinatarios preso ao card',
      R._CP_ENDPOINT_CARD.get('/api/control-panel/branch-settlement/recipients'), 'branchsettlement')
PG = io.open('apps/templates/pages/reconciliation-payrec.html', encoding='utf-8').read()
check('botao Branch Settl. nasce escondido', 'id="prBranchBtn" hidden' in PG, True)
JS = io.open('apps/static/js/pages/reconciliation-payrec.js', encoding='utf-8').read()
check('o JS so mostra na data de hoje', "refDate() === today" in JS, True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS: %d' % len(fails)))
sys.exit(1 if fails else 0)
