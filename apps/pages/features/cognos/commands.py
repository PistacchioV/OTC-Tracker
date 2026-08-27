# -*- coding: utf-8 -*-
"""A importação do dia — acha o arquivo na pasta de origem, extrai e grava pelo
store da plataforma.
"""
import os
import traceback
from datetime import datetime



def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _cog_import(ref=None):
    """Find "FXO Detail*.xlsx" in COG_SOURCE_ROOT, extract, write today's JSON."""
    ref = ref or datetime.now()
    if not os.path.isdir(_R().COG_SOURCE_ROOT):
        return {'success': False, 'error': 'Source folder not found: {}'.format(_R().COG_SOURCE_ROOT)}
    matches = sorted(f for f in os.listdir(_R().COG_SOURCE_ROOT)
                     if f.lower().startswith('fxo detail') and f.lower().endswith(('.xlsx', '.xls', '.txt')))
    if not matches:
        return {'success': False, 'error': 'No "FXO Detail*" file found in {}'.format(_R().COG_SOURCE_ROOT)}
    src_path = os.path.join(_R().COG_SOURCE_ROOT, matches[0])
    try:
        rows = _R()._cog_read_rows(src_path)
    except Exception:
        _R().log.warning("[cognos] read failed for %s:\n%s", src_path, traceback.format_exc())
        return {'success': False, 'error': 'Could not read {}'.format(matches[0])}
    out, kept = _R()._cog_extract(rows)
    jp = _R()._cog_json_path(ref)
    _R()._cog_save(jp, out)
    _R()._ds_write_updated(jp, ref.strftime('%H:%M:%S'))
    try:
        os.remove(src_path)
    except OSError:
        _R().log.warning("[cognos] could not delete source %s", src_path)
    _R().log.info("[cognos] imported %s: kept %d → %s", matches[0], kept, jp)
    return {'success': True, 'file': matches[0], 'rows': kept, 'date': ref.strftime('%Y-%m-%d')}
