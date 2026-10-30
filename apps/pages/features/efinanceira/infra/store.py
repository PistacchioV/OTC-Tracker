# -*- coding: utf-8 -*-
"""O armazém da E-Financeira: UM documento por MÊS, `efin/efin_AAAAMM.json` no
`DATA_DIR` — que desde o §434 vive no BANCO (o `data_store` grava a tabela do
caminho; nenhum JSON é escrito).

    {"days": {"2026-09-15": {"ndf": {"rows": [...eventos], "at", "by"},
                             "ops": {...}, "exp": {...}}},
     "edits":   {chave da operação: {fields, orig, status, maker, ...}},
     "deleted": {chave: {by, name, at}},
     "manual":  [ {...operação incluída à mão} ],
     "files":   {página: {name, path, at, sid, n, lines: {chave: linha}}},
     "history": [ {page, name, path, at, sid, n} ]}

Os eventos são guardados por DIA e por FONTE: cada coleta SUBSTITUI a fatia
dela, então reimportar não conta duas vezes e uma fonte nunca apaga a outra. A
operação (a linha da tela e do arquivo) é montada na LEITURA, e a correção da
tela fica à parte (`edits`) — sobrevive a um novo import.

Todo ciclo ler → alterar → gravar roda dentro de `_lock`, e a leitura é
ESTRITA: banco ocupado ou ilegível SOBE — lido como "mês vazio", o `mutate`
gravaria só a fatia nova por cima do mês inteiro (§436).
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
        base = os.path.join(data_dir(), 'efin')
    return os.path.join(base, 'efin_%s.json' % month_key)


def now():
    return datetime.now().replace(microsecond=0).isoformat(sep=' ')


def _vazio():
    return {'days': {}, 'edits': {}, 'deleted': {}, 'manual': [], 'files': {}, 'history': []}


def _read(month_key):
    from apps.pages import data_store
    try:
        data = data_store.read(path(month_key))
    except FileNotFoundError:
        return _vazio()
    if not isinstance(data, dict):
        raise ValueError('efin store is not an object: %s' % type(data).__name__)
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
