"""Compara o porte Python (otc_boxparse.py) com o JS REAL (otc-fileupload.js).

As funcoes puras do JS sao recortadas do arquivo e executadas no JavaScriptCore;
o resultado e comparado com o do Python para centenas de entradas. parseEmailHtml
+ buildRow sao comparados via HTML sintetico rodando os dois lados.

Rodar depois de qualquer alteracao em otc-fileupload.js OU otc_boxparse.py.
"""
import io, json, os, re, subprocess, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))   # scripts/tests/ -> raiz do repo
JSC = '/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc'
sys.path.insert(0, ROOT)
from apps.pages import otc_boxparse as P

JS = io.open(os.path.join(ROOT, 'apps/static/js/pages/otc-fileupload.js'), encoding='utf-8').read()

fails = []
def check(label, got, exp):
    if got != exp:
        fails.append('%s: py=%r js=%r' % (label, got, exp))
        print('  FAIL %-46s py=%-22r js=%r' % (label, got, exp))

def cut(name, pat):
    m = re.search(pat, JS, re.S)
    assert m, 'nao achei %s no JS' % name
    return m.group(0)

# --- recorta as funcoes puras do JS ---------------------------------------
pieces = [
    cut('MONTH_CODES',      r'var MONTH_CODES\s*=\s*\{.*?\};'),
    cut('MONTH_NAMES_ABBR', r'var MONTH_NAMES_ABBR\s*=\s*\{.*?\};'),
    cut('fmtNum2dp',        r'function fmtNum2dp\(.*?\n    \}'),
    cut('normalizeCcy',     r'function normalizeCcy\(.*?\n    \}'),
    cut('parseDate',        r'function parseDate\(.*?\n    \}'),
    cut('fmtDate',          r'function fmtDate\(.*?\n    \}'),
    cut('fmtDateStr',       r'function fmtDateStr\(.*?\n    \}'),
    cut('extractMonth',     r'function extractMonthFromTradeDate\(.*?\n    \}'),
    cut('extractDirection', r'function extractDirection\(.*?\n    \}'),
    cut('contractParts',    r'function contractParts\(.*?\n    \}'),
    cut('MONTH_ABBR_ORDER',  r'var MONTH_ABBR_ORDER\s*=\s*\[.*?\];'),
    cut('contractMonthYear', r'function contractMonthYear\(.*?\n    \}'),
    cut('dateMonthYear',     r'function dateMonthYear\(.*?\n    \}'),
    cut('monthsAhead',       r'function monthsAhead\(.*?\n    \}'),
    cut('B3_MY_RE',        r'var B3_MY_RE = [^\n]+'),
    cut('splitB3Pattern',  r'function splitB3Pattern\(.*?\n    \}'),
    cut('buildB3Code',     r'function buildB3Code\(.*?\n    \}'),
    cut('b3MapEntry',      r'function b3MapEntry\(.*?\n    \}'),
    cut('calculateB3Id',    r'function calculateB3Id\(.*?\n    \}'),
    cut('isCentsFactor',    r'function isCentsFactor\(.*?\n    \}'),
    cut('parseFator',       r'function parseFator\(.*?\n    \}'),
]
# calculateB3Id le os mapas do escopo do modulo; injetamos os do teste
FIXED = {'MPB_LME': 'LOPBDY', 'MAL_LME': 'LOAHDY', 'NG_NYMEX': 'NG1',
         'FO_0.5%_SING_FOB': 'NACX0005', 'FO_0.5%_ROT_BRG_FOB': 'NAEB0011'}
# Padroes na notacao nova: "MY" = mes/ano, _ = espaco. O FCPO deixou de ser
# SPECIAL no codigo-fonte e virou um padrao do cadastro (§164).
DYN = {'BO_CBOT': 'BO"MY"', 'C_CBOT': 'C_"MY"', 'SB_ICE': 'SB"MY"',
       'W_CBOT': 'W_"MY"', 'KC_ICE': 'KC"MY"', 'WTI_NYMEX': 'WTI"MY"',
       'FCPO_BURSA_MYR': 'KO"MY"BNMK'}
# SPECIAL: os DOIS codigos do BRT_IPE, hoje cadastrados (B3 CODE / B3 CODE FAR).
SPECIAL = {'BRT_IPE': {'near': 'CO"MY"', 'far': 'CO1-2'}}
HOL = {'BO_CBOT': 'CBY_AGS', 'MAL_LME': 'LME', 'BRT_IPE': 'IPE',
       'FCPO_BURSA_MYR': 'BURSA', 'NG_NYMEX': 'NYMEX'}

def jsc_run(body):
    src = ('var MARKET_FIXED_CODES=%s;var MARKET_DYNAMIC_PREFIX=%s;'
           'var MARKET_SPECIAL_CODES=%s;\n'
           % (json.dumps(FIXED), json.dumps(DYN), json.dumps(SPECIAL))) + \
          '\n'.join(pieces) + '\n' + body
    r = subprocess.run([JSC, '-e', src], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[:2000]); sys.exit('jsc falhou')
    return r.stdout

def batch(fn_call, inputs):
    """Roda fn_call(x) no JS para cada input; devolve lista de strings."""
    body = ('var IN=%s;IN.forEach(function(x){var r;try{r=%s}catch(e){r="<err>"}'
            'print(r===null||r===undefined?"<null>":String(r));});'
            % (json.dumps(inputs), fn_call))
    return jsc_run(body).splitlines()

# --- fmtNum2dp -------------------------------------------------------------
print('\n== fmtNum2dp (abs) ==')
NUMS = ['1234.5678', '0.125', '2.675', '1.005', '0.005', '-2.675', '2.5', '1.115',
        '8.345', '0.615', '-1500000', '1,234,567.891', '0', '', 'abc', '12abc',
        '1e3', '0.001', '99999999.999', '-0.004', '.5', '7']
for v, js in zip(NUMS, batch('fmtNum2dp(x,true)', NUMS)):
    check('fmtNum2dp(%r,abs)' % v, str(P._fmt_num_2dp(v, True)), js)
print('== fmtNum2dp (sinal) ==')
for v, js in zip(NUMS, batch('fmtNum2dp(x,false)', NUMS)):
    check('fmtNum2dp(%r)' % v, str(P._fmt_num_2dp(v, False)), js)

# --- normalizeCcy ----------------------------------------------------------
print('== normalizeCcy ==')
CCY = ['BRR', 'brr', ' USB ', 'USD', 'BRL', '', 'eur', 'MXB']
for v, js in zip(CCY, batch('normalizeCcy(x)', CCY)):
    check('normalizeCcy(%r)' % v, P._normalize_ccy(v), js)

# --- fmtDateStr ------------------------------------------------------------
print('== fmtDateStr ==')
DATES = ['21-May-2026', '19-Apr-2025', '1-Jan-26', '2026-12-15', '12/15/2026',
         '05 Jun 2026', '3/7/2026', '', '31-Dec-2026', '9-Sep-2026',
         '15-XXX-2026', '2026-02-30']
for v, js in zip(DATES, batch('fmtDateStr(x)', DATES)):
    check('fmtDateStr(%r)' % v, P._fmt_date_str(v), js)

# --- extractMonthFromTradeDate --------------------------------------------
print('== extractMonthFromTradeDate ==')
for v, js in zip(DATES, batch('extractMonthFromTradeDate(x)', DATES)):
    check('month(%r)' % v, P._extract_month_from_trade_date(v), js)

# --- extractDirection ------------------------------------------------------
print('== extractDirection ==')
TYPES = ['Sell Option (Put)', 'Buy Swap', 'BUY', 'sell', 'Nothing', '',
         'Buy and Sell']
for v, js in zip(TYPES, batch('extractDirection(x)', TYPES)):
    check('direction(%r)' % v, P._extract_direction(v), js)

# --- calculateB3Id ---------------------------------------------------------
print('== calculateB3Id ==')
COMBOS = [('MAL_LME', 'May27'), ('BO_CBOT', 'Dec26'), ('C_CBOT', 'Jul25'),
          ('BRT_IPE', 'Mar27'), ('FCPO_BURSA_MYR', 'Sep26'), ('NG_NYMEX', 'Jan26'),
          ('W_CBOT', 'Nov28'), ('UNKNOWN_MKT', 'Feb26'), ('KC_ICE', 'Aug26'),
          ('', 'May27'), ('MAL_LME', ''), ('SB_ICE', 'bad'),
          ('FO_0.5%_ROT_BRG_FOB', 'Jun26')]
# A data de liquidacao so muda o BRT_IPE asiatico, mas entra em TODOS os combos:
# se algum dia ela vazar para outro market, a divergencia aparece aqui.
SETTLES = ['', '05/01/2027', '02/02/2027', '28/02/2027', '05/12/2026',
           '05/03/2027', '2027-02-02', 'lixo']
for van in (True, False):
    ins = [[m, c, sd] for (m, c) in COMBOS for sd in SETTLES]
    body = ('var IN=%s;IN.forEach(function(x){print(String(calculateB3Id(x[0],x[1],%s,x[2])));});'
            % (json.dumps(ins), 'true' if van else 'false'))
    for (mkt, ctr, sd), js in zip(ins, jsc_run(body).splitlines()):
        check('b3(%r,%r,van=%s,settle=%r)' % (mkt, ctr, van, sd),
              P.calculate_b3_id(mkt, ctr, van, FIXED, DYN, SPECIAL, sd), js)

# O caso que motivou a regra (§212), escrito por extenso para nao depender do
# JS: asiatica de BRT_IPE com o contrato DOIS meses a frente da liquidacao sai
# CO1-2; com UM mes, sai o codigo do mes.
print('== BRT_IPE asiatico x distancia ate a liquidacao ==')
for settle, ctr, exp in (('05/01/2027', 'Mar27', 'CO1-2'),
                         ('02/02/2027', 'Mar27', 'COH7'),
                         ('28/02/2027', 'Mar27', 'COH7'),
                         ('05/12/2026', 'Jan27', 'COF7'),
                         ('05/12/2026', 'Mar27', 'CO1-2'),
                         ('05/03/2027', 'Mar27', 'CO1-2'),
                         ('',           'Mar27', 'CO1-2')):
    check('asian %s %s' % (settle, ctr),
          P.calculate_b3_id('BRT_IPE', ctr, False, FIXED, DYN, SPECIAL, settle), exp)
# Vanilla nao mudou: sempre o codigo do mes, com ou sem data.
for settle in ('05/01/2027', ''):
    check('vanilla %r' % settle,
          P.calculate_b3_id('BRT_IPE', 'Mar27', True, FIXED, DYN, SPECIAL, settle), 'COH7')

# --- isCentsFactor / parseFator -------------------------------------------
print('== isCentsFactor ==')
FACS = ['0.01', '0,01', 0.01, '1', 1, '', None, '0.0100000001', 0.02, 'x']
ins = [f for f in FACS if f is not None]
for v, js in zip(ins, batch('String(isCentsFactor(x))', ins)):
    check('isCents(%r)' % v, str(P._is_cents_factor(v)).lower(), js)
check('isCents(None)', P._is_cents_factor(None), False)

# --- parseEmailHtml + buildRow (ponta a ponta) -----------------------------
print('\n== parseEmailHtml + buildRow (3 linhas) ==')
HEADERS = ['DealName', 'TradeDate', 'Market', 'Contract', 'Instrument', 'Type',
           'TotalNotional', 'Strike', 'StrikeCCY', 'Premium', 'PremiumPerUnit',
           'PremCCY', 'SettlementDate', 'SpotDate', 'FXConvDate',
           'FixingStartDate', 'FixingEndDate', 'Acronym', 'TradingBook',
           'OtherBook', 'SpotFXRate']
R1 = ['D5XO-A1', '21-May-2026', 'BO_CBOT', 'Dec26', 'Option (Put)',
      'Sell Option (Put)', '-1500000.555', '2.675', 'USB', '-12345.675',
      '0.4567', 'BRR', '30-Jun-2026', '25-May-2026', '29-Jun-2026',
      '01-Jun-2026', '30-Jun-2026', 'ACMEBR', 'BOOK-A', 'BOOK-B', '5.4321']
R2 = ['D5XO-A1', '21-May-2026', 'BO_CBOT', 'Dec26', 'Option (Put)',
      'Buy Option (Put)', '1500000.555', '2.675', 'USB', '12345.675',
      '0.4567', 'BRR', '30-Jun-2026', '25-May-2026', '29-Jun-2026',
      '01-Jun-2026', '30-Jun-2026', 'LAWTON', 'BOOK-A', 'BOOK-B', '5.4321']

def mk_html(headers, rows, nested=False, extra_table=True):
    h = ''.join('<th>%s</th>' % x for x in headers)
    body = ''.join('<tr>%s</tr>' % ''.join('<td>%s</td>' % c for c in r) for r in rows)
    inner = ('<table><tr><td>ruido aninhado</td></tr></table>' if nested else '')
    pre = ('<table><tr><td>cabecalho encaminhado</td></tr></table>' if extra_table else '')
    return ('<html><body>%s<table><tr>%s</tr>%s</table>%s</body></html>'
            % (pre, h, body, inner))

HTML = mk_html(HEADERS, [R1, R2])
REF = {'ACMEBR': {'spn': '0012345', 'counterparty': 'ACME BRASIL LTDA',
                  'taxId': '11.111.111/0001-11'}}
SUBJ = {'BOZ6': {'commodity': 'SOYBEAN OIL', 'fatorConversao': 0.01}}

# jsc nao tem DOMParser -> parseEmailHtml roda so no Python; comparamos buildRow
# alimentando o JS com os deals que o Python extraiu, e conferimos a extracao
# separadamente contra o esperado (bloco "identidade das 3 linhas").
def js_build_rows(deals, layout):
    src = ('var MARKET_FIXED_CODES=%s,MARKET_DYNAMIC_PREFIX=%s,MARKET_SPECIAL_CODES=%s;\n'
           % (json.dumps(FIXED), json.dumps(DYN), json.dumps(SPECIAL))
           + 'var REF=%s,SUBJ=%s,DEALS=%s,LAYOUT=%s;\n' %
           (json.dumps(REF), json.dumps(SUBJ), json.dumps(deals), json.dumps(layout))
           + '\n'.join(pieces) + '\n'
           + cut('getField', r'function getField\(.*?\n    \}') + '\n'
           + cut('quotedBadge', r'function quotedBadge\(.*?\n    \}') + '\n'
           + cut('escHtml', r'function _escHtml\(.*?\n') + '\n'
           + cut('escRow', r'function _escRow\(.*?\n') + '\n'
           + cut('generateUUID', r'function generateUUID\(.*?\n    \}') + '\n'
           + 'var MARKET_TO_FX_HOLIDAY=%s;\n' % json.dumps(HOL)
           + cut('buildRow', r'function buildRow\(deal, refMap.*?\n    \}\n')
           + '\nprint(JSON.stringify(DEALS.map(function(d){'
             'return buildRow(d,REF,SUBJ,"SID001","fixed-id",LAYOUT).data;})));')
    r = subprocess.run([JSC, '-e', src], capture_output=True, text=True)
    if r.returncode != 0:
        print('STDOUT:', r.stdout[:2000]); print('STDERR:', r.stderr[:2000])
        sys.exit('jsc buildRow falhou')
    return json.loads(r.stdout)

py_deals = P.parse_email_html(HTML)
print('   linhas extraidas pelo Python: %d (esperado 3)' % len(py_deals))
if len(py_deals) != 3:
    fails.append('parse_email_html devolveu %d linhas' % len(py_deals))

MAPS = {'fixed': FIXED, 'dynamic': DYN, 'holiday': HOL, 'special': SPECIAL}
for layout in ('opt', 'ndf'):
    js_rows = js_build_rows(py_deals, layout)
    for i, d in enumerate(py_deals):
        py = P.build_deal(d, REF, SUBJ, 'SID001', layout, MAPS)
        js = js_rows[i]
        for k in sorted(set(py) | set(js)):
            check('%s[%d].%s' % (layout, i, k), py.get(k), js.get(k))

# --- extracao: identidade das 3 linhas ------------------------------------
print('== identidade das 3 linhas ==')
opt = [P.build_deal(d, REF, SUBJ, 'SID001', 'opt', MAPS) for d in py_deals]
check('linha0 acronym', opt[0]['Acronym'], 'ACMEBR')
check('linha0 client',  opt[0]['Client'], 'ACME BRASIL LTDA')
check('linha0 direcao', opt[0]['Direction'], 'SELL')
check('linha1 acronym', opt[1]['Acronym'], 'LAWTON')
check('linha1 direcao invertida', opt[1]['Direction'], 'SELL')  # era BUY na linha
check('linha2 acronym', opt[2]['Acronym'], 'JPMORGANBM')
check('linha2 client',  opt[2]['Client'], 'BANCO J.P MORGAN S.A')
check('linha2 direcao', opt[2]['Direction'], 'BUY')
check('ndf sem Premium', 'Premium' in P.build_deal(py_deals[0], REF, SUBJ, '', 'ndf', MAPS), False)
check('opt com Premium', 'Premium' in opt[0], True)

# --- robustez do parser HTML ----------------------------------------------
print('== robustez do HTML ==')
check('sem tabela', P.parse_email_html('<p>oi</p>'), [])
check('vazio', P.parse_email_html(''), [])
check('tabela sem DealName', P.parse_email_html('<table><tr><th>X</th></tr><tr><td>1</td></tr></table>'), [])
nested = P.parse_email_html(mk_html(HEADERS, [R1, R2], nested=True))
check('tabela aninhada nao quebra', len(nested), 3)
nbsp = P.parse_email_html(mk_html(['DealName', 'TradeDate'], [['&nbsp;D1&nbsp;', '21-May-2026']], extra_table=False))
check('nbsp virou espaco/trim', nbsp[0]['DealName'] if nbsp else None, 'D1')
tags = P.parse_email_html(mk_html(['DealName', 'TradeDate'], [['<b>D<span>2</span></b>', '21-May-2026']], extra_table=False))
check('tags dentro da celula', tags[0]['DealName'] if tags else None, 'D2')
one = P.parse_email_html(mk_html(HEADERS, [R1], extra_table=False))
check('so 1 linha de dados -> 1 deal', len(one), 1)

print('\n%s' % ('TUDO BATENDO COM O JS' if not fails else 'FALHAS (%d):' % len(fails)))
for f in fails[:40]:
    print('  - %s' % f)
sys.exit(1 if fails else 0)
