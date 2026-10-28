# -*- coding: utf-8 -*-
"""New Deals › DCE › FXO: a réplica do Option › FXO para o offshore (§721).

A página é a MESMA tela e o MESMO backend do Opt FXO, com a variante `dce` no
request (`platform.new_deals.FXO_VARIANTS`): cache próprio
(`DCE_FXO_CACHE_DIR`), rótulo próprio no sino (`DCE FXO`) e nome próprio do
arquivo da B3 (`FXO_DCE_<visão>`). Ainda NÃO está ligada à API da Athena
(equipe, 28/10/2026).

  1. a página existe: as rotas `/api/new-deals/dce-fxo/*`, o template chamando
     só elas (nenhum `opt-fxo` que grave), o menu (página PRÓPRIA, sem
     `data-nav-alias`), o título traduzido, o rótulo nos três mapas do sino, o
     card no Intraday Monitor e a família no backfill da esteira;
  2. o cache é SEPARADO: o Add Row da DCE grava no cache dela, a busca da DCE
     acha e a do Opt FXO não; Edit e Delete pela DCE acham a linha; o sino diz
     `DCE FXO`;
  3. sem API: o `import-api` da DCE responde 501 com código, o template não o
     chama, e o pull automático segue só no onshore mesmo dentro de um
     request da DCE;
  4. o Send Conecta (preview) da DCE nomeia o arquivo `FXO_DCE_…`;
  5. as confirmações leem os DOIS caches (mesmo documento, mesma esteira), sem
     repetir o mesmo Deal.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_dce_fxo.py
"""
import os
import re
import sys
import tempfile
from datetime import datetime, timezone, timedelta

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

TMP = tempfile.mkdtemp(prefix='dce-fxo-')

from apps import create_app                                      # noqa: E402
from apps.config import DebugConfig                              # noqa: E402

app = create_app(DebugConfig)
from apps.pages import routes as R                               # noqa: E402
from apps.pages.platform import new_deals as ND                  # noqa: E402
from apps.pages.platform import notifications as NOTIF           # noqa: E402
from apps.pages.features.deals_monitor import domain as DM       # noqa: E402

DCE_REAL = R.DCE_FXO_CACHE_DIR
R.OPT_FXO_CACHE_DIR = os.path.join(TMP, 'opt')
R.DCE_FXO_CACHE_DIR = os.path.join(TMP, 'dce')

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def ler(*partes):
    return open(os.path.join(ROOT, *partes), encoding='utf-8').read()


print('== 1. a página ==')
rotas = {str(r) for r in app.url_map.iter_rules() if '/dce-fxo' in str(r)}
for suf in ('/cache', '/cache/search', '/cache/<deal_id>', '/cache/bulk-delete', '/cache/bulk-patch',
            '/cache/batch', '/import-xlsx', '/send-conecta', '/mapping-b3', '/premium-email', '/import-api'):
    check('rota /api/new-deals/dce-fxo%s' % suf, '/api/new-deals/dce-fxo' + suf in rotas)
tpl = ler('apps', 'templates', 'pages', 'new_deals-dce-fxo.html')
check('o template não chama nenhuma API do Opt FXO', re.findall(r'/api/new-deals/opt-fxo', tpl), [])
check('o template não chama o import-api', 'dce-fxo/import-api' in tpl, False)
check('título próprio', 'data-lang="nd-dce-fxo-page-title"' in tpl and '{% block title %}DCE FXO Options' in tpl)
side = ler('apps', 'templates', 'partials', 'sidenav.html')
m = re.search(r'<a href="/new_deals-dce-fxo"([^>]*)>', side)
check('no menu, como página PRÓPRIA (sem data-nav-alias)', bool(m) and 'data-nav-alias' not in m.group(1))
import json                                                       # noqa: E402
for lang in ('en', 'br', 'es'):
    tr = json.loads(ler('apps', 'static', 'data', 'translations', lang + '.json'))
    check('textos em %s' % lang, all(tr.get(k) for k in (
        'nd-dce-fxo-page-title', 'swal-dce-fxo-no-api-title', 'swal-dce-fxo-no-api')))
check('sino: _NOTIF_PAGE_URL', NOTIF._NOTIF_PAGE_URL.get('DCE FXO'), '/new_deals-dce-fxo')
check('sino: topbar', "'DCE FXO':             '/new_deals-dce-fxo'" in ler('apps', 'templates', 'partials', 'topbar.html'))
check('sino: sw-push', "'DCE FXO': '/new_deals-dce-fxo'" in ler('apps', 'static', 'js', 'sw-push.js'))
card = next((c for c in DM._NDM_CARDS if c['key'] == 'dce-fxo'), None)
check('card no Intraday Monitor, pasta DCE/FXO', (card or {}).get('dirs'), ('DCE/FXO',))
check('   a pasta do card é a do cache (cache/new deals/DCE/FXO)',
      os.path.normpath(DCE_REAL).endswith(os.path.join('new deals', 'DCE', 'FXO')))
check('   na taxonomia e no grupo de opções da tela',
      'dce-fxo' in DM._NDM_TAXONOMY and "'opt-fxo', 'dce-fxo'" in ler('apps', 'templates', 'pages', 'intraday-monitor.html'))
import importlib.util                                             # noqa: E402
spec = importlib.util.spec_from_file_location('bf', os.path.join(ROOT, 'scripts', 'backfill_manual_confirmations.py'))
BF = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BF)
check('família no backfill da esteira', BF.FAMILIES.get('DCE FXO', {}).get('dir'), ('DCE', 'FXO'))

print('\n== 2. o cache separado ==')
avisos = []
_notif = R._create_notification
R._create_notification = lambda *a, **k: avisos.append(a[3] if len(a) > 3 else k.get('page'))
c = app.test_client()
with c.session_transaction() as s:
    s.update(authenticated=True, user_sid='T000001', user_name='T', user_role='ADMIN', session_ip='127.0.0.1',
             session_expires_at=(datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat())
DEAL = {'Deal': 'DCE-1', 'Client': 'CLIENTE OFFSHORE', 'TradeDate': '28/10/2026', 'Status': 'New',
        'TradeType': 'VANILLA', 'Instrument': 'CALL', 'Direction': 'BUY', 'TotalNotional': '1000000',
        'Strike': '5.40', 'UnderlyingAsset': 'USD', 'StrikeCurrency': 'BRL', 'SettlementDate': '30/11/2026',
        'SpotDate': '30/10/2026', 'PremiumPerUnit': '0.05'}
try:
    r = c.post('/api/new-deals/dce-fxo/cache', json=dict(DEAL))
    check('Add Row da DCE grava', (r.status_code, (r.get_json() or {}).get('success')), (200, True))
    dce_fp = os.path.join(R.DCE_FXO_CACHE_DIR, '2026', '10', '20261028_optfxo.json')
    check('   no cache DELA', os.path.isfile(dce_fp))
    check('   e não no do Opt FXO', os.path.isdir(R.OPT_FXO_CACHE_DIR), False)
    achou = [d['Deal'] for d in (c.post('/api/new-deals/dce-fxo/cache/search', json={'filters': []}).get_json() or {}).get('deals', [])]
    check('a busca da DCE acha', achou, ['DCE-1'])
    achou = [d['Deal'] for d in (c.post('/api/new-deals/opt-fxo/cache/search', json={'filters': []}).get_json() or {}).get('deals', [])]
    check('a busca do Opt FXO não acha', achou, [])
    r = c.patch('/api/new-deals/dce-fxo/cache/DCE-1?client=CLIENTE%20OFFSHORE', json={'Strike': '5.50'})
    check('Edit pela DCE acha a linha', (r.status_code, (r.get_json() or {}).get('success')), (200, True))
    check('   o sino diz DCE FXO', avisos[-1:], ['DCE FXO'])
    r = c.patch('/api/new-deals/opt-fxo/cache/DCE-1?client=CLIENTE%20OFFSHORE', json={'Strike': '5.60'})
    check('Edit pelo Opt FXO NÃO acha a linha da DCE', r.status_code, 404)

    print('\n== 3. sem API ==')
    r = c.post('/api/new-deals/dce-fxo/import-api', json={})
    check('import-api da DCE: 501 com código', (r.status_code, (r.get_json() or {}).get('code')),
          (501, 'dce_api_not_connected'))
    with app.test_request_context('/'):
        from flask import g
        g.nd_fxo_variant = 'dce'
        check('a variante do request é a DCE', ND._fxo_variant(), 'dce')
        gravou = []
        orig = (ND._fxo_api_fetch, ND._fxo_api_apply)
        ND._fxo_api_fetch = lambda ref_date=None: (datetime(2026, 10, 28), '20261028', [])
        ND._fxo_api_apply = lambda records, ref_dt, date, sid='API', actor_name='', variant=None: gravou.append(variant) or {}
        try:
            ND._fxo_api_pull()
        finally:
            ND._fxo_api_fetch, ND._fxo_api_apply = orig
        check('o pull da API segue no onshore mesmo dentro da DCE', gravou, ['onshore'])
    check('a DCE não tem cadastro de interbook', ND.FXO_VARIANTS['dce']['interbook'], None)

    print('\n== 4. o arquivo da B3 ==')
    r = c.post('/api/new-deals/dce-fxo/send-conecta', json={'deals': [dict(DEAL)], 'download': True})
    j = r.get_json() or {}
    if j.get('ok'):
        check('preview da DCE: FXO_DCE_…', [f['filename'] for f in j.get('files', [])], ['FXO_DCE_Banco.txt'])
        j2 = c.post('/api/new-deals/opt-fxo/send-conecta', json={'deals': [dict(DEAL)], 'download': True}).get_json() or {}
        check('preview do Opt FXO segue FXO_…', [f['filename'] for f in j2.get('files', [])], ['FXO_Banco.txt'])
    else:
        print('  skip: sem o template do File Interpreter nesta máquina (%s)' % j.get('error'))

    print('\n== 5. as confirmações leem os dois caches ==')
    from apps.pages.platform import confirmations as CF
    ND._fxo_persist_deals([dict(DEAL, Deal='ON-1', Client='CLIENTE ONSHORE')], 'onshore')
    ND._fxo_persist_deals([dict(DEAL, Deal='ON-1', Client='CLIENTE ONSHORE')], 'dce')   # o mesmo nos dois
    with app.test_request_context('/'):
        deals = sorted((d['Deal'], d['Client']) for d in CF._conf_load_optfxo(datetime(2026, 10, 28)))
    check('onshore + DCE, o repetido uma vez', deals,
          [('DCE-1', 'CLIENTE OFFSHORE'), ('ON-1', 'CLIENTE ONSHORE')])

    r = c.delete('/api/new-deals/dce-fxo/cache/DCE-1?client=CLIENTE%20OFFSHORE')
    check('Delete pela DCE', (r.status_code, (r.get_json() or {}).get('success')), (200, True))
finally:
    R._create_notification = _notif

print(('\nFALHAS (%d): %s' % (len(fails), fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
