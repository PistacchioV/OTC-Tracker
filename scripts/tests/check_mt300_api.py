# -*- coding: utf-8 -*-
"""O card MT300 ponta a ponta — os dois endpoints e o disparo automatico.

O `check_mt300.py` (33 assercoes) protege o MOTOR: quem entra, o sinal, o
contravalor derivado. O que ninguem prendia era a casca HTTP, e ali moram as
decisoes que nao dao erro nenhum:

  1. **dia sem operacao do grupo e SUCESSO com aviso, nao erro** — o Run devolve
     200 com "e-mail not sent": a rotina funcionou, nao havia o que casar no
     DVP. E o oposto do BACC, onde a planilha vazia VAI;
  2. **o POST das listas e MERGE, nao substituicao** — gravar so o TO nao apaga
     o Cc (que nasce com a caixa do OTC Ops); chave presente e vazia LIMPA;
  3. **o Run manual grava as listas que vierem no payload ANTES de rodar** — e o
     botao do card, que envia o que esta na tela — e NAO consome o claim do
     disparo das 19:30;
  4. **no automatico, `empty` e `no_recipient` CONSOMEM o slot** (nenhum dos
     dois melhora na retentativa) e **erro de SMTP o DEVOLVE**.

SMTP e stubado no modulo `smtplib`; o arquivo-dia e o cadastro em tempfile.
Nada sai da maquina.
"""
import io, json, os, sys, tempfile, smtplib
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)

TMP = tempfile.mkdtemp()

from apps.pages import routes as R                          # noqa: E402

# Os schedulers de verdade nao sobem num teste: depois das 19:30 o catch-up do
# proprio MT300 tentaria reivindicar o slot REAL e mandar o e-mail do dia.
R._SCHEDULERS[:] = []

from apps import create_app                                 # noqa: E402
from apps.config import DebugConfig                         # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

# O card mora em features/mt300. Os arquivos saem TODOS da pasta de plataforma
# (`routes._DAILY_METRIC_DIR`) por busca atrasada, entao UM redirecionamento
# aponta os tres para o tmp.
from apps.pages.features.mt300 import commands as C                  # noqa: E402
from apps.pages.features.mt300.infra import persistence as P         # noqa: E402

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

# ── o cadastro e o arquivo-dia de mentira ───────────────────────────────────
_real_mapping = R._mapping_rows
R._mapping_rows = lambda key, *a, **kw: (
    [{'COUNTERPARTY': 'NESTLE BRASIL SA', 'CNPJ': '60.409.075/0001-52', 'SPN': '806544'}]
    if key == 'mt300' else _real_mapping(key, *a, **kw))

HOJE = R._br_now()
_dia_dir = os.path.join(TMP, 'nd')
os.makedirs(os.path.join(_dia_dir, HOJE.strftime('%Y'), HOJE.strftime('%m')), exist_ok=True)
_cfg = R._generic_nd_cfg('vanilla')
_dia_path = os.path.join(_dia_dir, HOJE.strftime('%Y'), HOJE.strftime('%m'),
                         HOJE.strftime('%Y%m%d') + _cfg['suffix'])


def grava_dia(deals):
    io.open(_dia_path, 'w', encoding='utf-8').write(json.dumps(deals))


DEAL = {'Deal': 'D5VL-XYZ', 'Client': 'NESTLE BRASIL LTDA.', 'TaxID': '60.409.075/0001-52',
        'SPN': '806544', 'LE': 'JPM', 'Instrument': 'Avg Rate Forward',
        'TradeDate': '26/08/2026', 'SettlementDate': '27/01/2027',
        'Notional': '1,000.00', 'Rate': '5.25470000', 'LastFixingDate': '20/01/2027',
        'QuantityCurrency': 'USD', 'OtherQuantityCurrency': 'BRL', 'Direction': 'SELL'}
grava_dia([DEAL])
_orig_dir = R._GENERIC_ND_PRODUCTS['vanilla']['dir']
R._GENERIC_ND_PRODUCTS['vanilla']['dir'] = _dia_dir

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
        ENVIADOS.append({'rcpt': list(destinatarios), 'msg': corpo})


smtplib.SMTP = _FakeSMTP

NOTIFS = []
R._create_notification = lambda sid, nome, acao, pagina, msg='': NOTIFS.append((acao, pagina, msg))

try:
    print('== 1. sem sessao ==')
    check('GET recipients -> 401', anon.get('/api/control-panel/mt300/recipients').status_code, 401)
    check('POST run -> 401', anon.post('/api/control-panel/mt300/run').status_code, 401)

    print('\n== 2. as listas: merge, nao substituicao ==')
    d = c.get('/api/control-panel/mt300/recipients').get_json()
    check('GET antes de gravar: Cc nasce com a caixa do OTC Ops',
          (d['to'], d['cc']), ('', 'brazil.otc.ops@jpmorgan.com'))
    check('   rows conta a operacao do grupo de hoje', d['rows'], 1)
    check('   time = 19:30', d['time'], '19:30')
    c.post('/api/control-panel/mt300/recipients', json={'to': 'grupo@cliente.com'})
    d = c.get('/api/control-panel/mt300/recipients').get_json()
    check('gravar so o TO preserva o Cc padrao',
          (d['to'], d['cc']), ('grupo@cliente.com', 'brazil.otc.ops@jpmorgan.com'))
    c.post('/api/control-panel/mt300/recipients', json={'cc': ''})
    d = c.get('/api/control-panel/mt300/recipients').get_json()
    check('   e a chave presente-e-vazia LIMPA aquela lista',
          (d['to'], d['cc']), ('grupo@cliente.com', ''))
    c.post('/api/control-panel/mt300/recipients', json={'cc': 'brazil.otc.ops@jpmorgan.com'})

    print('\n== 3. o Run manual ==')
    r = c.post('/api/control-panel/mt300/run', json={'to': 'novo@cliente.com'})
    d = r.get_json()
    check('o payload grava ANTES de rodar (o botao envia o que esta na tela)',
          (r.status_code, d['sent'], d['rows']), (200, True, 1))
    check('   a mensagem conta', d['message'], '1 trade(s) sent to 1 recipient(s) (+1 in copy).')
    check('   rcpt = TO novo + Cc', sorted(ENVIADOS[-1]['rcpt']),
          ['brazil.otc.ops@jpmorgan.com', 'novo@cliente.com'])
    check('   o assunto leva a data do dia',
          ('Subject: MT300 - %s' % HOJE.strftime('%d/%m/%Y')) in ENVIADOS[-1]['msg'], True)
    st = json.load(io.open(P.status_file(), encoding='utf-8'))
    check('   status gravado, claim do automatico intacto',
          (st['result'], os.path.exists(P.claim_file())), ('sent:1', False))
    check('   e avisa no sino', NOTIFS[-1][:2], ('MT300 Sent', 'Control Panel'))

    print('\n== 4. dia sem operacao do grupo: SUCESSO com aviso ==')
    grava_dia([dict(DEAL, Client='SUZANO SA', TaxID='16.404.287/0001-55', SPN='999')])
    r = c.post('/api/control-panel/mt300/run')
    d = r.get_json()
    check('200 com e-mail not sent', (r.status_code, d['success'], d['sent']), (200, True, False))
    check('   dizendo o motivo', 'e-mail not sent' in d['message'], True)
    grava_dia([DEAL])

    print('\n== 5. sem TO e 400; SMTP fora e 500 ==')
    c.post('/api/control-panel/mt300/recipients', json={'to': ''})
    r = c.post('/api/control-panel/mt300/run')
    check('400 pedindo o TO', (r.status_code, 'No TO recipient saved' in r.get_json()['error']),
          (400, True))
    c.post('/api/control-panel/mt300/recipients', json={'to': 'grupo@cliente.com'})
    _FakeSMTP.falha = OSError('connection refused')
    r = c.post('/api/control-panel/mt300/run')
    check('500 com o erro', (r.status_code, 'connection refused' in r.get_json()['error']),
          (500, True))
    _FakeSMTP.falha = None

    print('\n== 6. o disparo automatico ==')
    _biz_real = R._pcx_is_bizday
    R._pcx_is_bizday = lambda d: False
    check('feriado nao dispara', C.fire_slot('2026-08-25 19:30', HOJE), False)
    R._pcx_is_bizday = lambda d: True

    # `empty` CONSOME o slot: sem operacao nao ha e-mail, e retentar nao muda.
    grava_dia([dict(DEAL, Client='SUZANO SA', TaxID='16.404.287/0001-55', SPN='999')])
    check('dia vazio dispara e consome', C.fire_slot('2026-08-25 19:30', HOJE), True)
    st = json.load(io.open(P.status_file(), encoding='utf-8'))
    check('   com o desfecho no status', st['result'], 'empty')
    grava_dia([DEAL])
    check('   e o slot fica consumido', C.fire_slot('2026-08-25 19:30', HOJE), False)

    # Erro de SMTP DEVOLVE o slot: a proxima volta retenta e o dia nao se perde.
    _FakeSMTP.falha = OSError('smtp fora')
    check('falha de envio dispara', C.fire_slot('2026-08-26 19:30', HOJE), True)
    _FakeSMTP.falha = None
    n_antes = len(ENVIADOS)
    check('   e a retentativa do MESMO slot envia',
          (C.fire_slot('2026-08-26 19:30', HOJE), len(ENVIADOS) - n_antes), (True, 1))
    st = json.load(io.open(P.status_file(), encoding='utf-8'))
    check('   com o status do dia', st['result'], 'sent:1')
    R._pcx_is_bizday = _biz_real
finally:
    R._GENERIC_ND_PRODUCTS['vanilla']['dir'] = _orig_dir
    R._mapping_rows = _real_mapping

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
