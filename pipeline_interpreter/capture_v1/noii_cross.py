"""Dual Opening/Closing Cross capture from an already verified NOII screen."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable

from .contracts import WindowInfo
from .navigation import NavigationDriver, RelativePoint, SafeZone
from .navigation import WindowsNavigationDriver
from .privacy_crop import WEBULL_MARKET_SCREEN_PRIVACY_CROP, crop_chart_in_place
from .validation import validate_png


NOII_CROSS_POINTS = {
    # Opening is the operator-verified starting state and is not clicked.
    # Calibrated to the centre of the adjacent Closing Cross button in the
    # current full-width Webull NOII layout.
    "close": RelativePoint(0.232, 0.106),
}
NOII_CROSS_ZONE = SafeZone("noii_cross_tabs", 0.21, 0.095, 0.25, 0.12)
NOII_CROSS_LABELS = {
    "open": {"openingcross", "open"},
    "close": {"closingcross", "close"},
}


def _token(value: str) -> str:
    return "".join(c for c in value.lower() if c.isalnum())


def capture_noii_crosses(
    *,
    ticker: str,
    window: WindowInfo,
    output_directory: Path,
    verify_cross: Callable[[str, Path], str],
    driver: NavigationDriver | None = None,
    closing_point: RelativePoint | None = None,
) -> tuple[Path, tuple[Path, ...]]:
    """Capture both crosses; fail atomically if either tab is not confirmed."""
    ticker = ticker.strip().upper()
    driver = driver or WindowsNavigationDriver()
    closing_point = closing_point or NOII_CROSS_POINTS["close"]
    final_dir = output_directory.resolve()
    if final_dir.exists():
        raise FileExistsError(final_dir)
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{final_dir.name}.", dir=final_dir.parent))
    records, assets, hashes = [], [], set()
    try:
        driver.foreground(window)
        for phase in ("open", "close"):
            # Capture the already-visible Opening Cross first. Only after it is
            # verified do we navigate to Closing Cross. This makes the state
            # transition explicit and prevents a bad Opening coordinate from
            # silently capturing Closing twice.
            if phase == "close":
                point = closing_point
                if not 0.0 <= point.x <= 1.0 or not 0.0 <= point.y <= 1.0:
                    raise RuntimeError(
                        f"UNSAFE_NAVIGATION_TARGET:noii_cross_tabs:{phase}"
                    )
                driver.click_relative(window, point)
                time.sleep(1.5)
            asset = stage / (
                f"{ticker}_orderbook_imbalance_{phase}.png"
            )
            driver.capture_screen_region(window, asset)
            crop = crop_chart_in_place(
                asset,
                WEBULL_MARKET_SCREEN_PRIVACY_CROP,
                profile="webull_noii_cross_privacy_20260726_v1",
            )
            validation = validate_png(asset)
            if not validation.valid:
                raise RuntimeError("|".join(validation.findings))
            observed = verify_cross(phase, asset)
            if _token(observed) not in NOII_CROSS_LABELS[phase]:
                raise RuntimeError(
                    f"NOII_CROSS_TYPE_MISMATCH:{phase}:{observed.strip() or 'EMPTY'}"
                )
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()
            if digest in hashes:
                raise RuntimeError("DUPLICATE_NOII_CROSS_CAPTURE")
            hashes.add(digest)
            assets.append(asset)
            records.append({
                "phase": phase, "filename": asset.name, "sha256": digest,
                "observed_label": observed.strip(), "privacy_crop": crop,
            })
        manifest = stage / "noii_cross_manifest.json"
        manifest.write_text(json.dumps({
            "schema_version": "capture_v1.noii_cross.1",
            "ticker": ticker, "status": "captured", "assets": records,
            "published": False,
        }, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(stage, final_dir)
        return final_dir / manifest.name, tuple(
            final_dir / item.name for item in assets
        )
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
