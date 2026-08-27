# -*- coding: utf-8 -*-
"""As rotas de NDF Other Publisher.

Só a casca: coleta e Conecta são plataforma do New Deals — o resto fica no routes até a fase platform/, alcançado por _R().
"""
import os
import traceback
from datetime import datetime

from flask import (jsonify, redirect, render_template, request,
                   send_file, session, url_for)

from apps.pages import blueprint


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/ndf-other-publisher')
def ndf_other_publisher():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/ndf-other-publisher.html', segment='ndf-other-publisher',
                           ref_date=datetime.now().strftime('%Y-%m-%d'))

@blueprint.route('/api/ndf-other-publisher/data')
def api_ndfop_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    payload = _R()._ndfop_collect(ref)
    payload.update({'success': True, 'ref_date': ref.strftime('%Y-%m-%d'),
                    'ref_date_fmt': ref.strftime('%d/%m/%Y')})
    return jsonify(payload)

@blueprint.route('/api/ndf-other-publisher/row/confirm', methods=['POST'])
def api_ndfop_row_confirm():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    rid = str(p.get('id', '') or '').strip()
    if not rid:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    ds = str(p.get('date', '') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    path, meta = _R()._ndfop_meta_load(ref)
    sid = session.get('user_sid', '')
    entry = meta.get(rid) or {}
    entry.update({'status': 'OK', 'checker': sid, 'maker': entry.get('maker', '')})
    meta[rid] = entry
    try:
        _R()._ndfop_meta_save(path, meta)
    except Exception:
        _R().log.error('[ndf-other-publisher] confirm save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'NDF Other Publisher Row Confirmed',
                         _R()._NOTIF_DS_OTHERPUB, '{} ({})'.format(rid, ref.strftime('%Y-%m-%d')))
    return jsonify({'success': True})

@blueprint.route('/api/ndf-other-publisher/row/edit', methods=['POST'])
def api_ndfop_row_edit():
    """Persist manual cell overrides for a derived row. The edit is an overlay —
    the row keeps being rebuilt from Operations B3 / Cockpit / Live Position, and
    only the edited cells are replaced. Editing resets the row to Pending so the
    checker has to look at it again."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    rid = str(p.get('id', '') or '').strip()
    cells = p.get('cells')
    if not rid or not isinstance(cells, list):
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    ds = str(p.get('date', '') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    path, meta = _R()._ndfop_meta_load(ref)
    sid = session.get('user_sid', '')
    entry = meta.get(rid) or {}
    entry.update({'cells': [str(c or '').strip() for c in cells[:len(_R()._NDFOP_COLUMNS)]],
                  'status': 'Pending', 'maker': sid, 'checker': ''})
    meta[rid] = entry
    try:
        _R()._ndfop_meta_save(path, meta)
    except Exception:
        _R().log.error('[ndf-other-publisher] edit save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'NDF Other Publisher Row Edited',
                         _R()._NOTIF_DS_OTHERPUB, '{} ({})'.format(rid, ref.strftime('%Y-%m-%d')))
    return jsonify({'success': True})

@blueprint.route('/api/ndf-other-publisher/row/delete', methods=['POST'])
def api_ndfop_row_delete():
    """Hide a derived row. Nothing is removed from the source files, so the delete
    is recorded as a tombstone in the day's overlay and can be undone by editing
    the JSON."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    rid = str(p.get('id', '') or '').strip()
    if not rid:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    ds = str(p.get('date', '') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    path, meta = _R()._ndfop_meta_load(ref)
    sid = session.get('user_sid', '')
    entry = meta.get(rid) or {}
    entry.update({'deleted': True, 'deleted_by': sid})
    meta[rid] = entry
    try:
        _R()._ndfop_meta_save(path, meta)
    except Exception:
        _R().log.error('[ndf-other-publisher] delete save failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, session.get('user_name', ''), 'NDF Other Publisher Row Deleted',
                         _R()._NOTIF_DS_OTHERPUB, '{} ({})'.format(rid, ref.strftime('%Y-%m-%d')))
    return jsonify({'success': True})

@blueprint.route('/api/ndf-other-publisher/row/preview')
def api_ndfop_row_preview():
    """Double-click preview: the Conecta fields of one row, vertically. A Lawton
    row returns two views (Banco × Lawton and the account-swapped Lawton × Banco)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    rid = (request.args.get('id') or '').strip()
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    cells = _R()._ndfop_rows_by_id(ref).get(rid)
    if cells is None:
        return jsonify({'success': False, 'error': 'Row not found.'}), 404
    lawton = _R()._ndfop_acct8(cells[_R()._NDFOP_COLUMNS.index('CONTA CONTRAPARTE')]) == _R()._NDFOP_LAWTON
    try:
        views = [{'title': 'Banco × Lawton' if lawton else 'Banco',
                  'fields': _R()._ndfop_conecta_fields(cells)}]
        if lawton:
            views.append({'title': 'Lawton × Banco',
                          'fields': _R()._ndfop_conecta_fields(cells, swap=True)})
    except ValueError:
        _R().log.error('[ndf-other-publisher] preview failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': _R()._NDFOP_FI_ERROR}), 500
    return jsonify({'success': True, 'id': rid, 'views': views})

@blueprint.route('/api/ndf-other-publisher/send', methods=['POST'])
def api_ndfop_send():
    """Row-level or batch send: writes TAXA_BANCO.txt (and TAXA_LAWTON.txt when a
    Lawton row is included) to the Batch Conecta New folder. All-or-nothing: a row
    without a usable TX PARIDADE aborts the whole request, so a batch is never
    half-sent."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    ids = [str(i or '').strip() for i in (p.get('ids') or []) if str(i or '').strip()]
    if not ids:
        return jsonify({'success': False, 'error': 'No rows selected.'}), 400
    ds = str(p.get('date', '') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    by_id = _R()._ndfop_rows_by_id(ref)
    missing = [i for i in ids if i not in by_id]
    if missing:
        return jsonify({'success': False,
                        'error': 'Row(s) not found: ' + ', '.join(missing)}), 404
    i_stk = _R()._NDFOP_COLUMNS.index('TX PARIDADE')
    bad = [i for i in ids if not _R()._ndfop_rate12(by_id[i][i_stk])]
    if bad:
        return jsonify({'success': False,
                        'error': 'TX PARIDADE missing/invalid: ' + ', '.join(bad)}), 400
    banco_lines, lawton_lines = [], []
    try:
        for rid in ids:
            cells = by_id[rid]
            banco_lines.append(''.join(v for _, v in _R()._ndfop_conecta_fields(cells)))
            if _R()._ndfop_acct8(cells[_R()._NDFOP_COLUMNS.index('CONTA CONTRAPARTE')]) == _R()._NDFOP_LAWTON:
                lawton_lines.append(''.join(v for _, v in _R()._ndfop_conecta_fields(cells, swap=True)))
        # Headers differ by participant name, TCO_* style: the template's X(20)
        # pads both (JPMORGANBM = 10 + 10 spaces, INTRAGLAWTONFDO = 15 + 5).
        banco_header = _R()._ndfop_conecta_header('JPMORGANBM')
        lawton_header = _R()._ndfop_conecta_header('INTRAGLAWTONFDO')
    except ValueError:
        _R().log.error('[ndf-other-publisher] send failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': _R()._NDFOP_FI_ERROR}), 500
    files = []
    try:
        os.makedirs(_R().CONECTA_NEW_PATH, exist_ok=True)
        fp = _R()._unique_filepath(_R().CONECTA_NEW_PATH, 'TAXA_BANCO.txt')
        with open(fp, 'w', encoding='utf-8') as fh:
            fh.write('\n'.join([banco_header] + banco_lines))
        files.append({'filename': os.path.basename(fp), 'count': len(banco_lines)})
        if lawton_lines:
            fp = _R()._unique_filepath(_R().CONECTA_NEW_PATH, 'TAXA_LAWTON.txt')
            with open(fp, 'w', encoding='utf-8') as fh:
                fh.write('\n'.join([lawton_header] + lawton_lines))
            files.append({'filename': os.path.basename(fp), 'count': len(lawton_lines)})
    except Exception as exc:
        _R().log.error('[ndf-other-publisher] send failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': str(exc)}), 500
    sid = session.get('user_sid', '')
    # Files are on the share — flip the rows to Sent in the day's overlay (same
    # as New Deals: checker = whoever sent). Best-effort: a meta write failure
    # must not report the send itself as failed.
    try:
        path, meta = _R()._ndfop_meta_load(ref)
        for rid in ids:
            entry = meta.get(rid) or {}
            entry.update({'status': 'Sent', 'checker': sid})
            meta[rid] = entry
        _R()._ndfop_meta_save(path, meta)
    except Exception:
        _R().log.error('[ndf-other-publisher] sent-status save failed:\n%s', traceback.format_exc())
    _R()._create_notification(sid, session.get('user_name', ''), 'Sent to B3', _R()._NOTIF_DS_OTHERPUB,
                         str(len(ids)) + ' row' + ('' if len(ids) == 1 else 's') + ' sent')
    return jsonify({'success': True, 'count': len(ids), 'files': files})
