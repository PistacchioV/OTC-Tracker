# -*- coding: utf-8 -*-
"""Rotas de Live Position › Swap › Strategy."""
from flask import jsonify, redirect, render_template, request, session, url_for

from apps.pages import blueprint
from apps.pages.features.swap_strategy import commands, queries


def _R():
    from apps.pages import routes
    return routes


def _erro(exc):
    return jsonify({'success': False, 'code': exc.code, 'params': exc.params,
                    'message': exc.code}), exc.status


@blueprint.route('/live-position-swap-strategy')
def live_position_swap_strategy():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/live-position-swap-strategy.html',
                           segment='live-position-swap-strategy')


@blueprint.route('/api/live-position-swap-strategy/data')
def api_swap_strategy_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    payload = queries.entries()
    payload['success'] = True
    return jsonify(payload)


@blueprint.route('/api/live-position-swap-strategy/import-file', methods=['POST'])
def api_swap_strategy_import():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    f = request.files.get('file')
    if f is None:
        return jsonify({'success': False, 'code': 'strategy_no_file', 'params': {},
                        'message': 'strategy_no_file'}), 400
    try:
        out = commands.import_file(f.read(), f.filename or '', sid=session.get('user_sid', ''))
    except commands.CommandError as exc:
        return _erro(exc)
    out['success'] = True
    return jsonify(out)


@blueprint.route('/api/live-position-swap-strategy/edit', methods=['POST'])
def api_swap_strategy_edit():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    try:
        commands.edit(p.get('id'), p.get('fields') or {}, sid=session.get('user_sid', ''))
    except commands.CommandError as exc:
        return _erro(exc)
    return jsonify({'success': True})


@blueprint.route('/api/live-position-swap-strategy/delete', methods=['POST'])
def api_swap_strategy_delete():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    try:
        n = commands.delete(p.get('ids') or [])
    except commands.CommandError as exc:
        return _erro(exc)
    return jsonify({'success': True, 'deleted': n})
