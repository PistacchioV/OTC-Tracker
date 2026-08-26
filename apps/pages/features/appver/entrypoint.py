# -*- coding: utf-8 -*-
"""As duas rotas do card New Version Released."""
import traceback

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.appver import commands, queries


def _routes():
    from apps.pages import routes
    return routes


@blueprint.route('/api/control-panel/app-version/recipients', methods=['GET', 'POST'])
def api_cp_app_version_recipients():
    """GET → a versão lida agora, quantos usuários ativos receberiam, o Cc e o
    desfecho do último envio; POST → grava o Cc.

    A versão e a CONTAGEM voltam no GET de propósito: são as duas coisas que
    alguém precisa conferir ANTES de mandar um e-mail para a mesa inteira."""
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if request.method == 'POST':
        try:
            commands.save_recipients(request.get_json(silent=True) or {})
        except Exception as e:                              # noqa: BLE001
            R.log.error('[app-version] save recipients failed:\n%s', traceback.format_exc())
            return jsonify({'success': False,
                            'error': '{}: {}'.format(type(e).__name__, e)}), 500
        return jsonify({'success': True})
    versao, bruto, erro = queries.read_link()
    try:
        ativos = len(queries.active_users())
    except Exception:                                       # noqa: BLE001
        # Banco indisponível não pode derrubar o card: o Cc ainda precisa ser
        # editável, e a linha de status é quem diz que a contagem falhou.
        R.log.warning('[app-version] não consegui contar os usuários:\n%s', traceback.format_exc())
        ativos = None
    return jsonify({'success': True, **queries.recipients(),
                    'version': versao, 'version_error': erro,
                    # O conteúdo lido vai junto, cortado: é como se confere que
                    # o `link.txt` aponta para a versão que se quer anunciar.
                    'link_preview': bruto[:200],
                    'path': queries.link_path(),
                    'active_users': ativos,
                    'last': queries.status()})


@blueprint.route('/api/control-panel/app-version/run', methods=['POST'])
def api_cp_app_version_run():
    """Manda o aviso AGORA para todo usuário ativo (botão do card)."""
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    try:
        out = commands.run_manual(request.get_json(silent=True) or {})
    except Exception as e:                                  # noqa: BLE001
        R.log.error('[app-version] run manual falhou:\n%s', traceback.format_exc())
        return jsonify({'success': False,
                        'error': '{}: {}'.format(type(e).__name__, e)}), 500
    if not out['sent'] and out.get('reason') == 'no_version':
        # 400 e não 500: o pedido está bem formado, o que falta é o arquivo
        # dizer qual versão foi publicada. E o e-mail NÃO sai sem ela — um aviso
        # de "nova versão" sem o número não diz nada a quem recebe.
        return jsonify({'success': False,
                        'error': 'Could not read the version from {}{}.'.format(
                            out.get('path') or 'link.txt',
                            ' — ' + out['error'] if out.get('error') else '')}), 400
    if not out['sent'] and out.get('reason') == 'no_recipient':
        return jsonify({'success': False,
                        'error': 'No user with status Active in Users & Roles — '
                                 'there is nobody to notify.'}), 400
    if not out['sent']:
        return jsonify({'success': False, 'error': out.get('error') or 'unknown'}), 500
    R._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                           'New Version Announced', 'Control Panel',
                           '{} → {} active user(s)'.format(out['version'], out['to']))
    return jsonify({'success': True, **out,
                    'message': 'Version {} announced to {} active user(s){}.'.format(
                        out['version'], out['to'],
                        ' (+{} in copy)'.format(out['cc']) if out['cc'] else '')})
