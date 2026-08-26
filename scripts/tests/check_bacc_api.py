# -*- coding: utf-8 -*-
"""O card BACC EA Metrics ponta a ponta — os dois endpoints e o disparo.

Escrito ANTES de o BACC sair do `routes.py`, para a extracao ter contra o que
provar. O que ele prende e o que nao da erro nenhum quando cai:

  1. **planilha vazia VAI assim mesmo** — um dia sem operacao manual e ele
     proprio a metrica. O unico motivo de nao enviar e lista de TO em branco
     (`no_recipient`), que o Run devolve como 400 dizendo o que preencher;
  2. **o Run manual nao consome o claim do automatico** — ele grava o status
     como slot `manual`, e queimar o horario faria o relatorio do dia nao sair;
  3. **no automatico, `no_recipient` CONSOME o slot** (retentar nao mudaria
     nada; quem resolve e o card) e **erro de SMTP DEVOLVE o slot** (falha
     transitoria nao pode custar o dia);
  4. **a esteira fora do ar nao derruba o card**: o GET devolve `rows: None` e
     as listas continuam editaveis;
  5. horario invalido em `BACC_EA_METRICS_TIME` cai no padrao 16:00 — um typo
     no `.env` nao mata a rotina.

SMTP e stubado no modulo `smtplib` (vale antes e depois da extracao); a esteira
e stubada em `manual_conf.load_all`. Nada sai da maquina.
"""
import io, json, os, sys, tempfile, smtplib
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)

TMP = tempfile.mkdtemp()

from apps.pages import routes as R                          # noqa: E402
from apps.pages import manual_conf as M                     # noqa: E402

# Os schedulers de verdade nao sobem num teste: depois das 16:00 o catch-up do
# proprio BACC tentaria reivindicar o slot REAL e mandar o e-mail do dia.
R._SCHEDULERS[:] = []

from apps import create_app                                 # noqa: E402
from apps.config import DebugConfig                         # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

# O card mora em features/bacc. Os arquivos saem TODOS da pasta de plataforma
# (`routes._DAILY_METRIC_DIR`) por busca atrasada, entao UM redirecionamento
# aponta os tres para o tmp.
from apps.pages.features.bacc import commands as C, queries as Q     # noqa: E402
from apps.pages.features.bacc.infra import persistence as P          # noqa: E402

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

# ── a esteira de mentira ────────────────────────────────────────────────────
# Dicts crus bastam: quem le so faz .get(). T-D ja terminou (Ok) e T-E ja teve
# callback — os dois ficam FORA do anexo; a ordem e o aging decrescente.
FAKE = [
    {'Trade ID': 'T-A', 'Aging Confirmação': '3', 'Pending': 'Pending OTC',
     'Data Callback': '', 'Notional Amount CCY': 'USD 1500000',
     'Produto': 'FXO', 'Cliente': 'ACME', 'LOB': 'CEM'},
    {'Trade ID': 'T-B', 'Aging Confirmação': '12', 'Pending': 'Pending MO',
     'Data Callback': '', 'Notional Amount CCY': 'BRL 250000.50',
     'Produto': 'SWAP', 'Cliente': 'BETA', 'LOB': 'CEM'},
    {'Trade ID': 'T-D', 'Aging Confirmação': '99', 'Pending': 'Ok',
     'Data Callback': '', 'Notional Amount CCY': 'USD 1'},
    {'Trade ID': 'T-E', 'Aging Confirmação': '40', 'Pending': 'Pending OTC',
     'Data Callback': '01/08/2026', 'Notional Amount CCY': 'EUR 77'},
]
_real_load = M.load_all
M.load_all = lambda: [dict(r) for r in FAKE]


# ── SMTP de mentira, no MODULO — vale antes e depois da extracao ────────────
ENVIADOS = []


class _FakeSMTP(object):
    falha = None

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def sendmail(self, remetente, destinatarios, corpo):
        if _FakeSMTP.falha:
            raise _FakeSMTP.falha
        ENVIADOS.append({'from': remetente, 'rcpt': list(destinatarios), 'msg': corpo})


smtplib.SMTP = _FakeSMTP

NOTIFS = []
R._create_notification = lambda sid, nome, acao, pagina, msg='': NOTIFS.append((acao, pagina, msg))

print('== 1. sem sessao ==')
check('GET recipients -> 401', anon.get('/api/control-panel/bacc-ea-metrics/recipients').status_code, 401)
check('POST run -> 401', anon.post('/api/control-panel/bacc-ea-metrics/run').status_code, 401)

print('\n== 2. as listas do card ==')
r = c.get('/api/control-panel/bacc-ea-metrics/recipients')
d = r.get_json()
check('GET antes de gravar -> vazio', (r.status_code, d['to'], d['cc']), (200, '', ''))
# O anexo teria as duas linhas pendentes de agora — o card mostra o numero.
check('   rows = o que o anexo teria', d['rows'], 2)
check('   time = o horario do disparo', d['time'], '16:00')
r = c.post('/api/control-panel/bacc-ea-metrics/recipients',
           json={'to': 'metricas@jpmorgan.com; ops@jpmorgan.com', 'cc': 'Metricas@jpmorgan.com, chefe@jpmorgan.com'})
check('POST grava', (r.status_code, r.get_json()['success']), (200, True))
d = c.get('/api/control-panel/bacc-ea-metrics/recipients').get_json()
check('   e o GET devolve verbatim',
      (d['to'], d['cc']),
      ('metricas@jpmorgan.com; ops@jpmorgan.com', 'Metricas@jpmorgan.com, chefe@jpmorgan.com'))

print('\n== 3. a esteira fora do ar nao derruba o card ==')
M.load_all = lambda: (_ for _ in ()).throw(RuntimeError('duckdb travado'))
d = c.get('/api/control-panel/bacc-ea-metrics/recipients').get_json()
check('GET continua 200 com rows None', (d['success'], d['rows']), (True, None))
M.load_all = lambda: [dict(r) for r in FAKE]

print('\n== 4. o Run manual ==')
r = c.post('/api/control-panel/bacc-ea-metrics/run')
d = r.get_json()
check('envia', (r.status_code, d['success'], d['sent']), (200, True, True))
check('   as 2 pendentes, 2 TO, 1 CC (o repetido do TO cai, cego a caixa)',
      (d['rows'], d['to'], d['cc']), (2, 2, 1))
check('   a mensagem conta os tres', d['message'],
      '2 operation(s) sent to 2 recipient(s) (+1 in copy).')
env = ENVIADOS[-1]
check('   rcpt = TO + CC', sorted(env['rcpt']),
      ['chefe@jpmorgan.com', 'metricas@jpmorgan.com', 'ops@jpmorgan.com'])
check('   o assunto e contrato e nao muda',
      'Subject: Support to OTC Derivatives - EA Metrics' in env['msg'], True)
nome = 'EA Metrics - {}.xlsx'.format(R._br_now().strftime('%Y%m%d'))
check('   o anexo e o do dia', ('filename="%s"' % nome) in env['msg'], True)
st = json.load(io.open(P.status_file(), encoding='utf-8'))
check('   status = slot manual, sem tocar no claim do automatico',
      (st['slot'], st['result'], os.path.exists(P.claim_file())),
      ('manual', 'sent:2', False))
check('   e avisa no sino', NOTIFS[-1][:2], ('BACC EA Metrics Sent', 'Control Panel'))

print('\n== 5. planilha vazia VAI assim mesmo ==')
M.load_all = lambda: []
r = c.post('/api/control-panel/bacc-ea-metrics/run')
d = r.get_json()
check('sent com 0 linhas', (r.status_code, d['sent'], d['rows']), (200, True, 0))
M.load_all = lambda: [dict(r) for r in FAKE]

print('\n== 6. sem TO nao sai de casa ==')
c.post('/api/control-panel/bacc-ea-metrics/recipients', json={'to': '', 'cc': 'chefe@jpmorgan.com'})
r = c.post('/api/control-panel/bacc-ea-metrics/run')
check('400 pedindo o TO', (r.status_code, 'No TO recipient saved' in r.get_json()['error']),
      (400, True))
c.post('/api/control-panel/bacc-ea-metrics/recipients',
       json={'to': 'metricas@jpmorgan.com', 'cc': ''})

print('\n== 7. SMTP fora do ar e 500, e o status do dia fica como estava ==')
antes = json.load(io.open(P.status_file(), encoding='utf-8'))
_FakeSMTP.falha = OSError('connection refused')
r = c.post('/api/control-panel/bacc-ea-metrics/run')
check('500 com o erro', (r.status_code, 'connection refused' in r.get_json()['error']), (500, True))
check('   status intacto', json.load(io.open(P.status_file(), encoding='utf-8')), antes)
_FakeSMTP.falha = None

print('\n== 8. o horario do disparo nao morre por typo ==')
_time_real = P.TIME_RAW
P.TIME_RAW = '07:30'
check('07:30 vale', Q.send_time(), (7, 30))
P.TIME_RAW = '25:99'
check('typo cai no padrao', Q.send_time(), (16, 0))
P.TIME_RAW = _time_real

print('\n== 9. o disparo automatico ==')
_biz_real = R._pcx_is_bizday
R._pcx_is_bizday = lambda d: False
agora = R._br_now()
check('feriado nao dispara', C.fire_slot('2026-08-25 16:00', agora), False)
R._pcx_is_bizday = lambda d: True

# no_recipient CONSOME o slot: retentar nao mudaria nada, quem resolve e o card.
c.post('/api/control-panel/bacc-ea-metrics/recipients', json={'to': '', 'cc': ''})
check('sem TO o disparo acontece', C.fire_slot('2026-08-25 16:00', agora), True)
st = json.load(io.open(P.status_file(), encoding='utf-8'))
check('   com o desfecho no status', st['result'], 'no_recipient')
c.post('/api/control-panel/bacc-ea-metrics/recipients', json={'to': 'metricas@jpmorgan.com'})
check('   e o slot fica consumido', C.fire_slot('2026-08-25 16:00', agora), False)

# Erro de SMTP DEVOLVE o slot: a proxima volta do laco retenta e o dia nao se
# perde por uma falha transitoria.
_FakeSMTP.falha = OSError('smtp fora')
check('falha de envio dispara', C.fire_slot('2026-08-26 16:00', agora), True)
_FakeSMTP.falha = None
n_antes = len(ENVIADOS)
check('   e a retentativa do MESMO slot envia',
      (C.fire_slot('2026-08-26 16:00', agora), len(ENVIADOS) - n_antes), (True, 1))
st = json.load(io.open(P.status_file(), encoding='utf-8'))
check('   com o status do dia', st['result'], 'sent:2')

R._pcx_is_bizday = _biz_real
M.load_all = _real_load

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
