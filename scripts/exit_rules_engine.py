"""
Exit Rules Engine
=================
Converts existing manifest fields into explicit per-trade exit rules.
Runs on morning_candidates CSV via orchestrator Phase 10.
All 6 output fields are additive — no existing columns are modified.
"""
from datetime import date, timedelta
import math
from typing import Any


_MAX_THETA_DAYS = 365


def _f(row: dict, *keys: str, default: float = 0.0) -> float:
    for k in keys:
        v = row.get(k)
        if v is None or v == "":
            continue
        try:
            f = float(v)
            if math.isfinite(f):
                return f
        except Exception:
            continue
    return default


def compute_exit_rules(row: dict) -> dict:
    try:
        live_price   = _f(row, "live_price", "signal_price")
        target       = _f(row, "structural_target")
        stop         = _f(row, "structural_stop", "invalidation_level")
        theta        = abs(_f(row, "contract_theta"))
        dte          = _f(row, "dte", "contract_dte")
        contract_mid = _f(row, "contract_mid")
        direction    = str(
            row.get("canonical_direction") or row.get("primary_direction") or ""
        ).upper().strip()

        exit_target = target if target > 0 else None
        exit_stop   = stop   if stop   > 0 else None

        theta_days = None
        exit_theta_date = None
        if theta > 0 and contract_mid > 0:
            theta_days = int(contract_mid * 0.5 / theta)
            theta_days = max(1, min(theta_days, int(dte) if dte > 0 else _MAX_THETA_DAYS))
            exit_theta_date = (date.today() + timedelta(days=theta_days)).isoformat()

        exit_max_dte = int(dte * 0.5) if dte > 0 else None

        rr_ok = False
        if live_price and exit_target and exit_stop:
            if direction == "CALL":
                reward = exit_target - live_price
                risk   = live_price  - exit_stop
            else:
                reward = live_price  - exit_target
                risk   = exit_stop   - live_price
            rr_ok = risk > 0 and (reward / risk) >= 1.5

        parts = []
        if exit_target:
            parts.append(f"TARGET {exit_target:.2f}")
        if exit_stop:
            parts.append(f"STOP {exit_stop:.2f}")
        if exit_theta_date:
            parts.append(f"THETA_EXIT {exit_theta_date}")
        if exit_max_dte:
            parts.append(f"MAX_DTE -{exit_max_dte}d")
        if not rr_ok and exit_target and exit_stop:
            parts.append("RR_BELOW_1.5_REVIEW")

        return {
            "exit_target_price": exit_target,
            "exit_stop_price":   exit_stop,
            "exit_theta_date":   exit_theta_date,
            "exit_max_dte":      exit_max_dte,
            "exit_rr_valid":     bool(rr_ok),
            "exit_rule_summary": " | ".join(parts) if parts else "MANUAL_REVIEW",
        }
    except Exception:
        return {
            "exit_target_price": None,
            "exit_stop_price":   None,
            "exit_theta_date":   None,
            "exit_max_dte":      None,
            "exit_rr_valid":     None,
            "exit_rule_summary": "ERROR",
        }


def enrich_dataframe(df: "pd.DataFrame") -> "pd.DataFrame":
    import pandas as pd
    rows = [compute_exit_rules(r) for r in df.to_dict("records")]
    exit_df = pd.DataFrame(rows, index=df.index)
    for col in exit_df.columns:
        df[col] = exit_df[col]
    return df
