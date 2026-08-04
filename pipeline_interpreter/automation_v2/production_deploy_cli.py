from __future__ import annotations

import argparse
import json
from pathlib import Path

from .production_deploy import deploy_package


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Recoverably deploy an evidence package")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--charts-directory", type=Path, required=True)
    parser.add_argument("--backup-directory", type=Path, required=True)
    parser.add_argument("--deployment-id", required=True)
    parser.add_argument("--confirm-production-deployment", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = deploy_package(
            manifest_path=args.manifest,
            charts_directory=args.charts_directory,
            backup_directory=args.backup_directory,
            deployment_id=args.deployment_id,
            confirmed=args.confirm_production_deployment,
        )
    except Exception as exc:
        result = {"status": "stopped", "published": False, "findings": [str(exc)]}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "published" else 2


if __name__ == "__main__":
    raise SystemExit(main())
