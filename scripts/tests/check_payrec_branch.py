#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_payrec_branch.py — Branch Settlement Control no Pay/Rec (G&O, passos 7-15).

Em dia com liquidação contra a MGT (JPMorgan Chase Bank, N.A. - São Paulo
Branch), a recon ganha uma linha de quebra ADICIONAL com o net das pernas B2B
Banco × MGT — mesmo valor, mesma direção —, que fica aberta até a reversão
manual (aprovada por um VP por e-mail) liquidar e casar aqui.

O que este script prova:

  1. `branch_settlement` separa, dos registros do Cockpit, o B2B (visão do
     Banco; a perna do livro da MGT entra com sinal trocado e só sem a do
     Banco) e as operações MGT × cliente (bruto, IR, total), e compara em
     módulo o net B2B com o net contra clientes;
  2. a perna intragrupo não entra no lado JPM como se fosse cliente (a grafia
     `BANCO J.P MORGAN S.A`, sem ponto, escapava da lista);
  3. o Run cria a linha no card certo (Pay/Receive pelo sinal do net), com a
     marca `branch`, e ela só casa com a liquidação INTERBANCÁRIA no mesmo
     sentido — nunca com a perna de um cliente de mesmo valor;
  4. dia sem MGT não cria nada;
  5. o rascunho .eml: destinatários do card, contas origem/destino do
     Counterparty Details, a lista MGT × cliente com o total e a comparação;
     sem conta cadastrada, avisa por código; sem TO, recusa;
  6. o card existe no Control Panel com TO e CC, e o botão na tela.

Não encosta em dado real: a gravação do resultado e as leituras de cadastro
são stubs.
"""
import base64
import email
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


def ck(legal, cpty, settle, ir='', deal='D1', b3=''):
    return {'LEGAL': legal, 'NM_COUNTERPARTY': cpty, 'ID_SOURCE_DEAL': deal,
            'CD_CETIP_RETURN': b3, '[PROD] Cockpit.SETTLEMENT': settle, 'VL_TAX_INCOME': ir}


DIA = [
    ck(BANCO, 'CLIENTE A', '-1000.00', '0.05', 'N1'),            # liquidação normal do Banco
    ck(MGT, 'CLIENTE X', '-50000.00', '2.50', 'M1', '26E001'),     # MGT paga o cliente X
    ck(MGT, 'CLIENTE Y', '20000.00', '', 'M2', '26E002'),          # MGT recebe do cliente Y
    ck(BANCO, MGT, '30000.00', '', 'B1'),                          # B2B, visão do Banco
    ck(MGT, BANCO, '-30000.00', '', 'B1M'),                        # a mesma, visão da MGT
]

print('\n== 1. branch_settlement ==')
b = RP.branch_settlement(DIA)
check('ha liquidacao com a Branch', b['has_settlement'], True)
check('o B2B vem do livro do Banco (a visao da MGT nao dobra)', [r['deal'] for r in b['b2b']], ['B1'])
check('net do B2B', b['b2b_net'], 30000.0)
check('direcao na visao do Banco', b['pay_receive'], 'Receive')
check('operacoes MGT x cliente', [r['deal'] for r in b['trades']], ['M1', 'M2'])
check('bruto / IR / total do cliente X',
      [(r['gross'], r['ir'], r['total']) for r in b['trades'] if r['deal'] == 'M1'],
      [(-50000.0, 2.5, -49997.5)])
check('totais contra clientes', (b['client_gross'], b['client_ir'], b['client_net']),
      (-30000.0, 2.5, -29997.5))
check('diferenca em modulo (B2B x net contra cliente)', b['difference'], 2.5)
so_mgt = RP.branch_settlement([ck(MGT, BANCO, '-30000.00')])
check('sem a perna do Banco, a da MGT entra com o sinal trocado', so_mgt['b2b_net'], 30000.0)
check('dia sem MGT nao tem liquidacao com a Branch',
      RP.branch_settlement([ck(BANCO, 'CLIENTE A', '10')])['has_settlement'], False)
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

print('\n== 3. o Run cria a linha de quebra ==')
_stubs = (RP._gather_sources, RP._persist, RP._load_net_type_map, RP._apply_carry_forward,
          RP._net_type_for, RP._settlement_exception_for, RP._is_bank_cpty)


def run(ndf_rows, client_rows=()):
    RP._gather_sources = lambda files, mode: [('spb', list(client_rows), ['x'])] if client_rows else []
    RP._persist = lambda d, p, strict=False: None
    RP._load_net_type_map = lambda: {}
    RP._apply_carry_forward = lambda d, pp, pr, st: (pp, pr)
    RP._net_type_for = lambda m, c: 'Total Net'
    RP._settlement_exception_for = lambda c: None
    RP._is_bank_cpty = lambda n: False
    return RP.run_payrec('2026-09-25', ndf_rows=ndf_rows)


_cli_spb = RP._cli_spb
try:
    out = run(DIA)
    br = [r for r in out['pending_receivement'] if r.get('branch')]
    check('uma linha da Branch no Pending Receivement', len(br), 1)
    check('valor e direcao dos B2B', (br[0]['jpm_value'], br[0]['pay_receive']) if br else None,
          (30000.0, 'Receive'))
    check('JPM cpty e a Branch, LE JPM', (br[0]['jpm_cpty'], br[0]['le']) if br else None, (MGT, 'JPM'))
    check('nada da Branch no Pending Payment',
          [r for r in out['pending_payment'] if r.get('branch')], [])
    check('o resultado grava o bloco da Branch', out['branch']['b2b_net'], 30000.0)

    neg = run([ck(BANCO, MGT, '-12.34')])
    check('net negativo vai para o Pending Payment',
          [(r['jpm_value'], r['pay_receive']) for r in neg['pending_payment'] if r.get('branch')],
          [(-12.34, 'Pay')])

    check('dia sem MGT nao cria linha',
          [r for r in run([ck(BANCO, 'CLIENTE A', '-10')])['pending_payment'] if r.get('branch')], [])

    # A reversão liquidada: o interbancário no mesmo sentido fecha a quebra; a
    # perna de um cliente de MESMO valor não.
    RP._cli_spb = lambda rows, cols, mgt=False: list(rows)
    interb = {'value': 30000.0, 'client': '', 'sistema': 'SPB - outros bancos', 'snumconta': '',
              'product': 'NDF', 'pay_receive': 'Receive', 'le': 'JPM', 'bank': True, 'tol': 20.0,
              'drop_if_unmatched': True}
    fechou = run([ck(BANCO, MGT, '30000.00')], [interb])
    check('interbancario no mesmo sentido casa a quebra',
          [r['status'] for r in fechou['settled'] if r.get('branch')], ['Settled'])
    cliente = {'value': 30000.0, 'client': 'CLIENTE Z', 'sistema': 'SPB - conta externa',
               'snumconta': '', 'product': 'NDF', 'pay_receive': 'Receive', 'le': 'JPM'}
    nao = run([ck(BANCO, MGT, '30000.00')], [cliente])
    check('perna de cliente de mesmo valor NAO fecha a quebra',
          [r['status'] for r in nao['pending_receivement'] if r.get('branch')], ['Pending'])
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

gravado = {'branch': RP.branch_settlement(DIA)}
CPD = [
    {'SPN': '96096', 'COUNTERPARTY': BANCO, 'BANKING': {
        'ACCOUNTS': [{'id': 'a1', 'bank': '376', 'agency': '0001', 'account': '111-1'}],
        'DEFAULT_PAY': {'current': 'a1'}, 'DEFAULT_RECEIVE': {'current': 'a1'}}},
    {'SPN': '55555', 'COUNTERPARTY': MGT, 'BANKING': {
        'ACCOUNTS': [{'id': 'm1', 'bank': '488', 'agency': '0002', 'account': '222-2'}],
        'DEFAULT_PAY': {'current': 'm1'}, 'DEFAULT_RECEIVE': {'current': None}}},
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
    check('origem = conta de pagamento da MGT (o Banco recebe)', 'BCO: 488 | AG: 0002 | CC: 222-2' in html, True)
    check('destino = conta de recebimento do Banco', 'BCO: 376 | AG: 0001 | CC: 111-1' in html, True)
    check('lista as operacoes MGT x cliente', ('CLIENTE X' in html, 'CLIENTE Y' in html), (True, True))
    check('net B2B, net contra cliente e o IR total',
          ('30,000.00' in html, '-29,997.50' in html, '2.50' in html), (True, True, True))
    check('sem aviso com as duas contas cadastradas', j.get('warnings'), [])

    CPD[0]['BANKING']['DEFAULT_RECEIVE'] = {'current': None}
    j = cl.post('/reconciliation-payrec/branch-email', json={'recon_date': '2026-09-25'}).get_json()
    check('conta faltando avisa por codigo',
          [(w['code'], w['params']['slot']) for w in j.get('warnings', [])],
          [('branch_no_account', 'DEFAULT_RECEIVE')])

    saved['to'] = ''
    r = cl.post('/reconciliation-payrec/branch-email', json={'recon_date': '2026-09-25'})
    check('sem TO recusa com codigo', (r.status_code, (r.get_json() or {}).get('code')),
          (400, 'branch_no_recipient'))
    saved['to'] = 'vp@jpmorgan.com'
    gravado['branch'] = RP.branch_settlement([ck(BANCO, 'CLIENTE A', '10')])
    r = cl.post('/reconciliation-payrec/branch-email', json={'recon_date': '2026-09-25'})
    check('dia sem Branch recusa', (r.get_json() or {}).get('code'), 'branch_none')
    gravado['branch'] = RP.branch_settlement([ck(MGT, 'CLIENTE X', '-10')])
    r = cl.post('/reconciliation-payrec/branch-email', json={'recon_date': '2026-09-25'})
    check('com MGT e sem B2B nao chuta a direcao', (r.get_json() or {}).get('code'), 'branch_no_b2b')
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
