# -*- coding: utf-8 -*-
"""O arquivo-dia do Accrual (`cache/accrual/YYYY/MM/DD/accrual_swap_*.json`) e a
pasta de ORIGEM no share. Ler, gravar, achar o mais recente e localizar o
arquivo de operações do dia.

Os dois roots são de MÓDULO (mesmo contrato do engine que isto substitui): o
`ACCRUAL_JSON_ROOT` sai do `data_write` e o `ACCRUAL_SOURCE_ROOT` pende do
`SHARED_DRIVE_ROOT` — nenhum módulo monta a raiz à mão (§8).
"""
import os
import re
import traceback
from datetime import datetime

from apps.pages.features.accrual import domain
from apps.pages.platform import pu_fator as _pf
from apps.pages import data_store as _store  # noqa: E402


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


ACCRUAL_JSON_ROOT = _R().data_write('cache', 'accrual')

# A pasta de evidência do dia mora na platform (`pu_fator`, §452). Aliases.
ACCRUAL_SOURCE_ROOT = _pf.ACCRUAL_SOURCE_ROOT
_accrual_source_dir = _pf.accrual_source_dir
def _accrual_path_for(ymd):
    return os.path.join(ACCRUAL_JSON_ROOT, ymd[:4], ymd[4:6], ymd[6:8],
                        'accrual_swap_{}.json'.format(ymd))


def _accrual_latest_ymd():
    """Newest saved accrual date as 'YYYY-MM-DD' (scans accrual_swap_*.json under
    ACCRUAL_JSON_ROOT), or None if nothing saved yet. Lets the page land on the
    most recent dataset when no explicit date is requested (e.g. from a bell
    notification), instead of an empty 'today'."""
    latest = None
    if not _store.isdir(ACCRUAL_JSON_ROOT):
        return None
    for _root, _dirs, files in _store.walk(ACCRUAL_JSON_ROOT):
        for fn in files:
            m = re.match(r'accrual_swap_(\d{8})\.json$', fn)
            if m and (latest is None or m.group(1) > latest):
                latest = m.group(1)
    return '{}-{}-{}'.format(latest[:4], latest[4:6], latest[6:8]) if latest else None


def _accrual_load(date_str):
    ymd = _R()._accrual_parse_date(date_str) or datetime.now().strftime('%Y%m%d')
    path = _accrual_path_for(ymd)
    if not _store.isfile(path):
        return None, None
    try:
        return path, domain._accrual_migrate(_store.read(path))
    except Exception:
        _R().log.error('[accrual] read failed %s:\n%s', path, traceback.format_exc())
        return None, None


def _accrual_save(path, data):
    data['counts'] = {k: len(v) for k, v in (data.get('tables') or {}).items()}
    _R()._atomic_write_json(path, data)         # funil: atômico + espelho (§335)


def _accrual_persist(result, source_file, ymd=None):
    """Persist a build result under static/data/cache/accrual/YYYY/MM/DD/. Defaults
    to today; pass ymd ('YYYYMMDD') to store under the run/reference date instead.
    Returns (path, saved_dict)."""
    now = datetime.now()
    ymd = ymd or now.strftime('%Y%m%d')
    out_dir = os.path.join(ACCRUAL_JSON_ROOT, ymd[:4], ymd[4:6], ymd[6:8])
    os.makedirs(out_dir, exist_ok=True)
    saved = dict(result)
    saved['date']        = '{}-{}-{}'.format(ymd[:4], ymd[4:6], ymd[6:8])
    saved['saved_at']    = now.strftime('%Y-%m-%d %H:%M:%S')
    saved['source_file'] = source_file
    path = os.path.join(out_dir, 'accrual_swap_{}.json'.format(ymd))
    _R()._atomic_write_json(path, saved)        # funil: atômico + espelho (§335)
    _R().log.info('[accrual] saved %s', path)
    return path, saved


def _accrual_store_source(ymd, filename, blob):
    """Grava o arquivo SOLTO NO DROPZONE na pasta-fonte do dia — a mesma que o
    Import from folder lê e que o End Process usa como evidência (pedido de
    2026-09-01; espelho do `_mtm_store_source`, ver a razão de cada decisão
    lá). Devolve (caminho, erro); a falha não desfaz o processamento."""
    # Os DOIS separadores à mão: fora do Windows o basename não corta '\',
    # e um nome vindo do navegador com caminho viraria um arquivo esquisito.
    fn = str(filename or '').replace('\\', '/').rsplit('/', 1)[-1].strip()
    if not fn:
        return None, 'invalid filename'
    d = _accrual_source_dir(ymd)
    try:
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, fn)
        with open(path, 'wb') as fh:
            fh.write(blob)
        return path, None
    except OSError as exc:
        _R().log.warning('[accrual] não consegui guardar %s em %s: %s', fn, d, exc)
        return None, str(exc)


def _acc_find_operacoes(folder):
    if not _store.isdir(folder):
        return None
    for fn in _store.listdir(folder):
        if not _store.isfile(os.path.join(folder, fn)):
            continue
        base = os.path.splitext(fn)[0].lower()
        base = (base.replace('ç', 'c').replace('õ', 'o').replace('ã', 'a')
                    .replace('é', 'e').replace('ô', 'o'))
        if base.startswith('operac'):
            return os.path.join(folder, fn)
    return None
