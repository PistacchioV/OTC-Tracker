# -*- coding: utf-8 -*-
"""As rotas de Index B3 (o editor do SwapIndex.json).

Só a casca: o arquivo é o MESMO que o cadastro swap-index do /mapping edita.
"""
import io
import json
import os
import re
import traceback
from datetime import datetime

from flask import (jsonify, redirect, render_template, request,
                   session, url_for)

from apps.pages import blueprint


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@_R().blueprint.route('/api/b3/update', methods=['POST'])
def api_b3_update():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Unauthorized'}), 401
    payload = _R().request.get_json(silent=True) or {}
    table   = payload.get('table', '')
    idx     = payload.get('idx')
    fields  = payload.get('fields', {})
    action  = payload.get('action', 'edit')   # 'edit' | 'approve'
    user    = _R().session.get('user_sid', 'UNKNOWN')

    if table not in _R()._B3_FILE_MAP or idx is None:
        return _R().jsonify({'ok': False, 'error': 'bad_request'}), 400

    if not _R()._user_can_access_page('/reference-data' if table == 'refdata' else '/index-b3'):
        return _R().jsonify({'ok': False, 'error': 'forbidden'}), 403

    records, path = _R()._b3_load(table)
    if not (0 <= int(idx) < len(records)):
        return _R().jsonify({'ok': False, 'error': 'bad_index'}), 400

    rec = records[int(idx)]

    if action == 'approve':
        if rec.get('MAKER') == user:
            return _R().jsonify({'ok': False, 'error': 'same_user'}), 403
        rec['CHECKER'] = user
        new_status = 'INACTIVE' if rec.get('STATUS') == 'PENDING INACTIVE' else 'ACTIVE'
        rec['STATUS']  = new_status
    elif action == 'deactivate':
        rec['STATUS']  = 'PENDING INACTIVE'
        rec['MAKER']   = user
        rec['CHECKER'] = None
        new_status     = 'PENDING INACTIVE'
    else:
        for k, v in fields.items():
            rec[k] = v
        rec['STATUS']  = 'PENDING'
        rec['MAKER']   = user
        rec['CHECKER'] = None
        new_status     = 'PENDING'

    _R()._b3_save(path, records)
    # On checker approval of a Reference Data counterparty (→ ACTIVE), make sure
    # its Electronic Inventory folder tree exists. This touches a network share
    # (listdir + makedirs) and can be slow, so run it OFF the request path — the
    # response (and the on-screen status update + notification) must not wait.
    if table == 'refdata' and action == 'approve' and new_status == 'ACTIVE':
        try:
            _R().threading.Thread(target=_R()._ensure_counterparty_folders,
                             args=(rec.get('COUNTERPARTY', ''),), daemon=True).start()
        except Exception:
            pass
    # Reference Data shares this endpoint but is its own page — name it correctly
    # and carry SPN + counterparty so the bell deep-links to /reference-data?spn=.
    if table == 'refdata':
        page = 'Reference Data'
        spn  = str(rec.get('SPN', '') or '').strip()
        name = str(rec.get('COUNTERPARTY', '') or '').strip()
        detail = ('SPN ' + spn) if spn else 'SPN —'
        if name:
            detail += ' · ' + name
        detail += ' — ' + action + ' → ' + new_status
    else:
        page = 'Index B3'
        detail = table + ' — ' + action + ' → ' + new_status
    _R()._create_notification(user, _R().session.get('user_name', ''), 'Item Updated', page, detail)
    return _R().jsonify({'ok': True, 'new_status': new_status})

@_R().blueprint.route('/api/b3/delete', methods=['POST'])
def api_b3_delete():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Unauthorized'}), 401
    payload = _R().request.get_json(silent=True) or {}
    table   = payload.get('table', '')
    idx     = payload.get('idx')

    if table not in _R()._B3_FILE_MAP or idx is None:
        return _R().jsonify({'ok': False, 'error': 'bad_request'}), 400

    if not _R()._user_can_access_page('/reference-data' if table == 'refdata' else '/index-b3'):
        return _R().jsonify({'ok': False, 'error': 'forbidden'}), 403

    records, path = _R()._b3_load(table)
    if not (0 <= int(idx) < len(records)):
        return _R().jsonify({'ok': False, 'error': 'bad_index'}), 400

    removed = records.pop(int(idx))
    _R()._b3_save(path, records)
    if table == 'refdata':
        page = 'Reference Data'
        spn  = str((removed or {}).get('SPN', '') or '').strip()
        name = str((removed or {}).get('COUNTERPARTY', '') or '').strip()
        detail = ('SPN ' + spn) if spn else 'SPN —'
        if name:
            detail += ' · ' + name
    else:
        page = 'Index B3'
        detail = table
    _R()._create_notification(_R().session.get('user_sid', ''), _R().session.get('user_name', ''),
                         'Item Deleted', page, detail)
    return _R().jsonify({'ok': True})

@_R().blueprint.route('/api/b3/add', methods=['POST'])
def api_b3_add():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Unauthorized'}), 401
    payload = _R().request.get_json(silent=True) or {}
    table   = payload.get('table', '')
    fields  = payload.get('fields', {})
    user    = _R().session.get('user_sid', 'UNKNOWN')

    if table not in _R()._B3_FILE_MAP:
        return _R().jsonify({'ok': False, 'error': 'bad_request'}), 400

    if not _R()._user_can_access_page('/reference-data' if table == 'refdata' else '/index-b3'):
        return _R().jsonify({'ok': False, 'error': 'forbidden'}), 403

    records, path = _R()._b3_load(table)
    fields['STATUS']  = 'PENDING'
    fields['MAKER']   = user
    fields['CHECKER'] = None
    records.append(fields)
    _R()._b3_save(path, records)

    # Reference Data shares this endpoint but is its own page — name it correctly
    # and carry SPN + counterparty so the bell deep-links to /reference-data?spn=.
    if table == 'refdata':
        page = 'Reference Data'
        spn  = str(fields.get('SPN', '') or '').strip()
        name = str(fields.get('COUNTERPARTY', '') or '').strip()
        detail = ('SPN ' + spn) if spn else 'SPN —'
        if name:
            detail += ' · ' + name
        detail += ' (Pending approval)'
    else:
        page = 'Index B3'
        detail = table + ': ' + str(fields.get('TICKER', fields.get('CODE', fields.get('NAME', ''))))
    _R()._create_notification(user, _R().session.get('user_name', ''), 'New Item', page, detail)
    return _R().jsonify({'ok': True, 'idx': len(records) - 1})
