"""NDF Summary > Trade Level: a precisao do Forward Rate e do Fixing Rate.

O SETTLEMENT.xlsx traz a taxa forward com todas as casas que o sistema de origem
calculou. A tela mostrava SEIS, fixas — e o Fixing Rate, que sai de
`forward +/- settlement/notional`, era calculado com o valor CHEIO e impresso
tambem com seis. O resultado: a taxa na tela nao explicava o fixing ao lado dela,
e a diferenca que a mesa precisa conferir ficava escondida no arredondamento.

O que este teste prende:

  1. o forward mostrando TODAS as casas do arquivo. Voltar a um `'{:.6f}'` nao
     quebra nada — so esconde os digitos de novo, silenciosamente.

  2. o piso de OITO (pedido da mesa). Uma taxa curta ('5.4') nao pode encolher
     para '5.4' na coluna: a coluna inteira tem de ler como taxa, nao como
     numero solto. Quando o arquivo traz so seis casas, as duas ultimas saem
     zero — e esse zero e informacao: diz que a precisao que falta esta na
     ORIGEM, nao na tela.

  3. o fixing acompanhando a precisao do forward que o gerou. Menos casas
     esconderia a diferenca que a conta produziu; mais inventaria digitos que
     nenhuma das entradas tem.

  4. o valor CRU intacto. O que mudou e a exibicao — o calculo sempre usou a
     precisao inteira, e o teste confirma que continua usando.

  5. a largura da coluna. Sem `min-width`/`nowrap` a taxa longa quebra em duas
     linhas, e uma taxa partida ao meio parece um valor diferente — pior que a
     arredondada que se acabou de corrigir.

Nao encosta em dado real: chama as funcoes de formatacao e le o template.
"""
import io
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding='utf-8', errors='ignore').read()


print('== 1. o forward mostra o que o arquivo tem ==')
F = R._ndfc_fmt_fwd
check('13 casas saem as 13', F('5.4321987654321'), '5.4321987654321')
check('7 casas sobem ao piso', F('1234.5678901'), '1234.56789010')
check('9 casas saem as 9', F('5.123456789'), '5.123456789')
# Piso de OITO (pedido da mesa): quando o arquivo traz so seis, as duas ultimas
# saem zero — e esse zero e informacao, diz que a precisao que falta esta na
# ORIGEM e nao na tela.
check('6 casas sobem ao piso de 8', F('5.432199'), '5.43219900')
check('taxa curta tambem', F('5.4'), '5.40000000')
check('inteiro tambem', F('5'), '5.00000000')
check('e o zero a esquerda nao se perde', F('0.05'), '0.05000000')
check('o piso e 8', R._NDFC_FWD_MIN_DEC, 8)
# O arquivo as vezes vem com virgula decimal.
check('virgula decimal conta igual', F('5,4321987654321'), '5.4321987654321')
check('texto nao numerico passa inteiro', F('n/a'), 'n/a')
check('vazio continua vazio', F(''), '')

print('\n== 2. o fixing acompanha o forward ==')
LP = {'pos': 'COMPRADOR'}


def fixing(fwd, settle='1000.00', notional='1000000.00'):
    return R._ndfc_strike_calc({'VL_FORWARD_RATE': fwd,
                                '[PROD] Cockpit.SETTLEMENT': settle,
                                'VL_NOTIONAL_FC': notional}, LP, False)


check('forward com 13 casas -> fixing com 13', fixing('5.4321987654321'), '5.4331987654321')
check('forward com 6 -> os dois no piso de 8', fixing('5.432199'), '5.43319900')
check('forward curto -> os dois no piso', fixing('5.4'), '5.40100000')
# A direcao da conta nao mudou: vendedor subtrai.
check('vendedor subtrai',
      R._ndfc_strike_calc({'VL_FORWARD_RATE': '5.432199',
                           '[PROD] Cockpit.SETTLEMENT': '1000.00',
                           'VL_NOTIONAL_FC': '1000000.00'}, {'pos': 'VENDEDOR'}, False),
      '5.43119900')
check('cross-currency segue sem calcular', fixing_cross := R._ndfc_strike_calc(
      {'VL_FORWARD_RATE': '5.432199'}, LP, True), '-')

print('\n== 3. o valor CRU nao mudou ==')
# O calculo sempre usou a precisao inteira; o que mudou foi so a exibicao. Se o
# parse passasse a ler a taxa arredondada, o fixing pioraria em vez de melhorar.
check('o parse le todas as casas', R._ndfc_valnum('5.4321987654321'), 5.4321987654321)
check('   inclusive com virgula', R._ndfc_valnum('5,4321987654321'), 5.4321987654321)
SRC = read('apps/pages/routes.py')
blk = SRC.split('def _ndfc_strike_calc')[1].split('\ndef ')[0]
check('o calculo le o campo cru, nao a celula formatada',
      "_ndfc_valnum(rec.get('VL_FORWARD_RATE', ''))" in blk, True)
check('e nao ha mais teto de 6 casas na exibicao',
      "'{:.6f}'.format(float(s" in SRC, False)

print('\n== 4. a coluna cabe o numero ==')
HTML = read('apps/templates/pages/ndf-summary.html')
# As posicoes sao POSICIONAIS: contar os <th> da primeira linha do cabecalho e a
# unica forma de saber que o CSS aponta para a coluna certa.
head = HTML.split('id="ops-trade-table"', 1)[1].split('<tr class="ops-filter">', 1)[0]
pos = {}
for i, m in enumerate(re.finditer(r'<th[^>]*>(.*?)</th>', head, re.S), start=1):
    pos[re.sub(r'<[^>]+>', '', m.group(1)).strip()] = i
check('FORWARD RATE e a 12a coluna', pos.get('FORWARD RATE'), 12)
check('FIXING RATE e a 15a coluna', pos.get('FIXING RATE'), 15)
check('e o CSS mira essas duas',
      '#ops-trade-table th:nth-child(12), #ops-trade-table td:nth-child(12),' in HTML and
      '#ops-trade-table th:nth-child(15), #ops-trade-table td:nth-child(15) {' in HTML, True)
check('com nowrap para a taxa nao partir ao meio',
      'min-width: 165px; white-space: nowrap;' in HTML, True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
