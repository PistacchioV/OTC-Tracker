# -*- coding: utf-8 -*-
"""As quatro rotas da Recon de FXO.

Sessão, data, o encaminhamento dos arquivos do upload manual e o código de
status. O batimento é do `recon_fxo.py`; o que se decide aqui é o que a falha
vira na tela.
"""
from datetime import datetime

from flask import (jsonify, redirect, render_template, request, session,
                   url_for)

from apps.pages import blueprint
from apps.pages.features.reconciliation_fxo import commands, queries


def _log():
    """Ver a nota em `features/support/infra/persistence.py`: busca ATRASADA."""
    from apps.pages import routes
    return routes.log


@blueprint.route('/reconciliation-fxo')
def reconciliation_fxo():
    if not session.get('authenticated'):
        # A PÁGINA redireciona; as APIs abaixo respondem JSON. É de propósito:
        # um `<a>` que devolve 401 deixa a tela em branco.
        return redirect(url_for('pages_blueprint.sign_in_page'))
    from apps.pages import routes
    # D-1 no calendário ANBIMA: a posição da B3 e o EOD da Athena são do
    # fechamento anterior. Abrir em "hoje" mandaria todo mundo procurar um
    # arquivo que ainda não existe — e numa segunda-feira, ou no dia seguinte a
    # um feriado, "ontem" no calendário civil não é dia útil nenhum.
    return render_template(
        'pages/reconciliation-fxo.html', segment='reconciliation-fxo',
        ref_date=routes._prev_anbima_bizday(datetime.now()).strftime('%Y-%m-%d'))


@blueprint.route('/reconciliation-fxo/data')
def reconciliation_fxo_data():
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        return jsonify(queries.last(request.args.get('recon_date', '')))
    except Exception as e:                                    # noqa: BLE001
        _log().error('[recon_fxo_data] %s', e)
        return jsonify({'error': str(e)}), 500


@blueprint.route('/reconciliation-fxo/run', methods=['POST'])
def reconciliation_fxo_run():
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    mode = request.form.get('mode', 'auto')
    recon_date = request.form.get('recon_date', '')
    try:
        files = request.files.getlist('files') if mode == 'manual' else None
        result = commands.run(recon_date, files, mode)
        if result.get('success'):
            from apps.pages import routes
            routes._create_notification(
                session.get('user_sid', ''), session.get('user_name', ''),
                commands.NOTIF_ACTION, commands.NOTIF_PAGE,
                result.get('meta', '') + (' (' + recon_date + ')' if recon_date else ''))
        return jsonify(result)
    except FileNotFoundError as e:
        # O arquivo de posição do dia ainda não chegou na rede. Não é erro de
        # código: a tela oferece o upload manual em vez de mostrar um stack, e
        # por isso a resposta é 200 com `not_found`, e não um 500.
        _log().warning('[recon_fxo_run] arquivo não encontrado: %s', e)
        return jsonify({'not_found': True, 'detail': str(e)})
    except Exception as e:                                    # noqa: BLE001
        _log().error('[recon_fxo_run] %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


@blueprint.route('/reconciliation-fxo/comment', methods=['POST'])
def reconciliation_fxo_comment():
    """Grava (ou apaga) a justificativa de uma operação."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    payload = request.get_json(silent=True) or {}
    key = str(payload.get('key', '') or '').strip()
    if not key:
        return jsonify({'success': False,
                        'error': 'Sem a chave da operação não há o que comentar.'}), 400
    try:
        out = commands.save_comment(
            key,
            str(payload.get('comment', '') or '').strip(),
            str(payload.get('status', '') or ''),
            str(payload.get('status_raw', '') or ''))
        return jsonify({'success': True, **out})
    except Exception as e:                                    # noqa: BLE001
        _log().error('[recon_fxo_comment] %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500
