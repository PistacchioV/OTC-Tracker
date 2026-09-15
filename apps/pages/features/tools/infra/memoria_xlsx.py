# -*- coding: utf-8 -*-
"""A memória de cálculo da liquidação, em .xlsx — com as CONTAS, não só os
números.

O que a tela mostra é o resultado; o que a mesa precisa mandar para o cliente,
para a auditoria e para a contraparte que contesta é o CAMINHO até ele. Por
isso cada célula derivada deste arquivo é uma FÓRMULA de Excel de verdade,
encadeada até as entradas: o fixing do DI de cada dia, a taxa contratada, as
datas e o notional. Quem recebe pode clicar no ajuste líquido, mandar rastrear
precedentes e descer até a taxa publicada pelo Banco Central naquele dia — e
pode trocar uma entrada e ver o número andar. Um arquivo com os valores
prontos responderia "quanto"; este responde "por quê", que é a pergunta que
chega de volta.

Três coisas são consequência disso, e não decoração:

  - **os dias do índice vão inteiros, numa aba por ponta** (o DI da série 4389
    do BCB, o SOFR do NY Fed), com o fator de CADA dia escrito como fórmula
    sobre a taxa daquele dia e o acumulado como o produto da linha anterior
    pela atual. É a evidência do índice: sem ela o fator acumulado seria um
    número caído do céu no meio da conta;
  - **a aba principal referencia a célula do acumulado**, nunca o valor
    copiado — mexer num dia refaz a liquidação inteira;
  - **o Excel recalcula tudo ao abrir.** O openpyxl grava a fórmula sem valor
    em cache, então um visualizador que não calcula mostra célula vazia. É o
    preço de entregar a conta em vez do retrato dela.

O documento é do BANCO, não da ferramenta: o timbre é o wordmark do J.P.
Morgan e não há uma linha sobre o sistema que o gerou — nem no conteúdo, nem
nas propriedades do arquivo. Ele sai em português porque é assim que circula
entre a mesa, o cliente e a B3, ao contrário da tela (§2 do CLAUDE.md: texto
de tela nasce em inglês e é traduzido por `data-lang`).

As fórmulas são o PORTE do motor (`precificador/liquidacao.py`), linha por
linha — o fator diário do DI com o arredondamento na 8ª casa quando a tela o
pede, a capitalização no regime escolhido, a tabela regressiva do IR num
`SE` aninhado, a retenção só quando o banco paga. Divergir do motor aqui é
pior do que não ter o arquivo: seria uma memória que não explica o número que
a mesa mandou. Quem prende as duas juntas é o `check_tools_memoria.py`, que
abre o workbook, recalcula as fórmulas e compara com o resultado do motor.
"""
import io
import os
import re
from datetime import date, datetime

from apps.pages.precificador import contagem, liquidacao

# O wordmark já recortado do e-mail (318x66): a arte de 400x400 tem ~80px de
# transparência em cima e embaixo, e colada assim empurraria o cabeçalho
# inteiro para baixo.
LOGO = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', '..', '..', '..', 'static', 'images', 'LogoJPMorgan-email.png'))
# O wordmark ocupa as DUAS linhas do cabeçalho, com folga em volta: ancorado
# rente ao canto de A1 ele encostava na borda da célula e ficava escondido
# atrás da moldura no Excel. A âncora leva deslocamento em pixels (EMU), que é
# a única forma de centrá-lo verticalmente no bloco — `add_image(img, 'A1')`
# cola o canto superior esquerdo no canto da célula, sem margem nenhuma.
LOGO_W, LOGO_H = 190, 39
LOGO_ESQ, LOGO_TOPO = 14, 17
ALTURA_L1, ALTURA_L2 = 30, 24

ABA = 'Memória de Cálculo'
ABA_DIARIA = {liquidacao.ATIVA: 'Apuração diária - Ativa',
              liquidacao.PASSIVA: 'Apuração diária - Passiva'}

MOEDA_FMT = '#,##0.00'
FATOR_FMT = '0.0000000000'
PCT_FMT = '0.0000%'
DATA_FMT = 'DD/MM/YYYY'
INT_FMT = '0'
FX_FMT = '0.00000000'

NAVY = '243B53'
CINZA = 'EDF1F5'
TINTA = '1D1D1F'
MUDO = '6C6C72'

INDICE_PT = {
    liquidacao.PRE: 'Pré — taxa fixa',
    liquidacao.CDI: 'CDI — % do CDI ± spread, realizado',
    liquidacao.MOEDA: 'Moeda — só a variação cambial',
    liquidacao.CAMBIO: 'Cambial — variação cambial + cupom',
    liquidacao.SOFR: 'SOFR composto + spread',
    liquidacao.TERM_SOFR: 'Term SOFR + spread',
    liquidacao.EURIBOR: 'EURIBOR + spread',
    liquidacao.IPCA: 'IPCA por número-índice + cupom real',
    liquidacao.EQUITY: 'Ação ou índice — variação de preço',
    liquidacao.FATOR: 'Fator acumulado informado',
}

REGIME_PT = {contagem.COMPOSTO: 'Composto — (1 + i) ^ τ',
             contagem.SIMPLES: 'Simples — 1 + i · τ'}

BASE_AMORT_PT = {
    liquidacao.SOBRE_ORIGINAL: 'sobre o notional original (parcela constante)',
    liquidacao.SOBRE_REMANESCENTE: 'sobre o saldo remanescente (parcela decrescente)',
    liquidacao.AT_MATURITY: 'no vencimento (principal integral no encerramento)',
    liquidacao.SEM_TROCA: 'não se aplica — contrato sem troca de amortização',
}


def _fontes():
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    return Alignment, Border, Font, PatternFill, Side


# ── a escrita, célula a célula ──────────────────────────────────────────────

class _Folha(object):
    """Escrita em quatro colunas: rótulo, valor, complemento e a origem.

    A coluna D não é enfeite: é onde está escrito, em português, de onde o
    número da coluna B saiu. A fórmula responde ao Excel; a nota responde a
    quem lê o arquivo impresso."""

    def __init__(self, ws):
        Alignment, Border, Font, PatternFill, Side = _fontes()
        self.ws = ws
        self.linha = 1
        self.F_TITULO = Font(name='Calibri', size=16, bold=True, color=NAVY)
        self.F_SUB = Font(name='Calibri', size=10, color=MUDO)
        self.F_SECAO = Font(name='Calibri', size=10, bold=True, color='FFFFFF')
        self.F_ROTULO = Font(name='Calibri', size=10, color=TINTA)
        self.F_VALOR = Font(name='Calibri', size=10, color=TINTA)
        self.F_FORTE = Font(name='Calibri', size=11, bold=True, color=TINTA)
        self.F_NOTA = Font(name='Calibri', size=9, italic=True, color=MUDO)
        self.FILL_SECAO = PatternFill('solid', fgColor=NAVY)
        self.FILL_DESTAQUE = PatternFill('solid', fgColor=CINZA)
        # Documento se lê da esquerda para a direita, e a coluna de valores
        # mistura texto com número: alinhada à direita, o nome da contraparte
        # descolava do rótulo e cada linha começava num ponto diferente. Tudo
        # à esquerda é o que dá a coluna única que a vista espera.
        self.ESQ = Alignment(horizontal='left', vertical='center')

    def secao(self, texto):
        self.linha += 1
        for col in range(1, 5):
            c = self.ws.cell(row=self.linha, column=col, value=texto if col == 1 else None)
            c.fill = self.FILL_SECAO
            c.font = self.F_SECAO
        self.ws.row_dimensions[self.linha].height = 18
        self.linha += 1
        return self.linha

    def campo(self, rotulo, valor=None, fmt=None, complemento=None, nota=None,
              destaque=False):
        """Uma linha de rótulo → valor. Devolve o endereço ABSOLUTO do valor,
        que é o que as outras fórmulas referenciam."""
        ws, ln = self.ws, self.linha
        a = ws.cell(row=ln, column=1, value=rotulo)
        a.font = self.F_FORTE if destaque else self.F_ROTULO
        b = ws.cell(row=ln, column=2, value=valor)
        b.font = self.F_FORTE if destaque else self.F_VALOR
        b.alignment = self.ESQ
        if fmt:
            b.number_format = fmt
        if complemento is not None:
            c = ws.cell(row=ln, column=3, value=complemento)
            c.font = self.F_NOTA
        if nota:
            d = ws.cell(row=ln, column=4, value=nota)
            d.font = self.F_NOTA
        if destaque:
            for col in range(1, 5):
                ws.cell(row=ln, column=col).fill = self.FILL_DESTAQUE
            ws.row_dimensions[ln].height = 20
        self.linha += 1
        return '$B${}'.format(ln)

    def nota(self, texto):
        c = self.ws.cell(row=self.linha, column=1, value=texto)
        c.font = self.F_NOTA
        self.linha += 1

    def pular(self, quantas=1):
        self.linha += quantas


def _data(d):
    """`date` → `datetime`: o openpyxl grava data de verdade, que ordena e
    entra em conta (`fim − início` são os dias corridos)."""
    return datetime(d.year, d.month, d.day) if isinstance(d, date) else None


def _cap(expr, regime, tau):
    """A capitalização do motor (`contagem.fator`) em Excel."""
    if regime == contagem.SIMPLES:
        return '(1+({e})*{t})'.format(e=expr, t=tau)
    return '(1+({e}))^{t}'.format(e=expr, t=tau)


# ── a aba dos dias do índice ────────────────────────────────────────────────

def _aba_diaria(wb, ponta, titulo, percentual, arredondar):
    """Um dia por linha, com o fator do dia escrito como CONTA sobre a taxa.

    O CDI e o SOFR acumulam de jeitos diferentes e a diferença aparece aqui:
    o DI capitaliza `(1 + DI)^(1/252)` por dia útil publicado — truncado na 8ª
    casa quando a tela pede o padrão B3/CETIP —, e o SOFR corre linearmente
    sobre os dias CORRIDOS até o próximo dia útil, que é o que faz o fixing de
    sexta remunerar três dias. A coluna `n` sai da subtração das próprias
    datas: contá-la de novo aqui seria uma segunda regra para divergir da
    primeira."""
    Alignment, Border, Font, PatternFill, Side = _fontes()
    de_sofr = ponta.indexador == liquidacao.SOFR
    ws = wb.create_sheet(titulo)
    ws.sheet_view.showGridLines = False
    negrito = Font(name='Calibri', size=10, bold=True, color='FFFFFF')
    fill = PatternFill('solid', fgColor=NAVY)
    ws.cell(row=1, column=1, value=(
        'SOFR — composição diária (Federal Reserve Bank of New York)' if de_sofr
        else 'CDI — apuração diária (Banco Central do Brasil, série 4389)')
    ).font = Font(name='Calibri', size=12, bold=True, color=NAVY)

    ref = {}
    if de_sofr:
        ws.cell(row=2, column=1, value='Fim da janela de observação').font = Font(
            name='Calibri', size=10)
        c = ws.cell(row=2, column=2, value=_data(ponta.obs_fim))
        c.number_format = DATA_FMT
        ref['obs_fim'] = '$B$2'
    else:
        ws.cell(row=2, column=1, value='Percentual do CDI aplicado à taxa diária').font = Font(
            name='Calibri', size=10)
        c = ws.cell(row=2, column=2, value=percentual)
        c.number_format = PCT_FMT
        ref['pct'] = '$B$2'

    cabecalho = ['Data']
    if de_sofr:
        cabecalho.append('Observação')
    cabecalho += ['Taxa (% a.a.)']
    if de_sofr:
        cabecalho.append('Dias corridos (n)')
    cabecalho += ['Fator do dia', 'Fator acumulado']
    topo = 4
    for j, texto in enumerate(cabecalho, start=1):
        c = ws.cell(row=topo, column=j, value=texto)
        c.font = negrito
        c.fill = fill
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

    col_taxa = 'C' if de_sofr else 'B'
    col_n = 'D' if de_sofr else None
    col_fd = 'E' if de_sofr else 'C'
    col_ac = 'F' if de_sofr else 'D'

    primeira = topo + 1
    total = len(ponta.fixings)
    for i, d in enumerate(ponta.fixings):
        ln = primeira + i
        j = 1
        c = ws.cell(row=ln, column=j, value=_data(d.data)); c.number_format = DATA_FMT
        if de_sofr:
            j += 1
            c = ws.cell(row=ln, column=j, value=_data(d.data_observacao or d.data))
            c.number_format = DATA_FMT
        j += 1
        c = ws.cell(row=ln, column=j, value=d.taxa); c.number_format = PCT_FMT
        if de_sofr:
            j += 1
            # o n do último dia fecha na janela de observação, não na linha
            # seguinte, que não existe
            seguinte = ('A{}'.format(ln + 1) if i + 1 < total else ref['obs_fim'])
            c = ws.cell(row=ln, column=j, value='={}-A{}'.format(seguinte, ln))
            c.number_format = INT_FMT
        j += 1
        if de_sofr:
            formula = '=1+{t}{l}*{n}{l}/360'.format(t=col_taxa, n=col_n, l=ln)
        elif arredondar:
            formula = '=1+(ROUND((1+{t}{l})^(1/252),8)-1)*{p}'.format(
                t=col_taxa, l=ln, p=ref['pct'])
        else:
            formula = '=1+((1+{t}{l})^(1/252)-1)*{p}'.format(t=col_taxa, l=ln, p=ref['pct'])
        c = ws.cell(row=ln, column=j, value=formula); c.number_format = FATOR_FMT
        j += 1
        acumulado = ('={f}{l}'.format(f=col_fd, l=ln) if i == 0
                     else '={a}{ant}*{f}{l}'.format(a=col_ac, ant=ln - 1, f=col_fd, l=ln))
        c = ws.cell(row=ln, column=j, value=acumulado); c.number_format = FATOR_FMT

    ultima = primeira + total - 1
    ln = ultima + 2
    c = ws.cell(row=ln, column=1, value='Fator acumulado do período')
    c.font = Font(name='Calibri', size=10, bold=True)
    alvo = {'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6}[col_ac]
    c = ws.cell(row=ln, column=alvo, value='={a}{u}'.format(a=col_ac, u=ultima))
    c.font = Font(name='Calibri', size=10, bold=True)
    c.number_format = FATOR_FMT

    larguras = {'A': 13, 'B': 15, 'C': 15, 'D': 16, 'E': 18, 'F': 18}
    for letra, w in larguras.items():
        ws.column_dimensions[letra].width = w
    ws.freeze_panes = 'A{}'.format(primeira)
    refs = {'fator': "'{}'!${}${}".format(titulo, col_ac, ultima)}
    if 'pct' in ref:
        # O percentual do CDI mora numa célula SÓ, a que a conta do dia usa. Na
        # memória ele entra por referência: repetido em dois lugares, alguém
        # corrige um e a planilha passa a mostrar um percentual que não é o que
        # multiplicou os fatores diários.
        refs['pct'] = "'{}'!{}".format(titulo, ref['pct'])
    return refs


# ── o bloco de uma ponta ────────────────────────────────────────────────────

def _bloco_ponta(f, p, entrada, vbr, diaria, titulo, so_juros):
    """As entradas da ponta, o fator que elas produzem e o que ele vale em
    reais — nesta ordem, que é a da conta.

    Os três fatores ficam SEPARADOS (índice, câmbio, correção) porque só o
    primeiro vira juros: a variação cambial e a correção do IPCA ficam no
    principal, que num fluxo intermediário não troca de mãos. Somá-los num
    fator único daria o mesmo valor futuro e juros errados — foi o que custou
    2,4 milhões num fluxo de 1 bilhão na perna IPCA."""
    idx = p.indexador
    f.secao(titulo)
    f.campo('Índice', INDICE_PT.get(idx, idx))
    if idx in liquidacao.DECLARAM_MOEDA:
        f.campo('Moeda do fluxo', p.moeda,
                nota='quanto: liquida em reais, sem conversão' if p.quanto else None)
    if p.ativo:
        f.campo('Ativo', p.ativo)
    if p.tenor and idx in liquidacao.COM_FIXING:
        f.campo('Prazo do fixing', p.tenor)

    taxa = None
    if idx not in liquidacao.SEM_TAXA:
        taxa = f.campo('Spread contratado (% a.a.)' if idx in (liquidacao.CDI, liquidacao.SOFR)
                       else 'Taxa contratada (% a.a.)', entrada.taxa, PCT_FMT)
    if idx == liquidacao.CDI:
        f.campo('Percentual do CDI', '=' + diaria['pct'], PCT_FMT,
                nota='aplicado à taxa diária')

    tau = None
    if p.convencao:
        f.campo('Contagem de dias', contagem.nome_curto(p.convencao))
        f.campo('Regime de capitalização', REGIME_PT.get(p.regime, p.regime))
        dias = f.campo('Dias da contagem', p.dias_contados, INT_FMT)
        base = contagem.base(p.convencao)
        if base:
            ref_base = f.campo('Base do ano', base, INT_FMT)
            tau = f.campo('τ — fração de ano', '={}/{}'.format(dias, ref_base), FX_FMT,
                          nota='dias da contagem ÷ base do ano')
        else:
            tau = f.campo('τ — fração de ano', p.fracao_de_ano, FX_FMT,
                          nota='ACT/ACT ISDA: cada trecho de ano sobre o tamanho real do ano')

    cap = _cap(taxa, p.regime, tau) if taxa and tau else None
    if idx == liquidacao.CDI:
        acumulado = f.campo('Fator acumulado do CDI', '=' + diaria['fator'], FATOR_FMT,
                            nota='produto dos fatores diários da aba de apuração')
        formula = '={}*{}'.format(acumulado, cap)
    elif idx == liquidacao.SOFR:
        # O SOFR composto é "fixing + spread", como o Term SOFR e a EURIBOR: a
        # taxa ANUALIZADA da janela soma ao spread e as duas capitalizam UMA
        # vez. Por isso a memória mostra a anualização — sem ela a planilha
        # traria um fator e um spread sem dizer como um vira o outro — e a
        # deriva do fator acumulado da aba diária, nunca de um número copiado:
        # mexer num dia do índice refaz a taxa e a liquidação inteira.
        acumulado = f.campo('Fator composto do SOFR', '=' + diaria['fator'], FATOR_FMT,
                            nota='produto dos fatores diários da aba de apuração')
        janela = ((p.obs_fim - p.obs_inicio).days if (p.obs_inicio and p.obs_fim)
                  else p.dias_corridos)
        ref_janela = f.campo('Dias corridos da janela', janela, INT_FMT)
        composta = f.campo('SOFR composto (% a.a.)',
                           '=({}-1)*360/{}'.format(acumulado, ref_janela), PCT_FMT,
                           nota='(fator − 1) × 360 ÷ dias corridos da janela')
        formula = '=' + _cap('{}+{}'.format(composta, taxa), p.regime, tau)
    elif idx in liquidacao.COM_FIXING:
        fix = f.campo('Taxa do fixing (% a.a.)', p.taxa_do_fixing, PCT_FMT,
                      complemento=('fixada em {:%d/%m/%Y}'.format(p.data_fixing)
                                   if p.data_fixing else None))
        formula = '=' + _cap('{}+{}'.format(fix, taxa), p.regime, tau)
    elif idx == liquidacao.EQUITY:
        p0 = f.campo('Preço inicial', p.preco_inicial, '#,##0.0000')
        p1 = f.campo('Preço final', p.preco_final, '#,##0.0000')
        formula = '=({}/{})*{}'.format(p1, p0, cap)
    elif idx == liquidacao.MOEDA:
        formula = '=1'
    elif idx == liquidacao.FATOR:
        formula = None
    else:                                   # pré, cambial e o cupom do IPCA
        formula = '=' + cap

    fator_idx = f.campo(
        'Fator do índice', formula if formula else p.fator_do_indice, FATOR_FMT,
        nota=('informado' if idx == liquidacao.FATOR else
              'sem taxa contratada; rende a variação cambial' if idx == liquidacao.MOEDA
              else None))

    if p.ptax_inicial and p.ptax_final:
        i0 = f.campo('Fixing inicial da moeda', p.ptax_inicial, FX_FMT,
                     complemento=('PTAX de {:%d/%m/%Y}'.format(p.data_ptax_inicial)
                                  if p.data_ptax_inicial else 'informado'))
        i1 = f.campo('Fixing final da moeda', p.ptax_final, FX_FMT,
                     complemento=('PTAX de {:%d/%m/%Y}'.format(p.data_ptax_final)
                                  if p.data_ptax_final else 'informado'))
        fx = f.campo('Fator cambial', '={}/{}'.format(i1, i0), FATOR_FMT,
                     nota='fixing final ÷ fixing inicial')
    else:
        fx = f.campo('Fator cambial', p.fator_cambial, FATOR_FMT,
                     nota='fluxo em reais, sem conversão' if p.fator_cambial == 1.0 else None)

    if p.ni_inicial and p.ni_final:
        n0 = f.campo('Número-índice inicial (IPCA)', p.ni_inicial, '#,##0.000000',
                     complemento=p.mes_ni_inicial or 'do contrato')
        n1 = f.campo('Número-índice final (IPCA)', p.ni_final, '#,##0.000000',
                     complemento=(p.mes_ni_final + ' · IBGE') if p.mes_ni_final else 'informado')
        corr = f.campo('Fator de correção monetária', '={}/{}'.format(n1, n0), FATOR_FMT,
                       nota='número-índice final ÷ inicial; aplicado ao principal')
    else:
        corr = f.campo('Fator de correção monetária', p.fator_correcao, FATOR_FMT,
                       nota='sem correção de principal nesta ponta' if p.fator_correcao == 1.0
                       else None)

    fator = f.campo('Fator acumulado da ponta', '={}*{}*{}'.format(fx, corr, fator_idx),
                    FATOR_FMT, nota='fator cambial × correção × fator do índice')
    # A ponta fecha em UMA linha: o que ELA liquida neste fluxo. Num fluxo
    # intermediário é o juro — a correção e a variação cambial ficam no
    # principal, que segue para o período seguinte; no vencimento é o valor
    # da ponta inteiro. Mostrar os dois lados transformaria a memória de UMA
    # liquidação num comparativo de bases, e metade dos números não teria
    # acontecido: valor futuro num fluxo que não liquida principal é uma
    # projeção, e memória de liquidação não projeta.
    if so_juros:
        liquidado = f.campo(
            'Juros do período (R$)', '={}*{}*{}*({}-1)'.format(vbr, fx, corr, fator_idx),
            MOEDA_FMT, nota='juros da taxa sobre o principal corrigido')
    else:
        liquidado = f.campo(
            'Valor da ponta na liquidação (R$)', '={}*{}'.format(vbr, fator), MOEDA_FMT,
            nota='notional remanescente × fator acumulado')
    if p.contagem_vale_para_spread:
        f.nota('Produto diário do CDI em base 252; a contagem escolhida capitaliza o spread.')
    return {'fator': fator, 'liquidado': liquidado}


# ── o documento ─────────────────────────────────────────────────────────────

def _timbre(ws, titulo, subtitulo):
    """O wordmark do banco no alto à esquerda, e o título ao lado dele.

    Logo que não carrega não derruba a memória: o documento sai sem timbre e o
    log diz por quê. O contrário — 500 na cara de quem clicou em Extract
    porque o Pillow não subiu — troca o arquivo inteiro por um arquivo
    nenhum."""
    Alignment, Border, Font, PatternFill, Side = _fontes()
    ws.row_dimensions[1].height = ALTURA_L1
    ws.row_dimensions[2].height = ALTURA_L2
    try:
        from openpyxl.drawing.image import Image as _Img
        from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, OneCellAnchor
        from openpyxl.drawing.xdr import XDRPositiveSize2D
        from openpyxl.utils.units import pixels_to_EMU
        img = _Img(LOGO)
        img.width, img.height = LOGO_W, LOGO_H
        img.anchor = OneCellAnchor(
            _from=AnchorMarker(col=0, row=0, colOff=pixels_to_EMU(LOGO_ESQ),
                               rowOff=pixels_to_EMU(LOGO_TOPO)),
            ext=XDRPositiveSize2D(pixels_to_EMU(LOGO_W), pixels_to_EMU(LOGO_H)))
        ws.add_image(img)
    except Exception as exc:                                # noqa: BLE001
        import logging
        logging.getLogger('otc_tracker').warning(
            '[memoria] o timbre nao entrou na planilha: %s', exc)
    ws.merge_cells('B1:D1')
    c = ws.cell(row=1, column=2, value=titulo)
    c.font = Font(name='Calibri', size=16, bold=True, color=NAVY)
    c.alignment = Alignment(horizontal='left', vertical='bottom')
    ws.merge_cells('B2:D2')
    c = ws.cell(row=2, column=2, value=subtitulo)
    c.font = Font(name='Calibri', size=10, color=MUDO)
    c.alignment = Alignment(horizontal='left', vertical='top')


# ── o valor calculado de cada fórmula ───────────────────────────────────────
#
# O openpyxl escreve a fórmula com o cache VAZIO (`<f>…</f><v></v>`), e quem
# abre o arquivo sem recalcular — o Modo de Exibição Protegido do Excel (todo
# arquivo baixado pelo navegador entra nele), o painel de visualização, o
# Excel Online, o preview do anexo no Outlook — mostra a célula EM BRANCO. Era
# a memória inteira chegando à mesa sem um número: os rótulos e as entradas
# apareciam, e τ, os fatores, os juros, o IR e o ajuste líquido, que são
# justamente o que o documento existe para mostrar, ficavam vazios. O
# `fullCalcOnLoad` do workbook não alcança esse caso: ele manda recalcular na
# ABERTURA, e nenhum desses leitores calcula.
#
# Então o arquivo leva as DUAS coisas: a fórmula (é o que faz a memória ser
# auditável e refazer a conta quando a mesa mexe numa entrada) e o resultado
# dela gravado como cache (é o que faz o número aparecer em qualquer leitor).
# O cache não pode ser uma segunda conta escrita à mão — isso seria a planilha
# afirmando um número que a fórmula não dá. Ele sai da PRÓPRIA fórmula, pelo
# avaliador abaixo: as quatro operações, a potência, IF/AND/MIN/ABS/ROUND, as
# comparações e as referências (com ou sem aba) são tudo o que este arquivo
# usa. Data vira SERIAL, como no Excel — é por isso que `fim - início` dá os
# dias corridos.
_REF = re.compile(r"(?:'([^']+)'!)?(\$?[A-Z]{1,2}\$?[0-9]{1,6})")
_EPOCA = datetime(1899, 12, 30)
_FUNCOES = {'IF': lambda c, a, b: a if c else b, 'AND': lambda *a: all(a),
            'OR': lambda *a: any(a), 'MIN': min, 'MAX': max, 'ABS': abs,
            'ROUND': round, 'TRUE': True, 'FALSE': False}


def _serial(v):
    """Data → número de série do Excel; o resto passa como está."""
    if isinstance(v, datetime):
        return (v - _EPOCA).days
    if isinstance(v, date):
        return (datetime(v.year, v.month, v.day) - _EPOCA).days
    return v


def _valor_da_celula(wb, memo, aba, endereco, pilha=()):
    chave = (aba, endereco.replace('$', ''))
    if chave in memo:
        return memo[chave]
    if chave in pilha:
        raise ValueError('referência circular em %r' % (chave,))
    v = wb[aba][chave[1]].value
    if isinstance(v, str) and v.startswith('='):
        v = _avaliar(wb, memo, aba, v[1:], pilha + (chave,))
    else:
        v = _serial(v)
    memo[chave] = v
    return v


def _avaliar(wb, memo, aba, expressao, pilha=()):
    def troca(m):
        return repr(_valor_da_celula(wb, memo, m.group(1) or aba, m.group(2), pilha))

    py = _REF.sub(troca, expressao).replace('^', '**')
    return eval(py, {'__builtins__': {}}, dict(_FUNCOES))       # noqa: S307


def _cache_das_formulas(wb):
    """`{(aba, 'B13'): valor}` para toda célula de fórmula do workbook.

    As abas são percorridas de trás para a frente porque a principal
    REFERENCIA o acumulado da aba diária: resolvidas as diárias primeiro, cada
    linha delas só precisa da anterior, que já está no memo — em vez de uma
    recursão tão funda quanto o número de dias do fluxo.

    Fórmula que não dá para avaliar é PULADA, nunca inventada: a célula fica
    como o openpyxl a escreveu (fórmula sem cache) e o Excel a recalcula na
    abertura, que é o comportamento de hoje."""
    memo, saida = {}, {}
    for ws in reversed(wb.worksheets):
        for linha in ws.iter_rows():
            for c in linha:
                if not (isinstance(c.value, str) and c.value.startswith('=')):
                    continue
                try:
                    v = _valor_da_celula(wb, memo, ws.title, c.coordinate)
                except Exception as exc:                # noqa: BLE001
                    import logging
                    logging.getLogger('otc_tracker').warning(
                        '[memoria] fórmula não avaliada em %s!%s (%s): %s',
                        ws.title, c.coordinate, c.value, exc)
                    continue
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    saida[(ws.title, c.coordinate)] = v
    return saida


def _abas_por_arquivo(origem):
    """Nome da aba → `xl/worksheets/sheetN.xml`, pelo par workbook + rels.

    A ordem dos arquivos no pacote não é contrato: quem diz qual arquivo é
    qual aba é o `r:id` do `workbook.xml` resolvido no `.rels`."""
    wbxml = origem.read('xl/workbook.xml').decode('utf-8')
    rels = origem.read('xl/_rels/workbook.xml.rels').decode('utf-8')
    alvo = {}
    # Os atributos do `<Relationship>` não vêm em ordem fixa (o openpyxl grava
    # Type, Target e só então Id), então cada um se lê por conta própria.
    for atributos in re.findall(r'<Relationship\b([^>]*)>', rels):
        rid = re.search(r'\bId="([^"]*)"', atributos)
        destino = re.search(r'\bTarget="([^"]*)"', atributos)
        if rid and destino:
            # Alvo ABSOLUTO no pacote (`/xl/worksheets/sheet1.xml`) já é o
            # caminho da entrada do zip; o relativo é a partir de `xl/`.
            caminho = destino.group(1)
            alvo[rid.group(1)] = (caminho[1:] if caminho.startswith('/')
                                  else 'xl/' + caminho)
    saida = {}
    for atributos in re.findall(r'<sheet\b([^>]*?)/?>', wbxml):
        nome = re.search(r'\bname="([^"]*)"', atributos)
        rid = re.search(r'\br:id="([^"]*)"', atributos)
        if nome and rid and rid.group(1) in alvo:
            saida[_desescapar(nome.group(1))] = alvo[rid.group(1)]
    return saida


def _desescapar(texto):
    for de, para in (('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'),
                     ('&quot;', '"'), ('&apos;', "'")):
        texto = texto.replace(de, para)
    return texto


# O `<v>` vazio que o openpyxl deixa em cada fórmula NÃO tem grafia única: a
# biblioteca troca de serializador conforme o que está instalado. Com `lxml` ela
# escreve pelo escritor incremental, que abre a tag antes de saber se vem
# conteúdo e fecha logo depois (`<v></v>`); sem `lxml` cai no ElementTree, que
# serializa elemento vazio como `<v />`. Casar só com uma das duas formas faz o
# arquivo sair EXATAMENTE como saía antes na máquina que tem o outro
# serializador — sem um valor, e sem erro nenhum para denunciar. `lxml` não está
# no requirements: a instância do time é justamente a que não o tem.
_CELULA_FORMULA = re.compile(
    r'(<c r="([A-Z]{1,3}[0-9]{1,7})"[^>]*>(?:<f[^>]*>.*?</f>|<f[^>]*/>))'
    r'(?:<v\s*/>|<v[^>]*>[^<]*</v>)?')


def _injetar_cache(xml, valores):
    """Grava em cada fórmula o valor apurado, seja qual for o serializador."""
    def troca(m):
        v = valores.get(m.group(2))
        if v is None:
            return m.group(0)
        return '{}<v>{}</v>'.format(m.group(1), repr(float(v)) if v % 1 else '%d' % v)

    return _CELULA_FORMULA.sub(troca, xml)


def _selar(conteudo, cache=None):
    """Tira do arquivo a assinatura da BIBLIOTECA que o escreveu e grava o
    cache das fórmulas.

    O `docProps/app.xml` do openpyxl se anuncia ("Microsoft Excel Compatible /
    Openpyxl 3.1.5") e esse é o único lugar do pacote que o `wb.properties` não
    alcança. O documento vai para o cliente e para a auditoria: o que ele diz
    de si mesmo é o banco e a data, não a pilha de software de quem o gerou.
    O zip é reescrito inteiro porque uma entrada de tamanho diferente
    invalidaria o diretório central se fosse remendada no lugar — e é na mesma
    reescrita que o `<v>` de cada fórmula recebe o valor calculado."""
    import zipfile
    origem = zipfile.ZipFile(io.BytesIO(conteudo))
    por_arquivo = {}
    if cache:
        abas = _abas_por_arquivo(origem)
        for (aba, endereco), valor in cache.items():
            nome = abas.get(aba)
            if nome:
                por_arquivo.setdefault(nome, {})[endereco] = valor
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as saida:
        for nome in origem.namelist():
            dados = origem.read(nome)
            if nome == 'docProps/app.xml':
                dados = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                         b'<Properties xmlns="http://schemas.openxmlformats.org/'
                         b'officeDocument/2006/extended-properties">'
                         b'<Application>Microsoft Excel</Application></Properties>')
            elif nome in por_arquivo:
                dados = _injetar_cache(dados.decode('utf-8'),
                                       por_arquivo[nome]).encode('utf-8')
            saida.writestr(nome, dados)
    return buf.getvalue()


def construir(r, pontas, cetip_id='', contraparte='', calendario='ANBIMA',
              reter_ir=True, arredondar_di=False, emitido_em=None):
    """O workbook da liquidação `r`, em bytes.

    `pontas` são as duas pontas de ENTRADA (`liquidacao.Ponta`), porque o
    resultado não guarda o que foi CONTRATADO — a taxa e o percentual do CDI
    só existem do lado do formulário, e sem eles a memória mostraria o fator
    sem mostrar de que taxa ele veio."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = ABA
    ws.sheet_view.showGridLines = False
    for letra, w in (('A', 42), ('B', 20), ('C', 24), ('D', 72)):
        ws.column_dimensions[letra].width = w

    _timbre(ws, 'Memória de Cálculo',
            'Liquidação de swap em {:%d/%m/%Y}'.format(r.fim))
    f = _Folha(ws)
    f.linha = 4

    # ── as abas dos dias do índice vêm ANTES: a aba principal referencia a
    #    célula do acumulado delas, e a referência precisa da aba existindo.
    diaria = {}
    for lado, p in ((liquidacao.ATIVA, r.ativa), (liquidacao.PASSIVA, r.passiva)):
        if p.fixings:
            diaria[lado] = _aba_diaria(wb, p, ABA_DIARIA[lado], pontas[lado].percentual,
                                       arredondar_di)

    f.secao('Identificação')
    f.campo('CETIP ID', cetip_id or '—')
    f.campo('Contraparte', contraparte or '—')
    dop = f.campo('Data da operação', _data(r.data_operacao), DATA_FMT,
                  nota='base do prazo para o IR')
    ini = f.campo('Início do fluxo', _data(r.inicio), DATA_FMT)
    fim = f.campo('Fim do fluxo — liquidação', _data(r.fim), DATA_FMT)
    f.campo('Vencimento do swap', _data(r.vencimento) if r.vencimento else '—',
            DATA_FMT if r.vencimento else None)
    f.campo('Calendário', calendario)
    f.campo('Dias corridos do fluxo', '={}-{}'.format(fim, ini), INT_FMT)
    f.campo('Dias úteis do fluxo', r.dias_uteis, INT_FMT,
            nota='calendário {}'.format(calendario))

    f.secao('O principal (R$)')
    original = f.campo('Notional original', r.nocional_original, MOEDA_FMT,
                       nota='valor registrado; base de cálculo da amortização')
    vbr = f.campo('Notional remanescente', r.nocional, MOEDA_FMT, destaque=True,
                  nota='base de cálculo das duas pontas')
    pct_am = f.campo('Amortização no fim do fluxo', r.percentual_amortizacao, PCT_FMT)
    f.campo('A amortização incide', BASE_AMORT_PT.get(r.base_amortizacao, r.base_amortizacao))
    # A base VENCE o percentual no `Sem Troca`: o contrato não amortiza em fluxo
    # nenhum, e uma fórmula de MIN ali prometeria uma conta que o motor não faz.
    if r.base_amortizacao == liquidacao.SEM_TROCA:
        amortizado = f.campo('Valor amortizado', 0.0, MOEDA_FMT,
                             nota='contrato sem troca de amortização')
    else:
        referencia = (vbr if r.base_amortizacao in (liquidacao.SOBRE_REMANESCENTE,
                                                    liquidacao.AT_MATURITY) else original)
        amortizado = f.campo(
            'Valor amortizado', '=IF({p}<=0,0,MIN({s},{ref}*{p}))'.format(p=pct_am, s=vbr,
                                                                         ref=referencia),
            MOEDA_FMT, nota='apurada no encerramento do fluxo; não integra o fator do período')
    f.campo('Saldo do fluxo seguinte', '={}-{}'.format(vbr, amortizado), MOEDA_FMT)

    a = _bloco_ponta(f, r.ativa, pontas[liquidacao.ATIVA], vbr,
                     diaria.get(liquidacao.ATIVA), 'Ponta ativa (recebedora)',
                     r.so_juros)
    p_ = _bloco_ponta(f, r.passiva, pontas[liquidacao.PASSIVA], vbr,
                      diaria.get(liquidacao.PASSIVA), 'Ponta passiva (pagadora)',
                      r.so_juros)

    f.secao('Apuração do ajuste (R$)')
    f.campo('Base da liquidação',
            'Fluxo intermediário: liquida o diferencial de juros' if r.so_juros
            else 'Liquidação final: liquida o valor das duas pontas',
            nota='principal nocional; sem liquidação de principal em fluxo intermediário'
            if r.so_juros else 'o principal liquida neste fluxo')
    rotulo = 'Juros da ponta {}' if r.so_juros else 'Ponta {} na liquidação'
    la = f.campo(rotulo.format('ativa'), '=' + a['liquidado'], MOEDA_FMT)
    lp = f.campo(rotulo.format('passiva'), '=' + p_['liquidado'], MOEDA_FMT)
    bruto = f.campo('Ajuste bruto', '={}-{}'.format(la, lp), MOEDA_FMT,
                    nota='ponta ativa menos ponta passiva')
    prazo = f.campo('Prazo desde a data da operação (dias)',
                    '={}-{}'.format(fim, dop), INT_FMT)
    retem = f.campo('Retém IR na fonte', bool(reter_ir),
                    nota='retenção pela fonte pagadora')
    aliquota = f.campo(
        'Alíquota de IR',
        '=IF(AND({r},{b}<0),IF({p}<=180,0.225,IF({p}<=360,0.2,IF({p}<=720,0.175,0.15))),0)'
        .format(r=retem, b=bruto, p=prazo), '0.0%',
        nota='tabela regressiva: até 180d 22,5% · 181–360d 20% · 361–720d 17,5% · acima 15%')
    ir = f.campo('IR retido', '=ABS({})*{}'.format(bruto, aliquota), MOEDA_FMT)
    f.campo('Ajuste líquido', '=IF({b}<0,{b}+{i},{b}-{i})'.format(b=bruto, i=ir),
            MOEDA_FMT, destaque=True)
    f.campo('Parte devedora',
            'Banco J.P. Morgan' if r.banco_paga else (contraparte or 'Contraparte'),
            nota='parte com resultado negativo no fluxo')

    f.pular()
    f.nota('Principal nocional: não há liquidação de principal. Liquida-se o diferencial '
           'entre as pontas, devido pela parte com resultado negativo.')
    if diaria:
        f.nota('Fator do índice apurado dia a dia na aba de apuração diária; '
               + ('fator diário do DI arredondado na 8ª casa, padrão B3/CETIP.'
                  if arredondar_di else
                  'fator diário do DI em precisão cheia, sem arredondamento.'))
    f.nota('As células em fórmula trazem o valor apurado e recalculam quando '
           'uma entrada muda.')
    f.nota('Emitido em {:%d/%m/%Y}.'.format(emitido_em or date.today()))

    ws.freeze_panes = 'A4'
    wb.properties.creator = 'J.P. Morgan'
    wb.properties.lastModifiedBy = 'J.P. Morgan'
    wb.properties.title = 'Memória de Cálculo'
    wb.properties.description = None
    cache = _cache_das_formulas(wb)
    buf = io.BytesIO()
    wb.save(buf)
    return _selar(buf.getvalue(), cache)
