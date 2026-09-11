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
fechar com o interno. Só a perna VCP recebe fator; a calculada mostra o da
B3, para conferência.

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
    fator_p = pega('fator_p', fator(juros_p, diff_c, vbr) if vcp_p else num(base.get('b3_fator_p')))
    fator_c = pega('fator_c', fator(juros_c, diff_p, vbr) if vcp_c else num(base.get('b3_fator_c')))
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
