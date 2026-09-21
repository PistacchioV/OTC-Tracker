# -*- coding: utf-8 -*-
"""O arquivo-dia do Swap Cashflow: `cache/new deals/Swap/Cashflow/AAAA/MM/
AAAAMMDD_swapcashflow.json`, uma lista de deals. O New Deals Monitor varre
esta pasta (`_NDM_SWAP_DIRS`) e soma a linha no card da LOB dela — Swap CEM
ou Swap Equities (§517)."""
import json
import os

from apps.pages import data_store as _store


def _R():
    from apps.pages import routes
    return routes


SUFFIX = '_swapcashflow.json'


def cache_dir():
    return os.path.normpath(os.path.join(_R().NEW_DEALS_CACHE_ROOT, 'Swap', 'Cashflow'))


def day_path(ref):
    return os.path.join(cache_dir(), ref.strftime('%Y'), ref.strftime('%m'),
                        ref.strftime('%Y%m%d') + SUFFIX)


# O que o re-import PRESERVA da linha que já está no dia (a esteira e os
# números que já podem ter ido à B3). Os dois `FlowMyNumber*` são o Meu Número
# do 0034 (o cronograma), por visão.
KEEP_ON_REIMPORT = ('Status', 'Maker', 'Checker', 'MyNumber', 'MyNumberMirror',
                    'PremiumMyNumber', 'PremiumMyNumberMirror', 'FlowMyNumber',
                    'FlowMyNumberMirror', 'SentFiles', 'B3ID', 'Deal')


def key_of(e):
    """A chave interna da linha (`_id`, SWC-…)."""
    return str((e or {}).get('_id') or '')


def read_day(fp):
    """A lista do arquivo-dia (vazia se não existe). Banco ocupado SOBE — lido
    como "não há", um read-modify-write gravaria só o registro novo por cima
    do dia inteiro (§4)."""
    if not _store.exists(fp):
        return []
    try:
        entries = _store.read(fp)
    except (json.JSONDecodeError, ValueError):
        return []
    return entries if isinstance(entries, list) else []


def write_day(fp, entries):
    """O funil de gravação (`_atomic_write_json`) + o memo do dia esquecido.
    Quem chama segura o `_cache_lock` pelo ciclo inteiro."""
    _R()._atomic_write_json(fp, entries)
    _R()._daycache_forget(fp)


def upsert(ref, novas):
    """Upsert por `_id` no arquivo-dia de `ref`; o ciclo inteiro sob o
    `_cache_lock`. → quantidade gravada."""
    fp = day_path(ref)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    n = 0
    with _R()._cache_lock:
        entries = read_day(fp)
        for d in novas:
            idx = next((i for i, e in enumerate(entries) if key_of(e) == key_of(d)), None)
            if idx is not None:
                for k in KEEP_ON_REIMPORT:
                    if entries[idx].get(k):
                        d[k] = entries[idx][k]
                entries[idx] = d
            else:
                entries.append(d)
            n += 1
        write_day(fp, entries)
    _R().log.info('[SWAP CASHFLOW] Saved %d deal(s) → %s', n, fp)
    return n
