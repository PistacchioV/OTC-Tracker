"""Deals Monitor › aviso de pendencias: o disparo das 19h00 e 19h30.

O aviso e uma rotina que ninguem observa: quando ele nao chega, nao ha erro na
tela, nao ha linha vermelha, nao ha nada — so um e-mail que nao veio. Este teste
prende as tres formas de isso acontecer:

  1. o horario QUEIMADO por uma falha. A reserva do slot e feita ANTES do envio
     (e o que impede dois processos de mandarem o mesmo aviso). Se o envio falha
     e o slot fica reservado, o aviso daquele horario esta perdido para sempre —
     nem o restart o recupera, porque o catch-up consulta a mesma lista. Uma
     queda de SMTP de um minuto custava o aviso do dia.

  2. o mesmo, sem destinatario cadastrado: o horario passava, o slot era
     queimado, e cadastrar o destinatario depois nao trazia o aviso de volta.

  3. 'empty' tratado como falha. Nada pendente e desfecho LEGITIMO: o slot fica
     reservado, senao a rotina ficaria retentando o dia inteiro um e-mail que
     nao tem o que dizer.

E prende a observabilidade, que e o que transforma "nao esta funcionando" em
fato: o desfecho do ultimo disparo e o proximo horario saem no endpoint que a
tela do Control Panel ja consome.

Nao encosta em dado real: relogio, SMTP e destinatarios sao stubs, os arquivos
de controle vao para um tempfile e as raizes do modulo voltam no finally.
"""
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R
# O Deals Monitor mora em features/deals_monitor, separado em camadas: o
# patch vai no módulo DONO de cada nome (as travessias entre camadas são
# por atributo de módulo, então o espião intercepta).
from apps.pages.features.deals_monitor import commands as C      # noqa: E402
from apps.pages.features.deals_monitor import domain as D        # noqa: E402
from apps.pages.features.deals_monitor import queries as Q       # noqa: E402
from apps.pages.features.deals_monitor.infra import persistence as P  # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


class Bench(object):
    """Um dia controlado: relogio, envio e destinatarios nas nossas maos."""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix='ndm-sched-')
        self.sent = []
        self.result = True
        self.recips = {'to': 'ops@x', 'cc': ''}
        self._real = (P._NDM_PENDING_SENT_FILE, P._NDM_PENDING_STATUS_FILE, R._DAILY_METRIC_DIR,
                      R._br_now, C._send_ndm_pending_email, P._load_ndm_pending_recipients)
        P._NDM_PENDING_SENT_FILE = os.path.join(self.tmp, 'sent.json')
        P._NDM_PENDING_STATUS_FILE = os.path.join(self.tmp, 'status.json')
        R._DAILY_METRIC_DIR = self.tmp
        R._br_now = lambda: self.now
        P._load_ndm_pending_recipients = lambda: dict(self.recips)
        C._send_ndm_pending_email = self._send
        self.times = D._ndm_pending_times()
        self.now = datetime(2026, 8, 5, 8, 0)

    def _send(self, ref, to, cc):
        if self.result is True:
            self.sent.append(ref.strftime('%d/%m %H:%M'))
            return True
        return self.result

    def tick(self, when):
        """Uma volta do laco naquele instante (e o que o scheduler faz)."""
        self.now = datetime.strptime(when, '%Y-%m-%d %H:%M')
        C._ndm_pending_catch_up(self.times)

    def claimed(self):
        try:
            return json.load(io.open(P._NDM_PENDING_SENT_FILE, encoding='utf-8'))
        except Exception:
            return []

    def status(self):
        try:
            return json.load(io.open(P._NDM_PENDING_STATUS_FILE, encoding='utf-8'))
        except Exception:
            return {}

    def close(self):
        (P._NDM_PENDING_SENT_FILE, P._NDM_PENDING_STATUS_FILE, R._DAILY_METRIC_DIR,
         R._br_now, C._send_ndm_pending_email, P._load_ndm_pending_recipients) = self._real
        shutil.rmtree(self.tmp, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────────
print('== 1. o dia normal ==')
b = Bench()
try:
    check('os dois horarios', b.times, [(19, 0), (19, 30)])
    b.tick('2026-08-05 18:55')
    check('antes da hora nao dispara', b.sent, [])
    b.tick('2026-08-05 19:00')
    check('as 19h00 dispara', b.sent, ['05/08 19:00'])
    b.tick('2026-08-05 19:10')
    check('e nao repete na volta seguinte', b.sent, ['05/08 19:00'])
    b.tick('2026-08-05 19:30')
    check('as 19h30 dispara o segundo', b.sent, ['05/08 19:00', '05/08 19:30'])
    b.tick('2026-08-05 22:00')
    check('e nada mais no resto do dia', len(b.sent), 2)

    print('\n== 2. o restart depois do horario recupera o dia ==')
    # A instancia do time reinicia varias vezes por dia; subindo as 20h o aviso
    # simplesmente nao saia.
    b2 = Bench()
    try:
        b2.tick('2026-08-06 20:00')
        check('sobe as 20h e recupera os DOIS', b2.sent, ['06/08 20:00', '06/08 20:00'])
    finally:
        b2.close()

    print('\n== 3. SMTP fora do ar: o horario NAO pode ser queimado ==')
    b3 = Bench()
    try:
        b3.result = 'SMTPServerDisconnected: connection lost'
        b3.tick('2026-08-07 19:00')
        check('nao enviou', b3.sent, [])
        check('o erro fica registrado', b3.status().get('result'), b3.result)
        check('e o slot foi DEVOLVIDO', '2026-08-07 19:00' in b3.claimed(), False)
        b3.result = True
        b3.tick('2026-08-07 19:05')
        check('voltando o SMTP, a proxima volta RETENTA', b3.sent, ['07/08 19:05'])
        check('e o status vira enviado', b3.status().get('result'), 'enviado')
        b3.tick('2026-08-07 19:10')
        check('sem duplicata depois disso', b3.sent, ['07/08 19:05'])
    finally:
        b3.close()

    print('\n== 4. sem destinatario: idem ==')
    b4 = Bench()
    try:
        b4.recips = {'to': '', 'cc': ''}
        b4.tick('2026-08-08 19:00')
        check('nao enviou', b4.sent, [])
        check('o motivo fica registrado', b4.status().get('result'), 'sem destinatário configurado')
        check('e o slot foi devolvido', '2026-08-08 19:00' in b4.claimed(), False)
        b4.recips = {'to': 'ops@x', 'cc': ''}
        b4.tick('2026-08-08 19:20')
        check('cadastrando depois, o aviso do dia sai', b4.sent, ['08/08 19:20'])
    finally:
        b4.close()

    print('\n== 5. "nada pendente" NAO e falha ==')
    b5 = Bench()
    try:
        b5.result = 'empty'
        b5.tick('2026-08-09 19:00')
        check('registra empty', b5.status().get('result'), 'empty')
        # Retentar seria ficar o dia inteiro atras de um e-mail que nao tem o
        # que dizer.
        check('e MANTEM o slot reservado', '2026-08-09 19:00' in b5.claimed(), True)
    finally:
        b5.close()

    print('\n== 6. a tela consegue responder "o aviso saiu?" ==')
    b6 = Bench()
    try:
        b6.tick('2026-08-10 19:00')
        st = Q._ndm_pending_status()
        check('traz o desfecho do ultimo disparo', st['last'].get('result'), 'enviado')
        check('   com o horario', st['last'].get('slot'), '2026-08-10 19:00')
        check('traz os horarios configurados', st['times'], ['19:00', '19:30'])
        check('e o proximo horario', st['next'], '10/08/2026 19:30')
        # Depois do ultimo do dia, o proximo e o primeiro de amanha.
        b6.now = datetime(2026, 8, 10, 21, 0)
        check('vira o dia depois do ultimo', Q._ndm_pending_status()['next'], '11/08/2026 19:00')
    finally:
        b6.close()
finally:
    b.close()

print('\n== 7. o endpoint publica o status ==')
from apps import create_app                                   # noqa: E402
from apps.config import DebugConfig                           # noqa: E402

app = create_app(DebugConfig)

# ── O disparo roda numa THREAD, e la NAO ha application context ──────────────
# `render_template` (o corpo do e-mail) e `_get_logo_path` (que le
# current_app.root_path) exigem um. Sem ele o envio automatico das 19h morria com
# "Working outside of application context" — e o sintoma enganava, porque o botao
# Run do Control Panel funcionava: aquele roda dentro de um request.
import threading                                              # noqa: E402


class _SMTPStub(object):
    raw = None

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def sendmail(self, frm, to, raw):
        _SMTPStub.raw = raw


_smtp_real, _blocks_real = R.smtplib.SMTP, Q._ndm_pending_blocks
R.smtplib.SMTP = _SMTPStub
Q._ndm_pending_blocks = lambda ref: ([{'tipo': 'Registration', 'label': 'NDF',
                                       'itens': [{'produto': 'NDF Commodities',
                                                  'total': 3, 'detalhe': 'New 3'}],
                                       'total': 3}], 3)
try:
    check('o app fica disponivel fora do request', R._FLASK_APP is app, True)
    _res = {}

    def _numa_thread():
        _res['r'] = C._send_ndm_pending_email(datetime(2026, 8, 7), ['a@b.com'], [])

    _t = threading.Thread(target=_numa_thread)
    _t.start()
    _t.join()
    check('o envio funciona SEM request context', _res['r'], True)
    check('   e o corpo foi renderizado',
          'Pending Action - Deals Monitor' in (_SMTPStub.raw or ''), True)
    check('   com o logo inline', 'otc_logo' in (_SMTPStub.raw or ''), True)
    with app.test_request_context('/'):
        check('e continua funcionando DENTRO de um request',
              C._send_ndm_pending_email(datetime(2026, 8, 7), ['a@b.com'], []), True)
finally:
    R.smtplib.SMTP, Q._ndm_pending_blocks = _smtp_real, _blocks_real

cl = app.test_client()
with cl.session_transaction() as s:
    s['authenticated'] = True
    s['user_sid'] = 'T000000'
    s['user_name'] = 'T'
    s['user_role'] = 'ADMIN'
    s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
j = cl.get('/api/control-panel/deals-monitor/recipients').get_json() or {}
check('responde', j.get('success'), True)
for k in ('to', 'cc', 'times', 'next', 'now_br', 'last'):
    check('publica %s' % k, k in j, True)

# E a tela consome os tres campos que importam.
CP = io.open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'control-panel.html'),
             encoding='utf-8').read()
check('o card tem onde mostrar', 'id="cp-dm2-status"' in CP, True)
check('e le o desfecho', 'renderStatus(d)' in CP, True)
check('o retry roda a cada volta do laco',
      '_ndm_pending_catch_up(times)' in
      io.open(os.path.join(ROOT, 'apps', 'pages', 'features', 'deals_monitor', 'commands.py'),
              encoding='utf-8').read().split('def _ndm_pending_scheduler_loop')[1].split('def ')[0], True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
