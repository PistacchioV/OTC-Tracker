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
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# routes.py imports awmpy; provide a no-op fallback if it isn't installed.
try:
    import awmpy  # noqa: F401
except ImportError:
    import types as _types
    _stub = _types.ModuleType('awmpy')
    _stub.get_phonebook_data = lambda *a, **k: {}
    sys.modules['awmpy'] = _stub

from apps.pages import routes as R


def main():
    ap = argparse.ArgumentParser(description='Daily Pending Confirmation maintenance + snapshot.')
    ap.add_argument('--no-snapshot', action='store_true', help='Skip the daily JSON snapshot.')
    ap.add_argument('--dry-run', action='store_true', help='Report the re-routing without writing.')
    args = ap.parse_args()

    today = datetime.now().date()
    print('Today: {}'.format(today.strftime('%d/%m/%Y')))

    if args.dry_run:
        # Report only — mirror the re-route without writing.
        seen, all_rows = set(), []
        for cat in ('backlog', 'pending', 'ok'):
            for r in R._pc_load_rows(cat):
                tn = str(r.get('Trade Number', '') or '')
                key = tn or ('#' + str(len(all_rows)))
                if key in seen:
                    continue
                seen.add(key)
                all_rows.append(r)
        counts = {'backlog': 0, 'pending': 0, 'ok': 0}
        for r in all_rows:
            counts[R._pc_target_category(r)] += 1
        for cat in ('backlog', 'pending', 'ok'):
            print('  {:<8}: {}'.format(cat, counts[cat]))
        print('\nDRY-RUN — nothing written.')
        return

    # Reuse the exact maintenance the in-app 11:30 scheduler runs.
    buckets = R._pc_run_daily_maintenance(snapshot=not args.no_snapshot)
    if buckets is None:
        # Uma das três leituras falhou e NADA foi reescrito — reescrever por
        # cima de uma leitura falhada apagaria o balde (ver o docstring da
        # manutenção). O motivo está no log acima.
        print('\nABORTED: could not read one of the DBs — nothing was rewritten.')
        sys.exit(1)
    for cat in ('backlog', 'pending', 'ok'):
        print('  {:<8}: {}'.format(cat, len(buckets[cat])))
    print('\nDone.')


if __name__ == '__main__':
    main()
