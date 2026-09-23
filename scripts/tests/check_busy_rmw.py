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

Roda com bancos em tempfile; não toca em dado real.
"""
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
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

print()
if fails:
    print('FAILED: %d check(s)' % len(fails))
    sys.exit(1)
print('TUDO OK')
sys.exit(0)
