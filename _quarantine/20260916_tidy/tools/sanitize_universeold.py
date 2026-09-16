#!/usr/bin/env python3
"""
Universe Sanitation Utility

Creates:
- clean_universe.csv
- bad_universe.csv

Conservative US equity rules:
- Uppercase only
- A–Z, length 1–6
- Allow class shares like BRK.B / BF.B
- Reject foreign suffixes (.V, .TO, etc.)
"""

import argparse
import csv
import re
from pathlib import Path

BASE_PATTERN = re.compile(r"^[A-Z]{1,6}$")
CLASS_PATTERN = re.compile(r"^[A-Z]{1,6}\.[ABC]$")

BAD_SUFFIXES = (
    ".V", ".TO", ".CN", ".L", ".F", ".SW", ".PA", ".DE", ".MI", ".AS", ".ST", ".OL"
)

def normalise(raw: str) -> str:
    return raw.strip().upper()

def classify(t: str):
    if not t:
        return False, "EMPTY"

    if any(ch in t for ch in [" ", "\t", "/", "\\", "-", "^", "=", ",", ":", ";", "(", ")", "[", "]", "{", "}", "@", "#", "$", "%", "&", "*", "!", "?", "+"]):
        return False, "SPECIAL_CHARS"

    for suf in BAD_SUFFIXES:
        if t.endswith(suf):
            return False, f"FOREIGN_SUFFIX_{suf}"

    if "." in t:
        if CLASS_PATTERN.match(t):
            return True, "OK_CLASS"
        return False, "DOT_SUFFIX_NOT_ALLOWED"

    if BASE_PATTERN.match(t):
        return True, "OK_BASE"

    return False, "FORMAT_INVALID"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--outdir", default="data/universe")
    args = ap.parse_args()

    in_path = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    with in_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        ticker_col = reader.fieldnames[0]
        raw_rows = [row[ticker_col] for row in reader if row[ticker_col]]

    seen = set()
    clean_rows = []
    bad_rows = []

    for r in raw_rows:
        t = normalise(r)
        if not t or t in seen:
            continue
        seen.add(t)

        ok, reason = classify(t)
        if ok:
            clean_rows.append([t])
        else:
            bad_rows.append([t, reason, r])

    clean_path = outdir / "clean_universe.csv"
    bad_path = outdir / "bad_universe.csv"

    with clean_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticker"])
        w.writerows(clean_rows)

    with bad_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "reject_reason", "raw_input"])
        w.writerows(bad_rows)

    total = len(clean_rows) + len(bad_rows)
    pct_clean = (len(clean_rows) / total * 100) if total else 0

    print("=== UNIVERSE SANITATION COMPLETE ===")
    print(f"Total: {total}")
    print(f"Clean: {len(clean_rows)} ({pct_clean:.1f}%)")
    print(f"Rejected: {len(bad_rows)} ({100 - pct_clean:.1f}%)")
    print(f"Output: {clean_path}, {bad_path}")

if __name__ == "__main__":
    main()
