# -*- coding: utf-8 -*-
"""As regras da E-Financeira, PURAS: não importam o `routes`, não tocam banco
nem arquivo. Quem traz os dados é o `queries`; quem grava é o `commands`.

A E-Financeira é MENSAL e por CONTA: cada operação (o B3 ID é a `conta_num`)
vira UMA linha do arquivo do mês, com o que ela movimentou nele. Quatro páginas,
uma por sistema de origem, cada uma com o seu arquivo (`PAGES`).

O que entra vem dos EVENTOS de liquidação do mês — as mesmas linhas do NDF
Summary e do Trade Level do Other Products, dia a dia — mais as opções que
VENCERAM no mês sem caixa (só a posição as vê). A operação soma os eventos
(`aggregate`) e as colunas do arquivo saem de quatro regras (equipe, 30/10/2026):

  · Total Crédito (`balanco_totcred`) = prêmios RECEBIDOS no mês;
  · Total Débito (`balanco_totdeb`) = prêmios PAGOS no mês;
  · Pagamento Acumulado (`pag_totpgacum`) = o que o banco PAGOU ao cliente no
    mês, prêmio incluído — e o `pag_tp` é FATCA504 com valor, 999 sem;
  · Saldo (`balanco_vlrultdia`) = o prêmio recebido na VIDA da operação, só
    quando ela ENCERROU no mês (`conta_dtencerr`: vencimento, exercício,
    expiração ou recompra TOTAL; o fluxo de swap no meio da vida e a recompra
    parcial não encerram).

O valor que a liquidação recebeu do cliente não entra em coluna nenhuma do
arquivo — fica no Valor Interno, que a tela compara com o lado B3.
"""
import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal


# ── As quatro páginas: o sistema de origem e o arquivo de cada uma ─────────
# A ordem é a do menu (Regulatory › E-financeira).
# `notif` é o rótulo `page` do sino — um por página, nos TRÊS mapas (§8).
PAGES = {
    'kapital':    {'label': 'KAPITAL', 'file': 'KAPITAL_SWAP_EFINAN_{ym}.csv',
                   'notif': 'E-Financeira KAPITAL'},
    'athena-ndf': {'label': 'ATHENA-NDF', 'file': 'ATHENA_NDF_EFINAN_{ym}.csv',
                   'notif': 'E-Financeira ATHENA-NDF'},
    'athena-fxo': {'label': 'ATHENA-FXO', 'file': 'ATHENA_FXO_EFINAN_{ym}.csv',
                   'notif': 'E-Financeira ATHENA-FXO'},
    'pyramid':    {'label': 'PYRAMID', 'file': 'PYRAMID_{ym}.csv',
                   'notif': 'E-Financeira PYRAMID'},
}
PAGE_ORDER = ('kapital', 'athena-ndf', 'athena-fxo', 'pyramid')

PRODUCTS = ('NDF', 'OPTION', 'SWAP')
LOB_COMMODITIES = 'COMMODITIES'
LOBS = ('CEM', 'CEMHYB', 'EDG', LOB_COMMODITIES)

# As fontes da coleta de um dia: o NDF Summary, o Trade Level do Other Products
# e as opções que VENCEM no dia na posição (sem caixa, nenhuma tela de
# liquidação as mostra).
SOURCES = ('ndf', 'ops', 'exp')

# A tolerância do Valor Interno × Valor B3 é a da TELA de onde a linha veio:
# 5,00 no NDF Summary (`_NDFSUM_TOL`), 20,00 no Trade Level do Other Products
# (`_OPS_RECON_TOL`) — o teste confere a paridade com o routes.
TOL_BY_SOURCE = {'ndf': 5.0, 'ops': 20.0}

# Os eventos. O `Settlement Type` das telas (Premium · Maturity · Exercise ·
# Cashflow · Unwind) diz qual é; EXPIRY é a opção que venceu sem caixa e
# SETTLEMENT a liquidação de tipo que ninguém disse.
PREMIUM, MATURITY, EXERCISE, CASHFLOW, UNWIND, EXPIRY, SETTLEMENT = (
    'PREMIUM', 'MATURITY', 'EXERCISE', 'CASHFLOW', 'UNWIND', 'EXPIRY', 'SETTLEMENT')
_FECHA = (MATURITY, EXERCISE, EXPIRY)
_SUBTIPO = {MATURITY: 'Maturity', EXERCISE: 'Exercise', CASHFLOW: 'Cashflow',
            UNWIND: 'Unwind', EXPIRY: 'Expiry', SETTLEMENT: ''}

# O status da linha: a correção da tela (4-olhos) e o arquivo gerado.
ST_NEW, ST_PENDING, ST_APPROVED, ST_GENERATED = 'New', 'Pending', 'Approved', 'Generated'
STATUSES = (ST_PENDING, ST_NEW, ST_APPROVED, ST_GENERATED)

YES, NO = 'YES', 'NO'


class EfinError(ValueError):
    """Falha que a regra CONHECE: vai à tela com código + parâmetros e é dita
    no idioma de quem usa (§486); o `text` é só o fallback."""

    def __init__(self, code, text, **params):
        super().__init__(text.format(**params) if params else text)
        self.code = code
        self.text = text.format(**params) if params else text
        self.params = params


def aviso(code, text, **params):
    return {'code': code, 'text': text.format(**params) if params else text, 'params': params}


# ── Texto, número e data ────────────────────────────────────────────────────
def norm(s):
    """Maiúsculas, sem acento, espaço colapsado."""
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r'\s+', ' ', s).strip().upper()


def alnum(s):
    return re.sub(r'[^A-Z0-9]', '', norm(s))


def digits(s):
    return re.sub(r'\D', '', str(s or ''))


def cnpj_key(s):
    """CNPJ/CPF comparável: só dígitos, com o zero à esquerda que a planilha
    come de volta (12-13 dígitos é um CNPJ lido como número)."""
    d = digits(s)
    if 11 < len(d) < 14:
        d = d.zfill(14)
    return d


def num(v):
    """Número de planilha ou de tela, BR ou US (o ÚLTIMO separador é o decimal
    quando há os dois); `None` quando não há número — diferente de zero."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace('R$', '').replace('\xa0', '').replace(' ', '')
    if not s:
        return None
    neg = s.startswith('-') or s.endswith('-') or (s.startswith('(') and s.endswith(')'))
    s = s.strip('()+-')
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.') if s.rfind(',') > s.rfind('.') else s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '') if s.count(',') > 1 else s.replace(',', '.')
    elif s.count('.') > 1:
        s = s.replace('.', '')
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


def parse_date(v):
    """`date` de dd/mm/aaaa, aaaa-mm-dd, dd/mm/aa, aaaammdd ou datetime; None se não é data."""
    if v is None or v == '':
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()[:19]
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d/%m/%y', '%Y%m%d', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M:%S'):
        try:
            return datetime.strptime(s if ' ' in fmt else s[:10], fmt).date()
        except ValueError:
            continue
    return None


def iso(v):
    d = parse_date(v)
    return d.isoformat() if d else ''


def dmy(v):
    d = parse_date(v)
    return d.strftime('%d/%m/%Y') if d else ''


def r2(x):
    """2 casas meio-para-cima (o `round` do Python é o do banqueiro)."""
    return float(Decimal(str(x or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def month_key(d):
    return '%04d%02d' % (d.year, d.month)


def month_bounds(d):
    ini = date(d.year, d.month, 1)
    prox = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return ini, prox - timedelta(days=1)


# ── Produto, LOB e página ───────────────────────────────────────────────────
_LOB_EDG = ('EQUITIES', 'EQUITY', 'ACOES', 'INDICESINTERNACIONAIS', 'EDG')
_LOB_COMM = ('COMMODITIES', 'COMMODITY', 'COMM', 'MERCADORIA', 'MERCADORIAS')
_LOB_MOEDA = ('MOEDA', 'MOEDAS', 'TAXADECAMBIO', 'TAXASDECAMBIO', 'CAMBIO')


def produto_lob(product, lob, source=''):
    """(PRODUCT, LOB) como a tela os mostra — a mesma regra do WHT (§692), com a
    classe de ativo da opção traduzida:
      * TERMO / NDF COMMODITIES (o termo de mercadoria do Trade Level) → NDF ×
        COMMODITIES;
      * classe EQUITIES / INDICES INTERNACIONAIS → EDG (a mesa de equity);
      * classe MOEDA / TAXA DE CÂMBIO da opção → CEM;
      * NDF sem LOB (o do NDF Cockpit, fonte `ndf`) → CEM.
    Swap e opção sem LOB ficam SEM LOB (a tela avisa): chutar uma mesa mandaria
    a operação para o arquivo de outro sistema."""
    p, l = norm(product), norm(lob)
    if p in ('TERMO', 'NDF COMMODITIES', 'NDF COMM'):
        p, l = 'NDF', LOB_COMMODITIES
    elif p in ('OPTION COMM', 'OPCAO', 'OPCOES', 'OPTIONS'):
        p = 'OPTION'
        l = LOB_COMMODITIES if norm(product) == 'OPTION COMM' else l
    a = alnum(l)
    if a in _LOB_EDG:
        l = 'EDG'
    elif a in _LOB_COMM:
        l = LOB_COMMODITIES
    elif a in _LOB_MOEDA:
        l = 'CEM'
    if p == 'NDF' and not l and source in ('', 'ndf'):
        l = 'CEM'
    return p, l


def page_of(product, lob):
    """A página (o sistema de origem) da operação: tudo da EDG é PYRAMID (opção,
    NDF e swap); fora dela, o swap é KAPITAL (CEM/CEMHYB), a opção ATHENA-FXO
    (de câmbio e de mercadoria) e o NDF ATHENA-NDF (de câmbio e de mercadoria)."""
    if norm(lob) == 'EDG':
        return 'pyramid'
    return {'SWAP': 'kapital', 'OPTION': 'athena-fxo', 'NDF': 'athena-ndf'}.get(norm(product))


# ── O evento ────────────────────────────────────────────────────────────────
def kinds_of(settle_type, unwind=False):
    """Os tipos de um evento a partir do `Settlement Type` da tela ('Premium ·
    Maturity', 'EXERCISE', 'UNWIND'…). A recompra é UNWIND, sempre; texto que
    não diz nada vira SETTLEMENT (caixa sem tipo, que não encerra)."""
    if unwind:
        return [UNWIND]
    out = []
    for t in re.split(r'[·,/;]', str(settle_type or '')):
        t = norm(t)
        k = (PREMIUM if 'PREMI' in t else
             UNWIND if ('UNWIND' in t or 'ANTECIPA' in t or 'RECOMPRA' in t) else
             EXERCISE if 'EXERC' in t else
             CASHFLOW if ('CASHFLOW' in t or 'FLUXO' in t) else
             EXPIRY if 'EXPIR' in t else
             MATURITY if ('MATURITY' in t or 'VENCIMENTO' in t or 'RESGATE' in t) else '')
        if k and k not in out:
            out.append(k)
    return out or [SETTLEMENT]


def holder_of(v):
    """O banco é o TITULAR do prêmio (o que PAGA)? A `Posição da Parte` da
    opção (TITULAR/LANCADOR, códigos 11/12) ou o `Premio a ser pago pelo` do
    termo (PARTE = nós). True / False / None."""
    t = norm(v)
    if not t:
        return None
    if 'TITULAR' in t or t in ('11', '1', 'PARTE', 'HOLDER', 'BUYER', 'COMPRADOR'):
        return True
    if 'LANC' in t or 'CONTRA' in t or t in ('12', '2', 'WRITER', 'SELLER', 'VENDEDOR'):
        return False
    return None


def closes(ev):
    """O evento ENCERRA a operação? Vencimento, exercício e expiração sim; a
    recompra só a TOTAL (`closes` = True, a regra da vertical de Unwinds); o
    fluxo de swap só quando é o do vencimento. O resto não."""
    ks = ev.get('kinds') or ()
    if any(k in _FECHA for k in ks):
        return True
    if UNWIND in ks:
        return ev.get('closes') is True
    if CASHFLOW in ks:
        return bool(ev.get('maturity')) and ev.get('maturity') == ev.get('day')
    return False


def op_key(le, b3_id, internal_id):
    """A identidade da operação no mês: entidade × B3 ID (a `conta_num`), ou o
    Internal ID quando a linha veio sem B3 ID."""
    b3 = str(b3_id or '').strip().upper()
    return '%s|%s' % (norm(le), b3 or ('ID:' + str(internal_id or '').strip().upper()))


def event_label(kinds):
    """O Evento da tela, no vocabulário da equipe: `Premium Payment` e
    `Settlement` — com o tipo da liquidação entre parênteses, que é o que diz
    se a operação encerrou."""
    out = []
    if PREMIUM in kinds:
        out.append('Premium Payment')
    subs = [_SUBTIPO[k] for k in kinds if k != PREMIUM and _SUBTIPO.get(k)]
    if subs:
        out.append('Settlement (%s)' % ', '.join(subs))
    elif any(k != PREMIUM for k in kinds):
        out.append('Settlement')
    return ' · '.join(out)


def _primeiro(o, campo, valor):
    if valor not in (None, '') and o.get(campo) in (None, ''):
        o[campo] = valor


def aggregate(events):
    """{chave: operação} a partir dos eventos do mês (já com a `le` resolvida).

    Por evento: o PRÊMIO (só prêmio) entra em Total Crédito quando o banco
    recebe e em Total Débito + Pagamento Acumulado quando paga; a LIQUIDAÇÃO
    entra no Pagamento Acumulado quando o banco paga. O que encerra dá a Data
    de Encerramento (a mais tarde). Evento com prêmio E liquidação no mesmo
    caixa não se separa: vai como liquidação, marcado (`mixed`)."""
    ops = {}
    for e in sorted(events, key=lambda e: (e.get('day') or '', e.get('source') or '', e.get('seq') or 0)):
        k = op_key(e.get('le'), e.get('b3_id'), e.get('internal_id'))
        o = ops.get(k)
        if o is None:
            o = ops[k] = {
                'key': k, 'le': norm(e.get('le')), 'kinds': [], 'days': [], 'sources': [],
                'internal_value': None, 'b3_value': None, 'tol': 0.0,
                'tot_credit': 0.0, 'tot_debit': 0.0, 'payment': 0.0, 'closing': '',
                'premium': None, 'holder': None, 'premium_date': '', 'premium_event': False,
                'mixed': False, 'unwind_unknown': False, 'cash': False}
        for c in ('internal_id', 'b3_id', 'counterparty', 'taxid', 'product', 'lob',
                  'trade_date', 'maturity'):
            _primeiro(o, c, e.get(c))
        ks = list(e.get('kinds') or [SETTLEMENT])
        for kk in ks:
            if kk not in o['kinds']:
                o['kinds'].append(kk)
        if e.get('source') and e['source'] not in o['sources']:
            o['sources'].append(e['source'])
            o['tol'] = max(o['tol'], TOL_BY_SOURCE.get(e['source'], 0.0))
        v, b3 = e.get('value'), e.get('b3_value')
        if v is not None:
            o['internal_value'] = (o['internal_value'] or 0.0) + v
            o['cash'] = True
            if e.get('day') and e['day'] not in o['days']:
                o['days'].append(e['day'])
        if b3 is not None:
            o['b3_value'] = (o['b3_value'] or 0.0) + b3
        if v is None and EXPIRY not in ks:
            # liquidação que a tela mostrou sem valor interno: o Pagamento
            # Acumulado dela não se sabe
            o['no_value'] = True
        so_premio = ks == [PREMIUM]
        if v is not None:
            if so_premio:
                if v > 0:
                    o['tot_credit'] += v
                elif v < 0:
                    o['tot_debit'] += -v
                    o['payment'] += -v
                # o prêmio do MÊS diz o valor, quem paga e quando
                o['premium'], o['holder'] = abs(v), v < 0
                o['premium_date'], o['premium_event'] = e.get('day') or '', True
            elif v < 0:
                o['payment'] += -v
        if PREMIUM in ks and not so_premio:
            o['mixed'] = True
        # sem prêmio no mês, o da posição (a opção de 2021 que vence agora)
        if not o['premium_event']:
            _primeiro(o, 'premium', num(e.get('premium')) if e.get('premium') not in (None, '') else None)
            if o['holder'] is None and e.get('holder') is not None:
                o['holder'] = e.get('holder')
            _primeiro(o, 'premium_date', e.get('premium_date'))
        if UNWIND in ks and e.get('closes') is None:
            o['unwind_unknown'] = True
        if closes(e) and (e.get('day') or '') > o['closing']:
            o['closing'] = e.get('day') or ''
        if EXPIRY in ks and e.get('day') and e['day'] not in o['days']:
            o['days'].append(e['day'])
    for o in ops.values():
        # A expiração é a posição dizendo que a opção venceu; com o exercício
        # (ou o vencimento) no mesmo mês, ela é a mesma notícia duas vezes.
        if EXPIRY in o['kinds'] and any(k in (MATURITY, EXERCISE) for k in o['kinds']):
            o['kinds'].remove(EXPIRY)
        if o['premium'] is not None and o['premium'] <= 0:
            o['premium'] = None
    return ops


# ── A correção da tela (Edit, Add Row) e o fechamento da operação ──────────
# coluna da tela → (campo da operação, tipo). Os que ENTRAM na conta (a
# identidade, o prêmio, as datas) são aplicados antes de `finish`; os
# TOTAIS do arquivo, depois — o Saldo digitado vence o calculado.
EDIT_COLS = {
    'LE': ('le', 'select'), 'Internal ID': ('internal_id', 'text'), 'B3 ID': ('b3_id', 'text'),
    'Counterparty': ('counterparty', 'text'), 'Tax ID': ('taxid', 'text'),
    'Product': ('product', 'select'), 'LOB': ('lob', 'select'),
    'Trade Date': ('trade_date', 'date'), 'Settlement Date': ('maturity', 'date'),
    'Premium': ('premium', 'num'), 'Premium Holder': ('holder', 'select'),
    'Premium Payment Date': ('premium_date', 'date'),
    'Total Debit': ('tot_debit', 'num'), 'Total Credit': ('tot_credit', 'num'),
    'Balance': ('balance', 'num'), 'Accumulated Payment': ('payment', 'num'),
    'Closing Date': ('closing', 'date'), 'CGD Date': ('cgd_date', 'date'),
}
OUTPUT_FIELDS = ('tot_debit', 'tot_credit', 'balance', 'payment')
SELECTS = {'Product': PRODUCTS, 'LOB': LOBS, 'Premium Holder': ('', YES, NO)}
# O que o Add Row exige: sem eles a linha não vai ao arquivo nem à página certa.
ADD_REQUIRED = ('LE', 'B3 ID', 'Counterparty', 'Product', 'LOB')

REVIEW_PENDING = 'Pending'
REVIEW_APPROVED = 'Approved'


def clean_edit(col, raw, selects=None):
    """O valor gravável de `raw` para a coluna `col` — ou EfinError com o código."""
    alvo = EDIT_COLS.get(col)
    if not alvo:
        raise EfinError('edit_bad_column', 'A coluna {col} não se edita', col=col)
    campo, tipo = alvo
    s = str(raw if raw is not None else '').strip()
    if tipo == 'num':
        if not s:
            return None if campo == 'premium' else 0.0
        v = num(s)
        if v is None:
            raise EfinError('edit_bad_number', '{col}: "{value}" não é um número', col=col, value=s)
        if v < 0:
            raise EfinError('edit_negative', '{col}: o valor não pode ser negativo', col=col)
        return r2(v)
    if tipo == 'date':
        if not s:
            return ''
        d = parse_date(s)
        if not d:
            raise EfinError('edit_bad_date', '{col}: "{value}" não é uma data', col=col, value=s)
        return d.isoformat()
    if tipo == 'select':
        ops = list((selects or {}).get(col) or SELECTS.get(col) or ())
        v = norm(s)
        if v not in [norm(o) for o in ops]:
            raise EfinError('edit_bad_option', '{col}: "{value}" não é uma das opções', col=col, value=s)
        if campo == 'holder':
            return True if v == YES else (False if v == NO else None)
        return v
    if campo == 'b3_id':
        return s.upper()
    return s


def apply_fields(o, fields, only=None, skip=()):
    """`o` com os campos corrigidos; `only`/`skip` recortam (antes e depois de
    `finish`)."""
    for campo, valor in (fields or {}).items():
        if (only is not None and campo not in only) or campo in skip:
            continue
        o[campo] = valor
    return o


def finish(o, fields=None):
    """Fecha a operação: as correções de entrada, o Saldo (o prêmio RECEBIDO na
    vida, só de quem encerrou), as correções dos totais, o `pag_tp` e o
    veredito Interno × B3."""
    apply_fields(o, fields, skip=OUTPUT_FIELDS)
    o['product'], o['lob'] = produto_lob(o.get('product'), o.get('lob'), (o.get('sources') or [''])[0])
    closed = bool(o.get('closing'))
    prem = o.get('premium')
    o['balance'] = r2(prem) if (closed and prem and o.get('holder') is False) else 0.0
    for c in ('tot_credit', 'tot_debit', 'payment'):
        o[c] = r2(o.get(c) or 0.0)
    apply_fields(o, fields, only=OUTPUT_FIELDS)
    o['pag_tp'] = PAG_TP_PAGO if abs(o.get('payment') or 0.0) >= 0.005 else PAG_TP_SEM
    iv, bv = o.get('internal_value'), o.get('b3_value')
    if iv is not None and bv is not None:
        o['difference'] = r2(iv - bv)
        o['b3_check'] = 'OK' if abs(iv - bv) <= (o.get('tol') or 0.0) + 1e-9 else 'Check'
    else:
        o['difference'], o['b3_check'] = None, ''
    o['page'] = page_of(o.get('product'), o.get('lob'))
    return o


def missing(o, declarants):
    """O que falta para a linha ir ao arquivo (os nomes das colunas da tela)."""
    out = []
    if norm(o.get('le')) not in declarants:
        out.append('LE')
    if not str(o.get('b3_id') or '').strip():
        out.append('B3 ID')
    if not cnpj_key(o.get('taxid')):
        out.append('Tax ID')
    if not parse_date(o.get('cgd_date')):
        out.append('CGD Date')
    return out


def status_of(review, generated):
    if review == REVIEW_PENDING:
        return ST_PENDING
    if generated:
        return ST_GENERATED
    if review == REVIEW_APPROVED:
        return ST_APPROVED
    return ST_NEW


def _money(v):
    return None if v is None else r2(v)


def row_of(o):
    """A linha da tabela (as colunas da tela pelo nome)."""
    holder = o.get('holder')
    return {
        'key': o['key'],
        'Status': o.get('status') or ST_NEW,
        'review': o.get('review') or '', 'review_by': o.get('review_by') or '',
        'review_at': o.get('review_at') or '', 'edited': o.get('edited') or [],
        'manual': bool(o.get('manual')),
        'LE': o.get('le') or '',
        'Internal ID': o.get('internal_id') or '',
        'B3 ID': o.get('b3_id') or '',
        'Counterparty': o.get('counterparty') or '',
        'Tax ID': o.get('taxid') or '',
        'Product': o.get('product') or '',
        'LOB': o.get('lob') or '',
        'Trade Date': dmy(o.get('trade_date')),
        'Settlement Date': dmy(o.get('maturity')),
        'Premium': _money(o.get('premium')),
        'Premium Holder': YES if holder is True else (NO if holder is False else ''),
        'Premium Payment Date': dmy(o.get('premium_date')),
        'Event': o.get('event') or event_label(o.get('kinds') or []),
        'Event Date': ', '.join(dmy(d) for d in sorted(o.get('days') or [])),
        'Internal Value': _money(o.get('internal_value')),
        'B3 Value': _money(o.get('b3_value')),
        'Difference': o.get('difference'),
        'b3_check': o.get('b3_check') or '',
        'Total Debit': _money(o.get('tot_debit')),
        'Total Credit': _money(o.get('tot_credit')),
        'Balance': _money(o.get('balance')),
        'Accumulated Payment': _money(o.get('payment')),
        'Closing Date': dmy(o.get('closing')),
        'CGD Date': dmy(o.get('cgd_date')),
        # de onde veio a data do CGD: refdata · trackdocs · edit (o tooltip)
        'cgd_src': o.get('cgd_src') or '',
        'PAG_TP': o.get('pag_tp') or '',
        'missing': o.get('missing') or [],
    }


def counts(rows):
    c = {'total': len(rows), 'closed': 0, 'payments': 0, 'b3_check': 0, 'pending': 0, 'missing': 0}
    soma = {'tot_credit': 0.0, 'tot_debit': 0.0, 'balance': 0.0, 'payment': 0.0}
    for r in rows:
        c['closed'] += 1 if r['Closing Date'] else 0
        c['payments'] += 1 if r['PAG_TP'] == PAG_TP_PAGO else 0
        c['b3_check'] += 1 if r['b3_check'] == 'Check' else 0
        c['pending'] += 1 if r['Status'] == ST_PENDING else 0
        c['missing'] += 1 if r['missing'] else 0
        soma['tot_credit'] += r['Total Credit'] or 0.0
        soma['tot_debit'] += r['Total Debit'] or 0.0
        soma['balance'] += r['Balance'] or 0.0
        soma['payment'] += r['Accumulated Payment'] or 0.0
    c.update({k: r2(v) for k, v in soma.items()})
    return c


# ── O arquivo (CSV `;`, cabeçalho na 1ª linha) ──────────────────────────────
# O layout da equipe (30/10/2026), coluna a coluna. Os fixos são do layout; o
# declarante sai do cadastro `efin-declarant`; "não preencher" vai vazio.
HEADER = ('num_ente_declarante', 'cnpjdeclarante', 'num_ente_declarado', 'declarado_ni',
          'anomescaixa', 'conta_tp', 'conta_subtp', 'conta_tpnum', 'conta_agencia', 'conta_num',
          'conta_reportpais', 'conta_notitulares', 'conta_tprelacdecla', 'conta_dtencerr',
          'fl_primeiro_titular', 'balanco_totcred', 'balanco_totdeb', 'balanco_totcreditu',
          'balanco_totdebitu', 'balanco_vlrultdia', 'pag_tp', 'pag_totpgacum', 'cambio_totcomp',
          'cambio_totvend', 'cambio_tottransf', 'fundo_giin', 'fundo_cnpj', 'inter_giin', 'inter_ni',
          'prop_ni', 'conta_dtabertu')
CONTA_TP = '2'
CONTA_SUBTP = '203'
CONTA_TPNUM = 'OECD605'
CONTA_TPRELACDECLA = '1'
FL_PRIMEIRO_TITULAR = 'S'
# "When PAG_TP != 999, PAG_TOTPGACUM must be populated and != 0"
PAG_TP_PAGO = 'FATCA504'
PAG_TP_SEM = '999'
ENCODING = 'cp1252'


def money(v):
    """Valor do arquivo: vírgula decimal, sem milhar, duas casas; zero é `0`
    (o exemplo da equipe: `0;0;;;0;FATCA504;22256669,26`)."""
    x = r2(abs(v or 0.0))
    if x == 0:
        return '0'
    return ('%.2f' % x).replace('.', ',')


def _cel(s):
    return str(s or '').replace(';', ' ').replace('\r', ' ').replace('\n', ' ').strip()


def file_record(o, declarant, ym):
    """Os 31 campos da linha da operação `o` (já fechada por `finish`)."""
    pag = o.get('payment') or 0.0
    rec = {
        'num_ente_declarante': declarant.get('ente'),
        'cnpjdeclarante': digits(declarant.get('cnpj')),
        'declarado_ni': cnpj_key(o.get('taxid')),
        'anomescaixa': ym,
        'conta_tp': CONTA_TP,
        'conta_subtp': CONTA_SUBTP,
        'conta_tpnum': CONTA_TPNUM,
        'conta_num': str(o.get('b3_id') or '').strip().upper(),
        'conta_tprelacdecla': CONTA_TPRELACDECLA,
        'conta_dtencerr': dmy(o.get('closing')),
        'fl_primeiro_titular': FL_PRIMEIRO_TITULAR,
        'balanco_totcred': money(o.get('tot_credit')),
        'balanco_totdeb': money(o.get('tot_debit')),
        'balanco_vlrultdia': money(o.get('balance')),
        'pag_tp': o.get('pag_tp') or (PAG_TP_PAGO if abs(pag) >= 0.005 else PAG_TP_SEM),
        'pag_totpgacum': money(pag),
        'conta_dtabertu': dmy(o.get('cgd_date')),
    }
    return [_cel(rec.get(h, '')) for h in HEADER]


def file_text(records):
    """O arquivo inteiro: o cabeçalho e uma linha por operação, CRLF."""
    linhas = [';'.join(HEADER)] + [';'.join(r) for r in records]
    return '\r\n'.join(linhas) + '\r\n'


def file_name(page, ym):
    return PAGES[page]['file'].format(ym=ym)
