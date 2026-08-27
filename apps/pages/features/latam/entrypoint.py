# -*- coding: utf-8 -*-
"""As sete rotas da tela Latam Desk Position.

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


@_R().blueprint.route('/other-products-swap-latamdeskposition')
def other_products_swap_latamdeskposition():
    if not _R().session.get('authenticated'):
        return _R().redirect(_R().url_for('pages_blueprint.sign_in_page'))
    latest = _R()._latam_latest_ref()
    return _R().render_template('pages/other-products-swap-latamdeskposition.html',
                           segment='other-products-swap-latamdeskposition',
                           today=_R()._br_now().strftime('%Y-%m-%d'),
                           ref_date=(latest or _R().datetime.now()).strftime('%Y-%m-%d'))

@_R().blueprint.route('/api/other-products-swap-latamdeskposition/data')
def api_latam_data():
    """Sem ?date= a página abre no ÚLTIMO arquivo disponível (o relatório não é
    diário); com data, mostra exatamente aquele dia."""
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (_R().request.args.get('date') or '').strip()
    ref, latest = None, False
    if ds:
        try:
            ref = _R().datetime.strptime(ds[:10], '%Y-%m-%d')
        except ValueError:
            ref = None
    if ref is None:
        ref = _R()._latam_latest_ref()
        latest = ref is not None
        ref = ref or _R().datetime.now()
    payload = _R()._latam_collect(ref)
    payload.update({'success': True, 'latest': latest,
                    'date': ref.strftime('%Y-%m-%d'), 'date_fmt': ref.strftime('%d/%m/%Y'),
                    'dates': [d.strftime('%Y-%m-%d') for d in _R()._latam_all_dates()[:60]]})
    return _R().jsonify(payload)

@_R().blueprint.route('/api/other-products-swap-latamdeskposition/import', methods=['POST'])
def api_latam_import():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    ds = str(p.get('date', '') or '').strip()
    try:
        ref = _R().datetime.strptime(ds[:10], '%Y-%m-%d') if ds else _R().datetime.now()
    except ValueError:
        ref = _R().datetime.now()
    res = _R()._latam_import(ref)
    if res.get('success'):
        _R()._create_notification(_R().session.get('user_sid', ''), _R().session.get('user_name', ''),
                             'Latam Desk Imported', 'Latam Desk Position',
                             '{} row(s) imported ({})'.format(res.get('rows', 0), res.get('date', '')))
    return _R().jsonify(res)

@_R().blueprint.route('/api/other-products-swap-latamdeskposition/row/add', methods=['POST'])
def api_latam_row_add():
    """Linha manual → status 'OK' (maker = usuário atual). Persistida no JSON."""
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    cells = p.get('cells') or []
    sid = _R().session.get('user_sid', '')
    ref = _R()._latam_ref_from(p)
    jp, data = _R()._latam_load(ref)
    if data is None:
        data = []                                     # primeira linha manual em dia sem import
    rec = {}
    for i, c in enumerate(_R()._LATAM_LABELS):
        v = str(cells[i]).strip() if i < len(cells) and cells[i] is not None else ''
        rec[c] = _R()._latam_date(v) if c in _R()._LATAM_DATE_COLS else v
    rec['_lt_status'], rec['_lt_maker'], rec['_lt_checker'], rec['_lt_id'] = 'OK', sid, '', _R()._latam_new_id()
    data.append(rec)
    try:
        _R()._latam_save(jp, data)
    except Exception:
        _R().log.error('[latam] add save failed:\n%s', _R().traceback.format_exc())
        return _R().jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, _R().session.get('user_name', ''), 'Latam Desk Row Added',
                         'Latam Desk Position',
                         '{} ({})'.format(rec.get('Deal_ID', ''), ref.strftime('%Y-%m-%d')))
    return _R().jsonify({'success': True, 'id': rec['_lt_id']})

@_R().blueprint.route('/api/other-products-swap-latamdeskposition/row/edit', methods=['POST'])
def api_latam_row_edit():
    """Edita as células → status 'Pending', maker = usuário atual (checker limpo)."""
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    rid, cells = str(p.get('id', '')), (p.get('cells') or [])
    sid = _R().session.get('user_sid', '')
    ref = _R()._latam_ref_from(p)
    jp, data = _R()._latam_load(ref)
    rec = _R()._latam_find(data or [], rid)
    if rec is None:
        return _R().jsonify({'success': False, 'error': 'Row not found.'}), 404
    for i, c in enumerate(_R()._LATAM_LABELS):
        if i < len(cells):
            v = str(cells[i]).strip()
            rec[c] = _R()._latam_date(v) if c in _R()._LATAM_DATE_COLS else v
    rec['_lt_status'], rec['_lt_maker'], rec['_lt_checker'] = 'Pending', sid, ''
    try:
        _R()._latam_save(jp, data)
    except Exception:
        _R().log.error('[latam] edit save failed:\n%s', _R().traceback.format_exc())
        return _R().jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, _R().session.get('user_name', ''), 'Latam Desk Row Updated',
                         'Latam Desk Position',
                         '{} ({})'.format(rec.get('Deal_ID', ''), ref.strftime('%Y-%m-%d')))
    return _R().jsonify({'success': True})

@_R().blueprint.route('/api/other-products-swap-latamdeskposition/row/delete', methods=['POST'])
def api_latam_row_delete():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    rid = str(p.get('id', ''))
    sid = _R().session.get('user_sid', '')
    ref = _R()._latam_ref_from(p)
    jp, data = _R()._latam_load(ref)
    if data is None:
        return _R().jsonify({'success': False, 'error': 'No data for this date.'}), 404
    rec = _R()._latam_find(data, rid)
    if rec is None:
        return _R().jsonify({'success': False, 'error': 'Row not found.'}), 404
    data.remove(rec)
    try:
        _R()._latam_save(jp, data)
    except Exception:
        _R().log.error('[latam] delete save failed:\n%s', _R().traceback.format_exc())
        return _R().jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, _R().session.get('user_name', ''), 'Latam Desk Row Deleted',
                         'Latam Desk Position',
                         '{} ({})'.format(rec.get('Deal_ID', ''), ref.strftime('%Y-%m-%d')))
    return _R().jsonify({'success': True})

@_R().blueprint.route('/api/other-products-swap-latamdeskposition/row/confirm', methods=['POST'])
def api_latam_row_confirm():
    """Confirma uma linha Pending → 'OK'. Trava de quatro olhos: quem alterou não
    pode confirmar (outro usuário precisa)."""
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    rid = str(p.get('id', ''))
    sid = _R().session.get('user_sid', '')
    ref = _R()._latam_ref_from(p)
    jp, data = _R()._latam_load(ref)
    rec = _R()._latam_find(data or [], rid)
    if rec is None:
        return _R().jsonify({'success': False, 'error': 'Row not found.'}), 404
    maker = str(rec.get('_lt_maker', '') or '')
    if maker and maker == sid:
        return _R().jsonify({'success': False, 'error': 'same_user',
                        'message': 'A different user must confirm a row you changed.'}), 403
    rec['_lt_status'], rec['_lt_checker'] = 'OK', sid
    try:
        _R()._latam_save(jp, data)
    except Exception:
        _R().log.error('[latam] confirm save failed:\n%s', _R().traceback.format_exc())
        return _R().jsonify({'success': False, 'error': 'Save failed.'}), 500
    _R()._create_notification(sid, _R().session.get('user_name', ''), 'Latam Desk Row Confirmed',
                         'Latam Desk Position',
                         '{} ({})'.format(rec.get('Deal_ID', ''), ref.strftime('%Y-%m-%d')))
    return _R().jsonify({'success': True})
