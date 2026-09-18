# -*- coding: utf-8 -*-
"""O arquivo-dia da recompra de NDF de moeda:
`cache/unwinds/NDF/FX/AAAA/MM/AAAAMMDD_unwindndffx.json`, uma lista de linhas.

**Fora de `cache/new deals/` de proposito**: o New Deals Monitor VARRE aquela
pasta e agrupa pelos dois primeiros niveis do caminho (§454) — um dia gravado
la viraria um card `extra-...` no rodape do Monitor, classificado como
Registration, sem ninguem ter pedido. A recompra tera o card dela quando a
mesa disser.
"""
import json
import os

from apps.pages import data_store as _store
from apps.pages.data_paths import unwinds_cache_root


def _R():
    from apps.pages import routes
    return routes


SUFFIX = '_unwindndffx.json'


def cache_root():
    # O caminho mora no `data_paths` porque o New Deals Monitor varre por ele
    # tambem (§491): escrito dos dois lados, ele desliza sem erro nenhum.
    return unwinds_cache_root()


def cache_dir():
    return os.path.normpath(os.path.join(cache_root(), 'NDF', 'FX'))


def day_path(ref):
    return os.path.join(cache_dir(), ref.strftime('%Y'), ref.strftime('%m'),
                        ref.strftime('%Y%m%d') + SUFFIX)


# O que o re-import PRESERVA da linha que ja esta no dia: o que a mesa decidiu
# e o que ja pode ter ido a B3. O Nº de Controle Interno entra aqui pela mesma
# razao do Meu Numero do Swap Bullet — reemitir um numero novo para uma
# antecipacao ja enviada faria a B3 ver duas.
KEEP_ON_REIMPORT = ('Status', 'MyNumber', 'SettlementDate', 'SentFiles',
                    'Maker', 'Checker')


def key_of(e):
    """A chave da linha e o Athena ID: e o identificador da recompra no e-mail
    e o que a ponte usa para achar o contrato."""
    return str((e or {}).get('AthenaID') or '').strip().upper()


def upsert(ref, novas):
    """Upsert por Athena ID no arquivo-dia de `ref`; o ciclo INTEIRO sob o
    `_cache_lock` (ler -> alterar -> gravar). -> quantidade gravada."""
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
    _R().log.info('[UNWIND NDF FX] Saved %d row(s) -> %s', n, fp)
    return n


def save(fp, entries):
    """Grava a lista inteira de volta no arquivo-dia (o chamador ja esta sob o
    `_cache_lock`, como manda o read-modify-write)."""
    _R()._atomic_write_json(fp, entries)
    _R()._daycache_forget(fp)
