"""Disabled-by-default rollout contract; not wired into production commands."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Callable, TypeVar


class RolloutMode(str, Enum):
    OFF = "OFF"
    SHADOW = "SHADOW"


@dataclass(frozen=True, slots=True)
class RolloutConfig:
    mode: RolloutMode = RolloutMode.OFF
    allow_production_routing: bool = False
    immediate_legacy_fallback: bool = True

    def __post_init__(self) -> None:
        if self.allow_production_routing:
            raise ValueError("automation_v2 production routing is not authorized")


def load_rollout_config(
    environment: dict[str, str] | None = None,
) -> RolloutConfig:
    source = environment if environment is not None else os.environ
    raw = source.get("AVSHUNTER_INTERPRETER_AUTOMATION_V2", "OFF").strip().upper()
    if raw not in {mode.value for mode in RolloutMode}:
        raise ValueError(f"unsupported automation_v2 rollout mode: {raw}")
    return RolloutConfig(mode=RolloutMode(raw))


T = TypeVar("T")


def run_with_legacy_fallback(
    *,
    config: RolloutConfig,
    legacy: Callable[[], T],
    shadow_observer: Callable[[], object] | None = None,
) -> T:
    """Always return the legacy result; shadow observation is non-authoritative."""
    legacy_result = legacy()
    if config.mode is RolloutMode.SHADOW and shadow_observer is not None:
        try:
            shadow_observer()
        except Exception:
            if not config.immediate_legacy_fallback:
                raise
    return legacy_result

