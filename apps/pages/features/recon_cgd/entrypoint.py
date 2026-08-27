# -*- coding: utf-8 -*-
"""As cinco rotas da Recon de CGD."""
from flask import jsonify, render_template, request, session

from apps.pages import blueprint, recon_cgd as motor
from apps.pages.features.recon_cgd import commands, queries


def _routes():
    from apps.pages import routes
    return routes


@blueprint.route('/reconciliation-cgd')
def reconciliation_cgd():
    return render_template('pages/reconciliation-cgd.html', segment='reconciliation-cgd')


@blueprint.route('/api/reconciliation-cgd/data')
def api_cgd_recon_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ref = (request.args.get('recon_date') or request.args.get('date') or '').strip()
    res = queries.load(ref)
    if not res:
        # Sem cache a tela abre VAZIA dizendo que ninguém rodou aquele dia — e
        # não rodando sozinha: um GET que varre o share é um GET que trava.
        return jsonify(queries.empty_payload(ref))
    res['success'] = True
    res['recipients'] = queries.recipients()
    return jsonify(res)


@blueprint.route('/reconciliation-cgd/run', methods=['POST'])
def api_cgd_recon_run():
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ref = motor._parse_date(payload.get('recon_date') or payload.get('date'))
    try:
        res = commands.run(ref)
    except Exception as exc:                                # noqa: BLE001
        R.log.exception('[recon-cgd] falha ao rodar o batimento')
        return jsonify({'success': False, 'error': str(exc)}), 500
    res['success'] = True
    res['recipients'] = queries.recipients()
    return jsonify(res)


@blueprint.route('/api/reconciliation-cgd/recipients', methods=['GET', 'POST'])
def api_cgd_recon_recipients():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if request.method == 'GET':
        return jsonify({'success': True, **queries.recipients()})
    d = request.get_json(silent=True) or {}
    commands.save_recipients(d.get('to', ''), d.get('cc', ''))
    return jsonify({'success': True})


@blueprint.route('/reconciliation-cgd/email', methods=['POST'])
def api_cgd_recon_email():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ref = (payload.get('recon_date') or payload.get('date') or '').strip()
    res = queries.load(ref)
    if not res:
        # Mandar um relatório que ninguém rodou seria mandar o de outro dia.
        return jsonify({'success': False, 'error': 'not_run'}), 409
    ok, motivo, rec = commands.send_email(res)
    if not ok:
        return jsonify({'success': False, 'error': motivo}), 200
    return jsonify({'success': True, 'to': rec['to'], 'cc': rec['cc']})
