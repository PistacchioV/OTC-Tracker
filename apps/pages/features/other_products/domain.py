# -*- coding: utf-8 -*-
"""Other Products — regras puras. Hoje: o FATOR DE JUROS da perna VCP de um
swap (§452), o que a página Swap VCP manda à B3 no arquivo de PU/Fator.

A B3 não tem PU para a curva VCP (o "AVISO DE INEXISTENCIA DE PU" do
Operations B3): o fator vem do JP. A conta, na ordem em que a mesa a faz:

    notional amortizado = VBR (ou o original) × % do fluxo    ← DFLUXO, base do tipo
    juros da perna      = |curva da perna (OTM)| − notional amortizado
    diff B3 (perna calculada) = Valor Juros da B3 (Swap Eventos) − juros JP
    fator VCP = round((juros VCP + diff B3 da OUTRA perna) / VBR + 1, 8)

A diff da perna que a B3 já calcula entra no fator da perna VCP de
propósito: o que liquida é a DIFERENÇA das duas curvas, e se a B3 calculou a
outra perna acima do JP em D, só somar D à perna VCP faz o líquido na B3
fechar com o interno. Só a perna VCP recebe fator; a calculada fica sem, e a
tela escreve "-".

Tudo aqui é número puro: quem lê arquivo é `queries`, quem grava é
`commands`. Valor que não se resolve é `None`, nunca zero — zero é um fator
de 1,00000000 que a B3 aceita e liquida errado.
"""
from apps.pages.precificador import liquidacao
from apps.pages.platform import swap_flows as _sf

CAMPOS_EDITAVEIS = ('vbr', 'pct', 'tipo', 'amortizado', 'juros_p', 'diff_p',
                    'juros_c', 'diff_c', 'fator_p', 'fator_c')


def num(v):
    """Texto BR ('1.234,56'), US ('1,234.56') ou cru → float, ou None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(' ', '').replace('%', '')
    if not s or s in ('-', '—'):
        return None
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.') if s.rfind(',') > s.rfind('.') else s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def is_vcp(indexador):
    return 'vcp' in _sf.norm(indexador)


def notional_amortizado(vbr, original, pct, base):
    """% do fluxo sobre a base que o `Tipo Amortização` diz (original ×
    remanescente × vencimento) — a mesma `liquidacao.amortizar` do Swap
    Calculator. `pct` em pontos (33.33 = 33,33%). None sem VBR ou sem %."""
    if vbr is None or pct is None:
        return None
    if pct <= 0:
        return 0.0
    return liquidacao.amortizar(original if original else vbr, vbr, pct / 100.0,
                                base or liquidacao.SOBRE_ORIGINAL)


def juros(curva, amortizado):
    """|curva da perna| menos o que amortizou: só o que é juros."""
    if curva is None:
        return None
    return abs(curva) - (amortizado or 0.0)


def diff_b3(valor_b3, valor_jp):
    """O que a B3 calculou a mais (+) ou a menos (−) que o JP."""
    if valor_b3 is None or valor_jp is None:
        return None
    return valor_b3 - valor_jp


def fator(juros_vcp, diff_outra, vbr):
    """(juros + diff da outra perna) / VBR + 1, na 8ª casa."""
    if juros_vcp is None or not vbr:
        return None
    return round((juros_vcp + (diff_outra or 0.0)) / vbr + 1.0, 8)


# Acima disto a linha pede conferência. É tolerância de ARREDONDAMENTO: o fator
# vai à B3 com 8 casas e multiplica um VBR de milhões, então centavos de
# diferença são esperados e não dizem nada. Dez reais é o corte que a mesa usa.
TOLERANCIA_LIQUIDACAO = 10.0


def juros_do_fator(fator_, vbr):
    """Quanto de JUROS o fator rende sobre o VBR: `(fator − 1) × VBR`.

    É o que a B3 vai calcular com o fator que mandamos — o fator carrega
    principal + juros, e aqui só interessa a parte de juros, que é o que
    liquida. `None` sem fator ou sem VBR: zero afirmaria "não rendeu nada", e
    quem lê a coluna não distinguiria isso de "não deu para calcular"."""
    if fator_ is None or not vbr:
        return None
    return (fator_ - 1.0) * vbr


def liquidacao_vcp(vcp_p, vcp_c, fator_p, fator_c, vbr, juros_p, juros_c, diff_p, diff_c):
    """O que a B3 liquidaria com os fatores desta linha, ou `None`.

    É a PROVA REAL do fator: aplicado de volta ao VBR, ele tem de reproduzir o
    caixa que o interno (OTM) diz que o swap liquida. O que a coluna mede, no
    fim, é o ARREDONDAMENTO — o fator vai à B3 com 8 casas e multiplica um VBR
    de milhões —, mais qualquer perna que não fechou (sem fluxo, sem curva,
    lado trocado). Por isso cada perna entra pela fonte que a B3 vai usar:

      - perna VCP → `(fator − 1) × VBR`, com o fator JÁ arredondado, que é o
        que sai no `VCP_*.TXT`. Usar o fator cheio tornaria a conta uma
        tautologia: daria zero sempre, inclusive no dia em que a 8ª casa
        custasse dinheiro de verdade;
      - perna CALCULADA → o juro que a **B3** calcula, que é o nosso mais a
        diff (`diff_b3 = valor da B3 − valor JP`, então `juros + diff` é o
        valor da B3). É o que faz a diff se CANCELAR — ela já entrou no fator
        da perna VCP —, e é justamente esse cancelamento que leva a conta de
        volta ao caixa interno. Com o nosso valor aqui a diff sobraria na
        subtração e toda linha com divergência B3 acusaria falso.

    A ORDEM é a do `Internal Settlement`, contra quem esta coluna é comparada:
    **Parte menos Contraparte**, seja qual for a perna que tem fator. Montar
    "VCP menos a outra" inverte o sinal em toda linha cuja perna VCP é a
    Contraparte — o módulo bate, a diferença sai como o DOBRO do caixa e a
    linha marca `Check` sempre.

    Sem perna VCP nenhuma não há o que conferir (a linha não vai para o
    arquivo de PU/Fator), e a resposta é `None`."""
    def da_b3(juros_, diff_):
        if juros_ is None:
            return None
        return juros_ + (diff_ or 0.0)

    if not (vcp_p or vcp_c):
        return None
    parte = juros_do_fator(fator_p, vbr) if vcp_p else da_b3(juros_p, diff_p)
    cpty = juros_do_fator(fator_c, vbr) if vcp_c else da_b3(juros_c, diff_c)
    if parte is None or cpty is None:
        return None
    return parte - cpty


def diferenca_liquidacao(interno, vcp):
    """(diferença, veredito) entre o caixa interno e o do fator.

    O veredito é `''` quando não dá para comparar — e isso NÃO é `Ok`. Uma
    linha sem um dos dois valores marcada como conferida é a pior saída
    possível aqui: ela some do que a mesa tem para olhar."""
    if interno is None or vcp is None:
        return None, ''
    d = interno - vcp
    return d, ('Ok' if abs(d) < TOLERANCIA_LIQUIDACAO else 'Check')


def calcular(base, overrides=None):
    """As colunas da tabela de fatores a partir dos INSUMOS (`base`) e do que a
    mesa editou (`overrides`, campo → valor; o editado vence, campo a campo).

    `base`: vbr, original, pct, tipo, base_amort, curva_p, curva_c,
    b3_juros_p, b3_juros_c, b3_fator_p, b3_fator_c, idx_p, idx_c.
    Devolve os campos calculados + `vcp_p`/`vcp_c` + `manual` (os campos que
    vieram da edição)."""
    ov = dict(overrides or {})

    def pega(campo, calculado):
        if campo in ov and ov[campo] not in (None, ''):
            return num(ov[campo]) if campo != 'tipo' else ov[campo]
        return calculado

    vcp_p, vcp_c = is_vcp(base.get('idx_p')), is_vcp(base.get('idx_c'))
    vbr = pega('vbr', num(base.get('vbr')))
    pct = pega('pct', num(base.get('pct')))
    tipo = pega('tipo', base.get('tipo') or '')
    base_amort = _sf.base_da_amortizacao(tipo) or base.get('base_amort') or ''
    # BULLET no VENCIMENTO: o principal volta INTEIRO, e é o único fluxo que
    # existe. `Na Data de Vencimento` responde "neste fluxo não amortiza"
    # (`amortiza_no_fluxo`) — regra certa, escrita para os fluxos
    # INTERMEDIÁRIOS de um cashflow. No bullet não há intermediário: com 0% o
    # `juros = |curva| − 0` carrega o principal junto com os juros e o fator sai
    # com um 1,0 inteiro a mais. Num VBR de 9,8 mi com curva de 13,5 mi ele
    # virava 2,369 em vez de 1,369, e o `VCP_*.TXT` mandaria a B3 liquidar o
    # dobro.
    #
    # Quem sabe que o contrato é bullet é a POSIÇÃO (`Tipo de Contrato`, o mesmo
    # código que o Swap Characteristics traduz), e quem sabe que hoje é o
    # vencimento é a `Data Vencimento` dela: as duas perguntas chegam aqui
    # respondidas, porque o domain é puro e não lê arquivo.
    bullet_venc = bool(base.get('bullet_vencimento'))
    if bullet_venc:
        pct = pega('pct', 100.0)
        # At Maturity calcula sobre o SALDO — o que ainda está de pé. Num
        # contrato que já amortizou antes, o original é maior e a conta pelo
        # original só não erra por causa do `min`.
        base_amort = base_amort or liquidacao.AT_MATURITY
    if _sf.amortiza_no_fluxo(tipo) is False and not bullet_venc:
        amort_calc = 0.0
    else:
        amort_calc = notional_amortizado(vbr, num(base.get('original')), pct, base_amort)
    amortizado = pega('amortizado', amort_calc)
    juros_p = pega('juros_p', juros(num(base.get('curva_p')), amortizado))
    juros_c = pega('juros_c', juros(num(base.get('curva_c')), amortizado))
    diff_p = pega('diff_p', None if vcp_p else diff_b3(num(base.get('b3_juros_p')), juros_p))
    diff_c = pega('diff_c', None if vcp_c else diff_b3(num(base.get('b3_juros_c')), juros_c))
    # Só a perna VCP tem fator — é o que vai para a B3. A calculada fica sem, e
    # a tela escreve "-": mostrar ali o Fator de Juros da B3 parecia um fator
    # nosso, editável e enviável (pedido da mesa, 11/09/2026).
    fator_p = pega('fator_p', fator(juros_p, diff_c, vbr) if vcp_p else None)
    fator_c = pega('fator_c', fator(juros_c, diff_p, vbr) if vcp_c else None)
    return {'vbr': vbr, 'pct': pct, 'tipo': tipo, 'base_amort': base_amort,
            'amortizado': amortizado, 'juros_p': juros_p, 'juros_c': juros_c,
            'diff_p': diff_p, 'diff_c': diff_c, 'fator_p': fator_p, 'fator_c': fator_c,
            'vcp_p': vcp_p, 'vcp_c': vcp_c,
            'manual': sorted(k for k in ov if ov[k] not in (None, '') and k in CAMPOS_EDITAVEIS)}


def linha_para_arquivo(contrato, conta_p, idx_p, conta_c, idx_c, fator_p, fator_c):
    """A linha no FORMATO do Accrual (o gerador do PU/Fator lê por posição:
    0 código, 3 conta Parte, 5 indexador Parte, 6 conta Contraparte, 8
    indexador Contraparte, 9/10 fatores)."""
    def f8(v):
        return '' if v is None else '{:.8f}'.format(float(v))
    return [contrato, '', '', conta_p, '', idx_p, conta_c, '', idx_c, f8(fator_p), f8(fator_c)]


def problemas_para_envio(row):
    """Por que esta linha NÃO pode ir para o arquivo — vazio quando pode."""
    out = []
    if not row.get('vcp_p') and not row.get('vcp_c'):
        out.append('no VCP leg')
    if row.get('vcp_p') and row.get('fator_p') is None:
        out.append('Parte factor missing')
    if row.get('vcp_c') and row.get('fator_c') is None:
        out.append('Contraparte factor missing')
    if not row.get('conta_p'):
        out.append('Parte account missing')
    return out
