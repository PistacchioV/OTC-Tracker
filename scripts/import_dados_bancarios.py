#!/usr/bin/env python3
"""
Import bank accounts from the "dados_bancarios" spreadsheet into the BANKING
model of apps/static/data/CounterpartyDetails.json.

Spreadsheet layout (0-based / Excel column letter):
    A (0) = SPN code
    C (2) = Bank
    D (3) = Agency
    E (4) = Account (CC)

An SPN may own one or several active accounts (one per row). Each account is
stored in the record's BANKING.ACCOUNTS list:

    BANKING: {
        ACCOUNTS: [ {id, bank, agency, account, status, maker, checker} ],
        DEFAULT_PAY:     {current, pending, maker, checker},
        DEFAULT_RECEIVE: {current, pending, maker, checker}
    }

Imported accounts come in as status "Active" (this spreadsheet is the trusted
seed — only accounts registered later on the Reference Data page go through the
maker/checker Pending→Active flow). The import is idempotent and non-destructive:
accounts already present (same bank+agency+account) are kept with their id and
defaults; only genuinely new accounts are appended. When a record ends up with
exactly one account and no default set yet, that account becomes the default for
both PAY and RECEIVE.

⚠️ SPN matching ALWAYS ignores leading zeros on BOTH sides (sheet and JSON):
'000123' and '123' are the same counterparty.

Usage:
    python scripts/import_dados_bancarios.py [path/to/spreadsheet] [--dry-run]

If no path is given, the newest file in ~/Downloads whose name contains
"dados_bancarios" (.xlsx/.xlsm/.xls/.csv) is used.
"""

import os
import sys
import json
import glob
import uuid
import shutil
from datetime import datetime

import pandas as pd

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.normpath(os.path.join(
    _SCRIPT_DIR, '..', 'apps', 'static', 'data', 'CounterpartyDetails.json'))
DOWNLOADS = os.path.expanduser('~/Downloads')

# 0-based column indices
COL_SPN, COL_BANK, COL_AGENCY, COL_ACCOUNT = 0, 2, 3, 4

IMPORT_MAKER = 'IMPORT'        # marker for seed accounts (no human maker/checker)


# ── Helpers ────────────────────────────────────────────────────────────────
def find_spreadsheet():
    pats = []
    for ext in ('xlsx', 'xlsm', 'xls', 'csv'):
        pats += glob.glob(os.path.join(DOWNLOADS, '*.' + ext))
    cands = [p for p in pats
             if 'dados_bancarios' in os.path.basename(p).lower().replace(' ', '_')]
    return max(cands, key=os.path.getmtime) if cands else None


def norm_spn(value):
    """Normalize an SPN for matching: drop spaces, a trailing '.0' and leading
    zeros. '000123' and '123' both -> '123'."""
    s = str(value or '').strip()
    if not s:
        return ''
    if s.endswith('.0'):
        s = s[:-2]
    s = s.lstrip('0')
    return s or '0'


def is_spn(value):
    s = str(value or '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    return s.isdigit()


def cell(row, idx):
    if idx >= len(row):
        return ''
    v = row.iloc[idx]
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ''
    return str(v).strip()


def read_rows(path):
    if path.lower().endswith('.csv'):
        return pd.read_csv(path, header=None, dtype=str, keep_default_na=False)
    return pd.read_excel(path, header=None, dtype=str)


def _acc_key(a):
    return (str(a.get('bank', '')).strip().lower(),
            str(a.get('agency', '')).strip().lower(),
            str(a.get('account', '')).strip().lower())


def _new_account(bank, agency, account):
    return {
        'id': uuid.uuid4().hex[:8],
        'bank': bank, 'agency': agency, 'account': account,
        'status': 'Active',
        'maker': IMPORT_MAKER, 'checker': IMPORT_MAKER,
        'created_at': datetime.now().isoformat(timespec='seconds'),
    }


def _default_slot(existing=None):
    existing = existing or {}
    return {
        'current': existing.get('current') or None,
        'pending': existing.get('pending') or None,
        'maker':   existing.get('maker', ''),
        'checker': existing.get('checker', ''),
    }


# ── Main ───────────────────────────────────────────────────────────────────
def main(argv):
    dry_run = '--dry-run' in argv
    args = [a for a in argv if not a.startswith('--')]
    path = args[0] if args else find_spreadsheet()

    if not path:
        print('ERROR: no spreadsheet given and none matching "dados_bancarios" '
              'found in ~/Downloads.\nUsage: python scripts/import_dados_bancarios.py '
              '[path/to/spreadsheet] [--dry-run]')
        return 2
    if not os.path.exists(path):
        print('ERROR: file not found: ' + path)
        return 2

    print('Reading: ' + path)
    df = read_rows(path)

    # group accounts by normalized SPN
    groups = {}     # nspn -> {'spn': raw, 'accounts': [{bank,agency,account}]}
    rows_seen = 0
    for i in range(len(df)):
        row = df.iloc[i]
        spn_raw = cell(row, COL_SPN)
        if not is_spn(spn_raw):
            continue
        nspn = norm_spn(spn_raw)
        if not nspn:
            continue
        bank = cell(row, COL_BANK)
        agency = cell(row, COL_AGENCY)
        account = cell(row, COL_ACCOUNT)
        if not (bank or agency or account):
            continue
        rows_seen += 1
        g = groups.setdefault(nspn, {'spn': spn_raw.strip(), 'accounts': []})
        acc = {'bank': bank, 'agency': agency, 'account': account}
        if _acc_key(acc) not in {_acc_key(a) for a in g['accounts']}:
            g['accounts'].append(acc)

    total_accounts = sum(len(g['accounts']) for g in groups.values())
    print('Parsed: {} data rows, {} unique SPNs, {} accounts'.format(
        rows_seen, len(groups), total_accounts))

    # load JSON, index by normalized SPN
    with open(JSON_PATH, encoding='utf-8') as fh:
        data = json.load(fh)
    by_nspn = {}
    for rec in data:
        by_nspn.setdefault(norm_spn(rec.get('SPN', '')), rec)

    matched, created, added_accts = 0, 0, 0
    for nspn, g in groups.items():
        rec = by_nspn.get(nspn)
        if rec is None:
            rec = {'SPN': g['spn'], 'COUNTERPARTY': '', 'CGD': [],
                   'BANKING': {}, 'CONTACTS': []}
            data.append(rec)
            by_nspn[nspn] = rec
            created += 1
        else:
            matched += 1

        # normalize the BANKING container, migrating any legacy shape
        bank = rec.get('BANKING')
        if not isinstance(bank, dict):
            bank = {}
        accounts = bank.get('ACCOUNTS')
        if not isinstance(accounts, list):
            accounts = []
            # migrate legacy PAY/RECEIVE lists or flat BANK/AGENCY/ACCOUNT
            legacy = []
            for key in ('PAY', 'RECEIVE'):
                for b in (bank.get(key) or []):
                    legacy.append({'bank': b.get('bank', ''), 'agency': b.get('agency', ''),
                                   'account': b.get('account', '')})
            if not legacy and (rec.get('BANK') or rec.get('AGENCY') or rec.get('ACCOUNT')):
                legacy.append({'bank': rec.get('BANK', ''), 'agency': rec.get('AGENCY', ''),
                               'account': rec.get('ACCOUNT', '')})
            seen = set()
            for a in legacy:
                if any(a.values()) and _acc_key(a) not in seen:
                    seen.add(_acc_key(a))
                    accounts.append(_new_account(a['bank'], a['agency'], a['account']))

        existing_keys = {_acc_key(a): a for a in accounts}
        for a in g['accounts']:
            if _acc_key(a) not in existing_keys:
                accounts.append(_new_account(a['bank'], a['agency'], a['account']))
                added_accts += 1

        dp = _default_slot(bank.get('DEFAULT_PAY'))
        dr = _default_slot(bank.get('DEFAULT_RECEIVE'))
        # auto-default when there is a single account and none chosen yet
        active = [a for a in accounts if str(a.get('status', '')).lower() == 'active']
        if len(active) == 1:
            only = active[0]['id']
            if not dp['current']:
                dp['current'] = only
            if not dr['current']:
                dr['current'] = only

        rec['BANKING'] = {'ACCOUNTS': accounts, 'DEFAULT_PAY': dp, 'DEFAULT_RECEIVE': dr}
        # drop legacy flat keys now folded into ACCOUNTS
        for k in ('BANK', 'AGENCY', 'ACCOUNT'):
            rec.pop(k, None)

    print('Matched existing: {} | new records: {} | new accounts added: {} | JSON total: {}'.format(
        matched, created, added_accts, len(data)))

    if dry_run:
        print('\n[--dry-run] no changes written. Sample of first updated record:')
        print(json.dumps(by_nspn[next(iter(groups))], ensure_ascii=False, indent=2)[:1400])
        return 0

    bak = JSON_PATH + '.' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.bak'
    shutil.copy2(JSON_PATH, bak)
    with open(JSON_PATH, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print('Backup: ' + bak)
    print('Saved:  ' + JSON_PATH)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
