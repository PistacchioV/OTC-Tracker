# -*- coding: utf-8 -*-
"""As marcas do card dos swaps e o Economic Affirmation das operações MARCADAS
(§701).

O que se prova:
  1. `swap_new_deals.merge_flags`: só as quatro chaves, só bool; `None`
     devolve a marca à detecção;
  2. `/api/new-deals/swap-bullet/flags` grava SÓ o `SwapFlags` — o status,
     maker e checker ficam —, e o reimport o preserva (`KEEP_ON_REIMPORT`
     do Bullet e do Cashflow);
  3. `otcSwapFlags` (swap-deal.js, no node): Forward Start = Start ≠ Trade,
     Atualização de Notional = índice + data, Curva VCP = categoria de uma
     perna, Prêmio; a correção à mão vira `manual`;
  4. Economic Affirmation do swap: a IF do dia entra; a não-IF só MARCADA (em
     qualquer data, e com a data dela no rascunho); a perna interna nunca;
  5. o das commodities: a mesma regra (`_selected`), Lawton/JPM nunca;
  6. as páginas mandam o `_selected` e o tooltip tem chave própria (o rótulo
     do botão segue curto).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

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
app.config['TESTING'] = True
from apps.pages import routes as R                               # noqa: E402
from apps.pages import data_store as S                           # noqa: E402
from apps.pages import otc_emails as E                           # noqa: E402
from apps.pages.platform import swap_new_deals as SW             # noqa: E402
from apps.pages.features.swap_bullet.infra import persistence as BP   # noqa: E402
from apps.pages.features.swap_cashflow.infra import persistence as CP  # noqa: E402

R._create_notification = lambda *a, **k: None

print('== 1. merge_flags ==')
check('só as quatro chaves e só bool',
      SW.merge_flags({'fwd': True, 'x': True, 'vcp': 'sim'}, {'premium': False, 'outra': True}),
      {'fwd': True, 'premium': False})
check('None devolve à detecção', SW.merge_flags({'fwd': True, 'vcp': False}, {'fwd': None}), {'vcp': False})
check('lixo não quebra', SW.merge_flags('x', 'y'), {})

print('\n== 2. a rota grava só o SwapFlags ==')
TMP = tempfile.mkdtemp(prefix='swap-flags-')
BP.cache_dir = lambda: os.path.join(TMP, 'cache')
TD = datetime(2026, 10, 26)
fp = BP.day_path(TD)
os.makedirs(os.path.dirname(fp), exist_ok=True)
S.write(fp, [{'_id': 'SWB-1', 'TradeDate': '2026-10-26', 'Status': 'Approved', 'Maker': 'M1',
              'Checker': 'C1', 'Client': 'ACME'}])
cl = app.test_client()
with cl.session_transaction() as s:
    s.update(authenticated=True, user_sid='T000001', user_name='T', user_role='BO', session_ip='127.0.0.1',
             session_expires_at=(datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat())
r = cl.post('/api/new-deals/swap-bullet/flags',
            json={'deal_id': 'SWB-1', 'trade_date': '2026-10-26', 'flags': {'vcp': True}})
check('200', r.status_code, 200)
g = S.read(fp)[0]
check('   SwapFlags gravado; status, maker e checker como estavam',
      (g.get('SwapFlags'), g['Status'], g['Maker'], g['Checker']), ({'vcp': True}, 'Approved', 'M1', 'C1'))
r = cl.post('/api/new-deals/swap-bullet/flags',
            json={'deal_id': 'SWB-1', 'trade_date': '2026-10-26', 'flags': {'vcp': None}})
check('None limpa a correção', S.read(fp)[0].get('SwapFlags'), {})
r = cl.post('/api/new-deals/swap-bullet/flags', json={'deal_id': 'NAO-HA', 'trade_date': '2026-10-26',
                                                      'flags': {'vcp': True}})
check('deal inexistente: 404', r.status_code, 404)
check('o reimport preserva (Bullet e Cashflow)',
      ('SwapFlags' in BP.KEEP_ON_REIMPORT, 'SwapFlags' in CP.KEEP_ON_REIMPORT), (True, True))

print('\n== 3. otcSwapFlags (node) ==')
node = shutil.which('node')
if not node:
    check('node disponível', False, True)
else:
    js = r'''
global.window = global;
require(process.argv[1]);
function f(e){ return otcSwapFlags(e).map(function(x){ return [x.k, x.on, x.manual]; }); }
console.log(JSON.stringify([
  f({TradeDate:'2026-10-26', StartDate:'2026-11-06', NotionalIndex:'PTAX-V', NotionalObsDate:'2026-11-06',
     CurveACategory:'JUROS', CurveBCategory:'VCP', PremiumAmount:'1000'}),
  f({TradeDate:'2026-10-26', StartDate:'26/10/2026', CurveACategory:'JUROS', CurveBCategory:'TAXAS DE CAMBIO',
     PremiumSchedule:'Não', SwapFlags:{vcp:true, premium:false}})
]));
'''
    out = subprocess.run([node, '-e', js, os.path.join(ROOT, 'apps', 'static', 'js', 'swap-deal.js')],
                         capture_output=True, text=True, timeout=30)
    try:
        a, b = json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:                                            # noqa: BLE001
        a, b = None, None
    check('detectadas: as quatro acesas', a,
          [['fwd', True, False], ['notional', True, False], ['vcp', True, False], ['premium', True, False]])
    check('Start = Trade (outro formato) não é fwd; a correção vira manual; a igual à detecção não',
          b, [['fwd', False, False], ['notional', False, False], ['vcp', True, True], ['premium', False, False]])

print('\n== 4. Economic Affirmation do swap ==')
hoje = E._today_br()
iso_hoje = datetime.strptime(hoje, '%d/%m/%Y').strftime('%Y-%m-%d')
IF = {'_id': 'A', 'TradeDate': iso_hoje, 'Client': 'BANCO X SA', 'ClientAccount': '12345678',
      'ClientRefData': 'ok', 'LE': 'JPM'}
CLI = {'_id': 'B', 'TradeDate': iso_hoje, 'Client': 'BOTICARIO', 'ClientAccount': '73760102',
       'ClientAccountNote': 'omnibus', 'ClientRefData': 'ok', 'LE': 'JPM'}
VELHO = dict(CLI, _id='C', TradeDate='2026-10-20', Client='NATURA')
B2B = dict(CLI, _id='D', LE='LAWTON', Client='Lawton')
_orig_mail = E._swap_bullet_affirmation_email
E._swap_bullet_affirmation_email = lambda items, cli, acct, dia: {'cli': cli, 'dia': dia,
                                                                  'ids': [d['_id'] for d in items]}
try:
    sem = E.build_swap_bullet_affirmation_emails([IF, CLI, VELHO, B2B])
    check('sem marca: só a IF do dia', [d['cli'] for d in sem], ['BANCO X SA'])
    com = E.build_swap_bullet_affirmation_emails(
        [IF, dict(CLI, _selected=True), dict(VELHO, _selected=True), dict(B2B, _selected=True)])
    check('com marca: a IF e as marcadas, sem a perna interna',
          sorted((d['cli'], d['dia']) for d in com),
          sorted([('BANCO X SA', hoje), ('BOTICARIO', hoje), ('NATURA', '20/10/2026')]))
finally:
    E._swap_bullet_affirmation_email = _orig_mail

print('\n== 5. Economic Affirmation das commodities ==')
REC = {'IFX': {'B3 ACCOUNT': '12345.67-8', 'COUNTERPARTY': 'BANCO X SA'},
       'CLI': {'B3 ACCOUNT': '73760.10-2', 'COUNTERPARTY': 'FAZENDA Y'},
       'LAW': {'B3 ACCOUNT': '00041.00-7', 'COUNTERPARTY': 'LAWTON FUNDO'}}
_o = (E._build_refdata_index, E._build_refdata_spn_index, E._ref_for_deal, E._economic_affirmation_email)
E._build_refdata_index = lambda *a, **k: {}
E._build_refdata_spn_index = lambda *a, **k: {}
E._ref_for_deal = lambda a, b, d: REC.get(d.get('Acronym'), {})
E._economic_affirmation_email = lambda items, nome, b3, label: {'cli': nome}
try:
    base = [{'Deal': '1', 'Acronym': 'IFX', 'TradeDate': iso_hoje, 'Commodity': 'SOJA'},
            {'Deal': '2', 'Acronym': 'CLI', 'TradeDate': iso_hoje, 'Commodity': 'SOJA'},
            {'Deal': '3', 'Acronym': 'LAW', 'TradeDate': iso_hoje, 'Commodity': 'SOJA', 'Client': 'LAWTON'}]
    check('sem marca: só a IF', [d['cli'] for d in E.build_economic_affirmation_emails(base)], ['BANCO X SA'])
    marc = [dict(x, _selected=True) for x in base]
    check('marcadas: a não-IF entra, o Lawton não',
          sorted(d['cli'] for d in E.build_economic_affirmation_emails(marc)), ['BANCO X SA', 'FAZENDA Y'])
finally:
    E._build_refdata_index, E._build_refdata_spn_index, E._ref_for_deal, E._economic_affirmation_email = _o

print('\n== 6. as páginas ==')


def src(rel):
    return open(os.path.join(ROOT, *rel.split('/')), encoding='utf-8').read()


for rel in ('apps/templates/pages/new_deals-swap-bullet.html', 'apps/templates/pages/new_deals-product.html',
            'apps/templates/pages/new_deals-ndf-commodities.html',
            'apps/templates/pages/new_deals-opt-commodities.html'):
    check('%s manda o _selected' % rel.split('/')[-1], '_selected' in src(rel), True)
tr = json.load(open(os.path.join(ROOT, 'apps', 'static', 'data', 'translations', 'en.json'), encoding='utf-8'))
check('o rótulo do botão segue curto e o tooltip tem chave própria',
      (tr.get('nd-btn-econaff'), 'nd-btn-econaff-tip' in tr), ('Econ. Affirmation', True))

print(('\nFAIL: %d' % len(fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
