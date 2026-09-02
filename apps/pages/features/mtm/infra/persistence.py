# -*- coding: utf-8 -*-
"""O arquivo-dia do MtM e a pasta de ORIGEM no share (§8: a raiz pende do
`SHARED_DRIVE_ROOT`, nenhum módulo a escreve à mão).
"""
import os
import re
import traceback
from datetime import datetime

from apps.pages.features.mtm.infra import mappers

def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


MTM_SOURCE_ROOT = os.getenv('MTM_SOURCE_ROOT', os.path.join(
    _R().Config.SHARED_DRIVE_ROOT, 'Confirmation', 'Derivativos', 'OTC Tracker', 'Regulatory', 'MTM'))


MTM_JSON_ROOT = _R().data_write('cache', 'mtm')


def _mtm_path_for(ymd):
    return os.path.join(MTM_JSON_ROOT, ymd[:4], ymd[4:6], ymd[6:8], 'mtm_swap_{}.json'.format(ymd))


def _mtm_source_dir(ymd):
    ref = datetime.strptime(ymd, '%Y%m%d')
    month_folder = ref.strftime('%m') + '. ' + _R()._EN_MONTH_NAMES[ref.month - 1]
    return os.path.join(MTM_SOURCE_ROOT, ref.strftime('%Y'), month_folder, ref.strftime('%d'))


def _mtm_store_source(ymd, filename, blob):
    """Grava o arquivo SOLTO NO DROPZONE na pasta-fonte do dia (a mesma que o
    Import from folder lê) — pedido de 2026-09-01: processar sem guardar o
    original deixava a pasta oficial sem o arquivo que gerou o dado, e o
    Import from folder de amanhã não o acharia. Devolve (caminho, erro): quem
    chama decide o que mostrar — a falha aqui NÃO desfaz o processamento, que
    já aconteceu e foi salvo; ela vira aviso, nunca silêncio.

    Só o basename do nome (o navegador pode mandar caminho), e sobrescreve o
    homônimo — é o mesmo que a cópia manual pelo Explorer faria, e o arquivo
    re-soltado É a versão nova daquele relatório."""
    # Os DOIS separadores à mão: fora do Windows o basename não corta '\',
    # e um nome vindo do navegador com caminho viraria um arquivo esquisito.
    fn = str(filename or '').replace('\\', '/').rsplit('/', 1)[-1].strip()
    if not fn:
        return None, 'invalid filename'
    d = _mtm_source_dir(ymd)
    try:
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, fn)
        with open(path, 'wb') as fh:
            fh.write(blob)
        return path, None
    except OSError as exc:
        _R().log.warning('[mtm] não consegui guardar %s em %s: %s', fn, d, exc)
        return None, str(exc)


def _mtm_save(path, data):
    """Persist the MtM dataset, creating the YYYY/MM/DD dir first (mkstemp needs it).
    Trava por conta própria; como _cache_lock é RLock, isso não conflita com o
    caller que já tranca o ciclo ler → alterar → gravar (o correto, e o que todos
    fazem hoje). Aqui é só a garantia de que uma gravação nunca sai sem lock."""
    with _R()._cache_lock:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        _R()._atomic_write_json(path, data)


def _mtm_load(date_str):
    ymd = _R()._accrual_parse_date(date_str) or datetime.now().strftime('%Y%m%d')
    path = _mtm_path_for(ymd)
    if not os.path.isfile(path):
        return None, None
    try:
        with open(path, encoding='utf-8') as fh:
            return path, _R().json.load(fh)
    except Exception:
        _R().log.error('[mtm] read failed %s:\n%s', path, traceback.format_exc())
        return None, None


def _mtm_latest_ymd():
    latest = None
    if not os.path.isdir(MTM_JSON_ROOT):
        return None
    for _root, _dirs, files in os.walk(MTM_JSON_ROOT):
        for fn in files:
            m = re.match(r'mtm_swap_(\d{8})\.json$', fn)
            if m and (latest is None or m.group(1) > latest):
                latest = m.group(1)
    return '{}-{}-{}'.format(latest[:4], latest[4:6], latest[6:8]) if latest else None


def _mtm_find_recon_file(folder):
    if not os.path.isdir(folder):
        return None
    for fn in os.listdir(folder):
        if os.path.isfile(os.path.join(folder, fn)) and mappers._mtm_is_recon_name(fn):
            return os.path.join(folder, fn)
    return None
