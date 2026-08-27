# -*- coding: utf-8 -*-
"""As duas rotas do card Daily Metric."""
import base64
import traceback
from datetime import datetime

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.daily_metric import commands, queries


def _routes():
    from apps.pages import routes
    return routes


@blueprint.route('/api/control-panel/daily-metric/recipients', methods=['GET', 'POST'])
def api_cp_daily_metric_recipients():
    """GET → the saved TO/CC/BCC; POST → persist them (so they survive across runs)."""
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if request.method == 'GET':
        return jsonify({'success': True, **queries.recipients()})
    payload = request.get_json(silent=True) or {}
    try:
        commands.save_recipients((payload.get('to') or '').strip(),
                                 (payload.get('cc') or '').strip(),
                                 (payload.get('bcc') or '').strip())
    except Exception as e:                                  # noqa: BLE001
        R.log.error('[daily-metric] save recipients failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': '{}: {}'.format(type(e).__name__, e)}), 500
    return jsonify({'success': True})


@blueprint.route('/api/control-panel/daily-metric/run', methods=['POST'])
def api_cp_daily_metric_run():
    """Build the Daily Metric e-mail as a downloadable .eml draft (X-Unsent) for
    the saved recipients — the person opens it in Outlook, reviews and sends."""
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    date_str = (payload.get('date') or '').strip()
    try:
        ref = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.now()
    except ValueError:
        ref = datetime.now()
    rec = queries.recipients()
    to_list, cc_list, bcc_list = (R._parse_emails(rec['to']),
                                  R._parse_emails(rec['cc']),
                                  R._parse_emails(rec['bcc']))
    if not (to_list or cc_list or bcc_list):
        return jsonify({'success': False,
                        'error': 'Nenhum destinatário salvo. Preencha TO/CC/BCC antes de rodar.'}), 400
    raw, err = commands.build_draft(ref, to_list, cc_list, bcc_list)
    if err:
        return jsonify({'success': False, 'error': 'Draft failed: {}'.format(err)}), 500
    R._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                           'Daily Metric Draft', 'Control Panel',
                           'Outstanding Confirmation Brazil OTC draft generated ({})'.format(
                               ref.strftime('%Y-%m-%d')))
    n = len(to_list) + len(cc_list) + len(bcc_list)
    # The .eml ships as base64 in the JSON (New Deals premium-notice pattern) and
    # the page saves the file — Outlook opens it as an editable draft.
    return jsonify({'success': True,
                    'filename': 'Daily_Metric_Outstanding_Confirmation_{}.eml'.format(
                        ref.strftime('%d%m%Y')),
                    'b64': base64.b64encode(raw).decode('ascii'),
                    'message': 'Draft gerado com {} destinatário(s). Abra o arquivo baixado '
                               'no Outlook para revisar e enviar.'.format(n)})
