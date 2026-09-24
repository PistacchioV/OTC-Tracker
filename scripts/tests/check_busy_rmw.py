#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_busy_rmw.py — banco OCUPADO nunca vira "vazio" antes de uma gravação.

Varredura de 23/09/2026: vários ler → alterar → gravar liam a falha de leitura
(`BancoOcupado`, a instância vizinha com a trava) como "não há dado" e gravavam
por cima — o mesmo desenho do `_cpd_load` (§436). O que este script prende:

  1. tickets: `create` com o store ocupado LEVANTA e não grava (antes gravava
     um ticket só por cima de todos, reusando o id -0001);
  2. Operations B3 / OTM: a leitura de quem grava (`_day_records_for_write`)
     levanta no ocupado; a rota de linha responde 503 sem gravar; o import
     (`_opb3_side_write`) não grava o dia só com a fonte nova;
  3. `_mapping_rows`: ocupado SOBE (nunca o seed com 200); a API GET responde
     503; outra falha devolve o seed aos consumidores mas sobe no `strict`;
  4. Pending Confirmation: `_pc_save_from_deal` numa operação que JÁ EXISTE
     preserva o que a mesa preencheu; `_pc_upsert_rows` com a gravação do
     DESTINO falhando não apaga a linha dos outros bancos, e levanta.
  5. esteira: MO e FO validando a partir da MESMA leitura não se apagam
     (`save_changes`/`mutate_row` releem sob a trava); `upsert_row` levanta
     quando a gravação falha; o `mark_validated` fora do prazo sem motivo
     desfaz a transação inteira;
  6. Pay/Rec: o Justify levanta quando a gravação falha (antes: sucesso na
     tela, Pending no reload) e o End process não diz "rode a recon" quando o
     banco está ocupado;
  7. caches: a primeira carga do ANBIMA com o carimbo ilegível não CONGELA o
     calendário; o RefData ilegível não vira índice vazio sob o carimbo; a
     gravação limpa a marca de OCUPADO do próprio banco.
  8. autorização e maker-checker no SERVIDOR: POST de mapping sem a página é
     403; o `swap-index` gravado pelo /mapping entra PENDING (e o que está
     PENDING/INACTIVE não vale); o PATCH do New Deals não deixa o Maker aprovar
     o próprio Pending nem uma aba velha desfazer um Sent, e o Maker é o da
     sessão; MO/FO não assinam antes do OTC; o Delete da esteira recusa linha
     com carimbo; o Onboarding recusa escrita depois de uma reimportação (o
     `_id` já seria de outro CGD) e diz quando o `_id` não existe; a lista de
     datas do Latam não guarda a varredura de antes de um esquecimento; o
     índice de contas do Live Position acompanha o `b3-accounts`; e gerar uma
     confirmação esquece a listagem das pastas do Monitor.

Roda com bancos em tempfile; não toca em dado real.
"""
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
from apps.config import Config as _Cfg                      # noqa: E402
_Cfg.FOUR_EYES = True   # prova a trava da PROD; na dev o maker/checker e desligado (§553)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

from apps.pages import routes as R                            # noqa: E402
from apps.pages import data_store as S                        # noqa: E402
from apps.pages import duck_read                              # noqa: E402
from apps.pages import otc_tickets                            # noqa: E402
from apps.pages.platform import operations_b3 as OPB3         # noqa: E402
from apps.pages.platform import pending_confirmation as PC    # noqa: E402

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def ocupado(*_a, **_k):
    raise S.BancoOcupado('banco de teste ocupado')


class Troca:
    """Troca atributos e devolve no fim (o `with` desfaz mesmo com falha)."""

    def __init__(self, *trocas):
        self.trocas = trocas
        self.velhos = []

    def __enter__(self):
        for obj, nome, novo in self.trocas:
            self.velhos.append((obj, nome, getattr(obj, nome)))
            setattr(obj, nome, novo)
        return self

    def __exit__(self, *exc):
        for obj, nome, velho in reversed(self.velhos):
            setattr(obj, nome, velho)


def levanta(fn, *a, **k):
    try:
        fn(*a, **k)
    except S.BancoOcupado:
        return True
    except Exception as exc:                                  # noqa: BLE001
        return 'outra: %r' % exc
    return False


from apps import create_app                                   # noqa: E402
from apps.config import DebugConfig                           # noqa: E402

app = create_app(DebugConfig)
cl = app.test_client()
with cl.session_transaction() as s:
    s['authenticated'] = True
    s['user_sid'] = 'T000000'
    s['user_name'] = 'T'
    s['user_role'] = 'ADMIN'
    s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()

# ── 1. tickets ──────────────────────────────────────────────────────────────
print('== 1. tickets: ocupado não vira store vazio ==')
gravou = []
with Troca((S, 'read', ocupado), (otc_tickets, '_atomic_write', lambda p, d: gravou.append(d))):
    check('create com o store ocupado LEVANTA',
          levanta(otc_tickets.create, 'T000000', 'T', 't@x', 'assunto', 'Low', [], 'desc', 'BO'))
    check('e não grava nada', gravou, [])

# ── 2. Operations B3 / OTM ─────────────────────────────────────────────────
print('\n== 2. Operations B3 / OTM ==')
with Troca((S, 'isfile', lambda p: True), (S, 'read', ocupado)):
    check('_day_records_for_write levanta no ocupado',
          levanta(R._day_records_for_write, '/x/dia.json', lambda d: False))
with Troca((S, 'isfile', lambda p: False)):
    check('_day_records_for_write: dia ausente é None',
          R._day_records_for_write('/x/dia.json', lambda d: False), None)

gravou = []
with Troca((S, 'isfile', lambda p: True), (S, 'read', ocupado),
           (R, '_atomic_write_json', lambda p, d: gravou.append(p))):
    check('import (_opb3_side_write) levanta no ocupado',
          levanta(OPB3._opb3_side_write, [], b'', datetime(2026, 9, 23), 'operacoes'))
    check('e não grava o dia só com a fonte nova', gravou, [])

salvou = []
with Troca((R, '_opb3_load_for_write', ocupado), (R, '_otm_load_for_write', ocupado),
           (R, '_otm_save', lambda jp, d: salvou.append(jp))):
    for url in ('/api/operations-b3/row/add', '/api/operations-b3/row/edit',
                '/api/operations-b3/row/delete', '/api/operations-b3/row/confirm',
                '/api/otm-settlements/row/add', '/api/otm-settlements/row/edit',
                '/api/otm-settlements/row/delete', '/api/otm-settlements/row/confirm'):
        r = cl.post(url, json={'id': 'x', 'cells': ['a'], 'date': '2026-09-23'})
        check('%s responde 503 no ocupado' % url, r.status_code, 503)
    check('nenhuma rota de linha gravou', salvou, [])

# ── 3. _mapping_rows ────────────────────────────────────────────────────────
print('\n== 3. _mapping_rows ==')
KEY = 'b3-accounts'
R._mapping_cache.pop(KEY, None)
with Troca((S, 'isfile', lambda p: True), (S, 'getmtime', lambda p: 123.0),
           (S, 'read', ocupado), (duck_read, 'dataset_records', ocupado)):
    check('ocupado SOBE (não é o seed)', levanta(R._mapping_rows, KEY))
    r = cl.get('/api/mappings/' + KEY)
    check('GET /api/mappings responde 503', r.status_code, 503)
    check('   com database_busy', (r.get_json() or {}).get('error'), 'database_busy')


def quebrado(*_a, **_k):
    raise ValueError('conteúdo ilegível')


R._mapping_cache.pop(KEY, None)
with Troca((S, 'isfile', lambda p: True), (S, 'getmtime', lambda p: 124.0),
           (S, 'read', quebrado), (duck_read, 'dataset_records', quebrado)):
    seed = list(R._MAPPING_DEFS[KEY].get('seed') or [])
    check('outra falha: consumidor segue com o seed', R._mapping_rows(KEY), seed)
    try:
        R._mapping_rows(KEY, strict=True)
        check('strict levanta na outra falha', False)
    except ValueError:
        check('strict levanta na outra falha', True)
    r = cl.get('/api/mappings/' + KEY)
    check('GET da tela NÃO serve o seed com 200', r.status_code != 200)
R._mapping_cache.pop(KEY, None)

# ── 4. Pending Confirmation ────────────────────────────────────────────────
print('\n== 4. Pending Confirmation ==')
tmp = tempfile.mkdtemp(prefix='otc-busy-rmw-')
velho_dir = R._PC_DB_DIR
R._PC_DB_DIR = tmp
try:
    hoje = datetime.now().strftime('%d/%m/%Y')
    PC._pc_upsert_rows([{
        'Trade Number': 'TN1', 'Client': 'CLIENTE VELHO', 'Trade Date': hoje,
        'Pending Status': 'Pending Original', 'EA': 'Sim', 'Comments': 'da mesa',
        'FepWeb ID': 'FW-9', 'Break Reason': 'motivo', 'Pendência': 'p1'}])

    deal = {'Deal': 'TN1', 'Client': 'CLIENTE NOVO', 'SPN': '123',
            'TradeDate': datetime.now().strftime('%Y-%m-%d'),
            'SettlementDate': (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')}
    with Troca((PC, '_pc_is_internal_counterparty', lambda *a: False),
               (PC, '_pc_banker_for_spn', lambda spn: 'BANKER'),
               (PC, '_pc_refdata_enrich', lambda row: None),
               (R, '_mc_save_from_deal', lambda *a, **k: None)):
        PC._pc_save_from_deal(deal, 'NDF VANILLA')
    linha = PC._pc_find_row('TN1') or {}
    check('remapeamento preserva o Pending Status da mesa',
          linha.get('Pending Status'), 'Pending Original')
    for c, v in (('EA', 'Sim'), ('Comments', 'da mesa'), ('FepWeb ID', 'FW-9'),
                 ('Break Reason', 'motivo'), ('Pendência', 'p1')):
        check('   e o %s' % c, linha.get(c), v)
    check('   o que é do DEAL é atualizado (Client)', linha.get('Client'), 'CLIENTE NOVO')
    check('   e o vazio da mesa se preenche (Owner)', linha.get('Owner'), 'BANKER')

    # A linha vai para OK; a gravação do destino falha → ela NÃO some.
    orig = PC._pc_write_exec

    def falha_no_ok(cat, ops, raise_errors=False):
        if cat == 'ok':
            if raise_errors:
                raise S.BancoOcupado('ok ocupado')
            return False
        return orig(cat, ops, raise_errors=raise_errors)

    mover = dict(linha)
    mover['Pending Status'] = 'Exception FepWeb'        # resolvido → balde ok
    alvo = PC._pc_target_category(dict(mover))
    check('o caso de teste MUDA de balde (pending → ok)', alvo, 'ok')
    with Troca((PC, '_pc_write_exec', falha_no_ok)):
        check('upsert com o destino (%s) ocupado LEVANTA' % alvo,
              levanta(PC._pc_upsert_rows, [mover]))
    ainda = [r for cat in ('backlog', 'pending', 'ok')
             for r in R._pc_load_rows(cat) if r.get('Trade Number') == 'TN1']
    check('   e a linha NÃO sumiu dos três bancos', len(ainda), 1)

    # Sem falha, a mudança de balde continua: uma linha só, no destino.
    PC._pc_upsert_rows([dict(mover)])
    onde = [cat for cat in ('backlog', 'pending', 'ok')
            for r in R._pc_load_rows(cat) if r.get('Trade Number') == 'TN1']
    check('upsert normal move a linha e não duplica', onde, [alvo])
finally:
    R._PC_DB_DIR = velho_dir
    shutil.rmtree(tmp, ignore_errors=True)

# ── 5. esteira ─────────────────────────────────────────────────────────────
print('\n== 5. esteira: validações em paralelo e falha que sobe ==')
from apps.pages import manual_conf as M                       # noqa: E402
M._DB_DIR = tempfile.mkdtemp(prefix='otc-busy-mc-')
M._ENSURED.clear()
BASE = {'Trade ID': 'EST-1', 'Produto': 'SWAP', 'LOB': 'EDG', 'Cliente': 'C',
        'Data Operação': datetime.now().strftime('%d/%m/%Y'), 'Notional': '1',
        'Conferido OTC': datetime.now().strftime('%d/%m/%Y')}
M.upsert_row(M.blank_row(**BASE))
lida = M.find_row('EST-1')                   # as DUAS mesas abriram a mesma linha
mo = dict(lida, **{'VALIDADO p/ MO': '23/09/2026', 'Time Stamp MO': 'MO 1'})
fo = dict(lida, **{'VALIDADO p/ FO': '23/09/2026', 'Time Stamp FO': 'FO 1'})
M.save_changes(lida, mo)
M.save_changes(lida, fo)                     # a cópia do FO tem o MO vazio
final = M.find_row('EST-1') or {}
check('a validação do MO sobrevive à gravação do FO', final.get('VALIDADO p/ MO'), '23/09/2026')
check('   e a do FO está lá', final.get('VALIDADO p/ FO'), '23/09/2026')

def _escrita_falha(*_a, **_k):
    raise S.BancoOcupado('esteira ocupada')

with Troca((M, 'duckdb_write', _escrita_falha)):
    check('upsert_row com a gravação falhando LEVANTA',
          levanta(M.upsert_row, dict(final, Cliente='OUTRO')))
check('   e a linha continua como estava', (M.find_row('EST-1') or {}).get('Cliente'), 'C')

M.upsert_row(M.blank_row(**dict(BASE, **{'Trade ID': 'EST-3'})))   # OTC feito, MO pendente
with Troca((M, 'sla_breached', lambda row, stage: True)):
    try:
        M.mark_validated('EST-3', M.STAGE_MO, 'X', comment='')
        check('mark_validated fora do prazo sem motivo recusa', False)
    except M.SlaCommentRequired:
        check('mark_validated fora do prazo sem motivo recusa', True)
check('   e nada foi gravado (a transação desfez)',
      (M.find_row('EST-3') or {}).get('VALIDADO p/ MO'), '')
check('validar de novo uma etapa já validada não troca o carimbo',
      (M.mark_validated('EST-1', M.STAGE_MO, 'OUTRA') or {}).get('Time Stamp MO'), 'MO 1')

# ── 6. Pay/Rec ──────────────────────────────────────────────────────────────
print('\n== 6. Pay/Rec ==')
from apps.pages import recon_payrec as PR                     # noqa: E402
dia = {'summary': [1], 'pending_payment': [{'status': 'Pending', 'comment': ''}],
       'pending_receivement': []}
with Troca((PR, '_load_flat', lambda d, strict=False: {k: (list(v) if isinstance(v, list) else v)
                                                        for k, v in dia.items()}),
           (R, '_atomic_write_json', ocupado)):
    check('Justify com a gravação falhando LEVANTA (não responde sucesso)',
          levanta(PR.justify_row, '2026-09-23', 'pay', 0, 'motivo'))
with Troca((S, 'exists', lambda p: True), (S, 'read', ocupado)):
    check('End process com o banco ocupado LEVANTA (não é "rode a recon")',
          levanta(PR.finalize_history, '2026-09-23'))

# ── 7. caches ───────────────────────────────────────────────────────────────
print('\n== 7. caches ==')
from apps.pages.platform import anbima as AN                  # noqa: E402
salvo = (AN._ANBIMA_HOLIDAYS, AN._anbima_loaded, AN._anbima_mtime,
         AN._anbima_hols_cache, AN._anbima_hols_mtime)
try:
    AN._ANBIMA_HOLIDAYS, AN._anbima_loaded, AN._anbima_mtime = set(), False, None
    AN._anbima_hols_cache, AN._anbima_hols_mtime = None, None
    carimbos = [None, 10.0]                  # 1ª carga: carimbo ilegível (ocupado)
    with Troca((AN, '_anbima_stamp', lambda: carimbos[0]),
               (duck_read, 'dataset_rows', lambda p: [{'date': '2026-09-07'}])):
        AN._load_anbima()
        check('1ª carga sem carimbo NÃO marca "fixado à mão"', AN._anbima_loaded, False)
        AN._anbima_holidays()
        check('   nem o cache dos feriados', AN._anbima_hols_cache, None)
        carimbos[0] = 10.0
        AN._load_anbima()
        check('a carga seguinte carrega de verdade',
              (AN._anbima_loaded, AN._anbima_mtime, '2026-09-07' in AN._ANBIMA_HOLIDAYS),
              (True, 10.0, True))
        check('   e o cache dos feriados também', '2026-09-07' in AN._anbima_holidays())
    carimbos[0] = 11.0                       # o arquivo mudou, e a leitura falha
    with Troca((AN, '_anbima_stamp', lambda: carimbos[0]),
               (duck_read, 'dataset_rows', ocupado)):
        AN._load_anbima()
        check('leitura falha com calendário carregado MANTÉM os feriados',
              '2026-09-07' in AN._ANBIMA_HOLIDAYS)
        check('   (o conjunto do _anbima_holidays também)', '2026-09-07' in AN._anbima_holidays())
finally:
    (AN._ANBIMA_HOLIDAYS, AN._anbima_loaded, AN._anbima_mtime,
     AN._anbima_hols_cache, AN._anbima_hols_mtime) = salvo

velho = dict(R._REFDATA_TAXID_CACHE)
try:
    R._REFDATA_TAXID_CACHE.update(mtime=1.0, map={'123': 'CLIENTE'})
    with app.test_request_context('/'):
        with Troca((S, 'getmtime', lambda p: 2.0), (duck_read, 'refdata_rows', ocupado),
                   (S, 'read', ocupado)):
            check('RefData ilegível não vira índice vazio', R._refdata_by_taxid(), {'123': 'CLIENTE'})
    check('   e o carimbo novo NÃO foi guardado com a falha', R._REFDATA_TAXID_CACHE['mtime'], 1.0)
finally:
    R._REFDATA_TAXID_CACHE.clear(); R._REFDATA_TAXID_CACHE.update(velho)

DBX = '/x/banco.db'
S._ocupado_marca(DBX)
S._after_write(DBX, '/x/banco.json', 'banco.json')
check('a gravação limpa a marca de OCUPADO do próprio banco', S._ocupado_marcado(DBX), False)

# ── 8. autorização, maker-checker e caches menores ─────────────────────────
print('\n== 8. autorização e maker-checker no servidor ==')
with Troca((R, '_user_can_access_page', lambda url: False)):
    r = cl.post('/api/mappings/b3-accounts', json={'rows': []})
    check('POST de mapping sem a página /mapping é 403', r.status_code, 403)

from apps.pages.features.mapping import entrypoint as MAPE     # noqa: E402
atuais = [{'STATUS': 'ACTIVE', 'Codigo Referencia Externa': 'C01', 'Nome Curva': 'A',
           'Nome Categoria': 'X', 'MAKER': 'M1', 'CHECKER': 'C1'},
          {'STATUS': 'ACTIVE', 'Codigo Referencia Externa': 'C02', 'Nome Curva': 'B',
           'Nome Categoria': 'X', 'MAKER': 'M1', 'CHECKER': 'C1'}]
cols = [c['key'] for c in R._MAPPING_DEFS['swap-index']['columns']]
novas = [{'STATUS': 'ACTIVE', 'Codigo Referencia Externa': 'C01', 'Nome Curva': 'A',
          'Nome Categoria': 'X', 'MAKER': '', 'CHECKER': ''},            # igual
         {'STATUS': 'ACTIVE', 'Codigo Referencia Externa': 'C03', 'Nome Curva': 'NOVA',
          'Nome Categoria': 'X', 'MAKER': '', 'CHECKER': 'EU'}]          # nova, "ACTIVE"
with Troca((R, '_mapping_rows', lambda key, *a, **k: [dict(x) for x in atuais])):
    out = {x['Codigo Referencia Externa']: x for x in
           MAPE._maker_checker_rows('swap-index', 'Codigo Referencia Externa', cols,
                                    [dict(x) for x in novas], 'T000000')}
check('swap-index: linha igual mantém o STATUS/CHECKER gravados',
      (out['C01']['STATUS'], out['C01']['CHECKER']), ('ACTIVE', 'C1'))
check('   linha nova entra PENDING com a sessão como Maker (não o ACTIVE da tela)',
      (out['C03']['STATUS'], out['C03']['MAKER'], out['C03']['CHECKER']),
      ('PENDING', 'T000000', ''))
check('   linha removida vira PENDING DELETE, não some', out['C02']['STATUS'], 'PENDING DELETE')
with Troca((R, '_mapping_rows', lambda key, *a, **k: list(out.values()))):
    idx = R._swapindex_lookup()
check('PENDING não vale na leitura; PENDING DELETE vale até aprovado',
      ('C03' in idx, 'C02' in idx, 'C01' in idx), (False, True, True))

from apps.pages.features.new_deals import entrypoint as NDE    # noqa: E402
g = NDE._nd_guard_updates
check('New Deals: Pending → Approved pelo próprio Maker é recusado',
      g({'Status': 'Pending', 'Maker': 'A000001'}, {'Status': 'Approved'}, 'a000001')[1], 'same_user')
check('   por outro usuário passa', g({'Status': 'Pending', 'Maker': 'A000001'},
                                      {'Status': 'Approved'}, 'B000002')[1], '')
check('   New → Approved segue livre (§540)', g({'Status': 'New', 'Maker': 'A000001'},
                                                {'Status': 'Approved'}, 'A000001')[1], '')
check('   aba velha não desfaz um Sent', g({'Status': 'Sent'}, {'Status': 'Approved'}, 'X')[1],
      'status_regression')
check('   Amend continua passando', g({'Status': 'Success'}, {'Status': 'Amend'}, 'X')[1], '')
check('   o Maker é o da SESSÃO, não o do corpo',
      g({'Status': 'New'}, {'Maker': 'OUTRO'}, 'B000002')[0]['Maker'], 'B000002')

M.upsert_row(M.blank_row(**{'Trade ID': 'EST-2', 'Produto': 'SWAP', 'LOB': 'EDG',
                             'Cliente': 'C', 'Data Operação': datetime.now().strftime('%d/%m/%Y'),
                             'Notional': '1'}))
try:
    M.mark_validated('EST-2', M.STAGE_MO, 'X')
    check('MO não assina antes do OTC', False)
except M.StageNotPending:
    check('MO não assina antes do OTC', True)
r = cl.post('/api/manual-confirmation/delete', json={'keys': ['EST-1']})
check('Delete da esteira recusa linha com carimbo (409)', r.status_code, 409)
check('   e ela continua lá', M.find_row('EST-1') is not None)
r = cl.post('/api/manual-confirmation/delete', json={'keys': ['EST-2']})
check('   linha intocada apaga', (r.status_code, M.find_row('EST-2')), (200, None))

print('\n== 8b. Onboarding: a geração da importação ==')
from apps.pages import cgd_docs as CG                          # noqa: E402
CGP = os.path.join(tempfile.mkdtemp(prefix='otc-busy-cgd-'), 'cgd.db')
CG.replace_all([{'Razão Social': 'EMPRESA A'}, {'Razão Social': 'EMPRESA B'}], path=CGP)
gen1 = CG.generation(CGP)
check('a importação grava uma geração', bool(gen1))
check('escrita com a geração em vigor grava', CG.update_row('1', {'Status': 'Active'}, path=CGP, gen=gen1), 1)
import time as _t; _t.sleep(0.01)
CG.replace_all([{'Razão Social': 'EMPRESA B'}], path=CGP)       # reimportou: o _id 1 é OUTRO
try:
    CG.update_row('1', {'Status': 'Cancelled'}, path=CGP, gen=gen1)
    check('escrita com a geração VELHA é recusada', False)
except CG.Reimportado:
    check('escrita com a geração VELHA é recusada', True)
try:
    CG.delete_row('1', path=CGP, gen=gen1)
    check('   o delete também', False)
except CG.Reimportado:
    check('   o delete também', True)
check('   e o documento que herdou o _id 1 está intacto',
      [(r['Razão Social'], r['Status']) for r in CG.load_all(CGP)], [('EMPRESA B', '')])
check('_id que não existe devolve 0 (não "1" fixo)',
      CG.update_row('99', {'Status': 'Active'}, path=CGP, gen=CG.generation(CGP)), 0)

print('\n== 8c. caches menores ==')
chamou = []
def _dias_com_esquecimento(root, suf):
    R._latam_dates_forget()               # um import no MEIO da varredura
    chamou.append(1)
    return []
R._latam_dates_forget()
with Troca((S, 'isdir', lambda p: True), (R, '_day_files', _dias_com_esquecimento)):
    R._latam_all_dates()
check('Latam: varredura de antes do esquecimento não é guardada',
      (bool(chamou), R._latam_dates_memo['dates']), (True, None))

base = {'x': 'y'}
rows = [{'B3 ACCOUNT': '11111.00-1', 'COUNTERPARTY': 'CLIENTE'}]
omni = {'v': set()}
contas = {'v': []}
with Troca((R, '_refdata_by_taxid', lambda: base), (R, '_refdata_records', lambda: rows),
           (R, '_mapping_rows', lambda key, *a, **k: contas['v']),
           (R, '_b3_is_omnibus', lambda acc: acc in omni['v'])):
    R._LP_ACCOUNT_NAME_CACHE.update(src=None, map=None)
    antes = dict(R._lp_account_names())
    omni['v'] = {'11111001'}; contas['v'] = [{'mudou': True}]   # conta virou guarda-chuva
    depois = dict(R._lp_account_names())
check('Live Position: marcar guarda-chuva no b3-accounts vale sem mexer no RefData',
      ('11111001' in antes, '11111001' in depois), (True, False))
R._LP_ACCOUNT_NAME_CACHE.update(src=None, map=None)

from apps.pages.platform import manual_confirmation as PMC      # noqa: E402
PMC._MC_DOCS_CACHE['/pasta'] = (1e18, ['velho.pdf'])
with Troca((PMC, '_mc_conf_trade_keys', lambda picked, product: [])):
    PMC._mc_stamp_generated([], 'ndf-comm')
check('gerar a confirmação esquece a listagem das pastas do Monitor',
      '/pasta' in PMC._MC_DOCS_CACHE, False)

print()
if fails:
    print('FAILED: %d check(s)' % len(fails))
    sys.exit(1)
print('TUDO OK')
sys.exit(0)
