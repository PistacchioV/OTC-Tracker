# -*- coding: utf-8 -*-
"""As regras PURAS da página New Deals › Swap › Cetes (mesa, 21/10/2026, §650).

O que chega: o e-mail "Cetes & associated trades - ##new trade, tranche N"
(Brazil CETE Notifications), com as operações da tranche em BLOCOS numerados
(`#8 offshore intercompany ndf`, `#9 cetip usd irs`…), cada um uma lista de
`rótulo: valor`. Só o **cetip usd irs** vai à B3: o swap USD Fixed × SOFR entre
o Banco (cetesbra) e o Lawton (cetesbra), registrado pelas DUAS pontas.

O arquivo é o Registro de Contrato com Pagamento Final na versão 1 do layout
(`swap-pagamento-final`, header de 38 e registro de 1899 caracteres) — o
exemplo da mesa campo a campo:

  * as duas curvas são VCP (C00, 100%); a PARTE leva a curva que RECEBE — na
    visão do Banco, o SOFR; na do Lawton, o Dólar com o juros fixo;
  * Sinal e Juros só na perna de taxa fixa; Descrição só na curva da Parte;
  * PU inicial 1,00000000 nas duas, Cupom Limpo = o fx rate for reference e
    Data de Cotação = o D-n do `fx fixing` (t-2 → 02);
  * **Valor base em REAIS**: o swap na B3 é sempre em BRL — o USD notional
    vezes o fx rate for reference;
  * o MESMO Meu Número nas duas visões, a LOB (CEM) no Código Identificador.

O que cada perna é na B3 (curva, Tipo/Classe da VCP, se leva a taxa fixa e o
texto da Descrição) é o cadastro `swap-cetes-leg` (/mapping), nunca um de-para
no código. Sem Flask, sem arquivo, sem rede, sem `routes`.
"""
import hashlib
import re

from apps.pages.platform import swap_deal_ticket as _dtk

norm = _dtk.norm
parse_date = _dtk.parse_date
parse_number = _dtk.parse_number
iso = _dtk.iso
ymd = _dtk.ymd
b3_num = _dtk.b3_num

# As colunas da página (o CATÁLOGO as copia — feature não importa feature —
# e o `check_swap_cetes.py` cobra a paridade): [campo, rótulo, tipo].
COLUMNS = (
    ('Tranche', 'Tranche', 'text'),
    ('Block', 'Block', 'text'),
    ('Booking', 'Booking', 'text'),
    ('Venue', 'Venue', 'text'),
    ('StartDate', 'Effective', 'date'),
    ('MaturityDate', 'Maturity', 'date'),
    ('NotionalUSD', 'USD Notional', 'money'),
    ('FxRate', 'FX Rate (reference)', 'number'),
    ('Notional', 'Notional (BRL)', 'money'),
    ('FixedRate', 'Fixed Rate %', 'number'),
    ('FixedPayer', 'Pays Fixed', 'text'),
    ('WePay', 'We Pay', 'text'),
    ('WeRec', 'We Receive', 'text'),
    ('Accruals', 'Accruals', 'text'),
    ('Payments', 'Payments', 'text'),
    ('FxFixing', 'FX Fixing', 'text'),
    ('FxSettlement', 'FX Settlement', 'text'),
    ('Direction', 'Direction', 'text'),
    ('Adhesion', 'Adhesion', 'text'),
    ('MyNumber', 'Meu Número', 'text'),
    ('Subject', 'E-mail Subject', 'text'),
    ('Maker', 'Maker', 'text'),
    ('Checker', 'Checker', 'text'),
)
FIELDS = tuple(c[0] for c in COLUMNS)
DATE_FIELDS = ('StartDate', 'MaturityDate')
STATUS_SENDABLE = ('New', 'Approved')

# As duas visões: o Banco lança como Parte com o Lawton de Contraparte, e o
# Lawton o espelho. A LE de cada ponta é a do cadastro `b3-accounts`.
VIEWS = ('bank', 'lawton')
VIEW_LE = {'bank': ('JPM', 'LAWTON'), 'lawton': ('LAWTON', 'JPM')}
FILE_NAMES = {'bank': 'SWAP_CETES_BANCO.txt', 'lawton': 'SWAP_CETES_LAWTON.txt'}


def le_pair(view):
    """O par de pernas da visão (o mesmo vocabulário das variantes do File
    Interpreter e do `_conecta_file_name`)."""
    return {'bank': 'JPM x LAWTON', 'lawton': 'LAWTON x JPM'}[view]


# ── O e-mail ─────────────────────────────────────────────────────────────────

_HEAD = re.compile(r'^#\s*(\d{1,3})\s*[:.)\-]?\s+(\S.*?)\s*$')
_HEAD_NUM = re.compile(r'^#\s*(\d{1,3})\s*[:.)\-]?$')     # o "#9" sozinho: o título é a linha seguinte
_KV = re.compile(r'^([A-Za-z][A-Za-z0-9 /&().%\-]*?)\s*:\s*(.*?)\s*$')
_TRANCHE = re.compile(r'tranche\s*#?\s*(\d+)', re.I)

# rótulo do e-mail (minúsculo, espaços simples) → campo do deal
LABELS = {
    'booking': 'Booking', 'venue': 'Venue', 'fx rate for reference': 'FxRate',
    'fx rate': 'FxRate', 'usd notional': 'NotionalUSD', 'notional': 'NotionalUSD',
    'effective': 'StartDate', 'effective date': 'StartDate', 'start': 'StartDate',
    'maturity': 'MaturityDate', 'maturity date': 'MaturityDate',
    'fix rate': 'FixedRate', 'fixed rate': 'FixedRate',
    'we pay': 'WePay', 'we rec': 'WeRec', 'we receive': 'WeRec',
    'accruals': 'Accruals', 'payments': 'Payments', 'fx fixing': 'FxFixing',
    'fx settlement': 'FxSettlement', 'direction': 'Direction',
}


def _label(s):
    return re.sub(r'\s+', ' ', str(s or '').strip().lower())


def blocks(lines):
    """As linhas do corpo → [{num, title, fields: {rótulo: valor}}], um por
    bloco `#N título`. O que vem antes do primeiro bloco (saudação, o
    resumo da tranche) fica de fora.

    O bloco chega de DUAS formas, e as duas valem: a linha inteira (`#9
    cetip usd irs`, `booking: F Talioli`) ou uma CÉLULA por linha — a tabela
    do Outlook põe um `<p class=MsoNormal>` dentro de cada `<td>`, e o
    `html_to_lines` quebra em cada parágrafo: `#9`, `cetip usd irs`,
    `booking:`, `F Talioli`. Aí o `#9` sozinho espera o título na linha
    seguinte, e o rótulo sem valor espera o valor. A linha que vem depois de
    um rótulo é o valor dele, a menos que seja outro rótulo sem valor (o
    anterior estava vazio) ou um rótulo CONHECIDO com valor (a forma
    inteira) — assim um valor com dois-pontos não vira rótulo."""
    out, cur, num, rotulo = [], None, None, None
    for ln in lines or []:
        txt = str(ln or '').strip()
        if not txt:
            continue
        if num is not None:
            cur = {'num': num, 'title': txt, 'fields': {}}
            out.append(cur)
            num = None
            continue
        m = _HEAD.match(txt)
        if m:
            cur = {'num': m.group(1), 'title': m.group(2).strip(), 'fields': {}}
            out.append(cur)
            rotulo = None
            continue
        m = _HEAD_NUM.match(txt)
        if m:
            num, rotulo = m.group(1), None
            continue
        if cur is None:
            continue
        kv = _KV.match(txt)
        par = bool(kv and kv.group(2))
        if rotulo is not None and not (kv and not par) and not (par and _label(kv.group(1)) in LABELS):
            cur['fields'].setdefault(rotulo, txt)
            rotulo = None
            continue
        if par:
            cur['fields'].setdefault(_label(kv.group(1)), kv.group(2).strip())
            rotulo = None
        elif kv:
            rotulo = _label(kv.group(1))
    return out


def is_cetip_irs(title):
    """O bloco é o swap que vai à B3? (`cetip usd irs`)."""
    n = norm(title)
    return 'CETIP' in n and 'IRS' in n


def tranche_of(subject):
    m = _TRANCHE.search(str(subject or ''))
    return m.group(1) if m else ''


def _num_txt(v, places=None):
    """O número do e-mail como texto de máquina ('78,860,000.00' →
    '78860000.00'); '' se não é número."""
    n = parse_number(v)
    if n is None:
        return ''
    return ('%.' + str(places) + 'f') % n if places is not None else ('%.8f' % n).rstrip('0').rstrip('.')


_PAYS = re.compile(r'\b(banco|bank|jpm|lawton)\b[^;,]*?\bpays?\s+(fix\w*|float\w*|sofr\w*)', re.I)


def fixed_payer(direction, we_pay=''):
    """Quem paga a taxa fixa — 'BANCO' ou 'LAWTON' — pela linha `direction`
    ("banco (cetesbra) pays fix vs lawton (cetesbra)"); sem ela, pelo `we pay`
    (o "we" do e-mail é o Banco). '' quando não dá para dizer."""
    m = _PAYS.search(str(direction or ''))
    if m:
        quem = 'LAWTON' if m.group(1).lower() == 'lawton' else 'BANCO'
        if m.group(2).lower().startswith('fix'):
            return quem
        return 'BANCO' if quem == 'LAWTON' else 'LAWTON'
    if 'FIX' in norm(we_pay):
        return 'BANCO'
    return ''


def quote_code(fx_fixing):
    """`t-2` → '02' (a Data de Cotação D-n da B3); '' sem o número."""
    m = re.search(r'[tTdD]\s*[-−]\s*(\d)', str(fx_fixing or ''))
    return m.group(1).zfill(2) if m else ''


def notional_brl(deal):
    """O Valor Base em REAIS: o USD notional × o fx rate for reference, em
    centavos (a B3 registra o swap em BRL). '' sem os dois."""
    usd, fx = parse_number(deal.get('NotionalUSD')), parse_number(deal.get('FxRate'))
    if usd is None or fx is None:
        return ''
    return '%.2f' % round(usd * fx + 1e-9, 2)


def make_deal_id(deal):
    """Chave interna ESTÁVEL do deal (o re-import do mesmo e-mail cai na
    mesma linha): tranche, bloco, datas e o notional em USD."""
    base = '|'.join(str(deal.get(k) or '') for k in ('Tranche', 'Block', 'StartDate', 'MaturityDate',
                                                       'NotionalUSD'))
    return 'CTS-' + hashlib.sha1(base.encode('utf-8')).hexdigest()[:10].upper()


def deal_from_block(block, trade_iso, subject=''):
    """Um bloco `cetip usd irs` → o deal da página (Status New). Datas em ISO,
    números como texto de máquina; o Valor Base em BRL já calculado."""
    f = dict((LABELS[k], v) for k, v in (block.get('fields') or {}).items() if k in LABELS)
    d = {
        'Status': 'New', 'LE': 'JPM', 'LOB': 'CEM', 'Deal': '', 'B3ID': '',
        'TradeDate': trade_iso, 'Client': 'Lawton',
        'Tranche': tranche_of(subject), 'Block': '#' + str(block.get('num') or ''),
        'Booking': f.get('Booking', ''), 'Venue': f.get('Venue', ''),
        'StartDate': iso(parse_date(f.get('StartDate'))) or '',
        'MaturityDate': iso(parse_date(f.get('MaturityDate'))) or '',
        'NotionalUSD': _num_txt(f.get('NotionalUSD'), 2),
        'FxRate': _num_txt(f.get('FxRate')),
        'FixedRate': _num_txt(f.get('FixedRate')),
        'WePay': f.get('WePay', ''), 'WeRec': f.get('WeRec', ''),
        'Accruals': f.get('Accruals', ''), 'Payments': f.get('Payments', ''),
        'FxFixing': f.get('FxFixing', ''), 'FxSettlement': f.get('FxSettlement', ''),
        'Direction': f.get('Direction', ''),
        'Adhesion': 'CGD', 'Functionality': 'SEM FUNCIONALIDADE', 'PremiumSchedule': 'Não', 'Reset': 'Não',
        'Subject': str(subject or '').strip(),
        'Maker': '', 'Checker': '',
    }
    d['FixedPayer'] = fixed_payer(d['Direction'], d['WePay'])
    d['QuoteDateCode'] = quote_code(d['FxFixing'])
    d['Notional'] = notional_brl(d)
    d['_id'] = make_deal_id(d)
    return d


def refresh(deal):
    """Recalcula o que DERIVA dos campos (depois de uma edição): o Valor Base
    em BRL, quem paga a fixa e o D-n — o que a mesa digitou nos derivados
    vale só até ela mexer num insumo."""
    deal['Notional'] = notional_brl(deal)
    if not str(deal.get('FixedPayer') or '').strip():
        deal['FixedPayer'] = fixed_payer(deal.get('Direction'), deal.get('WePay'))
    deal['QuoteDateCode'] = quote_code(deal.get('FxFixing')) or str(deal.get('QuoteDateCode') or '')
    return deal


# ── As pernas (cadastro `swap-cetes-leg`) ────────────────────────────────────

def _yes(v):
    return norm(v) in ('YES', 'SIM', 'Y', 'S', 'TRUE', '1')


def leg_row(rows, text):
    """A linha do cadastro para o texto da perna (`we pay`/`we rec`): `Exact`
    vence `Contains`; entre os `Contains`, o token mais longo. None sem linha."""
    alvo = norm(text)
    if not alvo:
        return None
    exatas = [r for r in rows or [] if norm(r.get('MATCH')) == 'EXACT' and norm(r.get('LEG')) == alvo]
    if exatas:
        return exatas[0]
    cands = [r for r in rows or [] if norm(r.get('MATCH')) != 'EXACT' and norm(r.get('LEG'))
             and norm(r.get('LEG')) in alvo]
    cands.sort(key=lambda r: -len(norm(r.get('LEG'))))
    return cands[0] if cands else None


def legs(deal, rows):
    """{'JPM': linha, 'LAWTON': linha} — a perna que cada ponta RECEBE — ou
    (None, [lacunas]). A perna fixa é a linha com RATE = Yes; quem a recebe é
    quem NÃO a paga."""
    faltas = []
    r_pay, r_rec = leg_row(rows, deal.get('WePay')), leg_row(rows, deal.get('WeRec'))
    if r_pay is None:
        faltas.append(lacuna('swt_leg_unmapped', 'leg "%s" has no row in /mapping › Swap Cetes Legs'
                             % (deal.get('WePay') or '—'), leg=deal.get('WePay') or '—'))
    if r_rec is None:
        faltas.append(lacuna('swt_leg_unmapped', 'leg "%s" has no row in /mapping › Swap Cetes Legs'
                             % (deal.get('WeRec') or '—'), leg=deal.get('WeRec') or '—'))
    if faltas:
        return None, faltas
    fixas = [r for r in (r_pay, r_rec) if _yes(r.get('RATE'))]
    if len(fixas) != 1:
        return None, [lacuna('swt_fixed_leg', 'exactly one leg must carry the fixed rate (RATE = Yes)')]
    fixa = fixas[0]
    flutuante = r_rec if fixa is r_pay else r_pay
    payer = str(deal.get('FixedPayer') or '').strip().upper()
    if payer not in ('BANCO', 'LAWTON'):
        return None, [lacuna('swt_no_direction', 'who pays the fixed rate (Direction)')]
    if payer == 'BANCO':
        return {'JPM': flutuante, 'LAWTON': fixa}, []
    return {'JPM': fixa, 'LAWTON': flutuante}, []


def fmt_br(n, min_places):
    """5.0089 → '5,0089'; 4.228 → '4,2280' (pelo menos `min_places` casas, sem
    perder as que o número tem)."""
    if n is None:
        return ''
    s = ('%.8f' % float(n)).rstrip('0')
    inteiro, _, dec = s.partition('.')
    dec = dec.ljust(min_places, '0')
    return inteiro + ',' + dec


def description(row, deal):
    """O texto da Descrição da curva: o DESCRIPTION do cadastro com `{fx}`,
    `{rate}` e `{dn}` preenchidos (`{fx}` = o fx rate for reference, `{rate}`
    = a taxa fixa, `{dn}` = o n do D-n)."""
    tpl = str((row or {}).get('DESCRIPTION') or '')
    dn = str(int(deal.get('QuoteDateCode'))) if str(deal.get('QuoteDateCode') or '').isdigit() else ''
    return (tpl.replace('{fx}', fmt_br(parse_number(deal.get('FxRate')), 4))
               .replace('{rate}', fmt_br(parse_number(deal.get('FixedRate')), 4))
               .replace('{dn}', dn))


# ── Lacunas (§486: código + params, o texto é só o fallback) ────────────────

def lacuna(code, text, **params):
    return {'code': code, 'params': params, 'text': text}


def lacuna_texts(itens):
    return [x.get('text', '') if isinstance(x, dict) else str(x) for x in itens or []]


def missing_for_send(deal, rows, accounts, codes):
    """O que impede os arquivos da B3 — [{code, params, text}]."""
    faltas = []

    def falta(field):
        faltas.append(lacuna('swt_missing', field, field=field))

    if not parse_date(deal.get('StartDate')):
        falta('Effective')
    if not parse_date(deal.get('MaturityDate')):
        falta('Maturity')
    if parse_number(deal.get('NotionalUSD')) is None:
        falta('USD Notional')
    if parse_number(deal.get('FxRate')) is None:
        falta('FX Rate (reference)')
    if parse_number(deal.get('FixedRate')) is None:
        falta('Fixed Rate')
    if not str(deal.get('QuoteDateCode') or '').strip():
        faltas.append(lacuna('swt_no_fx_fixing', 'FX Fixing (t-n)'))
    for le in ('JPM', 'LAWTON'):
        if not accounts.get(le):
            faltas.append(lacuna('swt_no_account', 'own B3 account of %s in /mapping › B3 Accounts' % le, le=le))
    for k, campo in (('adhesion', 'Adhesion'), ('functionality', 'Functionality'),
                     ('premium_schedule', 'Premium Schedule'), ('reset', 'Reset')):
        if not str((codes or {}).get(k) or '').strip():
            faltas.append(lacuna('swt_no_code', '%s has no B3 code in /mapping' % campo, field=campo))
    _l, erros = legs(deal, rows)
    faltas.extend(erros)
    return faltas


# ── O registro 0301 (Pagamento Final, versão 1 do layout) ────────────────────

# A largura de cada campo do registro (seq → caracteres), a do manual: o
# template `swap-pagamento-final` do File Interpreter. Soma 1899.
V1_WIDTHS = {
    1: 5, 2: 1, 3: 4, 4: 10, 5: 8, 6: 14, 7: 10, 8: 8, 9: 14, 10: 10, 11: 8, 12: 8, 13: 2, 14: 16,
    15: 2, 16: 2, 17: 2, 18: 100, 19: 8, 20: 2, 21: 5, 22: 22, 23: 5, 24: 320, 25: 42, 26: 5, 27: 3,
    28: 8, 29: 2, 30: 7, 31: 16, 32: 16, 33: 5, 34: 3, 35: 8, 36: 2, 37: 7, 38: 16, 39: 16, 40: 2,
    41: 15, 42: 5, 43: 2, 44: 2, 45: 7, 46: 2, 47: 22, 48: 5, 49: 320, 50: 22, 51: 5, 52: 320,
    53: 15, 54: 2, 55: 15, 56: 2, 57: 2, 58: 2, 59: 2, 60: 2, 61: 5, 62: 2, 63: 10, 64: 8, 65: 8,
    66: 8, 67: 2, 68: 2, 69: 2, 70: 2, 71: 5, 72: 2, 73: 10, 74: 8, 75: 8, 76: 8, 77: 7, 78: 2,
    79: 2, 80: 5, 81: 10, 82: 8, 83: 8, 84: 8, 85: 7, 86: 2, 87: 2, 88: 5, 89: 10, 90: 8, 91: 8,
    92: 8, 93: 10, 94: 15, 95: 2, 96: 2, 97: 10, 98: 15, 99: 2, 100: 2, 101: 2, 102: 16, 103: 2,
    104: 2, 105: 16, 106: 2, 107: 2, 108: 16, 109: 16, 110: 2, 111: 10, 112: 16, 113: 8, 114: 11,
    115: 1, 116: 14, 117: 2,
}
RECORD_LENGTH = 1899
HEADER_LENGTH = 38


def _fit(seq, s):
    w = V1_WIDTHS[seq]
    return str(s)[:w].ljust(w)


def record_values(deal, view, accounts, codes, leg_rows):
    """Os 117 campos do registro tipo 1, por seq, JÁ na largura do manual (o
    que não se aplica vai em branco). `leg_rows` = o `legs()` do deal; `codes`
    = os códigos dos cadastros (Adesão, Funcionalidade, Sim/Não, Sinal)."""
    parte_le, contra_le = VIEW_LE[view]
    vals = dict((str(k), ' ' * w) for k, w in V1_WIDTHS.items())
    vals['1'] = 'SWAP '
    vals['2'] = '1'
    vals['3'] = '0301'
    vals['4'] = _dtk._digits(deal.get('MyNumber')).zfill(10)[-10:]
    vals['5'] = _fit(5, accounts.get(parte_le, '').zfill(8))
    vals['8'] = _fit(8, accounts.get(contra_le, '').zfill(8))
    vals['11'] = _fit(11, ymd(deal.get('StartDate')))
    vals['12'] = _fit(12, ymd(deal.get('MaturityDate')))
    vals['13'] = _fit(13, str(codes.get('adhesion') or '').zfill(2))
    vals['14'] = b3_num(deal.get('Notional'), 14, 2) or vals['14']
    vals['15'] = _fit(15, str(codes.get('functionality') or '').zfill(2))
    vals['16'] = _fit(16, str(codes.get('premium_schedule') or '').zfill(2))
    vals['17'] = _fit(17, str(codes.get('reset') or '').zfill(2))
    vals['19'] = _fit(19, ymd(deal.get('TradeDate')))
    sinal = str(codes.get('sign_plus') or '00').zfill(2)
    # Curva para Atualização: 26-32 a curva da Parte, 33-39 a da Contraparte.
    # A taxa (Sinal + Juros) só vai na perna de taxa FIXA.
    for base, le in ((26, parte_le), (33, contra_le)):
        row = leg_rows[le]
        vals[str(base)] = b3_num(100, 3, 2)
        vals[str(base + 1)] = _fit(base + 1, str(row.get('CURVE') or '').strip())
        if _yes(row.get('RATE')):
            vals[str(base + 3)] = sinal
            vals[str(base + 4)] = b3_num(deal.get('FixedRate'), 3, 4) or vals[str(base + 4)]
    # Se curva(s) = VCP: 47-49 a Parte, 50-52 a Contraparte; Cupom Limpo e Data
    # de Cotação 53-54 / 55-56. O Tipo/Classe vai alinhado à direita com
    # espaço, como no arquivo da mesa ('   21'); a Descrição só na Parte.
    fx = parse_number(deal.get('FxRate'))
    dn = str(deal.get('QuoteDateCode') or '').zfill(2)
    for base, cl_base, le in ((47, 53, parte_le), (50, 55, contra_le)):
        row = leg_rows[le]
        vals[str(base)] = b3_num(1, 14, 8)
        vals[str(base + 1)] = _dtk._digits(row.get('VCP CODE')).rjust(5)[-5:]
        if le == parte_le:
            vals[str(base + 2)] = _fit(base + 2, description(row, deal))
        vals[str(cl_base)] = b3_num(fx, 8, 7) or vals[str(cl_base)]
        vals[str(cl_base + 1)] = dn
    vals['116'] = str(deal.get('LOB') or '').strip()[:14].rjust(14)
    return vals


def header_values(participant, today_ymd):
    """O header (tipo 0) da versão 1: sem o campo de versão do layout."""
    return {'1': 'SWAP ', '2': '0', '3': '0301', '4': str(participant or '').ljust(20)[:20], '5': today_ymd}


# ── O retorno da B3 e a Intrag ───────────────────────────────────────────────

def return_signature_account(accounts):
    """A conta que o plano B do casamento do retorno procura numa das pontas
    (`swap_deal_ticket._return_signature` lê o `ClientAccount`): a do Lawton."""
    return accounts.get('LAWTON', '')


INTRAG_PORTFOLIO = 'INTRAGJP552'      # a carteira do LAWTON na Intrag (`intrag/domain.INTRAG_CARTEIRAS`)
INTRAG_LAWTON_NAME = 'Lawton'
INTRAG_BANK_NAME = 'Banco JP Morgan'


def intrag_entry(deal, leg_rows, quote_date_iso):
    """A linha da Intrag Swap — a visão do LAWTON (Parte = Lawton com a perna
    que ele recebe; Contraparte = Banco), na carteira dele. Os 36 campos do
    `swap_deal_ticket.INTRAG_SWAP_FIELDS`."""
    plain = _dtk.plain_num

    def leg(le):
        row = leg_rows[le]
        fixa = _yes(row.get('RATE'))
        return {
            'pct': '100', 'ref_code': str(row.get('CURVE') or '').strip(), 'categoria': 'VCP',
            'codigo': _dtk._digits(row.get('VCP CODE')), 'sinal': 'Positivo',
            'juros': (plain(deal.get('FixedRate')) or '0') if fixa else '0',
            'lim_sup': '', 'lim_inf': '', 'quote_date': quote_date_iso or '',
            'desc_vcp': description(row, deal), 'preco_inicial': plain(deal.get('FxRate')),
        }

    entry = {
        'carteira': INTRAG_PORTFOLIO,
        'b3_id': str(deal.get('B3ID') or '').strip(),
        'start_date': iso(parse_date(deal.get('StartDate'))),
        'maturity_date': iso(parse_date(deal.get('MaturityDate'))),
        'base_value': plain(deal.get('Notional')),
        'funcionalidades': '',
        'parte': INTRAG_LAWTON_NAME, 'curva_parte': 'VCP',
        'contraparte': INTRAG_BANK_NAME, 'curva_contraparte': 'VCP',
        'agenda_premios': 'Não', 'premium_payment_date': '', 'premium_payer': '', 'premio': '',
    }
    for n, le in ((1, 'LAWTON'), (2, 'JPM')):
        for k, v in leg(le).items():
            entry['%s_%d' % (k, n)] = v
    entry.update({'_deal': str(deal.get('_id') or ''), '_client': INTRAG_LAWTON_NAME,
                  'status': 'New', 'maker': '', 'checker': ''})
    return entry
