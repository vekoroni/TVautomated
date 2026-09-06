"""Command-line entry point for attended dry-run and shadow capture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .contracts import CaptureMode, CaptureRequest, CaptureStatus
from .service import run_capture


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AVSHUNTER read-only Webull capture")
    parser.add_argument("ticker")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--invocation-id", required=True)
    parser.add_argument("--staging-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("OFF", "DRY_RUN", "SHADOW"), default="OFF")
    parser.add_argument(
        "--confirm-ticker-visible", action="store_true",
        help="Attest that the requested ticker is visibly selected in Webull",
    )
    parser.add_argument(
        "--confirm-daily-view", action="store_true",
        help="Attest that the Webull chart visibly shows the Daily timeframe",
    )
    args = parser.parse_args(argv)
    result = run_capture(
        CaptureRequest(
            ticker=args.ticker, run_id=args.run_id,
            invocation_id=args.invocation_id, staging_root=args.staging_root,
            mode=CaptureMode(args.mode),
            operator_confirmed_ticker=args.confirm_ticker_visible,
            operator_confirmed_daily=args.confirm_daily_view,
        )
    )
    print(json.dumps({
        "ticker": result.ticker, "mode": result.mode.value,
        "status": result.status.value, "findings": list(result.findings),
        "manifest_path": result.manifest_path, "published": result.published,
        "assets": list(result.assets),
    }, sort_keys=True))
    return 0 if result.status in {
        CaptureStatus.DISABLED, CaptureStatus.VALIDATED, CaptureStatus.CAPTURED
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())

