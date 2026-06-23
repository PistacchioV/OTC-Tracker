#!/usr/bin/env python3
"""
Import CGD + Pay/Receive banking details from the "CGD_Bank" spreadsheet into
apps/static/data/CounterpartyDetails.json.

Spreadsheet layout (0-based / Excel column letter):
    H (7)  = SPN code
    N (13) = CGD  (dd/mm/yyyy)
    O (14) = Bank
    P (15) = Agency
    Q (16) = Account (CC)

Each row carries one CGD value and one banking line for an SPN. Rows are grouped
by SPN (leading zeros ignored on BOTH sides, sheet and JSON). For each matched
record:
    - CGD          ← list of the CGD dates seen for that SPN (deduped)
    - BANKING.PAY  ← list of {bank, agency, account} from the rows
    - BANKING.RECEIVE ← SAME list as PAY (mirror, per request)
COUNTERPARTY and CONTACTS are preserved; the legacy flat BANK/AGENCY/ACCOUNT keys
are dropped in favour of the structured BANKING object. SPNs in the sheet but
missing from the JSON are appended as new records. A timestamped .bak of the JSON
is written before saving.

Usage:
    python scripts/import_cgd_bank.py [path/to/spreadsheet] [--dry-run]

If no path is given, the newest file in ~/Downloads whose name contains
"CGD_Bank" (.xlsx/.xlsm/.xls/.csv) is used.
"""

import os
import re
import sys
import json
import glob
import shutil
from datetime import datetime

import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.normpath(os.path.join(
    _SCRIPT_DIR, '..', 'apps', 'static', 'data', 'CounterpartyDetails.json'))
DOWNLOADS = os.path.expanduser('~/Downloads')

# 0-based column indices
COL_SPN, COL_CGD, COL_BANK, COL_AGENCY, COL_ACCOUNT = 7, 13, 14, 15, 16


# ── Helpers ────────────────────────────────────────────────────────────────
def find_spreadsheet():
    pats = []
    for ext in ('xlsx', 'xlsm', 'xls', 'csv'):
        pats += glob.glob(os.path.join(DOWNLOADS, '*.' + ext))
    cands = [p for p in pats
             if 'cgd_bank' in os.path.basename(p).lower().replace(' ', '_')]
    if not cands:
        return None
    return max(cands, key=os.path.getmtime)


def norm_spn(value):
    """Normalize an SPN for matching: drop spaces, a trailing '.0' (pandas reads
    123 as '123.0') and leading zeros. '000123' and '123' both -> '123'."""
    s = str(value or '').strip()
    if not s:
        return ''
    if s.endswith('.0'):
        s = s[:-2]
    s = s.lstrip('0')
    return s or '0'


def is_spn(value):
    """True when the cell looks like an SPN (all digits) — skips header rows."""
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


def fmt_cgd(raw):
    """Coerce a CGD cell to dd/mm/yyyy. Handles already-formatted dd/mm/yyyy,
    ISO datetimes ('2026-06-23 00:00:00' / '2026-06-23') and yyyy/mm/dd."""
    s = str(raw or '').strip()
    if not s:
        return ''
    if s.endswith('.0'):
        s = s[:-2]
    # already dd/mm/yyyy (or dd-mm-yyyy)
    m = re.match(r'^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$', s)
    if m:
        d, mo, y = m.groups()
        return '{:02d}/{:02d}/{}'.format(int(d), int(mo), y)
    # ISO-ish yyyy-mm-dd[ ...]
    m = re.match(r'^(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
    if m:
        y, mo, d = m.groups()
        return '{:02d}/{:02d}/{}'.format(int(d), int(mo), y)
    return s            # leave anything unexpected verbatim


def read_rows(path):
    if path.lower().endswith('.csv'):
        return pd.read_csv(path, header=None, dtype=str, keep_default_na=False)
    return pd.read_excel(path, header=None, dtype=str)


# ── Main ───────────────────────────────────────────────────────────────────
def main(argv):
    dry_run = '--dry-run' in argv
    args = [a for a in argv if not a.startswith('--')]
    path = args[0] if args else find_spreadsheet()

    if not path:
        print('ERROR: no spreadsheet given and none matching "CGD_Bank" found in '
              '~/Downloads.\nUsage: python scripts/import_cgd_bank.py '
              '[path/to/spreadsheet] [--dry-run]')
        return 2
    if not os.path.exists(path):
        print('ERROR: file not found: ' + path)
        return 2

    print('Reading: ' + path)
    df = read_rows(path)

    # group CGD + banking lines by normalized SPN
    groups = {}     # nspn -> {'spn': raw, 'cgd': [..], 'banks': [{bank,agency,account}]}
    rows_seen = 0
    for i in range(len(df)):
        row = df.iloc[i]
        spn_raw = cell(row, COL_SPN)
        if not is_spn(spn_raw):
            continue                          # header / blank / non-SPN row
        nspn = norm_spn(spn_raw)
        if not nspn:
            continue
        rows_seen += 1
        g = groups.setdefault(nspn, {'spn': spn_raw.strip(), 'cgd': [], 'banks': []})

        cgd = fmt_cgd(cell(row, COL_CGD))
        if cgd and cgd not in g['cgd']:
            g['cgd'].append(cgd)

        bank = cell(row, COL_BANK)
        agency = cell(row, COL_AGENCY)
        account = cell(row, COL_ACCOUNT)
        if bank or agency or account:
            entry = {'bank': bank, 'agency': agency, 'account': account}
            if entry not in g['banks']:
                g['banks'].append(entry)

    print('Parsed: {} data rows, {} unique SPNs'.format(rows_seen, len(groups)))

    # load JSON and index by normalized SPN
    with open(JSON_PATH, encoding='utf-8') as fh:
        data = json.load(fh)
    by_nspn = {}
    for rec in data:
        by_nspn.setdefault(norm_spn(rec.get('SPN', '')), rec)

    matched, created = 0, 0
    for nspn, g in groups.items():
        rec = by_nspn.get(nspn)
        if rec is None:
            rec = {'SPN': g['spn'], 'COUNTERPARTY': '', 'CGD': [],
                   'BANKING': {'PAY': [], 'RECEIVE': []}, 'CONTACTS': []}
            data.append(rec)
            by_nspn[nspn] = rec
            created += 1
        else:
            matched += 1

        # preserve COUNTERPARTY + CONTACTS; structure the rest
        rec['COUNTERPARTY'] = str(rec.get('COUNTERPARTY', '') or '')
        contacts = rec.get('CONTACTS', [])
        rec['CONTACTS'] = contacts if isinstance(contacts, list) else []
        # drop legacy flat banking keys
        for k in ('BANK', 'AGENCY', 'ACCOUNT'):
            rec.pop(k, None)

        if g['cgd']:
            rec['CGD'] = g['cgd']
        if g['banks']:
            # PAY and RECEIVE mirror the same banking lines (per request)
            rec['BANKING'] = {'PAY': list(g['banks']),
                              'RECEIVE': [dict(b) for b in g['banks']]}

    print('Matched existing: {} | new records appended: {} | JSON total: {}'.format(
        matched, created, len(data)))

    if dry_run:
        print('\n[--dry-run] no changes written. Sample of first updated record:')
        sample_nspn = next(iter(groups))
        print(json.dumps(by_nspn[sample_nspn], ensure_ascii=False, indent=2)[:1200])
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
