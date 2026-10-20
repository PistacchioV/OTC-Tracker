# -*- coding: utf-8 -*-
"""O armazém do Projects: um documento só, `projects/projects.json` no
`DATA_DIR` — que desde o §434 vive no BANCO (o `data_store` grava a tabela do
caminho; nenhum JSON é escrito).

    {"seq": 3, "projects": [ {...}, {...}, {...} ]}

`seq` é o contador do id (PRJ-0001, PRJ-0002…) e mora NO DOCUMENTO: derivado
do maior id, o número de um projeto apagado voltaria, e o link fixado na barra
de alguém passaria a abrir outro projeto.

Todo ciclo ler → alterar → gravar roda dentro de `_lock` (o mesmo desenho do
`otc_tickets`). A leitura é ESTRITA: banco ocupado ou ilegível SOBE (o tratador
global responde 503) — lido como "não há projeto", o `mutate` gravaria só o
projeto novo por cima de todos (§436).
"""
import os
import threading
from datetime import datetime

_lock = threading.RLock()

# O teste aponta para um tmp trocando este atributo. Fica em None (e o caminho
# é resolvido na CHAMADA) para o import não tocar no `DATA_DIR` (§522).
FILE = None


def path():
    if FILE:
        return FILE
    from apps.pages.data_paths import data_dir
    return os.path.join(data_dir(), 'projects', 'projects.json')


def now():
    return datetime.now().replace(microsecond=0).isoformat(sep=' ')


def _read():
    from apps.pages import data_store
    try:
        data = data_store.read(path())
    except FileNotFoundError:
        return {'seq': 0, 'projects': []}
    if not isinstance(data, dict):
        raise ValueError('projects store is not an object: %s' % type(data).__name__)
    data.setdefault('seq', 0)
    data.setdefault('projects', [])
    return data


def load():
    """O documento inteiro, para LER."""
    with _lock:
        return _read()


def mutate(fn):
    """Lê, entrega o documento a `fn` (que o altera NO LUGAR) e grava. O que
    `fn` devolver volta para quem chamou. Uma exceção de `fn` não grava nada."""
    from apps.pages import data_store
    with _lock:
        data = _read()
        result = fn(data)
        data_store.write(path(), data)
        return result


def next_id(data):
    data['seq'] = int(data.get('seq') or 0) + 1
    return 'PRJ-%04d' % data['seq']


def find(data, project_id):
    pid = str(project_id or '').strip().upper()
    for p in data.get('projects') or []:
        if p.get('id') == pid:
            return p
    return None


def child_id(project, counter, prefix):
    """Id de tarefa/marco/subtarefa: contador DENTRO do pai, pelo mesmo motivo
    do `seq` (apagado não volta a ser usado)."""
    project[counter] = int(project.get(counter) or 0) + 1
    return '%s%d' % (prefix, project[counter])
