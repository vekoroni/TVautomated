"""Pure, advisory-only normalisation of exact-symbol tastytrade quote snapshots.

No broker client, account data, pipeline verdict or capital decision belongs in
this domain boundary. An observed quote supports human review, not an order.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Mapping

from canonical_data.option_identity import normalise_occ_symbol


def _utc(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp is missing")
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _decimal(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a price or size")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid decimal") from exc
    if not result.is_finite() or result < 0:
        raise ValueError("non-finite or negative decimal")
    return str(result)


def _symbol(value: Any, instrument_type: str) -> str:
    if instrument_type == "Equity Option":
        return normalise_occ_symbol(value)
    if instrument_type != "Equity":
        raise ValueError("unsupported broker instrument type")
    symbol = str(value or "").strip().upper()
    if not symbol or any(char.isspace() for char in symbol):
        raise ValueError("invalid equity symbol")
    return symbol


@dataclass(frozen=True, slots=True)
class BrokerQuoteObservation:
    requested_symbol: str
    broker_symbol: str | None
    instrument_type: str
    provider: str
    provider_updated_at_utc: str | None
    fetched_at_utc: str
    bid: str | None
    ask: str | None
    bid_size: str | None
    ask_size: str | None
    identity_state: str
    time_state: str
    quote_state: str
    multiplier_state: str
    supports_execution_review: bool
    observation_hash: str | None
    authority: str = "ADVISORY_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def observe_tastytrade_quote(
    payload: Mapping[str, Any] | list[Mapping[str, Any]], *,
    requested_symbol: str, instrument_type: str, fetched_at_utc: str,
    selected_contract_multiplier: int | None = None,
    broker_contract_multiplier: int | None = None,
) -> BrokerQuoteObservation:
    """Select one exact quote; never substitute another symbol or quote time.

    Option multiplier must be verified against independent broker instrument
    metadata. Neither a standard 100x multiplier nor quote fetch time is
    inferred. An unavailable quote stays an explicit unavailable observation.
    """
    wanted = _symbol(requested_symbol, instrument_type)
    fetched = _utc(fetched_at_utc)
    items = payload.get("items") if isinstance(payload, Mapping) else payload
    if not isinstance(items, list) or any(not isinstance(row, Mapping) for row in items):
        raise ValueError("broker quote payload requires an items array")
    matches = []
    for row in items:
        if row.get("instrument-type") != instrument_type:
            continue
        try:
            symbol = _symbol(row.get("symbol"), instrument_type)
        except ValueError:
            continue
        if symbol == wanted:
            matches.append(row)
    if len(matches) > 1:
        raise ValueError("ambiguous duplicate exact-symbol broker quotes")
    row = matches[0] if matches else None
    if instrument_type == "Equity Option":
        if (type(selected_contract_multiplier) is not int
                or type(broker_contract_multiplier) is not int
                or selected_contract_multiplier <= 0 or broker_contract_multiplier <= 0):
            multiplier_state = "UNVERIFIED"
        elif selected_contract_multiplier != broker_contract_multiplier:
            multiplier_state = "MISMATCH"
        else:
            multiplier_state = "VERIFIED"
    else:
        multiplier_state = "NOT_APPLICABLE"
    if row is None:
        return BrokerQuoteObservation(
            wanted, None, instrument_type, "TASTYTRADE", None, fetched,
            None, None, None, None, "NOT_RETURNED", "NO_PROVIDER_TIME",
            "NO_QUOTE", multiplier_state, False, None,
        )
    timestamp = row.get("updated-at")
    try:
        provider_time = _utc(timestamp)
        time_state = (
            "AFTER_FETCH" if provider_time > fetched else "PROVIDER_TIME_PRESENT"
        )
    except ValueError:
        provider_time, time_state = None, "PROVIDER_TIME_MISSING"
    try:
        bid = _decimal(row.get("bid"))
        ask = _decimal(row.get("ask"))
        bid_size = _decimal(row.get("bid-size"))
        ask_size = _decimal(row.get("ask-size"))
        if row.get("is-trading-halted") is True:
            quote_state = "HALTED"
        elif bid is None and ask is None:
            quote_state = "NO_QUOTE"
        elif bid is None or ask is None or Decimal(bid) == 0 or Decimal(ask) == 0:
            quote_state = "ONE_SIDED"
        elif Decimal(bid) > Decimal(ask):
            quote_state = "CROSSED"
        elif bid_size is None or ask_size is None:
            quote_state = "SIZE_MISSING"
        elif Decimal(bid_size) == 0 or Decimal(ask_size) == 0:
            quote_state = "NO_DISPLAYED_SIZE"
        else:
            quote_state = "TWO_SIDED_OBSERVED"
    except ValueError:
        bid = ask = bid_size = ask_size = None
        quote_state = "INVALID_QUOTE_DATA"
    observation_hash = hashlib.sha256(json.dumps(
        dict(row), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    return BrokerQuoteObservation(
        wanted, wanted, instrument_type, "TASTYTRADE", provider_time, fetched,
        bid, ask, bid_size, ask_size, "EXACT_SYMBOL", time_state,
        quote_state, multiplier_state,
        time_state == "PROVIDER_TIME_PRESENT"
        and quote_state == "TWO_SIDED_OBSERVED"
        and multiplier_state in ("VERIFIED", "NOT_APPLICABLE"),
        observation_hash,
    )
