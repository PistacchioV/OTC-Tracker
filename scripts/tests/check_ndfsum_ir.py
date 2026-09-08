# -*- coding: utf-8 -*-
"""check_ndfsum_ir.py — o IR do termo de MOEDA com piso de R$ 1,00 acumulado no mes (§423).

A API getTradesBySettle nao traz o imposto que o SETTLEMENT.xlsx trazia; o NDF
Summary passou a CALCULAR: 0,005% sobre a liquidacao em que o banco paga, e um
piso mensal por contraparte — abaixo de R$ 1,00 nao retem e acumula; quando o
acumulado mais o do dia alcanca R$ 1,00, retem a soma; mes novo zera.

  1. a regra pura (`_ndfsum_ir_apply`): abaixo do piso → bruto e acumula; a soma
     alcanca o piso → retem a soma na PRIMEIRA operacao com imposto; positivo e
     isento nao pagam; arredondamento a 2 casas;
  2. o ledger mensal: dias anteriores sem entrada sao CURADOS do arquivo do
     Cockpit, na ordem; a entrada do dia e SUBSTITUIDA (recarregar nao dobra);
     mes novo comeca em zero; o ledger vai para o tmp, nunca para o dado real;
  3. o aviso: `ir_carry` marca a operacao que levou o acumulado e `ir_waived` a
     liquidacao dispensada — e o e-mail escreve a nota correspondente.
"""
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='otc-share-'))

from apps.pages import routes as R                            # noqa: E402
from apps.pages import otc_emails as E                        # noqa: E402

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


print('\n== 1. a regra pura ==')
check('abaixo do piso: bruto, e acumula', R._ndfsum_ir_apply([-5000.0], 0.0), ([0.0], 0.25, 0.0, 0.25))
check('acumulado + dia ainda abaixo do piso: segue bruto', R._ndfsum_ir_apply([-5000.0], 0.25), ([0.0], 0.25, 0.0, 0.5))
check('acumulado + dia alcanca o piso: retem a SOMA', R._ndfsum_ir_apply([-5000.0], 0.9), ([1.15], 0.25, 1.15, 0.0))
check('exatamente R$ 1,00 retem', R._ndfsum_ir_apply([-20000.0], 0.0), ([1.0], 1.0, 1.0, 0.0))
check('duas operacoes: o acumulado entra na PRIMEIRA com imposto',
      R._ndfsum_ir_apply([3000.0, -5000.0, -30000.0], 0.9), ([0.0, 1.15, 1.5], 1.75, 2.65, 0.0))
check('cliente pagando (positivo) nao tem IR', R._ndfsum_ir_apply([240000.0], 0.7), ([0.0], 0.0, 0.0, 0.7))
check('isento: nada, e o acumulado nao muda', R._ndfsum_ir_apply([-240000.0], 0.3, exempt=True), ([0.0], 0.0, 0.0, 0.3))
check('o exemplo do aviso: 240.000 → 12,00', R._ndfsum_ir_apply([-240000.0], 0.0), ([12.0], 12.0, 12.0, 0.0))

print('\n== 2. o ledger mensal ==')
TMP = tempfile.mkdtemp(prefix='otc-ndfsum-ir-')
R._B3_DATA_DIR = TMP
R.NDFC_JSON_ROOT = os.path.join(TMP, 'cache', 'daily settlement')
R._ndfc_ir_exempt = lambda name: 'LAWTON' in str(name).upper()


def cockpit(day, rows):
    jp = R._ndfc_json_path(day)
    os.makedirs(os.path.dirname(jp), exist_ok=True)
    recs = [{'LEGAL': legal, 'NM_COUNTERPARTY': nm, '[PROD] Cockpit.SETTLEMENT': str(v)}
            for legal, nm, v in rows]
    with io.open(jp, 'w', encoding='utf-8') as fh:
        json.dump(recs, fh)


d1, d2, d3 = datetime(2026, 9, 1), datetime(2026, 9, 2), datetime(2026, 9, 3)
cockpit(d1, [('BANCO J.P MORGAN S.A', 'ACME LTDA', -5000.0),         # 0,25 → bruto
             ('BANCO J.P MORGAN S.A', 'LAWTON FUNDO', -900000.0),    # isento
             ('LAWTON MULTIMERCADO', 'ACME LTDA', -900000.0)])       # legal fora do universo
cockpit(d2, [('BANCO J.P MORGAN S.A', 'ACME LTDA', -9000.0)])         # 0,45 → acumulado 0,70
try:
    g3 = R._ndfsum_ir_cockpit_groups(
        [{'LEGAL': 'BANCO J.P MORGAN S.A', 'NM_COUNTERPARTY': 'ACME LTDA', '[PROD] Cockpit.SETTLEMENT': '-7000.00'},
         {'LEGAL': 'BANCO J.P MORGAN S.A', 'NM_COUNTERPARTY': 'BETA SA', '[PROD] Cockpit.SETTLEMENT': '-100.00'}])
    res = R._ndfsum_ir_for_day(d3, g3)
    acme = res[R._fcst_norm('ACME LTDA')]
    check('2. dias 01 e 02 curados do Cockpit → acumulado 0,70 entra no dia 03', acme['carry_in'], 0.7)
    check('2. 0,70 + 0,35 = 1,05 → retem a soma', (acme['taxes'], acme['withheld']), ([1.05], 1.05))
    check('2. BETA (0,01) fica bruta e acumula', res[R._fcst_norm('BETA SA')]['taxes'], [0.0])
    ledger = R._ndfsum_ir_ledger_load(d3)
    check('2. ledger tem os tres dias', sorted(ledger), ['2026-09-01', '2026-09-02', '2026-09-03'])
    check('2. o isento nao acumula', ledger['2026-09-01'][R._fcst_norm('LAWTON FUNDO')]['carry_after'], 0.0)
    check('2. a perna fora do universo (legal LAWTON) nao entrou',
          ledger['2026-09-01'][R._fcst_norm('ACME LTDA')]['due'], 0.25)
    res2 = R._ndfsum_ir_for_day(d3, g3)
    check('2. recarregar o dia nao dobra (entrada substituida)', res2[R._fcst_norm('ACME LTDA')]['taxes'], [1.05])
    d4 = datetime(2026, 9, 4)
    res4 = R._ndfsum_ir_for_day(d4, R._ndfsum_ir_cockpit_groups(
        [{'LEGAL': 'BANCO J.P MORGAN S.A', 'NM_COUNTERPARTY': 'ACME LTDA', '[PROD] Cockpit.SETTLEMENT': '-1000.00'}]))
    check('2. depois de reter, o acumulado da ACME voltou a zero', res4[R._fcst_norm('ACME LTDA')]['carry_in'], 0.0)
    check('2. e o da BETA segue (0,01) para o proximo dia dela',
          R._ndfsum_ir_ledger_load(d4)['2026-09-03'][R._fcst_norm('BETA SA')]['carry_after'], 0.01)
    oct1 = datetime(2026, 10, 1)
    reso = R._ndfsum_ir_for_day(oct1, R._ndfsum_ir_cockpit_groups(
        [{'LEGAL': 'BANCO J.P MORGAN S.A', 'NM_COUNTERPARTY': 'BETA SA', '[PROD] Cockpit.SETTLEMENT': '-100.00'}]))
    check('2. mes novo comeca em zero', reso[R._fcst_norm('BETA SA')]['carry_in'], 0.0)
    check('2. o ledger de outubro e outro arquivo',
          os.path.basename(R._ndfsum_ir_ledger_path(oct1)), 'ndf-ir-ledger_202610.json')
    check('2. o ledger ficou no tmp', R._ndfsum_ir_ledger_path(d3).startswith(TMP))

    print('\n== 3. o aviso ==')
    E._build_cpdetails_index = lambda: {}
    E._ndf_pdf_set = lambda: set()
    base = {'counterparty': 'ACME LTDA', 'legal': 'BANCO J.P MORGAN S.A', 'athena': 'DBH-1', 'trade_date': '01/07/2026',
            'notional_fc': 1000.0, 'ccy': 'USD', 'settlement': -7000.0, 'net_type': 'Total Net', 'spn': '1', 'taxid': ''}
    d = E._ndf_settlement_email([dict(base, tax=1.05, ir_carry=0.7, ir_waived=False, fixing='5.1253')],
                                'ACME LTDA', 'JPM', '03/09/2026', {})
    check('3. a nota do acumulado sai no aviso', 'inclui R$ 0,70' in d['html'])
    check('3. a coluna Fixing sai com o Spot', '5,1253' in d['html'] and '>Fixing<' in d['html'])
    d = E._ndf_settlement_email([dict(base, settlement=-100.0, tax=0.0, ir_carry=0.0, ir_waived=True)],
                                'BETA SA', 'JPM', '03/09/2026', {})
    check('3. a nota da dispensa sai no aviso', 'inferior a R$ 1,00' in d['html'])
    d = E._ndf_settlement_email([dict(base, settlement=-240000.0, tax=12.0, ir_carry=0.0, ir_waived=False)],
                                'YARA', 'JPM', '04/09/2026', {})
    check('3. sem acumulado nem dispensa, nenhuma nota', 'R$ 1,00' not in d['html'])
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
