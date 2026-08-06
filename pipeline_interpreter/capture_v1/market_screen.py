"""Allowlisted Webull market-screen navigation for shadow calibration."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from .contracts import WindowInfo
from .navigation import NavigationDriver, RelativePoint, SafeZone
from .navigation import WindowsNavigationDriver
from .privacy_crop import (
    WEBULL_MARKET_SCREEN_PRIVACY_CROP,
    crop_chart_in_place,
)
from .validation import validate_png


# Calibrated against the accepted full-window Webull layout. This phase maps
# only primary read-only tabs; controls that can submit or modify orders are
# deliberately outside the allowlisted zone.
MARKET_SCREEN_POINTS = {
    # Recalibrated after the 2026-07 Webull Desktop update. Coordinates use
    # the full application window with the Watchlists rail visible.
    "options": RelativePoint(0.161, 0.046),
    # Dedicated verification route for an Options chain layout with the
    # Greeks columns visible. It opens the same read-only primary tab.
    "greeks": RelativePoint(0.161, 0.046),
    "tape": RelativePoint(0.209, 0.046),
    "orderbook": RelativePoint(0.265, 0.046),
    "noii": RelativePoint(0.308, 0.046),
    # Read-only Short Interest tab in the accepted full-window Webull strip.
    "short": RelativePoint(0.583, 0.046),
}
MARKET_SCREEN_TAB_ZONE = SafeZone(
    "market_screen_tabs", 0.14, 0.035, 0.61, 0.06
)
TICKER_SCREEN_MISMATCH = "TICKER_SCREEN_MISMATCH"


def record_ticker_verification(
    *,
    manifest_path: Path,
    expected_ticker: str,
    observed_ticker: str,
) -> bool:
    """Record the operator's exact screen-ticker transcription and mismatch flag."""
    expected = expected_ticker.strip().upper()
    observed = observed_ticker.strip().upper()
    matched = bool(expected) and observed == expected
    metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata["ticker_verification"] = {
        "method": "OPERATOR_EXACT_SCREEN_TRANSCRIPTION",
        "expected": expected,
        "observed": observed,
        "matched": matched,
    }
    metadata["status"] = "mapped" if matched else "stopped"
    metadata["findings"] = [] if matched else [TICKER_SCREEN_MISMATCH]
    metadata["pipeline_published"] = False
    manifest_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return matched


def map_market_screen(
    *,
    window: WindowInfo,
    screen: str,
    output_directory: Path,
    driver: NavigationDriver | None = None,
) -> tuple[Path, Path]:
    """Open one read-only market tab and emit cropped calibration evidence."""
    normalized = screen.strip().lower()
    point = MARKET_SCREEN_POINTS.get(normalized)
    if point is None:
        raise ValueError(f"UNSUPPORTED_MARKET_SCREEN:{screen}")
    if not MARKET_SCREEN_TAB_ZONE.contains(point):
        raise RuntimeError(f"UNSAFE_NAVIGATION_TARGET:market_screen_tabs:{normalized}")

    driver = driver or WindowsNavigationDriver()
    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise FileExistsError(output_directory)
    output_directory.mkdir(parents=True)
    image_path = output_directory / f"webull_{normalized}_screen_map.png"
    manifest_path = output_directory / "market_screen_map.json"
    try:
        driver.foreground(window)
        deadline = time.monotonic() + 2.0
        while not driver.is_foreground(window):
            if time.monotonic() >= deadline:
                raise RuntimeError("WEBULL_FOREGROUND_NOT_CONFIRMED")
            time.sleep(0.05)
        time.sleep(0.35)
        driver.click_relative(window, point)
        time.sleep(2.0)
        driver.capture_screen_region(window, image_path)
        privacy_crop = crop_chart_in_place(
            image_path,
            WEBULL_MARKET_SCREEN_PRIVACY_CROP,
            profile="webull_market_screen_privacy_20260726_v1",
        )
        validation = validate_png(image_path)
        if not validation.valid:
            raise RuntimeError(
                "MARKET_SCREEN_DIAGNOSTIC_INVALID:"
                + "|".join(validation.findings)
            )
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "capture_v1.market_screen_map.1",
                    "screen": normalized,
                    "action": "OPEN_READ_ONLY_MARKET_SCREEN",
                    "allowed_control": "market_screen_tabs",
                    "point": {"x": point.x, "y": point.y},
                    "diagnostic_image": image_path.name,
                    "verification": "VISUAL_REVIEW_REQUIRED",
                    "ticker_verification": "NOT_PERFORMED",
                    "status": "awaiting_ticker_verification",
                    "findings": [],
                    "privacy_crop": privacy_crop,
                    "uncropped_image_retained": False,
                    "pipeline_published": False,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return image_path, manifest_path
    except Exception:
        shutil.rmtree(output_directory, ignore_errors=True)
        raise
