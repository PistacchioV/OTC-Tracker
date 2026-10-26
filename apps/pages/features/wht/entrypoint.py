# -*- coding: utf-8 -*-
"""As rotas do WHT (Withholding Tax / Imposto)."""
from flask import Response, jsonify, redirect, render_template, request, session, url_for

from apps.pages import blueprint
from apps.pages.features.wht import commands, domain, queries


def _routes():
    from apps.pages import routes
    return routes


def _erro(exc, status=500):
    """Falha que a regra CONHECE vai com código + parâmetros (a tela diz no
    idioma de quem usa); o resto, como `tipo: mensagem` (§476)."""
    if isinstance(exc, domain.WhtError):
        return jsonify({'success': False, 'error': exc.text, 'error_code': exc.code,
                        'error_params': exc.params}), 400
    _routes().log.warning('[wht] falha:', exc_info=exc)
    return jsonify({'success': False, 'error': '%s: %s' % (type(exc).__name__, exc)}), status


@blueprint.route('/regulatory/wht')
def wht_page():
    """Regulatory › WHT — o item do menu existia desde o começo como placeholder."""
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    # A Reference date nasce no D-1 (dia útil ANBIMA): no dia do recolhimento o
    # que se confere é o decêndio que acabou de fechar.
    return render_template('pages/wht.html', segment='wht',
                           ref_date=queries.parse_ref(None).isoformat())


@blueprint.route('/api/wht/data')
def api_wht_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    try:
        ref = queries.parse_ref(request.args.get('date'))
        payload = queries.build(ref)
    except Exception as exc:                                # noqa: BLE001
        return _erro(exc)
    payload['success'] = True
    payload['import_job'] = commands.job_status(ref)
    return jsonify(payload)


@blueprint.route('/api/wht/import-settlements', methods=['POST'])
def api_wht_import_settlements():
    """Dispara o Import Settlements do decêndio em SEGUNDO PLANO e devolve o
    trabalho (`job`); a tela acompanha pelo `/api/wht/import-status`."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    ref = queries.parse_ref(p.get('date'))
    try:
        job = commands.start_import(ref, session.get('user_sid', ''))
    except Exception as exc:                                # noqa: BLE001
        return _erro(exc)
    return jsonify({'success': True, 'job': job, 'ref': ref.isoformat()})


@blueprint.route('/api/wht/import-status')
def api_wht_import_status():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({'success': True,
                    'job': commands.job_status(queries.parse_ref(request.args.get('date')))})


@blueprint.route('/api/wht/hub-import', methods=['POST'])
def api_wht_hub_import():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    files = [(f.filename, f.read()) for f in request.files.getlist('files') if f and f.filename]
    if not files:
        return jsonify({'success': False, 'error': 'No file', 'error_code': 'no_file',
                        'error_params': {}}), 400
    try:
        res = commands.import_hub(files, session.get('user_sid', ''))
        payload = queries.build(queries.parse_ref(request.form.get('date')))
    except Exception as exc:                                # noqa: BLE001
        return _erro(exc)
    payload.update({'success': True, 'hub': res})
    return jsonify(payload)


@blueprint.route('/api/wht/hub-file', methods=['POST'])
def api_wht_hub_file():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    try:
        nome, corpo, n = commands.hub_file(queries.parse_ref(p.get('date')), p.get('keys') or None)
    except Exception as exc:                                # noqa: BLE001
        return _erro(exc)
    return Response(corpo, mimetype='text/plain; charset=windows-1252',
                    headers={'Content-Disposition': 'attachment; filename="%s"' % nome,
                             'X-WHT-Count': str(n), 'X-WHT-Name': nome})
