#!/usr/bin/env python3
"""
AVSHUNTER Phase 5 - Market Physics State Engine.

This module enriches existing Vanguard / actuarial rows with deterministic
physics-derived state transition fields. It does not create signals, verdicts,
or execution permission.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Iterable, Mapping, Optional

import pandas as pd

log = logging.getLogger("market_physics")

PHYSICS_FIELDS = [
    "physics_state_id",
    "market_energy_score",
    "compression_energy",
    "directional_force",
    "force_alignment_score",
    "trend_inertia",
    "volatility_pressure",
    "entropy_score",
    "regime_instability_score",
    "phase_transition_probability",
    "shock_sensitivity",
    "liquidity_friction_score",
    "hidden_state_label",
    "state_transition_label",
    "future_state_5d",
    "future_state_10d",
    "future_state_20d",
    "transition_success_5d",
    "transition_success_10d",
    "transition_success_20d",
]

PHYSICS_NUMERIC_FIELDS = [
    "market_energy_score",
    "compression_energy",
    "directional_force",
    "force_alignment_score",
    "trend_inertia",
    "volatility_pressure",
    "entropy_score",
    "regime_instability_score",
    "phase_transition_probability",
    "shock_sensitivity",
    "liquidity_friction_score",
    "transition_success_5d",
    "transition_success_10d",
    "transition_success_20d",
]

PHYSICS_AUDIT_FIELDS = [
    "physics_data_quality",
    "physics_defaulted_fields",
    "physics_degraded_reason",
]

ALL_PHYSICS_FIELDS = PHYSICS_FIELDS + PHYSICS_AUDIT_FIELDS

MISSING_TOKENS = {"", "NONE", "UNKNOWN", "MISSING", "N/A", "NAN", "NULL"}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:
        pass
    if isinstance(value, str):
        return value.strip().upper() in MISSING_TOKENS
    return False


def _first(row: Mapping[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        if key in row and not _is_missing(row.get(key)):
            return row.get(key)
    return default


def _num(row: Mapping[str, Any], keys: Iterable[str], default: float = 50.0) -> tuple[float, bool]:
    value = _first(row, keys, None)
    if _is_missing(value):
        return float(default), True
    try:
        return float(value), False
    except Exception:
        return float(default), True


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(max(lo, min(hi, float(value))), 4)


def _as_0_100(value: float) -> float:
    if -1.0 <= value <= 1.0:
        return _clamp(value * 100.0)
    return _clamp(value)


def _signed_return(value: float) -> float:
    if -1.0 <= value <= 1.0:
        value *= 100.0
    return _clamp(value * 4.0, -100.0, 100.0)


def _word(row: Mapping[str, Any], keys: Iterable[str], default: str = "") -> str:
    value = _first(row, keys, default)
    return str(value or "").strip().upper()


def _contains(value: str, needles: Iterable[str]) -> bool:
    return any(n in value for n in needles)


def _bucket(value: float, name: str, signed: bool = False) -> str:
    if signed:
        if value >= 35:
            return f"{name}_BULL"
        if value <= -35:
            return f"{name}_BEAR"
        return f"{name}_BALANCED"
    if value >= 70:
        return f"{name}_HIGH"
    if value >= 40:
        return f"{name}_MED"
    return f"{name}_LOW"


def _future_state_from_label(label: str, horizon: str) -> str:
    mapping = {
        "BALANCE_TO_UPSIDE_EXPANSION": "INFERRED_UPSIDE_EXPANSION",
        "BALANCE_TO_DOWNSIDE_EXPANSION": "INFERRED_DOWNSIDE_EXPANSION",
        "CONTINUATION_UP": "INFERRED_UP_CONTINUATION",
        "CONTINUATION_DOWN": "INFERRED_DOWN_CONTINUATION",
        "REVERSAL_UP": "INFERRED_REVERSAL_UP",
        "REVERSAL_DOWN": "INFERRED_REVERSAL_DOWN",
        "FAILED_BREAKOUT_RISK": "INFERRED_FAILED_EXPANSION_RISK",
        "CHOP_CONTINUATION": "INFERRED_CHOP_CONTINUATION",
        "NO_TRANSITION_EDGE": "INFERRED_NO_EDGE",
    }
    return f"{mapping.get(label, 'INFERRED_UNKNOWN')}__{horizon}"


def _success_probability(base: float, horizon: str) -> float:
    multiplier = {"5d": 0.92, "10d": 1.0, "20d": 0.88}.get(horizon, 1.0)
    return _clamp(base * multiplier)


def calculate_market_physics(
    row: Mapping[str, Any],
    macro_context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Calculate deterministic physics fields for one Vanguard/candidate row."""
    macro_context = macro_context or {}
    defaulted: list[str] = []

    def n(keys: Iterable[str], default: float = 50.0) -> float:
        value, used_default = _num(row, keys, default)
        if used_default:
            first_key = next(iter(keys), "unknown")
            defaulted.append(str(first_key))
        return value

    atr_pct = _as_0_100(n(["atr_percentile", "atr_percentile_rank", "ATR_percentile", "layer2__atr_percentile"], 50.0))
    adx = _as_0_100(n(["adx_14", "ADX_14", "adx", "trend_strength"], 25.0))
    volume_ratio = _as_0_100(n(["volume_ratio", "rvol", "scanner_rvol", "relative_volume"], 1.0))
    if volume_ratio <= 5.0:
        volume_ratio = _clamp(volume_ratio * 50.0)
    iv_rank = _as_0_100(n(["iv_rank", "iv_percentile", "ivp", "ivp_252d", "contract_iv_percentile"], 50.0))
    spread_pct = n(["spread_pct_mid", "contract_spread_pct", "spread_pct", "eil_spread_pct_live"], 0.08)
    if spread_pct <= 1.0:
        spread_pct *= 100.0
    avg_volume = n(["avg_volume", "average_volume", "volume", "scanner_volume"], 1_000_000.0)
    beta = n(["beta", "market_beta"], 1.0)
    return_5d = _signed_return(n(["return_5d", "ret_5d", "sector_5d_return"], 0.0))
    return_10d = _signed_return(n(["return_10d", "ret_10d"], 0.0))

    trend_text = _word(row, ["trend_direction", "layer2__trend_direction", "dominant_trend", "trend"])
    vwap_text = _word(row, ["vwap_bias", "vwap_bias_eod"])
    structure_text = _word(row, ["structure_quality", "layer2__structure_quality", "crabel_state"])
    phase_text = _word(row, ["phase_v2", "layer2__phase_v2", "wyckoff_phase_bucket", "phase"])
    macro_label = str(
        macro_context.get("macro_regime_label")
        or row.get("macro_regime_label")
        or row.get("macro_regime")
        or ""
    ).upper()
    sector_alignment = _word(row, ["ticker_sector_alignment", "sector_alignment"])
    edge_direction = _word(row, ["edge_direction", "vanguard_edge_direction", "layer2__edge_direction"])

    squeeze_flag = 0.0
    crabel_text = _word(row, ["crabel_pattern", "crabel_state"])
    if _contains(crabel_text, ["SQUEEZE", "COMPRESSION", "INSIDE", "NR7"]):
        squeeze_flag = 25.0
    compression_energy = _clamp((100.0 - atr_pct) * 0.70 + squeeze_flag + (100.0 - min(iv_rank, 100.0)) * 0.10)

    force = (return_5d * 0.35) + (return_10d * 0.20)
    if _contains(trend_text, ["UP", "BULL", "RISING", "MARKUP"]):
        force += 30.0
    elif _contains(trend_text, ["DOWN", "BEAR", "FALLING", "MARKDOWN"]):
        force -= 30.0
    if _contains(vwap_text, ["ABOVE", "BULL", "POSITIVE"]):
        force += 15.0
    elif _contains(vwap_text, ["BELOW", "BEAR", "NEGATIVE"]):
        force -= 15.0
    if volume_ratio >= 130:
        force += 10.0 if force >= 0 else -10.0
    directional_force = _clamp(force, -100.0, 100.0)

    signs: list[int] = []
    if abs(directional_force) >= 10:
        signs.append(1 if directional_force > 0 else -1)
    if _contains(trend_text, ["UP", "BULL", "RISING", "MARKUP"]):
        signs.append(1)
    elif _contains(trend_text, ["DOWN", "BEAR", "FALLING", "MARKDOWN"]):
        signs.append(-1)
    if _contains(macro_label, ["RISK_ON", "BULL"]):
        signs.append(1)
    elif _contains(macro_label, ["RISK_OFF", "BEAR"]):
        signs.append(-1)
    if sector_alignment == "ALIGNED":
        signs.append(1 if directional_force >= 0 else -1)
    elif sector_alignment == "CONFLICTED":
        signs.append(-1 if directional_force >= 0 else 1)
    if _contains(edge_direction, ["UP", "CALL", "BULL", "LONG"]):
        signs.append(1)
    elif _contains(edge_direction, ["DOWN", "PUT", "BEAR", "SHORT"]):
        signs.append(-1)
    if signs:
        majority = 1 if sum(signs) >= 0 else -1
        agreement = sum(1 for s in signs if s == majority) / len(signs)
        force_alignment_score = _clamp(agreement * 100.0)
    else:
        force_alignment_score = 50.0

    inertia_bonus = 0.0
    if _contains(structure_text, ["STRONG", "CLEAN", "HIGH", "GOOD"]):
        inertia_bonus += 18.0
    if _contains(phase_text, ["MARKUP", "MARKDOWN", "TREND", "CONTINUATION"]):
        inertia_bonus += 18.0
    trend_inertia = _clamp(adx * 0.55 + min(abs(directional_force), 100.0) * 0.25 + inertia_bonus)

    volatility_pressure = _clamp(atr_pct * 0.45 + iv_rank * 0.35 + compression_energy * 0.20)
    entropy_score = _clamp((100.0 - force_alignment_score) * 0.45 + (100.0 - min(abs(directional_force), 100.0)) * 0.25 + (100.0 - trend_inertia) * 0.20 + max(0.0, volatility_pressure - 70.0) * 0.10)

    drift_status = str(macro_context.get("regime_drift_status") or row.get("regime_drift_status") or "").upper()
    instability = entropy_score * 0.35 + volatility_pressure * 0.25
    if drift_status in {"DRIFTING", "FLIPPED", "CONFLICTED"}:
        instability += 20.0
    if sector_alignment == "CONFLICTED":
        instability += 15.0
    regime_instability_score = _clamp(instability)

    gap_score = _as_0_100(abs(n(["gap_pct", "gap_percent", "overnight_gap_pct"], 0.0)) * 5.0)
    shock_sensitivity = _clamp(atr_pct * 0.35 + iv_rank * 0.30 + min(abs(beta), 3.0) / 3.0 * 20.0 + gap_score * 0.15)

    liquidity_friction_score = _clamp(
        min(spread_pct * 4.0, 70.0)
        + (25.0 if avg_volume < 500_000 else 12.0 if avg_volume < 1_000_000 else 0.0)
    )

    market_energy_score = _clamp(
        compression_energy * 0.35
        + volatility_pressure * 0.25
        + min(abs(directional_force), 100.0) * 0.20
        + trend_inertia * 0.10
        + (100.0 - entropy_score) * 0.10
    )

    actuarial_prob = n(["layer2__adjusted_prob_target_hit", "layer2__baseline_probability", "win_rate_10d", "win_rate_20d"], 50.0)
    if 0.0 <= actuarial_prob <= 1.0:
        actuarial_prob *= 100.0
    phase_transition_probability = _clamp(
        actuarial_prob * 0.25
        + market_energy_score * 0.25
        + force_alignment_score * 0.20
        + volatility_pressure * 0.15
        + (100.0 - entropy_score) * 0.15
        - liquidity_friction_score * 0.10
    )

    abs_force = abs(directional_force)
    if entropy_score >= 65 and abs_force < 25:
        hidden_state_label = "HIGH_ENTROPY_CHOP"
        state_transition_label = "NO_TRANSITION_EDGE"
    elif compression_energy >= 65 and directional_force >= 25 and entropy_score < 60:
        hidden_state_label = "COMPRESSED_BULLISH_FORCE"
        state_transition_label = "BALANCE_TO_UPSIDE_EXPANSION"
    elif compression_energy >= 65 and directional_force <= -25 and entropy_score < 60:
        hidden_state_label = "COMPRESSED_BEARISH_FORCE"
        state_transition_label = "BALANCE_TO_DOWNSIDE_EXPANSION"
    elif trend_inertia >= 65 and directional_force >= 25:
        hidden_state_label = "TRENDING_BULLISH_INERTIA"
        state_transition_label = "CONTINUATION_UP"
    elif trend_inertia >= 65 and directional_force <= -25:
        hidden_state_label = "TRENDING_BEARISH_INERTIA"
        state_transition_label = "CONTINUATION_DOWN"
    elif volatility_pressure >= 75 and compression_energy >= 55:
        hidden_state_label = "VOL_EXPANSION_PENDING"
        state_transition_label = "FAILED_BREAKOUT_RISK" if entropy_score >= 55 else "NO_TRANSITION_EDGE"
    elif shock_sensitivity >= 75:
        hidden_state_label = "SHOCK_SENSITIVE"
        state_transition_label = "NO_TRANSITION_EDGE"
    elif market_energy_score < 35:
        hidden_state_label = "LOW_ENERGY_NO_EDGE"
        state_transition_label = "NO_TRANSITION_EDGE"
    elif compression_energy >= 55:
        hidden_state_label = "COMPRESSED_BALANCED"
        state_transition_label = "CHOP_CONTINUATION"
    elif directional_force >= 20:
        hidden_state_label = "TRENDING_BULLISH_INERTIA"
        state_transition_label = "CONTINUATION_UP"
    elif directional_force <= -20:
        hidden_state_label = "TRENDING_BEARISH_INERTIA"
        state_transition_label = "CONTINUATION_DOWN"
    else:
        hidden_state_label = "LOW_ENERGY_NO_EDGE"
        state_transition_label = "NO_TRANSITION_EDGE"

    physics_state_id = "|".join([
        "PHYS",
        _bucket(market_energy_score, "ENERGY"),
        _bucket(directional_force, "FORCE", signed=True),
        _bucket(trend_inertia, "INERTIA"),
        _bucket(entropy_score, "ENTROPY"),
        _bucket(volatility_pressure, "VOL_PRESSURE"),
        _bucket(liquidity_friction_score, "FRICTION"),
    ])

    future_state_5d = _first(row, ["future_state_5d"], None) or _future_state_from_label(state_transition_label, "5D")
    future_state_10d = _first(row, ["future_state_10d"], None) or _future_state_from_label(state_transition_label, "10D")
    future_state_20d = _first(row, ["future_state_20d"], None) or _future_state_from_label(state_transition_label, "20D")

    out = {
        "physics_state_id": physics_state_id,
        "market_energy_score": market_energy_score,
        "compression_energy": compression_energy,
        "directional_force": directional_force,
        "force_alignment_score": force_alignment_score,
        "trend_inertia": trend_inertia,
        "volatility_pressure": volatility_pressure,
        "entropy_score": entropy_score,
        "regime_instability_score": regime_instability_score,
        "phase_transition_probability": phase_transition_probability,
        "shock_sensitivity": shock_sensitivity,
        "liquidity_friction_score": liquidity_friction_score,
        "hidden_state_label": hidden_state_label,
        "state_transition_label": state_transition_label,
        "future_state_5d": future_state_5d,
        "future_state_10d": future_state_10d,
        "future_state_20d": future_state_20d,
        "transition_success_5d": _success_probability(phase_transition_probability, "5d"),
        "transition_success_10d": _success_probability(phase_transition_probability, "10d"),
        "transition_success_20d": _success_probability(phase_transition_probability, "20d"),
        "physics_data_quality": "DEGRADED_DEFAULTS" if defaulted else "CONFIRMED",
        "physics_defaulted_fields": json.dumps(sorted(set(defaulted))),
        "physics_degraded_reason": "NEUTRAL_DEFAULTS_USED" if defaulted else "",
    }
    return out


def ensure_physics_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure all physics fields exist, using explicit neutral defaults."""
    out = df.copy()
    if out.empty:
        for field in ALL_PHYSICS_FIELDS:
            if field not in out.columns:
                out[field] = pd.Series(dtype="object")
        return out
    missing = [field for field in PHYSICS_FIELDS if field not in out.columns]
    if missing:
        neutral_rows = [calculate_market_physics(row.to_dict()) for _, row in out.iterrows()]
        neutral = pd.DataFrame(neutral_rows, index=out.index)
        for field in ALL_PHYSICS_FIELDS:
            if field not in out.columns and field in neutral.columns:
                out[field] = neutral[field]
    for field in PHYSICS_NUMERIC_FIELDS:
        if field in out.columns:
            out[field] = pd.to_numeric(out[field], errors="coerce").fillna(50.0 if field != "directional_force" else 0.0)
    return out


def enrich_with_market_physics(
    df: pd.DataFrame,
    macro_context: Optional[Mapping[str, Any]] = None,
) -> pd.DataFrame:
    """Append market physics fields to a dataframe without removing columns."""
    out = df.copy()
    if out.empty:
        return ensure_physics_fields(out)
    log.info("Physics layer loaded")
    physics_rows = [calculate_market_physics(row.to_dict(), macro_context=macro_context) for _, row in out.iterrows()]
    physics_df = pd.DataFrame(physics_rows, index=out.index)
    for field in ALL_PHYSICS_FIELDS:
        if field in out.columns:
            out[field] = out[field].where(~out[field].isna() & (out[field].astype(str).str.strip() != ""), physics_df[field])
        else:
            out[field] = physics_df[field]
    missing_count = int(out[PHYSICS_FIELDS].isna().sum().sum())
    degraded_count = int((out.get("physics_data_quality", "") == "DEGRADED_DEFAULTS").sum())
    log.info(
        "Physics fields calculated: rows=%d missing_values=%d degraded_rows=%d",
        len(out),
        missing_count,
        degraded_count,
    )
    return out


def append_physics_fields_from_source(target_df: pd.DataFrame, source_df: pd.DataFrame) -> pd.DataFrame:
    """Carry physics fields from an upstream dataframe by ticker, preserving target values."""
    if target_df is None or target_df.empty:
        return target_df
    out = target_df.copy()
    if source_df is None or source_df.empty or "ticker" not in out.columns or "ticker" not in source_df.columns:
        return ensure_physics_fields(out)
    source_cols = ["ticker"] + [c for c in ALL_PHYSICS_FIELDS if c in source_df.columns]
    if len(source_cols) <= 1:
        return ensure_physics_fields(out)
    src = source_df[source_cols].copy()
    src["ticker"] = src["ticker"].astype(str).str.upper().str.strip()
    src = src.drop_duplicates(subset=["ticker"], keep="last")
    out["ticker"] = out["ticker"].astype(str).str.upper().str.strip()
    merged = out.merge(src, on="ticker", how="left", suffixes=("", "__physics"))
    for field in ALL_PHYSICS_FIELDS:
        alt = f"{field}__physics"
        if alt in merged.columns:
            if field in merged.columns:
                current = merged[field]
                fill = current.isna() | current.astype(str).str.strip().isin(["", "nan", "None", "UNKNOWN", "MISSING"])
                merged.loc[fill, field] = merged.loc[fill, alt]
                merged = merged.drop(columns=[alt])
            else:
                merged[field] = merged[alt]
                merged = merged.drop(columns=[alt])
    return ensure_physics_fields(merged)


# ── F8 (ACK, 19 Sep 2026): measured price inputs ─────────────────────────────────────────────────────────────
# Run 20260918_112522 used neutral defaults for returns, average volume and beta on every row: nothing computed
# them. They are measured from the canonical price store at the row's evidence session (point-in-time).
from pathlib import Path as _Path

CANONICAL_PRICE_DB = _Path(__file__).resolve().parents[1] / "data" / "canonical" / "historical_prices.sqlite"
_BETA_SESSIONS = 60
_AVG_VOLUME_SESSIONS = 20


def _store_bars(symbol: str, as_of: str, count: int) -> list[tuple[str, float, float]]:
    import sqlite3
    try:
        con = sqlite3.connect(f"file:{_Path(CANONICAL_PRICE_DB).as_posix()}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT trading_date, close, volume FROM ohlcv_daily WHERE ticker = ? AND trading_date <= ? "
                "AND close IS NOT NULL ORDER BY trading_date DESC LIMIT ?", (symbol.upper(), as_of, count)).fetchall()
        finally:
            con.close()
    except Exception:  # noqa: BLE001 - reported as unavailable, never zero
        return []
    return [(str(d), float(c), float(v) if v is not None else float("nan")) for d, c, v in reversed(rows)]


def physics_price_inputs(ticker: str, as_of: Any) -> Dict[str, Any]:
    """Returns (fractions), 20-session average share volume and 60-session beta vs SPY at ``as_of``.

    Inputs that cannot be measured are left absent so the physics engine flags them; the reason is recorded in
    ``physics_price_inputs_state``.
    """
    session = str(as_of or "").strip()[:10]
    if not session or session.upper() in {"NAN", "NONE"}:
        return {"physics_price_inputs_state": "EVIDENCE_SESSION_UNAVAILABLE"}
    bars = _store_bars(ticker, session, _BETA_SESSIONS + 1)
    if len(bars) < 11:
        return {"physics_price_inputs_state": "TICKER_PRICES_UNAVAILABLE"}
    closes = [c for _, c, _ in bars]
    volumes = [v for _, _, v in bars[-_AVG_VOLUME_SESSIONS:] if v == v]
    out: Dict[str, Any] = {
        "return_5d": closes[-1] / closes[-6] - 1.0,
        "return_10d": closes[-1] / closes[-11] - 1.0,
        "physics_price_inputs_state": "CANONICAL_PRICE_STORE",
    }
    if volumes:
        out["avg_volume"] = sum(volumes) / len(volumes)
    spy = {d: c for d, c, _ in _store_bars("SPY", session, _BETA_SESSIONS + 1)}
    paired = [(c, spy[d]) for d, c, _ in bars if d in spy]
    if len(paired) >= 21:
        tr = [paired[i][0] / paired[i - 1][0] - 1.0 for i in range(1, len(paired))]
        mr = [paired[i][1] / paired[i - 1][1] - 1.0 for i in range(1, len(paired))]
        mean_t, mean_m = sum(tr) / len(tr), sum(mr) / len(mr)
        var_m = sum((m - mean_m) ** 2 for m in mr)
        if var_m > 0:
            out["beta"] = sum((t - mean_t) * (m - mean_m) for t, m in zip(tr, mr)) / var_m
    return out



# ── Forward pressure verdict (ACK, 19 Sep 2026) ───────────────────────────────────────────────────────────────
# EIL routes a no-current-edge row to EOD_PROBE_CANDIDATE when physics shows forward pressure in the trade's
# direction; nothing produced that verdict, so the route never fired. Display, measurement and review routing
# only - no capital, no ticket ranking.
_PRESSURE_WITH = {
    "CALL": {"BALANCE_TO_UPSIDE_EXPANSION": "EARLY_PRESSURE_BUILDING", "CONTINUATION_UP": "MONETISABLE_PRESSURE"},
    "PUT": {"BALANCE_TO_DOWNSIDE_EXPANSION": "EARLY_PRESSURE_BUILDING", "CONTINUATION_DOWN": "MONETISABLE_PRESSURE"},
}
_PRESSURE_AGAINST = {
    "CALL": {"BALANCE_TO_DOWNSIDE_EXPANSION", "CONTINUATION_DOWN"},
    "PUT": {"BALANCE_TO_UPSIDE_EXPANSION", "CONTINUATION_UP"},
}


def physics_forward_verdict(state_transition_label: Any, direction: Any) -> str:
    """EARLY_PRESSURE_BUILDING | MONETISABLE_PRESSURE | PRESSURE_AGAINST_DIRECTION | NO_DIRECTIONAL_PRESSURE |
    NOT_APPLICABLE_NON_DIRECTIONAL | PHYSICS_UNAVAILABLE."""
    side = str(direction or "").strip().upper()
    if side not in _PRESSURE_WITH:
        return "NOT_APPLICABLE_NON_DIRECTIONAL"
    label = str(state_transition_label or "").strip().upper()
    if label in MISSING_TOKENS:
        return "PHYSICS_UNAVAILABLE"
    if label in _PRESSURE_WITH[side]:
        return _PRESSURE_WITH[side][label]
    if label in _PRESSURE_AGAINST[side]:
        return "PRESSURE_AGAINST_DIRECTION"
    return "NO_DIRECTIONAL_PRESSURE"
