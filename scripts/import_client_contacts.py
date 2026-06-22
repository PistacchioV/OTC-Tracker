#!/usr/bin/env python3
"""
Import client contacts from the "CONTATO DE CLIENTES" spreadsheet into
apps/static/data/CounterpartyDetails.json.

Spreadsheet layout — data starts at row 5:
    B = SPN code              E = contact name
    C = counterparty name     F = phone number
    D = active flag ("A")     G = e-mail
                              H = Rule (what the contact is used for)

Each spreadsheet row is ONE contact. Rows are grouped by SPN and written to the
record's CONTACTS array as {name, phone, email, rules[], status}. Matching is by
SPN with leading zeros ignored on BOTH sides (spreadsheet and JSON).

For a matched SPN, CONTACTS is replaced by the imported list; CGD and BANKING are
preserved. SPNs present in the sheet but missing from the JSON are appended as new
records. A timestamped .bak of the JSON is written before saving.

Usage:
    python scripts/import_client_contacts.py [path/to/spreadsheet] [--dry-run]

If no path is given, the newest file in ~/Downloads whose name contains
"CONTATO DE CLIENTES" (.xlsx/.xlsm/.xls/.csv) is used.
"""

import os
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

DATA_START_ROW = 5            # 1-based; first data row in the sheet
# 0-based column indices
COL_SPN, COL_NAME, COL_ACTIVE, COL_CONTACT, COL_PHONE, COL_EMAIL, COL_RULE = 1, 2, 3, 4, 5, 6, 7

# Map spreadsheet rule labels → the canonical rules used by the Reference Data
# editor (so the Settlement/Negotiation view lines match). Unknown values are
# kept verbatim (title-cased).
_RULE_MAP = {
    'NEGOTIATION': 'Negotiation', 'NEGOCIACAO': 'Negotiation', 'NEGOCIAÇÃO': 'Negotiation',
    'REPURCHASE': 'Repurchase', 'RECOMPRA': 'Repurchase',
    'SETTLEMENT': 'Settlement', 'LIQUIDACAO': 'Settlement', 'LIQUIDAÇÃO': 'Settlement',
    'CONFIRMATION LETTER': 'Confirmation Letter', 'CARTA DE CONFIRMACAO': 'Confirmation Letter',
    'CARTA DE CONFIRMAÇÃO': 'Confirmation Letter',
    'SETTLEMENT ADVICE': 'Settlement Advice', 'AVISO DE LIQUIDACAO': 'Settlement Advice',
    'AVISO DE LIQUIDAÇÃO': 'Settlement Advice',
    'CONTACT CONFIRMATION': 'Contact Confirmation', 'CONFIRMACAO DE CONTATO': 'Contact Confirmation',
    'IOF': 'IOF',
}


# ── Helpers ────────────────────────────────────────────────────────────────
def find_spreadsheet():
    pats = []
    for ext in ('xlsx', 'xlsm', 'xls', 'csv'):
        pats += glob.glob(os.path.join(DOWNLOADS, '*.' + ext))
    cands = [p for p in pats if 'contato de clientes' in os.path.basename(p).lower()]
    if not cands:
        return None
    return max(cands, key=os.path.getmtime)


def norm_spn(value):
    """Normalize an SPN for matching: drop surrounding spaces, a trailing '.0'
    (when read as a number) and leading zeros. '000123' and '123' both -> '123'."""
    s = str(value or '').strip()
    if not s:
        return ''
    if s.endswith('.0'):                 # pandas may read 123 as '123.0'
        s = s[:-2]
    s = s.lstrip('0')
    return s or '0'


def cell(row, idx):
    if idx >= len(row):
        return ''
    v = row.iloc[idx]
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ''
    return str(v).strip()


def parse_rules(raw):
    out, seen = [], set()
    for part in str(raw or '').replace('\n', ';').replace('/', ';').replace(',', ';').split(';'):
        p = part.strip()
        if not p:
            continue
        canon = _RULE_MAP.get(p.upper(), p)
        if canon.upper() not in seen:
            seen.add(canon.upper())
            out.append(canon)
    return out


def read_rows(path):
    if path.lower().endswith('.csv'):
        df = pd.read_csv(path, header=None, dtype=str, keep_default_na=False)
    else:
        df = pd.read_excel(path, header=None, dtype=str)
    return df


# ── Main ───────────────────────────────────────────────────────────────────
def main(argv):
    dry_run = '--dry-run' in argv
    args = [a for a in argv if not a.startswith('--')]
    path = args[0] if args else find_spreadsheet()

    if not path:
        print('ERROR: no spreadsheet given and none matching "CONTATO DE CLIENTES" '
              'found in ~/Downloads.\nUsage: python scripts/import_client_contacts.py '
              '[path/to/spreadsheet] [--dry-run]')
        return 2
    if not os.path.exists(path):
        print('ERROR: file not found: ' + path)
        return 2

    print('Reading: ' + path)
    df = read_rows(path)

    # group contacts by normalized SPN
    groups = {}     # nspn -> {'spn': raw, 'name': str, 'contacts': [..]}
    rows_seen = 0
    for i in range(DATA_START_ROW - 1, len(df)):
        row = df.iloc[i]
        spn_raw = cell(row, COL_SPN)
        nspn = norm_spn(spn_raw)
        if not nspn:
            continue
        rows_seen += 1
        g = groups.setdefault(nspn, {'spn': spn_raw.strip(), 'name': '', 'contacts': []})
        cp_name = cell(row, COL_NAME)
        if cp_name and not g['name']:
            g['name'] = cp_name
        cname = cell(row, COL_CONTACT)
        phone = cell(row, COL_PHONE)
        email = cell(row, COL_EMAIL)
        rule = cell(row, COL_RULE)
        if not (cname or phone or email or rule):
            continue            # blank contact line
        status = 'Active' if cell(row, COL_ACTIVE).upper() == 'A' else 'Inactive'
        g['contacts'].append({
            'name': cname, 'phone': phone, 'email': email,
            'rules': parse_rules(rule), 'status': status,
        })

    total_contacts = sum(len(g['contacts']) for g in groups.values())
    print('Parsed: {} data rows, {} unique SPNs, {} contacts'.format(
        rows_seen, len(groups), total_contacts))

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

    print('Matched existing: {} | new records appended: {} | JSON total: {}'.format(
        matched, created, len(data)))

    if dry_run:
        print('\n[--dry-run] no changes written. Sample of first updated record:')
        sample_nspn = next(iter(groups))
        print(json.dumps(by_nspn[sample_nspn], ensure_ascii=False, indent=2)[:1200])
        return 0

    # backup then write
    bak = JSON_PATH + '.' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.bak'
    shutil.copy2(JSON_PATH, bak)
    with open(JSON_PATH, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print('Backup: ' + bak)
    print('Saved:  ' + JSON_PATH)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
