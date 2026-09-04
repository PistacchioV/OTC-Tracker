# -*- coding: utf-8 -*-
"""Os arquivos-dia do Intrag (um por produto) e a pasta de envio.

A gravação é read-modify-write sob o `_cache_lock` da plataforma, com escrita
atômica — o ciclo INTEIRO travado, senão duas gravações do mesmo dia perdem uma
das duas (§4).
"""
import json
import os
from datetime import datetime

def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


INTRAG_NDF_CACHE_DIR = os.path.normpath(os.path.join(
    _R().data_dir(), "cache", "new deals", "Intrag", "NDF"
))


INTRAG_OPT_CACHE_DIR = os.path.normpath(os.path.join(
    _R().data_dir(), "cache", "new deals", "Intrag", "Option"
))


INTRAG_SWAP_CACHE_DIR = os.path.normpath(os.path.join(
    _R().data_dir(), "cache", "new deals", "Intrag", "Swap"
))


INTRAG_DCE_OPT_CACHE_DIR = os.path.normpath(os.path.join(
    _R().data_dir(), "cache", "new deals", "Intrag", "DCE Option"
))


INTRAG_NDF_SEND_DIR = os.path.join(
    _R().Config.SHARED_DRIVE_ROOT, 'Confirmation', 'Derivativos', 'OTC Tracker', 'Intrag')


def _intrag_ndf_persist(entry, td):
    """Append/update uma entrada no day-file da Intrag NDF (chave = _deal)."""
    ref = td or datetime.now()
    dir_path = os.path.join(INTRAG_NDF_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'))
    os.makedirs(dir_path, exist_ok=True)
    fname = ref.strftime('%Y%m%d') + '_intrag_ndf.json'
    file_path = os.path.join(dir_path, fname)

    with _R()._cache_lock:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as fh:
                    entries = json.load(fh)
                if not isinstance(entries, list):
                    entries = []
            except (json.JSONDecodeError, ValueError):
                entries = []
        else:
            entries = []
        deal_id = entry['_deal']
        idx = next((i for i, e in enumerate(entries) if e.get('_deal') == deal_id), None)
        if idx is not None:
            # Preserve the existing lifecycle state on re-save — only the very
            # first time an entry lands in the JSON does it start as 'New'.
            entry['status']  = entries[idx].get('status') or 'New'
            entry['maker']   = entries[idx].get('maker', '')
            entry['checker'] = entries[idx].get('checker', '')
            entries[idx] = entry
        else:
            entries.append(entry)
        _R()._atomic_write_json(file_path, entries)
    _R().log.info('[INTRAG NDF] Saved entry deal=%r → %s', deal_id, file_path)
