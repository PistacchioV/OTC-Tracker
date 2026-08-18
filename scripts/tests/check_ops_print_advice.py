"""Print Advice do Other Products: o botao do Summary e o BLOCKER do valor vazio.

Duas coisas, e as duas erram em SILENCIO:

1. **Um botao no Settlement Summary gera as TRES familias** (Swap, NDF
   Commodities e Opcao) na mesma data. Antes era abrir tres telas e clicar em
   tres botoes — e bastava esquecer uma para o cliente ficar sem o aviso daquele
   produto, sem nada na tela dizendo.

2. **Contraparte com valor nao identificado NAO vira aviso.** As colunas de
   resultado (bruto e liquido) SAO o aviso: e por elas que o cliente paga ou
   recebe. Em branco, o documento nao diz quanto — mas parece completo, e vai
   assinado. Pior desfecho possivel.

   O corte e da CONTRAPARTE INTEIRA, e nao da linha furada: o aviso e netado por
   contraparte (e por commodity, para quem esta no `ndfc-advice-split`), entao
   tirar so a linha mandaria um total que nao fecha com as operacoes do cliente.

   E o bloqueio TEM de aparecer na tela — uma contraparte que some do lote sem
   dizer por que e uma contraparte que ninguem vai cobrar.

Nao encosta em rede nem em dado real: as linhas sao sinteticas.
"""
import io
import json
import base64
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R                           # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label
          + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding='utf-8', errors='ignore').read()


print('== 1. As colunas exigidas sao o resultado BRUTO e o LIQUIDO ==')
# O IR fica de fora de proposito: ele e derivado, e zero e um valor legitimo.
check('as tres familias tem par de colunas',
      {k: len(v) for k, v in sorted(R._OPSADV_REQUIRED.items())},
      {'ndf': 2, 'option': 2, 'swap': 2})
for fam, headers in (('ndf', R._ndfadv_email_headers()),
                     ('option', R._optadv_email_headers()),
                     ('swap', R._swadv_email_headers(False))):
    faltando = [c for c in R._OPSADV_REQUIRED[fam] if c not in headers]
    # Coluna que nao existe no cabecalho e regra que nunca confere nada: o
    # blocker deixaria passar o aviso vazio, calado.
    check('%-6s: as colunas exigidas existem no cabecalho do aviso' % fam, faltando, [])
# As duas variantes do swap (Vencimento / Pagamento de Premio) tem as colunas de
# valor no MESMO lugar — e por isso o indice de uma serve para as duas.
h0, h1 = R._swadv_email_headers(False), R._swadv_email_headers(True)
check('swap: as duas variantes concordam nos indices de valor',
      [h0.index(c) for c in R._OPSADV_REQUIRED['swap']],
      [h1.index(c) for c in R._OPSADV_REQUIRED['swap']])


print('\n== 2. O corte e da CONTRAPARTE inteira, nao da linha ==')
H = R._ndfadv_email_headers()
BASE = ['B3', 'CONF', '01/01/2026', 'CACAU(CCU)', '14/08/2026', '14/08/2026', '100']


def ndf_row(cp, apurado, liquido):
    return {'counterparty': cp, 'lob': 'COMMODITY',
            'cells': list(BASE) + [apurado, '0,00', liquido]}


rows = [ndf_row('BAYER S.A.', 'R$ 404.997,20', 'R$ 404.997,20'),
        ndf_row('MONDELEZ BRASIL LTDA', '', ''),              # a linha furada
        ndf_row('MONDELEZ BRASIL LTDA', 'R$ 240.104,66', 'R$ 240.104,66'),   # boa
        ndf_row('NUTRADE COMERCIAL EXPORTADORA LTDA', 'R$ 473.392,42', 'R$ 473.392,42')]
kept, blocked = R._opsadv_block_incomplete('ndf', rows, H)
check('a contraparte com furo sai INTEIRA, inclusive a linha boa',
      sorted({r['counterparty'] for r in kept}),
      ['BAYER S.A.', 'NUTRADE COMERCIAL EXPORTADORA LTDA'])
check('quem esta completo continua', len(kept), 2)
check('o bloqueio diz contraparte, produto e colunas',
      [(b['counterparty'], b['product'], b['columns']) for b in blocked],
      [('MONDELEZ BRASIL LTDA', 'NDF Commodities',
        ['Resultado Apurado (R$)', 'Resultado Líquido (R$)'])])
check('e conta as linhas furadas', blocked[0]['rows'], 1)
# Espaco em branco nao e valor: a celula ' ' e tao vazia quanto ''.
kept2, b2 = R._opsadv_block_incomplete('ndf', [ndf_row('X', '   ', 'R$ 1,00')], H)
check('celula so com espaco tambem bloqueia', (len(kept2), len(b2)), (0, 1))
check('nada furado nao bloqueia nada',
      R._opsadv_block_incomplete('ndf', [ndf_row('Y', 'R$ 1,00', 'R$ 1,00')], H)[1], [])
# O IR vazio NAO bloqueia: ele e derivado, e a coluna nao esta em _OPSADV_REQUIRED.
so_ir = {'counterparty': 'Z', 'lob': '', 'cells': list(BASE) + ['R$ 1,00', '', 'R$ 1,00']}
check('IR em branco NAO bloqueia (ele e derivado, e zero e legitimo)',
      R._opsadv_block_incomplete('ndf', [so_ir], H)[1], [])
# Cabecalho renomeado: o blocker avisa e deixa passar, em vez de cortar pelo
# indice errado — cortar a contraparte errada seria pior do que nao cortar.
kept3, b3 = R._opsadv_block_incomplete('ndf', [ndf_row('W', '', '')], ['Outra Coisa'])
check('cabecalho sem as colunas nao corta ninguem', (len(kept3), len(b3)), (1, 0))

print('\n== 3. O swap usa as colunas DELE ==')
srow = {'counterparty': 'X LTDA', 'lob': '',
        'cells': ['C1', '01/01', '01/02', '30', '100', 'I', 'C', 'I', 'C', '', '15%', '0', '']}
kept4, b4 = R._opsadv_block_incomplete('swap', [srow], h0)
check('Resultado Bruto / Valor Líquido em branco bloqueiam',
      [(b['product'], b['columns']) for b in b4],
      [('Swap', ['Resultado Bruto', 'Valor Líquido'])])
check('e a linha nao vai para o gerador', kept4, [])

print('\n== 4. O disclaimer atravessa os dois formatos de resposta ==')
# Ate 2 rascunhos a resposta e JSON (o `blocked` vai no corpo); 3+ vem um .zip
# binario, e o resumo tem de viajar no cabecalho.
hdr = R._opsadv_blocked_header(blocked)
volta = json.loads(base64.b64decode(hdr).decode('utf-8'))
check('base64 de UTF-8: o acento do nome volta inteiro',
      volta[0]['counterparty'], 'MONDELEZ BRASIL LTDA')
check('e as colunas tambem', volta[0]['columns'][1], 'Resultado Líquido (R$)')

SRC = read('apps/pages/routes.py')
print('\n== 5. As QUATRO entradas passam pelo blocker ==')
for fn, fam in (('api_swap_settlement_advice_emails', 'swap'),
                ('api_ndf_settlement_advice_emails', 'ndf'),
                ('api_option_settlement_advice_emails', 'option')):
    bloco = SRC.split('def %s' % fn, 1)[1].split('\n@blueprint', 1)[0]
    check('%s bloqueia antes de gerar' % fn,
          "_opsadv_block_incomplete('%s'" % fam in bloco, True)
    check('   e devolve o `blocked` na resposta JSON', "'blocked': blocked" in bloco, True)
    check('   e no cabecalho do .zip', "_opsadv_blocked_header(blocked)" in bloco, True)
bloco = SRC.split('def _opsadv_family_drafts', 1)[1].split('\n@blueprint', 1)[0]
check('o Summary usa o MESMO blocker das tres telas',
      bloco.count('_opsadv_block_incomplete'), 3)

print('\n== 6. O botao do Summary e as tres familias ==')
check('a rota existe',
      "@blueprint.route('/api/other-products-summary/print-advice'" in SRC, True)
check('e cobre as tres familias', R._OPSADV_FAMILIES, ('swap', 'ndf', 'option'))
TPL = read('apps/templates/pages/other-products-summary.html')
check('o botao esta na toolbar do Summary', 'id="opsPrintAdvice"' in TPL, True)
check('   com data-lang', 'data-lang="ops-print-advice"' in TPL, True)
check('   e a pagina carrega o helper do disclaimer',
      'js/ops-advice-blocked.js' in TPL, True)
# O helper e um arquivo so: quatro copias da frase divergiriam na primeira
# correcao de texto.
for nome in ('other-products-swap-settlement-advice', 'other-products-ndf-settlement-advice',
             'other-products-option-settlement-advice'):
    check('%s carrega o helper' % nome,
          'js/ops-advice-blocked.js' in read('apps/templates/pages/%s.html' % nome), True)
HELP = read('apps/static/js/ops-advice-blocked.js')
check('o helper le os DOIS caminhos (corpo JSON e cabecalho do zip)',
      ['function html(' in HELP, 'function fromHeader(' in HELP], [True, True])
for lang in ('en', 'br', 'es'):
    tr = json.load(io.open(os.path.join(ROOT, 'apps', 'static', 'data', 'translations',
                                        lang + '.json'), encoding='utf-8'))
    check('%s.json tem o rotulo do botao' % lang, 'ops-print-advice' in tr, True)

print('\n== 7. OTM Settlements: Pending primeiro, depois Cpty Name ==')
# A pagina e uma fila de trabalho: quem abre quer ver o que falta. Com o Ok
# misturado no meio, a pendencia some numa lista de duzentas linhas.
OTM = read('apps/static/js/pages/otm-settlements.js')
check('a ordem padrao comeca pelo Status', "var defaultOrder = [[2, 'asc']];" in OTM, True)
check('   e segue por Cpty Name e Trade Id',
      ["defaultOrder.push([iCpty + 3, 'asc'])" in OTM,
       "defaultOrder.push([iTrade + 3, 'asc'])" in OTM], [True, True])
# Ordenar pelo TEXTO do badge daria uma ordem por idioma; pelo HTML, pela classe
# do CSS. O rank sai do status CRU, no data-st.
check('o badge carrega o status cru no data-st', OTM.count('data-st="') >= 3, True)
check('e a ordenacao e ortogonal ao display (so o sort ve o rank)',
      "(type === 'sort' || type === 'type') ? statusRank(d) : d" in OTM, True)
m = re.search(r'_ST_RANK = \{([^}]*)\}', OTM)
check('Pending vem antes de New, e Ok por ultimo',
      [p.strip() for p in (m.group(1) if m else '').split(',') if p.strip()],
      ['pending: 0', 'new: 1', 'ok: 2'])


print('\n== 8. O assunto do aviso leva CONTRAPARTE + CNPJ ==')
# O nome sozinho nao identifica: o mesmo grupo tem varias entidades com nomes
# quase iguais ("Mondelez Brasil" x "Mondelez Brasil Norte Nordeste"), e quem
# arquiva o aviso casa pelo cadastro, que e por CNPJ.
from apps.pages import otc_emails as E                      # noqa: E402
check('nome + CNPJ mascarado',
      E._subject_cpty('MONDELEZ BRASIL LTDA', '12345678000199'),
      'MONDELEZ BRASIL LTDA 12.345.678/0001-99')
check('ja mascarado no cadastro nao duplica a mascara',
      E._subject_cpty('MONDELEZ BRASIL LTDA', '12.345.678/0001-99'),
      'MONDELEZ BRASIL LTDA 12.345.678/0001-99')
# `_fmt_cnpj` devolve o texto CRU quando nao sao 14 digitos: um assunto
# terminando num pedaco de numero seria pior do que nao ter numero nenhum.
check('documento incompleto NAO entra no assunto',
      [E._subject_cpty('BAYER S.A.', '123'), E._subject_cpty('BAYER S.A.', ''),
       E._subject_cpty('BAYER S.A.', None)],
      ['BAYER S.A.'] * 3)
# Os TRES avisos usam o helper — um assunto que nao leva o CNPJ e o aviso que o
# arquivo do cliente nao vai casar.
SRCE = read('apps/pages/otc_emails.py')
# O `)` no fim e o que separa as CHAMADAS da linha do `def` (que termina em `:`).
check('os tres assuntos de liquidacao passam pelo helper',
      SRCE.count('_subject_cpty(contraparte, taxid))'), 3)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
