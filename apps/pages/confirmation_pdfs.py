# -*- coding: utf-8 -*-
"""PDFs das confirmações de derivativos (Termo de Mercadoria e Opção).

Réplica em reportlab dos documentos HTML de confirmação (mesmo texto legal dos
templates .doc legados — TERMO.doc e OPÇÃO COMMODITY.doc). A4 paisagem, com a
Tabela de Referência (Anexo I) em página própria.

Import é lazy no chamador: se o reportlab não estiver instalado, o save
retorna erro claro em vez de derrubar o app.
"""
import re
from io import BytesIO

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle, PageBreak)

_BLACK = colors.black


def _styles():
    base = dict(fontName='Times-Roman', fontSize=10.5, leading=14,
                textColor=_BLACK, alignment=4)          # 4 = justify
    return {
        'title':   ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=12,
                                  leading=15, alignment=1, spaceAfter=10),
        'body':    ParagraphStyle('body', spaceAfter=6, **base),
        'section': ParagraphStyle('section', fontName='Times-Bold', fontSize=10.5,
                                  leading=14, spaceBefore=8, spaceAfter=6),
        'item':    ParagraphStyle('item', leftIndent=28, spaceAfter=5, **base),
        'formula': ParagraphStyle('formula', fontName='Times-Bold', fontSize=10.5,
                                  leading=14, leftIndent=54, spaceAfter=6),
        'center':  ParagraphStyle('center', fontName='Times-Italic', fontSize=10.5,
                                  leading=14, alignment=1, spaceBefore=10, spaceAfter=10),
        'sig':     ParagraphStyle('sig', fontName='Times-Roman', fontSize=10.5,
                                  leading=14, spaceAfter=4),
        'sigb':    ParagraphStyle('sigb', fontName='Times-Bold', fontSize=10.5,
                                  leading=14, spaceAfter=4),
        'annex':   ParagraphStyle('annex', fontName='Times-Bold', fontSize=12,
                                  leading=15, alignment=1, spaceAfter=12),
        'th':      ParagraphStyle('th', fontName='Times-Bold', fontSize=7,
                                  leading=8.5, alignment=1),
        'td':      ParagraphStyle('td', fontName='Times-Roman', fontSize=7.5,
                                  leading=9, alignment=1),
    }


def _e(v):
    return (str(v) if v is not None else '').replace('&', '&amp;') \
        .replace('<', '&lt;').replace('>', '&gt;')


def _sub(txt):
    """Marca <sub>i</sub> estilo índice — reportlab entende <sub> nativo."""
    return txt.replace('[i]', '<sub>i</sub>')


# ── Anexo II (só Palm Oil) — moedas e taxas de câmbio ────────────────────────
# Texto do TERMO - PALM OIL.doc. O mesmo conteúdo está no template Jinja: os
# dois documentos são réplicas independentes (é o padrão deste módulo desde as
# primeiras confirmações), então mexer no texto legal exige mexer nos dois.
_PALM_MOEDAS = [
    ('ARS', 'o Peso Argentino ou seu sucessor legal'),
    ('AUD', 'o Dólar Australiano ou seu sucessor legal'),
    ('BRL', 'o Real ou seu sucessor legal'),
    ('CLP', 'o Peso Chileno ou seu sucessor legal'),
    ('CAD', 'o Dólar Canadense ou seu sucessor legal'),
    ('CHF', 'o Franco Suíço ou seu sucessor legal'),
    ('CNY', 'o Yuan Renminbi ou seu sucessor legal'),
    ('CNH', 'o Yuan Renminbi de Hong Kong ou seu sucessor legal'),
    ('COP', 'o Peso Colombiano ou seu sucessor legal'),
    ('DKK', 'a Coroa Dinamarquesa ou sua sucessora legal'),
    ('EUR', 'o Euro ou seu sucessor legal'),
    ('GBP', 'a Libra Esterlina ou sua sucessora legal'),
    ('INR', 'a Rúpia Indiana ou sua sucessora legal'),
    ('JPY', 'o Yen Japonês ou seu sucessor legal'),
    ('MXN', 'o Peso Mexicano ou seu sucessor legal'),
    ('MYR', 'o Ringgit Malaio ou seu sucessor legal'),
    ('NOK', 'a Coroa Norueguesa ou sua sucessora legal'),
    ('PEN', 'o Novo Sol ou seu sucessor legal'),
    ('SEK', 'o Coroa Suéca ou seu sucessor legal'),
    ('USD', 'o Dólar norte-americano ou seu sucessor legal'),
]

_PALM_PTAX = ('significa a taxa de câmbio de compra ou de venda do {c}, conforme o Tipo de Taxa de '
              'Conversão[i], expressa pela quantidade de BRL por cada {c}, conforme divulgada pelo '
              'Banco Central do Brasil em sua página da internet na respectiva Data de Verificação.')
_PALM_WMCO = ('significa a taxa de câmbio, expressa por uma quantidade de {c} por cada unidade de '
              'USD, apurada conforme metodologia de apuração das taxas spot de fechamento do '
              'WM/Reuters, com publicação diária, às 16h do horário de Londres, a ser obtida '
              'através de consulta ao sistema de informação Bloomberg na página "{p} WMCO CRNCY '
              '&lt;GO&gt;" na respectiva Data de Verificação.')

_PALM_TAXAS = [
    ('USD PTAX', _PALM_PTAX.format(c='USD')),
    ('ARS MAE', 'significa a taxa de câmbio, expressa em uma quantidade de ARS por cada unidade de '
     'USD, determinada a partir da média das negociações realizadas no mercado eletrônico para '
     'liquidação no mesmo dia, conforme divulgada pela Mercado Abierto Electronico ("MAE") por '
     'volta das 15:00 horas de Buenos Aires, e que pode ser obtida na página da internet da '
     'FOREX-MAE (www.mae.com.ar) como a taxa "PPN" ("Promedio Ponderado Noticiado") na respectiva '
     'Data de Verificação.'),
    ('AUD PTAX', _PALM_PTAX.format(c='AUD')),
    ('ARS WMCO', _PALM_WMCO.format(c='ARS', p='ARS')),
    ('CAD PTAX', _PALM_PTAX.format(c='CAD')),
    ('CHF PTAX', _PALM_PTAX.format(c='CHF')),
    ('CNY USD', 'significa a taxa de câmbio, expressa por uma quantidade de CNY por cada unidade '
     'de USD, com publicação diária no sistema de informação Bloomberg na tela "CNYMUSD Index '
     '&lt;GO&gt;" às 9h15 do horário de Beijing na respectiva Data de Verificação.'),
    ('CNY PTAX', _PALM_PTAX.format(c='CNY')),
    ('CNH BBG', 'significa a taxa de câmbio da CNH, expressa pela quantidade de CNH por cada USD, '
     'conforme divulgada pela Bloomberg na página "CNH L160 Curncy" na respectiva Data de '
     'Verificação.'),
    # A página citada na CNH WMCO é a "PEN WMCO CRNCY" no documento de origem —
    # está assim no .doc, não é erro de transcrição.
    ('CNH WMCO', _PALM_WMCO.format(c='CNH', p='PEN')),
    ('EURO BBG L160', 'significa a taxa de câmbio do Euro, expressa pela quantidade de USD por '
     'cada EUR, conforme divulgada pela Bloomberg na página "EUR L160 Curncy" às 16 horas de '
     'Londres na respectiva Data de Verificação.'),
    ('EURO PTAX', _PALM_PTAX.format(c='EUR')),
    ('EURO WMCO', 'significa a taxa de câmbio, expressa por uma quantidade de USD por cada unidade '
     'de EUR, apurada conforme metodologia de apuração das taxas spot de fechamento do WM/Reuters, '
     'com publicação diária, às 16h do horário de Londres, a ser obtida através de consulta ao '
     'sistema de informação Bloomberg na página "EUR WMCO CRNCY &lt;GO&gt;" na respectiva Data de '
     'Verificação.'),
    ('INR USD', 'significa a taxa de câmbio, expressa por uma quantidade de INR por cada unidade '
     'de USD, divulgada pelo Reserve Bank of India (www.rbi.org.in) por volta das 13:30 horário '
     'local na respectiva Data de Verificação.'),
    ('NOK PTAX', _PALM_PTAX.format(c='NOK')),
    ('USD EUR', 'significa a taxa de câmbio entre USD e EUR, expressa pela quantidade de USD por '
     'cada EUR, apurada utilizando a metodologia do Banco Central Europeu e publicada através do '
     'website www.ecb.int/stats/exchange/eurofxref/html/index.en.html e no sistema de informação '
     'Bloomberg na página "EUCFUSD INDEX &lt;GO&gt;" às 15:00 CET (Central European Time) na '
     'respectiva Data de Verificação.'),
    ('GBP PTAX', _PALM_PTAX.format(c='GBP')),
    ('JPY PTAX', _PALM_PTAX.format(c='JPY')),
    ('SEK PTAX', _PALM_PTAX.format(c='SEK')),
    ('CLP OBSERVADO', 'significa a taxa de câmbio, expressa por uma quantidade de CLP por cada '
     'unidade de USD, determinada a partir da média das negociações realizadas no mercado à vista '
     'de compra e venda entre CLP e USD efetuadas no Mercado Cambiario Formal ("MCF") durante o '
     'dia útil bancário imediatamente anterior, a ser divulgada na página da internet do Banco '
     'Central do Chile (www.bcentral.cl) como "Dolar Observado" na respectiva Data de Verificação.'),
    ('COP TRM', 'significa a taxa de câmbio, expressa por uma quantidade de COP por cada unidade '
     'de USD, determinada a partir da média ponderada das operações de compra e venda entre as '
     'moedas, efetuadas pelos Intermediarios del Mercado Cambiario colombiano, para serem '
     'exercidas no mesmo dia da negociação, a ser obtida na página da Superitendencia Financeira '
     'de Colombia (www.superfinanceira.gov.co) referente à Tasa de Cambio Representativa del '
     'Mercado – TRM na respectiva Data de Verificação.'),
    ('MXN PTAX', _PALM_PTAX.format(c='MXN')),
    ('MXN WMCO', _PALM_WMCO.format(c='MXN', p='MXN')),
    ('PEN WMCO', _PALM_WMCO.format(c='PEN', p='PEN')),
    ('PEN INTERBANK AVE" ou "PEN05" ou "BCRPAVER Index',
     'significa a taxa de câmbio, expressa por uma quantidade de PEN por cada unidade de USD, '
     'determinada a partir da média das operações de câmbio interbancárias para liquidação no '
     'mesmo dia, a ser obtida na página do Banco Central de Reserva del Peru referente ao "Tipo de '
     'Cambio Interbancario Promedio" na respectiva Data de Verificação.'),
    ('DKK PTAX', _PALM_PTAX.format(c='DKK')),
    ('MYR USD', 'significa a taxa de câmbio, expressa por uma quantidade de MYR por cada unidade '
     'de USD, divulgada na página "MYR BNMK Currency" do terminal Bloomberg às 15h30 (horário de '
     'Kuala Lumpur) na respectiva Data de Verificação.'),
]


def _anexo_ii(S):
    """Flowables do Anexo II (moedas + taxas de câmbio) da confirmação Palm Oil."""
    out = [PageBreak(),
           Paragraph('ANEXO II À CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS', S['annex']),
           Paragraph('Os termos em letra maiúscula utilizados na Confirmação e Operações de '
                     'Derivativos terão os significados que lhes são atribuídos neste Anexo II.',
                     S['body']),
           Paragraph('1) Definições das Moedas', S['section'])]
    for code, meaning in _PALM_MOEDAS:
        out.append(Paragraph('<b>"{}"</b> – significa {}.'.format(code, meaning), S['item']))
    out.append(Paragraph('2) Definições das Taxas de Câmbio', S['section']))
    for name, meaning in _PALM_TAXAS:
        out.append(Paragraph(_sub('<b>"{}"</b> {}'.format(name, meaning)), S['item']))
    return out


def _parties_block(doc, S, nome, cnpj):
    """Seção 2 (a./b.) igual ao HTML: rótulo à esquerda, e à direita o nome em
    negrito com o CNPJ na linha de baixo.

    Antes era um parágrafo corrido ('Parte A: BANCO ... — CNPJ/MF: ...'), o que
    fazia o PDF salvo sair diferente do documento que o usuário revisou na tela
    — e é o PDF que vai para a contraparte. Tabela de duas colunas porque o
    alinhamento do CNPJ sob o nome não sobrevive a um parágrafo justificado."""
    def _pair(letter, label, name, doc_id):
        return [Paragraph('{} &nbsp;&nbsp; <b>{}</b>'.format(letter, label), S['sig']),
                Paragraph('<b>{}</b><br/>CNPJ/MF: &nbsp; {}'.format(name, doc_id), S['sig'])]

    label_w = 86
    tbl = Table([_pair('a.', 'Parte A:', 'BANCO J.P. MORGAN S.A.', '33.172.537/0001–98'),
                 [Paragraph('', S['sig']), Paragraph('', S['sig'])],
                 _pair('b.', 'Parte B:', nome, cnpj)],
                colWidths=[label_w, doc.width - label_w - 28])
    tbl.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, -1), 28),      # mesmo recuo do estilo 'item'
        ('LEFTPADDING', (1, 0), (1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 1), (-1, 1), 8),        # respiro entre a. e b.
    ]))
    return tbl


def termo_strike_usd_pdf(conf):
    return termo_pdf(conf, variant='usd')


def termo_platts_strike_usd_pdf(conf):
    return termo_pdf(conf, variant='platts')


def termo_strike_brl_pdf(conf):
    return termo_pdf(conf, variant='brl')


def termo_pdf(conf, variant='usd'):
    """Bytes do PDF da confirmação Termo de Mercadoria.

    variant: 'usd' (TERMO.doc), 'platts' (Código/Fonte de Divulgação no Anexo),
    'brl' (sem PTAX pontual — USD PTAX = média entre as Datas Inicial/Final de
    Verificação USD PTAX; Anexo com 15 colunas e Forward em R$) ou 'palmoil'
    (TERMO - PALM OIL.doc: Taxa de Conversão da Mercadoria, Anexo I com 17
    colunas e o Anexo II com as definições de moedas e taxas de câmbio)."""
    S = _styles()
    palm = variant == 'palmoil'
    buf = BytesIO()
    page = landscape(A4)
    doc = BaseDocTemplate(buf, pagesize=page,
                          leftMargin=18 * mm, rightMargin=18 * mm,
                          topMargin=15 * mm, bottomMargin=15 * mm,
                          title='Confirmação de Operações de Derivativos')
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='f')
    doc.addPageTemplates([PageTemplate(id='p', frames=[frame])])

    cgd   = _e(conf.get('cgd_date'))
    nome  = _e(conf.get('parteb_nome'))
    cnpj  = _e(conf.get('parteb_cnpj'))
    d_neg = _e(conf.get('data_neg'))
    d_ext = _e(conf.get('data_extenso'))

    st = []
    st.append(Paragraph('CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS', S['title']))
    st.append(Paragraph(
        'Esta Confirmação ("Confirmação") tem por objetivo reger as Operações de Derivativos a '
        'Parte A e a Parte B abaixo qualificadas, de acordo com as disposições legais e '
        'regulamentares aplicáveis e no âmbito do ' +
        ('<i>Contrato Global de Derivativos</i>' if palm else
         '<i>Contrato Global de Derivativos e do Apêndice ao Contrato Global de Derivativos</i>') +
        ', ambos firmados entre as Partes em ' + cgd +
        ' ("Contrato"), cujos termos são incorporados por referência a este instrumento.', S['body']))
    st.append(Paragraph(
        'Esta Confirmação formaliza uma ou mais Operações de Derivativos contratadas na mesma data '
        'entre as Partes individualizadas abaixo na Tabela Referência. No entanto, cada Operação de '
        'Derivativo é uma operação individual para fins tributários e de registro, sem prejuízo das '
        'disposições do Contrato que tratam da compensação e do cálculo do Valor de Vencimento '
        'Antecipado.', S['body']))
    st.append(Paragraph(
        'Para fins dos cálculos descritos nessa Confirmação, a quantidade de Dias Úteis será '
        'apurada pelo Agente de Cálculo conforme as convenções e as práticas de mercado para '
        'contagem de dias úteis a depender da taxa, índice ou preço utilizado como referência em '
        'uma Operação de Derivativo.', S['body']))

    # Seção 1
    st.append(Paragraph('1. &nbsp;&nbsp; <u>Definições Gerais</u>', S['section']))
    if palm:
        st.append(Paragraph(
            'Os termos não definidos nesta Confirmação terão os mesmos significados a eles no '
            'Anexo II. Caso um termo em letras maísculas não esteja definido no Anexo II ou nesta '
            'Confirmação, eles terão os mesmos significados atribuídos a eles no Contrato. Em caso '
            'de conflito entre uma definição do Contrato e a desta Confirmação, prevalecerá, para '
            'os fins desta Operação de Derivativo, a definição que constar desta Confirmação.',
            S['body']))
        st.append(Paragraph(
            'O Anexo II contém as definições das moedas e das taxas de câmbio utilizadas como '
            'referência às Operações de Derivativos e para o cálculo do respectivo do Valor de '
            'Liquidação de cada Operação. Portanto, o Anexo II é parte inseparável e essencial '
            'desta Confirmação e ambos devem ser lidos em conjunto. Para se evitar dúvidas, os '
            'termos definidos no Anexo II e não utilizados nesta Confirmação, não serão aplicáveis '
            'a uma Operação.', S['body']))
    else:
        st.append(Paragraph(
            'Os termos não definidos nesta Confirmação terão os mesmos significados a eles atribuídos '
            'no Contrato. Em caso de conflito entre uma definição do Contrato e a desta Confirmação, '
            'prevalecerá, para os fins desta Operação de Derivativo, a definição que constar desta '
            'Confirmação.', S['body']))

    # Seção 2
    st.append(Paragraph('2. &nbsp;&nbsp; <u>Definição das Partes</u>', S['section']))
    st.append(_parties_block(doc, S, nome, cnpj))
    st.append(Spacer(1, 8))
    st.append(Paragraph(
        'A Parte A e a Parte B, além destas denominações, são também aqui individualmente '
        'denominadas "Parte", e em conjunto "Partes".', S['item']))
    st.append(Paragraph('c. &nbsp;&nbsp; <b>Agente de Cálculo:</b> Parte A, salvo se disposto de '
                        'outra forma no Apêndice', S['item']))
    st.append(Paragraph('d. &nbsp;&nbsp; <b>Acelerador:</b> Parte A', S['item']))

    # Seção 3
    st.append(Paragraph('3. &nbsp;&nbsp; <u>Disposições Gerais</u>', S['section']))
    st.append(Paragraph('a. <b>Local do Registro:</b> B3 S.A. – Brasil, Bolsa, Balcão;', S['item']))
    st.append(Paragraph('b. <b>Data de Negociação:</b> ' + d_neg + ';', S['item']))
    st.append(Paragraph('c. <b>Tipo de Operação:</b> Termo de Mercadoria;', S['item']))
    st.append(Paragraph(_sub(
        'd. <b>Tabela de Referência:</b> Os dados e condições financeiras aplicáveis a cada '
        'Operação de Derivativo[i] contratada entre as Partes na Data de Negociação estão descritos '
        'na Tabela de Referência disposta no Anexo I.'), S['item']))

    # Seção 4
    st.append(Paragraph('4. &nbsp;&nbsp; <u>Cálculo do Valor de Liquidação de cada Operação:</u>', S['section']))
    st.append(Paragraph(
        '<b>4.1.</b> Operação de Termo é a operação em que o Comprador se obriga a comprar e o '
        'Vendedor se obriga a vender uma Quantidade de Mercadoria por um preço futuro definido '
        'pelas partes. Cada Operação de Termo descrita nessa Confirmação será liquidada por '
        'diferença em Reais, conforme a fórmula de cálculo disposta abaixo:', S['body']))
    st.append(Paragraph(_sub(
        'Em cada Data de Vencimento[i] de uma Operação[i], o Agente de Cálculo apurará, com base '
        'nas variáveis aplicáveis à respectiva Operação[i], conforme indicadas na Tabela de '
        'Referência, o Valor de Liquidação[i] a ser pago por uma Parte à outra, na forma seguir:'),
        S['body']))
    if variant == 'brl':
        st.append(Paragraph(_sub(
            'a. &nbsp; Se, na Data de Vencimento[i], o Preço da Mercadoria na Liquidação[i], '
            'convertido para Reais, for superior à Taxa Forward[i] aplicável, o Vendedor[i] '
            'pagará ao Comprador[i] o resultado da seguinte fórmula:'), S['item']))
    elif palm:
        st.append(Paragraph(_sub(
            'a. &nbsp; Se, na Data de Vencimento[i], o Preço da Mercadoria na Liquidação[i] for '
            'superior à Taxa Forward[i] aplicável, o Vendedor[i] pagará ao Comprador[i] o resultado '
            'da seguinte fórmula. O Valor de Liquidação[i] será convertido para Reais utilizando o '
            'USD PTAX de venda, conforme definido no Anexo II, divulgado na Data de Verificação da '
            'PTAX[i]:'), S['item']))
    else:
        st.append(Paragraph(_sub(
            'a. &nbsp; Se, na Data de Vencimento[i], o Preço da Mercadoria na Liquidação[i] for '
            'superior à Taxa Forward[i] aplicável, o Vendedor[i] pagará ao Comprador[i] o resultado da '
            'seguinte fórmula. O Valor de Liquidação[i] será convertido para Reais utilizando o USD '
            'PTAX divulgado na Data de Verificação da PTAX[i] caso da Mercadoria seja cotada em '
            'dólares norte-americanos:'), S['item']))
    st.append(Paragraph(_sub(
        'Valor de Liquidação[i] = Quantidade[i] x (Preço da Mercadoria na Liquidação[i] – Taxa '
        'Forward[i])'), S['formula']))
    if variant == 'brl':
        st.append(Paragraph(_sub(
            'b. &nbsp; Se, na Data de Vencimento[i], o Preço da Mercadoria na Liquidação[i] for '
            'inferior à Taxa Forward[i] aplicável, o Comprador[i] pagará ao Vendedor[i] o '
            'resultado da seguinte fórmula:'), S['item']))
    elif palm:
        st.append(Paragraph(_sub(
            'b. &nbsp; Se, na Data de Vencimento[i], o Preço da Mercadoria na Liquidação[i] for '
            'inferior à Taxa Forward[i] aplicável, o Comprador[i] pagará ao Vendedor[i] o resultado '
            'da seguinte fórmula. O Valor de Liquidação[i] será convertido para Reais utilizando o '
            'USD PTAX de venda, conforme definido no Anexo II, divulgado na Data de Verificação da '
            'PTAX[i]:'), S['item']))
    else:
        st.append(Paragraph(_sub(
            'b. &nbsp; Se, na Data de Vencimento[i], o Preço da Mercadoria na Liquidação[i] for '
            'inferior à Taxa Forward[i] aplicável, o Comprador[i] pagará ao Vendedor[i] o resultado da '
            'seguinte fórmula. O Valor de Liquidação[i] será convertido para Reais utilizando na Data '
            'de Verificação da PTAX[i] à Data de Vencimento[i] caso da Mercadoria seja cotada em '
            'dólares norte-americanos:'), S['item']))
    st.append(Paragraph(_sub(
        'Valor de Liquidação[i] = Quantidade[i] x (Taxa Forward[i] &nbsp; – Preço da Mercadoria na '
        'Liquidação[i])'), S['formula']))
    st.append(Paragraph(
        '<b>4.2.</b> Para fins da metodologia de cálculo acima, os seguintes termos terão as '
        'definições que lhe são atribuídas conforme abaixo:', S['body']))
    defs42_brl = [
        'a. <b>Mercadoria[i]:</b> Para cada Operação[i], significa o contrato futuro de mercadoria '
        '(commodity) cujo código de negociação - Ticker[i] - na respectiva Bolsa de Valores está '
        'indicado na Tabela de Referência.',
        'b. <b>Comprador[i]:</b> Para cada Operação[i], significa a Parte compradora da '
        'Mercadoria[i], conforme indicada na Tabela de Referência;',
        'c. <b>Data de Vencimento[i]:</b> significa a data em que ocorrerá a liquidação de cada '
        'Operação[i], conforme indicadas na Tabela de Referência, mediante o desembolso do Valor '
        'de Liquidação[i] pelo Comprador[i] ou pelo Vendedor[i], de acordo com a apuração '
        'realizada pelo Agente de Cálculo na forma da cláusula anterior;',
        'd. <b>Data de Verificação:</b> Significa a Data Inicial de Verificação da Mercadoria, a '
        'Data Final de Verificação da Mercadoria ou qualquer dia útil dentro do Período de '
        'Verificação do Preço da Mercadoria, conforme o caso, em que o Preço da Mercadoria[i] '
        'tenha que ser apurado para quaisquer fins desta Confirmação;',
        'e. <b>Quantidade[i]:</b> Para cada Operação[i], significa a quantidade indicada na '
        'Tabela da Referência;',
        'f. <b>Período de Verificação do Preço da Mercadoria:</b> significa todos os dias úteis '
        'entre a Data Inicial de Verificação da Mercadoria[i] (inclusive) e a Data Final de '
        'Verificação da Mercadoria[i]; (inclusive);',
        'g. <b>Preço da Mercadoria[i]:</b> significa o preço de fechamento do contrato futuro da '
        'Mercadoria referente ao Ticker[i] divulgado pela Bolsa de Valores[i] na Data de '
        'Verificação[i].',
        'h. <b>Preço da Mercadoria na Liquidação[i]:</b> para cada Operação[i], significa a média '
        'simples do Preço da Mercadoria[i] apurada em cada dia útil do Período de Verificação do '
        'Preço da Mercadoria. Para se evitar dúvidas, caso o Período de Verificação do Preço da '
        'Mercadoria tenha apenas 1 dia, então a Preço da Mercadoria na Liquidação[i] será a Preço '
        'da Mercadoria[i] divulgada na Data Final de Verificação da Mercadoria[i]. Caso o Preço '
        'da Mercadoria na Liquidação[i] seja cotado em dólares norte-americanos, o Preço da '
        'Mercadoria na Liquidação será convertido para Reais pela USD PTAX[i];',
        'i. <b>USD PTAX[i]:</b> significa a média simples da taxa de conversão entre o Real '
        '("BRL") e o Dólar dos Estados Unidos ("USD") apurada em cada dia útil entre a Data '
        'Inicial de Verificação USD PTAX[i] (inclusive) e a Data Final de Verificação USD PTAX[i] '
        '(inclusive), ambas contidas na Tabela de Referência, sendo tal taxa expressa pela '
        'quantidade de Reais por cada Dólar dos Estados Unidos, referente a operações '
        'interbancárias de venda de Dólares dos Estados Unidos com liquidação em dois dias úteis, '
        'conforme apurada pelo Banco Central do Brasil, e que pode ser obtida na página da '
        'internet http://www.bcb.gov.br/?txcambio, opção "Cotações e boletins", por volta das '
        '13:15 horas divulgada em cada dia útil;',
        'j. <b>Taxa Forward[i]:</b> Para cada Operação[i], será a taxa indicada na Tabela de '
        'Referência; e',
        'k. <b>Vendedor[i]:</b> Para cada Operação[i], significa a outra Parte que não a Parte '
        'indicada como Comprador na Tabela da Referência.',
    ]
    defs42 = [
        'a. <b>Mercadoria[i]:</b> Para cada Operação[i], significa o contrato futuro de mercadoria '
        '(commodity) cujo código de negociação - Ticker[i] - na respectiva Bolsa de Valores está '
        'indicado na Tabela de Referência.',
        'b. <b>Comprador[i]:</b> Para cada Operação[i], significa a Parte compradora da '
        'Mercadoria[i], conforme indicada na Tabela de Referência;',
        'c. <b>Data de Vencimento[i]:</b> significa a data em que ocorrerá a liquidação de cada '
        'Operação[i], conforme indicadas na Tabela de Referência, mediante o desembolso do Valor '
        'de Liquidação[i] pelo Comprador[i] ou pelo Vendedor[i], de acordo com a apuração '
        'realizada pelo Agente de Cálculo na forma da cláusula anterior;',
        'd. <b>Data de Verificação:</b> Significa a Data Inicial de Verificação da Mercadoria, a '
        'Data Final de Verificação da Mercadoria ou qualquer dia útil dentro do Período de '
        'Verificação do Preço da Mercadoria, conforme o caso, em que o Preço da Mercadoria[i] '
        'tenha que ser apurado para quaisquer fins desta Confirmação;',
        'e. <b>Data de Verificação da PTAX[i]:</b> Para cada Operação[i], significa a data '
        'indicada na Tabela de Referência',
        'f. <b>Quantidade[i]:</b> Para cada Operação[i], significa a quantidade indicada na '
        'Tabela da Referência;',
        'g. <b>Período de Verificação do Preço da Mercadoria:</b> significa todos os dias úteis '
        'entre a Data Inicial de Verificação da Mercadoria[i] (inclusive) e a Data Final de '
        'Verificação da Mercadoria[i]; (inclusive);',
        'h. <b>Preço da Mercadoria[i]:</b> significa o preço de fechamento do contrato futuro da '
        'Mercadoria referente ao Ticker[i] divulgado pela Bolsa de Valores[i] na Data de '
        'Verificação[i].',
        'i. <b>Preço da Mercadoria na Liquidação[i]:</b> para cada Operação[i], significa a média '
        'simples do Preço da Mercadoria[i] apurada em cada dia útil do Período de Verificação do '
        'Preço da Mercadoria. Para se evitar dúvidas, caso o Período de Verificação do Preço da '
        'Mercadoria tenha apenas 1 dia, então a Preço da Mercadoria na Liquidação[i] será a Preço '
        'da Mercadoria[i] divulgada na Data Final de Verificação da Mercadoria[i];',
        'j. <b>USD PTAX:</b> significa a taxa de conversão entre o Real ("BRL") e o Dólar dos '
        'Estados Unidos ("USD"), expressa pela quantidade de Reais por cada Dólar dos Estados '
        'Unidos, referente a operações interbancárias de venda de Dólares dos Estados Unidos com '
        'liquidação em dois dias úteis, conforme apurada pelo Banco Central do Brasil, e que pode '
        'ser obtida na página da internet http://www.bcb.gov.br/?txcambio, opção "Cotações e '
        'boletins", por volta das 13:15 horas divulgada na Data de Verificação da PTAX[i].',
        'k. <b>Taxa Forward[i]:</b> Para cada Operação[i], será a taxa indicada na Tabela de '
        'Referência; e',
        'l. <b>Vendedor[i]:</b> Para cada Operação[i], significa a outra Parte que não a Parte '
        'indicada como Comprador na Tabela da Referência.',
    ]
    # Palm Oil: a "Taxa de Conversão da Mercadoria" entra como letra i., a USD
    # PTAX sai daqui (foi para o Anexo II) e as letras seguintes andam junto.
    defs42_palm = [
        defs42[0], defs42[1], defs42[2],
        'd. <b>Data de Verificação:</b> Significa i) a Data Inicial de Verificação da Mercadoria, '
        'a Data Final de Verificação da Mercadoria, qualquer dia útil dentro do Período de '
        'Verificação do Preço da Mercadoria, conforme o caso, em que o Preço da Mercadoria[i] '
        'tenha que ser apurado para quaisquer fins desta Confirmação ou ii) a Data de Verificação '
        'da Ptax, a Data de Verificação da Taxa de Conversão da Mercadoria ou qualquer dia em que '
        'uma taxa de câmbio deva ser apurada para quaisquer fins desta Confirmação;',
        defs42[4], defs42[5], defs42[6],
        'h. <b>Preço da Mercadoria[i]:</b> significa o preço de fechamento da mercadoria à vista '
        'referente ao Ticker[i], caso esse represente uma mercadoria para entrega à vista, ou o '
        'contrato futuro referente ao Ticker[i], caso esse represente um contrato futuro sobre a '
        'Mercadoria, divulgado pela Bolsa de Valores[i] na Data de Verificação[i] e que, se '
        'aplicável, poderá ser obtido mediante consulta à tela do terminal Bloomberg que estiver '
        'indicada na Tabela de Referência e convertido para USD por meio da divisão deste preço '
        'pela Taxa de Conversão da Mercadoria.',
        'i. <b>Taxa de Conversão da Mercadoria:</b> significa a taxa de câmbio cuja definição '
        'consta no Anexo II aplicável à respectiva Operação[i] conforme indicado na Tabela de '
        'Referência que será divulgada na Data de Verificação da Taxa de Conversão da '
        'Mercadoria[i] indicada na Tabela de Referência;',
        defs42[8].replace('i. <b>', 'j. <b>', 1),
        'k. <b>Taxa Forward[i]:</b> Para cada Operação[i], será a taxa indicada na Tabela de '
        'Referência; e',
        defs42[11],
    ]
    for d in (defs42_brl if variant == 'brl' else defs42_palm if palm else defs42):
        st.append(Paragraph(_sub(d), S['item']))

    # Seção 5
    st.append(Paragraph('5. &nbsp;&nbsp; <u>Prêmio</u>', S['section']))
    st.append(Paragraph(_sub(
        'Caso tenha sido indicado na Tabela de Referência que haverá pagamento de Prêmio em '
        'relação a uma Operação[i], a Parte Devedora do Prêmio[i] deverá pagar o Prêmio[i] a outra '
        'Parte na Data de Pagamento de Prêmio[i] indicado na Tabela de Referência. As Partes '
        'reconhecem que o valor de Prêmio[i] está economicamente vinculado à respectiva Operação[i] '
        'como um todo, incluindo na definição do valor da Taxa Forward[i] e das demais condições '
        'financeiras da respectiva Operação[i] e, consequentemente ao Valor de Liquidação, de tal '
        'forma que o valor pago do Prêmio[i] faz parte do equilíbrio econômico-financeiro da '
        'Operação[i]. Portanto, o valor pago a título de prêmio não será devolvido em nenhuma '
        'hipótese, ainda que o resultado da Operação[i] seja desfavorável à Parte que pagou o '
        'Prêmio[i].'), S['body']))

    # Seção 6
    st.append(Paragraph('6. &nbsp;&nbsp; <u>Declarações:</u>', S['section']))
    st.append(Paragraph(
        'Em adição às declarações feitas no Contrato, e como condição para a celebração desta '
        'Confirmação, as Partes e o Garantidor, se aplicável, declaram individualmente:', S['body']))
    decls = [
        'a. Que estão agindo por conta própria, tendo tomado de forma independente a decisão '
        'quanto a realizar a presente Operação de Derivativo, bem como quanto à adequação e '
        'conveniência da mesma, com base em critérios próprios e, na medida que cada uma '
        'considerou necessária, na opinião de seus próprios consultores;',
        'b. Que não estão se baseando em qualquer comunicação (escrita ou verbal) da outra parte, '
        'ou de qualquer pessoa agindo em seu nome, como forma de orientação para investimento ou '
        'recomendação para participar da presente operação, ficando entendido que as informações e '
        'explicações relativas aos termos e condições desta ou de qualquer outra Operação de '
        'Derivativo, não deverão ser consideradas como orientação de investimento, nem como '
        'recomendação de participação;',
        'c. Que nenhuma comunicação (escrita ou verbal), recebida de uma Parte, ou de qualquer '
        'pessoa agindo em seu nome, pela outra, será considerada como seguro ou garantia quanto à '
        'expectativa dos resultados previstos da Operação;',
        'd. Que têm conhecimento e experiência dentro do mercado de derivativos, suficientes para '
        'entender a estrutura de cada Operação de Derivativos, incluindo, sem limitação, os '
        'critérios determinados no Contrato para a apuração do Valor de Reposição, com os quais '
        'concordam sem restrições;',
        'e. Que estão cientes dos riscos inerentes às Operações de Derivativos e têm plena '
        'capacidade financeira para assumir as obrigações que venham a ser exigíveis em '
        'decorrência das Operações contratadas, mesmo nos piores cenários econômicos, bem como '
        'capacidade técnica e operacional para cumprir todas as obrigações estabelecidas no '
        'Contrato e em quaisquer Confirmações;',
        'f. Que as declarações prestadas de acordo do Contrato continuam plenamente válidas;',
        'g. Que tiveram a oportunidade de discutir absolutamente todos os termos do Contrato e de '
        'cada Confirmação, incluindo, mas não se limitando, a forma de resolução de conflitos e os '
        'critérios de cálculo, assumindo total responsabilidade pelos mesmos;',
        'h. Que tiveram prévio acesso a todas as informações que julgavam necessárias à sua '
        'decisão independente de celebração do Contrato e de cada Operação de Derivativos;',
        'i. Que cada Operação de Derivativos tem para a Parte B o intuito de proteção contra '
        'riscos financeiros a que estejam expostas, decorrentes de disparidades de taxas ou '
        'índices entre seus direitos e obrigações, de acordo com as normas aplicáveis e políticas '
        'internas relativas à condução de seus negócios;',
        'j. Que uma Parte não está agindo como agente fiduciário da outra Parte ou como sua '
        'assessora em relação a essa operação;',
        'k. Que estão plenamente cientes de que todas e quaisquer obrigações pecuniárias '
        'decorrentes da celebração de Operações sob o presente Contrato, por suas próprias '
        'naturezas, estão sujeitas a efeitos decorrentes de fatores econômicos e/ou políticos, '
        'entre outros, que podem levar à oscilações bruscas na cotação entre moedas estrangeiras e '
        'a moeda corrente nacional, nos preços de mercadorias, nos índices de preços, nos índices '
        'inflacionários, nas taxas de juros, entre outros e que podem produzir alterações '
        'relevantes nas obrigações pecuniárias assumidas. Diante disso, as Partes reconhecem desde '
        'já serem tais circunstâncias próprias e inerentes a Operações de Derivativos, sendo, '
        'pois, referidas oscilações e alterações previsíveis e até esperadas para todos os fins e '
        'efeitos;',
        'l. Que diante da possibilidade de ocorrência das oscilações e variações mencionadas na '
        'alínea anterior, as Partes reconhecem sua plena ciência de que o eventual aumento abrupto '
        'e significativo do valor das obrigações assumidas não poderá ser tipificado como espécie '
        'de onerosidade excessiva para o fim de escusá-la do cumprimento de suas obrigações;',
        'm. Que buscaram aconselhamento de seus próprios consultores fiscais, jurídicos e '
        'contábeis, no intuito de tomar uma decisão independente sobre a contratação da presente '
        'Operação;',
        'n. Que a Parte A é considerada instituição coberta para fins da Resolução CMN nº 4.662 e, '
        'caso a Parte B não seja uma Entidade Regulada, que a Parte B <b><u>não</u></b> é uma '
        'contraparte coberta para fins da Resolução CMN nº 4.662. Para fins desta declaração, '
        '"Entidades Reguladas" significa as instituições autorizadas a funcionar pelo Banco '
        'Central do Brasil, as entidades abertas ou fechadas de previdência complementar, as '
        'sociedades seguradoras, os fundos de investimento e as companhias securitizadoras; e',
        'o. Que estão cientes da possibilidade do Preço da Mercadoria[i] ser cotado a valores '
        'negativos, o que poderá causar uma perda financeira sem qualquer limite para o Comprador, '
        'e que o cálculo do Valor de Liquidação[i] conforme aqui definido não sofrerá qualquer '
        'ajuste ou a perda para uma das Partes não será limitada de nenhuma forma ainda que o '
        'Preço da Mercadoria[i] seja um número negativo. Ainda assim, as Partes concordam em '
        'manter os parâmetros de cálculo previstos no Contrato e nesta Confirmação.',
    ]
    if palm:
        # Palm Oil traz duas declarações a mais (customização/CVM e Regras e
        # Parâmetros), que empurram as três últimas de m./n./o. para o./p./q.
        decls = decls[:12] + [
            'm. Que esta Operação foi customizada para a Parte B atendendo aos critérios definidos '
            'pela Parte B no momento da contratação, que a Parte B solicitou a contratação desta '
            'Operação à Parte A e que esta Operação não possui garantia de contraparte central '
            'garantidora. Por conta dessas características, a Parte B entende que o custo total '
            'desta Operação, representado pelos parâmetros financeiros aqui estabelecidos, já '
            'constituem informação suficiente para a tomada de decisão de contratação pela Parte B '
            'e portanto, conforme entendimentos da CVM, a Parte A não está obrigada a informar à '
            'Parte B o valor de sua remuneração na qualidade de intermediária de valores '
            'mobiliários para esta Operação;',
            'n. Que as Operações de Derivativos, bem como os direitos e as obrigações delas '
            'decorrentes, sujeitam-se às Regras e Parâmetros de Atuação da Parte A ("Regras e '
            'Parâmetros"), à legislação em vigor, às normas, regulamentos, procedimentos, usos, '
            'práticas e costumes adotados e geralmente aceitos no mercado de capitais brasileiro. '
            'Nesse sentido, A Parte B está ciente que o documento Regras e Parâmetros é parte '
            'integrante do Contrato e sua versão mais recente encontra-se disponível na página '
            'eletrônica da Parte A. A Parte B concorda que as Regras e Parâmetros poderão ser '
            'alteradas unilateralmente pela Parte A e as alterações serão comunicadas '
            'imediatamente à Parte B;',
            decls[12].replace('m. ', 'o. ', 1),
            decls[13].replace('n. ', 'p. ', 1),
            decls[14].replace('o. ', 'q. ', 1),
        ]
    for d in decls:
        st.append(Paragraph(_sub(d), S['item']))

    # Seção 7
    st.append(Paragraph('7. &nbsp;&nbsp; <u>Ratificação</u>', S['section']))
    st.append(Paragraph(
        'A presente Confirmação é parte integrante e inseparável do Contrato, motivo pelo qual as '
        'Partes ratificam, nesta oportunidade, todos os termos nele previstos.', S['body']))
    st.append(Paragraph(
        'E por estarem assim, justas e contratadas, as Partes, por seus representantes legais '
        'devidamente constituídos e com poderes para celebrar Operações de Derivativos, assinam a '
        'presente Confirmação em 2 (duas) vias de igual teor e forma, para o mesmo fim, juntamente '
        'com as testemunhas abaixo.', S['body']))
    st.append(Paragraph('[A próxima página contém as assinaturas da Confirmação de Operação de '
                        'Derivativo]', S['center']))

    # ── Página de assinaturas ────────────────────────────────────────────────
    st.append(PageBreak())
    st.append(Paragraph('[Página de assinaturas da Confirmação de Operação de Derivativo]', S['center']))
    st.append(Paragraph('São Paulo, ' + d_ext + '.', S['sig']))
    st.append(Spacer(1, 14))

    line = '_' * 46

    def _sig_block(name):
        # Nome da parte em linha própria (span nas duas colunas); os dois
        # campos Por:/____/Nome: lado a lado, alinhados na mesma altura.
        data = [
            [Paragraph('<b>' + name + '</b>', S['sigb']), Paragraph('', S['sig'])],
            [Paragraph('Por:', S['sig']), Paragraph('Por:', S['sig'])],
            [Paragraph(line, S['sig']), Paragraph(line, S['sig'])],
            [Paragraph('Nome:', S['sig']), Paragraph('Nome:', S['sig'])],
        ]
        tbl = Table(data, colWidths=[doc.width / 2.0] * 2)
        tbl.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('SPAN', (0, 0), (1, 0)),
            ('TOPPADDING', (0, 1), (-1, 1), 24),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (0, -1), 16),
        ]))
        return tbl

    st.append(_sig_block('BANCO J.P. MORGAN S.A.'))
    st.append(Spacer(1, 24))
    st.append(_sig_block(nome))
    st.append(Spacer(1, 24))
    st.append(Paragraph(
        '<b>Ao assinar a presente Confirmação, os representantes legais das Partes acima '
        'identificados, declaram, expressa e irrevogavelmente, que possuem poderes suficientes '
        'para representar as Partes na contratação da presente Operação de Derivativo.</b>', S['body']))
    st.append(Spacer(1, 18))
    wit = Table([
        [Paragraph('Testemunhas:', S['sig']), Paragraph('', S['sig'])],
        [Paragraph('1. &nbsp;-', S['sig']), Paragraph('2.-', S['sig'])],
        [Paragraph(line, S['sig']), Paragraph(line, S['sig'])],
        [Paragraph('Nome:', S['sig']), Paragraph('Nome:', S['sig'])],
        [Paragraph('RG:', S['sig']), Paragraph('RG:', S['sig'])],
    ], colWidths=[doc.width / 2.0] * 2)
    wit.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                             ('LEFTPADDING', (0, 0), (-1, -1), 0),
                             ('TOPPADDING', (0, 1), (-1, 1), 18)]))
    st.append(wit)

    # ── Anexo I — Tabela de Referência ───────────────────────────────────────
    st.append(PageBreak())
    st.append(Paragraph('ANEXO I À CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS', S['annex']))
    ticker_h = 'Código de Divulgação[i]' if variant == 'platts' else 'Ticker[i]'
    fonte_h = 'Fonte de Divulgação' if variant == 'platts' else 'Bolsa de Valores'
    if variant == 'brl':
        heads = ['i', 'Nº', 'Comprador[i]', ticker_h, fonte_h, 'Quantidade',
                 'Prêmio[i]', 'Parte Devedora do Prêmio[i]', 'Data de Pagamento do Prêmio[i]',
                 'Data Inicial de Verificação USD PTAX[i]', 'Data Final de Verificação USD PTAX[i]',
                 'Taxa Forward[i] (expresso em R$)',
                 'Data Inicial de Verificação da Mercadoria[i]',
                 'Data Final de Verificação da Mercadoria[i]', 'Data de Vencimento[i]']
    elif palm:
        heads = ['i', 'Nº', 'Comprador[i]', ticker_h, fonte_h, 'Código da Bloomberg', 'Quantidade',
                 'Taxa de Conversão da Mercadoria',
                 'Data de Verificação da Taxa de Conversão da Mercadoria',
                 'Prêmio[i]', 'Parte Devedora do Prêmio[i]', 'Data de Pagamento do Prêmio[i]',
                 'Data de Verificação da PTAX[i]', 'Taxa Forward[i]',
                 'Data Inicial de Verificação da Mercadoria[i]',
                 'Data Final de Verificação da Mercadoria[i]', 'Data de Vencimento[i]']
    else:
        heads = ['i', 'Nº', 'Comprador[i]', ticker_h, fonte_h, 'Quantidade',
                 'Prêmio[i]', 'Parte Devedora do Prêmio[i]', 'Data de Pagamento do Prêmio[i]',
                 'Data de Verificação da PTAX[i]', 'Taxa Forward[i]',
                 'Data Inicial de Verificação da Mercadoria[i]',
                 'Data Final de Verificação da Mercadoria[i]', 'Data de Vencimento[i]']
    data = [[Paragraph(_sub(_e(h)), S['th']) for h in heads]]
    for i, r in enumerate(conf.get('rows') or [], start=1):
        cells = [
            Paragraph('<b>%d</b>' % i, S['td']),
            Paragraph(_e(r.get('num')), S['td']),
            Paragraph(_e(r.get('comprador')), S['td']),
            Paragraph(_e(r.get('ticker')), S['td']),
            Paragraph(_e(r.get('bolsa')), S['td']),
        ]
        if palm:
            cells.append(Paragraph(_e(r.get('bbg')), S['td']))
        cells.append(Paragraph(_e(r.get('qtd')), S['td']))
        if palm:
            cells.append(Paragraph(_e(r.get('taxaConv')), S['td']))
            cells.append(Paragraph(_e(r.get('dtTaxaConv')), S['td']))
        cells += [
            Paragraph(_e(r.get('premio')), S['td']),
            Paragraph(_e(r.get('devedor')), S['td']),
            Paragraph(_e(r.get('dtPremio')), S['td']),
        ]
        if variant == 'brl':
            cells.append(Paragraph(_e(r.get('ptaxIni')), S['td']))
            cells.append(Paragraph(_e(r.get('ptaxFim')), S['td']))
        else:
            cells.append(Paragraph(_e(r.get('ptax')), S['td']))
        cells += [
            Paragraph(_e(r.get('forward')), S['td']),
            Paragraph(_e(r.get('dtIni')), S['td']),
            Paragraph(_e(r.get('dtFim')), S['td']),
            Paragraph(_e(r.get('dtVenc')), S['td']),
        ]
        data.append(cells)
    w = doc.width
    if variant == 'brl':
        widths = [w * f for f in (0.025, 0.085, 0.055, 0.09, 0.06, 0.06, 0.05, 0.065,
                                  0.07, 0.075, 0.075, 0.065, 0.08, 0.08, 0.065)]
    elif palm:
        widths = [w * f for f in (0.02, 0.075, 0.05, 0.07, 0.075, 0.055, 0.05, 0.055,
                                  0.075, 0.045, 0.06, 0.06, 0.06, 0.055, 0.065, 0.065, 0.06)]
    else:
        widths = [w * f for f in (0.025, 0.09, 0.06, 0.10, 0.065, 0.06, 0.055, 0.07,
                                  0.075, 0.075, 0.065, 0.09, 0.09, 0.08)]
    tbl = Table(data, colWidths=widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, _BLACK),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    st.append(tbl)

    if palm:
        st += _anexo_ii(S)

    doc.build(st)
    return buf.getvalue()


def opcao_pdf(conf, variant='usd'):
    """Bytes do PDF da confirmação de Opção de Commodities (strike em USD).

    Mesmo esqueleto do termo_pdf; o texto legal é o do OPÇÃO COMMODITY.doc
    legado (cláusulas de call/put e definições a–p) e o Anexo I tem 16
    colunas (Tipo da Opção, Forma de Exercício, Preço de Exercício, Data de
    Exercício)."""
    S = _styles()
    buf = BytesIO()
    page = landscape(A4)
    doc = BaseDocTemplate(buf, pagesize=page,
                          leftMargin=18 * mm, rightMargin=18 * mm,
                          topMargin=15 * mm, bottomMargin=15 * mm,
                          title='Confirmação de Operações de Derivativos')
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='f')
    doc.addPageTemplates([PageTemplate(id='p', frames=[frame])])

    cgd   = _e(conf.get('cgd_date'))
    nome  = _e(conf.get('parteb_nome'))
    cnpj  = _e(conf.get('parteb_cnpj'))
    d_neg = _e(conf.get('data_neg'))
    d_ext = _e(conf.get('data_extenso'))

    st = []
    st.append(Paragraph('CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS', S['title']))
    st.append(Paragraph(
        'Esta Confirmação ("Confirmação") tem por objetivo reger as Operações de Derivativos a '
        'Parte A e a Parte B abaixo qualificadas, de acordo com as disposições legais e '
        'regulamentares aplicáveis e no âmbito do <i>Contrato Global de Derivativos e do Apêndice '
        'ao Contrato Global de Derivativos</i>, ambos firmados entre as Partes em ' + cgd +
        ' ("Contrato"), cujos termos são incorporados por referência a este instrumento.', S['body']))

    # Seção 1
    st.append(Paragraph('1. &nbsp;&nbsp; <u>Definições Gerais</u>', S['section']))
    st.append(Paragraph(
        'Os termos não definidos nesta Confirmação terão os mesmos significados a eles atribuídos '
        'no Contrato. Em caso de conflito entre uma definição do Contrato e a desta Confirmação, '
        'prevalecerá, para os fins de cada Operação de Derivativo, a definição que constar desta '
        'Confirmação.', S['body']))
    st.append(Paragraph(_sub(
        'Esta Confirmação formaliza uma ou mais Operações de Derivativos (referidas doravante de '
        'forma individual e indistinta como "Operação[i]") contratadas na mesma data entre as '
        'Partes individualizadas abaixo na Tabela Referência. No entanto, cada Operação de '
        'Derivativo é uma operação individual para fins tributários e de registro, sem prejuízo '
        'das disposições do Contrato que tratam da compensação e do cálculo do Valor de '
        'Vencimento Antecipado.'), S['body']))
    st.append(Paragraph(
        'Para fins dos cálculos descritos nessa Confirmação, a quantidade de Dias Úteis será '
        'apurada pelo Agente de Cálculo conforme as convenções e as práticas de mercado para '
        'contagem de dias úteis a depender da taxa, índice ou preço utilizado como referência em '
        'uma Operação de Derivativo.', S['body']))

    # Seção 2
    st.append(Paragraph('2. &nbsp;&nbsp; <u>Definição das Partes</u>', S['section']))
    st.append(_parties_block(doc, S, nome, cnpj))
    st.append(Spacer(1, 8))
    st.append(Paragraph(
        'A Parte A e a Parte B, além destas denominações, são também aqui individualmente '
        'denominadas "Parte", e em conjunto "Partes".', S['item']))
    st.append(Paragraph('c. &nbsp;&nbsp; <b>Agente de Cálculo:</b> Parte A, salvo se disposto de '
                        'outra forma no Apêndice', S['item']))
    st.append(Paragraph('d. &nbsp;&nbsp; <b>Acelerador:</b> Parte A', S['item']))

    # Seção 3
    st.append(Paragraph('3. &nbsp;&nbsp; <u>Disposições Gerais</u>', S['section']))
    st.append(Paragraph('a. <b>Local do Registro:</b> B3 S.A. – Brasil, Bolsa, Balcão;', S['item']))
    st.append(Paragraph('b. <b>Data de Negociação:</b> ' + d_neg + ';', S['item']))
    st.append(Paragraph('c. <b>Tipo de Operação:</b> Opção;', S['item']))
    st.append(Paragraph(_sub(
        'd. <b>Tipo de Opção:</b> Para cada Operação[i], conforme especificado no Anexo I'), S['item']))
    st.append(Paragraph(_sub(
        'e. <b>Prêmio:</b> Para cada Operação[i], será o valor de Prêmio especificado no Anexo I '
        'a ser pago pelo Comprador ao Vendedor na Data de Pagamento do Prêmio;'), S['item']))
    st.append(Paragraph(_sub(
        'f. <b>Data de Pagamento do Prêmio[i]:</b> Para cada Operação[i], significa a data '
        'indicada na Tabela de Referência em que o Prêmio[i] deverá ser pago ao Vendedor.'), S['item']))
    st.append(Paragraph(_sub(
        'g. <b>Tabela de Referência:</b> Os dados e condições financeiras aplicáveis a cada '
        'Operação[i] contratada entre as Partes na Data de Negociação estão descritos na Tabela '
        'de Referência disposta no Anexo I.'), S['item']))

    # Seção 4
    st.append(Paragraph('4. &nbsp;&nbsp; <u>Cálculo do Valor de Liquidação de cada Operação:</u>', S['section']))
    st.append(Paragraph(_sub(
        '<b>4.1.</b> A Operação de Opção de Compra é a operação em que o Comprador do Vendedor '
        'adquire a opção de comprar a Quantidade de Mercadoria por um preço de exercício '
        'determinado entre as Partes. A Operação de Opção de Venda é a operação em que o '
        'Comprador do Vendedor adquire a opção de vender a Quantidade de Mercadoria por um preço '
        'de exercício determinado entre as Partes. A Opção de Compra e a Opção de Venda são '
        'doravante referidas de forma indistinta meramente como "Opção". Para adquirir o direito '
        'de compra ou de venda, conforme o caso, o Comprador pagará um valor de Prêmio ao '
        'vendedor em cada Operação[i]. Cada Operação[i] de Opção descrita nessa Confirmação será '
        'liquidada por diferença em Reais, conforme a fórmula de cálculo disposta abaixo:'), S['body']))
    st.append(Paragraph(_sub(
        'Na Data de Exercício ou na Data Final de Verificação da Mercadoria de uma Operação[i], '
        'a depender da Forma de Exercício, o Agente de Cálculo apurará, com base nas variáveis '
        'aplicáveis à respectiva Operação[i], conforme indicadas na Tabela de Referência, o Valor '
        'de Liquidação[i] a ser pago por uma Parte à outra, na forma seguir:'), S['body']))
    st.append(Paragraph(_sub(
        'a. &nbsp; <b>Opção de Compra (call):</b> Caso, na Data de Exercício[i], o Preço Final da '
        'Mercadoria[i] seja superior ao Preço de Exercício[i] e consequentemente seja exercida a '
        'opção de compra, o Valor de Liquidação significa o montante a ser pago pelo Vendedor[i] '
        'ao Comprador[i], na Data de Vencimento[i], correspondente à diferença positiva entre o '
        'Preço Final da Mercadoria[i] e o Preço de Exercício[i], multiplicado pela Quantidade[i], '
        'conforme a relação abaixo.'), S['item']))
    st.append(Paragraph(_sub(
        'Valor de Liquidação[i] = Máx[(Preço Final da Mercadoria[i] – Preço de Exercício[i]); 0] '
        'x Quantidade[i]'), S['formula']))
    st.append(Paragraph(_sub(
        'b. &nbsp; <b>Opção de Venda (put):</b> Caso, na Data de Exercício[i], o Preço Final da '
        'Mercadoria[i] seja inferior ao Preço de Exercício[i] e consequentemente seja exercida a '
        'opção de venda, o Valor de Liquidação[i] significa o montante a ser pago pelo '
        'Vendedor[i] ao Comprador[i], na Data de Vencimento[i], correspondente à diferença '
        'positiva entre o Preço de Exercício[i] e o Preço Final[i], multiplicado pela Quantidade, '
        'conforme a relação abaixo.'), S['item']))
    st.append(Paragraph(_sub(
        'Valor de Liquidação[i] = Máx[(Preço de Exercício[i] – Preço Final da Mercadoria[i]); 0] '
        'x Quantidade[i]'), S['formula']))
    st.append(Paragraph(
        '<b>4.2.</b> Para fins da metodologia de cálculo acima, os seguintes termos terão as '
        'definições que lhe são atribuídas conforme abaixo:', S['body']))
    defs42 = [
        'a. <b>Mercadoria[i]:</b> Para cada Operação[i], significa o contrato futuro de '
        'mercadoria (commodity) cujo código de negociação - Ticker[i] - na respectiva Bolsa de '
        'Valores está indicado na Tabela de Referência.',
        'b. <b>Comprador[i]:</b> Para cada Operação[i], significa a Parte compradora da Opção, '
        'conforme indicada na Tabela de Referência;',
        'c. <b>Data de Vencimento[i]:</b> significa a data em que ocorrerá a liquidação de cada '
        'Operação[i], conforme indicadas na Tabela de Referência, mediante o desembolso do Valor '
        'de Liquidação[i] pelo Comprador[i] ou pelo Vendedor[i], de acordo com a apuração '
        'realizada pelo Agente de Cálculo na forma da cláusula anterior;',
        'd. <b>Data de Exercício[i]:</b> Para cada Operação[i], significa a data indicada na '
        'Tabela de Referência na qual o Comprador poderá exercer a Opção. Para as Opções '
        'Asiáticas, a Data de Exercício é a Data Final de Verificação da Mercadoria[i].',
        'e. <b>Data de Verificação[i]:</b> Significa a Data de Exercício no caso das Opções '
        'Européias ou cada dia útil dentro do Período de Verificação do Preço da Mercadoria no '
        'caso de Opções Asiáticas.',
        'f. <b>Data Inicial de Verificação da Mercadoria[i]:</b> para cada Operação[i] que seja '
        'uma Opção Asiática, significa a data indicada na Tabela de Referência.',
        'g. <b>Data Final de Verificação da Mercadoria[i]:</b> para cada Operação[i] que seja '
        'uma Opção Asiática, significa a data indicada na Tabela de Referência.',
        'h. <b>Forma de Exercício:</b> significa a Forma de Exercício indicada na Tabela de '
        'Referência dentre as alternativas abaixo: '
        'i. <b>Europeia.</b> O Preço Final da Mercadoria a ser utilizado no cálculo do Valor de '
        'Liquidação da Operação[i] será apurado com referência ao Preço da Mercadoria divulgada '
        'na Data de Exercício[i]. Na respectiva Data de Exercício da Operação[i], caso o Valor '
        'de Liquidação a ser pago pelo Vendedor seja positivo, então a Opção será exercida '
        'automaticamente, independentemente de qualquer manifestação do Comprador[i]. '
        'ii. <b>Asiática:</b> O Preço Final da Mercadoria a ser utilizado no cálculo do Valor de '
        'Liquidação da Operação[i] será apurado com referência à média simples dos Preços da '
        'Mercadoria apuradas diariamente no Período de Verificação do Preço da Mercadoria. Na '
        'respectiva Data Final de Verificação da Mercadoria[i], caso o Valor de Liquidação a ser '
        'pago pelo Vendedor seja positivo, então a Opção será exercida automaticamente, '
        'independentemente de qualquer manifestação do Comprador.',
        'i. <b>Quantidade[i]:</b> Para cada Operação[i], significa a quantidade indicada na '
        'Tabela da Referência;',
        'j. <b>Período de Verificação do Preço da Mercadoria:</b> significa todos os dias úteis '
        'entre a Data Inicial de Verificação da Mercadoria[i] (inclusive) e a Data Final de '
        'Verificação da Mercadoria[i]; (inclusive);',
        'k. <b>Preço da Mercadoria[i]:</b> significa o preço de fechamento do contrato futuro da '
        'Mercadoria referente ao Ticker[i] divulgado pela Bolsa de Valores[i] na Data de '
        'Verificação[i].',
        'l. <b>Preço Final da Mercadoria[i]:</b> '
        'i. Para Opções Européias, o Preço Final[i] será a Preço da Mercadoria apurada na Data '
        'de Exercício[i]. '
        'ii. Para Opções Asiáticas, o Preço Final[i] será a média simples dos Preços da '
        'Mercadoria apuradas em cada dia útil do Período de Verificação do Preço da Mercadoria. '
        'Caso o Preço Final da Mercadoria[i] seja cotado em dólares norte-americanos, o Preço '
        'Final da Mercadoria[i] será convertido para Reais pela USD PTAX;',
        'm. <b>Preço de Exercício[i]:</b> para cada Operação[i], indicado na Tabela de '
        'Referência pelo qual o Vendedor se obrigou a vender ou a comprar do Comprador a '
        'Mercadoria[i], conforme o Tipo de Opção.',
        'n. <b>USD PTAX:</b> significa a taxa de conversão entre o Real ("BRL") e o Dólar dos '
        'Estados Unidos ("USD"), expressa pela quantidade de Reais por cada Dólar dos Estados '
        'Unidos, referente a operações interbancárias de venda de Dólares dos Estados Unidos com '
        'liquidação em dois dias úteis, conforme apurada pelo Banco Central do Brasil, e que pode '
        'ser obtida na página da internet http://www.bcb.gov.br/?txcambio, opção "Cotações e '
        'boletins", por volta das 13:15 horas divulgada na Data de Verificação da PTAX[i].;',
        'o. <b>Data de Verificação da PTAX[i]:</b> Para cada Operação[i], significa a data '
        'indicada na Tabela de Referência; e',
        'p. <b>Vendedor[i]:</b> para cada Operação[i], significa a outra Parte que não a Parte '
        'indicada como Comprador[i] na Tabela da Referência.',
    ]
    for d in defs42:
        st.append(Paragraph(_sub(d), S['item']))

    # Seção 5 — Declarações (mesmo texto do Termo)
    st.append(Paragraph('5. &nbsp;&nbsp; <u>Declarações:</u>', S['section']))
    st.append(Paragraph(
        'Em adição às declarações feitas no Contrato, e como condição para a celebração desta '
        'Confirmação, as Partes e o Garantidor, se aplicável, declaram individualmente:', S['body']))
    decls = [
        'a. Que estão agindo por conta própria, tendo tomado de forma independente a decisão '
        'quanto a realizar a presente Operação de Derivativo, bem como quanto à adequação e '
        'conveniência da mesma, com base em critérios próprios e, na medida que cada uma '
        'considerou necessária, na opinião de seus próprios consultores;',
        'b. Que não estão se baseando em qualquer comunicação (escrita ou verbal) da outra parte, '
        'ou de qualquer pessoa agindo em seu nome, como forma de orientação para investimento ou '
        'recomendação para participar da presente operação, ficando entendido que as informações e '
        'explicações relativas aos termos e condições desta ou de qualquer outra Operação de '
        'Derivativo, não deverão ser consideradas como orientação de investimento, nem como '
        'recomendação de participação;',
        'c. Que nenhuma comunicação (escrita ou verbal), recebida de uma Parte, ou de qualquer '
        'pessoa agindo em seu nome, pela outra, será considerada como seguro ou garantia quanto à '
        'expectativa dos resultados previstos da Operação;',
        'd. Que têm conhecimento e experiência dentro do mercado de derivativos, suficientes para '
        'entender a estrutura de cada Operação de Derivativos, incluindo, sem limitação, os '
        'critérios determinados no Contrato para a apuração do Valor de Reposição, com os quais '
        'concordam sem restrições;',
        'e. Que estão cientes dos riscos inerentes às Operações de Derivativos e têm plena '
        'capacidade financeira para assumir as obrigações que venham a ser exigíveis em '
        'decorrência das Operações contratadas, mesmo nos piores cenários econômicos, bem como '
        'capacidade técnica e operacional para cumprir todas as obrigações estabelecidas no '
        'Contrato e em quaisquer Confirmações;',
        'f. Que as declarações prestadas de acordo do Contrato continuam plenamente válidas;',
        'g. Que tiveram a oportunidade de discutir absolutamente todos os termos do Contrato e de '
        'cada Confirmação, incluindo, mas não se limitando, a forma de resolução de conflitos e os '
        'critérios de cálculo, assumindo total responsabilidade pelos mesmos;',
        'h. Que tiveram prévio acesso a todas as informações que julgavam necessárias à sua '
        'decisão independente de celebração do Contrato e de cada Operação de Derivativos;',
        'i. Que cada Operação de Derivativos tem para a Parte B o intuito de proteção contra '
        'riscos financeiros a que estejam expostas, decorrentes de disparidades de taxas ou '
        'índices entre seus direitos e obrigações, de acordo com as normas aplicáveis e políticas '
        'internas relativas à condução de seus negócios;',
        'j. Que uma Parte não está agindo como agente fiduciário da outra Parte ou como sua '
        'assessora em relação a essa operação;',
        'k. Que estão plenamente cientes de que todas e quaisquer obrigações pecuniárias '
        'decorrentes da celebração de Operações sob o presente Contrato, por suas próprias '
        'naturezas, estão sujeitas a efeitos decorrentes de fatores econômicos e/ou políticos, '
        'entre outros, que podem levar à oscilações bruscas na cotação entre moedas estrangeiras e '
        'a moeda corrente nacional, nos preços de mercadorias, nos índices de preços, nos índices '
        'inflacionários, nas taxas de juros, entre outros e que podem produzir alterações '
        'relevantes nas obrigações pecuniárias assumidas. Diante disso, as Partes reconhecem desde '
        'já serem tais circunstâncias próprias e inerentes a Operações de Derivativos, sendo, '
        'pois, referidas oscilações e alterações previsíveis e até esperadas para todos os fins e '
        'efeitos;',
        'l. Que diante da possibilidade de ocorrência das oscilações e variações mencionadas na '
        'alínea anterior, as Partes reconhecem sua plena ciência de que o eventual aumento abrupto '
        'e significativo do valor das obrigações assumidas não poderá ser tipificado como espécie '
        'de onerosidade excessiva para o fim de escusá-la do cumprimento de suas obrigações;',
        'm. Que buscaram aconselhamento de seus próprios consultores fiscais, jurídicos e '
        'contábeis, no intuito de tomar uma decisão independente sobre a contratação da presente '
        'Operação;',
        'n. Que a Parte A é considerada instituição coberta para fins da Resolução CMN nº 4.662 e, '
        'caso a Parte B não seja uma Entidade Regulada, que a Parte B <b><u>não</u></b> é uma '
        'contraparte coberta para fins da Resolução CMN nº 4.662. Para fins desta declaração, '
        '"Entidades Reguladas" significa as instituições autorizadas a funcionar pelo Banco '
        'Central do Brasil, as entidades abertas ou fechadas de previdência complementar, as '
        'sociedades seguradoras, os fundos de investimento e as companhias securitizadoras; e',
        'o. Que estão cientes da possibilidade do Preço da Mercadoria[i] ser cotado a valores '
        'negativos, o que poderá causar uma perda financeira sem qualquer limite para o Comprador, '
        'e que o cálculo do Valor de Liquidação[i] conforme aqui definido não sofrerá qualquer '
        'ajuste ou a perda para uma das Partes não será limitada de nenhuma forma ainda que o '
        'Preço da Mercadoria[i] seja um número negativo. Ainda assim, as Partes concordam em '
        'manter os parâmetros de cálculo previstos no Contrato e nesta Confirmação.',
    ]
    for d in decls:
        st.append(Paragraph(_sub(d), S['item']))

    # Seção 6 — Ratificação
    st.append(Paragraph('6. &nbsp;&nbsp; <u>Ratificação</u>', S['section']))
    st.append(Paragraph(
        'A presente Confirmação é parte integrante e inseparável do Contrato, motivo pelo qual as '
        'Partes ratificam, nesta oportunidade, todos os termos nele previstos.', S['body']))
    st.append(Paragraph(
        'E por estarem assim, justas e contratadas, as Partes, por seus representantes legais '
        'devidamente constituídos e com poderes para celebrar Operações de Derivativos, assinam a '
        'presente Confirmação em 2 (duas) vias de igual teor e forma, para o mesmo fim, juntamente '
        'com as testemunhas abaixo.', S['body']))
    st.append(Paragraph('[A próxima página contém as assinaturas da Confirmação de Operação de '
                        'Derivativo]', S['center']))

    # ── Página de assinaturas ────────────────────────────────────────────────
    st.append(PageBreak())
    st.append(Paragraph('[Página de assinaturas da Confirmação de Operação de Derivativo]', S['center']))
    st.append(Paragraph('São Paulo, ' + d_ext + '.', S['sig']))
    st.append(Spacer(1, 14))

    line = '_' * 46

    def _sig_block(name):
        # Nome da parte em linha própria (span nas duas colunas); os dois
        # campos Por:/____/Nome: lado a lado, alinhados na mesma altura.
        data = [
            [Paragraph('<b>' + name + '</b>', S['sigb']), Paragraph('', S['sig'])],
            [Paragraph('Por:', S['sig']), Paragraph('Por:', S['sig'])],
            [Paragraph(line, S['sig']), Paragraph(line, S['sig'])],
            [Paragraph('Nome:', S['sig']), Paragraph('Nome:', S['sig'])],
        ]
        tbl = Table(data, colWidths=[doc.width / 2.0] * 2)
        tbl.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('SPAN', (0, 0), (1, 0)),
            ('TOPPADDING', (0, 1), (-1, 1), 24),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (0, -1), 16),
        ]))
        return tbl

    st.append(_sig_block('BANCO J.P. MORGAN S.A.'))
    st.append(Spacer(1, 24))
    st.append(_sig_block(nome))
    st.append(Spacer(1, 24))
    st.append(Paragraph(
        '<b>Ao assinar a presente Confirmação, os representantes legais das Partes acima '
        'identificados, declaram, expressa e irrevogavelmente, que possuem poderes suficientes '
        'para representar as Partes na contratação da presente Operação de Derivativo.</b>', S['body']))
    st.append(Spacer(1, 18))
    wit = Table([
        [Paragraph('Testemunhas:', S['sig']), Paragraph('', S['sig'])],
        [Paragraph('1. &nbsp;-', S['sig']), Paragraph('2.-', S['sig'])],
        [Paragraph(line, S['sig']), Paragraph(line, S['sig'])],
        [Paragraph('Nome:', S['sig']), Paragraph('Nome:', S['sig'])],
        [Paragraph('RG:', S['sig']), Paragraph('RG:', S['sig'])],
    ], colWidths=[doc.width / 2.0] * 2)
    wit.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                             ('LEFTPADDING', (0, 0), (-1, -1), 0),
                             ('TOPPADDING', (0, 1), (-1, 1), 18)]))
    st.append(wit)

    # ── Anexo I — Tabela de Referência (16 colunas) ──────────────────────────
    st.append(PageBreak())
    st.append(Paragraph('ANEXO I À CONFIRMAÇÃO DE OPERAÇÕES DE DERIVATIVOS', S['annex']))
    heads = ['i', 'Nº', 'Tipo da Opção[i]', 'Forma de Exercício', 'Ticker[i]',
             'Bolsa de Valores', 'Quantidade', 'Data de Verificação da PTAX[i]',
             'Comprador[i]', 'Prêmio[i]', 'Data de Pagamento do Prêmio[i]',
             'Preço de Exercício[i]',
             'Data Inicial de Verificação da Mercadoria[i]',
             'Data Final de Verificação da Mercadoria[i]',
             'Data de Exercício[i]', 'Data de Vencimento[i]']
    data = [[Paragraph(_sub(_e(h)), S['th']) for h in heads]]
    for i, r in enumerate(conf.get('rows') or [], start=1):
        data.append([
            Paragraph('<b>%d</b>' % i, S['td']),
            Paragraph(_e(r.get('num')), S['td']),
            Paragraph(_e(r.get('tipo')), S['td']),
            Paragraph(_e(r.get('forma')), S['td']),
            Paragraph(_e(r.get('ticker')), S['td']),
            Paragraph(_e(r.get('bolsa')), S['td']),
            Paragraph(_e(r.get('qtd')), S['td']),
            Paragraph(_e(r.get('ptax')), S['td']),
            Paragraph(_e(r.get('comprador')), S['td']),
            Paragraph(_e(r.get('premio')), S['td']),
            Paragraph(_e(r.get('dtPremio')), S['td']),
            Paragraph(_e(r.get('strike')), S['td']),
            Paragraph(_e(r.get('dtIni')), S['td']),
            Paragraph(_e(r.get('dtFim')), S['td']),
            Paragraph(_e(r.get('dtExerc')), S['td']),
            Paragraph(_e(r.get('dtVenc')), S['td']),
        ])
    w = doc.width
    widths = [w * f for f in (0.02, 0.08, 0.05, 0.055, 0.08, 0.055, 0.05, 0.07,
                              0.05, 0.065, 0.07, 0.06, 0.08, 0.08, 0.065, 0.07)]
    tbl = Table(data, colWidths=widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, _BLACK),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
    ]))
    st.append(tbl)

    doc.build(st)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
# OPÇÃO DE CÂMBIO (FXO) — PDF a partir do PRÓPRIO documento
# ------------------------------------------------------------------------------
# As confirmações anteriores têm duas cópias do texto legal: o template Jinja e
# a réplica em reportlab deste módulo, mantidas em sincronia à mão. Nos dois
# documentos de FXO isso não serve: eles são o export do Word intocado ("não
# misture templates nem altere nada, tem que manter 100% do texto original"), e
# uma segunda cópia digitada seria justamente o que pode divergir.
#
# Então aqui o PDF é gerado a partir do HTML do documento já renderizado — o
# mesmo que vira o .doc. O texto não tem como divergir porque é o mesmo texto;
# o que este conversor faz é só transpor a estrutura (parágrafos, negrito,
# tabelas, quebras de página) para flowables do reportlab. O layout fica no
# padrão dos outros PDFs do módulo, não pixel a pixel igual ao Word — como já
# acontece com as demais réplicas.
# ══════════════════════════════════════════════════════════════════════════════
from html.parser import HTMLParser                                    # noqa: E402

from reportlab.platypus import HRFlowable                             # noqa: E402

_FX_INLINE = {'b': 'b', 'strong': 'b', 'i': 'i', 'em': 'i', 'u': 'u',
              'sub': 'sub', 'sup': 'super'}
_FX_DROP = {'style', 'script', 'title', 'head', 'meta', 'link'}


class _WordHtmlToFlowables(HTMLParser):
    """Converte o HTML do documento do Word em flowables do reportlab.

    Só o que o documento realmente usa: parágrafos, ênfases inline, tabelas
    (as duas de assinatura, sem borda, e o Anexo I com borda), a régua acima
    da página de assinaturas e as quebras de página do Word
    (<br style="page-break-before: always">)."""

    def __init__(self, S, width):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.S, self.width = S, width
        self.flow = []
        self.buf = []          # trechos inline do parágrafo/célula corrente
        self.drop = 0          # dentro de <style>/<script>/…
        self.align = None      # alinhamento do <p> corrente
        self.block = 'p'       # tag do bloco corrente (h2 = título do documento)
        self.tables = []       # pilha de tabelas (o documento não aninha, mas custa nada)
        self.open = []         # ênfases abertas, para fechar/reabrir a cada bloco

    # ── coleta ──────────────────────────────────────────────────────────────
    def _txt(self):
        """Texto do bloco corrente com as ênfases balanceadas.

        No Word um <i> costuma abrir antes de um <p> e fechar depois dele; o
        reportlab exige a marcação fechada dentro do parágrafo, então cada
        bloco fecha o que estiver aberto e o próximo reabre."""
        s = ''.join(self.buf) + ''.join('</%s>' % t for t in reversed(self.open))
        self.buf = ['<%s>' % t for t in self.open]
        s = s.replace('\n', ' ')
        while '  ' in s:
            s = s.replace('  ', ' ')
        s = s.strip()
        return '' if not re.sub(r'<[^>]*>|&nbsp;|\s|\xa0', '', s) else s

    def _style(self, name):
        # h1..h6 são os títulos do documento (no Word: centralizados e em
        # negrito) — no corpo o que manda é o align do parágrafo.
        if self.block and self.block[0] == 'h' and self.block[1:].isdigit():
            return self.S['doctitle']
        if self.align == 'center' and name in ('body', 'sig'):
            return self.S['centered']
        return self.S[name]

    def _emit(self, text):
        """Fecha o bloco corrente: vai para a célula da tabela ou para o corpo."""
        if self.tables and self.tables[-1]['cell'] is not None:
            if text:
                self.tables[-1]['cell'].append(text)
            return
        if not text:
            # parágrafo vazio do Word (<o:p>&nbsp;</o:p>) — vira respiro, não
            # uma linha em branco de altura cheia
            if self.flow and not isinstance(self.flow[-1], Spacer):
                self.flow.append(Spacer(1, 5))
        else:
            self.flow.append(Paragraph(text, self._style('body')))

    def _flush(self):
        text = self._txt()
        self._emit(text)
        return text

    # ── HTMLParser ──────────────────────────────────────────────────────────
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in _FX_DROP:
            self.drop += 1
            return
        if self.drop:
            return
        if tag in _FX_INLINE:
            self.open.append(_FX_INLINE[tag])
            self.buf.append('<%s>' % _FX_INLINE[tag])
        elif tag == 'br':
            if 'page-break-before' in (a.get('style') or ''):
                self._flush()
                if not self.tables:
                    self.flow.append(PageBreak())
            else:
                self.buf.append('<br/>')
        elif tag in ('p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._flush()
            style = (a.get('style') or '')
            self.align = a.get('align') or ('center' if 'text-align: center' in style else None)
            self.block = tag
        elif tag == 'table':
            self._flush()
            self.tables.append({'rows': [], 'row': None, 'cell': None,
                                'grid': str(a.get('border') or '0') != '0'})
        elif tag == 'tr' and self.tables:
            self.tables[-1]['row'] = []
        elif tag in ('td', 'th') and self.tables:
            self.buf, self.open = [], []
            self.tables[-1]['cell'] = []
        elif tag == 'div' and 'solid' in (a.get('style') or ''):
            # a régua que o Word desenha como borda inferior de um <div> vazio
            self._flush()
            self.flow.append(HRFlowable(width='100%', thickness=1.2, color=_BLACK,
                                        spaceBefore=10, spaceAfter=6))

    def handle_endtag(self, tag):
        if tag in _FX_DROP:
            self.drop = max(0, self.drop - 1)
            return
        if self.drop:
            return
        if tag in _FX_INLINE:
            name = _FX_INLINE[tag]
            if name in self.open:                 # o Word fecha o que não abriu
                self.open.reverse()
                self.open.remove(name)
                self.open.reverse()
                self.buf.append('</%s>' % name)
        elif tag in ('p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._flush()
            self.align, self.block = None, 'p'
        elif tag in ('td', 'th') and self.tables:
            t = self.tables[-1]
            self._flush()
            # a célula guarda TEXTO: o tamanho da fonte depende de quantas
            # colunas a tabela tem, e isso só se sabe no </table>
            cell = [c for c in (t['cell'] or []) if c]
            t['cell'] = None
            if t['row'] is None:
                t['row'] = []
            t['row'].append(cell)
        elif tag == 'tr' and self.tables:
            t = self.tables[-1]
            if t['row']:
                t['rows'].append(t['row'])
            t['row'] = None
        elif tag == 'table' and self.tables:
            self._table(self.tables.pop())

    def handle_data(self, data):
        if self.drop or not data:
            return
        self.buf.append(_e(data))

    # ── tabelas ─────────────────────────────────────────────────────────────
    def _table(self, t):
        raw = [r for r in t['rows'] if r]
        if not raw:
            return
        ncol = max(len(r) for r in raw)
        # Anexo I do Asian tem 16 colunas em A4 paisagem: a 7,5pt do estilo
        # padrão um deal name ('D5XO-S7U6K') não cabe na célula e quebra no
        # meio. A fonte acompanha a largura disponível, com piso de 5,5pt.
        if t['grid'] and ncol > 12:
            size = max(5.5, 7.5 * 12.0 / ncol)
            style = ParagraphStyle('tdn', parent=self.S['tdc'],
                                   fontSize=size, leading=size + 1.5)
        else:
            style = self.S['tdc'] if t['grid'] else self.S['sig']
        rows = [[[Paragraph(c, style) for c in cell] or Paragraph('', style)
                 for cell in r] for r in raw]
        rows = [r + [''] * (ncol - len(r)) for r in rows]
        if t['grid']:
            # Anexo I: primeira coluna estreita (o índice i), o resto igual.
            unit = self.width / (ncol - 0.6)
            widths = [unit * 0.4] + [unit] * (ncol - 1)
            cmds = [('GRID', (0, 0), (-1, -1), 0.5, _BLACK),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                    ('LEFTPADDING', (0, 0), (-1, -1), 1.5),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 1.5)]
            tbl = Table(rows, colWidths=widths, repeatRows=1)
        else:
            widths = [self.width / float(ncol)] * ncol
            # Tabelas sem borda são as de assinatura e a de testemunhas. O Word
            # alinha as duas colunas empilhando parágrafos VAZIOS, que o _emit
            # descarta (viram respiro, não linha) — sem eles o "Por:/Nome:" da
            # direita subia para o topo da célula. Alinhar pelo rodapé dispensa
            # a contagem de linhas em branco e ainda aguenta o nome da
            # contraparte quebrar em duas linhas, que desalinhava até no Word.
            cmds = [('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6)]
            tbl = Table(rows, colWidths=widths)
        tbl.setStyle(TableStyle(cmds))
        target = (self.tables[-1]['cell'] if (self.tables and self.tables[-1]['cell'] is not None)
                  else None)
        if target is None:
            self.flow.append(tbl)


def opcao_fx_pdf(conf, variant='vanilla', doc_html=None):
    """Bytes do PDF da confirmação de Opção de Câmbio (FXO).

    `doc_html` é o documento já renderizado (o mesmo HTML que vira o .doc) —
    é dele que sai TODO o texto, para não existir uma segunda transcrição do
    documento do Word. `variant` ('vanilla' | 'asian') só escolhe o template
    quando o chamador não manda o HTML pronto, e serve de rótulo do arquivo."""
    if not doc_html:
        raise ValueError('opcao_fx_pdf: doc_html é obrigatório (HTML do documento renderizado)')
    S = _styles()
    S['centered'] = ParagraphStyle('centered', parent=S['body'], alignment=1)
    S['doctitle'] = ParagraphStyle('doctitle', parent=S['body'], fontName='Times-Bold',
                                   fontSize=12, leading=15, alignment=1,
                                   spaceBefore=6, spaceAfter=10)
    S['tdc'] = ParagraphStyle('tdc', parent=S['td'], alignment=1)

    buf = BytesIO()
    doc = BaseDocTemplate(buf, pagesize=landscape(A4),
                          leftMargin=18 * mm, rightMargin=18 * mm,
                          topMargin=15 * mm, bottomMargin=15 * mm,
                          title='Confirmação de Operações de Derivativos')
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='f')
    doc.addPageTemplates([PageTemplate(id='p', frames=[frame])])

    body = doc_html[doc_html.find('<body'):] or doc_html
    parser = _WordHtmlToFlowables(S, doc.width)
    parser.feed(body)
    parser.close()
    parser._flush()
    doc.build(parser.flow or [Paragraph('', S['body'])])
    return buf.getvalue()
