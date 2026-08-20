"""EV Engine v3 Stage EV-0 contracts and barrier-outcome instrumentation.

This module is intentionally non-authoritative.  It validates candidate inputs and
builds an EV-specific historical barrier sidecar without changing the live
actuarial database or any downstream execution decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


EV3_STAGE0_VERSION = "ev3-stage0-v0.2.0"
EV3_INPUT_SCHEMA_VERSION = "ev3-input-v0.2.0"
EV3_BARRIER_SCHEMA_VERSION = "ev3-barrier-v0.2.0"

STATE_DIMENSIONS: tuple[str, ...] = (
    "vol_regime",
    "trend_direction",
    "structure_quality",
    "adx_bucket",
    "wyckoff_phase_bucket",
    "trend_maturity",
    "atr_pct_bucket",
)

DEFAULT_TARGET_GRID: tuple[float, ...] = (0.01, 0.02, 0.03, 0.05, 0.07, 0.10, 0.15, 0.20)
DEFAULT_STOP_GRID: tuple[float, ...] = (0.01, 0.02, 0.03, 0.05, 0.07, 0.10, 0.15)
DEFAULT_HORIZONS: tuple[int, ...] = (5, 10, 20)

ACCEPTED_DIRECTION_STATES = {
    "RESOLVED",
    "NO_CONFLICT",
    "MITIGATED",
    "ALIGNED",
    "OK",
    "AGREEMENT",
    "NO_PROBABILITY_OPINION",
}
REJECTED_DIRECTION_STATES = {
    "",
    "NOT_EVALUATED",
    "PENDING",
    "UNRESOLVED",
    "CONFLICT",
    "CONFLICTED",
    "BLOCKED",
}

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "ticker": ("ticker", "symbol", "underlying_symbol"),
    "canonical_direction": (
        "canonical_direction",
        "resolved_direction",
        "options_direction",
        "direction",
    ),
    "direction_status": (
        "direction_status",
        "direction_arbitration_status",
        "direction_conflict_status",
    ),
    "entry_spot": ("entry_spot", "signal_price", "underlying_price", "current_price"),
    "target_spot": ("target_spot", "target_price", "structural_target", "target_in_play"),
    "invalidation_spot": (
        "invalidation_spot",
        "invalidation_price",
        "invalidation_level",
        "structural_invalidation",
    ),
    "horizon_bucket": (
        "horizon_bucket",
        "preferred_horizon",
        "layer2__preferred_horizon",
        "actuarial_horizon_bucket",
    ),
    "planned_hold_sessions": (
        "planned_hold_sessions",
        "horizon_hold_sessions",
    ),
    "state_key": (
        "ev3_barrier_state_key",
        "state_key",
        "layer2__matched_state_key",
        "layer2__outcomes__matched_state_key",
    ),
    "contract_symbol": (
        "contract_symbol",
        "contract_occ_symbol",
        "recommended_contract",
        "occ_symbol",
    ),
    "strike": ("contract_strike", "strike"),
    "expiration": ("contract_expiry", "expiration", "expiry"),
    "quote_timestamp_utc": (
        "quote_timestamp_utc",
        "contract_quote_timestamp_utc",
        "contract_quote_timestamp",
        "options_as_of_utc",
    ),
    "bid": ("contract_bid", "option_bid", "bid"),
    "ask": ("contract_ask", "option_ask", "ask"),
    "dte_calendar": ("contract_dte", "dte", "days_to_expiry"),
    "delta": ("contract_delta", "option_delta", "delta"),
    "gamma": ("contract_gamma", "option_gamma", "gamma"),
    "theta": ("contract_theta", "option_theta", "theta"),
    "vega": ("contract_vega", "option_vega", "vega"),
    "implied_volatility": ("contract_iv", "implied_volatility", "iv"),
    "open_interest": ("contract_oi", "open_interest", "oi"),
    "volume": ("contract_volume", "option_volume", "volume"),
    "contract_multiplier": ("contract_multiplier", "multiplier"),
    "contract_structure": ("contract_structure", "structure"),
    "candidate_generation_rank": ("ev3_candidate_generation_rank", "candidate_generation_rank"),
    "candidate_policy_version": ("ev3_candidate_policy_version", "candidate_policy_version"),
    "risk_free_rate": ("risk_free_rate", "risk_free_rate_decimal"),
    "dividend_yield": ("dividend_yield", "dividend_yield_decimal"),
}


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _first_present(row: Mapping[str, Any], names: Iterable[str]) -> tuple[Any, str | None]:
    for name in names:
        if name in row and not _missing(row[name]):
            return row[name], name
    return None, None


def _number(value: Any) -> float | None:
    if _missing(value):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _normalise_direction(value: Any) -> str:
    text = str(value or "").strip().upper()
    mapping = {"LONG_CALL": "CALL", "BULLISH": "CALL", "LONG_PUT": "PUT", "BEARISH": "PUT"}
    return mapping.get(text, text)


def _normalise_horizon(value: Any) -> str:
    text = str(value or "").strip().upper().replace("–", "_").replace("-", "_")
    text = text.replace(" ", "")
    mapping = {
        "1_5D": "1_5D",
        "1_5": "1_5D",
        "5D": "1_5D",
        "5": "1_5D",
        "6_10D": "6_10D",
        "6_10": "6_10D",
        "10D": "6_10D",
        "10": "6_10D",
        "11_20D": "11_20D",
        "11_20": "11_20D",
        "20D": "11_20D",
        "20": "11_20D",
    }
    return mapping.get(text, text)


def _parse_timestamp(value: Any) -> pd.Timestamp | None:
    if _missing(value):
        return None
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if stamp.tzinfo is None:
        return None
    return stamp.tz_convert("UTC")


@dataclass(frozen=True)
class EV3ValidationResult:
    accepted: bool
    reason_code: str
    canonical: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)
    detail: str = ""

    def diagnostic_row(self, row_index: Any = None) -> dict[str, Any]:
        return {
            "row_index": row_index,
            "ticker": self.canonical.get("ticker", ""),
            "ev3_status": "ACCEPTED" if self.accepted else "REJECTED",
            "ev3_reason_code": self.reason_code,
            "ev3_reason_detail": self.detail,
            "ev3_input_schema_version": EV3_INPUT_SCHEMA_VERSION,
            "ev3_field_provenance": json.dumps(self.provenance, sort_keys=True),
        }


def validate_ev3_input(
    row: Mapping[str, Any],
    *,
    phase: str = "EOD",
    require_contract: bool = True,
    now_utc: Any = None,
    max_quote_age_seconds: int | None = None,
    minimum_open_interest: int = 0,
    minimum_volume: int = 0,
    expiry_buffer_days: int = 3,
) -> EV3ValidationResult:
    """Validate and canonicalise one EV3 input row without fabricating data."""

    canonical: dict[str, Any] = {
        "ev3_input_phase": str(phase).strip().upper(),
        "ev3_input_schema_version": EV3_INPUT_SCHEMA_VERSION,
    }
    provenance: dict[str, str] = {}

    def resolve(name: str) -> Any:
        value, source = _first_present(row, FIELD_ALIASES[name])
        if source is not None:
            provenance[name] = source
        return value

    ticker = str(resolve("ticker") or "").strip().upper()
    canonical["ticker"] = ticker
    if not ticker:
        return EV3ValidationResult(False, "REJECT_TICKER", canonical, provenance, "ticker missing")

    direction = _normalise_direction(resolve("canonical_direction"))
    canonical["canonical_direction"] = direction
    if direction not in {"CALL", "PUT"}:
        return EV3ValidationResult(
            False,
            "REJECT_DIRECTION_UNRESOLVED",
            canonical,
            provenance,
            f"direction={direction or 'MISSING'}",
        )

    direction_status = str(resolve("direction_status") or "").strip().upper()
    canonical["direction_status"] = direction_status
    if direction_status in REJECTED_DIRECTION_STATES or direction_status not in ACCEPTED_DIRECTION_STATES:
        return EV3ValidationResult(
            False,
            "REJECT_DIRECTION_UNRESOLVED",
            canonical,
            provenance,
            f"direction_status={direction_status or 'MISSING'}",
        )

    for field_name in ("entry_spot", "target_spot", "invalidation_spot"):
        canonical[field_name] = _number(resolve(field_name))
        if canonical[field_name] is None or canonical[field_name] <= 0:
            return EV3ValidationResult(
                False,
                "REJECT_THESIS_PRICE",
                canonical,
                provenance,
                f"{field_name} missing, non-numeric, or non-positive",
            )

    entry = canonical["entry_spot"]
    target = canonical["target_spot"]
    invalidation = canonical["invalidation_spot"]
    topology_valid = (
        invalidation < entry < target if direction == "CALL" else target < entry < invalidation
    )
    if not topology_valid:
        return EV3ValidationResult(
            False,
            "REJECT_THESIS_TOPOLOGY",
            canonical,
            provenance,
            f"{direction}: target={target}, entry={entry}, invalidation={invalidation}",
        )

    target_distance = abs(target - entry) / entry
    stop_distance = abs(entry - invalidation) / entry
    rr = target_distance / stop_distance if stop_distance > 0 else 0.0
    canonical.update(
        target_distance_fraction=target_distance,
        stop_distance_fraction=stop_distance,
        rr_underlying=rr,
    )
    if not math.isfinite(rr) or rr <= 0:
        return EV3ValidationResult(False, "REJECT_RR_ZERO", canonical, provenance, f"rr={rr}")

    horizon = _normalise_horizon(resolve("horizon_bucket"))
    hold = _number(resolve("planned_hold_sessions"))
    canonical["horizon_bucket"] = horizon
    canonical["planned_hold_sessions"] = int(hold) if hold is not None and hold.is_integer() else hold
    if horizon not in {"1_5D", "6_10D", "11_20D"} or hold is None or not hold.is_integer() or not 1 <= hold <= 20:
        return EV3ValidationResult(
            False,
            "REJECT_HORIZON",
            canonical,
            provenance,
            f"horizon={horizon or 'MISSING'}, planned_hold_sessions={hold}",
        )
    horizon_bounds = {"1_5D": (1, 5), "6_10D": (6, 10), "11_20D": (11, 20)}
    lower_hold, upper_hold = horizon_bounds[horizon]
    if not lower_hold <= int(hold) <= upper_hold:
        return EV3ValidationResult(
            False,
            "REJECT_HORIZON",
            canonical,
            provenance,
            f"planned_hold_sessions={int(hold)} outside {horizon}",
        )

    for horizon_days in (5, 10, 20):
        value, source = _first_present(
            row,
            (f"expected_move_{horizon_days}d", f"l3_expected_move_{horizon_days}d"),
        )
        if source is None:
            continue
        move = _number(value)
        if move is None or not 0 < move < 0.60:
            return EV3ValidationResult(
                False,
                "REJECT_UNIT_MOVE",
                canonical,
                provenance,
                f"{source}={value!r}; expected a fraction in (0, 0.60)",
            )
        provenance[f"expected_move_{horizon_days}d"] = source
        canonical[f"expected_move_{horizon_days}d"] = move

    if not require_contract:
        return EV3ValidationResult(True, "ACCEPTED_THESIS_ONLY", canonical, provenance)

    state_key = str(resolve("state_key") or "").strip()
    canonical["state_key"] = state_key
    if not state_key:
        return EV3ValidationResult(False, "REJECT_STATE_KEY", canonical, provenance, "state_key missing")

    contract_symbol = str(resolve("contract_symbol") or "").strip().upper()
    canonical["contract_symbol"] = contract_symbol
    if not contract_symbol:
        return EV3ValidationResult(False, "REJECT_CONTRACT_SYMBOL", canonical, provenance, "contract symbol missing")

    structure = str(resolve("contract_structure") or "LONG_SINGLE").strip().upper()
    canonical["contract_structure"] = structure
    if structure != "LONG_SINGLE":
        return EV3ValidationResult(
            False, "REJECT_STRUCTURE_UNSUPPORTED", canonical, provenance, f"structure={structure}"
        )
    canonical["candidate_generation_rank"] = _number(resolve("candidate_generation_rank"))
    canonical["candidate_policy_version"] = str(resolve("candidate_policy_version") or "").strip()

    strike = _number(resolve("strike"))
    canonical["strike"] = strike
    if strike is None or strike <= 0:
        return EV3ValidationResult(False, "REJECT_STRIKE", canonical, provenance, f"strike={strike}")

    expiration_value = resolve("expiration")
    expiration = None
    if not _missing(expiration_value):
        try:
            expiration = pd.Timestamp(expiration_value).date().isoformat()
        except (TypeError, ValueError):
            expiration = None
    canonical["expiration"] = expiration
    if expiration is None:
        return EV3ValidationResult(False, "REJECT_EXPIRATION", canonical, provenance, "expiration missing or invalid")

    quote_stamp = _parse_timestamp(resolve("quote_timestamp_utc"))
    canonical["quote_timestamp_utc"] = quote_stamp.isoformat() if quote_stamp is not None else None
    if quote_stamp is None:
        return EV3ValidationResult(
            False,
            "REJECT_QUOTE_TIMESTAMP",
            canonical,
            provenance,
            "timezone-aware quote timestamp missing",
        )

    if max_quote_age_seconds is None:
        max_quote_age_seconds = 24 * 60 * 60 if canonical["ev3_input_phase"] == "EOD" else 15 * 60
    now_stamp = pd.Timestamp(now_utc) if now_utc is not None else pd.Timestamp.now(tz="UTC")
    if now_stamp.tzinfo is None:
        now_stamp = now_stamp.tz_localize("UTC")
    else:
        now_stamp = now_stamp.tz_convert("UTC")
    quote_age = (now_stamp - quote_stamp).total_seconds()
    canonical["quote_age_seconds"] = quote_age
    canonical["quote_freshness_limit_seconds"] = max_quote_age_seconds
    if quote_age < 0 or quote_age > max_quote_age_seconds:
        return EV3ValidationResult(
            False,
            "REJECT_QUOTE_STALE",
            canonical,
            provenance,
            f"quote_age_seconds={quote_age:.1f}, maximum={max_quote_age_seconds}",
        )

    for name in ("bid", "ask", "dte_calendar", "delta", "gamma", "theta", "vega", "implied_volatility", "open_interest", "volume"):
        canonical[name] = _number(resolve(name))

    bid, ask = canonical["bid"], canonical["ask"]
    if bid is None or ask is None or bid < 0 or ask <= 0 or bid > ask:
        return EV3ValidationResult(False, "REJECT_QUOTE", canonical, provenance, f"bid={bid}, ask={ask}")
    canonical["mid"] = (bid + ask) / 2.0
    canonical["spread_fraction_mid"] = (ask - bid) / canonical["mid"] if canonical["mid"] > 0 else math.inf
    if not 0 <= canonical["spread_fraction_mid"] <= 1:
        return EV3ValidationResult(
            False,
            "REJECT_UNIT_SPREAD",
            canonical,
            provenance,
            f"spread_fraction_mid={canonical['spread_fraction_mid']}",
        )

    dte = canonical["dte_calendar"]
    if dte is None or not dte.is_integer() or not 1 <= dte <= 180:
        return EV3ValidationResult(False, "REJECT_DTE", canonical, provenance, f"dte={dte}")
    canonical["dte_calendar"] = int(dte)
    required_calendar_days = math.ceil(int(hold) * 7 / 5) + int(expiry_buffer_days)
    canonical["minimum_dte_calendar"] = required_calendar_days
    if int(dte) < required_calendar_days:
        return EV3ValidationResult(
            False,
            "REJECT_DTE_FEASIBILITY",
            canonical,
            provenance,
            f"dte={int(dte)}, required={required_calendar_days}, hold_sessions={int(hold)}",
        )

    delta = canonical["delta"]
    if delta is None or not 0 < abs(delta) < 1 or (direction == "CALL" and delta <= 0) or (direction == "PUT" and delta >= 0):
        return EV3ValidationResult(False, "REJECT_UNIT_DELTA", canonical, provenance, f"direction={direction}, delta={delta}")

    if canonical["gamma"] is None or canonical["gamma"] < 0:
        return EV3ValidationResult(False, "REJECT_UNIT_GAMMA", canonical, provenance, f"gamma={canonical['gamma']}")
    if canonical["theta"] is None:
        return EV3ValidationResult(False, "REJECT_UNIT_THETA", canonical, provenance, "theta missing or non-numeric")
    canonical["theta_decay_per_day"] = abs(canonical["theta"])
    if canonical["theta_decay_per_day"] > 0.20 * canonical["mid"]:
        return EV3ValidationResult(
            False,
            "REJECT_UNIT_THETA",
            canonical,
            provenance,
            f"theta_decay={canonical['theta_decay_per_day']}, mid={canonical['mid']}",
        )
    if canonical["vega"] is None or canonical["vega"] < 0:
        return EV3ValidationResult(False, "REJECT_UNIT_VEGA", canonical, provenance, f"vega={canonical['vega']}")
    iv = canonical["implied_volatility"]
    if iv is None or not 0 < iv <= 5:
        return EV3ValidationResult(False, "REJECT_UNIT_IV", canonical, provenance, f"iv={iv}")
    oi = canonical["open_interest"]
    volume = canonical["volume"]
    if oi is None or oi < minimum_open_interest or volume is None or volume < minimum_volume:
        return EV3ValidationResult(
            False,
            "REJECT_LIQUIDITY",
            canonical,
            provenance,
            f"open_interest={oi}, minimum_oi={minimum_open_interest}, "
            f"volume={volume}, minimum_volume={minimum_volume}",
        )

    multiplier_value = resolve("contract_multiplier")
    multiplier = _number(multiplier_value)
    canonical["contract_multiplier"] = multiplier
    if multiplier is None or multiplier <= 0:
        return EV3ValidationResult(
            False,
            "REJECT_CONTRACT_MULTIPLIER",
            canonical,
            provenance,
            f"multiplier={multiplier}",
        )

    rate = _number(resolve("risk_free_rate"))
    dividend_yield = _number(resolve("dividend_yield"))
    if rate is not None and not -0.05 <= rate <= 0.25:
        return EV3ValidationResult(False, "REJECT_UNIT_RATE", canonical, provenance, f"risk_free_rate={rate}")
    if dividend_yield is not None and not 0 <= dividend_yield <= 0.25:
        return EV3ValidationResult(False, "REJECT_UNIT_DIVIDEND", canonical, provenance, f"dividend_yield={dividend_yield}")
    canonical["risk_free_rate"] = rate
    canonical["dividend_yield"] = dividend_yield

    return EV3ValidationResult(True, "ACCEPTED", canonical, provenance)


def validate_ev3_dataframe(
    frame: pd.DataFrame,
    **kwargs: Any,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return canonical accepted rows and stable diagnostics for every input row."""

    accepted: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for index, row in frame.iterrows():
        result = validate_ev3_input(row.to_dict(), **kwargs)
        diagnostics.append(result.diagnostic_row(index))
        if result.accepted:
            canonical = dict(result.canonical)
            canonical["source_row_index"] = index
            canonical["ev3_field_provenance"] = json.dumps(result.provenance, sort_keys=True)
            accepted.append(canonical)
    return pd.DataFrame(accepted), pd.DataFrame(diagnostics)


@dataclass(frozen=True)
class BarrierGrid:
    targets: tuple[float, ...] = DEFAULT_TARGET_GRID
    stops: tuple[float, ...] = DEFAULT_STOP_GRID
    horizons: tuple[int, ...] = DEFAULT_HORIZONS
    shrinkage_k: float = 30.0

    def __post_init__(self) -> None:
        for label, values in (("targets", self.targets), ("stops", self.stops)):
            if not values or any(not 0 < float(value) < 0.60 for value in values):
                raise ValueError(f"{label} must contain fractions in (0, 0.60)")
            if tuple(sorted(set(values))) != tuple(values):
                raise ValueError(f"{label} must be unique and ascending")
        if not self.horizons or any(int(value) <= 0 for value in self.horizons):
            raise ValueError("horizons must be positive")
        if tuple(sorted(set(self.horizons))) != tuple(self.horizons):
            raise ValueError("horizons must be unique and ascending")
        if self.shrinkage_k <= 0:
            raise ValueError("shrinkage_k must be positive")


def build_state_key(frame: pd.DataFrame) -> pd.Series:
    missing = [name for name in STATE_DIMENSIONS if name not in frame.columns]
    if missing:
        raise ValueError(f"state frame missing dimensions: {', '.join(missing)}")
    if frame[list(STATE_DIMENSIONS)].isna().any().any():
        raise ValueError("state dimensions contain null values")
    return frame[list(STATE_DIMENSIONS)].astype(str).agg("|".join, axis=1)


def classify_barrier_path(
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    entry: float,
    direction: str,
    target_distance: float,
    stop_distance: float,
) -> tuple[str, int]:
    """Classify one forward OHLC path; same-bar double touches are ambiguous."""

    direction = _normalise_direction(direction)
    if direction not in {"CALL", "PUT"}:
        raise ValueError("direction must be CALL or PUT")
    if len(highs) != len(lows):
        raise ValueError("highs and lows must have equal length")
    if entry <= 0 or target_distance <= 0 or stop_distance <= 0:
        raise ValueError("entry and distances must be positive")

    if direction == "CALL":
        target_level = entry * (1 + target_distance)
        stop_level = entry * (1 - stop_distance)
        target_hits = np.asarray(highs, dtype=float) >= target_level
        stop_hits = np.asarray(lows, dtype=float) <= stop_level
    else:
        target_level = entry * (1 - target_distance)
        stop_level = entry * (1 + stop_distance)
        target_hits = np.asarray(lows, dtype=float) <= target_level
        stop_hits = np.asarray(highs, dtype=float) >= stop_level

    target_indices = np.flatnonzero(target_hits)
    stop_indices = np.flatnonzero(stop_hits)
    target_day = int(target_indices[0] + 1) if len(target_indices) else None
    stop_day = int(stop_indices[0] + 1) if len(stop_indices) else None
    if target_day is None and stop_day is None:
        return "TIMEOUT", len(highs)
    if target_day is not None and stop_day is not None and target_day == stop_day:
        return "AMBIGUOUS", target_day
    if stop_day is None or (target_day is not None and target_day < stop_day):
        return "TARGET_FIRST", int(target_day)
    return "STOP_FIRST", int(stop_day)


@dataclass
class _BarrierAccumulator:
    target_count: np.ndarray
    stop_count: np.ndarray
    timeout_count: np.ndarray
    ambiguous_count: np.ndarray
    target_day_sum: np.ndarray
    stop_day_sum: np.ndarray
    n_nominal: int = 0
    date_blocks: set[int] = field(default_factory=set)

    @classmethod
    def empty(cls, n_targets: int, n_stops: int) -> "_BarrierAccumulator":
        shape = (n_targets, n_stops)
        zeros_int = lambda: np.zeros(shape, dtype=np.int64)
        zeros_float = lambda: np.zeros(shape, dtype=np.float64)
        return cls(zeros_int(), zeros_int(), zeros_int(), zeros_int(), zeros_float(), zeros_float())


def _first_hit_days(mask: np.ndarray, missing_day: int) -> np.ndarray:
    any_hit = mask.any(axis=1)
    return np.where(any_hit, mask.argmax(axis=1) + 1, missing_day).astype(np.int16)


def _forward_matrix(values: np.ndarray, positions: np.ndarray, horizon: int) -> np.ndarray:
    """Return a padded forward matrix; unavailable right-edge sessions are NaN."""

    offsets = np.arange(1, horizon + 1, dtype=np.int64)
    indices = positions[:, None] + offsets[None, :]
    valid = indices < len(values)
    result = np.full(indices.shape, np.nan, dtype=float)
    result[valid] = values[indices[valid]]
    return result


def accumulate_ticker_barriers(
    state_rows: pd.DataFrame,
    history: pd.DataFrame,
    accumulators: dict[tuple[str, str, int], _BarrierAccumulator],
    grid: BarrierGrid,
) -> dict[str, int]:
    """Accumulate one ticker into global state/direction/horizon matrices."""

    required_history = {"date", "high", "low", "close"}
    missing_history = required_history.difference(history.columns)
    if missing_history:
        raise ValueError(f"history missing columns: {', '.join(sorted(missing_history))}")
    required_state = {"date", *STATE_DIMENSIONS}
    missing_state = required_state.difference(state_rows.columns)
    if missing_state:
        raise ValueError(f"state rows missing columns: {', '.join(sorted(missing_state))}")

    history = history.copy()
    history["date"] = pd.to_datetime(history["date"], errors="coerce").dt.normalize()
    history = history.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")
    for name in ("high", "low", "close"):
        history[name] = pd.to_numeric(history[name], errors="coerce")
    if history[["high", "low", "close"]].isna().any().any():
        raise ValueError("history contains invalid OHLC values")

    states = state_rows.copy()
    states["date"] = pd.to_datetime(states["date"], errors="coerce").dt.normalize()
    states = states.dropna(subset=["date"])
    states["state_key"] = build_state_key(states)

    date_to_position = {date: position for position, date in enumerate(history["date"])}
    states["_position"] = states["date"].map(date_to_position)
    missing_dates = int(states["_position"].isna().sum())
    states = states.dropna(subset=["_position"]).copy()
    states["_position"] = states["_position"].astype(int)
    maximum_horizon = max(grid.horizons)
    minimum_horizon = min(grid.horizons)
    mature_any = states["_position"] + minimum_horizon < len(history)
    immature_by_horizon = {
        int(horizon): int((states["_position"] + int(horizon) >= len(history)).sum())
        for horizon in grid.horizons
    }
    states = states.loc[mature_any].copy()
    if states.empty:
        return {
            "used_rows": 0,
            "missing_dates": missing_dates,
            "immature_rows_by_horizon": immature_by_horizon,
            "used_rows_by_horizon": {int(horizon): 0 for horizon in grid.horizons},
        }

    positions = states["_position"].to_numpy(dtype=np.int64)
    closes = history["close"].to_numpy(dtype=float)[positions]
    future_high = _forward_matrix(history["high"].to_numpy(dtype=float), positions, maximum_horizon)
    future_low = _forward_matrix(history["low"].to_numpy(dtype=float), positions, maximum_horizon)
    target_grid = np.asarray(grid.targets, dtype=float)
    stop_grid = np.asarray(grid.stops, dtype=float)
    missing_day = maximum_horizon + 1

    directional_days: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for direction in ("CALL", "PUT"):
        if direction == "CALL":
            target_masks = future_high[:, :, None] >= closes[:, None, None] * (1 + target_grid[None, None, :])
            stop_masks = future_low[:, :, None] <= closes[:, None, None] * (1 - stop_grid[None, None, :])
        else:
            target_masks = future_low[:, :, None] <= closes[:, None, None] * (1 - target_grid[None, None, :])
            stop_masks = future_high[:, :, None] >= closes[:, None, None] * (1 + stop_grid[None, None, :])
        target_days = np.column_stack(
            [_first_hit_days(target_masks[:, :, index], missing_day) for index in range(len(target_grid))]
        )
        stop_days = np.column_stack(
            [_first_hit_days(stop_masks[:, :, index], missing_day) for index in range(len(stop_grid))]
        )
        directional_days[direction] = (target_days, stop_days)

    state_values = states["state_key"].to_numpy(dtype=object)
    state_codes, unique_states = pd.factorize(state_values, sort=True)
    dates = states["date"].to_numpy(dtype="datetime64[D]").astype(np.int64)
    n_states = len(unique_states)
    matrix_shape = (n_states, len(target_grid), len(stop_grid))
    used_rows_by_horizon: dict[int, int] = {}
    for horizon in grid.horizons:
        horizon_mature = positions + int(horizon) < len(history)
        used_rows_by_horizon[int(horizon)] = int(horizon_mature.sum())
        if not horizon_mature.any():
            continue
        horizon_codes = state_codes[horizon_mature]
        state_counts = np.bincount(horizon_codes, minlength=n_states).astype(int)
        calendar_block_days = {5: 7, 10: 14, 20: 28}.get(horizon, max(horizon, 1))
        block_values = dates[horizon_mature] // calendar_block_days
        blocks_by_state = [set() for _ in range(n_states)]
        for code, block in np.unique(np.column_stack([horizon_codes, block_values]), axis=0):
            blocks_by_state[int(code)].add(int(block))

        for direction, (target_days_all, stop_days_all) in directional_days.items():
            target_days = target_days_all[horizon_mature]
            stop_days = stop_days_all[horizon_mature]
            target_3d = target_days[:, :, None]
            stop_3d = stop_days[:, None, :]
            target_in = target_3d <= horizon
            stop_in = stop_3d <= horizon
            ambiguous = target_in & stop_in & (target_3d == stop_3d)
            target_first = target_in & (~stop_in | (target_3d < stop_3d))
            stop_first = stop_in & (~target_in | (stop_3d < target_3d))
            timeout = ~(ambiguous | target_first | stop_first)

            local_target = np.zeros(matrix_shape, dtype=np.int64)
            local_stop = np.zeros(matrix_shape, dtype=np.int64)
            local_timeout = np.zeros(matrix_shape, dtype=np.int64)
            local_ambiguous = np.zeros(matrix_shape, dtype=np.int64)
            local_target_days = np.zeros(matrix_shape, dtype=np.float64)
            local_stop_days = np.zeros(matrix_shape, dtype=np.float64)
            np.add.at(local_target, horizon_codes, target_first)
            np.add.at(local_stop, horizon_codes, stop_first)
            np.add.at(local_timeout, horizon_codes, timeout)
            np.add.at(local_ambiguous, horizon_codes, ambiguous)
            np.add.at(local_target_days, horizon_codes, np.where(target_first, target_3d, 0))
            np.add.at(local_stop_days, horizon_codes, np.where(stop_first | ambiguous, stop_3d, 0))

            for code, state_key in enumerate(unique_states):
                if state_counts[code] == 0:
                    continue
                key = (str(state_key), direction, int(horizon))
                accumulator = accumulators.get(key)
                if accumulator is None:
                    accumulator = _BarrierAccumulator.empty(len(target_grid), len(stop_grid))
                    accumulators[key] = accumulator
                accumulator.target_count += local_target[code]
                accumulator.stop_count += local_stop[code]
                accumulator.timeout_count += local_timeout[code]
                accumulator.ambiguous_count += local_ambiguous[code]
                accumulator.target_day_sum += local_target_days[code]
                accumulator.stop_day_sum += local_stop_days[code]
                accumulator.n_nominal += int(state_counts[code])
                accumulator.date_blocks.update(blocks_by_state[code])

    return {
        "used_rows": len(states),
        "missing_dates": missing_dates,
        "immature_rows_by_horizon": immature_by_horizon,
        "used_rows_by_horizon": used_rows_by_horizon,
    }


def finalise_barrier_cache(
    accumulators: Mapping[tuple[str, str, int], _BarrierAccumulator],
    grid: BarrierGrid,
    *,
    calculation_version: str = EV3_STAGE0_VERSION,
    built_at_utc: str | None = None,
) -> pd.DataFrame:
    """Convert accumulated matrices to a versioned, shrunk barrier cache."""

    built_at = built_at_utc or datetime.now(timezone.utc).isoformat()
    prior_counts: dict[tuple[str, int, float, float], np.ndarray] = {}
    for (_, direction, horizon), acc in accumulators.items():
        for target_index, target in enumerate(grid.targets):
            for stop_index, stop in enumerate(grid.stops):
                key = (direction, horizon, target, stop)
                values = prior_counts.setdefault(key, np.zeros(4, dtype=np.int64))
                values += np.array(
                    [
                        acc.target_count[target_index, stop_index],
                        acc.stop_count[target_index, stop_index],
                        acc.timeout_count[target_index, stop_index],
                        acc.ambiguous_count[target_index, stop_index],
                    ],
                    dtype=np.int64,
                )

    rows: list[dict[str, Any]] = []
    for (state_key, direction, horizon), acc in sorted(accumulators.items()):
        n_nominal = int(acc.n_nominal)
        n_effective = min(n_nominal, len(acc.date_blocks))
        shrinkage_weight = n_effective / (n_effective + grid.shrinkage_k) if n_effective else 0.0
        for target_index, target in enumerate(grid.targets):
            for stop_index, stop in enumerate(grid.stops):
                target_count = int(acc.target_count[target_index, stop_index])
                stop_count = int(acc.stop_count[target_index, stop_index])
                timeout_count = int(acc.timeout_count[target_index, stop_index])
                ambiguous_count = int(acc.ambiguous_count[target_index, stop_index])
                total = target_count + stop_count + timeout_count + ambiguous_count
                if total != n_nominal:
                    raise ValueError(
                        f"barrier count invariant failed for {state_key}/{direction}/{horizon}/{target}/{stop}: "
                        f"total={total}, n_nominal={n_nominal}"
                    )
                if total <= 0:
                    continue

                # Same-bar ambiguity is allocated to the stop leg for the conservative EV probability.
                raw = np.array([target_count, stop_count + ambiguous_count, timeout_count], dtype=float) / total
                prior_values = prior_counts[(direction, horizon, target, stop)]
                prior_total = int(prior_values.sum())
                prior = np.array(
                    [prior_values[0], prior_values[1] + prior_values[3], prior_values[2]],
                    dtype=float,
                ) / prior_total
                adjusted = shrinkage_weight * raw + (1 - shrinkage_weight) * prior
                adjusted /= adjusted.sum()

                stop_denominator = stop_count + ambiguous_count
                row = {
                    "state_key": state_key,
                    "direction": direction,
                    "horizon_sessions": horizon,
                    "target_distance_fraction": target,
                    "stop_distance_fraction": stop,
                    "n_nominal": n_nominal,
                    "n_effective": n_effective,
                    "date_block_count": len(acc.date_blocks),
                    "target_count": target_count,
                    "stop_count": stop_count,
                    "timeout_count": timeout_count,
                    "ambiguous_count": ambiguous_count,
                    "p_target_first_raw": raw[0],
                    "p_stop_first_raw_conservative": raw[1],
                    "p_timeout_raw": raw[2],
                    "p_ambiguous_raw": ambiguous_count / total,
                    "p_target_first": adjusted[0],
                    "p_stop_first": adjusted[1],
                    "p_timeout": adjusted[2],
                    "probability_sum": float(adjusted.sum()),
                    "target_exit_session_mean": (
                        float(acc.target_day_sum[target_index, stop_index] / target_count)
                        if target_count
                        else np.nan
                    ),
                    "stop_exit_session_mean_conservative": (
                        float(acc.stop_day_sum[target_index, stop_index] / stop_denominator)
                        if stop_denominator
                        else np.nan
                    ),
                    "timeout_exit_session": horizon,
                    "shrinkage_weight": shrinkage_weight,
                    "shrinkage_k": grid.shrinkage_k,
                    "effective_n_method": "UNIQUE_CALENDAR_BLOCKS_V1",
                    "ambiguous_policy": "ALLOCATE_TO_STOP_FOR_PROBABILITY",
                    "calculation_version": calculation_version,
                    "schema_version": EV3_BARRIER_SCHEMA_VERSION,
                    "built_at_utc": built_at,
                }
                rows.append(row)
    result = pd.DataFrame(rows)
    if not result.empty:
        duplicate_key = [
            "state_key",
            "direction",
            "horizon_sessions",
            "target_distance_fraction",
            "stop_distance_fraction",
            "calculation_version",
        ]
        if result.duplicated(duplicate_key).any():
            raise ValueError("duplicate EV3 barrier cache keys")
        error = (result[["p_target_first", "p_stop_first", "p_timeout"]].sum(axis=1) - 1).abs().max()
        if error > 1e-9:
            raise ValueError(f"probability sum invariant failed: max_error={error}")
    return result


def merge_barrier_accumulators(
    target: dict[tuple[str, str, int], _BarrierAccumulator],
    source: Mapping[tuple[str, str, int], _BarrierAccumulator],
) -> None:
    """Merge independently accumulated ticker/chunk results in place."""

    for key, incoming in source.items():
        current = target.get(key)
        if current is None:
            target[key] = incoming
            continue
        current.target_count += incoming.target_count
        current.stop_count += incoming.stop_count
        current.timeout_count += incoming.timeout_count
        current.ambiguous_count += incoming.ambiguous_count
        current.target_day_sum += incoming.target_day_sum
        current.stop_day_sum += incoming.stop_day_sum
        current.n_nominal += incoming.n_nominal
        current.date_blocks.update(incoming.date_blocks)


def build_barrier_cache_from_frames(
    state_rows: pd.DataFrame,
    histories: Mapping[str, pd.DataFrame],
    *,
    grid: BarrierGrid | None = None,
    built_at_utc: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Small/in-memory build path used by regression tests and pilot runs."""

    grid = grid or BarrierGrid()
    if "ticker" not in state_rows.columns:
        raise ValueError("state rows missing ticker")
    accumulators: dict[tuple[str, str, int], _BarrierAccumulator] = {}
    coverage: dict[str, dict[str, int]] = {}
    for ticker, rows in state_rows.groupby(state_rows["ticker"].astype(str).str.upper(), sort=True):
        if ticker not in histories:
            coverage[ticker] = {"used_rows": 0, "missing_history": len(rows)}
            continue
        coverage[ticker] = accumulate_ticker_barriers(rows, histories[ticker], accumulators, grid)
    cache = finalise_barrier_cache(accumulators, grid, built_at_utc=built_at_utc)
    audit = barrier_cache_audit(cache)
    audit["ticker_coverage"] = coverage
    return cache, audit


def barrier_cache_audit(cache: pd.DataFrame) -> dict[str, Any]:
    if cache.empty:
        return {
            "status": "EMPTY",
            "rows": 0,
            "states": 0,
            "probability_sum_max_error": None,
            "duplicate_key_count": 0,
            "schema_version": EV3_BARRIER_SCHEMA_VERSION,
        }
    key = [
        "state_key",
        "direction",
        "horizon_sessions",
        "target_distance_fraction",
        "stop_distance_fraction",
        "calculation_version",
    ]
    probability_error = (
        cache[["p_target_first", "p_stop_first", "p_timeout"]].sum(axis=1) - 1
    ).abs()
    return {
        "status": "PASS" if float(probability_error.max()) <= 1e-9 and not cache.duplicated(key).any() else "FAIL",
        "rows": len(cache),
        "states": int(cache["state_key"].nunique()),
        "directions": sorted(cache["direction"].unique().tolist()),
        "horizons": sorted(int(value) for value in cache["horizon_sessions"].unique()),
        "probability_sum_max_error": float(probability_error.max()),
        "duplicate_key_count": int(cache.duplicated(key).sum()),
        "ambiguous_cell_observations": int(cache["ambiguous_count"].sum()),
        "schema_version": EV3_BARRIER_SCHEMA_VERSION,
        "calculation_versions": sorted(cache["calculation_version"].unique().tolist()),
    }


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
