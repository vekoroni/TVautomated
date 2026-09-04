"""Disabled-by-default feature flags for incremental CDS adoption."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping


def _as_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalised = value.strip().lower()
    if normalised in {"1", "true", "yes", "on"}:
        return True
    if normalised in {"0", "false", "no", "off", ""}:
        return False
    return default


@dataclass(frozen=True, slots=True)
class CanonicalFeatureFlags:
    """Controls CDS activation. Every switch defaults to off."""

    enabled: bool = False
    write_through: bool = False
    stage_gating_enforced: bool = False
    offline_replay: bool = False
    ohlcv_mode: str = "OFF"

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> "CanonicalFeatureFlags":
        env = os.environ if environment is None else environment
        mode = str(env.get("AVSHUNTER_CDS2_OHLCV_MODE", "OFF")).strip().upper()
        if mode not in {"OFF", "SHADOW", "ACTIVE"}:
            mode = "OFF"
        return cls(
            enabled=_as_bool(env.get("AVSHUNTER_CANONICAL_DATA_ENABLED")),
            write_through=_as_bool(env.get("AVSHUNTER_CANONICAL_WRITE_THROUGH")),
            stage_gating_enforced=_as_bool(
                env.get("AVSHUNTER_STAGE_GATING_ENFORCED")
            ),
            offline_replay=_as_bool(env.get("AVSHUNTER_CANONICAL_OFFLINE_REPLAY")),
            ohlcv_mode=mode,
        )
