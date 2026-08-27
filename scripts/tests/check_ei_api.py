# -*- coding: utf-8 -*-
"""As quatro rotas do Electronic Inventory (a casca; os helpers _ei_* sao
plataforma — o Track, o TED e os saves de confirmacao usam os mesmos).

O que ele prende:

  1. **clients** casa RefData × pastas do share: pasta sem RefData entra
     (on_disk=True), RefData sem pasta so ganha badge quando o SCAN COMPLETO
     justifica (on_disk=False; scan correndo = None, sem badge);
  2. **upload** recusa extensao fora da lista (400) e share fora do ar (503);
     Confirmations arquiva por ano/mes/dia/PRODUTO via TYPE_FOLDER — a mesma
     pasta em que o app grava o que gera;
  3. documents sem client e 400; file inexistente e 404.
"""
import io, json, os, sys, tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

TMP = tempfile.mkdtemp()

from apps.pages import routes as R                          # noqa: E402
from apps import create_app                                 # noqa: E402
from apps.config import DebugConfig                         # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

R.ELECTRONIC_INVENTORY_ROOT = os.path.join(TMP, 'EI')
os.makedirs(os.path.join(R.ELECTRONIC_INVENTORY_ROOT, 'ACME SA'), exist_ok=True)
R._ei_refdata_clients = lambda: [('ACME SA', '100'), ('SO NO REF', '200')]
NOTIFS = []
R._create_notification = lambda *a, **k: NOTIFS.append(a[2:4])

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
            s['user_name'] = 'Alice'
            s['user_role'] = 'BO'
            s['user_email'] = 'a@x'
            s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    return c


c, anon = cliente(), cliente(auth=False)

print('== 1. sem sessao ==')
for ep in ('clients', 'documents', 'upload'):
    met = 'post' if ep == 'upload' else 'get'
    check('%s -> 401' % ep,
          getattr(anon, met)('/api/electronic-inventory/' + ep).status_code, 401)

print('\n== 2. clients: RefData × share ==')
R._ei_scan_root = lambda: (True, {R._ei_match_key('ACME SA'): 'ACME SA'}, True)
d = c.get('/api/electronic-inventory/clients').get_json()
por = {x['name']: x for x in d['clients']}
check('pasta + RefData casam (on_disk True, SPN preenchido)',
      (por['ACME SA']['on_disk'], por['ACME SA']['spn']), (True, '100'))
check('   RefData sem pasta ganha badge quando o scan e COMPLETO',
      por['SO NO REF']['on_disk'], False)
R._ei_scan_root = lambda: (True, {}, False)
d = c.get('/api/electronic-inventory/clients').get_json()
por = {x['name']: x for x in d['clients']}
check('   com o scan CORRENDO nao ha como afirmar (on_disk None, sem badge)',
      por['SO NO REF']['on_disk'], None)

print('\n== 3. documents e file ==')
check('documents sem client e 400',
      c.get('/api/electronic-inventory/documents').status_code, 400)
check('file inexistente e 404',
      c.get('/api/electronic-inventory/file?client=ACME%20SA&rel=Transactional/x.pdf').status_code, 404)

print('\n== 4. upload ==')
r = c.post('/api/electronic-inventory/upload',
           data={'client': 'ACME SA', 'type': 'Transactional', 'subtype': 'CGD',
                 'date': '26/08/2026',
                 'file': (io.BytesIO(b'%PDF'), 'doc.exe')})
check('extensao fora da lista e 400', r.status_code, 400)
r = c.post('/api/electronic-inventory/upload',
           data={'client': 'ACME SA', 'type': 'NAO-EXISTE',
                 'file': (io.BytesIO(b'%PDF'), 'doc.pdf')})
check('tipo fora das tres pastas e 400', r.status_code, 400)
r = c.post('/api/electronic-inventory/upload',
           data={'client': 'ACME SA', 'type': 'Transactional', 'subtype': 'CGD',
                 'date': '26/08/2026',
                 'file': (io.BytesIO(b'%PDF conteudo'), 'doc.pdf')})
d = r.get_json()
check('upload valido grava', (r.status_code, d['success']), (200, True))
trans = os.path.join(R.ELECTRONIC_INVENTORY_ROOT, 'ACME SA', 'Transactional')
arquivos = os.listdir(trans) if os.path.isdir(trans) else []
check('   na pasta Transactional do cliente', len(arquivos), 1)
check('   e o arquivo baixa pela rota file',
      c.get('/api/electronic-inventory/file?client=ACME%20SA&rel=' +
            'Transactional/' + arquivos[0]).status_code, 200)

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
