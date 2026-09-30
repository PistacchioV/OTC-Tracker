#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_intraday_monitor.py — o Intraday Monitor (ex-New Deals Monitor, §567).

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_intraday_monitor.py

O que prende:
  1. a agenda (`domain.task_config`): o padrão de cada tarefa, valor ruim de
     UMA tarefa caindo no padrão DELA, lista vazia de dias = "nunca";
  2. o estado (`domain.avalia`): feita / atrasada / em andamento / a fazer,
     feriado e dia fora da agenda não devidos, feita depois do prazo;
  3. a Intrag desde o import (`domain.intrag_destino`): as três regras do
     espelho, e `Success` saindo daqui (quem conta é a linha real da Intrag);
  4. ponta a ponta com o app num DATA_DIR tmp: o card do Control Panel grava e
     lê a agenda, o snapshot põe a recon como feita pelo registro de execuções
     (com o `End process` como selo), a Comitente só é devida na terça, e a
     operação importada contra o Banco aparece na zona Intrag como
     `Awaiting B3 ID` — e some de lá quando vira `Success`;
  4b. o Pay/Rec só conclui no End process (rodar é 50%); a Branch Reversal só
      existe com liquidação da Branch e anda em três passos — detectada,
      rascunho do VP, reversão casada no Pay/Rec — e o e-mail diz o passo;
  4c. o card de D-1: cada pendência com o link já na data (`?tradedate=` no
      New Deals; na recon, a REFERÊNCIA que ela teria usado), e as páginas de
      destino abrindo nessa data;
  4d. TODA `/reconciliation-*/run` do `url_map` é uma tarefa do catálogo e
      grava `task_runs.record` — recon nova sem isso reprova aqui;
  4g. as tarefas MENSAIS: Swap Accrual no último dia útil, Swap MtM do 1º ao
      4º dia útil — concluem no End process, que no MtM vale em qualquer dia
      da janela; fora da janela não são devidas;
  5. o endereço antigo redireciona e as allowlists antigas (a página e o card
     do aviso) continuam valendo.
"""
import os
import sys
import tempfile
from datetime import date, datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

RAIZ = tempfile.mkdtemp(prefix='intraday-monitor-')
os.environ['OTC_DATA_DIR'] = RAIZ
os.environ['OTC_DATABASE_DIR'] = os.path.join(RAIZ, 'db')
os.environ.setdefault('SECRET_KEY', 'x')
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


from apps.pages.features.deals_monitor import domain as D     # noqa: E402

print('== 1. a agenda ==')
cfg = D.task_config({})
check('uma agenda por tarefa do catálogo', sorted(cfg), sorted(D.TASK_IDS))
check('Conf. Matching: diária', cfg['recon-conf-matching']['days'], [0, 1, 2, 3, 4])
# As rotinas do Control Panel (mesa, 28/09/2026): Save CETIP Files é diária e a
# cobrança das confirmações é de segunda e quinta — o mesmo dia do pacote dela.
check('Save CETIP Files: diária', cfg['save-cetip']['days'], [0, 1, 2, 3, 4])
check('Confirmations Escalation: segunda e quinta', cfg['conf-escalation']['days'], [0, 3])
check('Branch Reversal: seg-sex (só existe com liquidação da Branch)',
      cfg['branch-reversal']['days'], [0, 1, 2, 3, 4])
check('Pay/Rec: diária (seg-sex) até 20:00', cfg['recon-payrec'], {'days': [0, 1, 2, 3, 4], 'deadline': '20:00'})
check('Comitente: toda terça', cfg['recon-comitente']['days'], [1])
check('CGD: toda sexta', cfg['recon-cgd']['days'], [4])
check('FXO: diária', cfg['recon-fxo']['days'], [0, 1, 2, 3, 4])
for z in ('registration', 'confirmation', 'intrag'):
    check('%s: diária' % z, cfg[z]['days'], [0, 1, 2, 3, 4])
ruim = D.task_config({'recon-fxo': {'days': [1, 9, 'x', 3], 'deadline': '25:00'},
                      'recon-cgd': {'days': [], 'deadline': '17:30'}})
check('dia fora de 0..6 some', ruim['recon-fxo']['days'], [1, 3])
check('horário inválido cai no padrão DA TAREFA', ruim['recon-fxo']['deadline'], '20:00')
check('lista vazia é "nunca"', ruim['recon-cgd']['days'], [])
check('horário válido fica', ruim['recon-cgd']['deadline'], '17:30')
check('as outras tarefas não são tocadas', ruim['recon-payrec'], cfg['recon-payrec'])

print('\n== 2. o estado ==')
c = {'days': [0, 1, 2, 3, 4], 'deadline': '20:00'}
ter = date(2026, 9, 22)                     # terça
antes, depois = datetime(2026, 9, 22, 15, 0), datetime(2026, 9, 22, 21, 0)
check('feita', D.avalia(c, ter, antes, False, True, False)['state'], 'done')
check('a fazer', D.avalia(c, ter, antes, False, False, False)['state'], 'todo')
check('em andamento', D.avalia(c, ter, antes, False, False, True)['state'], 'in_progress')
check('atrasada', D.avalia(c, ter, depois, False, False, True)['state'], 'late')
check('feita depois do prazo marca late_done',
      D.avalia(c, ter, depois, False, True, False, datetime(2026, 9, 22, 20, 30))['late_done'], True)
check('feita no prazo não', D.avalia(c, ter, depois, False, True, False,
                                     datetime(2026, 9, 22, 19, 0))['late_done'], False)
check('minutos até o prazo', D.avalia(c, ter, antes, False, False, False)['minutes_left'], 300)
check('feriado não é devido', D.avalia(c, ter, antes, True, False, False)['due'], False)
check('sábado fora da agenda', D.avalia(c, date(2026, 9, 26), antes, False, False, False)['due'], False)

print('\n== 3. a Intrag desde o import ==')
BJ = 'BANCO J.P. MORGAN S.A.'
check('NDF Commodities contra o Banco → Intrag NDF',
      D.intrag_destino('NDF/Commodities', {'Client': BJ, 'Status': 'New'}), 'Intrag/NDF')
check('... contra cliente, não', D.intrag_destino('NDF/Commodities', {'Client': 'CARGILL', 'Status': 'New'}), None)
check('Commodities Options contra o Banco → Intrag Option',
      D.intrag_destino('Option/Commodities', {'Client': BJ, 'Status': 'Pending'}), 'Intrag/Option')
check('FX Options contra o Banco → Intrag Option',
      D.intrag_destino('Option/FXO', {'Client': BJ, 'Status': 'Approved'}), 'Intrag/Option')
check('NDF Vanilla contra o Lawton → Intrag NDF',
      D.intrag_destino('NDF/Vanilla', {'Client': 'LAWTON FIM', 'Status': 'New'}), 'Intrag/NDF')
check('NDF Other Publisher contra o Lawton → Intrag NDF',
      D.intrag_destino('NDF/OtherPublisher', {'Client': 'Lawton', 'Status': 'Sent'}), 'Intrag/NDF')
check('FWD Start fica fora (o espelho também)',
      D.intrag_destino('NDF/FwdStart', {'Client': 'LAWTON', 'Status': 'New'}), None)
check('Swap B2B → Intrag Swap', D.intrag_destino('Swap/Bullet', {'LE': 'ATACAMA', 'Status': 'New'}), 'Intrag/Swap')
check('Swap contra cliente, não', D.intrag_destino('Swap/Cashflow', {'LE': 'JPM', 'Status': 'New'}), None)
check('Success sai (a linha real da Intrag conta)',
      D.intrag_destino('NDF/Commodities', {'Client': BJ, 'Status': 'Success'}), None)
check('Success sem caixa também', D.intrag_destino('NDF/Commodities', {'Client': BJ, 'status': 'success'}), None)
check('Canceled não conta', D.intrag_destino('NDF/Commodities', {'Client': BJ, 'Status': 'Canceled'}), None)

print('\n== 4. ponta a ponta ==')
from apps.config import DebugConfig                           # noqa: E402
from apps import create_app                                   # noqa: E402

app = create_app(DebugConfig)
app.config['TESTING'] = True
cl = app.test_client()
with cl.session_transaction() as s:
    s.update({'authenticated': True, 'user_sid': 'T000000', 'user_name': 'Tester',
              'user_role': 'ADMIN', 'session_ip': '127.0.0.1'})

from apps.pages import routes as R                            # noqa: E402
from apps.pages.platform import task_runs                     # noqa: E402

r = cl.get('/api/control-panel/intraday-tasks')
j = r.get_json() or {}
check('GET da agenda: 200', r.status_code, 200)
check('uma linha por tarefa', [t['id'] for t in j.get('tasks', [])], list(D.TASK_IDS))
r = cl.post('/api/control-panel/intraday-tasks',
            json={'tasks': {'recon-fxo': {'days': [0, 2], 'deadline': '18:30'}}})
check('POST da agenda: 200', r.status_code, 200)
fxo = [t for t in cl.get('/api/control-panel/intraday-tasks').get_json()['tasks'] if t['id'] == 'recon-fxo'][0]
check('a agenda salva volta', (fxo['days'], fxo['deadline']), ([0, 2], '18:30'))
check('tarefa desconhecida é 400',
      cl.post('/api/control-panel/intraday-tasks', json={'tasks': {'x': {}}}).status_code, 400)
cl.post('/api/control-panel/intraday-tasks', json={'tasks': {}})       # volta ao padrão

# A terça passada: a Comitente é devida, a CGD não. A Pay/Rec rodou e foi
# finalizada; a FXO não rodou.
task_runs.record('recon-payrec', 'T000000', 'Tester', '2026-09-22', {'open': 3},
                 now=datetime(2026, 9, 22, 14, 5))
task_runs.record('recon-payrec', 'T000000', 'Tester', '2026-09-22', event='end',
                 now=datetime(2026, 9, 22, 18, 0))
task_runs.record('recon-comitente', 'T000001', 'Outra', '', {'open': 0},
                 now=datetime(2026, 9, 22, 20, 45))

# Uma operação de NDF Commodities contra o Banco, importada e ainda sem B3 ID.
dia_nd = os.path.join(R.NEW_DEALS_CACHE_ROOT, 'NDF', 'Commodities', '2026', '09',
                      '20260922_ndfcomm.json')
R._atomic_write_json(dia_nd, [{'Deal': '111', 'Client': BJ, 'Status': 'New'},
                              {'Deal': '222', 'Client': 'CARGILL', 'Status': 'New'}])

snap = cl.get('/api/intraday-monitor?date=2026-09-22').get_json()
tk = {t['id']: t for t in snap['tasks']}
check('Pay/Rec feita pelo registro', tk['recon-payrec']['state'], 'done')
check('... com a hora da primeira execução', tk['recon-payrec']['ran_at'], '14:05')
check('... as quebras em aberto do registro', tk['recon-payrec']['open'], 3)
check('... e o End process como selo', tk['recon-payrec']['ended'], True)
check('Comitente devida na terça', tk['recon-comitente']['due'], True)
check('Comitente feita, mas depois do prazo', (tk['recon-comitente']['state'],
                                               tk['recon-comitente']['late_done']), ('done', True))
check('CGD não é devida na terça', tk['recon-cgd']['due'], False)
check('FXO (dia passado, não rodou) atrasada', tk['recon-fxo']['state'], 'late')
check('atividade do dia, do mais novo ao mais velho',
      [(a['task'], a['event']) for a in snap['activity']],
      [('recon-comitente', 'run'), ('recon-payrec', 'end'), ('recon-payrec', 'run')])
check('KPIs somam as devidas', snap['kpis']['due'],
      sum(1 for t in snap['tasks'] if t['due']))

intrag = [c for c in snap['cards'] if c['key'] == 'intrag-ndf'][0]
check('a operação do Banco já conta na Intrag, antes do B3 ID',
      intrag['statuses'].get(D.AWAITING_B3), 1)
check('a do cliente não', intrag['total'], 1)
check('e a Intrag fica em aberto no quadro', (tk['intrag']['total'], tk['intrag']['open']), (1, 1))

R._atomic_write_json(dia_nd, [{'Deal': '111', 'Client': BJ, 'Status': 'Success', 'B3_ID': '9'},
                              {'Deal': '222', 'Client': 'CARGILL', 'Status': 'New'}])
snap = cl.get('/api/intraday-monitor?date=2026-09-22').get_json()
intrag = [c for c in snap['cards'] if c['key'] == 'intrag-ndf'][0]
check('no Success sai daqui (quem conta é o espelho)', intrag['statuses'].get(D.AWAITING_B3), None)

print('\n== 4b. Pay/Rec só conclui no End process; a Branch Reversal ==')
from apps.pages import recon_payrec                           # noqa: E402
from apps.pages.features.deals_monitor import queries as Q    # noqa: E402
task_runs.record('recon-payrec', 'T000000', 'Tester', '2026-09-23', {'open': 1},
                 now=datetime(2026, 9, 23, 11, 0))
R._atomic_write_json(os.path.join(recon_payrec._CACHE_DIR, '2026-09-23.json'), {
    'recon_date': '2026-09-23', 'summary': [], 'settled': [], 'pending_receivement': [],
    'branch': {'has_settlement': True, 'pay_receive': 'Pay', 'reversal_net': -1564325.5},
    'pending_payment': [{'branch': 'reversal', 'status': 'Pending', 'jpm_value': -1564325.5}]})
snap = cl.get('/api/intraday-monitor?date=2026-09-23').get_json()
tk = {t['id']: t for t in snap['tasks']}
check('Pay/Rec que só RODOU não está concluído', tk['recon-payrec']['state'] != 'done', True)
check('... e anda pela metade', tk['recon-payrec']['progress'], 50)
check('Branch Reversal devida (houve liquidação da Branch)', tk['branch-reversal']['due'], True)
check('... sem rascunho: 0%', tk['branch-reversal']['progress'], 0)
check('Branch na terça 22 (sem liquidação) não é devida',
      [t for t in cl.get('/api/intraday-monitor?date=2026-09-22').get_json()['tasks']
       if t['id'] == 'branch-reversal'][0]['due'], False)
task_runs.record('branch-reversal', 'T000000', 'Tester', '2026-09-23', event='draft',
                 now=datetime(2026, 9, 23, 15, 30))
tk = {t['id']: t for t in cl.get('/api/intraday-monitor?date=2026-09-23').get_json()['tasks']}
check('rascunho do VP gerado: 50%, não concluída',
      (tk['branch-reversal']['progress'], tk['branch-reversal']['state'] != 'done',
       tk['branch-reversal']['draft_at']), (50, True, '15:30'))
tarefas, _b, _t, _k = Q._intraday_pending(datetime(2026, 9, 23))
det = {t['id']: t['detail'] for t in tarefas}
check('o e-mail diz que falta o End process', 'End process not run yet' in det.get('recon-payrec', ''), True)
check('o e-mail diz o valor e o passo da Branch',
      'Bank pays R$ 1,564,325.50' in det.get('branch-reversal', '') and 'not settled' in det['branch-reversal'], True)
R._atomic_write_json(os.path.join(recon_payrec._CACHE_DIR, '2026-09-23.json'), {
    'recon_date': '2026-09-23', 'summary': [], 'pending_payment': [], 'pending_receivement': [],
    'branch': {'has_settlement': True, 'pay_receive': 'Pay', 'reversal_net': -1564325.5},
    'settled': [{'branch': 'reversal', 'status': 'Settled', 'jpm_value': -1564325.5}]})
tk = {t['id']: t for t in cl.get('/api/intraday-monitor?date=2026-09-23').get_json()['tasks']}
check('reversão casada no Pay/Rec: concluída', tk['branch-reversal']['state'], 'done')

print('\n== 4c. o que ficou de D-1, com o link já filtrado ==')
Q._PREV_CACHE.clear()
prev = cl.get('/api/intraday-monitor?date=2026-09-23').get_json()['prev']
check('D-1 da quarta 23 é a terça 22', prev['date'], '2026-09-22')
urls = [i.get('url') for i in prev['items']]
check('a operação de registro abre o New Deals no Trade Date de D-1',
      '/new_deals-ndf-commodities?tradedate=2026-09-22' in urls, True)
check('a recon que não rodou abre na referência que ela teria (o dia útil anterior)',
      '/reconciliation-fxo?date=2026-09-21' in urls, True)
check('o Pay/Rec finalizado em D-1 não aparece', any('reconciliation-payrec' in (u or '') for u in urls), False)
check('a página carrega o leitor da data do link', 'deep-link.js' in cl.get('/intraday-monitor').data.decode('utf-8'), True)
check('a FXO abre na data do link', 'value="2026-09-01"' in cl.get('/reconciliation-fxo?date=2026-09-01').data.decode('utf-8'), True)
check('o Pay/Rec abre na data do link',
      'data-ref-date="2026-09-01"' in cl.get('/reconciliation-payrec?date=2026-09-01').data.decode('utf-8'), True)
check('data malformada é ignorada',
      'data-ref-date="x"' in cl.get('/reconciliation-payrec?date=x').data.decode('utf-8'), False)

print('\n== 4d. TODA recon é uma tarefa (e grava o registro) ==')
import inspect, re as _re                                      # noqa: E401,E402
por_url = {t['url']: t for t in D.TASKS if t['kind'] == 'recon'}
runs = [r for r in app.url_map.iter_rules() if _re.match(r'^/reconciliation-[a-z0-9-]+/run$', r.rule)]
check('há recons no url_map', len(runs) >= 5, True)
for r in runs:
    pagina = r.rule[:-len('/run')]
    tk = por_url.get(pagina)
    check('%s está no catálogo de tarefas' % pagina, bool(tk), True)
    if tk:
        fonte = inspect.getsource(app.view_functions[r.endpoint])
        check('   e o run grava task_runs.record(%r)' % tk['id'],
              "task_runs.record('%s'" % tk['id'] in fonte, True)

import io as _io                                               # noqa: E402
for _arq, _tid in (('apps/pages/features/cetip/entrypoint.py', 'save-cetip'),
                   ('apps/pages/features/conf_escalation/commands.py', 'conf-escalation')):
    _src = _io.open(os.path.join(ROOT, _arq), encoding='utf-8').read()
    check('a rotina %s grava task_runs.record' % _tid, "task_runs.record('%s'" % _tid in _src, True)

print('\n== 4d2. Save CETIP Files sem registro: o aviso do sino é o plano B ==')
# Quem salvou por uma instância sem o `task_runs.record` (outra pessoa, pull
# atrasado) só deixa o aviso "CETIP Files Saved" — a tarefa tem de fechar.
from apps.pages.features.deals_monitor import queries as _DQ0                # noqa: E402
_dia_cetip = date(2026, 9, 29)
_nc = R.get_notif_connection()
try:
    _nc.execute("INSERT INTO notifications (actor_sid, actor_name, action, page, detail, created_at) "
                "VALUES ('X1', 'Outro', 'CETIP Files Saved', 'Control Panel', "
                "'0 file(s) saved (2026-09-28)', TIMESTAMP '2026-09-29 08:05:00')")
    _nc.commit()
finally:
    _nc.close()
check('aviso com 0 arquivo não conclui', _DQ0._recon_fallback('save-cetip', _dia_cetip)[0], False)
_nc = R.get_notif_connection()
try:
    _nc.execute("INSERT INTO notifications (actor_sid, actor_name, action, page, detail, created_at) "
                "VALUES ('X1', 'Outro', 'CETIP Files Saved', 'Control Panel', "
                "'12 file(s) saved (2026-09-28)', TIMESTAMP '2026-09-29 08:31:00')")
    _nc.commit()
finally:
    _nc.close()
check('aviso com arquivo salvo conclui, na hora do aviso',
      _DQ0._recon_fallback('save-cetip', _dia_cetip)[:2], (True, '08:31'))
check('   e só no dia do aviso', _DQ0._recon_fallback('save-cetip', date(2026, 9, 30))[0], False)

print('\n== 4e. a Intrag Unwind: a recompra do fundo conta desde o IMPORT (§582) ==')
from apps.pages.features.unwinds import commands as _UC                     # noqa: E402
from apps.pages.features.deals_monitor import queries as _DQ                # noqa: E402
from apps.pages.features.intrag.infra import persistence as _IP             # noqa: E402
from apps.pages import data_store as _S                                     # noqa: E402
_L = {'AthenaID': 'D5NQ-HMNV-BCO', 'Contract': '26E02931710', 'Counterparty': 'LAWTON',
      'Result': 6321326.69, 'Direction': 'RECEIVE', 'PartyAccount': '73760009',
      'CptyAccount': '00041007', 'TradeDate': '2026-01-05', 'MaturityDate': '2026-12-15',
      'SettlementDate': '2026-09-30', 'OriginalNotional': 200000.0, 'UnwoundNotional': 100000.0,
      'UnwoundBefore': 0.0, 'UnwindDate': '2026-09-28', 'Status': 'Imported'}
with app.test_request_context():
    check('a recompra do fundo grava a Intrag', len(_UC.intrag_da_recompra([_L])), 1)
    _ref = datetime(2026, 9, 28)
    _c = next((x for x in _DQ._ndm_monitor_snapshot(_ref)[0] if x.get('key') == 'intrag-unwind'), {})
    check('   o card conta a linha no dia da recompra', (_c.get('total'), _c.get('statuses')),
          (1, {'New': 1}))
    _rows = [r for b in _DQ._ndm_pending_blocks(_ref)[0]
             for r in (b.get('rows') or []) if r.get('key') == 'intrag-unwind']
    check('   no aviso das 19h: pendente, como produto Unwind (a tela e de todos)',
          [(r['product'], r['pending']) for r in _rows], [('Unwind', 1)])
    _fp = os.path.join(_IP.INTRAG_UNWIND_CACHE_DIR, '2026', '09', '20260928_intrag_unwind.json')
    _lst = _S.read(_fp); _lst[0]['status'] = 'Sent'
    R._atomic_write_json(_fp, _lst); R._daycache_forget(_fp)
    _rows = [r for b in _DQ._ndm_pending_blocks(_ref)[0]
             for r in (b.get('rows') or []) if r.get('key') == 'intrag-unwind']
    check('   Sent na Intrag fecha a pendencia', [r['pending'] for r in _rows if r['pending']], [])

print('\n== 4f. o Termo de Resilição na zona Confirmations ==')
from apps.pages.features.unwinds.infra import persistence as _UP                # noqa: E402
_CLI = dict(_L, AthenaID='STP-TERMO-CLI', Contract='26E02931711', Counterparty='CSN MINERACAO S.A.',
            CptyAccount='73760102', Currency='USD')
_FUNDO = dict(_L, AthenaID='STP-TERMO-FDO', Contract='26E02931712', Currency='USD')
with app.test_request_context():
    _UP.upsert(datetime(2026, 9, 28), [_CLI, _FUNDO])
    _conf = _DQ._ndm_monitor_snapshot(datetime(2026, 9, 28))[1]
    _t = next((c for c in _conf if c.get('key') == 'conf-unwind-termo'), None)
    check('o card existe na zona Confirmations', bool(_t), True)
    check('   conta só a recompra contra o CLIENTE (o fundo não tem Termo)',
          (_t or {}).get('total'), 1)
    _rows = [r for b in _DQ._ndm_pending_blocks(datetime(2026, 9, 28))[0]
             for r in (b.get('rows') or []) if r.get('key') == 'conf-unwind-termo']
    check('   pendente no aviso das 19h, como Unwind · Termo de Resilição',
          [(r['product'], r['detail'], r['pending']) for r in _rows],
          [('Unwind', 'Termo de Resilição', 1)])
_html = open(os.path.join(ROOT, 'apps/templates/pages/intraday-monitor.html'), encoding='utf-8').read()
check('   a tela o desenha no bloco Unwinds', "conf: ['conf-unwind-termo']" in _html, True)

print('\n== 4g. as tarefas mensais (Swap Accrual e Swap MtM) ==')
fer = {'2026-10-12'}
check('último dia útil de setembro/2026', D.janela_mensal(('last', 1), date(2026, 9, 3), fer), [date(2026, 9, 30)])
check('1º ao 4º dia útil de outubro/2026 (pula o fim de semana)',
      D.janela_mensal(('first', 4), date(2026, 10, 20), fer),
      [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5), date(2026, 10, 6)])
cm = {'days': [0, 1, 2, 3, 4], 'deadline': '20:00'}
check('prazo no fim da janela: no 1º dia útil, à noite, ainda não atrasou',
      D.avalia(cm, date(2026, 10, 1), datetime(2026, 10, 1, 21, 0), False, False, False,
               prazo_dia=date(2026, 10, 6))['state'], 'todo')

def _tk(dia):
    return {t['id']: t for t in cl.get('/api/intraday-monitor?date=' + dia).get_json()['tasks']}

tk = _tk('2026-09-29')
check('Accrual fora do último dia útil não é devido', tk['swap-accrual']['due'], False)
check('MtM fora da janela não é devido', tk['swap-mtm']['due'], False)
task_runs.record('swap-accrual', 'T000000', 'Tester', '20260930', {'open': 2},
                 now=datetime(2026, 9, 30, 10, 0))
tk = _tk('2026-09-30')
check('Accrual devido no último dia útil', tk['swap-accrual']['due'], True)
check('... rodado (recon) mas sem End process: 50%, não concluído',
      (tk['swap-accrual']['progress'], tk['swap-accrual']['state'] != 'done'), (50, True))
task_runs.record('swap-accrual', 'T000000', 'Tester', '20260930', event='end',
                 now=datetime(2026, 9, 30, 17, 0))
check('... com o End process: concluído', _tk('2026-09-30')['swap-accrual']['state'], 'done')
tk = _tk('2026-10-01')
check('MtM devido no 1º dia útil', tk['swap-mtm']['due'], True)
check('... com o prazo no 4º dia útil', tk['swap-mtm']['deadline_at'][:10], '2026-10-06')
task_runs.record('swap-mtm', 'T000000', 'Tester', '20260930', event='end',
                 now=datetime(2026, 10, 2, 16, 0))
check('MtM ainda em aberto no 1º dia útil', _tk('2026-10-01')['swap-mtm']['state'] != 'done', True)
tk = _tk('2026-10-05')
check('End process no 2º dia útil conclui o MtM no 3º', tk['swap-mtm']['state'], 'done')
check('... dizendo o dia', tk['swap-mtm']['ended_on'], '02/10')
check('MtM depois da janela não é devido', _tk('2026-10-07')['swap-mtm']['due'], False)

print('\n== 5. o endereço antigo ==')
r = cl.get('/new-deals-monitor')
check('/new-deals-monitor redireciona', (r.status_code, r.headers.get('Location', '').endswith('/intraday-monitor')),
      (302, True))
r = cl.get('/intraday-monitor')
check('a página nova abre', r.status_code, 200)
check('com o nome novo', 'Intraday Monitor' in r.data.decode('utf-8'), True)


class _Con(object):
    def execute(self, *a):
        return self

    def fetchone(self):
        return ('["/new-deals-monitor"]', 'BO')

    def close(self):
        pass


_orig = R.get_db_connection
R.get_db_connection = lambda readonly=False: _Con()
try:
    from apps.pages.platform import authz
    check('a allowlist antiga vale para a página nova',
          '/intraday-monitor' in authz._read_user_authz('T000009')[1], True)
    _Con.fetchone = lambda self: ('["/control-panel#dealsmonitor"]', 'BO')
    check('e o card antigo do aviso vale para o card novo',
          '/control-panel#intradaytasks' in authz._read_user_authz('T000009')[1], True)
finally:
    R.get_db_connection = _orig

print('\nFALHAS: %d' % len(fails))
sys.exit(1 if fails else 0)
