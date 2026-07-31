"""
Porte para Python do parser de "Brazil Booking Recap" que vive em
``apps/static/js/pages/otc-fileupload.js`` (parseEmailHtml + buildRow).

POR QUE ESTE ARQUIVO EXISTE
---------------------------
O caminho manual (dropzone e botão Import) parseia o e-mail **no navegador**.
O scheduler de varredura do box roda **no servidor**, sem navegador, então a
mesma regra precisa existir aqui.

⚠️ ESTA É UMA SEGUNDA CÓPIA DE UMA REGRA DE NEGÓCIO. Mexeu numa, mexa na outra
— é a mesma armadilha do espelho JS/servidor do arquivo TER (HANDOFF §121), que
já produziu preview divergindo do arquivo gerado. O que protege as duas cópias é
``scratchpad/check_boxparse.py``: ele roda as funções JS **de verdade** no
JavaScriptCore e compara com as daqui, campo a campo. Rode-o depois de qualquer
alteração nos dois lados.

Equivalências que NÃO são óbvias e estão testadas contra o JS real:
  * ``_fmt_num_2dp``  → ``Number.toLocaleString('en-US', 2dp)`` arredonda a
    partir da representação decimal CURTA do double, half-up e "away from zero"
    (2.675 → 2.68, -2.675 → -2.68). ``'{:.2f}'.format`` erra esses casos, porque
    usa o valor binário exato e desempata para par (2.675 → 2.67).
  * ``_js_parse_float`` → ``parseFloat`` aceita lixo depois do número
    ("12abc" → 12.0) e devolve NaN quando não começa com número.
  * ``_get_cell_text`` → ``textContent`` de célula com tags aninhadas, com o
    nbsp que o Outlook injeta virando espaço comum.
  * O fallback de mês desconhecido em ``_parse_date`` cai em **janeiro**
    (``indexOf`` devolve -1 e o JS o troca por 0). Portado tal como está.
"""
import datetime as _dt
import logging
import re
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from html.parser import HTMLParser

_LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tabelas de mês (idênticas às do JS; a ORDEM de _MONTH_ABBR_ORDER importa —
# o JS usa o índice da chave como número do mês).
# ---------------------------------------------------------------------------
_MONTH_CODES = {
    'January': 'F', 'February': 'G', 'March':     'H',
    'April':   'J', 'May':      'K', 'June':      'M',
    'July':    'N', 'August':   'Q', 'September': 'U',
    'October': 'V', 'November': 'X', 'December':  'Z',
}

_MONTH_NAMES_ABBR = {
    'Jan': 'January', 'Feb': 'February', 'Mar': 'March',
    'Apr': 'April',   'May': 'May',      'Jun': 'June',
    'Jul': 'July',    'Aug': 'August',   'Sep': 'September',
    'Oct': 'October', 'Nov': 'November', 'Dec': 'December',
}
_MONTH_ABBR_ORDER = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                     'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
_MONTH_FULL_ORDER = [_MONTH_NAMES_ABBR[a] for a in _MONTH_ABBR_ORDER]


# ---------------------------------------------------------------------------
# Números — equivalentes exatos das primitivas do JS
# ---------------------------------------------------------------------------
_NUM_RE = re.compile(r'^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?')


def _js_parse_float(s):
    """``parseFloat`` do JS: ignora o que vier depois do número e devolve None
    (o NaN do JS) quando o texto não começa com um número."""
    if s is None:
        return None
    t = str(s).strip()
    if t[:8] == 'Infinity' or t[:9] in ('+Infinity', '-Infinity'):
        return float(t.replace('Infinity', 'inf'))
    m = _NUM_RE.match(t)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _fmt_num_2dp(val, abs_val=False):
    """``fmtNum2dp`` do JS: tira os separadores de milhar, opcionalmente pega o
    valor absoluto e formata como ``#,##0.00``. Texto não numérico volta como
    veio (o ``return val || ''`` do JS)."""
    n = _js_parse_float(str(val).replace(',', ''))
    if n is None:
        return val if val else ''
    if abs_val:
        n = abs(n)
    # toLocaleString arredonda sobre a representação decimal CURTA, half-up.
    # repr() em Python é essa mesma representação (menor string que faz
    # round-trip), então Decimal(repr(n)) reproduz o desempate do JS.
    try:
        q = Decimal(repr(n)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return val if val else ''
    return '{:,.2f}'.format(q)


def _is_cents_factor(f):
    """Fator Conversão == 0.01 ⇒ "Quoted in Cents" (tolerante a string/vírgula)."""
    if f is None or f == '':
        return False
    n = _js_parse_float(str(f).replace(',', '.')) if isinstance(f, str) else _num_or_none(f)
    return n is not None and abs(n - 0.01) < 1e-9


def _num_or_none(v):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return None if (n != n or n in (float('inf'), float('-inf'))) else n


def _parse_fator(fc):
    """Fator Conversão cru (número, '0.01', '0,01', None, '') → float|None."""
    if fc is None or fc == '':
        return None
    return (_js_parse_float(fc.replace(',', '.')) if isinstance(fc, str)
            else _num_or_none(fc))


def _normalize_ccy(v):
    """BRR → BRL, USB → USD; o resto passa apenas com trim."""
    if not v:
        return ''
    u = str(v).upper().strip()
    if u == 'BRR':
        return 'BRL'
    if u == 'USB':
        return 'USD'
    return str(v).strip()


# ---------------------------------------------------------------------------
# Datas
# ---------------------------------------------------------------------------
_DMY3_RE = re.compile(r'^(\d{1,2})[-\s/]([A-Za-z]{3,})[-\s/](\d{2,4})$')
_ISO_RE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})$')
_US_RE = re.compile(r'^(\d{1,2})/(\d{1,2})/(\d{4})$')
_MONTH_IN_DATE_RE = re.compile(r'^\d{1,2}[-/\s]([A-Za-z]{3,})[-/\s]\d{2,4}$')


def _parse_date(s):
    """``parseDate`` do JS → (ano, mês 1-12, dia) ou None.

    Cobre dd-mmm-yyyy (o formato do e-mail), ISO e US. O ``new Date(s)`` genérico
    do JS, que é dependente de engine, NÃO é replicado: entrada fora desses três
    formatos devolve None e o chamador mantém o texto original — que é o
    comportamento seguro para um valor que ninguém sabe ler."""
    if not s:
        return None
    s = str(s).strip()
    m = _DMY3_RE.match(s)
    if m:
        yr = int(m.group(3))
        if yr < 100:
            yr += 2000
        abbr = m.group(2)[0].upper() + m.group(2)[1:3].lower()
        try:
            mo_idx = _MONTH_ABBR_ORDER.index(abbr)
        except ValueError:
            mo_idx = 0          # o indexOf(-1) do JS vira 0 → janeiro
        return (yr, mo_idx + 1, int(m.group(1)))
    m = _ISO_RE.match(s)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _US_RE.match(s)
    if m:
        return (int(m.group(3)), int(m.group(1)), int(m.group(2)))
    return None


def _to_date(parts):
    """(ano, mês, dia) → date, normalizando dia fora de faixa como o
    ``new Date(y, m, d)`` do JS faz (30/02/2026 vira 02/03/2026). Sem isso, uma
    data inválida no e-mail sairia aqui diferente do que a tela mostra."""
    if not parts:
        return None
    yr, mo, dy = parts
    try:
        return _dt.date(yr, mo, 1) + _dt.timedelta(days=dy - 1)
    except (ValueError, OverflowError):
        return None


def _fmt_date_str(s):
    """Data em qualquer formato conhecido → dd/mm/yyyy; desconhecida volta crua."""
    d = _to_date(_parse_date(s))
    if not d:
        return s if s else ''
    return '{:02d}/{:02d}/{:04d}'.format(d.day, d.month, d.year)


def _extract_month_from_trade_date(raw):
    """'21-May-2026' → 'May' · '19-Apr-2025' → 'April' (nome cheio do mês)."""
    if not raw:
        return ''
    m = _MONTH_IN_DATE_RE.match(str(raw).strip())
    if m:
        word = m.group(1)
        if len(word) == 3:
            abbr = word[0].upper() + word[1:].lower()
            return _MONTH_NAMES_ABBR.get(abbr, word[0].upper() + word[1:].lower())
        return word[0].upper() + word[1:].lower()
    d = _to_date(_parse_date(raw))
    if d:
        return _MONTH_FULL_ORDER[d.month - 1]
    return ''


def _extract_direction(type_str):
    """'Sell Option (Put)' → 'SELL'."""
    if not type_str:
        return ''
    t = str(type_str).upper()
    if 'SELL' in t:
        return 'SELL'
    if 'BUY' in t:
        return 'BUY'
    return ''


# ---------------------------------------------------------------------------
# Código B3 do ativo subjacente
# ---------------------------------------------------------------------------
_CONTRACT_RE = re.compile(r'^([A-Za-z]{3})(\d+)$')


def _contract_parts(contract):
    """'May27' → ('K', '7')  (código do mês + último dígito do ano)."""
    if not contract:
        return None
    m = _CONTRACT_RE.match(str(contract).strip())
    if not m:
        return None
    abbr = m.group(1)[0].upper() + m.group(1)[1:3].lower()
    full = _MONTH_NAMES_ABBR.get(abbr, abbr)
    return (_MONTH_CODES.get(full, ''), m.group(2)[-1])


def _build_dynamic_code(prefix, contract):
    p = _contract_parts(contract)
    if not p:
        return prefix
    return prefix + p[0] + p[1]


def calculate_b3_id(market, contract, is_vanilla, fixed_codes, dynamic_prefix):
    """``calculateB3Id`` do JS. Os dois mapas vêm do cadastro Commodities × B3
    (/mapping) — nada de literal aqui, ver HANDOFF §131."""
    if not market or not contract:
        return ''
    mkt = str(market).upper().strip()
    if mkt in fixed_codes:
        return fixed_codes[mkt]
    if mkt == 'BRT_IPE':
        if is_vanilla:
            return _build_dynamic_code('CO', contract) or 'CO1-2'
        return 'CO1-2'
    if mkt == 'FCPO_BURSA_MYR':
        parts = _contract_parts(contract)
        if not parts:
            return ''
        return 'KO' + parts[0] + parts[1] + 'BNMK'
    prefix = dynamic_prefix.get(mkt)
    if not prefix:
        u = mkt.find('_')
        prefix = mkt[:u] if u > 0 else mkt
    return _build_dynamic_code(prefix, contract)


# ---------------------------------------------------------------------------
# HTML → linhas da tabela do booking recap
# ---------------------------------------------------------------------------
_VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link',
         'meta', 'param', 'source', 'track', 'wbr'}


class _Node(object):
    __slots__ = ('tag', 'parent', 'children', 'text')

    def __init__(self, tag, parent=None):
        self.tag = tag
        self.parent = parent
        self.children = []
        self.text = []

    def iter_desc(self, tags):
        """Descendentes com essas tags, em ordem de documento (o
        ``querySelectorAll`` do JS, que atravessa tabelas aninhadas)."""
        for ch in self.children:
            if ch.tag in tags:
                yield ch
            for d in ch.iter_desc(tags):
                yield d


def _walk_text(node):
    """textContent: todo texto descendente, na ordem em que aparece."""
    out = []
    for kind, payload in node.text:
        if kind == 't':
            out.append(payload)
        else:
            out.extend(_walk_text(payload))
    return out


class _TableParser(HTMLParser):
    """Constrói só o que o parser do e-mail precisa: a árvore de table/tr/td/th
    com o texto de cada célula. Tolerante a tag não fechada (o HTML do Outlook
    costuma vir assim)."""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.root = _Node('#root')
        self.cur = self.root
        self.tables = []

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            return
        node = _Node(tag, self.cur)
        self.cur.children.append(node)
        self.cur.text.append(('n', node))
        self.cur = node
        if tag == 'table':
            self.tables.append(node)

    def handle_startendtag(self, tag, attrs):
        node = _Node(tag, self.cur)
        self.cur.children.append(node)
        self.cur.text.append(('n', node))

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is self.root:
            return                      # fechamento órfão: ignora
        self.cur = n.parent or self.root

    def handle_data(self, data):
        self.cur.text.append(('t', data))


def _get_cell_text(node):
    """``getCellText``: textContent, nbsp → espaço, whitespace colapsado, trim."""
    s = ''.join(_walk_text(node))
    s = s.replace(' ', ' ')
    return re.sub(r'\s+', ' ', s).strip()


def _norm_header(s):
    return re.sub(r'[\s_]', '', str(s or '')).lower()


def parse_email_html(html_text):
    """``parseEmailHtml`` do JS → lista de dicts de deal.

    Acha a tabela cujo cabeçalho tem 'DealName' e devolve, no máximo, três
    registros — exatamente como o caminho do navegador:
      1. a 1ª linha de dados, como está (a ponta do cliente);
      2. a 2ª linha com a direção invertida → LAWTON;
      3. uma 3ª linha sintética, mesmos dados, ponta do Banco J.P. Morgan.
    """
    if not html_text:
        return []
    p = _TableParser()
    try:
        p.feed(html_text)
        p.close()
    except Exception as e:                                  # noqa: BLE001
        _LOG.warning('[boxparse] HTML ilegível: %s', e)
        return []

    target = None
    for tbl in p.tables:
        for c in tbl.iter_desc(('th', 'td')):
            if _norm_header(_get_cell_text(c)) == 'dealname':
                target = tbl
                break
        if target is not None:
            break
    if target is None:
        return []

    rows = list(target.iter_desc(('tr',)))
    if len(rows) < 2:
        return []

    header_idx = -1
    for i, r in enumerate(rows):
        if any(_norm_header(_get_cell_text(c)) == 'dealname'
               for c in r.iter_desc(('th', 'td'))):
            header_idx = i
            break
    if header_idx == -1:
        return []

    headers = [_get_cell_text(c) for c in rows[header_idx].iter_desc(('th', 'td'))]
    deals = []

    def row_cells(idx):
        if idx >= len(rows):
            return None
        # linhas de dados leem só <td> (o JS também), então uma linha de
        # cabeçalho repetida no meio da tabela não vira deal
        cells = [_get_cell_text(c) for c in rows[idx].iter_desc(('td',))]
        return cells or None

    client_cells = row_cells(header_idx + 1)
    if client_cells:
        d = {h: (client_cells[i] if i < len(client_cells) else '')
             for i, h in enumerate(headers)}
        d['_cells'] = client_cells
        deals.append(d)

    counter_cells = row_cells(header_idx + 2)
    if counter_cells:
        d2 = {h: (counter_cells[i] if i < len(counter_cells) else '')
              for i, h in enumerate(headers)}
        d2['_cells'] = counter_cells
        d2['_invertDirection'] = True
        deals.append(d2)

        d3 = {h: (counter_cells[i] if i < len(counter_cells) else '')
              for i, h in enumerate(headers)}
        d3['_cells'] = counter_cells
        d3['_jpMorganRow'] = True
        deals.append(d3)

    return deals


# ---------------------------------------------------------------------------
# deal parseado → registro do cache (o `rowData` do buildRow)
# ---------------------------------------------------------------------------
def _get_field(deal, name):
    """``getField``: acha a chave ignorando espaços, underscores e caixa."""
    lower = str(name).lower().replace(' ', '').replace('_', '')
    for k in deal:
        if str(k).lower().replace(' ', '').replace('_', '') == lower:
            v = deal[k]
            return '' if v is None else v
    return ''


# Pontas internas fixas — os mesmos literais do buildRow.
_LAWTON = {'spn': '0037862', 'counterparty': 'LAWTON MULTIMERCADO EXCLUSIVO',
           'taxId': '05.592.116/0001-80'}
_JPM = {'spn': '0023779', 'counterparty': 'BANCO J.P MORGAN S.A',
        'taxId': '33.172.537/0001-98'}


def build_deal(deal, ref_map, subj_idx, maker_sid, layout, maps):
    """``buildRow`` do JS, só a parte de dados (o ``rowData`` que vai ao cache).

    layout: 'ndf' (NDF Commodities) ou 'opt' (Opt Commodities — leva Premium,
    PremiumPerUnit, PremiumCCY e SpotDate a mais).
    maps: {'fixed': {...}, 'dynamic': {...}, 'holiday': {...}} do cadastro
    Commodities × B3.
    """
    maker_sid = maker_sid or ''
    deal_name = _get_field(deal, 'DealName')
    trade_date_raw = _get_field(deal, 'TradeDate')
    trade_date = _fmt_date_str(trade_date_raw)
    month = _extract_month_from_trade_date(trade_date_raw)
    contract = _get_field(deal, 'Contract')
    market = str(_get_field(deal, 'Market') or '').upper().strip()
    acronym = str(_get_field(deal, 'Acronym') or '').upper().strip()
    type_str = _get_field(deal, 'Type')

    fix_start_raw = _get_field(deal, 'FixingStartDate') or _get_field(deal, 'FixStart')
    fix_end_raw = _get_field(deal, 'FixingEndDate') or _get_field(deal, 'FixEnd')
    fix_start = _fmt_date_str(fix_start_raw)
    fix_end = _fmt_date_str(fix_end_raw)
    is_vanilla = bool(fix_start and fix_end and fix_start.strip() == fix_end.strip())
    trade_type = 'VANILLA' if is_vanilla else 'ASIAN'

    instrument = _get_field(deal, 'Instrument')
    b3_id = calculate_b3_id(market, contract, is_vanilla,
                            maps.get('fixed') or {}, maps.get('dynamic') or {})

    subj_entry = (subj_idx or {}).get(b3_id)
    commodity = (subj_entry or {}).get('commodity', '') if subj_entry else ''
    quoted_plain = ('MISSING' if not subj_entry
                    else ('YES' if _is_cents_factor(subj_entry.get('fatorConversao'))
                          else 'NO'))

    fx_holiday = (maps.get('holiday') or {}).get(market, '')

    ref = (ref_map or {}).get(acronym) or {'spn': '', 'counterparty': '', 'taxId': ''}
    if deal.get('_jpMorganRow'):
        acronym, ref = 'JPMORGANBM', _JPM
    if deal.get('_invertDirection'):
        acronym, ref = 'LAWTON', _LAWTON

    settle_date = _fmt_date_str(_get_field(deal, 'SettlementDate')
                                or _get_field(deal, 'SettleDate'))
    spot_date = _fmt_date_str(_get_field(deal, 'SpotDate'))
    fx_conv_date = _fmt_date_str(_get_field(deal, 'FXConvDate')
                                 or _get_field(deal, 'FxConvDate'))
    spot_fx_rate = (_get_field(deal, 'SpotFXRate') or _get_field(deal, 'SpotFxRate')
                    or _get_field(deal, 'Spot FX Rate'))

    notional_raw = (_get_field(deal, 'TotalNotional') or _get_field(deal, 'Total Notional')
                    or _get_field(deal, 'Notional') or _get_field(deal, 'Qty'))
    notional = _fmt_num_2dp(notional_raw, True)             # absoluto, 2 casas

    strike = _get_field(deal, 'Strike')

    cells = deal.get('_cells') or []
    strike_ccy_raw = ((cells[8] if len(cells) > 8 else '')
                      or _get_field(deal, 'StrikeCCY') or _get_field(deal, 'StrikeCurrency')
                      or _get_field(deal, 'Strike CCY') or _get_field(deal, 'StrikeCcy'))
    strike_ccy = _normalize_ccy(strike_ccy_raw)

    premium = _fmt_num_2dp(_get_field(deal, 'Premium'), False)   # mantém o sinal
    premium_pu = _get_field(deal, 'PremiumPerUnit') or _get_field(deal, 'PremPU')
    premium_ccy = _normalize_ccy(
        _get_field(deal, 'PremCCY') or _get_field(deal, 'PremiumCCY')
        or _get_field(deal, 'PremiumCurrency') or _get_field(deal, 'Prem CCY'))

    trading_book = _get_field(deal, 'TradingBook') or _get_field(deal, 'Trading Book')
    other_book = _get_field(deal, 'OtherBook') or _get_field(deal, 'Other Book')

    direction = _extract_direction(type_str)
    if deal.get('_invertDirection'):
        direction = 'BUY' if direction == 'SELL' else ('SELL' if direction == 'BUY' else direction)

    data = {
        'Status':            'New',
        'Deal':              deal_name,
        'B3_ID':             '',
        'TradeDate':         trade_date,
        'Month':             month,
        'SettlementDate':    settle_date,
        'SPN':               ref.get('spn', ''),
        'Acronym':           acronym,
        'Client':            ref.get('counterparty', '') or '',
        'TaxID':             ref.get('taxId', '') or '',
        'TradeType':         trade_type,
        'Market':            market,
        'UnderlyingAsset':   b3_id,
        'Commodities':       commodity,
        'FXHolidaySchedule': fx_holiday,
        'TotalNotional':     notional,
        'Instrument':        instrument,
        'Contract':          contract,
        'Strike':            strike,
        'StrikeCurrency':    strike_ccy,
        'Direction':         direction,
        'SpotFXRate':        spot_fx_rate,
        'FXConvDate':        fx_conv_date,
        'FixingStartDate':   fix_start,
        'FixingEndDate':     fix_end,
        'TradingBook':       trading_book,
        'OtherBook':         other_book,
        'QuotedInCents':     quoted_plain,
        'Maker':             maker_sid,
        'Checker':           '',
    }
    if layout != 'ndf':
        data['Premium'] = premium
        data['PremiumPerUnit'] = premium_pu
        data['PremiumCCY'] = premium_ccy
        data['SpotDate'] = spot_date
    return data


def deals_from_html(html_text, ref_map, subj_idx, maker_sid, layout, maps):
    """HTML de um e-mail → registros prontos para o cache."""
    return [build_deal(d, ref_map, subj_idx, maker_sid, layout, maps)
            for d in parse_email_html(html_text)]
