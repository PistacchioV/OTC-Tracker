# -*- coding: utf-8 -*-
"""Pending Confirmation › Dashboard: a tabela dinamica da fila pendente.

O que ele prende:

  1. linhas por Economic Group x Owner x Signature Type, da maior para a menor;
     colunas por TRIMESTRE da Trade Date (`2026 T1`, em ordem cronologica, sem
     data por ultimo) x Pending Status (alfabetico dentro do trimestre);
  2. o filtro e a FAIXA de pendencia (a coluna Status do Main), e a lista de
     faixas sai da mesma funcao que grava o Status (`_pc_aging_band_label`);
     a contagem de cada faixa e da fila INTEIRA;
  3. a fonte e a MESMA do Daily Metric (`_pc_latest_snapshot_rows`);
  4. a rota, o menu e a pagina existem; sem sessao e 401.

A fila e stubada em `routes` (plataforma); nada toca dado real.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages import routes as R                          # noqa: E402
from apps import create_app                                 # noqa: E402
from apps.config import DebugConfig                         # noqa: E402
from apps.pages.features.pc_dashboard import domain as D, queries as Q   # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True
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
            s['session_ip'] = '127.0.0.1'
            s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    return c


B10 = R._pc_aging_band_label(5)
B30 = R._pc_aging_band_label(45)
B90 = R._pc_aging_band_label(120)
FILA = [
    {'Economic Group': 'REDE D OR', 'Owner': 'Thiago', 'Signature Type': 'MANUAL',
     'Trade Date': '15/02/2026', 'Pending Status': 'Pending Original', 'Status': B90},
    {'Economic Group': 'REDE D OR', 'Owner': 'Thiago', 'Signature Type': 'MANUAL',
     'Trade Date': '20/03/2026', 'Pending Status': 'Pending Original', 'Status': B90},
    {'Economic Group': 'ATLANTIC NICKEL', 'Owner': 'Felipe', 'Signature Type': 'DIGITAL',
     'Trade Date': '10/01/2026', 'Pending Status': 'Pending Digital Signature', 'Status': B90},
    {'Economic Group': 'ATLANTIC NICKEL', 'Owner': 'Felipe', 'Signature Type': 'DIGITAL',
     'Trade Date': '05/04/2026', 'Pending Status': 'Pending Digital Signature', 'Status': B30},
    {'Economic Group': 'ATLANTIC NICKEL', 'Owner': 'Felipe', 'Signature Type': 'DIGITAL',
     'Trade Date': '06/04/2026', 'Pending Status': 'Pending Digital Signature', 'Status': B30},
    {'Economic Group': 'SUZANO', 'Owner': 'Thiago', 'Signature Type': 'DIGITAL',
     'Trade Date': '11/02/2026', 'Pending Status': 'Pending OTC', 'Status': B10},
    {'Economic Group': '', 'Owner': '', 'Signature Type': '',
     'Trade Date': '', 'Pending Status': 'Pending POA', 'Status': B10},
]
LIDAS = []


def _fila():
    LIDAS.append(1)
    return [dict(r) for r in FILA], 'live'


R._pc_latest_snapshot_rows = _fila

print('== 1. a tabela dinamica ==')
d = Q.data()
check('trimestres em ordem, sem data por ultimo', [q['label'] for q in d['quarters']],
      ['2026 T1', '2026 T2', '(no date)'])
check('   status alfabetico dentro do trimestre',
      [c['status'] for c in d['columns'] if c['quarter'] == '2026 T1'],
      ['Pending Digital Signature', 'Pending Original', 'Pending OTC'])   # a ordem da imagem da mesa
check('   linhas da maior para a menor',
      [(r['group'], r['total']) for r in d['rows']],
      [('ATLANTIC NICKEL', 3), ('REDE D OR', 2), ('(no group)', 1), ('SUZANO', 1)])
check('   Owner e Signature Type na linha', (d['rows'][0]['owner'], d['rows'][0]['signature']),
      ('Felipe', 'DIGITAL'))
check('   o total geral fecha com a fila', d['totals']['total'], len(FILA))
check('   e cada coluna soma o que as linhas somam',
      d['totals']['values'], [sum(r['values'][i] for r in d['rows']) for i in range(len(d['columns']))])
check('   a mesma fonte do Daily Metric', bool(LIDAS), True)

print('\n== 2. o filtro por faixa de pendencia ==')
check('as faixas saem da funcao que grava o Status, na ordem',
      [b['label'] for b in d['bands']][0], R._pc_aging_band_label(0))
check('   seis faixas', len(d['bands']), 6)
f = Q.data([B90])
check('so a faixa escolhida entra', f['totals']['total'], 3)
check('   e a contagem do chip continua sendo a da fila inteira',
      {b['label']: b['count'] for b in f['bands']}[B30], 2)
check('   nenhuma faixa = tabela vazia', Q.data([])['totals']['total'], 0)
check('   trimestre sem linha na faixa some', [q['label'] for q in f['quarters']], ['2026 T1'])

print('\n== 3. dominio puro ==')
check('rotulo do trimestre', D.quarter_label(D.quarter_of(datetime(2026, 11, 3).date())), '2026 T4')

print('\n== 4. rotas e menu ==')
c, anon = cliente(), cliente(auth=False)
check('sem sessao e 401', anon.get('/api/dashboard-pending-confirmation/data').status_code, 401)
r = c.get('/api/dashboard-pending-confirmation/data?bands=' + json.dumps([B30]))
check('API filtra pela lista JSON', (r.status_code, r.get_json()['totals']['total']), (200, 2))
check('   lista malformada e 400', c.get('/api/dashboard-pending-confirmation/data?bands=x').status_code, 400)
check('a pagina abre', c.get('/dashboard-pending-confirmation').status_code, 200)
menu = open(os.path.join(ROOT, 'apps/templates/partials/sidenav.html'), encoding='utf-8').read()
check('o menu do Pending Confirmation tem o Dashboard', 'href="/dashboard-pending-confirmation"' in menu, True)

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
