# -*- coding: utf-8 -*-
"""As dezoito rotas do Counterparty Details (17 do registro + Update Contacts)."""
import traceback

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.counterparty_details import commands, domain
from apps.pages.features.counterparty_details.infra import persistence


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/api/control-panel/import-contacts', methods=['POST'])
def api_cp_import_contacts():
    """Update client contacts from the uploaded 'CONTATO DE CLIENTES' spreadsheet."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'error': 'No file uploaded.'}), 400
    try:
        summary = commands._import_client_contacts(f.filename, f.read())
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        _R().log.error('[contacts] import failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': 'Failed to process the spreadsheet.'}), 500

    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Contacts Updated', 'Control Panel',
                         '{} contacts across {} counterparties'.format(summary['contacts'], summary['spns']))
    msg = ('<b>{contacts}</b> contacts imported across <b>{spns}</b> counterparties.'
           '<br>Matched existing: {matched} &middot; New records appended: {created}'
           '<br>Total counterparties: {total}').format(**summary)
    if summary.get('skipped_email') or summary.get('swept'):
        msg += ('<br>Placeholder e-mails ignored: {skipped_email} '
                '&middot; removed from the stored base: {swept}').format(**summary)
    return jsonify({'success': True, 'message': msg})

@blueprint.route('/api/counterparty-details/save', methods=['POST'])
def api_counterparty_details_save():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    payload = request.get_json(silent=True) or {}
    spn = str(payload.get('SPN', '') or '').strip()
    if not spn:
        return jsonify({'ok': False, 'error': 'missing_spn'}), 400

    created = _R()._cpd_find(_R()._cpd_load(), spn) is None
    data, rec = persistence._cpd_get_record(spn)

    # COUNTERPARTY name can still be set here; CGD / CONTACTS / BANKING are each
    # managed by their dedicated maker/checker endpoints below and are left untouched.
    if payload.get('COUNTERPARTY'):
        rec['COUNTERPARTY'] = payload.get('COUNTERPARTY')

    try:
        _R()._cpd_save_list(data)
    except IOError as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    return jsonify({'ok': True, 'created': created})

@blueprint.route('/api/counterparty-details/banking/account/add', methods=['POST'])
def api_cp_banking_account_add():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    if not spn:
        return jsonify({'ok': False, 'error': 'missing_spn'}), 400
    bank = str(p.get('bank', '') or '').strip()
    agency = str(p.get('agency', '') or '').strip()
    account = str(p.get('account', '') or '').strip()
    if not (bank or agency or account):
        return jsonify({'ok': False, 'error': 'empty_account'}), 400

    sid = session.get('user_sid', '') or ''
    data, rec, banking = persistence._bank_get_record(spn)
    acc = {'id': _R().uuid.uuid4().hex[:8], 'bank': bank, 'agency': agency,
           'account': account, 'status': 'Pending', 'maker': sid, 'checker': ''}
    banking['ACCOUNTS'].append(acc)
    _R()._cpd_save_list(data)
    commands._notify_bank('Bank Account Added', domain._bank_detail(spn, rec, domain._acc_disp(acc) + ' (Pending approval)'))
    return jsonify({'ok': True, 'account': acc})

@blueprint.route('/api/counterparty-details/banking/account/edit', methods=['POST'])
def api_cp_banking_account_edit():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    acc_id = str(p.get('id', '') or '').strip()
    if not spn:
        return jsonify({'ok': False, 'error': 'missing_spn'}), 400
    bank = str(p.get('bank', '') or '').strip()
    agency = str(p.get('agency', '') or '').strip()
    account = str(p.get('account', '') or '').strip()
    if not (bank or agency or account):
        return jsonify({'ok': False, 'error': 'empty_account'}), 400
    sid = session.get('user_sid', '') or ''
    data, rec, banking = persistence._bank_get_record(spn)
    acc = next((a for a in banking['ACCOUNTS'] if a['id'] == acc_id), None)
    if acc is None:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    # Editing bank details requires re-approval → back to Pending (maker/checker).
    acc['bank'] = bank
    acc['agency'] = agency
    acc['account'] = account
    acc['status'] = 'Pending'
    acc['maker'] = sid
    acc['checker'] = ''
    _R()._cpd_save_list(data)
    commands._notify_bank('Bank Account Edited', domain._bank_detail(spn, rec, domain._acc_disp(acc) + ' (Pending approval)'))
    return jsonify({'ok': True, 'account': acc})

@blueprint.route('/api/counterparty-details/banking/account/approve', methods=['POST'])
def api_cp_banking_account_approve():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    acc_id = str(p.get('id', '') or '').strip()
    sid = session.get('user_sid', '') or ''
    data, rec, banking = persistence._bank_get_record(spn)
    acc = next((a for a in banking['ACCOUNTS'] if a['id'] == acc_id), None)
    if acc is None:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    if acc.get('maker') and acc['maker'] == sid:
        return jsonify({'ok': False, 'error': 'same_user'}), 403
    acc['status'] = 'Active'
    acc['checker'] = sid
    _R()._cpd_save_list(data)
    commands._notify_bank('Bank Account Approved', domain._bank_detail(spn, rec, domain._acc_disp(acc)))
    return jsonify({'ok': True, 'account': acc})

@blueprint.route('/api/counterparty-details/banking/account/delete', methods=['POST'])
def api_cp_banking_account_delete():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    acc_id = str(p.get('id', '') or '').strip()
    data, rec, banking = persistence._bank_get_record(spn)
    removed = next((a for a in banking['ACCOUNTS'] if a['id'] == acc_id), None)
    banking['ACCOUNTS'] = [a for a in banking['ACCOUNTS'] if a['id'] != acc_id]
    for slot in ('DEFAULT_PAY', 'DEFAULT_RECEIVE'):
        d = banking[slot]
        if d.get('current') == acc_id:
            d['current'] = None
        if d.get('pending') == acc_id:
            d['pending'] = None
    _R()._cpd_save_list(data)
    commands._notify_bank('Bank Account Deleted', domain._bank_detail(spn, rec, domain._acc_disp(removed)))
    return jsonify({'ok': True})

@blueprint.route('/api/counterparty-details/banking/default/set', methods=['POST'])
def api_cp_banking_default_set():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    kind = str(p.get('kind', '') or '').upper()
    acc_id = str(p.get('id', '') or '').strip()
    if kind not in ('PAY', 'RECEIVE'):
        return jsonify({'ok': False, 'error': 'bad_kind'}), 400
    sid = session.get('user_sid', '') or ''
    data, rec, banking = persistence._bank_get_record(spn)
    acc = next((a for a in banking['ACCOUNTS'] if a['id'] == acc_id), None)
    if acc is None:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    if str(acc.get('status', '')).lower() != 'active':
        return jsonify({'ok': False, 'error': 'not_active'}), 400
    slot = banking['DEFAULT_' + kind]
    slot['pending'] = acc_id
    slot['maker'] = sid
    slot['checker'] = ''
    _R()._cpd_save_list(data)
    commands._notify_bank('Bank Default Set', domain._bank_detail(spn, rec, '{} → {} (Pending approval)'.format(kind, domain._acc_disp(acc))))
    return jsonify({'ok': True, 'slot': slot})

@blueprint.route('/api/counterparty-details/banking/default/approve', methods=['POST'])
def api_cp_banking_default_approve():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    kind = str(p.get('kind', '') or '').upper()
    if kind not in ('PAY', 'RECEIVE'):
        return jsonify({'ok': False, 'error': 'bad_kind'}), 400
    sid = session.get('user_sid', '') or ''
    data, rec, banking = persistence._bank_get_record(spn)
    slot = banking['DEFAULT_' + kind]
    if not slot.get('pending'):
        return jsonify({'ok': False, 'error': 'no_pending'}), 400
    if slot.get('maker') and slot['maker'] == sid:
        return jsonify({'ok': False, 'error': 'same_user'}), 403
    slot['current'] = slot['pending']
    slot['pending'] = None
    slot['checker'] = sid
    _R()._cpd_save_list(data)
    _acc = next((a for a in banking['ACCOUNTS'] if a['id'] == slot['current']), None)
    commands._notify_bank('Bank Default Approved', domain._bank_detail(spn, rec, '{} → {}'.format(kind, domain._acc_disp(_acc))))
    return jsonify({'ok': True, 'slot': slot})

@blueprint.route('/api/counterparty-details/cgd/add', methods=['POST'])
def api_cp_cgd_add():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    if not spn:
        return jsonify({'ok': False, 'error': 'missing_spn'}), 400
    value = str(p.get('value', '') or '').strip()
    if not value:
        return jsonify({'ok': False, 'error': 'empty_value'}), 400
    sid = session.get('user_sid', '') or ''
    data, rec = persistence._cpd_get_record(spn)
    item = {'id': _R().uuid.uuid4().hex[:8], 'value': value,
            'status': 'Pending', 'maker': sid, 'checker': ''}
    rec['CGD'].append(item)
    _R()._cpd_save_list(data)
    commands._notify_bank('CGD Added', domain._bank_detail(spn, rec, value + ' (Pending approval)'))
    return jsonify({'ok': True, 'item': item})

@blueprint.route('/api/counterparty-details/cgd/edit', methods=['POST'])
def api_cp_cgd_edit():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    value = str(p.get('value', '') or '').strip()
    if not value:
        return jsonify({'ok': False, 'error': 'empty_value'}), 400
    sid = session.get('user_sid', '') or ''
    data, rec = persistence._cpd_get_record(spn)
    item = next((x for x in rec['CGD'] if x['id'] == iid), None)
    if item is None:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    item['value'] = value
    item['status'] = 'Pending'
    item['maker'] = sid
    item['checker'] = ''
    _R()._cpd_save_list(data)
    commands._notify_bank('CGD Edited', domain._bank_detail(spn, rec, value + ' (Pending approval)'))
    return jsonify({'ok': True, 'item': item})

@blueprint.route('/api/counterparty-details/cgd/approve', methods=['POST'])
def api_cp_cgd_approve():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    sid = session.get('user_sid', '') or ''
    data, rec = persistence._cpd_get_record(spn)
    item = next((x for x in rec['CGD'] if x['id'] == iid), None)
    if item is None:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    if item.get('maker') and item['maker'] == sid:
        return jsonify({'ok': False, 'error': 'same_user'}), 403
    item['status'] = 'Active'
    item['checker'] = sid
    _R()._cpd_save_list(data)
    commands._notify_bank('CGD Approved', domain._bank_detail(spn, rec, item['value']))
    return jsonify({'ok': True, 'item': item})

@blueprint.route('/api/counterparty-details/cgd/delete', methods=['POST'])
def api_cp_cgd_delete():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    data, rec = persistence._cpd_get_record(spn)
    removed = next((x for x in rec['CGD'] if x['id'] == iid), None)
    rec['CGD'] = [x for x in rec['CGD'] if x['id'] != iid]
    _R()._cpd_save_list(data)
    commands._notify_bank('CGD Deleted', domain._bank_detail(spn, rec, (removed or {}).get('value', '')))
    return jsonify({'ok': True})

@blueprint.route('/api/counterparty-details/net/edit', methods=['POST'])
def api_cp_net_edit():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    if not spn:
        return jsonify({'ok': False, 'error': 'missing_spn'}), 400
    value = str(p.get('value', '') or '').strip()
    if value not in _R()._CP_NET_TYPES:
        return jsonify({'ok': False, 'error': 'invalid_value'}), 400
    sid = session.get('user_sid', '') or ''
    data, rec = persistence._cpd_get_record(spn)
    rec['NET'] = {'value': value, 'status': 'Pending', 'maker': sid, 'checker': ''}
    _R()._cpd_save_list(data)
    commands._notify_bank('Net Type Edited', domain._bank_detail(spn, rec, value + ' (Pending approval)'))
    return jsonify({'ok': True, 'item': rec['NET']})

@blueprint.route('/api/counterparty-details/net/approve', methods=['POST'])
def api_cp_net_approve():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    sid = session.get('user_sid', '') or ''
    data, rec = persistence._cpd_get_record(spn)
    net = rec['NET']
    if net.get('maker') and net['maker'] == sid:
        return jsonify({'ok': False, 'error': 'same_user'}), 403
    net['status'] = 'Active'
    net['checker'] = sid
    _R()._cpd_save_list(data)
    commands._notify_bank('Net Type Approved', domain._bank_detail(spn, rec, net['value']))
    return jsonify({'ok': True, 'item': net})

@blueprint.route('/api/counterparty-details/contact/add', methods=['POST'])
def api_cp_contact_add():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    if not spn:
        return jsonify({'ok': False, 'error': 'missing_spn'}), 400
    fields = domain._contact_payload(p)
    if not (fields['name'] or fields['phone'] or fields['email'] or fields['rules']):
        return jsonify({'ok': False, 'error': 'empty_contact'}), 400
    sid = session.get('user_sid', '') or ''
    data, rec = persistence._cpd_get_record(spn)
    item = dict(fields, id=_R().uuid.uuid4().hex[:8], appr='Pending', maker=sid, checker='')
    rec['CONTACTS'].append(item)
    _R()._cpd_save_list(data)
    commands._notify_bank('Contact Added', domain._bank_detail(spn, rec, domain._contact_disp(item) + ' (Pending approval)'))
    return jsonify({'ok': True, 'item': item})

@blueprint.route('/api/counterparty-details/contact/edit', methods=['POST'])
def api_cp_contact_edit():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    fields = domain._contact_payload(p)
    if not (fields['name'] or fields['phone'] or fields['email'] or fields['rules']):
        return jsonify({'ok': False, 'error': 'empty_contact'}), 400
    sid = session.get('user_sid', '') or ''
    data, rec = persistence._cpd_get_record(spn)
    item = next((x for x in rec['CONTACTS'] if x['id'] == iid), None)
    if item is None:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    item.update(fields)
    item['appr'] = 'Pending'
    item['maker'] = sid
    item['checker'] = ''
    _R()._cpd_save_list(data)
    commands._notify_bank('Contact Edited', domain._bank_detail(spn, rec, domain._contact_disp(item) + ' (Pending approval)'))
    return jsonify({'ok': True, 'item': item})

@blueprint.route('/api/counterparty-details/contact/approve', methods=['POST'])
def api_cp_contact_approve():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    sid = session.get('user_sid', '') or ''
    data, rec = persistence._cpd_get_record(spn)
    item = next((x for x in rec['CONTACTS'] if x['id'] == iid), None)
    if item is None:
        return jsonify({'ok': False, 'error': 'not_found'}), 404
    if item.get('maker') and item['maker'] == sid:
        return jsonify({'ok': False, 'error': 'same_user'}), 403
    item['appr'] = 'Active'
    item['checker'] = sid
    _R()._cpd_save_list(data)
    commands._notify_bank('Contact Approved', domain._bank_detail(spn, rec, domain._contact_disp(item)))
    return jsonify({'ok': True, 'item': item})

@blueprint.route('/api/counterparty-details/contact/delete', methods=['POST'])
def api_cp_contact_delete():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    data, rec = persistence._cpd_get_record(spn)
    removed = next((x for x in rec['CONTACTS'] if x['id'] == iid), None)
    rec['CONTACTS'] = [x for x in rec['CONTACTS'] if x['id'] != iid]
    _R()._cpd_save_list(data)
    commands._notify_bank('Contact Deleted', domain._bank_detail(spn, rec, domain._contact_disp(removed)))
    return jsonify({'ok': True})
