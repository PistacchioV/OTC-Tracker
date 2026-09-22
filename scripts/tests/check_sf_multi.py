"""Filtro inteligente com VÁRIOS valores (uma lista de Trade IDs).

Prende:
  §1 o servidor (`platform/new_deals._deal_matches`, que responde o
     `/cache/search` das páginas de New Deals): `123, 456; 789` casa com
     QUALQUER um; `1,250,000` continua um número só; o chip `Status ≠ Success`
     (modo `not`) segue valor único;
  §2 o `sf-multi.js` (a mesma regra no navegador: Intrag, DCE, Unwinds e a
     linha de filtro por coluna), executado no `jsc` do macOS;
  §3 as páginas: todas as que têm filtro inteligente ou linha de filtro
     carregam o script, e nenhuma voltou ao `column(...).search(this.value)`
     cru, que tratava a lista como um texto só.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_sf_multi.py
"""
import glob
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

JSC = '/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc'
FAILS = []


def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        FAILS.append(msg)


# ── §1 servidor ──────────────────────────────────────────────────────────
from apps.pages.platform import new_deals as nd  # noqa: E402

deals = [{'Deal': '35123456', 'Status': 'Sent', 'Notional': '1,250,000.00'},
         {'Deal': '35999999', 'Status': 'Success', 'Notional': '500,000.00'},
         {'Deal': 'ABC-77', 'Status': 'Error', 'Notional': '75,000.00'}]


def hits(filters):
    return [d['Deal'] for d in deals if nd._deal_matches(d, filters)]


check(hits([{'field': 'Deal', 'type': 'text', 'value': '35123456'}]) == ['35123456'],
      '§1 um valor: igual a antes')
check(hits([{'field': 'Deal', 'type': 'text', 'value': '35123456, abc-77'}]) == ['35123456', 'ABC-77'],
      '§1 lista com vírgula casa qualquer um (sem caixa)')
check(hits([{'field': 'Deal', 'type': 'text', 'value': '35123456;35999999\nABC-77'}])
      == ['35123456', '35999999', 'ABC-77'], '§1 `;` e quebra de linha também separam')
check(hits([{'field': 'Deal', 'type': 'text', 'value': '35123456, 35999999'},
            {'field': 'Status', 'type': 'text', 'value': 'Success', 'mode': 'not'}]) == ['35123456'],
      '§1 lista + chip Status ≠ Success (E entre os chips)')
check(hits([{'field': 'Notional', 'type': 'number', 'value': '1,250,000'}]) == ['35123456'],
      '§1 número com milhar é UM valor')
check(hits([{'field': 'Notional', 'type': 'number', 'value': '1,250,000; 75,000'}]) == ['35123456', 'ABC-77'],
      '§1 lista de números separa só por `;`')
check(nd._filter_tokens('1,250,000') == ['1,250,000'], '§1 milhar num campo de texto também é UM valor')

# ── §2 navegador ─────────────────────────────────────────────────────────
js = open(os.path.join(ROOT, 'apps/static/js/sf-multi.js'), encoding='utf-8').read()
if not os.path.exists(JSC):
    check(False, '§2 jsc do macOS não encontrado')
else:
    probe = r'''
var window = this, document = { addEventListener: function () {} };
''' + js + r'''
function Col() { this.s = ''; this.args = null; }
Col.prototype.search = function (v, re, smart, ci) {
  if (arguments.length === 0) return this.s;
  this.s = v; this.args = [re, smart, ci]; return this;
};
var M = window.otcSfMulti, out = {};
out.one = M.tokens('35123456');
out.many = M.tokens('35123456, ABC-77;x\n y');
out.thousand = M.tokens('1,250,000.50');
out.numList = M.tokens('1,000; 2,000', true);
out.multi = [M.isMulti('a, b'), M.isMulti('a'), M.isMulti('1,250,000')];
var c = new Col();
out.changed1 = M.columnSearch(c, 'a.b, c');
out.regex = c.s; out.args = c.args;
out.changed2 = M.columnSearch(c, 'a.b, c');
out.changed3 = M.columnSearch(c, 'plain');
out.plain = [c.s, c.args];
print(JSON.stringify(out));
'''
    tmp = os.path.join(os.environ.get('TMPDIR', '/tmp'), 'sf_multi_probe.js')
    with open(tmp, 'w', encoding='utf-8') as fh:
        fh.write(probe)
    r = subprocess.run([JSC, tmp], capture_output=True, text=True)
    try:
        o = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        o = {}
        print(r.stdout, r.stderr)
    check(o.get('one') == ['35123456'], '§2 um valor')
    check(o.get('many') == ['35123456', 'ABC-77', 'x', 'y'], '§2 `,` `;` e quebra de linha separam')
    check(o.get('thousand') == ['1,250,000.50'], '§2 milhar é UM valor')
    check(o.get('numList') == ['1,000', '2,000'], '§2 lista numérica separa só por `;`')
    check(o.get('multi') == [True, False, False], '§2 isMulti')
    check(o.get('changed1') is True and o.get('regex') == 'a\\.b|c' and o.get('args') == [True, False, True],
          '§2 lista vira regex OR escapado, sem smart, sem caixa')
    check(o.get('changed2') is False, '§2 mesma busca não redesenha')
    check(o.get('changed3') is True and o.get('plain', [None])[0] == 'plain',
          '§2 valor único volta à busca padrão do DataTables')

# ── §3 páginas ───────────────────────────────────────────────────────────
pages = sorted(glob.glob(os.path.join(ROOT, 'apps/templates/pages/new_deals-*.html'))
               + glob.glob(os.path.join(ROOT, 'apps/templates/pages/intrag-*.html'))
               + glob.glob(os.path.join(ROOT, 'apps/templates/pages/unwinds-*.html')))
raw = re.compile(r'column\([^)]*\)\.search\((this\.value|f\.value)\)')
n = 0
for p in pages:
    s = open(p, encoding='utf-8').read()
    if 'function sfCandidates' not in s and 'column-search-input-bar' not in s:
        continue
    n += 1
    name = os.path.basename(p)
    check('js/sf-multi.js' in s, '§3 %s carrega o sf-multi.js' % name)
    check(not raw.search(s), '§3 %s sem busca crua de coluna' % name)
    if 'function sfCandidates' in s:
        check('otcSfMulti.isMulti(val)' in s, '§3 %s oferece colunas de texto para a lista' % name)
check(n >= 17, '§3 páginas cobertas: %d' % n)

print('\nTUDO OK' if not FAILS else '\n%d FALHA(S)' % len(FAILS))
sys.exit(1 if FAILS else 0)
