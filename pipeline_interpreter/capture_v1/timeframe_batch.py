"""Five-timeframe Webull shadow capture with deterministic selection checks."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from PIL import Image

from .backend import CaptureBackend, WindowsShadowBackend
from .contracts import WindowInfo
from .navigation import (
    FULL_CHART_INTERVAL_POINTS,
    WindowsNavigationDriver,
    NavigationDriver,
    open_chart_workspace,
)
from .privacy_crop import crop_chart_in_place
from .validation import validate_png


TIMEFRAME_ORDER = ("daily", "4h", "1h", "15m", "5m")
TIMEFRAME_SELECTION_ATTEMPTS = 3


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _selected_indicator_visible(image_path: Path, timeframe: str) -> bool:
    """Detect Webull's blue selected label/underline near the expected button."""
    point = FULL_CHART_INTERVAL_POINTS[timeframe]
    with Image.open(image_path).convert("RGB") as image:
        width, height = image.size
        center_x = round(width * point.x)
        left, right = max(0, center_x - 24), min(width, center_x + 24)
        top = max(0, round(height * 0.915))
        bottom = min(height, round(height * 0.955))
        region = image.crop((left, top, right, bottom))
        pixels = (
            region.get_flattened_data()
            if hasattr(region, "get_flattened_data")
            else region.getdata()
        )
        return any(
            blue > 145 and blue > red + 35 and blue > green + 15
            for red, green, blue in pixels
        )


def capture_timeframe_batch(
    *,
    ticker: str,
    window: WindowInfo,
    output_directory: Path,
    navigator: NavigationDriver | None = None,
    capture_backend: CaptureBackend | None = None,
    establish_chart_workspace: bool = True,
) -> tuple[Path, tuple[Path, ...]]:
    """Navigate/capture five charts; never publish outside the shadow directory."""
    ticker = ticker.strip().upper()
    navigator = navigator or WindowsNavigationDriver()
    capture_backend = capture_backend or WindowsShadowBackend()
    final_dir = output_directory.resolve()
    if final_dir.exists():
        raise FileExistsError(final_dir)
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{final_dir.name}.", dir=final_dir.parent))
    try:
        navigator.foreground(window)
        deadline = time.monotonic() + 2.0
        while not navigator.is_foreground(window):
            if time.monotonic() >= deadline:
                raise RuntimeError("WEBULL_FOREGROUND_NOT_CONFIRMED")
            time.sleep(0.05)
        # Enforce the workspace at the component boundary as well as in the
        # ticker workflow. This prevents callers or retries from inheriting an
        # Options/market-data screen before timeframe coordinates are used.
        if establish_chart_workspace:
            open_chart_workspace(window=window, driver=navigator)
        records, assets, hashes = [], [], set()
        for timeframe in TIMEFRAME_ORDER:
            selection_attempt = 0
            selected = False
            diagnostic = stage / f".{ticker}_{timeframe}_verification.png"
            while selection_attempt < TIMEFRAME_SELECTION_ATTEMPTS:
                selection_attempt += 1
                navigator.foreground(window)
                time.sleep(0.2)
                navigator.click_relative(
                    window, FULL_CHART_INTERVAL_POINTS[timeframe]
                )
                time.sleep(1.0)
                navigator.capture_screen_region(window, diagnostic)
                selected = _selected_indicator_visible(diagnostic, timeframe)
                diagnostic.unlink(missing_ok=True)
                if selected:
                    break
                # Allow Webull one bounded render recovery before retrying the
                # exact same allowlisted control.
                time.sleep(0.4)
            if not selected:
                raise RuntimeError(f"TIMEFRAME_SELECTION_NOT_VERIFIED:{timeframe}")
            asset = stage / f"{ticker}_{timeframe}.png"
            method = capture_backend.capture_window(window, asset)
            crop_metadata = crop_chart_in_place(asset)
            validation = validate_png(asset)
            if not validation.valid:
                raise RuntimeError("|".join(validation.findings))
            digest = _sha256(asset)
            if digest in hashes:
                raise RuntimeError(f"DUPLICATE_TIMEFRAME_CAPTURE:{timeframe}")
            hashes.add(digest)
            assets.append(asset)
            records.append({
                "timeframe": timeframe, "filename": asset.name,
                "sha256": digest, "width": validation.width,
                "height": validation.height, "capture_method": method,
                "selection_verification": "BLUE_INDICATOR_CONFIRMED",
                "selection_attempts": selection_attempt,
                "privacy_crop": crop_metadata,
            })
        manifest = stage / "timeframe_capture_manifest.json"
        manifest.write_text(json.dumps({
            "schema_version": "capture_v1.timeframe_batch.1",
            "ticker": ticker, "status": "captured",
            "timeframes": list(TIMEFRAME_ORDER), "assets": records,
            "privacy": {
                "uncropped_images_retained": False,
                "profile": "webull_chart_privacy_20260725_v1",
            },
            "published": False,
        }, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(stage, final_dir)
        return (
            final_dir / manifest.name,
            tuple(final_dir / asset.name for asset in assets),
        )
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
