# -*- coding: utf-8 -*-
"""Edit, Confirm e Delete da tabela do WHT (§702).

A linha da tabela é montada na LEITURA e a coleta seguinte substitui a fatia
do dia: a correção é guardada à parte, por linha de ORIGEM, e aplicada antes do
batimento. O que se prova:
  1. o Edit grava a correção e a linha volta `Pending` com o valor novo — e
     ela SOBREVIVE a uma nova coleta do mesmo dia;
  2. o 4-olhos: quem editou não confirma (403 `approve_own`); outro usuário
     confirma (`Approved`); sem nada pendente é `approve_none`;
  3. a validação pelo TIPO da coluna: número, data do mês do decêndio, opção
     (a LE é JPM ou MGT) — e coluna do lado que a linha não tem;
  4. na linha só do HUB o Internal ID é o Docto dele;
  5. o lote: a mesma correção em várias linhas;
  6. o HUB File recusa linha com edição pendente;
  7. o Delete tira a linha e uma nova importação não a traz de volta;
  8. a página: a coluna Actions, o modal no padrão, as colunas editáveis do
     servidor, o lote e o rótulo `WHT` nos três mapas do sino.

Roda em tmp (DATA_DIR/DATABASE_DIR próprios).
"""
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
RAIZ = tempfile.mkdtemp(prefix='otc-wht-edit-')
os.environ['OTC_DATA_DIR'] = RAIZ
os.environ['OTC_DATABASE_DIR'] = os.path.join(RAIZ, 'db')
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

from apps.config import Config as _Cfg                           # noqa: E402
_Cfg.FOUR_EYES = True        # prova a trava da PROD (§553)

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def src(*rel):
    return open(os.path.join(ROOT, *rel), encoding='utf-8').read()


from apps import create_app                                      # noqa: E402
from apps.config import DebugConfig                              # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True
from apps.pages import routes as R                               # noqa: E402
from apps.pages.features.wht import commands as C, domain as D, queries as Q   # noqa: E402
from apps.pages.features.wht.infra import store                  # noqa: E402

R._br_now = lambda: datetime(2026, 10, 22, 10, 0)
R._pcx_is_bizday = lambda d: d.weekday() < 5
R._create_notification = lambda *a, **k: None

OTC = {'day': '2026-10-14', 'source': 'ndf', 'seq': 0, 'internal_id': '1234567', 'b3_id': '26J0001',
       'product': 'NDF', 'lob': 'CEM', 'event': 'MATURITY', 'gross': 100000.0, 'devido': 5.0,
       'taxable': True, 'counterparty': 'CLIENTE D LTDA', 'taxid': '04.885.503/0001-42', 'le': 'JPM',
       'ir_unknown': False, 'id': '2026-10-14|ndf|JPM|1234567|1'}
HUB = {'empresa': '00001', 'docto': 'XYZ-9', 'code': '5273', 'tributo': 'IRRF', 'date': '2026-10-15',
       'gross': 2000.0, 'ir': 0.1, 'name': 'OUTRO SA', 'cnpj': '11222333000181', 'file': 'hub.xls'}
OTC2 = dict(OTC, seq=1, internal_id='7654321', id='2026-10-14|ndf|JPM|7654321|1', gross=50.0)


def semeia():
    def fn(doc):
        doc['otc'] = {'2026-10-14': {'ndf': {'rows': [dict(OTC), dict(OTC2)], 'at': '', 'by': ''}}}
        doc['hub'] = [dict(HUB)]
    store.mutate('202610', fn)


semeia()


def cliente(sid):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(authenticated=True, user_sid=sid, user_name=sid, user_role='BO', session_ip='127.0.0.1',
                 session_expires_at=(datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat())
    return c


a, b = cliente('A000001'), cliente('B000002')


def dados():
    return a.get('/api/wht/data?date=2026-10-20').get_json()


def linha(j, chave):
    return next((r for r in j['rows'] if r['key'] == chave), None)


j = dados()
o = linha(j, OTC['id'])
hk = next(r for r in j['rows'] if r['status'] == D.ST_ONLY_HUB)
check('as linhas trazem as chaves das origens', (o['otc_key'], o['hub_key'] == '', hk['otc_key'],
                                                 hk['hub_key'].startswith('HUB|')),
      (OTC['id'], True, '', True))

print('== 1. Edit ==')
r = a.post('/api/wht/edit', json={'date': '2026-10-20', 'items': [
    {'otc_key': o['otc_key'], 'hub_key': '', 'changes': {'OTC_GV': '120.000,50', 'OTC_cntpy': 'CLIENTE NOVO'}}]})
j = r.get_json()
x = linha(j, OTC['id'])
check('grava e devolve a página', (r.status_code, j['count']), (200, 1))
check('   o valor novo, Pending, quem editou e as colunas',
      (x['OTC_GV'], x['OTC_cntpy'], x['review'], x['review_by'], x['edited']),
      (120000.5, 'CLIENTE NOVO', 'Pending', 'A000001', ['OTC_GV', 'OTC_cntpy']))
doc = store.load('202610')
check('   o orig guardado e a linha coletada intacta',
      (doc['edits'][OTC['id']]['orig'], doc['otc']['2026-10-14']['ndf']['rows'][0]['gross']),
      ({'gross': 100000.0, 'counterparty': 'CLIENTE D LTDA'}, 100000.0))
C._put(datetime(2026, 10, 14).date(), 'ndf', [dict(OTC, gross=99.0), dict(OTC2)])
check('a coleta seguinte do dia NÃO desfaz a correção', linha(dados(), OTC['id'])['OTC_GV'], 120000.5)

print('\n== 2. Confirm (4-olhos) ==')
item = [{'otc_key': OTC['id'], 'hub_key': ''}]
r = a.post('/api/wht/approve', json={'date': '2026-10-20', 'items': item})
check('quem editou não confirma: 403', (r.status_code, r.get_json().get('error_code')), (403, 'approve_own'))
r = b.post('/api/wht/approve', json={'date': '2026-10-20', 'items': item})
check('outro usuário confirma', (r.status_code, linha(r.get_json(), OTC['id'])['review']), (200, 'Approved'))
r = b.post('/api/wht/approve', json={'date': '2026-10-20', 'items': item})
check('sem nada pendente: approve_none', r.get_json().get('error_code'), 'approve_none')

print('\n== 3. a validação pelo tipo ==')
for col, val, cod in (('OTC_GV', 'abc', 'edit_bad_number'), ('OTC_ET', '05/11/2026', 'edit_other_month'),
                      ('OTC_ET', 'ontem', 'edit_bad_date'), ('OTC_LE', 'LAWTON', 'edit_bad_option'),
                      ('Event', 'QUALQUER', 'edit_bad_option'),
                      ('HUB_GV', '10', 'edit_no_side'), ('Status', 'x', 'edit_bad_column')):
    r = a.post('/api/wht/edit', json={'date': '2026-10-20', 'items': [
        {'otc_key': OTC['id'], 'hub_key': '', 'changes': {col: val}}]})
    check('%s = %r → %s' % (col, val, cod), (r.status_code, r.get_json().get('error_code')), (400, cod))
r = a.post('/api/wht/edit', json={'date': '2026-10-20', 'items': [
    {'otc_key': OTC['id'], 'hub_key': '', 'changes': {'OTC_LE': 'mgt', 'OTC_ET': '16/10/2026',
                                                       'OTC_TD': '03/02/2025'}}]})
x = linha(r.get_json(), OTC['id'])
check('a LE MGT, a data do evento do mês e o Trade Date de qualquer dia (e a linha volta a Pending)',
      (x['OTC_LE'], x['OTC_ET'], x['OTC_TD'], x['review']), ('MGT', '16/10/2026', '03/02/2025', 'Pending'))
r = a.post('/api/wht/edit', json={'date': '2026-10-20', 'items': [
    {'otc_key': 'NAO|EXISTE', 'hub_key': '', 'changes': {'OTC_GV': '1'}}]})
check('linha que não existe mais: 409 edit_row_gone', (r.status_code, r.get_json().get('error_code')),
      (409, 'edit_row_gone'))

print('\n== 4. a linha só do HUB ==')
r = a.post('/api/wht/edit', json={'date': '2026-10-20', 'items': [
    {'otc_key': '', 'hub_key': hk['hub_key'], 'changes': {'Internal ID': 'NOVO-1', 'HUB_GV': '2500'}}]})
x = linha(r.get_json(), hk['key'])
check('o Internal ID é o Docto do HUB', (x['Internal ID'], x['HUB_GV'], x['review'], sorted(x['edited'])),
      ('NOVO-1', 2500.0, 'Pending', ['HUB_GV', 'Internal ID']))

print('\n== 5. o lote ==')
r = a.post('/api/wht/edit', json={'date': '2026-10-20', 'items': [
    {'otc_key': OTC['id'], 'hub_key': '', 'changes': {'Event': 'unwind'}},
    {'otc_key': OTC2['id'], 'hub_key': '', 'changes': {'Event': 'unwind'}}]})
j = r.get_json()
check('a mesma correção nas duas linhas', ([linha(j, k)['Event'] for k in (OTC['id'], OTC2['id'])], j['count']),
      (['UNWIND', 'UNWIND'], 2))

print('\n== 6. o HUB File ==')
r = a.post('/api/wht/hub-file', json={'date': '2026-10-20', 'keys': [OTC['id']]})
check('recusa a linha com edição pendente', (r.status_code, r.get_json().get('error_code')),
      (400, 'hub_file_pending'))

print('\n== 7. Delete ==')
r = a.post('/api/wht/delete', json={'date': '2026-10-20', 'items': [{'otc_key': '', 'hub_key': hk['hub_key']},
                                                                      {'otc_key': OTC2['id'], 'hub_key': ''}]})
j = r.get_json()
check('as duas linhas saem', (r.status_code, linha(j, hk['key']), linha(j, OTC2['id'])), (200, None, None))
semeia()
check('e a nova importação não as traz de volta', (linha(dados(), hk['key']), linha(dados(), OTC2['id'])),
      (None, None))
check('   a outra continua', linha(dados(), OTC['id']) is not None, True)

print('\n== 8. Add Row ==')
r = a.post('/api/wht/derive', json={'fields': {'Product': 'NDF', 'LOB': 'CEM', 'Event': 'MATURITY',
                                                'OTC_GV': '200000', 'OTC_cntpy': 'CLIENTE X', 'OTC_LE': 'JPM',
                                                'OTC_ET': '15/10/2026'}})
j = r.get_json()
check('derive do NDF: 0,005% do valor e o código do cadastro', (j['success'], j['devido'], bool(j['code'])),
      (True, 10.0, True))
r = a.post('/api/wht/derive', json={'fields': {'Product': 'SWAP', 'LOB': 'CEM', 'Event': 'MATURITY',
                                                'OTC_GV': '1000', 'OTC_cntpy': 'CLIENTE X', 'OTC_ET': '15/10/2026'}})
check('swap sem Trade Date: add_swap_trade_date', r.get_json().get('error_code'), 'add_swap_trade_date')
R._ops_swap_ir_rate = lambda cpty, prazo, recebe: 0.225 if prazo <= 180 else 0.15
r = a.post('/api/wht/derive', json={'fields': {'Product': 'SWAP', 'LOB': 'CEM', 'Event': 'MATURITY',
                                                'OTC_GV': '1000', 'OTC_cntpy': 'CLIENTE X', 'OTC_ET': '15/10/2026',
                                                'OTC_TD': '01/01/2025'}})
check('swap com Trade Date: a regressiva pelo prazo (> 180 dias → 15%)', r.get_json().get('devido'), 150.0)
r = a.post('/api/wht/add', json={'date': '2026-10-20', 'items': [{'fields': {
    'Internal ID': 'MAN-1', 'Product': 'SWAP', 'LOB': 'CEM', 'Event': 'maturity', 'OTC_LE': 'JPM',
    'OTC_ET': '15/10/2026', 'OTC_TD': '01/06/2026', 'OTC_GV': '1000', 'OTC_cntpy': 'CLIENTE X'}}]})
j = r.get_json()
x = next((z for z in j['rows'] if z['Internal ID'] == 'MAN-1'), None)
check('a linha manual entra Pending, com o IR calculado e o Trade Date',
      (r.status_code, x and x['review'], x and x['Devido'], x and x['OTC_TD'], x and x['Event']),
      (200, 'Pending', 225.0, '01/06/2026', 'MATURITY'))
r = a.post('/api/wht/add', json={'date': '2026-10-20', 'items': [{'fields': {'Product': 'NDF'}}]})
check('campo obrigatório faltando: add_missing', r.get_json().get('error_code'), 'add_missing')
r = a.post('/api/wht/delete', json={'date': '2026-10-20', 'items': [{'otc_key': x['otc_key'], 'hub_key': ''}]})
check('a linha manual também se apaga', next((z for z in r.get_json()['rows'] if z['Internal ID'] == 'MAN-1'), None),
      None)

print('\n== 9. o evento, o Trade Date e o IR ==')
check('a recompra é UNWIND (também juntada a outro tipo, ou só pela marca)',
      (D.event_of('UNWIND · CASHFLOW'), D.event_of('', True), D.event_of('maturity')),
      ('UNWIND', 'UNWIND', 'MATURITY'))
with app.test_request_context('/'):
    ln = Q.ndf_rows(datetime(2026, 10, 14).date(), [{'settlement': -100.0, 'counterparty': 'C', 'athena': 'A1',
                                                     'b3': 'B1', 'trade_date': '02/03/2026', 'unwind': True,
                                                     'settle_type': 'UNWIND'}])
check('o NDF traz o Trade Date da fonte e o evento da recompra', (ln[0]['trade_date'], ln[0]['event']),
      ('2026-03-02', 'UNWIND'))
o1 = {'date': datetime(2026, 10, 14).date(), 'gross': 100.0, 'ir': 0.30, 'code': 'X', 'tributo': 'Y', 'le': 'JPM',
      'counterparty': 'A', 'taxid': ''}
h1 = dict(o1, ir=0.29, name='A', cnpj='')
check('Check_IR com tolerância de 1 centavo (0,30 × 0,29 bate; 0,30 × 0,28 não)',
      (D._checks(o1, h1)['IR'], D._checks(o1, dict(h1, ir=0.28))['IR']), (True, False))

print('\n== 10. a página e os mapas ==')
html = a.get('/regulatory/wht').data.decode('utf-8')
check('a coluna Actions, o modal liquid-glass e o lote',
      ('data-lang="wht-actions"' in html, bool(re.search(r'id="whtEditModal"[\s\S]{0,200}liquid-glass', html)),
       'id="wht-mass-col"' in html, '"OTC_LE": ["otc", "le", "select"]' in html,
       '"OTC_LE": ["JPM", "MGT"]' in html), (True, True, True, True, True))
check('as colunas novas, o Add Row e o status em CAIXA ALTA',
      ("'OTC_ET'" in src('apps', 'templates', 'pages', 'wht.html') and "'HUB_ET'" in src('apps', 'templates', 'pages', 'wht.html'),
       'id="wht-add"' in html, 'data-case="upper"' in src('apps', 'templates', 'pages', 'wht.html'),
       "getAttribute('data-case') === 'upper'" in src('apps', 'static', 'js', 'otc.js')), (True, True, True, True))


check('o rótulo WHT nos três mapas do sino',
      ("'WHT': '/regulatory/wht'" in src('apps', 'pages', 'platform', 'notifications.py'),
       "'WHT': '/regulatory/wht'" in src('apps', 'static', 'js', 'sw-push.js'),
       bool(re.search(r"'WHT':\s+'/regulatory/wht'", src('apps', 'templates', 'partials', 'topbar.html')))),
      (True, True, True))

print(('\nFAIL: %d' % len(fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
