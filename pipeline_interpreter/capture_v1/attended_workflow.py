"""Attended end-to-end Webull evidence capture for one shadow ticker."""

from __future__ import annotations

import json
from pathlib import Path

from .backend import WindowsShadowBackend
from .navigation import WindowsNavigationDriver
from .noii_cross import capture_noii_crosses
from .ticker_batch import capture_ticker_workflow
from .ticker_market_screen import capture_ticker_market_screen


MARKET_SCREENS = ("options", "greeks", "tape", "orderbook", "short")


def run_attended_capture(
    *, ticker: str, output_directory: Path,
    automatic_ticker_acceptance: bool = False,
    chart_already_open: bool = False,
) -> Path:
    """Capture all twelve required assets using allowlisted Webull controls.

    Navigation and capture are automated. Exact ticker/screen transcription is
    intentionally retained as an attended shadow safety boundary.
    """
    symbol = ticker.strip().upper()
    final = output_directory.resolve()
    if final.exists():
        manifest = final / "attended_capture_manifest.json"
        if manifest.is_file():
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            if payload.get("ticker") == symbol and payload.get("status") == "captured":
                return manifest
        raise FileExistsError(final)

    backend = WindowsShadowBackend()
    windows = tuple(item for item in backend.discover("Webull") if item.visible)
    if len(windows) != 1:
        raise RuntimeError(f"WEBULL_WINDOW_COUNT:{len(windows)}")
    window = windows[0]
    if window.minimized:
        raise RuntimeError("WEBULL_MINIMIZED")
    driver = WindowsNavigationDriver()
    final.mkdir(parents=True)

    def verify_ticker(expected: str, diagnostic: Path) -> str:
        print(f"\n[{symbol}] Webull ticker diagnostic: {diagnostic}")
        if automatic_ticker_acceptance:
            print(f"[{symbol}] Ticker accepted automatically for shadow capture.")
            return expected
        return input(f"Type the exact ticker visible (expected {expected}): ")

    def verify_screen_type(expected: str, diagnostic: Path) -> str:
        print(f"[{symbol}] Screen diagnostic: {diagnostic}")
        return input(f"Type the visible screen name (expected {expected}): ")

    chart_manifest, chart_assets = capture_ticker_workflow(
        ticker=symbol,
        window=window,
        output_directory=final / "charts",
        verify_ticker=verify_ticker,
        navigator=driver,
        capture_backend=backend,
        establish_chart_workspace=not chart_already_open,
    )

    screen_manifests: list[str] = []
    for screen in MARKET_SCREENS:
        result = capture_ticker_market_screen(
            ticker=symbol,
            screen=screen,
            window=window,
            output_directory=final / f"screen_{screen}",
            verify_screen_ticker=verify_ticker,
            verify_screen_type=verify_screen_type,
            driver=driver,
        )
        if not result.matched:
            raise RuntimeError(result.finding or f"{screen.upper()}_CAPTURE_NOT_VERIFIED")
        screen_manifests.append(str(result.manifest))

    noii = capture_ticker_market_screen(
        ticker=symbol,
        screen="noii",
        window=window,
        output_directory=final / "screen_noii",
        verify_screen_ticker=verify_ticker,
        verify_screen_type=verify_screen_type,
        driver=driver,
    )
    if not noii.matched:
        raise RuntimeError(noii.finding or "NOII_CAPTURE_NOT_VERIFIED")

    def verify_cross(expected: str, diagnostic: Path) -> str:
        print(f"[{symbol}] NOII diagnostic: {diagnostic}")
        return input(f"Type the visible NOII cross tab (expected {expected}): ")

    cross_manifest, cross_assets = capture_noii_crosses(
        ticker=symbol,
        window=window,
        output_directory=final / "noii_crosses",
        verify_cross=verify_cross,
        driver=driver,
    )

    manifest = final / "attended_capture_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "capture_v1.attended_workflow.1",
                "ticker": symbol,
                "status": "captured",
                "chart_manifest": str(chart_manifest),
                "chart_assets": [str(path) for path in chart_assets],
                "screen_manifests": screen_manifests + [str(noii.manifest)],
                "noii_cross_manifest": str(cross_manifest),
                "noii_cross_assets": [str(path) for path in cross_assets],
                "published": False,
                "production_charts_touched": False,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return manifest
