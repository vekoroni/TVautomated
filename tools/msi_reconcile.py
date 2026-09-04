"""Independent MSI handoff reconciliation and command-line validator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.interpreter_handoff import (  # noqa: E402
    HandoffValidationError,
    validate_handoff_manifest,
)


RECONCILE_VERSION = "msi-reconcile-v1.1"
AUTHORITY_FIELDS = (
    "governed_direction",
    "final_action",
    "thesis_state",
    "olm_guard_disposition",
)
IDENTITY_FIELDS = (
    "run_id",
    "ticker",
    "thesis_id",
    "trade_idea_id",
    "selected_structure_id",
    "selected_quote_snapshot_id",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _contract(value: Mapping[str, Any]) -> str:
    return _text(
        value.get("selected_contract_symbol")
        or value.get("morning_selected_contract_symbol")
        or value.get("contract_symbol")
    ).upper().replace("O:", "").replace(" ", "")


def reconcile_handoff(
    manifest_path: Path | str,
    *,
    require_accepted: bool = True,
) -> dict[str, Any]:
    try:
        handoff = validate_handoff_manifest(
            manifest_path,
            require_accepted=require_accepted,
        )
    except HandoffValidationError as error:
        return {
            "schema_version": "msi_reconciliation_v1",
            "reconcile_version": RECONCILE_VERSION,
            "status": "FAIL",
            "manifest_path": str(Path(manifest_path).resolve()),
            "mismatches": [f"HANDOFF_VALIDATION:{error}"],
        }

    books = {_text(row.get("ticker")).upper(): dict(row) for row in handoff.book_rows}
    bundles = {_text(row.get("ticker")).upper(): dict(row) for row in handoff.bundles}
    mismatches: list[str] = []
    for ticker in sorted(set(books) | set(bundles)):
        book = books.get(ticker)
        bundle = bundles.get(ticker)
        if book is None or bundle is None:
            mismatches.append(f"{ticker}:BOOK_BUNDLE_PRESENCE")
            continue
        for field in IDENTITY_FIELDS:
            if _text(book.get(field)).upper() != _text(bundle.get(field)).upper():
                mismatches.append(f"{ticker}:IDENTITY:{field}")
        if _contract(book) != _contract(bundle):
            mismatches.append(f"{ticker}:IDENTITY:selected_contract_symbol")
        governed = bundle.get("governed_record") or {}
        if not isinstance(governed, Mapping):
            mismatches.append(f"{ticker}:GOVERNED_RECORD_MISSING")
            continue
        for field in AUTHORITY_FIELDS:
            if _text(book.get(field)).upper() != _text(governed.get(field)).upper():
                mismatches.append(f"{ticker}:AUTHORITY:{field}")
        authority_map = bundle.get("authority_map") or {}
        if isinstance(authority_map, Mapping):
            for prohibited in ("final_action", "capital_permission", "governed_direction"):
                if _text(authority_map.get(prohibited)).upper() in {
                    "MACRO",
                    "MACRO_QUANT_PACKET",
                    "INTERPRETER",
                    "INTERPRETER_ASSESSMENT",
                }:
                    mismatches.append(f"{ticker}:AUTHORITY_OWNER:{prohibited}")

    return {
        "schema_version": "msi_reconciliation_v1",
        "reconcile_version": RECONCILE_VERSION,
        "status": "PASS" if not mismatches else "FAIL",
        "manifest_path": str(handoff.manifest_path),
        "run_id": handoff.manifest.get("run_id"),
        "book_rows": len(handoff.book_rows),
        "bundle_rows": len(handoff.bundles),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and reconcile an MSI handoff")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output")
    parser.add_argument("--allow-unaccepted", action="store_true")
    args = parser.parse_args()
    report = reconcile_handoff(
        args.manifest,
        require_accepted=not args.allow_unaccepted,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
