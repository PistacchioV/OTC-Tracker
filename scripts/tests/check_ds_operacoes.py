#!/usr/bin/env python3
"""check_ds_operacoes.py — o filtro do arquivo de operações do Daily Settlement.

Duas colunas decidem o que entra no `operacoes-jpm.json`: a CONTA e o TIPO DE
TÍTULO. E o que entra alcança muito mais do que o card: este é o JSON que a
página Operations B3 lê, e é dele que saem a mensageria, os avisos de liquidação
e os cards de reconciliação. Uma conta que não passa por aqui não existe para
nenhum deles — some sem erro nenhum, e a tela mostra a menos.

O outro jeito de quebrar isto é sutil: a coluna dos filtros do `_DS_IMPORTS` é
**1-based** (`_ds_cell(row, col - 1)`), enquanto a do `_CETIP_BEHAVIOUR`, logo
acima no mesmo arquivo, é 0-based. Trocar um pelo outro filtra pela coluna
vizinha, e o resultado é um arquivo vazio ou uma lista com o que não devia estar
lá — nos dois casos sem exceção nenhuma.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.tmp-share'))

from apps.pages import routes as R          # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    print(('  ok  ' if ok else ' FAIL ') + label)
    if not ok:
        print('        esperado: %r' % (want,))
        print('        veio:     %r' % (got,))
        fails.append(label)


# A ordem das colunas é a do arquivo real (header na linha 5): Conta é a 2ª e
# Tipo Título a 10ª — os dois números que os filtros do spec citam.
HEADER = ['Data', 'Conta', 'Tipo Operação', 'C/V', 'Título', 'Tipo de Regime',
          'Data Vencimento', 'Valor', 'Modalidade Liquidação', 'Tipo Título', 'Status']


def linha(conta, tipo_titulo):
    r = ['-'] * len(HEADER)
    r[1] = conta
    r[9] = tipo_titulo
    return r


def arquivo(linhas):
    rows = [['c1'], ['c2'], ['c3'], ['c4'], HEADER] + linhas
    return '\n'.join('\t'.join(map(str, r)) for r in rows).encode('latin-1')


print('\n== 1. o spec ==')
spec = R._opb3_spec()
check('o spec existe', spec is not None, True)
check('e alimenta a página Operations B3', spec.get('opb3'), True)
contas = next(f[2] for f in spec['filters'] if f[0] == 'digits')
# 73760.00-9 é a conta PRÓPRIA e 73760.20-5 a de CLIENTE 2 (ver `b3-accounts`).
# A de CLIENTE 1 (73760.10-2) fica de fora, como sempre esteve.
check('as contas do Banco que entram', contas, {'73760009', '73760205'})
check('a coluna da conta é a 2ª (1-based)',
      next(f[1] for f in spec['filters'] if f[0] == 'digits'), 2)

print('\n== 2. o que passa e o que não passa ==')
recs, total = R._ds_process(arquivo([
    linha('73760.00-9', 'TER'),
    linha('73760.20-5', 'SWAP'),
    linha('7376020 5', 'OPC'),          # mesma conta, outra pontuação
    linha('73760.10-2', 'TER'),         # CLIENT 1 — fora
    linha('04880.00-6', 'SWAP'),        # MGT — é o outro spec
    linha('73760.20-5', 'CDB'),         # tipo de título fora da lista
]), spec)
check('leu as seis linhas de dado', total, 6)
check('manteve três', len(recs), 3)
check('a própria entra', [r for r in recs if r['Conta'] == '73760.00-9'] != [], True)
check('a de cliente 2 entra', [r for r in recs if r['Conta'] == '73760.20-5'] != [], True)
# A conta chega ora `73760.20-5`, ora `7376020 5`: a comparação é por DÍGITOS, e
# comparar string deixaria metade do arquivo de fora em silêncio.
check('e entra escrita sem pontuação',
      [r for r in recs if r['Conta'] == '7376020 5'] != [], True)
check('a de cliente 1 fica de fora',
      [r for r in recs if r['Conta'] == '73760.10-2'], [])
check('a da MGT fica de fora (é o outro spec)',
      [r for r in recs if r['Conta'] == '04880.00-6'], [])
check('e o tipo de título de fora da lista também',
      [r for r in recs if r['Tipo Título'] == 'CDB'], [])

print('\n== 3. o spec da MGT continua o dele ==')
mgt = next((s for s in R._DS_IMPORTS if s.get('key') == 'operacoes-mgt'), None)
check('o spec da MGT existe', mgt is not None, True)
check('e só a conta da MGT', next(f[2] for f in mgt['filters'] if f[0] == 'digits'),
      {'04880006'})
recs_mgt, _ = R._ds_process(arquivo([linha('04880.00-6', 'SWAP'),
                                     linha('73760.20-5', 'SWAP')]), mgt)
check('o arquivo da MGT não leva conta do Banco', len(recs_mgt), 1)

print('\nFALHAS: %d' % len(fails))
sys.exit(1 if fails else 0)
