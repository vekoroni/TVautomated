"""Stable result serialization shared by CLI and batch manifests."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


def to_plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, MappingProxyType):
        return {str(key): to_plain(item) for key, item in value.items()}
    if is_dataclass(value):
        return {
            item.name: to_plain(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): to_plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_plain(item) for item in value]
    return value
