# -*- coding: utf-8 -*-
"""O card Daily Metric (Outstanding Confirmation Brazil OTC) ponta a ponta.

O que ele prende, e que nao da erro nenhum quando cai:

  1. **o Run nao ENVIA nada — gera um RASCUNHO .eml** (X-Unsent: 1) que volta em
     base64 no JSON: quem assina quer ler antes de sair. O Bcc vai no HEADER,
     ao contrario de um envio de verdade (o rascunho precisa pre-preencher o
     campo para a pessoa revisar);
  2. **o pivo por grupo economico**: so aging >= 30, baldes 30-59/60-89/>=90,
     verde quando o RefData marca assinatura DIGITAL, ordenado do maior total;
  3. **o mes/dia em curso e carimbado com a leitura de AGORA** e o pct refeito
     — sem isso o cartao dizia 177 e a ultima barra 167;
  4. sem destinatario salvo o Run devolve 400 pedindo as listas.

Snapshot e historia stubados em `routes` (plataforma); nada sai da maquina.
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

# O card mora em features/daily_metric; o arquivo de destinatarios pende da
# pasta de plataforma por busca atrasada.
from apps.pages.features.daily_metric import domain as DMD, queries as DMQ   # noqa: E402
DM_pivot = DMQ.pivot
DM_stamp = DMD.stamp_now
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

# ── plataforma stubada: o snapshot e a historia ─────────────────────────────
LINHAS = [
    {'Client': 'ACME SA',  'SPN': '100', 'Aging': '45', 'LOB': 'CEM'},
    {'Client': 'ACME SA',  'SPN': '100', 'Aging': '75', 'LOB': 'CEM'},
    {'Client': 'BETA LTD', 'SPN': '200', 'Aging': '95', 'LOB': 'EDG'},
    {'Client': 'NOVO SEM REF', 'SPN': '', 'Aging': '31', 'LOB': 'CEM'},
    {'Client': 'JOVEM',    'SPN': '300', 'Aging': '10', 'LOB': 'CEM'},   # < 30: fora
]
REFDATA = {'100': {'ECONOMIC GROUP': 'GRUPO ACME', 'BANKER': 'Fulano', 'SIGNATURE TYPE': 'Digital'},
           '200': {'ECONOMIC GROUP': 'GRUPO BETA', 'BANKER': 'Sicrano', 'SIGNATURE TYPE': 'Manual'}}
R._pc_latest_snapshot_rows = lambda: ([dict(r) for r in LINHAS], 'stub')
R._pc_metrics_history = lambda: {'gt30': {
    'monthly': [{'period': '2026-07', 'volume': 150, 'pct': None},
                {'period': '2026-08', 'volume': 167, 'pct': 11}],
    'daily':   [{'date': '2026-08-25', 'volume': 160, 'pct': None}],
}}
R._fxo_refdata_by_spn = lambda: {R._norm_spn(k): v for k, v in REFDATA.items()}
R._pc_refdata_by_name = lambda: {}
NOTIFS = []
R._create_notification = lambda sid, nome, acao, pagina, msg='': NOTIFS.append((acao, pagina))

print('== 1. sem sessao ==')
check('GET recipients -> 401', anon.get('/api/control-panel/daily-metric/recipients').status_code, 401)
check('POST run -> 401', anon.post('/api/control-panel/daily-metric/run').status_code, 401)

print('\n== 2. o pivo por grupo economico ==')
pivot, totals = DM_pivot([dict(r) for r in LINHAS])
check('so aging >= 30 entra, agrupado pelo ECONOMIC GROUP do RefData',
      [(p['group'], p['b1'], p['b2'], p['b3'], p['total']) for p in pivot],
      [('GRUPO ACME', 1, 1, 0, 2), ('GRUPO BETA', 0, 0, 1, 1), ('NOVO SEM REF', 1, 0, 0, 1)])
check('   verde so quando o RefData diz DIGITAL',
      [p['digital'] for p in pivot], [True, False, False])
check('   banker do RefData', [p['banker'] for p in pivot][:2], ['Fulano', 'Sicrano'])
check('   totais fecham', (totals['b1'], totals['b2'], totals['b3'], totals['total']),
      (2, 1, 1, 4))

print('\n== 3. o periodo em curso e carimbado com a leitura de agora ==')
serie = [{'period': '2026-07', 'volume': 150, 'pct': None},
         {'period': '2026-08', 'volume': 167, 'pct': 11}]
out = DM_stamp(serie, 'period', '2026-08', 177)
check('o ponto do mes corrente vira o total de agora', (out[-1]['volume'], out[-1]['pct']),
      (177, 18))
out = DM_stamp(serie, 'period', '2026-09', 90)
check('   e um mes novo ganha ponto proprio, com pct contra o anterior',
      (len(out), out[-1]['period'], out[-1]['volume'], out[-1]['pct']), (3, '2026-09', 90, -46))

print('\n== 4. destinatarios ==')
c.post('/api/control-panel/daily-metric/recipients',
       json={'to': 'chefe@jpmorgan.com', 'cc': 'mesa@jpmorgan.com', 'bcc': 'b1@x.com, b2@x.com'})
d = c.get('/api/control-panel/daily-metric/recipients').get_json()
check('TO/CC/BCC persistem', (d['to'], d['cc'], d['bcc']),
      ('chefe@jpmorgan.com', 'mesa@jpmorgan.com', 'b1@x.com, b2@x.com'))

print('\n== 5. o Run gera RASCUNHO, nao envio ==')
r = c.post('/api/control-panel/daily-metric/run', json={'date': '2026-08-26'})
d = r.get_json()
check('200 com o nome do arquivo', (r.status_code, d['filename']),
      (200, 'Daily_Metric_Outstanding_Confirmation_26082026.eml'))
eml = base64.b64decode(d['b64']).decode('utf-8', 'replace')
check('   X-Unsent = rascunho editavel no Outlook', 'X-Unsent: 1' in eml, True)
check('   o Bcc vai no HEADER (o rascunho pre-preenche o campo)',
      'Bcc: b1@x.com, b2@x.com' in eml, True)
check('   o assunto leva a data',
      'Daily Metric - Outstanding Confirmation Brazil OTC - 26/08/2026' in eml, True)
check('   e avisa no sino', NOTIFS[-1], ('Daily Metric Draft', 'Control Panel'))

print('\n== 6. sem destinatario nenhum e 400 ==')
c.post('/api/control-panel/daily-metric/recipients', json={'to': '', 'cc': '', 'bcc': ''})
r = c.post('/api/control-panel/daily-metric/run')
check('400 pedindo as listas', (r.status_code, 'destinat' in r.get_json()['error']), (400, True))

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
