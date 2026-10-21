"""Pay/Rec: o SWAP casa e liquida até R$20 de diferença (21/10/2026).

O lado interno do SWAP chega BRUTO e sai líquido do IR regressivo do cadastro;
o que o cliente paga difere disso em alguns reais. Com o R$1 dos centavos o
par ficava solto dos dois lados. Este teste prende:

  * SWAP com R$15 de diferença casa e sai Settled; com R$25 não casa;
  * o resto (NDF) continua no R$1;
  * a janela larga é uma passada no FIM: um swap não rouba o par exato de uma
    linha que vem depois dele, e a ordem da tela não muda;
  * o sentido conta (um Pay de −8 não casa com um Receive de +8);
  * entre candidatos, a mesma contraparte vem antes do valor mais próximo;
  * o resumo fecha (a diferença do swap liquidado entra na folga);
  * o carry-forward junta o swap pendente de ontem com o pagamento de hoje;
  * o match manual aceita R$20 quando todo o lado JPM é SWAP, e só aí;
  * a tela recebe as duas tolerâncias.

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


def J(product, cpty, value):
    return {'product': product, 'cpty': cpty, 'value': value, 'le': 'JPM',
            'pay_receive': 'Receive' if value > 0 else 'Pay'}


def C(client, value, product='NDF'):
    return {'value': value, 'client': client, 'sistema': 'SPB - Derivativos', 'snumconta': '',
            'product': product, 'le': 'JPM', 'pay_receive': 'Receive' if value > 0 else 'Pay'}


def _by_jpm(details, value):
    return next(d for d in details if d['jpm_value'] == value)


# 1 · a janela do SWAP é R$20; a do resto segue R$1
det, summ = RP._reconcile([J('SWAP', 'SUZANO SA', -100000.00)], [C('SUZANO S.A.', -99985.00)])
d = _by_jpm(det, -100000.00)
check(d['client_value'] == -99985.00 and d['status'] == 'Settled',
      'SWAP −100.000,00 × −99.985,00 (R$15) → casa e sai Settled')
check(len(det) == 1, '… numa linha só (o cliente não sobra como pendente)')
check(all(r['check_value'] == 'OK' for r in summ), 'o resumo fecha com a diferença do swap liquidado')

det, _ = RP._reconcile([J('SWAP', 'SUZANO SA', -100000.00)], [C('SUZANO S.A.', -99975.00)])
check(_by_jpm(det, -100000.00)['client_value'] == '' and len(det) == 2,
      'SWAP com R$25 de diferença → não casa (duas pendências)')

det, _ = RP._reconcile([J('SWAP', 'SUZANO SA', -100000.00)], [C('SUZANO S.A.', -100020.00)])
check(_by_jpm(det, -100000.00)['status'] == 'Settled', 'R$20 exatos ainda cabem')

det, _ = RP._reconcile([J('NDF', 'SUZANO SA', -100000.00)], [C('SUZANO S.A.', -99985.00)])
check(_by_jpm(det, -100000.00)['client_value'] == '' and len(det) == 2,
      'NDF com R$15 → continua sem casar (R$1)')

check(RP._TOL_SWAP == 20.0 and RP._TOL_SETTLED == 1.0, 'constantes: SWAP 20, centavos 1')

# 2 · a janela larga é no fim: o swap não rouba o par exato de quem vem depois
jpm = [J('SWAP', 'ALFA SA', -5000.00), J('NDF', 'BETA SA', -5010.00)]
cli = [C('BETA SA', -5010.00), C('ALFA SA', -4990.00)]
det, _ = RP._reconcile(jpm, cli)
check(_by_jpm(det, -5010.00)['client_value'] == -5010.00, 'o NDF fica com o seu par exato')
check(_by_jpm(det, -5000.00)['client_value'] == -4990.00, 'o swap fica com o que sobrou na janela')
check([r['jpm_value'] for r in det[:2]] == [-5000.00, -5010.00], 'a ordem das linhas é a do lado JPM')

# 3 · sentido: Pay pequeno não casa com Receive
det, _ = RP._reconcile([J('SWAP', 'ALFA SA', -8.00)], [C('ALFA SA', 8.00)])
check(_by_jpm(det, -8.00)['client_value'] == '', 'SWAP Pay −8 × Receive +8 → não casa')

# 4 · mesma contraparte antes do valor mais próximo
det, _ = RP._reconcile([J('SWAP', 'SUZANO SA', -1000.00)],
                       [C('VALE SA', -1003.00), C('SUZANO S.A.', -1012.00)])
check(_by_jpm(det, -1000.00)['client'] == 'SUZANO S.A.',
      'VALE a R$3 × SUZANO a R$12 → fica a SUZANO (a mesma contraparte)')
det, _ = RP._reconcile([J('SWAP', 'SUZANO SA', -1000.00)], [C('VALE SA', -1003.00)])
check(_by_jpm(det, -1000.00)['client'] == 'VALE SA', 'sem a mesma contraparte, vale o valor (o motor é por valor)')

# 5 · carry-forward: o swap pendente de ontem × o pagamento de hoje
carried = {'pending_payment': [{'le': 'JPM', 'product': 'SWAP', 'jpm_cpty': 'SUZANO SA', 'client': '',
                                'pay_receive': 'Pay', 'jpm_value': -2000.00, 'client_value': '',
                                'status': 'Pending Payment', 'difference': 2000.00}],
           'pending_receivement': []}
_orig_prev = RP._prev_finalized
RP._prev_finalized = lambda d: (carried, '2026-10-20')
TODAY = {'le': 'JPM', 'product': 'NDF', 'jpm_cpty': '', 'client': 'SUZANO S.A.', 'pay_receive': 'Pay',
         'jpm_value': '', 'client_value': -1990.00, 'status': 'Pending', 'difference': -1990.00}
today = [dict(TODAY)]
settled = []
pp, pr = RP._apply_carry_forward('2026-10-21', today, [], settled)
check(not pp and len(settled) == 1 and settled[0]['client_value'] == -1990.00,
      'swap de ontem −2.000 × pagamento de hoje −1.990 → uma linha Settled')
carried['pending_payment'][0]['product'] = 'NDF'
today = [dict(TODAY)]
settled = []
pp, pr = RP._apply_carry_forward('2026-10-21', today, [], settled)
check(len(pp) == 2 and not settled, 'o mesmo com NDF → não junta (R$1)')
RP._prev_finalized = _orig_prev

# 6 · match manual
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
DATE = '2026-10-21'


def _row(product, jpm_cpty='', client='', jv='', cv=''):
    return {'le': 'JPM', 'product': product, 'jpm_cpty': jpm_cpty, 'client': client,
            'pay_receive': 'Pay', 'jpm_value': jv, 'client_value': cv, 'sistema': '',
            'snumconta': '', 'status': 'Pending', 'difference': 0}


def _seed(jpm_product):
    MEM.clear()
    RP._persist(DATE, {'success': True, 'summary': [], 'settled': [], 'pending_receivement': [],
                       'pending_payment': [_row(jpm_product, jpm_cpty='SUZANO SA', jv=-1000.00),
                                           _row('NDF', client='SUZANO S.A.', cv=-1015.00)]},
                strict=True)


def _err(fn):
    try:
        fn()
    except RP.ManualMatchError as e:
        return e.code, e.params
    return None, None


_seed('SWAP')
data, group = RP.manual_match(DATE, [0, 1], [], user='Tester')
check(group['kind'] == 'pair' and abs(group['net'] - 15.0) < 1e-9,
      'manual: JPM SWAP −1.000 × cliente −1.015 → casa (R$15 na janela do swap)')
_seed('NDF')
code, params = _err(lambda: RP.manual_match(DATE, [0, 1], []))
check(code == 'match_over_tolerance' and params.get('tol') == '1.00',
      'manual: o mesmo com NDF → match_over_tolerance, tolerância 1.00')
check(RP._manual_tol(['SWAP', 'SWAP']) == 20.0 and RP._manual_tol(['SWAP', 'NDF']) == 1.0
      and RP._manual_tol([]) == 1.0, '_manual_tol: todo SWAP → 20; misturado ou sem JPM → 1')
os.makedirs = _orig_makedirs

# 7 · a tela recebe as duas tolerâncias, e o JS usa a do swap pela mesma regra
with open(os.path.join(ROOT, 'apps/templates/pages/reconciliation-payrec.html'), encoding='utf-8') as fh:
    html = fh.read()
with open(os.path.join(ROOT, 'apps/static/js/pages/reconciliation-payrec.js'), encoding='utf-8') as fh:
    js = fh.read()
with open(os.path.join(ROOT, 'apps/pages/features/recon_payrec/entrypoint.py'), encoding='utf-8') as fh:
    ep = fh.read()
check('data-match-tol-swap="{{ match_tol_swap }}"' in html and 'match_tol_swap=' in ep,
      'template e rota levam a tolerância do swap')
check("data-match-tol-swap" in js and "r.product === 'SWAP'" in js and 'fmtNum(tol)' in js,
      'o JS escolhe a tolerância pelo lado JPM e mostra a que vale')

print()
print('TUDO OK' if not fails else '%d FALHA(S)' % len(fails))
sys.exit(1 if fails else 0)
