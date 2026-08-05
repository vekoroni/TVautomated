#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

REQUIRED_TOP_LEVEL_KEYS = ["ticker"]

def read_json(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))

def validate_one_package(p):
    errors = []
    try:
        obj = read_json(p)
    except Exception as e:
        return False, [f"Invalid JSON: {e}"]

    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in obj:
            errors.append(f"Missing required key: {key}")

    if "has_macro_regime" not in obj or obj.get("has_macro_regime") is not True:
        errors.append("has_macro_regime missing or not True")

    if not ("regime_snapshot" in obj or "macro" in obj):
        errors.append("Missing macro data (regime_snapshot or macro)")

    return len(errors) == 0, errors

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--packages_dir", required=True)
    parser.add_argument("--fail_on_any", action="store_true")
    args = parser.parse_args()

    packages_dir = Path(args.packages_dir)
    if not packages_dir.exists():
        print("ERROR: packages_dir not found")
        sys.exit(2)

    package_files = [p for p in packages_dir.glob("*.json") if p.name != "index.json"]

    total = 0
    failed = 0

    for p in package_files:
        total += 1
        ok, errors = validate_one_package(p)
        if not ok:
            failed += 1
            print(f"FAIL: {p.stem}")
            for e in errors:
                print(f"  - {e}")

    print(f"Checked {total} packages. Failed: {failed}")

    if args.fail_on_any and failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
