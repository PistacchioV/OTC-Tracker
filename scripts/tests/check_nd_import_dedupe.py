#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""O import do dropzone não DUPLICA a operação que a grade não tinha (02/10/2026).

O `otc-fileupload.js` só reconhece a operação já importada entre as linhas
CARREGADAS na grade. Fora dela, mandava um POST de linha nova, e o servidor só
substituía com Deal + Client IGUAIS no arquivo da Trade Date: Client
reenriquecido/editado ou Trade Date corrigida faziam a mesma operação entrar
duas vezes. Com `_import` o servidor acha a linha (Deal + Acronym, depois
Deal + Client, em todos os dias) e aplica a regra do Amend do box scan.

  1. mesmo Deal + Acronym, Client diferente → substitui, não duplica (Amend,
     B3 ID preservado);
  2. e-mail repetido sem mudança → `same`, nada gravado;
  3. Trade Date corrigida → a linha MUDA de arquivo, uma só no total;
  4. operação nova → acrescenta;
  5. sem `_import` (Add Row) o POST segue como era;
  6. vale para NDF Comm e para as genéricas (Vanilla);
  7. o dropzone manda `_import`.
"""
import os
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
RAIZ = tempfile.mkdtemp(prefix='nd-import-dedupe-')
os.environ['OTC_DATA_DIR'] = RAIZ
os.environ['OTC_DATABASE_DIR'] = os.path.join(RAIZ, 'db')
os.environ.setdefault('SECRET_KEY', 'x')
os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='share-')
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

falhas = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok   ' if ok else '  FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        falhas.append(label)


from apps.config import DebugConfig                           # noqa: E402
from apps import create_app                                   # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True
cl = app.test_client()
with cl.session_transaction() as s:
    s.update({'authenticated': True, 'user_sid': 'T000000', 'user_name': 'T',
              'user_role': 'ADMIN', 'session_ip': '127.0.0.1'})

from apps.pages import routes as R                            # noqa: E402


def todas(url):
    r = cl.post(url + '/search', json={'filters': []})
    return [d for d in (r.get_json() or {}).get('deals', []) if (d.get('Deal') or '').startswith('T-')]


def base(**kw):
    d = {'Deal': 'T-1', 'Acronym': 'ACME', 'Client': 'ACME SA', 'TradeDate': '01/10/2026',
         'Strike': '10', 'Status': 'New', 'Maker': 'M000001', 'B3_ID': ''}
    d.update(kw)
    return d


for nome, url in (('Opt Comm', '/api/new-deals/opt-commodities/cache'),
                  ('NDF Comm', '/api/new-deals/ndf-commodities/cache'),
                  ('Vanilla', '/api/new-deals/vanilla/cache')):
    print('\n== %s ==' % nome)
    r = cl.post(url, json=base(Status='Success', B3_ID='26E000001', Deal='T-1'))
    check('gravou a original', r.status_code, 200)

    # 1. Client diferente (reenriquecido), mesmo Deal + Acronym
    r = cl.post(url, json=dict(base(Client='ACME S.A.', Strike='11'), _import=True))
    j = r.get_json() or {}
    check('1. resultado amend', j.get('result'), 'amend')
    linhas = [d for d in todas(url) if d['Deal'] == 'T-1']
    check('1. uma linha só', len(linhas), 1)
    check('1. Status Amend', linhas[0].get('Status'), 'Amend')
    check('1. B3 ID preservado', linhas[0].get('B3_ID'), '26E000001')
    check('1. dado novo gravado', linhas[0].get('Strike'), '11')
    check('1. _import não vai ao banco', '_import' in linhas[0], False)

    # 2. repetido
    r = cl.post(url, json=dict(base(Client='ACME S.A.', Strike='11'), _import=True))
    check('2. e-mail repetido = same', (r.get_json() or {}).get('result'), 'same')
    check('2. continua uma', len([d for d in todas(url) if d['Deal'] == 'T-1']), 1)

    # 3. Trade Date corrigida → outro arquivo-dia
    r = cl.post(url, json=dict(base(Client='ACME S.A.', Strike='11', TradeDate='02/10/2026'), _import=True))
    check('3. amend na troca de dia', (r.get_json() or {}).get('result'), 'amend')
    linhas = [d for d in todas(url) if d['Deal'] == 'T-1']
    check('3. uma linha só depois de mudar de dia', len(linhas), 1)
    check('3. ficou na Trade Date nova', linhas[0].get('TradeDate'), '02/10/2026')
    check('3. B3 ID foi junto', linhas[0].get('B3_ID'), '26E000001')

    # 4. nova
    r = cl.post(url, json=dict(base(Deal='T-2'), _import=True))
    check('4. nova = new', (r.get_json() or {}).get('result'), 'new')
    check('4. acrescentou', len([d for d in todas(url) if d['Deal'] == 'T-2']), 1)

    # 5. sem _import: Deal + Client como sempre (Add Row)
    r = cl.post(url, json=base(Deal='T-3', Client='X'))
    r = cl.post(url, json=base(Deal='T-3', Client='Y'))
    check('5. Add Row sem _import segue Deal + Client', len([d for d in todas(url) if d['Deal'] == 'T-3']), 2)

print('\n== 7. o dropzone manda _import ==')
js = open(os.path.join(ROOT, 'apps/static/js/pages/otc-fileupload.js'), encoding='utf-8').read()
check('postImport existe', 'function postImport(' in js)
check('manda _import', '_import: true' in js)

print('\nTUDO OK' if not falhas else '\n%d FALHA(S)' % len(falhas))
sys.exit(1 if falhas else 0)
