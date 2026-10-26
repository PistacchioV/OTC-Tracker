"""A cópia que falhou é DITA na tela (§696).

Gravar na origem (New Deals, swaps, recompras) dispara cópias para o Pending
Confirmation, a esteira das confirmações e a Intrag. Cada uma é melhor esforço
— a origem já gravou —, e por isso engolia a exceção: a tela dizia "sent to
Intrag", a cópia não existia e ninguém tentava de novo.

O que se prova:
  1. `mirrors.falhou` registra no request (sem repetir) e loga; fora de request
     só loga;
  2. o `after_request` põe o registro no `X-OTC-Mirror-Failed` das rotas
     `/api/*` (e só nelas);
  3. `_pc_save_from_deal`, `_mc_save_from_deal` e o espelho da Intrag Option
     devolvem o VEREDITO e registram a falha;
  4. os quatro espelhos da Intrag do New Deals (PATCH e Mapping, NDF Comm e
     moeda) chamam o registro;
  5. o `session-guard.js` mostra o aviso traduzido DEPOIS do Swal da página;
  6. a frase "and sent to Intrag" não é mais afirmada sempre.
"""
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.check-share'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

fails = []


def check(label, cond, extra=''):
    print(('  ok  ' if cond else ' FAIL ') + label + ('' if cond else '   ' + repr(extra)))
    if not cond:
        fails.append(label)


from apps import create_app                                      # noqa: E402
from apps.config import DebugConfig                              # noqa: E402

app = create_app(DebugConfig)
from apps.pages import routes as R                               # noqa: E402
from apps.pages.platform import mirrors                          # noqa: E402
from apps.pages.platform import pending_confirmation as PCM      # noqa: E402
from apps.pages.platform import manual_confirmation as MCM       # noqa: E402

print('== 1. o registro ==')
check('fora de request: só loga e devolve False', mirrors.falhou('pc', 'X-1') is False)
with app.test_request_context('/api/qualquer'):
    mirrors.falhou('intrag', 'D-1', RuntimeError('ocupado'))
    mirrors.falhou('intrag', 'D-1', RuntimeError('de novo'))
    mirrors.falhou('pc', 'D-2')
    check('registra sem repetir', mirrors.registradas() == [
        {'target': 'intrag', 'ref': 'D-1'}, {'target': 'pc', 'ref': 'D-2'}], mirrors.registradas())
    v = mirrors.cabecalho()
    check('o cabeçalho é JSON ASCII', json.loads(v) == mirrors.registradas() and v.isascii(), v)

print('\n== 2. o cabeçalho só nas rotas /api/* ==')
from flask import Response                                       # noqa: E402
with app.test_request_context('/api/x'):
    mirrors.falhou('mc', 'K-1')
    r = R.add_mirror_failed_header(Response('{}'))
    check('/api/* leva o X-OTC-Mirror-Failed', json.loads(r.headers.get('X-OTC-Mirror-Failed', '[]'))
          == [{'target': 'mc', 'ref': 'K-1'}], dict(r.headers))
with app.test_request_context('/pagina'):
    mirrors.falhou('mc', 'K-1')
    r = R.add_mirror_failed_header(Response('<html>'))
    check('página HTML não leva', 'X-OTC-Mirror-Failed' not in r.headers)
with app.test_request_context('/api/y'):
    r = R.add_mirror_failed_header(Response('{}'))
    check('sem falha, sem cabeçalho', 'X-OTC-Mirror-Failed' not in r.headers)

print('\n== 3. os espelhos devolvem o veredito ==')
deal = {'Deal': 'D-9', 'Client': 'ACME SA', 'SPN': '123', 'TradeDate': '2026-10-20',
        'SettlementDate': '2026-11-20', 'Status': 'Success'}
_orig_find = PCM._pc_find_row


def _ocupado(_tn):
    raise IOError('banco ocupado')


PCM._pc_find_row = _ocupado
_orig_row = PCM._pc_row_from_deal
PCM._pc_row_from_deal = lambda d, pt, ps, tn, src: {'Trade Number': tn or d['Deal']}
try:
    with app.test_request_context('/api/z'):
        res = PCM._pc_save_from_deal(deal, 'NDF COMM')
        check('_pc_save_from_deal: banco ocupado → False e registrado',
              res is False and mirrors.registradas() == [{'target': 'pc', 'ref': 'D-9'}],
              (res, mirrors.registradas()))
    PCM._pc_row_from_deal = lambda *a: None
    with app.test_request_context('/api/z'):
        check('perna interna → None, sem registro',
              PCM._pc_save_from_deal(deal, 'NDF COMM') is None and not mirrors.registradas())
finally:
    PCM._pc_find_row, PCM._pc_row_from_deal = _orig_find, _orig_row

from apps.pages import manual_conf as MC                         # noqa: E402
_orig_mcf = MC.find_row
MC.find_row = _ocupado
try:
    with app.test_request_context('/api/z'):
        res = MCM._mc_save_from_deal(deal, 'NDF COMM', trade_number='D-9')
        check('_mc_save_from_deal: leitura falha → False e registrado',
              res is False and mirrors.registradas() == [{'target': 'mc', 'ref': 'D-9'}],
              (res, mirrors.registradas()))
        check('source sem esteira → None', MCM._mc_save_from_deal(deal, 'NDF') is None)
finally:
    MC.find_row = _orig_mcf

from apps.pages.features.intrag import commands as IC            # noqa: E402
_orig_opt = IC._save_intrag_opt_entry


def _quebra(*a, **k):
    raise IOError('banco ocupado')


IC._save_intrag_opt_entry = _quebra
try:
    with app.test_request_context('/api/z'):
        r1 = IC._maybe_save_intrag_opt({'Deal': 'OPT-1', 'Client': 'BANCO J.P. MORGAN S.A.'})
        r2 = IC._maybe_save_intrag_opt({'Deal': 'OPT-2', 'Client': 'ACME'})
        check('Intrag Option: falha → False registrado; cliente externo → None',
              r1 is False and r2 is None
              and mirrors.registradas() == [{'target': 'intrag', 'ref': 'OPT-1'}],
              (r1, r2, mirrors.registradas()))
finally:
    IC._save_intrag_opt_entry = _orig_opt

print('\n== 4. os espelhos da Intrag do New Deals registram a falha ==')
src = open(os.path.join(ROOT, 'apps', 'pages', 'features', 'new_deals', 'entrypoint.py'),
           encoding='utf-8').read()
check('os quatro espelhos da Intrag do New Deals registram a falha',
      src.count("_mirrors.falhou('intrag'") == 4, src.count("_mirrors.falhou('intrag'"))

print('\n== 5. o session-guard.js mostra o aviso depois do Swal da página ==')
node = shutil.which('node')
if not node:
    check('node disponível', False, 'sem node')
else:
    js = r'''
var fired = [], visible = true, timers = [];
global.localStorage = { getItem: function () { return 'br'; } };
global.window = global;
window.location = { href: 'http://h/x', origin: 'http://h' };
global.setTimeout = function (fn, ms) { timers.push(fn); };
global.Swal = { isVisible: function () { return visible; },
                fire: function (o) { fired.push(o); } };
var hdr = '[{"target":"intrag","ref":"OPT-1"},{"target":"pc","ref":"D-9"}]';
window.fetch = function () { return Promise.resolve({ status: 200,
    headers: { get: function (k) { return k === 'X-OTC-Mirror-Failed' ? hdr : null; } } }); };
require(process.argv[1]);
window.fetch('/api/new-deals/x').then(function () {
    timers.shift()();                 // os 400 ms
    var antes = fired.length;         // o Swal da página está aberto: espera
    visible = false;
    while (timers.length) timers.shift()();
    console.log(JSON.stringify({ antes: antes, fired: fired }));
});
'''
    out = subprocess.run([node, '-e', js, os.path.join(ROOT, 'apps', 'static', 'js', 'session-guard.js')],
                         capture_output=True, text=True, timeout=30)
    try:
        res = json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:                                            # noqa: BLE001
        res = {}
    check('espera o Swal da página fechar', res.get('antes') == 0, (out.stdout, out.stderr))
    f = (res.get('fired') or [{}])[0]
    check('e avisa em português, com os alvos e as operações',
          f.get('icon') == 'warning' and 'Intrag' in f.get('text', '')
          and 'Pending Confirmation' in f.get('text', '') and 'OPT-1, D-9' in f.get('text', '')
          and f.get('title', '').startswith('Gravado'), f)

print('\n== 6. a tela não afirma mais "sent to Intrag" ==')
import glob                                                      # noqa: E402
com = [p for p in glob.glob(os.path.join(ROOT, 'apps', 'templates', 'pages', 'new_deals-*.html'))
       if 'and sent to Intrag' in open(p, encoding='utf-8').read()]
check('nenhuma página de New Deals', com == [], com)
for lg in ('en', 'br', 'es'):
    tr = json.load(open(os.path.join(ROOT, 'apps', 'static', 'data', 'translations', lg + '.json'),
                        encoding='utf-8'))
    check('tradução %s sem a afirmação' % lg, 'Intrag' not in tr.get('swal-b3-confirmed-text', ''))

print(('\nFAIL: %d' % len(fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
