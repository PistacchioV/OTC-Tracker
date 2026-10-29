# -*- coding: utf-8 -*-
"""RED Clients — Rapid Exposure: as rotas (§730).

O card do Control Panel manda a planilha (`run`) e lê a última rodada
(`status`); as telas de liquidação perguntam quem está marcado (`list`).
"""
from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.red_clients import commands, queries
from apps.pages.features.red_clients.infra import persistence


def _R():
    from apps.pages import routes
    return routes


@blueprint.route('/api/control-panel/red-clients/run', methods=['POST'])
def api_red_clients_run():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'code': 'red_no_file', 'error': 'No file uploaded.'}), 400
    try:
        resumo = commands.run(f.filename, f.read(), session.get('user_sid', ''),
                              session.get('user_name', ''))
    except persistence.PlanilhaInvalida as exc:
        return jsonify({'success': False, 'code': exc.code, 'params': exc.params,
                        'error': exc.code}), 400
    msg = '{} RED client(s) · {} entered · {} left · {} ECI(s) without a Reference Data match'.format(
        len(resumo['red']), len(resumo['entered']), len(resumo['left']), resumo['eci_unmatched'])
    return jsonify({'success': True, 'message': msg, 'summary': resumo})


@blueprint.route('/api/control-panel/red-clients/status')
def api_red_clients_status():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({'success': True, 'last': queries.status()})


@blueprint.route('/api/red-clients')
def api_red_clients_list():
    """Quem está RED agora — para a pílula das telas de liquidação e o aviso
    antes de gerar o aviso de liquidação."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({'success': True, 'clients': queries.flagged()})
