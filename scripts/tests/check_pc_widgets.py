"""Pending Confirmation: os cards do topo (as seis faixas + o Total).

A tela tinha seis cards de faixa de aging e ganhou um setimo, de Total. Duas
coisas ficam presas aqui:

  1. cada card diz a QUE faixa pertence, pelo data-pc-band. O JS lia a posicao no
     DOM (RANGE_ORDER[i]) e casava com o indice do querySelectorAll — inserir um
     card no meio, ou mover um, deslocava em silencio os numeros de todos os
     seguintes. Nao dava erro nenhum: os cards continuavam preenchidos, com o
     numero do vizinho.

  2. o Total soma o que os SEIS cards somam, e nada alem disso. Ele conta dentro
     do mesmo teste de faixa: uma linha sem Aging nao entra em faixa nenhuma e
     tambem nao entra no total. Contar essas linhas so no total deixaria o card
     fora da soma dos outros seis, e a primeira leitura de quem olha a tela e
     somar os cards na mao.

Nao encosta em dado real: le o template e roda a contagem do proprio arquivo no
JavaScriptCore, com linhas sinteticas no lugar da DataTable.
"""
import io
import json
import os
import re
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
JSC = '/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc'

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


HTML = io.open(os.path.join(ROOT, 'apps/templates/pages/pending-confirmation.html'),
               encoding='utf-8', errors='ignore').read()

print('== 1. cada card se identifica pela faixa, nao pela posicao ==')
bands = re.findall(r'data-pc-band="([^"]+)"', HTML)
ORDER = ['u10', 'r10', 'r20', 'r30', 'r60', 'r90', 'total']
check('sete cards, na ordem das faixas + Total', bands, ORDER)
check('nenhuma faixa repetida', len(set(bands)), 7)
# O JS le o atributo; se voltar a ler o indice, este teste cai.
js = HTML.split('function updateWidgets()', 1)[1].split('\n    }\n', 1)[0]
check('o JS casa pelo atributo', "getAttribute('data-pc-band')" in HTML, True)
check('e nao pelo indice do forEach', 'RANGE_ORDER[i]' in HTML, False)
check('o seletor exige o atributo',
      "'.pending-widgets-row .card-body[data-pc-band]'" in HTML, True)
order_js = re.search(r"var RANGE_ORDER = \[([^\]]+)\]", HTML).group(1)
check('o RANGE_ORDER tem as mesmas sete',
      [x.strip().strip("'") for x in order_js.split(',')], ORDER)

print('\n== 2. o card de Total e visualmente outra coisa ==')
# A rampa das faixas vai de verde a vermelho; o Total nao e uma severidade a
# mais, e a soma delas. Se ele entrar na rampa, vira uma setima faixa aos olhos.
ramp = re.findall(r"pending-widget-value\"[^>]*style=\"color: (#[0-9a-fA-F]{6})", HTML)
tot = HTML.split('data-pc-band="total"', 1)[1]
tot_color = re.search(r'pending-widget-value" style="color: (#[0-9a-fA-F]{6})', tot).group(1)
check('a cor do Total nao repete nenhuma faixa',
      [c for c in ramp if c.lower() == tot_color.lower()], [tot_color])
check('   (e a unica ocorrencia e o proprio Total)', tot_color.lower(), '#0066cc')
check('o Total tem a classe que muda a moldura', 'col col-pending-total' in HTML, True)
check('   e a moldura esta declarada', '.col-pending-total .card' in HTML, True)
check('o icone do Total nao e de relogio', 'ti-sum' in tot.split('</h3>', 1)[0], True)

print('\n== 3. o layout comporta os sete ==')
# O Bootstrap nao tem row-cols-7 (o grid dele para em 6): a largura vem do CSS
# da propria pagina. Deixar o row-cols-xxl-6 no markup poria os dois brigando.
row_div = re.search(r'<div class="row [^"]*pending-widgets-row"', HTML).group(0)
check('o row-cols-xxl-6 saiu do markup', 'row-cols-xxl-6' in row_div, False)
check('a largura de 1/7 esta no CSS', 'width: 14.2857%' in HTML, True)
check('a entrada escalonada cobre o setimo',
      '.pending-widgets-row .col:nth-child(7)' in HTML, True)

print('\n== 4. a contagem: o Total fecha com a soma das faixas ==')
if not os.path.exists(JSC):
    print('  --   jsc ausente (so macOS): secao pulada')
else:
    # Roda a contagem REAL do arquivo, trocando so a fonte das linhas.
    body = HTML.split('function updateWidgets() {', 1)[1]
    body = body.split('// Update widget cards in DOM order', 1)[0] if \
        '// Update widget cards in DOM order' in body else \
        body.split('// Cada card diz a que faixa pertence', 1)[0]
    band_fn = HTML.split('function _pcAgingBand(days) {', 1)[1].split('\n    }', 1)[0]
    src = '''
    function _pcStrip(v) { return v == null ? '' : String(v).trim(); }
    function _pcAgingBand(days) {%s
    }
    var table = { rows: function() { return { data: function() { return {
        each: function(cb) { ROWS.forEach(cb); } }; } }; } };
    function updateWidgets() {%s
        return counts;
    }
    ''' % (band_fn, body)
    # 12 colunas: 6 = Aging, 11 = Pending Status.
    def row(aging, pend):
        r = [''] * 12
        r[6] = aging
        r[11] = pend
        return r

    rows = [
        row('3', 'Pending FO'), row('9', 'Pending FO'),          # u10 = 2
        row('12', 'Pending MO'),                                  # r10 = 1
        row('25', 'Pending Legal'), row('29', 'Pending Legal'),   # r20 = 2
        row('45', 'Pending Original'),                            # r30 = 1
        row('61', 'Pending OTC'), row('89', 'Pending OTC'),       # r60 = 2
        row('120', 'Pending POA'),                                # r90 = 1
        row('7', 'Exception Digital Fep Web'),   # resolvida: nao conta em lugar nenhum
        row('', 'Pending FO'),                   # sem aging: sem faixa, sem total
        row('x', 'Pending FO'),                  # aging ilegivel: idem
    ]
    prog = 'var ROWS = %s;\nvar c = updateWidgets();\nprint(JSON.stringify(c));' % json.dumps(rows)
    out = subprocess.run([JSC, '-e', src + prog], capture_output=True, text=True)
    if out.returncode != 0:
        check('a contagem roda no jsc', out.stderr.strip()[:200], '')
    else:
        c = json.loads(out.stdout.strip())
        check('cada faixa conta o seu',
              [c[b]['total'] for b in ORDER[:6]], [2, 1, 2, 1, 2, 1])
        check('o Total e a soma das faixas',
              c['total']['total'], sum(c[b]['total'] for b in ORDER[:6]))
        check('   e vale 9 (as tres linhas de fora nao entram)', c['total']['total'], 9)
        # A quebra por tipo tambem fecha, linha a linha do card.
        for t in ('fo', 'mo', 'legal', 'orig', 'otc', 'poa', 'ds', 'mofo', 'sa', 'others'):
            check('a linha %s fecha' % t,
                  c['total'][t], sum(c[b][t] for b in ORDER[:6]))
        check('   e a soma das dez linhas da o total do card',
              sum(c['total'][t] for t in ('ds', 'fo', 'legal', 'mo', 'mofo',
                                          'orig', 'otc', 'poa', 'sa', 'others')),
              c['total']['total'])
        # A linha "Exception *" e resolvida — se ela voltar a contar, o total
        # deixa de bater com a tabela e com o Excel.
        # Ha quatro linhas 'Pending FO' no lote: duas com aging valido, uma
        # Exception e duas sem aging. So as duas primeiras contam.
        check('a Exception fica de fora do total', c['total']['fo'], 2)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
