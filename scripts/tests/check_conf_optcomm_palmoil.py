"""Confirmacao de Opcao de Commodities de PALM OIL (familia 'palm-oil').

O documento e o OPCAO COMMODITY - PALM OIL.doc, e ele e o irmao do
opt-comm-strike-usd.html com um punhado de mudancas — o mesmo parentesco que o
Termo de palm oil tem com o Termo em USD. Duas armadilhas moram ai:

  * um documento parece copia do outro, entao e facil editar um e esquecer o
    irmao (foi o que este script pega no item 1: FORA da lista declarada de
    diferencas, os dois textos tem de seguir palavra a palavra iguais);
  * o Anexo I tem TRES colunas a mais (Codigo da Bloomberg, Taxa de Conversao
    da Mercadoria e a Data de Verificacao dela) e elas so aparecem no documento
    se o gerador as escrever na linha — cabecalho e linha desalinham em
    silencio, e o que a contraparte recebe e a coluna vizinha.

E protege ainda o que o Word NAO tinha: o .doc cita "Anexo II" sete vezes e nao
traz a secao. Ela foi trazida do Termo de palm oil (mesma mesa, mesmo anexo),
porque a formula de liquidacao aponta para ela — sem isso a confirmacao sai
mandando o cliente ler um anexo que nao existe.

Nao encosta em dado real: renderiza o template com um conf de exemplo.
"""
import difflib
import html
import io
import os
import re
import sys
import unicodedata

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.test-share'))

from apps.pages import routes as R                           # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


USD_TPL = 'apps/templates/confirmations/opt-comm-strike-usd.html'
PALM_TPL = 'apps/templates/confirmations/opt-comm-palmoil-strike-myrusd.html'
TERMO_PALM_TPL = 'apps/templates/confirmations/ndf-comm-palmoil-strike-myrusd.html'


def words(path, upto=None):
    """Palavras do DOCUMENTO (sem painel, sem Jinja, sem acento/pontuacao)."""
    raw = io.open(path, encoding='utf-8').read()
    if upto:
        raw = raw[:raw.index(upto)]
    raw = re.sub(r'(?s)\{% if not doc_only %\}.*?\{% endif %\}', ' ', raw, count=1)
    raw = re.sub(r'(?s)\{%.*?%\}|\{\{.*?\}\}', ' ', raw)
    raw = re.sub(r'(?is)<head.*?</head>', ' ', raw)
    raw = re.sub(r'(?is)<(style|script).*?</\1>', ' ', raw)
    raw = re.sub(r'(?is)<!--.*?-->', ' ', raw)
    raw = re.sub(r'(?s)<[^>]+>', ' ', raw)
    raw = html.unescape(raw).replace('\xa0', ' ')
    raw = unicodedata.normalize('NFKD', raw)
    raw = ''.join(c for c in raw if not unicodedata.combining(c))
    return re.sub(r'[^A-Za-z0-9$%/]+', ' ', raw).lower().split()


def th_cells(path):
    """Os <th> do Anexo I, com o <sub>i</sub> virando '[i]' (como no PDF)."""
    raw = io.open(path, encoding='utf-8').read()
    head = raw[raw.index('<thead>'):raw.index('</thead>')]
    out = []
    for cell in re.findall(r'(?is)<th[^>]*>(.*?)</th>', head):
        cell = re.sub(r'(?is)<sub[^>]*>(.*?)</sub>', r'[\1]', cell)
        cell = html.unescape(re.sub(r'(?s)<[^>]+>', '', cell)).replace('\xa0', ' ')
        out.append(' '.join(cell.split()))
    return out


def row_fields(path):
    """As chaves `r.<campo>` da linha do Anexo I, na ordem em que saem."""
    raw = io.open(path, encoding='utf-8').read()
    body = raw[raw.index('<tbody id="ops-tbody">'):raw.index('</tbody>')]
    return re.findall(r'\{\{\s*r\.(\w+)\s*\}\}', body)


print('\n== 1. fora das diferencas declaradas, o texto e o do irmao em USD ==')
# Ate o Anexo I: o Anexo II so existe no palm oil e entraria como um bloco
# gigante de 'insert', escondendo qualquer clausula mexida por engano.
u = words(USD_TPL, upto='<!-- ANEXO I -->')
p = words(PALM_TPL, upto='<!-- ANEXO I -->')
sm = difflib.SequenceMatcher(None, u, p, autojunk=False)
diffs = [(t, ' '.join(u[i1:i2]), ' '.join(p[j1:j2]))
         for t, i1, i2, j1, j2 in sm.get_opcodes() if t != 'equal']
# As diferencas PERMITIDAS, uma a uma (o inicio de cada trecho basta para
# identificar; o texto inteiro esta no .doc).
ESPERADAS = [
    'no anexo ii caso um termo',      # §1 remete ao Anexo II
    'o anexo ii contem as definicoes',# §1 paragrafo novo do Anexo II
    'ou ii a data de verificacao da ptax',  # §4.2.e Data de Verificacao (i / ii)
    'e que se aplicavel',             # §4.2.k Bloomberg + Taxa de Conversao
    'taxa de conversao da mercadoria significa',  # §4.2.l definicao nova
    'caso o preco final',             # sai: a conversao pela PTAX vira Anexo II
    'usd ptax significa a taxa',      # sai: a PTAX passa a ser definida no Anexo II
    'esta operacao foi customizada',  # §5.m nova
    'regras e parametros de atuacao',  # §5.n nova
]
achadas = ' | '.join((a + ' ' + c).strip() for _, a, c in diffs)
for esperada in ESPERADAS:
    check('diferenca esperada presente: %s...' % esperada[:34],
          esperada in achadas, True)
# E NADA alem delas: 12 trechos, nem um a mais (clausula mexida por engano
# aparece aqui como o 13o).
check('nenhuma diferenca fora da lista', len(diffs), 12)
# Letras das alineas: o palm oil vai ate 'q' nas declaracoes; o USD, ate 'o'.
palm_raw = io.open(PALM_TPL, encoding='utf-8').read()
usd_raw = io.open(USD_TPL, encoding='utf-8').read()
check('declaracoes vao ate q no palm oil', palm_raw.count('<span class="ltr">q.</span>'), 1)
check('declaracoes param em o no USD', usd_raw.count('<span class="ltr">q.</span>'), 0)
# As quatro listas alfabeticas do documento (§2 a-d, §3 a-g, §4.2 a-p e §5
# a-q): cada letra sai uma vez por lista, sem buraco nem repetida — e o que
# quebra quando se insere uma alinea e esquece de reletrar as seguintes.
import collections as _c
check('as alineas nao repetem nem faltam',
      dict(sorted(_c.Counter(re.findall(r'<span class="ltr">([a-z])\.</span>',
                                        palm_raw)).items())),
      {'a': 4, 'b': 4, 'c': 3, 'd': 3, 'e': 3, 'f': 3, 'g': 3, 'h': 2, 'i': 2,
       'j': 2, 'k': 2, 'l': 2, 'm': 2, 'n': 2, 'o': 2, 'p': 2, 'q': 1})

print('\n== 2. cabecalho do Anexo I, celula a celula ==')
# Exatamente como esta no OPCAO COMMODITY - PALM OIL.doc.
PALM_HEADS = ['i', 'Nº', 'Tipo da Opção', 'Forma de Exercício', 'Ticker[i]',
              'Bolsa de Valores', 'Código da Bloomberg', 'Quantidade[i]',
              'Taxa de Conversão da Mercadoria',
              'Data de Verificação da Taxa de Conversão da Mercadoria',
              'Data de Verificação da PTAX[i]', 'Comprador[i]', 'Prêmio[i]',
              'Data de Pagamento do Prêmio[i]', 'Preço de Exercício[i]',
              'Data Inicial de Verificação da Mercadoria[i]',
              'Data Final de Verificação da Mercadoria[i]',
              'Data de Exercício', 'Data de Vencimento[i]']
check('cabecalho do template', th_cells(PALM_TPL), PALM_HEADS)
check('19 colunas', len(PALM_HEADS), 19)
check('USD continua com 16 (nao pode ter mudado)', len(th_cells(USD_TPL)), 16)

print('\n== 3. a linha do Anexo I acompanha o cabecalho ==')
FIELDS = ['num', 'tipo', 'forma', 'ticker', 'bolsa', 'bbg', 'qtd', 'taxaConv',
          'dtTaxaConv', 'ptax', 'comprador', 'premio', 'dtPremio', 'strike',
          'dtIni', 'dtFim', 'dtExerc', 'dtVenc']
check('campos da linha, na ordem', row_fields(PALM_TPL), FIELDS)
check('linha tem uma celula por coluna (a 1a e o indice)',
      len(FIELDS) + 1, len(PALM_HEADS))
# O painel de edicao redesenha a MESMA tabela: campo que falte ali sai da
# tabela no primeiro toque do usuario, com o cabecalho intacto.
panel = re.findall(r'\{ *key: *"(\w+)"', palm_raw)
check('painel edita os mesmos campos', panel, FIELDS)
check('renderTable escreve os mesmos campos',
      re.findall(r'<td>\$\{row\.(\w+)\}</td>', palm_raw), FIELDS)

print('\n== 4. o Anexo II existe e e o mesmo do Termo de palm oil ==')
check('o documento tem ANEXO II', '<p class="annex-title">ANEXO II' in palm_raw, True)
def bloco_anexo2(path):
    raw = io.open(path, encoding='utf-8').read()
    i = raw.index('<!-- ANEXO II -->')
    j = raw.index('</div><!-- /doc-body -->')
    txt = html.unescape(re.sub(r'(?s)<[^>]+>', ' ', raw[i:j]))
    return ' '.join(txt.split())
check('Anexo II identico ao do Termo de palm oil',
      bloco_anexo2(PALM_TPL), bloco_anexo2(TERMO_PALM_TPL))
check('a taxa MYR USD esta definida', 'MYR USD' in bloco_anexo2(PALM_TPL), True)
# Toda citacao de "Anexo II" no corpo tem para onde apontar.
check('o corpo cita o Anexo II', palm_raw.count('Anexo II') >= 5, True)

print('\n== 5. a familia esta ligada de ponta a ponta ==')
check('mercadoria palm oil -> familia palm-oil',
      R._conf_opt_family({'Commodities': 'OLEO DE PALMA EM USD'}, None), 'palm-oil')
check('pelo cadastro do Subjacente tambem',
      R._conf_opt_family({}, {'mercadoria': 'OLEO DE PALMA EM USD'}), 'palm-oil')
check('outra mercadoria segue strike-usd',
      R._conf_opt_family({'Commodities': 'OLEO DE SOJA'}, None), 'strike-usd')
check('familia tem template',
      R._CONF_OPT_FAMILY_TEMPLATES.get('palm-oil', (None,))[0],
      'confirmations/opt-comm-palmoil-strike-myrusd.html')
check('familia tem rota',
      R._CONF_OPT_FAMILY_TEMPLATES.get('palm-oil', (None, None))[1],
      '/confirmation/opt-comm/palmoil-strike-myrusd')
# O PDF sai do HTML renderizado (§139), e nao de uma segunda transcricao em
# reportlab: `opcao_pdf` nao conhece esta familia e imprimiria o Anexo I de 16
# colunas, sem a Taxa de Conversao, no documento que vai assinado.
check('o PDF vem do HTML renderizado', 'palm-oil' in R._CONF_OPT_PDF_FROM_HTML, True)
check('e nao da replica em reportlab',
      R._CONF_OPT_PDF_VARIANT.get('palm-oil'), None)

print('\n== 6. o gerador escreve as tres colunas novas ==')
# O gerador mora em platform/confirmations.py (§316); o corpo vai até o
# próximo statement de topo (não há mais rota ao lado dele).
src = io.open('apps/pages/platform/confirmations.py', encoding='utf-8').read()
corpo = src.split('def _conf_opt_generation_page(', 1)[1].split('\ndef ', 1)[0]
for campo in ('bbg', 'taxaConv', 'dtTaxaConv'):
    check("_conf_opt_generation_page preenche %s" % campo,
          ("row['%s']" % campo) in corpo, True)
check('a bolsa do palm oil e a constante do documento',
      '_CONF_PALMOIL_BOLSA' in corpo, True)
check('a taxa de conversao tambem',
      '_CONF_PALMOIL_TAXA_CONV' in corpo, True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'all ok'))
sys.exit(1 if fails else 0)
