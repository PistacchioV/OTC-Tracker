# -*- coding: utf-8 -*-
"""As quatro rotas do Conf. Matching."""
from flask import jsonify, redirect, render_template, request, session, url_for

from apps.pages import blueprint
from apps.pages.features.recon_conf_matching import commands, domain, queries


def _routes():
    from apps.pages import routes
    return routes


@blueprint.route('/reconciliation-conf-matching')
def reconciliation_conf_matching():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/reconciliation-conf-matching.html',
                           segment='reconciliation-conf-matching')


@blueprint.route('/api/reconciliation-conf-matching/data')
def api_conf_matching_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ref = (request.args.get('recon_date') or request.args.get('date') or '').strip()
    res = queries.load(ref)
    if not res:
        return jsonify(queries.empty_payload(ref))
    res['success'] = True
    return jsonify(res)


@blueprint.route('/reconciliation-conf-matching/run', methods=['POST'])
def api_conf_matching_run():
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ref = queries.parse_date(payload.get('recon_date') or payload.get('date'))
    try:
        res = commands.run(ref)
    except Exception as exc:                                # noqa: BLE001
        R.log.exception('[conf-matching] falha ao rodar o batimento')
        return jsonify({'success': False, 'error': domain.error_text(exc)}), 500
    res['success'] = True
    return jsonify(res)


@blueprint.route('/reconciliation-conf-matching/comment', methods=['POST'])
def api_conf_matching_comment():
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    key = str(payload.get('key', '') or '').strip()
    if not key:
        return jsonify({'success': False, 'error': 'missing_key'}), 400
    try:
        txt = commands.save_comment(key, payload.get('comment', ''))
    except Exception as exc:                                # noqa: BLE001
        R.log.exception('[conf-matching] falha ao gravar o comentário')
        return jsonify({'success': False, 'error': domain.error_text(exc)}), 500
    return jsonify({'success': True, 'comment': txt})
