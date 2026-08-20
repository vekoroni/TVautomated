"""
McMillan advisory layer.

This module adds operator-facing context to EIL and morning handoff data.
It is intentionally read-only with respect to decisions: no filtering, no
sizing, and no verdict changes.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


MCMILLAN_FIELDS = [
    "iv_gex_entry_quality",
    "iv_gex_entry_quality_label",
    "iv_gex_entry_quality_narrative",
    "gamma_island_on_path",
    "move_theta_ratio",
    "move_theta_margin_label",
    "move_theta_narrative",
    "crowd_arrival_state",
    "crowd_arrival_score",
    "crowd_arrival_components",
    "crowd_arrival_narrative",
]


STATE_RELATIVE_PATH = Path("data") / "output" / "state" / "avshunter_run_state.json"


def _get(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        value = row.get(key, default)
    except AttributeError:
        return default
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return value


def _text(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = _get(row, key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in {"nan", "none", "<na>"}:
            return text
    return ""


def _number(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _get(row, key)
        if value is None:
            continue
        try:
            num = float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            continue
        if math.isfinite(num):
            return num
    return None


def _truthy(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip().upper()
    return text in {"1", "TRUE", "YES", "Y", "ON"}


def _normalise_percent(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    value = float(value)
    if abs(value) <= 1.0:
        value *= 100.0
    return max(0.0, min(100.0, value))


def _percent_to_decimal(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    value = abs(float(value))
    if value <= 1.0:
        return value
    return value / 100.0


def _ivp(row: Mapping[str, Any]) -> float | None:
    raw = _number(
        row,
        "ivp",
        "iv_percentile",
        "iv_rank",
        "ivp_252d",
        "ivp_30d",
        "atm_iv_percentile",
        "l3_iv_percentile",
        "l3_iv_rank",
    )
    return _normalise_percent(raw)


def _iv_bucket(ivp: float | None) -> str:
    if ivp is None:
        return "UNKNOWN_IV"
    if ivp < 30:
        return "CHEAP_IV"
    if ivp > 70:
        return "EXPENSIVE_IV"
    return "MID_IV"


def _gex_bucket(row: Mapping[str, Any]) -> str:
    label = _text(
        row,
        "eil_gex_regime",
        "dealer_gamma_state",
        "gex_regime",
        "gamma_regime",
        "gamma_velocity_label",
    ).upper()
    if any(token in label for token in ("NEGATIVE", "AMPLIFY", "SHORT_GAMMA", "RISK")):
        return "AMPLIFYING_GEX"
    if any(token in label for token in ("POSITIVE", "PIN", "DAMPEN", "LONG_GAMMA")):
        return "PINNING_GEX"

    score = _number(row, "gex_regime_score", "eil_gex_score")
    if score is not None:
        scaled = score / 100.0 if score > 1 else score
        if scaled <= 0.40:
            return "AMPLIFYING_GEX"
        if scaled >= 0.60:
            return "PINNING_GEX"

    if _truthy(_get(row, "gamma_risk_flag")):
        return "AMPLIFYING_GEX"
    return "UNKNOWN_GEX"


def _price_between(start: float | None, end: float | None, point: float | None) -> bool:
    if start is None or end is None or point is None:
        return False
    low = min(start, end)
    high = max(start, end)
    return low <= point <= high


def _gamma_island_on_path(row: Mapping[str, Any]) -> bool:
    explicit = _get(row, "gamma_island_on_path")
    if explicit is not None:
        return _truthy(explicit)
    return False


def _iv_gex_advisory(row: Mapping[str, Any]) -> dict[str, Any]:
    ivp = _ivp(row)
    iv_bucket = _iv_bucket(ivp)
    gex_bucket = _gex_bucket(row)
    explicit_island = _get(row, "gamma_island_on_path") is not None
    island = _gamma_island_on_path(row)
    island_level = _number(row, "gamma_island_level")
    island_distance = _number(row, "gamma_island_distance_pct")
    island_label = _text(row, "gamma_island_label")
    island_source = _text(row, "gamma_island_source")

    if iv_bucket == "CHEAP_IV" and gex_bucket == "AMPLIFYING_GEX":
        quality = 4
        label = "MAXIMUM_TAILWIND"
    elif iv_bucket == "CHEAP_IV" and gex_bucket == "PINNING_GEX":
        quality = 3
        label = "CHEAP_BUT_PINNED"
    elif iv_bucket == "MID_IV" and gex_bucket == "AMPLIFYING_GEX":
        quality = 3
        label = "FAIR_IV_WITH_GEX_TAILWIND"
    elif iv_bucket == "EXPENSIVE_IV" and gex_bucket == "AMPLIFYING_GEX":
        quality = 2
        label = "EXPENSIVE_BUT_CAN_EXPAND"
    elif iv_bucket == "EXPENSIVE_IV" and gex_bucket == "PINNING_GEX":
        quality = 1
        label = "LEAST_FAVOURABLE"
    elif iv_bucket == "UNKNOWN_IV" or gex_bucket == "UNKNOWN_GEX":
        quality = 2
        label = "INCOMPLETE_REVIEW"
    else:
        quality = 2
        label = "NEUTRAL"

    iv_text = "IVP unavailable" if ivp is None else f"IVP {ivp:.1f}"
    if island:
        if island_level is not None:
            dist_text = "" if island_distance is None else f", {island_distance:.2f}% from spot"
            island_text = f"gamma island on path near {island_level:.2f}{dist_text}"
        else:
            island_text = "gamma island on path"
    elif explicit_island:
        source_text = f" via {island_source}" if island_source else ""
        label_text = f" ({island_label})" if island_label else ""
        island_text = f"per-strike gamma surface checked{source_text}; no gamma island detected on path{label_text}"
    else:
        island_text = "gamma island surface unavailable in Phase 1"
    narrative = f"{iv_text}; {iv_bucket}; {gex_bucket}; {island_text}. Advisory only."
    return {
        "iv_gex_entry_quality": quality,
        "iv_gex_entry_quality_label": label,
        "iv_gex_entry_quality_narrative": narrative,
        "gamma_island_on_path": bool(island),
    }


def _horizon_days(row: Mapping[str, Any]) -> float:
    text = _text(row, "expected_holding_window", "expected_move_window", "horizon_bucket", "macro_preferred_horizon").upper()
    if "1_5" in text or "1-5" in text:
        return 5.0
    if "6_10" in text or "6-10" in text:
        return 10.0
    if "11_20" in text or "11-20" in text:
        return 20.0
    dte = _number(row, "dte", "contract_dte")
    if dte and dte > 0:
        return max(1.0, min(10.0, dte))
    return 5.0


def _move_theta_advisory(row: Mapping[str, Any]) -> dict[str, Any]:
    move_decimal = _percent_to_decimal(
        _number(
            row,
            "expected_move_pct",
            "expected_move_pct_eod",
            "l3_expected_move_pct",
            "expected_move_10d_pct",
            "expected_move_5d_pct",
            "expected_move_10d",
            "expected_move_5d",
        )
    )
    spot = _number(row, "underlying_price", "signal_price", "scanner_price", "close", "price")
    theta = _number(row, "contract_theta", "theta")
    delta = _number(row, "contract_delta", "delta")
    days = _horizon_days(row)

    if move_decimal is None or spot is None or theta is None or abs(theta) <= 1e-9:
        return {
            "move_theta_ratio": "",
            "move_theta_margin_label": "UNAVAILABLE",
            "move_theta_narrative": "Expected move, spot, or theta missing. Manual review required.",
        }

    delta_abs = abs(delta) if delta is not None and abs(delta) > 0 else 0.50
    expected_delta_move = spot * move_decimal * delta_abs
    theta_cost = abs(theta) * days
    ratio = expected_delta_move / theta_cost if theta_cost > 0 else None

    if ratio is None or not math.isfinite(ratio):
        label = "UNAVAILABLE"
        ratio_out: float | str = ""
    elif ratio >= 10:
        label = "WIDE_MARGIN"
        ratio_out = round(ratio, 3)
    elif ratio >= 5:
        label = "MODERATE_MARGIN"
        ratio_out = round(ratio, 3)
    elif ratio >= 2:
        label = "TIGHT_MARGIN"
        ratio_out = round(ratio, 3)
    else:
        label = "CRITICAL"
        ratio_out = round(ratio, 3)

    narrative = (
        f"Expected move proxy over {days:.0f}d vs theta drag; "
        f"ratio={ratio_out if ratio_out != '' else 'unavailable'}. Advisory only."
    )
    return {
        "move_theta_ratio": ratio_out,
        "move_theta_margin_label": label,
        "move_theta_narrative": narrative,
    }


def _state_path(base_dir: str | Path | None) -> Path:
    root = Path(base_dir) if base_dir is not None else Path.cwd()
    return root / STATE_RELATIVE_PATH


def _load_previous_state(base_dir: str | Path | None) -> dict[str, Any]:
    path = _state_path(base_dir)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    tickers = payload.get("tickers", {})
    return tickers if isinstance(tickers, dict) else {}


def _write_state(df: pd.DataFrame, run_id: str, base_dir: str | Path | None) -> Path:
    path = _state_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tickers: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        ticker = _text(row, "ticker", "underlying").upper()
        if not ticker:
            continue
        tickers[ticker] = {
            "ivp": _ivp(row),
            "gex_bucket": _gex_bucket(row),
            "gamma_flip_gap_pct": _number(row, "gamma_flip_gap_pct"),
        }
    payload = {
        "version": 1,
        "run_id": run_id,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "tickers": tickers,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return path


def _crowd_arrival_advisory(row: Mapping[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    components: list[str] = []
    notes: list[str] = []
    ticker = _text(row, "ticker", "underlying").upper()
    current_ivp = _ivp(row)
    previous_row = previous.get(ticker, {}) if ticker else {}
    previous_ivp = previous_row.get("ivp") if isinstance(previous_row, dict) else None

    if _truthy(_get(row, "iv_accel_detected")):
        components.append("IV_ACCEL")
    elif current_ivp is not None and previous_ivp is not None:
        try:
            if current_ivp - float(previous_ivp) >= 10:
                components.append("IV_ACCEL")
        except (TypeError, ValueError):
            pass
    elif current_ivp is not None:
        notes.append("no prior IVP state")

    rvol = _number(row, "scanner_rvol", "volume_ratio", "relative_volume", "rvol")
    vol_label = _text(row, "vol_confirmation_label").upper()
    if (rvol is not None and rvol >= 1.5) or any(token in vol_label for token in ("CONFIRM", "SPIKE", "SURGE")):
        components.append("RVOL_SPIKE")

    gap = _number(row, "gamma_flip_gap_pct")
    gamma_label = _text(row, "gamma_velocity_label").upper()
    if (gap is not None and abs(gap) <= 5.0) or any(token in gamma_label for token in ("APPROACH", "ACCEL", "NEAR")):
        components.append("GAMMA_FLIP_PROXIMITY")

    components = sorted(set(components))
    score = len(components)
    if score >= 3:
        state = "LATE_CROWD_RISK"
    elif score == 2:
        state = "CROWD_ARRIVING"
    elif score == 1:
        state = "EARLY_CROWD_HINT"
    else:
        state = "EARLY_NO_CROWD"

    parts = ";".join(components)
    extra = f" ({'; '.join(notes)})" if notes else ""
    narrative = f"{state}: {parts or 'no crowd-arrival components'}{extra}. Advisory only."
    return {
        "crowd_arrival_state": state,
        "crowd_arrival_score": score,
        "crowd_arrival_components": parts,
        "crowd_arrival_narrative": narrative,
    }


def enrich_dataframe(
    df: pd.DataFrame,
    run_id: str,
    base_dir: str | Path | None = None,
    write_state: bool = True,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    out = df.copy()
    previous = _load_previous_state(base_dir)

    rows: list[dict[str, Any]] = []
    for _, row in out.iterrows():
        advisory = {}
        advisory.update(_iv_gex_advisory(row))
        advisory.update(_move_theta_advisory(row))
        advisory.update(_crowd_arrival_advisory(row, previous))
        rows.append(advisory)

    advisory_df = pd.DataFrame(rows, index=out.index)
    for field in MCMILLAN_FIELDS:
        out[field] = advisory_df[field] if field in advisory_df.columns else ""

    state_path = None
    if write_state:
        state_path = _write_state(out, run_id=run_id, base_dir=base_dir)

    stats = {
        "rows": int(len(out)),
        "fields_added": list(MCMILLAN_FIELDS),
        "iv_gex_labels": dict(Counter(out["iv_gex_entry_quality_label"].astype(str))),
        "move_theta_labels": dict(Counter(out["move_theta_margin_label"].astype(str))),
        "crowd_arrival_states": dict(Counter(out["crowd_arrival_state"].astype(str))),
        "state_path": str(state_path) if state_path is not None else "",
    }
    return out, stats


def enrich_csv(
    path: str | Path,
    run_id: str,
    base_dir: str | Path | None = None,
    inplace: bool = True,
    write_state: bool = True,
) -> dict[str, Any]:
    csv_path = Path(path)
    df = pd.read_csv(csv_path, low_memory=False)
    enriched, stats = enrich_dataframe(df, run_id=run_id, base_dir=base_dir, write_state=write_state)
    if inplace:
        enriched.to_csv(csv_path, index=False)
    stats["path"] = str(csv_path)
    return stats
