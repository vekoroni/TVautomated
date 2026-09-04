"""Runtime configuration for the governed MSI v1.1 rollout.

All switches default off.  Capturing new data and consuming it are separate so
the pipeline can collect additive evidence before a reader is promoted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Mapping


MSI_CONFIG_VERSION = "msi-runtime-v1.1"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "msi_runtime.json"
_ENV_BY_FIELD = {
    "v2_capture": "MSI_V2_CAPTURE",
    "cds_resolver": "MSI_CDS_RESOLVER",
    "minute_bars": "MSI_MINUTE_BARS",
    "structure": "MSI_STRUCTURE",
    "lab_v3_view": "MSI_LAB_V3_VIEW",
    "macro_advisory": "MSI_MACRO_ADVISORY",
    "interpreter_resolver": "MSI_INTERPRETER_RESOLVER",
    "screen_adapter": "MSI_SCREEN_ADAPTER",
}


def _flag(env: Mapping[str, str], name: str) -> bool:
    return str(env.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class MSIRuntimeFlags:
    v2_capture: bool = False
    cds_resolver: bool = False
    minute_bars: bool = False
    structure: bool = False
    lab_v3_view: bool = False
    macro_advisory: bool = False
    interpreter_resolver: bool = False
    screen_adapter: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "MSIRuntimeFlags":
        source = os.environ if env is None else env
        return cls(
            v2_capture=_flag(source, "MSI_V2_CAPTURE"),
            cds_resolver=_flag(source, "MSI_CDS_RESOLVER"),
            minute_bars=_flag(source, "MSI_MINUTE_BARS"),
            structure=_flag(source, "MSI_STRUCTURE"),
            lab_v3_view=_flag(source, "MSI_LAB_V3_VIEW"),
            macro_advisory=_flag(source, "MSI_MACRO_ADVISORY"),
            interpreter_resolver=_flag(source, "MSI_INTERPRETER_RESOLVER"),
            screen_adapter=_flag(source, "MSI_SCREEN_ADAPTER"),
        )

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)

    @property
    def fingerprint(self) -> str:
        payload = {
            "version": MSI_CONFIG_VERSION,
            "flags": self.to_dict(),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        return hashlib.sha256(encoded).hexdigest()


def active_flags(env: Mapping[str, str] | None = None) -> MSIRuntimeFlags:
    # Passing an explicit mapping is the deterministic unit-test/override path.
    if env is not None:
        return MSIRuntimeFlags.from_env(env)

    config_path = Path(os.environ.get("MSI_CONFIG_PATH", DEFAULT_CONFIG_PATH))
    merged: dict[str, str] = {}
    if config_path.is_file():
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"MSI runtime config is invalid: {config_path}: {error}") from error
        values = payload.get("flags", payload) if isinstance(payload, Mapping) else {}
        if not isinstance(values, Mapping):
            raise RuntimeError(f"MSI runtime config flags are invalid: {config_path}")
        for field, env_name in _ENV_BY_FIELD.items():
            if field in values:
                merged[env_name] = "1" if bool(values[field]) else "0"
            elif env_name in values:
                merged[env_name] = "1" if bool(values[env_name]) else "0"
    for env_name in _ENV_BY_FIELD.values():
        if env_name in os.environ:
            merged[env_name] = os.environ[env_name]
    return MSIRuntimeFlags.from_env(merged)


__all__ = [
    "DEFAULT_CONFIG_PATH",
    "MSI_CONFIG_VERSION",
    "MSIRuntimeFlags",
    "active_flags",
]
