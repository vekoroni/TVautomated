"""Resolve one immutable market-rate observation per run from governed macro."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
import hashlib, json, math
from pathlib import Path
from typing import Any, Mapping

MARKET_RATE_VERSION = "market_rate_observation_v1"

@dataclass(frozen=True, slots=True)
class MarketRateObservation:
    rate_annual_fraction: float | None
    rate_source: str
    rate_as_of: str | None
    dataset_id: str | None
    quality_state: str
    calculation_version: str = MARKET_RATE_VERSION
    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

def _walk(value: Any):
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)

def resolve_market_rate(payload: Mapping[str, Any], *, raw_bytes: bytes | None = None) -> MarketRateObservation:
    for node in _walk(payload):
        for key in ("t3m", "sofr", "fed_funds", "fed_funds_rate"):
            if key not in node:
                continue
            raw = node.get(key)
            if isinstance(raw, Mapping):
                raw = raw.get("value") or raw.get("rate")
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            fraction = value / 100.0 if abs(value) > 0.25 else value
            if not -0.05 <= fraction <= 0.25:
                continue
            as_of = node.get("rates_data_as_of") or node.get("as_of") or node.get("as_of_date")
            material = raw_bytes or json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
            dataset_id = str(payload.get("macro_packet_id") or payload.get("dataset_id") or hashlib.sha256(material).hexdigest())
            return MarketRateObservation(fraction, f"MACRO:{key.upper()}", str(as_of) if as_of else None, dataset_id, "PASS")
    return MarketRateObservation(None, "NONE", None, None, "RATE_UNAVAILABLE")

def load_market_rate(path: Path | str) -> MarketRateObservation:
    source = Path(path)
    if not source.is_file():
        return MarketRateObservation(None, "NONE", None, None, "RATE_UNAVAILABLE")
    raw = source.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return MarketRateObservation(None, "NONE", None, hashlib.sha256(raw).hexdigest(), "DATA_DEFECT")
    return resolve_market_rate(payload, raw_bytes=raw)


def rate_inputs(path: Path | str | None) -> dict:
    """The valuation engine's rate arguments for one run (G5, ACK 17 Oct 2026): the run's own observed rate.

    `path` is the run folder or any file inside it; the nearest macro_snapshot.json up to three levels up is the run's.
    Returns {"rate", "rate_basis"} for anticipated_move_fields / option_value. With no observed rate the rate is None
    and the basis says why, so the engine's governed fallback is used and labelled (missing is never neutral).
    """
    if path is None:
        return {"rate": None, "rate_basis": "RATE_UNAVAILABLE:NO_RUN"}
    start = Path(path)
    folders = [start] if start.is_dir() else []
    folders += list(start.parents)[:3]
    for folder in folders:
        snapshot = folder / "macro_snapshot.json"
        if snapshot.is_file():
            obs = load_market_rate(snapshot)
            if obs.quality_state == "PASS" and obs.rate_annual_fraction is not None:
                as_of = f" as of {obs.rate_as_of}" if obs.rate_as_of else ""
                return {"rate": obs.rate_annual_fraction, "rate_basis": f"{obs.rate_source}{as_of} run {folder.name}"}
            return {"rate": None, "rate_basis": f"RATE_UNAVAILABLE:{obs.quality_state} run {folder.name}"}
    return {"rate": None, "rate_basis": "RATE_UNAVAILABLE:NO_MACRO_SNAPSHOT"}
