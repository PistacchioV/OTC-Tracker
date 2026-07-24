#!/usr/bin/env python3
"""Remove placeholder contacts from CounterpartyDetails.json.

The 'CONTATO DE CLIENTES' spreadsheet is filled by hand, so a contact with no
real address often carries a stand-in instead of a blank cell: 'xxx', 'x-x', and
— the ones that slip through a naive check — strings that ARE valid e-mail
syntax but address nobody, like 'xx@xx.com'. Confirmations sent there bounce.

The import route filters these out going forward; this script cleans what is
already stored. It reuses the exact predicate from apps/pages/routes.py, so the
two can never drift apart.

Usage
-----
    python scripts/clean_placeholder_contacts.py            # dry run (default)
    python scripts/clean_placeholder_contacts.py --apply    # write the changes

A timestamped .bak of the JSON is written before any change.
"""
import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(ROOT, 'apps', 'static', 'data', 'CounterpartyDetails.json')
ROUTES_PATH = os.path.join(ROOT, 'apps', 'pages', 'routes.py')


def load_predicate():
    """Pull _cc_email_is_usable straight out of routes.py.

    Importing the module would pull in Flask, DuckDB and the whole app; the
    filter block is self-contained, so exec'ing just that slice keeps this
    script runnable anywhere while guaranteeing identical behaviour."""
    src = open(ROUTES_PATH, encoding='utf-8').read()
    try:
        start = src.index('_CC_EMAIL_RE = re.compile')
        end = src.index('def _cc_parse_rules')
    except ValueError:
        sys.exit('Could not locate the placeholder-filter block in routes.py — '
                 'it was probably renamed. Fix this script before running it.')
    ns = {'re': re}
    exec(src[start:end], ns)
    return ns['_cc_email_is_usable']


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--apply', action='store_true',
                    help='write the cleaned file (default is a dry run)')
    ap.add_argument('--json', default=JSON_PATH, help='path to CounterpartyDetails.json')
    args = ap.parse_args()

    is_usable = load_predicate()

    with open(args.json, encoding='utf-8') as fh:
        data = json.load(fh)

    dropped = []
    total_contacts = 0
    for rec in data:
        contacts = rec.get('CONTACTS') or []
        total_contacts += len(contacts)
        kept = []
        for c in contacts:
            email = str((c or {}).get('email', '') or '').strip()
            # A blank e-mail is not a placeholder — leave those contacts alone.
            if email and not is_usable(email):
                dropped.append((rec.get('SPN', ''), rec.get('COUNTERPARTY', ''),
                                c.get('name', ''), email))
            else:
                kept.append(c)
        rec['CONTACTS'] = kept

    print('Counterparties: %d   Contacts: %d' % (len(data), total_contacts))
    print('Placeholder contacts found: %d\n' % len(dropped))
    if dropped:
        w = max(len(d[3]) for d in dropped)
        print('  %-10s %-*s %s' % ('SPN', w, 'E-MAIL', 'CONTACT / COUNTERPARTY'))
        for spn, cp, name, email in sorted(dropped):
            print('  %-10s %-*s %s' % (spn, w, email, (name or '(no name)') + ' — ' + cp[:40]))
        print()

    if not args.apply:
        print('Dry run — nothing written. Re-run with --apply to remove them.')
        return

    if not dropped:
        print('Nothing to remove.')
        return

    bak = '%s.%s.bak' % (args.json, datetime.now().strftime('%Y%m%d-%H%M%S'))
    shutil.copy2(args.json, bak)
    with open(args.json, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print('Removed %d contacts.\nBackup: %s' % (len(dropped), bak))


if __name__ == '__main__':
    main()
