# -*- coding: utf-8 -*-
"""As três rotas do Box Scan (varredura do box compartilhado do Outlook)."""
from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.boxscan import commands
from apps.pages.features.boxscan.infra import persistence

# O wiring do routes registra o scheduler com este nome.
start_scheduler = commands.start_scheduler


def _routes():
    from apps.pages import routes
    return routes


@blueprint.route('/api/new-deals/box-scan', methods=['POST'])
def api_new_deals_box_scan():
    """Sweep the shared Outlook box for booking-recap emails of one product.

    Triggered when the New Deals Import button is clicked with an empty dropzone.
    Returns each matching email's HTML body so the client can run it through the
    same parse pipeline as a dropped file. 'Cancel' emails are deleted from the
    box. product = 'ndf' (Swap emails) or 'opt' (Option emails).
    """
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    product = (request.get_json(silent=True) or {}).get('product', '')
    try:
        from apps.pages.otc_boxscan import scan_new_deals_box
        return jsonify(scan_new_deals_box(product))
    except EnvironmentError as e:
        # win32com/Outlook absent (e.g. non-Windows host) — let the client fall
        # back to the manual dropzone.
        return jsonify({'unavailable': True, 'detail': str(e)})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        _routes().log.error('[api_new_deals_box_scan] %s', e)
        return jsonify({'error': str(e)}), 500


@blueprint.route('/api/new-deals/box-scan/run', methods=['POST'])
def api_new_deals_box_scan_run():
    """Dispara a varredura do box na hora, sem esperar os 30 min. Serve para
    conferir o agendamento na instância da equipe."""
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    product = (request.get_json(silent=True) or {}).get('product', '')
    products = [product] if product in persistence.PRODUCTS else list(persistence.PRODUCTS)
    out = {}
    for p in products:
        try:
            out[p] = commands.pull(p)
        except EnvironmentError as e:
            out[p] = {'unavailable': True, 'detail': str(e)}
        except Exception as e:                              # noqa: BLE001
            _routes().log.error('[boxscan] run manual de %s: %s', p, e)
            out[p] = {'error': str(e)}
    return jsonify({'ok': True, 'results': out})


@blueprint.route('/api/new-deals/box-archive', methods=['POST'])
def api_new_deals_box_archive():
    """Move a processed booking-recap email to Inbox > New deals > B2Bs Automatic.

    Called by the client after an email scanned via /box-scan has had its deals
    imported, so the box keeps only unprocessed emails.
    """
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    entry_id = (request.get_json(silent=True) or {}).get('entry_id', '')
    try:
        from apps.pages.otc_boxscan import archive_email
        return jsonify(archive_email(entry_id))
    except EnvironmentError as e:
        return jsonify({'unavailable': True, 'detail': str(e)})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        _routes().log.error('[api_new_deals_box_archive] %s', e)
        return jsonify({'error': str(e)}), 500



@blueprint.route('/api/parse-msg-html', methods=['POST'])
def api_parse_msg_html():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    f = request.files.get('file')
    if not f:
        return jsonify({'ok': False, 'error': 'no file'}), 400
    # Cap the .msg size before handing the bytes to the OLE/CFB parser to avoid
    # memory-exhaustion DoS from an oversized upload.
    _MAX_MSG_BYTES = 25 * 1024 * 1024
    try:
        import extract_msg
        import io
        data = f.read(_MAX_MSG_BYTES + 1)
        if len(data) > _MAX_MSG_BYTES:
            return jsonify({'ok': False, 'error': 'file too large'}), 413
        msg = extract_msg.openMsg(io.BytesIO(data))
        html_body = getattr(msg, 'htmlBody', None)
        if html_body:
            if isinstance(html_body, bytes):
                html_body = html_body.decode('utf-8', errors='replace')
            return jsonify({'ok': True, 'html': html_body})
        # Fallback to plain text body wrapped in <pre>
        body = getattr(msg, 'body', None) or ''
        if isinstance(body, bytes):
            body = body.decode('utf-8', errors='replace')
        return jsonify({'ok': True, 'html': '<pre>' + body + '</pre>'})
    except Exception as e:
        _routes().log.error('parse_msg_html error: %s', e)
        return jsonify({'ok': False, 'error': str(e)}), 500
