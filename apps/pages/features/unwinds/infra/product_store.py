# -*- coding: utf-8 -*-
"""O arquivo-dia das recompras do CATALOGO (as onze paginas de
`pages/unwinds-product.html`):
`cache/unwinds/<dir do catalogo>/AAAA/MM/AAAAMMDD<suffix>`, uma lista de linhas.

A mesma arvore da Fase 1 (`cache/unwinds/NDF/FX/...`), uma pasta por produto,
e pelo MESMO `data_paths.unwinds_cache_root()`: e por ela que o New Deals
Monitor varre (§491) e o painel conta. Escrita pelo funil `_atomic_write_json`
sob o `_cache_lock` (read-modify-write INTEIRO); leitura pelo armazem.
"""
import os

from apps.pages import data_store as _store
from apps.pages.data_paths import unwinds_cache_root


def _R():
    from apps.pages import routes
    return routes


def cache_root():
    return unwinds_cache_root()


def cache_dir(page):
    return os.path.normpath(os.path.join(cache_root(), *page['dir'].split('/')))


def day_path(page, ref):
    return os.path.join(cache_dir(page), ref.strftime('%Y'), ref.strftime('%m'),
                        ref.strftime('%Y%m%d') + page['suffix'])


def read_day(fp):
    """A lista do arquivo-dia; ausente e lista vazia. Banco OCUPADO sobe (e o
    `BancoOcupado` do armazem): lido como "vazio", um read-modify-write
    gravaria so a linha nova por cima do dia inteiro (§4)."""
    if not _store.exists(fp):
        return []
    lst = _store.read(fp)
    return lst if isinstance(lst, list) else []


def save(fp, entries):
    """Grava a lista inteira (o chamador ja esta sob o `_cache_lock`)."""
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    _R()._atomic_write_json(fp, entries)
    _R()._daycache_forget(fp)
