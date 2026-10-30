# -*- coding: utf-8 -*-
"""As rotas da E-Financeira (Regulatory › E-financeira › KAPITAL, ATHENA-NDF,
ATHENA-FXO e PYRAMID): uma tela, quatro páginas — o sistema de origem é o
parâmetro."""
from flask import Response, abort, jsonify, redirect, render_template, request, session, url_for

from apps.pages import blueprint
from apps.pages.features.efinanceira import commands, domain, queries


def _routes():
    from apps.pages import routes
    return routes


def _erro(exc, status=500):
    """Falha que a regra CONHECE vai com código + parâmetros (a tela diz no
    idioma de quem usa); o resto, como `tipo: mensagem` (§476)."""
    if isinstance(exc, domain.EfinError):
        st = 403 if exc.code == 'approve_own' else (409 if exc.code == 'edit_row_gone' else 400)
        return jsonify({'success': False, 'error': exc.text, 'error_code': exc.code,
                        'error_params': exc.params}), st
    _routes().log.warning('[efin] falha:', exc_info=exc)
    return jsonify({'success': False, 'error': '%s: %s' % (type(exc).__name__, exc)}), status


def _sem_sessao():
    return jsonify({'success': False, 'error': 'Not authenticated'}), 401


@blueprint.route('/regulatory/e-financeira/<page>')
def efinanceira_page(page):
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    if page not in domain.PAGES:
        abort(404)
    return render_template('pages/efinanceira.html', segment='efinanceira',
                           page=page, page_label=domain.PAGES[page]['label'],
                           ref_date=queries.parse_ref(None).isoformat(),
                           edit_cols={k: list(v) for k, v in domain.EDIT_COLS.items()},
                           edit_selects={k: list(v) for k, v in domain.SELECTS.items()},
                           add_required=list(domain.ADD_REQUIRED))


@blueprint.route('/api/efinanceira/<page>/data')
def api_efinanceira_data(page):
    if not session.get('authenticated'):
        return _sem_sessao()
    if page not in domain.PAGES:
        abort(404)
    try:
        ref = queries.parse_ref(request.args.get('date'))
        payload = queries.build(page, ref)
    except Exception as exc:                                # noqa: BLE001
        return _erro(exc)
    payload['success'] = True
    payload['import_job'] = commands.job_status(ref)
    return jsonify(payload)


@blueprint.route('/api/efinanceira/import-settlements', methods=['POST'])
def api_efinanceira_import():
    """Dispara o Import Settlements do MÊS em segundo plano (as quatro páginas
    de uma vez) e devolve o trabalho; a tela acompanha pelo `import-status`."""
    if not session.get('authenticated'):
        return _sem_sessao()
    ref = queries.parse_ref((request.get_json(silent=True) or {}).get('date'))
    try:
        job = commands.start_import(ref, session.get('user_sid', ''))
    except Exception as exc:                                # noqa: BLE001
        return _erro(exc)
    return jsonify({'success': True, 'job': job, 'ref': ref.isoformat()})


@blueprint.route('/api/efinanceira/import-status')
def api_efinanceira_import_status():
    if not session.get('authenticated'):
        return _sem_sessao()
    return jsonify({'success': True,
                    'job': commands.job_status(queries.parse_ref(request.args.get('date')))})


@blueprint.route('/api/efinanceira/<page>/generate', methods=['POST'])
def api_efinanceira_generate(page):
    """O arquivo do mês da página: gravado no share e devolvido para download."""
    if not session.get('authenticated'):
        return _sem_sessao()
    if page not in domain.PAGES:
        abort(404)
    ref = queries.parse_ref((request.get_json(silent=True) or {}).get('date'))
    try:
        nome, corpo, n, caminho = commands.generate(page, ref, session.get('user_sid', ''))
    except Exception as exc:                                # noqa: BLE001
        return _erro(exc)
    try:
        _routes()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                       'File Generated', domain.PAGES[page]['notif'],
                                       '%s · %d row(s)' % (nome, n))
    except Exception:                                       # noqa: BLE001
        _routes().log.warning('[efin] sino do arquivo não saiu', exc_info=True)
    return Response(corpo, mimetype='text/csv; charset=windows-1252',
                    headers={'Content-Disposition': 'attachment; filename="%s"' % nome,
                             'X-EFIN-Count': str(n), 'X-EFIN-Name': nome, 'X-EFIN-Path': caminho})


# ── Edit, Confirm, Delete e Add Row ─────────────────────────────────────────
def _acao(page, fn, action):
    """Roda a escrita, avisa no sino e devolve a página redesenhada."""
    if not session.get('authenticated'):
        return _sem_sessao()
    if page not in domain.PAGES:
        abort(404)
    p = request.get_json(silent=True) or {}
    ref = queries.parse_ref(p.get('date'))
    try:
        n = fn(ref, p.get('items') or [], session.get('user_sid', ''), session.get('user_name', ''))
        payload = queries.build(page, ref)
    except Exception as exc:                                # noqa: BLE001
        return _erro(exc)
    try:
        _routes()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                       action, domain.PAGES[page]['notif'],
                                       '%d row(s) · %s' % (n, domain.month_key(ref)))
    except Exception:                                       # noqa: BLE001
        _routes().log.warning('[efin] sino de %s não saiu', action, exc_info=True)
    payload.update({'success': True, 'count': n})
    return jsonify(payload)


@blueprint.route('/api/efinanceira/<page>/edit', methods=['POST'])
def api_efinanceira_edit(page):
    return _acao(page, commands.edit, 'Deal Updated')


@blueprint.route('/api/efinanceira/<page>/approve', methods=['POST'])
def api_efinanceira_approve(page):
    return _acao(page, commands.approve, 'Status Updated')


@blueprint.route('/api/efinanceira/<page>/delete', methods=['POST'])
def api_efinanceira_delete(page):
    return _acao(page, commands.delete, 'Deal Deleted')


@blueprint.route('/api/efinanceira/<page>/add', methods=['POST'])
def api_efinanceira_add(page):
    return _acao(page, commands.add, 'New Item')
