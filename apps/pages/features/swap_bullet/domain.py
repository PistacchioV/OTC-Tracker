# -*- coding: utf-8 -*-
"""As regras PURAS da página New Deals › Swap › Bullet.

O Deal Ticket, as visões do deal, o prêmio (0897), as lacunas, a linha da
Intrag Swap e o deal das confirmações moram na horizontal
`platform/swap_deal_ticket.py` desde 21/09/2026 — o Swap Cashflow lê o MESMO
Deal Ticket, e feature não importa feature. Este módulo os RE-EXPORTA com os
nomes de sempre (quem lê `domain.X` continua lendo o mesmo objeto) e guarda o
que é só do Bullet: o Registro de Contrato com Pagamento Final (código 0301,
layout 00003, seção 4.2.3 do manual).

Sem Flask, sem arquivo, sem rede, sem `routes`.
"""
from apps.pages.platform.swap_deal_ticket import *  # noqa: F401,F403
from apps.pages.platform.swap_deal_ticket import (  # noqa: F401
    _blank, _curve, _digits, _is_ours, _ponta, _sign, _clean_pct, _clean_rate,
    _clean_limit, _label_of, _value_right, _nearest_block, _proper, _fmt_dd_mmm_aaaa,
    _tokens, _safe_date, _functionality_text, _OUR_SIDE_RE, _ATACAMA_RE, _DT_LABELS,
    _DT_BLOCK_HEADERS, _DT_STOP_LABELS, _MONTHS, _MONTHS_PT, _INTRAG_BANK_NAME,
    _INTRAG_ATACAMA_NAME, _CLOSE_RE,
)


# ── O registro 0301 (Pagamento Final v00003) ─────────────────────────────────

def swap_record_values(deal, view, accounts, codes, my_number):
    """Os 123 campos do registro tipo 1 do 0301, por seq, JÁ na largura do
    manual (zero à esquerda nos 9(n), espaço à direita nos X(n), branco no
    que não se aplica). `codes` = {'functionality','adhesion','signA',
    'signB','premium_schedule','reset','curveA','curveB'} já traduzidos
    pelos cadastros (o `commands` os resolve; aqui só se posiciona).

    Regras da perna: só a curva JUROS leva Sinal e Juros; só a VCP leva PU
    inicial (sempre 1.00000000), Tipo/Classe, Cupom Limpo e Data de Cotação;
    a Descrição só vai na VCP quando ela é a curva da PARTE (a ponta ativa
    da visão); o Cap/Floor vai na curva em que o DT o declara (o bloco
    Curva VCP). O Titular
    do prêmio (107) é PARTE/CONTRAPARTE de quem paga; o Valor (108) sai
    zerado porque a agenda vai no 0897."""
    parte, contra = view_sides(deal, view, accounts)
    vals = {}
    vals['1'] = 'SWAP '
    vals['2'] = '1'
    vals['3'] = '0301'
    vals['4'] = _digits(my_number).zfill(10)[-10:]
    vals['5'] = parte['account'].zfill(8)[-8:] if parte['account'] else _blank(8)
    vals['6'] = (parte['taxid'] or '').ljust(14)[:14]
    vals['7'] = _blank(10)
    vals['8'] = contra['account'].zfill(8)[-8:] if contra['account'] else _blank(8)
    vals['9'] = (contra['taxid'] or '').ljust(14)[:14]
    vals['10'] = _blank(10)
    vals['11'] = ymd(deal.get('StartDate')).ljust(8)
    vals['12'] = ymd(deal.get('MaturityDate')).ljust(8)
    vals['13'] = (codes.get('adhesion') or '').rjust(2, '0') if codes.get('adhesion') else _blank(2)
    vals['14'] = b3_num(deal.get('Notional'), 14, 2) or _blank(16)
    vals['15'] = (codes.get('functionality') or '').zfill(2) if codes.get('functionality') else _blank(2)
    prem = norm(deal.get('PremiumSchedule')) in ('SIM', 'YES', 'S', 'Y')
    vals['16'] = codes.get('premium_schedule') or ('00' if prem else '01')
    vals['17'] = codes.get('reset') or '01'
    vals['18'] = _blank(100)
    vals['19'] = _blank(8)
    vals['20'] = _blank(2)
    vals['21'] = _blank(5)
    vals['22'] = _blank(22)
    vals['23'] = _blank(5)
    vals['24'] = _blank(320)
    vals['25'] = _blank(42)
    # Curva para Atualização: 26-32 Parte, 33-39 Contraparte.
    for base, side in ((26, parte), (33, contra)):
        c = _curve(deal, side['curve'])
        code_key = 'curve' + side['curve']
        juros = c['category'] != 'VCP'
        vals[str(base)] = b3_num(c['pct'], 3, 2) or _blank(5)
        vals[str(base + 1)] = (codes.get(code_key) or '').ljust(3)[:3]
        vals[str(base + 2)] = _blank(8)
        vals[str(base + 3)] = (codes.get('sign' + side['curve']) or '00') if juros else _blank(2)
        vals[str(base + 4)] = (b3_num(c['rate'], 3, 4) or '0000000') if juros else _blank(7)
        vals[str(base + 5)] = b3_num(c['floor'], 8, 8) or _blank(16)
        vals[str(base + 6)] = b3_num(c['cap'], 8, 8) or _blank(16)
    # Terceira curva: não se usa.
    for seq, w in ((40, 2), (41, 15), (42, 5), (43, 2), (44, 2), (45, 7), (46, 2)):
        vals[str(seq)] = _blank(w)
    # Se curva(s) = VCP: 47-49 Parte, 50-52 Contraparte; Cupom Limpo 53-54 / 55-56.
    price = parse_number(deal.get('InitialPrice'))
    # PU inicial é SEMPRE 1.00000000 na perna VCP (regra da mesa); o Cupom
    # Limpo leva o Preço Inicial do DT (100% Spot → 100.0000000).
    text = str(deal.get('VcpText') or '').strip() or vcp_text(deal)
    for base, cl_base, side in ((47, 53, parte), (50, 55, contra)):
        c = _curve(deal, side['curve'])
        if c['category'] == 'VCP':
            vals[str(base)] = b3_num(1, 14, 8)
            vals[str(base + 1)] = _digits(deal.get('VcpCode')).zfill(5)[-5:] if _digits(deal.get('VcpCode')) else _blank(5)
            # A Descrição só vai na curva da PONTA ATIVA da visão — a Parte —
            # e só quando ela é VCP. Contraparte com VCP fica em branco: é
            # como os arquivos da mesa saem (Cliente e Atacama sem descrição,
            # Banco com ela, porque ali o JPM carrega a VCP).
            vals[str(base + 2)] = text[:320].ljust(320) if side is parte else _blank(320)
            vals[str(cl_base)] = b3_num(price, 8, 7) or _blank(15)
            vals[str(cl_base + 1)] = (str(deal.get('QuoteDateCode') or '').zfill(2)
                                      if str(deal.get('QuoteDateCode') or '').strip() else _blank(2))
        else:
            vals[str(base)] = _blank(22)
            vals[str(base + 1)] = _blank(5)
            vals[str(base + 2)] = _blank(320)
            vals[str(cl_base)] = _blank(15)
            vals[str(cl_base + 1)] = _blank(2)
    # 57-106: Libor, TJMI, Commodity, Funcionalidade (triggers) — não se aplicam.
    widths = {57: 2, 58: 2, 59: 2, 60: 2, 61: 5, 62: 2, 63: 10, 64: 8, 65: 8, 66: 8,
              67: 2, 68: 2, 69: 2, 70: 2, 71: 5, 72: 2, 73: 10, 74: 8, 75: 8, 76: 8,
              77: 7, 78: 2, 79: 2, 80: 5, 81: 10, 82: 8, 83: 8, 84: 8,
              85: 7, 86: 2, 87: 2, 88: 5, 89: 10, 90: 8, 91: 8, 92: 8,
              93: 10, 94: 15, 95: 2, 96: 2, 97: 10, 98: 15, 99: 2, 100: 2,
              101: 2, 102: 16, 103: 2, 104: 2, 105: 16, 106: 2}
    for seq, w in widths.items():
        vals[str(seq)] = _blank(w)
    # Titular / Prêmio (1) da funcionalidade.
    if prem:
        # Quem paga é a Parte (00) ou a Contraparte (01)? A nossa perna é a
        # Parte nas visões cliente/banco e a CONTRAPARTE na visão da Atacama.
        payer_ours = _is_ours(deal.get('PremiumPayer', ''))
        parte_paga = payer_ours if parte['le'] == 'JPM' else (not payer_ours)
        vals['107'] = '00' if parte_paga else '01'
        vals['108'] = '0' * 16
    else:
        vals['107'] = _blank(2)
        vals['108'] = _blank(16)
    vals['109'] = _blank(16)
    vals['110'] = _blank(2)
    vals['111'] = _blank(10)
    vals['112'] = _blank(16)
    vals['113'] = _blank(8)
    vals['114'] = _blank(11)
    vals['115'] = _blank(1)
    vals['116'] = str(deal.get('LOB') or '').strip()[:14].rjust(14)
    for seq, w in ((117, 2), (118, 2), (119, 2), (120, 2), (121, 10), (122, 2), (123, 10)):
        vals[str(seq)] = _blank(w)
    return vals


def swap_header_values(participant, today_ymd):
    return {'1': 'SWAP ', '2': '0', '3': '0301', '4': str(participant or '').ljust(20)[:20],
            '5': today_ymd, '6': '00003'}


SWAP_RECORD_LENGTH = 1927
