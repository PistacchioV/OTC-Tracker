# -*- coding: utf-8 -*-
"""O liga/desliga do envio AUTOMÁTICO dos cards do Control Panel (§722).

  1. `platform/auto_send`: sem arquivo os seis estão LIGADOS; desligar e ligar
     gravam; a leitura que falha LEVANTA (nunca "ligado" nem "desligado"
     chutado);
  2. o disparo automático dos sete cards (seis de e-mail e a planilha do
     Pending, que GRAVA no share): DESLIGADO reserva o horário, grava o
     desfecho `disabled` e NÃO envia; LIGADO envia; leitura que falha levanta
     ANTES de reservar (o laço tenta de novo, o horário não se perde);
  3. a rota `/api/control-panel/auto-send`: GET com os cards da pessoa, POST
     liga/desliga, payload ruim é 400, card sem acesso é 403;
  4. a tela: um interruptor por card (os mesmos seis), nascendo escondido; o
     desfecho `disabled` desenhado nos seis cards; textos nas três línguas; os
     seis ids existem no `_CONTROL_PANEL_CARDS`; e cada laço pergunta ao
     interruptor do SEU card;
  5. o card escondido por ambiente (`CP_HIDDEN_CARDS`, §724 — o New Version
     Released no Stratos): sai do Control Panel e das caixas do /page-access.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_cp_auto_send.py
"""
import json
import os
import re
import sys
import tempfile
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps import create_app                                      # noqa: E402
from apps.config import DebugConfig                              # noqa: E402

app = create_app(DebugConfig)
from apps.pages import routes as R                               # noqa: E402
from apps.pages import data_store as S                           # noqa: E402
from apps.pages.platform import auto_send as AS                  # noqa: E402
from apps.pages.platform import authz as AZ                      # noqa: E402

R._DAILY_METRIC_DIR = tempfile.mkdtemp(prefix='cp-auto-')
fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def ler(*p):
    return open(os.path.join(ROOT, *p), encoding='utf-8').read()


print('== 1. o interruptor ==')
check('sem arquivo, todos ligados', {c: v['enabled'] for c, v in AS.estado().items()},
      {c: True for c in AS.CARDS})
AS.definir('baccea', False, 'T000001', 'Teste')
check('desligar grava', (AS.ligado('baccea'), AS.ligado('mt300')), (False, True))
check('   com quem e quando', AS.estado()['baccea']['by'], 'Teste')
AS.definir('baccea', True, 'T000001')
check('ligar de novo', AS.ligado('baccea'), True)
try:
    AS.definir('outro', False)
    check('card fora da lista recusa', False)
except ValueError:
    check('card fora da lista recusa', True)
_read0 = S.read


def _ocupado(*a, **k):
    raise S.BancoOcupado('control-panel')


S.read = _ocupado
try:
    AS.ligado('baccea')
    check('leitura que falha LEVANTA', False)
except S.BancoOcupado:
    check('leitura que falha LEVANTA', True)
finally:
    S.read = _read0

print('\n== 2. o disparo automático dos sete ==')
from apps.pages.features.bacc import commands as BACC              # noqa: E402
from apps.pages.features.bacc.infra import persistence as BACCP    # noqa: E402
from apps.pages.features.mt300 import commands as MT               # noqa: E402
from apps.pages.features.mt300.infra import persistence as MTP     # noqa: E402
from apps.pages.features.mdea import commands as MD                # noqa: E402
from apps.pages.features.mdea.infra import persistence as MDP      # noqa: E402
from apps.pages.features.conf_escalation import commands as CE     # noqa: E402
from apps.pages.features.conf_escalation.infra import persistence as CEP  # noqa: E402
from apps.pages.features.deals_monitor import commands as DM       # noqa: E402
from apps.pages.features.deals_monitor.infra import persistence as DMP    # noqa: E402
from apps.pages.features.projects import commands as PJ            # noqa: E402
from apps.pages.features.projects.infra import alerts as PJA       # noqa: E402
from apps.pages.features.pcx import commands as PCX                # noqa: E402
from apps.pages.features.pcx.infra import persistence as PCXP      # noqa: E402

AGORA = datetime(2026, 10, 29, 19, 0)
_biz0 = R._pcx_is_bizday
R._pcx_is_bizday = lambda d: True


def caso(nome, card, mod_claim, attr_claim, mod_status, attr_status, mod_envio, attr_envio, envio_ret, dispara):
    """Liga/desliga o card e confere: reservou? gravou `disabled`? enviou?"""
    for ligado in (False, True):
        AS.definir(card, ligado)
        reg = {'claim': 0, 'status': [], 'envio': 0}
        orig = (getattr(mod_claim, attr_claim), getattr(mod_status, attr_status), getattr(mod_envio, attr_envio))

        def _claim(*a, **k):
            reg['claim'] += 1
            return True

        def _status(*a, **k):
            reg['status'].append(a)

        def _envio(*a, **k):
            reg['envio'] += 1
            return envio_ret

        setattr(mod_claim, attr_claim, _claim)
        setattr(mod_status, attr_status, _status)
        setattr(mod_envio, attr_envio, _envio)
        try:
            dispara()
        finally:
            setattr(mod_claim, attr_claim, orig[0])
            setattr(mod_status, attr_status, orig[1])
            setattr(mod_envio, attr_envio, orig[2])
        if ligado:
            check('%s ligado: envia' % nome, (reg['claim'], reg['envio']), (1, 1))
        else:
            check('%s desligado: reserva, grava `disabled` e NÃO envia' % nome,
                  (reg['claim'], reg['envio'], any(AS.DESLIGADO in a for a in reg['status'])), (1, 0, True))
    # leitura que falha: levanta antes de reservar
    reg = {'claim': 0}
    orig = getattr(mod_claim, attr_claim)
    setattr(mod_claim, attr_claim, lambda *a, **k: reg.__setitem__('claim', reg['claim'] + 1) or True)
    S.read = _ocupado
    try:
        dispara()
        check('%s: leitura que falha levanta' % nome, False)
    except S.BancoOcupado:
        check('%s: leitura que falha levanta ANTES de reservar' % nome, reg['claim'], 0)
    finally:
        S.read = _read0
        setattr(mod_claim, attr_claim, orig)


caso('BACC EA', 'baccea', BACCP, 'claim_slot', BACCP, 'write_status', BACC, 'run',
     {'sent': True, 'rows': 1}, lambda: BACC.fire_slot('2026-10-29 16:00', AGORA))
caso('MT300', 'mt300', MTP, 'claim_slot', MTP, 'write_status', MT, 'run',
     {'sent': True, 'rows': 1}, lambda: MT.fire_slot('2026-10-29 19:30', AGORA))
caso('Manual Deals EA', 'manualdealsea', MDP, 'claim_slot', MDP, 'write_status', MD, 'run',
     {'sent': True, 'rows': 1}, lambda: MD.fire_slot('routine', '2026-10-29 10:00', AGORA))
caso('Confirmations Escalation', 'confescalation', CEP, 'claim_slot', CEP, 'write_status', CE, 'run',
     {'sent': [{'rows': 1}], 'errors': [], 'skipped': []},
     lambda: (setattr(CE, '_registra', lambda *a, **k: None), CE.fire_slot('routine', '2026-10-29 09:00', AGORA)))
_rec0 = DMP._load_ndm_pending_recipients
DMP._load_ndm_pending_recipients = lambda: {'to': 'a@jpmorgan.com', 'cc': ''}
caso('Intraday Monitor', 'intradaytasks', DMP, '_ndm_pending_claim_slot', DMP, '_ndm_pending_status_write',
     DM, '_send_ndm_pending_email', True, lambda: DM._ndm_pending_disparar('2026-10-29 19:00', AGORA))
DMP._load_ndm_pending_recipients = _rec0
caso('Initiatives Alerts', 'initiativealerts', PJA, 'claim', PJA, 'write_status', PJ, 'run_alerts',
     {'initiatives': 1}, lambda: PJ.alerts_run_once(datetime(2026, 10, 29, 9, 0)))
# o sétimo não manda e-mail: GRAVA a planilha do Pending (o "envio" é o save)
caso('Pending Spreadsheet', 'pendingspreadsheet', PCXP, 'claim_slot', PCXP, 'write_status', PCX, 'save',
     (1, 'x.xlsx'), lambda: PCX.fire_slot('2026-10-29 10:45', AGORA))
R._pcx_is_bizday = _biz0
for c in AS.CARDS:
    AS.definir(c, True)

print('\n== 3. a rota ==')
cl = app.test_client()
with cl.session_transaction() as s:
    s.update(authenticated=True, user_sid='T000001', user_name='Teste', user_role='ADMIN', session_ip='127.0.0.1')
_acc0 = R._get_page_access
R._get_page_access = lambda sid: (True, {'/control-panel#baccea', '/control-panel#mt300'})
try:
    d = cl.get('/api/control-panel/auto-send').get_json() or {}
    check('GET: só os cards da pessoa', sorted((d.get('cards') or {}).keys()), ['baccea', 'mt300'])
    r = cl.post('/api/control-panel/auto-send', json={'card': 'mt300', 'enabled': False})
    check('POST desliga', (r.status_code, (r.get_json() or {}).get('enabled'), AS.ligado('mt300')), (200, False, False))
    r = cl.post('/api/control-panel/auto-send', json={'card': 'mt300', 'enabled': 'no'})
    check('payload ruim: 400', r.status_code, 400)
    r = cl.post('/api/control-panel/auto-send', json={'card': 'confescalation', 'enabled': False})
    check('card sem acesso: 403', (r.status_code, AS.ligado('confescalation')), (403, True))
    R._get_page_access = lambda sid: (False, set())
    d = cl.get('/api/control-panel/auto-send').get_json() or {}
    check('acesso não configurado: todos', sorted((d.get('cards') or {}).keys()), sorted(AS.CARDS))
finally:
    R._get_page_access = _acc0
    AS.definir('mt300', True)

print('\n== 4. a tela e os laços ==')
html = ler('apps', 'templates', 'pages', 'control-panel.html')
check('um interruptor por card, os mesmos da lista',
      sorted(re.findall(r'data-cp-auto="([a-z0-9]+)" hidden', html)), sorted(AS.CARDS))
for c in AS.CARDS:
    bloco = html[html.index('<div class="cp-card" data-cp-card="%s">' % c):]
    check('   o de %s mora no card dele' % c, bloco.index('data-cp-auto="%s"' % c) < bloco.index('cp-card__title'))
check('o desfecho `disabled` desenhado nos sete cards (cpAutoSkipped)', html.count('cpAutoSkipped(') - 1, len(AS.CARDS))
for lang in ('en', 'br', 'es'):
    tr = json.loads(ler('apps', 'static', 'data', 'translations', lang + '.json'))
    check('textos em %s' % lang, all(tr.get(k) for k in (
        'cp-auto-on', 'cp-auto-off', 'cp-auto-skipped', 'cp-auto-toast-on', 'cp-auto-toast-off', 'cp-auto-fail')))
ids = {c['id'] for c in AZ._CONTROL_PANEL_CARDS}
check('todos são cards do Control Panel', set(AS.CARDS) <= ids)
LACOS = {'baccea': 'bacc', 'mt300': 'mt300', 'manualdealsea': 'mdea', 'confescalation': 'conf_escalation',
         'intradaytasks': 'deals_monitor', 'initiativealerts': 'projects', 'pendingspreadsheet': 'pcx'}
check('um laço por card', sorted(LACOS), sorted(AS.CARDS))
for card, feat in LACOS.items():
    fonte = ler('apps', 'pages', 'features', feat, 'commands.py')
    check('o laço de %s pergunta ao interruptor DELE' % card,
          re.findall(r"auto_send\.ligado\('([a-z0-9]+)'\)", fonte), [card])

print('\n== 5. card escondido por ambiente (CP_HIDDEN_CARDS, §724) ==')
with cl.session_transaction() as s:
    s.update(authenticated=True, user_sid='E930179', user_name='Master', user_role='MASTER', session_ip='127.0.0.1')
html = cl.get('/control-panel').get_data(as_text=True)
check('sem a configuração: o New Version Released aparece', 'data-cp-card="appversion"' in html)
pa = cl.get('/page-access').get_data(as_text=True)
check('   e é caixa no /page-access', '"appversion"' in pa)
app.config['CP_HIDDEN_CARDS'] = ('appversion',)
try:
    html = cl.get('/control-panel').get_data(as_text=True)
    check('escondido: o card e a seção Application saem',
          ('data-cp-card="appversion"' in html, 'data-cp-hdr="application"' in html), (False, False))
    check('   os outros cards ficam', 'data-cp-card="mt300"' in html)
    pa = cl.get('/page-access').get_data(as_text=True)
    check('   e sai das caixas do /page-access', ('"appversion"' in pa, '"mt300"' in pa), (False, True))
finally:
    app.config.pop('CP_HIDDEN_CARDS', None)

print(('\nFALHAS (%d): %s' % (len(fails), fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
