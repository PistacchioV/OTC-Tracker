# -*- coding: utf-8 -*-
"""As três rotas do New Deals Monitor (página + card de pendências)."""
import traceback
from datetime import datetime

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.deals_monitor import engine

# O wiring do routes registra o scheduler com este nome.
start_scheduler = None  # preenchido abaixo do import do engine
start_scheduler = engine._ndm_pending_start_scheduler


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/api/new-deals/monitor')
def api_new_deals_monitor():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    cards, conf_cards = engine._ndm_monitor_snapshot(ref)
    return jsonify({'success': True, 'date': ref.strftime('%Y-%m-%d'),
                    'cards': cards, 'conf_cards': conf_cards})

@blueprint.route('/api/control-panel/deals-monitor/recipients', methods=['GET', 'POST'])
def api_cp_deals_monitor_recipients():
    """TO/CC do aviso diário, do card Deals Monitor. Salvar vazio nos dois
    campos volta ao default da mesa em vez de desligar a rotina em silêncio."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if request.method == 'GET':
        return jsonify({'success': True, **engine._load_ndm_pending_recipients(),
                        **engine._ndm_pending_status()})
    payload = request.get_json(silent=True) or {}
    try:
        engine._save_ndm_pending_recipients((payload.get('to') or '').strip(),
                                     (payload.get('cc') or '').strip())
    except Exception as e:                                  # noqa: BLE001
        _R().log.error('[deals-monitor] save recipients failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': '{}: {}'.format(type(e).__name__, e)}), 500
    return jsonify({'success': True})

@blueprint.route('/api/control-panel/deals-monitor/run', methods=['POST'])
def api_cp_deals_monitor_run():
    """Dispara o aviso na hora, sem esperar os horários agendados."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ds = (payload.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    rec = engine._load_ndm_pending_recipients()
    to_list, cc_list = _R()._parse_emails(rec['to']), _R()._parse_emails(rec['cc'])
    if not (to_list or cc_list):
        return jsonify({'success': False,
                        'error': 'Nenhum destinatário salvo. Preencha o TO antes de rodar.'}), 400
    result = engine._send_ndm_pending_email(ref, to_list, cc_list)
    if result == 'empty':
        return jsonify({'success': True,
                        'message': 'Nothing pending on the Deals Monitor — no e-mail sent.'})
    if result is not True:
        return jsonify({'success': False, 'error': 'E-mail failed: {}'.format(result)}), 500
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Deals Monitor Sent', 'Control Panel',
                         'Pending Action e-mailed ({})'.format(ref.strftime('%Y-%m-%d')))
    return jsonify({'success': True,
                    'message': 'Pending Action enviado para {} destinatário(s).'.format(
                        len(to_list) + len(cc_list))})
