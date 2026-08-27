# -*- coding: utf-8 -*-
"""MtM de Swap — importação da pasta, ciclo da linha, geração dos arquivos B3,
validação e a recon. Movido VERBATIM do routes.py (nomes preservados).

Ficaram no routes: `_mtm_parse_num` (o NDF Summary, o Operations B3 e o
Settlement Advice de Swap parseiam números com ele) e `_mtm_norm_party` (o
accrual casa os fatores CEM pelo mesmo normalizador).
"""
import os
import random
import re
import traceback
from datetime import datetime, timedelta

from flask import render_template


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


MTM_SOURCE_ROOT = _R().os.getenv('MTM_SOURCE_ROOT', _R().os.path.join(
    _R().Config.SHARED_DRIVE_ROOT, 'Confirmation', 'Derivativos', 'OTC Tracker', 'Regulatory', 'MTM'))

MTM_JSON_ROOT = _R().data_write('cache', 'mtm')

_MTM_ACCOUNT      = '73760009'               # col D house account (73760.00-9), digits only

_MTM_FILTER_COL   = 3                         # col D

_MTM_RECON_DATA_ROW  = 8                      # ConsultaInformacoesAtualizMID: headers row 8, data from row 9 (idx 8)

_MTM_RECON_VALUE_COL = 6                      # col G = registered Valor MTM (signed)

_MTM_SWAP_BOOKS   = ('CEM', 'EDG', 'Hybrids', 'Commodities')

_MTM_FIXED_HEADERS = [
    'Código IF', 'Data Início', 'PARTE / Conta', 'Nome Simplificado Parte',
    'CONTRAPARTE / Conta', 'Nome Simplificado Contraparte',
    'Data Vencimento', 'Valor MTM', 'Comments',
]

_MTM_DISPLAY_SRC  = [0, 2, 3, 4, 5, 6, 10, None, None]

_MTM_COE_HEADERS  = ['Código do COE', 'Nome Simplificado Emissor', 'Conta Emissor', 'Nome Figura', 'Valor MTM', 'Comments']

_MTM_COE_SRC      = [0, 1, 2, 3, None, None]  # A,B,C,D (A '#' stripped) + Valor MTM (blank) + Comments (manual)

_MTM_COE_REFDATE_COL = 6                       # col G reference date

_MTM_VALOR_IDX    = _MTM_FIXED_HEADERS.index('Valor MTM')    # 7

_MTM_COMMENT_IDX  = _MTM_FIXED_HEADERS.index('Comments')     # 8

_MTM_COE_VALOR_IDX   = _MTM_COE_HEADERS.index('Valor MTM')   # 4

_MTM_COE_COMMENT_IDX = _MTM_COE_HEADERS.index('Comments')    # 5

_MTM_ZERO_COMMENT   = 'MtM não pode ser Zero'

_MTM_STATUS_MISSING = 'Missing MtM'                   # rows with no matching MtM value

_MTM_CEM_SELF_PARTY = _R()._mtm_norm_party('Bco J.P. Morgan S.A. 2768 - GEM BR - RATES')

def _mtm_is_cem_value_name(n):
    nl = (n or '').lower()
    return 'vcp_cetip_mtm' in nl and not nl.endswith('.msg')

def _mtm_parse_num_br(s):
    """Parse a BRL-formatted amount like "-1.802.855,64" (dot thousands, comma
    decimal, optional surrounding quotes) → float, or None. Used for the recon file
    (ConsultaInformacoesAtualizMID), whose values are in BRL format — unlike the
    page's US-format Valor MTM (see _mtm_parse_num)."""
    s = str(s or '').strip().strip("'").strip('"').strip()
    if not s:
        return None
    s = s.replace('.', '').replace(',', '.')      # drop dot thousands, comma → decimal
    try:
        return float(s)
    except ValueError:
        return None

def _mtm_apply_cem_values(cem_rows, file_rows):
    """Fill each CEM row's 'Valor MTM' (rounded 2dp, signed) from VCP_CETIP_MTM,
    matching col C (CETIP ID) to Código IF. Zero → keep 0.00 + zero comment.
    Rows with NO matching value → status 'Missing MtM'. cem_rows are FINALIZED
    (status at index -4). Returns (matched, zeros, missing)."""
    vmap = {}
    for r in file_rows:
        b = _R()._mtm_norm_party(_R()._cc_cell(r, 1))
        if not b or b == _MTM_CEM_SELF_PARTY:
            continue                                     # keep B <> our GEM-Rates side
        cid = str(_R()._cc_cell(r, 2) or '').strip().strip("'").strip('"')
        num = _R()._mtm_parse_num(_R()._cc_cell(r, 3))
        if not cid or num is None:
            continue                                     # header row skipped here too
        vmap.setdefault(cid.upper(), num)
    matched = zeros = missing = 0
    for row in cem_rows:
        cid = str(row[0] or '').strip().upper()
        if cid in vmap:
            v = round(vmap[cid], 2)
            if v == 0:                                     # keep 0.00 in the table (the
                row[_MTM_COMMENT_IDX] = _MTM_ZERO_COMMENT  # preview/file registers 1 cent)
                zeros += 1
            row[_MTM_VALOR_IDX] = '{:,.2f}'.format(v)      # #,##0.00 (comma thousands)
            matched += 1
        else:
            row[-4] = _MTM_STATUS_MISSING                  # no MtM value → Missing MtM
            missing += 1
    return matched, zeros, missing

def _mtm_is_edg_value_name(n):
    """EDG/COE MtM values file — named 'EDG.<ext>' (any extension)."""
    return _R().os.path.splitext(n or '')[0].strip().lower() == 'edg'

def _mtm_apply_edg_values(data, file_rows):
    """EDG file: col A = contract ID, col B = MtM value (IDs 'JP*' are COE, the rest
    EDG). Match by ID onto the EDG and COE tables; set 'Valor MTM' (#,##0.00 signed,
    zero → 0.00 + zero comment). Rows with NO matching value → status 'Missing MtM'.
    Rows are FINALIZED (status at -4). Returns (edg_matched, coe_matched, zeros, missing)."""
    tables = data.get('tables') or {}
    fmap = {}
    for r in file_rows:
        cid = str(_R()._cc_cell(r, 0) or '').strip().strip("'").strip('"')
        num = _R()._mtm_parse_num(_R()._cc_cell(r, 1))
        if cid and num is not None:
            fmap.setdefault(cid.upper(), num)              # header row skipped (value not numeric)
    edg_m = coe_m = zeros = missing = 0
    for row in tables.get('EDG', []) or []:
        cid = str(row[0] or '').strip().upper()
        if cid in fmap:
            v = round(fmap[cid], 2)
            if v == 0:                                     # keep 0.00 in the table (the
                row[_MTM_COMMENT_IDX] = _MTM_ZERO_COMMENT  # preview/file registers 1 cent)
                zeros += 1
            row[_MTM_VALOR_IDX] = '{:,.2f}'.format(v)
            edg_m += 1
        else:
            row[-4] = _MTM_STATUS_MISSING
            missing += 1
    for row in tables.get('COE', []) or []:
        cid = str(row[0] or '').strip().upper()
        if cid in fmap:
            v = round(fmap[cid], 2)
            if v == 0:                                     # keep 0.00 in the table (the
                row[_MTM_COE_COMMENT_IDX] = _MTM_ZERO_COMMENT  # preview/file registers 1 cent)
                zeros += 1
            row[_MTM_COE_VALOR_IDX] = '{:,.2f}'.format(v)
            coe_m += 1
        else:
            row[-4] = _MTM_STATUS_MISSING
            missing += 1
    return edg_m, coe_m, zeros, missing

_MTM_HYB_MAP_PATH  = _R().data_path('mapping_swap-hyb.json')

_MTM_HYB_VALUE_COL = 4                                # col E: MTM in scaling currency

def _mtm_is_hyb_value_name(n):
    return 'stream_level_mtm' in (n or '').lower()

def _mtm_load_hyb_mapping():
    try:
        with open(_MTM_HYB_MAP_PATH, encoding='utf-8') as fh:
            data = _R().json.load(fh)
        return data if isinstance(data, list) else []
    except Exception:
        return []

def _mtm_apply_hyb_values(hyb_rows, file_rows, mapping):
    """SUMIF col E ('MTM in scaling currency') grouped by Trade Name (col A) in the
    Stream_level_MTM file; resolve the mapping's B3 ID and set each Hybrids row's
    'Valor MTM' (Código IF = B3 ID). Rows with NO matching value → 'Missing MtM'.
    hyb_rows are FINALIZED (status at -4). Returns (matched, zeros, missing)."""
    sums = {}                                            # normalized Trade Name → Σ col E
    for r in file_rows:
        name = _R()._mtm_norm_party(_R()._cc_cell(r, 0))
        num  = _R()._mtm_parse_num(_R()._cc_cell(r, _MTM_HYB_VALUE_COL))
        if not name or num is None:
            continue                                     # header / blank line
        sums[name] = sums.get(name, 0.0) + num
    vmap = {}                                            # B3 ID → summed value
    for m in mapping:
        key = _R()._mtm_norm_party(m.get('trade_name'))
        b3  = str(m.get('b3_id') or '').strip().upper()
        if b3 and key in sums:
            vmap[b3] = vmap.get(b3, 0.0) + sums[key]
    matched = zeros = missing = 0
    for row in hyb_rows:
        cid = str(row[0] or '').strip().upper()
        if cid in vmap:
            v = round(vmap[cid], 2)
            if v == 0:                                     # keep 0.00 in the table (the
                row[_MTM_COMMENT_IDX] = _MTM_ZERO_COMMENT  # preview/file registers 1 cent)
                zeros += 1
            row[_MTM_VALOR_IDX] = '{:,.2f}'.format(v)
            matched += 1
        else:
            row[-4] = _MTM_STATUS_MISSING
            missing += 1
    return matched, zeros, missing

def _mtm_path_for(ymd):
    return _R().os.path.join(MTM_JSON_ROOT, ymd[:4], ymd[4:6], ymd[6:8], 'mtm_swap_{}.json'.format(ymd))

def _mtm_source_dir(ymd):
    ref = _R().datetime.strptime(ymd, '%Y%m%d')
    month_folder = ref.strftime('%m') + '. ' + _R()._EN_MONTH_NAMES[ref.month - 1]
    return _R().os.path.join(MTM_SOURCE_ROOT, ref.strftime('%Y'), month_folder, ref.strftime('%d'))

def _mtm_is_swap_name(n):
    return 'sematualmid' in (n or '').lower()

def _mtm_is_coe_name(n):
    nl = (n or '').lower()
    return 'coe' in nl and ('consultamtmcoe' in nl or 'swap-coe' in nl)

def _mtm_coe_refdate():
    """Last ANBIMA business day of the PENULTIMATE month vs. today (e.g. Jul → May)."""
    now = _R().datetime.now()
    y, m = now.year, now.month - 2
    while m <= 0:
        m += 12
        y -= 1
    return _R()._last_anbima_bizday_of_month(y, m).date()

def _mtm_build_swap(rows):
    """Split swap rows into the four LOB books via the latest SWAP position join."""
    records, ref_date = _R()._swap_pos_latest_records()
    lob_map = _R()._swap_pos_lob_map(records)
    buckets = {k: [] for k in _MTM_SWAP_BOOKS}
    kept = matched = 0
    for row in rows:
        a_raw = _R()._cc_cell(row, 0)
        if not a_raw and not any(_R()._cc_cell(row, c) for c in _MTM_DISPLAY_SRC if c is not None):
            continue                                     # blank line
        if _R()._acc_digits(_R()._cc_cell(row, _MTM_FILTER_COL)) != _MTM_ACCOUNT:
            continue                                     # col D: house account only
        kept += 1
        contract = a_raw.replace('#', '').strip()        # col A: drop '#'
        ident = lob_map.get(contract.upper()) or lob_map.get('#' + _R()._acc_digits(contract))
        lob = _R()._accrual_lob(ident)
        if not lob:
            continue                                     # IF not found / unclassified
        matched += 1
        cells = []
        for src in _MTM_DISPLAY_SRC:
            if src is None:  cells.append('')
            elif src == 0:   cells.append(contract)
            else:            cells.append(_R()._cc_cell(row, src))
        buckets[lob].append(cells)
    return buckets, ref_date, kept, matched

def _mtm_build_coe(rows):
    """COE rows whose col G reference date == last ANBIMA bizday of the penultimate month."""
    tgt = _mtm_coe_refdate()
    out = []
    for row in rows:
        a_raw = _R()._cc_cell(row, 0)
        if not a_raw and not any(_R()._cc_cell(row, c) for c in _MTM_COE_SRC if c is not None):
            continue
        g = _R()._parse_date_any(_R()._cc_cell(row, _MTM_COE_REFDATE_COL))
        if g is None or g != tgt:
            continue
        cells = []
        for src in _MTM_COE_SRC:
            if src is None:  cells.append('')
            elif src == 0:   cells.append(a_raw.replace('#', '').strip())
            else:            cells.append(_R()._cc_cell(row, src))
        out.append(cells)
    return out, tgt.strftime('%Y-%m-%d')

def _mtm_finalize(buckets):
    """Append [status, maker, checker, id] to each row; return per-book counts."""
    for lob, rws in buckets.items():
        for i, rw in enumerate(rws):
            rw.extend(['New', '', ''])
            rw.append('{}-{}'.format(lob, i))
    return {k: len(v) for k, v in buckets.items()}

def _mtm_normalize_zeros(data):
    """Belt-and-suspenders: any STORED Valor MTM that is exactly zero is KEPT as
    0.00 in the table (canonical #,##0.00 format) + the zero comment, across every
    book. The value is inserted exactly as it comes from the spreadsheet; only the
    preview and generated files bump a zero to 1 in the last decimal place (B3
    rejects a zero MtM) — see _mtm_gen_min_value. Blank (unfilled / 'Missing MtM')
    cells are left untouched. Returns the count normalized."""
    n = 0
    for lob, table in (data.get('tables') or {}).items():
        vidx = _MTM_COE_VALOR_IDX if lob == 'COE' else _MTM_VALOR_IDX
        cidx = _MTM_COE_COMMENT_IDX if lob == 'COE' else _MTM_COMMENT_IDX
        for r in table or []:
            if not r or len(r) <= vidx:
                continue
            raw = '' if r[vidx] is None else str(r[vidx]).strip()
            if raw == '':
                continue                                   # blank / Missing → leave as-is
            v = _R()._mtm_parse_num(raw)
            if v is not None and round(v, 2) == 0:
                r[vidx] = '{:,.2f}'.format(0.0)            # keep 0.00 in the table
                if len(r) > cidx and not str(r[cidx] or '').strip():
                    r[cidx] = _MTM_ZERO_COMMENT
                n += 1
    return n

def _mtm_build_from_folder(folder):
    files = [fn for fn in _R().os.listdir(folder) if _R().os.path.isfile(_R().os.path.join(folder, fn))]
    swap_fn = next((fn for fn in files if _mtm_is_swap_name(fn)), None)
    coe_fn  = next((fn for fn in files if _mtm_is_coe_name(fn)), None)
    buckets = {k: [] for k in _MTM_SWAP_BOOKS}
    buckets['COE'] = []
    ref_date = coe_ref = None
    kept = matched = 0
    if swap_fn:
        with open(_R().os.path.join(folder, swap_fn), 'rb') as fh:
            rows = _R()._cc_read_rows(swap_fn, fh.read())
        sb, ref_date, kept, matched = _mtm_build_swap(rows)
        buckets.update(sb)
    if coe_fn:
        with open(_R().os.path.join(folder, coe_fn), 'rb') as fh:
            rows = _R()._cc_read_rows(coe_fn, fh.read())
        buckets['COE'], coe_ref = _mtm_build_coe(rows)
    # CEM MtM values (VCP_CETIP_MTM) — applied to the CEM book before finalize.
    # Finalize FIRST (adds status/meta) so the value files can set 'Missing MtM'.
    counts = _mtm_finalize(buckets)
    cem_val_fn = next((fn for fn in files if _mtm_is_cem_value_name(fn)), None)
    cem_matched = cem_zeros = cem_missing = 0
    if cem_val_fn and buckets.get('CEM'):
        with open(_R().os.path.join(folder, cem_val_fn), 'rb') as fh:
            vrows = _R()._cc_read_rows(cem_val_fn, fh.read())
        cem_matched, cem_zeros, cem_missing = _mtm_apply_cem_values(buckets['CEM'], vrows)
    edg_val_fn = next((fn for fn in files if _mtm_is_edg_value_name(fn)), None)
    edg_matched = edg_coe_matched = edg_missing = 0
    if edg_val_fn:
        with open(_R().os.path.join(folder, edg_val_fn), 'rb') as fh:
            erows = _R()._cc_read_rows(edg_val_fn, fh.read())
        edg_matched, edg_coe_matched, _ez, edg_missing = _mtm_apply_edg_values({'tables': buckets}, erows)
    # Hybrids MtM values (Stream_level_MTM) — SUMIF by Trade Name via mapping_swap-hyb.json.
    hyb_val_fn = next((fn for fn in files if _mtm_is_hyb_value_name(fn)), None)
    hyb_matched = hyb_zeros = hyb_missing = 0
    if hyb_val_fn and buckets.get('Hybrids'):
        with open(_R().os.path.join(folder, hyb_val_fn), 'rb') as fh:
            hrows = _R()._cc_read_rows(hyb_val_fn, fh.read())
        hyb_matched, hyb_zeros, hyb_missing = _mtm_apply_hyb_values(
            buckets['Hybrids'], hrows, _mtm_load_hyb_mapping())
    # Final guard: canonicalize any zero MtM to 0.00 + zero comment (the table keeps
    # the exact spreadsheet value; the preview/files bump it to 1 cent when generated).
    _mtm_normalize_zeros({'tables': buckets})
    return {
        'success': True, 'tables': buckets, 'counts': counts,
        'ref_date': ref_date, 'coe_ref_date': coe_ref,
        'diagnostics': {'kept': kept, 'matched': matched,
                        'swap_file': swap_fn, 'coe_file': coe_fn,
                        'cem_value_file': cem_val_fn,
                        'cem_matched': cem_matched, 'cem_zeros': cem_zeros, 'cem_missing': cem_missing,
                        'edg_value_file': edg_val_fn,
                        'edg_matched': edg_matched, 'edg_coe_matched': edg_coe_matched,
                        'edg_missing': edg_missing,
                        'hyb_value_file': hyb_val_fn,
                        'hyb_matched': hyb_matched, 'hyb_zeros': hyb_zeros,
                        'hyb_missing': hyb_missing},
    }, (swap_fn, coe_fn)

def _mtm_save(path, data):
    """Persist the MtM dataset, creating the YYYY/MM/DD dir first (mkstemp needs it).
    Trava por conta própria; como _cache_lock é RLock, isso não conflita com o
    caller que já tranca o ciclo ler → alterar → gravar (o correto, e o que todos
    fazem hoje). Aqui é só a garantia de que uma gravação nunca sai sem lock."""
    with _R()._cache_lock:
        _R().os.makedirs(_R().os.path.dirname(path), exist_ok=True)
        _R()._atomic_write_json(path, data)

def _mtm_load(date_str):
    ymd = _R()._accrual_parse_date(date_str) or _R().datetime.now().strftime('%Y%m%d')
    path = _mtm_path_for(ymd)
    if not _R().os.path.isfile(path):
        return None, None
    try:
        with open(path, encoding='utf-8') as fh:
            return path, _R().json.load(fh)
    except Exception:
        _R().log.error('[mtm] read failed %s:\n%s', path, _R().traceback.format_exc())
        return None, None

def _mtm_latest_ymd():
    latest = None
    if not _R().os.path.isdir(MTM_JSON_ROOT):
        return None
    for _root, _dirs, files in _R().os.walk(MTM_JSON_ROOT):
        for fn in files:
            m = _R().re.match(r'mtm_swap_(\d{8})\.json$', fn)
            if m and (latest is None or m.group(1) > latest):
                latest = m.group(1)
    return '{}-{}-{}'.format(latest[:4], latest[4:6], latest[6:8]) if latest else None

def _mtm_find_row(data, lob, rid):
    for r in (data.get('tables') or {}).get(lob, []) or []:
        if r and str(r[-1]) == str(rid):
            return r
    return None

_MTM_GEN_LAWTON_ACCT  = '00041007'                   # Lawton  = 00041.00-7

_MTM_GEN_ATACAMA_ACCT = {'85398005'}                 # Atacama = 85398.00-5

_MTM_GEN_PARTY = {                                   # Nome Simplificado Parte (20 chars)
    'BANCO':   'JPMORGANBM'       + ' ' * 10,
    'LAWTON':  'INTRAGLAWTONFDO'  + ' ' * 5,
    'ATACAMA': 'INTRAGATACAMAFDO' + ' ' * 4,
}

_MTM_GEN_PARTY_ACCT = {                              # Código Conta Parte per view
    'BANCO': '73760009', 'LAWTON': '00041007', 'ATACAMA': '85398005',
}

_MTM_GEN_BOOK_SUFFIX = {'EDG': 'EDG', 'CEM': 'CEM', 'Hybrids': 'HYB'}

_MTM_GEN_BOOK_CPTY = {'EDG': 'ATACAMA', 'CEM': 'LAWTON', 'Hybrids': 'LAWTON'}

_MTM_FI_KEY = 'mid-informacoes-derivativos'

_MTM_GEN_COE_COLS  = ['Tipo IF', 'Tipo de Linha', 'Código operação', 'Código do Instrumento Financeiro',
                      'Conta do Emissor', 'Data Referência', 'Valor MTM', 'Débito/Crédito']

def _mtm_fi_registro_fields():
    """Campos do bloco de registro do cadastro MID — rótulos (preview) e
    larguras (fatiar a linha pronta de volta em células)."""
    tpl = _R()._fi_tpl_cached(_MTM_FI_KEY)
    block = next((b for b in (tpl or {}).get('blocks', [])
                  if b.get('id') == 'registro-emissao'), None)
    if block is None:
        raise ValueError('file-interpreter template missing: {}/registro-emissao'.format(_MTM_FI_KEY))
    return block.get('fields', [])

def _mtm_gen_min_value(v):
    """Zero MtM → the smallest registrable amount (1 in the last available decimal
    place, i.e. 0.01), since B3 rejects a zero MtM. Applied ONLY when generating the
    preview / file — the table keeps the spreadsheet's exact 0.00. Non-zero values
    pass through unchanged."""
    v = v or 0.0
    return 0.01 if round(v, 2) == 0 else v

def _mtm_valor_fixed(v, int_digits):
    """Absolute value as (int_digits + 2) zero-padded digits (implicit 2 decimals)."""
    return str(int(round(abs(v or 0.0) * 100))).zfill(int_digits + 2)

def _mtm_rand_meunum():
    return ''.join(_R().random.choice('0123456789') for _ in range(10))

def _mtm_cpty_of(row):
    """Lawton / Atacama / None from the book row's CONTRAPARTE / Conta (idx 4)."""
    acct = _R()._acc_digits(row[4] if len(row) > 4 else '')
    if acct == _MTM_GEN_LAWTON_ACCT:
        return 'LAWTON'
    if acct in _MTM_GEN_ATACAMA_ACCT:
        return 'ATACAMA'
    return None

def _mtm_swap_line(cid, party_key, sinal, v, ymd):
    """UMA linha de registro (tipo 1): literais Fixed saem do cadastro; os
    valores calculados entram por seq e são usados verbatim — byte a byte o
    que sempre foi enviado."""
    return _R()._fi_build_line(_MTM_FI_KEY, 'registro-emissao', {
        '4': _mtm_rand_meunum(), '5': str(cid or ''),
        '6': _MTM_GEN_PARTY[party_key], '7': _MTM_GEN_PARTY_ACCT[party_key],
        '8': sinal, '9': _mtm_valor_fixed(_mtm_gen_min_value(v), 10),
        '12': ymd,
    }, page_url='/mtm-swap')

def _mtm_swap_header(party_key, today):
    """Linha de header (tipo 0) — literais e larguras do cadastro; participante
    e data entram por seq."""
    return _R()._fi_build_line(_MTM_FI_KEY, 'header',
                          {'4': _MTM_GEN_PARTY[party_key], '5': today},
                          page_url='/mtm-swap')

def _mtm_coe_header(today):
    return 'COE' + '  ' + '0' + '0475' + _MTM_GEN_PARTY['BANCO'] + today

def _mtm_generate_book(book_key, rows, ymd):
    """Files for one swap book: MtM_BANCO-<suffix> always; plus the book's fixed
    counterparty file (EDG→Atacama, CEM/Hybrids→Lawton) with the mirror rows
    (opposite sign) for that book's intragroup contracts."""
    suffix = _MTM_GEN_BOOK_SUFFIX.get(book_key)
    if not suffix:
        return {}
    book_cpty = _MTM_GEN_BOOK_CPTY.get(book_key)     # ATACAMA (EDG) / LAWTON (CEM,HYB)
    today = _R().datetime.now().strftime('%Y%m%d')
    banco = 'MtM_BANCO-' + suffix
    files = {banco: {'view': 'BANCO',
                     'header': _mtm_swap_header('BANCO', today), 'lines': []}}
    for row in rows:
        v = _R()._mtm_parse_num(row[7]) or 0.0            # Valor MTM (display) → float
        cid = row[0]
        sinal = '00' if v >= 0 else '01'
        files[banco]['lines'].append(_mtm_swap_line(cid, 'BANCO', sinal, v, ymd))
        # Mirror only the rows whose counterparty matches the book's fixed side.
        if book_cpty and _mtm_cpty_of(row) == book_cpty:
            fn = 'MtM_' + book_cpty + '-' + suffix
            files.setdefault(fn, {'view': book_cpty,
                                  'header': _mtm_swap_header(book_cpty, today), 'lines': []})
            files[fn]['lines'].append(_mtm_swap_line(cid, book_cpty, '01' if v >= 0 else '00', v, ymd))
    return files

def _mtm_generate_coe(rows, ymd):
    today = _R().datetime.now().strftime('%Y%m%d')
    f = {'view': 'BANCO', 'cols': _MTM_GEN_COE_COLS, 'header': _mtm_coe_header(today), 'rows': []}
    for row in rows:
        v = _R()._mtm_parse_num(row[_MTM_COE_VALOR_IDX]) or 0.0
        f['rows'].append({
            'Tipo IF': 'COE  ', 'Tipo de Linha': '1', 'Código operação': '0475',
            'Código do Instrumento Financeiro': str(row[0] or ''), 'Conta do Emissor': '73760401',
            'Data Referência': ymd, 'Valor MTM': _mtm_valor_fixed(_mtm_gen_min_value(v), 16),
            'Débito/Crédito': '+' if v >= 0 else '-',
        })
    return {'MtM_BANCO-COE': f}

def _mtm_file_lines(fdata):
    if 'lines' in fdata:                             # MID: linha pronta pelo cadastro
        return [fdata['header']] + fdata['lines']
    return [fdata['header']] + [''.join(r[c] for c in fdata['cols']) for r in fdata['rows']]

def _mtm_write_gen_files(files, ymd):
    """Write each file (.txt, Latin-1, CRLF) to CONECTA_NEW_PATH and the day's MTM
    source folder. Returns list of written paths (best-effort)."""
    dests = [_R().CONECTA_NEW_PATH, _mtm_source_dir(ymd)]
    written = []
    for fname, fdata in files.items():
        content = '\r\n'.join(_mtm_file_lines(fdata)) + '\r\n'
        for d in dests:
            try:
                _R().os.makedirs(d, exist_ok=True)
                path = _R().os.path.join(d, fname + '.txt')
                with open(path, 'w', encoding='latin-1', newline='') as fh:
                    fh.write(content)
                written.append(path)
            except Exception:
                _R().log.error('[mtm] write %s → %s failed:\n%s', fname, d, _R().traceback.format_exc())
    return written

def _mtm_gen_preview(files):
    """Preview payload: per file, the parsed columns/rows for the modal table.
    Arquivos MID são fatiados de volta da linha PRONTA pelas larguras do
    cadastro — os rótulos vêm dos `field` do template, então renomear/editar
    pela tela muda o preview no próximo duplo clique."""
    out = []
    for fn, fd in files.items():
        if 'lines' in fd:
            cols, cuts, pos = [], [], 0
            for f in _mtm_fi_registro_fields():
                w = _R()._fi_width(f.get('format')) or 0
                cols.append(f.get('field', ''))
                cuts.append((pos, pos + w))
                pos += w
            rows = [[ln[a:b] for a, b in cuts] for ln in fd['lines']]
        else:
            cols = fd['cols']
            rows = [[r[c] for c in fd['cols']] for r in fd['rows']]
        out.append({'filename': fn + '.txt', 'view': fd['view'], 'cols': cols,
                    'header': fd['header'], 'rows': rows})
    return out

_MTM_VAL_BOOKS = ('CEM', 'EDG', 'Hybrids')           # swap books (+ COE handled apart)

def _mtm_missing_rows(data, books):
    """Rows still flagged 'Missing MtM' (no MtM value) across the given books."""
    out, tables = [], (data.get('tables') or {})
    for lob in books:
        for r in tables.get(lob, []) or []:
            if r and str(r[-4] or '').strip().lower().startswith('missing'):
                out.append({'lob': lob, 'codigo': str(r[0] or ''), 'id': str(r[-1])})
    return out

def _mtm_check_status_rows(data):
    """(checks, uncommented) — rows whose status is 'Check' (recon divergence).
    MtM row = data cells + [status(-4), maker(-3), checker(-2), id(-1)]; Comments = -5."""
    checks, pending = [], []
    for lob, table in (data.get('tables') or {}).items():
        for r in table or []:
            if not r or len(r) < 5:
                continue
            if str(r[-4] or '').strip().lower() == 'check':
                comment = str(r[-5] or '').strip()
                item = {'id': str(r[-1]), 'lob': lob, 'codigo': str(r[0] or ''), 'comment': comment}
                checks.append(item)
                if not comment:
                    pending.append(item)
    return checks, pending

def _send_mtm_validation_email(subject, html, logo_path, attach_paths):
    """SMTP-only MtM EOM validation e-mail to Brazil OTC Ops, attaching the
    Lawton/Atacama view files. HTML/logo resolved by the caller. Best-effort."""
    from email.mime.image import MIMEImage
    from email.mime.base import MIMEBase
    from email import encoders
    try:
        msg = _R().MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = _R().SHARED_MAILBOX
        msg['To'] = _R().CETIP_OTC_OPS_EMAIL
        related = _R().MIMEMultipart('related')
        alt = _R().MIMEMultipart('alternative')
        alt.attach(_R().MIMEText('MtM EOM validation files attached.', 'plain', 'utf-8'))
        alt.attach(_R().MIMEText(html, 'html', 'utf-8'))
        related.attach(alt)
        if logo_path:
            with open(logo_path, 'rb') as f:
                img = MIMEImage(f.read())
            img.add_header('Content-ID', '<otc_logo>')
            img.add_header('Content-Disposition', 'inline', filename='logo.png')
            related.attach(img)
        _R()._attach_email_gradient(related)
        msg.attach(related)
        for path in attach_paths:
            try:
                with open(path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', 'attachment', filename=_R().os.path.basename(path))
                msg.attach(part)
            except Exception:
                _R().log.warning('[mtm] could not attach %s:\n%s', path, _R().traceback.format_exc())
        with _R().smtplib.SMTP(_R().SMTP_HOST, _R().SMTP_PORT, timeout=20) as server:
            server.sendmail(_R().SHARED_MAILBOX, [_R().CETIP_OTC_OPS_EMAIL], msg.as_string())
        _R().log.info('[mtm] validation e-mail sent to %s', _R().CETIP_OTC_OPS_EMAIL)
        return True
    except Exception:
        _R().log.error('[mtm] validation e-mail FAILED:\n%s', _R().traceback.format_exc())
        return False

def _send_mtm_endprocess_email(subject, html, logo_path):
    """SMTP-only MtM EOM final-status e-mail to Brazil OTC Ops. Best-effort."""
    from email.mime.image import MIMEImage
    try:
        msg = _R().MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = _R().SHARED_MAILBOX
        msg['To'] = _R().CETIP_OTC_OPS_EMAIL
        msg['Cc'] = ', '.join(_R()._ACC_ENDPROC_CC)               # same From/To/Cc as accrual end-process
        related = _R().MIMEMultipart('related')
        alt = _R().MIMEMultipart('alternative')
        alt.attach(_R().MIMEText('MtM Swap EOM final status.', 'plain', 'utf-8'))
        alt.attach(_R().MIMEText(html, 'html', 'utf-8'))
        related.attach(alt)
        if logo_path:
            with open(logo_path, 'rb') as f:
                img = MIMEImage(f.read())
            img.add_header('Content-ID', '<otc_logo>')
            img.add_header('Content-Disposition', 'inline', filename='logo.png')
            related.attach(img)
        _R()._attach_email_gradient(related)
        msg.attach(related)
        recipients = [_R().CETIP_OTC_OPS_EMAIL] + _R()._ACC_ENDPROC_CC
        with _R().smtplib.SMTP(_R().SMTP_HOST, _R().SMTP_PORT, timeout=20) as server:
            server.sendmail(_R().SHARED_MAILBOX, recipients, msg.as_string())
        _R().log.info('[mtm] end-process e-mail sent to %s (cc %s)', _R().CETIP_OTC_OPS_EMAIL, _R()._ACC_ENDPROC_CC)
        return True
    except Exception:
        _R().log.error('[mtm] end-process e-mail FAILED:\n%s', _R().traceback.format_exc())
        return False

def _mtm_is_recon_name(n):
    return 'consultainformacoesatualizmid' in _R()._mtm_norm_party(n)

def _mtm_recon_key(s):
    """Contract-ID match key: drop the '#' (replace with nothing) and normalize to
    match the page's Código IF."""
    return str(s or '').replace('#', '').strip().strip("'").strip('"').upper()

def _mtm_run_recon(data, rows):
    """Build {ID → registered MtM} from the ConsultaInformacoesAtualizMID rows (house
    account only) and flag each page row Success/Check by value equality. Mutates
    data (recon map + status). Returns a summary dict."""
    fmap = {}
    for i in range(_MTM_RECON_DATA_ROW, len(rows)):
        row = rows[i]
        if _R()._acc_digits(_R()._cc_cell(row, _MTM_FILTER_COL)) != _MTM_ACCOUNT:      # col D
            continue
        key = _mtm_recon_key(_R()._cc_cell(row, 0))                              # col A
        val = _mtm_parse_num_br(_R()._cc_cell(row, _MTM_RECON_VALUE_COL))        # col G (BRL format)
        if not key or val is None:
            continue
        fmap.setdefault(key, round(val, 2))

    recon_out, ok_rows, check_rows = {}, 0, 0
    for lob, table in (data.get('tables') or {}).items():
        vidx = _MTM_COE_VALOR_IDX if lob == 'COE' else _MTM_VALOR_IDX
        for r in table or []:
            if not r or len(r) < 5:
                continue
            key = _mtm_recon_key(r[0])
            if key not in fmap:
                continue
            fv = fmap[key]
            pv = _R()._mtm_parse_num(r[vidx])
            # Compare against the value we'd register: a page 0.00 is generated as
            # 0.01 (B3 rejects a zero MtM), so it should reconcile with the file's 0.01.
            ok = (pv is not None and round(_mtm_gen_min_value(pv), 2) == fv)
            recon_out[str(r[-1])] = {'ok': ok, 'file': '{:,.2f}'.format(fv)}
            r[-4] = 'Success' if ok else 'Check'                            # status
            if ok: ok_rows += 1
            else:  check_rows += 1
    data['recon'] = recon_out
    return {'success_rows': ok_rows, 'check_rows': check_rows, 'map_entries': len(fmap)}

def _mtm_find_recon_file(folder):
    if not _R().os.path.isdir(folder):
        return None
    for fn in _R().os.listdir(folder):
        if _R().os.path.isfile(_R().os.path.join(folder, fn)) and _mtm_is_recon_name(fn):
            return _R().os.path.join(folder, fn)
    return None
