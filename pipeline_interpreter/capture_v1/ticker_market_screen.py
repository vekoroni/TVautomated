"""Integrated ticker switch and verified market-screen shadow workflow."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .contracts import WindowInfo
from .market_screen import (
    TICKER_SCREEN_MISMATCH,
    map_market_screen,
    record_ticker_verification,
)
from .navigation import NavigationDriver, WindowsNavigationDriver
from .navigation import switch_ticker_for_visual_review


ScreenTickerVerifier = Callable[[str, Path], str]
ScreenTypeVerifier = Callable[[str, Path], str]
MARKET_SCREEN_TYPE_MISMATCH = "MARKET_SCREEN_TYPE_MISMATCH"

SCREEN_TYPE_ALIASES = {
    "options": {"options", "option"},
    "greeks": {
        "greeks", "optionsgreeks", "optionschaingreeks",
        "optionchaingreeks",
    },
    "tape": {"tape", "timesales", "timeandsales"},
    "orderbook": {"orderbook", "book"},
    "noii": {"noii", "imbalance", "orderimbalance"},
    "short": {"short", "shortinterest", "shortinterestdata"},
}


def _screen_token(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


@dataclass(frozen=True, slots=True)
class TickerMarketScreenResult:
    manifest: Path
    diagnostic_image: Path
    matched: bool
    finding: str | None
    assets: tuple[Path, ...] = ()


def capture_ticker_market_screen(
    *,
    ticker: str,
    screen: str,
    window: WindowInfo,
    output_directory: Path,
    verify_screen_ticker: ScreenTickerVerifier,
    verify_screen_type: ScreenTypeVerifier | None = None,
    driver: NavigationDriver | None = None,
) -> TickerMarketScreenResult:
    """Switch ticker, capture one read-only screen, and preserve mismatch evidence."""
    normalized = ticker.strip().upper()
    driver = driver or WindowsNavigationDriver()
    final_dir = output_directory.resolve()
    if final_dir.exists():
        raise FileExistsError(final_dir)
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{final_dir.name}.", dir=final_dir.parent))
    try:
        ticker_image, ticker_manifest = switch_ticker_for_visual_review(
            window=window,
            ticker=normalized,
            output_directory=stage / "ticker_selection",
            driver=driver,
        )
        screen_image, screen_manifest = map_market_screen(
            window=window,
            screen=screen,
            output_directory=stage / "market_screen",
            driver=driver,
        )
        observed = verify_screen_ticker(normalized, screen_image)
        ticker_matched = record_ticker_verification(
            manifest_path=screen_manifest,
            expected_ticker=normalized,
            observed_ticker=observed,
        )
        normalized_screen = screen.strip().lower()
        observed_screen = (
            verify_screen_type(normalized_screen, screen_image)
            if verify_screen_type is not None
            else normalized_screen
        )
        screen_matched = _screen_token(observed_screen) in SCREEN_TYPE_ALIASES[
            normalized_screen
        ]
        matched = ticker_matched and screen_matched
        if not ticker_matched:
            finding = TICKER_SCREEN_MISMATCH
        elif not screen_matched:
            finding = MARKET_SCREEN_TYPE_MISMATCH
        else:
            finding = None
        canonical_assets: list[Path] = []
        canonical_names = {
            "short": f"{normalized}_short.png",
            "greeks": f"{normalized}_options_chain_greeks.png",
        }
        if matched and normalized_screen in canonical_names:
            canonical = stage / canonical_names[normalized_screen]
            shutil.copy2(screen_image, canonical)
            canonical_assets.append(canonical)
        workflow_manifest = stage / "ticker_market_screen_manifest.json"
        workflow_manifest.write_text(
            json.dumps(
                {
                    "schema_version": "capture_v1.ticker_market_screen.1",
                    "ticker": normalized,
                    "screen": screen.strip().lower(),
                    "status": "mapped" if matched else "stopped",
                    "findings": [] if matched else [finding],
                    "ticker_selection": {
                        "diagnostic": str(ticker_image.relative_to(stage)).replace("\\", "/"),
                        "manifest": str(ticker_manifest.relative_to(stage)).replace("\\", "/"),
                    },
                    "market_screen": {
                        "diagnostic": str(screen_image.relative_to(stage)).replace("\\", "/"),
                        "manifest": str(screen_manifest.relative_to(stage)).replace("\\", "/"),
                    },
                    "screen_ticker_verification": {
                        "expected": normalized,
                        "observed": observed.strip().upper(),
                        "matched": ticker_matched,
                    },
                    "screen_type_verification": {
                        "expected": normalized_screen,
                        "observed": observed_screen.strip(),
                        "matched": screen_matched,
                    },
                    "assets": [
                        {
                            "filename": asset.name,
                            "role": (
                                "SHORT_INTEREST"
                                if normalized_screen == "short"
                                else "OPTIONS_CHAIN_GREEKS"
                            ),
                            "source": str(screen_image.relative_to(stage)).replace("\\", "/"),
                        }
                        for asset in canonical_assets
                    ],
                    "published": False,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        image_relative = screen_image.relative_to(stage)
        os.replace(stage, final_dir)
        return TickerMarketScreenResult(
            manifest=final_dir / workflow_manifest.name,
            diagnostic_image=final_dir / image_relative,
            matched=matched,
            finding=finding,
            assets=tuple(final_dir / asset.name for asset in canonical_assets),
        )
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise

