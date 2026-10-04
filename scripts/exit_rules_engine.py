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

from contracts.governed_states import LifecycleEvaluationState


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


def _expiry(row: dict):
    for key in ("contract_expiry", "selected_contract_expiry", "expiry"):
        text = str(row.get(key) or "")[:10]
        try:
            return date.fromisoformat(text)
        except ValueError:
            continue
    return None


def compute_exit_rules(row: dict) -> dict:
    try:
        live_price   = _f(row, "live_price", "signal_price")
        # Step 4d (ACK 3 Oct 2026): the exit target is the anticipated level; the retired 3R / structural
        # target is never an exit. The invalidation is the thesis exit.
        target       = _f(row, "anticipated_level")
        stop         = _f(row, "invalidation_spot", "ev3_invalidation_spot")
        theta        = abs(_f(row, "contract_theta"))
        # Step 4d: DTE from the selected contract's own expiry (calendar days), never a row default.
        expiry       = _expiry(row)
        dte          = float((expiry - date.today()).days) if expiry is not None else 0.0
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
            theta_exit = date.today() + timedelta(days=theta_days)
            exit_theta_date = (min(theta_exit, expiry) if expiry is not None else theta_exit).isoformat()

        exit_max_dte = int(dte * 0.5) if dte > 0 else None

        # ACK 3 Oct 2026 (D-B, step 5): no stop-based R:R; the exit plan states whether the move pays.
        move_pays = str(row.get("anticipated_pays_state") or "NOT_COMPUTED").upper()

        parts = []
        if exit_target:
            parts.append(f"TARGET {exit_target:.2f}")
        if exit_stop:
            parts.append(f"STOP {exit_stop:.2f}")
        if exit_theta_date:
            parts.append(f"THETA_EXIT {exit_theta_date}")
        if exit_max_dte:
            parts.append(f"MAX_DTE -{exit_max_dte}d")
        if move_pays == "DOES_NOT_PAY_AT_ANTICIPATED_TIME":
            parts.append("MOVE_DOES_NOT_PAY_REVIEW")

        return {
            "exit_target_price": exit_target,
            "exit_stop_price":   exit_stop,
            "exit_theta_date":   exit_theta_date,
            "exit_max_dte":      exit_max_dte,
            "exit_rr_valid":     None,          # legacy stop-based R:R, retired (audit only)
            "exit_move_pays":    move_pays,
            "exit_rule_summary": (
                LifecycleEvaluationState.NOT_EVALUATED_NON_DIRECTIONAL.value
                if direction not in {"CALL", "PUT"}
                else " | ".join(parts) if parts else "MANUAL_REVIEW"
            ),
        }
    except Exception:
        return {
            "exit_target_price": None,
            "exit_stop_price":   None,
            "exit_theta_date":   None,
            "exit_max_dte":      None,
            "exit_rr_valid":     None,
            "exit_move_pays":    None,
            "exit_rule_summary": "ERROR",
        }


def enrich_dataframe(df: "pd.DataFrame") -> "pd.DataFrame":
    import pandas as pd
    rows = [compute_exit_rules(r) for r in df.to_dict("records")]
    exit_df = pd.DataFrame(rows, index=df.index)
    for col in exit_df.columns:
        df[col] = exit_df[col]
    return df
