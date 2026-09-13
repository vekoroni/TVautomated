"""Single governed execution policy for production long options.

Both Morning Gate and the Intelligence Lab import these values so spread and
structure authority cannot drift between the two handoff stages.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from types import MappingProxyType
from typing import Any, Mapping


LONG_OPTION_POLICY_VERSION = "long-options-production-v1"
LONG_OPTION_EXECUTABLE_SPREAD_MAX_PCT = 18.0
LONG_OPTION_REVIEWABLE_SPREAD_MAX_PCT = 25.0
LONG_OPTION_ALLOWED_STRUCTURES = frozenset({"LONG_SINGLE"})
LONG_OPTION_ALLOWED_SIDES = frozenset({"CALL", "PUT"})
LONG_OPTION_ALLOWED_INSTRUMENTS = frozenset({"LONG_CALL", "LONG_PUT"})

LONG_OPTION_EXECUTION_POLICY = MappingProxyType(
    {
        "policy_version": LONG_OPTION_POLICY_VERSION,
        "allowed_structures": LONG_OPTION_ALLOWED_STRUCTURES,
        "allowed_sides": LONG_OPTION_ALLOWED_SIDES,
        "allowed_instruments": LONG_OPTION_ALLOWED_INSTRUMENTS,
        "executable_spread_max_pct": LONG_OPTION_EXECUTABLE_SPREAD_MAX_PCT,
        "reviewable_spread_max_pct": LONG_OPTION_REVIEWABLE_SPREAD_MAX_PCT,
    }
)

QUOTE_POLICY_VERSION = "long-options-quote-policy-v2"
QUOTE_SPREAD_DENOMINATOR = "MID"
EXECUTION_QUOTE_FRESHNESS_MAX_SECONDS = 15 * 60


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def quote_spread_fraction(bid: Any, ask: Any) -> float | None:
    """Return ``(ask-bid)/mid`` as a fraction for a valid two-sided quote.

    Every production consumer uses this definition.  Percentage display fields
    are derived with :func:`quote_spread_percent`; they are never reinterpreted
    heuristically as fractions.
    """
    bid_value = _finite(bid)
    ask_value = _finite(ask)
    if (
        bid_value is None
        or ask_value is None
        or bid_value < 0
        or ask_value <= 0
        or bid_value > ask_value
    ):
        return None
    mid = (bid_value + ask_value) / 2.0
    if mid <= 0:
        return None
    return (ask_value - bid_value) / mid


def quote_spread_percent(bid: Any, ask: Any) -> float | None:
    spread = quote_spread_fraction(bid, ask)
    return spread * 100.0 if spread is not None else None


def quote_age_seconds(
    observed_at: Any,
    *,
    as_of_utc: datetime | str | None = None,
) -> float | None:
    """Calculate quote age from an ISO or epoch provider timestamp.

    Epoch seconds, milliseconds, microseconds and nanoseconds are accepted.
    Missing or invalid timestamps stay missing; callers must not stamp age zero.
    """
    if observed_at in (None, ""):
        return None
    observed: datetime | None = None
    numeric = _finite(observed_at)
    if numeric is not None:
        absolute = abs(numeric)
        scale = 1.0
        if absolute >= 1e18:
            scale = 1e9
        elif absolute >= 1e15:
            scale = 1e6
        elif absolute >= 1e12:
            scale = 1e3
        try:
            observed = datetime.fromtimestamp(numeric / scale, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            observed = None
    if observed is None:
        try:
            text = str(observed_at).strip().replace("Z", "+00:00")
            observed = datetime.fromisoformat(text)
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
            observed = observed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None

    if isinstance(as_of_utc, datetime):
        as_of = as_of_utc
    elif as_of_utc:
        try:
            as_of = datetime.fromisoformat(str(as_of_utc).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        as_of = datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    age = (as_of.astimezone(timezone.utc) - observed).total_seconds()
    return max(0.0, age)


def evaluate_execution_viability(
    row: Mapping[str, Any],
    hydrated: Mapping[str, Any],
    *,
    as_of_utc: datetime | str | None = None,
) -> dict[str, Any]:
    """Evaluate observable execution quality without forecasting profitability.

    This is the hard execution-evidence contract.  EV, R:R and target-scenario
    valuation are deliberately absent.
    """
    symbol = str(
        hydrated.get("selected_contract_symbol")
        or row.get("morning_selected_contract_symbol")
        or row.get("contract_symbol")
        or ""
    ).strip()
    structure = str(
        hydrated.get("selected_structure")
        or row.get("selected_structure")
        or row.get("contract_structure")
        or ""
    ).strip().upper()
    instrument = str(
        hydrated.get("instrument")
        or row.get("instrument")
        or row.get("options_strategy")
        or ""
    ).strip().upper()
    if not structure and instrument in LONG_OPTION_ALLOWED_INSTRUMENTS:
        structure = "LONG_SINGLE"
    status = str(
        hydrated.get("selected_structure_hydration_status")
        or row.get("selected_structure_hydration_status")
        or ""
    ).strip().upper()
    leg = hydrated.get("selected_long_leg")
    if not isinstance(leg, Mapping):
        direct_bid = hydrated.get("live_contract_bid", hydrated.get("bid"))
        direct_ask = hydrated.get("live_contract_ask", hydrated.get("ask"))
        if direct_bid not in (None, "") or direct_ask not in (None, ""):
            leg = {"bid": direct_bid, "ask": direct_ask}
            if not status:
                status = "COMPLETE"
    base = {
        "execution_viability_policy_version": QUOTE_POLICY_VERSION,
        "execution_viability_contract_symbol": symbol,
        "execution_viability_eligible": False,
        "execution_viability_reviewable": False,
        "execution_viability_spread_denominator": QUOTE_SPREAD_DENOMINATOR,
    }
    if status != "COMPLETE":
        return {
            **base,
            "execution_viability_state": "DATA_MISSING",
            "execution_viability_reason": "SELECTED_STRUCTURE_NOT_HYDRATED",
        }
    if structure not in LONG_OPTION_ALLOWED_STRUCTURES:
        return {
            **base,
            "execution_viability_state": "UNSUPPORTED_STRUCTURE",
            "execution_viability_reason": "PRODUCTION_REQUIRES_LONG_SINGLE",
        }
    if not isinstance(leg, Mapping):
        return {
            **base,
            "execution_viability_state": "DATA_MISSING",
            "execution_viability_reason": "SELECTED_LONG_LEG_MISSING",
        }
    bid = _finite(leg.get("bid"))
    ask = _finite(leg.get("ask"))
    if bid is None or ask is None:
        return {
            **base,
            "execution_viability_state": "DATA_MISSING",
            "execution_viability_reason": "BID_OR_ASK_MISSING",
        }
    if bid < 0 or ask <= 0 or bid > ask:
        return {
            **base,
            "execution_viability_state": "INVALID_QUOTE",
            "execution_viability_reason": "NEGATIVE_CROSSED_OR_NON_POSITIVE_ASK",
        }
    provider_timestamp = (
        hydrated.get("selected_quote_timestamp_utc")
        or hydrated.get("quote_provider_timestamp_utc")
        or hydrated.get("live_contract_provider_updated")
        or row.get("quote_provider_timestamp_utc")
        or row.get("selected_quote_timestamp_utc")
    )
    age = quote_age_seconds(provider_timestamp, as_of_utc=as_of_utc)
    if age is None:
        return {
            **base,
            "execution_viability_state": "CURRENT_QUOTE_UNAVAILABLE",
            "execution_viability_reason": "PROVIDER_QUOTE_TIMESTAMP_REQUIRED",
            "execution_viability_quote_age_seconds": None,
        }
    spread_pct = quote_spread_percent(bid, ask)
    details = {
        **base,
        "execution_viability_bid": bid,
        "execution_viability_ask": ask,
        "execution_viability_spread_pct": spread_pct,
        "execution_viability_spread_fraction_mid": (
            spread_pct / 100.0 if spread_pct is not None else None
        ),
        "execution_viability_quote_provider_timestamp_utc": str(provider_timestamp),
        "execution_viability_quote_age_seconds": age,
    }
    if age > EXECUTION_QUOTE_FRESHNESS_MAX_SECONDS:
        return {
            **details,
            "execution_viability_state": "REQUOTE_REQUIRED",
            "execution_viability_reason": "PROVIDER_QUOTE_OUTSIDE_FRESHNESS_WINDOW",
        }
    if bid == 0:
        return {
            **details,
            "execution_viability_state": "ZERO_BID_REVIEW",
            "execution_viability_reason": "ONE_SIDED_ZERO_BID",
        }
    if spread_pct is None:
        return {
            **details,
            "execution_viability_state": "INVALID_QUOTE",
            "execution_viability_reason": "SPREAD_NOT_COMPUTABLE",
        }
    if spread_pct > LONG_OPTION_REVIEWABLE_SPREAD_MAX_PCT:
        return {
            **details,
            "execution_viability_state": "BLOCKED_WIDE_SPREAD",
            "execution_viability_reason": "SPREAD_ABOVE_REVIEW_MAXIMUM",
        }
    if spread_pct > LONG_OPTION_EXECUTABLE_SPREAD_MAX_PCT:
        return {
            **details,
            "execution_viability_state": "MANUAL_LIQUIDITY_REVIEW",
            "execution_viability_reason": "SPREAD_ABOVE_EXECUTABLE_MAXIMUM",
            "execution_viability_reviewable": True,
        }
    return {
        **details,
        "execution_viability_state": "EXECUTABLE_QUOTE",
        "execution_viability_reason": "VALID_TWO_SIDED_QUOTE_WITHIN_SPREAD_POLICY",
        "execution_viability_eligible": True,
        "execution_viability_reviewable": True,
    }
