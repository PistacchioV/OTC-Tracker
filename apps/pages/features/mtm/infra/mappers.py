# -*- coding: utf-8 -*-
"""Planilha de valores → a coluna Valor de cada linha, um formato por LOB (CEM,
EDG e Hybrids). O Hybrids ainda passa por um de-para em JSON.
"""
from apps.pages.features.mtm import domain

def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


_MTM_CEM_SELF_PARTY = _R()._mtm_norm_party('Bco J.P. Morgan S.A. 2768 - GEM BR - RATES')


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
                row[domain._MTM_COMMENT_IDX] = domain._MTM_ZERO_COMMENT  # preview/file registers 1 cent)
                zeros += 1
            row[domain._MTM_VALOR_IDX] = '{:,.2f}'.format(v)      # #,##0.00 (comma thousands)
            matched += 1
        else:
            row[-4] = domain._MTM_STATUS_MISSING                  # no MtM value → Missing MtM
            missing += 1
    return matched, zeros, missing


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
                row[domain._MTM_COMMENT_IDX] = domain._MTM_ZERO_COMMENT  # preview/file registers 1 cent)
                zeros += 1
            row[domain._MTM_VALOR_IDX] = '{:,.2f}'.format(v)
            edg_m += 1
        else:
            row[-4] = domain._MTM_STATUS_MISSING
            missing += 1
    for row in tables.get('COE', []) or []:
        cid = str(row[0] or '').strip().upper()
        if cid in fmap:
            v = round(fmap[cid], 2)
            if v == 0:                                     # keep 0.00 in the table (the
                row[domain._MTM_COE_COMMENT_IDX] = domain._MTM_ZERO_COMMENT  # preview/file registers 1 cent)
                zeros += 1
            row[domain._MTM_COE_VALOR_IDX] = '{:,.2f}'.format(v)
            coe_m += 1
        else:
            row[-4] = domain._MTM_STATUS_MISSING
            missing += 1
    return edg_m, coe_m, zeros, missing


_MTM_HYB_MAP_PATH  = _R().data_path('mapping_swap-hyb.json')


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
        num  = _R()._mtm_parse_num(_R()._cc_cell(r, domain._MTM_HYB_VALUE_COL))
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
                row[domain._MTM_COMMENT_IDX] = domain._MTM_ZERO_COMMENT  # preview/file registers 1 cent)
                zeros += 1
            row[domain._MTM_VALOR_IDX] = '{:,.2f}'.format(v)
            matched += 1
        else:
            row[-4] = domain._MTM_STATUS_MISSING
            missing += 1
    return matched, zeros, missing


def _mtm_is_recon_name(n):
    return 'consultainformacoesatualizmid' in _R()._mtm_norm_party(n)
