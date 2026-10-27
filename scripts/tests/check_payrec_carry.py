"""Pay/Rec: o Pending Payment / Pending Receivement passa para os dias seguintes.

A linha marcada como Pending Payment/Receivement no Edit é uma liquidação que
não aconteceu, e tem de seguir na recon até casar ou ser justificada. O
carry-forward (`_apply_carry_forward`) lê o dia anterior pelo
`_prev_finalized`, que enumerava o histórico com `glob` no DISCO — e desde o
§434 o histórico só existe no BANCO. Não via nada (ou via o último JSON legado
que sobrou no disco), e a pendência sumia no dia seguinte. Os outros testes do
Pay/Rec trocam o `_prev_finalized` por um stub, e por isso nada acusava.

Este teste usa o ARMAZÉM de verdade (numa subárvore própria do DATA_DIR,
apagada no fim):
  1. o histórico gravado no banco é achado; o dia mais recente antes da data;
  2. sem histórico (dia rodado e não finalizado) vale o resultado do Run, e o
     histórico vence o Run do mesmo dia;
  3. ponta a ponta: marcar → End process → o dia seguinte traz a pendência;
     o dia depois (rodado, não finalizado) continua trazendo; Justified não vai;
  4. marcar DEPOIS do End process grava no histórico (a tela e o dia seguinte
     leem dele).
"""
import os
import sys
import tempfile
import uuid

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps import create_app                                      # noqa: E402
from apps.config import DebugConfig                              # noqa: E402

app = create_app(DebugConfig)
from apps.pages import recon_payrec as RP                        # noqa: E402
from apps.pages import routes as R                               # noqa: E402
from apps.pages import data_store as S                           # noqa: E402
from apps.pages.data_paths import data_write                     # noqa: E402

fails = []


def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


TAG = 'check-payrec-carry-' + uuid.uuid4().hex[:8]
RP._CACHE_DIR = data_write('cache', TAG, 'work')
RP._HISTORY_BASE = data_write('cache', TAG, 'hist')


def _pend(cpty, val, status='Pending', pr='PAY'):
    return {'le': 'JPM', 'product': 'NDF', 'jpm_cpty': cpty, 'client': '', 'pay_receive': pr,
            'jpm_value': val, 'client_value': '', 'difference': '', 'status': status, 'comment': ''}


def _day(pay=(), rec=()):
    return {'success': True, 'summary': [{'x': 1}], 'pending_payment': list(pay),
            'pending_receivement': list(rec), 'settled': []}


def _limpa():
    for raiz in (RP._CACHE_DIR, RP._HISTORY_BASE):
        try:
            for dirpath, _d, files in list(S.walk(raiz)):
                for f in files:
                    S.remove(os.path.join(dirpath, f))
        except Exception:                                        # noqa: BLE001
            pass


try:
    with app.app_context():
        print('== 1. o histórico no banco é achado ==')
        R._atomic_write_json(RP._history_path('2031-03-05'), _day([_pend('A', -1)]))
        R._atomic_write_json(RP._history_path('2031-03-10'), _day([_pend('B', -2)]))
        prev = RP._prev_finalized('2031-03-11')
        check(prev is not None and prev[1] == '2031-03-10', 'o mais recente antes da data: %r' % (prev and prev[1]))
        check(prev is not None and prev[0]['pending_payment'][0]['jpm_cpty'] == 'B', 'e o conteúdo dele')
        check(RP._prev_finalized('2031-03-10')[1] == '2031-03-05', 'estritamente ANTES da data')
        check(RP._prev_finalized('2031-03-05') is None, 'nada antes: None')

        print('\n== 2. sem histórico vale o Run; no mesmo dia o histórico vence ==')
        RP._persist('2031-03-12', _day([_pend('RUN', -3)]), strict=True)
        check(RP._prev_finalized('2031-03-13')[1] == '2031-03-12', 'o dia rodado e não finalizado conta')
        RP._persist('2031-03-10', _day([_pend('WORK', -9)]), strict=True)
        check(RP._prev_finalized('2031-03-11')[0]['pending_payment'][0]['jpm_cpty'] == 'B',
              'histórico vence o Run do mesmo dia')
        _limpa()

        print('\n== 3. ponta a ponta ==')
        D1, D2, D3 = '2031-04-01', '2031-04-02', '2031-04-03'
        RP._persist(D1, _day([_pend('ACME', -100.0), _pend('BETA', -50.0)],
                             [_pend('GAMA', 70.0, pr='REC')]), strict=True)
        RP.justify_row(D1, 'pay', 0, '', 'Pending Payment')
        RP.justify_row(D1, 'pay', 1, 'pago por fora', 'Pending')        # → Justified
        RP.justify_row(D1, 'rec', 0, '', 'Pending Receivement')
        check(RP.finalize_history(D1) is not None, 'End process grava o histórico')
        pp, pr = RP._apply_carry_forward(D2, [], [], [])
        check([r['jpm_cpty'] for r in pp] == ['ACME'], 'D+1: o Pending Payment vem; o Justified não (%r)'
              % [r['jpm_cpty'] for r in pp])
        check([r['jpm_cpty'] for r in pr] == ['GAMA'], 'D+1: o Pending Receivement vem')
        check(pp and pp[0]['carry_origin'] == D1 and pp[0]['status'] == 'Pending Payment',
              'com a origem e o status preservados')
        RP._persist(D2, _day(pp, pr), strict=True)                     # D+1 rodado, sem End process
        pp3, pr3 = RP._apply_carry_forward(D3, [], [], [])
        check([r['jpm_cpty'] for r in pp3] == ['ACME'] and pp3[0]['carry_origin'] == D1,
              'D+2 (D+1 sem End process): segue, com a origem de D')
        check(pp3 and pp3[0]['comment'] == 'Pagamento pendente de 01/04/2031', 'o comentário diz desde quando')
        settled = [{'le': 'JPM', 'jpm_value': -100.0, 'client_value': -100.0, 'status': 'Settled'}]
        pp4, _ = RP._apply_carry_forward(D3, [], [], settled)
        check(pp4 == [], 'liquidou hoje: sai da lista')
        _limpa()

        print('\n== 4. marcar depois do End process ==')
        RP._persist(D1, _day([_pend('ACME', -100.0)]), strict=True)
        RP.finalize_history(D1)
        out = RP.justify_row(D1, 'pay', 0, '', 'Pending Payment')
        check(out is not None, 'o Justify responde')
        check(RP.load_last(D1)['pending_payment'][0]['status'] == 'Pending Payment',
              'a tela (o histórico) mostra a marca')
        pp, _ = RP._apply_carry_forward(D2, [], [], [])
        check([r['jpm_cpty'] for r in pp] == ['ACME'], 'e o dia seguinte a traz')
        check(RP._load_flat(D1)['pending_payment'][0]['status'] == 'Pending Payment',
              'o cache de trabalho acompanha (mesma linha)')
        check(RP.justify_row(D1, 'pay', 5, '', 'Pending Payment') is None, 'índice fora: None')
finally:
    with app.app_context():
        _limpa()

print(('\nFAIL: %d' % len(fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
