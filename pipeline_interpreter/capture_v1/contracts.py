"""Immutable contracts for the screenshot capture boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


class CaptureMode(str, Enum):
    OFF = "OFF"
    DRY_RUN = "DRY_RUN"
    SHADOW = "SHADOW"
    ENABLED = "ENABLED"


class CaptureStatus(str, Enum):
    DISABLED = "disabled"
    VALIDATED = "validated"
    CAPTURED = "captured"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ViewSpec:
    name: str
    source: str
    required: bool = True
    timeframe: str = ""


DAILY_VIEW = ViewSpec("daily", "WEBULL", True, "D")


@dataclass(frozen=True, slots=True)
class CaptureRequest:
    ticker: str
    run_id: str
    invocation_id: str
    staging_root: Path
    mode: CaptureMode = CaptureMode.OFF
    views: tuple[ViewSpec, ...] = (DAILY_VIEW,)
    expected_window_pattern: str = "Webull"
    operator_confirmed_ticker: bool = False
    operator_confirmed_daily: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ticker = self.ticker.strip().upper()
        if not ticker or not ticker.replace(".", "").replace("-", "").isalnum():
            raise ValueError("invalid ticker")
        if not self.run_id.strip() or not self.invocation_id.strip():
            raise ValueError("run_id and invocation_id are required")
        if self.mode is CaptureMode.ENABLED:
            raise ValueError("capture_v1 cannot publish to production in phase 1")
        object.__setattr__(self, "ticker", ticker)
        object.__setattr__(self, "staging_root", Path(self.staging_root).resolve())
        object.__setattr__(self, "views", tuple(self.views))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class WindowInfo:
    handle: int
    title: str
    process_id: int
    visible: bool
    minimized: bool
    bounds: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class CaptureResult:
    ticker: str
    run_id: str
    invocation_id: str
    mode: CaptureMode
    status: CaptureStatus
    findings: tuple[str, ...]
    staging_directory: str = ""
    manifest_path: str = ""
    assets: tuple[str, ...] = ()
    published: bool = False
