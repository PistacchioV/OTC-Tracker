# -*- coding: utf-8 -*-
"""As três rotas do card Settlement Forecast (o coletor é plataforma)."""
import traceback
from datetime import datetime

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.forecast import commands, queries


def _routes():
    from apps.pages import routes
    return routes


@blueprint.route('/api/control-panel/settlement-forecast/data', methods=['POST'])
def api_cp_forecast_data():
    """Compute the forecast for a reference date and return it as JSON for the
    page to render (ApexCharts + tables)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    R = _routes()
    payload = request.get_json(silent=True) or {}
    mode = (payload.get('mode') or '').strip().lower()
    date_str = (payload.get('date') or '').strip()
    try:
        days = int(payload.get('days') or R.FORECAST_BIZDAYS)
    except (TypeError, ValueError):
        days = R.FORECAST_BIZDAYS
    if days not in R.FORECAST_RANGE_CHOICES:
        days = R.FORECAST_BIZDAYS
    try:
        if date_str:
            ref = datetime.strptime(date_str, '%Y-%m-%d')
        elif mode == 'latest':
            # Dashboard: use the most recent date that actually has saved JSONs
            # (D-1, else D-2, …). Never blocks just because D-1 isn't saved yet.
            ref = R._forecast_latest_ref()
            if ref is None:
                return jsonify({'success': False,
                                'error': 'No B3 JSON files found in the last 10 business days. '
                                         'Run “Save CETIP Files” first.'}), 400
        else:
            ref = R._prev_anbima_bizday(datetime.now())   # strict D-1 (Control Panel run)
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid date (expected YYYY-MM-DD).'}), 400

    data = R._forecast_payload(ref, days=days)
    if not any(s['found'] for s in data['sources']):
        # In strict mode this means the mandatory D-1 files are missing.
        return jsonify({'success': False,
                        'error': 'No B3 JSON files found for {}. Run “Save CETIP Files” first.'
                        .format(ref.strftime('%d/%m/%Y')),
                        'sources': data['sources']}), 400
    return jsonify({'success': True, **data})


@blueprint.route('/api/control-panel/settlement-forecast/recipients', methods=['GET', 'POST'])
def api_cp_forecast_recipients():
    """GET → the saved TO/CC; POST → persist them (so they survive across runs)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    R = _routes()
    if request.method == 'GET':
        return jsonify({'success': True, **queries.recipients()})
    payload = request.get_json(silent=True) or {}
    try:
        commands.save_recipients((payload.get('to') or '').strip(),
                                  (payload.get('cc') or '').strip())
    except Exception as e:
        R.log.error('[forecast] save recipients failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': '{}: {}'.format(type(e).__name__, e)}), 500
    return jsonify({'success': True})


@blueprint.route('/api/control-panel/settlement-forecast/email', methods=['POST'])
def api_cp_forecast_email():
    """Receive the client-rendered chart PNGs (data URIs), rebuild the report
    tables server-side and e-mail the Settlement Forecast to the saved TO/CC."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    R = _routes()
    payload = request.get_json(silent=True) or {}
    date_str = (payload.get('date') or '').strip()
    try:
        ref = (datetime.strptime(date_str, '%Y-%m-%d') if date_str
               else R._prev_anbima_bizday(datetime.now()))
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid date (expected YYYY-MM-DD).'}), 400

    rec = queries.recipients()
    to_list, cc_list = R._parse_emails(rec['to']), R._parse_emails(rec['cc'])
    if not (to_list or cc_list):
        return jsonify({'success': False,
                        'error': 'Nenhum destinatário salvo. Preencha TO/CC antes de rodar.'}), 400

    data = R._forecast_payload(ref)
    imgs = payload.get('images') or {}
    images = {
        'fcst_product': R._decode_data_uri(imgs.get('by_product')),
        'fcst_entity':  R._decode_data_uri(imgs.get('by_entity')),
    }
    result = commands.send(data, images, to_list, cc_list)
    if result is not True:
        return jsonify({'success': False, 'error': 'E-mail failed: {}'.format(result)}), 500

    R._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Settlement Forecast Sent', 'Control Panel',
                         'Forecast e-mailed ({})'.format(ref.strftime('%Y-%m-%d')))
    n = len(to_list) + len(cc_list)
    return jsonify({'success': True,
                    'message': 'Settlement Forecast enviado para {} destinatário(s).'.format(n)})

