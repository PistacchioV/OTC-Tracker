"""Ponta a ponta do scheduler de box scan, com o Outlook stubado.

Cobre: persistencia no arquivo do dia certo, dedup por Deal+Acronym, amend
preservando o B3 ID, e-mail sem deal NAO arquivado, e o roteamento por produto.
Nao toca em Outlook nem em rede.
"""
import io, json, os, shutil, sys, tempfile, types

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))   # scripts/tests/ -> raiz do repo
sys.path.insert(0, ROOT)
os.environ.setdefault('DEBUG', 'False')

# --- stub do otc_boxscan ANTES de importar routes --------------------------
BOX = {'ndf': [], 'opt': []}
ARCHIVED = []
stub = types.ModuleType('apps.pages.otc_boxscan')
def scan_new_deals_box(product):
    return {'ok': True, 'emails': list(BOX.get(product, [])), 'cancelled': []}
def archive_email(entry_id):
    ARCHIVED.append(entry_id)
    return {'ok': True}
stub.scan_new_deals_box = scan_new_deals_box
stub.archive_email = archive_email
sys.modules['apps.pages.otc_boxscan'] = stub

from apps.pages import routes as R                      # noqa: E402

fails = []
def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '  got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)

# --- redireciona o cache para um tmp --------------------------------------
TMP = tempfile.mkdtemp()
R.CACHE_BASE_DIR = os.path.join(TMP, 'opt')
R.NDF_COMM_CACHE_DIR = os.path.join(TMP, 'ndf')
R._BOX_PRODUCTS['opt']['dir'] = lambda: R.CACHE_BASE_DIR
R._BOX_PRODUCTS['ndf']['dir'] = lambda: R.NDF_COMM_CACHE_DIR
R._create_notification = lambda *a, **k: None            # sem DuckDB no teste

HEADERS = ['DealName', 'TradeDate', 'Market', 'Contract', 'Instrument', 'Type',
           'TotalNotional', 'Strike', 'StrikeCCY', 'Premium', 'PremiumPerUnit',
           'PremCCY', 'SettlementDate', 'SpotDate', 'FXConvDate',
           'FixingStartDate', 'FixingEndDate', 'Acronym', 'TradingBook',
           'OtherBook', 'SpotFXRate']

def row(deal='D-1', notional='1500000.00', strike='2.675', acr='ACMEBR', direction='Sell'):
    return [deal, '21-May-2026', 'BO_CBOT', 'Dec26', 'Option (Put)',
            direction + ' Option (Put)', notional, strike, 'USB', '-12345.67',
            '0.4567', 'BRR', '30-Jun-2026', '25-May-2026', '29-Jun-2026',
            '01-Jun-2026', '30-Jun-2026', acr, 'BOOK-A', 'BOOK-B', '5.4321']

def html(rows):
    h = ''.join('<th>%s</th>' % x for x in HEADERS)
    b = ''.join('<tr>%s</tr>' % ''.join('<td>%s</td>' % c for c in r) for r in rows)
    return '<html><body><table><tr>%s</tr>%s</table></body></html>' % (h, b)

def email(eid, rows, subject='Brazil Booking Recap - BO_CBOT Option'):
    return {'entry_id': eid, 'subject': subject, 'html': html(rows)}

def dayfile(product):
    d = R._BOX_PRODUCTS[product]
    p = os.path.join(d['dir'](), '2026', '05', '20260521' + d['suffix'])
    if not os.path.isfile(p):
        return []
    return json.load(io.open(p, encoding='utf-8'))

print('\n== 1. import inicial (opt): 1 e-mail, 2 linhas -> 3 deals ==')
BOX['opt'] = [email('E1', [row(), row(direction='Buy')])]
r = R._box_scan_pull('opt')
check('e-mails lidos', r['emails'], 1)
check('deals gerados', r['deals'], 3)
check('novos', r['new'], 3)
check('arquivado', r['archived'], 1)
check('entry arquivado', ARCHIVED, ['E1'])
rows_ = dayfile('opt')
check('gravou 3 no arquivo do dia', len(rows_), 3)
check('acronyms', sorted(d['Acronym'] for d in rows_), ['ACMEBR', 'JPMORGANBM', 'LAWTON'])
check('status inicial', sorted({d['Status'] for d in rows_}), ['New'])
check('maker sintetico', rows_[0]['Maker'], 'BOX')
check('layout opt tem Premium', 'Premium' in rows_[0], True)
check('notional formatado', rows_[0]['TotalNotional'], '1,500,000.00')

print('\n== 2. mesmo e-mail de novo: idempotente (nada muda) ==')
ARCHIVED[:] = []
r = R._box_scan_pull('opt')
check('nenhum novo', r['new'], 0)
check('nenhum amend', r['amended'], 0)
check('continua com 3 linhas', len(dayfile('opt')), 3)

print('\n== 3. amend: strike mudou, B3 ID preservado ==')
# simula um deal ja registrado na B3
rows_ = dayfile('opt')
p = os.path.join(R.CACHE_BASE_DIR, '2026', '05', '20260521_optcomm.json')
for d in rows_:
    if d['Acronym'] == 'ACMEBR':
        d['B3_ID'] = 'B3-999'
        d['Status'] = 'Success'
        d['Checker'] = 'SID-X'
json.dump(rows_, io.open(p, 'w', encoding='utf-8'))

BOX['opt'] = [email('E2', [row(strike='3.100'), row(direction='Buy', strike='3.100')])]
r = R._box_scan_pull('opt')
check('3 amendados', r['amended'], 3)
check('nenhum novo', r['new'], 0)
rows_ = dayfile('opt')
check('continua com 3 linhas', len(rows_), 3)
acme = [d for d in rows_ if d['Acronym'] == 'ACMEBR'][0]
check('B3 ID preservado', acme['B3_ID'], 'B3-999')
check('status virou Amend', acme['Status'], 'Amend')
check('strike novo', acme['Strike'], '3.100')
check('checker limpo (re-aprovacao)', acme['Checker'], '')
check('AmendChanged registra Strike', 'Strike' in (acme.get('AmendChanged') or []), True)

print('\n== 4. e-mail sem linha de deal NAO e arquivado ==')
ARCHIVED[:] = []
BOX['opt'] = [{'entry_id': 'E3', 'subject': 'Brazil Booking Recap - vazio',
               'html': '<html><body><p>sem tabela</p></body></html>'}]
r = R._box_scan_pull('opt')
check('nenhum deal', r['deals'], 0)
check('nao arquivou', r['archived'], 0)
check('box intocado', ARCHIVED, [])

print('\n== 5. produto ndf grava no diretorio proprio e sem Premium ==')
BOX['ndf'] = [email('N1', [row(deal='N-1')], subject='Brazil Booking Recap - MAL_LME Swap')]
BOX['opt'] = []
r = R._box_scan_pull('ndf')
check('1 deal (so 1 linha no e-mail)', r['deals'], 1)
nrows = dayfile('ndf')
check('gravou no dir do ndf', len(nrows), 1)
check('layout ndf sem Premium', 'Premium' in nrows[0], False)
check('opt nao foi tocado', len(dayfile('opt')), 3)

print('\n== 6. deal em outra trade date vai para outro arquivo ==')
other = row(deal='D-OUT')
other[1] = '03-Jun-2026'
BOX['ndf'] = [email('N2', [other], subject='Brazil Booking Recap - Swap')]
R._box_scan_pull('ndf')
p2 = os.path.join(R.NDF_COMM_CACHE_DIR, '2026', '06', '20260603_ndfcomm.json')
check('arquivo de 03/06 criado', os.path.isfile(p2), True)
check('arquivo de 21/05 intocado', len(dayfile('ndf')), 1)

print('\n== 7. scheduler e rota ==')
threading = __import__('threading')


def viva():
    return any(t.name == 'box-scan-scheduler' and t.daemon
               for t in threading.enumerate())


check('intervalo padrao 30 min', R._BOX_SCAN_POLL_MIN, 30)
# O laco sobe com o APP, nunca com o import: os 67 scripts daqui importam o
# routes, e a thread que nascia no import fazia o processo do TESTE disparar
# e-mail agendado de verdade (e reservar o slot, calando o app real).
check('o import NAO sobe a thread', viva(), False)
check('mas o laco esta registrado',
      '_box_scan_start_scheduler' in [f.__name__ for _, f in R._SCHEDULERS], True)
from apps import create_app                              # noqa: E402
from apps.config import DebugConfig                      # noqa: E402
rules = {str(x.rule) for x in create_app(DebugConfig).url_map.iter_rules()}
check('e o create_app sobe', viva(), True)
check('rota /api/new-deals/box-scan/run registrada',
      '/api/new-deals/box-scan/run' in rules, True)
check('rota /api/new-deals/box-scan continua',
      '/api/new-deals/box-scan' in rules, True)

shutil.rmtree(TMP, ignore_errors=True)
print('\n%s' % ('TUDO OK' if not fails else 'FALHAS: %r' % fails))
sys.exit(1 if fails else 0)
