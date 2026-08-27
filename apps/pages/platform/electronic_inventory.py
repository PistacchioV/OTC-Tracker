# -*- coding: utf-8 -*-
"""O motor do Electronic Inventory — resolução de pasta de cliente no share,
o scanner do root com cache/TTL, versões ordinais e a listagem de arquivos.

Movido VERBATIM do `routes.py` (fase platform/ — CLAUDE.md §10). É horizontal:
além da tela do EI, o upload do Onboarding (Apêndice/Taxonomy/abonado — §
CLAUDE.md), o `_mc_confirmation_docs` do Confirmations Monitor e o link de
documento da esteira (`_mc_ei_link`) passam todos por aqui.

O `routes.py` mantém os nomes como ALIAS. O **`ELECTRONIC_INVENTORY_ROOT`
FICA no `routes` de propósito**: é a superfície de patch do `check_ei_api`
(`R.ELECTRONIC_INVENTORY_ROOT = tmp`), e movê-lo faria o teste apontar o root
falso enquanto o motor lê o de verdade — a mesma razão do `_B3_DATA_DIR` e do
`OTM_JSON_ROOT` (§314). O ESTADO do scanner (`_EI_ROOT_CACHE`, mutado in
place) mora AQUI, e o alias do routes continua vivo.

O `_CONFIRMATION_TYPES` vem DIRETO do `manual_conf` — é a mesma tupla que o
routes apelida, e o import direto preserva a linha
`_EI_CONFIRMATION_TYPES = _CONFIRMATION_TYPES` byte a byte.
"""
import json
import logging
import os
import re
import threading
import time
import traceback
from datetime import datetime

from apps.pages.manual_conf import CONFIRMATION_TYPES as _CONFIRMATION_TYPES

log = logging.getLogger('otc_tracker')

EI_SUBFOLDERS = ('Confirmations', 'Transactional', 'SSI')
_EI_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _ei_sanitize(name):
    """Windows-safe counterparty folder name (drop illegal chars incl. '/',
    collapse whitespace, trim trailing dots/spaces). Mirrors
    scripts/create_counterparty_folders.sanitize_folder_name."""
    s = _EI_ILLEGAL.sub('', name or '')
    s = re.sub(r'\s+', ' ', s).strip()
    return s.rstrip('. ')


def _ei_match_key(name):
    """Comparison key for a counterparty name: sanitized, uppercase and with the
    PUNCTUATION dropped (dots, commas, hyphens, apostrophes).

    The tolerant match already ignored case/whitespace/illegal chars, but kept
    punctuation — and punctuation is exactly where the row and the folder
    disagree: the DB says 'REFINARIA DE MATARIPE SA' (or 'S/A', whose slash the
    sanitizer strips into 'SA'), the share folder says 'S.A'. Same counterparty,
    zero matches — and the Monitor said 'no PDF' with the PDF sitting right
    there. Two DIFFERENT counterparties whose names differ only in punctuation
    do not exist in practice; the CNPJ comparison elsewhere makes the same bet
    digits-only, for the same reason.

    Letters and digits ONLY — not punctuation-swapped-for-space: 'S.A' must
    equal 'SA' AND 'S A', and any spacing rule breaks one of the two. Accented
    letters survive (\\w matches them in py3), so 'AÇOMINAS' keeps its Ç."""
    s = _ei_sanitize(name).upper()
    return re.sub(r'[\W_]+', '', s)


def _ei_actual_dir_name(folder):
    """On-disk folder name matching the sanitized `folder`, tolerant to
    case/whitespace/illegal-char/punctuation differences. Falls back to `folder`
    itself.

    Consults the background share scan first (_EI_ROOT_CACHE). Listing the root
    directly costs one stat per counterparty folder over the network share, so a
    cache hit is the difference between instant and tens of seconds — that scan
    is exactly why the cache exists."""
    from apps.pages import routes
    key = _ei_match_key(folder)
    try:
        with _EI_ROOT_CACHE_LOCK:
            complete = bool(_EI_ROOT_CACHE.get('complete'))
            cached = _EI_ROOT_CACHE['dirs'].get(key) if complete else None
    except Exception:
        complete, cached = False, None
    if cached:
        return cached
    if complete:
        # Scan finished and this counterparty has no folder yet — the caller
        # creates it under the sanitized name. No point re-listing the share.
        return folder
    try:
        if os.path.isdir(routes.ELECTRONIC_INVENTORY_ROOT):
            for entry in os.listdir(routes.ELECTRONIC_INVENTORY_ROOT):
                if (os.path.isdir(os.path.join(routes.ELECTRONIC_INVENTORY_ROOT, entry))
                        and _ei_match_key(entry) == key):
                    return entry
    except Exception:
        pass
    return folder


def _ei_client_dir_names(client):
    """TODAS as pastas da raiz que casam com esta contraparte (cega à pontuação).

    Antes de o casamento ignorar pontuação, o app não achava a pasta 'S.A' a
    partir da linha 'SA' e criava a gêmea sanitizada ao lado — o share guarda as
    DUAS, com documentos repartidos entre elas. `_ei_actual_dir_name` devolve UM
    nome por chave (é o contrato certo para ESCRITA, que precisa de um destino
    só); a LEITURA tem de olhar em todas, senão a gêmea vencedora do scan
    sombreia a outra e o PDF que está nela "não existe".

    Sempre devolve ao menos o nome sanitizado, para a leitura degradar para o
    comportamento antigo quando não há gêmea nenhuma."""
    from apps.pages import routes
    folder = _ei_sanitize(client)
    if not folder:
        return []
    key = _ei_match_key(folder)
    nomes = []
    try:
        with _EI_ROOT_CACHE_LOCK:
            complete = bool(_EI_ROOT_CACHE.get('complete'))
            if complete:
                nomes = list((_EI_ROOT_CACHE.get('multi') or {}).get(key) or [])
    except Exception:
        complete, nomes = False, []
    if not nomes and not complete:
        # Scan ainda correndo: uma listagem direta é lenta mas correta — e é o
        # mesmo fallback que `_ei_actual_dir_name` já paga nesse estado.
        try:
            if os.path.isdir(routes.ELECTRONIC_INVENTORY_ROOT):
                nomes = [e for e in os.listdir(routes.ELECTRONIC_INVENTORY_ROOT)
                         if _ei_match_key(e) == key
                         and os.path.isdir(os.path.join(routes.ELECTRONIC_INVENTORY_ROOT, e))]
        except Exception:
            nomes = []
    return nomes or [folder]

# ============================================================================
#  ELECTRONIC INVENTORY — per-counterparty document library
#  Root: ELECTRONIC_INVENTORY_ROOT\<Client>\{Confirmations,Transactional,SSI}
#  Confirmations are foldered by date (YYYY\MM\DD); SSI / Transactional are flat
#  with a "<TYPE> - <Client> - ddmmyyyy" naming convention. Browsing reads
#  straight from the network share — offline/empty just yields empty lists,
#  never a 500. Folder names come from RefData.json COUNTERPARTY (same source
#  scripts/create_counterparty_folders.py uses), matched tolerantly by
#  _ei_sanitize so a slightly different on-disk name is still found.
# ============================================================================
_EI_TRANSACTIONAL_TYPES = ('CGD', 'Appendix', 'CSA', 'CGD Amendment', 'Appendix Amendment')
# Confirmations are filed per trade product, under
# Confirmations/<yyyy>/<mm>. <Month>/<dd>/<Product>.
# A MESMA lista do cadastro da esteira e do dropdown do Track Confirmations —
# ver o import no topo. Uma cópia literal aqui foi o que deixou o upload falando
# 'FXO' e o cadastro de validação falando 'OPTION' para o mesmo documento.
_EI_CONFIRMATION_TYPES = _CONFIRMATION_TYPES
_EI_PREVIEWABLE = {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.txt'}
_EI_ALLOWED_UPLOAD = {'.pdf', '.msg', '.eml', '.doc', '.docx', '.xls', '.xlsx',
                      '.png', '.jpg', '.jpeg', '.gif', '.txt', '.zip'}


def _ei_refdata_clients():
    """[(name, spn)] from RefData.json. Best-effort: [] if missing/unreadable."""
    from apps.pages import routes
    try:
        with open(os.path.join(routes._B3_DATA_DIR, 'RefData.json'), encoding='utf-8') as fh:
            rows = json.load(fh)
    except Exception:
        return []
    out = []
    for r in (rows if isinstance(rows, list) else []):
        name = (r.get('COUNTERPARTY') or '').strip()
        if name:
            out.append((name, (r.get('SPN') or '').strip()))
    return out


def _ei_resolve_client_dir(client, create=False):
    """Absolute <ROOT>\\<client> path via the tolerant sanitized match. When
    create=True, ensures the three subfolders exist first."""
    from apps.pages import routes
    folder = _ei_sanitize(client)
    if not folder:
        return None
    if create:
        routes._ensure_counterparty_folders(client)
    # Cached share scan first — see _ei_actual_dir_name.
    return os.path.join(routes.ELECTRONIC_INVENTORY_ROOT, _ei_actual_dir_name(folder))


_EI_MONTH_NAMES = ('January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December')
# Month folder is '<mm>. <Month>' ('06. June') so the share sorts numerically and
# still reads at a glance in Explorer. Folders written before this convention are
# plain '<mm>' — _EI_MONTH_DIR_RE matches both so browsing never loses them.
_EI_MONTH_DIR_RE = re.compile(r'^(\d{2})(?:\.\s*[A-Za-z]+)?$')


def _ei_month_folder(mm):
    """'06' -> '06. June'. Falls back to the bare number if mm is out of range."""
    try:
        return '%s. %s' % (mm, _EI_MONTH_NAMES[int(mm) - 1])
    except Exception:
        return mm


def _ei_ordinal(n):
    """1 -> '1st', 2 -> '2nd', 3 -> '3rd', 4 -> '4th' … (11/12/13 are 'th')."""
    if 11 <= (n % 100) <= 13:
        return '%dth' % n
    return '%d%s' % (n, {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th'))


def _ei_version_prefix(n, style):
    """Version marker for the n-th copy. Confirmations read as '#2 NDF - …'
    (a trade count), agreements as '2nd CGD AMENDMENT - …' (a legal ordinal).
    The first copy carries no marker at all."""
    if n <= 1:
        return ''
    return ('#%d ' % n) if style == 'hash' else ('%s ' % _ei_ordinal(n))


def _ei_next_ordinal(target_dir, prefix, cname):
    """Which numbered copy of `<prefix> - <cname> - …` the next upload becomes.

    Counts what is already filed in `target_dir` and returns max+1, so a second
    CGD Amendment lands as '2nd CGD AMENDMENT - …' regardless of its date. Max
    (not count) so deleting a middle document never re-issues a taken number.
    Matches both marker styles ('#2 ' and '2nd ') so a folder that already holds
    one convention keeps counting correctly. Returns 1 when nothing matches."""
    pat = re.compile(
        r'^(?:(?:#(\d+)|(\d+)(?:st|nd|rd|th))\s+)?%s\s+-\s+%s\s+-\s+'
        % (re.escape(prefix), re.escape(cname)), re.IGNORECASE)
    highest = 0
    try:
        for entry in os.listdir(_ei_long_path(target_dir)):
            m = pat.match(entry)
            if m:
                seen = m.group(1) or m.group(2)
                highest = max(highest, int(seen) if seen else 1)
    except Exception:
        return 1        # unreadable/missing dir — caller still writes the file
    return highest + 1


def _ei_human_size(n):
    try:
        n = float(n)
    except Exception:
        return ''
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return ('%d %s' % (int(n), unit)) if unit == 'B' else ('%.1f %s' % (n, unit))
        n /= 1024.0
    return ''


def _ei_iter_files(base, doctype):
    """Yield a dict per file under <base>/<doctype>. Confirmations recurses and
    reads a dd/mm/yyyy date from the YYYY/MM/DD path; Transactional derives a
    sub-type from the '<TYPE> - ...' filename prefix. rel is POSIX, base-relative."""
    sub = os.path.join(base, doctype)
    # A varredura parte da forma ESTENDIDA (\\?\): na instância do JP a raiz é
    # o UNC (\\Nawest...\intra, +41 chars sobre o I:\) e o nome da contraparte
    # entra DUAS vezes no caminho (pasta e arquivo) — a SSI de uma filial de
    # nome longo passa dos 260 do MAX_PATH e o os.stat falhava com "not found",
    # com o `continue` pulando em silêncio um arquivo que está na pasta (foi a
    # SAINT-GOBAIN FILIAL 0177, 288 chars). O gate de 250 do _ei_long_path não
    # serve aqui: `sub` é curto, quem estoura são os caminhos que o walk monta
    # descendo dele (Confirmations desce ano/mês/dia/produto).
    if os.name == 'nt':
        sub = _ei_extended(os.path.normpath(os.path.abspath(sub)))
    if not os.path.isdir(sub):
        return
    for dirpath, _dirs, files in os.walk(sub):
        for fn in files:
            if fn.startswith('.') or fn.startswith('~$'):
                continue
            ext = os.path.splitext(fn)[1].lower()
            # Lista tudo que o Upload aceita (SSI costuma ser scan JPG/PNG, CGD
            # chega como .msg, …) — só PDF deixava sumir arquivo presente na
            # pasta (SSI da AMAGGI). Lixo de sistema (Thumbs.db, temporários)
            # continua fora por não estar no whitelist.
            if ext not in _EI_ALLOWED_UPLOAD:
                continue
            full = os.path.join(dirpath, fn)
            try:
                st = os.stat(full)
            except Exception:
                continue
            rel_within = os.path.relpath(dirpath, sub).replace('\\', '/')
            parts = [p for p in rel_within.split('/') if p and p != '.']
            doc_date = ''
            if doctype == 'Confirmations' and len(parts) >= 3:
                mdir = _EI_MONTH_DIR_RE.match(parts[1])
                if (re.match(r'^\d{4}$', parts[0]) and mdir and re.match(r'^\d{2}$', parts[2])):
                    doc_date = '%s/%s/%s' % (parts[2], mdir.group(1), parts[0])
            subtype = ''
            if doctype in ('Transactional', 'Confirmations'):
                # Drop the version marker ('2nd CGD AMENDMENT - …', '#2 NDF - …')
                # so the sub-type still matches every copy of the same kind.
                m = re.match(r'^\s*(?:(?:#\d+|\d+(?:st|nd|rd|th))\s+)?([A-Za-z0-9/&.\- ]+?)\s+-\s+',
                             fn, re.IGNORECASE)
                subtype = (m.group(1).strip().upper() if m else '')
            yield {
                'name': fn,
                'doctype': doctype,
                'subtype': subtype,
                # Montado das partes, não de relpath(full, base): `full` pode
                # estar na forma \\?\ e `base` na comum — relpath entre as duas
                # não tem raiz em comum. O resultado é byte a byte o de antes.
                'rel': '/'.join([doctype] + parts + [fn]),
                'ext': ext.lstrip('.').upper(),
                'previewable': ext in _EI_PREVIEWABLE,
                'size': st.st_size,
                'size_h': _ei_human_size(st.st_size),
                'doc_date': doc_date,
                'modified': int(st.st_mtime),
                'modified_h': datetime.fromtimestamp(st.st_mtime).strftime('%d/%m/%Y %H:%M'),
            }


# Cache for the (slow) network-share folder scan. The I:\ drive can take far
# longer than a request should ever block, so the scan runs in a background
# thread that fills this cache; requests serve whatever is cached and never wait
# more than a short grace period. `complete` distinguishes "scanned, folder truly
# absent" from "not scanned yet" so the UI never shows a false "no folder" badge.
_EI_ROOT_CACHE = {'ts': 0.0, 'exists': None, 'dirs': {}, 'multi': {},
                  'complete': False, 'scanning': False}
_EI_ROOT_CACHE_TTL = 300.0       # seconds a completed scan stays fresh
_EI_ROOT_CACHE_LOCK = threading.Lock()


def _ei_scan_root_worker():
    """Full (unbounded) share scan → fills _EI_ROOT_CACHE. Runs in a daemon thread
    so the slow enumeration never blocks the request that triggered it."""
    from apps.pages import routes
    exists, dirs, multi, ok = False, {}, {}, False
    try:
        exists = os.path.isdir(routes.ELECTRONIC_INVENTORY_ROOT)
        if exists:
            with os.scandir(routes.ELECTRONIC_INVENTORY_ROOT) as it:
                for entry in it:
                    try:
                        if entry.is_dir():
                            # A chave do cache é a MESMA do lookup
                            # (_ei_match_key): pontuação fora, senão a pasta
                            # 'S.A' nunca casa com a linha 'SA'.
                            key = _ei_match_key(entry.name)
                            dirs[key] = entry.name
                            # Gêmeas de pontuação têm a MESMA chave: antes do
                            # casamento cego à pontuação o app não achava a
                            # pasta 'S.A' e criava a 'SA' ao lado — o share
                            # guarda as DUAS, com documentos repartidos entre
                            # elas. Com uma entrada só, a última enumerada
                            # SOMBREAVA a outra e o que estava nela "sumia".
                            multi.setdefault(key, []).append(entry.name)
                    except OSError:
                        continue
        ok = True
    except Exception:
        log.warning('[ei] scanning root failed:\n%s', traceback.format_exc())
    with _EI_ROOT_CACHE_LOCK:
        if ok:
            _EI_ROOT_CACHE.update(ts=time.time(), exists=exists, dirs=dirs,
                                  multi=multi, complete=True)
        _EI_ROOT_CACHE['scanning'] = False


def _ei_scan_root(grace=6.0):
    """Return (root_exists, dirs, complete). Serves the cached scan when fresh;
    otherwise kicks off a background rescan and waits up to `grace` seconds for it
    to finish (so a responsive share fills in on the very first load), then returns
    the best data available. `complete` is False when the share hasn't been fully
    scanned yet — the caller must NOT claim a folder is missing in that case."""
    now = time.time()
    with _EI_ROOT_CACHE_LOCK:
        fresh = _EI_ROOT_CACHE['complete'] and (now - _EI_ROOT_CACHE['ts']) < _EI_ROOT_CACHE_TTL
        if fresh:
            return (_EI_ROOT_CACHE['exists'], dict(_EI_ROOT_CACHE['dirs']), True)
        start = not _EI_ROOT_CACHE['scanning']
        if start:
            _EI_ROOT_CACHE['scanning'] = True
    if start:
        threading.Thread(target=_ei_scan_root_worker, daemon=True).start()
    # Give the scan a short grace window to complete (short-circuits as soon as done).
    deadline = now + grace
    while time.time() < deadline:
        with _EI_ROOT_CACHE_LOCK:
            if _EI_ROOT_CACHE['complete'] and _EI_ROOT_CACHE['ts'] >= now - _EI_ROOT_CACHE_TTL:
                return (_EI_ROOT_CACHE['exists'], dict(_EI_ROOT_CACHE['dirs']), True)
        time.sleep(0.15)
    # Still scanning — return any stale data we have, flagged incomplete.
    with _EI_ROOT_CACHE_LOCK:
        return (_EI_ROOT_CACHE['exists'], dict(_EI_ROOT_CACHE['dirs']), False)


def _ei_extended(path):
    r"""Forma estendida (\\?\...) INCONDICIONAL — só a montagem da string, sem
    os gates de `_ei_long_path`. É a raiz de um os.walk que precisa disto: a
    raiz em si é curta e passaria pelo gate de 250, mas quem estoura o MAX_PATH
    são os caminhos que a varredura monta DESCENDO dela — e o prefixo só
    protege os filhos se já estiver no pai. O caminho tem de vir absoluto e
    normalizado: \\?\ desliga a normalização dali em diante."""
    if path.startswith('\\\\?\\'):
        return path
    if path.startswith('\\\\'):                 # UNC: \\server\share -> \\?\UNC\server\share
        return '\\\\?\\UNC\\' + path[2:]
    return '\\\\?\\' + path


def _ei_long_path(path):
    r"""Windows extended-length form (\\?\...) for paths near MAX_PATH (260).

    The Confirmations tree (<client>/Confirmations/<yyyy>/<mm>. <Month>/<dd>/
    <product>/<TYPE> - <client> - <ddmmyyyy>.pdf) repeats a counterparty name
    that can be 50+ chars twice, so a long name lands within a few dozen chars
    of the limit. Past it every os.path/open call fails with a plain "not
    found", which is indistinguishable from a missing file. No-op off Windows,
    on short paths, and on already-prefixed ones. The path must already be
    absolute and normalised — \\?\ disables all further normalisation."""
    if os.name != 'nt' or len(path) < 250:
        return path
    return _ei_extended(path)


def _ei_locate_file(client, rel):
    """Caminho completo de um arquivo do Electronic Inventory, ou None.

    O arquivo pode estar em QUALQUER gêmea de pontuação da contraparte
    ('S.A' ou 'SA') — a mesma razão pela qual a busca de docs olha em todas.

    Path-traversal guard: levanta ValueError num `rel` que escapa da pasta do
    cliente. De propósito NÃO usa os.path.realpath: no Windows ele resolve o
    drive mapeado (I:) para o alvo UNC, trocando 3 caracteres por ~37 e
    empurrando um caminho fundo de Confirmations para além do MAX_PATH — o
    arquivo então dava 404 estando lá no share. normpath colapsa '..' e '.'
    textualmente, que é exatamente o que a guarda precisa; um `rel` absoluto
    ou com drive escapa da base e cai na mesma comparação.
    """
    from apps.pages import routes
    for nome in _ei_client_dir_names(client):
        base_abs = os.path.normpath(os.path.abspath(
            os.path.join(routes.ELECTRONIC_INVENTORY_ROOT, nome)))
        cand = os.path.normpath(os.path.join(base_abs, rel))
        if not (cand == base_abs or cand.startswith(base_abs + os.sep)):
            raise ValueError('rel escapes the client folder')
        cand = _ei_long_path(cand)
        if os.path.isfile(cand):
            return cand
    return None
