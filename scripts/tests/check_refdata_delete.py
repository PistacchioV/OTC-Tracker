# -*- coding: utf-8 -*-
"""O DELETE do Reference Data com maker/checker (`/api/b3/*`).

Apagar cadastro de contraparte e' destrutivo e nao tinha revisao nenhuma: o
botao da lixeira desativava (PENDING INACTIVE -> INACTIVE, e a linha ficava),
e o `/api/b3/delete` — que apaga de verdade — ia no clique, sem checker. O que
este guarda prende:

  1. **pedir a exclusao nao apaga nada**: `request_delete` marca
     `PENDING DELETE`, carimba o MAKER e limpa o CHECKER. O registro continua
     no arquivo, visivel, ate alguem aprovar;
  2. **quem pediu nao aprova** (`same_user`, 403) — a mesma regra do resto do
     maker/checker desta tela;
  3. **aprovar um PENDING DELETE REMOVE** o registro, e a resposta traz
     `removed: True`. Esse campo e' contrato com a tela: todo botao da grade
     carrega o `data-idx` (a POSICAO no array), entao remover o item i desloca
     os seguintes — sem o aviso, a tela apagaria so a linha do DOM e os
     vizinhos passariam a apontar para o registro errado, gravando em cima de
     outro cliente sem erro nenhum (a armadilha do Delete da Intrag, §430);
  4. **aprovar o que NAO e' delete continua so mudando o status** — PENDING
     vira ACTIVE e PENDING INACTIVE vira INACTIVE, e o arquivo nao encolhe.

Tudo num tempfile; nao toca em dado real.
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
from apps.pages import data_store as S                      # noqa: E402
from apps import create_app                                 # noqa: E402
from apps.config import DebugConfig                         # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True

# O cadastro vai para um tmp: `_B3_DATA_DIR` e' a superficie de patch (ele fica
# no routes justamente por isso). O `duck_read` responderia pelo banco REAL, e
# a leitura DB-first ignoraria o arquivo do teste — por isso o espelho esta
# desligado e o `_b3_load` cai no JSON, que e' o canal de emergencia de sempre.
R._B3_DATA_DIR = TMP
PATH = os.path.join(TMP, 'RefData.json')

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def semear():
    R._atomic_write_json(PATH, ([
        {'SPN': '111', 'COUNTERPARTY': 'ALPHA SA', 'STATUS': 'ACTIVE',
         'MAKER': 'A111111', 'CHECKER': 'B222222'},
        {'SPN': '222', 'COUNTERPARTY': 'BETA LTDA', 'STATUS': 'ACTIVE',
         'MAKER': 'A111111', 'CHECKER': 'B222222'},
        {'SPN': '333', 'COUNTERPARTY': 'GAMA SA', 'STATUS': 'PENDING',
         'MAKER': 'A111111', 'CHECKER': None},
    ]))


def registros():
    return S.read(PATH)


def cliente(sid):
    c = app.test_client()
    with c.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = sid
        s['user_name'] = 'Fulano ' + sid
        s['user_role'] = 'BO'
        s['user_email'] = 'x@jpmorgan.com'
        s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
    return c


R._create_notification = lambda *a, **k: None
R._user_can_access_page = lambda *a, **k: True
maker, checker = cliente('A111111'), cliente('B222222')


def upd(cli, idx, action):
    return cli.post('/api/b3/update', json={'table': 'refdata', 'idx': idx, 'action': action})


semear()
print('== 1. pedir a exclusao NAO apaga ==')
r = upd(maker, 1, 'request_delete')
check('200 com o status novo', (r.status_code, r.get_json().get('new_status')),
      (200, 'PENDING DELETE'))
recs = registros()
check('o registro CONTINUA no arquivo', len(recs), 3)
check('   marcado como PENDING DELETE', recs[1]['STATUS'], 'PENDING DELETE')
check('   com o MAKER de quem pediu', recs[1]['MAKER'], 'A111111')
check('   e o CHECKER limpo', recs[1]['CHECKER'], None)
check('   sem tocar nos vizinhos',
      [x['SPN'] for x in recs], ['111', '222', '333'])

print('\n== 2. quem pediu nao aprova ==')
r = upd(maker, 1, 'approve')
check('403 same_user', (r.status_code, r.get_json().get('error')), (403, 'same_user'))
check('   e nada foi removido', len(registros()), 3)

print('\n== 3. o checker aprova, e AI o registro some ==')
r = upd(checker, 1, 'approve')
j = r.get_json()
check('200', r.status_code, 200)
check('   a resposta AVISA que removeu (contrato com a tela)', j.get('removed'), True)
recs = registros()
check('   o arquivo encolheu', len(recs), 2)
check('   e sobrou quem devia', [x['SPN'] for x in recs], ['111', '333'])

print('\n== 4. aprovar o que nao e delete so muda o status ==')
# O GAMA era o indice 2; com o BETA removido ele passou a ser o 1 — que e'
# exatamente por que a tela RELE a tabela depois de uma remocao.
r = upd(checker, 1, 'approve')
check('200 ACTIVE', (r.status_code, r.get_json().get('new_status')), (200, 'ACTIVE'))
check('   sem `removed`', r.get_json().get('removed'), None)
recs = registros()
check('   o arquivo nao encolheu', len(recs), 2)
check('   e o CHECKER foi carimbado', recs[1]['CHECKER'], 'B222222')

print('\n== 5. o deactivate continua existindo para as outras tabelas ==')
semear()
r = upd(maker, 0, 'deactivate')
check('PENDING INACTIVE', r.get_json().get('new_status'), 'PENDING INACTIVE')
r = upd(checker, 0, 'approve')
check('   aprovado vira INACTIVE, sem remover',
      (r.get_json().get('new_status'), len(registros())), ('INACTIVE', 3))

print('\n== 6. sem sessao ==')
anon = app.test_client()
check('401', anon.post('/api/b3/update',
                       json={'table': 'refdata', 'idx': 0,
                             'action': 'request_delete'}).status_code, 401)

print(('\nFAIL: %d' % len(fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
