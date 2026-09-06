"""CLI for integrated Webull ticker and market-screen shadow capture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backend import WindowsShadowBackend
from .market_screen import MARKET_SCREEN_POINTS
from .ticker_market_screen import capture_ticker_market_screen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Switch ticker and capture one verified Webull market screen"
    )
    parser.add_argument("ticker")
    parser.add_argument("screen", choices=tuple(MARKET_SCREEN_POINTS))
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--confirm-ticker-market-screen-shadow", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_ticker_market_screen_shadow:
        parser.error("--confirm-ticker-market-screen-shadow is required")

    backend = WindowsShadowBackend()
    windows = tuple(item for item in backend.discover("Webull") if item.visible)
    if len(windows) != 1:
        print(json.dumps({
            "status": "stopped",
            "finding": f"WEBULL_WINDOW_COUNT:{len(windows)}",
            "published": False,
        }))
        return 2

    def verify(expected: str, diagnostic: Path) -> str:
        print(f"Requested ticker: {expected}")
        print(f"Market-screen diagnostic: {diagnostic}")
        return input(
            "Type the exact ticker visible inside the captured market screen: "
        )

    def verify_type(expected: str, _diagnostic: Path) -> str:
        return input(
            f"Type the visible market screen name (expected {expected}): "
        )

    try:
        result = capture_ticker_market_screen(
            ticker=args.ticker,
            screen=args.screen,
            window=windows[0],
            output_directory=args.output_directory,
            verify_screen_ticker=verify,
            verify_screen_type=verify_type,
        )
    except Exception as exc:
        print(json.dumps({
            "status": "stopped", "finding": str(exc), "published": False,
        }, sort_keys=True))
        return 2
    payload = {
        "status": "mapped_for_visual_review" if result.matched else "stopped",
        "ticker": args.ticker.upper(),
        "screen": args.screen,
        "finding": result.finding,
        "assets": [str(path) for path in result.assets],
        "diagnostic_image": str(result.diagnostic_image),
        "manifest": str(result.manifest),
        "published": False,
    }
    print(json.dumps(payload, sort_keys=True))
    return 0 if result.matched else 2


if __name__ == "__main__":
    raise SystemExit(main())

