"""Esteira → Pending Confirmation: o que a gravação da esteira espelha, e o que
ela NÃO pode desfazer (§696).

O que se prova:
  1. `_mc_pc_sync`:
     * etapa da esteira entra verbatim; `Ok` vira o status de ASSINATURA pela
       regra do Pending (Digital → Pending Digital Signature, Internal →
       Exception Digital Fep Web, o resto → Pending Original);
     * com o Pending já fora da esteira (Concluded, Signed Digitally), a
       gravação seguinte da esteira NÃO o reescreve;
     * reabrir a esteira (Pending OTC) volta o Pending para a etapa;
     * banco do Pending ilegível: registra a falha (`mirrors`), não levanta.
  2. Edit do Track: desfazer a validação de outra mesa pela grade é 403 —
     o Edit da página velha mandava a linha inteira e apagava a assinatura;
     a mesa da etapa desfaz a dela.
  3. Arrastar OTC → OK (admin) sem callback: 409 ANTES de gravar — nada
     assinado. Validar um lote em que a SEGUNDA pede justificativa: 409 e a
     primeira não fica assinada.
  4. Laço que levanta no meio (banco ocupado): o que já foi gravado vai para
     o Pending mesmo assim.

Bancos da esteira e do Pending num tmp; sino trocado por espião.
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
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.check-share'))

from apps.pages import manual_conf as M                          # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


TMP_DB = tempfile.mkdtemp(prefix='mc-sync-db-')
TMP_MAP = tempfile.mkdtemp(prefix='mc-sync-map-')
TMP_PC = tempfile.mkdtemp(prefix='mc-sync-pc-')
M._DB_DIR = TMP_DB
M._MAPPINGS_DIR = TMP_MAP
with io.open(os.path.join(TMP_MAP, 'manual-conf-validation.json'), 'w', encoding='utf-8') as fh:
    json.dump([{'PRODUCT': 'NDF COMM', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED', 'FO': 'EXEMPT'}], fh)

hoje = datetime.now().strftime('%d/%m/%Y')
velho = (datetime.now() - timedelta(days=40)).strftime('%d/%m/%Y')

from apps.pages import routes as R                               # noqa: E402
from apps import create_app                                      # noqa: E402
from apps.config import DebugConfig                              # noqa: E402
from apps.pages.platform import pending_confirmation as PC       # noqa: E402
from apps.pages.platform import manual_confirmation as PMC       # noqa: E402
from apps.pages.platform import mirrors                          # noqa: E402

R._PC_DB_DIR = TMP_PC
R._create_notification = lambda *a, **k: None
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


def esteira(key, data=hoje, **kw):
    d = {'Trade ID': key, 'Produto': 'NDF COMM', 'LOB': 'CEM', 'Cliente': 'ACME S.A.',
         'Data Operação': data}
    d.update(kw)
    M.upsert_row(M.blank_row(**d))
    return M.find_row(key)


def pending(key, status='Pending OTC', sig='', trade=None):
    PC._pc_upsert_rows([{'Trade Number': key, 'Product Type': 'NDF COMM', 'Client': 'ACME S.A.',
                         'Pending Status': status, 'Signature Type': sig,
                         'Trade Date': trade or hoje,
                         'Maturity Date': (datetime.now() + timedelta(days=200)).strftime('%d/%m/%Y')}])


def pc_status(key):
    return (PC._pc_find_row(key) or {}).get('Pending Status')


print('== 1. _mc_pc_sync ==')
for k, sig, esperado in (('D1', 'Digital', 'Pending Digital Signature'),
                         ('I1', 'Internal', 'Exception Digital Fep Web'),
                         ('O1', 'Manual', 'Pending Original')):
    esteira(k, Pending=M.STATUS_OK)
    pending(k, 'Pending FepWeb', sig)
    PMC._mc_pc_sync([dict(M.find_row(k), Pending=M.STATUS_OK)])
    check('Ok + %s → %s' % (sig, esperado), pc_status(k), esperado)
pending('D1', 'Concluded', 'Digital')
PMC._mc_pc_sync([dict(M.find_row('D1'), Pending=M.STATUS_OK)])
check('Pending já resolvido pela equipe NÃO volta a Pending', pc_status('D1'), 'Concluded')
PMC._mc_pc_sync([dict(M.find_row('D1'), Pending=M.PENDING_OTC)])
check('a esteira reaberta volta o Pending para a etapa', pc_status('D1'), M.PENDING_OTC)
esteira('E1')
pending('E1', 'Pending OTC')
PMC._mc_pc_sync([dict(M.find_row('E1'), Pending=M.PENDING_MO)])
check('etapa da esteira entra verbatim', pc_status('E1'), M.PENDING_MO)
_orig = PC._pc_find_rows


def _ocupado(_tns):
    raise IOError('banco ocupado')


PC._pc_find_rows = _ocupado
try:
    with app.test_request_context('/api/manual-confirmation/x'):
        PMC._mc_pc_sync([dict(M.find_row('E1'), Pending=M.PENDING_FO)])
        check('Pending ilegível: não levanta e registra a falha',
              [x['target'] for x in mirrors.registradas()], ['pc'])
finally:
    PC._pc_find_rows = _orig

print('\n== 2. Edit do Track não desfaz a validação de outra mesa ==')
esteira('V1', **{'Conferido OTC': hoje, 'Time Stamp OTC': 'x', 'VALIDADO p/ MO': hoje,
                 'Time Stamp MO': 'y'})
pending('V1', 'Pending FepWeb')
como('BO')
# A linha VELHA da página (antes da validação do MO), inteira — o que o modal
# mandava até o §696.
r = cl.post('/api/manual-confirmation/upsert', json={'row': {
    'Trade ID': 'V1', 'VALIDADO p/ MO': '', 'Data Callback': hoje}})
check('BO com a linha velha: 403', (r.status_code, (r.get_json() or {}).get('stage')), (403, M.STAGE_MO))
check('   e a validação do MO fica', M.find_row('V1')['VALIDADO p/ MO'], hoje)
r = cl.post('/api/manual-confirmation/upsert', json={'row': {'Trade ID': 'V1', 'Data Callback': hoje}})
check('só o campo mexido: grava', r.status_code, 200)
check('   e a validação do MO continua', (M.find_row('V1')['VALIDADO p/ MO'],
                                        M.find_row('V1')['Data Callback']), (hoje, hoje))
como('MO')
r = cl.post('/api/manual-confirmation/upsert', json={'row': {'Trade ID': 'V1', 'VALIDADO p/ MO': ''}})
check('o MO desfaz a DELE', (r.status_code, M.find_row('V1')['VALIDADO p/ MO']), (200, ''))
tpl = io.open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'manual-confirmation-track.html'),
              encoding='utf-8').read()
check('o modal guarda o valor de abertura e manda só o que mudou',
      "data-orig" in tpl and "v === ($(this).attr('data-orig') || '')" in tpl, True)

print('\n== 3. a recusa vem ANTES de gravar ==')
esteira('C1')
pending('C1', 'Pending OTC')
como('ADMIN')
r = cl.post('/api/manual-confirmation/move', json={'keys': ['C1'], 'from': 'OTC', 'to': 'OK'})
check('admin OTC → OK sem callback: 409', (r.status_code, (r.get_json() or {}).get('code')),
      (409, 'callback_required'))
check('   e NADA foi assinado', (M.find_row('C1')['Conferido OTC'], M.find_row('C1')['Pending']),
      ('', M.PENDING_OTC))
esteira('B1')
esteira('B2', data=velho)                 # fora do prazo: pede justificativa
como('BO')
r = cl.post('/api/manual-confirmation/validate', json={'keys': ['B1', 'B2'], 'stage': 'OTC'})
check('lote com a 2ª atrasada: 409', (r.status_code, (r.get_json() or {}).get('sla_comment_required')),
      (409, True))
check('   e a 1ª NÃO ficou assinada', M.find_row('B1')['Conferido OTC'], '')

print('\n== 4. laço que levanta no meio: o gravado vai ao Pending ==')
esteira('P1', Pending=M.PENDING_FEPWEB, **{'Conferido OTC': hoje, 'VALIDADO p/ MO': hoje,
                                          'Data Callback': hoje})
esteira('P2', Pending=M.PENDING_FEPWEB, **{'Conferido OTC': hoje, 'VALIDADO p/ MO': hoje,
                                          'Data Callback': hoje})
pending('P1', 'Pending FepWeb', 'Digital')
pending('P2', 'Pending FepWeb', 'Digital')
_save = M.save_changes
n = {'i': 0}


def _segunda_quebra(antes, depois):
    n['i'] += 1
    if n['i'] == 2:
        raise IOError('banco ocupado')
    return _save(antes, depois)


M.save_changes = _segunda_quebra
try:
    como('BO')
    r = cl.post('/api/manual-confirmation/fepweb-sent', json={'keys': ['P1', 'P2']})
    check('a resposta é de erro', r.status_code >= 500, True)
finally:
    M.save_changes = _save
check('   a 1ª foi marcada e o Pending a acompanhou',
      (bool(M.find_row('P1')[M.SENT_COLUMN]), pc_status('P1')), (True, 'Pending Digital Signature'))
check('   a 2ª ficou como estava', (M.find_row('P2')[M.SENT_COLUMN], pc_status('P2')),
      ('', 'Pending FepWeb'))

print('\n== 5. a grade do Track tem as travas do Monitor (§701) ==')
esteira('G1')
como('MO')
r = cl.post('/api/manual-confirmation/upsert', json={'row': {'Trade ID': 'G1', 'VALIDADO p/ MO': hoje}})
check('MO antes do OTC pela grade: 409 stage_not_pending',
      (r.status_code, (r.get_json() or {}).get('code')), (409, 'stage_not_pending'))
check('   e nada gravado', M.find_row('G1')['VALIDADO p/ MO'], '')
como('BO')
r = cl.post('/api/manual-confirmation/upsert', json={'row': {'Trade ID': 'G1', 'Conferido OTC': hoje}})
check('o OTC valida pela grade', r.status_code, 200)
como('MO')
r = cl.post('/api/manual-confirmation/upsert', json={'row': {'Trade ID': 'G1', 'VALIDADO p/ MO': hoje}})
check('   e então o MO', (r.status_code, M.find_row('G1')['Pending']), (200, M.PENDING_FEPWEB))
como('BO')
r = cl.post('/api/manual-confirmation/upsert', json={'row': {'Trade ID': 'G1', 'Conferido OTC': ''}})
check('desfazer só a do OTC com o MO validado: 409 mc_reopen_instead',
      (r.status_code, (r.get_json() or {}).get('code')), (409, 'mc_reopen_instead'))
r = cl.post('/api/manual-confirmation/upsert', json={'row': {'Trade ID': 'G1', M.SENT_COLUMN: hoje}})
check('Enviado sem callback pela grade: 409 callback_required',
      (r.status_code, (r.get_json() or {}).get('code')), (409, 'callback_required'))
esteira('G2')
r = cl.post('/api/manual-confirmation/upsert', json={'row': {
    'Trade ID': 'G2', 'Data Callback': hoje, M.SENT_COLUMN: hoje}})
check('Enviado com a esteira em Pending OTC: 409 mc_not_fepweb',
      (r.status_code, (r.get_json() or {}).get('code')), (409, 'mc_not_fepweb'))
como('MO')
r = cl.post('/api/manual-confirmation/upsert', json={'row': {
    'Trade ID': 'G1', 'Data Callback': hoje, M.SENT_COLUMN: hoje}})
check('Enviado é do OTC: o MO leva 403', (r.status_code, (r.get_json() or {}).get('stage')),
      (403, M.STAGE_OTC))
como('BO')
r = cl.post('/api/manual-confirmation/upsert', json={'row': {
    'Trade ID': 'G1', 'Data Callback': hoje, M.SENT_COLUMN: hoje}})
check('o OTC, com callback e as validações: grava Ok', (r.status_code, M.find_row('G1')['Pending']),
      (200, M.STATUS_OK))
tpl = io.open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'manual-confirmation-track.html'),
              encoding='utf-8').read()
check('a tela traduz as recusas novas nas três línguas',
      all(tpl.count('e_' + c + ':') == 3 for c in ('stage_not_pending', 'mc_reopen_instead',
                                                   'mc_not_fepweb', 'callback_required')), True)

print('\n== 6. o Pending Confirmation grava só o que mudou (§701) ==')
pending('M1', 'Pending OTC', 'Digital')
carregada = {k: ('' if v is None else str(v)) for k, v in PC._pc_find_row('M1').items()}
# Depois da carga, outra pessoa conclui e preenche o FepWeb ID…
PC._pc_upsert_rows([dict(carregada, **{'Pending Status': 'Concluded', 'FepWeb ID': 'F-9'})])
# …e esta tela, com a linha velha, só mexeu nos Comments.
editada = dict(carregada, Comments='ligar amanhã')
r = cl.post('/api/pending-confirmation/upsert', json={'row': editada, 'orig': carregada})
check('grava', r.status_code, 200)
g = PC._pc_find_row('M1')
check('   o Comments entrou e o que a outra pessoa gravou ficou',
      (g['Comments'], g['Pending Status'], g['FepWeb ID']), ('ligar amanhã', 'Concluded', 'F-9'))
r = cl.post('/api/pending-confirmation/upsert', json={'rows': [editada], 'origs': [carregada]})
check('o lote (mass update) segue a mesma regra', PC._pc_find_row('M1')['Pending Status'], 'Concluded')
r = cl.post('/api/pending-confirmation/upsert', json={'row': editada})
check('sem orig (aba antiga / Add Row): a linha inteira, como antes',
      PC._pc_find_row('M1')['Pending Status'], 'Pending OTC')
PC._pc_delete_trade_number('M1')
r = cl.post('/api/pending-confirmation/upsert', json={'row': editada, 'orig': carregada})
check('linha apagada por outra pessoa: 409 pc_row_gone, sem recriar',
      (r.status_code, (r.get_json() or {}).get('code'), PC._pc_find_row('M1')),
      (409, 'pc_row_gone', None))
_orig_w = PC._pc_write_exec


def _ocupado_w(cat, ops, raise_errors=False):
    if raise_errors:
        raise IOError('banco ocupado')
    return False


pending('M2', 'Pending OTC')
PC._pc_write_exec = _ocupado_w
try:
    r = cl.post('/api/pending-confirmation/delete', json={'trade_number': 'M2'})
    check('Delete com o banco ocupado: NÃO responde success',
          (r.get_json() or {}).get('success'), False)
finally:
    PC._pc_write_exec = _orig_w
check('   e a linha continua', PC._pc_find_row('M2') is not None, True)
tpl = io.open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'pending-confirmation.html'),
              encoding='utf-8').read()
check('a tela manda o orig e tira a linha da grade só depois do servidor',
      'orig: orig === undefined ? pcOrigOf(d) : orig' in tpl
      and 'origs: ds.map(pcOrigOf)' in tpl
      and 'pcDeleteRow(tn).then(function(ok)' in tpl, True)

print(('\nFAIL: %d' % len(fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
