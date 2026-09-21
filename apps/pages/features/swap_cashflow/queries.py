# -*- coding: utf-8 -*-
"""Leituras do Swap Cashflow: os deals do(s) arquivo(s)-dia, o finder pelo
`_id`, e os cadastros que o gerador consulta — os do Bullet pela horizontal
(`platform/swap_new_deals`), mais o tipo de amortização."""
from datetime import datetime

from apps.pages import data_store as _store
from apps.pages.platform import swap_new_deals as _sw
from apps.pages.features.swap_cashflow import domain
from apps.pages.features.swap_cashflow.infra import persistence


def _R():
    from apps.pages import routes
    return routes


def entries(date_str='', date_from='', date_to=''):
    """Os deals: de UM dia (`date`), de um intervalo, ou de toda a árvore."""
    out = []
    if date_from or date_to:
        d_from = _R()._parse_date_any(date_from)
        d_to = _R()._parse_date_any(date_to)
        dias = list(_R()._day_files(persistence.cache_dir(), persistence.SUFFIX, d_from, d_to))
        _R()._day_prefetch(dias)
        for fp, fname, mtime, size in dias:
            fdate = _R()._parse_date_any(fname[:8])
            if fdate is None or (d_from and fdate < d_from) or (d_to and fdate > d_to):
                continue
            out.extend(_R()._day_json(fp, mtime, size))
    elif date_str:
        ref = _R()._parse_date_any(date_str)
        if ref is None:
            return []
        fp = persistence.day_path(datetime(ref.year, ref.month, ref.day))
        try:
            st = _store.stat(fp)
        except OSError:
            return []
        out.extend(_R()._day_json(fp, st.st_mtime, st.st_size))
    else:
        dias = list(_R()._day_files(persistence.cache_dir(), persistence.SUFFIX))
        _R()._day_prefetch(dias)
        for fp, _fname, mtime, size in dias:
            out.extend(_R()._day_json(fp, mtime, size))
    return [dict(e) for e in out if isinstance(e, dict) and persistence.key_of(e)]


def find(deal_id, trade_date=''):
    """(caminho, lista MUTÁVEL, índice) do deal — pelo arquivo-dia da Trade
    Date quando ela vem; senão varre a árvore. (None, [], None) se não há."""
    deal_id = str(deal_id or '').strip()
    if not deal_id:
        return None, [], None
    cand = []
    ref = _R()._parse_date_any(trade_date) if trade_date else None
    if ref is not None:
        cand.append(persistence.day_path(datetime(ref.year, ref.month, ref.day)))
    else:
        cand.extend(fp for fp, _n, _m, _s in _R()._day_files(persistence.cache_dir(), persistence.SUFFIX))
    for fp in cand:
        try:
            lst = _store.read(fp)
        except FileNotFoundError:
            continue
        except _store.BancoOcupado:
            raise
        except Exception:                                   # noqa: BLE001
            continue
        if not isinstance(lst, list):
            continue
        for i, e in enumerate(lst):
            if isinstance(e, dict) and persistence.key_of(e) == deal_id:
                return fp, lst, i
    if ref is not None:
        return find(deal_id, '')
    return None, [], None


# ── Cadastros ────────────────────────────────────────────────────────────────

own_accounts = _sw.own_accounts
le_by_spn = _sw.le_by_spn
refdata_by_spn = _sw.refdata_by_spn
template_blocks = _sw.template_blocks


def amortization_rows():
    """As linhas do cadastro `swap-amortizacao` (CODE × LABEL)."""
    return _R()._mapping_rows('swap-amortizacao') or []


def codes_for(deal):
    """Os códigos B3 do deal: os do Bullet (`platform/swap_new_deals.codes_for`)
    mais o do Tipo de Amortização (`amortization`, 9(02) do 0034)."""
    codes = dict(_sw.codes_for(deal))
    codes['amortization'] = domain.amortization_code(amortization_rows(), deal.get('AmortizationType', ''))
    return codes
