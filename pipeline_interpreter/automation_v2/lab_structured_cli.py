from __future__ import annotations

import argparse
import json
from pathlib import Path

from .lab_structured import build_structured_lab_manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Stage structured Intelligence Lab data for one ticker"
    )
    parser.add_argument("ticker")
    parser.add_argument("--pipeline-outputs", type=Path, required=True)
    parser.add_argument("--output-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build_structured_lab_manifest(
            ticker=args.ticker,
            pipeline_outputs=args.pipeline_outputs,
            output_file=args.output_file,
        )
    except Exception as exc:
        print(json.dumps({
            "status": "stopped", "finding": str(exc), "published": False,
        }, sort_keys=True))
        return 2
    print(json.dumps({
        "status": "staged", "ticker": result.ticker,
        "run_id": result.run_id, "manifest": str(result.manifest),
        "findings": list(result.findings), "published": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

