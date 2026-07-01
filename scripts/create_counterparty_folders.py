"""
create_counterparty_folders.py
-------------------------------
Pre-creates the Electronic Inventory folder tree for every counterparty listed
in apps/static/data/RefData.json.

Layout (matches the shared drive):
    ELECTRONIC_INVENTORY_ROOT\\{Counterparty Name}\\Confirmations
    ELECTRONIC_INVENTORY_ROOT\\{Counterparty Name}\\Transactional
    ELECTRONIC_INVENTORY_ROOT\\{Counterparty Name}\\SSI

Counterparty names come straight from the COUNTERPARTY field. Characters that
Windows forbids in a directory name (<>:"/\\|?*) are stripped — e.g.
"BUNGE ALIMENTOS S/A" becomes the folder "BUNGE ALIMENTOS SA". Trailing dots /
spaces are also trimmed (Windows silently drops them).

Existing folders are detected tolerantly: the counterparty name and each folder
already on disk are reduced to a normalized key (illegal chars removed, spaces
collapsed, upper-cased) before comparison, so a folder someone created earlier
with a slightly different sanitization (e.g. "S A", "S-A") is still recognized
and reused instead of duplicated. Only the missing subfolders are created.

The same sanitization + ensure logic lives in apps/pages/routes.py
(_ei_sanitize / _ensure_counterparty_folders) so the Reference Data approval
hook and this script always agree on folder names. Keep them in sync.

Usage
    # every counterparty in RefData.json
    python scripts/create_counterparty_folders.py

    # only ACTIVE counterparties
    python scripts/create_counterparty_folders.py --active-only

    # override the root (else $ELECTRONIC_INVENTORY_ROOT, else routes.py default)
    python scripts/create_counterparty_folders.py --root "D:\\OTC\\Electronic Inventory"

    # preview without creating anything
    python scripts/create_counterparty_folders.py --dry-run
"""

import argparse
import json
import os
import re
import sys

# ── paths ────────────────────────────────────────────────────────────────────

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT    = os.path.dirname(SCRIPT_DIR)
REFDATA_JSON = os.path.join(REPO_ROOT, 'apps', 'static', 'data', 'RefData.json')

# Same default as apps/pages/routes.py (ELECTRONIC_INVENTORY_ROOT). Overridable
# via the ELECTRONIC_INVENTORY_ROOT env var or the --root flag.
DEFAULT_ROOT = os.getenv(
    'ELECTRONIC_INVENTORY_ROOT',
    r'I:\Confirmation\Derivativos\OTC Tracker\Electronic Inventory')

# The three subfolders every counterparty gets.
SUBFOLDERS = ('Confirmations', 'Transactional', 'SSI')

# ── name sanitization (kept in sync with routes.py _ei_sanitize) ──────────────

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_folder_name(name):
    """Windows-safe folder name: drop illegal chars, collapse spaces, trim
    trailing dots/spaces. '/' is removed (BUNGE S/A -> BUNGE SA)."""
    s = _ILLEGAL.sub('', name or '')
    s = re.sub(r'\s+', ' ', s).strip()
    return s.rstrip('. ')


def norm_key(name):
    """Case/whitespace/illegal-char insensitive key for existence matching."""
    return sanitize_folder_name(name).upper()


# ── refdata ──────────────────────────────────────────────────────────────────

def load_counterparties(active_only):
    try:
        with open(REFDATA_JSON, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except Exception as exc:
        sys.exit('ERROR: could not read RefData.json ({}): {}'.format(REFDATA_JSON, exc))

    names, seen = [], set()
    for rec in data:
        name = (rec.get('COUNTERPARTY') or '').strip()
        if not name:
            continue
        if active_only and (rec.get('STATUS') or '').upper() != 'ACTIVE':
            continue
        key = norm_key(name)
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def existing_index(root):
    """Map norm_key(folder) -> actual folder name for dirs already under root."""
    index = {}
    if not os.path.isdir(root):
        return index
    for entry in os.listdir(root):
        if os.path.isdir(os.path.join(root, entry)):
            index.setdefault(norm_key(entry), entry)
    return index


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description='Create Electronic Inventory counterparty folders from RefData.json.')
    ap.add_argument('--root', default=DEFAULT_ROOT,
                    help='Electronic Inventory root (default: $ELECTRONIC_INVENTORY_ROOT or the routes.py default).')
    ap.add_argument('--active-only', action='store_true',
                    help='Only counterparties with STATUS == ACTIVE.')
    ap.add_argument('--dry-run', action='store_true',
                    help='List what would be created without touching the disk.')
    args = ap.parse_args()

    names = load_counterparties(args.active_only)
    index = existing_index(args.root)

    print('Root        : {}'.format(args.root))
    print('Counterparties : {} ({})'.format(
        len(names), 'ACTIVE only' if args.active_only else 'all'))
    print('Subfolders  : {}'.format(', '.join(SUBFOLDERS)))
    print('Mode        : {}'.format('DRY-RUN (nothing written)' if args.dry_run else 'CREATE'))
    print('-' * 70)

    made_parent = made_sub = existed_full = failed = 0

    for name in sorted(names, key=norm_key):
        folder = index.get(norm_key(name)) or sanitize_folder_name(name)
        parent = os.path.join(args.root, folder)
        parent_exists = os.path.isdir(parent)

        missing = []
        for sub in SUBFOLDERS:
            sub_path = os.path.join(parent, sub)
            if not os.path.isdir(sub_path):
                missing.append(sub)

        if not missing and parent_exists:
            existed_full += 1
            continue

        if args.dry_run:
            tag = 'NEW' if not parent_exists else 'add subfolders'
            print('would create [{}]: {}  ->  {}'.format(tag, folder, ', '.join(missing)))
            if not parent_exists:
                made_parent += 1
            made_sub += len(missing)
            continue

        try:
            if not parent_exists:
                os.makedirs(parent, exist_ok=True)
                made_parent += 1
            for sub in missing:
                os.makedirs(os.path.join(parent, sub), exist_ok=True)
                made_sub += 1
        except Exception as exc:
            failed += 1
            print('FAILED: {} -> {}'.format(parent, exc))

    print('-' * 70)
    print('Counterparty folders {}: {}'.format(
        'to create' if args.dry_run else 'created', made_parent))
    print('Subfolders {}      : {}'.format(
        'to create' if args.dry_run else 'created', made_sub))
    print('Already complete            : {}'.format(existed_full))
    if failed:
        print('Failed                      : {}'.format(failed))


if __name__ == '__main__':
    main()
