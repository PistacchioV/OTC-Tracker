"""Avisos de liquidacao: a conta do CLIENTE quando o BANCO paga.

Os defaults do Reference Data (Counterparty Details) sao a visao do CLIENTE:
`DEFAULT_PAY` e a conta de onde ELE paga, `DEFAULT_RECEIVE` a conta em que ELE
recebe. O aviso e escrito na visao do BANCO: Resultado Final negativo e o banco
pagando, o cliente recebendo — e a conta impressa tem de ser a de RECEIVE
(mesa, 29/09/2026). Os quatro avisos imprimiam a de PAY: com PAY na conta
interna e RECEIVE na externa, o documento mandava o dinheiro para a conta
errada, sem erro nenhum.

O que este teste prende:
  1. a regra (`_client_account_for_bank_paying`): RECEIVE, nunca PAY;
  2. sem RECEIVE aprovado nao cai para o PAY nem para "a primeira ativa";
  3. os QUATRO avisos (premio, NDF, swap, termo/opcao de commodities) chamam a
     regra — e nenhum pede mais a conta de PAY;
  4. o documento renderizado (swap) traz a conta de RECEIVE.
"""
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

from apps.pages import otc_emails as E  # noqa: E402

FAILS = []


def check(label, got, exp):
    ok = got == exp
    print('{} {}{}'.format('ok  ' if ok else 'FAIL', label,
                           '' if ok else ' -> got {!r}, expected {!r}'.format(got, exp)))
    if not ok:
        FAILS.append(label)


INTERNA = {'id': 'p1', 'bank': '376', 'agency': '0011', 'account': '1111111', 'status': 'Active'}
EXTERNA = {'id': 'r1', 'bank': '341', 'agency': '0910', 'account': '2222222', 'status': 'Active'}


def cp(receive=True):
    return {'SPN': '9', 'BANKING': {
        'ACCOUNTS': [INTERNA, EXTERNA],
        'DEFAULT_PAY': {'current': 'p1'},
        'DEFAULT_RECEIVE': {'current': 'r1' if receive else None}}}


# 1. PAY interna, RECEIVE externa -> banco pagando imprime a EXTERNA.
check('banco paga -> DEFAULT_RECEIVE do cliente',
      E._client_account_for_bank_paying(cp()), ('341', '0910', '2222222'))

# 2. Sem RECEIVE aprovado: vazio (o aviso mostra '—'), nunca a de PAY.
check('sem DEFAULT_RECEIVE nao cai para o PAY',
      E._client_account_for_bank_paying(cp(receive=False)), ('', '', ''))

# Formato legado continua respondendo pelo lado de RECEIVE.
check('legado: lista RECEIVE',
      E._client_account_for_bank_paying({'BANKING': {
          'PAY': [{'bank': '1', 'agency': '2', 'account': '3'}],
          'RECEIVE': [{'bank': '4', 'agency': '5', 'account': '6'}]}}),
      ('4', '5', '6'))

# 3. Os quatro avisos chamam a regra; ninguem pede mais a conta de PAY.
src = open(os.path.join(ROOT, 'apps', 'pages', 'otc_emails.py'), encoding='utf-8').read()
check('quatro avisos usam a regra', src.count('= _client_account_for_bank_paying(cp)'), 4)
check('nenhum aviso pede o PAY', re.findall(r"_first_bank\(", src), [])

# 4. O documento do swap, banco pagando, traz a conta de RECEIVE.
items = [{'bruto': -1000.0, 'ir': 0.0, 'liquido': -1000.0, 'spn': '9',
          'taxid': '12345678000199', 'cells': ['X']}]
draft = E._swap_settlement_email(items, 'CLIENTE X', 'JPM', False, None,
                                 {E._norm_spn('9'): cp()}, ['Contrato'])
html = draft['html']
check('aviso de swap traz a conta de RECEIVE', '2222222' in html, True)
check('aviso de swap nao traz a de PAY', '1111111' in html, False)

print('\nTUDO OK' if not FAILS else '\n{} FALHA(S)'.format(len(FAILS)))
sys.exit(1 if FAILS else 0)
