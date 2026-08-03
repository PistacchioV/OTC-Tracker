"""Confirmacao de Opcao de Commodities com strike em BRL (familia 'brl').

O OPÇÃO COMMODITY - BRL.doc e o OPÇÃO COMMODITY.doc (USD) tem o MESMO texto
legal — conferido palavra a palavra — e a diferenca inteira mora no cabecalho do
Anexo I: o Preco de Exercicio sai anunciado em reais e tres subscritos `i` mudam
de lugar. Isso e uma armadilha: um documento parece copia do outro, entao e
facil editar um e esquecer o irmao, ou "corrigir" o cabecalho e desalinhar o
template do PDF.

O que este script protege:

  1. Os dois templates seguem identicos palavra a palavra FORA do cabecalho do
     Anexo I. Qualquer clausula mexida num deles e nao no outro cai aqui.
  2. O cabecalho de cada um bate celula a celula com o respectivo Word.
  3. O PDF (replica em reportlab) usa o MESMO cabecalho do template. Sao as duas
     copias que a contraparte ve: o PDF assinado e o HTML revisado na tela.
  4. A familia esta ligada de ponta a ponta: deal com strike em BRL cai em
     'brl', a familia tem template e rota, e o save escolhe a variante do PDF.

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

from apps.pages import confirmation_pdfs as P                # noqa: E402
from apps.pages import routes as R                           # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


USD_TPL = 'apps/templates/confirmations/opt-comm-strike-usd.html'
BRL_TPL = 'apps/templates/confirmations/opt-comm-strike-brl.html'


def words(path):
    """Palavras do DOCUMENTO (sem painel, sem Jinja, sem acento/pontuacao)."""
    raw = io.open(path, encoding='utf-8').read()
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


print('\n== 1. o texto legal dos dois documentos e o mesmo ==')
u, b = words(USD_TPL), words(BRL_TPL)
sm = difflib.SequenceMatcher(None, u, b, autojunk=False)
diffs = [(t, ' '.join(u[i1:i2]), ' '.join(b[j1:j2]))
         for t, i1, i2, j1, j2 in sm.get_opcodes() if t != 'equal']
# As UNICAS diferencas permitidas sao as do cabecalho do Anexo I: o 'i' que sai
# de Tipo da Opcao, o 'i' que entra em Quantidade, o '(em R$)' do strike e o 'i'
# que sai de Data de Exercicio.
check('so 4 diferencas de palavra', len(diffs), 4)
check('as diferencas sao as do cabecalho',
      sorted((t, a, c) for t, a, c in diffs),
      sorted([('delete', 'i', ''), ('insert', '', 'i'),
              ('insert', '', 'em r$'), ('delete', 'i', '')]))

print('\n== 2. cabecalho do Anexo I, celula a celula ==')
# Exatamente como esta no OPÇÃO COMMODITY - BRL.doc.
BRL_HEADS = ['i', 'Nº', 'Tipo da Opção', 'Forma de Exercício', 'Ticker[i]',
             'Bolsa de Valores', 'Quantidade[i]', 'Data de Verificação da PTAX[i]',
             'Comprador[i]', 'Prêmio[i]', 'Data de Pagamento do Prêmio[i]',
             'Preço de Exercício[i] (em R$)',
             'Data Inicial de Verificação da Mercadoria[i]',
             'Data Final de Verificação da Mercadoria[i]',
             'Data de Exercício', 'Data de Vencimento[i]']
USD_HEADS = ['i', 'Nº', 'Tipo da Opção[i]', 'Forma de Exercício', 'Ticker[i]',
             'Bolsa de Valores', 'Quantidade', 'Data de Verificação da PTAX[i]',
             'Comprador[i]', 'Prêmio[i]', 'Data de Pagamento do Prêmio[i]',
             'Preço de Exercício[i]',
             'Data Inicial de Verificação da Mercadoria[i]',
             'Data Final de Verificação da Mercadoria[i]',
             'Data de Exercício[i]', 'Data de Vencimento[i]']
check('template BRL', th_cells(BRL_TPL), BRL_HEADS)
check('template USD (nao pode ter mudado)', th_cells(USD_TPL), USD_HEADS)
check('16 colunas nos dois', (len(BRL_HEADS), len(USD_HEADS)), (16, 16))

print('\n== 3. o PDF usa o MESMO cabecalho do template ==')
check('PDF brl == template brl', P.opcao_anexo_heads('brl'), th_cells(BRL_TPL))
check('PDF usd == template usd', P.opcao_anexo_heads('usd'), th_cells(USD_TPL))
check('variante desconhecida cai no usd', P.opcao_anexo_heads('xpto'), USD_HEADS)

print('\n== 4. a familia esta ligada de ponta a ponta ==')
check('strike BRL -> familia brl',
      R._conf_deal_family({'StrikeCurrency': 'BRL'}, None), 'brl')
check('strike BRR -> familia brl',
      R._conf_deal_family({'StrikeCurrency': 'BRR'}, None), 'brl')
check('strike USD segue strike-usd',
      R._conf_deal_family({'StrikeCurrency': 'USD'}, None), 'strike-usd')
check('familia brl tem template',
      R._CONF_OPT_FAMILY_TEMPLATES.get('brl', (None,))[0],
      'confirmations/opt-comm-strike-brl.html')
check('familia brl tem rota',
      R._CONF_OPT_FAMILY_TEMPLATES.get('brl', (None, None))[1],
      '/confirmation/opt-comm/strike-brl')
check('save escolhe o PDF em brl', R._CONF_OPT_PDF_VARIANT.get('brl'), 'brl')
check('save mantem usd por omissao', R._CONF_OPT_PDF_VARIANT.get('strike-usd', 'usd'), 'usd')

print('\n== 5. o documento renderiza nos dois modos ==')
from apps import create_app                                  # noqa: E402
from apps.config import DebugConfig                          # noqa: E402
from flask import render_template                            # noqa: E402

CONF = {'ref_date': '2026-08-03', 'cgd_date': '26 de Abril de 2010',
        'parteb_nome': 'CONTRAPARTE TESTE SA', 'parteb_cnpj': '00.000.000/0001-00',
        'data_neg': '04/09/2024', 'data_extenso': '04 de Setembro de 2024',
        'mercadoria': 'SOJA', 'acronym': 'TESTE',
        'rows': [{'num': 'DEAL-1', 'tipo': 'Venda', 'forma': 'Europeia', 'ticker': 'S K5',
                  'bolsa': 'CBOT', 'qtd': '100.000', 'ptax': '28/03/2025',
                  'comprador': 'Parte B', 'premio': 'R$ 266.000,00', 'dtPremio': '05/09/2024',
                  'strike': '59,65', 'dtIni': 'Não Aplicável', 'dtFim': 'Não Aplicável',
                  'dtExerc': '28/03/2025', 'dtVenc': '31/03/2025'}],
        'warnings': []}

app = create_app(DebugConfig)
with app.app_context():
    full = render_template('confirmations/opt-comm-strike-brl.html', conf=CONF)
    doc = render_template('confirmations/opt-comm-strike-brl.html', conf=CONF, doc_only=True)
check('painel presente na tela', 'Salvar Word + PDF' in full, True)
check('painel FORA do .doc', 'Salvar Word + PDF' in doc, False)
check('o save manda a familia brl', "family: 'brl'" in full, True)
check('strike da operacao no documento', '59,65' in doc, True)
check('cabecalho em R$ no documento', '(em R$)' in doc, True)
pdf = P.opcao_pdf(CONF, variant='brl')
check('PDF gera bytes', pdf[:4], b'%PDF')
rotas = {str(r) for r in app.url_map.iter_rules()}
check('a rota da familia brl existe',
      '/confirmation/opt-comm/strike-brl' in rotas, True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
