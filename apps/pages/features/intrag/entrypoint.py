# -*- coding: utf-8 -*-
"""As quinze rotas das telas da Intrag."""
import json
import os
from datetime import datetime

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.intrag import commands, queries
from apps.pages.features.intrag.infra import persistence


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/api/intrag/ndf')
def api_intrag_ndf():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    date_str  = request.args.get('date', '').strip()       # YYYY-MM-DD (single day)
    date_from = request.args.get('date_from', '').strip()  # YYYY-MM-DD (range start)
    date_to   = request.args.get('date_to', '').strip()    # YYYY-MM-DD (range end)
    entries = []
    if date_from or date_to:
        # Trade Date range — load every day-file within [from, to] inclusive
        d_from = _R()._parse_date_any(date_from)
        d_to   = _R()._parse_date_any(date_to)
        # Com intervalo há o que PODAR: ano e mês inteiros fora dele são
        # descartados antes de o `scandir` entrar neles. Quem decide continua
        # sendo a data no NOME do arquivo, logo abaixo.
        for fp, fname, mtime, size in _R()._day_files(persistence.INTRAG_NDF_CACHE_DIR, '_intrag_ndf.json', d_from, d_to):
            fdate = _R()._parse_date_any(fname[:8])
            if fdate is None:
                continue
            if d_from and fdate < d_from:
                continue
            if d_to and fdate > d_to:
                continue
            entries.extend(_R()._day_json(fp, mtime, size))
    elif date_str:
        try:
            ref = datetime.strptime(date_str, '%Y-%m-%d')
            fname = ref.strftime('%Y%m%d') + '_intrag_ndf.json'
            fp = os.path.join(persistence.INTRAG_NDF_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'), fname)
            if os.path.isfile(fp):
                with open(fp, 'r', encoding='utf-8') as fh:
                    entries = json.load(fh)
                if not isinstance(entries, list):
                    entries = []
        except Exception as exc:
            _R().log.warning('[INTRAG NDF] date load error date=%r: %s', date_str, exc)
    else:
        # Sem data nenhuma: a árvore inteira, e aí só o memo ajuda.
        for fp, _fname, mtime, size in _R()._day_files(persistence.INTRAG_NDF_CACHE_DIR, '_intrag_ndf.json'):
            entries.extend(_R()._day_json(fp, mtime, size))
    # `na_2` é a coluna Information Source dos dois layouts; linha gravada
    # antes da limpeza ainda traz `[`/`|` no arquivo — sai legível daqui.
    return jsonify({'success': True, 'entries': queries._limpar_info_source(entries, 'na_2')})

@blueprint.route('/api/intrag/option')
def api_intrag_option():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    date_str  = request.args.get('date', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to   = request.args.get('date_to', '').strip()
    suffix = '_intrag_opt.json'
    entries = []
    if date_from or date_to:
        d_from = _R()._parse_date_any(date_from)
        d_to   = _R()._parse_date_any(date_to)
        # Com intervalo há o que PODAR: ano e mês inteiros fora dele são
        # descartados antes de o `scandir` entrar neles. Quem decide continua
        # sendo a data no NOME do arquivo, logo abaixo.
        for fp, fname, mtime, size in _R()._day_files(persistence.INTRAG_OPT_CACHE_DIR, suffix, d_from, d_to):
            fdate = _R()._parse_date_any(fname[:8])
            if fdate is None:
                continue
            if d_from and fdate < d_from:
                continue
            if d_to and fdate > d_to:
                continue
            entries.extend(_R()._day_json(fp, mtime, size))
    elif date_str:
        try:
            ref = datetime.strptime(date_str, '%Y-%m-%d')
            fp = os.path.join(persistence.INTRAG_OPT_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'),
                              ref.strftime('%Y%m%d') + suffix)
            if os.path.isfile(fp):
                with open(fp, 'r', encoding='utf-8') as fh:
                    entries = json.load(fh)
                if not isinstance(entries, list):
                    entries = []
        except Exception as exc:
            _R().log.warning('[INTRAG OPT] date load error date=%r: %s', date_str, exc)
    else:
        # Sem data nenhuma: a árvore inteira, e aí só o memo ajuda.
        for fp, _fname, mtime, size in _R()._day_files(persistence.INTRAG_OPT_CACHE_DIR, suffix):
            entries.extend(_R()._day_json(fp, mtime, size))
    return jsonify({'success': True,
                    'entries': queries._limpar_info_source(entries, 'information_source')})

@blueprint.route('/api/intrag/option/send-file', methods=['POST'])
def api_intrag_option_send_file():
    """Generate the Intrag Option .txt file(s) from the selected rows and flip
    New/Approved → Sent. Same standard folder as NDF; file Intrag-Option-YYYYMMDD.txt.

    Body: { "items": [ { "deal_id": str, "cells": [...38...] } ] }. Rows are
    grouped by Registration Date (data col index 3) — one file per date."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    payload = request.get_json(silent=True) or {}
    items = payload.get('items')
    if not isinstance(items, list) or not items:
        rows = payload.get('rows')
        if not isinstance(rows, list) or not rows:
            return jsonify({'success': False, 'message': 'No rows provided'}), 400
        items = [{'deal_id': '', 'cells': r} for r in rows if isinstance(r, list)]

    REG_DATE_IDX = 3   # Registration Date within the 38 data columns
    SENDABLE = {'New', 'Approved'}

    groups = {}
    sent_ids = []
    for it in items:
        if not isinstance(it, dict):
            continue
        cells = ['' if c is None else str(c) for c in (it.get('cells') or [])]
        if not cells:
            continue
        td_raw = cells[REG_DATE_IDX] if len(cells) > REG_DATE_IDX else ''
        ref = _R()._parse_date_any(td_raw) or datetime.now()
        groups.setdefault(ref.strftime('%Y%m%d'), {'ref': ref, 'rows': []})['rows'].append(cells)
        if it.get('deal_id'):
            sent_ids.append((it['deal_id'], td_raw))

    if not groups:
        return jsonify({'success': False, 'message': 'No valid rows provided'}), 400

    written = []
    try:
        with _R()._cache_lock:
            for key, grp in groups.items():
                ref = grp['ref']
                month_folder = ref.strftime('%m') + '. ' + _R()._EN_MONTH_NAMES[ref.month - 1]
                dir_path = os.path.join(persistence.INTRAG_NDF_SEND_DIR, ref.strftime('%Y'), month_folder, ref.strftime('%d'))
                os.makedirs(dir_path, exist_ok=True)
                base = 'Intrag-Option-' + key
                candidate = base + '.txt'
                n = 0
                while os.path.exists(os.path.join(dir_path, candidate)):
                    n += 1
                    candidate = base + ' (' + str(n) + ').txt'
                file_path = os.path.join(dir_path, candidate)
                with open(file_path, 'w', encoding='utf-8') as fh:
                    fh.write('\n'.join(';'.join(r) for r in grp['rows']))
                written.append(file_path)
                _R().log.info('[INTRAG OPT] Wrote send file %s (%d row(s))', file_path, len(grp['rows']))

            for deal_id, td_raw in sent_ids:
                fp, entries, idx = queries._find_intrag_opt_entry(deal_id, td_raw)
                if idx is None:
                    continue
                if (entries[idx].get('status') or 'New') in SENDABLE:
                    entries[idx]['status'] = 'Sent'
                    _R()._atomic_write_json(fp, entries)
    except Exception as exc:
        _R().log.error('[INTRAG OPT] send-file failed: %s', exc)
        return jsonify({'success': False, 'message': 'File generation failed: ' + str(exc)}), 500

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Intrag Sent', 'Intrag Option',
                         str(len(items)) + ' row' + ('' if len(items) == 1 else 's') + ' sent')
    return jsonify({'success': True, 'files': written, 'count': len(items)})

@blueprint.route('/api/intrag/option/edit', methods=['POST'])
def api_intrag_option_edit():
    """Row-level edit on an Intrag Option entry → status 'Pending', records maker."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload    = request.get_json(silent=True) or {}
    deal_id    = (payload.get('deal_id') or '').strip()
    trade_date = (payload.get('trade_date') or '').strip()
    fields     = payload.get('fields') or {}
    if not deal_id:
        return jsonify({'success': False, 'message': 'Missing deal_id'}), 400
    with _R()._cache_lock:
        fp, entries, idx = queries._find_intrag_opt_entry(deal_id, trade_date)
        if idx is None:
            return jsonify({'success': False, 'message': 'Entry not found'}), 404
        if isinstance(fields, dict):
            for k, v in fields.items():
                if k in entries[idx] and k not in ('_deal', '_client', 'status', 'maker', 'checker'):
                    entries[idx][k] = v
        # Mesma regra do NDF: Intrag ID digitado = Success (o desfecho do
        # Mapping); sem mudança nele, a edição de dado segue o 4-eyes.
        status = 'Pending'
        if 'intrag_id' in payload:
            novo   = str(payload.get('intrag_id') or '').strip()
            antigo = str(entries[idx].get('intrag_id') or '').strip()
            entries[idx]['intrag_id'] = novo
            if novo and novo != antigo:
                status = 'Success'
        entries[idx]['status']  = status
        entries[idx]['maker']   = session.get('user_sid', '')
        entries[idx]['checker'] = ''
        _R()._atomic_write_json(fp, entries)
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Deal Updated', 'Intrag Option', deal_id)
    return jsonify({'success': True, 'status': status})

@blueprint.route('/api/intrag/option/approve', methods=['POST'])
def api_intrag_option_approve():
    """Move an Intrag Option entry Pending → Approved (maker ≠ checker)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload    = request.get_json(silent=True) or {}
    deal_id    = (payload.get('deal_id') or '').strip()
    trade_date = (payload.get('trade_date') or '').strip()
    if not deal_id:
        return jsonify({'success': False, 'message': 'Missing deal_id'}), 400
    user_sid = session.get('user_sid', '')
    with _R()._cache_lock:
        fp, entries, idx = queries._find_intrag_opt_entry(deal_id, trade_date)
        if idx is None:
            return jsonify({'success': False, 'message': 'Entry not found'}), 404
        if (entries[idx].get('status') or '') != 'Pending':
            return jsonify({'success': False, 'message': 'Only Pending entries can be approved.'}), 400
        if entries[idx].get('maker') and entries[idx]['maker'] == user_sid:
            return jsonify({'success': False,
                            'message': 'Maker cannot approve their own change — a different user must check it.'}), 403
        entries[idx]['status']  = 'Approved'
        entries[idx]['checker'] = user_sid
        _R()._atomic_write_json(fp, entries)
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Status Updated', 'Intrag Option', deal_id + ' → Approved')
    return jsonify({'success': True, 'status': 'Approved'})

@blueprint.route('/api/intrag/ndf/send-file', methods=['POST'])
def api_intrag_ndf_send_file():
    """Generate the Intrag NDF .txt file(s) from the selected table rows.

    Body: { "rows": [ [col0, col1, ... col29], ... ] } — the 30 data columns,
    in NDF_COLS order. Rows are grouped by their Trade Date (data col index 10)
    so each file lands in its own date folder:

        I:\\Confirmation\\Derivativos\\OTC Tracker\\Intrag\\YYYY\\mm. Mmmm\\dd
        (e.g. 2026\\06. June\\22)

    Each file is named Intrag-NDF-YYYYMMDD.txt; if a file already exists it is
    NOT overwritten — a copy with " (1)", " (2)", ... is created instead. Each
    selected row becomes one line; columns are separated by ';'. A single-row
    (row-level) send therefore produces a file with one line.
    """
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    payload = request.get_json(silent=True) or {}
    # New format: items = [{ "deal_id": str, "cells": [...30...] }, ...]
    # Legacy format: rows = [[...30...], ...] (no status tracking).
    items = payload.get('items')
    if not isinstance(items, list) or not items:
        rows = payload.get('rows')
        if not isinstance(rows, list) or not rows:
            return jsonify({'success': False, 'message': 'No rows provided'}), 400
        items = [{'deal_id': '', 'cells': r} for r in rows if isinstance(r, list)]

    TRADE_DATE_IDX = 10  # index of Trade Date within the 30 data columns
    SENDABLE = {'New', 'Approved'}

    # Group rows by Trade Date → one file per distinct trade date. For the common
    # case (all rows share a trade date) this yields a single file.
    groups = {}
    sent_ids = []   # (deal_id, trade_date) pairs eligible to flip to 'Sent'
    for it in items:
        if not isinstance(it, dict):
            continue
        cells = ['' if c is None else str(c) for c in (it.get('cells') or [])]
        if not cells:
            continue
        td_raw = cells[TRADE_DATE_IDX] if len(cells) > TRADE_DATE_IDX else ''
        ref = _R()._parse_date_any(td_raw) or datetime.now()
        key = ref.strftime('%Y%m%d')
        groups.setdefault(key, {'ref': ref, 'rows': []})['rows'].append(cells)
        if it.get('deal_id'):
            sent_ids.append((it['deal_id'], td_raw))

    if not groups:
        return jsonify({'success': False, 'message': 'No valid rows provided'}), 400

    written = []
    try:
        with _R()._cache_lock:
            for key, grp in groups.items():
                ref = grp['ref']
                month_folder = ref.strftime('%m') + '. ' + _R()._EN_MONTH_NAMES[ref.month - 1]
                dir_path = os.path.join(
                    persistence.INTRAG_NDF_SEND_DIR, ref.strftime('%Y'), month_folder, ref.strftime('%d')
                )
                os.makedirs(dir_path, exist_ok=True)

                base = 'Intrag-NDF-' + key
                candidate = base + '.txt'
                n = 0
                while os.path.exists(os.path.join(dir_path, candidate)):
                    n += 1
                    candidate = base + ' (' + str(n) + ').txt'
                file_path = os.path.join(dir_path, candidate)

                content = '\n'.join(';'.join(r) for r in grp['rows'])
                with open(file_path, 'w', encoding='utf-8') as fh:
                    fh.write(content)
                written.append(file_path)
                _R().log.info('[INTRAG NDF] Wrote send file %s (%d row(s))', file_path, len(grp['rows']))

            # Flip status New/Approved → Sent for every persisted entry sent.
            for deal_id, td_raw in sent_ids:
                fp, entries, idx = queries._find_intrag_ndf_entry(deal_id, td_raw)
                if idx is None:
                    continue
                if (entries[idx].get('status') or 'New') in SENDABLE:
                    entries[idx]['status'] = 'Sent'
                    _R()._atomic_write_json(fp, entries)
    except Exception as exc:
        _R().log.error('[INTRAG NDF] send-file failed: %s', exc)
        return jsonify({'success': False, 'message': 'File generation failed: ' + str(exc)}), 500

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Intrag Sent', 'Intrag NDF',
                         str(len(items)) + ' row' + ('' if len(items) == 1 else 's') + ' sent')
    return jsonify({'success': True, 'files': written, 'count': len(items)})

@blueprint.route('/api/intrag/ndf/edit', methods=['POST'])
def api_intrag_ndf_edit():
    """Persist a row-level edit on an Intrag NDF entry → status becomes 'Pending'
    and the editing user is recorded as the maker (4-eyes control)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    payload    = request.get_json(silent=True) or {}
    deal_id    = (payload.get('deal_id') or '').strip()
    trade_date = (payload.get('trade_date') or '').strip()
    fields     = payload.get('fields') or {}
    if not deal_id:
        return jsonify({'success': False, 'message': 'Missing deal_id'}), 400

    with _R()._cache_lock:
        fp, entries, idx = queries._find_intrag_ndf_entry(deal_id, trade_date)
        if idx is None:
            return jsonify({'success': False, 'message': 'Entry not found'}), 404
        if isinstance(fields, dict):
            for k, v in fields.items():
                if k in entries[idx] and k not in ('_deal', '_client', 'status', 'maker', 'checker'):
                    entries[idx][k] = v
        # Intrag ID digitado na edição = o mesmo desfecho do Mapping: a linha
        # está casada com o registro e vai a Success. Inalterado (ou limpo), a
        # edição é de DADO e segue o 4-eyes de sempre (Pending).
        status = 'Pending'
        if 'intrag_id' in payload:
            novo   = str(payload.get('intrag_id') or '').strip()
            antigo = str(entries[idx].get('intrag_id') or '').strip()
            entries[idx]['intrag_id'] = novo
            if novo and novo != antigo:
                status = 'Success'
        entries[idx]['status']  = status
        entries[idx]['maker']   = session.get('user_sid', '')
        entries[idx]['checker'] = ''
        _R()._atomic_write_json(fp, entries)

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Deal Updated', 'Intrag NDF', deal_id)
    return jsonify({'success': True, 'status': status})

@blueprint.route('/api/intrag/ndf/approve', methods=['POST'])
def api_intrag_ndf_approve():
    """Move an Intrag NDF entry Pending → Approved. Enforces maker ≠ checker:
    the user who made the edit cannot approve their own change."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    payload    = request.get_json(silent=True) or {}
    deal_id    = (payload.get('deal_id') or '').strip()
    trade_date = (payload.get('trade_date') or '').strip()
    if not deal_id:
        return jsonify({'success': False, 'message': 'Missing deal_id'}), 400

    user_sid = session.get('user_sid', '')
    with _R()._cache_lock:
        fp, entries, idx = queries._find_intrag_ndf_entry(deal_id, trade_date)
        if idx is None:
            return jsonify({'success': False, 'message': 'Entry not found'}), 404
        if (entries[idx].get('status') or '') != 'Pending':
            return jsonify({'success': False, 'message': 'Only Pending entries can be approved.'}), 400
        if entries[idx].get('maker') and entries[idx]['maker'] == user_sid:
            return jsonify({'success': False,
                            'message': 'Maker cannot approve their own change — a different user must check it.'}), 403
        entries[idx]['status']  = 'Approved'
        entries[idx]['checker'] = user_sid
        _R()._atomic_write_json(fp, entries)

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Status Updated', 'Intrag NDF', deal_id + ' → Approved')
    return jsonify({'success': True, 'status': 'Approved'})

@blueprint.route('/api/intrag/ndf/mapping-intrag-id', methods=['POST'])
def api_intrag_ndf_mapping_intrag_id():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    results, err = commands._intrag_run_mapping(deals, 1, 'NDF - TERMO MERCADORIA', 2, queries._find_intrag_ndf_entry)
    if results is None:
        return jsonify({'ok': False, 'error': err}), 400
    return jsonify({'ok': True, 'results': results})

@blueprint.route('/api/intrag/option/mapping-intrag-id', methods=['POST'])
def api_intrag_option_mapping_intrag_id():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    results, err = commands._intrag_run_mapping(deals, 2, 'OPCAO', 8, queries._find_intrag_opt_entry)
    if results is None:
        return jsonify({'ok': False, 'error': err}), 400
    return jsonify({'ok': True, 'results': results})

@blueprint.route('/api/intrag/swap')
def api_intrag_swap():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    date_str  = request.args.get('date', '').strip()       # YYYY-MM-DD (single day)
    date_from = request.args.get('date_from', '').strip()  # YYYY-MM-DD (range start)
    date_to   = request.args.get('date_to', '').strip()    # YYYY-MM-DD (range end)
    suffix = '_intrag_swap.json'
    entries = []
    if date_from or date_to:
        d_from = _R()._parse_date_any(date_from)
        d_to   = _R()._parse_date_any(date_to)
        # Com intervalo há o que PODAR: ano e mês inteiros fora dele são
        # descartados antes de o `scandir` entrar neles. Quem decide continua
        # sendo a data no NOME do arquivo, logo abaixo.
        for fp, fname, mtime, size in _R()._day_files(persistence.INTRAG_SWAP_CACHE_DIR, suffix, d_from, d_to):
            fdate = _R()._parse_date_any(fname[:8])
            if fdate is None:
                continue
            if d_from and fdate < d_from:
                continue
            if d_to and fdate > d_to:
                continue
            entries.extend(_R()._day_json(fp, mtime, size))
    elif date_str:
        try:
            ref = datetime.strptime(date_str, '%Y-%m-%d')
            fp = os.path.join(persistence.INTRAG_SWAP_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'),
                              ref.strftime('%Y%m%d') + suffix)
            if os.path.isfile(fp):
                with open(fp, 'r', encoding='utf-8') as fh:
                    entries = json.load(fh)
                if not isinstance(entries, list):
                    entries = []
        except Exception as exc:
            _R().log.warning('[INTRAG SWAP] date load error date=%r: %s', date_str, exc)
    else:
        # Sem data nenhuma: a árvore inteira, e aí só o memo ajuda.
        for fp, _fname, mtime, size in _R()._day_files(persistence.INTRAG_SWAP_CACHE_DIR, suffix):
            entries.extend(_R()._day_json(fp, mtime, size))
    return jsonify({'success': True, 'entries': entries})

@blueprint.route('/api/intrag/swap/send-file', methods=['POST'])
def api_intrag_swap_send_file():
    """Generate the Intrag Swap .txt file(s) from the selected rows and flip
    New/Approved → Sent. Same standard folder as NDF; file Intrag-Swap-YYYYMMDD.txt.

    Body: { "items": [ { "deal_id": str, "cells": [...36...] } ] }. Rows are
    grouped by Data Início (data col index 2) — one file per date."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    payload = request.get_json(silent=True) or {}
    items = payload.get('items')
    if not isinstance(items, list) or not items:
        rows = payload.get('rows')
        if not isinstance(rows, list) or not rows:
            return jsonify({'success': False, 'message': 'No rows provided'}), 400
        items = [{'deal_id': '', 'cells': r} for r in rows if isinstance(r, list)]

    START_DATE_IDX = 2   # Data Início within the 36 data columns
    SENDABLE = {'New', 'Approved'}

    groups = {}
    sent_ids = []
    for it in items:
        if not isinstance(it, dict):
            continue
        cells = ['' if c is None else str(c) for c in (it.get('cells') or [])]
        if not cells:
            continue
        td_raw = cells[START_DATE_IDX] if len(cells) > START_DATE_IDX else ''
        ref = _R()._parse_date_any(td_raw) or datetime.now()
        groups.setdefault(ref.strftime('%Y%m%d'), {'ref': ref, 'rows': []})['rows'].append(cells)
        if it.get('deal_id'):
            sent_ids.append((it['deal_id'], td_raw))

    if not groups:
        return jsonify({'success': False, 'message': 'No valid rows provided'}), 400

    written = []
    try:
        with _R()._cache_lock:
            for key, grp in groups.items():
                ref = grp['ref']
                month_folder = ref.strftime('%m') + '. ' + _R()._EN_MONTH_NAMES[ref.month - 1]
                dir_path = os.path.join(persistence.INTRAG_NDF_SEND_DIR, ref.strftime('%Y'), month_folder, ref.strftime('%d'))
                os.makedirs(dir_path, exist_ok=True)
                base = 'Intrag-Swap-' + key
                candidate = base + '.txt'
                n = 0
                while os.path.exists(os.path.join(dir_path, candidate)):
                    n += 1
                    candidate = base + ' (' + str(n) + ').txt'
                file_path = os.path.join(dir_path, candidate)
                with open(file_path, 'w', encoding='utf-8') as fh:
                    fh.write('\n'.join(';'.join(r) for r in grp['rows']))
                written.append(file_path)
                _R().log.info('[INTRAG SWAP] Wrote send file %s (%d row(s))', file_path, len(grp['rows']))

            for deal_id, td_raw in sent_ids:
                fp, entries, idx = queries._find_intrag_swap_entry(deal_id, td_raw)
                if idx is None:
                    continue
                if (entries[idx].get('status') or 'New') in SENDABLE:
                    entries[idx]['status'] = 'Sent'
                    _R()._atomic_write_json(fp, entries)
    except Exception as exc:
        _R().log.error('[INTRAG SWAP] send-file failed: %s', exc)
        return jsonify({'success': False, 'message': 'File generation failed: ' + str(exc)}), 500

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Intrag Sent', 'Intrag Swap',
                         str(len(items)) + ' row' + ('' if len(items) == 1 else 's') + ' sent')
    return jsonify({'success': True, 'files': written, 'count': len(items)})

@blueprint.route('/api/intrag/swap/edit', methods=['POST'])
def api_intrag_swap_edit():
    """Row-level edit on an Intrag Swap entry → status 'Pending', records maker."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload    = request.get_json(silent=True) or {}
    deal_id    = (payload.get('deal_id') or '').strip()
    trade_date = (payload.get('trade_date') or '').strip()
    fields     = payload.get('fields') or {}
    if not deal_id:
        return jsonify({'success': False, 'message': 'Missing deal_id'}), 400
    with _R()._cache_lock:
        fp, entries, idx = queries._find_intrag_swap_entry(deal_id, trade_date)
        if idx is None:
            return jsonify({'success': False, 'message': 'Entry not found'}), 404
        if isinstance(fields, dict):
            for k, v in fields.items():
                if k in entries[idx] and k not in ('_deal', '_client', 'status', 'maker', 'checker'):
                    entries[idx][k] = v
        entries[idx]['status']  = 'Pending'
        entries[idx]['maker']   = session.get('user_sid', '')
        entries[idx]['checker'] = ''
        _R()._atomic_write_json(fp, entries)
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Deal Updated', 'Intrag Swap', deal_id)
    return jsonify({'success': True, 'status': 'Pending'})

@blueprint.route('/api/intrag/swap/approve', methods=['POST'])
def api_intrag_swap_approve():
    """Move an Intrag Swap entry Pending → Approved (maker ≠ checker)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload    = request.get_json(silent=True) or {}
    deal_id    = (payload.get('deal_id') or '').strip()
    trade_date = (payload.get('trade_date') or '').strip()
    if not deal_id:
        return jsonify({'success': False, 'message': 'Missing deal_id'}), 400
    user_sid = session.get('user_sid', '')
    with _R()._cache_lock:
        fp, entries, idx = queries._find_intrag_swap_entry(deal_id, trade_date)
        if idx is None:
            return jsonify({'success': False, 'message': 'Entry not found'}), 404
        if (entries[idx].get('status') or '') != 'Pending':
            return jsonify({'success': False, 'message': 'Only Pending entries can be approved.'}), 400
        if entries[idx].get('maker') and entries[idx]['maker'] == user_sid:
            return jsonify({'success': False,
                            'message': 'Maker cannot approve their own change — a different user must check it.'}), 403
        entries[idx]['status']  = 'Approved'
        entries[idx]['checker'] = user_sid
        _R()._atomic_write_json(fp, entries)
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Status Updated', 'Intrag Swap', deal_id + ' → Approved')
    return jsonify({'success': True, 'status': 'Approved'})

@blueprint.route('/api/intrag/swap/mapping-intrag-id', methods=['POST'])
def api_intrag_swap_mapping_intrag_id():
    # Boletas CSV: linhas de swap identificadas pela col B == 'SWAP' com o B3 ID
    # na col C (mesmo formato das linhas de NDF). Ajustar match_col/match_val/b3_col
    # aqui se o layout real do CSV de retorno para swap for diferente.
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    results, err = commands._intrag_run_mapping(deals, 1, 'SWAP', 2, queries._find_intrag_swap_entry)
    if results is None:
        return jsonify({'ok': False, 'error': err}), 400
    return jsonify({'ok': True, 'results': results})
