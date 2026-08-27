# -*- coding: utf-8 -*-
"""As duas rotas do card Signature Collection."""
from flask import jsonify, make_response, session

from apps.pages import blueprint
from apps.pages.features.sigcoll import domain, queries


def _routes():
    from apps.pages import routes
    return routes


@blueprint.route('/api/control-panel/signature-collection/preview')
def api_cp_signature_collection_preview():
    """Summary of what a run would produce: one row per counterparty draft."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    bankers = queries.bankers_index()
    items = []
    for g in queries.groups():
        cc = queries.cc_emails(g['banker'], bankers)
        items.append({'counterparty': g['cp_name'], 'disclaimer': g['disclaimer'],
                      'confirmations': len(g['rows']), 'cc_count': len(cc)})
    return jsonify({'success': True, 'drafts': len(items),
                    'confirmations': sum(i['confirmations'] for i in items), 'items': items})


@blueprint.route('/api/control-panel/signature-collection/generate', methods=['POST'])
def api_cp_signature_collection_generate():
    """Build one .eml draft per counterparty and stream them as a download (a single
    .eml, or a .zip when there is more than one). Opens as editable drafts in Outlook
    via the X-Unsent header; From = is.trade.doc@jpmchase.com."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    from apps.pages import otc_emails
    drafts = queries.build_drafts()
    if not drafts:
        return jsonify({'success': False,
                        'error': 'No pending-signature confirmations found.'}), 404
    fname, mime, data = otc_emails.build_drafts_download(drafts, domain.FROM)
    resp = make_response(data)
    resp.headers['Content-Type'] = mime
    resp.headers['Content-Disposition'] = 'attachment; filename="{}"'.format(fname)
    resp.headers['X-Draft-Count'] = str(len(drafts))
    _routes()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Signature Collection Generated', 'Control Panel',
                         '{} pending-signature draft(s) generated'.format(len(drafts)))
    return resp

