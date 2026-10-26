# -*- coding: utf-8 -*-
"""O armazém do WHT: UM documento por MÊS, `wht/wht_AAAAMM.json` no
`DATA_DIR` — que desde o §434 vive no BANCO (o `data_store` grava a tabela do
caminho; nenhum JSON é escrito).

    {"otc": {"2026-10-14": {"ndf": {"rows": [...], "at": "...", "by": "..."},
                            "ops": {...}}},
     "hub": [ {...linha do relatório do HUB...} ],
     "hub_files": [ {"name", "at", "sid", "rows", "scope"} ]}

O lado OTC é guardado por DIA de liquidação e por FONTE (`ndf` = NDF Summary,
`ops` = Other Products): cada coleta SUBSTITUI a fatia dela, então recarregar
uma tela não conta duas vezes, e uma fonte nunca apaga a outra. O mês inteiro
mora junto porque o piso de R$ 1,00 é do MÊS (o decêndio precisa dos anteriores).

Todo ciclo ler → alterar → gravar roda dentro de `_lock`, e a leitura é
ESTRITA: banco ocupado ou ilegível SOBE — lido como "mês vazio", o `mutate`
gravaria só a fatia nova por cima do mês inteiro (§436). Grava só se mudou: a
tela do Summary abre muitas vezes ao dia com o mesmo resultado.
"""
import json
import os
import threading
from datetime import datetime

_lock = threading.RLock()

# O teste aponta para um tmp trocando este atributo. Fica em None (e o caminho
# é resolvido na CHAMADA) para o import não tocar no `DATA_DIR` (§522).
DIR = None


def path(month_key):
    if DIR:
        base = DIR
    else:
        from apps.pages.data_paths import data_dir
        base = os.path.join(data_dir(), 'wht')
    return os.path.join(base, 'wht_%s.json' % month_key)


def now():
    return datetime.now().replace(microsecond=0).isoformat(sep=' ')


def _vazio():
    return {'otc': {}, 'hub': [], 'hub_files': []}


def _read(month_key):
    from apps.pages import data_store
    try:
        data = data_store.read(path(month_key))
    except FileNotFoundError:
        return _vazio()
    if not isinstance(data, dict):
        raise ValueError('wht store is not an object: %s' % type(data).__name__)
    for k, v in _vazio().items():
        data.setdefault(k, v)
    return data


def load(month_key):
    """O documento do mês, para LER."""
    with _lock:
        return _read(month_key)


def mutate(month_key, fn):
    """Lê, entrega o documento a `fn` (que o altera NO LUGAR) e grava se mudou.
    O que `fn` devolver volta para quem chamou; uma exceção não grava nada."""
    from apps.pages import data_store
    with _lock:
        data = _read(month_key)
        antes = json.dumps(data, sort_keys=True, default=str)
        result = fn(data)
        if json.dumps(data, sort_keys=True, default=str) != antes:
            os.makedirs(os.path.dirname(path(month_key)), exist_ok=True)
            data_store.write(path(month_key), data)
        return result
