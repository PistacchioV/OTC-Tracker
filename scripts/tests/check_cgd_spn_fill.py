#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_cgd_spn_fill.py — o preenchimento do Tracking Docs pelo SPN e o Tax ID
formatado.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_cgd_spn_fill.py

Banco e RefData num tmp; nada de dado real.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')

from apps.pages import cgd_docs as C                                # noqa: E402

FALHAS = []


def check(nome, obtido, esperado):
    if obtido == esperado:
        print('ok   ' + nome)
    else:
        FALHAS.append(nome)
        print('FAIL %s\n     obtido  : %r\n     esperado: %r' % (nome, obtido, esperado))


# ── 1. fmt_cnpj ────────────────────────────────────────────────────────────
f = C.fmt_cnpj
check('só dígitos vira CNPJ', f('12345678000190'), '12.345.678/0001-90')
check('já formatado fica igual', f('12.345.678/0001-90'), '12.345.678/0001-90')
check('zero perdido da planilha volta', f('1234567000190'), '01.234.567/0001-90')
check('grupo: cada entidade, separador "; "',
      f('12345678000190;98765432000110'), '12.345.678/0001-90; 98.765.432/0001-10')
check('CPF fica como veio', f('123.456.789-01'), '123.456.789-01')
check('N/A fica', f('N/A'), 'N/A')
check('Tax ID estrangeiro fica', f('US-EIN 12-3456789'), 'US-EIN 12-3456789')
check('vazio fica vazio', f(''), '')
check('TAXID_COLUMNS são colunas do banco',
      [c for c in C.TAXID_COLUMNS if c not in C.COLUMNS], [])

# ── 2. funil: gravação e leitura ───────────────────────────────────────────
tmp = tempfile.mkdtemp(prefix='cgdspn-')
db = os.path.join(tmp, 'cgd_sharepoint.db')
base = {c: '' for c in C.COLUMNS}
linhas = [
    dict(base, **{'Razão Social': 'ALFA SA', 'CNPJ': '12345678000190', 'SPN': '861826'}),
    dict(base, **{'Razão Social': 'BETA', 'SPN': '0861826.0', 'ECI': 'MANUAL',
                  'Grupo Economico': '0'}),
    dict(base, **{'Razão Social': 'GAMA; DELTA', 'SPN': '861826; 7039347'}),
    dict(base, **{'Razão Social': 'EPS', 'SPN': '5555'}),        # ambíguo
    dict(base, **{'Razão Social': 'ZETA', 'SPN': '999'}),        # fora do RefData
    dict(base, **{'Razão Social': 'ETA'}),                       # sem SPN
]
C.replace_all(linhas, db)
lidas = C.load_all(db)
check('import grava CNPJ formatado', lidas[0]['CNPJ'], '12.345.678/0001-90')

refdata = os.path.join(tmp, 'RefData.json')
with open(refdata, 'w') as fh:
    json.dump([
        {'SPN': '861826', 'ECONOMIC GROUP': 'Bussola Group', 'ECI': '221690142',
         'CASID': '221690142.0', 'UCN': '4097919244'},
        {'SPN': '7039347', 'ECONOMIC GROUP': 'SAFIRA HOLDING', 'ECI': '977255989',
         'CASID': '977255989', 'UCN': '92237696010'},
        {'SPN': '5555', 'ECONOMIC GROUP': 'G', 'ECI': '1', 'CASID': 'C', 'UCN': 'U'},
        {'SPN': '5555.0', 'ECONOMIC GROUP': 'G', 'ECI': '2', 'CASID': 'C', 'UCN': 'U'},
    ], fh)

script = os.path.join(REPO, 'scripts', 'fill_cgd_from_refdata_spn.py')


def roda(*extra):
    p = subprocess.run([sys.executable, script, '--db', db, '--refdata', refdata] + list(extra),
                       capture_output=True, text=True, env=os.environ.copy())
    if p.returncode != 0:
        print(p.stdout, p.stderr)
    return p


# ── 3. dry-run não grava ───────────────────────────────────────────────────
roda('--dry-run')
check('dry-run não grava', C.load_all(db)[0]['ECI'], '')

# ── 4. a passada de verdade ────────────────────────────────────────────────
p = roda()
check('script sai 0', p.returncode, 0)
r = {x['Razão Social']: x for x in C.load_all(db)}
check('SPN simples preenche as quatro',
      [r['ALFA SA'][c] for c in ('Grupo Economico', 'ECI', 'CASID', 'UCN')],
      ['Bussola Group', '221690142', '221690142', '4097919244'])
check('SPN com zero e .0 casa; valor manual FICA; 0 é vazio',
      [r['BETA']['ECI'], r['BETA']['Grupo Economico'], r['BETA']['UCN']],
      ['MANUAL', 'Bussola Group', '4097919244'])
check('grupo com dois SPNs junta os valores',
      r['GAMA; DELTA']['Grupo Economico'], 'Bussola Group; SAFIRA HOLDING')
check('SPN ambíguo: o campo divergente NÃO preenche',
      r['EPS']['ECI'], '')
check('SPN ambíguo: o campo que concorda preenche',
      r['EPS']['Grupo Economico'], 'G')
check('fora do RefData fica vazio', r['ZETA']['ECI'], '')
check('relatório cita o SPN fora do cadastro', '999' in p.stdout, True)
check('relatório cita o SPN ambíguo', 'AMBÍGUO' in p.stdout, True)

# ── 5. idempotente; --force reescreve ──────────────────────────────────────
p = roda()
check('segunda passada não acha nada', 'Nada a fazer' in p.stdout, True)
roda('--force')
check('--force sobrescreve o manual', C.load_all(db)[1]['ECI'], '221690142')

print('\n%d falha(s)' % len(FALHAS))
sys.exit(1 if FALHAS else 0)
