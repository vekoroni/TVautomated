"""One-time live calibration for the Webull NOII Closing Cross control."""

from __future__ import annotations

import argparse
import ctypes
import json
import time
from pathlib import Path

from .backend import WindowsShadowBackend


class Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Calibrate the NOII Closing Cross")
    parser.add_argument("--output-file", type=Path, required=True)
    parser.add_argument("--countdown", type=int, default=5)
    args = parser.parse_args(argv)

    windows = tuple(
        window for window in WindowsShadowBackend().discover("Webull")
        if window.visible
    )
    if len(windows) != 1:
        print(json.dumps({
            "status": "stopped",
            "finding": f"WEBULL_WINDOW_COUNT:{len(windows)}",
            "published": False,
        }, sort_keys=True))
        return 2

    print(
        "Move the mouse to the CENTRE of the Closing Cross tab and keep it "
        "there. Do not click."
    )
    for remaining in range(max(1, args.countdown), 0, -1):
        print(f"Capturing cursor position in {remaining}...")
        time.sleep(1)

    cursor = Point()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(cursor)):
        print(json.dumps({
            "status": "stopped", "finding": "CURSOR_POSITION_READ_FAILED",
            "published": False,
        }, sort_keys=True))
        return 2

    window = windows[0]
    left, top, right, bottom = window.bounds
    width, height = right - left, bottom - top
    relative_x = (cursor.x - left) / width
    relative_y = (cursor.y - top) / height
    if not 0.0 <= relative_x <= 1.0 or not 0.0 <= relative_y <= 1.0:
        print(json.dumps({
            "status": "stopped",
            "finding": "CURSOR_OUTSIDE_WEBULL_WINDOW",
            "published": False,
        }, sort_keys=True))
        return 2

    payload = {
        "schema_version": "capture_v1.noii_navigation_profile.1",
        "control": "closing_cross",
        "relative_point": {"x": relative_x, "y": relative_y},
        "window_bounds": list(window.bounds),
        "published": False,
    }
    target = args.output_file.resolve()
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps({
        "status": "calibrated", "profile": str(target),
        "relative_point": payload["relative_point"], "published": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

