# -*- coding: utf-8 -*-
"""As duas rotas do card MT300."""
import traceback

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.mt300 import commands, domain, queries

# O routes.py registra o scheduler no bloco de wiring com este nome — a
# superfície pública da feature é o entrypoint.
start_scheduler = commands.start_scheduler


def _routes():
    from apps.pages import routes
    return routes


@blueprint.route('/api/control-panel/mt300/recipients', methods=['GET', 'POST'])
def api_cp_mt300_recipients():
    """GET → TO/Cc, o desfecho do último disparo e quantas operações o e-mail
    teria AGORA; POST → grava as listas."""
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if request.method == 'POST':
        try:
            commands.save_recipients(request.get_json(silent=True) or {})
        except Exception as e:                              # noqa: BLE001
            R.log.error('[mt300] save recipients failed:\n%s', traceback.format_exc())
            return jsonify({'success': False,
                            'error': '{}: {}'.format(type(e).__name__, e)}), 500
        return jsonify({'success': True})
    try:
        n = len(queries.rows(R._br_now()))
    except Exception:                                       # noqa: BLE001
        # Um arquivo-dia ilegível não pode derrubar o card: as listas de
        # destinatário ainda precisam ser editáveis.
        R.log.warning('[mt300] não consegui contar as operações:\n%s', traceback.format_exc())
        n = None
    return jsonify({'success': True, **queries.recipients(),
                    'rows': n, 'last': queries.status(),
                    'time': '{:02d}:{:02d}'.format(*domain.TIME)})


@blueprint.route('/api/control-panel/mt300/run', methods=['POST'])
def api_cp_mt300_run():
    """Manda o e-mail AGORA (botão Run do card). Roda mesmo em feriado — quem
    clicou decidiu; o resto da regra está no `commands.run_manual`."""
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    try:
        out = commands.run_manual(request.get_json(silent=True) or {})
    except Exception as e:                                  # noqa: BLE001
        R.log.error('[mt300] run manual falhou:\n%s', traceback.format_exc())
        return jsonify({'success': False,
                        'error': '{}: {}'.format(type(e).__name__, e)}), 500
    if not out['sent'] and out.get('reason') == 'empty':
        return jsonify({'success': True, **out,
                        'message': 'No MT300 trade for the registered counterparties '
                                   'today — e-mail not sent.'})
    if not out['sent'] and out.get('reason') == 'no_recipient':
        return jsonify({'success': False,
                        'error': 'No TO recipient saved for this card — fill the TO field '
                                 'and save before running.'}), 400
    if not out['sent']:
        return jsonify({'success': False, 'error': out.get('error') or 'unknown'}), 500
    R._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                           'MT300 Sent', 'Control Panel',
                           '{} trade(s) → {} recipient(s)'.format(out['rows'], out['to']))
    return jsonify({'success': True, **out,
                    'message': '{} trade(s) sent to {} recipient(s){}.'.format(
                        out['rows'], out['to'],
                        ' (+{} in copy)'.format(out['cc']) if out['cc'] else '')})
