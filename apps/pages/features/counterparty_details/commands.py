# -*- coding: utf-8 -*-
"""As escritas do Counterparty Details — o import da planilha CONTATO DE
CLIENTES (parse → merge → varredura de placeholders → grava) e o aviso do sino
das ações de maker/checker. O parse campo a campo (`_cc_*`) e a gravação
(`_cpd_save_list`) são da `platform/counterparty.py`, por busca atrasada.
"""


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


def _notify_bank(action, detail):
    """Emit a notification-bell entry for a banking maker/checker action."""
    _R()._create_notification(_R().session.get('user_sid', ''), _R().session.get('user_name', ''),
                         action, 'Reference Data', detail)
