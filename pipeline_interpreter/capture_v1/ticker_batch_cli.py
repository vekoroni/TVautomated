"""Interactive CLI for the combined Webull ticker workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backend import WindowsShadowBackend
from .ticker_batch import capture_ticker_workflow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select, verify, and capture five Webull chart timeframes"
    )
    parser.add_argument("ticker")
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--confirm-full-chart-layout", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_full_chart_layout:
        parser.error("--confirm-full-chart-layout is required")

    backend = WindowsShadowBackend()
    windows = tuple(item for item in backend.discover("Webull") if item.visible)
    if len(windows) != 1:
        print(json.dumps({
            "status": "stopped",
            "finding": f"WEBULL_WINDOW_COUNT:{len(windows)}",
            "published": False,
        }))
        return 2

    def verify(requested: str, diagnostic: Path) -> str:
        print(f"Webull was asked to open {requested}.")
        print(f"Diagnostic: {diagnostic}")
        return input(
            "Type the exact ticker now visible in the Webull chart header: "
        )

    try:
        manifest, assets = capture_ticker_workflow(
            ticker=args.ticker,
            window=windows[0],
            output_directory=args.output_directory,
            verify_ticker=verify,
            capture_backend=backend,
        )
    except Exception as exc:
        print(json.dumps({
            "status": "stopped", "finding": str(exc), "published": False,
        }, sort_keys=True))
        return 2

    print(json.dumps({
        "status": "captured",
        "ticker": args.ticker.upper(),
        "assets": [str(path) for path in assets],
        "manifest": str(manifest),
        "published": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

