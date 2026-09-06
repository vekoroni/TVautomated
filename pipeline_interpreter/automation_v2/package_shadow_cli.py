from __future__ import annotations

import argparse
import json
from pathlib import Path

from .package_shadow import run_package_shadow


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish to isolated shadow charts and prove stateless ingestion"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--invocation-id", required=True)
    parser.add_argument("--confirm-shadow-publication", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_shadow_publication:
        parser.error("--confirm-shadow-publication is required")
    try:
        report = run_package_shadow(
            manifest_path=args.manifest,
            output_directory=args.output_directory,
            invocation_id=args.invocation_id,
        )
        payload = json.loads(report.read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({
            "status": "stopped", "finding": str(exc),
            "production_charts_touched": False, "published": False,
        }, sort_keys=True))
        return 2
    print(json.dumps({
        "status": payload["status"], "ticker": payload["ticker"],
        "report": str(report), "asset_count": payload["asset_count"],
        "sovereign_preserved": payload["sovereign_preserved"],
        "effective_verdict": payload["effective_verdict"],
        "production_charts_touched": False, "published": False,
    }, sort_keys=True))
    return 0 if payload["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())

