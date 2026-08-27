# -*- coding: utf-8 -*-
"""Counterparty Details — o registro por SPN (CGD, contatos, banking, NET) com
maker/checker por item, e o import da planilha CONTATO DE CLIENTES.

Movido VERBATIM do routes.py. Os LEITORES ficaram lá: `_cpd_path/_cpd_load/
_cpd_find` (summaries, advices, TED e o e-mail de cobrança leem o registro) e
os normalizadores compartilhados `_norm_spn/_bank_norm/_cgd_norm`.
"""
import os
import uuid
from datetime import datetime


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _import_client_contacts(filename, raw_bytes):
    """Parse the spreadsheet bytes and merge contacts into CounterpartyDetails.json.
    Returns a summary dict; raises ValueError on a recoverable input problem."""
    rows = _R()._cc_read_rows(filename, raw_bytes)

    groups = {}                    # nspn -> {'spn', 'name', 'contacts'[]}
    rows_seen = 0
    skipped_email = []             # placeholder addresses left out of the import
    for i in range(_R()._CONTACTS_DATA_START_ROW - 1, len(rows)):
        row = rows[i]
        spn_raw = _R()._cc_cell(row, _R()._CC_SPN)
        nspn = _R()._norm_spn(spn_raw)
        if not nspn:
            continue
        # Only import contacts flagged Active ("A") in column D — inactive rows
        # are ignored entirely (an SPN with no active rows is left untouched).
        if _R()._cc_cell(row, _R()._CC_ACTIVE).upper() != 'A':
            continue
        cname = _R()._cc_cell(row, _R()._CC_CONTACT)
        phone = _R()._cc_cell(row, _R()._CC_PHONE)
        email = _R()._cc_cell(row, _R()._CC_EMAIL)
        rule  = _R()._cc_cell(row, _R()._CC_RULE)
        if not (cname or phone or email or rule):
            continue               # blank contact line
        rows_seen += 1
        # A filled-in but unusable address ('xxx', 'xx@xx.com') means the row
        # carries no way to reach anyone — skip it instead of importing a
        # contact that will bounce.
        if email and not _R()._cc_email_is_usable(email):
            skipped_email.append('%s · %s · %s' % (spn_raw.strip(), cname or '(no name)', email))
            continue
        g = groups.setdefault(nspn, {'spn': spn_raw.strip(), 'name': '', 'contacts': []})
        cp_name = _R()._cc_cell(row, _R()._CC_NAME)
        if cp_name and not g['name']:
            g['name'] = cp_name
        g['contacts'].append({
            'name': cname, 'phone': phone, 'email': email,
            'rules': _R()._cc_parse_rules(rule), 'status': 'Active',
        })

    if not groups:
        raise ValueError('No active contact rows found (data is expected to start at row 5, '
                         'with the SPN in column B and the Active flag "A" in column D).')

    data = _R()._cpd_load()
    by_nspn = {}
    for rec in data:
        by_nspn.setdefault(_R()._norm_spn(rec.get('SPN', '')), rec)

    matched = created = 0
    for nspn, g in groups.items():
        rec = by_nspn.get(nspn)
        if rec is None:
            rec = {'SPN': g['spn'], 'COUNTERPARTY': g['name'], 'CGD': [],
                   'BANKING': {'PAY': [], 'RECEIVE': []}, 'CONTACTS': []}
            data.append(rec)
            by_nspn[nspn] = rec
            created += 1
        else:
            matched += 1
            if g['name'] and not str(rec.get('COUNTERPARTY', '') or '').strip():
                rec['COUNTERPARTY'] = g['name']
        rec['CONTACTS'] = g['contacts']     # replace contacts for this SPN

    # Sweep the WHOLE base, not just the SPNs in this spreadsheet: placeholders
    # imported before this filter existed live under counterparties the current
    # file may not even mention.
    swept = 0
    for rec in data:
        kept, dropped = _R()._cc_drop_placeholder_contacts(rec.get('CONTACTS') or [])
        if dropped:
            rec['CONTACTS'] = kept
            swept += len(dropped)
            for c in dropped:
                _R().log.info('[contacts] swept placeholder %s · %s · %s',
                         rec.get('SPN', ''), c.get('name', ''), c.get('email', ''))

    _R()._cpd_save_list(data)
    if skipped_email:
        _R().log.info('[contacts] %d placeholder e-mail rows skipped on import:\n  %s',
                 len(skipped_email), '\n  '.join(skipped_email))
    return {
        'rows': rows_seen, 'spns': len(groups),
        'contacts': sum(len(g['contacts']) for g in groups.values()),
        'matched': matched, 'created': created, 'total': len(data),
        'skipped_email': len(skipped_email), 'swept': swept,
    }


def _bank_get_record(spn):
    """Return (data, rec, banking) for an SPN, creating the record if needed."""
    data = _R()._cpd_load()
    rec = _R()._cpd_find(data, spn)
    if rec is None:
        rec = {'SPN': str(spn or '').strip(), 'COUNTERPARTY': '', 'CGD': [],
               'BANKING': _R()._bank_norm({}), 'CONTACTS': []}
        data.append(rec)
    rec['BANKING'] = _R()._bank_norm(rec.get('BANKING'))
    return data, rec, rec['BANKING']


def _cpd_get_record(spn):
    """Return (data, rec) for an SPN with CGD/CONTACTS/BANKING/NET normalized; create if missing."""
    data = _R()._cpd_load()
    rec = _R()._cpd_find(data, spn)
    if rec is None:
        rec = {'SPN': str(spn or '').strip(), 'COUNTERPARTY': '', 'CGD': [],
               'BANKING': _R()._bank_norm({}), 'CONTACTS': [], 'NET': _R()._net_norm({})}
        data.append(rec)
    rec['CGD'] = _R()._cgd_norm(rec.get('CGD'))
    rec['CONTACTS'] = _R()._contacts_norm(rec.get('CONTACTS'))
    rec['BANKING'] = _R()._bank_norm(rec.get('BANKING'))
    rec['NET'] = _R()._net_norm(rec.get('NET'))
    return data, rec

def _contact_disp(c):
    if not c:
        return ''
    return (c.get('name') or c.get('email') or c.get('id') or '').strip()

def _acc_disp(acc):
    if not acc:
        return ''
    return (acc.get('bank') or acc.get('account') or acc.get('id') or '').strip()

def _bank_detail(spn, rec, extra=''):
    """Notification detail: 'SPN <spn> · <counterparty> · <extra>'. The leading
    'SPN <spn>' lets the bell deep-link to Reference Data filtered by that SPN."""
    name = str((rec or {}).get('COUNTERPARTY', '') or '').strip()
    head = 'SPN {} · {}'.format(spn, name) if name else 'SPN {}'.format(spn)
    return head + ' · ' + extra if extra else head

def _notify_bank(action, detail):
    """Emit a notification-bell entry for a banking maker/checker action."""
    _R()._create_notification(_R().session.get('user_sid', ''), _R().session.get('user_name', ''),
                         action, 'Reference Data', detail)

def _contact_payload(p):
    rules = p.get('rules')
    if not isinstance(rules, list):
        rules = []
    return {
        'name':   str(p.get('name', '') or '').strip(),
        'phone':  str(p.get('phone', '') or '').strip(),
        'email':  str(p.get('email', '') or '').strip(),
        'rules':  [str(r).strip() for r in rules if str(r).strip()],
        'status': str(p.get('status', 'Active') or 'Active').strip() or 'Active',
    }
