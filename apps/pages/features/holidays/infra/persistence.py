# -*- coding: utf-8 -*-
"""O registro de calendários e os arquivos de feriado, em disco."""
import json
import os
import traceback

from apps.pages.features.holidays import domain
from apps.pages import data_store as _store  # noqa: E402

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


def _calendars_db():
    """O registro pela tabela `_registry` — DB-first (fase 3, HANDOFF §328).

    Só responde quando o manifest prova que o banco reflete o
    `holiday-calendars.json` atual; senão `None` e vale o caminho JSON de
    sempre (que é quem SEMEIA — registro vindo do seed nem tem arquivo para o
    manifest provar)."""
    try:
        from apps.pages import duck_read
        from apps.pages import json_to_duckdb as core
        # Pelo `_raw`/`_seq` (raw_records): a ORDEM do registro é a ordem das
        # pills e do sorteio de cores da tela, e o SELECT sem ordenação não a
        # promete.
        rows = duck_read.raw_records(
            'holiday_calendars.db', '_registry', domain.CAL_FILE,
            manifest_key=core._dataset_manifest_key(domain.CAL_FILE))
    except Exception:                                       # noqa: BLE001
        return None
    if not rows:
        return None
    rows = [r for r in rows
            if isinstance(r, dict) and str(r.get('name', '') or '').strip()]
    return rows or None


def calendars():
    """O registro de calendários.

    Semeia na PRIMEIRA leitura e cacheia por mtime — calendário criado pela tela
    vale no request seguinte, sem restart, como os mappings. É o que dispensa um
    "rode este script depois do pull": a instância que nunca abriu a tela já
    responde com os onze de sempre.

    O registro está no `.gitignore` — o seed o recria, e versioná-lo daria
    conflito de merge a cada calendário criado pela tela.
    """
    linhas = _calendars_db()
    if linhas is not None:
        return linhas
    R = _routes()
    path = registry_path()
    if not _store.isfile(path):
        with R._cache_lock:
            if not _store.isfile(path):
                try:
                    os.makedirs(data_dir(), exist_ok=True)
                    R._atomic_write_json(path, [dict(r) for r in domain.CAL_SEED])
                except Exception:                           # noqa: BLE001
                    R.log.warning('[holidays] seed do registro falhou:\n%s',
                                  traceback.format_exc())
                    return [dict(r) for r in domain.CAL_SEED]
    try:
        mt = _store.getmtime(path)
        if _cache['mtime'] == mt and _cache['rows'] is not None:
            return _cache['rows']
        rows = _store.read(path) or []
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
    """Os feriados de um calendário. Arquivo ausente ou ilegível → lista vazia.

    DB-first (fase 3): a tabela do calendário responde quando o manifest prova
    que ela reflete o arquivo atual — senão vale o JSON de sempre (DB-only: §434)
    é avisado. A data volta como STRING ISO, a forma que o JSON sempre teve."""
    linhas = _load_holidays_db(filename)
    if linhas is not None:
        return linhas
    try:
        fp = calendar_path(filename)
        if not _store.exists(fp):
            return []
        return _store.read(fp)
    except (json.JSONDecodeError, IOError):
        return []


def _load_holidays_db(filename):
    """Os feriados de um calendário pelo banco — delegado ao `duck_read`, que é
    onde a leitura mora desde que os outros cinco leitores de feriado do app
    (SLA da esteira, aging do CGD, recon de CGD, precificador, schedules do
    TER) passaram a usá-la. O `nome` vai resolvido daqui porque o registro
    desta tela aceita o SEED, que o banco não tem como provar."""
    alvo = str(filename or '').strip().lower()
    nome = next((str(r.get('name', '') or '') for r in calendars()
                 if str(r.get('file', '') or '').strip().lower() == alvo), None)
    if not nome:
        return None
    try:
        from apps.pages import duck_read
        return duck_read.calendar_rows(calendar_path(filename), nome=nome)
    except Exception:                                       # noqa: BLE001
        return None


def write_holidays(filename, holidays):
    """Grava os feriados. Devolve `None` ou a mensagem de erro.

    A escrita é ATÔMICA — o navegador lê este arquivo por URL estática
    (`/static/data/<file>`), e um fetch no meio de um write não pode ver JSON
    pela metade — e, desde o §434, grava a tabela do calendário no
    `holiday_calendars.db` acompanha na hora. O aviso é explícito porque o
    nome do arquivo de calendário só o registro conhece — o gancho genérico
    do funil não teria como classificá-lo."""
    try:
        _routes()._atomic_write_json(calendar_path(filename), holidays)
    except Exception as e:                                  # noqa: BLE001
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
    nomes = [f[:-5] for f in _store.listdir(data_dir())
             if f.endswith('.json') and f not in sistema]
    nomes.sort()
    return nomes
