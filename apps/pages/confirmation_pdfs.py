# -*- coding: utf-8 -*-
"""PDFs das confirmações de derivativos (Termo de Mercadoria).

Réplica em reportlab do documento HTML de confirmação (o mesmo texto legal do
template TERMO.doc legado). A4 paisagem — mesma orientação do .doc original —
com a Tabela de Referência (Anexo I) em página própria.

Import é lazy no chamador: se o reportlab não estiver instalado, o save
retorna erro claro em vez de derrubar o app.
"""
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


def termo_strike_usd_pdf(conf):
    return termo_pdf(conf, variant='usd')


def termo_platts_strike_usd_pdf(conf):
    return termo_pdf(conf, variant='platts')


def termo_strike_brl_pdf(conf):
    return termo_pdf(conf, variant='brl')


def termo_pdf(conf, variant='usd'):
    """Bytes do PDF da confirmação Termo de Mercadoria.

    variant: 'usd' (TERMO.doc), 'platts' (Código/Fonte de Divulgação no Anexo)
    ou 'brl' (sem PTAX pontual — USD PTAX = média entre as Datas Inicial/Final
    de Verificação USD PTAX; Anexo com 15 colunas e Forward em R$)."""
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
    st.append(Paragraph(
        'Os termos não definidos nesta Confirmação terão os mesmos significados a eles atribuídos '
        'no Contrato. Em caso de conflito entre uma definição do Contrato e a desta Confirmação, '
        'prevalecerá, para os fins desta Operação de Derivativo, a definição que constar desta '
        'Confirmação.', S['body']))

    # Seção 2
    st.append(Paragraph('2. &nbsp;&nbsp; <u>Definição das Partes</u>', S['section']))
    st.append(Paragraph('a. &nbsp;&nbsp; <b>Parte A:</b> &nbsp;&nbsp; <b>BANCO J.P. MORGAN S.A.</b> '
                        '— CNPJ/MF: 33.172.537/0001–98', S['item']))
    st.append(Paragraph('b. &nbsp;&nbsp; <b>Parte B:</b> &nbsp;&nbsp; <b>' + nome + '</b> '
                        '— CNPJ/MF: ' + cnpj, S['item']))
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
    for d in (defs42_brl if variant == 'brl' else defs42):
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
        data = [
            [Paragraph('<b>' + name + '</b>', S['sigb']), Paragraph('Por:', S['sig'])],
            [Paragraph('', S['sig']), Paragraph(line, S['sig'])],
            [Paragraph('', S['sig']), Paragraph('Nome:', S['sig'])],
            [Paragraph('Por:', S['sig']), Paragraph('Por:', S['sig'])],
            [Paragraph(line, S['sig']), Paragraph(line, S['sig'])],
            [Paragraph('Nome:', S['sig']), Paragraph('Nome:', S['sig'])],
        ]
        tbl = Table(data, colWidths=[doc.width / 2.0] * 2)
        tbl.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 3), (-1, 3), 24),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
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
            Paragraph(_e(r.get('qtd')), S['td']),
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

    doc.build(st)
    return buf.getvalue()
