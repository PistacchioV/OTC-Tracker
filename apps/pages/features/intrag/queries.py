# -*- coding: utf-8 -*-
"""As buscas nos arquivos-dia do Intrag — a linha de um deal (NDF, Opção ou
Swap) e o CSV de retorno da B3 na pasta de export. Sem efeito nenhum.
"""
import json
import os

from apps.pages.features.intrag import domain
from apps.pages.features.intrag.infra import persistence

def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _limpar_info_source(entries, key):
    """As entradas com o Information Source LEGÍVEL (separadores → espaço).

    As linhas gravadas antes da limpeza ainda carregam `[`/`|` no arquivo-dia,
    e é aqui — na leitura — que elas saem certas para a tela sem reescrever
    cache nenhum. A cópia é rasa e só da linha que precisa: as listas vêm do
    memo do daycache, e mutar o dict de lá seria editar o cache compartilhado
    por fora do lock."""
    out = []
    for e in entries:
        if isinstance(e, dict):
            v = e.get(key)
            limpo = domain._intrag_info_source(v)
            if limpo != v:
                e = dict(e)
                e[key] = limpo
        out.append(e)
    return out


def _find_intrag_ndf_entry(deal_id, trade_date):
    """Locate an Intrag NDF entry by deal id (+ optional trade date to narrow the
    daily file). Returns (file_path, entries_list, idx) or (None, None, None)."""
    if not deal_id:
        return None, None, None
    ref = _R()._parse_date_any(trade_date) if trade_date else None
    candidate_files = []
    if ref is not None:
        fp = os.path.join(
            persistence.INTRAG_NDF_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'),
            ref.strftime('%Y%m%d') + '_intrag_ndf.json'
        )
        if os.path.isfile(fp):
            candidate_files.append(fp)
    if not candidate_files and os.path.isdir(persistence.INTRAG_NDF_CACHE_DIR):
        for root, _, files in os.walk(persistence.INTRAG_NDF_CACHE_DIR):
            for fname in files:
                if fname.endswith('_intrag_ndf.json'):
                    candidate_files.append(os.path.join(root, fname))
    for fp in candidate_files:
        try:
            with open(fp, 'r', encoding='utf-8') as fh:
                entries = json.load(fh)
            if not isinstance(entries, list):
                continue
        except (json.JSONDecodeError, ValueError, OSError):
            continue
        idx = next((i for i, e in enumerate(entries) if e.get('_deal') == deal_id), None)
        if idx is not None:
            return fp, entries, idx
    return None, None, None


def _find_intrag_opt_entry(deal_id, trade_date):
    """Locate an Intrag Option entry by deal id (+ optional trade date)."""
    if not deal_id:
        return None, None, None
    ref = _R()._parse_date_any(trade_date) if trade_date else None
    candidate_files = []
    if ref is not None:
        fp = os.path.join(persistence.INTRAG_OPT_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'),
                          ref.strftime('%Y%m%d') + '_intrag_opt.json')
        if os.path.isfile(fp):
            candidate_files.append(fp)
    if not candidate_files and os.path.isdir(persistence.INTRAG_OPT_CACHE_DIR):
        for root, _, files in os.walk(persistence.INTRAG_OPT_CACHE_DIR):
            for fname in files:
                if fname.endswith('_intrag_opt.json'):
                    candidate_files.append(os.path.join(root, fname))
    for fp in candidate_files:
        try:
            with open(fp, 'r', encoding='utf-8') as fh:
                entries = json.load(fh)
            if not isinstance(entries, list):
                continue
        except (json.JSONDecodeError, ValueError, OSError):
            continue
        idx = next((i for i, e in enumerate(entries) if e.get('_deal') == deal_id), None)
        if idx is not None:
            return fp, entries, idx
    return None, None, None


def _find_intrag_dce_opt_entry(deal_id, trade_date):
    """Locate an Intrag DCE Option entry by deal id (= Trade ID do extrato),
    with the optional trade date narrowing the daily file."""
    if not deal_id:
        return None, None, None
    ref = _R()._parse_date_any(trade_date) if trade_date else None
    candidate_files = []
    if ref is not None:
        fp = os.path.join(persistence.INTRAG_DCE_OPT_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'),
                          ref.strftime('%Y%m%d') + '_intrag_dce_opt.json')
        if os.path.isfile(fp):
            candidate_files.append(fp)
    if not candidate_files and os.path.isdir(persistence.INTRAG_DCE_OPT_CACHE_DIR):
        for root, _, files in os.walk(persistence.INTRAG_DCE_OPT_CACHE_DIR):
            for fname in files:
                if fname.endswith('_intrag_dce_opt.json'):
                    candidate_files.append(os.path.join(root, fname))
    for fp in candidate_files:
        try:
            with open(fp, 'r', encoding='utf-8') as fh:
                entries = json.load(fh)
            if not isinstance(entries, list):
                continue
        except (json.JSONDecodeError, ValueError, OSError):
            continue
        idx = next((i for i, e in enumerate(entries) if e.get('_deal') == deal_id), None)
        if idx is not None:
            return fp, entries, idx
    return None, None, None


def _intrag_find_export_csv():
    """Most recent Boletas*.csv in the Return folder, or None."""
    try:
        cands = [os.path.join(_R().RETURN_PATH, fn) for fn in os.listdir(_R().RETURN_PATH)
                 if fn.lower().startswith('boletas') and fn.lower().endswith('.csv')]
    except OSError:
        return None
    cands = [p for p in cands if os.path.isfile(p)]
    return max(cands, key=lambda p: os.path.getmtime(p)) if cands else None


def _find_intrag_swap_entry(deal_id, trade_date):
    """Locate an Intrag Swap entry by deal id (+ optional start date to narrow
    the daily file). Returns (file_path, entries_list, idx) or (None, None, None)."""
    if not deal_id:
        return None, None, None
    ref = _R()._parse_date_any(trade_date) if trade_date else None
    candidate_files = []
    if ref is not None:
        fp = os.path.join(
            persistence.INTRAG_SWAP_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'),
            ref.strftime('%Y%m%d') + '_intrag_swap.json'
        )
        if os.path.isfile(fp):
            candidate_files.append(fp)
    if not candidate_files and os.path.isdir(persistence.INTRAG_SWAP_CACHE_DIR):
        for root, _, files in os.walk(persistence.INTRAG_SWAP_CACHE_DIR):
            for fname in files:
                if fname.endswith('_intrag_swap.json'):
                    candidate_files.append(os.path.join(root, fname))
    for fp in candidate_files:
        try:
            with open(fp, 'r', encoding='utf-8') as fh:
                entries = json.load(fh)
            if not isinstance(entries, list):
                continue
        except (json.JSONDecodeError, ValueError, OSError):
            continue
        idx = next((i for i, e in enumerate(entries) if e.get('_deal') == deal_id), None)
        if idx is not None:
            return fp, entries, idx
    return None, None, None
