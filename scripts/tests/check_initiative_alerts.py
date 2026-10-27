# -*- coding: utf-8 -*-
"""Os alertas das iniciativas — e-mail + sino (§701).

O que se prova:
  1. `domain.alerts`: sem atualização há MAIS de 5 dias úteis (5 não basta);
     prazo da iniciativa e da tarefa aberta a 2 dias úteis ou menos (3 não; a
     tarefa Done não); o fim no próprio dia e até 7 dias depois; só `On going`;
  2. `run_alerts`: UM e-mail por iniciativa, TO = o box + quem está nela, CC
     do card sem repetir o TO; o sino só para os envolvidos, do ator SYSTEM
     (o toast mostra o logo); a chave marcada — o segundo disparo não manda
     nada; e-mail que falha não marca nem toca o sino;
  3. o disparo automático: só a partir das 08:00 e em dia útil;
  4. o card do Control Panel (registro, rotas do card, template), o scheduler
     no `routes`, a preferência da Settings e as traduções.
"""
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.check-share'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


from apps import create_app                                      # noqa: E402
from apps.config import DebugConfig                              # noqa: E402

app = create_app(DebugConfig)
from apps.pages import routes as R                               # noqa: E402
from apps.pages.features.projects import commands as C, domain as D   # noqa: E402
from apps.pages.features.projects.infra import alerts as A, store as S  # noqa: E402


def uteis(a, b):
    """Dias de semana em (a, b] — o calendário do teste, sem feriado."""
    a, b = date.fromisoformat(a[:10]), date.fromisoformat(b[:10])
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        n += d.weekday() < 5
    return n


HOJE = '2026-10-27'          # terça
print('== 1. domain.alerts ==')
base = {'id': 'PRJ-0001', 'name': 'Projeto X', 'status': 'On going', 'lead_sid': 'L000001',
        'members': [{'sid': 'M000002', 'name': 'M'}], 'tasks': []}
k = lambda p: sorted(a['kind'] for a in D.alerts(p, HOJE, uteis))
check('6 dias úteis sem atualização: stale', k(dict(base, updated_at='2026-10-19 10:00:00')), ['stale'])
check('5 dias úteis: ainda não', k(dict(base, updated_at='2026-10-20 10:00:00')), [])
check('prazo a 2 dias úteis: due_soon', k(dict(base, updated_at=HOJE, due_date='2026-10-29')), ['due_soon'])
check('prazo a 3 dias úteis: ainda não', k(dict(base, updated_at=HOJE, due_date='2026-10-30')), [])
check('o fim é hoje: ends', k(dict(base, updated_at=HOJE, due_date=HOJE)), ['ends'])
check('o fim passou há 7 dias e não saiu: ends', k(dict(base, updated_at=HOJE, due_date='2026-10-20')), ['ends'])
check('há 8 dias: não', k(dict(base, updated_at=HOJE, due_date='2026-10-19')), [])
tarefas = [{'id': 't1', 'title': 'Aberta', 'status': 'In progress', 'due': '2026-10-28', 'assignee_name': 'Ana'},
           {'id': 't2', 'title': 'Feita', 'status': 'Done', 'due': '2026-10-28'},
           {'id': 't3', 'title': 'Longe', 'status': 'To do', 'due': '2026-11-10'}]
al = D.alerts(dict(base, updated_at=HOJE, tasks=tarefas), HOJE, uteis)
check('só a tarefa aberta a 1 dia útil', [(a['kind'], a['params']['task']) for a in al], [('task_due', 'Aberta')])
check('a chave diz iniciativa, tarefa e data', al[0]['key'], 'PRJ-0001:t1:due:2026-10-28')
for st in ('On hold', 'Concluded'):
    check('%s não alerta' % st, D.alerts(dict(base, status=st, updated_at='2026-09-01', due_date=HOJE), HOJE, uteis), [])

print('\n== 2. run_alerts ==')
DOC = {'projects': [dict(base, updated_at='2026-10-19 10:00:00', due_date='2026-10-29',
                         tasks=[{'id': 't1', 'title': 'Tarefa', 'status': 'To do', 'due': '2026-10-28',
                                 'assignee_sid': 'T000003', 'assignee_name': 'Tito'}]),
                    dict(base, id='PRJ-0002', name='Tranquilo', updated_at=HOJE)]}
S.load = lambda: DOC
R._anbima_biz_diff = lambda a, b: uteis(a.strftime('%Y-%m-%d'), b.strftime('%Y-%m-%d'))
FEITAS, ENVIOS, SINO, STATUS = set(), [], [], {}
A.sent_keys = lambda strict=False: set(FEITAS)
A.mark_sent = lambda keys: FEITAS.update(keys)
A.load_recipients = lambda: {'to': 'brazil.otc.ops@jpmorgan.com', 'cc': 'master@jpmorgan.com; l1@jpmorgan.com'}
A.write_status = lambda r: STATUS.__setitem__('r', r)
A.emails_of = lambda sids: {s: s.lower()[:2] + '@jpmorgan.com' for s in sids}
RESP = {'v': True}


def _send(assunto, html, to, cc):
    ENVIOS.append((assunto, to, cc, html))
    return RESP['v']


A.send = _send
R._user_wants = lambda sid, key: True
R._create_notification = lambda *a, **k: SINO.append((a, k))
r = C.run_alerts(HOJE)
check('uma iniciativa, três alertas', (r['initiatives'], r['alerts']), (1, 3))
assunto, to, cc, html = ENVIOS[0]
check('TO = o box + lead, time e responsável', to,
      ['brazil.otc.ops@jpmorgan.com', 'l0@jpmorgan.com', 'm0@jpmorgan.com', 't0@jpmorgan.com'])
check('CC do card', cc, ['master@jpmorgan.com', 'l1@jpmorgan.com'])
check('o assunto diz a iniciativa e a data', assunto, 'Initiative alert — Projeto X — 27/10/2026')
check('o corpo tem as três frases', all(x in html for x in ('No update for 6 business days',
                                                           'Initiative due in 2 business day(s)',
                                                           'Task &quot;Tarefa&quot; due in 1 business day(s)')
                                        ) or all(x in html for x in ('No update for 6 business days',
                                                                     'Initiative due in 2 business day(s)',
                                                                     'Task "Tarefa" due')), True)
check('o sino: só os três envolvidos, ator SYSTEM, página Initiatives',
      sorted((a[0], a[1], a[2], a[3], k['target_sid']) for a, k in SINO),
      sorted(('SYSTEM', 'OTC Tracker', 'Initiative Alert', 'Initiatives', s)
             for s in ('L000001', 'M000002', 'T000003')))
check('status do card', STATUS['r'], 'sent:1')
ENVIOS.clear(); SINO.clear()
r = C.run_alerts(HOJE)
check('segundo disparo: nada (cada alerta sai uma vez)', (r['initiatives'], ENVIOS, SINO, STATUS['r']),
      (0, [], [], 'empty'))
FEITAS.clear(); RESP['v'] = 'SMTPError: relay'
r = C.run_alerts(HOJE)
check('e-mail que falha: não marca e não toca o sino', (FEITAS, SINO, r['failed'][0][0]),
      (set(), [], 'PRJ-0001'))
check('   e o status diz o erro', STATUS['r'].startswith('error:'), True)

print('\n== 3. o disparo automático ==')
CHAMOU = []
C.run_alerts = lambda today, **k: CHAMOU.append(today) or {'initiatives': 0}
A.claim = lambda slot: True
check('antes das 08:00: nada', C.alerts_run_once(datetime(2026, 10, 27, 7, 59)), None)
check('sábado: nada', C.alerts_run_once(datetime(2026, 10, 31, 9, 0)), None)
C.alerts_run_once(datetime(2026, 10, 27, 8, 5))
check('dia útil, 08:05: dispara para o dia', CHAMOU, ['2026-10-27'])


def src(*rel):
    return open(os.path.join(ROOT, *rel), encoding='utf-8').read()


print('\n== 4. card, scheduler, preferência ==')
from apps.pages.platform import authz                            # noqa: E402
check('o card no registro, depois do Confirmations Escalation',
      [c['id'] for c in authz._CONTROL_PANEL_CARDS][2:4], ['confescalation', 'initiativealerts'])
check('as duas rotas do card', {authz._CP_ENDPOINT_CARD.get('/api/control-panel/initiative-alerts/' + x)
                               for x in ('recipients', 'run')}, {'initiativealerts'})
rotas = {str(r) for r in app.url_map.iter_rules()}
check('as rotas existem', {'/api/control-panel/initiative-alerts/recipients',
                           '/api/control-panel/initiative-alerts/run'} <= rotas, True)
cp = src('apps', 'templates', 'pages', 'control-panel.html')
check('o card no template', 'data-cp-card="initiativealerts"' in cp and 'data-ia-run' in cp, True)
check('o scheduler registrado no routes',
      "_schedule_on_start('initiative-alerts', _f_projects.start_alerts_scheduler)" in src('apps', 'pages', 'routes.py'),
      True)
from apps.pages.features.user_home import domain as UH            # noqa: E402
check('a preferência da Settings', ('initiative_alerts' in UH.NOTIFY_KEYS,
                                    "['initiative_alerts'," in src('apps', 'static', 'js', 'pages', 'settings.js')),
      (True, True))
for lg in ('en', 'br', 'es'):
    tr = json.load(open(os.path.join(ROOT, 'apps', 'static', 'data', 'translations', lg + '.json'), encoding='utf-8'))
    check('traduções do card em %s' % lg, all(k in tr for k in ('cp-r-ia-title', 'cp-r-ia-desc', 'cp-ia-to',
                                                                  'cp-ia-sent', 'cp-ia-empty')), True)
check('o ícone da ação no topbar', bool(re.search(r"'Initiative Alert':\s*\{ icon:", src('apps', 'templates', 'partials', 'topbar.html'))), True)

print(('\nFAIL: %d' % len(fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
