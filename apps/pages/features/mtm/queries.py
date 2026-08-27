# -*- coding: utf-8 -*-
"""As leituras que montam o MtM do dia — a tabela de Swap (posição × LOB), a de
COE, a normalização dos zeros e a varredura da pasta de origem.
"""
import os
from datetime import datetime

from apps.pages.features.mtm import domain
from apps.pages.features.mtm.infra import mappers

def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _mtm_coe_refdate():
    """Last ANBIMA business day of the PENULTIMATE month vs. today (e.g. Jul → May)."""
    now = datetime.now()
    y, m = now.year, now.month - 2
    while m <= 0:
        m += 12
        y -= 1
    return _R()._last_anbima_bizday_of_month(y, m).date()


def _mtm_build_swap(rows):
    """Split swap rows into the four LOB books via the latest SWAP position join."""
    records, ref_date = _R()._swap_pos_latest_records()
    lob_map = _R()._swap_pos_lob_map(records)
    buckets = {k: [] for k in domain._MTM_SWAP_BOOKS}
    kept = matched = 0
    for row in rows:
        a_raw = _R()._cc_cell(row, 0)
        if not a_raw and not any(_R()._cc_cell(row, c) for c in domain._MTM_DISPLAY_SRC if c is not None):
            continue                                     # blank line
        if _R()._acc_digits(_R()._cc_cell(row, domain._MTM_FILTER_COL)) != domain._MTM_ACCOUNT:
            continue                                     # col D: house account only
        kept += 1
        contract = a_raw.replace('#', '').strip()        # col A: drop '#'
        ident = lob_map.get(contract.upper()) or lob_map.get('#' + _R()._acc_digits(contract))
        lob = _R()._accrual_lob(ident)
        if not lob:
            continue                                     # IF not found / unclassified
        matched += 1
        cells = []
        for src in domain._MTM_DISPLAY_SRC:
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
        if not a_raw and not any(_R()._cc_cell(row, c) for c in domain._MTM_COE_SRC if c is not None):
            continue
        g = _R()._parse_date_any(_R()._cc_cell(row, domain._MTM_COE_REFDATE_COL))
        if g is None or g != tgt:
            continue
        cells = []
        for src in domain._MTM_COE_SRC:
            if src is None:  cells.append('')
            elif src == 0:   cells.append(a_raw.replace('#', '').strip())
            else:            cells.append(_R()._cc_cell(row, src))
        out.append(cells)
    return out, tgt.strftime('%Y-%m-%d')


def _mtm_normalize_zeros(data):
    """Belt-and-suspenders: any STORED Valor MTM that is exactly zero is KEPT as
    0.00 in the table (canonical #,##0.00 format) + the zero comment, across every
    book. The value is inserted exactly as it comes from the spreadsheet; only the
    preview and generated files bump a zero to 1 in the last decimal place (B3
    rejects a zero MtM) — see _mtm_gen_min_value. Blank (unfilled / 'Missing MtM')
    cells are left untouched. Returns the count normalized."""
    n = 0
    for lob, table in (data.get('tables') or {}).items():
        vidx = domain._MTM_COE_VALOR_IDX if lob == 'COE' else domain._MTM_VALOR_IDX
        cidx = domain._MTM_COE_COMMENT_IDX if lob == 'COE' else domain._MTM_COMMENT_IDX
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
                    r[cidx] = domain._MTM_ZERO_COMMENT
                n += 1
    return n


def _mtm_build_from_folder(folder):
    files = [fn for fn in os.listdir(folder) if os.path.isfile(os.path.join(folder, fn))]
    swap_fn = next((fn for fn in files if domain._mtm_is_swap_name(fn)), None)
    coe_fn  = next((fn for fn in files if domain._mtm_is_coe_name(fn)), None)
    buckets = {k: [] for k in domain._MTM_SWAP_BOOKS}
    buckets['COE'] = []
    ref_date = coe_ref = None
    kept = matched = 0
    if swap_fn:
        with open(os.path.join(folder, swap_fn), 'rb') as fh:
            rows = _R()._cc_read_rows(swap_fn, fh.read())
        sb, ref_date, kept, matched = _mtm_build_swap(rows)
        buckets.update(sb)
    if coe_fn:
        with open(os.path.join(folder, coe_fn), 'rb') as fh:
            rows = _R()._cc_read_rows(coe_fn, fh.read())
        buckets['COE'], coe_ref = _mtm_build_coe(rows)
    # CEM MtM values (VCP_CETIP_MTM) — applied to the CEM book before finalize.
    # Finalize FIRST (adds status/meta) so the value files can set 'Missing MtM'.
    counts = domain._mtm_finalize(buckets)
    cem_val_fn = next((fn for fn in files if domain._mtm_is_cem_value_name(fn)), None)
    cem_matched = cem_zeros = cem_missing = 0
    if cem_val_fn and buckets.get('CEM'):
        with open(os.path.join(folder, cem_val_fn), 'rb') as fh:
            vrows = _R()._cc_read_rows(cem_val_fn, fh.read())
        cem_matched, cem_zeros, cem_missing = mappers._mtm_apply_cem_values(buckets['CEM'], vrows)
    edg_val_fn = next((fn for fn in files if domain._mtm_is_edg_value_name(fn)), None)
    edg_matched = edg_coe_matched = edg_missing = 0
    if edg_val_fn:
        with open(os.path.join(folder, edg_val_fn), 'rb') as fh:
            erows = _R()._cc_read_rows(edg_val_fn, fh.read())
        edg_matched, edg_coe_matched, _ez, edg_missing = mappers._mtm_apply_edg_values({'tables': buckets}, erows)
    # Hybrids MtM values (Stream_level_MTM) — SUMIF by Trade Name via mapping_swap-hyb.json.
    hyb_val_fn = next((fn for fn in files if domain._mtm_is_hyb_value_name(fn)), None)
    hyb_matched = hyb_zeros = hyb_missing = 0
    if hyb_val_fn and buckets.get('Hybrids'):
        with open(os.path.join(folder, hyb_val_fn), 'rb') as fh:
            hrows = _R()._cc_read_rows(hyb_val_fn, fh.read())
        hyb_matched, hyb_zeros, hyb_missing = mappers._mtm_apply_hyb_values(
            buckets['Hybrids'], hrows, mappers._mtm_load_hyb_mapping())
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
