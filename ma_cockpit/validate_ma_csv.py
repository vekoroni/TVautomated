from __future__ import annotations

import argparse
import json

from ma_csv_schema import validate_ma_manual_review_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an AVSHUNTER M&A CSV.")
    parser.add_argument("path", help="CSV file to validate")
    args = parser.parse_args()

    report = validate_ma_manual_review_csv(args.path)
    print(
        json.dumps(
            {
                "path": report.path,
                "valid": report.valid,
                "row_count": report.row_count,
                "errors": report.errors,
                "warnings": report.warnings,
            },
            indent=2,
        )
    )
    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

