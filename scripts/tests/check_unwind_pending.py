# -*- coding: utf-8 -*-
"""A recompra no Pending Confirmation: vencimento e status por Total × Parcial
(equipe, 28/10/2026, §717).

  * PARCIAL (o contrato segue): Maturity Date = o vencimento da operação
    ORIGINAL; Pending Status pelo TIPO DE ASSINATURA da contraparte no
    Reference Data — Digital → `Pending Digital Signature`, Manual ou sem
    cadastro → `Pending Original`;
  * TOTAL (o saldo zera): Maturity Date = a data da RECOMPRA; Pending Status
    `Exception Digital Fep Web`, e o Status vira `Ok`.

O que se prende:
  1. `pending_da_recompra`: total, parcial, saldo desconhecido (= parcial: não
     fecha como Ok o que talvez não encerre o contrato) e parcial sem o
     vencimento original (fica a liquidação, como antes);
  2. a linha do Pending Confirmation montada do deal de verdade
     (`confirmation_deal` → `_pc_row_from_deal`), com o Reference Data
     trocado: Digital, Manual, total + a regra do próprio Pending (Status Ok);
     o `pending_status` explícito de quem chama continua vencendo;
  3. as recompras do CATÁLOGO (NDF/Opção de Commodities, Swap EDG) levam as
     mesmas chaves, pelo mesmo `confirmation_deal` da Fase 1.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_unwind_pending.py
"""
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(nome, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + nome + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        FALHAS.append(nome)


HOJE = date(2026, 10, 28)
# Parcial: recompra de 100 mil de um contrato de 500 mil (nada recomprado antes).
PARCIAL = {'AthenaID': 'STP-XE-AAA-0-0', 'Contract': '26C00000001', 'Currency': 'USD',
           'Counterparty': 'CLIENTE TESTE SA', 'TaxID': '11.111.111/0001-11',
           'OriginalNotional': 500000.0, 'UnwoundBefore': 0.0, 'UnwoundNotional': 100000.0,
           'MaturityDate': '15/01/2027', 'SettlementDate': '30/10/2026',
           'Result': 1234.56, 'CptyAccount': '73760102', 'PartyAccount': '73760009',
           'Status': 'Imported'}
# Total: o recomprado agora é o que restava (300 mil já recomprados antes).
TOTAL = dict(PARCIAL, AthenaID='STP-XE-BBB-0-0', Contract='26C00000002',
             UnwoundBefore=400000.0, UnwoundNotional=100000.0)
# Sem saldo: a posição não respondeu nem o original nem o já recomprado.
SEM_SALDO = {k: v for k, v in PARCIAL.items() if k not in ('OriginalNotional', 'UnwoundBefore')}
SEM_VENC = dict(PARCIAL, MaturityDate='')


def main():
    from run import app
    from apps.pages import routes as R
    from apps.pages.features.unwinds import commands as C
    from apps.pages.features.unwinds.product import commands as PC
    from apps.pages.platform import pending_confirmation as PPC

    print('== 1. pending_da_recompra ==')
    check('total: a data da recompra e Exception Digital Fep Web',
          C.pending_da_recompra(TOTAL, HOJE),
          {'_pc_maturity': '2026-10-28', '_pc_pending_status': 'Exception Digital Fep Web'})
    check('parcial: o vencimento ORIGINAL e o status pela assinatura',
          C.pending_da_recompra(PARCIAL, HOJE),
          {'_pc_maturity': '15/01/2027', '_pc_por_assinatura': True})
    check('saldo desconhecido: tratado como parcial',
          C.pending_da_recompra(SEM_SALDO, HOJE).get('_pc_por_assinatura'), True)
    check('parcial sem o vencimento original: fica a liquidação',
          C.pending_da_recompra(SEM_VENC, HOJE)['_pc_maturity'], '30/10/2026')

    print('\n== 2. a linha do Pending Confirmation ==')
    REF = {}
    original_ref = R._fxo_refdata_by_spn
    R._fxo_refdata_by_spn = lambda: dict(REF)
    try:
        with app.test_request_context('/'):
            def linha(l, assinatura, **kw):
                REF.clear()
                REF[R._norm_spn('999')] = {'SPN': '999', 'COUNTERPARTY': l['Counterparty'],
                                           'SIGNATURE TYPE': assinatura, 'ECONOMIC GROUP': 'GRUPO'}
                deal = C.confirmation_deal(l, HOJE)
                deal['SPN'] = '999'
                row = PPC._pc_row_from_deal(deal, C.MC_SOURCE, trade_number=deal['_mc_key'], **kw)
                return PPC._pc_apply_auto_rules(row) if row else row

            r = linha(PARCIAL, 'Digital')
            check('parcial + Digital: Pending Digital Signature, vencimento original',
                  (r['Pending Status'], r['Maturity Date']), ('Pending Digital Signature', '15/01/2027'))
            check('   e segue pendente (Status não é Ok)', r['Status'] != 'Ok', True)
            r = linha(PARCIAL, 'Manual')
            check('parcial + Manual: Pending Original', r['Pending Status'], 'Pending Original')
            r = linha(PARCIAL, '')
            check('parcial sem tipo cadastrado: Pending Original', r['Pending Status'], 'Pending Original')
            r = linha(TOTAL, 'Digital')
            check('total: Exception Digital Fep Web, vencimento = a recompra, Status Ok',
                  (r['Pending Status'], r['Maturity Date'], r['Status']),
                  ('Exception Digital Fep Web', '28/10/2026', 'Ok'))
            check('a Trade Date continua a data da recompra', r['Trade Date'], '28/10/2026')
            r = linha(PARCIAL, 'Digital', pending_status='Pending OTC')
            check('o pending_status explícito de quem chama vence', r['Pending Status'], 'Pending OTC')

            print('\n== 3. as recompras do catálogo ==')
            for page in PC.paginas_com_esteira():
                d = PC.confirmation_deal(page, dict(PARCIAL, _id='X1', DealID='D1'), HOJE)
                check('%s: parcial leva o vencimento original' % page['label'],
                      (d.get('_pc_maturity'), d.get('_pc_por_assinatura')), ('15/01/2027', True))
                d = PC.confirmation_deal(page, dict(TOTAL, _id='X2', DealID='D2'), HOJE)
                check('%s: total leva a data da recompra' % page['label'],
                      (d.get('_pc_maturity'), d.get('_pc_pending_status')),
                      ('2026-10-28', 'Exception Digital Fep Web'))
    finally:
        R._fxo_refdata_by_spn = original_ref

    print(('\nFALHAS (%d): %s' % (len(FALHAS), FALHAS)) if FALHAS else '\nTUDO OK')
    return 1 if FALHAS else 0


if __name__ == '__main__':
    sys.exit(main())
