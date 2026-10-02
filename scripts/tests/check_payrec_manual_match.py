"""Pay/Rec: match manual de débito(s) × crédito(s) da mesma contraparte.

A mesa marca linhas do Pending Payment (débito, negativo) e do Pending
Receivement (crédito, positivo) que o motor não casou, e o botão Match as move
para o Settled — desde que:

  * haja ao menos uma de cada lado;
  * todas sejam da MESMA contraparte (pela chave `_cpty_key`, então
    `SUZANO SA` e `SUZANO S.A.` são uma só);
  * a soma débito + crédito fique dentro da tolerância;
  * nenhuma tenha os dois lados preenchidos (essa o motor já casou).

E o match sobrevive a um novo Run: o Run refaz o dia do zero, e o grupo é
reaplicado do arquivo `manual-matches/<data>.json`.

Não encosta em dado real: o armazém e o `routes` são stubs em memória.
"""
import os
import sys
import tempfile
import threading
import types

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

import apps.pages as P                                          # noqa: E402
from apps.pages import recon_payrec as RP                       # noqa: E402

fails = []


def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


# ── stubs: armazém e routes em memória ───────────────────────────────────────
MEM = {}


class _Store:
    @staticmethod
    def exists(p):
        return p in MEM

    @staticmethod
    def read(p):
        import copy
        if p not in MEM:
            raise FileNotFoundError(p)
        return copy.deepcopy(MEM[p])

    @staticmethod
    def isdir(p):
        return True


def _write(p, payload):
    import copy
    MEM[p] = copy.deepcopy(payload)


fake_routes = types.SimpleNamespace(_cache_lock=threading.Lock(), _atomic_write_json=_write)
sys.modules['apps.pages.routes'] = fake_routes
P.routes = fake_routes
RP._store = _Store
_orig_makedirs = os.makedirs
os.makedirs = lambda *a, **k: None

DATE = '2026-10-02'


def _row(pr, jpm_cpty='', client='', jv='', cv='', status='Pending'):
    return {'le': 'JPM', 'product': 'NDF', 'jpm_cpty': jpm_cpty, 'client': client,
            'pay_receive': pr, 'jpm_value': jv, 'client_value': cv, 'sistema': '',
            'snumconta': '', 'status': status, 'difference': 0}


def _seed():
    MEM.clear()
    data = {'success': True, 'summary': [], 'settled': [],
            'pending_payment': [
                _row('Pay', jpm_cpty='SUZANO SA', jv=-1000.00),              # 0
                _row('Pay', client='SUZANO S.A.', cv=-500.40),               # 1
                _row('Pay', jpm_cpty='VALE SA', jv=-300.00),                 # 2
                _row('Pay', jpm_cpty='SUZANO SA', client='SUZANO SA',        # 3 casada pelo motor
                     jv=-10.0, cv=-15.0),
            ],
            'pending_receivement': [
                _row('Receive', client='SUZANO SA', cv=1500.00),             # 0
                _row('Receive', jpm_cpty='VALE SA', jv=900.00),              # 1
            ]}
    RP._persist(DATE, data, strict=True)
    return data


def _err(fn):
    try:
        fn()
    except RP.ManualMatchError as e:
        return e.code
    return None


# 1 · recusas
_seed()
check(_err(lambda: RP.manual_match(DATE, [0], [])) == 'match_need_two', 'uma linha só → match_need_two')
check(_err(lambda: RP.manual_match(DATE, [2], [0])) == 'match_cpty_differs', 'VALE × SUZANO → match_cpty_differs')
check(_err(lambda: RP.manual_match(DATE, [0], [0])) == 'match_over_tolerance',
      '-1000 + 1500 = 500 → match_over_tolerance')
check(_err(lambda: RP.manual_match(DATE, [3], [0])) == 'match_already_matched',
      'linha com os dois lados → match_already_matched')
check(_err(lambda: RP.manual_match(DATE, [9], [0])) == 'match_row_missing', 'índice fora → match_row_missing')
check(_err(lambda: RP.manual_match('2026-01-01', [0], [0])) == 'match_no_recon', 'dia sem recon → match_no_recon')
check(not any(k.endswith('manual-matches/' + DATE + '.json') for k in MEM),
      'recusa não grava grupo nenhum')

# 2 · vários débitos × um crédito, mesma contraparte por chave, dentro da tolerância
data, group = RP.manual_match(DATE, [0, 1], [0], user='Tester', sid='E000001')
check(abs(group['net'] - (-0.40)) < 1e-9, 'soma -1000 - 500,40 + 1500 = -0,40')
check(len(data['pending_payment']) == 2 and len(data['pending_receivement']) == 1,
      'as três linhas saem das pendências')
manual = [r for r in data['settled'] if r.get('manual_match') == group['id']]
check(len(manual) == 3 and all(r['status'] == 'Settled' for r in manual), 'e entram no Settled como Settled')
check(all(r.get('matched_by') == 'Tester' for r in manual), 'com quem casou')
saved = RP._load_flat(DATE, strict=True)
check(len(saved['settled']) == 3, 'o resultado do dia foi regravado')

# 3 · o grupo sobrevive a um novo Run (reaplicado sobre as pendências recalculadas)
fresh = _seed()   # o Run regrava o dia do zero; o arquivo dos matches não é tocado pelo Run
MEM[RP._manual_path(DATE)] = {'groups': [group]}
pp, pr, st = fresh['pending_payment'], fresh['pending_receivement'], fresh['settled']
n = RP._apply_manual_matches(DATE, pp, pr, st)
check(n == 1 and len(pp) == 2 and len(pr) == 1 and len(st) == 3, 'Run seguinte reaplica o match')

# 4 · grupo cujas linhas sumiram não é aplicado pela metade
fresh = _seed()
fresh['pending_receivement'].pop(0)
MEM[RP._manual_path(DATE)] = {'groups': [group]}
pp, pr, st = fresh['pending_payment'], fresh['pending_receivement'], fresh['settled']
n = RP._apply_manual_matches(DATE, pp, pr, st)
check(n == 0 and len(pp) == 4 and not st, 'linha ausente → grupo não aplicado e nada se move')

# 5 · pernas JPM × perna Client do MESMO lado (§623): duas JPM no Pending
# Payment contra uma Client no Pending Payment, Σ JPM = Σ Client. Era o caso
# que o botão nem habilitava — só aceitava débito × crédito.
MEM.clear()
RP._persist(DATE, {'success': True, 'summary': [], 'settled': [], 'pending_receivement': [],
                   'pending_payment': [
                       _row('Pay', jpm_cpty='LAWTON MULTIMERCADO EXCLUSIVO', jv=-298394195.14),  # 0
                       _row('Pay', jpm_cpty='LAWTON MULTIMERCADO EXCLUSIVO', jv=-96882517.44),   # 1
                       _row('Pay', client='LAWTON MULTIMERCADO EXCLUSIVO', cv=-395276712.58),    # 2
                       _row('Pay', client='LAWTON MULTIMERCADO EXCLUSIVO', cv=-136927600.63),    # 3
                   ]}, strict=True)
check(_err(lambda: RP.manual_match(DATE, [0, 1, 3], [])) == 'match_over_tolerance',
      'JPM 395,3 mi × Client 136,9 mi → match_over_tolerance')
data, group = RP.manual_match(DATE, [0, 1, 2], [], user='Tester')
check(group['kind'] == 'pair' and abs(group['net']) < 1e-6,
      'Σ JPM = Σ Client → casa como pair, diferença zero')
check([r['client_value'] for r in data['pending_payment']] == [-136927600.63],
      'as três saem do Pending Payment')
check(len([r for r in data['settled'] if r.get('manual_match') == group['id']]) == 3,
      'e entram no Settled')

os.makedirs = _orig_makedirs
print()
print('TUDO OK' if not fails else '%d FALHA(S)' % len(fails))
sys.exit(1 if fails else 0)
