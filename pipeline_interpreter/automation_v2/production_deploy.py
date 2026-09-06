"""Recoverable production deployment for a validated ticker evidence package."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .package_publisher import PUBLISH_FEATURE_FLAG, publish_package, validate_package


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deploy_package(
    *,
    manifest_path: Path,
    charts_directory: Path,
    backup_directory: Path,
    deployment_id: str,
    confirmed: bool = False,
    feature_enabled: bool | None = None,
) -> dict[str, Any]:
    payload, findings = validate_package(manifest_path)
    if findings:
        return {"status": "stopped", "findings": list(findings), "published": False}
    if not confirmed:
        return {
            "status": "stopped",
            "findings": ["PRODUCTION_DEPLOYMENT_NOT_CONFIRMED"],
            "published": False,
        }
    enabled = (
        os.environ.get(PUBLISH_FEATURE_FLAG, "").strip() == "1"
        if feature_enabled is None
        else feature_enabled
    )
    if not enabled:
        return {
            "status": "stopped",
            "findings": ["PUBLISH_FEATURE_FLAG_DISABLED"],
            "published": False,
        }

    charts = charts_directory.resolve()
    backup = backup_directory.resolve()
    if backup.exists():
        return {
            "status": "stopped",
            "findings": ["BACKUP_DIRECTORY_EXISTS"],
            "published": False,
        }
    backup.mkdir(parents=True)
    records = payload["assets"]
    prior: list[dict[str, Any]] = []
    for record in records:
        target = charts / record["filename"]
        if target.is_file():
            saved = backup / record["filename"]
            shutil.copy2(target, saved)
            prior.append({
                "filename": record["filename"],
                "sha256": _sha256(saved),
            })

    receipt_path = backup / "production_deployment_receipt.json"
    receipt: dict[str, Any] = {
        "schema_version": "automation_v2.production_deployment.1",
        "deployment_id": deployment_id,
        "ticker": payload["ticker"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "manifest": str(manifest_path.resolve()),
        "charts_directory": str(charts),
        "status": "deploying",
        "prior_assets": prior,
        "published_assets": [],
        "sovereign_policy": "PRESERVED_BY_VALIDATED_EVIDENCE_PACKAGE",
    }
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    published_names: list[str] = []
    try:
        result = publish_package(
            manifest_path=manifest_path,
            charts_directory=charts,
            publish_requested=True,
            feature_enabled=True,
            replace_existing=True,
        )
        if result.status != "published":
            raise RuntimeError(",".join(result.findings) or result.status)
        expected = {r["filename"]: r["sha256"] for r in records}
        for path in result.published_files:
            actual = _sha256(path)
            if actual != expected[path.name]:
                raise RuntimeError(f"POST_PUBLISH_HASH_MISMATCH:{path.name}")
            published_names.append(path.name)
        receipt["published_assets"] = [
            {"filename": name, "sha256": expected[name]} for name in published_names
        ]
        receipt["status"] = "published"
        receipt["verified"] = True
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        return {
            "status": "published",
            "published": True,
            "ticker": payload["ticker"],
            "asset_count": len(published_names),
            "backup_count": len(prior),
            "receipt": str(receipt_path),
            "findings": [],
        }
    except Exception as exc:
        prior_names = {item["filename"] for item in prior}
        for record in records:
            target = charts / record["filename"]
            if record["filename"] in prior_names:
                shutil.copy2(backup / record["filename"], target)
            else:
                target.unlink(missing_ok=True)
        receipt["status"] = "rolled_back"
        receipt["verified"] = False
        receipt["finding"] = str(exc)
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        return {
            "status": "rolled_back",
            "published": False,
            "ticker": payload["ticker"],
            "receipt": str(receipt_path),
            "findings": [str(exc)],
        }

