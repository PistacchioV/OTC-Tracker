# -*- coding: utf-8 -*-
"""O motor do Settlement Forecast — a matriz entidade × produto × dia que a
página de Forecast desenha e o e-mail diário envia.

Movido VERBATIM do `routes.py` (fase platform/ — CLAUDE.md §10). É horizontal
porque a família de liquidação também lê daqui: `_ops_settlement_counts` e
`_ops_swap_trade_rows` (platform/settlement.py) usam `_forecast_collect`,
`_fcst_norm`, `_fcst_lob` e os mapas de contrato de swap
(`_swap_contract_ident_map`/`_swap_contract_cpty_map`) pelo alias do routes.

O `routes.py` mantém os nomes como ALIAS. O que ainda é do `routes` — o
`B3_JSON_ROOT`/`_b3_date_subpath` dos arquivos-dia e o calendário
(`_pcx_is_bizday`, `_prev_anbima_bizday`, trocados nos testes pelo `R.`) — é
alcançado por import ATRASADO dentro da função, andaime declarado.
"""
import json
import logging
import os

from apps.pages.request_cache import req_cached as _req_cached
import re
import traceback
import unicodedata
from datetime import datetime, timedelta

log = logging.getLogger('otc_tracker')

FORECAST_BIZDAYS = 15                 # default business-day look-ahead window (from today, inclusive)
FORECAST_RANGE_CHOICES = (15, 20, 30) # selectable horizons offered on the dashboard

# Entity code → name. Keys are normalised (digits only) at lookup, so dotted
# variants (00041.00-7) match too. Anything unmapped is dropped from the by-entity
# breakdown (mirrors the Alteryx !Contains([Entity],"0") filter).
_FCST_ENTITY_MAP = {
    '00041007': 'LAWTON',
    '04880006': 'MGT',
    '85398005': 'ATACAMA',
}
_FCST_ENTITY_ORDER = ['LAWTON', 'MGT', 'ATACAMA']
_FCST_PRODUCT_ORDER = ['NDF Moeda', 'NDF Commodities', 'Option FXO', 'Option Commodities',
                       'Option EDG', 'SWAP CEM', 'SWAP EDG', 'SWAP CEMHYB']

# One entry per JSON source. Field resolution is by NAME token (case-insensitive
# "contains", first match wins) so it survives small header differences.
#   date    : tokens to find the settlement/maturity/event date column
#   entity  : tokens to find the entity/counterparty column
#   product : ('fixed', label)        → constant product label
#             ('ndfclass', tokens)    → NDF Moeda / NDF Commodities from class field
#             ('sisbacen', tokens)    → option product by Código SISBACEN
#             ('lob', tokens)         → SWAP CEM/EDG/CEMHYB from "Código Identificador"
#             ('lob_join', tokens)    → same, but the source has only the contract
#                                       code; join it to the DPOSICAO-SWAP position
#                                       map to recover the identifier first
_FORECAST_SOURCES = [
    {'key': 'ndf', 'label': 'NDF (TER)', 'category': 'NDF',
     'file': lambda r: '73760_{}_DPOSICAO-TER.json'.format(r),
     # Prefer the exact "Data de Vencimento" (maturity) — the real JP TER file has
     # many columns and could carry other "…vencimento…" fields; fall back to a
     # loose 'vencimento' only if the exact name isn't present.
     'date': ['data de vencimento', 'vencimento'],
     # Entity = the COUNTERPARTY account, NOT "Titular" (the holder / the bank),
     # same as the options file — else NDF is attributed to the holder and
     # vanishes from the by-entity breakdown.
     'entity': ['contraparte(conta)', 'contraparte', 'parte', 'conta'],
     'product': ('ndfclass', ['classe do ativo', 'ativo subjacente', 'mercadoria', 'classe'])},
    {'key': 'opc', 'label': 'Options (OPC)', 'category': 'Option',
     'file': lambda r: '73760_{}_DPOSICAO.json'.format(r),
     # Entity = the COUNTERPARTY account ("Contraparte(Conta)"), NOT "Titular"
     # (which is the holder / the bank, 73760). Listing 'titular' first previously
     # resolved every option to the holder → unmapped → the option premiums and
     # exercises showed under by-product but vanished from the by-entity breakdown.
     'date': ['vencimento'], 'entity': ['contraparte(conta)', 'contraparte', 'conta'],
     'product': ('optclass', ['classe do ativo', 'ativo subjacente', 'classe']),
     # Options (FXO/Comm/EDG) are counted on TWO dates: the maturity (col M,
     # "Data do Vencimento", via 'date') AND the premium settlement (col BN,
     # "Data de Liquidação do Prêmio", via 'date2'). A single contract therefore
     # contributes a count on each of those business days within the window.
     'date2': ['data de liquidacao do premio', 'data liquidacao do premio',
               'liquidacao do premio'],
     'date2_index': 65},   # fallback: col BN (1-based 66) if the header name shifts
    {'key': 'swap_pos', 'label': 'SWAP Position', 'category': 'Swap',
     'file': lambda r: '73760_{}_DPOSICAO-SWAP.json'.format(r),
     'date': ['data vencimento'], 'entity': ['contraparte'],
     'product': ('lob', ['código identificador', 'codigo identificador', 'identificador']),
     # "Tipo de Contrato" (1st col): 1 = cash-flow swap → counted via the FLUXO
     # file only (counting both would double it); 2 = bullet/final payment →
     # counted here by maturity (col M). So the Position file counts ONLY tipo 2.
     'count_where': (['tipo de contrato', 'tipo do contrato', 'tipo contrato', 'tipo de contr'], {'2'})},
    {'key': 'swap_flx', 'label': 'SWAP Flow', 'category': 'Swap',
     'file': lambda r: '73760_{}_DFLUXO.json'.format(r),
     'date': ['ocorrência do evento', 'ocorrencia do evento', 'evento'],
     'entity': ['nome simplificado contraparte', 'nome simplificado'],
     'product': ('lob', ['código identificador', 'codigo identificador', 'identificador'])},
    {'key': 'swap_prm', 'label': 'SWAP Premium Agenda', 'category': 'Swap',
     'file': lambda r: '73760_{}_DAGENDAPREMIOS.json'.format(r),
     # Premium settlement date = "Data do Evento" (col F). Name first, then col F
     # (index 5) as a fallback when the stored header is positional.
     'date': ['data do evento', 'evento'],
     'date_index': 5,
     # DAGENDAPREMIOS "Nome Simplificado" is the PARTE (holder), not the
     # counterparty — resolve the entity by JOINING the contract code to the
     # DPOSICAO-SWAP position map → Contraparte, so Lawton/MGT/Atacama premium
     # settlements are counted in the by-entity breakdown.
     'entity': ['nome simplificado', 'parte'],
     'entity_join': 'cpty',
     # DAGENDAPREMIOS has no "Código Identificador": classify by joining the
     # contract code (col A) to the DPOSICAO-SWAP position map → identifier → LOB.
     'product': ('lob_join', ['codigo do contrato', 'código do contrato', 'contrato'])},
]


_FCST_MONTH_ABBR = {  # English + Portuguese 3-letter month abbreviations → month number
    'jan': 1, 'feb': 2, 'fev': 2, 'mar': 3, 'apr': 4, 'abr': 4, 'may': 5, 'mai': 5,
    'jun': 6, 'jul': 7, 'aug': 8, 'ago': 8, 'sep': 9, 'set': 9, 'oct': 10, 'out': 10,
    'nov': 11, 'dec': 12, 'dez': 12,
}


def _fcst_parse_date(s):
    """Parse a CETIP date string (several known layouts) → date, or None."""
    s = (s or '').strip()
    if not s:
        return None
    s = s.split(' ')[0].split('T')[0]
    for fmt in ('%Y%m%d', '%d/%m/%Y', '%Y-%m-%d', '%d/%m/%y', '%d.%m.%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # dd-mmm-yyyy with month names (e.g. 06-Jul-2026) — locale-independent via map.
    m = re.match(r'^(\d{1,2})[-/ ]([A-Za-zçÇ]{3,9})[-/ ](\d{2,4})$', s)
    if m:
        mon = _FCST_MONTH_ABBR.get(m.group(2)[:3].lower())
        if mon:
            try:
                y = int(m.group(3))
                y += 2000 if y < 100 else 0
                return datetime(y, mon, int(m.group(1))).date()
            except ValueError:
                pass
    return None


def _fcst_map_entity(raw):
    """Map an entity code/name to LAWTON/MGT/ATACAMA, or None if unmapped.
    The account is accepted in ANY format — dotted (00041.00-7), plain digits
    (00041007), or embedded in a longer field — by matching the account's digit
    key as a substring of the row value's digits (each 8-digit account is unique
    enough that this can't collide with a client code)."""
    s = (raw or '').strip()
    if not s:
        return None
    digits = ''.join(ch for ch in s if ch.isdigit())
    for code, name in _FCST_ENTITY_MAP.items():
        if code in digits:
            return name
    up = s.upper()
    for nm in _FCST_ENTITY_ORDER:
        if nm in up:
            return nm
    return None


def _fcst_option_product(code):
    """Map an option's Código SISBACEN da Moeda Base → product (Alteryx Replace).
    220 → FX (FXO), COM → Commodities, INI → Equities. Falls back to FXO so an
    option is never dropped just because the classifier column couldn't be read."""
    c = (code or '').upper()
    if 'COM' in c or 'MERCAD' in c:
        return 'Option Commodities'
    if 'INI' in c or 'EQU' in c or 'ACAO' in c or 'AÇÃO' in c:
        return 'Option Equities'
    return 'Option FXO'   # 220 / câmbio / unmapped → FX options (default, never None)


def _fcst_ndf_product(asset_class):
    """NDF Moeda vs NDF Commodities from the asset-class field (Alteryx Replace:
    TAXAS DE CAMBIO → Moeda, COMMODITIES → Commodities)."""
    c = (asset_class or '').upper()
    if 'COMMOD' in c or 'MERCAD' in c:
        return 'NDF Commodities'
    return 'NDF Moeda'


def _fcst_opt_class_product(asset_class):
    """Option product from the OPC "Classe do Ativo Subjacente" (coluna N):
    TAXA DE CAMBIO → FXO, Commodities → Comm, everything else → EDG."""
    c = (asset_class or '').upper()
    if 'CAMB' in c or 'MOEDA' in c:
        return 'Option FXO'
    if 'COMMOD' in c or 'MERCAD' in c:
        return 'Option Commodities'
    return 'Option EDG'


def _fcst_lob(identifier):
    """SWAP line of business from the "Código Identificador" string, or None when
    the identifier carries no recognizable token.
    Order matters: hybrid is tested BEFORE CEM/EDG, because a hybrid's identifier
    also contains 'CEM' (e.g. 'CEMHYB', 'CEM-HIB') — testing 'CEM' first would
    swallow every hybrid into CEM and leave SWAP CEMHYB at zero.
    Accent-insensitive and tolerant of PT/EN hybrid spellings: the mock uses the
    English 'CEMHYB'/'HYB', but real B3 identifiers may use the Portuguese
    'HÍBRIDO'/'HIB'. Returns None (rather than defaulting to CEMHYB) when nothing
    matches, so callers can leave the row UNCLASSIFIED instead of mislabeling it —
    e.g. a premium whose contract has no match in the position file. Mirrors
    _accrual_lob (same field), which also returns None for the unmatched case."""
    s = _fcst_norm(identifier)   # lower-case + accent-stripped
    if 'cemhyb' in s or 'hib' in s:
        return 'CEMHYB'
    if 'edg' in s:
        return 'EDG'
    if 'cem' in s:
        return 'CEM'
    return None


def _forecast_spine(anchor=None, count=None):
    """The forecast column spine: the next `count` (default FORECAST_BIZDAYS)
    ANBIMA business days starting TODAY (inclusive), skipping weekends/holidays."""
    from apps.pages import routes
    count = count or FORECAST_BIZDAYS
    start = datetime.now().date()
    days, d = [], start
    while len(days) < count:
        if routes._pcx_is_bizday(d):
            days.append(d)
        d += timedelta(days=1)
    return days


def _fcst_norm(s):
    """Lower-case + strip accents, so an ascii token like 'liquidacao do premio'
    matches a 'Liquidação do Prêmio' column header."""
    s = unicodedata.normalize('NFKD', (s or '').lower())
    return ''.join(c for c in s if not unicodedata.combining(c))


def _fcst_resolve_key(keys, tokens):
    """Resolve a column by name (tokens in priority order, accent- and
    case-insensitive). An EXACT name match wins over a substring match, so
    'data de vencimento' resolves to the column literally named "Data de
    Vencimento" even when a longer "Data de Vencimento Antecipado" is present."""
    low = [(k, _fcst_norm(k)) for k in keys]
    for tok in tokens:                     # 1) exact match, priority order
        tnorm = _fcst_norm(tok)
        for k, kl in low:
            if kl == tnorm:
                return k
    for tok in tokens:                     # 2) substring fallback, priority order
        tnorm = _fcst_norm(tok)
        for k, kl in low:
            if tnorm in kl:
                return k
    return None


def _fcst_norm_contract(v):
    """Normalize a contract code for the premium↔position join (strip, drop a
    numeric '.0' tail so 12345.0 and 12345 match)."""
    s = str(v or '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s


def _swap_contract_ident_map(dref):
    """Map {Contrato → Código Identificador} from the DPOSICAO-SWAP file.
    DAGENDAPREMIOS carries only the contract code (no "Código Identificador"),
    so its premium rows recover the LOB by joining the contract code here and
    running _fcst_lob on the matched identifier. Empty dict when the position
    file is missing/unreadable or lacks the two columns."""
    from apps.pages import routes
    path = os.path.join(routes.B3_JSON_ROOT, 'Swap', routes._b3_date_subpath(dref),
                        '73760_{}_DPOSICAO-SWAP.json'.format(dref))
    out = {}
    if not os.path.isfile(path):
        return out
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            rows = json.load(fh)
    except Exception:
        log.warning("[forecast] could not read swap position for ident map:\n%s",
                    traceback.format_exc())
        return out
    if not rows:
        return out
    keys = list(rows[0].keys())
    contrato_key = _fcst_resolve_key(keys, ['contrato'])
    ident_key = _fcst_resolve_key(keys, ['código identificador', 'codigo identificador',
                                         'identificador'])
    if not contrato_key or not ident_key:
        log.warning("[forecast] swap ident map: contrato=%r ident=%r (one missing)",
                    contrato_key, ident_key)
        return out
    for r in rows:
        ck = _fcst_norm_contract(r.get(contrato_key, ''))
        iv = str(r.get(ident_key, '') or '').strip()
        if ck and iv:
            out.setdefault(ck, iv)
    return out


def _swap_contract_cpty_map(dref):
    """Map {Codigo do Contrato → Contraparte} from the DPOSICAO-SWAP position file
    (the Swap Characteristics source). Used to enrich the Swap Premium page and the
    Settlement Forecast premium entity breakdown, which only carry the contract
    code, not the counterparty. Reads positional (real 120+ field file) with a
    name-resolve fallback for the sparse dev mock. Contrato=idx 2, Contraparte=idx
    7 in _SWAPCHAR_LABELS."""
    from apps.pages import routes
    path = os.path.join(routes.B3_JSON_ROOT, 'Swap', routes._b3_date_subpath(dref),
                        '73760_{}_DPOSICAO-SWAP.json'.format(dref))
    out = {}
    if not os.path.isfile(path):
        return out
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            rows = json.load(fh)
    except Exception:
        return out
    if not rows:
        return out
    keys = list(rows[0].keys())
    contrato_key = _fcst_resolve_key(keys, ['codigo do contrato', 'código do contrato', 'contrato'])
    cpty_key = _fcst_resolve_key(keys, ['contraparte'])
    for r in rows:
        vals = list(r.values())
        full = len(vals) >= 120
        contrato = (vals[2] if len(vals) > 2 else '') if full else (r.get(contrato_key, '') if contrato_key else '')
        cpty = (vals[7] if len(vals) > 7 else '') if full else (r.get(cpty_key, '') if cpty_key else '')
        ck = _fcst_norm_contract(contrato)
        if ck:
            out.setdefault(ck, str(cpty or '').strip())
    return out


def _forecast_collect(dref, spine):
    """Read every JSON source and tally counts into by_product / by_entity
    matrices aligned with the business-day spine. Returns (by_product, by_entity,
    status[])."""
    from apps.pages import routes
    spine_index = {d: i for i, d in enumerate(spine)}
    n = len(spine)
    by_product, by_entity = {}, {}
    # {Contrato → Código Identificador} so premium-agenda rows (which lack the
    # identifier column) can be classified by joining on the contract code.
    swap_ident_by_contract = _swap_contract_ident_map(dref)
    # {Contrato → Contraparte} for sources (swap premium) whose intragroup entity
    # must be recovered by joining the contract code to the position file.
    swap_cpty_by_contract = _swap_contract_cpty_map(dref)
    status = []
    for src in _FORECAST_SOURCES:
        path = os.path.join(routes.B3_JSON_ROOT, src['category'], routes._b3_date_subpath(dref), src['file'](dref))
        st = {'label': src['label'], 'file': os.path.basename(path),
              'found': False, 'records': 0, 'counted': 0}
        if not os.path.isfile(path):
            status.append(st)
            continue
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                rows = json.load(fh)
        except Exception:
            log.warning("[forecast] could not read %s:\n%s", path, traceback.format_exc())
            status.append(st)
            continue
        st['found'] = True
        st['records'] = len(rows)
        if not rows:
            status.append(st)
            continue

        keys = list(rows[0].keys())
        date_key = _fcst_resolve_key(keys, src['date'])
        # Primary date fallback to a fixed column index if the header name could
        # not be resolved (e.g. Agenda Prêmios premium settlement = col F).
        if date_key is None and src.get('date_index') is not None:
            di = src['date_index']
            if 0 <= di < len(keys):
                date_key = keys[di]
        # Optional second date column (e.g. options also count on the premium
        # settlement date). Resolve by name, then fall back to a fixed column
        # index if the header name could not be found.
        date2_key = _fcst_resolve_key(keys, src['date2']) if src.get('date2') else None
        if date2_key is None and src.get('date2_index') is not None:
            i2 = src['date2_index']
            if 0 <= i2 < len(keys):
                date2_key = keys[i2]
        ent_key = _fcst_resolve_key(keys, src['entity'])
        pmode, pspec = src['product']
        prod_key = (_fcst_resolve_key(keys, pspec)
                    if pmode in ('sisbacen', 'lob', 'ndfclass', 'optclass', 'lob_join') else None)

        # Optional row gate: only count rows whose value in a given column is in
        # an allowed set (e.g. SWAP Position counts only "Tipo de Contrato" = 2).
        cw = src.get('count_where')
        cw_key = _fcst_resolve_key(keys, cw[0]) if cw else None
        cw_allowed = cw[1] if cw else None
        if cw and cw_key is None:
            log.warning("[forecast] %s: count_where column %r not found; counting all rows",
                        src['label'], cw[0])

        counted = 0
        for row in rows:
            if cw_key is not None:
                cwv = str(row.get(cw_key, '') or '').strip()
                if cwv.endswith('.0'):       # numeric read as 2.0 → '2'
                    cwv = cwv[:-2]
                if cwv.isdigit():            # leading zeros: '02' → '2', '01' → '1'
                    cwv = str(int(cwv))
                if cwv not in cw_allowed:
                    continue
            # Business-day slots this row counts on: the primary date plus an
            # optional second date (e.g. options count on both maturity AND
            # premium settlement). Dedup so a single row counts at most once per
            # day even when both dates land on the same business day.
            slots = set()
            d = _fcst_parse_date(row.get(date_key, '')) if date_key else None
            if d in spine_index:
                slots.add(spine_index[d])
            if date2_key is not None:
                d2 = _fcst_parse_date(row.get(date2_key, ''))
                if d2 in spine_index:
                    slots.add(spine_index[d2])
            if not slots:
                continue
            if pmode == 'fixed':
                product = pspec
            elif pmode == 'lob':
                lob = _fcst_lob(row.get(prod_key, '') if prod_key else '')
                product = ('SWAP ' + lob) if lob else None
            elif pmode == 'lob_join':
                # No identifier column: join the contract code to the swap
                # position map to recover the "Código Identificador", then LOB it.
                cc = _fcst_norm_contract(row.get(prod_key, '') if prod_key else '')
                lob = _fcst_lob(swap_ident_by_contract.get(cc, ''))
                product = ('SWAP ' + lob) if lob else None
            elif pmode == 'ndfclass':
                product = _fcst_ndf_product(row.get(prod_key, '') if prod_key else '')
            elif pmode == 'optclass':
                product = _fcst_opt_class_product(row.get(prod_key, '') if prod_key else '')
            else:
                product = _fcst_option_product(row.get(prod_key, '') if prod_key else '')
            # Unclassifiable swap (no LOB token / no position match): leave it
            # UNCOUNTED — better no classification than a wrong one. Drop from both
            # product and entity tallies so the totals stay consistent.
            if pmode in ('lob', 'lob_join') and product is None:
                continue
            if src.get('entity_join') == 'cpty':
                # Recover the counterparty by joining the contract code (prod_key
                # holds it for lob_join) to the DPOSICAO-SWAP position map.
                _cc = _fcst_norm_contract(row.get(prod_key, '') if prod_key else '')
                ent = _fcst_map_entity(swap_cpty_by_contract.get(_cc, ''))
            else:
                ent = _fcst_map_entity(row.get(ent_key, '')) if ent_key else None
            for di in slots:
                if product:
                    by_product.setdefault(product, [0] * n)[di] += 1
                if ent:
                    by_entity.setdefault(ent, [0] * n)[di] += 1
            counted += 1
        st['counted'] = counted
        st['date_field'] = date_key
        st['date2_field'] = date2_key
        st['entity_field'] = ent_key
        st['product_field'] = prod_key
        st['columns'] = keys
        st['count_where_field'] = cw_key
        status.append(st)
        log.info("[forecast] %s: %d rows, %d counted | date=%r date2=%r entity=%r product=%r%s",
                 src['label'], len(rows), counted, date_key, date2_key, ent_key, prod_key,
                 (' where=%r in %r' % (cw_key, sorted(cw_allowed))) if cw else '')
    return by_product, by_entity, status


def _forecast_matrix(mapping, order):
    """Ordered list of {label, values[], total} rows (known order first)."""
    ordered = [k for k in order if k in mapping] + [k for k in mapping if k not in order]
    return [{'label': k, 'values': mapping[k], 'total': sum(mapping[k])} for k in ordered]


def _forecast_payload(ref, days=None):
    """Compute the full forecast payload for a reference date."""
    dref = ref.strftime('%y%m%d')
    spine = _forecast_spine(ref, count=days)
    by_product, by_entity, status = _forecast_collect(dref, spine)
    # Keep the standard product set stable: a product with no settlements in the
    # window (e.g. SWAP CEMHYB) must still render as a 0 series, not disappear.
    for k in _FCST_PRODUCT_ORDER:
        by_product.setdefault(k, [0] * len(spine))
    product_rows = _forecast_matrix(by_product, _FCST_PRODUCT_ORDER)
    entity_rows = _forecast_matrix(by_entity, _FCST_ENTITY_ORDER)
    col_tot = [sum(r['values'][i] for r in product_rows) for i in range(len(spine))]
    return {
        'ref_date': ref.strftime('%Y-%m-%d'),
        'ref_date_fmt': ref.strftime('%d/%m/%Y'),
        'days': len(spine),
        'date_labels': [d.strftime('%d/%m') for d in spine],
        'date_full': [d.strftime('%d/%m/%Y') for d in spine],
        'products': product_rows,
        'entities': entity_rows,
        'col_totals': col_tot,
        'grand_total': sum(col_tot),
        'sources': status,
    }


def _forecast_has_files(ref):
    """True if at least one source JSON exists for this reference date."""
    from apps.pages import routes
    dref = ref.strftime('%y%m%d')
    for src in _FORECAST_SOURCES:
        if os.path.isfile(os.path.join(routes.B3_JSON_ROOT, src['category'], routes._b3_date_subpath(dref), src['file'](dref))):
            return True
    return False


@_req_cached
def _forecast_latest_ref(max_back=10):
    """Walk back from D-1 ANBIMA until a date with saved B3 JSONs is found.

    `@_req_cached`: a sondagem custa até 10 dias × 5 fontes de `isfile` NO
    SHARE (~50 idas à rede) só para responder "qual é a última posição" — e o
    dashboard e o Other Products perguntam a cada load. O cache por request +
    5 s cobre o refresh/polling; arquivo novo aparece no request seguinte ao
    TTL, que para uma sonda de existência não muda decisão nenhuma.
    Returns that date, or None if none exist within `max_back` business days.
    Used by the dashboard chart, which should show the latest available data;
    the Control Panel run instead requires D-1 strictly."""
    from apps.pages import routes
    ref = routes._prev_anbima_bizday(datetime.now())
    for _ in range(max_back):
        if _forecast_has_files(ref):
            return ref
        ref = routes._prev_anbima_bizday(ref)
    return None
