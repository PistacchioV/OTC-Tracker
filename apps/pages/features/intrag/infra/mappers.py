# -*- coding: utf-8 -*-
"""O CSV de retorno do Batch Conecta → `{chave: B3 ID}`."""
from apps.pages.features.intrag import domain


def _intrag_build_b3_map(csv_path, match_col, match_val, b3_col):
    """Parse the Boletas CSV (no header) → {b3_key → Intrag ID (col A)} for rows whose
    `match_col` equals `match_val`."""
    import csv as _csv
    out = {}
    with open(csv_path, 'r', encoding='latin-1', newline='') as fh:
        sample = fh.read(4096); fh.seek(0)
        delim = ';' if sample.count(';') > sample.count(',') else ','
        for row in _csv.reader(fh, delimiter=delim):
            if len(row) <= max(match_col, b3_col):
                continue
            if str(row[match_col]).strip().upper() != match_val:
                continue
            b3, intrag_id = domain._intrag_b3_key(row[b3_col]), str(row[0]).strip()
            if b3 and intrag_id:
                out.setdefault(b3, intrag_id)
    return out
