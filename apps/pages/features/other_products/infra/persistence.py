# -*- coding: utf-8 -*-
"""O arquivo-dia dos fatores do Swap VCP (§452): o que a mesa editou e o que
já foi enviado, por contrato, ao lado dos outros JSON do Daily Settlement
(`OTM_JSON_ROOT/AAAA/MM/DD/swap-vcp-factors_AAAAMMDD.json`, pelo funil).

Guarda só o DELTA: os campos editados (`overrides`), a esteira (`status`,
`maker`, `checker`) e os arquivos gerados. O calculado é refeito a cada
leitura a partir das fontes do dia — gravar o cálculo congelaria um número
que muda quando o OTM ou o evento chega mais tarde."""
from datetime import datetime


def _R():
    from apps.pages import routes
    return routes


def _path(ref):
    return _R()._ds_display_json_path(ref, 'swap-vcp-factors')


def _chave(contrato):
    return str(contrato or '').strip().upper()


def _vcp_factors_load(ref):
    """{contrato → {overrides, status, maker, checker, files, updated}}."""
    R = _R()
    jp = _path(ref)
    try:
        if not R._store.isfile(jp):
            return {}
        data = R._store.read(jp) or {}
    except Exception:                                       # noqa: BLE001
        R.log.warning('[swap-vcp] factors day file unreadable: %s', jp, exc_info=True)
        return {}
    return data if isinstance(data, dict) else {}


def _vcp_factors_update(ref, mutate):
    """Read-modify-write do arquivo-dia sob o `_cache_lock`; `mutate(data)`
    altera o dict no lugar. Devolve o dict gravado."""
    R = _R()
    jp = _path(ref)
    with R._cache_lock:
        data = {}
        try:
            if R._store.isfile(jp):
                data = R._store.read(jp) or {}
        except Exception:                                   # noqa: BLE001
            data = {}
        if not isinstance(data, dict):
            data = {}
        mutate(data)
        R._atomic_write_json(jp, data)
    return data


def stamp():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
