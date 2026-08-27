# -*- coding: utf-8 -*-
"""As sete rotas da tela Cognos."""
import traceback
from datetime import datetime

from flask import jsonify, redirect, render_template, request, session, url_for

from apps.pages import blueprint
from apps.pages.features.cognos import commands, domain, queries


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/cognos')
def cognos():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/cognos.html', segment='cognos',
                           today=_R()._br_now().strftime('%Y-%m-%d'))

@blueprint.route('/api/cognos/data')
def api_cog_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    payload = queries._cog_collect(ref)
    payload.update({'success': True, 'date': ref.strftime('%Y-%m-%d'),
                    'date_fmt': ref.strftime('%d/%m/%Y')})
    return jsonify(payload)

@blueprint.route('/api/cognos/import', methods=['POST'])
def api_cog_import():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    res = commands._cog_import(datetime.now())
    if res.get('success'):
        _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                             'Cognos Imported', 'Cognos',
                             '{} row(s) imported ({})'.format(res.get('rows', 0), res.get('date', '')))
    return jsonify(res)

@blueprint.route('/api/cognos/row/add', methods=['POST'])
def api_cog_row_add():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    cells = p.get('cells') or []
    sid = session.get('user_sid', '')
    ref = domain._cog_ref_from(p)
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
        _R().log.error('[cognos] add save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'Cognos Row Added', 'Cognos',
                         '{} ({})'.format(rec.get('Athena ID', ''), ref.strftime('%Y-%m-%d')))
    return jsonify({'success': True, 'id': rec['_cg_id']})

@blueprint.route('/api/cognos/row/edit', methods=['POST'])
def api_cog_row_edit():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    rid, cells = str(p.get('id', '')), (p.get('cells') or [])
    sid = session.get('user_sid', '')
    jp, data = _R()._cog_load(domain._cog_ref_from(p))
    rec = _R()._cog_find(data or [], rid)
    if rec is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    for i, c in enumerate(_R()._COG_COLUMNS):
        if i < len(cells):
            rec[c] = str(cells[i]).strip()
    rec['_cg_status'], rec['_cg_maker'], rec['_cg_checker'] = 'Pending', sid, ''
    try:
        _R()._cog_save(jp, data)
    except Exception:
        _R().log.error('[cognos] edit save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'Cognos Row Updated', 'Cognos',
                         '{} ({})'.format(rec.get('Athena ID', ''), domain._cog_ref_from(p).strftime('%Y-%m-%d')))
    return jsonify({'success': True})

@blueprint.route('/api/cognos/row/delete', methods=['POST'])
def api_cog_row_delete():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    rid = str(p.get('id', ''))
    sid = session.get('user_sid', '')
    jp, data = _R()._cog_load(domain._cog_ref_from(p))
    if data is None:
        return jsonify({'success': False, 'error': 'No data for this date.'}), 404
    rec = _R()._cog_find(data, rid)
    if rec is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    data.remove(rec)
    try:
        _R()._cog_save(jp, data)
    except Exception:
        _R().log.error('[cognos] delete save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'Cognos Row Deleted', 'Cognos',
                         '{} ({})'.format(rec.get('Athena ID', ''), domain._cog_ref_from(p).strftime('%Y-%m-%d')))
    return jsonify({'success': True})

@blueprint.route('/api/cognos/row/confirm', methods=['POST'])
def api_cog_row_confirm():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    rid = str(p.get('id', ''))
    sid = session.get('user_sid', '')
    jp, data = _R()._cog_load(domain._cog_ref_from(p))
    rec = _R()._cog_find(data or [], rid)
    if rec is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    maker = str(rec.get('_cg_maker', '') or '')
    if maker and maker == sid:
        return jsonify({'success': False, 'error': 'same_user',
                        'message': 'A different user must confirm a row you changed.'}), 403
    rec['_cg_status'], rec['_cg_checker'] = 'OK', sid
    try:
        _R()._cog_save(jp, data)
    except Exception:
        _R().log.error('[cognos] confirm save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'Cognos Row Confirmed', 'Cognos',
                         '{} ({})'.format(rec.get('Athena ID', ''), domain._cog_ref_from(p).strftime('%Y-%m-%d')))
    return jsonify({'success': True})
