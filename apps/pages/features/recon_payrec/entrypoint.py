# -*- coding: utf-8 -*-
"""As quatro rotas do Pay/Rec."""
from datetime import datetime

from flask import jsonify, redirect, render_template, request, session, url_for

from apps.pages import blueprint
from apps.pages.features.recon_payrec import commands, queries


def _routes():
    from apps.pages import routes
    return routes


@blueprint.route('/reconciliation-payrec')
def reconciliation_payrec():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    ref_date = datetime.now().strftime('%Y-%m-%d')   # Pay/Rec runs on today's date
    return render_template('pages/reconciliation-payrec.html',
                           segment='reconciliation-payrec', ref_date=ref_date)


@blueprint.route('/reconciliation-payrec/data')
def reconciliation_payrec_data():
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        return jsonify(queries.last(request.args.get('recon_date', '')))
    except Exception as e:                                  # noqa: BLE001
        R.log.error('[recon_payrec_data] %s', e)
        return jsonify({'error': str(e)}), 500


@blueprint.route('/reconciliation-payrec/run', methods=['POST'])
def reconciliation_payrec_run():
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    mode = request.form.get('mode', 'auto')
    recon_date = request.form.get('recon_date', '')
    try:
        files = request.files.getlist('files') if mode == 'manual' else None
        result = commands.run(recon_date, files=files, mode=mode)
        if result.get('success'):
            R._create_notification(
                session.get('user_sid', ''), session.get('user_name', ''),
                'Pay/Rec Reconciliation', 'Reconciliation',
                result.get('meta', '') + (' (' + recon_date + ')' if recon_date else '')
            )
        return jsonify(result)
    except FileNotFoundError as e:
        R.log.warning('[recon_payrec_run] arquivo não encontrado: %s', e)
        return jsonify({'not_found': True, 'detail': str(e)})
    except Exception as e:                                  # noqa: BLE001
        R.log.error('[recon_payrec_run] %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


@blueprint.route('/reconciliation-payrec/justify', methods=['POST'])
def reconciliation_payrec_justify():
    R = _routes()
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    payload = request.get_json(silent=True) or {}
    recon_date = (payload.get('recon_date') or '').strip()
    table = (payload.get('table') or '').strip()
    comment = (payload.get('comment') or '').strip()
    status = (payload.get('status') or '').strip()
    if table not in ('pay', 'rec'):
        return jsonify({'success': False, 'error': 'Invalid table'}), 400
    # A comment is required only when the row is being justified (status left as
    # "Pending"). Marking it as a carry-forward "Pending Payment/Receivement"
    # keeps it pending for the next days, so the comment is optional there.
    is_carry = status.lower() in ('pending payment', 'pending receivement')
    if not is_carry and not comment:
        return jsonify({'success': False, 'error': 'A justification comment is required.'}), 400
    try:
        data = commands.justify(recon_date, table, payload.get('index'), comment, status)
        if not data:
            return jsonify({'success': False, 'error': 'Row not found for this date.'}), 404
        return jsonify({'success': True})
    except Exception as e:                                  # noqa: BLE001
        R.log.error('[recon_payrec_justify] %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


@blueprint.route('/reconciliation-payrec/end-process', methods=['POST'])
def reconciliation_payrec_end():
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    R = _routes()
    recon_date = request.form.get('recon_date', '')
    try:
        # Persist the day's status to the dated history first — this is the record
        # of the finalized day, independent of whether SMTP is reachable.
        saved, emailed = commands.end_process(recon_date)
        if not saved:
            return jsonify({'success': False, 'error': 'No processed result for this date — run the reconciliation first.'})
        R._create_notification(
            session.get('user_sid', ''), session.get('user_name', ''),
            'Pay/Rec End of Day', 'Reconciliation',
            'Day finalised' + (' — e-mailed to OTC Ops' if emailed else ' (e-mail skipped)') +
            (' (' + recon_date + ')' if recon_date else '')
        )
        return jsonify({'success': True, 'emailed': bool(emailed)})
    except Exception as e:
        R.log.error('[recon_payrec_end] %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500
