# -*- coding: utf-8 -*-
"""Os arquivos-dia do Intrag (um por produto) e a pasta de envio.

A gravação é read-modify-write sob o `_cache_lock` da plataforma, com escrita
atômica — o ciclo INTEIRO travado, senão duas gravações do mesmo dia perdem uma
das duas (§4).
"""
import json
import os
from datetime import datetime
from apps.pages import data_store as _store  # noqa: E402

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
        if _store.exists(file_path):
            try:
                entries = _store.read(file_path)
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


INTRAG_DCE_SWAP_CACHE_DIR = os.path.normpath(os.path.join(
    _R().data_dir(), "cache", "new deals", "Intrag", "DCE Swap"
))


def _intrag_dce_swap_day_path(ref):
    """Caminho do arquivo-dia do DCE Swap para a data `ref` (datetime)."""
    return os.path.join(INTRAG_DCE_SWAP_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'),
                        ref.strftime('%Y%m%d') + '_intrag_dce_swap.json')


def _intrag_dce_swap_upsert(ref, novas):
    """Upsert de deals no arquivo-dia do DCE Swap (chave `_deal`).

    `novas` é a lista de entradas prontas (legs/flows/trade_date). Deal que já
    existe no dia tem legs/flows SUBSTITUÍDOS e a esteira PRESERVADA
    (status/maker/checker/intrag_id) — reimportar a planilha não desfaz
    validação nem mapeamento, como no DCE Option. O ciclo inteiro (ler →
    alterar → gravar) roda sob o `_cache_lock`. → quantidade gravada."""
    file_path = _intrag_dce_swap_day_path(ref)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    n = 0
    with _R()._cache_lock:
        entries = []
        if _store.exists(file_path):
            try:
                entries = _store.read(file_path)
                if not isinstance(entries, list):
                    entries = []
            except (json.JSONDecodeError, ValueError):
                entries = []
        for entry in novas:
            idx = next((i for i, e in enumerate(entries)
                        if e.get('_deal') == entry['_deal']), None)
            if idx is not None:
                for k in ('status', 'maker', 'checker', 'intrag_id'):
                    if entries[idx].get(k):
                        entry[k] = entries[idx][k]
                entries[idx] = entry
            else:
                entries.append(entry)
            n += 1
        _R()._atomic_write_json(file_path, entries)
    _R().log.info('[INTRAG DCE SWAP] Saved %d deal(s) → %s', n, file_path)
    return n
