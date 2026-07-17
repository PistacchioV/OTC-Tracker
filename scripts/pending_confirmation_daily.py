"""
pending_confirmation_daily.py
-----------------------------
Daily maintenance for the Pending Confirmation databases. Run once a day.

For every row across the three DBs (backlog / pending / ok) it:
  - recomputes Aging = today - Trade Date and the Status band label;
  - re-routes the row to the DB it now belongs to:
      * Trade Date older than 12 months  -> backlog
      * Pending Status resolved ('Concluded')  -> ok
      * otherwise -> pending
  - rewrites the three DBs with their current rows.

It then saves a JSON "photo" of the PENDING DB under
  apps/static/data/cache/pending-confirmation/YYYY/MM/DD/pending-confirmation_YYYYMMDD.json
(year/month/day like the other caches) so a metrics page can read the history.

Reuses the exact logic from apps/pages/routes.py so the daily job can never drift
from the live app.

Usage
    python scripts/pending_confirmation_daily.py
    python scripts/pending_confirmation_daily.py --no-snapshot   # only re-route/refresh
    python scripts/pending_confirmation_daily.py --dry-run       # report only
"""
import argparse
import json
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# routes.py imports awmpy (JPM-internal); present in production, stubbed off-env.
try:
    import awmpy  # noqa: F401
except ImportError:
    import types as _types
    _stub = _types.ModuleType('awmpy')
    _stub.get_phonebook_data = lambda *a, **k: {}
    sys.modules['awmpy'] = _stub

import duckdb
from apps.pages import routes as R


def _rewrite_db(category, rows):
    path = os.path.join(R._PC_DB_DIR, R._PC_DBS[category])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cols_ddl = ', '.join('"{}" VARCHAR'.format(c) for c in R._PC_COLUMNS)
    con = duckdb.connect(path)
    try:
        con.execute('DROP TABLE IF EXISTS {}'.format(R._PC_TABLE))
        con.execute('CREATE TABLE {} ({})'.format(R._PC_TABLE, cols_ddl))
        if rows:
            placeholders = ', '.join('?' for _ in R._PC_COLUMNS)
            con.executemany(
                'INSERT INTO {} VALUES ({})'.format(R._PC_TABLE, placeholders),
                [[r.get(c, '') for c in R._PC_COLUMNS] for r in rows])
    finally:
        con.close()


def _snapshot(rows_pending, today):
    y, m, dd = today.strftime('%Y'), today.strftime('%m'), today.strftime('%d')
    out_dir = os.path.join(R._PC_SNAPSHOT_DIR, y, m, dd)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'pending-confirmation_{}.json'.format(today.strftime('%Y%m%d')))
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(rows_pending, fh, ensure_ascii=False, indent=2)
    return path


def main():
    ap = argparse.ArgumentParser(description='Daily Pending Confirmation maintenance + snapshot.')
    ap.add_argument('--no-snapshot', action='store_true', help='Skip the daily JSON snapshot.')
    ap.add_argument('--dry-run', action='store_true', help='Report the re-routing without writing.')
    args = ap.parse_args()

    today = datetime.now().date()

    # Collect every row (deduped by Trade Number), refreshed, then re-routed.
    seen, all_rows = set(), []
    for cat in ('backlog', 'pending', 'ok'):
        for r in R._pc_load_rows(cat):        # _pc_load_rows already refreshes Aging/Status
            tn = str(r.get('Trade Number', '') or '')
            key = tn or ('#' + str(len(all_rows)))
            if key in seen:
                continue
            seen.add(key)
            all_rows.append(r)

    buckets = {'backlog': [], 'pending': [], 'ok': []}
    for r in all_rows:
        buckets[R._pc_target_category(r)].append(r)

    print('Today   : {}'.format(today.strftime('%d/%m/%Y')))
    print('Total   : {} row(s)'.format(len(all_rows)))
    for cat in ('backlog', 'pending', 'ok'):
        print('  {:<8}: {}'.format(cat, len(buckets[cat])))

    if args.dry_run:
        print('\nDRY-RUN — nothing written.')
        return

    for cat in ('backlog', 'pending', 'ok'):
        _rewrite_db(cat, buckets[cat])
    print('re-routed and rewrote the three DBs.')

    if not args.no_snapshot:
        path = _snapshot(buckets['pending'], today)
        print('snapshot: {} ({} rows)'.format(path, len(buckets['pending'])))

    print('\nDone.')


if __name__ == '__main__':
    main()
