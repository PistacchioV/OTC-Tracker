"""Col A ('Status') = 'Sucesso' e o unico que entra na recon, nas DUAS trilhas
do HistoricoMensagens (JPM e MGT): cliente de derivativos e interbancario LTR.
"""
import sys
import os
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))   # scripts/tests/ -> raiz do repo
sys.path.insert(0, ROOT)
from apps.pages.recon_payrec import _cli_spb

COLS = ['Status', 'Data', 'Hora', 'sNumConta', 'Valor (R$)', 'LTR',
        'Descrição Evento']

def row(status, evt='', ltr='', val='1000,00', conta='123'):
    return {'Status': status, 'Data': '', 'Hora': '', 'sNumConta': conta,
            'Valor (R$)': val, 'LTR': ltr, 'Descrição Evento': evt}

DERIV = 'OPERACAO DE DERIVATIVOS-ACME COMERCIAL LTDA'

CASES = [
    # (label, linhas, quantos registros devem sair)
    ('deriv Sucesso entra',            [row('Sucesso', evt=DERIV)],            1),
    ('deriv Erro NAO entra',           [row('Erro', evt=DERIV)],               0),
    ('deriv Rejeitado NAO entra',      [row('Rejeitada', evt=DERIV)],          0),
    ('deriv status vazio NAO entra',   [row('', evt=DERIV)],                   0),
    ('deriv LMA-COMM-BR Sucesso',      [row('Sucesso', evt='LMA-COMM-BR XPTO')], 1),
    ('deriv LMA-COMM-BR Erro',         [row('Erro', evt='LMA-COMM-BR XPTO')],  0),
    ('LTR0004 Sucesso entra',          [row('Sucesso', ltr='LTR0004')],        1),
    ('LTR0004 Erro NAO entra',         [row('Erro', ltr='LTR0004')],           0),
    ('LTR0005 Sucesso entra',          [row('Sucesso', ltr='LTR0005')],        1),
    ('LTR desconhecido NAO entra',     [row('Sucesso', ltr='LTR9999')],        0),
    ('sem evento e sem LTR NAO entra', [row('Sucesso')],                       0),
    ('acento/caixa: SUCESSO entra',    [row('SUCESSO', evt=DERIV)],            1),
    ('mistura 3 linhas -> 2',          [row('Sucesso', evt=DERIV),
                                        row('Erro',    evt=DERIV),
                                        row('Sucesso', ltr='LTR0004')],        2),
]

fails = []
for label, rows, exp in CASES:
    got = len(_cli_spb(rows, COLS))
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + '%-34s got=%d exp=%d' % (label, got, exp))
    if not ok:
        fails.append(label)

# direcao/sinal preservados
d = _cli_spb([row('Sucesso', evt=DERIV)], COLS)[0]
pay_ok = d['pay_receive'] == 'Pay' and d['value'] < 0 and d['client'] == 'ACME COMERCIAL LTDA'
print(('  ok  ' if pay_ok else ' FAIL ') + 'deriv continua Pay/negativo/nome limpo  %r' % (d,))
if not pay_ok:
    fails.append('deriv shape')

b = _cli_spb([row('Sucesso', ltr='LTR0005')], COLS)[0]
rec_ok = b['pay_receive'] == 'Receive' and b['value'] > 0 and b.get('bank') is True
print(('  ok  ' if rec_ok else ' FAIL ') + 'LTR0005 continua Receive/positivo/bank  %r' % (b,))
if not rec_ok:
    fails.append('ltr shape')

# MGT usa o mesmo parser e o mesmo filtro
m = _cli_spb([row('Erro', evt=DERIV)], COLS, mgt=True)
mgt_ok = len(m) == 0 and len(_cli_spb([row('Sucesso', evt=DERIV)], COLS, mgt=True)) == 1
print(('  ok  ' if mgt_ok else ' FAIL ') + 'MGT filtra igual ao JPM')
if not mgt_ok:
    fails.append('mgt')

# header ausente -> cai na posicao 0 (coluna A), que e o que o usuario descreveu
POS = ['A', 'B', 'C', 'sNumConta', 'Valor (R$)', 'LTR', 'Descrição Evento']
def prow(status, evt='', ltr=''):
    return {'A': status, 'B': '', 'C': '', 'sNumConta': '1', 'Valor (R$)': '10,00',
            'LTR': ltr, 'Descrição Evento': evt}
pos_ok = (len(_cli_spb([prow('Sucesso', evt=DERIV)], POS)) == 1
          and len(_cli_spb([prow('Erro', evt=DERIV)], POS)) == 0)
print(('  ok  ' if pos_ok else ' FAIL ') + 'sem header "Status" usa a coluna A (idx 0)')
if not pos_ok:
    fails.append('fallback col A')

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS: %r' % fails))
sys.exit(1 if fails else 0)
