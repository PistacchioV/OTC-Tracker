# -*- coding: utf-8 -*-
"""RED Clients — Rapid Exposure (§730).

  1. a REGRA (pura): o ECI casa por dígitos sem zero à esquerda (número do
     xls inclusive); a coluna K da aba; ACTIVE → RED, RED fica, PENDING e
     INACTIVE ficam (com a marca), quem sai da lista perde a marca e o RED
     volta a ACTIVE;
  2. a PLANILHA: a aba é achada pelo nome (sem caixa/espaço); aba ausente,
     aba sem ECI e arquivo que não é Excel RECUSAM sem gravar nada;
  3. a RODADA: aplica ao Reference Data num ciclo só, grava, devolve o resumo
     e o status da última rodada; a tarefa diária `red-clients` está no
     catálogo do Intraday Monitor;
  4. a APROVAÇÃO (`/api/b3/update`): o cliente marcado volta como RED, não
     como ACTIVE; o desmarcado como ACTIVE;
  5. os AVISOS de liquidação: `anota_avisos` põe o `X-Red-Clients` na
     resposta só com o cliente RED, e a comparação de nome do servidor e a do
     `red-clients.js` são a MESMA (executada no node);
  6. a TELA: o card no Control Panel (registro, endpoints, JS), a pílula na
     tela de Reference Data e o script nas quinze telas de liquidação.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_red_clients.py
"""
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

import run                                                 # noqa: E402
from apps.pages import routes as R                         # noqa: E402
from apps.pages.features.red_clients import domain as D, commands as C   # noqa: E402
from apps.pages.features.red_clients.infra import persistence as P       # noqa: E402
from apps.pages.platform import red_clients as PR          # noqa: E402

app = run.app
fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


print('== 1. a regra ==')
check('ECI: zeros à esquerda e número do xls', (D.eci_key('000220349472'), D.eci_key(220349472.0), D.eci_key('220349472.0')),
      ('220349472', '220349472', '220349472'))
check('ECI vazio, texto e zero não casam', (D.eci_key(''), D.eci_key('ABC12'), D.eci_key('0'), D.eci_key(None)), ('', '', '', ''))
linhas = [['h'] * 11, [None] * 10 + ['111'], [None] * 10 + [222.0], [None] * 5, [None] * 10 + ['']]
check('coluna K da aba (cabeçalho e linha curta caem)', D.ecis_da_aba(linhas), {'111', '222'})
check('a aba pelo nome, sem caixa nem espaço', (D.same_sheet(' jpm entities - open settlements '), D.same_sheet('Outra')), (True, False))


def base():
    return [
        {'COUNTERPARTY': 'ALPHA SA', 'ECI': '111', 'STATUS': 'ACTIVE'},
        {'COUNTERPARTY': 'BETA LTDA', 'ECI': '0222', 'STATUS': 'PENDING'},
        {'COUNTERPARTY': 'GAMA SA', 'ECI': '333', 'STATUS': 'RED', 'RED': 'Y'},
        {'COUNTERPARTY': 'DELTA SA', 'ECI': '444', 'STATUS': 'INACTIVE'},
        {'COUNTERPARTY': 'EPS SA', 'ECI': '', 'STATUS': 'ACTIVE'},
    ]


regs = base()
res = D.aplicar(regs, {'111', '222', '444', '999'})
por = {r['COUNTERPARTY']: r for r in regs}
check('ACTIVE na lista → RED, com a marca', (por['ALPHA SA']['STATUS'], por['ALPHA SA'].get('RED')), ('RED', 'Y'))
check('PENDING na lista fica PENDING, com a marca', (por['BETA LTDA']['STATUS'], por['BETA LTDA'].get('RED')), ('PENDING', 'Y'))
check('INACTIVE na lista fica INACTIVE, com a marca', (por['DELTA SA']['STATUS'], por['DELTA SA'].get('RED')), ('INACTIVE', 'Y'))
check('RED fora da lista → ACTIVE, sem a marca', (por['GAMA SA']['STATUS'], 'RED' in por['GAMA SA']), ('ACTIVE', False))
check('sem ECI não é tocado', por['EPS SA'], {'COUNTERPARTY': 'EPS SA', 'ECI': '', 'STATUS': 'ACTIVE'})
check('o resumo', (res['changed'], res['red'], sorted(res['entered']), res['left'], res['eci_unmatched']),
      (True, ['ALPHA SA'], ['ALPHA SA', 'BETA LTDA', 'DELTA SA'], ['GAMA SA'], 1))
res2 = D.aplicar(regs, {'111', '222', '444', '999'})
check('a mesma lista de novo não muda nada', (res2['changed'], res2['entered'], res2['left']), (False, [], []))

print('\n== 2. a planilha ==')
import openpyxl                                            # noqa: E402


def xlsx(abas):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nome, rows in abas:
        ws = wb.create_sheet(nome)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


plan = xlsx([('Resumo', [['x']]),
             ('JPM Entities-Open Settlements', [['A'] * 11, [None] * 10 + [111], [None] * 10 + ['0222']])])
check('lê a aba certa (não a primeira)', D.ecis_da_aba(P.linhas_da_aba(plan)), {'111', '222'})
for nome, raw, code in (('aba ausente', xlsx([('Outra', [['x']])]), 'red_sheet_missing'),
                        ('não é Excel', b'a;b;c\n1;2;3', 'red_not_excel')):
    try:
        P.linhas_da_aba(raw)
        check(nome + ' recusa', 'nada', code)
    except P.PlanilhaInvalida as exc:
        check(nome + ' recusa com o código', exc.code, code)

print('\n== 3. a rodada ==')
MEM = {'regs': base(), 'saves': 0}
_l0, _s0, _n0, _w0 = R._b3_load, R._b3_save, R._create_notification, P.write_status
R._b3_load = lambda table: (MEM['regs'], '/x/RefData.json')


def _save(path, recs):
    MEM['regs'] = recs
    MEM['saves'] += 1


R._b3_save = _save
R._create_notification = lambda *a, **k: None
STATUS = {}
P.write_status = lambda doc: STATUS.update(doc)
try:
    with app.test_request_context():
        r = C.run('rapid.xlsx', plan, 'A111111', 'Ana')
    check('gravou uma vez, com ALPHA e BETA marcados', (MEM['saves'], sorted(x['COUNTERPARTY'] for x in MEM['regs'] if x.get('RED'))),
          (1, ['ALPHA SA', 'BETA LTDA']))
    check('   GAMA saiu da lista e voltou a ACTIVE', [x['STATUS'] for x in MEM['regs'] if x['COUNTERPARTY'] == 'GAMA SA'], ['ACTIVE'])
    check('   o status da rodada tem quem e quando', (STATUS.get('file'), STATUS.get('by'), bool(STATUS.get('at'))),
          ('rapid.xlsx', 'Ana', True))
    MEM['saves'] = 0
    try:
        with app.test_request_context():
            C.run('vazia.xlsx', xlsx([('JPM Entities-Open Settlements', [['A'] * 11])]), 'A111111', 'Ana')
        check('aba sem ECI recusa', 'gravou', 'recusa')
    except P.PlanilhaInvalida as exc:
        check('aba sem ECI recusa SEM gravar (não tira todos do RED)', (exc.code, MEM['saves']), ('red_no_eci', 0))
    from apps.pages.features.deals_monitor import domain as DM
    tk = {t['id']: t for t in DM.TASKS}.get('red-clients')
    check('a tarefa diária no Intraday Monitor', (tk or {}).get('kind'), 'routine')

    print('\n== 4. a aprovação ==')
    from apps.config import Config
    MEM['regs'] = [{'COUNTERPARTY': 'ALPHA SA', 'ECI': '111', 'STATUS': 'PENDING', 'RED': 'Y', 'MAKER': 'B222222'},
                   {'COUNTERPARTY': 'BETA LTDA', 'ECI': '222', 'STATUS': 'PENDING', 'MAKER': 'B222222'}]
    _ua0 = R._user_can_access_page
    R._user_can_access_page = lambda p: True
    c = app.test_client()
    with c.session_transaction() as s:
        s.update({'authenticated': True, 'user_sid': 'A111111', 'user_name': 'Ana', 'user_role': 'ADMIN',
                  'session_ip': '127.0.0.1'})
    a = c.post('/api/b3/update', json={'table': 'refdata', 'idx': 0, 'action': 'approve'}).get_json()
    b = c.post('/api/b3/update', json={'table': 'refdata', 'idx': 1, 'action': 'approve'}).get_json()
    check('marcado aprovado volta RED', (a.get('new_status'), MEM['regs'][0]['STATUS']), ('RED', 'RED'))
    check('desmarcado aprovado volta ACTIVE', (b.get('new_status'), MEM['regs'][1]['STATUS']), ('ACTIVE', 'ACTIVE'))
    R._user_can_access_page = _ua0

    print('\n== 5. os avisos de liquidação ==')
    MEM['regs'] = [{'COUNTERPARTY': 'Banco Ômega S.A.', 'ECI': '1', 'STATUS': 'RED', 'RED': 'Y'},
                   {'COUNTERPARTY': 'ZETA LTDA', 'ECI': '2', 'STATUS': 'ACTIVE'}]
    check('nome: acento, pontuação e sufixo', PR.red_names(['BANCO OMEGA SA', 'ZETA LTDA', 'banco omega s/a']),
          ['BANCO OMEGA SA'])
    with app.test_request_context():
        nomes = PR.anota_avisos([{'counterparty': 'BANCO OMEGA SA'}, {'counterparty': 'ZETA LTDA'}])
        resp = app.process_response(app.make_response('x'))
        hdr = resp.headers.get('X-Red-Clients')
    check('o cabeçalho X-Red-Clients só com o RED', json.loads(base64.b64decode(hdr).decode('utf-8')) if hdr else None,
          ['BANCO OMEGA SA'])
    with app.test_request_context():
        PR.anota_avisos([{'counterparty': 'ZETA LTDA'}])
        resp = app.process_response(app.make_response('x'))
    check('   e nenhum cabeçalho sem RED', resp.headers.get('X-Red-Clients'), None)
    c2 = app.test_client()
    with c2.session_transaction() as s:
        s.update({'authenticated': True, 'user_sid': 'A111111', 'user_name': 'Ana', 'session_ip': '127.0.0.1'})
    lst = c2.get('/api/red-clients').get_json()
    check('a API lista quem está marcado', [x['name'] for x in lst.get('clients', [])], ['Banco Ômega S.A.'])
finally:
    R._b3_load, R._b3_save, R._create_notification, P.write_status = _l0, _s0, _n0, _w0

node = shutil.which('node')
if node:
    casos = ['Banco Ômega S.A.', 'BANCO OMEGA SA', 'Itaú Unibanco S/A', 'ACME Ltda.', 'X', '  a  b  ', 'Foo Inc', 'SA']
    js = io.open(os.path.join(ROOT, 'apps/static/js/red-clients.js'), encoding='utf-8').read()
    m = js[js.index('var SUFIXOS'):js.index('// ── textos')]
    prog = m + '\nconsole.log(JSON.stringify(%s.map(nameKey)));' % json.dumps(casos, ensure_ascii=False)
    out = subprocess.run([node, '-e', prog], capture_output=True, text=True).stdout.strip()
    check('o nome no JS é o MESMO do servidor (node)', json.loads(out or '[]'), [PR.name_key(x) for x in casos])
else:
    print('  skip: sem node')

print('\n== 6. as telas ==')
from apps.pages.platform import authz as AZ                # noqa: E402
check('o card no registro', any(c['id'] == 'redclients' for c in AZ._CONTROL_PANEL_CARDS), True)
check('   os endpoints presos ao card', (AZ._CP_ENDPOINT_CARD.get('/api/control-panel/red-clients/run'),
                                         AZ._CP_ENDPOINT_CARD.get('/api/control-panel/red-clients/status')), ('redclients', 'redclients'))
cp = io.open(os.path.join(ROOT, 'apps/templates/pages/control-panel.html'), encoding='utf-8').read()
check('   o card, o dropzone e o Run na tela', all(x in cp for x in (
    'data-cp-card="redclients"', "cpWireDropzone('cpRedDrop'", 'data-upload-endpoint="/api/control-panel/red-clients/run"',
    'accept=".xlsx,.xls"')), True)
rd = io.open(os.path.join(ROOT, 'apps/templates/pages/reference-data.html'), encoding='utf-8').read()
check('a pílula RED na tela de Reference Data (vermelha, maiúscula)',
      "text-bg-danger\" data-case=\"upper\">RED</span>'" in rd, True)
check('   e o aprovar em lote pula o RED', "badgeText === 'RED') return;" in rd, True)
PAGS = ['cognos', 'ndf-cockpit', 'ndf-other-publisher', 'ndf-summary', 'operations-b3',
        'other-products-ndf-settlement-advice', 'other-products-option-settlement-advice', 'other-products-summary',
        'other-products-swap-athena', 'other-products-swap-events', 'other-products-swap-kapital-hybrids',
        'other-products-swap-latamdeskposition', 'other-products-swap-settlement-advice', 'other-products-swap-vcp',
        'otm-settlements']
sem = [p for p in PAGS if 'red-clients.js' not in io.open(os.path.join(ROOT, 'apps/templates/pages/%s.html' % p), encoding='utf-8').read()]
check('as quinze telas de liquidação carregam o red-clients.js', sem, [])
ENT = ''.join(io.open(os.path.join(ROOT, f), encoding='utf-8').read() for f in (
    'apps/pages/features/ndf_summary/entrypoint.py', 'apps/pages/features/other_products/entrypoint.py'))
check('os cinco endpoints de aviso anotam os RED', ENT.count('_red_clients.anota_avisos(drafts)'), 5)
tr = {l: json.load(io.open(os.path.join(ROOT, 'apps/static/data/translations/%s.json' % l), encoding='utf-8')) for l in ('en', 'br', 'es')}
chaves = ['cp-r-red-title', 'cp-r-red-desc', 'cp-red-done', 'cp-red-last', 'e_red_sheet_missing', 'e_red_no_eci', 'im-task-red-clients']
check('as chaves nas três línguas', [k for k in chaves for l in tr if k not in tr[l]], [])

print(('\nFALHAS (%d): %s' % (len(fails), fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
