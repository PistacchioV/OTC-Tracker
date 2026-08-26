# -*- coding: utf-8 -*-
"""As duas rotas do card Confirmations Escalation."""
import traceback

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.conf_escalation import commands, domain, queries

# O routes.py registra o scheduler no bloco de wiring com este nome.
start_scheduler = commands.start_scheduler


def _routes():
    from apps.pages import routes
    return routes


@blueprint.route('/api/control-panel/confirmations-escalation/recipients',
                 methods=['GET', 'POST'])
def api_cp_conf_escalation_recipients():
    """GET → as três listas + o retrato da fila e o desfecho dos disparos;
    POST → grava as listas."""
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if request.method == 'POST':
        try:
            commands.save_recipients(request.get_json(silent=True) or {})
        except Exception as e:                              # noqa: BLE001
            R.log.error('[conf-escalation] save recipients failed:\n%s',
                        traceback.format_exc())
            return jsonify({'success': False,
                            'error': '{}: {}'.format(type(e).__name__, e)}), 500
        return jsonify({'success': True})
    try:
        otc, mo, grupos, esc, sem_grupo = queries.snapshot()
        counts = {'otc': len(otc), 'mo': len(mo), 'escalation': len(esc),
                  'fo': [{'id': g['id'], 'label': g['label'], 'count': len(g['rows'])}
                         for g in grupos],
                  'unmatched': sem_grupo}
    except Exception:                                       # noqa: BLE001
        # A esteira fora do ar não pode derrubar o card: as listas de
        # destinatários ainda precisam ser editáveis.
        R.log.warning('[conf-escalation] não consegui ler a esteira:\n%s',
                      traceback.format_exc())
        counts = {}
    now = R._br_now()
    return jsonify({'success': True, **queries.recipients(),
                    'counts': counts, 'last': queries.status(),
                    'next': queries.next_runs(now),
                    'now_br': now.strftime('%d/%m/%Y %H:%M'),
                    'time': '{:02d}:{:02d}'.format(*queries.send_time())})


@blueprint.route('/api/control-panel/confirmations-escalation/run', methods=['POST'])
def api_cp_conf_escalation_run():
    """Dispara agora, sem esperar o horário — `mode` em `domain.MODES`: o pacote
    da rotina, a escalação, ou UM e-mail só (o Run individual de cada item).
    O resto da regra está no `commands.run_manual`."""
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    mode = str((request.get_json(silent=True) or {}).get('mode') or 'routine').strip()
    if mode not in domain.MODES:
        mode = 'routine'
    try:
        out = commands.run_manual(mode)
    except Exception as e:                                  # noqa: BLE001
        R.log.error('[conf-escalation] run manual falhou:\n%s', traceback.format_exc())
        return jsonify({'success': False,
                        'error': '{}: {}'.format(type(e).__name__, e)}), 500
    if out['sent']:
        R._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                               'Confirmations Escalation Sent', 'Control Panel',
                               '{} e-mail(s) sent — {} confirmation(s)'.format(
                                   len(out['sent']), sum(s['rows'] for s in out['sent'])))
    return jsonify({'success': True, 'mode': mode, **out})
