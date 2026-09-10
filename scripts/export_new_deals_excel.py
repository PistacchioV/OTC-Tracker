#!/usr/bin/env python3
"""
Export all New Deals (Option + NDF) from the JSON cache into a single Excel
workbook saved to the user's Downloads folder.

Scans:  apps/static/data/cache/new deals/**/*.json   (Intrag subtree excluded)
Output: ~/Downloads/new_deals_export_<YYYYMMDD_HHMMSS>.xlsx

Sheets:
  - All Deals : every deal (union of columns) with metadata columns first
  - NDF       : NDF Commodities deals only
  - Option    : Option Commodities deals only

Usage:
    python scripts/export_new_deals_excel.py
"""

import os
import sys
import json
from datetime import datetime

import pandas as pd

# ── paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)


# ── o dado vem do ARMAZÉM, não da cópia do repositório ──────────────────────
# `apps/static/data/*.json` no checkout é a SEED; na instância o dado vive no
# DATA_DIR (o share) e, desde o §434, dentro dos bancos. Ler o JSON do
# repositório aqui era ler o Reference Data de meses atrás (§440).
def _caminho_de_dado(*parts):
    try:
        if REPO_ROOT not in sys.path:
            sys.path.insert(0, REPO_ROOT)
        os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', REPO_ROOT)
        from apps.pages.data_paths import data_path
        return data_path(*parts)
    except Exception:                                       # noqa: BLE001
        return os.path.join(REPO_ROOT, 'apps', 'static', 'data', *parts)


def _armazem():
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', REPO_ROOT)
    from apps.pages import data_store
    return data_store


def _ler_json_do_armazem(path):
    return _armazem().read(path)


CACHE_ROOT = _caminho_de_dado("cache", "new deals")
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")

META_COLS = ["Type", "Product", "FileDate", "SourceFile"]


def _product_from_path(file_path):
    """e.g. .../NDF/Commodities/2026/06/file.json -> ('NDF', 'NDF Commodities')."""
    rel = os.path.relpath(file_path, CACHE_ROOT).replace("\\", "/")
    parts = [p for p in rel.split("/")[:-1] if not p.isdigit()][:2]
    product = " ".join(parts) if parts else "Other"
    deal_type = "OPT" if product.lower().startswith("option") else "NDF"
    return deal_type, product


def collect_deals():
    """Walk the cache and return a flat list of deal dicts with metadata."""
    rows = []
    if not _armazem().isdir(CACHE_ROOT):
        print(f"⚠️  Cache root not found: {CACHE_ROOT}")
        return rows

    for root, _dirs, files in _armazem().walk(CACHE_ROOT):
        # Skip the Intrag subtree — those belong to the Intrag pages, not New Deals
        if os.sep + "Intrag" + os.sep in root + os.sep:
            continue
        for fname in sorted(files):
            if not fname.endswith(".json") or fname.endswith((".tmp", ".bak")):
                continue
            fp = os.path.join(root, fname)
            # File date from the YYYYMMDD filename prefix (best effort)
            try:
                file_date = datetime.strptime(fname[:8], "%Y%m%d").strftime("%Y-%m-%d")
            except ValueError:
                file_date = ""
            deal_type, product = _product_from_path(fp)
            try:
                data = _ler_json_do_armazem(fp)
            except Exception as exc:
                print(f"⚠️  Could not read {fp}: {exc}")
                continue
            if not isinstance(data, list):
                continue
            for d in data:
                # Include every deal record; skip only non-dicts and empty objects
                if not isinstance(d, dict) or not any(
                    (str(v).strip() if v is not None else "") for v in d.values()
                ):
                    continue
                row = {
                    "Type": deal_type,
                    "Product": product,
                    "FileDate": file_date,
                    "SourceFile": os.path.relpath(fp, CACHE_ROOT).replace("\\", "/"),
                }
                row.update(d)
                rows.append(row)
    return rows


def order_columns(df):
    """Metadata columns first, then the deal fields in first-seen order."""
    meta = [c for c in META_COLS if c in df.columns]
    rest = [c for c in df.columns if c not in META_COLS]
    return df[meta + rest]


def main():
    rows = collect_deals()
    if not rows:
        print("No deals found — nothing to export.")
        return

    df_all = order_columns(pd.DataFrame(rows))
    df_ndf = df_all[df_all["Type"] == "NDF"].dropna(axis=1, how="all")
    df_opt = df_all[df_all["Type"] == "OPT"].dropna(axis=1, how="all")

    os.makedirs(DOWNLOADS, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(DOWNLOADS, f"new_deals_export_{stamp}.xlsx")

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df_all.to_excel(writer, sheet_name="All Deals", index=False)
        if not df_ndf.empty:
            df_ndf.to_excel(writer, sheet_name="NDF", index=False)
        if not df_opt.empty:
            df_opt.to_excel(writer, sheet_name="Option", index=False)

        # Auto-fit column widths (cap at 60 chars)
        for ws in writer.book.worksheets:
            for col in ws.columns:
                width = max((len(str(c.value)) for c in col if c.value is not None), default=10)
                ws.column_dimensions[col[0].column_letter].width = min(width + 2, 60)

    print(f"✅ Exported {len(df_all)} deals "
          f"(NDF: {len(df_ndf)}, Option: {len(df_opt)})")
    print(f"   → {out_path}")


if __name__ == "__main__":
    main()
