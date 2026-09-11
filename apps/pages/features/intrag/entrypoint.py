# -*- coding: utf-8 -*-
"""As rotas das telas da Intrag (NDF, Option, Swap, DCE Option e DCE Swap)."""
import json
import os
import traceback
from datetime import datetime

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.intrag import commands, domain, queries
from apps.pages.features.intrag.infra import persistence, xlsx_grid
from apps.pages import data_store as _store  # noqa: E402


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
        _dias = list(_R()._day_files(persistence.INTRAG_NDF_CACHE_DIR, '_intrag_ndf.json', d_from, d_to))
        # UMA abertura de banco para todos os dias enumerados, em vez de
        # uma por dia: eles são tabelas do MESMO banco do produto (§4).
        _R()._day_prefetch(_dias)
        for fp, fname, mtime, size in _dias:
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
            if _store.isfile(fp):
                from apps.pages import duck_read       # DB-only (fase 3)
                entries = duck_read.day_records(fp)
                if not isinstance(entries, list):
                    entries = []
        except Exception as exc:
            _R().log.warning('[INTRAG NDF] date load error date=%r: %s', date_str, exc)
    else:
        # Sem data nenhuma: a árvore inteira, e aí só o memo ajuda.
        _dias = list(_R()._day_files(persistence.INTRAG_NDF_CACHE_DIR, '_intrag_ndf.json'))
        # UMA abertura de banco para todos os dias enumerados, em vez de
        # uma por dia: eles são tabelas do MESMO banco do produto (§4).
        _R()._day_prefetch(_dias)
        for fp, _fname, mtime, size in _dias:
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
        _dias = list(_R()._day_files(persistence.INTRAG_OPT_CACHE_DIR, suffix, d_from, d_to))
        # UMA abertura de banco para todos os dias enumerados, em vez de
        # uma por dia: eles são tabelas do MESMO banco do produto (§4).
        _R()._day_prefetch(_dias)
        for fp, fname, mtime, size in _dias:
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
            if _store.isfile(fp):
                from apps.pages import duck_read       # DB-only (fase 3)
                entries = duck_read.day_records(fp)
                if not isinstance(entries, list):
                    entries = []
        except Exception as exc:
            _R().log.warning('[INTRAG OPT] date load error date=%r: %s', date_str, exc)
    else:
        # Sem data nenhuma: a árvore inteira, e aí só o memo ajuda.
        _dias = list(_R()._day_files(persistence.INTRAG_OPT_CACHE_DIR, suffix))
        # UMA abertura de banco para todos os dias enumerados, em vez de
        # uma por dia: eles são tabelas do MESMO banco do produto (§4).
        _R()._day_prefetch(_dias)
        for fp, _fname, mtime, size in _dias:
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
                while _store.exists(os.path.join(dir_path, candidate)):
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
                while _store.exists(os.path.join(dir_path, candidate)):
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
    # PREFIXO de família (ver `mappers._intrag_build_b3_map`): a tela manda os
    # DOIS contract types — 'NDF - TERMO MERCADORIA' e 'NDF - TERMO DE
    # MOEDAS' — e o retorno ecoa o texto de cada um.
    results, err = commands._intrag_run_mapping(deals, 1, 'NDF - TERMO', 2, queries._find_intrag_ndf_entry)
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
        _dias = list(_R()._day_files(persistence.INTRAG_SWAP_CACHE_DIR, suffix, d_from, d_to))
        # UMA abertura de banco para todos os dias enumerados, em vez de
        # uma por dia: eles são tabelas do MESMO banco do produto (§4).
        _R()._day_prefetch(_dias)
        for fp, fname, mtime, size in _dias:
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
            if _store.isfile(fp):
                from apps.pages import duck_read       # DB-only (fase 3)
                entries = duck_read.day_records(fp)
                if not isinstance(entries, list):
                    entries = []
        except Exception as exc:
            _R().log.warning('[INTRAG SWAP] date load error date=%r: %s', date_str, exc)
    else:
        # Sem data nenhuma: a árvore inteira, e aí só o memo ajuda.
        _dias = list(_R()._day_files(persistence.INTRAG_SWAP_CACHE_DIR, suffix))
        # UMA abertura de banco para todos os dias enumerados, em vez de
        # uma por dia: eles são tabelas do MESMO banco do produto (§4).
        _R()._day_prefetch(_dias)
        for fp, _fname, mtime, size in _dias:
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
                while _store.exists(os.path.join(dir_path, candidate)):
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


# ═════════════════════════ DCE Option ════════════════════════════════════════
# A quarta página da Intrag: as linhas nascem do IMPORT do bob-report (o extrato
# ITAUDataExtract de FX Option), não do New Deals. Daí para a frente o ciclo é o
# mesmo das irmãs — editar (Pending) → aprovar (Approved, maker ≠ checker) →
# mapear (Success) → enviar (.txt `;` na mesma pasta e com a mesma lógica de
# nome das outras páginas de Intrag).

@blueprint.route('/api/intrag/dce-option')
def api_intrag_dce_option():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    date_str  = request.args.get('date', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to   = request.args.get('date_to', '').strip()
    suffix = '_intrag_dce_opt.json'
    entries = []
    if date_from or date_to:
        d_from = _R()._parse_date_any(date_from)
        d_to   = _R()._parse_date_any(date_to)
        # Com intervalo há o que PODAR: ano e mês inteiros fora dele são
        # descartados antes de o `scandir` entrar neles. Quem decide continua
        # sendo a data no NOME do arquivo, logo abaixo.
        _dias = list(_R()._day_files(persistence.INTRAG_DCE_OPT_CACHE_DIR, suffix, d_from, d_to))
        # UMA abertura de banco para todos os dias enumerados, em vez de
        # uma por dia: eles são tabelas do MESMO banco do produto (§4).
        _R()._day_prefetch(_dias)
        for fp, fname, mtime, size in _dias:
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
            fp = os.path.join(persistence.INTRAG_DCE_OPT_CACHE_DIR, ref.strftime('%Y'), ref.strftime('%m'),
                              ref.strftime('%Y%m%d') + suffix)
            # Pelo FUNIL do daycache, como os outros dois ramos: é ele que lê
            # DB-first (o espelho DuckDB desta página) — a busca do smart filter
            # consulta o banco em qualquer forma de data.
            #
            # E SEM o `isfile` na frente: a leitura é DB-only e o JSON é o meio
            # de ESCRITA (§4), então exigir o arquivo aqui era exigir o meio de
            # escrita para poder LER — com o dia no banco e o JSON fora do
            # disco, a tela vinha vazia dizendo "No data available". Ausente, o
            # `os.stat` falha e a chave do memo vira (0, 0), que é justamente o
            # que faz o memo não guardar um dia que ainda vai chegar.
            try:
                st = _store.stat(fp)
                mtime, size = st.st_mtime, st.st_size
            except OSError:
                mtime, size = 0, 0
            entries = list(_R()._day_json(fp, mtime, size))
        except Exception as exc:
            _R().log.warning('[INTRAG DCE OPT] date load error date=%r: %s', date_str, exc)
    else:
        # Sem data nenhuma: a árvore inteira, e aí só o memo ajuda.
        _dias = list(_R()._day_files(persistence.INTRAG_DCE_OPT_CACHE_DIR, suffix))
        # UMA abertura de banco para todos os dias enumerados, em vez de
        # uma por dia: eles são tabelas do MESMO banco do produto (§4).
        _R()._day_prefetch(_dias)
        for fp, _fname, mtime, size in _dias:
            entries.extend(_R()._day_json(fp, mtime, size))
    return jsonify({'success': True,
                    'entries': queries._limpar_info_source(entries, 'information_source')})


@blueprint.route('/api/intrag/dce-option/import-api', methods=['POST'])
def api_intrag_dce_option_import_api():
    """Import manual do bob-report (botão da página; `ref_date` = campo
    Reference Date, default hoje) — o mesmo desenho dos import-api do New
    Deals, com o endereço vindo do cadastro API/Bob Reports Links."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    ref_date = (request.get_json(silent=True) or {}).get('ref_date')
    try:
        result = commands._dce_opt_import(ref_date=ref_date,
                                          sid=session.get('user_sid', '') or 'API',
                                          actor_name=session.get('user_name', '') or 'Bob Report')
    except Exception as e:                              # noqa: BLE001
        _R().log.warning('[INTRAG DCE OPT] manual bob-report import failed: %s', e)
        return jsonify({'success': False, 'message': str(e)}), 502
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Deals Imported', 'Intrag DCE Option',
                         str(result.get('imported', 0)) + ' row(s) from the ' +
                         str(result.get('ref_date', '')) + ' bob-report')
    return jsonify(result)


@blueprint.route('/api/intrag/dce-option/send-file', methods=['POST'])
def api_intrag_dce_option_send_file():
    """Generate the Intrag DCE Option .txt file(s) from the selected rows and
    flip New/Approved → Sent. Same standard folder as the other Intrag pages;
    file Intrag-DCE-Option-YYYYMMDD.txt.

    Body: { "items": [ { "deal_id": str, "cells": [...28...] } ] }. Rows are
    grouped by Trade Date (data col index 3) — one file per date."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    payload = request.get_json(silent=True) or {}
    items = payload.get('items')
    if not isinstance(items, list) or not items:
        rows = payload.get('rows')
        if not isinstance(rows, list) or not rows:
            return jsonify({'success': False, 'message': 'No rows provided'}), 400
        items = [{'deal_id': '', 'cells': r} for r in rows if isinstance(r, list)]

    TRADE_DATE_IDX = 3   # Trade Date within the 28 data columns
    SENDABLE = {'New', 'Approved'}

    groups = {}
    sent_ids = []
    for it in items:
        if not isinstance(it, dict):
            continue
        cells = ['' if c is None else str(c) for c in (it.get('cells') or [])]
        if not cells:
            continue
        td_raw = cells[TRADE_DATE_IDX] if len(cells) > TRADE_DATE_IDX else ''
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
                base = 'Intrag-DCE-Option-' + key
                candidate = base + '.txt'
                n = 0
                while _store.exists(os.path.join(dir_path, candidate)):
                    n += 1
                    candidate = base + ' (' + str(n) + ').txt'
                file_path = os.path.join(dir_path, candidate)
                with open(file_path, 'w', encoding='utf-8') as fh:
                    fh.write('\n'.join(';'.join(r) for r in grp['rows']))
                written.append(file_path)
                _R().log.info('[INTRAG DCE OPT] Wrote send file %s (%d row(s))', file_path, len(grp['rows']))

            for deal_id, td_raw in sent_ids:
                fp, entries, idx = queries._find_intrag_dce_opt_entry(deal_id, td_raw)
                if idx is None:
                    continue
                if (entries[idx].get('status') or 'New') in SENDABLE:
                    entries[idx]['status'] = 'Sent'
                    _R()._atomic_write_json(fp, entries)
    except Exception as exc:
        _R().log.error('[INTRAG DCE OPT] send-file failed: %s', exc)
        return jsonify({'success': False, 'message': 'File generation failed: ' + str(exc)}), 500

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Intrag Sent', 'Intrag DCE Option',
                         str(len(items)) + ' row' + ('' if len(items) == 1 else 's') + ' sent')
    return jsonify({'success': True, 'files': written, 'count': len(items)})


@blueprint.route('/api/intrag/dce-option/edit', methods=['POST'])
def api_intrag_dce_option_edit():
    """Row-level edit on an Intrag DCE Option entry → status 'Pending', records maker."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload    = request.get_json(silent=True) or {}
    deal_id    = (payload.get('deal_id') or '').strip()
    trade_date = (payload.get('trade_date') or '').strip()
    fields     = payload.get('fields') or {}
    if not deal_id:
        return jsonify({'success': False, 'message': 'Missing deal_id'}), 400
    with _R()._cache_lock:
        fp, entries, idx = queries._find_intrag_dce_opt_entry(deal_id, trade_date)
        if idx is None:
            return jsonify({'success': False, 'message': 'Entry not found'}), 404
        if isinstance(fields, dict):
            for k, v in fields.items():
                if k in entries[idx] and k not in ('_deal', '_client', 'status', 'maker', 'checker'):
                    entries[idx][k] = v
        # Mesma regra das irmãs: Intrag ID digitado = Success (o desfecho do
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
                         'Deal Updated', 'Intrag DCE Option', deal_id)
    return jsonify({'success': True, 'status': status})


@blueprint.route('/api/intrag/dce-option/approve', methods=['POST'])
def api_intrag_dce_option_approve():
    """Move an Intrag DCE Option entry Pending → Approved (maker ≠ checker)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload    = request.get_json(silent=True) or {}
    deal_id    = (payload.get('deal_id') or '').strip()
    trade_date = (payload.get('trade_date') or '').strip()
    if not deal_id:
        return jsonify({'success': False, 'message': 'Missing deal_id'}), 400
    user_sid = session.get('user_sid', '')
    with _R()._cache_lock:
        fp, entries, idx = queries._find_intrag_dce_opt_entry(deal_id, trade_date)
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
                         'Status Updated', 'Intrag DCE Option', deal_id + ' → Approved')
    return jsonify({'success': True, 'status': 'Approved'})


@blueprint.route('/api/intrag/dce-option/mapping-intrag-id', methods=['POST'])
def api_intrag_dce_option_mapping_intrag_id():
    # O mesmo processo das irmãs: linhas de opção do Boletas CSV (col C ==
    # 'OPCAO', col I = id, col A = Intrag ID); a chave que a tela manda como
    # `b3_id` é o Trade ID do extrato.
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    results, err = commands._intrag_run_mapping(deals, 2, 'OPCAO', 8, queries._find_intrag_dce_opt_entry)
    if results is None:
        return jsonify({'ok': False, 'error': err}), 400
    return jsonify({'ok': True, 'results': results})

@blueprint.route('/api/intrag/<family>/delete', methods=['POST'])
def api_intrag_delete(family):
    """Apaga linhas de uma família de Intrag DO ARQUIVO-DIA.

    Existe porque o Delete das quatro telas era `table.row().remove()` e mais
    nada — a linha sumia da tela e voltava no F5, e o re-import a reencontrava
    com o status antigo (ver `commands._intrag_delete_entries`).

    Família desconhecida é **400**, nunca um sucesso vazio: a tela que pedir a
    família errada tem de dizer isso na hora, e não apagar zero linhas em
    silêncio parecendo que apagou.
    """
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    items = payload.get('items') or []
    if not isinstance(items, list) or not items:
        return jsonify({'success': False, 'message': 'No rows to delete'}), 400
    try:
        apagadas, nao_achadas = commands._intrag_delete_entries(family, items)
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    except Exception:
        _R().log.error('[intrag-delete] %s failed:\n%s', family, traceback.format_exc())
        return jsonify({'success': False, 'message': 'Delete failed'}), 500
    return jsonify({'success': True, 'deleted': apagadas, 'not_found': nao_achadas})


# ═════════════════════════ DCE Swap ══════════════════════════════════════════
# A quinta página da Intrag: as linhas nascem de uma PLANILHA solta no
# dropzone (as duas tabelas da Athena — características por perna e fluxos
# por cupom — ligadas pelo Deal Name), não do New Deals nem do bob-report. A
# unidade da esteira é o DEAL (status/maker/checker/intrag_id vivem nele; a
# grade de pernas e a de fluxos são só as suas duas faces), e o arquivo da
# Intrag é UMA linha por deal, traduzida do par Pay + Rec no servidor
# (`commands._dce_swap_line_fields`) — por isso a página tem preview de duplo
# clique: o que se vê na grade não é o que vai no arquivo.

_DCES_SUFFIX = '_intrag_dce_swap.json'


def _dces_entries(date_str, date_from, date_to):
    """Os deals do(s) arquivo(s)-dia pedidos — o mesmo desenho do DCE Option."""
    entries = []
    if date_from or date_to:
        d_from = _R()._parse_date_any(date_from)
        d_to   = _R()._parse_date_any(date_to)
        _dias = list(_R()._day_files(persistence.INTRAG_DCE_SWAP_CACHE_DIR, _DCES_SUFFIX, d_from, d_to))
        _R()._day_prefetch(_dias)
        for fp, fname, mtime, size in _dias:
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
            fp = persistence._intrag_dce_swap_day_path(ref)
            try:
                st = _store.stat(fp)
                mtime, size = st.st_mtime, st.st_size
            except OSError:
                mtime, size = 0, 0
            entries = list(_R()._day_json(fp, mtime, size))
        except Exception as exc:
            _R().log.warning('[INTRAG DCE SWAP] date load error date=%r: %s', date_str, exc)
    else:
        _dias = list(_R()._day_files(persistence.INTRAG_DCE_SWAP_CACHE_DIR, _DCES_SUFFIX))
        _R()._day_prefetch(_dias)
        for fp, _fname, mtime, size in _dias:
            entries.extend(_R()._day_json(fp, mtime, size))
    return [e for e in entries if isinstance(e, dict)]


@blueprint.route('/api/intrag/dce-swap')
def api_intrag_dce_swap():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    entries = _dces_entries(request.args.get('date', '').strip(),
                            request.args.get('date_from', '').strip(),
                            request.args.get('date_to', '').strip())
    return jsonify({'success': True, 'entries': entries,
                    'leg_fields': list(domain._DCE_SWAP_LEG_FIELDS),
                    'flow_fields': list(domain._DCE_SWAP_FLOW_FIELDS)})


@blueprint.route('/api/intrag/dce-swap/import-file', methods=['POST'])
def api_intrag_dce_swap_import_file():
    """A planilha do dropzone (multipart `file`; `trade_date` opcional em
    dd/mm/aaaa ou ISO, default hoje) → deals no arquivo-dia da Trade Date."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    f = request.files.get('file')
    if f is None or not f.filename:
        return jsonify({'success': False, 'message': 'No file received'}), 400
    ref_dt = _R()._api_ref_date(request.form.get('trade_date'))
    try:
        grid, sheets = xlsx_grid.grid_from_upload(f.filename, f.read())
    except Exception as exc:                                # noqa: BLE001
        _R().log.warning('[INTRAG DCE SWAP] unreadable upload %r: %s', f.filename, exc)
        return jsonify({'success': False, 'message': 'Could not read the file: ' + str(exc)}), 400
    try:
        result = commands._dce_swap_import_grid(grid, ref_dt, sid=session.get('user_sid', ''), sheets=sheets)
    except Exception as exc:                                # noqa: BLE001
        _R().log.error('[INTRAG DCE SWAP] import failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'message': 'Import failed: ' + str(exc)}), 500
    if not result.get('imported'):
        return jsonify({'success': False,
                        'message': 'No deal found — the file needs the two tables '
                                   '(Deal Name/Direction… and Deal Name/Coupon…).',
                        'unknown_headers': result.get('unknown_headers', [])}), 400
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                              'Deals Imported', 'Intrag DCE Swap',
                              str(result.get('imported', 0)) + ' deal(s) from ' + str(f.filename))
    result['file'] = f.filename
    return jsonify(result)


def _dces_clean_rows(rows, fields):
    """Pernas/fluxos vindos da tela: só as chaves do contrato, tudo texto."""
    out = []
    for r in (rows or []):
        if not isinstance(r, dict):
            continue
        row = {k: ('' if r.get(k) is None else str(r.get(k))).strip() for k in fields}
        if any(row.values()):
            out.append(row)
    return out


@blueprint.route('/api/intrag/dce-swap/edit', methods=['POST'])
def api_intrag_dce_swap_edit():
    """Edição do DEAL (pernas + fluxos + Intrag ID) → status 'Pending', maker.
    Intrag ID digitado = Success (o desfecho do Mapping), como nas irmãs."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload    = request.get_json(silent=True) or {}
    deal_id    = (payload.get('deal_id') or '').strip()
    trade_date = (payload.get('trade_date') or '').strip()
    if not deal_id:
        return jsonify({'success': False, 'message': 'Missing deal_id'}), 400
    with _R()._cache_lock:
        fp, entries, idx = queries._find_intrag_dce_swap_entry(deal_id, trade_date)
        if idx is None:
            return jsonify({'success': False, 'message': 'Entry not found'}), 404
        e = entries[idx]
        if 'legs' in payload:
            e['legs'] = _dces_clean_rows(payload.get('legs'), domain._DCE_SWAP_LEG_FIELDS)
        if 'flows' in payload:
            e['flows'] = _dces_clean_rows(payload.get('flows'), domain._DCE_SWAP_FLOW_FIELDS)
        pay = next((l for l in e.get('legs') or []
                    if str(l.get('direction') or '').strip().lower() == 'pay'), None)
        if pay:
            e['_client'] = pay.get('counterparty') or e.get('_client') or ''
        status = 'Pending'
        if 'intrag_id' in payload:
            novo   = str(payload.get('intrag_id') or '').strip()
            antigo = str(e.get('intrag_id') or '').strip()
            e['intrag_id'] = novo
            if novo and novo != antigo:
                status = 'Success'
        e['status']  = status
        e['maker']   = session.get('user_sid', '')
        e['checker'] = ''
        _R()._atomic_write_json(fp, entries)
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                              'Deal Updated', 'Intrag DCE Swap', deal_id)
    return jsonify({'success': True, 'status': status, 'entry': e})


@blueprint.route('/api/intrag/dce-swap/add', methods=['POST'])
def api_intrag_dce_swap_add():
    """Deal digitado à mão (Add Row): nasce New no arquivo-dia da Trade Date.
    Diferente das irmãs, aqui o Add GRAVA — um deal só de tela não teria
    preview nem send, porque a linha é montada no servidor."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    legs  = _dces_clean_rows(payload.get('legs'), domain._DCE_SWAP_LEG_FIELDS)
    flows = _dces_clean_rows(payload.get('flows'), domain._DCE_SWAP_FLOW_FIELDS)
    deal_id = next((l['deal_name'] for l in legs if l.get('deal_name')), '')
    if not deal_id:
        return jsonify({'success': False, 'message': 'Deal Name is required (on a leg)'}), 400
    for l in legs:
        l['deal_name'] = l['deal_name'] or deal_id
    ref_dt = _R()._api_ref_date(payload.get('trade_date'))
    pay = next((l for l in legs if str(l.get('direction') or '').strip().lower() == 'pay'), None)
    entry = {'_deal': deal_id, '_client': (pay or legs[0]).get('counterparty') or '',
             'trade_date': ref_dt.strftime('%Y-%m-%d'),
             'intrag_id': str(payload.get('intrag_id') or '').strip(),
             'legs': legs, 'flows': flows, 'status': 'New', 'maker': '', 'checker': ''}
    persistence._intrag_dce_swap_upsert(ref_dt, [entry])
    return jsonify({'success': True, 'entry': entry})


@blueprint.route('/api/intrag/dce-swap/approve', methods=['POST'])
def api_intrag_dce_swap_approve():
    """Pending → Approved (maker ≠ checker)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload    = request.get_json(silent=True) or {}
    deal_id    = (payload.get('deal_id') or '').strip()
    trade_date = (payload.get('trade_date') or '').strip()
    if not deal_id:
        return jsonify({'success': False, 'message': 'Missing deal_id'}), 400
    user_sid = session.get('user_sid', '')
    with _R()._cache_lock:
        fp, entries, idx = queries._find_intrag_dce_swap_entry(deal_id, trade_date)
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
                              'Status Updated', 'Intrag DCE Swap', deal_id + ' → Approved')
    return jsonify({'success': True, 'status': 'Approved'})


@blueprint.route('/api/intrag/dce-swap/mapping-intrag-id', methods=['POST'])
def api_intrag_dce_swap_mapping_intrag_id():
    # O mesmo processo da Intrag Swap: linhas de swap do Boletas CSV (col B ==
    # 'SWAP', id na col C, Intrag ID na col A); a chave que a tela manda como
    # `b3_id` é o Deal Name — o Contract Number que vai no arquivo.
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    results, err = commands._intrag_run_mapping(deals, 1, 'SWAP', 2, queries._find_intrag_dce_swap_entry)
    if results is None:
        return jsonify({'ok': False, 'error': err}), 400
    return jsonify({'ok': True, 'results': results})


def _dces_preview_payload(entry):
    fields = commands._dce_swap_line_fields(entry)
    names = domain._DCE_SWAP_FILE_FIELDS
    return {'fields': [{'seq': i + 1, 'field': names[i] if i < len(names) else '', 'value': v}
                       for i, v in enumerate(fields)],
            'line': ';'.join(fields)}


@blueprint.route('/api/intrag/dce-swap/preview')
def api_intrag_dce_swap_preview():
    """A linha da Intrag de UM deal, campo a campo — o preview do duplo clique.
    Deal sem par Pay+Rec devolve 422 com o motivo (é o que o Send recusaria)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    deal_id    = (request.args.get('deal_id') or '').strip()
    trade_date = (request.args.get('trade_date') or '').strip()
    fp, entries, idx = queries._find_intrag_dce_swap_entry(deal_id, trade_date)
    if idx is None:
        return jsonify({'success': False, 'message': 'Entry not found'}), 404
    entry = entries[idx]
    try:
        out = _dces_preview_payload(entry)
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 422
    ref = _R()._parse_date_any(entry.get('trade_date')) or datetime.now()
    out.update({'success': True, 'deal_id': deal_id,
                'file_name': commands._dce_swap_file_name(ref)})
    return jsonify(out)


@blueprint.route('/api/intrag/dce-swap/send-file', methods=['POST'])
def api_intrag_dce_swap_send_file():
    """Gera o arquivo da Intrag dos deals selecionados e vira New/Approved →
    Sent. Body: { "items": [ { "deal_id", "trade_date" } ] }. A linha é
    montada AQUI, do arquivo-dia (não das células da tela), agrupada por
    Trade Date — um arquivo por data, `LAWTON_OFF_SWAP_AAAAMMDD.txt` na pasta
    padrão da Intrag. Um deal sem par Pay+Rec recusa o lote INTEIRO com 400
    dizendo qual — nada é escrito pela metade."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    items = payload.get('items')
    if not isinstance(items, list) or not items:
        return jsonify({'success': False, 'message': 'No rows provided'}), 400
    SENDABLE = {'New', 'Approved'}
    groups, problemas, alvos = {}, [], []
    for it in items:
        if not isinstance(it, dict):
            continue
        deal_id = str(it.get('deal_id') or '').strip()
        td_raw = str(it.get('trade_date') or '').strip()
        if not deal_id:
            continue
        fp, entries, idx = queries._find_intrag_dce_swap_entry(deal_id, td_raw)
        if idx is None:
            problemas.append(deal_id + ': not found')
            continue
        entry = entries[idx]
        if (entry.get('status') or 'New') not in SENDABLE:
            problemas.append(deal_id + ': status ' + str(entry.get('status') or 'New'))
            continue
        try:
            fields = commands._dce_swap_line_fields(entry)
        except ValueError as exc:
            problemas.append(deal_id + ': ' + str(exc))
            continue
        ref = _R()._parse_date_any(entry.get('trade_date')) or datetime.now()
        groups.setdefault(ref.strftime('%Y%m%d'), {'ref': ref, 'rows': []})['rows'].append(fields)
        alvos.append((deal_id, entry.get('trade_date') or td_raw))
    if problemas:
        return jsonify({'success': False, 'message': 'Nothing sent — ' + '; '.join(problemas)}), 400
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
                nome = commands._dce_swap_file_name(ref)
                base, ext = os.path.splitext(nome)
                candidate = nome
                n = 0
                while _store.exists(os.path.join(dir_path, candidate)):
                    n += 1
                    candidate = base + ' (' + str(n) + ')' + ext
                file_path = os.path.join(dir_path, candidate)
                with open(file_path, 'w', encoding='utf-8') as fh:
                    fh.write('\n'.join(';'.join(r) for r in grp['rows']))
                written.append(file_path)
                _R().log.info('[INTRAG DCE SWAP] Wrote send file %s (%d row(s))', file_path, len(grp['rows']))
            for deal_id, td_raw in alvos:
                fp, entries, idx = queries._find_intrag_dce_swap_entry(deal_id, td_raw)
                if idx is None:
                    continue
                if (entries[idx].get('status') or 'New') in SENDABLE:
                    entries[idx]['status'] = 'Sent'
                    _R()._atomic_write_json(fp, entries)
    except Exception as exc:
        _R().log.error('[INTRAG DCE SWAP] send-file failed: %s', exc)
        return jsonify({'success': False, 'message': 'File generation failed: ' + str(exc)}), 500

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                              'Intrag Sent', 'Intrag DCE Swap',
                              str(len(alvos)) + ' deal' + ('' if len(alvos) == 1 else 's') + ' sent')
    return jsonify({'success': True, 'files': written, 'count': len(alvos)})
