# -*- coding: utf-8 -*-
"""As sete rotas da tela OTM Settlements.

Só a casca: o store por dia e os coletores são plataforma — o Save Daily
Settlement grava os mesmos arquivos e a família de liquidação do Other
Products lê os mesmos dados — e ficam no routes, alcançados por _R().
"""
import traceback
from datetime import datetime

from flask import jsonify, redirect, render_template, request, session, url_for

from apps.pages import blueprint


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@_R().blueprint.route('/otm-settlements')
def otm_settlements():
    if not _R().session.get('authenticated'):
        return _R().redirect(_R().url_for('pages_blueprint.sign_in_page'))
    return _R().render_template('pages/otm-settlements.html', segment='otm-settlements',
                           today=_R()._br_now().strftime('%Y-%m-%d'))

@_R().blueprint.route('/api/otm-settlements/data')
def api_otm_data():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (_R().request.args.get('date') or '').strip()
    try:
        ref = _R().datetime.strptime(ds[:10], '%Y-%m-%d') if ds else _R().datetime.now()
    except ValueError:
        ref = _R().datetime.now()
    payload = _R()._otm_collect(ref)
    payload.update({'success': True, 'date': ref.strftime('%Y-%m-%d'),
                    'date_fmt': ref.strftime('%d/%m/%Y')})
    return _R().jsonify(payload)

@_R().blueprint.route('/api/otm-settlements/import', methods=['POST'])
def api_otm_import():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    res = _R()._otm_import(_R().datetime.now())
    if res.get('success'):
        _R()._create_notification(_R().session.get('user_sid', ''), _R().session.get('user_name', ''),
                             'OTM Imported', 'OTM Settlements',
                             '{} row(s) imported ({})'.format(res.get('rows', 0), res.get('date', '')))
    return _R().jsonify(res)

@_R().blueprint.route('/api/otm-settlements/row/add', methods=['POST'])
def api_otm_row_add():
    """Insert a manual row → status 'OK' (maker = current user). Persisted to JSON."""
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    cells = p.get('cells') or []
    sid = _R().session.get('user_sid', '')
    ref = _R()._otm_ref_from(p)
    jp, data = _R()._otm_load(ref)
    if data is None:
        data = []                                     # first manual row on a day with no import
    rec = {c: (str(cells[i]).strip() if i < len(cells) and cells[i] is not None else '')
           for i, c in enumerate(_R()._OTM_COLUMNS)}
    rec['Cpty Name'] = rec.get('Cpty Name', '').upper()
    rec['_ot_status'], rec['_ot_maker'], rec['_ot_checker'], rec['_ot_id'] = 'OK', sid, '', _R()._otm_new_id()
    data.append(rec)
    try:
        _R()._otm_save(jp, data)
    except Exception:
        _R().log.error('[otm] add save failed:\n%s', _R().traceback.format_exc())
        return _R().jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, _R().session.get('user_name', ''), 'OTM Row Added', 'OTM Settlements',
                         '{} ({})'.format(rec.get('Trade Id', ''), ref.strftime('%Y-%m-%d')))
    return _R().jsonify({'success': True, 'id': rec['_ot_id']})

@_R().blueprint.route('/api/otm-settlements/row/edit', methods=['POST'])
def api_otm_row_edit():
    """Edit a row's cells → status 'Pending', maker = current user (checker reset)."""
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    rid, cells = str(p.get('id', '')), (p.get('cells') or [])
    sid = _R().session.get('user_sid', '')
    jp, data = _R()._otm_load(_R()._otm_ref_from(p))
    rec = _R()._otm_find(data or [], rid)
    if rec is None:
        return _R().jsonify({'success': False, 'error': 'Row not found.'}), 404
    for i, c in enumerate(_R()._OTM_COLUMNS):
        if i < len(cells):
            rec[c] = str(cells[i]).strip()
    rec['Cpty Name'] = rec.get('Cpty Name', '').upper()
    rec['_ot_status'], rec['_ot_maker'], rec['_ot_checker'] = 'Pending', sid, ''
    try:
        _R()._otm_save(jp, data)
    except Exception:
        _R().log.error('[otm] edit save failed:\n%s', _R().traceback.format_exc())
        return _R().jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, _R().session.get('user_name', ''), 'OTM Row Updated', 'OTM Settlements',
                         '{} ({})'.format(rec.get('Trade Id', ''), _R()._otm_ref_from(p).strftime('%Y-%m-%d')))
    return _R().jsonify({'success': True})

@_R().blueprint.route('/api/otm-settlements/row/delete', methods=['POST'])
def api_otm_row_delete():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    rid = str(p.get('id', ''))
    sid = _R().session.get('user_sid', '')
    jp, data = _R()._otm_load(_R()._otm_ref_from(p))
    if data is None:
        return _R().jsonify({'success': False, 'error': 'No data for this date.'}), 404
    rec = _R()._otm_find(data, rid)
    if rec is None:
        return _R().jsonify({'success': False, 'error': 'Row not found.'}), 404
    data.remove(rec)
    try:
        _R()._otm_save(jp, data)
    except Exception:
        _R().log.error('[otm] delete save failed:\n%s', _R().traceback.format_exc())
        return _R().jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, _R().session.get('user_name', ''), 'OTM Row Deleted', 'OTM Settlements',
                         '{} ({})'.format(rec.get('Trade Id', ''), _R()._otm_ref_from(p).strftime('%Y-%m-%d')))
    return _R().jsonify({'success': True})

@_R().blueprint.route('/api/otm-settlements/row/confirm', methods=['POST'])
def api_otm_row_confirm():
    """Confirm a Pending row → 'OK'. Maker/checker guard: the user who changed it
    cannot confirm it (a different user must)."""
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    rid = str(p.get('id', ''))
    sid = _R().session.get('user_sid', '')
    jp, data = _R()._otm_load(_R()._otm_ref_from(p))
    rec = _R()._otm_find(data or [], rid)
    if rec is None:
        return _R().jsonify({'success': False, 'error': 'Row not found.'}), 404
    maker = str(rec.get('_ot_maker', '') or '')
    if maker and maker == sid:
        return _R().jsonify({'success': False, 'error': 'same_user',
                        'message': 'A different user must confirm a row you changed.'}), 403
    rec['_ot_status'], rec['_ot_checker'] = 'OK', sid
    try:
        _R()._otm_save(jp, data)
    except Exception:
        _R().log.error('[otm] confirm save failed:\n%s', _R().traceback.format_exc())
        return _R().jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, _R().session.get('user_name', ''), 'OTM Row Confirmed', 'OTM Settlements',
                         '{} ({})'.format(rec.get('Trade Id', ''), _R()._otm_ref_from(p).strftime('%Y-%m-%d')))
    return _R().jsonify({'success': True})
