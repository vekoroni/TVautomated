"""Interactive CLI for five-timeframe shadow capture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backend import WindowsShadowBackend
from .timeframe_batch import capture_timeframe_batch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture Webull chart timeframes")
    parser.add_argument("ticker")
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--confirm-ticker-visible", action="store_true")
    parser.add_argument("--confirm-full-chart-layout", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_ticker_visible or not args.confirm_full_chart_layout:
        parser.error(
            "--confirm-ticker-visible and --confirm-full-chart-layout are required"
        )
    backend = WindowsShadowBackend()
    windows = tuple(item for item in backend.discover("Webull") if item.visible)
    if len(windows) != 1:
        print(json.dumps({"status": "stopped", "finding": f"WEBULL_WINDOW_COUNT:{len(windows)}"}))
        return 2
    try:
        manifest, assets = capture_timeframe_batch(
            ticker=args.ticker, window=windows[0],
            output_directory=args.output_directory, capture_backend=backend,
        )
    except Exception as exc:
        print(json.dumps({"status": "stopped", "finding": str(exc), "published": False}))
        return 2
    print(json.dumps({
        "status": "captured", "ticker": args.ticker.upper(),
        "assets": [str(path) for path in assets], "manifest": str(manifest),
        "published": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

