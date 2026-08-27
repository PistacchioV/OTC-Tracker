# -*- coding: utf-8 -*-
"""O card Settlement Forecast — a casca (data/recipients/email).

O COLETOR (`_forecast_spine/_collect/_payload/_latest_ref`) e plataforma: o
Other Products Summary le os mesmos numeros, e por isso ele fica no routes.
O que este teste prende e a casca:

  1. `data` sem arquivo nenhum e **400 mandando rodar o Save CETIP Files** —
     nao um payload vazio que desenharia um grafico zerado;
  2. TO/CC persistem e o email sem destinatario salvo e 400;
  3. ⚠️ **VERRUGA registrada de proposito**: os cabecalhos To/Cc do e-mail
     levam as listas SALVAS, mas o ENVELOPE (sendmail) vai para
     CETIP_OTC_OPS_EMAIL + _ACC_ENDPROC_CC — quem realmente recebe NAO e quem
     esta no card. Consertar isso e mudanca de comportamento e nao pertence a
     extracao; este teste existe para ninguem "consertar" sem decidir.
"""
import io, json, os, sys, tempfile, smtplib
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

# O card mora em features/forecast; o arquivo de destinatarios pende da pasta
# de plataforma por busca atrasada.
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

PAYLOAD = {'ref_date_fmt': '26/08/2026', 'date_labels': ['27/08'],
           'products': [], 'entities': [], 'col_totals': [], 'grand_total': 0,
           'sources': [{'key': 'x', 'found': True}]}
R._forecast_payload = lambda ref, days=None: dict(PAYLOAD)

ENVIADOS = []


class _FakeSMTP(object):
    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def sendmail(self, remetente, destinatarios, corpo):
        ENVIADOS.append({'rcpt': list(destinatarios), 'msg': corpo})


smtplib.SMTP = _FakeSMTP
NOTIFS = []
R._create_notification = lambda sid, nome, acao, pagina, msg='': NOTIFS.append((acao, pagina))

print('== 1. sem sessao ==')
for ep, met in [('data', 'post'), ('recipients', 'get'), ('email', 'post')]:
    check('%s -> 401' % ep,
          getattr(anon, met)('/api/control-panel/settlement-forecast/' + ep).status_code, 401)

print('\n== 2. data sem arquivo nenhum e 400 dizendo o que rodar ==')
R._forecast_payload = lambda ref, days=None: dict(PAYLOAD, sources=[{'key': 'x', 'found': False}])
r = c.post('/api/control-panel/settlement-forecast/data', json={'date': '2026-08-25'})
check('400 com Save CETIP Files', (r.status_code, 'Save CETIP Files' in r.get_json()['error']),
      (400, True))
R._forecast_payload = lambda ref, days=None: dict(PAYLOAD)
r = c.post('/api/control-panel/settlement-forecast/data', json={'date': '2026-08-25'})
check('com arquivo, 200', (r.status_code, r.get_json()['success']), (200, True))

print('\n== 3. TO/CC persistem; email sem lista e 400 ==')
r = c.post('/api/control-panel/settlement-forecast/email', json={'date': '2026-08-25'})
check('sem destinatario, 400', r.status_code, 400)
c.post('/api/control-panel/settlement-forecast/recipients',
       json={'to': 'chefe@jpmorgan.com', 'cc': 'mesa@jpmorgan.com'})
d = c.get('/api/control-panel/settlement-forecast/recipients').get_json()
check('TO/CC persistem', (d['to'], d['cc']), ('chefe@jpmorgan.com', 'mesa@jpmorgan.com'))

print('\n== 4. o envio — e a verruga do envelope ==')
r = c.post('/api/control-panel/settlement-forecast/email',
           json={'date': '2026-08-25', 'images': {}})
check('200', (r.status_code, r.get_json()['success']), (200, True))
env = ENVIADOS[-1]
check('os HEADERS levam as listas salvas',
      ('To: chefe@jpmorgan.com' in env['msg'], 'Cc: mesa@jpmorgan.com' in env['msg']),
      (True, True))
# ⚠️ A verruga: o envelope ignora o card e vai para as caixas fixas.
check('   mas o ENVELOPE vai para as caixas fixas (verruga registrada)',
      env['rcpt'], [R.CETIP_OTC_OPS_EMAIL] + list(R._ACC_ENDPROC_CC))
check('   e avisa no sino', NOTIFS[-1], ('Settlement Forecast Sent', 'Control Panel'))

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
