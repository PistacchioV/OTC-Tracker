"""
recover_json_cache.py
---------------------
Recovers valid deal entries from a corrupted *_optcomm.json (or *_ndfcomm.json)
cache file and writes them back, discarding only the truncated/malformed entry.

Usage:
    python scripts/recover_json_cache.py <path_to_corrupted_file.json>

The original file is backed up as <file>.bak before overwriting.
"""

import json
import os
import re
import shutil
import sys


def _try_full_parse(text):
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        return [data]
    except json.JSONDecodeError:
        return None


def _recover_objects(text):
    """
    Scan the raw text and extract every complete JSON object ({...}).
    Handles nested braces/brackets correctly. Returns list of dicts.
    """
    recovered = []
    i = 0
    n = len(text)

    while i < n:
        # Skip until we find the start of an object
        while i < n and text[i] != '{':
            i += 1
        if i >= n:
            break

        depth = 0
        in_string = False
        escape_next = False
        start = i

        for j in range(i, n):
            ch = text[j]
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[start:j + 1]
                    try:
                        obj = json.loads(candidate)
                        if isinstance(obj, dict):
                            recovered.append(obj)
                    except json.JSONDecodeError:
                        pass
                    i = j + 1
                    break
        else:
            # Reached end of string without closing brace — incomplete object, stop
            break

    return recovered


def recover(file_path):
    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    with open(file_path, 'r', encoding='utf-8') as fh:
        raw = fh.read()

    # 1. Try full parse first
    data = _try_full_parse(raw)
    if data is not None:
        print(f"File is valid JSON — {len(data)} entries, nothing to recover.")
        return

    print(f"File has invalid JSON. Attempting recovery…")

    recovered = _recover_objects(raw)

    if not recovered:
        print("ERROR: Could not extract any valid objects. File may be too corrupted.")
        sys.exit(1)

    # Deduplicate by (Deal, Client) keeping the last occurrence (most recent write wins)
    seen = {}
    for obj in recovered:
        key = (obj.get('Deal', ''), obj.get('Client', ''))
        seen[key] = obj
    deduped = list(seen.values())

    # Back up original
    backup_path = file_path + '.bak'
    shutil.copy2(file_path, backup_path)
    print(f"Backup saved → {backup_path}")

    # Write recovered data atomically
    tmp_path = file_path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as fh:
        json.dump(deduped, fh, ensure_ascii=False, indent=2)
    os.replace(tmp_path, file_path)

    print(f"Recovered {len(recovered)} raw objects → {len(deduped)} unique (Deal, Client) entries.")
    print(f"Written to: {file_path}")

    # Show summary
    print("\nRecovered entries:")
    for obj in deduped:
        print(f"  [{obj.get('Deal','?'):20}] {obj.get('Client','?'):40} Status={obj.get('Status','?')}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    recover(sys.argv[1])
