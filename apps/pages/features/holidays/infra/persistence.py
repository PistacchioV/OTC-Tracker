# -*- coding: utf-8 -*-
"""O registro de calendários e os arquivos de feriado, em disco."""
import json
import os
import traceback

from apps.pages.features.holidays import domain

_cache = {'mtime': None, 'rows': None}


def _routes():
    """Busca ATRASADA — ver `features/support/infra/persistence.py`.

    `_B3_DATA_DIR`, `_cache_lock`, `_atomic_write_json` e `log` ainda são de
    plataforma e moram no `routes`; e 61 testes trocam atributos lá.
    """
    from apps.pages import routes
    return routes


def data_dir():
    return _routes()._B3_DATA_DIR


def registry_path():
    return os.path.join(data_dir(), domain.CAL_FILE)


def calendar_path(filename):
    return os.path.join(data_dir(), filename)


def calendars():
    """O registro de calendários.

    Semeia na PRIMEIRA leitura e cacheia por mtime — calendário criado pela tela
    vale no request seguinte, sem restart, como os mappings. É o que dispensa um
    "rode este script depois do pull": a instância que nunca abriu a tela já
    responde com os onze de sempre.

    O registro está no `.gitignore` — o seed o recria, e versioná-lo daria
    conflito de merge a cada calendário criado pela tela.
    """
    R = _routes()
    path = registry_path()
    if not os.path.isfile(path):
        with R._cache_lock:
            if not os.path.isfile(path):
                try:
                    os.makedirs(data_dir(), exist_ok=True)
                    R._atomic_write_json(path, [dict(r) for r in domain.CAL_SEED])
                except Exception:                           # noqa: BLE001
                    R.log.warning('[holidays] seed do registro falhou:\n%s',
                                  traceback.format_exc())
                    return [dict(r) for r in domain.CAL_SEED]
    try:
        mt = os.path.getmtime(path)
        if _cache['mtime'] == mt and _cache['rows'] is not None:
            return _cache['rows']
        with open(path, encoding='utf-8') as fh:
            rows = json.load(fh) or []
        rows = [r for r in rows if isinstance(r, dict) and str(r.get('name', '')).strip()]
        _cache['mtime'] = mt
        _cache['rows'] = rows
        return rows
    except Exception:                                       # noqa: BLE001
        R.log.warning('[holidays] registro ilegível, usando o seed:\n%s',
                      traceback.format_exc())
        return [dict(r) for r in domain.CAL_SEED]


def file_for(name):
    """Arquivo JSON de um calendário, pelo nome, ou `None`.

    Cego a caixa e a espaço: o nome chega da tela e do payload de gravação, e um
    `sofr ` não pode deixar de achar o calendário em silêncio.

    A resolução é pelo REGISTRO e não por um mapa fixo — o calendário criado
    pela tela não estaria em literal nenhum do código, e o Save devolveria
    "Unknown calendar" para um calendário que a própria página acabou de mostrar.
    """
    alvo = str(name or '').strip().upper()
    if not alvo:
        return None
    for row in calendars():
        if str(row.get('name', '')).strip().upper() == alvo:
            fn = str(row.get('file', '')).strip()
            return fn or None
    return None


def load_holidays(filename):
    """Os feriados de um calendário. Arquivo ausente ou ilegível → lista vazia."""
    try:
        fp = calendar_path(filename)
        if not os.path.exists(fp):
            return []
        with open(fp, encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def write_holidays(filename, holidays):
    """Grava os feriados. Devolve `None` ou a mensagem de erro."""
    try:
        with open(calendar_path(filename), 'w', encoding='utf-8') as f:
            json.dump(holidays, f, ensure_ascii=False, indent=4)
    except IOError as e:
        return str(e)
    return None


def fx_schedule_names():
    """Os nomes de agenda que o FX holiday schedule oferece.

    O REGISTRO mora na mesma pasta e **não é uma agenda de feriados** — sem a
    exclusão ele apareceria como opção de schedule.
    """
    sistema = {
        'Subjacente.json', 'VCP.json', 'Dominio.json', 'RefData.json',
        'datatables-rendering.json', 'datatables.json',
        'treeview-data.json', 'typeahead-data-2.json', 'typeahead.json',
        domain.CAL_FILE,
    }
    nomes = [f[:-5] for f in os.listdir(data_dir())
             if f.endswith('.json') and f not in sistema]
    nomes.sort()
    return nomes
