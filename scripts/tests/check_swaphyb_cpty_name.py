"""Other Products > Swap > Kapital Hybrids: o Counterparty Name sai da SPN.

A coluna Counterparty SPN do BANCO_UPCOMING_PAYMENTS.csv e a chave; o nome e o
do cadastro (mesa, 30/09/2026), pela MESMA regra do OTM (`_otm_cpty_name`):

  1. `le-spn` — SPN de entidade NOSSA da o nome dela (ela nao esta no
     Reference Data como contraparte);
  2. Reference Data por SPN;
  3. sem nenhum dos dois, o texto do proprio arquivo — a linha nao sai anonima.

Nao encosta em dado real: o armazem, o de-para de Cetip ID e os dois cadastros
sao stubs.
"""
import os
import sys
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

from apps.pages import routes as R  # noqa: E402

FAILS = []


def check(label, got, exp):
    ok = got == exp
    print('{} {}{}'.format('ok  ' if ok else 'FAIL', label,
                           '' if ok else ' -> got {!r}, expected {!r}'.format(got, exp)))
    if not ok:
        FAILS.append(label)


LINHAS = [
    # entidade nossa: o nome vem do le-spn
    {'Kapital ID': '7005549258', 'Counterparty SPN': '4734603',
     'Counterparty Name': 'Lawton Multimercado Excl', 'Amount': '100'},
    # cliente: o nome vem do Reference Data (SPN com zero a esquerda no arquivo)
    {'Kapital ID': '7005550563', 'Counterparty SPN': '01598250',
     'Counterparty Name': 'MRS LOGISTI', 'Amount': '-50'},
    # SPN fora dos dois cadastros: fica o texto do arquivo
    {'Kapital ID': '7005549261', 'Counterparty SPN': '4816928',
     'Counterparty Name': 'Thalassius A022.21 Participacoes S.A.', 'Amount': '10'},
]

_orig = {k: getattr(R, k) for k in ('_ds_display_json_path', '_db_day_records',
                                     '_swaphyb_kap_to_cetip', '_ds_read_updated',
                                     '_mapping_rows', '_refdata_by_spn')}
_isfile = R._store.isfile
try:
    R._ds_display_json_path = lambda ref, name: '/tmp/swaphyb-test.json'
    R._store.isfile = lambda p: True
    R._db_day_records = lambda p: LINHAS
    R._swaphyb_kap_to_cetip = lambda: {}
    R._ds_read_updated = lambda p: ''
    R._mapping_rows = lambda key: ([{'LE': 'LAWTON', 'SPN': '4734603',
                                     'NAME': 'LAWTON MULTIMERCADO EXCLUSIVO LATAM E&H 44'}]
                                   if key == 'le-spn' else [])
    R._refdata_by_spn = lambda: {R._spn_key('1598250'): 'MRS LOGISTICA S/A'}

    out = R._swaphyb_collect(datetime(2026, 9, 30))
    i_nome = out['columns'].index('Counterparty Name')
    nomes = {r[0]: r[i_nome] for r in out['rows']}
    check('SPN de entidade nossa: o nome do le-spn', nomes['7005549258'],
          'LAWTON MULTIMERCADO EXCLUSIVO LATAM E&H 44')
    check('SPN de cliente: o nome do Reference Data (zero a esquerda ignorado)',
          nomes['7005550563'], 'MRS LOGISTICA S/A')
    check('SPN fora dos cadastros: fica o texto do arquivo', nomes['7005549261'],
          'Thalassius A022.21 Participacoes S.A.')
finally:
    for k, v in _orig.items():
        setattr(R, k, v)
    R._store.isfile = _isfile

print('\nTUDO OK' if not FAILS else '\n{} FALHA(S)'.format(len(FAILS)))
sys.exit(1 if FAILS else 0)
