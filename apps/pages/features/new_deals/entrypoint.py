# -*- coding: utf-8 -*-
"""As 44 rotas da família New Deals (NDF, FXO, Commodities e os genéricos).

Só a casca — a última e maior. Os MOTORES ficam no routes até a fase
platform/: os caches por dia e a persistência (`_generic_nd_*`, `_nd_*`), o
lookup de contraparte (`_ndf_ref_by_accronym`), o roteamento por publisher, o
espelho Lawton, os geradores TER/Conecta e os hooks de espelhamento (Pending
Confirmation, esteira, Intrag) — tudo alcançado por `_R()`.
"""
import io
import json
import os
import re
from datetime import datetime

from flask import jsonify, request, session

from apps.pages import blueprint


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/api/new-deals/opt-commodities/cache', methods=['POST'])
def api_save_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400
    _R()._nd_fix_underlying_marker(data)

    # Use the deal's TradeDate (dd/mm/yyyy) for the directory; fall back to today
    trade_date_raw = data.get('TradeDate', '')
    try:
        ref_date = datetime.strptime(trade_date_raw, '%d/%m/%Y')
    except (ValueError, TypeError):
        ref_date = datetime.now()

    dir_path = os.path.join(
        _R().CACHE_BASE_DIR,
        ref_date.strftime('%Y'),
        ref_date.strftime('%m')
    )
    os.makedirs(dir_path, exist_ok=True)

    fname = ref_date.strftime('%Y%m%d') + '_optcomm.json'
    file_path = os.path.join(dir_path, fname)

    with _R()._cache_lock:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
            except (json.JSONDecodeError, ValueError):
                deals = []
        else:
            deals = []

        deal_name   = data.get('Deal', '').strip()
        client_name = data.get('Client', '').strip()
        data.pop('_client', None)
        existing_idx = next((i for i, d in enumerate(deals)
                             if deal_name
                             and d.get('Deal', '').strip() == deal_name
                             and d.get('Client', '').strip() == client_name), None)
        if existing_idx is not None:
            deals[existing_idx] = data
        else:
            deals.append(data)
        target_idx = existing_idx if existing_idx is not None else len(deals) - 1
        for _k in ('Maker', 'Checker'):
            if _k in deals[target_idx]:
                deals[target_idx][_k] = deals[target_idx].pop(_k)
        _R()._atomic_write_json(file_path, deals)

    return jsonify({"success": True, "deal": data.get('Deal', '')})

@blueprint.route('/api/new-deals/opt-commodities/cache/search', methods=['POST'])
def api_search_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    body = request.get_json(silent=True) or {}
    filters = body.get('filters', [])

    # `_day_files` + `_day_json`: `os.scandir` (a listagem já traz mtime e
    # tamanho) e memo por arquivo, então a segunda busca não reabre o que não
    # mudou. A busca não tem intervalo de datas, então não há o que podar.
    matched = []
    for fpath, _fname, mtime, size in _R()._day_files(_R().CACHE_BASE_DIR, '_optcomm.json'):
        for deal in _R()._day_json(fpath, mtime, size):
            if _R()._deal_matches(deal, filters):
                matched.append(deal)

    return jsonify({"success": True, "deals": matched})

@blueprint.route('/api/new-deals/opt-commodities/cache/<deal_id>', methods=['PATCH'])
def api_update_deal_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    client  = request.args.get('client')
    updates = request.get_json(silent=True)
    if not updates:
        return jsonify({"success": False, "message": "No data provided"}), 400

    file_path, _ = _R()._find_deal_in_cache(deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _R()._cache_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                deals = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            deals = []
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        updates.pop('_client', None)
        deals[idx].update(updates)
        for _k in ('Maker', 'Checker'):
            if _k in deals[idx]:
                deals[idx][_k] = deals[idx].pop(_k)
        _R()._atomic_write_json(file_path, deals)
        updated_deal = deals[idx].copy()

    # Mirror NDF: push to Intrag Option when Status→Success and the counterparty
    # is Banco J.P. Morgan (intragroup). External clients instead become a fresh
    # outstanding confirmation → Pending Confirmation (the manual-mapping twin of
    # the return-file scan trigger; _pc_save_from_deal skips internal legs itself).
    if str(updates.get('Status', '')) == 'Success':
        _R()._intrag_engine()._maybe_save_intrag_opt(updated_deal)
        _R()._pc_save_from_deal(updated_deal, 'OPTION COMM')     # → pending confirmation

    _fields = {k: v for k, v in updates.items() if k not in ('Maker', 'Checker', '_client')}
    if _fields:
        if 'Status' in _fields:
            # The 'Sent' transition is already announced by the 'Sent to B3'
            # notification emitted from send-conecta — skip the redundant
            # 'Status Updated' entry so the bell shows a single item per send.
            if str(_fields.get('Status', '')) != 'Sent':
                _R()._create_notification(
                    session.get('user_sid', ''), session.get('user_name', ''),
                    'Status Updated', 'Opt Comm',
                    deal_id + ' → ' + str(_fields.get('Status', '')) + _R()._nd_token(updated_deal.get('TradeDate'))
                )
        else:
            _R()._create_notification(
                session.get('user_sid', ''), session.get('user_name', ''),
                'Deal Updated', 'Opt Comm',
                deal_id + ' (' + ', '.join(_fields.keys()) + ')' + _R()._nd_token(updated_deal.get('TradeDate'))
            )
    return jsonify({"success": True})

@blueprint.route('/api/new-deals/opt-commodities/cache/<deal_id>', methods=['DELETE'])
def api_delete_deal_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    client = request.args.get('client')
    file_path, _ = _R()._find_deal_in_cache(deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _R()._cache_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                deals = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            deals = []
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        removed = deals.pop(idx)
        _R()._atomic_write_json(file_path, deals)

    _R()._create_notification(
        session.get('user_sid', ''), session.get('user_name', ''),
        'Deal Deleted', 'Opt Comm', deal_id + _R()._nd_token((removed or {}).get('TradeDate'))
    )
    return jsonify({"success": True})

@blueprint.route('/api/new-deals/opt-commodities/cache/bulk-delete', methods=['POST'])
def api_bulk_delete_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data  = request.get_json(silent=True)
    pairs = data.get('pairs', []) if data else []
    if not pairs:
        return jsonify({"success": False, "message": "No pairs provided"}), 400

    pair_set = {(p.get('deal', ''), p.get('client', '')) for p in pairs}

    # Group pairs by their source file (search outside the lock — read-only scan)
    file_pairs = {}
    for deal_name, client_name in pair_set:
        fp, _ = _R()._find_deal_in_cache(deal_name, client_name)
        if fp:
            file_pairs.setdefault(fp, set()).add((deal_name, client_name))

    deleted = 0
    for fp, pairs_in_file in file_pairs.items():
        with _R()._cache_lock:
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                deals = []
            if not isinstance(deals, list):
                deals = [deals]
            before = len(deals)
            deals  = [d for d in deals if (d.get('Deal', ''), d.get('Client', '')) not in pairs_in_file]
            deleted += before - len(deals)
            _R()._atomic_write_json(fp, deals)

    not_found = len(pair_set) - deleted
    if deleted > 0:
        _R()._create_notification(
            session.get('user_sid', ''), session.get('user_name', ''),
            'Bulk Delete', 'Opt Comm',
            str(deleted) + ' deal' + ('s' if deleted != 1 else '') + ' deleted'
        )
    return jsonify({"success": True, "deleted": deleted, "not_found": not_found})

@blueprint.route('/api/new-deals/opt-commodities/cache/bulk-patch', methods=['POST'])
def api_opt_bulk_patch_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data    = request.get_json(silent=True)
    patches = data.get('patches', []) if data else []
    if not patches:
        return jsonify({"success": False, "message": "No patches provided"}), 400

    # Group by source file (outside lock — read-only scan)
    file_patches = {}
    for p in patches:
        deal_id = p.get('deal_id', '')
        client  = p.get('client', '')
        updates = p.get('updates', {})
        if not deal_id or not updates:
            continue
        fp, _ = _R()._find_deal_in_cache(deal_id, client)
        if fp:
            file_patches.setdefault(fp, []).append((deal_id, client, updates))

    updated = 0
    for fp, file_ops in file_patches.items():
        with _R()._cache_lock:
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                deals = []
            for deal_id, client, updates in file_ops:
                want_client = (client or '').strip()
                matching = [i for i, d in enumerate(deals)
                            if (d.get('Deal') or '').strip() == deal_id.strip()
                            and (not want_client or (d.get('Client') or '').strip() == want_client)]
                if matching:
                    for idx in matching:
                        deals[idx].update(updates)
                        updated += 1
                else:
                    _R().log.warning("[OPT BULK-PATCH] idx not found: deal=%r client=%r in %s",
                                deal_id, client, fp)
            _R()._atomic_write_json(fp, deals)

    if updated > 0:
        _R()._create_notification(
            session.get('user_sid', ''), session.get('user_name', ''),
            'Bulk Update', 'Opt Comm',
            str(updated) + ' deal' + ('s' if updated != 1 else '') + ' updated'
        )
    return jsonify({"success": True, "updated": updated})

@blueprint.route('/api/new-deals/opt-fxo/cache', methods=['POST'])
def api_save_fxo_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    trade_date_raw = data.get('TradeDate', '')
    try:
        ref_date = datetime.strptime(trade_date_raw, '%d/%m/%Y')
    except (ValueError, TypeError):
        ref_date = datetime.now()

    dir_path = os.path.join(_R().OPT_FXO_CACHE_DIR, ref_date.strftime('%Y'), ref_date.strftime('%m'))
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, ref_date.strftime('%Y%m%d') + '_optfxo.json')

    with _R()._cache_lock:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
            except (json.JSONDecodeError, ValueError):
                deals = []
        else:
            deals = []

        deal_name   = data.get('Deal', '').strip()
        client_name = data.get('Client', '').strip()
        data.pop('_client', None)
        existing_idx = next((i for i, d in enumerate(deals)
                             if deal_name
                             and d.get('Deal', '').strip() == deal_name
                             and d.get('Client', '').strip() == client_name), None)
        # Persist in table-column order (Maker/Checker last) — not alphabetical.
        if existing_idx is not None:
            deals[existing_idx] = _R()._fxo_order_deal(data)
        else:
            deals.append(_R()._fxo_order_deal(data))
        _R()._atomic_write_json(file_path, deals)

    return jsonify({"success": True, "deal": data.get('Deal', '')})

@blueprint.route('/api/new-deals/opt-fxo/cache/search', methods=['POST'])
def api_search_fxo_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    body = request.get_json(silent=True) or {}
    filters = body.get('filters', [])
    # `_day_files` + `_day_json`: `os.scandir` (a listagem já traz mtime e
    # tamanho) e memo por arquivo, então a segunda busca não reabre o que não
    # mudou. A busca não tem intervalo de datas, então não há o que podar.
    matched = []
    for fpath, _fname, mtime, size in _R()._day_files(_R().OPT_FXO_CACHE_DIR, '_optfxo.json'):
        for deal in _R()._day_json(fpath, mtime, size):
            if _R()._deal_matches(deal, filters):
                matched.append(deal)
    return jsonify({"success": True, "deals": matched})

@blueprint.route('/api/new-deals/opt-fxo/cache/<deal_id>', methods=['PATCH'])
def api_update_fxo_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    client  = request.args.get('client')
    updates = request.get_json(silent=True)
    if not updates:
        return jsonify({"success": False, "message": "No data provided"}), 400

    file_path, _ = _R()._find_fxo(deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _R()._cache_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                deals = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            deals = []
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        updates.pop('_client', None)
        deals[idx].update(updates)
        # Rewrite in table-column order (Maker/Checker last) — not alphabetical.
        deals[idx] = _R()._fxo_order_deal(deals[idx])
        _R()._atomic_write_json(file_path, deals)
        updated_deal = deals[idx].copy()

    # Mirror opt-comm: push to Intrag Option (FXO overrides) when Status→Success
    # and the counterparty is Banco J.P. Morgan (intragroup). External clients
    # instead flow to Pending Confirmation (manual-mapping twin of the return-file
    # scan trigger; _pc_save_from_deal skips internal legs itself).
    if str(updates.get('Status', '')) == 'Success':
        _R()._intrag_engine()._maybe_save_intrag_fxo(updated_deal)
        _R()._pc_save_from_deal(updated_deal, 'OPTION')          # → pending confirmation

    _fields = {k: v for k, v in updates.items() if k not in ('Maker', 'Checker', '_client')}
    if _fields:
        if 'Status' in _fields:
            if str(_fields.get('Status', '')) != 'Sent':
                _R()._create_notification(
                    session.get('user_sid', ''), session.get('user_name', ''),
                    'Status Updated', 'Opt FXO',
                    deal_id + ' → ' + str(_fields.get('Status', '')) + _R()._nd_token(updated_deal.get('TradeDate'))
                )
        else:
            _R()._create_notification(
                session.get('user_sid', ''), session.get('user_name', ''),
                'Deal Updated', 'Opt FXO',
                deal_id + ' (' + ', '.join(_fields.keys()) + ')' + _R()._nd_token(updated_deal.get('TradeDate'))
            )
    return jsonify({"success": True})

@blueprint.route('/api/new-deals/opt-fxo/cache/<deal_id>', methods=['DELETE'])
def api_delete_fxo_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    client = request.args.get('client')
    file_path, _ = _R()._find_fxo(deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _R()._cache_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                deals = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            deals = []
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        removed = deals.pop(idx)
        _R()._atomic_write_json(file_path, deals)

    _R()._create_notification(
        session.get('user_sid', ''), session.get('user_name', ''),
        'Deal Deleted', 'Opt FXO', deal_id + _R()._nd_token((removed or {}).get('TradeDate'))
    )
    return jsonify({"success": True})

@blueprint.route('/api/new-deals/opt-fxo/cache/bulk-delete', methods=['POST'])
def api_bulk_delete_fxo_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    data  = request.get_json(silent=True)
    pairs = data.get('pairs', []) if data else []
    if not pairs:
        return jsonify({"success": False, "message": "No pairs provided"}), 400

    pair_set = {(p.get('deal', ''), p.get('client', '')) for p in pairs}
    file_pairs = {}
    for deal_name, client_name in pair_set:
        fp, _ = _R()._find_fxo(deal_name, client_name)
        if fp:
            file_pairs.setdefault(fp, set()).add((deal_name, client_name))

    deleted = 0
    for fp, pairs_in_file in file_pairs.items():
        with _R()._cache_lock:
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                deals = []
            if not isinstance(deals, list):
                deals = [deals]
            before = len(deals)
            deals  = [d for d in deals if (d.get('Deal', ''), d.get('Client', '')) not in pairs_in_file]
            deleted += before - len(deals)
            _R()._atomic_write_json(fp, deals)

    not_found = len(pair_set) - deleted
    if deleted > 0:
        _R()._create_notification(
            session.get('user_sid', ''), session.get('user_name', ''),
            'Bulk Delete', 'Opt FXO',
            str(deleted) + ' deal' + ('s' if deleted != 1 else '') + ' deleted'
        )
    return jsonify({"success": True, "deleted": deleted, "not_found": not_found})

@blueprint.route('/api/new-deals/opt-fxo/cache/bulk-patch', methods=['POST'])
def api_fxo_bulk_patch_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    data    = request.get_json(silent=True)
    patches = data.get('patches', []) if data else []
    if not patches:
        return jsonify({"success": False, "message": "No patches provided"}), 400

    file_patches = {}
    for p in patches:
        deal_id = p.get('deal_id', '')
        client  = p.get('client', '')
        updates = p.get('updates', {})
        if not deal_id or not updates:
            continue
        fp, _ = _R()._find_fxo(deal_id, client)
        if fp:
            file_patches.setdefault(fp, []).append((deal_id, client, updates))

    updated = 0
    for fp, file_ops in file_patches.items():
        with _R()._cache_lock:
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                deals = []
            for deal_id, client, updates in file_ops:
                want_client = (client or '').strip()
                matching = [i for i, d in enumerate(deals)
                            if (d.get('Deal') or '').strip() == deal_id.strip()
                            and (not want_client or (d.get('Client') or '').strip() == want_client)]
                for idx in matching:
                    deals[idx].update(updates)
                    deals[idx] = _R()._fxo_order_deal(deals[idx])
                    updated += 1
            _R()._atomic_write_json(fp, deals)

    if updated > 0:
        _R()._create_notification(
            session.get('user_sid', ''), session.get('user_name', ''),
            'Bulk Update', 'Opt FXO',
            str(updated) + ' deal' + ('s' if updated != 1 else '') + ' updated'
        )
    return jsonify({"success": True, "updated": updated})

@blueprint.route('/api/new-deals/opt-fxo/import-api', methods=['POST'])
def api_fxo_import_api():
    """Manual trigger of the Athena FXO pull (Import button, empty dropzone).
    `ref_date` = campo Reference Date da página (default hoje)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        result = _R()._fxo_api_pull(sid=session.get('user_sid', '') or 'API',
                               actor_name=session.get('user_name', '') or 'Athena API',
                               ref_date=(request.get_json(silent=True) or {}).get('ref_date'))
    except Exception as e:                              # noqa: BLE001
        _R().log.warning('[opt-fxo] manual Athena API import failed: %s', e)
        return jsonify({'success': False, 'message': str(e)}), 502
    return jsonify(result)

@blueprint.route('/api/new-deals/ndf/import-api', methods=['POST'])
def api_ndf_import_api():
    """Manual trigger of the Athena NDF pull (Import button, empty dropzone,
    on the FWD Start / Other Publisher / Vanilla pages). `ref_date` = campo
    Reference Date da página (default hoje)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        result = _R()._ndf_api_pull(sid=session.get('user_sid', '') or 'API',
                               actor_name=session.get('user_name', '') or 'Athena API',
                               ref_date=(request.get_json(silent=True) or {}).get('ref_date'))
    except Exception as e:                              # noqa: BLE001
        _R().log.warning('[ndf] manual Athena API import failed: %s', e)
        return jsonify({'success': False, 'message': str(e)}), 502
    return jsonify(result)

@blueprint.route('/api/new-deals/opt-fxo/cache/batch', methods=['POST'])
def api_fxo_cache_batch():
    """Persist a finalized list of FXO deals (after the page resolves duplicates)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    data = request.get_json(silent=True) or {}
    deals = data.get('deals', [])
    if not deals:
        return jsonify({'success': True, 'imported': 0})
    saved = _R()._fxo_persist_deals(deals)
    if saved:
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'New Deals', 'Opt FXO',
                             '{} deal{} imported from XLSX'.format(saved, '' if saved == 1 else 's'))
    return jsonify({'success': True, 'imported': saved})

@blueprint.route('/api/new-deals/opt-fxo/import-xlsx', methods=['POST'])
def api_fxo_import_xlsx():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    import openpyxl

    files = request.files.getlist('files')
    if not files and 'file' in request.files:
        files = [request.files['file']]
    if not files:
        return jsonify({'success': False, 'message': 'no_file'}), 400

    sid = session.get('user_sid', '') or ''
    refmap = _R()._fxo_refdata_by_spn()
    refmap_acr = _R()._fxo_refdata_by_accronym(refmap)
    deals, errors = [], []

    for f in files:
        if not f or not (f.filename or '').lower().endswith('.xlsx'):
            continue
        try:
            wb = openpyxl.load_workbook(io.BytesIO(f.read()), read_only=True, data_only=True)
        except Exception as e:                       # noqa: BLE001
            errors.append('{}: {}'.format(f.filename, e))
            continue
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        try:
            header = next(it)
        except StopIteration:
            wb.close()
            continue

        col = {}
        for i, h in enumerate(header):
            n = re.sub(r'[\s_]+', ' ', str(h or '').strip().upper())
            if n and n not in col:
                col[n] = i

        def g(row, name):
            i = col.get(name)
            return row[i] if (i is not None and i < len(row)) else None

        for r in it:
            if r is None:
                continue
            deal = _R()._fxo_deal_from_row(lambda name: g(r, name), sid, refmap, refmap_acr)
            if deal:
                deals.append(deal)
        wb.close()

    # dry_run=1 → parse only (the page first checks Deal+Client duplicates against
    # the table and asks the user before persisting via /cache/batch).
    dry_run = (request.args.get('dry_run') in ('1', 'true', 'yes')
               or (request.form.get('dry_run') in ('1', 'true', 'yes')))
    saved = 0
    if not dry_run:
        saved = _R()._fxo_persist_deals(deals)
        if saved:
            _R()._create_notification(sid, session.get('user_name', ''),
                                 'New Deals', 'Opt FXO',
                                 '{} deal{} imported from XLSX'.format(saved, '' if saved == 1 else 's'))
    return jsonify({'success': True, 'imported': saved, 'deals': deals, 'errors': errors})

@blueprint.route('/api/new-deals/opt-fxo/send-conecta', methods=['POST'])
def api_fxo_send_conecta():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    """B3 Conecta file for FXO. Same layout as opt-commodities with the FXO tweaks
    (all in the File Interface template 'opcoes-flexiveis-vcp', page overrides):
    Tipo Indicador (seq 3)='4', Tipo de Cotação (seq 18)='1' (an older docstring
    said '2', but production always wrote '1' — the cadastro documents the real byte),
    'Data de fixing do ativo subjacente' (seq 20) = last fixing date when VANILLA
    (blank ASIAN), 'Data de fixing da moeda do ativo subjacente' (seq 21) always
    blank. Asian fixing-date count uses the ANBIMA calendar (FXHolidaySchedule).
    A montagem das linhas é do cadastro (_fi_build_line): ordem, larguras e
    literais Fixed saem do template; aqui ficam só os valores calculados."""
    from decimal import Decimal
    import datetime as _dt
    import json as _json

    data  = request.get_json(silent=True) or {}
    deals = data.get('deals', [])
    download = bool(data.get('download'))   # preview: devolve o conteúdo, não grava
    if not deals:
        return jsonify({'ok': False, 'error': 'No deals provided'}), 400

    # O cadastro é a autoridade da linha: sem template (ou sem os blocos), o
    # arquivo NÃO sai meio montado — erro claro pedindo o /file-interpreter.
    _tpl = _R()._fi_tpl_cached('opcoes-flexiveis-vcp')
    if _tpl is None or not {'header', 'registro', 'registro-media-asiatica'} <= {
            b.get('id') for b in _tpl.get('blocks', [])}:
        return jsonify({'ok': False, 'error': 'File Interpreter template missing/invalid '
                                              '— check /file-interpreter (opcoes-flexiveis-vcp)'}), 500

    today = _dt.datetime.today().strftime('%Y%m%d')

    def _sh(v):
        return re.sub(r'<[^>]+>', '', str(v or '')).strip()

    def _date(val):
        val = _sh(val)
        if not val:
            return ''
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y'):
            try:
                return _dt.datetime.strptime(val, fmt).strftime('%Y%m%d')
            except ValueError:
                continue
        return ''

    def _num(val, div100=False):
        val = _sh(str(val or ''))
        if not val:
            return ''
        clean = val.replace(',', '')
        try:
            d = Decimal(clean)
            if div100:
                d = d / Decimal('100')
            return format(d.normalize(), 'f').replace('.', ',')
        except Exception:
            return clean.replace('.', ',')

    def _qty(val):
        v = _sh(str(val or ''))
        if not v:
            return ''
        try:
            return str(int(round(float(v.replace(',', ''))))) + ',00'
        except Exception:
            return v

    def _cli(client):
        c = client.upper()
        if 'LAWTON' in c:
            return '73760009'
        if 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return '00041007'
        return '73760009'

    def _cpty(client):
        c = client.upper()
        if 'LAWTON' in c:
            return '00041007'
        if 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return '73760009'
        return '73760102'

    def _taxid(client, taxid):
        c = client.upper()
        if 'LAWTON' in c or 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return ''
        return re.sub(r'[.\-/]', '', _sh(taxid))

    deal_count = 0
    # Um destino por ARQUIVO: o padrão é FXO_Banco.txt, e a variante do
    # template (pelo par de pernas do deal) pode cadastrar outro nome.
    out_files  = {}

    for deal in deals:
        # No download (preview) o status não importa — baixa até cancelado.
        if not download and str(deal.get('Status', '') or '').strip() == 'Canceled':
            continue                    # cancelado via API: fora dos arquivos
        client     = _sh(deal.get('Client', ''))
        taxid      = _sh(deal.get('TaxID', ''))
        instrument = _sh(deal.get('Instrument', ''))
        direction  = _sh(deal.get('Direction', ''))
        trade_type       = _sh(deal.get('TradeType', ''))
        strike_ccy       = _sh(deal.get('StrikeCurrency', ''))
        fx_holiday_sched = _sh(deal.get('FXHolidaySchedule', '')) or 'anbima'
        vanilla          = trade_type.upper() == 'VANILLA'
        asian            = trade_type.upper() == 'ASIAN'
        brl              = strike_ccy.upper() == 'BRL'

        opt = 'P' if 'PUT' in instrument.upper() else ('C' if 'CALL' in instrument.upper() else '')
        dir_code  = '2' if direction.upper() == 'SELL' else '1'
        fix_start = _date(deal.get('FixingStartDate', ''))
        fix_end   = _date(deal.get('FixingEndDate', ''))

        # ANBIMA calendar (file name is case-insensitive on the FS we run on)
        _deal_holidays = set()
        if not vanilla and fx_holiday_sched:
            # Strip anything but word chars so a crafted FXHolidaySchedule
            # (e.g. '../../secret') can't escape the data dir (path traversal).
            _sched_file = re.sub(r'[^A-Za-z0-9_]', '', fx_holiday_sched.replace('-', '_').lower())
            holiday_path = os.path.join(_R()._B3_DATA_DIR, '{}.json'.format(_sched_file)) if _sched_file else None
            try:
                with open(holiday_path, encoding='utf-8') as _hf:
                    _raw = _json.load(_hf)
                _deal_holidays = set(item['date'] if isinstance(item, dict) else item for item in _raw)
            except Exception:
                pass

        _biz = 0
        if not vanilla and fix_start and fix_end:
            try:
                _s = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
                _e = _dt.datetime.strptime(fix_end, '%Y%m%d').date()
                _cur = _s
                while _cur <= _e:
                    if _cur.weekday() < 5 and _cur.strftime('%Y-%m-%d') not in _deal_holidays:
                        _biz += 1
                    _cur += _dt.timedelta(days=1)
            except Exception:
                pass

        # Só os campos não-Fixed, por seq do cadastro; os literais ('OPC  00002',
        # Tipo Indicador '4', Tipo de Cotação '1', Tipo de Exercício '2'…)
        # saem do template — byte a byte o que sempre foi enviado.
        trade_date = _date(deal.get('TradeDate', ''))
        _spot_date = _date(deal.get('SpotDate', ''))
        _is_bank_or_lawton = ('LAWTON' in client.upper() or 'BANCO J.P MORGAN' in client.upper()
                              or 'JP MORGAN' in client.upper())
        vals = {
            '4':  _cli(client),
            '5':  dir_code,
            '7':  _cpty(client),
            '8':  _taxid(client, taxid),
            '9':  opt,
            '10': trade_date,
            '11': _date(deal.get('SettlementDate', '')),
            '12': _sh(deal.get('UnderlyingAsset', '')),
            '13': _qty(deal.get('TotalNotional', '')),
            '14': _num(deal.get('Strike', '')),
            '19': 'S' if brl else '',
            '20': fix_end if vanilla else '',         # FXO: fixing do ativo = last fixing (VANILLA)
            '24': str(_R().random.randint(1000000000, 9999999999)),
            '25': _sh(deal.get('Deal', '')),
            '27': _num(deal.get('PremiumPerUnit', '')),
            '29': ('2' if trade_date == _spot_date else '3') if _is_bank_or_lawton else '1',
            '33': _spot_date,
            '48': '' if vanilla else '1',
            '49': '0' if vanilla else (str(_biz) if _biz else ''),
        }

        # Par de pernas → variante do template (Fixed das contas por par);
        # sem variante, o base — byte a byte o de sempre.
        le_pair = _R()._opc_le_pair(client)
        fname = (_R()._fi_variant_file_name('opcoes-flexiveis-vcp', '/new_deals-opt-fxo', le_pair)
                 or 'FXO_Banco.txt')
        dest = out_files.setdefault(fname, [])

        deal_count += 1
        dest.append(_R()._fi_build_line('opcoes-flexiveis-vcp', 'registro', vals,
                                   page_url='/new_deals-opt-fxo', le_pair=le_pair,
                                   deal=deal))

        # Asian — one fixing line (line type 2) per business day in the window
        if asian and fix_start and fix_end:
            try:
                _s2 = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
                _e2 = _dt.datetime.strptime(fix_end, '%Y%m%d').date()
            except Exception:
                _s2 = _e2 = None
            _cur2 = _s2
            while _s2 and _cur2 <= _e2:
                if _cur2.weekday() < 5 and _cur2.strftime('%Y-%m-%d') not in _deal_holidays:
                    dest.append(_R()._fi_build_line(
                        'opcoes-flexiveis-vcp', 'registro-media-asiatica',
                        {'3': _cur2.strftime('%Y%m%d')}, page_url='/new_deals-opt-fxo',
                        le_pair=le_pair, deal=deal))
                _cur2 += _dt.timedelta(days=1)

    # O header do OPC não depende do par (participante Fixed no template + a
    # data): o mesmo header abre todos os arquivos.
    header = _R()._fi_build_line('opcoes-flexiveis-vcp', 'header', {'4': today},
                            page_url='/new_deals-opt-fxo')
    if not out_files:
        out_files['FXO_Banco.txt'] = []   # lote só de cancelados: header, como sempre

    try:
        if download:
            files = [{'filename': fname, 'content': '\n'.join([header] + lines)}
                     for fname, lines in out_files.items()]
            return jsonify({'ok': True, 'count': deal_count, 'files': files,
                            'filename': files[0]['filename'] if files else ''})
        os.makedirs(_R().CONECTA_NEW_PATH, exist_ok=True)
        generated = []
        for fname, lines in out_files.items():
            filepath = _R()._unique_filepath(_R().CONECTA_NEW_PATH, fname)
            with open(filepath, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join([header] + lines))
            generated.append(os.path.basename(filepath))
        if deal_count > 0:
            _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                 'Sent to B3', 'Opt FXO',
                                 str(deal_count) + ' deal' + ('' if deal_count == 1 else 's') + ' sent')
        return jsonify({'ok': True, 'filename': generated[0] if generated else '',
                        'count': deal_count, 'files': generated})
    except Exception as exc:                          # noqa: BLE001
        return jsonify({'ok': False, 'error': str(exc)}), 500

@blueprint.route('/api/new-deals/opt-fxo/mapping-b3', methods=['POST'])
def api_fxo_mapping_b3():
    """Same B3-ID mapping as opt-commodities (Conecta return files carry 'OPC'
    option lines), but resolves deals in the _optfxo.json cache."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    data = request.get_json(silent=True) or {}
    sent_deals = data.get('deals', [])
    if not sent_deals:
        return jsonify({'ok': True, 'results': []})

    mapping = {}
    files_to_delete = []
    try:
        if not os.path.isdir(_R().RETURN_PATH):
            return jsonify({'ok': False, 'error': 'Return folder not found: {}'.format(_R().RETURN_PATH)}), 400
        for fname in os.listdir(_R().RETURN_PATH):
            fpath = os.path.join(_R().RETURN_PATH, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                with open(fpath, encoding='utf-8', errors='replace') as fh:
                    lines = fh.readlines()
                file_has_opc = False
                for line in lines[1:]:
                    line = line.strip()
                    if not line or line[56:59] != 'OPC':
                        continue
                    file_has_opc = True
                    parts = line.split(';')
                    if len(parts) < 5:
                        continue
                    b3_id       = parts[1].strip()
                    status_text = parts[3].strip()
                    pipe_parts  = parts[4].strip().split('|')
                    if len(pipe_parts) < 25 or pipe_parts[1].strip() != '1':
                        continue
                    deal_text = pipe_parts[24].strip()
                    if not deal_text:
                        continue
                    is_ok = (status_text == 'EXECUCAO OK')
                    if deal_text not in mapping or (is_ok and not mapping[deal_text]['ok']):
                        mapping[deal_text] = {'b3_id': b3_id, 'ok': is_ok}
                if file_has_opc:
                    files_to_delete.append(fpath)
            except Exception:
                continue
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    results = []
    for sent in sent_deals:
        deal_text   = sent.get('Deal', '')
        client_name = sent.get('Client', '')
        if not deal_text or deal_text not in mapping:
            continue
        info       = mapping[deal_text]
        new_status = 'Success' if info['ok'] else 'Error'
        updates    = {'Status': new_status}
        if info['ok']:
            updates['B3_ID'] = info['b3_id']

        file_path, idx = _R()._find_fxo(deal_text, client_name)
        if file_path is not None:
            intrag_candidate = None
            with _R()._cache_lock:
                try:
                    with open(file_path, 'r', encoding='utf-8') as fh:
                        deals_list = json.load(fh)
                    deals_list[idx].update(updates)
                    _R()._atomic_write_json(file_path, deals_list)
                    if new_status == 'Success':
                        intrag_candidate = deals_list[idx].copy()
                except Exception:
                    pass
            if intrag_candidate is not None:
                _R()._intrag_engine()._maybe_save_intrag_fxo(intrag_candidate)
                _R()._pc_save_from_deal(intrag_candidate, 'OPTION')      # → pending confirmation

        results.append({
            'id':     deal_text,
            'deal':   deal_text,
            'b3_id':  info['b3_id'] if info['ok'] else '',
            'status': new_status,
        })

    for fpath in files_to_delete:
        try:
            os.remove(fpath)
        except Exception:
            pass

    if results:
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'B3 Mapped', 'Opt FXO',
                             str(len(results)) + ' deal' + ('' if len(results) == 1 else 's') + ' mapped')
    return jsonify({'ok': True, 'results': results})

@blueprint.route('/api/new-deals/ndf-commodities/cache', methods=['POST'])
def api_ndf_save_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400
    _R()._nd_fix_underlying_marker(data)

    trade_date_raw = data.get('TradeDate', '')
    try:
        ref_date = datetime.strptime(trade_date_raw, '%d/%m/%Y')
    except (ValueError, TypeError):
        ref_date = datetime.now()

    dir_path = os.path.join(_R().NDF_COMM_CACHE_DIR, ref_date.strftime('%Y'), ref_date.strftime('%m'))
    os.makedirs(dir_path, exist_ok=True)

    fname = ref_date.strftime('%Y%m%d') + '_ndfcomm.json'
    file_path = os.path.join(dir_path, fname)

    with _R()._cache_lock:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
            except (json.JSONDecodeError, ValueError):
                deals = []
        else:
            deals = []

        deal_name   = data.get('Deal', '').strip()
        client_name = data.get('Client', '').strip()
        existing_idx = next((i for i, d in enumerate(deals)
                             if deal_name
                             and d.get('Deal', '').strip() == deal_name
                             and d.get('Client', '').strip() == client_name), None)
        if existing_idx is not None:
            deals[existing_idx] = data
        else:
            deals.append(data)

        _R()._atomic_write_json(file_path, deals)

    # When used as the manual-edit fallback (PATCH 404 → upsert), ?notify=1 makes
    # the row-level edit produce the same bell notification a PATCH would.
    if request.args.get('notify') and deal_name:
        _R()._create_notification(
            session.get('user_sid', ''), session.get('user_name', ''),
            'Deal Updated', 'NDF Comm',
            deal_name + (' / ' + client_name if client_name else '') + _R()._nd_token(data.get('TradeDate')))

    return jsonify({"success": True, "deal": data.get('Deal', '')})

@blueprint.route('/api/new-deals/ndf-commodities/cache/search', methods=['POST'])
def api_ndf_search_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    body = request.get_json(silent=True) or {}
    filters = body.get('filters', [])

    # `_day_files` + `_day_json`: `os.scandir` (a listagem já traz mtime e
    # tamanho) e memo por arquivo, então a segunda busca não reabre o que não
    # mudou. A busca não tem intervalo de datas, então não há o que podar.
    matched = []
    for fpath, _fname, mtime, size in _R()._day_files(_R().NDF_COMM_CACHE_DIR, '_ndfcomm.json'):
        for deal in _R()._day_json(fpath, mtime, size):
            if _R()._deal_matches(deal, filters):
                matched.append(deal)

    return jsonify({"success": True, "deals": matched})

@blueprint.route('/api/new-deals/ndf-commodities/cache/<deal_id>', methods=['PATCH'])
def api_ndf_update_deal_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    client  = request.args.get('client')
    updates = request.get_json(silent=True)
    _R().log.info("[NDF PATCH] deal_id=%r client=%r updates=%s", deal_id, client, updates)

    if not updates:
        _R().log.warning("[NDF PATCH] No JSON body received")
        return jsonify({"success": False, "message": "No data provided"}), 400

    file_path, idx_found = _R()._find_ndf_deal_in_cache(deal_id, client)
    _R().log.info("[NDF PATCH] _find_ndf_deal_in_cache → file=%s idx=%s", file_path, idx_found)

    if file_path is None:
        # _find_ndf_deal_in_cache already emitted the detailed diagnosis (repr diffs, client mismatch list)
        _R().log.warning("[NDF PATCH] 404 — deal_id=%r (repr=%r) client=%r (repr=%r)",
                    deal_id, repr(deal_id), client, repr(client))
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _R()._cache_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                deals = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            _R().log.error("[NDF PATCH] JSON parse error in file=%s", file_path)
            deals = []
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        _R().log.debug("[NDF PATCH] idx in loaded file=%s", idx)
        if idx is None:
            _R().log.warning("[NDF PATCH] 404 — deal found in file scan but not after reload. deal_id=%r client=%r file=%s", deal_id, client, file_path)
            return jsonify({"success": False, "message": "Deal not found"}), 404
        prev_status = deals[idx].get('Status', '?')
        deals[idx].update(updates)
        _R().log.info("[NDF PATCH] Updated deal[%d] %r: Status %r→%r updates=%s",
                 idx, deal_id, prev_status, deals[idx].get('Status', '?'), updates)
        _R()._atomic_write_json(file_path, deals)
        updated_deal = deals[idx].copy()

    # Save to Intrag when Status→Success and client is BANCO JP MORGAN
    new_status = updated_deal.get('Status', '')
    cl_lower = (updated_deal.get('Client', '') or '').lower()
    if new_status == 'Success' and 'banco' in cl_lower and 'morgan' in cl_lower:
        try:
            _R()._intrag_engine()._save_intrag_ndf_entry(updated_deal)
        except Exception as exc:
            _R().log.error('[NDF PATCH] Failed to save Intrag entry for deal=%r: %s', deal_id, exc)
    # External clients (non-intragroup) instead become a fresh outstanding
    # confirmation → Pending Confirmation. Manual-mapping twin of the return-file
    # scan trigger; _pc_save_from_deal skips internal/intragroup legs itself.
    if new_status == 'Success':
        _R()._pc_save_from_deal(updated_deal, 'NDF COMM')        # → pending confirmation

    _fields = {k: v for k, v in updates.items() if k not in ('Maker', 'Checker', '_client')}
    if _fields:
        if 'Status' in _fields:
            # The 'Sent' transition is already announced by the 'Sent to B3'
            # notification emitted from send-conecta — skip the redundant
            # 'Status Updated' entry so the bell shows a single item per send.
            if str(_fields.get('Status', '')) != 'Sent':
                _R()._create_notification(
                    session.get('user_sid', ''), session.get('user_name', ''),
                    'Status Updated', 'NDF Comm',
                    deal_id + ' → ' + str(_fields.get('Status', '')) + _R()._nd_token(updated_deal.get('TradeDate'))
                )
        else:
            _R()._create_notification(
                session.get('user_sid', ''), session.get('user_name', ''),
                'Deal Updated', 'NDF Comm',
                deal_id + ' (' + ', '.join(_fields.keys()) + ')' + _R()._nd_token(updated_deal.get('TradeDate'))
            )
    return jsonify({"success": True})

@blueprint.route('/api/new-deals/ndf-commodities/cache/<deal_id>', methods=['DELETE'])
def api_ndf_delete_deal_cache(deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    client = request.args.get('client')
    file_path, _ = _R()._find_ndf_deal_in_cache(deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _R()._cache_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                deals = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            deals = []
        idx = next((i for i, d in enumerate(deals)
                    if (d.get('Deal') or '').strip() == (deal_id or '').strip()
                    and (client is None or (d.get('Client', '') or '').strip() == (client or '').strip())), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        removed = deals.pop(idx)
        _R()._atomic_write_json(file_path, deals)

    _R()._create_notification(
        session.get('user_sid', ''), session.get('user_name', ''),
        'Deal Deleted', 'NDF Comm', deal_id + _R()._nd_token((removed or {}).get('TradeDate'))
    )
    return jsonify({"success": True})

@blueprint.route('/api/new-deals/ndf-commodities/cache/bulk-delete', methods=['POST'])
def api_ndf_bulk_delete_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data  = request.get_json(silent=True)
    pairs = data.get('pairs', []) if data else []
    _R().log.info("[NDF BULK-DELETE] Received %d pair(s): %s", len(pairs), pairs)

    if not pairs:
        return jsonify({"success": False, "message": "No pairs provided"}), 400

    pair_set = {(p.get('deal', ''), p.get('client', '')) for p in pairs}
    _R().log.info("[NDF BULK-DELETE] Unique pairs after dedup: %s", list(pair_set))

    # Check for suspicious empty keys
    empty_keys = [(d, c) for d, c in pair_set if not d or not c]
    if empty_keys:
        _R().log.warning("[NDF BULK-DELETE] WARNING — pairs with empty deal or client: %s", empty_keys)

    # Group pairs by their source file (search outside the lock — read-only scan)
    file_pairs = {}
    for deal_name, client_name in pair_set:
        fp, idx_found = _R()._find_ndf_deal_in_cache(deal_name, client_name)
        _R().log.debug("[NDF BULK-DELETE] _find deal=%r client=%r → file=%s idx=%s",
                  deal_name, client_name, fp, idx_found)
        if fp:
            file_pairs.setdefault(fp, set()).add((deal_name, client_name))
        else:
            _R().log.warning("[NDF BULK-DELETE] NOT FOUND: deal=%r (repr=%r) client=%r (repr=%r)",
                        deal_name, repr(deal_name), client_name, repr(client_name))

    _R().log.info("[NDF BULK-DELETE] Files to mutate: %s", list(file_pairs.keys()))

    deleted = 0
    for fp, pairs_in_file in file_pairs.items():
        with _R()._cache_lock:
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                _R().log.error("[NDF BULK-DELETE] JSON parse error in %s", fp)
                deals = []
            if not isinstance(deals, list):
                deals = [deals]
            before = len(deals)
            _R().log.info("[NDF BULK-DELETE] File %s has %d deals BEFORE delete. Removing pairs: %s",
                     os.path.basename(fp), before, list(pairs_in_file))
            deals  = [d for d in deals if (d.get('Deal', ''), d.get('Client', '')) not in pairs_in_file]
            after  = len(deals)
            deleted += before - after
            _R().log.info("[NDF BULK-DELETE] File %s: %d → %d deals (removed %d)",
                     os.path.basename(fp), before, after, before - after)
            _R()._atomic_write_json(fp, deals)

    not_found = len(pair_set) - deleted
    _R().log.info("[NDF BULK-DELETE] Done. deleted=%d not_found=%d", deleted, not_found)
    if deleted > 0:
        _R()._create_notification(
            session.get('user_sid', ''), session.get('user_name', ''),
            'Bulk Delete', 'NDF Comm',
            str(deleted) + ' deal' + ('s' if deleted != 1 else '') + ' deleted'
        )
    return jsonify({"success": True, "deleted": deleted, "not_found": not_found})

@blueprint.route('/api/new-deals/ndf-commodities/cache/bulk-patch', methods=['POST'])
def api_ndf_bulk_patch_deal_cache():
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401

    data    = request.get_json(silent=True)
    patches = data.get('patches', []) if data else []
    _R().log.info("[NDF BULK-PATCH] Received %d patch(es)", len(patches))

    if not patches:
        return jsonify({"success": False, "message": "No patches provided"}), 400

    # Group by source file (outside lock — read-only scan)
    file_patches = {}
    for p in patches:
        deal_id = p.get('deal_id', '')
        client  = p.get('client', '')
        updates = p.get('updates', {})
        if not deal_id or not updates:
            continue
        fp, _ = _R()._find_ndf_deal_in_cache(deal_id, client)
        if fp:
            file_patches.setdefault(fp, []).append((deal_id, client, updates))
        else:
            _R().log.warning("[NDF BULK-PATCH] NOT FOUND: deal=%r client=%r", deal_id, client)

    updated = 0
    for fp, file_ops in file_patches.items():
        with _R()._cache_lock:
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                deals = []
            for deal_id, client, updates in file_ops:
                idx = next((i for i, d in enumerate(deals)
                            if d.get('Deal') == deal_id and (not client or d.get('Client', '') == client)), None)
                if idx is not None:
                    deals[idx].update(updates)
                    updated += 1
                    _R().log.debug("[NDF BULK-PATCH] Updated deal=%r client=%r", deal_id, client)
            _R()._atomic_write_json(fp, deals)

    _R().log.info("[NDF BULK-PATCH] Done. updated=%d", updated)
    if updated > 0:
        _R()._create_notification(
            session.get('user_sid', ''), session.get('user_name', ''),
            'Bulk Update', 'NDF Comm',
            str(updated) + ' deal' + ('s' if updated != 1 else '') + ' updated'
        )
    return jsonify({"success": True, "updated": updated})

@blueprint.route('/api/new-deals/ndf-commodities/send-conecta', methods=['POST'])
def api_ndf_send_conecta():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    import datetime as _dt

    data  = request.get_json(silent=True) or {}
    deals = data.get('deals', [])
    download = bool(data.get('download'))   # preview: devolve o conteúdo, não grava
    if not deals:
        return jsonify({'ok': False, 'error': 'No deals provided'}), 400

    today = _dt.datetime.today().strftime('%Y%m%d')

    # Um destino por ARQUIVO: o nome padrão é TCO_{LAWTON,BANCO}.txt e a
    # variante do template (pelo par de pernas do deal) pode cadastrar outro
    # em `file_name`. Headers pelo bloco `header` do cadastro (layout 00003);
    # o Participante sai do `b3-accounts` pela LE da visão — ou do Fixed da
    # variante, quando o cadastro o fixou.
    page_url  = '/new_deals-ndf-commodities'
    out_files = {}
    try:
        for deal in deals:
            is_jpmorgan, ter_lines = _R()._ndf_comm_ter_lines(deal)
            bucket = 'LAWTON' if is_jpmorgan else 'BANCO'
            client = re.sub(r'<[^>]+>', '', str(deal.get('Client', '') or '')).strip()
            pair   = _R()._ter_le_pair(_R()._TER_BUCKET_LE[bucket], client)
            fname  = (_R()._fi_variant_file_name(_R()._TER_FI_KEY, page_url, pair)
                      or 'TCO_{}.txt'.format(bucket))
            d = out_files.setdefault(fname, {'bucket': bucket, 'pair': pair,
                                             'lines': [], 'count': 0})
            d['lines'].extend(ter_lines)
            d['count'] += 1
        headers = {fname: _R()._ter_file_header(_R()._TER_BUCKET_LE[d['bucket']], today,
                                           page_url, le_pair=d['pair'])
                   for fname, d in out_files.items() if d['lines']}
    except ValueError as exc:
        _R().log.error('[NDF COMM] send-conecta sem header: %s', exc)
        return jsonify({'ok': False, 'error': str(exc) or _R()._TER_FI_ERROR}), 500

    output_dir = _R().CONECTA_NEW_PATH
    generated  = []
    try:
        if download:
            generated = [{'filename': fname, 'count': d['count'],
                          'content': '\n'.join([headers[fname]] + d['lines'])}
                         for fname, d in out_files.items() if d['lines']]
            return jsonify({'ok': True, 'count': sum(d['count'] for d in out_files.values()),
                            'files': generated,
                            'filename': generated[0]['filename'] if generated else ''})
        os.makedirs(output_dir, exist_ok=True)
        for fname, d in out_files.items():
            if not d['lines']:
                continue
            path = _R()._unique_filepath(output_dir, fname)
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join([headers[fname]] + d['lines']))
            generated.append({'filename': os.path.basename(path), 'count': d['count']})
        total = sum(d['count'] for d in out_files.values())
        primary = generated[0]['filename'] if generated else ''
        if total > 0:
            _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''), 'Sent to B3', 'NDF Comm', str(total) + ' deal' + ('' if total == 1 else 's') + ' sent')
        return jsonify({'ok': True, 'filename': primary, 'count': total, 'files': generated})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

@blueprint.route('/api/new-deals/ndf-commodities/mapping-b3', methods=['POST'])
def api_ndf_mapping_b3():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    data = request.get_json(silent=True) or {}
    sent_deals = data.get('deals', [])
    if not sent_deals:
        return jsonify({'ok': True, 'results': []})

    mapping         = {}
    files_to_delete = []
    try:
        if not os.path.isdir(_R().RETURN_PATH):
            return jsonify({'ok': False, 'error': f'Return folder not found: {_R().RETURN_PATH}'}), 400

        for fname in os.listdir(_R().RETURN_PATH):
            fpath = os.path.join(_R().RETURN_PATH, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                with open(fpath, 'r', encoding='latin-1') as fh:
                    lines = fh.readlines()
                file_has_ter = False
                for line in lines[1:]:  # skip header row
                    line = line.strip()
                    if not line:
                        continue
                    # Sigla at chars 57-59 (1-based): NDF maps only 'TER' (termo) lines
                    if line[56:59] != 'TER':
                        continue
                    file_has_ter = True
                    if 'EXECUCAO OK' not in line:
                        continue
                    parts = line.split(';')
                    if len(parts) < 2:
                        continue
                    b3_id = parts[1].strip()
                    for sd in sent_deals:
                        deal_text = sd.get('Deal', '')
                        if deal_text and deal_text not in mapping and deal_text in line:
                            mapping[deal_text] = b3_id
                # Only delete return files that actually carried TER (NDF) lines
                if file_has_ter:
                    files_to_delete.append(fpath)
            except Exception:
                continue
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    results = []
    for sd in sent_deals:
        deal_text   = sd.get('Deal', '')
        client_name = sd.get('Client', '')
        if str(sd.get('Status', '') or '').strip() == 'Canceled':
            continue                    # cancelado via API: fora do mapping
        if deal_text and deal_text in mapping:
            b3_id      = mapping[deal_text]
            new_status = 'Success'
            updates    = {'Status': new_status, 'B3_ID': b3_id}
        else:
            b3_id      = ''
            new_status = 'Error'
            updates    = {'Status': new_status}

        intrag_candidate = None
        if deal_text:
            file_path, idx = _R()._find_ndf_deal_in_cache(deal_text, client_name)
            if file_path is not None:
                with _R()._cache_lock:
                    try:
                        with open(file_path, 'r', encoding='utf-8') as fh:
                            deals_list = json.load(fh)
                        deals_list[idx].update(updates)
                        with open(file_path, 'w', encoding='utf-8') as fh:
                            json.dump(deals_list, fh, ensure_ascii=False, indent=2)
                        if new_status == 'Success':
                            intrag_candidate = deals_list[idx].copy()
                    except Exception:
                        pass

        if intrag_candidate is not None:
            cl_low = (intrag_candidate.get('Client', '') or '').lower()
            if 'banco' in cl_low and 'morgan' in cl_low:
                try:
                    _R()._intrag_engine()._save_intrag_ndf_entry(intrag_candidate)
                except Exception as exc:
                    _R().log.error('[MAPPING-B3] Intrag save failed for deal=%r: %s', deal_text, exc)
            _R()._pc_save_from_deal(intrag_candidate, 'NDF COMM')       # → pending confirmation

        results.append({
            'id':     deal_text,
            'deal':   deal_text,
            'b3_id':  b3_id,
            'status': new_status,
        })

    for fpath in files_to_delete:
        try:
            os.remove(fpath)
        except Exception:
            pass

    if results:
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''), 'B3 Mapped', 'NDF Comm', str(len(results)) + ' deal' + ('' if len(results) == 1 else 's') + ' mapped')
    return jsonify({'ok': True, 'results': results})

@blueprint.route('/api/new-deals/opt-commodities/send-conecta', methods=['POST'])
def api_send_conecta():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    from decimal import Decimal
    import datetime as _dt

    data  = request.get_json(silent=True) or {}
    deals = data.get('deals', [])
    download = bool(data.get('download'))   # preview: devolve o conteúdo, não grava
    if not deals:
        return jsonify({'ok': False, 'error': 'No deals provided'}), 400

    # O cadastro do File Interface (opcoes-flexiveis-vcp) comanda a montagem
    # das linhas — ordem, larguras e literais Fixed saem do template; aqui
    # ficam só os valores calculados. Sem template/blocos, erro claro: nunca
    # arquivo para a B3 meio montado em silêncio.
    _tpl = _R()._fi_tpl_cached('opcoes-flexiveis-vcp')
    if _tpl is None or not {'header', 'registro', 'registro-media-asiatica'} <= {
            b.get('id') for b in _tpl.get('blocks', [])}:
        return jsonify({'ok': False, 'error': 'File Interpreter template missing/invalid '
                                              '— check /file-interpreter (opcoes-flexiveis-vcp)'}), 500

    today = _dt.datetime.today().strftime('%Y%m%d')

    def _sh(v):
        return re.sub(r'<[^>]+>', '', str(v or '')).strip()

    def _date(val):
        val = _sh(val)
        if not val:
            return ''
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d/%m/%Y'):
            try:
                return _dt.datetime.strptime(val, fmt).strftime('%Y%m%d')
            except ValueError:
                continue
        return ''

    def _num(val, div100=False):
        val = _sh(str(val or ''))
        if not val:
            return ''
        clean = val.replace(',', '')
        try:
            d = Decimal(clean)
            if div100:
                d = d / Decimal('100')
            s = format(d.normalize(), 'f')
            return s.replace('.', ',')
        except Exception:
            return clean.replace('.', ',')

    def _qty(val):
        """Integer quantity formatted as {int},00 for B3 field 13."""
        v = _sh(str(val or ''))
        if not v:
            return ''
        clean = v.replace(',', '')
        try:
            return str(int(round(float(clean)))) + ',00'
        except Exception:
            return v

    def _cli(client):
        c = client.upper()
        if 'LAWTON' in c:
            return '73760009'
        if 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return '00041007'
        return '73760009'

    def _cpty(client):
        c = client.upper()
        if 'LAWTON' in c:
            return '00041007'
        if 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return '73760009'
        return '73760102'

    def _taxid(client, taxid):
        c = client.upper()
        if 'LAWTON' in c or 'BANCO J.P MORGAN' in c or 'JP MORGAN' in c:
            return ''
        return re.sub(r'[.\-/]', '', _sh(taxid))

    import json as _json
    deal_count = 0
    # Um destino por ARQUIVO: o padrão é OPC_Banco.txt, e a variante do
    # template (pelo par de pernas do deal) pode cadastrar outro nome.
    out_files  = {}

    for deal in deals:
        # No download (preview) o status não importa — baixa até cancelado.
        if not download and str(deal.get('Status', '') or '').strip() == 'Canceled':
            continue                    # cancelado via API: fora dos arquivos
        client     = _sh(deal.get('Client', ''))
        taxid      = _sh(deal.get('TaxID', ''))
        instrument = _sh(deal.get('Instrument', ''))
        direction  = _sh(deal.get('Direction', ''))
        trade_type        = _sh(deal.get('TradeType', ''))
        strike_ccy        = _sh(deal.get('StrikeCurrency', ''))
        fx_holiday_sched  = _sh(deal.get('FXHolidaySchedule', ''))
        qic               = _sh(deal.get('QuotedInCents', 'NO')).upper() == 'YES'
        vanilla           = trade_type.upper() == 'VANILLA'
        asian             = trade_type.upper() == 'ASIAN'
        brl               = strike_ccy.upper() == 'BRL'

        opt = 'P' if 'PUT'  in instrument.upper() else ('C' if 'CALL' in instrument.upper() else '')
        dir_code   = '2' if direction.upper() == 'SELL' else '1'
        fix_start  = _date(deal.get('FixingStartDate', ''))
        fix_end    = _date(deal.get('FixingEndDate', ''))
        fxconv     = _date(deal.get('FXConvDate', ''))

        _deal_holidays = set()
        if not vanilla and fx_holiday_sched:
            _sched_file2 = fx_holiday_sched.replace('-', '_')
            holiday_path = _R().data_path(f'{_sched_file2}.json')
            try:
                with open(holiday_path, encoding='utf-8') as _hf:
                    _raw = _json.load(_hf)
                _deal_holidays = set(
                    item['date'] if isinstance(item, dict) else item
                    for item in _raw
                )
            except Exception:
                pass

        _biz = 0
        if not vanilla and fix_start and fix_end:
            try:
                _s = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
                _e = _dt.datetime.strptime(fix_end,   '%Y%m%d').date()
                _cur = _s
                while _cur <= _e:
                    _date_str = _cur.strftime('%Y-%m-%d')
                    if _cur.weekday() < 5 and _date_str not in _deal_holidays:
                        _biz += 1
                    _cur += _dt.timedelta(days=1)
            except Exception:
                pass

        # Só os campos não-Fixed, por seq do cadastro; os literais ('OPC  00002',
        # Tipo Indicador '3', Tipo de Exercício '2'…) saem do template —
        # byte a byte o que sempre foi enviado.
        trade_date = _date(deal.get('TradeDate', ''))
        _spot_date = _date(deal.get('SpotDate', ''))
        _is_bank_or_lawton = 'LAWTON' in client.upper() or 'BANCO J.P MORGAN' in client.upper() or 'JP MORGAN' in client.upper()
        vals = {
            '4':  _cli(client),
            '5':  dir_code,
            '7':  _cpty(client),
            '8':  _taxid(client, taxid),
            '9':  opt,
            '10': trade_date,
            '11': _date(deal.get('SettlementDate', '')),
            '12': _sh(deal.get('UnderlyingAsset', '')),
            '13': _qty(deal.get('TotalNotional', '')),
            '14': _num(deal.get('Strike', ''), div100=qic),
            # Tipo de Cotação: cadastro (Commodities × B3 › Tipo de Cotação —
            # Opção). Sem linha, ou coluna vazia, sai o '5' de sempre. §177
            '18': _R()._b3_quote_cfg(_sh(deal.get('UnderlyingAsset', '')))['opt'],
            '19': 'S' if brl else '',
            '20': fix_start if vanilla else '',
            '21': fxconv if (not brl or vanilla) else '',
            '24': str(_R().random.randint(1000000000, 9999999999)),
            '25': _sh(deal.get('Deal', '')),
            '27': _num(deal.get('PremiumPerUnit', ''), div100=qic),
            '29': ('2' if trade_date == _spot_date else '3') if _is_bank_or_lawton else '1',
            '33': _spot_date,
            '48': '' if vanilla else '1',
            '49': '0' if vanilla else (str(_biz) if _biz else ''),
        }

        # Par de pernas → variante do template (Fixed das contas por par);
        # sem variante, o base — byte a byte o de sempre.
        le_pair = _R()._opc_le_pair(client)
        fname = (_R()._fi_variant_file_name('opcoes-flexiveis-vcp',
                                       '/new_deals-opt-commodities', le_pair)
                 or 'OPC_Banco.txt')
        dest = out_files.setdefault(fname, [])

        deal_count += 1
        dest.append(_R()._fi_build_line('opcoes-flexiveis-vcp', 'registro', vals,
                                   page_url='/new_deals-opt-commodities',
                                   le_pair=le_pair, deal=deal))

        if asian and fix_start and fix_end:
            try:
                _s2 = _dt.datetime.strptime(fix_start, '%Y%m%d').date()
                _e2 = _dt.datetime.strptime(fix_end,   '%Y%m%d').date()
            except Exception:
                _s2 = _e2 = None
            _cur2 = _s2
            while _s2 and _cur2 <= _e2:
                if _cur2.weekday() < 5 and _cur2.strftime('%Y-%m-%d') not in _deal_holidays:
                    _d = _cur2.strftime('%Y%m%d')
                    dest.append(_R()._fi_build_line(
                        'opcoes-flexiveis-vcp', 'registro-media-asiatica',
                        {'3': _d, '4': _d if brl else ''},
                        page_url='/new_deals-opt-commodities', le_pair=le_pair,
                        deal=deal))
                _cur2 += _dt.timedelta(days=1)

    # O header do OPC não depende do par (participante Fixed no template + a
    # data): o mesmo header abre todos os arquivos.
    header = _R()._fi_build_line('opcoes-flexiveis-vcp', 'header', {'4': today},
                            page_url='/new_deals-opt-commodities')
    if not out_files:
        out_files['OPC_Banco.txt'] = []   # lote só de cancelados: header, como sempre

    output_dir = _R().CONECTA_NEW_PATH
    try:
        if download:
            files = [{'filename': fname, 'content': '\n'.join([header] + lines)}
                     for fname, lines in out_files.items()]
            return jsonify({'ok': True, 'count': deal_count, 'files': files,
                            'filename': files[0]['filename'] if files else ''})
        os.makedirs(output_dir, exist_ok=True)
        generated = []
        for fname, lines in out_files.items():
            filepath = _R()._unique_filepath(output_dir, fname)
            with open(filepath, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join([header] + lines))
            generated.append(os.path.basename(filepath))
        if deal_count > 0:
            _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''), 'Sent to B3', 'Opt Comm', str(deal_count) + ' deal' + ('' if deal_count == 1 else 's') + ' sent')
        return jsonify({'ok': True, 'filename': generated[0] if generated else '',
                        'count': deal_count, 'files': generated})
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

@blueprint.route('/api/new-deals/opt-commodities/mapping-b3', methods=['POST'])
def api_mapping_b3():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    data = request.get_json(silent=True) or {}
    sent_deals = data.get('deals', [])   # [{id, Deal}]
    if not sent_deals:
        return jsonify({'ok': True, 'results': []})

    # ── scan return folder ────────────────────────────────────────────
    mapping       = {}   # deal_text -> {'b3_id': str, 'ok': bool}
    files_to_delete = []
    try:
        if not os.path.isdir(_R().RETURN_PATH):
            return jsonify({'ok': False, 'error': f'Return folder not found: {_R().RETURN_PATH}'}), 400

        for fname in os.listdir(_R().RETURN_PATH):
            fpath = os.path.join(_R().RETURN_PATH, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                with open(fpath, encoding='utf-8', errors='replace') as fh:
                    lines = fh.readlines()
                file_has_opc = False
                for line in lines[1:]:   # skip header
                    line = line.strip()
                    if not line:
                        continue
                    # Sigla at chars 57-59 (1-based): Options map only 'OPC' (opção) lines
                    if line[56:59] != 'OPC':
                        continue
                    file_has_opc = True
                    parts = line.split(';')
                    if len(parts) < 5:
                        continue
                    b3_id       = parts[1].strip()
                    status_text = parts[3].strip()
                    opc_part    = parts[4].strip()
                    pipe_parts  = opc_part.split('|')
                    if len(pipe_parts) < 25:
                        continue
                    if pipe_parts[1].strip() != '1':   # only type-1 (characteristics) lines
                        continue
                    deal_text = pipe_parts[24].strip()
                    if not deal_text:
                        continue
                    is_ok = (status_text == 'EXECUCAO OK')
                    if deal_text not in mapping or (is_ok and not mapping[deal_text]['ok']):
                        mapping[deal_text] = {'b3_id': b3_id, 'ok': is_ok}
                # Only delete return files that actually carried OPC (Option) lines
                if file_has_opc:
                    files_to_delete.append(fpath)
            except Exception:
                continue
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    # ── match sent deals and update cache ────────────────────────────
    results = []
    for sent in sent_deals:
        deal_text   = sent.get('Deal', '')
        client_name = sent.get('Client', '')
        if not deal_text or deal_text not in mapping:
            continue

        info       = mapping[deal_text]
        new_status = 'Success' if info['ok'] else 'Error'
        updates    = {'Status': new_status}
        if info['ok']:
            updates['B3_ID'] = info['b3_id']

        if deal_text:
            file_path, idx = _R()._find_deal_in_cache(deal_text, client_name)
            if file_path is not None:
                intrag_candidate = None
                with _R()._cache_lock:
                    try:
                        with open(file_path, 'r', encoding='utf-8') as fh:
                            deals_list = json.load(fh)
                        deals_list[idx].update(updates)
                        with open(file_path, 'w', encoding='utf-8') as fh:
                            json.dump(deals_list, fh, ensure_ascii=False, indent=2)
                        if new_status == 'Success':
                            intrag_candidate = deals_list[idx].copy()
                    except Exception:
                        pass
                if intrag_candidate is not None:
                    _R()._intrag_engine()._maybe_save_intrag_opt(intrag_candidate)
                    _R()._pc_save_from_deal(intrag_candidate, 'OPTION COMM')   # → pending confirmation

        results.append({
            'id':     deal_text,
            'deal':   deal_text,
            'b3_id':  info['b3_id'] if info['ok'] else '',
            'status': new_status
        })

    # ── delete processed return files ────────────────────────────────
    for fpath in files_to_delete:
        try:
            os.remove(fpath)
        except Exception:
            pass

    if results:
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''), 'B3 Mapped', 'Opt Comm', str(len(results)) + ' deal' + ('' if len(results) == 1 else 's') + ' mapped')
    return jsonify({'ok': True, 'results': results})

@blueprint.route('/api/new-deals/opt-commodities/premium-email', methods=['POST'])
def api_opt_premium_email():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    from apps.pages import otc_emails
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    drafts = otc_emails.build_premium_emails(deals, asset_label='Opção de Commodities')
    if not drafts:
        return jsonify({'ok': True, 'count': 0})
    return _R()._email_drafts_response(drafts)

@blueprint.route('/api/new-deals/opt-fxo/premium-email', methods=['POST'])
def api_fxo_premium_email():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    from apps.pages import otc_emails
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    drafts = otc_emails.build_premium_emails(deals, asset_label='Opção de Moeda',
                                             ref_key='FX CASH ACCRONYM',
                                             cc_comm_sales=False)   # FX flow — Comm Sales isn't copied
    if not drafts:
        return jsonify({'ok': True, 'count': 0})
    return _R()._email_drafts_response(drafts)

@blueprint.route('/api/new-deals/opt-commodities/economic-affirmation', methods=['POST'])
def api_opt_economic_affirmation_email():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    from apps.pages import otc_emails
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    drafts = otc_emails.build_economic_affirmation_emails(deals, asset_label='Opção Mercadoria')
    if not drafts:
        return jsonify({'ok': True, 'count': 0})
    return _R()._email_drafts_response(drafts)

@blueprint.route('/api/new-deals/ndf-commodities/economic-affirmation', methods=['POST'])
def api_ndf_economic_affirmation_email():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    from apps.pages import otc_emails
    deals = (request.get_json(silent=True) or {}).get('deals', [])
    drafts = otc_emails.build_economic_affirmation_emails(deals, asset_label='Termo de Mercadoria')
    if not drafts:
        return jsonify({'ok': True, 'count': 0})
    return _R()._email_drafts_response(drafts)

@blueprint.route('/api/new-deals/ndf-commodities/confirmations')
def api_ndfcomm_confirmations():
    """Grupos de confirmação da reference date, com o link de geração quando o
    template da família já existe (por ora, só strike-usd)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    groups, _statuses, _total = _R()._conf_ndfcomm_groups(ref)
    state = _R()._conf_state_load(ref)
    out = []
    for g in groups:
        available = g['family'] in _R()._CONF_FAMILY_TEMPLATES
        entry = state.get(_R()._conf_key(g['acronym'], g['mercadoria'], g['family'])) or {}
        status = entry.get('status') or 'New'
        qs = ('date=' + ref.strftime('%Y-%m-%d')
              + '&acronym=' + _R().quote(g['acronym'])
              + '&mercadoria=' + _R().quote(g['mercadoria']))
        url = _R()._CONF_FAMILY_TEMPLATES[g['family']][1] + '?' + qs if available else None
        validate_url = ('/confirmation/ndf-comm/validate?' + qs + '&family=' + _R().quote(g['family'])) \
            if status in ('Generated', 'Success') else None
        out.append({
            'acronym': g['acronym'], 'client': g['client'],
            'mercadoria': g['mercadoria'], 'family': g['family'],
            'count': g['count'], 'eligible': g['eligible'],
            'available': available, 'url': url,
            'status': status, 'validate_url': validate_url,
        })
    return jsonify({'success': True, 'date': ref.strftime('%Y-%m-%d'), 'groups': out})

@blueprint.route('/api/new-deals/opt-commodities/confirmations')
def api_optcomm_confirmations():
    """Grupos de confirmação de Opção de Commodities da reference date."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    groups, _statuses, _total = _R()._conf_optcomm_groups(ref)
    state = _R()._conf_state_load(ref, 'opt-comm')
    out = []
    for g in groups:
        available = g['family'] in _R()._CONF_OPT_FAMILY_TEMPLATES
        entry = state.get(_R()._conf_key(g['acronym'], g['mercadoria'], g['family'])) or {}
        status = entry.get('status') or 'New'
        qs = ('date=' + ref.strftime('%Y-%m-%d')
              + '&acronym=' + _R().quote(g['acronym'])
              + '&mercadoria=' + _R().quote(g['mercadoria']))
        url = _R()._CONF_OPT_FAMILY_TEMPLATES[g['family']][1] + '?' + qs if available else None
        validate_url = ('/confirmation/opt-comm/validate?' + qs + '&family=' + _R().quote(g['family'])) \
            if status in ('Generated', 'Success') else None
        out.append({
            'acronym': g['acronym'], 'client': g['client'],
            'mercadoria': g['mercadoria'], 'family': g['family'],
            'count': g['count'], 'eligible': g['eligible'],
            'available': available, 'url': url,
            'status': status, 'validate_url': validate_url,
        })
    return jsonify({'success': True, 'date': ref.strftime('%Y-%m-%d'), 'groups': out})

@blueprint.route('/api/new-deals/opt-fxo/confirmations')
def api_optfxo_confirmations():
    """Grupos de confirmação de Opção de Câmbio da reference date."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    groups, _statuses, _total = _R()._conf_optfxo_groups(ref)
    state = _R()._conf_state_load(ref, 'opt-fxo')
    out = []
    for g in groups:
        available = g['family'] in _R()._CONF_FXO_FAMILY_TEMPLATES
        entry = state.get(_R()._conf_key(g['acronym'], g['mercadoria'], g['family'])) or {}
        status = entry.get('status') or 'New'
        qs = ('date=' + ref.strftime('%Y-%m-%d')
              + '&acronym=' + _R().quote(g['acronym'])
              + '&mercadoria=' + _R().quote(g['mercadoria']))
        url = _R()._CONF_FXO_FAMILY_TEMPLATES[g['family']][1] + '?' + qs if available else None
        validate_url = ('/confirmation/opt-fxo/validate?' + qs + '&family=' + _R().quote(g['family'])) \
            if status in ('Generated', 'Success') else None
        out.append({
            'acronym': g['acronym'], 'client': g['client'],
            'mercadoria': g['mercadoria'], 'family': g['family'],
            'count': g['count'], 'eligible': g['eligible'],
            'available': available, 'url': url,
            'status': status, 'validate_url': validate_url,
        })
    return jsonify({'success': True, 'date': ref.strftime('%Y-%m-%d'), 'groups': out})

@blueprint.route('/api/new-deals/ndf-fwdstart/confirmations')
def api_ndffwdstart_confirmations():
    """Grupos de confirmação de NDF FWD Start da reference date."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    groups, _statuses, _total = _R()._conf_fwdstart_groups(ref)
    state = _R()._conf_state_load(ref, 'ndf-fwdstart')
    out = []
    for g in groups:
        available = g['family'] in _R()._CONF_FWDSTART_FAMILY_TEMPLATES
        entry = state.get(_R()._conf_key(g['acronym'], g['mercadoria'], g['family'])) or {}
        status = entry.get('status') or 'New'
        qs = ('date=' + ref.strftime('%Y-%m-%d')
              + '&acronym=' + _R().quote(g['acronym'])
              + '&mercadoria=' + _R().quote(g['mercadoria']))
        url = _R()._CONF_FWDSTART_FAMILY_TEMPLATES[g['family']][1] + '?' + qs if available else None
        validate_url = ('/confirmation/ndf-fwdstart/validate?' + qs + '&family=' + _R().quote(g['family'])) \
            if status in ('Generated', 'Success') else None
        out.append({
            'acronym': g['acronym'], 'client': g['client'],
            'mercadoria': g['mercadoria'], 'family': g['family'],
            'count': g['count'], 'eligible': g['eligible'],
            'available': available, 'url': url,
            'status': status, 'validate_url': validate_url,
        })
    return jsonify({'success': True, 'date': ref.strftime('%Y-%m-%d'), 'groups': out})

@blueprint.route('/api/new-deals/<product>/cache', methods=['POST'])
def api_generic_nd_save_cache(product):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _R()._generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "No data provided"}), 400

    try:
        ref_date = datetime.strptime(data.get('TradeDate', ''), '%d/%m/%Y')
    except (ValueError, TypeError):
        ref_date = datetime.now()

    dir_path = os.path.join(cfg['dir'], ref_date.strftime('%Y'), ref_date.strftime('%m'))
    os.makedirs(dir_path, exist_ok=True)
    file_path = os.path.join(dir_path, ref_date.strftime('%Y%m%d') + cfg['suffix'])

    with _R()._cache_lock:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
                if not isinstance(deals, list):
                    deals = [deals]
            except (json.JSONDecodeError, ValueError):
                deals = []
        else:
            deals = []

        deal_name   = data.get('Deal', '').strip()
        client_name = data.get('Client', '').strip()
        existing_idx = next((i for i, d in enumerate(deals)
                             if deal_name
                             and d.get('Deal', '').strip() == deal_name
                             and d.get('Client', '').strip() == client_name), None)
        if existing_idx is not None:
            deals[existing_idx] = data
        else:
            deals.append(data)
        _R()._atomic_write_json(file_path, deals)

    return jsonify({"success": True, "deal": data.get('Deal', '')})

@blueprint.route('/api/new-deals/<product>/cache/search', methods=['POST'])
def api_generic_nd_search_cache(product):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _R()._generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404

    filters = (request.get_json(silent=True) or {}).get('filters', [])
    matched, refmap_cache = [], {}
    # `mutavel=True`: o `_generic_nd_reenrich` ALTERA os dicionários, e sem a
    # cópia a alteração ficaria gravada no memo — o próximo leitor veria o dado
    # de outro request. Ela custa microssegundos contra a dezena de
    # milissegundos de uma leitura no share.
    for fpath, _fname, mtime, size in _R()._day_files(cfg['dir'], cfg['suffix']):
        deals = _R()._day_json(fpath, mtime, size, mutavel=True)
        try:
            # Contraparte cadastrada depois do import → persiste o
            # enriquecimento, senão a linha volta vazia a cada visita.
            if _R()._generic_nd_reenrich(deals, refmap_cache):
                with _R()._cache_lock:
                    _R()._atomic_write_json(fpath, deals)
                # O mtime novo já invalidaria a entrada, mas contar com isso é
                # contar com a resolução do relógio do share.
                _R()._daycache_forget(fpath)
        except Exception:                                   # noqa: BLE001
            continue
        for deal in deals:
            if _R()._deal_matches(deal, filters):
                matched.append(deal)
    return jsonify({"success": True, "deals": matched})

@blueprint.route('/api/new-deals/<product>/cache/<deal_id>', methods=['PATCH'])
def api_generic_nd_update_cache(product, deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _R()._generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404

    client  = request.args.get('client')
    updates = request.get_json(silent=True)
    if not updates:
        return jsonify({"success": False, "message": "No data provided"}), 400

    file_path, _ = _R()._find_generic_nd_deal(cfg, deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _R()._cache_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                deals = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            deals = []
        idx = next((i for i, d in enumerate(deals)
                    if d.get('Deal') == deal_id and (client is None or d.get('Client', '') == client)), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        deals[idx].update(updates)
        _R()._atomic_write_json(file_path, deals)
        updated_deal = deals[idx].copy()

    # Vanilla / Other Publisher contra o Lawton alimentam a Intrag NDF no
    # layout "Instrucao NDF Moeda" quando o Status vira Success (FWD Start fora
    # — o strike só existe na strike set date, quando rebooka como vanilla).
    if str(updates.get('Status', '')) == 'Success':
        if product in ('vanilla', 'other-publishers') and \
                'LAWTON' in (updated_deal.get('Client', '') or '').upper():
            try:
                _R()._intrag_engine()._save_intrag_ndf_moeda_entry(updated_deal)
            except Exception as exc:
                _R().log.error('[ND %s] Intrag moeda save failed for deal=%r: %s',
                          product, deal_id, exc)
        _R()._generic_nd_pc_trigger(product, updated_deal)       # → pending confirmation

    _fields = {k: v for k, v in updates.items() if k not in ('Maker', 'Checker', '_client')}
    if _fields:
        if 'Status' in _fields:
            # The 'Sent' transition is already announced by the 'Sent to B3'
            # notification emitted from send-conecta — skip the redundant
            # 'Status Updated' entry so the bell shows a single item per send.
            if str(_fields.get('Status', '')) != 'Sent':
                _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                     'Status Updated', cfg['label'], deal_id + ' → ' + str(_fields.get('Status', '')) + _R()._nd_token(updated_deal.get('TradeDate')))
        else:
            _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                 'Deal Updated', cfg['label'], deal_id + ' (' + ', '.join(_fields.keys()) + ')' + _R()._nd_token(updated_deal.get('TradeDate')))
    return jsonify({"success": True})

@blueprint.route('/api/new-deals/<product>/cache/<deal_id>', methods=['DELETE'])
def api_generic_nd_delete_cache(product, deal_id):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _R()._generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404

    client = request.args.get('client')
    file_path, _ = _R()._find_generic_nd_deal(cfg, deal_id, client)
    if file_path is None:
        return jsonify({"success": False, "message": "Deal not found"}), 404

    with _R()._cache_lock:
        try:
            with open(file_path, 'r', encoding='utf-8') as fh:
                deals = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            deals = []
        idx = next((i for i, d in enumerate(deals)
                    if d.get('Deal') == deal_id and (client is None or d.get('Client', '') == client)), None)
        if idx is None:
            return jsonify({"success": False, "message": "Deal not found"}), 404
        removed = deals.pop(idx)
        _R()._atomic_write_json(file_path, deals)

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Deal Deleted', cfg['label'], deal_id + _R()._nd_token((removed or {}).get('TradeDate')))
    return jsonify({"success": True})

@blueprint.route('/api/new-deals/<product>/cache/bulk-delete', methods=['POST'])
def api_generic_nd_bulk_delete_cache(product):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _R()._generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404

    data  = request.get_json(silent=True)
    pairs = data.get('pairs', []) if data else []
    if not pairs:
        return jsonify({"success": False, "message": "No pairs provided"}), 400

    pair_set = {(p.get('deal', ''), p.get('client', '')) for p in pairs}
    file_pairs = {}
    for deal_name, client_name in pair_set:
        fp, _ = _R()._find_generic_nd_deal(cfg, deal_name, client_name)
        if fp:
            file_pairs.setdefault(fp, set()).add((deal_name, client_name))

    deleted = 0
    for fp, pairs_in_file in file_pairs.items():
        with _R()._cache_lock:
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                deals = []
            if not isinstance(deals, list):
                deals = [deals]
            before = len(deals)
            deals  = [d for d in deals if (d.get('Deal', ''), d.get('Client', '')) not in pairs_in_file]
            deleted += before - len(deals)
            _R()._atomic_write_json(fp, deals)

    not_found = len(pair_set) - deleted
    if deleted > 0:
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'Bulk Delete', cfg['label'],
                             str(deleted) + ' deal' + ('s' if deleted != 1 else '') + ' deleted')
    return jsonify({"success": True, "deleted": deleted, "not_found": not_found})

@blueprint.route('/api/new-deals/<product>/cache/bulk-patch', methods=['POST'])
def api_generic_nd_bulk_patch_cache(product):
    if not session.get('authenticated'):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    cfg = _R()._generic_nd_cfg(product)
    if not cfg:
        return jsonify({"success": False, "message": "Unknown product"}), 404

    data    = request.get_json(silent=True)
    patches = data.get('patches', []) if data else []
    if not patches:
        return jsonify({"success": False, "message": "No patches provided"}), 400

    file_patches = {}
    for p in patches:
        deal_id = p.get('deal_id', '')
        client  = p.get('client', '')
        updates = p.get('updates', {})
        if not deal_id or not updates:
            continue
        fp, _ = _R()._find_generic_nd_deal(cfg, deal_id, client)
        if fp:
            file_patches.setdefault(fp, []).append((deal_id, client, updates))

    updated = 0
    for fp, file_ops in file_patches.items():
        with _R()._cache_lock:
            try:
                with open(fp, 'r', encoding='utf-8') as fh:
                    deals = json.load(fh)
            except (json.JSONDecodeError, ValueError):
                deals = []
            success_deals = []
            for deal_id, client, updates in file_ops:
                idx = next((i for i, d in enumerate(deals)
                            if d.get('Deal') == deal_id and (not client or d.get('Client', '') == client)), None)
                if idx is not None:
                    deals[idx].update(updates)
                    updated += 1
                    if str(updates.get('Status', '')) == 'Success':
                        success_deals.append(deals[idx].copy())
            _R()._atomic_write_json(fp, deals)
        for d in success_deals:
            _R()._generic_nd_pc_trigger(product, d)              # → pending confirmation

    if updated > 0:
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'Bulk Update', cfg['label'],
                             str(updated) + ' deal' + ('s' if updated != 1 else '') + ' updated')
    return jsonify({"success": True, "updated": updated})

@blueprint.route('/api/new-deals/<product>/send-conecta', methods=['POST'])
def api_generic_nd_send_conecta(product):
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    data = request.get_json(silent=True) or {}
    # `download: true` (o botão do preview) devolve o CONTEÚDO do arquivo em
    # vez de gravar no Batch Conecta — mesmo gerador, byte a byte, sem
    # notificação e IGNORANDO o status do deal.
    #
    # O VANILLA gera arquivo como os outros dois. Ele já nascia no download (o
    # registro dele era de outra ferramenta e o app só montava o arquivo), e a
    # mesa passou a registrar por aqui: o que muda é o DESTINO, não o gerador —
    # a mesma linha, o mesmo template do File Interpreter e as mesmas linhas de
    # verificação, agora gravadas no Batch Conecta.
    download = bool(data.get('download'))
    valid = ('fwd-start', 'other-publishers', 'vanilla')
    if product not in valid:
        return jsonify({'ok': False, 'error': 'send-conecta not available for this product'}), 404
    is_fwd = product == 'fwd-start'
    prefix = {'fwd-start': 'FWDSTART', 'other-publishers': 'OTHERPUBLISHER',
              'vanilla': 'VANILLA'}[product]
    page_url = {'fwd-start': '/new_deals-ndf-fwdstart',
                'other-publishers': '/new_deals-ndf-otherpublisher',
                'vanilla': '/new_deals-ndf-vanilla'}[product]

    deals = data.get('deals', [])
    if not deals:
        return jsonify({'ok': False, 'error': 'No deals provided'}), 400

    today = datetime.today().strftime('%Y%m%d')

    # Um destino por ARQUIVO de saída: o nome padrão é {prefix}_{bucket}.txt,
    # e a variante do template (pelo par de pernas do deal) pode cadastrar
    # outro em `file_name`. Deals do mesmo bucket com variantes de nomes
    # diferentes saem em arquivos separados — é o que o cadastro pediu.
    out_files = {}
    counts = _R().Counter()

    def _fi_dest(bucket, client):
        pair = _R()._ter_le_pair(_R()._TER_BUCKET_LE[bucket], client)
        fname = (_R()._fi_variant_file_name(_R()._TER_FI_KEY, page_url, pair)
                 or '{}_{}.txt'.format(prefix, bucket))
        if fname not in out_files:
            out_files[fname] = {'bucket': bucket, 'pair': pair, 'lines': []}
        return out_files[fname], fname

    try:
        made_by_deal = []
        for deal in deals:
            if download and isinstance(deal, dict):
                deal = {k: v for k, v in deal.items() if k != 'Status'}
            made = _R()._generic_ndf_ter_line(deal, is_fwd, page_url=page_url)
            if made is None:
                continue
            made_by_deal.append((deal, made[0]))
            bucket, line = made
            dest, fname = _fi_dest(
                bucket, re.sub(r'<[^>]+>', '', str(deal.get('Client', '') or '')).strip())
            dest['lines'].append(line)
            counts[fname] += 1
            # As linhas de verificação (tipo 2) do Vanilla saem nos DOIS
            # caminhos. Emitir só no download faria o arquivo baixado para
            # conferência diferir do que vai para a B3 — divergência que não
            # aparece em lugar nenhum até a B3 recusar o registro.
            if product == 'vanilla':
                dest['lines'].extend(
                    _R()._vanilla_verification_lines(deal, page_url, dest['pair']))
        # Quebra visão banco × visão Lawton: a linha do banco contra o Lawton
        # gera também a visão Lawton (espelho sintetizado), A MENOS que o lote
        # já traga a perna explícita do mesmo trade — aí ela é a visão Lawton
        # e sintetizar duplicaria o registro na B3. O casamento é pelos termos
        # econômicos (`_nd_lawton_sig`) e consome uma perna explícita por
        # linha do banco, para dois trades iguais no mesmo dia não dividirem
        # um espelho só.
        explicit = [_R()._nd_lawton_sig(d) for d, b in made_by_deal if b == 'LAWTON']
        for deal, bucket in made_by_deal:
            if bucket != 'BANCO' or 'LAWTON' not in str(deal.get('Client', '') or '').upper():
                continue
            sig = _R()._nd_lawton_sig(deal)
            if sig in explicit:
                explicit.remove(sig)
                continue
            mirror = _R()._nd_lawton_mirror(deal)
            made = _R()._generic_ndf_ter_line(mirror, is_fwd, page_url=page_url)
            if made is None:
                continue
            b2, l2 = made
            dest, fname = _fi_dest(b2, str(mirror.get('Client', '') or ''))
            dest['lines'].append(l2)
            counts[fname] += 1
        # O header é por ARQUIVO: a LE é a do bucket e a variante é a do par
        # do primeiro deal que caiu nele (mesma perna nossa → mesmo header).
        headers = {fname: _R()._ter_file_header(_R()._TER_BUCKET_LE[d['bucket']], today,
                                           page_url, le_pair=d['pair'])
                   for fname, d in out_files.items() if d['lines']}
    except ValueError as exc:
        _R().log.error('[ND %s] send-conecta sem header: %s', product, exc)
        return jsonify({'ok': False, 'error': str(exc) or _R()._TER_FI_ERROR}), 500

    generated = []
    try:
        if download:
            for fname, d in out_files.items():
                if not d['lines']:
                    continue
                generated.append({'filename': fname, 'count': counts[fname],
                                  'content': '\n'.join([headers[fname]] + d['lines'])})
            return jsonify({'ok': True, 'count': len(made_by_deal), 'files': generated,
                            'filename': generated[0]['filename'] if generated else ''})
        os.makedirs(_R().CONECTA_NEW_PATH, exist_ok=True)
        for fname, d in out_files.items():
            if not d['lines']:
                continue
            path = _R()._unique_filepath(_R().CONECTA_NEW_PATH, fname)
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join([headers[fname]] + d['lines']))
            generated.append({'filename': os.path.basename(path), 'count': counts[fname]})
        # `count` da resposta e da notificação = DEALS enviados; o espelho
        # sintetizado do Lawton é uma linha a mais no arquivo (conta no
        # per-file `files`), não um deal a mais.
        total = len(made_by_deal)
        if total > 0:
            cfg = _R()._generic_nd_cfg(product)
            _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                 'Sent to B3', cfg['label'] if cfg else product,
                                 str(total) + ' deal' + ('' if total == 1 else 's') + ' sent')
        primary = generated[0]['filename'] if generated else ''
        return jsonify({'ok': True, 'filename': primary, 'count': total, 'files': generated})
    except Exception as exc:                            # noqa: BLE001
        return jsonify({'ok': False, 'error': str(exc)}), 500

@blueprint.route('/api/new-deals/<product>/mapping-b3', methods=['POST'])
def api_generic_nd_mapping_b3(product):
    """B3 return-file scan for the generic NDF pages — same logic as the
    ndf-commodities mapping. The TER files write the RIGHT-14 chars of the Deal
    as Código Identificador, so the return-line match uses that suffix."""
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    cfg = _R()._generic_nd_cfg(product)
    if not cfg:
        return jsonify({'ok': False, 'error': 'Unknown product'}), 404

    data = request.get_json(silent=True) or {}
    # `ref_date` = campo Reference Date da página. Com ele a lista sai do ARQUIVO
    # DO DIA e não da tabela: a tabela mostra o resultado da última busca, então
    # mapear o que estava renderizado deixava de fora operações do mesmo dia que
    # ninguém tinha filtrado. `deals` continua aceito para chamadas com lista
    # explícita.
    sent_deals = (_R()._generic_nd_mapping_candidates(cfg, product, data.get('ref_date'))
                  if data.get('ref_date') else data.get('deals', []))
    if not sent_deals:
        return jsonify({'ok': True, 'results': []})

    mapping         = {}
    files_to_delete = []
    try:
        if not os.path.isdir(_R().RETURN_PATH):
            return jsonify({'ok': False, 'error': f'Return folder not found: {_R().RETURN_PATH}'}), 400

        for fname in os.listdir(_R().RETURN_PATH):
            fpath = os.path.join(_R().RETURN_PATH, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                with open(fpath, 'r', encoding='latin-1') as fh:
                    lines = fh.readlines()
                file_has_ter = False
                for line in lines[1:]:  # skip header row
                    line = line.strip()
                    if not line:
                        continue
                    # Sigla at chars 57-59 (1-based): only 'TER' (termo) lines
                    if line[56:59] != 'TER':
                        continue
                    file_has_ter = True
                    if 'EXECUCAO OK' not in line:
                        continue
                    parts = line.split(';')
                    if len(parts) < 2:
                        continue
                    b3_id = parts[1].strip()
                    for sd in sent_deals:
                        deal_text = sd.get('Deal', '')
                        if deal_text and deal_text not in mapping and deal_text[-14:] in line:
                            mapping[deal_text] = b3_id
                # Only delete return files that actually carried TER (NDF) lines
                if file_has_ter:
                    files_to_delete.append(fpath)
            except Exception:
                continue
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500

    results = []
    for sd in sent_deals:
        deal_text   = sd.get('Deal', '')
        client_name = sd.get('Client', '')
        if str(sd.get('Status', '') or '').strip() == 'Canceled':
            continue                    # cancelado via API: fora do mapping
        if deal_text and deal_text in mapping:
            b3_id      = mapping[deal_text]
            new_status = 'Success'
            updates    = {'Status': new_status, 'B3_ID': b3_id}
        else:
            b3_id = ''
            # Não achou no retorno: só vira 'Error' quem estava esperando
            # retorno. Agora que a varredura pega o dia inteiro em qualquer
            # status, marcar todo mundo derrubaria para Error operações que nem
            # sequer foram registradas ainda (Approved/Pending) — e, pior, um
            # Success sem B3 ID.
            prev = str(sd.get('Status', '') or '').strip()
            if prev and prev not in _R()._ND_MAPPING_ERRORABLE:
                new_status = prev
                updates    = {}
            else:
                new_status = 'Error'
                updates    = {'Status': new_status}

        success_deal = None
        if deal_text and updates:
            file_path, idx = _R()._find_generic_nd_deal(cfg, deal_text, client_name)
            if file_path is not None:
                with _R()._cache_lock:
                    try:
                        with open(file_path, 'r', encoding='utf-8') as fh:
                            deals_list = json.load(fh)
                        deals_list[idx].update(updates)
                        _R()._atomic_write_json(file_path, deals_list)
                        if new_status == 'Success':
                            success_deal = deals_list[idx].copy()
                    except Exception:
                        pass

        if success_deal is not None:
            # Vanilla / Other Publisher contra o Lawton → Intrag NDF (layout
            # "Instrucao NDF Moeda"), mesmo gatilho do update manual.
            if product in ('vanilla', 'other-publishers') and \
                    'LAWTON' in (success_deal.get('Client', '') or '').upper():
                try:
                    _R()._intrag_engine()._save_intrag_ndf_moeda_entry(success_deal)
                except Exception as exc:
                    _R().log.error('[MAPPING-%s] Intrag moeda save failed for deal=%r: %s',
                              product, deal_text, exc)
            _R()._generic_nd_pc_trigger(product, success_deal)   # → pending confirmation

        # Só entra no resultado quem MUDOU. Varrendo o dia inteiro, a lista
        # passa a incluir deals que ficaram como estavam — contá-los inflaria o
        # "N deal(s) mapped" da notificação e os contadores da tela.
        if updates:
            results.append({
                'id':     deal_text,
                'deal':   deal_text,
                'b3_id':  b3_id,
                'status': new_status,
            })

    for fpath in files_to_delete:
        try:
            os.remove(fpath)
        except Exception:
            pass

    if results:
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'B3 Mapped', cfg['label'],
                             str(len(results)) + ' deal' + ('' if len(results) == 1 else 's') + ' mapped')
    return jsonify({'ok': True, 'results': results})
