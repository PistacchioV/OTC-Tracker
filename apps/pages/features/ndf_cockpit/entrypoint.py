# -*- coding: utf-8 -*-
"""As rotas de NDF Cockpit.

Só a casca: o store por dia é plataforma — o resto fica no routes até a fase platform/, alcançado por _R().
"""
import traceback
from datetime import datetime

from flask import (jsonify, redirect, render_template, request,
                   session, url_for)

from apps.pages import blueprint


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/ndf-cockpit')
def ndf_cockpit():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/ndf-cockpit.html', segment='ndf-cockpit',
                           today=_R()._br_now().strftime('%Y-%m-%d'))

@blueprint.route('/api/ndf-cockpit/data')
def api_ndfc_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    payload = _R()._ndfc_collect(ref)
    payload.update({'success': True, 'date': ref.strftime('%Y-%m-%d'),
                    'date_fmt': ref.strftime('%d/%m/%Y')})
    return jsonify(payload)

@blueprint.route('/api/ndf-cockpit/import', methods=['POST'])
def api_ndfc_import():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    res = _R()._ndfc_import(datetime.now())
    if res.get('success'):
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'NDF Cockpit Imported', 'NDF Cockpit',
                             '{}: {} row(s) ({})'.format(res.get('file', ''), res.get('rows', 0), res.get('date', '')))
    return jsonify(res)

@blueprint.route('/api/ndf-cockpit/row/add', methods=['POST'])
def api_ndfc_row_add():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    cells = p.get('cells') or []
    sid = session.get('user_sid', '')
    ref = _R()._ndfc_ref_from(p)
    jp, data = _R()._ndfc_load(ref)
    if data is None:
        data = []
    rec = {c: (str(cells[i]).strip() if i < len(cells) and cells[i] is not None else '')
           for i, c in enumerate(_R()._NDFC_COLUMNS)}
    for c in _R()._NDFC_UPPER_COLS:
        rec[c] = rec.get(c, '').upper()
    rec['_nc_status'], rec['_nc_maker'], rec['_nc_checker'], rec['_nc_id'] = 'OK', sid, '', _R()._otm_new_id()
    data.append(rec)
    try:
        _R()._ndfc_save(jp, data)
    except Exception:
        _R().log.error('[ndfc] add save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'NDF Cockpit Row Added', 'NDF Cockpit',
                         '{} ({})'.format(rec.get('ID_DEAL', ''), ref.strftime('%Y-%m-%d')))
    return jsonify({'success': True, 'id': rec['_nc_id']})

@blueprint.route('/api/ndf-cockpit/row/edit', methods=['POST'])
def api_ndfc_row_edit():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    rid, cells = str(p.get('id', '')), (p.get('cells') or [])
    sid = session.get('user_sid', '')
    jp, data = _R()._ndfc_load(_R()._ndfc_ref_from(p))
    rec = _R()._ndfc_find(data or [], rid)
    if rec is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    for i, c in enumerate(_R()._NDFC_COLUMNS):
        if i < len(cells):
            rec[c] = str(cells[i]).strip()
    for c in _R()._NDFC_UPPER_COLS:
        rec[c] = rec.get(c, '').upper()
    rec['_nc_status'], rec['_nc_maker'], rec['_nc_checker'] = 'Pending', sid, ''
    try:
        _R()._ndfc_save(jp, data)
    except Exception:
        _R().log.error('[ndfc] edit save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'NDF Cockpit Row Updated', 'NDF Cockpit',
                         '{} ({})'.format(rec.get('ID_DEAL', ''), _R()._ndfc_ref_from(p).strftime('%Y-%m-%d')))
    return jsonify({'success': True})

@blueprint.route('/api/ndf-cockpit/row/delete', methods=['POST'])
def api_ndfc_row_delete():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    rid = str(p.get('id', ''))
    sid = session.get('user_sid', '')
    jp, data = _R()._ndfc_load(_R()._ndfc_ref_from(p))
    if data is None:
        return jsonify({'success': False, 'error': 'No data for this date.'}), 404
    rec = _R()._ndfc_find(data, rid)
    if rec is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    data.remove(rec)
    try:
        _R()._ndfc_save(jp, data)
    except Exception:
        _R().log.error('[ndfc] delete save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'NDF Cockpit Row Deleted', 'NDF Cockpit',
                         '{} ({})'.format(rec.get('ID_DEAL', ''), _R()._ndfc_ref_from(p).strftime('%Y-%m-%d')))
    return jsonify({'success': True})

@blueprint.route('/api/ndf-cockpit/row/confirm', methods=['POST'])
def api_ndfc_row_confirm():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    rid = str(p.get('id', ''))
    sid = session.get('user_sid', '')
    jp, data = _R()._ndfc_load(_R()._ndfc_ref_from(p))
    rec = _R()._ndfc_find(data or [], rid)
    if rec is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    maker = str(rec.get('_nc_maker', '') or '')
    if maker and maker == sid:
        return jsonify({'success': False, 'error': 'same_user',
                        'message': 'A different user must confirm a row you changed.'}), 403
    rec['_nc_status'], rec['_nc_checker'] = 'OK', sid
    try:
        _R()._ndfc_save(jp, data)
    except Exception:
        _R().log.error('[ndfc] confirm save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'NDF Cockpit Row Confirmed', 'NDF Cockpit',
                         '{} ({})'.format(rec.get('ID_DEAL', ''), _R()._ndfc_ref_from(p).strftime('%Y-%m-%d')))
    return jsonify({'success': True})
