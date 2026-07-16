"""
backfill_cetip_position_files.py
--------------------------------
One-off / catch-up backfill of the CETIP position files the daily "Save CETIP
Files" card handles — now INCLUDING CETIP21_AAMMDD_DOPERACOES.txt.

It walks the CETIP source tree and, for every day folder, saves each matched
position file into the destination tree and writes its per-day JSON, reusing the
EXACT same logic as the daily routine (imported from apps/pages/routes.py:
_CETIP_RULES / _cetip_save_file / _b3_export_json). So the renaming, the ';'
parsing, and the DOPERACOES header-on-first-line + Conta ∈ {73760009, 04880006}
and Tipo Titulo ∈ {TER, SWAP, OPC} filters all match the daily card exactly.

Source tree:  CETIP_SOURCE_ROOT\\{YYYY}\\{MM. Month}\\{DD}
                (default I:\\Confirmation\\Derivativos\\OTC Tracker\\Alteryx\\
                 Posição B3\\ARQUIVOS CETIP)
Dest tree:    CETIP_DEST_ROOT\\{YYYY}\\{MM. Month}\\{DD}
                (default I:\\Confirmation\\Derivativos\\OTC Tracker\\CETIP Files\\
                 Position Files)

Only NEW work is done — nothing already there is touched:
  - a destination file is written only if it does NOT already exist;
  - a per-day JSON is created only for days whose JSON does NOT already exist.
Pass --overwrite to force re-saving files and rebuilding JSONs.

The daily routine's VCP indexer refresh (vcp_update) and its flat network-share
secondary copies (extra_dest) are intentionally SKIPPED here: they mutate
shared/live reference state and must not be replayed over historical days.

Usage
    # whole source tree (every year/month/day present)
    python scripts/backfill_cetip_position_files.py

    # limit to one year subtree
    python scripts/backfill_cetip_position_files.py --year 2026

    # override source/destination roots (else the env vars / routes.py defaults)
    python scripts/backfill_cetip_position_files.py --src "D:\\in" --dest "D:\\out"

    # copy the files only, don't build JSONs
    python scripts/backfill_cetip_position_files.py --no-json

    # re-save files and rebuild JSONs even when they already exist
    python scripts/backfill_cetip_position_files.py --overwrite

    # preview what would be done, writing nothing
    python scripts/backfill_cetip_position_files.py --dry-run
"""
import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# routes.py imports `awmpy` (a JPM-internal module). It's present on the JPM
# environment where this backfill actually runs; off-environment we install a
# minimal stub so the module still imports — the backfill only uses routes.py's
# pure file helpers (_CETIP_RULES / _cetip_save_file / _b3_export_json), never
# the phonebook, so the stub is never exercised.
try:
    import awmpy  # noqa: F401
except ImportError:
    import types as _types
    _stub = _types.ModuleType('awmpy')
    _stub.get_phonebook_data = lambda *a, **k: {}
    sys.modules['awmpy'] = _stub

# Reuse the daily-routine logic verbatim so the backfill can never drift from it.
from apps.pages import routes as R


def iter_day_dirs(src_root, only_year=None):
    """Yield (relative 'YYYY/MM. Month/DD', abs day dir) for each day folder."""
    if not os.path.isdir(src_root):
        sys.exit('ERROR: source root not found: {}'.format(src_root))
    for year in sorted(os.listdir(src_root)):
        ypath = os.path.join(src_root, year)
        if not os.path.isdir(ypath) or (only_year and year != str(only_year)):
            continue
        for month_folder in sorted(os.listdir(ypath)):
            mpath = os.path.join(ypath, month_folder)
            if not os.path.isdir(mpath):
                continue
            for day in sorted(os.listdir(mpath)):
                dpath = os.path.join(mpath, day)
                if os.path.isdir(dpath):
                    yield os.path.join(year, month_folder, day), dpath


def process_day(src_dir, dest_dir, make_json, overwrite, dry_run, stats):
    """Save every matched position file for one day (skipping ones already saved)
    and export its JSON (skipping days already created), mirroring the daily loop."""
    files = [f for f in os.listdir(src_dir) if os.path.isfile(os.path.join(src_dir, f))]
    if not files:
        return
    for rule in R._CETIP_RULES:
        for name in files:
            if not rule['match'](name.lower()):
                continue
            dref = name[rule['date_start']:rule['date_start'] + 6]
            if len(dref) < 6 or not dref.isdigit():
                stats['bad_date'] += 1
                continue
            dest_name = rule['dest_name'](dref)
            dest_path = os.path.join(dest_dir, dest_name)
            src_path = os.path.join(src_dir, name)

            # 1) Save the file — only when it isn't already there (no overwrite).
            if os.path.exists(dest_path) and not overwrite:
                stats['file_exists'] += 1
            elif dry_run:
                print('  SAVE  {:<40} -> {}'.format(name, dest_name))
                stats['file_saved'] += 1
            else:
                try:
                    os.makedirs(dest_dir, exist_ok=True)
                    R._cetip_save_file(src_path, dest_path)
                    stats['file_saved'] += 1
                except Exception as exc:
                    print('  FAIL save {}: {}'.format(name, exc))
                    stats['errors'] += 1
                    continue

            # 2) Export JSON — only for days not yet created (skip_existing).
            if make_json and rule.get('json'):
                if dry_run:
                    stats['json'] += 1
                    continue
                read_from = dest_path if os.path.exists(dest_path) else src_path
                try:
                    if R._b3_export_json(read_from, rule['json'], dest_name, dref,
                                         skip_existing=not overwrite):
                        stats['json'] += 1
                except Exception as exc:
                    print('  FAIL json {}: {}'.format(name, exc))
                    stats['errors'] += 1


def main():
    ap = argparse.ArgumentParser(
        description='Backfill CETIP position files (incl. DOPERACOES) into the '
                    'destination tree without overwriting what is already there.')
    ap.add_argument('--year', help='Limit to a single year subtree (e.g. 2026).')
    ap.add_argument('--src', default=R.CETIP_SOURCE_ROOT,
                    help='Source root (default: $CETIP_SOURCE_ROOT / routes.py default).')
    ap.add_argument('--dest', default=R.CETIP_DEST_ROOT,
                    help='Destination root (default: $CETIP_DEST_ROOT / routes.py default).')
    ap.add_argument('--no-json', action='store_true',
                    help='Only copy the files; do not build the per-day JSONs.')
    ap.add_argument('--overwrite', action='store_true',
                    help='Re-save files and rebuild JSONs even if they already exist.')
    ap.add_argument('--dry-run', action='store_true',
                    help='Preview what would be saved/created; write nothing.')
    args = ap.parse_args()

    src_root, dest_root = args.src, args.dest
    make_json = not args.no_json

    print('Source     : {}'.format(src_root))
    print('Destination: {}'.format(dest_root))
    print('Year       : {}'.format(args.year or 'ALL'))
    print('JSON export : {}'.format('yes' if make_json else 'no'))
    print('Mode        : {}{}'.format(
        'DRY-RUN (nothing written)' if args.dry_run else 'WRITE',
        ' + OVERWRITE' if args.overwrite else ' (skip existing)'))
    print('-' * 78)

    stats = {'file_saved': 0, 'file_exists': 0, 'json': 0, 'bad_date': 0, 'errors': 0}
    days = 0
    for rel, day_dir in iter_day_dirs(src_root, only_year=args.year):
        dest_dir = os.path.join(dest_root, rel)
        days += 1
        print('[{}]'.format(rel))
        process_day(day_dir, dest_dir, make_json, args.overwrite, args.dry_run, stats)

    print('-' * 78)
    print('Day folders scanned          : {}'.format(days))
    print('Files {:<24}: {}'.format('to save' if args.dry_run else 'saved', stats['file_saved']))
    print('Files already present (kept) : {}'.format(stats['file_exists']))
    if make_json:
        print('JSONs {:<24}: {}'.format('to create' if args.dry_run else 'created/kept', stats['json']))
    if stats['bad_date']:
        print('Files with unparseable date  : {}'.format(stats['bad_date']))
    if stats['errors']:
        print('Errors                       : {}'.format(stats['errors']))


if __name__ == '__main__':
    main()
