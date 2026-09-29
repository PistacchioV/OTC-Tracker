# -*- coding: utf-8 -*-
"""As rotas do Pending Confirmation › Dashboard."""
import json

from flask import jsonify, redirect, render_template, request, session, url_for

from apps.pages import blueprint
from apps.pages.features.pc_dashboard import queries


@blueprint.route('/dashboard-pending-confirmation')
def dashboard_pending_confirmation():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/dashboard-pending-confirmation.html',
                           segment='dashboard-pending-confirmation')


@blueprint.route('/api/dashboard-pending-confirmation/data')
def api_pc_dashboard_data():
    """A tabela dinâmica. `bands` é a lista JSON das faixas escolhidas; sem o
    parâmetro vêm todas (lista vazia é "nenhuma", e a tabela vem vazia)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    selected = None
    raw = request.args.get('bands')
    if raw is not None:
        try:
            selected = [str(b) for b in json.loads(raw)]
        except (ValueError, TypeError):
            return jsonify({'success': False, 'code': 'bad_bands',
                            'error': 'bands must be a JSON list'}), 400
    return jsonify({'success': True, **queries.data(selected)})
