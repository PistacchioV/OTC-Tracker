# -*- coding: utf-8 -*-
"""O card Weekly Escalation (CEM/EDG) ponta a ponta.

O que ele prende:

  1. **o Run gera RASCUNHO .eml** (X-Unsent), como o Daily Metric e pela mesma
     razao: e cobranca NOMINAL a banqueiros — quem assina le antes de sair;
  2. **a quebra e por LOB (CEM/EDG), banqueiro e EMPRESA** (nome do cliente,
     nao o grupo economico): >= 30 dias, banker do RefData caindo para o Owner,
     LOB fora das duas fica DE FORA;
  3. ordenacao: banqueiro pelo total desc, empresa pela contagem desc.

Snapshot stubado em `routes` (plataforma); nada sai da maquina.
"""
import base64, io, json, os, sys, tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

TMP = tempfile.mkdtemp()

from apps.pages import routes as R                          # noqa: E402
from apps import create_app                                 # noqa: E402
from apps.config import DebugConfig                         # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

# O card mora em features/weekly_escalation; o arquivo de destinatarios pende
# da pasta de plataforma por busca atrasada.
from apps.pages.features.weekly_escalation import queries as WEQ             # noqa: E402
WE_blocks = WEQ.blocks
R._DAILY_METRIC_DIR = TMP

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

LINHAS = [
    {'Client': 'ACME SA',   'SPN': '100', 'Aging': '45', 'LOB': 'CEM'},
    {'Client': 'ACME SA',   'SPN': '100', 'Aging': '75', 'LOB': 'CEM'},
    {'Client': 'DELTA SA',  'SPN': '',    'Aging': '40', 'LOB': 'CEM', 'Owner': 'Beltrano'},
    {'Client': 'BETA LTD',  'SPN': '200', 'Aging': '95', 'LOB': 'EDG'},
    {'Client': 'FORA LOB',  'SPN': '200', 'Aging': '99', 'LOB': 'GDT'},   # LOB fora: cai
    {'Client': 'JOVEM',     'SPN': '100', 'Aging': '10', 'LOB': 'CEM'},   # < 30: cai
]
REFDATA = {'100': {'BANKER': 'Fulano'}, '200': {'BANKER': 'Sicrano'}}
R._pc_latest_snapshot_rows = lambda: ([dict(r) for r in LINHAS], 'stub')
R._fxo_refdata_by_spn = lambda: {R._norm_spn(k): v for k, v in REFDATA.items()}
R._pc_refdata_by_name = lambda: {}
NOTIFS = []
R._create_notification = lambda sid, nome, acao, pagina, msg='': NOTIFS.append((acao, pagina))

print('== 1. sem sessao ==')
check('GET recipients -> 401', anon.get('/api/control-panel/weekly-escalation/recipients').status_code, 401)
check('POST run -> 401', anon.post('/api/control-panel/weekly-escalation/run').status_code, 401)

print('\n== 2. a quebra por LOB, banqueiro e empresa ==')
blocos = WE_blocks([dict(r) for r in LINHAS])
check('duas LOBs, nesta ordem', [b['lob'] for b in blocos], ['CEM', 'EDG'])
cem = blocos[0]
check('CEM: banqueiro do RefData primeiro (total desc), Owner como fallback',
      [(b['banker'], b['total']) for b in cem['bankers']],
      [('Fulano', 2), ('Beltrano', 1)])
check('   as empresas com a contagem', cem['bankers'][0]['companies'],
      [{'name': 'ACME SA', 'count': 2}])
check('   o total da LOB fecha', cem['total'], 3)
check('EDG: so a linha da LOB', (blocos[1]['total'], blocos[1]['bankers'][0]['banker']),
      (1, 'Sicrano'))
check('LOB fora de CEM/EDG e aging < 30 ficam de fora',
      sum(b['total'] for b in blocos), 4)

print('\n== 3. destinatarios e o rascunho ==')
c.post('/api/control-panel/weekly-escalation/recipients',
       json={'to': 'banker@jpmorgan.com', 'cc': 'mesa@jpmorgan.com'})
d = c.get('/api/control-panel/weekly-escalation/recipients').get_json()
check('TO/CC persistem', (d['to'], d['cc']), ('banker@jpmorgan.com', 'mesa@jpmorgan.com'))
r = c.post('/api/control-panel/weekly-escalation/run', json={'date': '2026-08-26'})
d = r.get_json()
check('200 com o nome do arquivo', (r.status_code, d['filename']),
      (200, 'Weekly_Escalation_CEM_EDG_26082026.eml'))
eml = base64.b64decode(d['b64']).decode('utf-8', 'replace')
check('   X-Unsent = rascunho editavel', 'X-Unsent: 1' in eml, True)
check('   o assunto leva a data',
      'Pending Confirmation - Weekly Escalation - CEM/EDG 26/08/2026' in eml, True)
check('   e avisa no sino', NOTIFS[-1], ('Weekly Escalation Draft', 'Control Panel'))

print('\n== 4. sem destinatario e 400 ==')
c.post('/api/control-panel/weekly-escalation/recipients', json={'to': '', 'cc': ''})
r = c.post('/api/control-panel/weekly-escalation/run')
check('400 pedindo as listas', (r.status_code, 'destinat' in r.get_json()['error']), (400, True))

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
