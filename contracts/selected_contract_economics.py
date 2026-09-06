"""Canonical selected-option hydration and trader-facing monetisability.

The morning gate uses this module after a structure has been selected.  It is
deliberately provider-agnostic: callers supply one exact-symbol quote function.
No alternative contract is allowed to populate the selected structure unless
every selected leg has been hydrated successfully.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import math
import re
from typing import Any, Callable, Dict, Iterable, List, Mapping

from contracts.long_option_policy import quote_spread_fraction


RR_CALCULATION_VERSION = "selected-contract-rr-v1"
MONETISABILITY_CALCULATION_VERSION = "expiry-intrinsic-floor-v2-advisory"
#: AVS-FIX-001 W1.3 (QT-D07). Every monetisability outcome carries this,
#: including FAILED and DATA_MISSING: the reader must never have to infer
#: from a blank whether the figure was advisory. The value is the member
#: AVS-SD-002 Phase 2 pinned; AVS-FIX-001 named it "ADVISORY_ONLY", which
#: means the same thing but is not the vocabulary in use, and binding
#: rule 9 forbids introducing a second name for one state.
MONETISABILITY_AUTHORITY = "ADVISORY_SCENARIO_ONLY"
MONETISABILITY_MIN_PROFIT_PCT = 20.0

# ---------------------------------------------------------------------------
# AVS-FIX-001 W3.4 (RCA3-D05, DEC-1) — the second, ADVISORY-ONLY valuation.
#
# `monetisability_state` values the contract at its EXPIRY INTRINSIC floor:
# max(target - strike, 0) for a call. That is deliberately conservative and
# deliberately biased in one direction -- it can only ever understate a
# position, because it prices away every day of remaining time value. RCA-003
# D-05 measured the cost of that bias: rows that reach their target with
# real time value left are labelled NOT_MONETISABLE.
#
# This adds a SECOND record beside the intrinsic one. It never replaces it and
# never touches it. `monetisability_state` remains the floor and remains what
# every existing consumer reads; `monetisability_state_timevalue` is the
# Black-Scholes value of the same contract at `structural_target` on the final
# session of the hold, against the same 20% profit floor.
#
# The model is named on every row rather than assumed:
#   sigma = contract_iv held constant from selection
#   r = 0, q = 0
#   T = max(dte - hold_days, 0) / 365
# Holding IV constant is the assumption most likely to be wrong, and it is
# stated in `monetisability_timevalue_assumptions` on every row so a reader
# never has to infer it.
#
# AUTHORITY: ADVISORY_ONLY. It changes nothing downstream. It grants no
# permission, removes none, and the Execution Gate remains the sole writer of
# `final_action`.
# ---------------------------------------------------------------------------
MONETISABILITY_TIMEVALUE_MODEL = "BS_CONST_IV_R0_Q0"
MONETISABILITY_TIMEVALUE_AUTHORITY = "ADVISORY_ONLY"
MONETISABILITY_TIMEVALUE_ASSUMPTIONS = (
    "sigma=contract_iv held constant from selection; r=0; q=0; "
    "T=max(dte-hold_days,0)/365; European exercise; "
    "no dividend, no early exercise, no IV path"
)
HYDRATION_SCHEMA_VERSION = "selected-contract-hydration-v1"

_OCC_RE = re.compile(
    r"^(?:O:)?(?P<root>[A-Z0-9.]{1,12})(?P<expiry>\d{6})"
    r"(?P<side>[CP])(?P<strike>\d{8})$",
    re.IGNORECASE,
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.upper() in {"", "NAN", "NONE", "NULL", "N/A"} else text


def _number(value: Any) -> float | None:
    try:
        number = float(str(value).replace("$", "").replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalise_occ_symbol(value: Any) -> str:
    text = _text(value).upper().replace(" ", "")
    return text[2:] if text.startswith("O:") else text


def contract_symbols(value: Any) -> List[str]:
    """Return ordered OCC symbols from a single or composite value."""
    if isinstance(value, (list, tuple)):
        raw_values: Iterable[Any] = value
    else:
        text = _text(value)
        if not text:
            return []
        try:
            decoded = json.loads(text)
            raw_values = decoded if isinstance(decoded, list) else [text]
        except (TypeError, ValueError, json.JSONDecodeError):
            matches = re.findall(r"(?:O:)?[A-Z0-9.]{1,12}\d{6}[CP]\d{8}", text.upper())
            raw_values = matches or re.split(r"[/|,;]", text.split(":", 1)[-1])
    symbols: List[str] = []
    for raw in raw_values:
        symbol = normalise_occ_symbol(raw)
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols


def parse_occ_symbol(value: Any) -> Dict[str, Any]:
    symbol = normalise_occ_symbol(value)
    match = _OCC_RE.fullmatch(symbol)
    if not match:
        raise ValueError(f"invalid OCC symbol: {value!r}")
    expiry = datetime.strptime(match.group("expiry"), "%y%m%d").date()
    side = "CALL" if match.group("side").upper() == "C" else "PUT"
    return {
        "symbol": symbol,
        "root": match.group("root").upper(),
        "expiry": expiry.isoformat(),
        "side": side,
        "strike": int(match.group("strike")) / 1000.0,
    }


def canonical_structure(value: Any, symbols: List[str]) -> str:
    text = _text(value).upper().replace("-", "_").replace(" ", "_")
    if "BULL_CALL" in text and ("DEBIT" in text or "VERTICAL" in text):
        return "BULL_CALL_DEBIT"
    if "BEAR_PUT" in text and ("DEBIT" in text or "VERTICAL" in text):
        return "BEAR_PUT_DEBIT"
    if "DEBIT_SPREAD_CALL" in text:
        return "BULL_CALL_DEBIT"
    if "DEBIT_SPREAD_PUT" in text:
        return "BEAR_PUT_DEBIT"
    if "DEBIT_SPREAD" in text or "VERTICAL" in text:
        return "MULTI_LEG_DEBIT"
    if len(symbols) > 1:
        return "MULTI_LEG"
    if len(symbols) == 1:
        return "LONG_SINGLE"
    return text or "UNSPECIFIED"


def economics_evaluation_id(
    ticker: Any,
    direction: Any,
    structure: Any,
    symbols: List[str],
) -> str:
    if not symbols:
        return ""
    direction_text = _text(direction).upper()
    if "CALL" in direction_text:
        direction_text = "CALL"
    elif "PUT" in direction_text:
        direction_text = "PUT"
    payload = "|".join(
        [_text(ticker).upper(), direction_text, _text(structure).upper(), "/".join(symbols)]
    )
    return f"ECI1:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def parse_selected_structure(
    value: Any,
    *,
    direction: Any = "",
    instrument: Any = "",
) -> Dict[str, Any]:
    raw = _text(value)
    symbols = contract_symbols(raw)
    structure_hint = raw.split(":", 1)[0] if ":" in raw else instrument
    structure = canonical_structure(structure_hint, symbols)
    direction_text = _text(direction).upper()
    side = "CALL" if "CALL" in direction_text else "PUT" if "PUT" in direction_text else ""

    if not symbols:
        return {
            "status": "FAILED",
            "reason": "NO_SELECTED_CONTRACT",
            "structure": structure,
            "symbols": [],
        }
    try:
        metadata = [parse_occ_symbol(symbol) for symbol in symbols]
    except ValueError as exc:
        return {
            "status": "FAILED",
            "reason": "INVALID_OCC_SYMBOL",
            "detail": str(exc),
            "structure": structure,
            "symbols": symbols,
        }
    if side and any(item["side"] != side for item in metadata):
        return {
            "status": "FAILED",
            "reason": "SELECTED_LEG_DIRECTION_MISMATCH",
            "structure": structure,
            "symbols": symbols,
        }
    if len({item["expiry"] for item in metadata}) != 1:
        return {
            "status": "FAILED",
            "reason": "SELECTED_LEG_EXPIRY_MISMATCH",
            "structure": structure,
            "symbols": symbols,
        }
    wants_vertical = structure in {
        "BULL_CALL_DEBIT", "BEAR_PUT_DEBIT", "MULTI_LEG", "MULTI_LEG_DEBIT",
    }
    if wants_vertical and len(symbols) != 2:
        return {
            "status": "FAILED",
            "reason": "SELECTED_STRUCTURE_LEGS_MISSING",
            "structure": structure,
            "symbols": symbols,
        }
    if not wants_vertical and len(symbols) != 1:
        return {
            "status": "FAILED",
            "reason": "LONG_SINGLE_HAS_MULTIPLE_LEGS",
            "structure": structure,
            "symbols": symbols,
        }
    if len(symbols) == 2:
        if side == "CALL":
            structure = "BULL_CALL_DEBIT"
            metadata.sort(key=lambda item: item["strike"])
        elif side == "PUT":
            structure = "BEAR_PUT_DEBIT"
            metadata.sort(key=lambda item: item["strike"], reverse=True)
        else:
            return {
                "status": "FAILED",
                "reason": "VERTICAL_DIRECTION_UNRESOLVED",
                "structure": structure,
                "symbols": symbols,
            }
        symbols = [item["symbol"] for item in metadata]
    return {
        "status": "COMPLETE",
        "reason": "",
        "structure": structure,
        "symbols": symbols,
        "metadata": metadata,
    }


def _quote_record(symbol: str, live: Mapping[str, Any], fetched_at_utc: str) -> Dict[str, Any]:
    meta = parse_occ_symbol(symbol)
    bid = _number(live.get("live_contract_bid"))
    ask = _number(live.get("live_contract_ask"))
    mid = _number(live.get("live_contract_mid"))
    if mid is None and bid is not None and ask is not None:
        mid = (bid + ask) / 2.0
    if bid is None or ask is None or mid is None or bid < 0 or ask <= 0 or bid > ask or mid <= 0:
        raise ValueError(f"invalid two-sided quote for {symbol}: bid={bid}, ask={ask}, mid={mid}")
    quote_time = _text(live.get("live_options_fetched_at")) or fetched_at_utc
    dte = (date.fromisoformat(meta["expiry"]) - date.fromisoformat(quote_time[:10])).days
    bid_size = _number(live.get("live_contract_bid_size"))
    ask_size = _number(live.get("live_contract_ask_size"))
    size_quality = (
        "OBSERVED" if bid_size is not None and ask_size is not None
        else "PARTIAL" if bid_size is not None or ask_size is not None
        else "MISSING"
    )
    return {
        **meta,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "bid_size": bid_size,
        "ask_size": ask_size,
        "bid_size_quality": _text(live.get("contract_bid_size_quality")),
        "ask_size_quality": _text(live.get("contract_ask_size_quality")),
        "contract_size_quality": size_quality,
        "quote_quality": _text(live.get("contract_quote_quality")),
        "spread_fraction_mid": quote_spread_fraction(bid, ask),
        "iv": _number(live.get("live_contract_iv")),
        "delta": _number(live.get("live_contract_delta")),
        "gamma": _number(live.get("live_contract_gamma")),
        "theta": _number(live.get("live_contract_theta")),
        "vega": _number(live.get("live_contract_vega")),
        "oi": _number(live.get("live_contract_oi")),
        "volume": _number(live.get("live_contract_volume")),
        "contract_multiplier": _number(live.get("live_contract_multiplier")) or 100.0,
        "quote_timestamp_utc": quote_time,
        "provider_updated": live.get("live_contract_provider_updated", ""),
        "source": _text(live.get("live_options_source")),
        "dte": dte,
    }


def _snapshot_id(structure: str, legs: List[Mapping[str, Any]]) -> str:
    fields = [structure]
    for leg in legs:
        fields.extend(
            str(leg.get(name, ""))
            for name in ("symbol", "quote_timestamp_utc", "bid", "ask", "mid", "source")
        )
    return f"QUOTE1:{hashlib.sha256('|'.join(fields).encode('utf-8')).hexdigest()[:24]}"


def hydrate_selected_structure(
    selected: Any,
    fetch_contract: Callable[[str], Mapping[str, Any]],
    *,
    ticker: Any,
    direction: Any,
    instrument: Any = "",
    fetched_at_utc: str | None = None,
) -> Dict[str, Any]:
    """Hydrate every leg and return one canonical aggregate quote."""
    parsed = parse_selected_structure(selected, direction=direction, instrument=instrument)
    if parsed["status"] != "COMPLETE":
        return {
            "selected_structure_hydration_status": "FAILED",
            "selected_structure_hydration_reason": parsed["reason"],
            "selected_structure": parsed.get("structure", ""),
            "selected_contract_symbols": json.dumps(parsed.get("symbols", [])),
        }
    fetched_at = fetched_at_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    legs: List[Dict[str, Any]] = []
    for symbol in parsed["symbols"]:
        live = dict(fetch_contract(symbol) or {})
        source = _text(live.get("live_options_source"))
        if source in {"", "MARKETDATA_NO_QUOTE", "MARKETDATA_FAILED"}:
            return {
                "selected_structure_hydration_status": "FAILED",
                "selected_structure_hydration_reason": f"SELECTED_LEG_QUOTE_UNAVAILABLE:{symbol}:{source or 'UNKNOWN'}",
                "selected_structure": parsed["structure"],
                "selected_contract_symbols": json.dumps(parsed["symbols"]),
                "live_options_source": source or "UNKNOWN",
                "live_options_error": live.get("live_options_error", ""),
            }
        try:
            legs.append(_quote_record(symbol, live, fetched_at))
        except ValueError as exc:
            return {
                "selected_structure_hydration_status": "FAILED",
                "selected_structure_hydration_reason": f"SELECTED_LEG_QUOTE_INVALID:{exc}",
                "selected_structure": parsed["structure"],
                "selected_contract_symbols": json.dumps(parsed["symbols"]),
                "live_options_source": source or "UNKNOWN",
                "live_options_error": live.get("live_options_error", ""),
            }

    structure = parsed["structure"]
    selected_symbol = (
        legs[0]["symbol"]
        if structure == "LONG_SINGLE"
        else f"{structure}:{legs[0]['symbol']}/{legs[1]['symbol']}"
    )
    if structure == "LONG_SINGLE":
        aggregate = dict(legs[0])
        long_leg = dict(legs[0])
        short_leg: Dict[str, Any] | None = None
    else:
        long_leg, short_leg = legs
        if long_leg["contract_multiplier"] != short_leg["contract_multiplier"]:
            return {
                "selected_structure_hydration_status": "FAILED",
                "selected_structure_hydration_reason": "SELECTED_LEG_MULTIPLIER_MISMATCH",
                "selected_structure": structure,
                "selected_contract_symbols": json.dumps(parsed["symbols"]),
            }
        entry_debit = long_leg["ask"] - short_leg["bid"]
        exit_credit = max(long_leg["bid"] - short_leg["ask"], 0.0)
        mid = long_leg["mid"] - short_leg["mid"]
        if entry_debit <= 0 or mid <= 0:
            return {
                "selected_structure_hydration_status": "FAILED",
                "selected_structure_hydration_reason": "SELECTED_VERTICAL_DEBIT_INVALID",
                "selected_structure": structure,
                "selected_contract_symbols": json.dumps(parsed["symbols"]),
            }
        aggregate = {
            "bid": exit_credit,
            "ask": entry_debit,
            "mid": mid,
            # For a debit-spread entry the displayed capacity is constrained by
            # the long-leg ask and short-leg bid.  Exit capacity is the inverse.
            "ask_size": min(
                value for value in (long_leg["ask_size"], short_leg["bid_size"])
                if value is not None
            ) if any(value is not None for value in (long_leg["ask_size"], short_leg["bid_size"])) else None,
            "bid_size": min(
                value for value in (long_leg["bid_size"], short_leg["ask_size"])
                if value is not None
            ) if any(value is not None for value in (long_leg["bid_size"], short_leg["ask_size"])) else None,
            "contract_size_quality": (
                "OBSERVED" if all(
                    value is not None for value in (
                        long_leg["ask_size"], short_leg["bid_size"],
                        long_leg["bid_size"], short_leg["ask_size"],
                    )
                ) else "PARTIAL" if any(
                    value is not None for value in (
                        long_leg["ask_size"], short_leg["bid_size"],
                        long_leg["bid_size"], short_leg["ask_size"],
                    )
                ) else "MISSING"
            ),
            "quote_quality": "COMPOSITE_VERTICAL",
            "spread_fraction_mid": (entry_debit - exit_credit) / mid,
            "max_leg_spread_fraction_mid": max(
                long_leg["spread_fraction_mid"], short_leg["spread_fraction_mid"]
            ),
            "iv": long_leg["iv"],
            "delta": None if long_leg["delta"] is None or short_leg["delta"] is None else long_leg["delta"] - short_leg["delta"],
            "gamma": None if long_leg["gamma"] is None or short_leg["gamma"] is None else long_leg["gamma"] - short_leg["gamma"],
            "theta": None if long_leg["theta"] is None or short_leg["theta"] is None else long_leg["theta"] - short_leg["theta"],
            "vega": None if long_leg["vega"] is None or short_leg["vega"] is None else long_leg["vega"] - short_leg["vega"],
            "oi": min(x for x in (long_leg["oi"], short_leg["oi"]) if x is not None) if any(x is not None for x in (long_leg["oi"], short_leg["oi"])) else None,
            "volume": min(x for x in (long_leg["volume"], short_leg["volume"]) if x is not None) if any(x is not None for x in (long_leg["volume"], short_leg["volume"])) else None,
            "contract_multiplier": long_leg["contract_multiplier"],
            "quote_timestamp_utc": max(long_leg["quote_timestamp_utc"], short_leg["quote_timestamp_utc"]),
            "source": long_leg["source"],
            "dte": long_leg["dte"],
            "strike": long_leg["strike"],
            "expiry": long_leg["expiry"],
        }
    evaluation_id = economics_evaluation_id(
        ticker, direction, structure, [leg["symbol"] for leg in legs]
    )
    return {
        "selected_structure_hydration_status": "COMPLETE",
        "selected_structure_hydration_reason": "",
        "selected_structure_hydration_schema_version": HYDRATION_SCHEMA_VERSION,
        "selected_structure": structure,
        "selected_structure_id": evaluation_id,
        "selected_contract_symbol": selected_symbol,
        "selected_contract_symbols": json.dumps([leg["symbol"] for leg in legs]),
        "selected_quote_snapshot_id": _snapshot_id(structure, legs),
        "selected_quote_timestamp_utc": aggregate["quote_timestamp_utc"],
        "selected_legs_json": json.dumps(legs, sort_keys=True, separators=(",", ":")),
        "selected_long_leg": long_leg,
        "selected_short_leg": short_leg,
        "live_contract_symbol": selected_symbol,
        "live_contract_bid": aggregate["bid"],
        "live_contract_ask": aggregate["ask"],
        "live_contract_mid": aggregate["mid"],
        "live_contract_bid_size": aggregate.get("bid_size"),
        "live_contract_ask_size": aggregate.get("ask_size"),
        "contract_size_quality": aggregate.get("contract_size_quality", "MISSING"),
        "contract_quote_quality": aggregate.get("quote_quality", ""),
        "live_contract_spread_pct": aggregate["spread_fraction_mid"] * 100.0,
        "selected_max_leg_spread_pct": (
            aggregate.get("max_leg_spread_fraction_mid", aggregate["spread_fraction_mid"])
            * 100.0
        ),
        "live_contract_iv": aggregate["iv"],
        "live_contract_delta": aggregate["delta"],
        "live_contract_gamma": aggregate["gamma"],
        "live_contract_theta": aggregate["theta"],
        "live_contract_vega": aggregate["vega"],
        "live_contract_oi": aggregate["oi"],
        "live_contract_volume": aggregate["volume"],
        "live_contract_multiplier": aggregate["contract_multiplier"],
        "live_contract_quote_timestamp": aggregate["quote_timestamp_utc"],
        "live_options_source": aggregate["source"],
        "selected_quote_source": aggregate["source"],
        "live_options_fetched_at": fetched_at,
    }


def recompute_premium_rr(
    row: Mapping[str, Any],
    hydrated: Mapping[str, Any],
) -> Dict[str, Any]:
    """Calculate premium return-to-risk for the exact hydrated structure."""
    if hydrated.get("selected_structure_hydration_status") != "COMPLETE":
        return {
            "rr_recompute_status": "FAILED",
            "rr_recompute_reason": "SELECTED_STRUCTURE_NOT_HYDRATED",
        }
    direction_text = _text(
        row.get("canonical_direction") or row.get("resolved_direction") or row.get("direction")
    ).upper()
    direction = "CALL" if "CALL" in direction_text else "PUT" if "PUT" in direction_text else ""
    entry_spot = _number(
        row.get("live_price") or row.get("entry_spot") or row.get("signal_price") or row.get("underlying_price")
    )
    target_spot = _number(
        row.get("target_spot") or row.get("target_price") or row.get("structural_target")
    )
    if direction not in {"CALL", "PUT"} or entry_spot is None or target_spot is None:
        return {
            "rr_recompute_status": "FAILED",
            "rr_recompute_reason": "SELECTED_RR_THESIS_INPUT_MISSING",
        }
    if (direction == "CALL" and target_spot <= entry_spot) or (
        direction == "PUT" and target_spot >= entry_spot
    ):
        return {
            "rr_recompute_status": "FAILED",
            "rr_recompute_reason": "SELECTED_RR_TARGET_TOPOLOGY_INVALID",
        }
    long_leg = hydrated.get("selected_long_leg")
    short_leg = hydrated.get("selected_short_leg")
    if not isinstance(long_leg, Mapping):
        return {"rr_recompute_status": "FAILED", "rr_recompute_reason": "SELECTED_LONG_LEG_MISSING"}
    structure = _text(hydrated.get("selected_structure")).upper()
    if structure == "LONG_SINGLE":
        entry_debit = _number(long_leg.get("ask"))
        strike = _number(long_leg.get("strike"))
        if entry_debit is None or strike is None or entry_debit <= 0:
            return {"rr_recompute_status": "FAILED", "rr_recompute_reason": "SELECTED_ENTRY_DEBIT_INVALID"}
        target_value = max(target_spot - strike, 0.0) if direction == "CALL" else max(strike - target_spot, 0.0)
    else:
        if not isinstance(short_leg, Mapping):
            return {"rr_recompute_status": "FAILED", "rr_recompute_reason": "SELECTED_SHORT_LEG_MISSING"}
        long_ask = _number(long_leg.get("ask"))
        short_bid = _number(short_leg.get("bid"))
        long_strike = _number(long_leg.get("strike"))
        short_strike = _number(short_leg.get("strike"))
        if None in {long_ask, short_bid, long_strike, short_strike}:
            return {"rr_recompute_status": "FAILED", "rr_recompute_reason": "SELECTED_VERTICAL_INPUT_MISSING"}
        entry_debit = float(long_ask) - float(short_bid)
        if entry_debit <= 0:
            return {"rr_recompute_status": "FAILED", "rr_recompute_reason": "SELECTED_ENTRY_DEBIT_INVALID"}
        if direction == "CALL":
            target_value = max(target_spot - float(long_strike), 0.0) - max(target_spot - float(short_strike), 0.0)
        else:
            target_value = max(float(long_strike) - target_spot, 0.0) - max(float(short_strike) - target_spot, 0.0)
    option_gain = target_value - entry_debit
    rr = option_gain / entry_debit
    evaluation_id = _text(hydrated.get("selected_structure_id"))
    return {
        "rr_recompute_status": "COMPLETE",
        "rr_recompute_reason": "",
        "rr_calculation_version": RR_CALCULATION_VERSION,
        "rr_contract_symbol": hydrated.get("selected_contract_symbol", ""),
        "rr_evaluation_id": evaluation_id,
        "rr_entry_debit_per_share": round(entry_debit, 6),
        "rr_target_value_per_share": round(target_value, 6),
        "rr_premium_expected": round(rr, 6),
        "rr_options": round(rr, 6),
        "rr_predicted": round(rr, 6),
        "option_gain_at_target": round(option_gain, 6),
    }


def _black_scholes_value(
    side: str, spot: float, strike: float, years: float, vol: float
) -> float | None:
    """BS value with r = q = 0, degrading to intrinsic at the boundaries.

    At T = 0 or sigma = 0 the formula is undefined and the answer is intrinsic
    value, which is also the correct lower bound. Reuses the repository's own
    pricer (scripts/compute_greeks_bs.py) so there is one implementation.
    """

    intrinsic = max(spot - strike, 0.0) if side == "CALL" else max(strike - spot, 0.0)
    if years <= 0 or vol <= 0 or spot <= 0 or strike <= 0:
        return intrinsic
    try:
        from scripts.compute_greeks_bs import black_scholes_price
    except ImportError:                                   # pragma: no cover
        try:
            from compute_greeks_bs import black_scholes_price
        except ImportError:
            return None
    try:
        value = black_scholes_price(
            side.lower(), spot, strike, years, 0.0, vol
        )
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    if value is None or value != value:
        return None
    # A European option with r = q = 0 is never worth less than intrinsic.
    # Enforced rather than assumed, so a pricer edge case cannot produce a
    # time-value record weaker than the floor it is meant to sit above.
    return max(float(value), intrinsic)


def evaluate_timevalue_monetisability(
    row: Mapping[str, Any],
    hydrated: Mapping[str, Any],
    intrinsic: Mapping[str, Any],
    *,
    minimum_profit_pct: float = MONETISABILITY_MIN_PROFIT_PCT,
) -> Dict[str, Any]:
    """The advisory time-value companion to `evaluate_long_option_monetisability`.

    AVS-FIX-001 W3.4 (RCA3-D05, DEC-1). Returns only `*_timevalue*` fields, so
    it can never overwrite the intrinsic record it is handed. If anything
    needed is missing the state is NOT_EVALUATED with a named reason -- never a
    guess, and never a fallback to the intrinsic answer, which would make the
    second column silently duplicate the first.
    """

    base = {
        "monetisability_state_timevalue": "NOT_EVALUATED",
        "monetisability_timevalue_profit_pct": None,
        "monetisability_timevalue_value_per_share": None,
        "monetisability_timevalue_model": MONETISABILITY_TIMEVALUE_MODEL,
        "monetisability_timevalue_authority": MONETISABILITY_TIMEVALUE_AUTHORITY,
        "monetisability_timevalue_assumptions": MONETISABILITY_TIMEVALUE_ASSUMPTIONS,
        "monetisability_timevalue_reason": "",
    }

    if str(intrinsic.get("monetisability_status") or "").upper() != "COMPLETE":
        return {**base, "monetisability_timevalue_reason": "INTRINSIC_RECORD_INCOMPLETE"}

    direction = _text(intrinsic.get("monetisability_direction")).upper()
    if direction not in {"CALL", "PUT"}:
        return {**base, "monetisability_timevalue_reason": "NON_DIRECTIONAL"}

    entry_ask = _number(intrinsic.get("monetisability_entry_ask"))
    strike = _number(intrinsic.get("monetisability_strike"))
    target_spot = _number(intrinsic.get("monetisability_structural_target_spot"))
    if not entry_ask or entry_ask <= 0 or not strike or not target_spot:
        return {**base, "monetisability_timevalue_reason": "ENTRY_STRIKE_OR_TARGET_MISSING"}

    def _first_present(*sources_and_keys):
        """First key that is present and numeric.

        An `or` chain cannot be used here: a legitimate hold of 0 sessions and
        a legitimate DTE of 0 are both falsy, and would fall through to the
        next candidate or to None.
        """
        for source, key in sources_and_keys:
            value = _number(source.get(key))
            if value is not None:
                return value
        return None

    vol = _first_present(
        (row, "contract_iv"), (row, "implied_vol"), (hydrated, "contract_iv")
    )
    if vol is None or vol <= 0:
        return {**base, "monetisability_timevalue_reason": "CONTRACT_IV_UNAVAILABLE"}
    # A percentage-form IV (18.7) is normalised to a decimal (0.187). A real
    # volatility above 5.0 is not plausible for a listed single name.
    if vol > 5.0:
        vol = vol / 100.0

    dte = _first_present((row, "contract_dte"), (row, "dte"), (hydrated, "dte"))
    if dte is None or dte < 0:
        return {**base, "monetisability_timevalue_reason": "CONTRACT_DTE_UNAVAILABLE"}
    hold_days = _first_present(
        (row, "planned_hold_sessions"), (row, "hold_days"), (row, "hold_sessions")
    )
    if hold_days is None or hold_days < 0:
        return {**base, "monetisability_timevalue_reason": "PLANNED_HOLD_UNAVAILABLE"}

    years = max(dte - hold_days, 0.0) / 365.0
    value = _black_scholes_value(direction, target_spot, strike, years, vol)
    if value is None:
        return {**base, "monetisability_timevalue_reason": "PRICER_UNAVAILABLE"}

    profit = value - entry_ask
    profit_pct = (profit / entry_ask) * 100.0
    if profit <= 0:
        state = "NOT_MONETISABLE"
        reason = "TIMEVALUE_AT_TARGET_BELOW_ENTRY_COST"
    elif profit_pct < float(minimum_profit_pct):
        state = "LIMITED"
        reason = "POSITIVE_TIMEVALUE_PROFIT_BELOW_MINIMUM"
    else:
        state = "MONETISABLE"
        reason = "TIMEVALUE_AT_TARGET_CLEARS_PROFIT_FLOOR"

    return {
        **base,
        "monetisability_state_timevalue": state,
        "monetisability_timevalue_profit_pct": round(profit_pct, 4),
        "monetisability_timevalue_value_per_share": round(float(value), 6),
        "monetisability_timevalue_years_to_expiry": round(years, 8),
        "monetisability_timevalue_iv_used": round(vol, 6),
        "monetisability_timevalue_reason": reason,
    }


def evaluate_long_option_monetisability(
    row: Mapping[str, Any],
    hydrated: Mapping[str, Any],
    *,
    minimum_profit_pct: float = MONETISABILITY_MIN_PROFIT_PCT,
) -> Dict[str, Any]:
    """Classify whether one exact long call/put can monetise its thesis target.

    This deliberately avoids a future option-pricing model.  The entry uses the
    current ask and the target value uses expiry intrinsic value, producing a
    conservative, deterministic answer that is recomputed whenever hydration
    selects a different OCC contract.
    """
    base = {
        "monetisability_calculation_version": MONETISABILITY_CALCULATION_VERSION,
        "monetisability_minimum_profit_pct": float(minimum_profit_pct),
        "monetisability_contract_symbol": hydrated.get("selected_contract_symbol", ""),
        "monetisability_evaluation_id": hydrated.get("selected_structure_id", ""),
        "monetisability_eligible": False,
        "monetisability_authority": MONETISABILITY_AUTHORITY,
        "monetisability_valuation_basis": "EXPIRY_INTRINSIC_FLOOR",
        "monetisability_hard_execution_authority": False,
    }
    if hydrated.get("selected_structure_hydration_status") != "COMPLETE":
        return {
            **base,
            "monetisability_status": "FAILED",
            "monetisability_state": "DATA_MISSING",
            "monetisability_reason": "SELECTED_STRUCTURE_NOT_HYDRATED",
        }
    if _text(hydrated.get("selected_structure")).upper() != "LONG_SINGLE":
        return {
            **base,
            "monetisability_status": "FAILED",
            "monetisability_state": "CONTRACT_REPAIR",
            "monetisability_reason": "PRODUCTION_REQUIRES_LONG_SINGLE",
        }

    direction_text = _text(
        row.get("canonical_direction") or row.get("resolved_direction") or row.get("direction")
    ).upper()
    direction = "CALL" if "CALL" in direction_text else "PUT" if "PUT" in direction_text else ""
    target_spot = _number(
        row.get("target_spot") or row.get("target_price") or row.get("structural_target")
    )
    long_leg = hydrated.get("selected_long_leg")
    if direction not in {"CALL", "PUT"} or target_spot is None or not isinstance(long_leg, Mapping):
        return {
            **base,
            "monetisability_status": "FAILED",
            "monetisability_state": "DATA_MISSING",
            "monetisability_reason": "DIRECTION_TARGET_OR_LONG_LEG_MISSING",
        }

    entry_ask = _number(long_leg.get("ask"))
    strike = _number(long_leg.get("strike"))
    if entry_ask is None or entry_ask <= 0 or strike is None or strike <= 0:
        return {
            **base,
            "monetisability_status": "FAILED",
            "monetisability_state": "DATA_MISSING",
            "monetisability_reason": "ENTRY_ASK_OR_STRIKE_INVALID",
        }

    if direction == "CALL":
        breakeven = strike + entry_ask
        target_intrinsic = max(target_spot - strike, 0.0)
        target_clears_breakeven = target_spot > breakeven
    else:
        breakeven = strike - entry_ask
        target_intrinsic = max(strike - target_spot, 0.0)
        target_clears_breakeven = target_spot < breakeven

    target_profit = target_intrinsic - entry_ask
    target_profit_pct = (target_profit / entry_ask) * 100.0
    if not target_clears_breakeven or target_profit <= 0:
        state = "NOT_MONETISABLE"
        reason = "STRUCTURAL_TARGET_DOES_NOT_CLEAR_BREAKEVEN"
        eligible = False
    elif target_profit_pct < float(minimum_profit_pct):
        state = "LIMITED"
        reason = "POSITIVE_TARGET_PROFIT_BELOW_MINIMUM"
        eligible = True
    else:
        state = "MONETISABLE"
        reason = "TARGET_CLEARS_BREAKEVEN_AND_PROFIT_FLOOR"
        eligible = True

    return {
        **base,
        "monetisability_status": "COMPLETE",
        "monetisability_state": state,
        "monetisability_reason": reason,
        "monetisability_eligible": eligible,
        "monetisability_direction": direction,
        "monetisability_entry_ask": round(entry_ask, 6),
        "monetisability_strike": round(strike, 6),
        "monetisability_breakeven_spot": round(breakeven, 6),
        "monetisability_structural_target_spot": round(target_spot, 6),
        "monetisability_target_intrinsic_per_share": round(target_intrinsic, 6),
        "monetisability_target_profit_per_share": round(target_profit, 6),
        "monetisability_target_profit_pct": round(target_profit_pct, 4),
    }
