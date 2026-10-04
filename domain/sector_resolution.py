"""One owner for a row's sector (XLU-D03, ACK 2 Oct 2026).

A placeholder sector (ETF, FUND, blank, ...) resolves through the ticker's sector ETF to its
GICS sector using config/sector_etf_map_v1.json. Returns the upper-case sector or "".
"""
from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any, Mapping

MAP_PATH = Path(__file__).resolve().parents[1] / "config" / "sector_etf_map_v1.json"


@functools.lru_cache(maxsize=1)
def sector_map() -> dict:
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip().upper()


def resolve_sector(row: Mapping[str, Any]) -> str:
    cfg = sector_map()
    placeholders = {p.upper() for p in cfg["placeholder_sectors"]}
    for key in ("gics_sector_norm", "gics_sector", "sector"):
        value = _text(row.get(key))
        if value and value not in placeholders:
            return value
    for key in ("sector_etf", "sector_etf_mapped", "ticker"):
        mapped = cfg["etf_to_sector"].get(_text(row.get(key)))
        if mapped:
            return mapped
    return ""
