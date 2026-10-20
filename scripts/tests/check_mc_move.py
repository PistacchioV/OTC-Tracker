"""Confirmations Monitor: arrastar o card entre as colunas (`/api/manual-confirmation/move`, §632).

Soltar na coluna seguinte ASSINA a etapa pelas mesmas funções da tela do
documento (`mark_validated`, o release do Legal, o envio do FepWeb com o
callback antes). A mesa move só a etapa DELA e um passo à frente; admin e
master movem qualquer card para qualquer coluna — para trás é reabrir.

Bancos da esteira num tmp (`manual_conf._DB_DIR`), cadastro de validação num
tmp, espelho do Pending Confirmation e sino trocados por espiões: nada real.
"""
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

from apps.pages import manual_conf as M                          # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


TMP_DB = tempfile.mkdtemp(prefix='mc-move-db-')
TMP_MAP = tempfile.mkdtemp(prefix='mc-move-map-')
M._DB_DIR = TMP_DB
M._MAPPINGS_DIR = TMP_MAP
with io.open(os.path.join(TMP_MAP, 'manual-conf-validation.json'), 'w', encoding='utf-8') as fh:
    json.dump([{'PRODUCT': 'NDF COMM', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED', 'FO': 'EXEMPT'},
               {'PRODUCT': 'SWAP', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED', 'FO': 'REQUESTED'}], fh)

hoje = datetime.now().strftime('%d/%m/%Y')


def novo(key, produto='NDF COMM', **kw):
    # Data Operação de hoje: dentro do prazo, sem justificativa de SLA
    d = {'Trade ID': key, 'Produto': produto, 'LOB': 'CEM', 'Cliente': 'ACME S.A.', 'Data Operação': hoje}
    d.update(kw)
    M.upsert_row(M.blank_row(**d))
    return M.find_row(key)


from apps.pages import routes as R                               # noqa: E402
from apps import create_app                                      # noqa: E402
from apps.config import DebugConfig                              # noqa: E402

NOTIFS, SYNC = [], []
R._create_notification = lambda *a, **k: NOTIFS.append(a)
R._mc_pc_sync = lambda rows: SYNC.append(len(rows))

app = create_app(DebugConfig)
app.config['TESTING'] = True
cl = app.test_client()


def como(papel, sid='T000000'):
    with cl.session_transaction() as s:
        s['authenticated'] = True
        s['user_sid'] = sid
        s['user_name'] = 'T'
        s['user_role'] = papel
        s['session_ip'] = '127.0.0.1'
        s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()


def mover(keys, de, para, comment=''):
    r = cl.post('/api/manual-confirmation/move', json={'keys': keys, 'from': de, 'to': para, 'comment': comment})
    return r.status_code, (r.get_json() or {})


print('== 1. a mesa: a SUA etapa, um passo à frente ==')
novo('A1')
como('BO')
st, d = mover(['A1'], 'OTC', 'MO')
check('BO solta o Pending OTC no MO: assina o OTC', st, 200)
check('   e a linha vai para Pending MO', M.find_row('A1')['Pending'], M.PENDING_MO)
check('   o espelho do Pending Confirmation é chamado', SYNC[-1:], [1])
st, d = mover(['A1'], 'MO', 'FEPWEB')
check('BO não move a etapa do MO', (st, d.get('code')), (403, 'move_not_allowed'))
como('MO')
st, d = mover(['A1'], 'MO', 'OK')
check('MO não pula etapa (MO → Ok)', (st, d.get('code')), (403, 'move_not_allowed'))
st, d = mover(['A1'], 'MO', 'FEPWEB')
check('MO solta o seu card no FepWeb: assina o MO', st, 200)
check('   e a linha vai para Pending FepWeb', M.find_row('A1')['Pending'], M.PENDING_FEPWEB)
st, d = mover(['A1'], 'FEPWEB', 'OTC')
check('MO não reabre (para trás é do admin)', (st, d.get('code')), (403, 'move_not_allowed'))
como('BO')
st, d = mover(['A1'], 'FEPWEB', 'OK')
check('FepWeb → Ok sem callback é recusado', (st, d.get('code')), (409, 'callback_required'))
M.save_changes(M.find_row('A1'), dict(M.find_row('A1'), **{'Data Callback': hoje}))
st, d = mover(['A1'], 'FEPWEB', 'OK')
check('com o callback, vira Ok', (st, M.find_row('A1')['Pending']), (200, M.STATUS_OK))

print('\n== 2. Legal ==')
novo('L1', Pending=M.PENDING_LEGAL)
check('nasce no hold do jurídico', M.find_row('L1')['Pending'], M.PENDING_LEGAL)
como('FO')
st, d = mover(['L1'], 'LEGAL', 'OTC')
check('FO não solta o Legal (é do OTC Ops)', (st, d.get('code')), (403, 'move_not_allowed'))
como('BO')
st, d = mover(['L1'], 'LEGAL', 'OTC')
check('BO solta o Legal no OTC', (st, M.find_row('L1')['Pending']), (200, M.PENDING_OTC))

print('\n== 3. admin: qualquer card, qualquer coluna ==')
novo('S1', produto='SWAP')
como('ADMIN')
st, d = mover(['S1'], 'OTC', 'FEPWEB')
r = M.find_row('S1')
check('admin pula etapas: OTC → FepWeb assina OTC, MO e FO', st, 200)
check('   OTC, MO e FO carimbados',
      [bool(r['Conferido OTC']), bool(r['VALIDADO p/ MO']), bool(r['VALIDADO p/ FO'])], [True, True, True])
check('   e a linha está em Pending FepWeb', r['Pending'], M.PENDING_FEPWEB)
st, d = mover(['S1'], 'FEPWEB', 'OTC')
r = M.find_row('S1')
check('admin reabre em Pending OTC: limpa as validações', (st, r['Pending']), (200, M.PENDING_OTC))
check('   OTC, MO e FO limpos', [r['Conferido OTC'], r['VALIDADO p/ MO'], r['VALIDADO p/ FO']], ['', '', ''])
st, d = mover(['S1'], 'OTC', 'LEGAL')
check('admin põe no hold do jurídico', (st, M.find_row('S1')['Pending']), (200, M.PENDING_LEGAL))
st, d = mover(['S1'], 'LEGAL', 'MO')
check('admin tira do Legal e já assina o OTC', (st, M.find_row('S1')['Pending']), (200, M.PENDING_MOFO))
como('MO')
st, d = mover(['S1'], 'MO', 'FEPWEB')
check('o MO assina só o MO num Pending MO/FO: sobra o FO', (st, M.find_row('S1')['Pending']), (200, M.PENDING_FO))

print('\n== 4. SLA vencido pede a justificativa ==')
velho = (datetime.now() - timedelta(days=40)).strftime('%d/%m/%Y')
novo('V1', **{'Data Operação': velho})
como('BO')
st, d = mover(['V1'], 'OTC', 'MO')
check('fora do prazo sem motivo: 409 sla_comment_required', (st, d.get('code')), (409, 'sla_comment_required'))
st, d = mover(['V1'], 'OTC', 'MO', comment='cliente demorou')
check('com o motivo, assina', (st, M.find_row('V1')['Pending']), (200, M.PENDING_MO))
check('   e o motivo vai para o comentário da etapa', M.find_row('V1').get('OTC Comments'), 'cliente demorou')

print('\n== 5. pedido torto ==')
st, d = mover(['A1'], 'OTC', 'OTC')
check('mesma coluna é recusada', st, 400)
st, d = mover(['NAO-EXISTE'], 'OTC', 'MO')
check('chave que não existe: 404', st, 404)
anon = app.test_client()
check('sem sessão: 401', anon.post('/api/manual-confirmation/move', json={}).status_code, 401)

print('\n== 6. quadro DESATUALIZADO: a coluna real manda, não a da tela ==')
# A tela não se atualiza sozinha. A permissão era conferida contra o `from`
# do request e a gravação agia sobre a coluna REAL: um card velho reabria uma
# confirmação Ok ou assinava a etapa de outra mesa.
novo('Z1')
M.save_changes(M.find_row('Z1'), dict(M.find_row('Z1'), **{'Data Callback': hoje}))
como('ADMIN')
mover(['Z1'], 'OTC', 'OK')
check('Z1 está Ok', M.find_row('Z1')['Pending'], M.STATUS_OK)
antes = dict(M.find_row('Z1'))
como('BO')
st, d = mover(['Z1'], 'LEGAL', 'OTC')
check('BO com o card velho em Legal: 409 stale_card', (st, d.get('code'), d.get('stage')), (409, 'stale_card', 'OK'))
check('   e NADA foi reaberto', {k: M.find_row('Z1').get(k) for k in ('Pending', 'Conferido OTC', 'VALIDADO p/ MO', M.SENT_COLUMN)},
      {k: antes.get(k) for k in ('Pending', 'Conferido OTC', 'VALIDADO p/ MO', M.SENT_COLUMN)})
como('ADMIN')
st, d = mover(['Z1'], 'FEPWEB', 'OTC')
check('o admin com o card velho também: 409 (reabrir um Ok por engano é destrutivo)', (st, d.get('code')), (409, 'stale_card'))
novo('Z2')                                                    # em Pending OTC
como('MO')
st, d = mover(['Z2'], 'MO', 'FEPWEB')
check('MO com o card velho em MO numa linha em Pending OTC: 409', (st, d.get('code'), d.get('stage')), (409, 'stale_card', 'OTC'))
check('   e o OTC NÃO foi assinado por um MO', M.find_row('Z2').get('Conferido OTC') or '', '')
como('BO')
mover(['Z2'], 'OTC', 'MO')
st, d = mover(['Z2'], 'OTC', 'MO')
check('o mesmo passo de novo (segunda aba): 409, não assina duas vezes', (st, d.get('code')), (409, 'stale_card'))
novo('Z3')
st, d = mover(['Z3', 'Z2'], 'OTC', 'MO')
check('card com várias chaves e UMA fora do lugar: nada é gravado', (st, M.find_row('Z3')['Pending']), (409, M.PENDING_OTC))

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
