# -*- coding: utf-8 -*-
"""O arquivo-dia do Swap Bullet: `cache/new deals/Swap/Bullet/AAAA/MM/
AAAAMMDD_swapbullet.json`, uma lista de deals. O Monitor varre esta pasta
(card `swap-bullet`, §454)."""
import json
import os

from apps.pages import data_store as _store


def _R():
    from apps.pages import routes
    return routes


SUFFIX = '_swapbullet.json'


def cache_dir():
    return os.path.normpath(os.path.join(_R().NEW_DEALS_CACHE_ROOT, 'Swap', 'Bullet'))


def day_path(ref):
    return os.path.join(cache_dir(), ref.strftime('%Y'), ref.strftime('%m'),
                        ref.strftime('%Y%m%d') + SUFFIX)


# O que o re-import PRESERVA da linha que já está no dia (a esteira e os
# números que já podem ter ido à B3).
KEEP_ON_REIMPORT = ('Status', 'Maker', 'Checker', 'MyNumber', 'MyNumberMirror',
                    'PremiumMyNumber', 'PremiumMyNumberMirror', 'SentFiles', 'B3ID', 'Deal')


def key_of(e):
    """A chave interna da linha; linha anterior à coluna B3 ID (que guardava o
    hash em `Deal`) responde pelo `Deal`."""
    return str((e or {}).get('_id') or (e or {}).get('Deal') or '')


def migrate(e):
    """Linha gravada antes da coluna B3 ID: o hash `SWB-…` morava em `Deal`.
    Passa para `_id` e deixa o Deal em BRANCO (é da mesa). Muta e devolve."""
    if isinstance(e, dict) and not e.get('_id') and str(e.get('Deal') or '').startswith('SWB-'):
        e['_id'] = e['Deal']
        e['Deal'] = ''
    if isinstance(e, dict) and e.get('Deal') and e.get('Deal') == e.get('_id'):
        e['Deal'] = ''          # o hash copiado para o Deal por um re-import antigo
    if isinstance(e, dict):
        e.setdefault('B3ID', '')
    return e


def upsert(ref, novas):
    """Upsert por `_id` (a chave interna) no arquivo-dia de `ref`; o ciclo
    inteiro sob o `_cache_lock`. → quantidade gravada."""
    fp = day_path(ref)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    n = 0
    with _R()._cache_lock:
        entries = []
        if _store.exists(fp):
            try:
                entries = _store.read(fp)
                if not isinstance(entries, list):
                    entries = []
            except (json.JSONDecodeError, ValueError):
                entries = []
        entries = [migrate(e) for e in entries]
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
        _R()._atomic_write_json(fp, entries)
        _R()._daycache_forget(fp)
    _R().log.info('[SWAP BULLET] Saved %d deal(s) → %s', n, fp)
    return n
