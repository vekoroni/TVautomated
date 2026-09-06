from __future__ import annotations

import argparse
import json
from pathlib import Path

from .package_publisher import publish_package


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate or explicitly publish a complete evidence package"
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--charts-directory", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = publish_package(
            manifest_path=args.manifest,
            charts_directory=args.charts_directory,
            publish_requested=args.publish,
            replace_existing=args.replace_existing,
        )
    except Exception as exc:
        print(json.dumps({
            "status": "stopped", "findings": [str(exc)],
            "published": False,
        }, sort_keys=True))
        return 2
    print(json.dumps({
        "status": result.status, "findings": list(result.findings),
        "published_files": [str(path) for path in result.published_files],
        "published": result.status == "published",
    }, sort_keys=True))
    return 0 if result.status in {"validated", "published"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

