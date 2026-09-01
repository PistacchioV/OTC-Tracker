# -*- coding: utf-8 -*-
"""O motor do New Deals — os caches de deal das quatro páginas (Opt
Commodities, Opt FXO, NDF Commodities e as genéricas FWD Start/Other
Publisher), os dois pulls da Athena com seus schedulers, a regra de Amend
(§7: econômico vs cosmético, `Sent`/`Success` protegidos), a resolução de
contraparte por accronym (§7), a perna fraca (§7), o espelho Lawton (§7) e a
geração TER (`_generic_ndf_ter_line`/`_ndf_comm_ter_lines`).

Movido VERBATIM do `routes.py` (fase platform/ — CLAUDE.md §10). É horizontal:
as 44 rotas da casca `features/new_deals` chamam isto por `_R()`, o box scan
persiste por aqui, e o `_generic_nd_pc_trigger` alimenta o Pending
Confirmation (que dispara a esteira).

O `routes.py` mantém os nomes como ALIAS. **Ficam no `routes` de propósito**:
os caminhos de cache (`NEW_DEALS_CACHE_ROOT`, `NDF_COMM_CACHE_DIR`,
`OPT_FXO_CACHE_DIR`, `CACHE_BASE_DIR`, `B3_JSON_ROOT` — superfícies de patch
dos testes), o `_fxo_refdata_by_spn` e o par `_GENERIC_ND_PRODUCTS`/
`_generic_nd_cfg` — patchados pelos testes E chamados por dentro da fatia,
então só interceptam todos os caminhos morando no routes (lição do §316). O
`_nd_token` também não veio: é helper de NOTIFICAÇÃO (o Accrual o usa). O
ESTADO dos schedulers (`*_scheduler_started`, rebindado) mora AQUI.
"""
import json
import logging
import os
import random
import re
import threading
import time
import traceback
from datetime import datetime, timedelta

from apps.pages import otc_boxparse
from apps.pages.data_paths import data_path
from apps.pages.request_cache import once_per_request

log = logging.getLogger('otc_tracker')


@once_per_request
def _optcomm_file_list():
    """A listagem `(caminho, mtime, tamanho)` dos arquivos-dia do Opt
    Commodities, UMA vez por request. Os endpoints de bulk (delete, patch,
    Mapping B3) chamam o finder uma vez por LINHA selecionada, e cada chamada
    refazia o `os.walk` da árvore inteira NO SHARE — 50 linhas × ~500 dias era
    o request de minutos sem erro nenhum (§7 do CLAUDE.md, a classe do "um
    stat por linha"). Fora de um request o decorator não memoiza e o
    comportamento é o de sempre."""
    from apps.pages import routes
    return [(fp, mt, sz) for fp, _fn, mt, sz in
            routes._day_files(routes.CACHE_BASE_DIR, '_optcomm.json')]


@once_per_request
def _optfxo_file_list():
    from apps.pages import routes
    return [(fp, mt, sz) for fp, _fn, mt, sz in
            routes._day_files(routes.OPT_FXO_CACHE_DIR, '_optfxo.json')]

def _ndf_ter_path(ref, max_back=10, exact=False):
    """Newest existing DPOSICAO-TER (path, dref) walking back from `ref` (D-1 ANBIMA).

    `exact=True` NÃO anda para trás: devolve o arquivo daquele dia ou nada. É o
    que o Advanced Export pede — num intervalo, a busca para trás faria todo dia
    sem arquivo devolver o do dia anterior, e a planilha sairia com o mesmo dia
    repetido carimbado com datas diferentes."""
    from apps.pages import routes
    cur = ref
    for _ in range(1 if exact else max_back):
        dref = cur.strftime('%y%m%d')
        p = os.path.join(routes.B3_JSON_ROOT, 'NDF', routes._b3_date_subpath(dref),
                         '73760_{}_DPOSICAO-TER.json'.format(dref))
        if os.path.isfile(p):
            return p, dref
        cur = routes._prev_anbima_bizday(cur)
    return None, None

def _find_deal_in_cache(deal_name, client_name=None):
    """Search all YYYYMMDD_optcomm.json files for a deal by Deal + Client.
    Returns (file_path, list_index) or (None, None).

    A leitura vai pelo `_day_json` (o memo por mtime/tamanho do daycache) e a
    listagem pelo `_optcomm_file_list` (uma por request): antes cada chamada
    abria TODO arquivo da árvore com `open()` cru — e os bulks chamam isto por
    linha. O índice devolvido continua sendo o do arquivo: quem grava reabre o
    arquivo fresco sob o `_cache_lock`, e as escritas desses laços são
    in-place (não removem nem reordenam), então uma listagem do começo do
    request segue apontando para o par certo."""
    from apps.pages import routes
    files_scanned     = 0
    deal_name_matches = []   # Deal matched but Client didn't

    for fpath, mtime, size in reversed(_optcomm_file_list()):   # newest first
        fname = os.path.basename(fpath)
        files_scanned += 1
        try:
            deals = routes._day_json(fpath, mtime, size)
            for i, deal in enumerate(deals):
                d_name   = (deal.get('Deal')   or '').strip()
                d_client = (deal.get('Client') or '').strip()
                if d_name == deal_name.strip():
                    want = (client_name or '').strip()
                    if not want or d_client == want:
                        log.debug("[_find_opt] FOUND %r client=%r → %s[%d]",
                                  deal_name, client_name, fname, i)
                        return fpath, i
                    else:
                        deal_name_matches.append({
                            'file': fname, 'idx': i,
                            'stored_client': repr(d_client),
                            'wanted_client': repr(want)
                        })
        except Exception:
            log.warning("[_find_opt] Error reading %s: %s", fpath, traceback.format_exc())
            continue

    if deal_name_matches:
        log.warning(
            "[_find_opt] CLIENT MISMATCH for deal=%r  wanted_client=%r\n"
            "  Matches by name (stored vs wanted): %s",
            deal_name, repr(client_name), deal_name_matches
        )
    elif files_scanned == 0:
        log.error("[_find_opt] No _optcomm.json files found in %s", routes.CACHE_BASE_DIR)
    else:
        log.warning("[_find_opt] deal=%r client=%r NOT FOUND in %d file(s)",
                    deal_name, client_name, files_scanned)
    return None, None


def _nd_fix_underlying_marker(deal):
    """Tira do UnderlyingAsset um `"MY"` que tenha sobrado do padrão do cadastro.

    O código chega pronto do navegador. Um cliente com o `otc-fileupload.js`
    ANTERIOR ao §164 em cache trata o padrão como prefixo literal e concatena o
    mês/ano no fim — `HO"MY"` vira `HO"MY"U6` em vez de `HOU6`, e o deal entra
    com um Underlying Asset que não existe no Subjacente ("Missing Index B3").
    Foi o que aconteceu em 03/08/2026 (§170).

    A guarda fica na GRAVAÇÃO, não na leitura: corrigir só na tela deixaria o
    arquivo — que é o que alimenta o Conecta e o registro na B3 — com o código
    torto. O aviso no log é o que identifica a máquina com o JS velho.
    """
    if not isinstance(deal, dict):
        return
    ua = deal.get('UnderlyingAsset')
    if not isinstance(ua, str) or '"' not in ua:
        return
    fixed = otc_boxparse.strip_b3_marker(ua)
    if fixed != ua:
        deal['UnderlyingAsset'] = fixed
        log.warning('[new-deals] UnderlyingAsset com marcador de padrão: %r → %r '
                    '(deal=%r · cliente com JS antigo em cache?)',
                    ua, fixed, deal.get('Deal', ''))

def _deal_matches(deal, filters):
    """Return True when a deal dict satisfies every filter.

    Date filters support a `mode` of 'from' (cell >= value), 'to'
    (cell <= value) or 'exact'/absent (equality, both bounds inclusive when a
    'from'+'to' pair is supplied for the same field).
    """
    from apps.pages import routes
    for f in filters:
        field = f.get('field', '')
        ftype = f.get('type', 'text')
        value = str(f.get('value', '')).strip()
        if not field or not value:
            continue
        cell_val = str(deal.get(field, '')).strip()
        if ftype == 'text':
            # mode 'not' = "different from" (case-insensitive equality, negated) —
            # used by the New Deals default chip Status <> Success.
            if (f.get('mode') or '').lower() == 'not':
                if value.lower() == cell_val.lower():
                    return False
            elif value.lower() not in cell_val.lower():
                return False
        elif ftype == 'date':
            mode = (f.get('mode') or 'exact').lower()
            fval = routes._parse_date_any(value)
            cval = routes._parse_date_any(cell_val)
            if mode in ('from', 'to'):
                # Range bound — both the filter value and the cell must parse
                if fval is None or cval is None:
                    return False
                if mode == 'from' and cval < fval:
                    return False
                if mode == 'to' and cval > fval:
                    return False
            else:
                # Exact: compare as dates when both parse, else fall back to
                # substring so partial inputs (e.g. "06/2026") still work
                if fval is not None and cval is not None:
                    if cval != fval:
                        return False
                elif value not in cell_val:
                    return False
        elif ftype == 'number':
            if value.replace(',', '') not in cell_val.replace(',', ''):
                return False
    return True

# ==============================================================================
# API — OPT FXO CACHE (mesma lógica que opt-commodities, arquivo _optfxo.json)
# CRUD + bulk only. mapping-b3 / send-conecta / premium / econ-affirmation e o
# import do blotter XLSX (Brazil_FXO_Blotter_Extended_*_YYYYMMDD.xlsx) são
# product-specific e serão implementados quando o mapeamento de colunas chegar.
# ==============================================================================
def _find_fxo(deal_name, client_name=None):
    """Search all YYYYMMDD_optfxo.json files for a deal by Deal + Client.
    Returns (file_path, list_index) or (None, None). Mesma mecânica (e mesma
    razão) do `_find_deal_in_cache` acima: listagem uma vez por request,
    leitura pelo memo do daycache."""
    from apps.pages import routes
    for fpath, mtime, size in reversed(_optfxo_file_list()):   # newest first
        try:
            deals = routes._day_json(fpath, mtime, size)
            for i, deal in enumerate(deals):
                d_name   = (deal.get('Deal')   or '').strip()
                d_client = (deal.get('Client') or '').strip()
                if deal_name and d_name == deal_name.strip():
                    want = (client_name or '').strip()
                    if not want or d_client == want:
                        return fpath, i
        except Exception:
            continue
    return None, None


# ──────────────────────────────────────────────────────────────────────────
# OPT FXO — XLSX blotter import (Brazil_FXO_Blotter_Extended_*_YYYYMMDD.xlsx)
# ──────────────────────────────────────────────────────────────────────────
# Internal 3-letter currency codes (feed) → ISO. Extend as new codes appear.
_FXO_MONTHS_EN = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                  'August', 'September', 'October', 'November', 'December']


def _fxo_ccy(code):
    """Código de moeda da Athena → ISO. O de-para vem da tela Mapping (aba
    Currency Codes); código não cadastrado passa como veio."""
    from apps.pages import routes
    c = str(code or '').strip().upper()
    return routes._mapping_ccy_maps()[0].get(c, c)


def _fxo_num(v):
    """Parse a blotter number (native float, or BR '1.234,56' / US '1234.56') → float|None."""
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    neg = s.startswith('-')
    s = s.lstrip('+-').replace(' ', '')
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')   # BR: dot=thousands, comma=decimal
    elif ',' in s:
        s = s.replace(',', '.')                     # comma decimal
    try:
        val = float(s)
        return -val if neg else val
    except ValueError:
        return None


def _fxo_date_dmy(v):
    """yyyy-mm-dd / datetime / date → dd/mm/yyyy; blank/other → ''."""
    if v is None or v == '':
        return ''
    if hasattr(v, 'strftime'):
        return v.strftime('%d/%m/%Y')
    s = str(v).strip().split('T')[0].split(' ')[0]
    if not s:
        return ''
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%d/%m/%Y')
        except ValueError:
            continue
    return s

def _fxo_refdata_by_accronym(refmap_spn=None):
    """FX CASH ACCRONYM (upper) → registro do Reference Data. Deriva do índice
    por SPN já carregado (sem reler o arquivo) quando ele é passado. É o índice
    que resolve a contraparte pelo código, e não pelo SPN — necessário para as
    pernas internas, cujo SPN é de book e não está no Reference Data."""
    from apps.pages import routes
    out = {}
    for rec in (refmap_spn if refmap_spn is not None else routes._fxo_refdata_by_spn()).values():
        a = str(rec.get('FX CASH ACCRONYM', '') or '').strip().upper()
        if a and a not in out:
            out[a] = rec
    return out


# Canonical field order = the New Deals Opt-FXO table column order (same order the
# XLSX import builds each dict). Persisted _optfxo.json must follow this, not the
# alphabetical order some legacy writes produced. Maker/Checker are kept last.
_FXO_FIELD_ORDER = (
    'Status', 'Deal', 'B3_ID', 'TradeDate', 'Month', 'SettlementDate',
    'SPN', 'Acronym', 'Client', 'TaxID', 'TradeType', 'UnderlyingAsset',
    'FXHolidaySchedule', 'TotalNotional', 'Instrument', 'Strike',
    'StrikeCurrency', 'Direction', 'Premium', 'PremiumPerUnit', 'PremiumCCY',
    'SpotDate', 'FixingStartDate', 'FixingEndDate', 'TradingBook', 'OtherBook',
)


def _fxo_order_deal(d):
    """Return a new dict with keys in table-column order so the persisted
    _optfxo.json is column-ordered (not alphabetical). Known columns come first
    in canonical order, then any extra keys (e.g. _fdate) in their existing
    order, and Maker/Checker always last (matching the previous convention)."""
    if not isinstance(d, dict):
        return d
    tail = ('Maker', 'Checker')
    ordered = {}
    for k in _FXO_FIELD_ORDER:
        if k in d:
            ordered[k] = d[k]
    for k, v in d.items():
        if k not in ordered and k not in tail:
            ordered[k] = v
    for k in tail:
        if k in d:
            ordered[k] = d[k]
    return ordered


def _fxo_deal_from_row(get, sid, refmap, refmap_acr=None):
    """Build one Opt-FXO deal dict from a source row. `get(NAME)` returns the
    value of the normalized-uppercase column NAME — the XLSX blotter headers
    and the Athena API field names normalize to the same keys, so both sources
    share this builder (same drop filters, same derivations).
    Returns None when the row must be skipped."""
    PUT_CALL = {'PUT': 'Option (Put)', 'CALL': 'Option (Call)'}

    # Drop rows with empty End Counterparty / Description / SPN
    end_cp = str(get('END COUNTERPARTY') or '').strip()
    if end_cp == '':
        return None
    if str(get('END COUNTERPARTY DESCRIPTION') or '').strip() == '':
        return None
    if str(get('SPN') or '').strip() == '':
        return None

    # B3 does not accept underscores in the deal id on file registration —
    # replace '_' with '-' at the source (applies to Deal, dedup, Conecta).
    deal_name = str(get('DEAL NAME') or '').strip().replace('_', '-')
    if not deal_name:
        return None

    spn = str(get('SPN') or '').strip()
    if spn.endswith('.0'):
        spn = spn[:-2]
    # A contraparte é procurada pelo ACCRONYM DA CONTRAPARTE — o End Counterparty
    # —, depois pela identidade da entidade quando ele é perna interna, e só então
    # pelo SPN da API (que passou a trazer o SPN da contraparte, §174).
    #
    # O Settlement Location NÃO entra aqui: ele diz respeito à nossa perna, não à
    # contraparte, então usá-lo para achar a contraparte casaria a linha errada.
    # É por isso que só `_ndf_le_from_accronym(end_cp)` alimenta o passo da LE —
    # ele existe para perna interna, cujo End Counterparty é nome de book JPM.
    if refmap_acr is None:
        refmap_acr = _fxo_refdata_by_accronym(refmap)
    le_cp = _ndf_le_from_accronym(end_cp)
    ref = _ndf_ref_by_accronym(refmap_acr, end_cp, le_cp, refmap, spn)
    # SPN da tela: o do Reference Data quando a contraparte foi resolvida; o da
    # API só enquanto não há cadastro nenhum a que recorrer.
    spn = str(ref.get('SPN', '') or '').strip() or spn

    strike_v = _fxo_num(get('STRIKE'))
    premq_v  = _fxo_num(get('PREMIUM QUANTITY'))
    qty_v    = _fxo_num(get('QUANTITY'))
    ppu_v    = (premq_v / qty_v) if (premq_v is not None and qty_v not in (None, 0)) else None

    first_fix = get('FIRST FIXING DATE')
    last_fix  = get('LAST FIXING DATE')
    if str(first_fix or '').strip() and str(last_fix or '').strip():
        trade_type, fix_start, fix_end = 'ASIAN', _fxo_date_dmy(first_fix), _fxo_date_dmy(last_fix)
    else:
        exp = _fxo_date_dmy(get('EXPIRATION DATE'))
        trade_type, fix_start, fix_end = 'VANILLA', exp, exp

    trade_date = _fxo_date_dmy(get('TRADE DATE'))
    try:
        month = _FXO_MONTHS_EN[datetime.strptime(trade_date, '%d/%m/%Y').month - 1] if trade_date else ''
    except ValueError:
        month = ''

    direction = str(get('TYPE') or '').strip().upper()
    strike_ccy = _fxo_ccy(get('QUANTITY CURRENCY'))  # FXO: Underlying Asset == Strike Currency

    return {
        'Status':            'New',
        'Deal':              deal_name,
        'B3_ID':             '',
        'TradeDate':         trade_date,
        'Month':             month,
        'SettlementDate':    _fxo_date_dmy(get('SETTLEMENT DATE')),
        'SPN':               spn,
        # Sem cadastro no Reference Data a coluna fica com o código cru da API
        # (mesma regra do NDF). Além de não esconder a informação, é o que dá ao
        # badge "Missing Counterparty" da tela o que consultar: ele só limpa a
        # marcação de perna interna quando há um accronym na célula para procurar
        # no mapping Legal Entity × Accronym.
        #
        # PERNA INTERNA mantém o accronym que veio da API: a contraparte foi
        # resolvida pela razão social da entidade, e trocar 'LM-FWDECOMBRR FXC'
        # por 'JPMORGANBM' apagaria da tela o book que a operação realmente tem
        # (§174).
        'Acronym':           end_cp if le_cp else ((ref.get('FX CASH ACCRONYM', '') or '') or end_cp),
        'Client':            ref.get('COUNTERPARTY', '') or '',
        'TaxID':             ref.get('TAX ID', '') or '',
        'TradeType':         trade_type,
        'UnderlyingAsset':   strike_ccy,
        'FXHolidaySchedule': 'ANBIMA',
        'TotalNotional':     ('{:,.2f}'.format(qty_v) if qty_v is not None else ''),
        'Instrument':        PUT_CALL.get(str(get('OPTION TYPE') or '').strip().upper(), ''),
        'Strike':            ('{:.6f}'.format(strike_v) if strike_v is not None else ''),
        'StrikeCurrency':    strike_ccy,
        'Direction':         direction,
        'Premium':           ('{:,.2f}'.format(premq_v) if premq_v is not None else ''),
        'PremiumPerUnit':    ('{:,.8f}'.format(ppu_v) if ppu_v is not None else ''),
        'PremiumCCY':        _fxo_ccy(get('PREMIUM CCY')),
        'SpotDate':          _fxo_date_dmy(get('PREMIUM DATE')),
        'FixingStartDate':   fix_start,
        'FixingEndDate':     fix_end,
        'TradingBook':       str(get('TRADING BOOK') or '').strip(),
        'OtherBook':         str(get('OTHER BOOK') or '').strip(),
        'Maker':             sid,
    }


def _fxo_persist_deals(deals):
    """Upsert FXO deals into per-TradeDate _optfxo.json by Deal+Client. Returns count."""
    from apps.pages import routes
    by_file = {}
    for d in deals:
        try:
            ref_date = datetime.strptime(d.get('TradeDate', ''), '%d/%m/%Y')
        except (ValueError, TypeError):
            ref_date = datetime.now()
        dir_path = os.path.join(routes.OPT_FXO_CACHE_DIR, ref_date.strftime('%Y'), ref_date.strftime('%m'))
        fpath = os.path.join(dir_path, ref_date.strftime('%Y%m%d') + '_optfxo.json')
        by_file.setdefault(fpath, (dir_path, []))[1].append(d)

    saved = 0
    with routes._cache_lock:
        for fpath, (dir_path, ds) in by_file.items():
            os.makedirs(dir_path, exist_ok=True)
            try:
                with open(fpath, encoding='utf-8') as fh:
                    existing = json.load(fh)
                if not isinstance(existing, list):
                    existing = [existing]
            except (IOError, json.JSONDecodeError):
                existing = []
            for d in ds:
                idx = next((i for i, e in enumerate(existing)
                            if (e.get('Deal') or '').strip() == (d.get('Deal') or '').strip()
                            and (e.get('Client') or '').strip() == (d.get('Client') or '').strip()), None)
                if idx is not None:
                    existing[idx] = _fxo_order_deal(d)
                else:
                    existing.append(_fxo_order_deal(d))
                saved += 1
            routes._atomic_write_json(fpath, existing)
    return saved


# ──────────────────────────────────────────────────────────────────────────
# OPT FXO — Athena getTrades API import (manual button + 10-min scheduler)
# ──────────────────────────────────────────────────────────────────────────
# The API returns the same columns as the XLSX blotter, so the rows go through
# the same _fxo_deal_from_row filters/derivations. Unlike the XLSX flow, the
# API pull NEVER overwrites an existing Deal+Client — a deal already in the day
# file may have been worked (Approved/Sent) and a 10-min poll must not reset it.

# Campos que NUNCA entram na comparação de amend: Status/B3_ID/Maker/Checker
# são do fluxo da página; SPN/Client/TaxID vêm do RefData (o re-enriquecimento
# os altera sem a operação ter mudado); AmendChanged é o próprio marcador.
# Campos que o amend da API NÃO toca: são nossos, não da API. Status e B3 ID são
# do fluxo de registro, Maker/Checker de quem operou, AmendChanged é o próprio
# registro do amend.
#
# SPN, Client e Tax ID **saíram desta lista** (§176). Eles ficavam de fora porque
# são enriquecimento nosso (Reference Data) e não campo da API — só que isso
# congelava a contraparte na primeira importação: operação rebookada para outro
# cliente ficava para sempre com o nome antigo na tela, e a linha que veio sem
# contraparte nunca ganhava a que passou a resolver. Agora são comparados como
# qualquer outro campo; o que os protege de derrubar um Success para Amend é
# `_nd_amend_is_economic`, que olha o ACCRONYM.
_ND_AMEND_SKIP = {'Status', 'B3_ID', 'Maker', 'Checker', 'AmendChanged'}

# Campos que mudam o DADO mas não o NEGÓCIO: a célula é destacada como qualquer
# outra, mas quem já está Success não volta para a fila por causa deles. Os dois
# books são onde a operação está pendurada dentro do banco — a contraparte, o
# valor e o prazo do negócio não mudam quando ela troca de book. É uma lista
# curta de propósito: o default é econômico, porque um campo em que ninguém
# pensou aparecendo como Amend custa uma revisão, e o contrário custa uma
# operação registrada errada.
_ND_AMEND_COSMETIC = {'OtherBook', 'TradingBook'}

# A mesma ideia, mas quando o campo só é cosmético em UM produto. A chave é a do
# `_GENERIC_ND_PRODUCTS`.
#
# **NDF FWD Start × Strike**: o que a B3 registra é o **Strike Set Offset** — o
# spread sobre a taxa que só será conhecida no dia do fixing. O Strike da linha é
# a projeção daquela taxa no momento do booking, e a Athena a recalcula a cada
# pull: a operação não mudou, mudou o mercado. Sem esta exceção, todo FWD Start
# já registrado voltava sozinho para a fila de Amend, e a mesa reconferia um
# registro que continuava certo. A célula segue destacada (o campo entra em
# `AmendChanged` como qualquer outro); o que não regride é o status.
_ND_AMEND_COSMETIC_BY_PRODUCT = {'fwd-start': {'Strike'}}

# Os status em que a operação JÁ SAIU DA MESA, e por isso só um dado ECONÔMICO
# a devolve para a fila de Amend. `Sent` é o arquivo de registro enviado à B3 e
# `Success` é o retorno com o B3 ID — nos dois casos a operação está registrada
# (ou a caminho), e o trabalho de conferir já foi feito por alguém.
#
# O `Sent` estava de fora, e era um buraco por onde passava exatamente o que a
# regra do `Success` existe para evitar: a Athena troca o Other Book, ou o
# Reference Data passa a resolver o accronym de uma perna interna, e a operação
# que a mesa acabou de mandar para a B3 voltava sozinha para `Amend` — sem
# Checker, fora da lista de enviadas, e reconferida à toa. E o `Sent` vem ANTES
# do `Success`, então a janela em que isso acontecia era justamente a de espera
# do retorno da B3.
#
# O que NÃO muda: mudança econômica derruba os dois do mesmo jeito, e a célula
# segue destacada (`AmendChanged`) em qualquer um dos casos — o que não regride
# é o status.
_ND_AMEND_KEEP_STATUS = {'Success', 'Sent'}


def _nd_amend_entity(acr):
    """Entidade de um accronym FX Cash. Duas fontes, nessa ordem: a LE cadastrada
    no mapping le-accronym e, quando o código não está cadastrado, o sufixo
    depois do último hífen — é assim que a API sufixa o End Counterparty
    ('CMBB-LAW' → 'LAW'), o mesmo corte que _ndf_accronym_variants usa. Sem
    nenhum dos dois devolve '' (entidade desconhecida)."""
    le = _ndf_le_from_accronym(acr)
    if le:
        return le
    a = str(acr or '').strip().upper()
    return a.rsplit('-', 1)[-1].strip() if '-' in a else ''


def _nd_amend_same_entity(old, new, stored, incoming):
    """Dois accronyms são da MESMA entidade (JPM→JPM, MGT→MGT, LAW→LAW)?
    Trocar o código dentro da entidade é registro; trocar de entidade muda a
    ponta do negócio.

    Quando o produto carrega a coluna LE (os três NDFs), ela é a resposta: é
    derivada do accronym e da settlement location, e é justamente a entidade.
    O FXO não tem essa coluna, e aí a entidade sai do próprio accronym.
    Entidade desconhecida nunca empata — dois códigos que ninguém sabe de onde
    vêm podem ser de entidades diferentes, e o seguro é tratar como econômico."""
    le_old = str(stored.get('LE', '') or '').strip().upper()
    le_new = str(incoming.get('LE', '') or '').strip().upper()
    if le_old or le_new:
        return bool(le_old) and le_old == le_new
    ent_old, ent_new = _nd_amend_entity(old), _nd_amend_entity(new)
    return bool(ent_old) and ent_old == ent_new


def _nd_amend_flat(v):
    return str(v or '').strip()


def _nd_amend_is_economic(field, old, new, stored, incoming, product=''):
    """A mudança desse campo justifica derrubar um deal já Success para Amend?

    `product` é a chave do `_GENERIC_ND_PRODUCTS` quando quem chama sabe de que
    página o deal veio — é o que permite um campo ser cosmético em UM produto
    (ver `_ND_AMEND_COSMETIC_BY_PRODUCT`). Vazio significa "não sei", e aí só a
    lista geral vale: o default é econômico, porque um campo esquecido virando
    Amend custa uma revisão e o contrário custa uma operação registrada errada.
    """
    if field in _ND_AMEND_COSMETIC:
        return False
    if field in _ND_AMEND_COSMETIC_BY_PRODUCT.get(product, ()):
        return False
    if field in ('SPN', 'Client', 'TaxID'):
        # Os três são DERIVADOS da contraparte, e a contraparte é o accronym
        # (nunca o SPN nem a settlement location — §147/§148). Com o accronym
        # igual, mudou a nossa resolução e não o negócio: é o caso de §174, em
        # que a perna interna passou a achar SPN/Client/Tax ID que antes vinham
        # vazios. Destaca a célula, mantém o Success. Mudando o accronym, vale a
        # mesma régua dele: só é econômico se trocou de entidade.
        acr_old = _nd_amend_flat(stored.get('Acronym')).upper()
        acr_new = _nd_amend_flat(incoming.get('Acronym')).upper()
        if acr_old == acr_new:
            return False
        return not _nd_amend_same_entity(acr_old, acr_new, stored, incoming)
    if field == 'Acronym':
        # Accronym aparecendo onde a célula estava VAZIA, com o SPN da operação
        # intacto, é enriquecimento nosso que melhorou — a contraparte sempre foi
        # a mesma, ninguém rebookou nada. Sem esta exceção, passar a preencher o
        # accronym das pernas internas no FXO devolveria para a fila, de uma vez,
        # todo deal interno que já estava Success. A célula ainda é destacada;
        # só o status é que não regride.
        if not old and _nd_amend_flat(stored.get('SPN')) == _nd_amend_flat(incoming.get('SPN')):
            return False
        return not _nd_amend_same_entity(old, new, stored, incoming)
    return True


def _nd_api_amend(stored, incoming, product=''):
    """Bate um deal já importado com a versão atual da API. Campo de dado
    diferente → aplica o valor novo e registra o nome do campo em AmendChanged
    (o front destaca as células). Deal já Canceled não é reaberto. Retorna a
    lista de campos alterados.

    Status: a mudança normalmente joga o deal para 'Amend'. A exceção é quem já
    saiu da mesa — **Sent** e **Success** (`_ND_AMEND_KEEP_STATUS`) —, que só cai
    para Amend quando alguma informação **econômica** mudou (contraparte/
    entidade, vencimento, notional, strike, compra × venda, put × call, prêmio,
    data de pagamento do prêmio…). Mexer só no Other Book, ou trocar o accronym
    dentro da mesma entidade, destaca a célula e mantém o status: são detalhes de
    booking, e devolver para a fila uma operação já enviada à B3 gera retrabalho
    à toa."""
    if str(stored.get('Status', '') or '').strip() == 'Canceled':
        return []
    registrado = str(stored.get('Status', '') or '').strip() in _ND_AMEND_KEEP_STATUS
    # Foto do deal ANTES de qualquer escrita: o loop já gravou os campos
    # anteriores em `stored`, então perguntar a ele "a LE mudou?" no meio do
    # caminho responderia sempre que não.
    before = dict(stored)
    changed, economic = [], False
    for k, v in incoming.items():
        if k in _ND_AMEND_SKIP:
            continue
        old = str(stored.get(k, '') or '').strip()
        new = str(v or '').strip()
        if old != new:
            stored[k] = v
            changed.append(k)
            if _nd_amend_is_economic(k, old, new, before, incoming, product):
                economic = True
    if changed:
        if economic or not registrado:
            stored['Status'] = 'Amend'
        prev = stored.get('AmendChanged') or []
        stored['AmendChanged'] = sorted(set(prev) | set(changed))
    return changed


def _nd_amend_index(existing):
    """Índices de um arquivo do dia para o amend da API: por (Deal, Client) e por
    Deal. O segundo existe porque o Client PODE mudar — ver `_nd_amend_find`."""
    idx, by_deal = {}, {}
    for e in existing:
        if not isinstance(e, dict):
            continue
        deal = (e.get('Deal') or '').strip()
        idx[(deal, (e.get('Client') or '').strip())] = e
        by_deal.setdefault(deal, []).append(e)
    return idx, by_deal


def _nd_amend_find(st, deal):
    """Linha já gravada correspondente a este deal da API, ou None.

    A chave normal é **Deal + Client**. Quando o Client muda — a operação foi
    rebookada para outra contraparte, ou a nossa resolução passou a achar o nome
    que antes vinha vazio (§174) — essa chave não casa, e o deal entrava como
    LINHA NOVA: a operação aparecia duas vezes, a antiga com a contraparte velha,
    e nenhuma das duas marcada como Amend.

    Por isso, sem match pela chave, procura-se **pelo Deal ID**. Só quando ele é
    único no arquivo: o mesmo Deal pode ter duas pernas gravadas (é o que o
    cancelamento por Deal já trata), e aí não há como saber qual delas a API está
    amendando — nesse caso o deal entra como novo, que é o comportamento antigo e
    deixa a decisão para o operador."""
    key = ((deal.get('Deal') or '').strip(), (deal.get('Client') or '').strip())
    row = st['idx'].get(key)
    if row is not None:
        return row
    same = st['by_deal'].get((deal.get('Deal') or '').strip()) or []
    return same[0] if len(same) == 1 else None


def _nd_amend_register(st, deal):
    """Grava o deal recém-inserido nos dois índices, para o mesmo pull não o
    inserir de novo (nem pela chave, nem pelo Deal)."""
    d = (deal.get('Deal') or '').strip()
    st['idx'][(d, (deal.get('Client') or '').strip())] = deal
    st['by_deal'].setdefault(d, []).append(deal)


def _nd_cancel_in_file(fpath, deal_name):
    """Cancelamento vindo da API: **apaga** as linhas desse Deal no arquivo do
    dia. A operação deixou de existir na origem, então mantê-la na tela é
    convidar alguém a registrar na B3 um negócio que não existe mais.

    A ÚNICA exceção é o deal que **já foi registrado na B3** (Status Success
    **com** B3 ID): esse existe lá fora e o cancelamento exige ação humana na
    B3. Apagar a linha esconderia essa pendência, então ele só vira
    Status='Canceled' e continua visível (badge escuro). Success sem B3 ID não
    chegou a ser registrado — é apagado como os demais.

    Retorna (removidas, marcadas_canceled)."""
    from apps.pages import routes
    if not deal_name or not os.path.isfile(fpath):
        return 0, 0
    with routes._cache_lock:
        try:
            with open(fpath, encoding='utf-8') as fh:
                deals = json.load(fh)
            if not isinstance(deals, list):
                deals = [deals]
        except (IOError, json.JSONDecodeError):
            return 0, 0
        kept, removed, marked = [], 0, 0
        for dd in deals:
            if not isinstance(dd, dict) or (dd.get('Deal') or '').strip() != deal_name:
                kept.append(dd)
                continue
            status = (dd.get('Status') or '').strip()
            if status == 'Canceled':                       # já tratado num pull anterior
                kept.append(dd)
                continue
            if status == 'Success' and str(dd.get('B3_ID') or '').strip():
                dd['Status'] = 'Canceled'                  # registrado na B3 → fica à vista
                kept.append(dd)
                marked += 1
                continue
            removed += 1                                   # nunca registrado → sai da tabela
        if removed or marked:
            routes._atomic_write_json(fpath, kept)
        return removed, marked


def _fxo_persist_new_deals(deals):
    """Insert deals whose Deal+Client is new; existing ones are compared with
    the incoming API data — any difference applies the new values, flips the
    Status to Amend and records AmendChanged. Returns (inserted, amended_names)."""
    from apps.pages import routes
    fresh, amended, seen_files = [], [], {}
    with routes._cache_lock:
        for d in deals:
            try:
                ref_date = datetime.strptime(d.get('TradeDate', ''), '%d/%m/%Y')
            except (ValueError, TypeError):
                ref_date = datetime.now()
            fpath = os.path.join(routes.OPT_FXO_CACHE_DIR, ref_date.strftime('%Y'), ref_date.strftime('%m'),
                                 ref_date.strftime('%Y%m%d') + '_optfxo.json')
            if fpath not in seen_files:
                existing = []
                try:
                    with open(fpath, encoding='utf-8') as fh:
                        existing = json.load(fh)
                    if not isinstance(existing, list):
                        existing = [existing]
                except (IOError, json.JSONDecodeError):
                    existing = []
                idx, by_deal = _nd_amend_index(existing)
                seen_files[fpath] = {'existing': existing, 'idx': idx,
                                     'by_deal': by_deal, 'dirty': False}
            st = seen_files[fpath]
            row = _nd_amend_find(st, d)
            if row is not None:
                if _nd_api_amend(row, d):
                    amended.append(d.get('Deal') or '')
                    st['dirty'] = True
                continue
            _nd_amend_register(st, d)           # dedup within the same pull too
            fresh.append(d)
        for fpath, st in seen_files.items():
            if st['dirty']:
                routes._atomic_write_json(fpath, st['existing'])
    if fresh:
        _fxo_persist_deals(fresh)
    return fresh, amended


def _fxo_deals_from_api_records(records, sid):
    """Athena getTrades records → (deal dicts, cancelados). Cancelados são os
    registros com isCancelled = true: (Deal, TradeDate dd/mm/yyyy) para marcar
    Status='Canceled' no cache quando o deal já tiver sido importado. isDead não
    conta como cancelamento — ver `_api_rec_is_cancelled` (§173)."""
    from apps.pages import routes
    refmap = routes._fxo_refdata_by_spn()
    refmap_acr = _fxo_refdata_by_accronym(refmap)
    deals, cancelled = [], []
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        norm = {}
        for k, v in rec.items():
            n = re.sub(r'[\s_]+', ' ', str(k or '').strip().upper())
            if n and n not in norm:
                norm[n] = v
        if _api_rec_is_cancelled(norm):
            nm = str(norm.get('DEAL NAME') or '').strip().replace('_', '-')
            if nm:
                cancelled.append((nm, _fxo_date_dmy(norm.get('TRADE DATE'))))
            continue
        deal = _fxo_deal_from_row(norm.get, sid, refmap, refmap_acr)
        if deal:
            deals.append(deal)
    return deals, cancelled

def _fxo_api_pull(sid='API', actor_name='Athena API', ref_date=None):
    """Fetch the reference date's FXO trades from the Athena API and insert the
    new ones. Shared by the manual Import button (which sends the Reference Date
    field, default today) and the hourly scheduler (always today). Raises on
    network/SSO errors — callers decide how loud to be about it."""
    from apps.pages import routes
    from apps.pages import athena_api
    if not athena_api.is_available():
        raise RuntimeError("The 'requests' package is not installed; "
                           "the Athena API client is unavailable.")
    ref_dt = routes._api_ref_date(ref_date)
    date = ref_dt.strftime('%Y%m%d')
    payload = athena_api.fetch_fxo_trades(date)
    records = athena_api.extract_records(payload)
    deals, cancelled = _fxo_deals_from_api_records(records, sid)
    inserted, amended = _fxo_persist_new_deals(deals)
    # isCancelled na API → a linha SAI do arquivo do dia (a operação não existe
    # mais). Só quem já foi registrado na B3 fica, como 'Canceled'.
    removed = canceled = 0
    for nm, td in cancelled:
        try:
            rd = datetime.strptime(td, '%d/%m/%Y') if td else ref_dt
        except ValueError:
            rd = ref_dt
        r, c = _nd_cancel_in_file(
            os.path.join(routes.OPT_FXO_CACHE_DIR, rd.strftime('%Y'), rd.strftime('%m'),
                         rd.strftime('%Y%m%d') + '_optfxo.json'), nm)
        removed += r
        canceled += c
    if inserted or amended or removed or canceled:
        bits = []
        if inserted:
            bits.append('{} imported'.format(len(inserted)))
        if amended:
            bits.append('{} amended'.format(len(amended)))
        if removed:
            bits.append('{} removed (cancelled)'.format(removed))
        if canceled:
            bits.append('{} canceled'.format(canceled))
        routes._create_notification(sid, actor_name, 'New Deals', 'Opt FXO',
                             'Athena API{}: {} deal(s)'.format(routes._api_ref_suffix(ref_dt),
                                                              ', '.join(bits)))
    # Mesma prestação de contas do pull de NDF: "veio 0" tem de dizer se a API
    # devolveu nada ou se os registros foram descartados, e por quê.
    log.info('[opt-fxo] pull ref=%s: %d fetched · %d parseados · importados=%d '
             'amendados=%d · cancelados na API=%d (linhas removidas=%d, '
             'marcadas Canceled por já terem B3 ID=%d)',
             date, len(records), len(deals), len(inserted), len(amended),
             len(cancelled), removed, canceled)
    return {'success': True, 'date': date, 'fetched': len(records),
            'parsed': len(deals), 'imported': len(inserted),
            'amended': len(amended), 'canceled': canceled, 'removed': removed,
            # chave 'dead' mantida: é o que as 4 telas leem para o resumo do
            # import. O conteúdo é só isCancelled desde §173.
            'dead': len(cancelled), 'deals': inserted}


# In-app scheduler — polls the Athena FXO API every FXO_API_POLL_MIN minutes
# (default 60) with trade date = today. Same self-contained pattern as the
# pending-confirmation daily scheduler. Off the JPM network every poll fails;
# repeats of the same error are demoted to debug so the log stays readable.
_FXO_API_POLL_MIN = int(os.getenv('FXO_API_POLL_MIN', '60') or 60)
_fxo_api_scheduler_started = False
_fxo_api_scheduler_lock = threading.Lock()


def _fxo_api_scheduler_loop():
    from apps.pages import routes
    last_err = None
    while True:
        time.sleep(max(60, _FXO_API_POLL_MIN * 60))
        if not routes._import_window_open():
            continue                    # fora do horário da mesa — `_import_window_open`
        try:
            res = _fxo_api_pull()
            if res.get('imported'):
                log.info('[opt-fxo] Athena API poll: %d new deal(s) imported '
                         '(%d fetched)', res['imported'], res['fetched'])
            last_err = None
        except Exception as e:                          # noqa: BLE001
            msg = str(e)
            if msg != last_err:
                log.warning('[opt-fxo] Athena API poll failed: %s', msg)
            else:
                log.debug('[opt-fxo] Athena API poll failed again: %s', msg)
            last_err = msg


def _fxo_api_start_scheduler():
    from apps.pages import routes
    global _fxo_api_scheduler_started
    from apps.pages import athena_api
    if not athena_api.is_available():
        log.info('[opt-fxo] Athena API scheduler NOT started (requests missing)')
        return
    with _fxo_api_scheduler_lock:
        if _fxo_api_scheduler_started:
            return
        _fxo_api_scheduler_started = True
    threading.Thread(target=_fxo_api_scheduler_loop,
                     name='fxo-athena-api-scheduler', daemon=True).start()
    log.info('[opt-fxo] Athena API scheduler started (every %d min · janela %s BRT)',
             _FXO_API_POLL_MIN, routes._import_window_label())

def _ndf_api_norm(rec):
    """Normalize an API record's keys the same way the XLSX headers are
    normalized (underscores/spaces → single space, uppercase)."""
    norm = {}
    for k, v in rec.items():
        n = re.sub(r'[\s_]+', ' ', str(k or '').strip().upper())
        if n and n not in norm:
            norm[n] = v
    return norm


def _ndf_api_get(norm, *names):
    """First non-empty value among alternative normalized field names."""
    for n in names:
        v = norm.get(n)
        if v not in (None, ''):
            return v
    return None


def _api_rec_is_cancelled(norm):
    """True só para os registros com **isCancelled = true** na API.

    `isDead` NÃO entra: até 04/08/2026 os dois flags eram tratados igual e um
    trade marcado isDead simplesmente não era importado — mas isDead é estado
    interno da Athena (o registro deixou de ser a versão viva do trade), e não
    "a operação não existe". Quem cancela uma operação é o isCancelled; o resto
    tem que ser puxado. §173
    """
    for k in ('ISCANCELLED', 'IS CANCELLED'):
        v = norm.get(k)
        if v is True or str(v).strip().lower() == 'true':
            return True
    return False


def _ndf_flat(s):
    """Só letras e números, em maiúsculas — o nome do book casa independente de
    espaço e hífen ("BR ON - LN LAWTON NDF" ≡ "BR ON-LN LAWTON NDF")."""
    return re.sub(r'[^A-Z0-9]', '', str(s or '').upper())

# O `upgrade` do cadastro da recon de FXO mora no `recon_fxo`, e não aqui, pelo
# mesmo motivo do cadastro da esteira: quem lê aquele arquivo a cada run é o
# motor da recon, e enquanto o upgrade vivesse só nesta tela ele veria o JSON
# cru — a coluna nova não existiria para quem nunca abriu o /mapping.
def _fxo_internal_cpty_upgrade(rows):
    # Import preguiçoso, como os demais usos do `recon_fxo` aqui: aquele módulo
    # carrega o pandas, e a tela de /mapping não é motivo para arrastá-lo para a
    # subida do app.
    from apps.pages import recon_fxo as _rf
    return _rf.internal_cpty_upgrade(rows)


def _fxo_book_disregard_upgrade(rows):
    from apps.pages import recon_fxo as _rf
    return _rf.book_disregard_upgrade(rows)

def _ndf_weak_leg(qty_ccy, other_ccy):
    """A moeda FRACA do par, quando existe uma — é ela que manda inverter o
    strike, e é ela que diz com quantas casas o 1/taxa vai para o arquivo.

    A convenção é do PAR, não da COLUNA. A API manda o strike da moeda fraca
    como moeda/BRL (3,33 MXN por real) e a aplicação inteira trabalha com
    R$/moeda — e qual das duas pernas carrega o notional depende de como a mesa
    bookou, não da moeda. Testar só a `Other Quantity Units` deixava passar sem
    inverter justamente a operação cotada NA moeda fraca: o BRL/CNH de
    19/08/2026 saiu com 1,29567245 no lugar de 0,77179965, e com ele o
    contravalor do MT300 e a taxa do arquivo Intrag, que leem o Rate como
    R$/moeda.

    Par com as DUAS pernas fracas não tem BRL para a convenção apontar — a
    inversão seria um chute, e a linha fica como a API mandou."""
    from apps.pages import routes
    weak = routes._mapping_ccy_maps()[1]
    pernas = [c for c in (str(qty_ccy or '').strip().upper(),
                          str(other_ccy or '').strip().upper()) if c in weak]
    return pernas[0] if len(pernas) == 1 else None


def _ndf_le_from_location(loc):
    """Settlement Location da API → Legal Entity da página (mapping le-accronym).
    None quando não há linha cadastrada para aquela location."""
    from apps.pages import routes
    l = str(loc or '').strip().upper()
    if not l:
        return None
    for r in routes._mapping_rows('le-accronym'):
        if str(r.get('SETTLEMENT LOCATION', '') or '').strip().upper() == l:
            return str(r.get('LE', '') or '').strip().upper() or None
    return None


def _ndf_le_from_accronym(acr):
    """LE cadastrada para esse End Counterparty na coluna ACCRONYM do mapping
    le-accronym. Casa o código exato e também o accronym base (o mesmo corte de
    _ndf_accronym_variants); a comparação é achatada por _ndf_flat, então espaço
    e hífen a mais no cadastro não impedem o match ('LM-FXECOMBRR JPMCBB FXC' ≡
    'LM FXECOMBRR JPMCBB FXC'). None quando não há linha."""
    from apps.pages import routes
    cands = {_ndf_flat(c) for c in _ndf_accronym_variants(acr)}
    cands.discard('')
    if not cands:
        return None
    for r in routes._mapping_rows('le-accronym'):
        a = _ndf_flat(r.get('ACCRONYM'))
        if a and a in cands:
            return str(r.get('LE', '') or '').strip().upper() or None
    return None


def _ndf_le_accronyms(le):
    """Códigos cadastrados para essa LE no mapping le-accronym (na ordem da
    tabela), mais o nome da própria LE no fim. É por aqui que a contraparte de
    uma perna interna é resolvida: cadastre para a LE tanto os códigos que a API
    manda (nomes de book, ex. 'LM-FXECOMBRR JPMCBB FXC') quanto o accronym da
    entidade no Reference Data (ex. 'JPMORGANBM', 'LAWTON') — o que existir no
    cadastro traz SPN/Client/Tax ID, e uma linha por entidade resolve todos os
    books dela."""
    from apps.pages import routes
    l = str(le or '').strip().upper()
    if not l:
        return []
    out = []
    for r in routes._mapping_rows('le-accronym'):
        if str(r.get('LE', '') or '').strip().upper() != l:
            continue
        a = str(r.get('ACCRONYM', '') or '').strip().upper()
        if a and a not in out:
            out.append(a)
    if l not in out:
        out.append(l)
    return out


def _ndf_accronym_variants(acr):
    """Códigos a tentar no Reference Data para um End Counterparty da API: o
    próprio e, quando ele vem sufixado por entidade, o accronym sem o último
    trecho depois do hífen ('CMBB-LAW' → 'CMBB'). É o que dispensa cadastrar a
    mesma contraparte uma vez por LE, sem precisar configurar sufixo nenhum."""
    a = str(acr or '').strip().upper()
    if not a:
        return []
    out = [a]
    base = a.rsplit('-', 1)[0].strip() if '-' in a else ''
    # Base curta demais provavelmente não é acronym de contraparte — não tenta.
    if len(base) >= 3 and base not in out:
        out.append(base)
    return out


def _ndf_le_row(le):
    """Linha do mapping le-spn dessa Legal Entity ({} quando não há)."""
    from apps.pages import routes
    l = str(le or '').strip().upper()
    if not l:
        return {}
    for r in routes._mapping_rows('le-spn'):
        if str(r.get('LE', '') or '').strip().upper() == l:
            return r
    return {}

def _ndf_le_refdata(le, refmap_acr, refmap_spn=None):
    """Contraparte de uma PERNA INTERNA (o End Counterparty é a própria entidade
    JPM), nesta ordem:

      1. **razão social** cadastrada para a LE em le-spn, procurada no Reference
         Data pelo nome normalizado — é o passo que faltava: book interno não tem
         accronym no Reference Data, então antes disto a linha ficava com SPN,
         Client e Tax ID vazios (§174);
      2. accronyms cadastrados para a LE em le-accronym (o que já funcionava);
      3. **SPN** cadastrado para a LE em le-spn: se ele existir no Reference Data
         devolve a linha inteira; se não, devolve só o SPN, para a coluna não
         ficar vazia quando é a única informação registrada.

    {} quando nada casa — e aí a tela marca Missing Counterparty, que é o pedido
    de cadastro, não uma contraparte inventada."""
    from apps.pages import routes
    row = _ndf_le_row(le)
    name = str(row.get('NAME', '') or '').strip()
    if name:
        rec = routes._refdata_by_name(refmap_spn).get(routes._pc_norm(name))
        if rec:
            return rec
    for cand in _ndf_le_accronyms(le):
        rec = refmap_acr.get(cand)
        if rec:
            return rec
    spn = str(row.get('SPN', '') or '').strip()
    if spn:
        if refmap_spn is None:
            refmap_spn = routes._fxo_refdata_by_spn()
        return refmap_spn.get(routes._norm_spn(spn)) or {'SPN': spn}
    return {}


def _ndf_ref_by_accronym(refmap_acr, acr, le=None, refmap_spn=None, api_spn=''):
    """Linha do Reference Data do End Counterparty, nesta ordem:

      1. código exato e accronym sem o sufixo da entidade;
      2. sendo perna interna (`le`), a identidade da entidade — razão social,
         accronyms cadastrados e SPN (ver `_ndf_le_refdata`);
      3. não sendo, o **SPN que veio da API**.

    {} quando nada casa.

    `le` tem de ser a entidade DA CONTRAPARTE (a que sai do accronym dela), nunca
    a que sai da Settlement Location, que é a nossa perna: com a location, um
    cliente sem accronym cadastrado era resolvido como a própria JPMorgan.

    O passo 3 é novo (§174): o campo SPN da API passou a trazer o SPN da
    contraparte — antes vinha o da Legal Entity, e usá-lo como chave era o mesmo
    erro do parágrafo acima por outro caminho. Ele fica por último de propósito,
    depois do accronym, que é a chave que a mesa cadastra."""
    from apps.pages import routes
    for cand in _ndf_accronym_variants(acr):
        rec = refmap_acr.get(cand)
        if rec:
            return rec
    if le:
        return _ndf_le_refdata(le, refmap_acr, refmap_spn)
    if api_spn:
        if refmap_spn is None:
            refmap_spn = routes._fxo_refdata_by_spn()
        return refmap_spn.get(routes._norm_spn(api_spn)) or {}
    return {}


def _ndf_api_key(name):
    """Nome de campo da tela → chave do registro normalizado (_ndf_api_norm)."""
    return re.sub(r'[\s_]+', ' ', str(name or '').strip().upper())


def _ndf_interbook_rules():
    """Regras do filtro interbook como (campo A, valor A, campo B, valor B), com
    valores já achatados por _ndf_flat. BOTH WAYS = YES gera também a linha com
    os valores trocados entre os dois campos."""
    from apps.pages import routes
    out = []
    for r in routes._mapping_rows('interbook-ndf'):
        fa, fb = _ndf_api_key(r.get('FIELD A')), _ndf_api_key(r.get('FIELD B'))
        va, vb = _ndf_flat(r.get('VALUE A')), _ndf_flat(r.get('VALUE B'))
        if not (fa and fb and va and vb):
            continue
        out.append((fa, va, fb, vb))
        if str(r.get('BOTH WAYS', '') or '').strip().upper() == 'YES':
            out.append((fa, vb, fb, va))
    return out

def _ndf_is_interbook(norm):
    """True quando o registro da API é uma perna interbook — pares cadastrados na
    tela Mapping (aba Interbook API). Predicado compartilhado: o mapeamento usa
    para descartar e o pull para contar, sem duplicar a regra."""
    for fa, va, fb, vb in _ndf_interbook_rules():
        if _ndf_flat(norm.get(fa)) == va and _ndf_flat(norm.get(fb)) == vb:
            return True
    return False


def _ndf_deal_from_api(rec, sid, refmap_acr, today_dmy, refmap_spn=None):
    """One Athena NDF getTrades record → (target_product, deal_dict).
    target_product is a _GENERIC_ND_PRODUCTS key; (None, None) = skip."""
    norm = _ndf_api_norm(rec)
    get = norm.get

    if _api_rec_is_cancelled(norm):
        return None, None
    deal_name = str(get('DEAL NAME') or '').strip().replace('_', '-')
    if not deal_name:
        return None, None
    end_cp = str(get('END COUNTERPARTY') or '').strip()
    if not end_cp:
        return None, None
    # Internal holding book — not a client trade, never imported
    if 'GLOBAL_HOLDING_BOOK' in end_cp.upper().replace(' ', '_').replace('-', '_'):
        return None, None
    # Interbook (Other Book × Settlement Location) — mesma natureza do holding
    # book acima: perna interna, não é negócio de cliente.
    if _ndf_is_interbook(norm):
        return None, None

    # LE da CONTRAPARTE: só quando o próprio End Counterparty está cadastrado no
    # mapping Legal Entity × Accronym, ou seja, quando a contraparte é uma perna
    # interna (outra entidade JPM). Fora esse caso ela é None — e tem de ser.
    loc = str(get('SETTLEMENT LOCATION') or '').strip().upper()
    le_cp = _ndf_le_from_accronym(end_cp)
    # LE da coluna da tela: a NOSSA perna. Cai para a Settlement Location, e sem
    # cadastro a location crua fica visível.
    le = le_cp or _ndf_le_from_location(loc) or loc

    # Contraparte, nesta ordem:
    #   1. accronym exato do End Counterparty no Reference Data (e o accronym
    #      sem o sufixo de entidade — evita cadastrar a mesma contraparte uma
    #      vez por LE);
    #   2. só então, e SOMENTE se a contraparte for perna interna (le_cp), os
    #      demais accronyms daquela entidade.
    #
    # O passo 2 recebe `le_cp`, NUNCA a LE da Settlement Location: a location é
    # a nossa perna, e usá-la aqui fazia um cliente virar a própria JPMorgan.
    # Foi o que aconteceu com SOMICHEL (Michelin): accronym não cadastrado +
    # Settlement Location BRAZIL → LE JPM → a linha veio com SPN, nome e CNPJ do
    # Banco J.P. Morgan, em silêncio, numa operação que vai para registro.
    #
    # Sendo perna interna, o passo 2 é a IDENTIDADE DA ENTIDADE (razão social
    # cadastrada em le-spn → Reference Data; depois accronyms; depois o SPN da
    # LE). Não sendo, entra o SPN que veio da API — que passou a trazer o SPN da
    # contraparte, e não mais o da Legal Entity (§174). Ele fica por último, e
    # nunca é consultado para perna interna, para não reintroduzir por outro
    # caminho o erro do parágrafo acima.
    #
    # Nada casando, SPN/Client/TaxID ficam vazios e a página marca "Missing
    # Counterparty" — que é o erro certo: pede cadastro em vez de inventar.
    ref = _ndf_ref_by_accronym(refmap_acr, end_cp, le_cp, refmap_spn,
                               str(get('SPN') or '').strip())
    spn = str(ref.get('SPN', '') or '').strip()

    first_fix = _fxo_date_dmy(get('FIRST FIXING DATE'))
    last_fix  = _fxo_date_dmy(_ndf_api_get(norm, 'LAST FIXING DATE') or get('EXPIRATION DATE'))
    # ASIAN only when there is an actual fixing window (first ≠ last). An empty
    # FIRST_FIXING_DATE (last falls back to Expiration Date) is a single fixing
    # → VANILLA.
    trade_type = 'ASIAN' if (first_fix and last_fix and first_fix != last_fix) else 'VANILLA'

    trade_date = _fxo_date_dmy(get('TRADE DATE'))
    try:
        month = _FXO_MONTHS_EN[datetime.strptime(trade_date, '%d/%m/%Y').month - 1] if trade_date else ''
    except ValueError:
        month = ''

    qty_ccy   = _fxo_ccy(get('QUANTITY CURRENCY'))
    other_ccy = _fxo_ccy(get('OTHER QUANTITY UNITS'))
    qty_v     = _fxo_num(get('QUANTITY'))
    strike_v  = _fxo_num(get('STRIKE'))
    # Moedas fracas cotam invertido vs BRL: a API manda o strike como
    # Moeda/BRL (ex.: 3,33 MXN por BRL) — a página e os arquivos (Conecta,
    # Intrag) trabalham com BRL por unidade da moeda (0,30...), então o Rate
    # é gravado já invertido quando o PAR tem uma moeda fraca (flag Weak Ccy
    # do cadastro Currency Base), em qualquer das duas pernas — ver
    # `_ndf_weak_leg`.
    if strike_v and _ndf_weak_leg(qty_ccy, other_ccy):
        strike_v = 1.0 / strike_v
    instr     = str(get('INSTRUMENT TYPE') or '').strip()
    publisher = str(get('PUBLISHER') or '').strip()
    # FX Pair comes with internal ccy codes ("USB/BRR") → ISO ("USD/BRL")
    fx_pair = re.sub(r'[A-Z]{3}', lambda m: _fxo_ccy(m.group(0)),
                     str(get('INSTRUMENT') or '').strip().upper())

    # Routing (order matters: FWD Start wins over the publisher test).
    # Vanilla × Other Publisher sai do CADASTRO, não de literal: a linha do
    # publisher em /mapping › Publisher × B3 (NDF) com NOTES = BACEN vai para
    # Vanilla; o resto (e publisher sem linha) vai para Other Publisher. Uma
    # linha sem Match Tokens casa só pelo texto completo, então 'PTAX' e
    # 'PTAX|BRR|PTAX' são cadastros distintos e independentes (§166).
    if 'FXFORWARDSTART' in instr.upper().replace(' ', ''):
        strike_set = _fxo_date_dmy(_ndf_api_get(norm, 'STRIKE SET DATE', 'STRIKESETDATE'))
        # Fixa hoje: será cancelada e re-bookada como vanilla, então não entra em
        # página nenhuma. Ainda assim o deal é MONTADO e devolvido no alvo
        # `_fwd-start-fixing` — é dele que sai a chave que reconhece o
        # re-booking do outro lado (ver _ndf_rebook_key).
        target = '_fwd-start-fixing' if (strike_set and strike_set == today_dmy) \
            else 'fwd-start'
    elif not _ndf_publisher_is_bacen(publisher):
        target = 'other-publishers'
    else:
        target = 'vanilla'

    deal = {
        'Status':            'New',
        'LE':                le,
        'Deal':              deal_name,
        'B3_ID':             '',
        'TradeDate':         trade_date,
        'Month':             month,
        'SettlementDate':    _fxo_date_dmy(get('SETTLEMENT DATE')),
        'SPN':               spn,
        # Perna interna mantém o accronym da API (o nome do book), §174.
        'Acronym':           end_cp if le_cp else ((ref.get('FX CASH ACCRONYM', '') or '') or end_cp),
        'Client':            ref.get('COUNTERPARTY', '') or '',
        'TaxID':             ref.get('TAX ID', '') or '',
        'FirstFixingDate':   first_fix,
        'LastFixingDate':    last_fix,
        'Instrument':        instr,
        'TradeType':         trade_type,
        'Direction':         str(get('TYPE') or '').strip().upper(),
        'FXPair':            fx_pair,
        'QuantityCurrency':  qty_ccy,
        'OtherQuantityCurrency': other_ccy,
        'Publisher':         publisher,
        'Notional':          ('{:,.2f}'.format(qty_v) if qty_v is not None else ''),
        'Rate':              ('{:,.8f}'.format(strike_v) if strike_v is not None else ''),
        'IsBRRFixed':        ('YES' if qty_ccy == 'BRL' else 'NO'),
        'TradingBook':       str(get('TRADING BOOK') or '').strip(),
        'OtherBook':         str(get('OTHER BOOK') or '').strip(),
        # `loc` é o SETTLEMENT LOCATION cru (upper) já lido para derivar a LE.
        'SettlementLocation': loc,
        'Maker':             sid,
    }
    if target in ('fwd-start', '_fwd-start-fixing'):
        deal['StrikeSetDate']   = _fxo_date_dmy(_ndf_api_get(norm, 'STRIKE SET DATE', 'STRIKESETDATE'))
        deal['StrikeSetOffset'] = str(_ndf_api_get(norm, 'STRIKE OFFSET', 'STRIKEOFFSET',
                                                   'STRIKE SET OFFSET') or '').strip()
        # Strike da API, na MESMA convenção do Rate (já invertido para moeda
        # fraca, acima): BRL por unidade da moeda base. É ele que converte o
        # notional no XML da confirmação, então divergir do Rate faria a coluna
        # da tela e o valor do arquivo contarem histórias diferentes.
        deal['Strike'] = ('{:,.8f}'.format(strike_v) if strike_v is not None else '')
        deal['Rate'] = ''       # FWD Start: strike is only set on the strike set date
    return target, deal


def _generic_nd_persist_new_deals(product, deals):
    """Insert deals whose Deal+Client is new in the product's day file; existing
    ones are compared with the incoming API data — any difference applies the
    new values, flips the Status to Amend and records AmendChanged (front
    highlight). Returns (inserted, amended_names)."""
    from apps.pages import routes
    cfg = routes._generic_nd_cfg(product)
    if not cfg:
        return [], []
    fresh, amended, seen_files = [], [], {}
    with routes._cache_lock:
        for d in deals:
            try:
                ref_date = datetime.strptime(d.get('TradeDate', ''), '%d/%m/%Y')
            except (ValueError, TypeError):
                ref_date = datetime.now()
            dir_path = os.path.join(cfg['dir'], ref_date.strftime('%Y'), ref_date.strftime('%m'))
            fpath = os.path.join(dir_path, ref_date.strftime('%Y%m%d') + cfg['suffix'])
            if fpath not in seen_files:
                existing = []
                try:
                    with open(fpath, encoding='utf-8') as fh:
                        existing = json.load(fh)
                    if not isinstance(existing, list):
                        existing = [existing]
                except (IOError, json.JSONDecodeError):
                    existing = []
                idx, by_deal = _nd_amend_index(existing)
                seen_files[fpath] = {'dir': dir_path, 'existing': existing,
                                     'idx': idx, 'by_deal': by_deal}
            st = seen_files[fpath]
            row = _nd_amend_find(st, d)
            if row is not None:
                if _nd_api_amend(row, d, product):
                    amended.append(d.get('Deal') or '')
                continue
            _nd_amend_register(st, d)
            st['existing'].append(d)
            fresh.append(d)
        for fpath, st in seen_files.items():
            os.makedirs(st['dir'], exist_ok=True)
            routes._atomic_write_json(fpath, st['existing'])
    return fresh, amended


# ──────────────────────────────────────────────────────────────────────────
# FWD Start → Vanilla: o re-booking do dia da fixação não entra no Vanilla
# ──────────────────────────────────────────────────────────────────────────
# No dia em que um FWD Start fixa (Strike Set Date), a mesa CANCELA a operação e
# faz um booking novo, com outro Deal ID, já como NDF vanilla. As duas pontas são
# a MESMA operação — importar o re-booking encheria a página de Vanilla de
# duplicatas que ninguém pediu, e o Deal ID novo faz com que nenhuma regra de
# chave (Deal+Client) as reconheça como par.
#
# O par é reconhecido por **contraparte + notional + data de vencimento**, com a
# **Trade Date do vanilla igual à Strike Set Date do FWD Start**. Strike e trade
# date NÃO entram na comparação: o strike é justamente o que a fixação define
# (o FWD Start nem tem strike gravado, ver `deal['Rate'] = ''` acima), e a data
# de negociação do re-booking é outra por construção.
#
# Os FWD Start comparados vêm de duas fontes, unidas:
#   1. o próprio pull — os registros roteados para `_fwd-start-fixing`, que a
#      regra de roteamento já tira de circulação;
#   2. o cache das páginas de FWD Start dos últimos meses, porque a operação foi
#      bookada semanas antes e mora no arquivo do dia DELA, não no de hoje.
# A (2) é o que salva quando a API não devolve mais o FWD Start original no dia
# da fixação; a (1) é o que salva quando ele nunca chegou a ser importado.

_NDF_REBOOK_LOOKBACK_MONTHS = 24


def _ndf_rebook_key(deal, when_field):
    """(contraparte, notional, vencimento, data) de uma operação — a chave que
    emparelha um FWD Start (`when_field='StrikeSetDate'`) com o vanilla que o
    substituiu (`when_field='TradeDate'`).

    Devolve None quando falta qualquer uma das quatro partes. Chave incompleta
    não casa com nada, e é o lado seguro: na dúvida o deal É importado e o
    operador decide — o contrário some com a operação sem ninguém ver."""
    from apps.pages import routes
    cp = str(deal.get('SPN') or '').strip() or str(deal.get('Acronym') or '').strip().upper()
    notional = routes._conf_to_float(deal.get('Notional'))
    settle = routes._parse_date_any(deal.get('SettlementDate'))
    when = routes._parse_date_any(deal.get(when_field))
    if not cp or notional is None or not settle or not when:
        return None
    # abs: a direção da operação viaja no campo Direction, não no sinal do
    # notional — e o re-booking pode gravar o sinal do outro jeito.
    return (cp, round(abs(notional), 2), settle, when)


def _ndf_fwdstart_cached_keys(ref):
    """Chaves dos FWD Start já importados que podem ter virado vanilla: varre o
    cache dos últimos _NDF_REBOOK_LOOKBACK_MONTHS meses. Cancelado entra também
    — pelo contrário, está cancelado justamente porque o re-booking aconteceu.

    A pasta é `NDF/FwdStart`, UMA grafia — a mesma do
    `_GENERIC_ND_PRODUCTS['fwd-start']['dir']`, que é quem grava. Havia aqui uma
    segunda leitura em `NDF/FWD Start` chamada de "a outra grafia em produção",
    e ela nunca existiu: o app grava em `FwdStart` desde o commit que criou a
    página. O que tem espaço é o RÓTULO (`_dash_product_label` traduz um no
    outro), e o caminho com espaço saiu de um exemplo errado num docstring —
    daí para três leitores e, na dev, para uma pasta de mock criada à mão."""
    from apps.pages import routes
    months, first = [], datetime(ref.year, ref.month, 1)
    for _ in range(_NDF_REBOOK_LOOKBACK_MONTHS):
        months.append(first)
        first = datetime(first.year, first.month, 1) - timedelta(days=1)
        first = datetime(first.year, first.month, 1)
    keys = {}
    for base in (os.path.join(routes.NEW_DEALS_CACHE_ROOT, 'NDF', 'FwdStart'),):
        for m in months:
            dpath = os.path.join(base, m.strftime('%Y'), m.strftime('%m'))
            if not os.path.isdir(dpath):
                continue
            try:
                fnames = os.listdir(dpath)
            except OSError:
                continue
            for fname in fnames:
                if not fname.endswith('_ndffwdstart.json'):
                    continue
                try:
                    with open(os.path.join(dpath, fname), encoding='utf-8') as fh:
                        data = json.load(fh)
                except (IOError, OSError, json.JSONDecodeError):
                    continue
                for e in (data if isinstance(data, list) else []):
                    if not isinstance(e, dict):
                        continue
                    k = _ndf_rebook_key(e, 'StrikeSetDate')
                    if k:
                        # A TRADE DATE do FWD Start vai junto: o Manual Deals EA
                        # precisa dela para tirar do e-mail o FWD Start que foi
                        # bookado e fixou no MESMO dia (ver `features/mdea/queries.rows`). Só o
                        # Deal ID não responde essa pergunta.
                        keys.setdefault(k, {'deal': str(e.get('Deal') or '').strip(),
                                            'trade': str(e.get('TradeDate') or '').strip()})
    return keys


def _ndf_drop_fwdstart_rebooks(vanilla_deals, fixing_deals, ref):
    """Tira da lista de vanilla os re-bookings de FWD Start que fixaram.

    Retorna (deals_que_ficam, [(deal_vanilla, info_do_fwdstart)]), com
    `info_do_fwdstart` = `{'deal', 'trade'}` — o Deal ID e a Trade Date do FWD
    Start original."""
    if not vanilla_deals:
        return vanilla_deals, []
    keys = _ndf_fwdstart_cached_keys(ref)
    for d in fixing_deals:
        k = _ndf_rebook_key(d, 'StrikeSetDate')
        if k:
            keys.setdefault(k, {'deal': str(d.get('Deal') or '').strip(),
                                'trade': str(d.get('TradeDate') or '').strip()})
    if not keys:
        return vanilla_deals, []
    kept, dropped = [], []
    for d in vanilla_deals:
        k = _ndf_rebook_key(d, 'TradeDate')
        if k is not None and k in keys:
            dropped.append((d, keys[k]))
        else:
            kept.append(d)
    return kept, dropped


def _ndf_api_pull(sid='API', actor_name='Athena API', ref_date=None):
    """Fetch the reference date's NDF trades from the Athena API and route/insert
    the new ones into FWD Start / Other Publisher / Vanilla. `ref_date` vem do
    campo Reference Date das páginas (default hoje); o scheduler nunca manda, ou
    seja, sempre puxa o dia. Raises on network/SSO errors — the caller decides
    how loud to be about it.
    ⚠️ `now` daqui para baixo é a DATA DE REFERÊNCIA, não o relógio: é ela que
    decide o arquivo do dia, a regra do Strike Set Date de hoje no FWD Start e o
    dia procurado nos cancelamentos."""
    from apps.pages import routes
    from apps.pages import athena_api
    if not athena_api.is_available():
        raise RuntimeError("The 'requests' package is not installed; "
                           "the Athena API client is unavailable.")
    now = routes._api_ref_date(ref_date)
    payload = athena_api.fetch_ndf_trades(now.strftime('%Y%m%d'))
    records = athena_api.extract_records(payload)

    refmap_spn = routes._fxo_refdata_by_spn()
    refmap_acr = _fxo_refdata_by_accronym(refmap_spn)
    today_dmy = now.strftime('%d/%m/%Y')
    routed = {'fwd-start': [], 'other-publishers': [], 'vanilla': []}
    fixing_today = []           # FWD Start que fixam hoje: índice do re-booking
    skipped_interbook, cancelled = 0, []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        target, deal = _ndf_deal_from_api(rec, sid, refmap_acr, today_dmy, refmap_spn)
        if target == '_fwd-start-fixing':
            fixing_today.append(deal)
            continue
        if target is None:
            norm = _ndf_api_norm(rec)
            if _api_rec_is_cancelled(norm):
                # isCancelled: se o deal já foi importado, vira Canceled
                nm = str(norm.get('DEAL NAME') or '').strip().replace('_', '-')
                if nm:
                    cancelled.append((nm, _fxo_date_dmy(norm.get('TRADE DATE'))))
                continue
            if _ndf_is_interbook(norm):
                skipped_interbook += 1
            continue
        routed[target].append(deal)
    skipped_fwd_today = len(fixing_today)

    # O re-booking do FWD Start que fixou hoje chega como vanilla, com Deal ID
    # novo — sai antes de qualquer gravação.
    routed['vanilla'], rebooks = _ndf_drop_fwdstart_rebooks(
        routed['vanilla'], fixing_today, now)
    for d, fwd in rebooks:
        log.info('[ndf-api] vanilla %s não importado: re-booking do FWD Start %s '
                 '(contraparte %s · notional %s · vencimento %s)',
                 d.get('Deal') or '?', (fwd or {}).get('deal') or '?', d.get('Acronym') or '?',
                 d.get('Notional') or '?', d.get('SettlementDate') or '?')
    # O par (vanilla ↔ FWD Start) é GRAVADO, e não só registrado no log. Ele é
    # calculado aqui — o único lugar que vê os dois lados — e some em seguida: o
    # vanilla não entra em arquivo-dia nenhum (é justamente o que esta função
    # evita) e o FWD Start original está no arquivo do dia em que foi bookado,
    # semanas atrás, sem o Deal ID novo. Quem precisa do par depois é o e-mail
    # Manual Deals EA — a vertical features/mdea. A platform NÃO importa
    # feature (fronteira da seção 10): quem conhece as verticais é a casca, e o
    # gancho `routes._mdea_record_rebooks` faz a travessia.
    routes._mdea_record_rebooks(rebooks, now)

    targets = {}
    for product, deals in routed.items():
        inserted, amended = _generic_nd_persist_new_deals(product, deals)
        cfg = routes._generic_nd_cfg(product)
        if (inserted or amended) and cfg:
            bits = []
            if inserted:
                bits.append('{} imported'.format(len(inserted)))
            if amended:
                bits.append('{} amended'.format(len(amended)))
            routes._create_notification(sid, actor_name, 'New Deals', cfg['label'],
                                 'Athena API{}: {} deal(s)'.format(routes._api_ref_suffix(now),
                                                                   ', '.join(bits)))
        targets[product] = {'parsed': len(deals), 'imported': len(inserted),
                            'amended': len(amended), 'deals': inserted}

    # Cancelamentos: procura o Deal no arquivo do dia (trade date do registro)
    # dos três produtos. A linha é APAGADA — a operação não existe mais na
    # origem. Exceção: já registrado na B3 (Success com B3 ID) vira 'Canceled'
    # e continua visível, porque o cancelamento na B3 é ação humana.
    removed = canceled = 0
    for nm, td in cancelled:
        try:
            rd = datetime.strptime(td, '%d/%m/%Y') if td else now
        except ValueError:
            rd = now
        for product in routed:
            cfg = routes._generic_nd_cfg(product)
            r, c = _nd_cancel_in_file(
                os.path.join(cfg['dir'], rd.strftime('%Y'), rd.strftime('%m'),
                             rd.strftime('%Y%m%d') + cfg['suffix']), nm)
            removed += r
            canceled += c
    # Prestação de contas do pull: sem isso, "veio 0" não diz se a API devolveu
    # nada, se tudo estava cancelado ou se o filtro de interbook comeu os
    # registros — os três somem no mesmo zero da tela.
    log.info('[ndf-api] pull ref=%s: %d fetched · roteados fwd=%d op=%d vanilla=%d · '
             'importados=%d amendados=%d · cancelados na API=%d (linhas removidas=%d, '
             'marcadas Canceled por já terem B3 ID=%d) · '
             'interbook=%d · strike set na data=%d · re-booking de FWD Start=%d',
             now.strftime('%Y%m%d'), len(records),
             len(routed['fwd-start']), len(routed['other-publishers']), len(routed['vanilla']),
             sum(t['imported'] for t in targets.values()),
             sum(t['amended'] for t in targets.values()),
             len(cancelled), removed, canceled, skipped_interbook, skipped_fwd_today, len(rebooks))
    return {'success': True, 'date': now.strftime('%Y%m%d'), 'fetched': len(records),
            'skipped_fwd_strike_today': skipped_fwd_today,
            'skipped_fwd_rebook': len(rebooks),
            'skipped_fwd_rebook_deals': [d.get('Deal') or '' for d, _f in rebooks],
            'skipped_interbook': skipped_interbook, 'canceled': canceled,
            # chave 'dead' mantida pelo contrato com as telas — só isCancelled
            # desde §173.
            'removed': removed, 'dead': len(cancelled), 'targets': targets}


# In-app scheduler — polls the Athena NDF API every NDF_API_POLL_MIN minutes
# (default 20) with trade date = today, routing into FWD Start / Other
# Publisher / Vanilla. Same pattern as the FXO scheduler above.
_NDF_API_POLL_MIN = int(os.getenv('NDF_API_POLL_MIN', '20') or 20)
_ndf_api_scheduler_started = False
_ndf_api_scheduler_lock = threading.Lock()


def _ndf_api_scheduler_loop():
    from apps.pages import routes
    last_err = None
    while True:
        time.sleep(max(60, _NDF_API_POLL_MIN * 60))
        if not routes._import_window_open():
            continue                    # fora do horário da mesa — `_import_window_open`
        try:
            res = _ndf_api_pull()
            imported = sum(t.get('imported', 0) for t in (res.get('targets') or {}).values())
            if imported:
                log.info('[ndf] Athena API poll: %d new deal(s) imported '
                         '(%d fetched)', imported, res['fetched'])
            last_err = None
        except Exception as e:                          # noqa: BLE001
            msg = str(e)
            if msg != last_err:
                log.warning('[ndf] Athena API poll failed: %s', msg)
            else:
                log.debug('[ndf] Athena API poll failed again: %s', msg)
            last_err = msg


def _ndf_api_start_scheduler():
    from apps.pages import routes
    global _ndf_api_scheduler_started
    from apps.pages import athena_api
    if not athena_api.is_available():
        log.info('[ndf] Athena API scheduler NOT started (requests missing)')
        return
    with _ndf_api_scheduler_lock:
        if _ndf_api_scheduler_started:
            return
        _ndf_api_scheduler_started = True
    threading.Thread(target=_ndf_api_scheduler_loop,
                     name='ndf-athena-api-scheduler', daemon=True).start()
    log.info('[ndf] Athena API scheduler started (every %d min · janela %s BRT)',
             _NDF_API_POLL_MIN, routes._import_window_label())

def _find_ndf_deal_in_cache(deal_name, client_name=None):
    """Search all YYYYMMDD_ndfcomm.json files for a deal by Deal + Client.
    Returns (file_path, list_index) or (None, None)."""
    from apps.pages import routes
    files_scanned     = 0
    deals_scanned     = 0
    deal_name_matches = []   # where Deal matched but Client didn't
    all_names_seen    = []   # sample of (fname, deal_name, client) for every deal scanned

    if not os.path.isdir(routes.NDF_COMM_CACHE_DIR):
        log.error("[_find_ndf] CACHE DIR MISSING: %s", routes.NDF_COMM_CACHE_DIR)
        return None, None

    for root, _dirs, files in os.walk(routes.NDF_COMM_CACHE_DIR):
        for fname in sorted(files):
            if not fname.endswith('_ndfcomm.json'):
                continue
            fpath = os.path.join(root, fname)
            files_scanned += 1
            try:
                with open(fpath, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
                for i, deal in enumerate(deals):
                    deals_scanned += 1
                    d_name   = deal.get('Deal', '')
                    d_client = deal.get('Client', '')
                    all_names_seen.append((fname, d_name, d_client))
                    # Trim-tolerant match: a stray leading/trailing space in the
                    # cache or in the request must not cause a phantom 404.
                    if (d_name or '').strip() == (deal_name or '').strip():
                        if client_name is None or (d_client or '').strip() == (client_name or '').strip():
                            log.debug("[_find_ndf] FOUND %r client=%r → %s[%d]",
                                      deal_name, client_name, fname, i)
                            return fpath, i
                        else:
                            deal_name_matches.append({
                                'file': fname, 'idx': i,
                                'stored_client': repr(d_client),
                                'wanted_client': repr(client_name)
                            })
            except Exception:
                log.warning("[_find_ndf] Error reading %s: %s", fpath, traceback.format_exc())
                continue

    # ── Not found — emit targeted diagnosis ──────────────────────────────
    if deal_name_matches:
        # Deal name exists in cache but client field doesn't match
        log.warning(
            "[_find_ndf] CLIENT MISMATCH for deal=%r  wanted_client=%r\n"
            "  Matches by name (stored_client vs wanted_client): %s",
            deal_name, repr(client_name), deal_name_matches
        )
    elif files_scanned == 0:
        # Directory exists but contains no _ndfcomm.json files
        try:
            tree = []
            for root2, _dirs2, files2 in os.walk(routes.NDF_COMM_CACHE_DIR):
                level = root2.replace(routes.NDF_COMM_CACHE_DIR, '').count(os.sep)
                indent = '  ' * level
                tree.append(f"{indent}{os.path.basename(root2)}/")
                for f2 in files2[:5]:
                    tree.append(f"{'  ' * (level+1)}{f2}")
            log.warning(
                "[_find_ndf] NO _ndfcomm.json FILES FOUND in %s\n  Directory tree:\n%s",
                routes.NDF_COMM_CACHE_DIR, '\n'.join(tree) or '  (empty)'
            )
        except Exception:
            log.warning("[_find_ndf] NO _ndfcomm.json FILES FOUND in %s", routes.NDF_COMM_CACHE_DIR)
    else:
        # Deal name itself was never found in any file
        # Show every (file, stored_Deal, stored_Client) so the mismatch is obvious
        log.warning(
            "[_find_ndf] DEAL NAME NOT MATCHED: wanted=%r (repr=%r)\n"
            "  Scanned %d file(s), %d deal(s). All stored (Deal, Client) pairs:\n%s",
            deal_name, repr(deal_name),
            files_scanned, deals_scanned,
            '\n'.join(
                f"    [{fn}] Deal={repr(dn)}  Client={repr(dc)}"
                for fn, dn, dc in all_names_seen
            ) or '    (none)'
        )

    return None, None


# A montagem final das linhas TER passou a sair do cadastro do File Interface
# (template termo-multiclasses): a ordem dos campos e os literais Fixed vêm do
# JSON, com os overrides da página /new_deals-ndf-commodities resolvidos pelo
# motor (_fi_build_line). Os valores continuam calculados aqui, já na largura
# exata de sempre — o motor não reformata nada. Template/bloco ausente vira
# erro claro no endpoint, nunca arquivo montado do jeito velho em silêncio.
def _ndf_comm_ter_lines(deal):
    """Linhas TER de UM deal de NDF Commodities: a tipo 1 (Dados Fixos) e,
    para asiático, as tipo 2 (datas de verificação da janela de fixing).
    Devolve (is_jpmorgan, [linhas]) — is_jpmorgan decide o arquivo
    (TCO_LAWTON × TCO_BANCO). Template/bloco ausente levanta ValueError."""
    from apps.pages import routes
    from decimal import Decimal
    import datetime as _dt
    import json as _json

    def _sh(v):
        return re.sub(r'<[^>]+>', '', str(v or '')).strip()

    def _date(val):
        val = _sh(val)
        if not val:
            return ''
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y'):
            try:
                return _dt.datetime.strptime(val, fmt).strftime('%Y%m%d')
            except ValueError:
                continue
        return ''

    def _cpty(client):
        c = client.upper()
        if 'LAWTON' in c:
            return '00041007'
        if 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return '73760009'
        return '73760102'

    def _taxid(client, taxid):
        c = client.upper()
        if 'LAWTON' in c or 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return ''
        return re.sub(r'[.\-/]', '', _sh(taxid))

    def _pos(s, width, align='left', fill=' '):
        s = str(s or '')
        if len(s) > width:
            s = s[:width]
        return s.rjust(width, fill) if align == 'right' else s.ljust(width, fill)

    def _pos_num(val, int_digits, dec_digits, div100=False):
        """Fixed-width positional numeric: int_digits integer + dec_digits decimal, no separator."""
        v = _sh(str(val or ''))
        if not v:
            return '0' * (int_digits + dec_digits)
        try:
            d = Decimal(v.replace(',', ''))
            if div100:
                d = d / Decimal('100')
            d = abs(d)
            int_part = int(d)
            frac_int = int(((d - int_part) * Decimal(10 ** dec_digits)).to_integral_value())
            return str(int_part).zfill(int_digits) + str(frac_int).zfill(dec_digits)
        except Exception:
            return '0' * (int_digits + dec_digits)

    client           = _sh(deal.get('Client', ''))
    taxid            = _sh(deal.get('TaxID', ''))
    direction        = _sh(deal.get('Direction', ''))
    trade_type       = _sh(deal.get('TradeType', '')).upper()
    strike_ccy       = _sh(deal.get('StrikeCurrency', '')).upper()
    underlying       = _sh(deal.get('UnderlyingAsset', '')).upper()
    instrument       = _sh(deal.get('Instrument', '')).upper()
    _cu              = client.upper()
    is_jpmorgan      = bool(re.search(r'J\.?P\.?\s*MORGAN', _cu))
    part_account     = '00041007' if is_jpmorgan else '73760009'
    fx_holiday_sched = _sh(deal.get('FXHolidaySchedule', ''))
    qic              = _sh(deal.get('QuotedInCents', 'NO')).upper() == 'YES'
    asian            = trade_type == 'ASIAN'
    vanilla          = trade_type == 'VANILLA'
    brl              = strike_ccy == 'BRL'
    is_tas           = instrument.startswith('TAS')

    dir_code   = '0' if direction.upper() == 'BUY' else '1'
    fix_start  = _date(deal.get('FixingStartDate', ''))
    fix_end    = _date(deal.get('FixingEndDate', ''))
    fxconv     = _date(deal.get('FXConvDate', ''))
    trade_date = _date(deal.get('TradeDate', ''))
    settl_date = _date(deal.get('SettlementDate', ''))
    deal_id    = _sh(deal.get('Deal', ''))
    notional   = _sh(deal.get('TotalNotional', ''))
    # Quoted in Cents divide por 100 SEMPRE que o ativo é cotado em cents —
    # a moeda do strike não entra na conta. A regra é do ativo (Fator
    # Conversão 0,01 no Subjacente), não do par de moedas, então excetuar o
    # BRL fazia o mesmo ativo sair com strike 100× diferente conforme a
    # moeda do deal. §172
    strike_str = _pos_num(deal.get('Strike', ''), 12, 8, div100=qic)

    # Notional: integer right-justified to 14 chars + '00' = 16 chars total
    try:
        qty_int = int(round(float(notional.replace(',', ''))))
        qty_str = str(qty_int).rjust(14, '0') + '00'
    except Exception:
        qty_str = '0' * 16

    # Cadastro (Commodities × B3): coluna vazia devolve o 'F'/'A' e o
    # 340/358 de sempre — ver `_b3_quote_cfg`. §177
    _q           = routes._b3_quote_cfg(underlying)
    tipo_cotacao = _q['ndf']
    fonte_info   = _q['source']

    fix_single = fix_start if (fix_start and fix_start == fix_end) else ''
    tipo_media = 'N' if fix_single else 'A'

    _deal_holidays = set()
    if not vanilla and fx_holiday_sched:
        # Strip anything but word chars so a crafted FXHolidaySchedule
        # (e.g. '../../secret') can't escape the data dir (path traversal).
        _sched_file = re.sub(r'[^A-Za-z0-9_]', '', fx_holiday_sched.replace('-', '_'))
        holiday_path = data_path(f'{_sched_file}.json') if _sched_file else None
        try:
            with open(holiday_path, encoding='utf-8') as _hf:
                _raw = _json.load(_hf)
            _deal_holidays = set(
                item['date'] if isinstance(item, dict) else item
                for item in _raw
            )
        except Exception:
            pass

    biz_count = 0
    if not vanilla and fix_start and fix_end:
        try:
            _s = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
            _e = _dt.datetime.strptime(fix_end,   '%Y%m%d').date()
            _cur = _s
            while _cur <= _e:
                if _cur.weekday() < 5 and _cur.strftime('%Y-%m-%d') not in _deal_holidays:
                    biz_count += 1
                _cur += _dt.timedelta(days=1)
        except Exception:
            pass

    if vanilla:
        biz_str = '000'
    else:
        biz_str = str(biz_count).zfill(3)
    my_number = str(random.randint(1000000000, 9999999999))

    # Par de pernas → variante do template. A perna nossa é a MESMA regra do
    # arquivo destino: cliente JPM = visão Lawton (TCO_LAWTON), senão Banco.
    le_pair = routes._ter_le_pair('LAWTON' if is_jpmorgan else 'JPM', client)

    # Posicional (largura fixa, sem delimitador) — layout TER do cadastro.
    # Só os campos não-Fixed entram em `values` (seq do template); os
    # literais e os brancos saem do JSON.
    values = {
        '4': _pos(my_number, 10),                     # Nº Controle Interno
        '5': _pos(part_account, 8),                   # Lançamento do Participante
        '6': _pos(dir_code, 1),                       # Papel
        '8': _pos(_cpty(client), 8),                  # Contraparte
        '9': _pos(_taxid(client, taxid), 14),         # CPF/CNPJ Contraparte
        '12': _pos(' ' + fonte_info, 4),              # Fonte de Informação
        '16': _pos(qty_str, 16),                      # Valor Base / Quantidade
        '17': _pos(underlying, 10, 'right'),          # Código do Ativo Subjacente
        '18': _pos(strike_str, 20),                   # Taxa a Termo (R$/Moeda)
        '19': _pos(fix_single, 8),                    # Data de Fixing do Ativo Subjacente
        '20': _pos(trade_date, 8),                    # Data de Operação
        '21': _pos(settl_date, 8),                    # Data de Vencimento
        '23': _pos(tipo_cotacao, 1),                  # Tipo de Cotação
        '24': _pos('' if brl else fxconv, 8),         # Data de Fixing da Moeda
        '35': _pos('S' if is_tas else 'N', 1),        # Termo a Termo
        '36': _pos(trade_date if is_tas else '', 8),  # Data de Fixação
        '37': _pos('V' if is_tas else '', 1),         # Forma de Atualização
        '55': _pos('S' if brl else '', 1),            # Taxa a Termo em Reais
        '57': _pos(deal_id, 14, 'right'),             # Código Identificador
        '58': _pos(tipo_media, 1),                    # Tipo Média Asiático
        '59': _pos(biz_str, 3),                       # Quantidade de Datas de Verificação
    }
    lines = [routes._fi_build_line(routes._TER_FI_KEY, 'registro-dados-fixos', values,
                            page_url='/new_deals-ndf-commodities',
                            le_pair=le_pair, deal=deal)]

    # Asian fixing date rows (line type 2) — também pelo motor. O parse das
    # datas fica num try próprio: um ValueError do template tem de SUBIR até
    # o endpoint, não ser engolido junto com uma data malformada.
    #
    # Cotação para o Vencimento (campo 15) EFETIVA preenchida (> 0) desloca as
    # DATAS das linhas de verificação N dias úteis PARA FRENTE, no MESMO
    # calendário do deal — o campo é cadastrável (Fixed da variante ou
    # fórmula), e hoje nasce em branco: sem cadastro, nada muda.
    _cotv = routes._fi_effective_seq_value(routes._TER_FI_KEY, 'registro-dados-fixos', '15',
                                    values, '/new_deals-ndf-commodities',
                                    le_pair, deal).strip()
    _shift_n = int(_cotv) if _cotv.isdigit() and int(_cotv) > 0 else 0

    def _shift_biz(d0):
        cur, left = d0, _shift_n
        while left > 0:
            cur += _dt.timedelta(days=1)
            if cur.weekday() < 5 and cur.strftime('%Y-%m-%d') not in _deal_holidays:
                left -= 1
        return cur

    if asian and fix_start and fix_end:
        try:
            _s2 = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
            _e2 = _dt.datetime.strptime(fix_end,   '%Y%m%d').date()
        except ValueError:
            _s2 = _e2 = None
        _cur2 = _s2
        while _cur2 is not None and _cur2 <= _e2:
            if _cur2.weekday() < 5 and _cur2.strftime('%Y-%m-%d') not in _deal_holidays:
                _d  = _shift_biz(_cur2).strftime('%Y%m%d')
                _fx = _d if brl else ''
                lines.append(routes._fi_build_line(
                    routes._TER_FI_KEY, 'registro-dados-variaveis',
                    {'4': _pos(_d, 8),                    # Data Verificação
                     '6': _pos(_fx, 8) + _pos('', 10)},   # Data de Verificação da Moeda + filler
                    page_url='/new_deals-ndf-commodities', le_pair=le_pair, deal=deal))
            _cur2 += _dt.timedelta(days=1)
    return is_jpmorgan, lines

# Product Type shown on the Pending Confirmation row — the three generic NDF
# pages (Vanilla / Other Publisher / FWD Start) all report plain 'NDF'.
_GENERIC_ND_PC_TYPE = {'fwd-start': 'NDF',
                       'other-publishers': 'NDF',
                       'vanilla': 'NDF'}

# Qual das três páginas genéricas de NDF gera confirmação. Só o FWD Start —
# Vanilla e Other Publisher alimentam o Pending Confirmation e param por aí.
_GENERIC_ND_MC_SOURCE = {'fwd-start': 'NDF FWD START'}


def _generic_nd_pending_status(product, deal):
    """Pending Status de um deal genérico de NDF que virou Success.

    **O FWD Start vem primeiro, e antes do prazo.** Ele passa pela esteira de
    validação como todo produto que não seja Vanilla / Other Publisher, e a etapa
    de quem entra na esteira é `Pending OTC` — o prazo curto não a substitui. Com
    o teste de prazo na frente, um FWD Start de 30 dias nascia `Exception FepWeb`
    (resolvido) no Pending Confirmation enquanto a esteira o mantinha na fila do
    OTC: as duas telas contando coisas diferentes sobre a mesma confirmação.

    Vanilla e Other Publisher não têm esteira, e por isso são os únicos que caem
    na regra de prazo/assinatura — a MESMA função que a importação do Pending
    Update e a edição em massa da tela usam.
    """
    from apps.pages import routes
    if product == 'fwd-start':
        return 'Pending OTC'
    return routes._pc_signature_pending_status(
        routes._fxo_refdata_by_spn().get(routes._norm_spn(deal.get('SPN', '')), {}),
        routes._parse_date_any(deal.get('TradeDate', '')),
        routes._parse_date_any(deal.get('SettlementDate', '')))


def _generic_nd_pc_trigger(product, deal):
    """→ Pending Confirmation on Status Success (same trigger as the other New
    Deals products; _pc_save_from_deal skips internal/intragroup legs itself).
    FWD Start rows are keyed by the mapped B3 ID, not the Deal name."""
    from apps.pages import routes
    tn = None
    if product == 'fwd-start':
        tn = str(deal.get('B3_ID', '') or '').strip() or None
    # `source` separa as três páginas, que gravam o mesmo Product Type 'NDF':
    # só o FWD Start gera confirmação e entra em Manual Confirmations.
    routes._pc_save_from_deal(deal, _GENERIC_ND_PC_TYPE.get(product, 'NDF'),
                       pending_status=_generic_nd_pending_status(product, deal),
                       trade_number=tn,
                       source=_GENERIC_ND_MC_SOURCE.get(product))

def _find_generic_nd_deal(cfg, deal_name, client_name=None):
    """Locate a deal by Deal (+optional Client) across the product's cache files.
    Returns (file_path, list_index) or (None, None)."""
    base = cfg['dir']
    if not os.path.isdir(base):
        return None, None
    for root, _dirs, files in os.walk(base):
        for fname in sorted(files):
            if not fname.endswith(cfg['suffix']):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
                for i, deal in enumerate(deals):
                    if deal.get('Deal', '') == deal_name and (client_name is None or deal.get('Client', '') == client_name):
                        return fpath, i
            except Exception:
                continue
    return None, None


def _generic_nd_reenrich(deals, refmap_cache):
    """Preenche SPN/Client/TaxID de deals importados com contraparte faltante
    cujo Acronym (End Counterparty) passou a existir no RefData — o cadastro
    feito depois do import só corrigia o DOM da página; ao sair e voltar, o
    cache em disco ainda tinha os campos vazios (linha sem badge e sem
    cliente). Retorna True se algo mudou (o caller persiste o arquivo).
    refmap_cache: dict de 1 posição para construir o mapa por acronym só uma
    vez por request."""
    from apps.pages import routes
    changed = False
    for deal in deals:
        if not isinstance(deal, dict):
            continue
        if str(deal.get('SPN', '') or '').strip():
            continue
        acr = str(deal.get('Acronym', '') or '').strip().upper()
        if not acr:
            continue
        if 'map' not in refmap_cache:
            refmap_cache['spn'] = routes._fxo_refdata_by_spn()
            refmap_cache['map'] = _fxo_refdata_by_accronym(refmap_cache['spn'])
        # Mapping Legal Entity × Accronym: o accronym gravado pode identificar a
        # LE (é o caso do End Counterparty que é nome de book interno, importado
        # antes de a linha existir). Quando ele identifica, a LE gravada estava
        # errada — veio da Settlement Location — e é corrigida aqui, junto com a
        # contraparte da entidade, sem precisar de novo pull da API.
        #
        # Só `le_map` entra na busca da contraparte. Caindo para a LE gravada no
        # deal (que veio da Settlement Location, a NOSSA perna) um cliente sem
        # accronym cadastrado era re-enriquecido como a própria JPMorgan — o
        # mesmo erro de _ndf_deal_from_api, aqui aplicado a quem já está no
        # arquivo.
        le_map = _ndf_le_from_accronym(acr)
        # Sem SPN gravado não há o que passar como último recurso — a linha está
        # aqui justamente porque o campo veio vazio.
        rec = _ndf_ref_by_accronym(refmap_cache['map'], acr, le_map, refmap_cache['spn'])
        if not rec:
            if le_map and le_map != str(deal.get('LE', '') or '').strip().upper():
                deal['LE'] = le_map
                changed = True
            continue
        if le_map and le_map != str(deal.get('LE', '') or '').strip().upper():
            deal['LE'] = le_map
        deal['SPN'] = str(rec.get('SPN', '') or '')
        deal['Client'] = rec.get('COUNTERPARTY', '') or ''
        deal['TaxID'] = rec.get('TAX ID', '') or ''
        # Perna interna mantém o accronym da API (o nome do book) — §174.
        ref_acr = '' if le_map else str(rec.get('FX CASH ACCRONYM', '') or '').strip()
        if ref_acr:
            deal['Acronym'] = ref_acr
        changed = True
    return changed


# ──────────────────────────────────────────────────────────────────────────
# GENERIC NDF (FWD Start / Other Publisher) — send-conecta (TER files)
# ──────────────────────────────────────────────────────────────────────────
# Same positional TER layout as ndf-commodities, with the FX-NDF field rules.
# Lines are split into THREE files by participant entity:
#   • LE = LAWTON, or client is the Banco J.P. Morgan → the LAWTON-side leg →
#     *_LAWTON file (participant 00041007) — mirrors the ndf-commodities
#     convention;
#   • else LE = MGT → *_MGT file (participant 04880006);
#   • else → *_BANCO file (participant 73760009).
# Counterparty account follows the LE matrix used on the page previews.
#
# A perna Lawton × Banco NÃO depende de vir da API: quando a linha do banco
# tem o Lawton como contraparte e o lote não traz a perna espelhada explícita
# (LE = LAWTON) do mesmo trade, o envio SINTETIZA a visão Lawton a partir da
# própria linha — mesmo trade, Participante ↔ Contraparte trocados e Papel
# invertido — e ela cai no *_LAWTON. É a convenção que o TAXA da página
# /ndf-other-publisher sempre teve (uma linha, duas visões); aqui o desenho
# original apostava que a perna do book do Lawton chegaria como deal próprio,
# e ela não chega — o arquivo visão Lawton simplesmente nunca nascia.

# Athena publisher (feeder) → códigos B3: mapping publisher-ndf, tela Mapping.
def _ndf_publisher_row(publisher):
    """Linha do mapping publisher-ndf que casa o publisher.

    Duas passadas, nesta ordem:

    1. **Nome exato** — o PUBLISHER da linha igual ao publisher inteiro. Uma
       linha **sem** Match Tokens só casa aqui: é o texto completo, sem
       variação. É o que separa a linha 'PTAX' da 'PTAX|BRR|PTAX' — as duas
       existem e cada uma vale para o seu publisher exato.
    2. **Token** — só para linhas COM a coluna TOKENS preenchida, porque a
       Athena manda o publisher composto ('PTAX|USB|WMR|4' → REUTERS - WMR).

    Nada casando → {}.
    """
    from apps.pages import routes
    p = (publisher or '').strip().upper()
    if not p:
        return {}
    rows = routes._mapping_rows('publisher-ndf')
    for r in rows:
        if str(r.get('PUBLISHER', '') or '').strip().upper() == p:
            return r
    for r in rows:
        for tok in re.split(r'[,;]', str(r.get('TOKENS', '') or '')):
            tok = tok.strip().upper()
            if tok and tok in p:
                return r
    return {}


# Valor da coluna NOTES que marca o feeder como BACEN — e, com isso, manda a
# operação para a página Vanilla em vez de Other Publisher.
_NDF_NOTES_BACEN = 'BACEN'


def _ndf_publisher_is_bacen(publisher):
    """True quando a linha do publisher no mapping tem NOTES = BACEN.

    É o que decide Vanilla × Other Publisher. Antes o teste era o literal
    `publisher.upper() != 'PTAX'` no roteamento da API, então qualquer variante
    ('PTAX|BRR|PTAX') caía em Other Publisher mesmo sendo PTAX do BACEN, e não
    havia como corrigir sem mexer no código. Agora quem decide é o cadastro.

    Publisher vazio conta como BACEN: é o default histórico do import, que
    tratava ausência de feeder como PTAX puro.
    """
    if not (publisher or '').strip():
        return True
    notes = str(_ndf_publisher_row(publisher).get('NOTES', '') or '').strip().upper()
    return notes == _NDF_NOTES_BACEN


def _ndf_publisher_codes(publisher):
    """Publisher → {'consulta': Fonte de Consulta, 'info': Tela ou Função de
    Consulta}. Publisher sem linha no mapping devolve {} (campos em branco)."""
    r = _ndf_publisher_row(publisher)
    if not r:
        return {}
    return {'consulta': str(r.get('FONTE CONSULTA', '') or '').strip(),
            'info': str(r.get('TELA CONSULTA', '') or '').strip()}


def _ndf_publisher_fonte_info(publisher):
    """Fonte de Informação do TER, 4 chars alinhados à direita. Sem linha no
    mapping = 1, que era o comportamento de quando isso era hardcoded."""
    fi = str(_ndf_publisher_row(publisher).get('FONTE INFO', '') or '').strip() or '1'
    return fi.rjust(4)

def _generic_ndf_ter_line(deal, is_fwd, page_url=None):
    """Linha tipo 1 (Dados Fixos) do TER de um deal FWD Start / Other
    Publisher. Devolve (bucket, linha) — bucket BANCO / LAWTON / MGT — ou
    None para deal cancelado. Os valores continuam calculados aqui, na
    largura exata de sempre; a ordem dos campos e os literais Fixed saem do
    cadastro (page_url decide os overrides de cada página). Template/bloco
    ausente levanta ValueError."""
    from apps.pages import routes
    def _s(v):
        return re.sub(r'<[^>]+>', '', str(v or '')).strip()

    def _pos(s, width, align='left', fill=' '):
        s = str(s or '')[:width]
        return s.rjust(width, fill) if align == 'right' else s.ljust(width, fill)

    def _znum(val, int_digits, dec_digits):
        """Zero-padded positional number: int_digits + dec_digits chars."""
        try:
            from decimal import Decimal
            d = abs(Decimal(str(val).replace(',', '')))
            ip = int(d)
            fp = int(((d - ip) * (10 ** dec_digits)).to_integral_value())
            return str(ip).zfill(int_digits) + str(fp).zfill(dec_digits)
        except Exception:
            return '0' * (int_digits + dec_digits)

    def _d8(v):
        dt = routes._parse_date_any(_s(v))
        return dt.strftime('%Y%m%d') if dt else ''

    def _is_jpm(c):
        return bool(re.search(r'J\.?P\.?\s*MORGAN', c.upper()))

    def _is_mgt(c):
        return 'MGT' in c.upper()

    def _is_lawton(c):
        return 'LAWTON' in c.upper()

    if str(deal.get('Status', '') or '').strip() == 'Canceled':
        return None                     # cancelado via API: fora dos arquivos
    client   = _s(deal.get('Client', ''))
    le       = _s(deal.get('LE', '')).upper()
    deal_id  = _s(deal.get('Deal', ''))
    publisher = _s(deal.get('Publisher', ''))
    qty_ccy  = _s(deal.get('QuantityCurrency', '')).upper()
    oth_ccy  = _s(deal.get('OtherQuantityCurrency', '')).upper()
    # O flag de asiático NÃO vem do TradeType: ele é derivado das datas de
    # fixing logo abaixo (asian_fix), para o arquivo não depender de um
    # rótulo que pode ter vindo do XLSX ou de uma edição manual.

    # Entity bucket + participant / counterparty accounts
    if 'LAWTON' in le:                        # LE Lawton: parte Lawton × banco JPM
        bucket, participant, cpty = 'LAWTON', '00041007', '73760009'
    elif _is_jpm(client):                     # Lawton-side mirror leg
        bucket, participant = 'LAWTON', '00041007'
        cpty = '04880006' if le == 'MGT' else '73760009'
    else:
        bucket = 'MGT' if le == 'MGT' else 'BANCO'
        participant = '04880006' if le == 'MGT' else '73760009'
        if _is_lawton(client):
            cpty = '00041007'
        elif le == 'MGT':
            cpty = '73760009' if _is_jpm(client) else '04880109'
        else:
            cpty = '04880006' if _is_mgt(client) else '73760102'
    taxid = '' if ('LAWTON' in le or _is_jpm(client) or _is_lawton(client) or _is_mgt(client)) \
        else re.sub(r'[.\-\/]', '', _s(deal.get('TaxID', '')))

    last_fix_dt = routes._parse_date_any(_s(deal.get('LastFixingDate', '')))
    settl_dt    = routes._parse_date_any(_s(deal.get('SettlementDate', '')))
    biz_diff    = routes._anbima_biz_diff(last_fix_dt, settl_dt)

    strike_set_dt = routes._parse_date_any(_s(deal.get('StrikeSetDate', '')))
    fixacao_dt    = routes._anbima_add_biz(strike_set_dt, biz_diff) if strike_set_dt else None

    # Fonte de Informação: coluna do mapping publisher-ndf (PTAX puro = 0,
    # demais feeders = 1). Boletim: no OP sai em branco; no FWD Start segue
    # a fonte (0 → 3, senão 1).
    fonte_info = _ndf_publisher_fonte_info(publisher)
    boletim    = ('3' if fonte_info.strip() == '0' else '1') if is_fwd else ' '

    # Valor Base / Quantidade: inteiro alinhado à direita em 14 + '00'. Estas
    # páginas mandam a coluna como Notional (só o NDF Comm usa TotalNotional)
    # — aceita os dois. O valor gravado é US ('{:,.2f}'), mas uma edição
    # manual pode chegar em BR; quando os dois separadores aparecem, quem
    # define o decimal é o que vem por último. Sem isso, '5.158.000,00' não
    # parseia e o campo sai com 16 zeros em silêncio.
    notional_s = (_s(deal.get('TotalNotional', '')) or _s(deal.get('Notional', ''))).replace(' ', '')
    if ',' in notional_s and '.' in notional_s:
        notional_s = (notional_s.replace('.', '').replace(',', '.')
                      if notional_s.rfind(',') > notional_s.rfind('.')
                      else notional_s.replace(',', ''))
    elif notional_s.count('.') > 1:
        notional_s = notional_s.replace('.', '')     # 5.158.000 — dois pontos só podem ser milhar
    else:
        notional_s = notional_s.replace(',', '')     # US, o formato que a aplicação grava
    try:
        qty_int = int(round(float(notional_s)))
        qty_str = str(qty_int).rjust(14, '0') + '00'
    except Exception:
        qty_str = '0' * 16

    fix_start = _d8(deal.get('FirstFixingDate', ''))
    fix_end   = _d8(deal.get('LastFixingDate', ''))
    # Asiático exige JANELA de fixing: primeira E última preenchidas e
    # DIFERENTES. First fixing vazio (fixing único) ou datas iguais = vanilla.
    # A regra antiga só testava a igualdade das duas, então o first vazio
    # caía em 'A' — um fixing único ia para a B3 como média asiática.
    asian_fix  = bool(fix_start and fix_end and fix_start != fix_end)
    # Vanilla: Data de Fixing do Ativo Subjacente = a data do fixing único
    # (a última preenchida). Asiático deixa em branco — as datas da janela
    # vão nas linhas de verificação.
    fix_single = '' if asian_fix else (fix_end or fix_start)
    # Data de Fixing do Ativo Subjacente (campo 19): HOJE o cadastro manda
    # branco para as DUAS páginas (Fixed vazio no termo-multiclasses — o FWD
    # Start passou a Blank em 2026-08-12, a pedido da mesa; o OP sempre foi).
    # O valor continua calculado e entregue ao motor: com o override Fixed ele
    # é ignorado, e re-apontar o cadastro para Page volta a mandar a data sem
    # tocar em código. `tipo_media` não depende deste campo — sai de
    # `asian_fix` —, então o branco não muda a classificação.
    if not is_fwd:
        fix_single = ''
    tipo_media = 'A' if asian_fix else 'N'

    if is_fwd:
        taxa_termo   = _pos('', 20)
        cot_venc     = str(biz_diff)[:1] or '0'
        fonte_cons   = ''
        tela_cons    = ''
        data_aval    = ''
        valor_perc   = _znum(_s(deal.get('StrikeSetOffset', '')) or '0', 4, 8)
    else:
        # O campo é a "Taxa a Termo (R$/Moeda)" e o Rate do deal JÁ está nessa
        # convenção — a inversão da moeda fraca é feita UMA vez, na importação
        # (`_ndf_weak_leg`). Aqui só entram as casas do cadastro (Inverse
        # Decimals), que é a precisão com que o 1/taxa vai para a B3.
        #
        # Este bloco invertia de novo, e por QUANTITY CURRENCY: como a
        # importação olhava a outra perna, as duas condições eram
        # complementares e o arquivo saía certo por compensação — mas a coluna
        # Rate da tela, o contravalor do MT300 e a taxa do Intrag ficavam com o
        # valor cru sempre que a moeda fraca era a do notional.
        rate_raw = _fxo_num(_s(deal.get('Rate', '')))
        _inv = routes._mapping_ccy_maps()[2]
        _leg = _ndf_weak_leg(qty_ccy, oth_ccy)
        if rate_raw and _leg in _inv:
            rate_val = round(rate_raw, _inv[_leg])
        else:
            rate_val = rate_raw
        taxa_termo   = _znum(rate_val if rate_val is not None else '0', 12, 8)
        cot_venc     = ' '
        pub = _ndf_publisher_codes(publisher)
        fonte_cons   = pub.get('consulta', '')
        tela_cons    = pub.get('info', '')
        data_aval    = _d8(deal.get('LastFixingDate', ''))
        valor_perc   = (_znum(_s(deal.get('StrikeSetOffset', '')), 4, 8)
                        if _s(deal.get('StrikeSetOffset', '')) else _pos('', 12))

    dir_code = '0' if _s(deal.get('Direction', '')).upper() == 'BUY' else '1'
    my_number = str(random.randint(1000000000, 9999999999))

    # OP com BRL fixed: inverte as moedas — a estrangeira vira a Moeda de
    # Referência e o BRL a Moeda Cotada.
    brl_fixed = (not is_fwd) and _s(deal.get('IsBRRFixed', '')).upper() == 'YES'
    moeda_ref, moeda_cot = (oth_ccy, qty_ccy) if brl_fixed else (qty_ccy, oth_ccy)

    # Só os campos não-Fixed entram em `values` (seq do template). O que
    # antes era literal na concatenação — Contrato Global 'S', Classe do
    # Ativo '2', Cotação R$/USD '1' e Paridade '3' do OP, Termo a Termo
    # S/N, Forma de Atualização 'V', 'N' de Atualizar/Ajustar, os brancos —
    # agora sai do cadastro, por página.
    values = {
        '4': _pos(my_number, 10),                    # Nº Controle Interno
        '5': _pos(participant, 8),                   # Lançamento do Participante
        '6': _pos(dir_code, 1),                      # Papel
        '8': _pos(cpty, 8),                          # Contraparte
        '9': _pos(taxid, 14),                        # CPF/CNPJ Contraparte
        '12': _pos(fonte_info, 4),                   # Fonte de Informação
        '13': _pos(routes._moeda_num_code(moeda_ref), 3),   # Moeda de Referência
        '14': _pos(routes._moeda_num_code(moeda_cot), 3),   # Moeda Cotada
        '15': _pos(cot_venc, 1),                     # Cotação para o Vencimento (FWD)
        '16': _pos(qty_str, 16),                     # Valor Base / Quantidade
        '18': _pos(taxa_termo, 20),                  # Taxa a Termo (OP)
        '19': _pos(fix_single, 8),                   # Data de Fixing do Ativo (FWD)
        '20': _pos(_d8(deal.get('TradeDate', '')), 8),       # Data de Operação
        '21': _pos(_d8(deal.get('SettlementDate', '')), 8),  # Data de Vencimento
        '22': _pos(boletim, 1),                      # Boletim (FWD)
        '26': _pos(fonte_cons, 1),                   # Fonte de Consulta (OP)
        '27': _pos(tela_cons, 8, 'right'),           # Tela ou Função de Consulta (OP)
        '32': _pos(data_aval, 8),                    # Data de Avaliação (OP)
        '36': _pos(fixacao_dt.strftime('%Y%m%d') if fixacao_dt else '', 8),  # Data de Fixação
        '38': _pos(valor_perc, 12),                  # Valor / Percentual Negociado
        '39': _pos((str(biz_diff)[:1] or '0') if is_fwd else ' ', 1),  # Cotação para Fixing (FWD)
        '55': _pos('S' if _s(deal.get('IsBRRFixed', '')).upper() == 'YES' else '', 1),  # Taxa a Termo em Reais
        '57': _pos(deal_id[-14:], 14, 'right'),      # Código Identificador (right 14 of Deal)
        '58': _pos(tipo_media, 1),                   # Tipo Média Asiático
        '59': _pos(str(routes._anbima_biz_diff(
            routes._parse_date_any(_s(deal.get('FirstFixingDate', ''))),
            routes._parse_date_any(_s(deal.get('LastFixingDate', ''))))
            + 1).zfill(3) if asian_fix else '000', 3),   # Qtde Datas Verificação
    }
    # O default é a página do produto; o download do Vanilla passa a DELE,
    # para os overrides e variantes do cadastro daquela página valerem.
    page_url = page_url or ('/new_deals-ndf-fwdstart' if is_fwd
                            else '/new_deals-ndf-otherpublisher')
    le_pair = routes._ter_le_pair(routes._TER_BUCKET_LE[bucket], client)
    return bucket, routes._fi_build_line(routes._TER_FI_KEY, 'registro-dados-fixos', values,
                                  page_url=page_url, le_pair=le_pair, deal=deal)


def _nd_lawton_mirror(deal):
    """A perna Lawton × Banco do MESMO trade, vista a partir da linha do banco
    contra o Lawton. LE = LAWTON leva a `_generic_ndf_ter_line` ao ramo que já
    monta a visão Lawton (participante 00041007 × contraparte 73760009, CNPJ em
    branco); o Papel inverte porque quem compra de um lado vende do outro. Todo
    o resto — datas, taxa, notional, publisher, Código Identificador — é do
    trade, então fica igual."""
    m = dict(deal)
    m['LE'] = 'LAWTON'
    m['Client'] = 'BANCO J.P. MORGAN S.A.'
    d = str(deal.get('Direction', '') or '').strip().upper()
    m['Direction'] = 'SELL' if d == 'BUY' else 'BUY'
    return m


def _nd_lawton_sig(deal):
    """Assinatura de trade para casar a perna do banco com a perna Lawton
    explícita do lote: (Data de Operação, Data de Vencimento, notional). Os
    Deal IDs das duas pernas são diferentes — cada book registra o seu —, então
    a correlação é pelos termos econômicos."""
    from apps.pages import routes
    def _dt8(v):
        dt = routes._parse_date_any(re.sub(r'<[^>]+>', '', str(v or '')).strip())
        return dt.strftime('%Y%m%d') if dt else ''
    raw = str(deal.get('TotalNotional') or deal.get('Notional') or '').replace(',', '').strip()
    try:
        val = round(float(raw), 2)
    except ValueError:
        val = None
    return (_dt8(deal.get('TradeDate')), _dt8(deal.get('SettlementDate')), val)

# Status que ESPERAM retorno da B3: só esses viram 'Error' quando o deal não
# aparece no arquivo. Um deal em Approved/Pending ainda nem foi registrado, e um
# já Success não pode regredir por causa de um arquivo que já foi consumido.
_ND_MAPPING_ERRORABLE = {'New', 'Sent', 'Error'}


def _generic_nd_mapping_candidates(cfg, product, ref_date):
    """Deals da Reference Date que entram no mapping do arquivo de retorno.

    Sai do ARQUIVO DO DIA, não da tabela. A tabela mostra o resultado da última
    busca — mapear o que estava renderizado deixava para trás operações do mesmo
    dia que ninguém tinha filtrado.

    Entram todos os status, exceto:
      • 'Canceled' — cancelado na API, fora do fluxo;
      • já 'Success' COM B3 ID — não há o que mapear e uma segunda passada só
        poderia perder informação.
    Nas outras páginas o filtro antigo (New/Sent/Error) é mantido: o Vanilla é
    que é registrado por outra ferramenta, e por isso precisa olhar qualquer
    status."""
    from apps.pages import routes
    ref = routes._parse_date_any(ref_date)
    if not ref:
        return []
    fpath = os.path.join(cfg['dir'], ref.strftime('%Y'), ref.strftime('%m'),
                         ref.strftime('%Y%m%d') + cfg['suffix'])
    if not os.path.isfile(fpath):
        return []
    try:
        with open(fpath, encoding='utf-8') as fh:
            deals = json.load(fh)
        if not isinstance(deals, list):
            deals = [deals]
    except (IOError, json.JSONDecodeError):
        return []

    out, seen = [], set()
    for d in deals:
        if not isinstance(d, dict):
            continue
        deal = str(d.get('Deal', '') or '').strip()
        if not deal:
            continue
        status = str(d.get('Status', '') or '').strip()
        if status == 'Canceled':
            continue
        if status == 'Success' and str(d.get('B3_ID', '') or '').strip():
            continue
        if product != 'vanilla' and status not in _ND_MAPPING_ERRORABLE:
            continue
        client = str(d.get('Client', '') or '').strip()
        key = (deal, client)
        if key in seen:
            continue
        seen.add(key)
        out.append({'Deal': deal, 'Client': client, 'Status': status})
    return out
