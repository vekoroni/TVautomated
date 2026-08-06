"""Interactive shadow CLI for mapping Webull market-data screens."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backend import WindowsShadowBackend
from .market_screen import (
    MARKET_SCREEN_POINTS,
    TICKER_SCREEN_MISMATCH,
    map_market_screen,
    record_ticker_verification,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Map one read-only Webull market-data screen"
    )
    parser.add_argument("screen", choices=tuple(MARKET_SCREEN_POINTS))
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--confirm-market-screen-shadow", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_market_screen_shadow:
        parser.error("--confirm-market-screen-shadow is required")

    backend = WindowsShadowBackend()
    windows = tuple(item for item in backend.discover("Webull") if item.visible)
    if len(windows) != 1:
        print(json.dumps({
            "status": "stopped",
            "finding": f"WEBULL_WINDOW_COUNT:{len(windows)}",
            "published": False,
        }))
        return 2
    try:
        image, manifest = map_market_screen(
            window=windows[0],
            screen=args.screen,
            output_directory=args.output_directory,
        )
        observed = input(
            "Type the exact ticker visible inside the captured market screen: "
        )
        matched = record_ticker_verification(
            manifest_path=manifest,
            expected_ticker=args.ticker,
            observed_ticker=observed,
        )
    except Exception as exc:
        print(json.dumps({
            "status": "stopped", "finding": str(exc), "published": False,
        }, sort_keys=True))
        return 2
    if not matched:
        print(json.dumps({
            "status": "stopped",
            "finding": TICKER_SCREEN_MISMATCH,
            "expected_ticker": args.ticker.upper(),
            "observed_ticker": observed.strip().upper(),
            "diagnostic_image": str(image),
            "manifest": str(manifest),
            "published": False,
        }, sort_keys=True))
        return 2
    print(json.dumps({
        "status": "mapped_for_visual_review",
        "ticker": args.ticker.upper(),
        "screen": args.screen,
        "diagnostic_image": str(image),
        "manifest": str(manifest),
        "published": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
