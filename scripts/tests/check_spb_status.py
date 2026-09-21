"""Col A ('Status') = 'Sucesso' e o unico que entra na recon, nas TRES trilhas
do HistoricoMensagens (JPM e MGT): cliente de derivativos, cliente por STR
(a via do BACEN) e interbancario LTR.

A trilha do STR entrou em 21/09/2026. Ela nao casava com nenhuma das outras
duas -- nem `Derivativos`/`LMA-COMM-BR` na descricao, nem `LTR000x` no codigo --
e caia no `continue` mudo do fim do laco: a perna do cliente nao existia, e a
operacao aparecia na tela como Pending Payment com `Client Value` VAZIO, com a
linha paga e `Sucesso` no arquivo o tempo todo. Foi um swap de R$ 253.194,78 da
SUZANO.

Ela exige o CODIGO e o PREFIXO juntos, e e isso que este guarda prende: o
`STR0007` sozinho e a mensagem de transferencia do SPB e carrega mais coisa que
liquidacao de cliente; o `STS - ` sozinho nao diz por qual via foi. Casar por um
so criaria perna de cliente SEM DINHEIRO atras -- que ou casa com uma perna JPM
legitima, escondendo uma quebra de verdade, ou vira pendencia fantasma.
"""
import sys
import os
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))   # scripts/tests/ -> raiz do repo
sys.path.insert(0, ROOT)

# Fora do Windows o share tem de ser absoluto para o `Config` importar (§8), e o
# `recon_payrec` pergunta a raiz a ele desde que deixou de escrever o `I:\` fixo.
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.check-share'))
from apps.pages.recon_payrec import _cli_spb

COLS = ['Status', 'Data', 'Hora', 'sNumConta', 'Valor (R$)', 'LTR',
        'Descrição Evento']

def row(status, evt='', ltr='', val='1000,00', conta='123'):
    return {'Status': status, 'Data': '', 'Hora': '', 'sNumConta': conta,
            'Valor (R$)': val, 'LTR': ltr, 'Descrição Evento': evt}

DERIV = 'OPERACAO DE DERIVATIVOS-ACME COMERCIAL LTDA'
STS = 'STS - SUZANO SA'                     # a linha real do relato

CASES = [
    # (label, linhas, quantos registros devem sair)
    ('deriv Sucesso entra',            [row('Sucesso', evt=DERIV)],            1),
    ('deriv Erro NAO entra',           [row('Erro', evt=DERIV)],               0),
    ('deriv Rejeitado NAO entra',      [row('Rejeitada', evt=DERIV)],          0),
    ('deriv status vazio NAO entra',   [row('', evt=DERIV)],                   0),
    ('deriv LMA-COMM-BR Sucesso',      [row('Sucesso', evt='LMA-COMM-BR XPTO')], 1),
    ('deriv LMA-COMM-BR Erro',         [row('Erro', evt='LMA-COMM-BR XPTO')],  0),
    ('STR0007 + STS Sucesso entra',    [row('Sucesso', evt=STS, ltr='STR0007')], 1),
    ('STR0007 + STS Erro NAO entra',   [row('Erro',    evt=STS, ltr='STR0007')], 0),
    # Os dois sao exigidos JUNTOS -- e o que impede perna sem dinheiro atras.
    ('STR0007 SEM o prefixo STS',      [row('Sucesso', evt='PAGAMENTO XPTO',
                                            ltr='STR0007')],                   0),
    ('prefixo STS SEM o STR0007',      [row('Sucesso', evt=STS, ltr='LTR9999')], 0),
    ('STS no MEIO do nome nao vale',   [row('Sucesso', evt='ACME STS - LTDA',
                                            ltr='STR0007')],                   0),
    ('STR0007 sem contraparte',        [row('Sucesso', evt='STS - ',
                                            ltr='STR0007')],                   0),
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

# O STR de cliente sai com o NOME limpo e no formato da trilha 1 -- e NAO como
# `bank`: ele tem contraparte, entao casa por nome, e um `bank=True` o faria
# casar por VALOR com tolerancia de R$20 contra qualquer perna do dia.
t = _cli_spb([row('Sucesso', evt=STS, ltr='STR0007', val='253194,77')], COLS)[0]
sts_ok = (t['pay_receive'] == 'Pay' and t['value'] == -253194.77
          and t['client'] == 'SUZANO SA' and not t.get('bank')
          and not t.get('drop_if_unmatched'))
print(('  ok  ' if sts_ok else ' FAIL ') + 'STR0007 Pay/negativo/nome limpo/nao-bank  %r' % (t,))
if not sts_ok:
    fails.append('sts shape')

# Hifen DENTRO da razao social sobrevive: so o prefixo sai.
h = _cli_spb([row('Sucesso', evt='STS - CIA BRASILEIRA - FILIAL SP',
                  ltr='STR0007')], COLS)[0]
hif_ok = h['client'] == 'CIA BRASILEIRA - FILIAL SP'
print(('  ok  ' if hif_ok else ' FAIL ') + 'hifen no nome sobrevive  %r' % (h['client'],))
if not hif_ok:
    fails.append('sts hifen')

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
