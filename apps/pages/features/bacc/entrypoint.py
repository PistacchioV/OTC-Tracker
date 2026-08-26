# -*- coding: utf-8 -*-
"""As duas rotas do card BACC EA Metrics."""
import traceback

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.bacc import commands, queries

# O routes.py registra o scheduler no bloco de wiring com este nome — a
# superfície pública da feature é o entrypoint.
start_scheduler = commands.start_scheduler


def _routes():
    from apps.pages import routes
    return routes


@blueprint.route('/api/control-panel/bacc-ea-metrics/recipients',
                 methods=['GET', 'POST'])
def api_cp_bacc_recipients():
    """GET → as duas listas, o desfecho do último disparo e quantas linhas o
    anexo teria agora; POST → grava as listas."""
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if request.method == 'POST':
        try:
            commands.save_recipients(request.get_json(silent=True) or {})
        except Exception as e:                              # noqa: BLE001
            R.log.error('[bacc-ea] save recipients failed:\n%s', traceback.format_exc())
            return jsonify({'success': False,
                            'error': '{}: {}'.format(type(e).__name__, e)}), 500
        return jsonify({'success': True})
    try:
        n = len(queries.rows())
    except Exception:                                       # noqa: BLE001
        # A esteira fora do ar não pode derrubar o card: as listas de
        # destinatários ainda precisam ser editáveis.
        R.log.warning('[bacc-ea] não consegui ler a esteira:\n%s', traceback.format_exc())
        n = None
    return jsonify({'success': True, **queries.recipients(),
                    'rows': n, 'last': queries.status(),
                    'time': '{:02d}:{:02d}'.format(*queries.send_time())})


@blueprint.route('/api/control-panel/bacc-ea-metrics/run', methods=['POST'])
def api_cp_bacc_run():
    """Manda o e-mail AGORA (botão Run do card). Roda mesmo em feriado — quem
    clicou decidiu; o resto da regra está no `commands.run_manual`."""
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    try:
        out = commands.run_manual()
    except Exception as e:                                  # noqa: BLE001
        R.log.error('[bacc-ea] run manual falhou:\n%s', traceback.format_exc())
        return jsonify({'success': False,
                        'error': '{}: {}'.format(type(e).__name__, e)}), 500
    if not out['sent'] and out.get('reason') == 'no_recipient':
        return jsonify({'success': False,
                        'error': 'No TO recipient saved for this card — fill the TO field '
                                 'and save before running.'}), 400
    if not out['sent']:
        return jsonify({'success': False, 'error': out.get('error') or 'unknown'}), 500
    R._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                           'BACC EA Metrics Sent', 'Control Panel',
                           '{} operation(s) → {} recipient(s)'.format(out['rows'], out['to']))
    return jsonify({'success': True, **out,
                    'message': '{} operation(s) sent to {} recipient(s){}.'.format(
                        out['rows'], out['to'],
                        ' (+{} in copy)'.format(out['cc']) if out['cc'] else '')})
