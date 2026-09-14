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

    O caixa do swap é a DIFERENÇA entre as duas pernas, e cada uma entra pela
    fonte que a B3 vai usar:

      - perna VCP → `(fator − 1) × VBR`, o fator que estamos mandando;
      - perna CALCULADA → o juro que a **B3** calcula, que é o nosso mais a
        diff (`diff_b3 = valor da B3 − valor JP`, então `juros + diff` é o
        valor da B3). Usar o nosso aqui compararia o interno com o interno e a
        coluna nunca acusaria nada. Sem a diff, vale o nosso — a alternativa
        seria não responder, e a linha ainda diz alguma coisa.

    Três desenhos, e é o do meio que a mesa citou explicitamente:

      VCP × calculada   →  juros do fator − juro da B3 na outra
      calculada × VCP   →  o mesmo, espelhado
      VCP × VCP         →  uma menos a outra, as duas pelo fator

    Sem perna VCP nenhuma não há o que conferir (a linha não vai para o
    arquivo de PU/Fator), e a resposta é `None`."""
    def da_b3(juros_, diff_):
        if juros_ is None:
            return None
        return juros_ + (diff_ or 0.0)

    if vcp_p and vcp_c:
        a, b = juros_do_fator(fator_p, vbr), juros_do_fator(fator_c, vbr)
    elif vcp_p:
        a, b = juros_do_fator(fator_p, vbr), da_b3(juros_c, diff_c)
    elif vcp_c:
        a, b = juros_do_fator(fator_c, vbr), da_b3(juros_p, diff_p)
    else:
        return None
    if a is None or b is None:
        return None
    return a - b


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
    if _sf.amortiza_no_fluxo(tipo) is False:
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
