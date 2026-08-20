from __future__ import annotations

from typing import Any, Mapping

NEUTRAL_DISTRIBUTION = {"bull": 0.30, "neutral": 0.40, "bear": 0.30}
BULLISH_DISTRIBUTION = {"bull": 0.45, "neutral": 0.35, "bear": 0.20}
BEARISH_DISTRIBUTION = {"bull": 0.20, "neutral": 0.35, "bear": 0.45}
BALANCED_DISTRIBUTION = {"bull": 0.33, "neutral": 0.34, "bear": 0.33}

REGIME_DISTRIBUTION_MAP = {
    "TRENDING_BULL": {"bull": 0.75, "neutral": 0.20, "bear": 0.05},
    "RISK_ON": {"bull": 0.65, "neutral": 0.25, "bear": 0.10},
    "RECOVERY": {"bull": 0.60, "neutral": 0.30, "bear": 0.10},
    "TRANSITIONAL_BULLISH": BULLISH_DISTRIBUTION,
    "TRENDING_BEAR": {"bull": 0.05, "neutral": 0.20, "bear": 0.75},
    "RISK_OFF": {"bull": 0.10, "neutral": 0.25, "bear": 0.65},
    "CRISIS": {"bull": 0.05, "neutral": 0.15, "bear": 0.80},
    "TRANSITIONAL_BEARISH": BEARISH_DISTRIBUTION,
    "RISK_OFF_TILT": {"bull": 0.15, "neutral": 0.35, "bear": 0.50},
    "NEUTRAL_TO_RISK_OFF": {"bull": 0.20, "neutral": 0.35, "bear": 0.45},
    "NEUTRAL_TO_DEFENSIVE": {"bull": 0.20, "neutral": 0.40, "bear": 0.40},
    "NEUTRAL_TO_RISK_ON": {"bull": 0.45, "neutral": 0.35, "bear": 0.20},
    "TRANSITIONAL_NEUTRAL": NEUTRAL_DISTRIBUTION,
    "CHOPPY_NEUTRAL": {"bull": 0.25, "neutral": 0.45, "bear": 0.30},
    "NEUTRAL": BALANCED_DISTRIBUTION,
    "TRANSITIONAL": BALANCED_DISTRIBUTION,
    "UNKNOWN": BALANCED_DISTRIBUTION,
    "MIXED": BALANCED_DISTRIBUTION,
}


def _text(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "_").replace("-", "_")


def _float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        out = float(value)
        if out > 1.0:
            out = out / 100.0
        return out
    except Exception:
        return None


def _is_neutral_drift(drift: str) -> bool:
    d = _text(drift)
    if not d:
        return False
    exact = {
        "DRIFTING_NEUTRAL",
        "NEUTRAL_DRIFT",
        "STABLE_NEUTRAL",
        "CHOPPY_NEUTRAL",
        "SIDEWAYS",
        "BALANCED",
        "BALANCED_NEUTRAL",
        "FLAT",
        "RANGE",
        "RANGE_BOUND",
    }
    if d in exact:
        return True
    if "NEUTRAL" in d and "BEAR" not in d and "BULL" not in d and "RISK_OFF" not in d and "RISK_ON" not in d:
        return True
    return any(token in d for token in ("STABLE", "SIDEWAYS", "BALANCED", "RANGE_BOUND"))


def derive_regime_sub_state(
    regime_state: Any,
    regime_drift_status: Any = "",
    dir_bias: Any = "",
    macro_conviction: Any = None,
) -> str:
    rs = _text(regime_state) or "UNKNOWN"
    drift = _text(regime_drift_status)
    bias = _text(dir_bias)
    conviction = _float(macro_conviction)

    if rs in REGIME_DISTRIBUTION_MAP and rs.startswith("TRANSITIONAL_"):
        return rs

    ambiguous = {"TRANSITIONAL", "UNKNOWN", "MIXED", "CHOPPY_NEUTRAL", "NEUTRAL", ""}
    if rs in ambiguous or "TRANSITION" in rs:
        if _is_neutral_drift(drift):
            return "TRANSITIONAL_NEUTRAL"
        if any(token in drift for token in ("BULL", "IMPROVING", "RISK_ON", "ACCELERATING_UP")):
            return "TRANSITIONAL_BULLISH"
        if any(token in drift for token in ("BEAR", "DETERIORATING", "RISK_OFF")):
            return "TRANSITIONAL_BEARISH"
        if bias in {"NEUTRAL", "ABSTAIN", "NONE", ""} and (conviction is None or conviction <= 0.55):
            return "TRANSITIONAL_NEUTRAL"
        if bias in {"CALL", "BULLISH", "RISK_ON"} and conviction is not None and conviction >= 0.55:
            return "TRANSITIONAL_BULLISH"
        if bias in {"PUT", "BEARISH", "RISK_OFF"} and conviction is not None and conviction >= 0.55:
            return "TRANSITIONAL_BEARISH"
        return "TRANSITIONAL_NEUTRAL"

    return rs


def derive_regime_distribution(
    regime_state: Any,
    regime_drift_status: Any = "",
    dir_bias: Any = "",
    macro_conviction: Any = None,
) -> dict[str, float]:
    sub_state = derive_regime_sub_state(regime_state, regime_drift_status, dir_bias, macro_conviction)
    return dict(REGIME_DISTRIBUTION_MAP.get(sub_state, REGIME_DISTRIBUTION_MAP.get(_text(regime_state), BALANCED_DISTRIBUTION)))


def normalise_macro_regime_fields(macro: Mapping[str, Any] | None) -> dict[str, Any]:
    out = dict(macro or {})
    regime_state = out.get("regime_state") or out.get("regime_label") or out.get("macro_regime_label") or "UNKNOWN"
    drift = out.get("regime_drift_status") or out.get("drift_status") or ""
    dir_bias = out.get("dir_bias") or out.get("direction_bias") or out.get("macro_direction_bias") or ""
    conviction = out.get("macro_conviction") or out.get("conviction_score") or out.get("predictability_score")

    sub_state = derive_regime_sub_state(regime_state, drift, dir_bias, conviction)
    distribution = derive_regime_distribution(regime_state, drift, dir_bias, conviction)

    out["regime_sub_state"] = sub_state
    out["macro_regime_sub_state"] = sub_state
    out["regime_distribution"] = distribution
    out["regime_distribution_source"] = "macro_regime_safety"

    if sub_state == "TRANSITIONAL_NEUTRAL":
        out["regime_drift_interpretation"] = "NEUTRAL_DRIFT_NO_DIRECTIONAL_EDGE"
    elif sub_state == "TRANSITIONAL_BULLISH":
        out["regime_drift_interpretation"] = "BULLISH_DRIFT_SELECTIVE_EDGE"
    elif sub_state == "TRANSITIONAL_BEARISH":
        out["regime_drift_interpretation"] = "BEARISH_DRIFT_SELECTIVE_EDGE"
    else:
        out["regime_drift_interpretation"] = "REGIME_DIRECT"

    return out
