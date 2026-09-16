"""Versioned, append-only configuration registry (P0-2, spec Appendix B)."""

from .model import (
    AuthorityState,
    ConfigEntry,
    ConfigError,
    ConfigValue,
    UNITS,
    ValidationState,
    ValueType,
)
from .registry import ConfigRegistry, ConfigSnapshot

__all__ = [
    "AuthorityState",
    "ConfigEntry",
    "ConfigError",
    "ConfigRegistry",
    "ConfigSnapshot",
    "ConfigValue",
    "UNITS",
    "ValidationState",
    "ValueType",
]
