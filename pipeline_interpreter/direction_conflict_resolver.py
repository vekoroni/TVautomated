"""
Direction Conflict Resolver — AVSHUNTER Pipeline Interpreter
Scores 7 evidence layers for a single ticker row.
Detects pipeline misdiagnosis when dominant direction != pipeline direction.
"""

from __future__ import annotations
from typing import Any


# ---------------------------------------------------------------------------
# Layer scoring helpers
# ---------------------------------------------------------------------------

def _get_str(row: dict, *keys: str) -> str:
    for k in keys:
        v = row.get(k)
        if v:
            return str(v).strip().upper()
    return ""


def _get_float(row: dict, *keys: str) -> float | None:
    for k in keys:
        v = row.get(k)
        if v not in (None, "", "N/A", "nan"):
            try:
                return float(v)
            except (ValueError, TypeError):
                continue
    return None


def _score_layer(layer_name: str, row: dict) -> tuple[str, str]:
    """Return (vote, reason). vote is 'CALL', 'PUT', or 'NEUTRAL'."""

    if layer_name == "macro":
        regime = _get_str(row, "macro_regime", "regime_state", "morning_macro_regime_state")
        if "BULL" in regime:
            return "CALL", f"macro_regime={regime}"
        if "BEAR" in regime:
            return "PUT", f"macro_regime={regime}"
        return "NEUTRAL", f"macro_regime={regime or 'missing'}"

    if layer_name == "actuarial":
        verdict = _get_str(row, "probability_verdict", "actuarial_direction", "prob_direction")
        if "POSITIVE_EDGE" in verdict or verdict == "CALL":
            return "CALL", f"probability_verdict={verdict}"
        if "NEGATIVE_EDGE" in verdict or verdict == "PUT":
            return "PUT", f"probability_verdict={verdict}"
        return "NEUTRAL", f"probability_verdict={verdict or 'missing'}"

    if layer_name == "pcr":
        pcr = _get_str(row, "pcr_signal", "pcr_direction", "put_call_ratio_signal")
        if "BULLISH" in pcr:
            return "CALL", f"pcr_signal={pcr}"
        if "BEARISH" in pcr:
            return "PUT", f"pcr_signal={pcr}"
        return "NEUTRAL", f"pcr_signal={pcr or 'missing'}"

    if layer_name == "catalyst":
        cat = _get_str(row, "catalyst_direction", "news_bias", "catalyst_side")
        if "CALL" in cat or "BULLISH" in cat:
            return "CALL", f"catalyst_direction={cat}"
        if "PUT" in cat or "BEARISH" in cat:
            return "PUT", f"catalyst_direction={cat}"
        return "NEUTRAL", f"catalyst_direction={cat or 'missing'}"

    if layer_name == "chart":
        phase = _get_str(row, "wyckoff_phase", "phase", "phase_best")
        intent = _get_str(row, "intent")
        if ("ACCUMULATION" in phase or "MARKUP" in phase) and ("BULLISH" in intent or "LONG" in intent):
            return "CALL", f"wyckoff_phase={phase} intent={intent}"
        if ("ACCUMULATION" in phase or "MARKUP" in phase):
            return "CALL", f"wyckoff_phase={phase}"
        if ("DISTRIBUTION" in phase or "MARKDOWN" in phase) and ("BEARISH" in intent or "SHORT" in intent):
            return "PUT", f"wyckoff_phase={phase} intent={intent}"
        if ("DISTRIBUTION" in phase or "MARKDOWN" in phase):
            return "PUT", f"wyckoff_phase={phase}"
        return "NEUTRAL", f"wyckoff_phase={phase or 'missing'}"

    if layer_name == "narrative":
        narr = _get_str(row, "trader_narrative", "narrative_direction", "signal_narrative")
        if "LONG_CALL" in narr or narr == "CALL":
            return "CALL", f"trader_narrative={narr}"
        if "LONG_PUT" in narr or narr == "PUT":
            return "PUT", f"trader_narrative={narr}"
        return "NEUTRAL", f"trader_narrative={narr or 'missing'}"

    if layer_name == "pipeline":
        direction = _get_str(row, "direction", "evening_direction", "canonical_direction")
        if direction == "CALL":
            return "CALL", f"pipeline_direction={direction}"
        if direction == "PUT":
            return "PUT", f"pipeline_direction={direction}"
        return "NEUTRAL", f"pipeline_direction={direction or 'missing'}"

    return "NEUTRAL", f"unknown layer: {layer_name}"


# ---------------------------------------------------------------------------
# Context modifiers
# ---------------------------------------------------------------------------

def _compute_weights(row: dict) -> tuple[dict[str, float], list[str]]:
    """Return per-layer weights and list of applied modifier names."""
    weights = {
        "macro":      1.0,
        "actuarial":  1.0,
        "pcr":        1.0,
        "catalyst":   1.0,
        "chart":      1.0,
        "narrative":  1.0,
        "pipeline":   1.0,
    }
    modifiers_applied = []

    # POST_EARNINGS_WINDOW
    days_since = _get_float(row, "days_since_earnings", "earnings_days_ago", "catalyst_age_days")
    if days_since is not None and days_since <= 10:
        weights["pcr"]      *= 0.5
        weights["catalyst"] *= 0.7
        modifiers_applied.append("POST_EARNINGS_WINDOW")

    # HIGH_VIX
    vix = _get_float(row, "vix_level", "macro_vix")
    if vix is not None and vix > 25:
        weights["pcr"] *= 0.5
        modifiers_applied.append("HIGH_VIX")
    else:
        regime_str = _get_str(row, "macro_regime", "regime_state")
        if "HIGH_VIX" in regime_str or "RISK_OFF" in regime_str:
            weights["pcr"] *= 0.5
            modifiers_applied.append("HIGH_VIX(regime_derived)")

    # ACTUARIAL_HIGH_N
    n_obs = _get_float(row, "actuarial_n", "n_observations", "actuarial_matches")
    if n_obs is not None and n_obs >= 300:
        weights["actuarial"] *= 1.3
        modifiers_applied.append("ACTUARIAL_HIGH_N")

    # CHART_CONFIRMED_TODAY
    adx = _get_float(row, "adx_daily", "adx_1d")
    ema_stack = row.get("ema_stack_bullish")
    if adx is not None and adx > 25 and ema_stack not in (None, "", "0", False):
        weights["chart"] *= 1.2
        modifiers_applied.append("CHART_CONFIRMED_TODAY")

    # PIPELINE_DIRECTION_SCORE_TIE
    call_sc = _get_float(row, "direction_call_score")
    put_sc  = _get_float(row, "direction_put_score")
    if call_sc is not None and put_sc is not None and call_sc == put_sc:
        weights["pipeline"] *= 0.5
        modifiers_applied.append("PIPELINE_DIRECTION_SCORE_TIE")

    return weights, modifiers_applied


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------

_LAYERS = ["macro", "actuarial", "pcr", "catalyst", "chart", "narrative", "pipeline"]

_LAYER_LABELS = {
    "macro":      "1. Macro regime",
    "actuarial":  "2. Actuarial probability",
    "pcr":        "3. PCR positioning",
    "catalyst":   "4. Catalyst direction",
    "chart":      "5. Chart / Wyckoff",
    "narrative":  "6. Trader narrative",
    "pipeline":   "7. Pipeline structural",
}


def resolve_direction(row: dict) -> dict[str, Any]:
    """
    Analyse a single ticker row from morning_validated_trades.
    Score 7 evidence layers with context-aware weights.
    Return dominant direction and conflict severity.
    """
    weights, modifiers_applied = _compute_weights(row)

    call_score = 0.0
    put_score  = 0.0
    call_layers = 0
    put_layers  = 0
    layer_detail = []

    for layer in _LAYERS:
        vote, reason = _score_layer(layer, row)
        w = weights[layer]
        entry = {
            "layer":  _LAYER_LABELS[layer],
            "vote":   vote,
            "weight": round(w, 4),
            "reason": reason,
        }
        layer_detail.append(entry)
        if vote == "CALL":
            call_score  += w
            call_layers += 1
        elif vote == "PUT":
            put_score  += w
            put_layers += 1

    # Dominant direction
    if call_score == 0 and put_score == 0:
        dominant_direction = "UNCLEAR"
        conflict_severity  = "NONE"
    else:
        dominant_direction = "CALL" if call_score >= put_score else "PUT"
        total = call_score + put_score
        minority_share = min(call_score, put_score) / total
        if minority_share < 0.15:
            conflict_severity = "NONE"
        elif minority_share < 0.20:
            conflict_severity = "LOW"
        elif minority_share < 0.45:
            conflict_severity = "MODERATE"
        else:
            conflict_severity = "HIGH"

    # Misdiagnosis detection
    pipeline_direction = _get_str(row, "direction", "evening_direction", "canonical_direction")
    misdiagnosed = (
        dominant_direction != "UNCLEAR"
        and bool(pipeline_direction)
        and dominant_direction != pipeline_direction
        and conflict_severity in ("MODERATE", "HIGH")
    )

    return {
        "dominant_direction":        dominant_direction,
        "pipeline_direction":        pipeline_direction,
        "misdiagnosed":              misdiagnosed,
        "conflict_severity":         conflict_severity,
        "call_score":                round(call_score, 2),
        "put_score":                 round(put_score, 2),
        "call_layers":               call_layers,
        "put_layers":                put_layers,
        "layer_detail":              layer_detail,
        "context_modifiers_applied": modifiers_applied,
    }
