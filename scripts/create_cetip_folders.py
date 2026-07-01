"""
create_cetip_folders.py
------------------------
Pre-creates the dated source folders the CETIP file-saving routine looks in.

The routine reads the daily B3 files from:
    CETIP_SOURCE_ROOT\\{YYYY}\\{MM. MonthName}\\{DD}
(see apps/pages/routes.py — CETIP_SOURCE_ROOT / api_cp_cetip_settlement). This
script creates one folder per ANBIMA **business day** (weekends and ANBIMA
holidays are skipped) so the folders exist ahead of time for the daily drop.

Folder layout matches the routine exactly:
    2026\\06. June\\30

The ANBIMA holiday calendar is read from apps/static/data/anbima.json (the same
file routes.py loads). Weekdays not in that list are treated as business days.

Usage
    # whole current year
    python scripts/create_cetip_folders.py

    # a specific year (or several)
    python scripts/create_cetip_folders.py --year 2026
    python scripts/create_cetip_folders.py --year 2026 2027

    # an explicit date range (inclusive)
    python scripts/create_cetip_folders.py --start 2026-01-01 --end 2026-12-31

    # override the root (else $CETIP_SOURCE_ROOT, else the routes.py default)
    python scripts/create_cetip_folders.py --root "D:\\CETIP\\ARQUIVOS CETIP"

    # preview without creating anything
    python scripts/create_cetip_folders.py --year 2026 --dry-run
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta

# ── paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.dirname(SCRIPT_DIR)
ANBIMA_JSON = os.path.join(REPO_ROOT, 'apps', 'static', 'data', 'anbima.json')

# Same default as apps/pages/routes.py (CETIP_SOURCE_ROOT). Overridable via the
# CETIP_SOURCE_ROOT env var or the --root flag.
DEFAULT_ROOT = os.getenv(
    'CETIP_SOURCE_ROOT',
    r'I:\Confirmation\Derivativos\OTC Tracker\Alteryx\Posição B3\ARQUIVOS CETIP')

# Same month labels as routes.py (_EN_MONTH_NAMES).
EN_MONTH_NAMES = (
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
)


# ── ANBIMA calendar ──────────────────────────────────────────────────────────

def load_anbima_holidays():
    """Set of 'YYYY-MM-DD' ANBIMA holiday strings (same source as routes.py)."""
    try:
        with open(ANBIMA_JSON, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        return {d['date'] for d in data}
    except Exception as exc:
        sys.exit('ERROR: could not read ANBIMA calendar ({}): {}'.format(ANBIMA_JSON, exc))


def is_business_day(d, holidays):
    """Weekday (Mon-Fri) and not an ANBIMA holiday."""
    return d.weekday() < 5 and d.strftime('%Y-%m-%d') not in holidays


# ── folder building ──────────────────────────────────────────────────────────

def day_folder(root, d):
    """Absolute path for a single day: root\\YYYY\\MM. Month\\DD."""
    month_folder = '{:02d}. {}'.format(d.month, EN_MONTH_NAMES[d.month - 1])
    return os.path.join(root, '{:04d}'.format(d.year), month_folder, '{:02d}'.format(d.day))


def daterange(start, end):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def parse_ymd(s):
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        sys.exit("ERROR: invalid date '{}' (expected YYYY-MM-DD).".format(s))


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description='Create year/month/day CETIP source folders for ANBIMA business days.')
    ap.add_argument('--year', nargs='+', type=int,
                    help='One or more years to create in full (e.g. --year 2026 2027).')
    ap.add_argument('--start', help='Range start date YYYY-MM-DD (inclusive).')
    ap.add_argument('--end', help='Range end date YYYY-MM-DD (inclusive).')
    ap.add_argument('--root', default=DEFAULT_ROOT,
                    help='Source root (default: $CETIP_SOURCE_ROOT or the routes.py default).')
    ap.add_argument('--dry-run', action='store_true',
                    help='List the folders that would be created without creating them.')
    args = ap.parse_args()

    # Resolve the date range.
    if args.start or args.end:
        if not (args.start and args.end):
            sys.exit('ERROR: --start and --end must be provided together.')
        start, end = parse_ymd(args.start), parse_ymd(args.end)
        if start > end:
            sys.exit('ERROR: --start is after --end.')
    elif args.year:
        years = sorted(set(args.year))
        start = date(years[0], 1, 1)
        end = date(years[-1], 12, 31)
    else:
        today = date.today()
        start = date(today.year, 1, 1)
        end = date(today.year, 12, 31)

    holidays = load_anbima_holidays()

    print('Root      : {}'.format(args.root))
    print('Range     : {} → {}  (business days only, ANBIMA)'.format(start, end))
    print('Mode      : {}'.format('DRY-RUN (nothing written)' if args.dry_run else 'CREATE'))
    print('-' * 70)

    created = skipped = existed = 0
    for d in daterange(start, end):
        if not is_business_day(d, holidays):
            skipped += 1
            continue
        path = day_folder(args.root, d)
        if args.dry_run:
            print('would create: {}'.format(path))
            created += 1
            continue
        try:
            if os.path.isdir(path):
                existed += 1
            else:
                os.makedirs(path, exist_ok=True)
                created += 1
        except Exception as exc:
            print('FAILED: {} → {}'.format(path, exc))

    print('-' * 70)
    print('Business-day folders {}: {}'.format(
        'to create' if args.dry_run else 'created', created))
    if not args.dry_run:
        print('Already existed              : {}'.format(existed))
    print('Non-business days skipped     : {}'.format(skipped))


if __name__ == '__main__':
    main()
