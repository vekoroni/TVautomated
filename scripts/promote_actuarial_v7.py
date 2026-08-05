"""Controlled, fail-closed promotion of validated actuarial v7 staging data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--backup-manifest", type=Path, required=True)
    args = parser.parse_args()
    validation = json.loads(args.validation.read_text(encoding="utf-8"))
    if validation.get("status") != "PASS":
        raise ValueError("promotion requires a PASS validation report")
    if Path(validation.get("path", "")).resolve() != args.staging.resolve():
        raise ValueError("validation report belongs to a different staging file")
    staging_hash = _sha256(args.staging)
    if staging_hash != validation.get("sha256"):
        raise ValueError("staging hash changed after validation")
    backup = json.loads(args.backup_manifest.read_text(encoding="utf-8"))
    backup_text = json.dumps(backup)
    if "actuarial_database_v6.parquet" not in backup_text:
        raise ValueError("Phase-0 manifest does not contain the v6 rollback database")
    if args.target.exists():
        raise FileExistsError(f"promotion target already exists: {args.target}")
    args.target.parent.mkdir(parents=True, exist_ok=True)
    os.link(args.staging, args.target)
    promoted_hash = _sha256(args.target)
    if promoted_hash != staging_hash:
        raise RuntimeError("promoted database hash mismatch")
    receipt = {
        "status": "PROMOTED_VERSIONED_NOT_CONFIGURED",
        "promoted_at_utc": datetime.now(timezone.utc).isoformat(),
        "staging": str(args.staging.resolve()),
        "target": str(args.target.resolve()),
        "sha256": promoted_hash,
        "validation_report": str(args.validation.resolve()),
        "backup_manifest": str(args.backup_manifest.resolve()),
        "rollback_database": r"C:\Users\ACKVerissimo\vanguard\data\actuarial_database_v6.parquet",
        "promotion_method": "same-volume-hardlink",
    }
    receipt_path = args.target.with_suffix(".promotion.json")
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
