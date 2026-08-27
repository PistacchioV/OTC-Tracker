# -*- coding: utf-8 -*-
"""A tela Cognos (FXO Detail) — CRUD por linha com confirmacao de outro usuario.

Linha nova entra `OK` com o maker; o EDIT devolve para `Pending`, regrava o
maker e LIMPA o checker; o CONFIRM exige OUTRO usuario (403 `same_user`) e
volta a `OK` com o checker. O store e por dia (o Save Daily Settlement grava o
mesmo arquivo, por isso `_cog_load/_cog_save` sao plataforma).
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

R.COG_JSON_ROOT = TMP

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def cliente(sid):
    c = app.test_client()
    with c.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = sid
        s['user_name'] = sid
        s['user_role'] = 'BO'
        s['user_email'] = sid + '@x'
        s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    return c


maker, checker, anon = cliente('A111111'), cliente('B222222'), app.test_client()
DIA = {'date': '2026-08-20'}

print('== 1. sem sessao ==')
check('data -> 401', anon.get('/api/cognos/data').status_code, 401)
check('row/add -> 401', anon.post('/api/cognos/row/add').status_code, 401)

print('\n== 2. linha nova entra OK com o maker ==')
r = maker.post('/api/cognos/row/add', json=dict(DIA, cells=['ATH-1', 'x', 'y']))
rid = r.get_json()['id']
check('200 com id', (r.status_code, bool(rid)), (200, True))
jp = os.path.join(TMP, '2026', '08', '20', 'cognos_20260820.json')
rec = json.load(io.open(jp, encoding='utf-8'))[0]
check('   OK, maker, sem checker',
      (rec['_cg_status'], rec['_cg_maker'], rec['_cg_checker']), ('OK', 'A111111', ''))

print('\n== 3. edit devolve para Pending ==')
r = maker.post('/api/cognos/row/edit', json=dict(DIA, id=rid, cells=['ATH-1', 'editado']))
check('200', r.status_code, 200)
rec = json.load(io.open(jp, encoding='utf-8'))[0]
check('   Pending, maker regravado, checker limpo',
      (rec['_cg_status'], rec['_cg_maker'], rec['_cg_checker']), ('Pending', 'A111111', ''))

print('\n== 4. confirm exige outro usuario ==')
r = maker.post('/api/cognos/row/confirm', json=dict(DIA, id=rid))
check('o maker nao confirma (403 same_user)',
      (r.status_code, r.get_json()['error']), (403, 'same_user'))
r = checker.post('/api/cognos/row/confirm', json=dict(DIA, id=rid))
check('outro usuario confirma', r.status_code, 200)
rec = json.load(io.open(jp, encoding='utf-8'))[0]
check('   OK de novo, com o checker', (rec['_cg_status'], rec['_cg_checker']),
      ('OK', 'B222222'))
r = checker.post('/api/cognos/row/confirm', json=dict(DIA, id='nao-existe'))
check('id inexistente e 404', r.status_code, 404)

print('\n== 5. delete tira a linha ==')
r = checker.post('/api/cognos/row/delete', json=dict(DIA, id=rid))
check('200', r.status_code, 200)
check('   arquivo vazio', json.load(io.open(jp, encoding='utf-8')), [])

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
