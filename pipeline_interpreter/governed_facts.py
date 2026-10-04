"""Deterministic governed facts for the Interpreter narrative (ACK 2 Oct 2026).

XLU-D07/D08: spot-versus-level sides are computed here, never inferred by the model.
XLU-D14: per-ticker gamma levels carry their chain source, as-of and scope.
XLU-D02: macro rates come from the governed record; rate figures in the narrative that the
governed facts do not hold are flagged.
Pure functions; no I/O.
"""
from __future__ import annotations

import math
import re
from typing import Any, Iterable, Mapping, Optional

SCOPE_NOTE = ("Per-ticker gamma from this ticker's option chain (all listed expiries in the fetched "
              "window, summed by strike); not the market-level Money Index GEX")
READINGS = {
    ("gamma_flip", "SPOT_ABOVE_LEVEL"): "spot is above the gamma flip",
    ("gamma_flip", "SPOT_BELOW_LEVEL"): "spot is below the gamma flip",
    ("call_wall", "SPOT_BELOW_LEVEL"): "call wall above spot: overhead resistance",
    ("call_wall", "SPOT_ABOVE_LEVEL"): "spot is above the call wall: the wall has been exceeded",
    ("put_wall", "SPOT_ABOVE_LEVEL"): "put wall below spot: support below",
    ("put_wall", "SPOT_BELOW_LEVEL"): "spot is below the put wall: the wall has been broken",
}
RATE_WORDS = re.compile(r"(10[- ]?y(ea)?r|10y|ten[- ]year|treasury|yield|t10y|2[- ]?y(ea)?r|fed funds|rates?\b)", re.I)
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s?%")


def _positive(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def level_relations(row: Mapping[str, Any], *, spot: Any, spot_source: str = "UNSPECIFIED") -> dict:
    price = _positive(spot)
    out: dict = {"spot": price, "spot_source": spot_source, "authority": "DETERMINISTIC_GOVERNED_FACT"}
    if price is None:
        out["state"] = "SPOT_UNAVAILABLE"
        return out
    out["state"] = "COMPUTED"
    for name in ("gamma_flip", "call_wall", "put_wall"):
        level = _positive(row.get(name))
        if level is None:
            out[name] = {"level": None, "side": "LEVEL_UNAVAILABLE"}
            continue
        side = "SPOT_ABOVE_LEVEL" if price > level else "SPOT_BELOW_LEVEL" if price < level else "SPOT_AT_LEVEL"
        out[name] = {"level": level, "side": side,
                     "distance_pct": round((price / level - 1.0) * 100.0, 4),
                     "reading": READINGS.get((name, side), "spot is at the level")}
    return out


def gamma_provenance(row: Mapping[str, Any]) -> dict:
    fields = {
        "chain_dataset_id": row.get("option_chain_dataset_id"),
        "chain_provider": row.get("option_chain_provider"),
        "chain_resolution": row.get("option_chain_resolution"),
        "chain_as_of": row.get("quote_as_of") or row.get("selected_quote_timestamp_utc"),
        "gamma_flip_method": row.get("gamma_flip_state") or row.get("gamma_flip_method"),
        "gamma_surface_source": row.get("gamma_island_source") or row.get("gamma_surface_source"),
    }
    recorded = any(v not in (None, "") for v in fields.values())
    return {"state": "RECORDED" if recorded else "SOURCE_NOT_RECORDED", "scope": "PER_TICKER_OPTION_CHAIN",
            "scope_note": SCOPE_NOTE, **fields}


def macro_rates(row: Mapping[str, Any], morning_fields: Optional[Mapping[str, Any]]) -> dict:
    sources = [morning_fields or {}, row]
    def first(*names):
        for source in sources:
            for name in names:
                value = source.get(name)
                if value not in (None, ""):
                    return value
        return None
    t10y = first("t10y", "macro_t10y", "us10y")
    out = {
        "t10y_pct": _positive(t10y),
        "macro_context_state": first("macro_context_state"),
        "macro_rates_context": first("macro_rates_context"),
        "macro_packet_id": first("macro_packet_id"),
        "authority": "GOVERNED_RECORD_ONLY",
    }
    out["state"] = ("AVAILABLE" if out["t10y_pct"] is not None or out["macro_rates_context"]
                    else "NOT_IN_GOVERNED_EVIDENCE")
    return out


def unverified_rate_claims(texts: Iterable[str], rates: Mapping[str, Any], *, tolerance_pct: float = 0.05) -> list:
    """Percent figures written next to rate words that the governed rates do not hold."""
    known = [v for v in (rates.get("t10y_pct"),) if isinstance(v, (int, float))]
    flagged: list = []
    for text in texts:
        for sentence in re.split(r"(?<=[.;!?])\s+", str(text or "")):
            if not RATE_WORDS.search(sentence):
                continue
            for match in PERCENT.finditer(sentence):
                value = float(match.group(1))
                if not any(abs(value - k) <= tolerance_pct for k in known):
                    flagged.append(match.group(0).replace(" ", ""))
    return flagged
