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
from datetime import date, datetime

from apps.pages.precificador import contagem, liquidacao

# O wordmark já recortado do e-mail (318x66): a arte de 400x400 tem ~80px de
# transparência em cima e embaixo, e colada assim empurraria o cabeçalho
# inteiro para baixo.
LOGO = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', '..', '..', '..', 'static', 'images', 'LogoJPMorgan-email.png'))
LOGO_W, LOGO_H = 168, 35

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
    liquidacao.SOBRE_ORIGINAL: 'sobre o notional original — parcela constante',
    liquidacao.SOBRE_REMANESCENTE: 'sobre o saldo remanescente — parcela decrescente',
    liquidacao.AT_MATURITY: 'no vencimento — o principal inteiro no fim',
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
        self.DIR = Alignment(horizontal='right')
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
        b.alignment = self.DIR
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

def _bloco_ponta(f, p, entrada, vbr, diaria, titulo):
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
                nota='quanto — liquida em reais, sem conversão' if p.quanto else None)
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
                nota='incide na taxa DIÁRIA: 110% do CDI a 14% dá 15,5031%, não 15,40%')

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
                          nota='ACT/ACT ISDA: cada trecho de ano dividido pelo tamanho real dele')

    cap = _cap(taxa, p.regime, tau) if taxa and tau else None
    if idx == liquidacao.CDI:
        acumulado = f.campo('Fator acumulado do CDI', '=' + diaria['fator'], FATOR_FMT,
                            nota='produto dos fatores diários da aba de apuração')
        formula = '={}*{}'.format(acumulado, cap)
    elif idx == liquidacao.SOFR:
        acumulado = f.campo('Fator composto do SOFR', '=' + diaria['fator'], FATOR_FMT,
                            nota='produto dos fatores diários da aba de apuração')
        formula = '={}*{}'.format(acumulado, cap)
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
        nota=('informado na tela' if idx == liquidacao.FATOR else
              'sem taxa: a perna rende só a variação cambial' if idx == liquidacao.MOEDA
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
                       nota='número-índice final ÷ inicial — fica no PRINCIPAL, não nos juros')
    else:
        corr = f.campo('Fator de correção monetária', p.fator_correcao, FATOR_FMT,
                       nota='sem correção de principal nesta ponta' if p.fator_correcao == 1.0
                       else None)

    fator = f.campo('Fator acumulado da ponta', '={}*{}*{}'.format(fx, corr, fator_idx),
                    FATOR_FMT, nota='fator cambial × correção × fator do índice')
    valor = f.campo('Valor futuro (R$)', '={}*{}'.format(vbr, fator), MOEDA_FMT,
                    nota='notional remanescente × fator acumulado')
    juros = f.campo('Juros do período (R$)',
                    '={}*{}*{}*({}-1)'.format(vbr, fx, corr, fator_idx), MOEDA_FMT,
                    nota='só o que a TAXA rendeu, sobre o principal já corrigido')
    if p.contagem_vale_para_spread:
        f.nota('O produto diário do CDI é sempre 252; a contagem escolhida capitaliza o spread.')
    return {'fator': fator, 'valor': valor, 'juros': juros}


# ── o documento ─────────────────────────────────────────────────────────────

def _timbre(ws, titulo, subtitulo):
    """O wordmark do banco no alto à esquerda, e o título ao lado dele.

    Logo que não carrega não derruba a memória: o documento sai sem timbre e o
    log diz por quê. O contrário — 500 na cara de quem clicou em Extract
    porque o Pillow não subiu — troca o arquivo inteiro por um arquivo
    nenhum."""
    Alignment, Border, Font, PatternFill, Side = _fontes()
    ws.row_dimensions[1].height = 42
    try:
        from openpyxl.drawing.image import Image as _Img
        img = _Img(LOGO)
        img.width, img.height = LOGO_W, LOGO_H
        ws.add_image(img, 'A1')
    except Exception as exc:                                # noqa: BLE001
        import logging
        logging.getLogger('otc_tracker').warning(
            '[memoria] o timbre nao entrou na planilha: %s', exc)
    ws.merge_cells('B1:D1')
    c = ws.cell(row=1, column=2, value=titulo)
    c.font = Font(name='Calibri', size=16, bold=True, color=NAVY)
    c.alignment = Alignment(horizontal='left', vertical='center')
    ws.merge_cells('B2:D2')
    c = ws.cell(row=2, column=2, value=subtitulo)
    c.font = Font(name='Calibri', size=10, color=MUDO)


def _selar(conteudo):
    """Tira do arquivo a assinatura da BIBLIOTECA que o escreveu.

    O `docProps/app.xml` do openpyxl se anuncia ("Microsoft Excel Compatible /
    Openpyxl 3.1.5") e esse é o único lugar do pacote que o `wb.properties` não
    alcança. O documento vai para o cliente e para a auditoria: o que ele diz
    de si mesmo é o banco e a data, não a pilha de software de quem o gerou.
    O zip é reescrito inteiro porque uma entrada de tamanho diferente
    invalidaria o diretório central se fosse remendada no lugar."""
    import zipfile
    origem = zipfile.ZipFile(io.BytesIO(conteudo))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as saida:
        for nome in origem.namelist():
            dados = origem.read(nome)
            if nome == 'docProps/app.xml':
                dados = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                         b'<Properties xmlns="http://schemas.openxmlformats.org/'
                         b'officeDocument/2006/extended-properties">'
                         b'<Application>Microsoft Excel</Application></Properties>')
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
                  nota='conta o prazo do IR')
    ini = f.campo('Início do fluxo', _data(r.inicio), DATA_FMT)
    fim = f.campo('Fim do fluxo — liquidação', _data(r.fim), DATA_FMT)
    f.campo('Vencimento do swap', _data(r.vencimento) if r.vencimento else '—',
            DATA_FMT if r.vencimento else None)
    f.campo('Calendário', calendario)
    f.campo('Dias corridos do fluxo', '={}-{}'.format(fim, ini), INT_FMT)
    f.campo('Dias úteis do fluxo', r.dias_uteis, INT_FMT,
            nota='pelo calendário {}'.format(calendario))

    f.secao('O principal (R$)')
    original = f.campo('Notional original', r.nocional_original, MOEDA_FMT,
                       nota='o valor registrado, só para calcular a amortização sobre ele')
    vbr = f.campo('Notional remanescente', r.nocional, MOEDA_FMT, destaque=True,
                  nota='a base que rende — multiplica o fator das DUAS pontas')
    pct_am = f.campo('Amortização no fim do fluxo', r.percentual_amortizacao, PCT_FMT)
    f.campo('A amortização incide', BASE_AMORT_PT.get(r.base_amortizacao, r.base_amortizacao))
    referencia = (vbr if r.base_amortizacao in (liquidacao.SOBRE_REMANESCENTE,
                                                liquidacao.AT_MATURITY) else original)
    amortizado = f.campo(
        'Valor amortizado', '=IF({p}<=0,0,MIN({s},{ref}*{p}))'.format(p=pct_am, s=vbr,
                                                                     ref=referencia),
        MOEDA_FMT, nota='acontece no FIM do fluxo: não entra no fator deste período')
    f.campo('Saldo do fluxo seguinte', '={}-{}'.format(vbr, amortizado), MOEDA_FMT)

    a = _bloco_ponta(f, r.ativa, pontas[liquidacao.ATIVA], vbr,
                     diaria.get(liquidacao.ATIVA), 'Ponta ativa — quem recebe o índice')
    p_ = _bloco_ponta(f, r.passiva, pontas[liquidacao.PASSIVA], vbr,
                      diaria.get(liquidacao.PASSIVA), 'Ponta passiva — quem paga o índice')

    f.secao('Apuração do ajuste (R$)')
    ja = f.campo('Juros da ponta ativa', '=' + a['juros'], MOEDA_FMT)
    jp = f.campo('Juros da ponta passiva', '=' + p_['juros'], MOEDA_FMT)
    dif_juros = f.campo('Diferencial de juros', '={}-{}'.format(ja, jp), MOEDA_FMT)
    va = f.campo('Valor futuro da ponta ativa', '=' + a['valor'], MOEDA_FMT)
    vp = f.campo('Valor futuro da ponta passiva', '=' + p_['valor'], MOEDA_FMT)
    dif_vf = f.campo('Diferencial de valor futuro', '={}-{}'.format(va, vp), MOEDA_FMT)
    f.campo('Base da liquidação',
            'Fluxo intermediário — liquida só o diferencial de juros' if r.so_juros
            else 'Liquidação final — liquida o valor futuro das duas pontas',
            nota='o principal é nocional: num fluxo intermediário ele não troca de mãos')
    bruto = f.campo('Ajuste bruto', '={}'.format(dif_juros if r.so_juros else dif_vf),
                    MOEDA_FMT)
    prazo = f.campo('Prazo desde a data da operação (dias)',
                    '={}-{}'.format(fim, dop), INT_FMT)
    retem = f.campo('Retém IR na fonte', bool(reter_ir),
                    nota='a retenção é da fonte PAGADORA: só quando o banco paga')
    aliquota = f.campo(
        'Alíquota de IR',
        '=IF(AND({r},{b}<0),IF({p}<=180,0.225,IF({p}<=360,0.2,IF({p}<=720,0.175,0.15))),0)'
        .format(r=retem, b=bruto, p=prazo), '0.0%',
        nota='tabela regressiva: até 180d 22,5% · 181–360d 20% · 361–720d 17,5% · acima 15%')
    ir = f.campo('IR retido', '=ABS({})*{}'.format(bruto, aliquota), MOEDA_FMT)
    f.campo('Ajuste líquido', '=IF({b}<0,{b}+{i},{b}-{i})'.format(b=bruto, i=ir),
            MOEDA_FMT, destaque=True)
    f.campo('Quem paga',
            'A ponta passiva paga a ponta ativa.' if r.quem_recebe == liquidacao.ATIVA
            else 'A ponta ativa paga a ponta passiva.')

    f.pular()
    f.nota('O principal do swap é nocional: não troca de mãos. Só a diferença entre as duas '
           'pontas liquida, e paga quem tem o resultado negativo.')
    if diaria:
        f.nota('O fator do índice vem da aba de apuração diária, dia a dia; '
               + ('o fator diário do DI é arredondado na 8ª casa (padrão B3/CETIP).'
                  if arredondar_di else
                  'o fator diário do DI corre com precisão cheia, sem arredondamento.'))
    f.nota('As células em fórmula recalculam ao abrir: trocar uma entrada refaz a liquidação.')
    f.nota('Emitido em {:%d/%m/%Y}.'.format(emitido_em or date.today()))

    ws.freeze_panes = 'A4'
    wb.properties.creator = 'J.P. Morgan'
    wb.properties.lastModifiedBy = 'J.P. Morgan'
    wb.properties.title = 'Memória de Cálculo'
    wb.properties.description = None
    buf = io.BytesIO()
    wb.save(buf)
    return _selar(buf.getvalue())
