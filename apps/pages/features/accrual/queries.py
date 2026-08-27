# -*- coding: utf-8 -*-
"""A leitura que monta o Accrual do dia — a posição de swap (VCP) repartida nos
quatro livros de LOB. Sem efeito nenhum: quem grava é `infra/persistence`.
"""
from apps.pages.features.accrual import domain


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _accrual_build_result(rows):
    """Core VCP→tables logic (no I/O). Splits the rows into the four LOB books and
    returns the result dict (without 'date'/'saved_at')."""
    records, ref_date = _R()._swap_pos_latest_records()
    lob_map = _R()._swap_pos_lob_map(records)

    buckets = {'CEM': [], 'EDG': [], 'Hybrids': [], 'Commodities': []}
    total = kept = matched = 0
    for i in range(domain._ACC_HEADER_ROW, len(rows)):
        row = rows[i]
        a_raw = _R()._cc_cell(row, 0)
        if not a_raw and not any(_R()._cc_cell(row, c)
                                 for c in domain._ACC_DISPLAY_SRC if c is not None):
            continue                                    # fully blank line
        total += 1
        contract = a_raw.replace('#', '').strip()       # col A: drop '#'
        if _R()._acc_digits(_R()._cc_cell(row, domain._ACC_ACCOUNT_COL)) not in domain._ACC_ACCOUNTS:
            continue                                    # col K: house accounts only
        kept += 1
        ident = lob_map.get(contract.upper())
        if ident is None:
            ident = lob_map.get('#' + _R()._acc_digits(contract))
        lob = _R()._accrual_lob(ident)
        if not lob:
            continue                                    # IF not found / unclassified
        matched += 1
        # Build the row aligned to _ACC_FIXED_HEADERS (None src → empty placeholder).
        cells = []
        for src in domain._ACC_DISPLAY_SRC:
            if src is None:      cells.append('')
            elif src == 0:       cells.append(contract)         # Código IF (# stripped)
            else:                cells.append(_R()._cc_cell(row, src))
        buckets[lob].append(cells)

    # Append, per row, the maker/checker meta and a stable id as the LAST cell.
    # Row layout: [ ...fixed data cells..., status, maker, checker, id ]
    for _lob, _rws in buckets.items():
        for _i, _rw in enumerate(_rws):
            _rw.extend(['New', '', ''])                # status, maker, checker
            _rw.append('{}-{}'.format(_lob, _i))       # stable id (last cell)

    return {
        'success': True,
        'headers': list(domain._ACC_FIXED_HEADERS),
        'tables': buckets,
        'counts': {k: len(v) for k, v in buckets.items()},
        'ref_date': ref_date,
        'diagnostics': {'total': total, 'kept': kept, 'matched': matched,
                        'position_records': len(records)},
    }
