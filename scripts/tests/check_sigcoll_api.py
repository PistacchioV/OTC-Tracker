# -*- coding: utf-8 -*-
"""O card Signature Collection (Cobranca) ponta a ponta.

Espelha a macro "MassEmail" da planilha legada, mas gera RASCUNHOS revisaveis
(.eml X-Unsent; .zip quando ha mais de um) em vez de enviar. O que ele prende:

  1. **um rascunho por (disclaimer, contraparte)** — Pending Digital Signature e
     Pending Original do MESMO cliente sao DOIS e-mails, porque o texto do
     disclaimer muda;
  2. **To = contatos de confirmacao** do CounterpartyDetails, caindo para TODOS
     os contatos quando nenhuma regra menciona confirmacao;
  3. **Cc = bankers do grupo** (cadastro Mapping > Bankers E-mails, casado por
     nome normalizado) + as duas caixas fixas, sem duplicar;
  4. sem pendencia de assinatura o generate e **404** — nao ha o que cobrar.

Tudo stubado em plataforma (`_pc_load_rows`, RefData, cadastro); nada sai da
maquina.
"""
import io, json, os, sys, tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages import routes as R                          # noqa: E402
from apps.pages import otc_emails as OE                     # noqa: E402
from apps import create_app                                 # noqa: E402
from apps.config import DebugConfig                         # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

# O card mora em features/sigcoll.
from apps.pages.features.sigcoll import queries as SCQ       # noqa: E402
SC_groups = SCQ.groups
SC_cc = SCQ.cc_emails
SC_to = SCQ.to_emails

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def cliente(auth=True):
    c = app.test_client()
    if auth:
        with c.session_transaction() as s:
            s['authenticated'] = True
            s['user_sid'] = 'A111111'
            s['user_name'] = 'Alice Souza'
            s['user_role'] = 'BO'
            s['user_email'] = 'alice.souza@jpmorgan.com'
            s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    return c


c, anon = cliente(), cliente(auth=False)

# ── plataforma stubada ──────────────────────────────────────────────────────
LINHAS = [
    {'Client': 'ACME SA', 'SPN': '100', 'Pending Status': 'Pending Digital Signature',
     'Aging': '40', 'Product Type': 'NDF', 'Trade Date': '01/07/2026',
     'Maturity Date': '01/09/2026', 'Trade Number': 'T-1', 'Owner': ''},
    {'Client': 'ACME SA', 'SPN': '100', 'Pending Status': 'Pending Original',
     'Aging': '10', 'Product Type': 'SWAP', 'Trade Date': '10/08/2026',
     'Maturity Date': '10/10/2026', 'Trade Number': 'T-2', 'Owner': ''},
    {'Client': 'BETA LTD', 'SPN': '200', 'Pending Status': 'Pending Original',
     'Aging': '5', 'Product Type': 'NDF', 'Trade Date': '20/08/2026',
     'Maturity Date': '20/09/2026', 'Trade Number': 'T-3', 'Owner': 'Beltrano'},
    {'Client': 'OK SA', 'SPN': '300', 'Pending Status': 'Ok'},   # resolvida: fora
]
REFDATA = {'100': {'COUNTERPARTY': 'ACME SA', 'BANKER': 'Fulano e Sicrano'},
           '200': {'COUNTERPARTY': 'BETA LTD', 'BANKER': ''}}
R._pc_load_rows = lambda cat: [dict(r) for r in LINHAS]
R._fxo_refdata_by_spn = lambda: {R._norm_spn(k): v for k, v in REFDATA.items()}
R._pc_refdata_by_name = lambda: {}
_real_mapping = R._mapping_rows
R._mapping_rows = lambda key, *a, **kw: (
    [{'BANKER': 'Fulano', 'EMAIL': 'fulano@jpmorgan.com'},
     {'BANKER': 'Sicrano', 'EMAIL': 'sicrano@jpmorgan.com'},
     {'BANKER': 'Beltrano', 'EMAIL': 'beltrano@jpmorgan.com'}]
    if key == 'bankers-email' else _real_mapping(key, *a, **kw))
CPD = {'100': {'CONTACTS': [
           {'email': 'conf@acme.com', 'rule': 'Confirmation'},
           {'email': 'outro@acme.com', 'rule': 'Invoices'}]},
       '200': {'CONTACTS': [{'email': 'a@beta.com'}, {'email': 'b@beta.com'}]}}
OE._build_cpdetails_index = lambda: CPD
_real_contacts = OE._contacts_emails


def _contacts(cp, kws):
    # regra 'Confirmation' casa por keyword; a do 200 nao tem regra nenhuma
    return [ct['email'] for ct in (cp.get('CONTACTS') or [])
            if any(k in str(ct.get('rule', '')).lower() for k in kws)]


OE._contacts_emails = _contacts
NOTIFS = []
R._create_notification = lambda sid, nome, acao, pagina, msg='': NOTIFS.append((acao, pagina))

print('== 1. sem sessao ==')
check('preview -> 401', anon.get('/api/control-panel/signature-collection/preview').status_code, 401)
check('generate -> 401', anon.post('/api/control-panel/signature-collection/generate').status_code, 401)

print('\n== 2. um grupo por (disclaimer, contraparte) ==')
gs = SC_groups()
# A ordem e (contraparte, disclaimer) alfabetica — 'Pendente de Assinatura'
# vem antes de 'Pendente de Assinatura Digital'.
check('tres grupos: um por (disclaimer, contraparte)',
      [(g['cp_name'], g['disclaimer']) for g in gs],
      [('ACME SA', 'Pendente de Assinatura'), ('ACME SA', 'Pendente de Assinatura Digital'),
       ('BETA LTD', 'Pendente de Assinatura')])
check('   a resolvida (Ok) fica fora', sum(len(g['rows']) for g in gs), 3)
check('   o banker vem do RefData, caindo para o Owner',
      [g['banker'] for g in gs], ['Fulano e Sicrano', 'Fulano e Sicrano', 'Beltrano'])

print('\n== 3. To e Cc ==')
check('To = contatos de confirmacao', SC_to(CPD['100']), ['conf@acme.com'])
check('   sem regra de confirmacao caem TODOS os contatos',
      SC_to(CPD['200']), ['a@beta.com', 'b@beta.com'])
bankers = SCQ.bankers_index()
check('Cc = bankers do grupo + caixas fixas, sem duplicar',
      SC_cc('Fulano e Sicrano', bankers),
      ['fulano@jpmorgan.com', 'sicrano@jpmorgan.com',
       'brazil.otc.ops@jpmorgan.com', 'is.trade.doc@jpmchase.com'])

print('\n== 4. preview ==')
d = c.get('/api/control-panel/signature-collection/preview').get_json()
check('conta os rascunhos e as confirmacoes', (d['drafts'], d['confirmations']), (3, 3))

print('\n== 5. generate: .zip com os tres rascunhos ==')
r = c.post('/api/control-panel/signature-collection/generate')
check('200 com a contagem no header', (r.status_code, r.headers.get('X-Draft-Count')), (200, '3'))
check('   e mais de um vira zip',
      'zip' in (r.headers.get('Content-Type') or '') or
      (r.headers.get('Content-Disposition') or '').endswith('.zip"'), True)
check('   e avisa no sino', NOTIFS[-1], ('Signature Collection Generated', 'Control Panel'))

print('\n== 6. sem pendencia, 404 ==')
R._pc_load_rows = lambda cat: []
r = c.post('/api/control-panel/signature-collection/generate')
check('404 dizendo que nao ha o que cobrar',
      (r.status_code, 'No pending-signature' in r.get_json()['error']), (404, True))

R._mapping_rows = _real_mapping
OE._contacts_emails = _real_contacts

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
