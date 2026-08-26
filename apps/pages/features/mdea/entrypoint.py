# -*- coding: utf-8 -*-
"""As duas rotas do card Manual Deals EA."""
import traceback

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.mdea import commands, domain, queries

# A superfície pública da feature: o wiring do routes registra o scheduler, e o
# pull do NDF grava os pares de re-booking por aqui.
start_scheduler = commands.start_scheduler
record_rebooks = commands.record_rebooks


def _routes():
    from apps.pages import routes
    return routes


@blueprint.route('/api/control-panel/manual-deals-ea/recipients', methods=['GET', 'POST'])
def api_cp_mdea_recipients():
    """GET → TO/Cc, o desfecho do último disparo de cada rotina e quantas linhas
    cada e-mail teria AGORA; POST → grava as listas."""
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if request.method == 'POST':
        try:
            commands.save_recipients(request.get_json(silent=True) or {})
        except Exception as e:                              # noqa: BLE001
            R.log.error('[manual-deals-ea] save recipients failed:\n%s', traceback.format_exc())
            return jsonify({'success': False,
                            'error': '{}: {}'.format(type(e).__name__, e)}), 500
        return jsonify({'success': True})
    counts = {}
    for kind in domain.KINDS:
        try:
            counts[kind] = len(queries.rows(kind, R._br_now()))
        except Exception:                                   # noqa: BLE001
            # Um arquivo-dia ilegível não pode derrubar o card: as listas de
            # destinatários ainda precisam ser editáveis.
            R.log.warning('[manual-deals-ea] não consegui contar %s:\n%s',
                          kind, traceback.format_exc())
            counts[kind] = None
    return jsonify({'success': True, **queries.recipients(),
                    'counts': counts, 'last': queries.status(),
                    'times': {k: '{:02d}:{:02d}'.format(*domain.TIME[k]) for k in domain.KINDS}})


@blueprint.route('/api/control-panel/manual-deals-ea/run', methods=['POST'])
def api_cp_mdea_run():
    """Manda o e-mail de UMA rotina agora (os dois botões Run do card). Roda
    mesmo em feriado — quem clicou decidiu; o resto está no `run_manual`."""
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    kind = str(payload.get('kind', '') or '').strip()
    if kind not in domain.KINDS:
        return jsonify({'success': False, 'error': 'Unknown routine.'}), 400
    try:
        out = commands.run_manual(kind, payload)
    except Exception as e:                                  # noqa: BLE001
        R.log.error('[manual-deals-ea] run manual falhou:\n%s', traceback.format_exc())
        return jsonify({'success': False,
                        'error': '{}: {}'.format(type(e).__name__, e)}), 500
    if not out['sent'] and out.get('reason') == 'empty':
        return jsonify({'success': True, **out,
                        'message': 'No {} deal to report for today — e-mail not sent.'
                                   .format(domain.LABEL[kind])})
    if not out['sent'] and out.get('reason') == 'no_recipient':
        return jsonify({'success': False,
                        'error': 'No TO recipient saved for this card — fill the TO field '
                                 'and save before running.'}), 400
    if not out['sent']:
        return jsonify({'success': False, 'error': out.get('error') or 'unknown'}), 500
    R._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                           'Manual Deals EA Sent', 'Control Panel',
                           '{} — {} deal(s) → {} recipient(s)'.format(
                               domain.LABEL[kind], out['rows'], out['to']))
    return jsonify({'success': True, **out,
                    'message': '{} — {} deal(s) sent to {} recipient(s){}.'.format(
                        domain.LABEL[kind], out['rows'], out['to'],
                        ' (+{} in copy)'.format(out['cc']) if out['cc'] else '')})
