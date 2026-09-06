"""Fail-closed orchestration for isolated screenshot capture."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .backend import CaptureBackend, WindowsShadowBackend
from .contracts import CaptureMode, CaptureRequest, CaptureResult, CaptureStatus
from .validation import validate_png


FORBIDDEN_TITLE_TOKENS = ("order entry", "trade ticket", "place order", "confirm order")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_capture(request: CaptureRequest, backend: CaptureBackend | None = None) -> CaptureResult:
    """Discover and optionally shadow-capture; never publish to MA_Inputs/charts."""
    if request.mode is CaptureMode.OFF:
        return CaptureResult(
            request.ticker, request.run_id, request.invocation_id,
            request.mode, CaptureStatus.DISABLED, ("CAPTURE_DISABLED",),
        )
    backend = backend or WindowsShadowBackend()
    windows = tuple(w for w in backend.discover(request.expected_window_pattern) if w.visible)
    if not windows:
        return CaptureResult(
            request.ticker, request.run_id, request.invocation_id,
            request.mode, CaptureStatus.STOPPED, ("WEBULL_WINDOW_NOT_FOUND",),
        )
    if len(windows) != 1:
        return CaptureResult(
            request.ticker, request.run_id, request.invocation_id,
            request.mode, CaptureStatus.STOPPED,
            (f"AMBIGUOUS_WEBULL_WINDOWS:{len(windows)}",),
        )
    window = windows[0]
    forbidden = next(
        (token for token in FORBIDDEN_TITLE_TOKENS if token in window.title.casefold()), ""
    )
    if forbidden:
        return CaptureResult(
            request.ticker, request.run_id, request.invocation_id,
            request.mode, CaptureStatus.STOPPED,
            (f"FORBIDDEN_TRADING_SURFACE:{forbidden.upper().replace(' ', '_')}",),
        )
    if window.minimized:
        return CaptureResult(
            request.ticker, request.run_id, request.invocation_id,
            request.mode, CaptureStatus.STOPPED, ("WEBULL_MINIMIZED",),
        )
    if request.mode is CaptureMode.DRY_RUN:
        return CaptureResult(
            request.ticker, request.run_id, request.invocation_id,
            request.mode, CaptureStatus.VALIDATED,
            ("DAILY_VIEW_NAVIGATION_NOT_YET_ENABLED",), published=False,
        )
    confirmations = []
    if not request.operator_confirmed_ticker:
        confirmations.append("OPERATOR_TICKER_CONFIRMATION_REQUIRED")
    if not request.operator_confirmed_daily:
        confirmations.append("OPERATOR_DAILY_VIEW_CONFIRMATION_REQUIRED")
    if confirmations:
        return CaptureResult(
            request.ticker, request.run_id, request.invocation_id,
            request.mode, CaptureStatus.STOPPED, tuple(confirmations), published=False,
        )

    final_dir = request.staging_root / request.run_id / request.ticker / request.invocation_id
    if final_dir.exists():
        raise FileExistsError(final_dir)
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{request.invocation_id}.", dir=final_dir.parent))
    try:
        assets: list[Path] = []
        records = []
        for view in request.views:
            if view.name != "daily":
                raise RuntimeError(f"VIEW_NOT_IMPLEMENTED:{view.name}")
            path = stage / f"{request.ticker}_{view.name}.png"
            capture_method = backend.capture_window(window, path)
            validation = validate_png(path)
            if not validation.valid:
                raise RuntimeError("|".join(validation.findings))
            assets.append(path)
            records.append(
                {
                    "view": view.name, "source": view.source,
                    "timeframe": view.timeframe, "filename": path.name,
                    "size_bytes": path.stat().st_size, "sha256": _sha256(path),
                    "captured_at": _timestamp(),
                    "width": validation.width, "height": validation.height,
                    "format": validation.format,
                    "capture_method": capture_method,
                    "ticker_validation": "OPERATOR_CONFIRMED",
                    "timeframe_validation": "OPERATOR_CONFIRMED",
                }
            )
        manifest = {
            "schema_version": "capture_v1.manifest.1", "ticker": request.ticker,
            "run_id": request.run_id, "invocation_id": request.invocation_id,
            "mode": request.mode.value, "status": CaptureStatus.CAPTURED.value,
            "window": {"title": window.title, "process_id": window.process_id},
            "operator_attestation": {
                "ticker_visible": request.operator_confirmed_ticker,
                "daily_timeframe_visible": request.operator_confirmed_daily,
            },
            "assets": records, "published": False,
        }
        (stage / "capture_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        os.replace(stage, final_dir)
        return CaptureResult(
            request.ticker, request.run_id, request.invocation_id,
            request.mode, CaptureStatus.CAPTURED, (), str(final_dir),
            str(final_dir / "capture_manifest.json"),
            tuple(str(final_dir / path.name) for path in assets), False,
        )
    except Exception as exc:
        shutil.rmtree(stage, ignore_errors=True)
        return CaptureResult(
            request.ticker, request.run_id, request.invocation_id,
            request.mode, CaptureStatus.FAILED, (str(exc),), published=False,
        )

