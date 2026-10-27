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
                           ref_date=queries.parse_ref(None).isoformat(),
                           # as colunas que o Edit e o lote corrigem (§702): uma fonte
                           edit_cols={k: list(v) for k, v in domain.EDIT_COLS.items()},
                           hub_only_cols={k: list(v) for k, v in domain.HUB_ONLY_COLS.items()},
                           edit_selects={k: list(v) for k, v in domain.EDIT_SELECTS.items()})


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


# ── Edit, Confirm e Delete da tabela (§702) ─────────────────────────────────
def _acao(fn, action, status_ok=200):
    """Roda a escrita, avisa no sino e devolve a página redesenhada."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    ref = queries.parse_ref(p.get('date'))
    try:
        n = fn(ref, p.get('items') or [], session.get('user_sid', ''), session.get('user_name', ''))
        payload = queries.build(ref)
    except domain.WhtError as exc:
        st = 403 if exc.code == 'approve_own' else (409 if exc.code == 'edit_row_gone' else 400)
        return jsonify({'success': False, 'error': exc.text, 'error_code': exc.code,
                        'error_params': exc.params}), st
    except Exception as exc:                                # noqa: BLE001
        return _erro(exc)
    try:
        _routes()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                       action, 'WHT', '%d row(s) · %s' % (n, ref.isoformat()))
    except Exception:                                       # noqa: BLE001
        _routes().log.warning('[wht] sino de %s não saiu', action, exc_info=True)
    payload.update({'success': True, 'count': n})
    return jsonify(payload), status_ok


@blueprint.route('/api/wht/edit', methods=['POST'])
def api_wht_edit():
    return _acao(commands.edit, 'Deal Updated')


@blueprint.route('/api/wht/approve', methods=['POST'])
def api_wht_approve():
    return _acao(commands.approve, 'Status Updated')


@blueprint.route('/api/wht/delete', methods=['POST'])
def api_wht_delete():
    return _acao(commands.delete, 'Deal Deleted')


@blueprint.route('/api/wht/add', methods=['POST'])
def api_wht_add():
    return _acao(commands.add, 'New Item')


@blueprint.route('/api/wht/derive', methods=['POST'])
def api_wht_derive():
    """O código, o tributo e o IR da operação que o Add Row está montando —
    a tela preenche os campos enquanto se digita (§702)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    f = (request.get_json(silent=True) or {}).get('fields') or {}
    m = {'Product': 'product', 'LOB': 'lob', 'Event': 'event', 'OTC_GV': 'gross',
         'OTC_cntpy': 'counterparty', 'OTC_taxid': 'taxid', 'OTC_TD': 'trade_date', 'OTC_ET': 'day',
         'OTC_LE': 'le', 'Internal ID': 'internal_id', 'B3 Id': 'b3_id'}
    dados = {k: f.get(c) for c, k in m.items()}
    for k in ('trade_date', 'day'):
        d = domain.parse_date(dados.get(k))
        dados[k] = d.isoformat() if d else ''
    try:
        return jsonify({'success': True, **queries.derive(dados)})
    except domain.WhtError as exc:
        return jsonify({'success': False, 'error': exc.text, 'error_code': exc.code,
                        'error_params': exc.params}), 400
