"""
import_pending_confirmation.py
------------------------------
Load "PENDING - Outstanding Confirmation OTC.xlsx" (dropped in this scripts/
folder on the production box) into three DuckDB databases under
apps/static/data/db, split by the row's trade-date age and status:

  pending-confirmation-backlog.db : Trade Date OLDER than 12 months from today
                                    (any status)
  pending-confirmation-ok.db      : Status == 'Ok'  AND Trade Date within 12 months
  pending-confirmation-pending.db : Status != 'Ok'  AND Trade Date within 12 months

Each DB has a single table `pending_confirmation` whose columns are the Pending
Confirmation PAGE columns:
  Status, LOB, SPN, Client, Aging, Product Type, Trade Date, Maturity Date,
  Trade Number, Pending Status, Owner, EA, Send Date, Return Date, Break Reason,
  Comments, Economic Group, Signature Type, FepWeb ID, Baixa Sem Abono,
  Pendência, Abono

Details
  - SPN is NOT in the spreadsheet: it is looked up from RefData.json by matching
    the Client name against COUNTERPARTY (accent/case-insensitive).
  - Aging = whole days between today and the Trade Date (today - trade date).
  - Date columns are stored as dd/mm/yyyy strings so the page's smart filter
    (and its date-type detection) reads them directly.

Usage
    python scripts/import_pending_confirmation.py
    python scripts/import_pending_confirmation.py --xlsx "C:\\path\\to\\file.xlsx"
    python scripts/import_pending_confirmation.py --dry-run        # parse + report only
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime

from dateutil.relativedelta import relativedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
DB_DIR = os.path.join(REPO_ROOT, 'apps', 'static', 'data', 'db')
REFDATA_PATH = os.path.join(REPO_ROOT, 'apps', 'static', 'data', 'RefData.json')
DEFAULT_XLSX = os.path.join(SCRIPT_DIR, 'PENDING - Outstanding Confirmation OTC.xlsx')

DB_FILES = {
    'backlog': os.path.join(DB_DIR, 'pending-confirmation-backlog.db'),
    'pending': os.path.join(DB_DIR, 'pending-confirmation-pending.db'),
    'ok':      os.path.join(DB_DIR, 'pending-confirmation-ok.db'),
}
TABLE = 'pending_confirmation'

# Page columns, in display order — these become the DB columns.
PAGE_COLUMNS = [
    'Status', 'LOB', 'SPN', 'Client', 'Aging', 'Product Type', 'Trade Date',
    'Maturity Date', 'Trade Number', 'Pending Status', 'Owner', 'EA', 'Send Date',
    'Return Date', 'Break Reason', 'Comments', 'Economic Group', 'Signature Type',
    'FepWeb ID', 'Baixa Sem Abono', 'Pendência', 'Abono',
]

# page column -> the spreadsheet header it comes from. SPN and Aging are derived
# (SPN looked up from RefData, Aging computed), so they are not mapped here.
PAGE_FROM_SHEET = {
    'Status': 'Status',
    'LOB': 'LOB',
    'Client': 'Client',
    'Product Type': 'Product Type',
    'Trade Date': 'Trade Date',
    'Maturity Date': 'Maturity Date',
    'Trade Number': 'Trade Number',
    'Pending Status': 'Pending Status',
    'Owner': 'Owner',
    'EA': 'EA',
    'Send Date': 'JP sending documentation',
    'Return Date': 'Client return the document',
    'Break Reason': 'Break Reason',
    'Comments': 'Overall Comments',
    'Economic Group': 'Economic Group',
    'Signature Type': 'Signature Type',
    'FepWeb ID': 'Trade Number IS FEP WEB',
    'Baixa Sem Abono': 'Baixa Sem Abono',
    'Pendência': 'Pendência',
    'Abono': 'Abono',
}

# The spreadsheet's actual column order (as delivered). Resolution is by HEADER
# NAME first (order-independent); this order is only a POSITIONAL fallback used
# when a header name can't be matched (e.g. a slightly different wording).
SHEET_ORDER = [
    'LOB', 'Client', 'Aging', 'Status', 'Product Type', 'Trade Date',
    'Maturity Date', 'Trade Number', 'Pending Status', 'Owner', 'EA',
    'JP sending documentation', 'Client return the document', 'Break Reason',
    'Overall Comments', 'Economic Group', 'Signature Type',
    'Trade Number IS FEP WEB', 'Baixa Sem Abono', 'Pendência', 'Abono',
]

# Columns whose values are dates → stored dd/mm/yyyy for the smart filter.
DATE_COLUMNS = {'Trade Date', 'Maturity Date', 'EA', 'Send Date', 'Return Date',
                'Baixa Sem Abono', 'Pendência', 'Abono'}


def _norm(s):
    """Accent/case-insensitive, non-alphanumeric-stripped key for matching."""
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]', '', s.lower())


def load_spn_map():
    """{normalized COUNTERPARTY name -> SPN} from RefData.json."""
    try:
        data = json.load(open(REFDATA_PATH, encoding='utf-8'))
    except Exception as exc:
        print('WARNING: could not read RefData.json ({}): {}'.format(REFDATA_PATH, exc))
        return {}
    out = {}
    for r in data:
        nm = _norm(r.get('COUNTERPARTY', ''))
        spn = str(r.get('SPN', '') or '').strip()
        if nm and spn and nm not in out:
            out[nm] = spn
    return out


def _to_date(v):
    """Parse a spreadsheet cell into a date, or None."""
    if v is None or v == '':
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s or s.lower() in ('nan', 'nat', 'none'):
        return None
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d/%m/%y', '%m/%d/%Y',
                '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M:%S'):
        try:
            return datetime.strptime(s.split('.')[0], fmt).date()
        except ValueError:
            continue
    return None


def _fmt_date(v):
    """dd/mm/yyyy for a date-ish cell; '' when it isn't a date."""
    d = _to_date(v)
    return d.strftime('%d/%m/%Y') if d else ''


def _cell(v):
    """Plain string for a non-date cell ('' for blanks/NaN)."""
    if v is None:
        return ''
    s = str(v).strip()
    if s.lower() in ('nan', 'nat', 'none'):
        return ''
    # openpyxl/pandas often bring integers as '123.0' → drop the trailing .0
    if re.fullmatch(r'-?\d+\.0', s):
        s = s[:-2]
    return s


def _resolve_headers(df_columns):
    """Map each spreadsheet source header name to the actual df column. Resolve by
    normalized HEADER NAME first (so column order doesn't matter); fall back to the
    column at that name's position in SHEET_ORDER when the name isn't found.
    Returns {source_name: df_column or None}."""
    df_columns = list(df_columns)
    norm_to_col = {}
    for c in df_columns:
        norm_to_col.setdefault(_norm(c), c)
    resolved = {}
    for src in set(PAGE_FROM_SHEET.values()):
        col = norm_to_col.get(_norm(src))
        if col is None and src in SHEET_ORDER:
            idx = SHEET_ORDER.index(src)
            if 0 <= idx < len(df_columns):
                col = df_columns[idx]
        resolved[src] = col
    return resolved


def build_rows(xlsx_path, spn_map, today):
    import pandas as pd
    df = pd.read_excel(xlsx_path, dtype=object)
    df = df.where(df.notna(), None)
    src_col = _resolve_headers(list(df.columns))

    missing = [s for s, c in src_col.items() if c is None]
    if missing:
        print('WARNING: spreadsheet is missing expected column(s): {}'.format(', '.join(sorted(missing))))

    cutoff = today - relativedelta(months=12)      # 12 months ago (calendar)
    buckets = {'backlog': [], 'pending': [], 'ok': []}
    unmatched_spn = set()

    for _, r in df.iterrows():
        def sheet(name):
            col = src_col.get(name)
            return r.get(col) if col is not None else None

        client = _cell(sheet('Client'))
        # SPN from RefData by Client name.
        spn = spn_map.get(_norm(client), '')
        if client and not spn:
            unmatched_spn.add(client)

        trade_raw = sheet('Trade Date')
        trade_date = _to_date(trade_raw)
        aging = str((today - trade_date).days) if trade_date else ''

        row = {}
        for page_col in PAGE_COLUMNS:
            if page_col == 'SPN':
                row[page_col] = spn
            elif page_col == 'Aging':
                row[page_col] = aging
            elif page_col == 'Client':
                row[page_col] = client
            else:
                val = sheet(PAGE_FROM_SHEET[page_col])
                row[page_col] = _fmt_date(val) if page_col in DATE_COLUMNS else _cell(val)

        # Route the row to a bucket.
        status_ok = _norm(row['Status']) == 'ok'
        if trade_date is not None and trade_date < cutoff:
            buckets['backlog'].append(row)
        elif status_ok:
            buckets['ok'].append(row)
        else:
            buckets['pending'].append(row)

    return buckets, unmatched_spn


def write_db(path, rows):
    import duckdb
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cols_ddl = ', '.join('"{}" VARCHAR'.format(c) for c in PAGE_COLUMNS)
    con = duckdb.connect(path)
    try:
        con.execute('DROP TABLE IF EXISTS {}'.format(TABLE))
        con.execute('CREATE TABLE {} ({})'.format(TABLE, cols_ddl))
        if rows:
            placeholders = ', '.join('?' for _ in PAGE_COLUMNS)
            con.executemany(
                'INSERT INTO {} VALUES ({})'.format(TABLE, placeholders),
                [[r.get(c, '') for c in PAGE_COLUMNS] for r in rows])
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser(
        description='Load the Pending Confirmation spreadsheet into the three '
                    'backlog/pending/ok DuckDB databases.')
    ap.add_argument('--xlsx', default=DEFAULT_XLSX,
                    help='Path to the PENDING - Outstanding Confirmation OTC.xlsx '
                         '(default: this scripts/ folder).')
    ap.add_argument('--db-dir', default=DB_DIR, help='Destination db folder.')
    ap.add_argument('--dry-run', action='store_true',
                    help='Parse and report the split without writing the databases.')
    args = ap.parse_args()

    if not os.path.isfile(args.xlsx):
        sys.exit('ERROR: spreadsheet not found: {}'.format(args.xlsx))

    today = date.today()
    spn_map = load_spn_map()
    print('Spreadsheet : {}'.format(args.xlsx))
    print('RefData SPNs: {}'.format(len(spn_map)))
    print('Today       : {}  (12-month cutoff = {})'.format(
        today.strftime('%d/%m/%Y'), (today - relativedelta(months=12)).strftime('%d/%m/%Y')))
    print('-' * 70)

    buckets, unmatched = build_rows(args.xlsx, spn_map, today)
    for name in ('backlog', 'pending', 'ok'):
        print('{:<8}: {} row(s)'.format(name, len(buckets[name])))
    if unmatched:
        print('Clients with NO SPN match ({}): {}'.format(
            len(unmatched), ', '.join(sorted(unmatched)[:15]) + ('…' if len(unmatched) > 15 else '')))

    if args.dry_run:
        print('\nDRY-RUN — no databases written.')
        return

    db_files = {k: os.path.join(args.db_dir, os.path.basename(v)) for k, v in DB_FILES.items()}
    for name in ('backlog', 'pending', 'ok'):
        write_db(db_files[name], buckets[name])
        print('wrote {} ({} rows)'.format(db_files[name], len(buckets[name])))
    print('\nDone.')


if __name__ == '__main__':
    main()
