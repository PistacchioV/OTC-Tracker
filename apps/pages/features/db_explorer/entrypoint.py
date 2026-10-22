# -*- coding: utf-8 -*-
"""As rotas do Database Explorer — só o MASTER (`_MASTER_SIDS`).

A página e toda a API conferem o master no servidor: o item do menu só
aparece para ele, mas um `Page_Access` vazio é acesso total (§5), e sem a
conferência aqui qualquer usuário sem allowlist abriria a tela pelo endereço.
"""
import logging

from flask import jsonify, redirect, render_template, request, session, url_for

from apps.pages import blueprint
from apps.pages.features.db_explorer import commands, domain, queries

log = logging.getLogger('otc_tracker')


def _R():
    from apps.pages import routes
    return routes


def _negado():
    """A resposta da API para quem não pode, ou None."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if not _R()._session_is_master():
        e = domain.ExplorerError('master_only', 'Only the master can use the Database Explorer', 403)
        return jsonify(e.payload()), 403
    return None


def _erro(e):
    return jsonify(e.payload()), e.status


@blueprint.route('/database-explorer')
def database_explorer():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    if not _R()._session_is_master():
        return redirect(url_for('pages_blueprint.dashboard'))
    return render_template('pages/database-explorer.html', segment='database-explorer',
                           dbx_limits=domain.LIMITS, dbx_default_limit=domain.DEFAULT_LIMIT)


@blueprint.route('/api/database-explorer/databases')
def api_dbx_databases():
    negado = _negado()
    if negado:
        return negado
    fresh = request.args.get('fresh') == '1'
    return jsonify({'success': True, 'databases': queries.databases(fresh=fresh)})


@blueprint.route('/api/database-explorer/tables')
def api_dbx_tables():
    negado = _negado()
    if negado:
        return negado
    try:
        return jsonify({'success': True, **queries.tables(request.args.get('db'))})
    except domain.ExplorerError as e:
        return _erro(e)


@blueprint.route('/api/database-explorer/rows', methods=['POST'])
def api_dbx_rows():
    negado = _negado()
    if negado:
        return negado
    p = request.get_json(silent=True) or {}
    try:
        out = queries.rows(p.get('db'), str(p.get('schema') or ''), str(p.get('table') or ''), p.get('limit'))
        return jsonify({'success': True, **out})
    except domain.ExplorerError as e:
        return _erro(e)


def _audita(acao, p, n, extra=''):
    # WARNING de propósito: é o nível que sai no log da instância (§9), e
    # gravar direto num banco por fora das telas tem de deixar rastro.
    log.warning('[db-explorer] %s %s %d row(s) in %s %s.%s%s', session.get('user_sid'), acao, n,
                p.get('db'), p.get('schema'), p.get('table'), extra)


@blueprint.route('/api/database-explorer/update', methods=['POST'])
def api_dbx_update():
    negado = _negado()
    if negado:
        return negado
    p = request.get_json(silent=True) or {}
    values = p.get('values')
    try:
        n = commands.update_rows(p.get('db'), str(p.get('schema') or ''), str(p.get('table') or ''),
                                 p.get('items'), values)
    except domain.ExplorerError as e:
        return _erro(e)
    _audita('updated', p, n, ' (columns: %s)' % ', '.join(sorted(values)))
    return jsonify({'success': True, 'updated': n})


@blueprint.route('/api/database-explorer/delete', methods=['POST'])
def api_dbx_delete():
    negado = _negado()
    if negado:
        return negado
    p = request.get_json(silent=True) or {}
    try:
        n = commands.delete_rows(p.get('db'), str(p.get('schema') or ''), str(p.get('table') or ''),
                                 p.get('items'))
    except domain.ExplorerError as e:
        return _erro(e)
    _audita('deleted', p, n)
    return jsonify({'success': True, 'deleted': n})
