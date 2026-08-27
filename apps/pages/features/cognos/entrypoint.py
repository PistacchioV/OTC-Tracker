# -*- coding: utf-8 -*-
"""As sete rotas da tela Cognos."""
import traceback
from datetime import datetime

from flask import jsonify, redirect, render_template, request, session, url_for

from apps.pages import blueprint
from apps.pages.features.cognos import engine


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@_R().blueprint.route('/cognos')
def cognos():
    if not _R().session.get('authenticated'):
        return _R().redirect(_R().url_for('pages_blueprint.sign_in_page'))
    return _R().render_template('pages/cognos.html', segment='cognos',
                           today=_R()._br_now().strftime('%Y-%m-%d'))

@_R().blueprint.route('/api/cognos/data')
def api_cog_data():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (_R().request.args.get('date') or '').strip()
    try:
        ref = _R().datetime.strptime(ds[:10], '%Y-%m-%d') if ds else _R().datetime.now()
    except ValueError:
        ref = _R().datetime.now()
    payload = engine._cog_collect(ref)
    payload.update({'success': True, 'date': ref.strftime('%Y-%m-%d'),
                    'date_fmt': ref.strftime('%d/%m/%Y')})
    return _R().jsonify(payload)

@_R().blueprint.route('/api/cognos/import', methods=['POST'])
def api_cog_import():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    res = engine._cog_import(_R().datetime.now())
    if res.get('success'):
        _R()._create_notification(_R().session.get('user_sid', ''), _R().session.get('user_name', ''),
                             'Cognos Imported', 'Cognos',
                             '{} row(s) imported ({})'.format(res.get('rows', 0), res.get('date', '')))
    return _R().jsonify(res)

@_R().blueprint.route('/api/cognos/row/add', methods=['POST'])
def api_cog_row_add():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    cells = p.get('cells') or []
    sid = _R().session.get('user_sid', '')
    ref = engine._cog_ref_from(p)
    jp, data = _R()._cog_load(ref)
    if data is None:
        data = []
    rec = {c: (str(cells[i]).strip() if i < len(cells) and cells[i] is not None else '')
           for i, c in enumerate(_R()._COG_COLUMNS)}
    rec['_cg_status'], rec['_cg_maker'], rec['_cg_checker'], rec['_cg_id'] = 'OK', sid, '', _R()._cog_new_id()
    data.append(rec)
    try:
        _R()._cog_save(jp, data)
    except Exception:
        _R().log.error('[cognos] add save failed:\n%s', _R().traceback.format_exc())
        return _R().jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, _R().session.get('user_name', ''), 'Cognos Row Added', 'Cognos',
                         '{} ({})'.format(rec.get('Athena ID', ''), ref.strftime('%Y-%m-%d')))
    return _R().jsonify({'success': True, 'id': rec['_cg_id']})

@_R().blueprint.route('/api/cognos/row/edit', methods=['POST'])
def api_cog_row_edit():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    rid, cells = str(p.get('id', '')), (p.get('cells') or [])
    sid = _R().session.get('user_sid', '')
    jp, data = _R()._cog_load(engine._cog_ref_from(p))
    rec = _R()._cog_find(data or [], rid)
    if rec is None:
        return _R().jsonify({'success': False, 'error': 'Row not found.'}), 404
    for i, c in enumerate(_R()._COG_COLUMNS):
        if i < len(cells):
            rec[c] = str(cells[i]).strip()
    rec['_cg_status'], rec['_cg_maker'], rec['_cg_checker'] = 'Pending', sid, ''
    try:
        _R()._cog_save(jp, data)
    except Exception:
        _R().log.error('[cognos] edit save failed:\n%s', _R().traceback.format_exc())
        return _R().jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, _R().session.get('user_name', ''), 'Cognos Row Updated', 'Cognos',
                         '{} ({})'.format(rec.get('Athena ID', ''), engine._cog_ref_from(p).strftime('%Y-%m-%d')))
    return _R().jsonify({'success': True})

@_R().blueprint.route('/api/cognos/row/delete', methods=['POST'])
def api_cog_row_delete():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    rid = str(p.get('id', ''))
    sid = _R().session.get('user_sid', '')
    jp, data = _R()._cog_load(engine._cog_ref_from(p))
    if data is None:
        return _R().jsonify({'success': False, 'error': 'No data for this date.'}), 404
    rec = _R()._cog_find(data, rid)
    if rec is None:
        return _R().jsonify({'success': False, 'error': 'Row not found.'}), 404
    data.remove(rec)
    try:
        _R()._cog_save(jp, data)
    except Exception:
        _R().log.error('[cognos] delete save failed:\n%s', _R().traceback.format_exc())
        return _R().jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, _R().session.get('user_name', ''), 'Cognos Row Deleted', 'Cognos',
                         '{} ({})'.format(rec.get('Athena ID', ''), engine._cog_ref_from(p).strftime('%Y-%m-%d')))
    return _R().jsonify({'success': True})

@_R().blueprint.route('/api/cognos/row/confirm', methods=['POST'])
def api_cog_row_confirm():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    rid = str(p.get('id', ''))
    sid = _R().session.get('user_sid', '')
    jp, data = _R()._cog_load(engine._cog_ref_from(p))
    rec = _R()._cog_find(data or [], rid)
    if rec is None:
        return _R().jsonify({'success': False, 'error': 'Row not found.'}), 404
    maker = str(rec.get('_cg_maker', '') or '')
    if maker and maker == sid:
        return _R().jsonify({'success': False, 'error': 'same_user',
                        'message': 'A different user must confirm a row you changed.'}), 403
    rec['_cg_status'], rec['_cg_checker'] = 'OK', sid
    try:
        _R()._cog_save(jp, data)
    except Exception:
        _R().log.error('[cognos] confirm save failed:\n%s', _R().traceback.format_exc())
        return _R().jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, _R().session.get('user_name', ''), 'Cognos Row Confirmed', 'Cognos',
                         '{} ({})'.format(rec.get('Athena ID', ''), engine._cog_ref_from(p).strftime('%Y-%m-%d')))
    return _R().jsonify({'success': True})
