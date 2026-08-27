# -*- coding: utf-8 -*-
"""As dezoito rotas do Counterparty Details (17 do registro + Update Contacts)."""
import traceback

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.counterparty_details import engine


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@_R().blueprint.route('/api/control-panel/import-contacts', methods=['POST'])
def api_cp_import_contacts():
    """Update client contacts from the uploaded 'CONTATO DE CLIENTES' spreadsheet."""
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    f = _R().request.files.get('file')
    if not f or not f.filename:
        return _R().jsonify({'success': False, 'error': 'No file uploaded.'}), 400
    try:
        summary = engine._import_client_contacts(f.filename, f.read())
    except ValueError as e:
        return _R().jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        _R().log.error('[contacts] import failed:\n%s', _R().traceback.format_exc())
        return _R().jsonify({'success': False, 'error': 'Failed to process the spreadsheet.'}), 500

    _R()._create_notification(_R().session.get('user_sid', ''), _R().session.get('user_name', ''),
                         'Contacts Updated', 'Control Panel',
                         '{} contacts across {} counterparties'.format(summary['contacts'], summary['spns']))
    msg = ('<b>{contacts}</b> contacts imported across <b>{spns}</b> counterparties.'
           '<br>Matched existing: {matched} &middot; New records appended: {created}'
           '<br>Total counterparties: {total}').format(**summary)
    if summary.get('skipped_email') or summary.get('swept'):
        msg += ('<br>Placeholder e-mails ignored: {skipped_email} '
                '&middot; removed from the stored base: {swept}').format(**summary)
    return _R().jsonify({'success': True, 'message': msg})

@_R().blueprint.route('/api/counterparty-details/save', methods=['POST'])
def api_counterparty_details_save():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401

    payload = _R().request.get_json(silent=True) or {}
    spn = str(payload.get('SPN', '') or '').strip()
    if not spn:
        return _R().jsonify({'ok': False, 'error': 'missing_spn'}), 400

    created = _R()._cpd_find(_R()._cpd_load(), spn) is None
    data, rec = engine._cpd_get_record(spn)

    # COUNTERPARTY name can still be set here; CGD / CONTACTS / BANKING are each
    # managed by their dedicated maker/checker endpoints below and are left untouched.
    if payload.get('COUNTERPARTY'):
        rec['COUNTERPARTY'] = payload.get('COUNTERPARTY')

    try:
        _R()._cpd_save_list(data)
    except IOError as e:
        return _R().jsonify({'ok': False, 'error': str(e)}), 500
    return _R().jsonify({'ok': True, 'created': created})

@_R().blueprint.route('/api/counterparty-details/banking/account/add', methods=['POST'])
def api_cp_banking_account_add():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    if not spn:
        return _R().jsonify({'ok': False, 'error': 'missing_spn'}), 400
    bank = str(p.get('bank', '') or '').strip()
    agency = str(p.get('agency', '') or '').strip()
    account = str(p.get('account', '') or '').strip()
    if not (bank or agency or account):
        return _R().jsonify({'ok': False, 'error': 'empty_account'}), 400

    sid = _R().session.get('user_sid', '') or ''
    data, rec, banking = engine._bank_get_record(spn)
    acc = {'id': _R().uuid.uuid4().hex[:8], 'bank': bank, 'agency': agency,
           'account': account, 'status': 'Pending', 'maker': sid, 'checker': ''}
    banking['ACCOUNTS'].append(acc)
    _R()._cpd_save_list(data)
    engine._notify_bank('Bank Account Added', engine._bank_detail(spn, rec, engine._acc_disp(acc) + ' (Pending approval)'))
    return _R().jsonify({'ok': True, 'account': acc})

@_R().blueprint.route('/api/counterparty-details/banking/account/edit', methods=['POST'])
def api_cp_banking_account_edit():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    acc_id = str(p.get('id', '') or '').strip()
    if not spn:
        return _R().jsonify({'ok': False, 'error': 'missing_spn'}), 400
    bank = str(p.get('bank', '') or '').strip()
    agency = str(p.get('agency', '') or '').strip()
    account = str(p.get('account', '') or '').strip()
    if not (bank or agency or account):
        return _R().jsonify({'ok': False, 'error': 'empty_account'}), 400
    sid = _R().session.get('user_sid', '') or ''
    data, rec, banking = engine._bank_get_record(spn)
    acc = next((a for a in banking['ACCOUNTS'] if a['id'] == acc_id), None)
    if acc is None:
        return _R().jsonify({'ok': False, 'error': 'not_found'}), 404
    # Editing bank details requires re-approval → back to Pending (maker/checker).
    acc['bank'] = bank
    acc['agency'] = agency
    acc['account'] = account
    acc['status'] = 'Pending'
    acc['maker'] = sid
    acc['checker'] = ''
    _R()._cpd_save_list(data)
    engine._notify_bank('Bank Account Edited', engine._bank_detail(spn, rec, engine._acc_disp(acc) + ' (Pending approval)'))
    return _R().jsonify({'ok': True, 'account': acc})

@_R().blueprint.route('/api/counterparty-details/banking/account/approve', methods=['POST'])
def api_cp_banking_account_approve():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    acc_id = str(p.get('id', '') or '').strip()
    sid = _R().session.get('user_sid', '') or ''
    data, rec, banking = engine._bank_get_record(spn)
    acc = next((a for a in banking['ACCOUNTS'] if a['id'] == acc_id), None)
    if acc is None:
        return _R().jsonify({'ok': False, 'error': 'not_found'}), 404
    if acc.get('maker') and acc['maker'] == sid:
        return _R().jsonify({'ok': False, 'error': 'same_user'}), 403
    acc['status'] = 'Active'
    acc['checker'] = sid
    _R()._cpd_save_list(data)
    engine._notify_bank('Bank Account Approved', engine._bank_detail(spn, rec, engine._acc_disp(acc)))
    return _R().jsonify({'ok': True, 'account': acc})

@_R().blueprint.route('/api/counterparty-details/banking/account/delete', methods=['POST'])
def api_cp_banking_account_delete():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    acc_id = str(p.get('id', '') or '').strip()
    data, rec, banking = engine._bank_get_record(spn)
    removed = next((a for a in banking['ACCOUNTS'] if a['id'] == acc_id), None)
    banking['ACCOUNTS'] = [a for a in banking['ACCOUNTS'] if a['id'] != acc_id]
    for slot in ('DEFAULT_PAY', 'DEFAULT_RECEIVE'):
        d = banking[slot]
        if d.get('current') == acc_id:
            d['current'] = None
        if d.get('pending') == acc_id:
            d['pending'] = None
    _R()._cpd_save_list(data)
    engine._notify_bank('Bank Account Deleted', engine._bank_detail(spn, rec, engine._acc_disp(removed)))
    return _R().jsonify({'ok': True})

@_R().blueprint.route('/api/counterparty-details/banking/default/set', methods=['POST'])
def api_cp_banking_default_set():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    kind = str(p.get('kind', '') or '').upper()
    acc_id = str(p.get('id', '') or '').strip()
    if kind not in ('PAY', 'RECEIVE'):
        return _R().jsonify({'ok': False, 'error': 'bad_kind'}), 400
    sid = _R().session.get('user_sid', '') or ''
    data, rec, banking = engine._bank_get_record(spn)
    acc = next((a for a in banking['ACCOUNTS'] if a['id'] == acc_id), None)
    if acc is None:
        return _R().jsonify({'ok': False, 'error': 'not_found'}), 404
    if str(acc.get('status', '')).lower() != 'active':
        return _R().jsonify({'ok': False, 'error': 'not_active'}), 400
    slot = banking['DEFAULT_' + kind]
    slot['pending'] = acc_id
    slot['maker'] = sid
    slot['checker'] = ''
    _R()._cpd_save_list(data)
    engine._notify_bank('Bank Default Set', engine._bank_detail(spn, rec, '{} → {} (Pending approval)'.format(kind, engine._acc_disp(acc))))
    return _R().jsonify({'ok': True, 'slot': slot})

@_R().blueprint.route('/api/counterparty-details/banking/default/approve', methods=['POST'])
def api_cp_banking_default_approve():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    kind = str(p.get('kind', '') or '').upper()
    if kind not in ('PAY', 'RECEIVE'):
        return _R().jsonify({'ok': False, 'error': 'bad_kind'}), 400
    sid = _R().session.get('user_sid', '') or ''
    data, rec, banking = engine._bank_get_record(spn)
    slot = banking['DEFAULT_' + kind]
    if not slot.get('pending'):
        return _R().jsonify({'ok': False, 'error': 'no_pending'}), 400
    if slot.get('maker') and slot['maker'] == sid:
        return _R().jsonify({'ok': False, 'error': 'same_user'}), 403
    slot['current'] = slot['pending']
    slot['pending'] = None
    slot['checker'] = sid
    _R()._cpd_save_list(data)
    _acc = next((a for a in banking['ACCOUNTS'] if a['id'] == slot['current']), None)
    engine._notify_bank('Bank Default Approved', engine._bank_detail(spn, rec, '{} → {}'.format(kind, engine._acc_disp(_acc))))
    return _R().jsonify({'ok': True, 'slot': slot})

@_R().blueprint.route('/api/counterparty-details/cgd/add', methods=['POST'])
def api_cp_cgd_add():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    if not spn:
        return _R().jsonify({'ok': False, 'error': 'missing_spn'}), 400
    value = str(p.get('value', '') or '').strip()
    if not value:
        return _R().jsonify({'ok': False, 'error': 'empty_value'}), 400
    sid = _R().session.get('user_sid', '') or ''
    data, rec = engine._cpd_get_record(spn)
    item = {'id': _R().uuid.uuid4().hex[:8], 'value': value,
            'status': 'Pending', 'maker': sid, 'checker': ''}
    rec['CGD'].append(item)
    _R()._cpd_save_list(data)
    engine._notify_bank('CGD Added', engine._bank_detail(spn, rec, value + ' (Pending approval)'))
    return _R().jsonify({'ok': True, 'item': item})

@_R().blueprint.route('/api/counterparty-details/cgd/edit', methods=['POST'])
def api_cp_cgd_edit():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    value = str(p.get('value', '') or '').strip()
    if not value:
        return _R().jsonify({'ok': False, 'error': 'empty_value'}), 400
    sid = _R().session.get('user_sid', '') or ''
    data, rec = engine._cpd_get_record(spn)
    item = next((x for x in rec['CGD'] if x['id'] == iid), None)
    if item is None:
        return _R().jsonify({'ok': False, 'error': 'not_found'}), 404
    item['value'] = value
    item['status'] = 'Pending'
    item['maker'] = sid
    item['checker'] = ''
    _R()._cpd_save_list(data)
    engine._notify_bank('CGD Edited', engine._bank_detail(spn, rec, value + ' (Pending approval)'))
    return _R().jsonify({'ok': True, 'item': item})

@_R().blueprint.route('/api/counterparty-details/cgd/approve', methods=['POST'])
def api_cp_cgd_approve():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    sid = _R().session.get('user_sid', '') or ''
    data, rec = engine._cpd_get_record(spn)
    item = next((x for x in rec['CGD'] if x['id'] == iid), None)
    if item is None:
        return _R().jsonify({'ok': False, 'error': 'not_found'}), 404
    if item.get('maker') and item['maker'] == sid:
        return _R().jsonify({'ok': False, 'error': 'same_user'}), 403
    item['status'] = 'Active'
    item['checker'] = sid
    _R()._cpd_save_list(data)
    engine._notify_bank('CGD Approved', engine._bank_detail(spn, rec, item['value']))
    return _R().jsonify({'ok': True, 'item': item})

@_R().blueprint.route('/api/counterparty-details/cgd/delete', methods=['POST'])
def api_cp_cgd_delete():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    data, rec = engine._cpd_get_record(spn)
    removed = next((x for x in rec['CGD'] if x['id'] == iid), None)
    rec['CGD'] = [x for x in rec['CGD'] if x['id'] != iid]
    _R()._cpd_save_list(data)
    engine._notify_bank('CGD Deleted', engine._bank_detail(spn, rec, (removed or {}).get('value', '')))
    return _R().jsonify({'ok': True})

@_R().blueprint.route('/api/counterparty-details/net/edit', methods=['POST'])
def api_cp_net_edit():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    if not spn:
        return _R().jsonify({'ok': False, 'error': 'missing_spn'}), 400
    value = str(p.get('value', '') or '').strip()
    if value not in _R()._CP_NET_TYPES:
        return _R().jsonify({'ok': False, 'error': 'invalid_value'}), 400
    sid = _R().session.get('user_sid', '') or ''
    data, rec = engine._cpd_get_record(spn)
    rec['NET'] = {'value': value, 'status': 'Pending', 'maker': sid, 'checker': ''}
    _R()._cpd_save_list(data)
    engine._notify_bank('Net Type Edited', engine._bank_detail(spn, rec, value + ' (Pending approval)'))
    return _R().jsonify({'ok': True, 'item': rec['NET']})

@_R().blueprint.route('/api/counterparty-details/net/approve', methods=['POST'])
def api_cp_net_approve():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    sid = _R().session.get('user_sid', '') or ''
    data, rec = engine._cpd_get_record(spn)
    net = rec['NET']
    if net.get('maker') and net['maker'] == sid:
        return _R().jsonify({'ok': False, 'error': 'same_user'}), 403
    net['status'] = 'Active'
    net['checker'] = sid
    _R()._cpd_save_list(data)
    engine._notify_bank('Net Type Approved', engine._bank_detail(spn, rec, net['value']))
    return _R().jsonify({'ok': True, 'item': net})

@_R().blueprint.route('/api/counterparty-details/contact/add', methods=['POST'])
def api_cp_contact_add():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    if not spn:
        return _R().jsonify({'ok': False, 'error': 'missing_spn'}), 400
    fields = engine._contact_payload(p)
    if not (fields['name'] or fields['phone'] or fields['email'] or fields['rules']):
        return _R().jsonify({'ok': False, 'error': 'empty_contact'}), 400
    sid = _R().session.get('user_sid', '') or ''
    data, rec = engine._cpd_get_record(spn)
    item = dict(fields, id=_R().uuid.uuid4().hex[:8], appr='Pending', maker=sid, checker='')
    rec['CONTACTS'].append(item)
    _R()._cpd_save_list(data)
    engine._notify_bank('Contact Added', engine._bank_detail(spn, rec, engine._contact_disp(item) + ' (Pending approval)'))
    return _R().jsonify({'ok': True, 'item': item})

@_R().blueprint.route('/api/counterparty-details/contact/edit', methods=['POST'])
def api_cp_contact_edit():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    fields = engine._contact_payload(p)
    if not (fields['name'] or fields['phone'] or fields['email'] or fields['rules']):
        return _R().jsonify({'ok': False, 'error': 'empty_contact'}), 400
    sid = _R().session.get('user_sid', '') or ''
    data, rec = engine._cpd_get_record(spn)
    item = next((x for x in rec['CONTACTS'] if x['id'] == iid), None)
    if item is None:
        return _R().jsonify({'ok': False, 'error': 'not_found'}), 404
    item.update(fields)
    item['appr'] = 'Pending'
    item['maker'] = sid
    item['checker'] = ''
    _R()._cpd_save_list(data)
    engine._notify_bank('Contact Edited', engine._bank_detail(spn, rec, engine._contact_disp(item) + ' (Pending approval)'))
    return _R().jsonify({'ok': True, 'item': item})

@_R().blueprint.route('/api/counterparty-details/contact/approve', methods=['POST'])
def api_cp_contact_approve():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    sid = _R().session.get('user_sid', '') or ''
    data, rec = engine._cpd_get_record(spn)
    item = next((x for x in rec['CONTACTS'] if x['id'] == iid), None)
    if item is None:
        return _R().jsonify({'ok': False, 'error': 'not_found'}), 404
    if item.get('maker') and item['maker'] == sid:
        return _R().jsonify({'ok': False, 'error': 'same_user'}), 403
    item['appr'] = 'Active'
    item['checker'] = sid
    _R()._cpd_save_list(data)
    engine._notify_bank('Contact Approved', engine._bank_detail(spn, rec, engine._contact_disp(item)))
    return _R().jsonify({'ok': True, 'item': item})

@_R().blueprint.route('/api/counterparty-details/contact/delete', methods=['POST'])
def api_cp_contact_delete():
    if not _R().session.get('authenticated'):
        return _R().jsonify({'ok': False, 'error': 'Not authenticated'}), 401
    p = _R().request.get_json(silent=True) or {}
    spn = str(p.get('SPN', '') or '').strip()
    iid = str(p.get('id', '') or '').strip()
    data, rec = engine._cpd_get_record(spn)
    removed = next((x for x in rec['CONTACTS'] if x['id'] == iid), None)
    rec['CONTACTS'] = [x for x in rec['CONTACTS'] if x['id'] != iid]
    _R()._cpd_save_list(data)
    engine._notify_bank('Contact Deleted', engine._bank_detail(spn, rec, engine._contact_disp(removed)))
    return _R().jsonify({'ok': True})
