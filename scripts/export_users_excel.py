#!/usr/bin/env python3
"""
Export every registered user from the DuckDB database (Users_OTCTracker.db) into
an Excel workbook saved to the user's Downloads folder.

Source:  apps/static/data/db/Users_OTCTracker.db   (table: users)
Output:  ~/Downloads/users_export_<YYYYMMDD_HHMMSS>.xlsx

Sheets:
  - Users   : one row per registered user, all columns
  - Summary : counts by Status and by Role

The DB is opened READ-ONLY. If the Flask app is running and holds the database
open (DuckDB single-writer lock), the script falls back to copying the database
files to a temp folder and reading from the copy, so it never blocks the app.

Usage:
    python scripts/export_users_excel.py
"""

import os
import shutil
import tempfile
from datetime import datetime

import duckdb
import pandas as pd

# ── paths ─────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(
    SCRIPT_DIR, "..", "apps", "static", "data", "db", "Users_OTCTracker.db"
))
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")

# Preferred column order; any other columns are appended in their natural order.
PREFERRED_COLS = [
    "SID", "Name", "Email", "Role_Description", "Position",
    "Role", "Status", "IP_Address", "created_at",
]


def _read_users():
    """Return the users table as a DataFrame, opening the DB read-only. Falls
    back to a temp copy if the live DB is locked by the running app."""
    try:
        conn = duckdb.connect(DB_PATH, read_only=True)
    except Exception as exc:
        print(f"ℹ️  Live DB busy ({exc}); reading from a temporary copy…")
        conn = _connect_via_copy()
    try:
        return conn.execute("SELECT * FROM users").fetchdf()
    finally:
        conn.close()


def _connect_via_copy():
    """Copy the DB (and its WAL, if any) to a temp folder and open the copy."""
    tmp_dir = tempfile.mkdtemp(prefix="otc_users_")
    tmp_db = os.path.join(tmp_dir, os.path.basename(DB_PATH))
    shutil.copy2(DB_PATH, tmp_db)
    wal = DB_PATH + ".wal"
    if os.path.isfile(wal):
        shutil.copy2(wal, tmp_db + ".wal")
    return duckdb.connect(tmp_db, read_only=True)


def _order_columns(df):
    """Known columns first (in PREFERRED_COLS order), then any extras."""
    known = [c for c in PREFERRED_COLS if c in df.columns]
    extra = [c for c in df.columns if c not in PREFERRED_COLS]
    return df[known + extra]


def _summary(df):
    """A small counts-by-Status / counts-by-Role breakdown."""
    blocks = []
    for col in ("Status", "Role"):
        if col in df.columns:
            counts = (df[col].fillna("(blank)").replace("", "(blank)")
                      .value_counts().rename_axis(col).reset_index(name="Count"))
            counts.insert(0, "Breakdown", col)
            blocks.append(counts.rename(columns={col: "Value"}))
    if not blocks:
        return pd.DataFrame(columns=["Breakdown", "Value", "Count"])
    return pd.concat(blocks, ignore_index=True)


def main():
    if not os.path.isfile(DB_PATH):
        print(f"❌ Database not found: {DB_PATH}")
        return

    df = _read_users()
    if df.empty:
        print("No users found — nothing to export.")
        return

    df = _order_columns(df)
    # Sort by Status then Name for a tidy listing (best effort).
    sort_cols = [c for c in ("Status", "Name") if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, kind="stable").reset_index(drop=True)

    summary = _summary(df)

    os.makedirs(DOWNLOADS, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(DOWNLOADS, f"users_export_{stamp}.xlsx")

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Users", index=False)
        summary.to_excel(writer, sheet_name="Summary", index=False)

        # Auto-fit column widths (cap at 60 chars).
        for ws in writer.book.worksheets:
            for col in ws.columns:
                width = max((len(str(c.value)) for c in col if c.value is not None),
                            default=10)
                ws.column_dimensions[col[0].column_letter].width = min(width + 2, 60)

    print(f"✅ Exported {len(df)} users → {out_path}")


if __name__ == "__main__":
    main()
