from __future__ import annotations

import argparse
import json
from pathlib import Path

from .backend import WindowsShadowBackend
from .navigation import RelativePoint
from .noii_cross import capture_noii_crosses


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Capture NOII opening/closing crosses")
    parser.add_argument("ticker")
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--navigation-profile", type=Path)
    parser.add_argument("--confirm-ticker-noii-visible", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_ticker_noii_visible:
        parser.error("--confirm-ticker-noii-visible is required")
    backend = WindowsShadowBackend()
    windows = tuple(w for w in backend.discover("Webull") if w.visible)
    if len(windows) != 1:
        print(json.dumps({"status": "stopped", "finding": f"WEBULL_WINDOW_COUNT:{len(windows)}", "published": False}))
        return 2

    print(
        "Starting-state requirement: select Opening Cross in Webull. "
        "The workflow will capture it, then navigate to Closing Cross."
    )

    def verify(phase, _image):
        return input(f"Type the visible NOII cross tab for {phase}: ")
    closing_point = None
    if args.navigation_profile:
        profile = json.loads(
            args.navigation_profile.read_text(encoding="utf-8")
        )
        if profile.get("schema_version") != "capture_v1.noii_navigation_profile.1":
            parser.error("unsupported NOII navigation profile")
        point = profile.get("relative_point", {})
        closing_point = RelativePoint(float(point["x"]), float(point["y"]))
    try:
        manifest, assets = capture_noii_crosses(
            ticker=args.ticker, window=windows[0],
            output_directory=args.output_directory, verify_cross=verify,
            closing_point=closing_point,
        )
    except Exception as exc:
        print(json.dumps({"status": "stopped", "finding": str(exc), "published": False}, sort_keys=True))
        return 2
    print(json.dumps({"status": "captured", "ticker": args.ticker.upper(),
        "assets": [str(p) for p in assets], "manifest": str(manifest),
        "published": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
