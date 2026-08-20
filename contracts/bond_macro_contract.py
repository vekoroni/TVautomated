"""Forward-compatible adapter for ``bond_macro_state.json`` sidecars."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


def _section(state: Mapping[str, Any], current: str, legacy: str = "") -> dict[str, Any]:
    value = state.get(current)
    if not isinstance(value, Mapping) and legacy:
        value = state.get(legacy)
    return dict(value) if isinstance(value, Mapping) else {}


def _first(mapping: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return default


def normalise_bond_macro_sidecar(state: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve the full sidecar and add stable pipeline-facing aliases."""
    if not isinstance(state, Mapping):
        raise TypeError("bond macro sidecar must be a JSON object")

    auction = _section(state, "auction", "auction_calendar")
    yield_curve = _section(state, "yield_curve")
    zn = _section(state, "zn_futures", "zn_direction")
    credit = _section(state, "credit_stress")
    composite = _section(state, "composite")

    # Preserve every source field/section so future additive schema changes
    # flow through without another hand-maintained orchestrator mapping.
    result = deepcopy(dict(state))
    result.update({
        "source_schema_version": state.get("schema_version", "UNKNOWN"),
        "curve_state": yield_curve.get("curve_state", "UNKNOWN"),
        "yield_2y": yield_curve.get("yield_2y"),
        "yield_10y": yield_curve.get("yield_10y"),
        "yield_30y": yield_curve.get("yield_30y"),
        "spread_bps": yield_curve.get("spread_bps"),
        "spread_10s30s_bps": yield_curve.get("spread_10s30s_bps"),
        "curve_move_1d": yield_curve.get("curve_move_1d", "UNKNOWN"),
        "curve_move_5d": yield_curve.get("curve_move_5d", "UNKNOWN"),
        "russell_tailwind": bool(yield_curve.get("russell_tailwind", False)),
        "yield_data_quality": yield_curve.get("data_quality", "UNKNOWN"),
        "yield_stale_flag": bool(yield_curve.get("stale_flag", False)),
        "yield_staleness_sessions": yield_curve.get("staleness_sessions"),
        "zn_ticker": _first(zn, "ticker_used", "ticker", default="UNKNOWN"),
        "zn_direction": _first(zn, "zn_direction", "direction", default="UNKNOWN"),
        "zn_5d_trend": zn.get("zn_5d_trend", "UNKNOWN"),
        "rate_regime_signal": zn.get("rate_regime_signal", "UNKNOWN"),
        "credit_stress_level": _first(credit, "stress_level", "stress_flag", default="UNKNOWN"),
        "credit_stress_flag": _first(credit, "stress_flag", "stress_level", default="UNKNOWN"),
        "credit_z_score": _first(credit, "ratio_zscore_20d", "z_score"),
        "credit_warning": bool(credit.get("credit_warning", False)),
        "credit_alert": bool(credit.get("credit_alert", False)),
        "auction_today": bool(auction.get("auction_today", False)),
        "auction_window": bool(auction.get("auction_window", False)),
        "auction_spread_risk": bool(_first(auction, "spread_risk_flag", "auction_today", default=False)),
        "long_end_in_window": bool(auction.get("long_end_in_window", False)),
        "days_to_next_long_end": auction.get("days_to_next_long_end"),
        "bond_macro_flag": _first(composite, "morning_manifest_flag", "flag", default="UNKNOWN"),
        "bond_macro_score": _first(composite, "macro_bond_score", "score"),
        "breakeven_adjustment_pct": composite.get("breakeven_adjustment_pct", 0),
        "trade_go": bool(composite.get("trade_go", True)),
        "primary_warning": composite.get("primary_warning", ""),
        "all_warnings": deepcopy(composite.get("all_warnings", [])),
        "summary": composite.get("summary", ""),
        "as_of_date": state.get("as_of_date", ""),
        "generated_at": state.get("generated_at", ""),
        "data_source": yield_curve.get("data_source", "UNKNOWN"),
    })
    return result
