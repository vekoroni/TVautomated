"""Combined ticker selection and five-timeframe shadow capture."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from .backend import CaptureBackend, WindowsShadowBackend
from .contracts import WindowInfo
from .navigation import NavigationDriver, WindowsNavigationDriver
from .navigation import switch_ticker_for_visual_review
from .timeframe_batch import capture_timeframe_batch


TickerVerifier = Callable[[str, Path], str]


def capture_ticker_workflow(
    *,
    ticker: str,
    window: WindowInfo,
    output_directory: Path,
    verify_ticker: TickerVerifier,
    navigator: NavigationDriver | None = None,
    capture_backend: CaptureBackend | None = None,
    establish_chart_workspace: bool = True,
) -> tuple[Path, tuple[Path, ...]]:
    """Select, manually verify, then capture; never publish partial output."""
    normalized = ticker.strip().upper()
    navigator = navigator or WindowsNavigationDriver()
    capture_backend = capture_backend or WindowsShadowBackend()
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
            driver=navigator,
        )
        observed = verify_ticker(normalized, ticker_image).strip().upper()
        if observed != normalized:
            raise RuntimeError(
                f"TICKER_EXACT_MATCH_NOT_CONFIRMED:{normalized}:{observed or 'EMPTY'}"
            )

        timeframe_manifest, assets = capture_timeframe_batch(
            ticker=normalized,
            window=window,
            output_directory=stage / "timeframes",
            navigator=navigator,
            capture_backend=capture_backend,
            establish_chart_workspace=establish_chart_workspace,
        )
        workflow_manifest = stage / "ticker_workflow_manifest.json"
        workflow_manifest.write_text(
            json.dumps(
                {
                    "schema_version": "capture_v1.ticker_workflow.1",
                    "ticker": normalized,
                    "status": "captured",
                    "ticker_verification": {
                        "method": "OPERATOR_EXACT_HEADER_TRANSCRIPTION",
                        "requested": normalized,
                        "observed": observed,
                        "matched": True,
                        "diagnostic": str(
                            ticker_image.relative_to(stage)
                        ).replace("\\", "/"),
                        "manifest": str(
                            ticker_manifest.relative_to(stage)
                        ).replace("\\", "/"),
                    },
                    "timeframe_manifest": str(
                        timeframe_manifest.relative_to(stage)
                    ).replace("\\", "/"),
                    "published": False,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        os.replace(stage, final_dir)
        return (
            final_dir / workflow_manifest.name,
            tuple(final_dir / asset.relative_to(stage) for asset in assets),
        )
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
