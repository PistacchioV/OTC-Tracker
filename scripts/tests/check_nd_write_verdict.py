#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""New Deals: o veredito de toda gravação sai da GRAVAÇÃO (26/10/2026, §685).

A varredura de 26/10/2026 achou, nas seis telas de New Deals, o mesmo defeito
do Delete corrigido no §684 em quase todo caminho que grava: a tela pintava e o
servidor respondia `success` dizendo só QUANTOS. O que este guarda prende, no
servidor:

  1. o Save do modal de Edit numa linha JÁ ENVIADA segue a régua do Amend
     (econômico → Amend, cosmético → o status fica), e a aba velha que só
     manda status continua recusada;
  2. o PATCH devolve o status que GRAVOU;
  3. bulk-delete e bulk-patch dizem par a par o que fizeram (`done`), o que não
     acharam (`not_found`) e o que o 4-olhos recusou (`refused`);
  4. banco ocupado SOBE (503) — nos finders, no bulk e nas importações —,
     nunca vira "não achei" nem dia vazio gravado por cima;
  5. o envio confere status e 4-olhos NO SERVIDOR antes do arquivo e marca
     `Sent` no mesmo pedido; as quatro rotas usam os dois;
  6. o Mapping B3 ID só apaga o retorno que absorveu inteiro, e o NDF Comm só
     põe `Error` em quem esperava retorno;
  7. o Add Row (POST sem `_import`) não substitui a operação gravada.

Não toca em dado real: o armazém é um dicionário em memória e a pasta de
retorno um tempdir.
"""
import ast
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'
from apps.config import Config as _Cfg                      # noqa: E402
_Cfg.FOUR_EYES = True        # prova a trava da PROD (§553)

from apps.pages import routes as R                            # noqa: E402
from apps.pages import data_store as S                        # noqa: E402
from apps.pages.platform import new_deals as PND              # noqa: E402
from apps.pages.features.new_deals import entrypoint as E     # noqa: E402

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


class Troca:
    def __init__(self, *trocas):
        self.trocas, self.velhos = trocas, []

    def __enter__(self):
        for obj, nome, novo in self.trocas:
            self.velhos.append((obj, nome, getattr(obj, nome)))
            setattr(obj, nome, novo)
        return self

    def __exit__(self, *exc):
        for obj, nome, velho in reversed(self.velhos):
            setattr(obj, nome, velho)


def ocupado(*_a, **_k):
    raise S.BancoOcupado('banco de teste ocupado')


# ── O armazém em memória: um arquivo-dia por produto ─────────────────────────
DIA = '/tmp/otc-share/teste/20261026_optcomm.json'
ARMAZEM = {}
GRAVADOS = []


def ler(path, *a, **k):
    if path not in ARMAZEM:
        raise FileNotFoundError(path)
    return [dict(x) for x in ARMAZEM[path]]


def gravar(path, dados):
    ARMAZEM[path] = [dict(x) for x in dados]
    GRAVADOS.append(path)


def achar(deal, client=None):
    for i, d in enumerate(ARMAZEM.get(DIA, [])):
        if d.get('Deal', '').strip() == (deal or '').strip() and \
                (not client or d.get('Client', '').strip() == (client or '').strip()):
            return DIA, i
    return None, None


def semeia():
    ARMAZEM.clear()
    del GRAVADOS[:]
    ARMAZEM[DIA] = [
        {'Deal': 'D-SENT', 'Client': 'CLIENTE A', 'Status': 'Sent', 'TotalNotional': '1000',
         'OtherBook': 'B1', 'Acronym': 'CLA', 'Maker': 'M000001'},
        {'Deal': 'D-APPR', 'Client': 'CLIENTE B', 'Status': 'Approved', 'Maker': 'M000001'},
        {'Deal': 'D-MINE', 'Client': 'CLIENTE C', 'Status': 'Approved', 'Maker': 'T000000'},
        {'Deal': 'D-PEND', 'Client': 'CLIENTE D', 'Status': 'Pending', 'Maker': 'M000001'},
    ]


from apps import create_app                                   # noqa: E402
from apps.config import DebugConfig                           # noqa: E402
app = create_app(DebugConfig)
cl = app.test_client()
with cl.session_transaction() as s:
    s['authenticated'] = True
    s['user_sid'] = 'T000000'
    s['user_name'] = 'T'
    s['user_role'] = 'ADMIN'
    s['session_ip'] = '127.0.0.1'
    s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()

BASE = [(S, 'read', ler), (R, '_atomic_write_json', gravar),
        (R, '_find_deal_in_cache', achar), (R, '_create_notification', lambda *a, **k: None)]

# ── 1. a régua do Edit numa linha já enviada ─────────────────────────────────
print('== 1. Edit numa linha Sent/Success: a régua do Amend ==')
g = E._nd_guard_updates
upd, rec = g({'Status': 'Sent', 'TotalNotional': '1000'},
             {'Status': 'Pending', 'TotalNotional': '2000'}, 'X')
check('mudança econômica vira Amend', (rec, upd.get('Status')), ('', 'Amend'))
check('   e marca o campo em AmendChanged', upd.get('AmendChanged'), ['TotalNotional'])
upd, rec = g({'Status': 'Success', 'OtherBook': 'B1', 'B3_ID': '26X'},
             {'Status': 'Pending', 'OtherBook': 'B2'}, 'X')
check('só cosmético (Other Book): o status FICA', (rec, 'Status' in upd), ('', False))
upd, rec = g({'Status': 'Sent', 'Strike': '5.1'}, {'Status': 'Pending', 'Strike': '5.2'}, 'X',
             'fwd-start')
check('Strike do FWD Start é cosmético (produto passado)', 'Status' in upd, False)
check('aba velha só com status segue recusada',
      g({'Status': 'Sent'}, {'Status': 'Approved'}, 'X')[1], 'status_regression')
check('   e o Pending SEM campo de dado também',
      g({'Status': 'Sent'}, {'Status': 'Pending', 'Maker': 'X'}, 'X')[1], 'status_regression')

# ── 2. o PATCH devolve o que gravou ─────────────────────────────────────────
print('\n== 2. PATCH: devolve o status GRAVADO ==')
semeia()
with Troca(*BASE):
    r = cl.patch('/api/new-deals/opt-commodities/cache/D-SENT?client=CLIENTE%20A',
                 json={'Status': 'Pending', 'TotalNotional': '5000', 'Maker': 'T000000'})
    j = r.get_json() or {}
check('Edit de linha Sent responde 200 com Amend', (r.status_code, j.get('status')), (200, 'Amend'))
check('   e o banco tem o Amend e o valor novo',
      (ARMAZEM[DIA][0]['Status'], ARMAZEM[DIA][0]['TotalNotional']), ('Amend', '5000'))
semeia()
with Troca(*BASE):
    r = cl.patch('/api/new-deals/opt-commodities/cache/D-SENT?client=CLIENTE%20A',
                 json={'Status': 'Approved'})
check('aba velha: 409 e nada gravado', (r.status_code, GRAVADOS), (409, []))
with Troca(*BASE), Troca((R, '_find_deal_in_cache', ocupado)):
    r = cl.patch('/api/new-deals/opt-commodities/cache/D-APPR?client=CLIENTE%20B',
                 json={'Status': 'Approved'})
check('finder ocupado é 503, não 404 "Deal not found"', r.status_code, 503)

# ── 3. bulk dizem o QUE fizeram ─────────────────────────────────────────────
print('\n== 3. bulk-delete e bulk-patch: par a par ==')
semeia()
with Troca(*BASE):
    r = cl.post('/api/new-deals/opt-commodities/cache/bulk-delete',
                json={'pairs': [{'deal': 'D-APPR', 'client': 'CLIENTE B'},
                                {'deal': 'D-NAO', 'client': 'X'},
                                {'deal': 'D-APPR', 'client': 'OUTRO'}]})
    j = r.get_json() or {}
check('done traz só o apagado', [(x['deal'], x['client']) for x in j.get('done', [])],
      [('D-APPR', 'CLIENTE B')])
check('not_found traz os dois que não existem',
      sorted((x['deal'], x['client']) for x in j.get('not_found', [])),
      [('D-APPR', 'OUTRO'), ('D-NAO', 'X')])
check('   e só a linha pedida saiu do banco', [d['Deal'] for d in ARMAZEM[DIA]],
      ['D-SENT', 'D-MINE', 'D-PEND'])
semeia()
with Troca(*BASE), Troca((S, 'read', ocupado)):
    r = cl.post('/api/new-deals/opt-commodities/cache/bulk-delete',
                json={'pairs': [{'deal': 'D-APPR', 'client': 'CLIENTE B'}]})
check('bulk-delete com o dia ocupado: 503 e nada gravado', (r.status_code, GRAVADOS), (503, []))
semeia()
with Troca(*BASE):
    r = cl.post('/api/new-deals/opt-commodities/cache/bulk-patch', json={'patches': [
        {'deal_id': 'D-SENT', 'client': 'CLIENTE A', 'updates': {'Status': 'Approved'}},
        {'deal_id': 'D-PEND', 'client': 'CLIENTE D', 'updates': {'Status': 'Approved'}},
        {'deal_id': 'D-NAO', 'client': 'X', 'updates': {'Status': 'Approved'}}]})
    j = r.get_json() or {}
check('done com o status gravado', [(x['deal_id'], x['status']) for x in j.get('done', [])],
      [('D-PEND', 'Approved')])
check('refused traz a aba velha', [(x['deal_id'], x['error']) for x in j.get('refused', [])],
      [('D-SENT', 'status_regression')])
check('not_found traz o que não existe', [x['deal_id'] for x in j.get('not_found', [])], ['D-NAO'])

# ── 4. o envio confere e marca ──────────────────────────────────────────────
print('\n== 4. envio: conferido antes, Sent no mesmo pedido ==')
semeia()
with Troca(*BASE), app.test_request_context():
    rec = E._nd_conferir_envio(achar, [{'Deal': 'D-APPR', 'Client': 'CLIENTE B'},
                                       {'Deal': 'D-PEND', 'Client': 'CLIENTE D'},
                                       {'Deal': 'D-MINE', 'Client': 'CLIENTE C'},
                                       {'Deal': 'D-NAO', 'Client': 'X'}], 'T000000')
check('Approved de outro passa; Pending, o próprio e o inexistente são recusados',
      sorted((x['deal'], x['error']) for x in rec),
      [('D-MINE', 'same_user'), ('D-NAO', 'not_found'), ('D-PEND', 'not_sendable')])
with Troca(*BASE), app.test_request_context():
    marc, falh = E._nd_marcar_enviados(achar, [{'Deal': 'D-APPR', 'Client': 'CLIENTE B'}], 'T000000')
check('marca Sent com o Checker da sessão',
      (marc, ARMAZEM[DIA][1]['Status'], ARMAZEM[DIA][1]['Checker'], falh),
      ([{'deal': 'D-APPR', 'client': 'CLIENTE B'}], 'Sent', 'T000000', []))
semeia()
with Troca(*BASE), Troca((S, 'read', ocupado)), app.test_request_context():
    marc, falh = E._nd_marcar_enviados(achar, [{'Deal': 'D-APPR', 'Client': 'CLIENTE B'}], 'T000000')
check('status que não grava volta em status_failed (a tela avisa: não reenviar)',
      (marc, len(falh), 'BancoOcupado' in (falh[0]['reason'] if falh else '')), ([], 1, True))
SRC = open(os.path.join(ROOT, 'apps/pages/features/new_deals/entrypoint.py'), encoding='utf-8').read()
arvore = ast.parse(SRC)
for fn in ('api_fxo_send_conecta', 'api_ndf_send_conecta', 'api_send_conecta',
           'api_generic_nd_send_conecta'):
    no = next(n for n in arvore.body if isinstance(n, ast.FunctionDef) and n.name == fn)
    chamadas = {c.func.id for c in ast.walk(no) if isinstance(c, ast.Call)
                and isinstance(c.func, ast.Name)}
    check('%s confere e marca' % fn,
          {'_nd_conferir_envio', '_nd_marcar_enviados'} <= chamadas)

# ── 5. o Mapping só apaga o retorno absorvido ───────────────────────────────
print('\n== 5. Mapping B3 ID: o retorno só some quando TODO absorvido ==')
RET = tempfile.mkdtemp(prefix='otc-ret-')


def linha_ter(deal, b3):
    # a sigla mora nas posições 57-59 da LINHA (o endpoint lê line[56:59])
    return ('1;%s;X;EXECUCAO OK;' % b3).ljust(56) + 'TER' + '  ' + deal


def retorno(nome, deals):
    with open(os.path.join(RET, nome), 'w', encoding='latin-1') as fh:
        fh.write('HEADER\n' + '\n'.join(linha_ter(d, '26X%03d' % i) for i, d in enumerate(deals)))


GEN = {'D-AAAAAAAAAAAAAA1': {'Deal': 'D-AAAAAAAAAAAAAA1', 'Client': 'C', 'Status': 'Sent'}}
VAN = '/tmp/otc-share/teste/20261026_vanilla.json'


def achar_gen(cfg, deal, client=None):
    for i, d in enumerate(ARMAZEM.get(VAN, [])):
        if d.get('Deal') == deal:
            return VAN, i
    return None, None


MAP = BASE + [(R, 'RETURN_PATH', RET), (R, '_find_generic_nd_deal', achar_gen),
              (R, '_generic_nd_pc_trigger', lambda *a, **k: None),
              (R, '_generic_nd_mapping_candidates', lambda cfg, p, ref: [dict(v) for v in GEN.values()])]
semeia()
ARMAZEM[VAN] = [dict(v) for v in GEN.values()]
retorno('misto.txt', ['D-AAAAAAAAAAAAAA1', 'D-OUTRODIA00000X9'])
retorno('so_nosso.txt', ['D-AAAAAAAAAAAAAA1'])
with Troca(*MAP):
    r = cl.post('/api/new-deals/vanilla/mapping-b3', json={'ref_date': '26/10/2026'})
    j = r.get_json() or {}
check('o mapeamento gravou o Success', [(x['deal'], x['saved'], x['status']) for x in j.get('results', [])],
      [('D-AAAAAAAAAAAAAA1', True, 'Success')])
check('retorno com linha de outro dia FICA; o absorvido inteiro sai',
      sorted(os.listdir(RET)), ['misto.txt'])
semeia()
ARMAZEM[VAN] = [dict(v) for v in GEN.values()]
retorno('so_nosso.txt', ['D-AAAAAAAAAAAAAA1'])
with Troca(*MAP), Troca((R, '_atomic_write_json', ocupado)):
    r = cl.post('/api/new-deals/vanilla/mapping-b3', json={'ref_date': '26/10/2026'})
    j = r.get_json() or {}
check('gravação que falha: saved false', [x['saved'] for x in j.get('results', [])], [False])
check('   e o retorno FICA para a próxima passada', 'so_nosso.txt' in os.listdir(RET))
check('NDF Comm: Error só para quem esperava retorno (usa _ND_MAPPING_ERRORABLE)',
      '_ND_MAPPING_ERRORABLE' in ast.get_source_segment(SRC, next(
          n for n in arvore.body if isinstance(n, ast.FunctionDef) and n.name == 'api_ndf_mapping_b3')))
shutil.rmtree(RET, ignore_errors=True)

# ── 6. finders, importação e Add Row ────────────────────────────────────────
print('\n== 6. finders estritos, importação e Add Row ==')
with Troca((R, '_day_json', lambda fp, mt, sz, strict=False, **k: ocupado() if strict else [])), \
     Troca((PND, '_optcomm_file_list', lambda: [(DIA, 1, 1)])):
    try:
        PND._find_deal_in_cache('D-APPR', 'CLIENTE B')
        check('finder com o dia ocupado LEVANTA', False)
    except S.BancoOcupado:
        check('finder com o dia ocupado LEVANTA', True)
semeia()
with Troca((S, 'read', ocupado), (R, '_atomic_write_json', gravar)):
    try:
        PND._generic_nd_persist_new_deals('vanilla', [{'Deal': 'N1', 'Client': 'C',
                                                      'TradeDate': '26/10/2026'}])
        check('import da API com o dia ocupado LEVANTA (não grava o dia só com o novo)', False)
    except S.BancoOcupado:
        check('import da API com o dia ocupado LEVANTA (não grava o dia só com o novo)', GRAVADOS == [])
semeia()
POST_DIA = os.path.join(R.CACHE_BASE_DIR, '2026', '10', '20261026_optcomm.json')
ARMAZEM[POST_DIA] = [dict(ARMAZEM[DIA][0])]
with Troca(*BASE), Troca((S, 'exists', lambda p: p in ARMAZEM)):
    r = cl.post('/api/new-deals/opt-commodities/cache',
                json={'Deal': 'D-SENT', 'Client': 'CLIENTE A', 'TradeDate': '26/10/2026',
                      'Status': 'Pending'})
check('Add Row de operação gravada: 409 deal_exists e nada substituído',
      (r.status_code, (r.get_json() or {}).get('error'), ARMAZEM[POST_DIA][0]['Status']),
      (409, 'deal_exists', 'Sent'))

print()
if fails:
    print('%d FALHA(S)' % len(fails))
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('TUDO OK')
