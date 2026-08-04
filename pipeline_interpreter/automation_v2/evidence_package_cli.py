from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evidence_package import assemble_evidence_package


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Assemble staged ticker evidence")
    parser.add_argument("ticker")
    parser.add_argument("--staging-root", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        manifest, findings = assemble_evidence_package(
            ticker=args.ticker, staging_root=args.staging_root,
            output_directory=args.output_directory,
        )
    except Exception as exc:
        print(json.dumps({
            "status": "stopped", "finding": str(exc), "published": False,
        }, sort_keys=True))
        return 2
    status = "complete" if not findings else "incomplete"
    print(json.dumps({
        "status": status, "ticker": args.ticker.upper(),
        "manifest": str(manifest), "findings": list(findings),
        "published": False,
    }, sort_keys=True))
    return 0 if not findings else 2


if __name__ == "__main__":
    raise SystemExit(main())
