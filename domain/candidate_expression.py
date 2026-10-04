"""C6 bounded long-option enumeration (AVS-SD-TEV-001/S2).

Pure, offline domain boundary. The caller supplies an explicit last exit date,
expiry buffer and breadth; this module never chooses a winner or computes EV.
It does not make broker calls and must not be used as an execution authority.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Mapping, Sequence

from canonical_data.option_identity import parse_occ_symbol
from canonical_data.session_clock import is_xnys_session, previous_xnys_session
from domain.ticker_forecast import (
    ForecastDirection, ForecastState, TickerForecast, option_right_for_forecast,
)


@dataclass(frozen=True, slots=True)
class CandidateExpression:
    run_id: str
    thesis_id: str
    ticker: str
    option_symbol: str
    option_right: str
    expiry_date: str
    strike: float
    quote_as_of_utc: str
    bid: float
    ask: float
    last_exit_date: str
    implied_vol: float | None = None
    contract_multiplier: int | None = None
    contract_multiplier_source: str | None = None
    expression_version: str = "candidate_expression_v1"


@dataclass(frozen=True, slots=True)
class CandidateExpressionSet:
    run_id: str
    thesis_id: str
    ticker: str
    forecast_state: ForecastState
    expression_state: str
    candidates: tuple[CandidateExpression, ...]
    rows_seen: int
    rejection_counts: dict[str, int]
    search_policy: dict[str, int | str]


def _finite_nonnegative(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _quote_time(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if stamp.tzinfo is not None else None


def enumerate_long_expressions(
    forecast: TickerForecast,
    chain: Sequence[Mapping[str, object]],
    *,
    last_exit_date: str,
    expiry_buffer_days: int,
    max_candidates: int,
    quote_cutoff_utc: str,
) -> CandidateExpressionSet:
    """Enumerate same-side contracts; preserve a reason for every chain row.

    The bounded search is intentionally policy-parameterized. The signed-off
    design has not yet approved a production breadth or expiry buffer.
    """
    if isinstance(expiry_buffer_days, bool) or not isinstance(expiry_buffer_days, int) or expiry_buffer_days < 0:
        raise ValueError("expiry_buffer_days must be a nonnegative integer")
    if isinstance(max_candidates, bool) or not isinstance(max_candidates, int) or max_candidates < 1:
        raise ValueError("max_candidates must be a positive integer")
    exit_date = date.fromisoformat(last_exit_date)
    if _quote_time(quote_cutoff_utc) is None:
        raise ValueError("quote_cutoff_utc must be a timezone-aware ISO timestamp")
    cutoff = datetime.fromisoformat(quote_cutoff_utc.replace("Z", "+00:00"))
    if exit_date < date.fromisoformat(forecast.evidence_session):
        raise ValueError("last_exit_date precedes forecast evidence session")
    policy = {"last_exit_date": last_exit_date, "expiry_buffer_days": expiry_buffer_days,
              "max_candidates": max_candidates, "quote_cutoff_utc": quote_cutoff_utc}
    if forecast.forecast_state in {ForecastState.INVALIDATED, ForecastState.DATA_INSUFFICIENT}:
        state = f"NOT_APPLICABLE_{forecast.forecast_state.value}"
        return CandidateExpressionSet(
            forecast.run_id, forecast.thesis_id, forecast.ticker,
            forecast.forecast_state, state, (), len(chain),
            {state: len(chain)} if chain else {}, policy,
        )
    if forecast.direction is ForecastDirection.NEUTRAL_RANGE:
        return CandidateExpressionSet(
            forecast.run_id, forecast.thesis_id, forecast.ticker,
            forecast.forecast_state, "NOT_APPLICABLE_NEUTRAL_RANGE", (), len(chain),
            {"NOT_APPLICABLE_NEUTRAL_RANGE": len(chain)} if chain else {}, policy,
        )
    right = option_right_for_forecast(forecast.direction)
    assert right in {"CALL", "PUT"}
    rejected: Counter[str] = Counter()
    eligible: list[CandidateExpression] = []
    symbol_counts: Counter[str] = Counter()
    for row in chain:
        if row.get("source_run_id") != forecast.run_id:
            continue
        try:
            symbol_counts[parse_occ_symbol(row.get("option_symbol")).symbol] += 1
        except ValueError:
            continue
    for row in chain:
        if row.get("source_run_id") != forecast.run_id:
            rejected["RUN_MISMATCH"] += 1
            continue
        try:
            identity = parse_occ_symbol(row.get("option_symbol"))
        except ValueError:
            rejected["INVALID_OCC"] += 1
            continue
        if symbol_counts[identity.symbol] > 1:
            rejected["DUPLICATE_SYMBOL"] += 1
            continue
        if identity.root != forecast.ticker:
            rejected["ROOT_MISMATCH"] += 1
            continue
        if identity.side != right:
            rejected["WRONG_SIDE"] += 1
            continue
        buffered_exit = identity.expiry - timedelta(days=expiry_buffer_days)
        if not is_xnys_session(buffered_exit):
            buffered_exit = previous_xnys_session(buffered_exit)
        contract_exit = min(exit_date, buffered_exit)
        if contract_exit <= date.fromisoformat(forecast.evidence_session):
            rejected["INSUFFICIENT_RUNWAY"] += 1
            continue
        bid, ask = _finite_nonnegative(row.get("bid")), _finite_nonnegative(row.get("ask"))
        if bid is None or ask is None or ask <= 0:
            rejected["MISSING_QUOTE"] += 1
            continue
        if bid > ask:
            rejected["CROSSED_QUOTE"] += 1
            continue
        quote_time = _quote_time(row.get("quote_as_of_utc"))
        if quote_time is None:
            rejected["MISSING_QUOTE_TIME"] += 1
            continue
        if datetime.fromisoformat(quote_time.replace("Z", "+00:00")) > cutoff:
            rejected["FUTURE_QUOTE"] += 1
            continue
        implied_vol = _finite_nonnegative(row.get("implied_vol"))
        multiplier_raw = _finite_nonnegative(row.get("contract_multiplier"))
        multiplier = (int(multiplier_raw) if multiplier_raw is not None
                      and multiplier_raw > 0 and multiplier_raw.is_integer() else None)
        eligible.append(CandidateExpression(
            forecast.run_id, forecast.thesis_id, forecast.ticker,
            identity.symbol, right, identity.expiry.isoformat(), identity.strike,
            quote_time, bid, ask, contract_exit.isoformat(), implied_vol, multiplier,
            str(row.get("contract_multiplier_source") or "").strip() or None,
        ))
    # Deterministic *enumeration*, not a forecast/EV ranking. All overflow is
    # counted rather than silently lost. Policy breadth awaits governance.
    eligible.sort(key=lambda item: (item.expiry_date, abs(item.strike - forecast.reference_spot), item.option_symbol))
    if len(eligible) > max_candidates:
        rejected["BOUNDED_SEARCH_OVERFLOW"] += len(eligible) - max_candidates
    candidates = tuple(eligible[:max_candidates])
    return CandidateExpressionSet(
        forecast.run_id, forecast.thesis_id, forecast.ticker,
        forecast.forecast_state,
        "CANDIDATES_UNVALUED" if candidates else "NO_SUITABLE_OPTION",
        candidates, len(chain), dict(sorted(rejected.items())), policy,
    )
