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


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


ACCRUAL_JSON_ROOT = _R().data_write('cache', 'accrual')

ACCRUAL_SOURCE_ROOT = os.getenv('ACCRUAL_SOURCE_ROOT', os.path.join(
    _R().Config.SHARED_DRIVE_ROOT, 'Confirmation', 'Derivativos', 'OTC Tracker', 'Regulatory',
    'Accrual'))


def _accrual_path_for(ymd):
    return os.path.join(ACCRUAL_JSON_ROOT, ymd[:4], ymd[4:6], ymd[6:8],
                        'accrual_swap_{}.json'.format(ymd))


def _accrual_latest_ymd():
    """Newest saved accrual date as 'YYYY-MM-DD' (scans accrual_swap_*.json under
    ACCRUAL_JSON_ROOT), or None if nothing saved yet. Lets the page land on the
    most recent dataset when no explicit date is requested (e.g. from a bell
    notification), instead of an empty 'today'."""
    latest = None
    if not os.path.isdir(ACCRUAL_JSON_ROOT):
        return None
    for _root, _dirs, files in os.walk(ACCRUAL_JSON_ROOT):
        for fn in files:
            m = re.match(r'accrual_swap_(\d{8})\.json$', fn)
            if m and (latest is None or m.group(1) > latest):
                latest = m.group(1)
    return '{}-{}-{}'.format(latest[:4], latest[4:6], latest[6:8]) if latest else None


def _accrual_load(date_str):
    ymd = _R()._accrual_parse_date(date_str) or datetime.now().strftime('%Y%m%d')
    path = _accrual_path_for(ymd)
    if not os.path.isfile(path):
        return None, None
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return path, domain._accrual_migrate(_R().json.load(fh))
    except Exception:
        _R().log.error('[accrual] read failed %s:\n%s', path, traceback.format_exc())
        return None, None


def _accrual_save(path, data):
    data['counts'] = {k: len(v) for k, v in (data.get('tables') or {}).items()}
    with open(path, 'w', encoding='utf-8') as fh:
        _R().json.dump(data, fh, ensure_ascii=False, indent=2)


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
    with open(path, 'w', encoding='utf-8') as fh:
        _R().json.dump(saved, fh, ensure_ascii=False, indent=2)
    _R().log.info('[accrual] saved %s', path)
    return path, saved


def _accrual_source_dir(ymd):
    """ACCRUAL_SOURCE_ROOT\\YYYY\\mm. Month\\DD for a 'YYYYMMDD' run date."""
    ref = datetime.strptime(ymd, '%Y%m%d')
    month_folder = ref.strftime('%m') + '. ' + _R()._EN_MONTH_NAMES[ref.month - 1]
    return os.path.join(ACCRUAL_SOURCE_ROOT, ref.strftime('%Y'), month_folder, ref.strftime('%d'))


def _acc_find_operacoes(folder):
    if not os.path.isdir(folder):
        return None
    for fn in os.listdir(folder):
        if not os.path.isfile(os.path.join(folder, fn)):
            continue
        base = os.path.splitext(fn)[0].lower()
        base = (base.replace('ç', 'c').replace('õ', 'o').replace('ã', 'a')
                    .replace('é', 'e').replace('ô', 'o'))
        if base.startswith('operac'):
            return os.path.join(folder, fn)
    return None
