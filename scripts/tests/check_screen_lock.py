# -*- coding: utf-8 -*-
"""A tela travada (Lock Screen do menu do usuário): só o fluxo de desbloqueio
passa, e todo o resto volta para o lock.

A exceção são as TRADUÇÕES: a própria tela travada as pede pelo
`/static/data/translations/...`, que é o `static_data_file` (vence o `static`
embutido) — barradas, o I18nManager lia a página do lock como JSON e o Lock
ficava em inglês para quem usa o app em português/espanhol. Só elas: RefData e
cadastros que a mesma rota serve continuam fechados.
"""
import os, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps import create_app                                 # noqa: E402
from apps.config import DebugConfig                         # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def cliente(locked):
    c = app.test_client()
    with c.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = 'A111111'
        s['user_name'] = 'A111111'
        s['user_role'] = 'BO'
        s['user_email'] = 'a@x'
        s['session_ip'] = '127.0.0.1'
        if locked:
            s['locked'] = True
    return c


def vai_ao_lock(resp):
    return resp.status_code == 302 and '/auth-2-lock-screen' in (resp.headers.get('Location') or '')


trav = cliente(True)

print('== 1. com a tela travada, as traduções passam ==')
for lang in ('en', 'br', 'es'):
    r = trav.get('/static/data/translations/%s.json' % lang)
    check('translations/%s.json -> 200' % lang, r.status_code, 200)
    check('   e é JSON', (r.mimetype or '').endswith('json'), True)

print('\n== 2. o resto continua fechado ==')
for path in ('/dashboard', '/api/me/access', '/static/data/RefData.json',
             '/static/data/translations/../RefData.json',
             '/static/data/translations/%2e%2e/RefData.json',
             '/static/data/mappings/le-spn.json'):
    check('%s volta para o lock' % path, vai_ao_lock(trav.get(path)), True)

print('\n== 3. a própria tela travada abre ==')
check('/auth-2-lock-screen -> 200', trav.get('/auth-2-lock-screen').status_code, 200)

print('\n== 4. sem o lock nada muda ==')
livre = cliente(False)
check('translations/br.json -> 200', livre.get('/static/data/translations/br.json').status_code, 200)
check('/dashboard não vai ao lock', vai_ao_lock(livre.get('/dashboard')), False)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
