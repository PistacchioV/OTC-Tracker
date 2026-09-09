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

    # ── 4. o balde e da CONTRAPARTE, com os TRES produtos dentro ────────────
    #  O piso de R$ 1,00 e do beneficiario, nao do produto: o mesmo cliente
    #  liquidando termo de moeda, termo de mercadoria e opcao de mercadoria no
    #  mesmo mes soma tudo num acumulado so. Com um balde por produto as tres
    #  parcelas ficariam abaixo do piso para sempre, e a diferenca nao apareceria
    #  em lugar nenhum.
    print('\n== 4. o balde unico por contraparte (moeda + mercadoria) ==')
    e1, e2 = datetime(2026, 12, 1), datetime(2026, 12, 2)

    def _linha_ndfc(nm, ap):
        return {'counterparty': nm, 'apurado': ap, 'ir': 0.0, 'liquido': ap,
                'cells': [''] * len(R._NDFADV_COLUMNS)}

    def _linha_optc(nm, ap):
        return {'counterparty': nm, 'apurado': ap, 'premium': True, 'ir': 0.0,
                'liquido': ap, 'cells': [''] * 12}

    NDFC = {'2026-12-01': [_linha_ndfc('ACME LTDA', -6000.0)]}     # 0,30
    OPTC = {'2026-12-01': [_linha_optc('ACME LTDA', -4000.0)]}     # 0,20 (o net)
    R._ndfadv_collect = lambda ref, with_ir=True: NDFC.get(ref.strftime('%Y-%m-%d'), [])
    R._optadv_collect = lambda ref, with_ir=True: OPTC.get(ref.strftime('%Y-%m-%d'), [])

    cockpit(e1, [('BANCO J.P MORGAN S.A', 'ACME LTDA', -5000.0)])   # 0,25
    g = R._ndfsum_ir_cockpit_groups(
        [{'LEGAL': 'BANCO J.P MORGAN S.A', 'NM_COUNTERPARTY': 'ACME LTDA',
          '[PROD] Cockpit.SETTLEMENT': '-6000.00'}])                # 0,30 no dia 02
    r2 = R._ndfsum_ir_for_day(e2, g)
    acme2 = r2[R._fcst_norm('ACME LTDA')]
    # dia 01: 0,25 (moeda) + 0,30 (termo merc) + 0,20 (opcao merc) = 0,75, tudo
    # abaixo do piso → nada retido, 0,75 acumulado.
    led = R._ndfsum_ir_ledger_load(e1)['2026-12-01'][R._fcst_norm('ACME LTDA')]
    check('4. as tres fontes do dia somam no MESMO devido', led['due'], 0.75)
    check('4. abaixo do piso, nada retido e tudo acumula',
          (led['withheld'], led['carry_after']), (0.0, 0.75))
    # dia 02: 0,75 + 0,30 = 1,05 → retem a soma. Com um balde por produto o
    # acumulado de moeda seria so 0,25 e nada seria retido aqui.
    check('4. o acumulado dos TRES produtos entra no dia seguinte', acme2['carry_in'], 0.75)
    check('4. e a soma alcanca o piso: retem 1,05', (acme2['taxes'], acme2['withheld']),
          ([1.05], 1.05))

    # A fatia volta por FONTE, na ordem, e cada tela le a sua.
    r1 = R._ndfsum_ir_for_day(e1, R._ndfsum_ir_cockpit_groups(
        [{'LEGAL': 'BANCO J.P MORGAN S.A', 'NM_COUNTERPARTY': 'ACME LTDA',
          '[PROD] Cockpit.SETTLEMENT': '-5000.00'}]), src='moeda')
    fat = r1[R._fcst_norm('ACME LTDA')]
    check('4. cada fonte recebe a fatia dela, no tamanho certo',
          (len(fat['taxes']), len(fat['ndfc']), len(fat['optc'])), (1, 1, 1))

    # E gravar pela tela de MERCADORIA nao apaga a contribuicao da moeda: o
    # `ledger[dia]` e substituido, entao o dia e montado inteiro venha a chamada
    # de onde vier. Sem isso o acumulado do mes sairia menor, sem erro nenhum.
    it = [_linha_ndfc('ACME LTDA', -6000.0)]
    R._ndfadv_apply_ir(e1, it)
    led2 = R._ndfsum_ir_ledger_load(e1)['2026-12-01'][R._fcst_norm('ACME LTDA')]
    check('4. o aviso de mercadoria nao apaga a moeda do dia', led2['due'], 0.75)
    check('4. e a linha do aviso fica bruta abaixo do piso',
          (it[0]['ir'], it[0]['liquido']), (0.0, -6000.0))
    check('4. a celula do IR e a do liquido sao reescritas',
          (it[0]['cells'][R._NDFADV_IR_COL], it[0]['cells'][R._NDFADV_LIQ_COL]) != ('', ''), True)

    # A opcao entra com o NET como UMA entrada, e o rateio usa o valor que o
    # ledger devolveu — nao `abs(net) * taxa`.
    OPTC['2026-12-02'] = [_linha_optc('BETA SA', -900000.0)]        # 45,00, acima do piso
    it2 = list(OPTC['2026-12-02'])
    R._optadv_apply_ir(it2, e2)
    check('4. acima do piso a opcao retem normalmente', it2[0]['ir'], 45.0)
    OPTC['2026-12-02'] = [_linha_optc('GAMA SA', -4000.0)]          # 0,20, abaixo
    it3 = list(OPTC['2026-12-02'])
    R._optadv_apply_ir(it3, e2)
    check('4. abaixo do piso a opcao sai BRUTA', it3[0]['ir'], 0.0)

    # ── 5. o ledger nunca segura a tela ─────────────────────────────────────
    #  A cura dos dias anteriores le, por dia, o Cockpit + Operations B3 + Live
    #  Position + OTM. No share isso custa mais que a tela inteira, e um mes tem
    #  vinte dias. Estourado o teto a cura para, o dia pedido sai com o
    #  acumulado que deu tempo de somar, e o ledger NAO e gravado — nada errado
    #  fica em disco e a proxima abertura cura o que faltou.
    print('\n== 5. o teto da cura ==')
    e9 = datetime(2026, 12, 9)
    for dia in (3, 4, 7, 8):
        cockpit(datetime(2026, 12, dia),
                [('BANCO J.P MORGAN S.A', 'DELTA SA', -900000.0)])   # 45,00/dia
    led_antes = json.dumps(R._ndfsum_ir_ledger_load(e9), sort_keys=True)
    _teto = R._NDFSUM_IR_CURA_TETO
    R._NDFSUM_IR_CURA_TETO = -1.0                 # nenhum dia cabe no teto
    try:
        r9 = R._ndfsum_ir_for_day(e9, R._ndfsum_ir_cockpit_groups(
            [{'LEGAL': 'BANCO J.P MORGAN S.A', 'NM_COUNTERPARTY': 'DELTA SA',
              '[PROD] Cockpit.SETTLEMENT': '-900000.00'}]))
    finally:
        R._NDFSUM_IR_CURA_TETO = _teto
    check('5. com o teto estourado a tela AINDA recebe o imposto do dia',
          r9[R._fcst_norm('DELTA SA')]['taxes'], [45.0])
    check('5. e nada foi gravado — a proxima abertura cura',
          json.dumps(R._ndfsum_ir_ledger_load(e9), sort_keys=True), led_antes)
    r9b = R._ndfsum_ir_for_day(e9, R._ndfsum_ir_cockpit_groups(
        [{'LEGAL': 'BANCO J.P MORGAN S.A', 'NM_COUNTERPARTY': 'DELTA SA',
          '[PROD] Cockpit.SETTLEMENT': '-900000.00'}]))
    check('5. sem o teto, a cura completa e o ledger grava os dias',
          sorted(k for k in R._ndfsum_ir_ledger_load(e9)
                 if k.startswith('2026-12-0')) [-1], '2026-12-09')
    check('5. e o dia sai com o acumulado dos quatro dias curados',
          r9b[R._fcst_norm('DELTA SA')]['carry_in'], 0.0)

    # ── 6. a cura e INCREMENTAL (§432) ──────────────────────────────────────
    #  No share UM dia ja passa do teto, e gravar so com o mes inteiro curado
    #  queria dizer NUNCA: toda abertura recoletava os mesmos dias e desistia
    #  no mesmo ponto. Hoje o dia curado e gravado NA HORA — so o dia pedido
    #  fica de fora enquanto o acumulado esta incompleto — e a rodada seguinte
    #  continua de onde a anterior parou. A coleta roda FORA do _cache_lock.
    print('\n== 6. a cura incremental ==')
    import time as _time
    e6 = datetime(2026, 8, 6)                     # uteis antes: 03, 04, 05
    for dia in (3, 4, 5):
        cockpit(datetime(2026, 8, dia),
                [('BANCO J.P MORGAN S.A', 'DELTA SA', -900000.0)])   # 45,00/dia
    g6 = R._ndfsum_ir_cockpit_groups(
        [{'LEGAL': 'BANCO J.P MORGAN S.A', 'NM_COUNTERPARTY': 'DELTA SA',
          '[PROD] Cockpit.SETTLEMENT': '-900000.00'}])
    _orig_groups = R._ndfsum_ir_day_groups
    lock_livre = []

    def _lento(d, groups=None, src='moeda'):
        # a coleta NAO pode estar sob o lock global: outro thread tem de
        # conseguir toma-lo enquanto um dia e curado
        lock_livre.append(R._cache_lock.acquire(timeout=0.5))
        if lock_livre[-1]:
            R._cache_lock.release()
        _time.sleep(0.05)
        return _orig_groups(d, groups, src)
    R._ndfsum_ir_day_groups = _lento
    R._NDFSUM_IR_CURA_TETO = 0.03                  # cabe UM dia, o segundo estoura
    try:
        r6 = R._ndfsum_ir_for_day(e6, g6)
    finally:
        R._ndfsum_ir_day_groups = _orig_groups
        R._NDFSUM_IR_CURA_TETO = _teto
    led6 = R._ndfsum_ir_ledger_load(e6)
    check('6. o dia curado antes do teto FICOU gravado', '2026-08-03' in led6)
    check('6. o dia em que o teto estourou nao foi curado', '2026-08-04' not in led6)
    check('6. o dia pedido NAO e gravado com o acumulado incompleto', '2026-08-06' not in led6)
    check('6. e a tela ainda recebe o imposto do dia', r6[R._fcst_norm('DELTA SA')]['taxes'], [45.0])
    check('6. a coleta rodou FORA do _cache_lock', all(lock_livre) and len(lock_livre) >= 2)
    r6b = R._ndfsum_ir_for_day(e6, g6)             # sem teto: continua de onde parou
    check('6. a rodada seguinte completa o mes e grava o dia pedido',
          sorted(k for k in R._ndfsum_ir_ledger_load(e6) if k.startswith('2026-08')),
          ['2026-08-03', '2026-08-04', '2026-08-05', '2026-08-06'])
    check('6. com os tres dias retidos, o acumulado que entra e zero',
          r6b[R._fcst_norm('DELTA SA')]['carry_in'], 0.0)
    # o aquecimento em background cura ate a VESPERA e nunca o dia pedido
    led7, carry7, ok7 = R._ndfsum_ir_cure_month(datetime(2026, 8, 10), teto=None)
    check('6. o aquecimento cura ate a vespera (07 sem Cockpit vira entrada vazia)',
          ok7 and led7.get('2026-08-07') == {} and '2026-08-10' not in led7)
    check('6. e devolve o acumulado da vespera', carry7.get(R._fcst_norm('DELTA SA')), 0.0)
finally:
    shutil.rmtree(TMP, ignore_errors=True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
