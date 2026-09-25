#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_ndfsum_card_count.py — os cards do NDF Summary contam só as contas PRÓPRIAS.

Mesa, 25/09/2026: no lado B3 dos cards (resgates do Operations B3), a
QUANTIDADE conta só a linha cuja `Conta` é 73760.00-9 (Banco) ou 04880.00-6
(MGT) — as contas `OWN` de JPM e MGT no `b3-accounts`, nunca fixadas no
código. O VALOR segue somando toda linha ("apenas na contagem").
"""
import os
import sys
import tempfile
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps import create_app                                     # noqa: E402
from apps.config import DebugConfig                             # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


app = create_app(DebugConfig)
with app.test_request_context('/'):
    from apps.pages import routes as R
    CONTAS = [
        {'LE': 'MGT', 'ACCOUNT': '04880.00-6', 'ACCOUNT TYPE': 'OWN'},
        {'LE': 'MGT', 'ACCOUNT': '04880.10-9', 'ACCOUNT TYPE': 'CLIENT 1'},
        {'LE': 'JPM', 'ACCOUNT': '73760.00-9', 'ACCOUNT TYPE': 'OWN'},
        {'LE': 'JPM', 'ACCOUNT': '73760.10-2', 'ACCOUNT TYPE': 'CLIENT 1'},
        {'LE': 'LAWTON', 'ACCOUNT': '00041.00-7', 'ACCOUNT TYPE': 'OWN'},
    ]

    def res(titulo, conta, valor):
        return {'Título': titulo, 'Tipo Operação': 'Resgate', 'Conta': conta, 'Valor': valor}

    OPS = [
        res('C1', '73760.00-9', '100,00'),   # conta própria do Banco → conta
        res('C2', '04880.00-6', '200,00'),   # conta própria da MGT → conta
        res('C2', '73760.00-9', '-200,00'),  # intragrupo espelhado → conta (também própria)
        res('C3', '73760.10-2', '50,00'),    # guarda-chuva → NÃO conta, valor soma
        res('C4', '00041.00-7', '10,00'),    # Lawton → NÃO conta
    ]
    orig = (R._mapping_rows, R._opb3_settle_rows, R._ndfsum_fx_map, R._ndfc_collect,
            R._ndfc_load, R._ndfc_b3_maps, R._opb3_legal_side)
    rows_orig = R._mapping_rows
    R._mapping_rows = lambda key, strict=False: CONTAS if key == 'b3-accounts' else rows_orig(key, strict)
    R._opb3_settle_rows = lambda ref: OPS
    R._ndfsum_fx_map = lambda ref: {'C1': 'vanilla', 'C2': 'vanilla', 'C3': 't0', 'C4': 'other'}
    R._ndfc_collect = lambda ref: {'rows': []}
    R._ndfc_load = lambda ref: ('jp', [])
    R._ndfc_b3_maps = lambda ref: ({}, {}, {})
    try:
        check('contas que contam = as OWN de JPM e MGT',
              sorted(R._ndfsum_count_accounts()), ['04880006', '73760009'])
        rc = R._ndfsum_collect(datetime(2026, 9, 25))['recon']
        check('vanilla: 3 linhas em conta própria', rc['vanilla']['b3_count'], 3)
        check('t0: guarda-chuva não conta', rc['t0']['b3_count'], 0)
        check('t0: mas o valor soma', rc['t0']['b3_value'], R._ndfsum_money(50.0))
        check('other: Lawton não conta', rc['other']['b3_count'], 0)
        check('total conta 3', rc['total']['b3_count'], 3)
        check('total soma o valor de todas', rc['total']['b3_value'], R._ndfsum_money(160.0))
    finally:
        (R._mapping_rows, R._opb3_settle_rows, R._ndfsum_fx_map, R._ndfc_collect,
         R._ndfc_load, R._ndfc_b3_maps, R._opb3_legal_side) = orig

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS: %d' % len(fails)))
sys.exit(1 if fails else 0)
