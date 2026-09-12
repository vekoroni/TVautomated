"""
AVSHUNTER Morning Gate v1.3
============================
Fail-closed morning validation. Replaces morning_thesis_validator.py entirely.

CHECK 0: Upstream authority      - only EOD_CANDIDATE_ONLY may proceed
CHECK 1: Monetisability          - exact-contract target clears breakeven
CHECK 2: EV3 evidence            - advisory diagnostics only
CHECK 3: Invalidation intact     - live price has not broken the thesis
CHECK 4: Macro context           - compare regime and publish rotation context
CHECK 5: Contract liquid         - valid live quote and governed structure
CHECK 6: Bond macro context      - bond state remains advisory/review
CHECK 7: Layer 3 model risk      - model-risk flags require review

Morning GO means MORNING_VALIDATED only. Human approval and an approved size
remain mandatory; this module never writes LIVE_AUTHORIZED.

All other context (VWAP, ORB, delta, IV rank, crowd arrival, horizon,
Fung-Hsieh, direction arbitration) is written as display fields only.
They NEVER gate the verdict.

Output: morning_validated_trades_{run_id}.csv
Columns: ticker, direction, verdict, block_reason, flag_reason,
         live_price, invalidation_price, contract_symbol,
         live_bid, live_ask, live_spread_pct, macro_regime_eod,
         macro_regime_now, regime_changed, size_modifier,
         [all EOD fields preserved, including v6 actuarial fields:
          iv_regime, horizon_bucket, crabel_state â€” display only, never gates]

Usage:
    python morning_gate.py
    python morning_gate.py --run-id 20260526_094003
    python morning_gate.py --run-id 20260526_094003 --spread-threshold 20
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from contracts.direction_governance import (
    DIRECTED as GOVERNED_DIRECTED_SIDES,
    resolve_governed_direction,
    validate_direction_record,
)

from contracts.selected_contract_economics import (
    contract_symbols as selected_contract_symbols_from_value,
    economics_evaluation_id as selected_economics_evaluation_id,
    evaluate_long_option_monetisability,
    hydrate_selected_structure,
    parse_occ_symbol,
    recompute_premium_rr,
)
from contracts.long_option_policy import (
    LONG_OPTION_EXECUTION_POLICY,
    evaluate_execution_viability,
    quote_age_seconds,
    quote_spread_percent,
)
from contracts.core_authority_policy import assert_frozen_thesis_fields
from contracts.options_liquidity_lifecycle import (
    LifecycleInputs,
    evaluate_options_liquidity_lifecycle,
)
from contracts.governed_states import GovernedDataState, LifecycleEvaluationState
from msi_runtime import active_flags as active_msi_flags

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MORNING_GATE] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("morning_gate")

ROOT         = Path(__file__).resolve().parent
RUNS_DIR     = ROOT / "data" / "output" / "runs"
MACRO_DIR    = ROOT / "dropbox" / "macro"
MACRO_PATH   = MACRO_DIR / "macro_intelligence_latest.json"
BOND_MACRO_PATH        = MACRO_DIR / "bond_macro_state.json"
BOND_MACRO_MAX_AGE_H   = 26  # hours â€” covers overnight gap to 09:45 ET
MACRO_MAX_AGE_H        = 14  # hours â€” macro JSON older than this is flagged STALE (display only)
ENRICHMENT_DELTA_PATH  = MACRO_DIR / "avshunter_macro_enrichment_delta.json"
CHINA_EXPOSURE_PATH    = MACRO_DIR / "china_revenue_exposure.json"

# AG-04 GARCH vol regime transition constants
_VIX_REGIME_THRESHOLD_PCT  = 10.0  # VIX move > 10% triggers transition flag
_GARCH_TRANSITION_DISCOUNT = 0.75  # multiplier applied to l3_vol_forecast_conf display field

# AG-03 Options skew constants
_SKEW_EXPIRY_WINDOW_DAYS = 30   # days forward to target expiry for skew chain fetch
_SKEW_CALL_HIGH          = 1.10  # call_iv / put_iv above this = CALL_SKEW_HIGH
_SKEW_PUT_HIGH           = 0.90  # call_iv / put_iv below this = PUT_SKEW_HIGH

POLYGON_API_KEY    = os.getenv("POLYGON_API_KEY", "").strip()
MARKETDATA_API_KEY = os.getenv("MARKETDATA_API_KEY", "").strip()

# Backward-compatible argument default. All spread decisions are resolved
# through LONG_OPTION_EXECUTION_POLICY; callers cannot relax the governed hard
# maximum by passing a larger legacy --spread-threshold value.
DEFAULT_SPREAD_THRESHOLD = LONG_OPTION_EXECUTION_POLICY["reviewable_spread_max_pct"]
LIVE_FETCH_WORKERS       = 8     # increased for AG-03 skew fetch (2 extra calls per ticker)
LIVE_FETCH_TIMEOUT       = 10.0  # seconds per ticker
EV3_BARRIER_CACHE_PATH   = Path(os.getenv(
    "EV3_BARRIER_CACHE_PATH",
    r"C:\Users\ACKVerissimo\vanguard\data\ev3_barrier_outcome_cache.parquet",
))
_EV3_BARRIER_CACHE: Any = None
_EV3_BARRIER_CACHE_ERROR = ""

# Layer 3 model-risk capital guardrails. These never break the thesis; they
# convert otherwise-valid trades into FLAG / MODEL_RISK_REVIEW.
MODEL_RISK_VOL_HARDCAP     = 2.50
MODEL_RISK_LOW_CONF        = 65.0
MODEL_RISK_HIGH_VOL        = 1.50
MODEL_RISK_THIN_BARS       = 100
MODEL_RISK_TAILWIND_CAP    = 1.50

# ---------------------------------------------------------------------------
# v6 actuarial schema display fields â€” pass-through only, never gate logic
# ---------------------------------------------------------------------------
V6_ACTUARIAL_DISPLAY_FIELDS = [
    "iv_regime",       # Volatility regime from v6 actuarial schema
    "horizon_bucket",  # Forward horizon segment: 1_5d / 6_10d / 11_20d
    "crabel_state",    # Short-horizon mean reversion state
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def configure_cds_runtime_for_morning_gate(
    environment: Optional[Dict[str, str]] = None,
    base_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Apply the production CDS defaults required by the direct Morning CLI.

    The orchestrator already applies these defaults before importing
    ``run_morning_gate``.  ``morning_gate.py`` is also an advertised production
    entrypoint, so it must establish the same canonical-store contract when it
    is launched directly.  ``setdefault`` preserves explicit rollback or test
    overrides.
    """
    env = os.environ if environment is None else environment
    root = Path(base_dir) if base_dir is not None else ROOT
    env.setdefault("AVSHUNTER_CANONICAL_DATA_ENABLED", "1")
    env.setdefault("AVSHUNTER_CANONICAL_WRITE_THROUGH", "1")
    env.setdefault("AVSHUNTER_CDS2_OHLCV_MODE", "ACTIVE")
    env.setdefault("AVSHUNTER_STAGE_GATING_ENFORCED", "1")
    env.setdefault(
        "AVSHUNTER_HISTORICAL_PRICE_DB",
        str(root / "data" / "canonical" / "historical_prices.sqlite"),
    )

    from canonical_data.feature_flags import CanonicalFeatureFlags

    flags = CanonicalFeatureFlags.from_environment(env)
    return {
        "enabled": flags.enabled,
        "write_through": flags.write_through,
        "ohlcv_mode": flags.ohlcv_mode,
        "stage_gating_enforced": flags.stage_gating_enforced,
        "database_path": env["AVSHUNTER_HISTORICAL_PRICE_DB"],
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc_datetime(value: Any) -> Optional[datetime]:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _f(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        v = float(str(value).replace("$", "").replace("%", "").replace(",", "").strip())
        return default if v != v else v  # NaN check
    except Exception:
        return default


def _s(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s.upper() in {"NAN", "NONE", "NULL", "N/A", ""} else s


def _u(value: Any) -> str:
    return _s(value).upper()


def _truthy(value: Any) -> bool:
    return _u(value) in {"1", "TRUE", "YES", "Y", "ON"}


def _ensure_governed_direction_record(row: Dict[str, Any]) -> Dict[str, Any]:
    """Materialise the GDR or an explicit-side migration adapter.

    Production EOD rows carry a complete record. The adapter exists only for
    older archived fixtures and never defaults an absent direction.
    """
    out = dict(row)
    if not _s(out.get("dir_calc_version")):
        explicit = _u(
            out.get("options_direction")
            or out.get("canonical_direction")
            or out.get("resolved_direction")
            or out.get("direction")
        )
        if explicit not in GOVERNED_DIRECTED_SIDES:
            explicit = "UNRESOLVED"
        out.update(resolve_governed_direction(
            ticker=out.get("ticker"),
            run_id=out.get("run_id"),
            discovery_direction=out.get("discovery_direction_preliminary"),
            governed_direction=explicit,
            governed_basis="MORNING_LEGACY_EXPLICIT_SIDE_ADAPTER",
            row=out,
        ))
    final_direction = _u(out.get("final_direction"))
    if final_direction:
        for field in ("direction", "canonical_direction", "resolved_direction", "primary_direction"):
            out[field] = final_direction
    return out


def _check_direction_integrity(row: Dict[str, Any]) -> tuple[bool, str]:
    return validate_direction_record(row)


def _check_upstream_authority(row: Dict[str, Any]) -> tuple[bool, str]:
    """Only a governed EOD candidate may be unlocked by morning validation."""
    source_stage = _u(row.get("authority_source_stage"))
    if source_stage != "FINAL_EXECUTION":
        return False, f"UNSAFE_AUTHORITY_SOURCE:{source_stage or 'MISSING'}"
    route = _u(row.get("final_route"))
    if route in {"OPTIONS_BLOCKED", "OPTIONS_EQUITY_ONLY_BETTER"}:
        return False, f"UPSTREAM_OPTIONS_ROUTE_BLOCKED:{route}"

    authority_state = _u(row.get("capital_authorization_state"))
    capital_permission = _u(
        row.get("capital_permission") or row.get("live_capital_permission")
    )
    eod_authorized = _truthy(row.get("eod_candidate_authorized"))
    if authority_state != "EOD_CANDIDATE_ONLY":
        return False, f"UPSTREAM_NOT_AUTHORIZED:{authority_state or 'MISSING'}"
    if capital_permission != "EOD_CANDIDATE_ONLY":
        return False, f"UPSTREAM_CAPITAL_PERMISSION:{capital_permission or 'MISSING'}"
    if not eod_authorized:
        return False, "UPSTREAM_EOD_CANDIDATE_AUTHORIZATION_FALSE"
    return True, "Governed EOD candidate awaiting live validation"


def _check_monetisability(row: Dict[str, Any]) -> tuple[bool, str]:
    """Use the exact selected contract's conservative target-profit state."""
    state = _u(row.get("monetisability_state"))
    reason = _s(row.get("monetisability_reason")) or "UNSPECIFIED"
    if state == "MONETISABLE":
        return True, f"MONETISABLE:{reason}"
    if state == "LIMITED":
        return True, f"LIMITED_MONETISABILITY:{reason}"
    if state == "NOT_MONETISABLE":
        return False, f"NOT_MONETISABLE:{reason}"
    return False, f"MONETISABILITY_DATA_MISSING:{state or 'MISSING'}:{reason}"


def _check_premium_economics(row: Dict[str, Any]) -> tuple[bool, str]:
    """Check observable execution viability; EV/R:R/scenario value are advisory."""
    state = _u(row.get("execution_viability_state"))
    reason = _s(row.get("execution_viability_reason")) or "UNSPECIFIED"
    if state == "EXECUTABLE_QUOTE":
        return True, f"EXECUTION_VIABLE:{reason}"
    if state == "MANUAL_LIQUIDITY_REVIEW":
        return True, f"EXECUTION_REVIEW_REQUIRED:{reason}"
    return False, f"EXECUTION_NOT_VIABLE:{state or 'MISSING'}:{reason}"


def _check_ev3_authority(row: Dict[str, Any]) -> tuple[bool, str]:
    """Publish EV3 evidence as advisory context with no capital effect."""
    state = _u(row.get("ev3_authority_state"))
    return True, f"EV3_ADVISORY_ONLY:{state or 'NOT_EVALUATED'}"


def _layer3_model_risk_guard(row: Dict[str, Any]) -> Dict[str, Any]:
    """Return Layer 3 model-risk diagnostics for Morning Gate."""
    flags = []
    existing = _s(row.get("l3_model_risk_flags"))
    if existing:
        for part in re.split(r"[|,;]", existing):
            flag = part.strip().upper()
            if flag and flag not in flags:
                flags.append(flag)

    vol = _f(row.get("l3_forward_realised_vol"))
    conf = _f(row.get("l3_vol_forecast_conf"))
    n_bars = _f(row.get("l3_n_bars"))
    tailwind = _f(row.get("l3_iv_tailwind_score"))

    def add(flag: str) -> None:
        if flag not in flags:
            flags.append(flag)

    if vol is not None and vol >= MODEL_RISK_VOL_HARDCAP:
        add("VOL_HARDCAP")
    if (
        conf is not None
        and vol is not None
        and conf <= MODEL_RISK_LOW_CONF
        and vol >= MODEL_RISK_HIGH_VOL
    ):
        add("LOW_CONF_HIGH_VOL")
    if n_bars is not None and n_bars < MODEL_RISK_THIN_BARS:
        add("THIN_HISTORY")
    if tailwind is not None and abs(tailwind) > MODEL_RISK_TAILWIND_CAP:
        add("IV_TAILWIND_EXTREME")

    capped_tailwind = ""
    if tailwind is not None:
        capped_tailwind = max(-MODEL_RISK_TAILWIND_CAP, min(MODEL_RISK_TAILWIND_CAP, tailwind))

    details = []
    if vol is not None:
        details.append(f"vol={vol:.4f}")
    if conf is not None:
        details.append(f"conf={conf:.1f}")
    if n_bars is not None:
        details.append(f"n_bars={int(n_bars)}")
    if tailwind is not None:
        details.append(f"iv_tailwind={tailwind:.4f}")

    flag_text = "|".join(flags)
    reason = "Layer 3 model risk clear"
    if flags:
        reason = "Layer 3 model risk guard - " + flag_text
        if details:
            reason += " (" + ", ".join(details) + ")"

    return {
        "passed": not flags,
        "flags": flags,
        "flag_text": flag_text,
        "reason": reason,
        "capped_tailwind": capped_tailwind,
    }


def _side(value: Any) -> str:
    text = _u(value)
    if text in {"CALL", "PUT"}:
        return text
    if "LONG_CALL" in text or " CALL" in text or text.endswith("CALL"):
        return "CALL"
    if "LONG_PUT" in text or " PUT" in text or text.endswith("PUT"):
        return "PUT"
    return ""


def _contract_side_from_row(row: Dict[str, Any]) -> str:
    selected = _side(row.get("selected_contract_side"))
    if selected:
        return selected
    for key in ("contract_symbol", "recommended_contract", "preferred_contract", "contract_occ_symbol"):
        text = _u(row.get(key))
        if "P0" in text:
            return "PUT"
        if "C0" in text:
            return "CALL"
    delta = _f(row.get("live_contract_delta") or row.get("contract_delta"))
    if delta is not None and delta < 0:
        return "PUT"
    if delta is not None and delta > 0:
        return "CALL"
    return ""


def _append_reason(existing: Any, addition: str) -> str:
    current = _s(existing)
    if not current:
        return addition
    if addition in current:
        return current
    return current + "; " + addition


def _apply_thesis_direction_guard(row: Dict[str, Any]) -> Dict[str, Any]:
    """Preserve locked footprint direction before active Morning Gate checks."""
    out = dict(row)
    # Governed rows are already decided. Morning records the lock; it never
    # restores a Discovery footprint or performs a new direction vote.
    if _s(out.get("dir_calc_version")):
        final_direction = _u(out.get("final_direction"))
        if final_direction:
            for key in ("direction", "canonical_direction", "resolved_direction", "primary_direction"):
                out[key] = final_direction
        out["footprint_lock_status"] = "DECOMMISSIONED_GDR_AUTHORITY"
        out["footprint_lock_reason"] = "Morning lock records the GDR final direction only"
        out["morning_direction_lock_status"] = (
            "LOCKED_GDR_FINAL" if final_direction in GOVERNED_DIRECTED_SIDES
            else "BLOCKED_GDR_NON_DIRECTIONAL"
        )
        return out
    footprint = _side(out.get("footprint_direction"))
    if footprint not in {"CALL", "PUT"}:
        return out

    current = _side(
        out.get("evening_direction")
        or out.get("canonical_direction")
        or out.get("resolved_direction")
        or out.get("direction")
    )
    lock_status = _u(out.get("footprint_lock_status"))
    reroute = _u(out.get("direction_reroute_status"))
    locked = lock_status.startswith("LOCKED") or reroute == "MAJOR_CATALYST_DIRECTION_OVERRIDE"
    if not locked:
        return out

    if current and current != footprint:
        for key in ("direction", "canonical_direction", "resolved_direction", "primary_direction", "evening_direction"):
            if key in out:
                out[key] = footprint
        catalyst = _side(out.get("catalyst_direction_bias") or out.get("catalyst_trade_bias"))
        reason = (
            f"Catalyst side {catalyst or 'UNKNOWN'} conflicts with thesis side {footprint}; "
            "thesis preserved, require live confirmation"
        )
        out["direction_reroute_status"] = "CATALYST_CONFLICT_THESIS_PRESERVED"
        out["footprint_lock_status"] = "LOCKED_UNTIL_LIVE_INVALIDATION"
        out["catalyst_direction_conflict_status"] = "CATALYST_CONFLICT_REQUIRES_CONFIRMATION"
        out["catalyst_direction_conflict_reason"] = reason
        out["direction_conflict_status"] = "MITIGATED_REQUIRES_CONFIRMATION"
        out["direction_conflict_gate"] = "VWAP_CONFIRMATION_REQUIRED"
        out["direction_conflict_reason"] = _append_reason(out.get("direction_conflict_reason"), reason)
        out["direction_decision_reason"] = _append_reason(
            out.get("direction_decision_reason"),
            f"GUARD:morning_gate_restored_locked_footprint_{footprint}_from_{current}",
        )
        summary = _s(out.get("thesis_summary"))
        pieces = summary.split(" ", 1)
        if len(pieces) == 2 and pieces[0].upper() in {"CALL", "PUT"}:
            out["thesis_summary"] = footprint + " " + pieces[1]

    contract_side = _contract_side_from_row(out)
    if contract_side and contract_side != footprint:
        out["morning_direction_guard_contract_side_conflict"] = "TRUE"
        out["contract_repair_required"] = "TRUE"
        out["contract_repair_reason"] = _append_reason(out.get("contract_repair_reason"), "SIDE_REPAIR_NEEDED")
    else:
        out["morning_direction_guard_contract_side_conflict"] = "FALSE"

    return out


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        log.warning("No rows to write.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    for row in rows:
        for k in row:
            if k not in fields:
                fields.append(k)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _normalise_score_integrity(
    run_dir: Path,
    run_id: str,
    report: Dict[str, Any],
) -> Dict[str, Any]:
    """Zero comparisons are not evidence of integrity."""
    normalised = dict(report or {})
    compared = int(normalised.get("compared", 0) or 0)
    integrity_source = _u(
        normalised.get("integrity_source") or normalised.get("lab_source")
    )
    if compared <= 0 or integrity_source in {"", "NOT_FOUND"}:
        normalised.update(
            integrity_pass=False,
            integrity_status="NOT_EVALUATED",
            integrity_reason="INTEGRITY_SOURCE_MISSING_OR_ZERO_ROWS_COMPARED",
        )
    else:
        normalised["integrity_status"] = (
            "PASS" if bool(normalised.get("integrity_pass")) else "FAIL"
        )
    _write_json(run_dir / f"score_integrity_{run_id}.json", normalised)
    return normalised


def _score_integrity_value(row: Dict[str, Any]) -> Optional[float]:
    """Read the governed candidate score without substituting another metric."""
    for field in ("scs_score", "composite", "score"):
        value = _f(row.get(field))
        if value is not None:
            return value
    return None


def _check_morning_handoff_score_integrity(
    run_id: str,
    input_rows: List[Dict[str, Any]],
    output_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compare candidate scores before and after Morning Gate materialisation.

    The Intelligence Lab is materialised after Morning Gate, so a Lab comparison
    cannot truthfully run inside this process. This check covers the completed
    Morning handoff now and records the downstream comparison as pending.
    """
    input_scores = {
        _u(row.get("ticker")): score
        for row in input_rows
        if _u(row.get("ticker"))
        for score in [_score_integrity_value(row)]
        if score is not None
    }
    output_scores = {
        _u(row.get("ticker")): score
        for row in output_rows
        if _u(row.get("ticker"))
        for score in [_score_integrity_value(row)]
        if score is not None
    }
    common = sorted(set(input_scores) & set(output_scores))
    missing_from_output = sorted(set(input_scores) - set(output_scores))
    unexpected_in_output = sorted(set(output_scores) - set(input_scores))
    mismatches = []
    for ticker in common:
        delta = abs(input_scores[ticker] - output_scores[ticker])
        if delta > 0.01:
            mismatches.append({
                "ticker": ticker,
                "input_score": round(input_scores[ticker], 4),
                "output_score": round(output_scores[ticker], 4),
                "delta": round(delta, 4),
            })
    compared = len(common)
    mismatch_rate = len(mismatches) / compared if compared else 0.0
    coverage_complete = (
        compared > 0
        and not missing_from_output
        and not unexpected_in_output
        and len(input_scores) == len(output_scores) == compared
    )
    return {
        "run_id": run_id,
        "checked_at_utc": _utc_now(),
        "integrity_scope": "MORNING_CANDIDATES_TO_VALIDATED_HANDOFF",
        "integrity_source": "morning_candidates_vs_morning_validated_trades",
        "input_tickers": len(input_scores),
        "output_tickers": len(output_scores),
        "compared": compared,
        "coverage_complete": coverage_complete,
        "missing_from_output": missing_from_output[:20],
        "unexpected_in_output": unexpected_in_output[:20],
        "mismatches": len(mismatches),
        "mismatch_rate": round(mismatch_rate, 4),
        "integrity_pass": coverage_complete and not mismatches,
        "mismatch_detail": mismatches[:20],
        "lab_score_integrity_status": "PENDING_POST_LAB_MATERIALISATION",
        "lab_score_integrity_reason": (
            "Intelligence Lab output is produced after Morning Gate; compare "
            "the governed Lab book in the post-Lab phase."
        ),
    }


def _check_post_lab_score_integrity(
    run_id: str,
    morning_rows: List[Dict[str, Any]],
    lab_path: Path,
) -> Dict[str, Any]:
    """Compare the preserved SCS score after governed Lab materialisation.

    ``composite_score`` in the Lab is a separate model output and is therefore
    never substituted for ``scs_score``. The latter is preserved inside the
    governed source payload until it becomes a first-class Lab column.
    """
    morning_scores = {
        _u(row.get("ticker")): score
        for row in morning_rows
        if _u(row.get("ticker"))
        for score in [_score_integrity_value(row)]
        if score is not None
    }
    if not lab_path.is_file():
        return {
            "run_id": run_id,
            "checked_at_utc": _utc_now(),
            "integrity_scope": "MORNING_VALIDATED_TO_INTELLIGENCE_LAB",
            "integrity_source": "NOT_FOUND",
            "lab_source": "NOT_FOUND",
            "morning_tickers": len(morning_scores),
            "lab_tickers": 0,
            "compared": 0,
            "mismatches": 0,
            "mismatch_rate": 0.0,
            "integrity_pass": False,
            "lab_score_integrity_status": "NOT_EVALUATED",
            "integrity_reason": f"LAB_BOOK_NOT_FOUND:{lab_path}",
        }

    lab_scores: Dict[str, float] = {}
    payload_errors: List[str] = []
    for row in _read_csv(lab_path):
        ticker = _u(row.get("ticker"))
        if not ticker:
            continue
        score = _score_integrity_value(row)
        if score is None:
            raw_payload = _s(row.get("source_payload_json"))
            if raw_payload:
                try:
                    payload = json.loads(raw_payload)
                    if isinstance(payload, dict):
                        score = _score_integrity_value(payload)
                except (TypeError, ValueError, json.JSONDecodeError):
                    payload_errors.append(ticker)
        if score is not None:
            lab_scores[ticker] = score

    common = sorted(set(morning_scores) & set(lab_scores))
    missing_from_lab = sorted(set(morning_scores) - set(lab_scores))
    unexpected_in_lab = sorted(set(lab_scores) - set(morning_scores))
    mismatches = []
    for ticker in common:
        delta = abs(morning_scores[ticker] - lab_scores[ticker])
        if delta > 0.01:
            mismatches.append({
                "ticker": ticker,
                "morning_score": round(morning_scores[ticker], 4),
                "lab_score": round(lab_scores[ticker], 4),
                "delta": round(delta, 4),
            })
    compared = len(common)
    mismatch_rate = len(mismatches) / compared if compared else 0.0
    coverage_complete = (
        compared > 0
        and not missing_from_lab
        and not unexpected_in_lab
        and not payload_errors
        and len(morning_scores) == len(lab_scores) == compared
    )
    integrity_pass = coverage_complete and not mismatches
    return {
        "run_id": run_id,
        "checked_at_utc": _utc_now(),
        "integrity_scope": "MORNING_VALIDATED_TO_INTELLIGENCE_LAB",
        "integrity_source": str(lab_path),
        "lab_source": lab_path.name,
        "score_field": "scs_score",
        "morning_tickers": len(morning_scores),
        "lab_tickers": len(lab_scores),
        "compared": compared,
        "coverage_complete": coverage_complete,
        "missing_from_lab": missing_from_lab[:20],
        "unexpected_in_lab": unexpected_in_lab[:20],
        "payload_parse_errors": payload_errors[:20],
        "mismatches": len(mismatches),
        "mismatch_rate": round(mismatch_rate, 4),
        "integrity_pass": integrity_pass,
        "lab_score_integrity_status": "PASS" if integrity_pass else "FAIL",
        "mismatch_detail": mismatches[:20],
    }


def _close_final_run_manifest(
    run_dir: Path,
    run_id: str,
    summary: Dict[str, Any],
    integrity: Dict[str, Any],
) -> None:
    """Close the EOD manifest after morning validation without granting capital."""
    manifest_path = run_dir / "final_run_manifest.json"
    manifest: Dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            log.warning("Final manifest unreadable; rebuilding morning closure: %s", exc)

    phase_status = dict(manifest.get("phase_status", {}) or {})
    phase_status["morning_validation"] = "PASS"
    output_files = dict(manifest.get("output_files", {}) or {})
    output_files["morning_validation"] = str(
        run_dir / "morning_validation" / f"morning_validated_trades_{run_id}.csv"
    )
    output_files["morning_validation_packet"] = str(
        run_dir / "morning_validation" / f"morning_gate_summary_{run_id}.json"
    )
    row_counts = dict(manifest.get("row_counts", {}) or {})
    row_counts["morning_validation"] = int(summary.get("input_candidates", 0) or 0)
    stale_flags = [
        flag for flag in list(manifest.get("stale_flags", []) or [])
        if flag not in {
            "EOD_MORNING_VALIDATION_PENDING",
            "SCORE_INTEGRITY_NOT_EVALUATED",
        }
    ]
    if integrity.get("integrity_status") != "PASS":
        stale_flags.append("SCORE_INTEGRITY_NOT_EVALUATED")

    validated = int(summary.get("go_count", 0) or 0)
    manifest.update(
        run_id=run_id,
        phase_status=phase_status,
        output_files=output_files,
        row_counts=row_counts,
        morning_validation_completed_at_utc=summary.get("validated_at_utc"),
        morning_validated_count=validated,
        morning_flag_count=int(summary.get("flag_count", 0) or 0),
        morning_block_count=int(summary.get("block_count", 0) or 0),
        morning_capital_permission=(
            "HUMAN_APPROVAL_REQUIRED" if validated else "NO"
        ),
        run_execution_permission=(
            "HUMAN_APPROVAL_REQUIRED" if validated else "NO"
        ),
        run_tradeable=False,
        run_tradeable_label=(
            "MORNING_VALIDATED_HUMAN_APPROVAL_REQUIRED"
            if validated else "NO_MORNING_VALIDATED_TRADES"
        ),
        next_action=(
            "HUMAN_REVIEW_AND_SIZE" if validated else "NO_TRADE"
        ),
        score_integrity_status=integrity.get("integrity_status", "NOT_EVALUATED"),
        score_integrity_scope=integrity.get("integrity_scope", ""),
        score_integrity_compared=int(integrity.get("compared", 0) or 0),
        lab_score_integrity_status=integrity.get(
            "lab_score_integrity_status", "NOT_EVALUATED"
        ),
        stale_flags=list(dict.fromkeys(stale_flags)),
    )
    _write_json(manifest_path, manifest)


def _latest_run_id() -> Optional[str]:
    latest = ROOT / "data" / "output" / "latest.json"
    if latest.exists():
        try:
            data = json.loads(latest.read_text(encoding="utf-8-sig"))
            rid = data.get("run_id") or data.get("latest_run_id")
            if rid:
                return str(rid).strip()
        except Exception:
            pass
    if RUNS_DIR.exists():
        dirs = sorted(p.name for p in RUNS_DIR.iterdir() if p.is_dir())
        return dirs[-1] if dirs else None
    return None


# ---------------------------------------------------------------------------
# Live data fetch â€” equity price only (Polygon)
# ---------------------------------------------------------------------------

def _fetch_live_price(ticker: str) -> Dict[str, Any]:
    """Fetch live equity snapshot from Polygon. Returns dict with live_price etc."""
    import urllib.request
    url = (
        f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/"
        f"{ticker}?apiKey={POLYGON_API_KEY}"
    )
    try:
        with urllib.request.urlopen(url, timeout=LIVE_FETCH_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        ticker_data = data.get("ticker", {})
        day  = ticker_data.get("day", {})
        prev = ticker_data.get("prevDay", {})
        last_quote = ticker_data.get("lastQuote", {}) or {}
        return {
            "live_price":      _f(ticker_data.get("lastTrade", {}).get("p"))
                               or _f(day.get("c")),
            "live_open":       _f(day.get("o")),
            "live_high":       _f(day.get("h")),
            "live_low":        _f(day.get("l")),
            "live_prev_close": _f(prev.get("c")),
            "live_volume":     _f(day.get("v")),
            "live_vwap":       _f(day.get("vw")),
            "underlying_bid":  _f(last_quote.get("p")),
            "underlying_ask":  _f(last_quote.get("P")),
            "underlying_bid_size": _f(last_quote.get("s")),
            "underlying_ask_size": _f(last_quote.get("S")),
            "underlying_quote_updated": _normalise_provider_timestamp(last_quote.get("t")),
            "live_data_source": "POLYGON_SNAPSHOT",
            "live_fetched_at": _utc_now(),
            # AG-01: earnings announcement date from snapshot (no extra API call)
            "live_earnings_announcement": _s(ticker_data.get("earningsAnnouncement", "")),
        }
    except Exception as exc:
        return {"live_fetch_error": str(exc), "live_data_source": "POLYGON_FAILED"}


def _fetch_live_contract(occ_symbol: str) -> Dict[str, Any]:
    """Fetch live options quote from MarketData.app."""
    import urllib.request
    encoded = occ_symbol.replace(" ", "%20")
    url = (
        f"https://api.marketdata.app/v1/options/quotes/{encoded}/"
        f"?token={MARKETDATA_API_KEY}"
    )
    try:
        with urllib.request.urlopen(url, timeout=LIVE_FETCH_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        if data.get("s") == "ok" and data.get("bid"):
            def api_value(*names: str) -> Any:
                for name in names:
                    value = data.get(name)
                    if isinstance(value, list):
                        value = value[0] if value else None
                    if value is not None:
                        return value
                return None

            bid = _f(api_value("bid"))
            ask = _f(api_value("ask"))
            mid = (bid + ask) / 2.0 if bid is not None and ask is not None else None
            spread_pct = quote_spread_percent(bid, ask)
            return {
                "live_contract_bid":        bid,
                "live_contract_ask":        ask,
                "live_contract_mid":        mid,
                "live_contract_spread_pct": round(spread_pct, 2) if spread_pct is not None else None,
                "live_contract_bid_size":   _f(api_value("bidSize")),
                "live_contract_ask_size":   _f(api_value("askSize")),
                "live_contract_iv":         _f(api_value("iv", "impliedVolatility")),
                "live_contract_delta":      _f(api_value("delta")),
                "live_contract_gamma":      _f(api_value("gamma")),
                "live_contract_theta":      _f(api_value("theta")),
                "live_contract_vega":       _f(api_value("vega")),
                "live_contract_oi":         _f(api_value("openInterest", "open_interest")),
                "live_contract_volume":     _f(api_value("volume")),
                "live_contract_multiplier": _f(api_value("contractMultiplier", "multiplier")),
                "live_contract_provider_updated": _normalise_provider_timestamp(
                    api_value("updated", "quoteTimestamp", "timestamp")
                ),
                "live_options_source":      "MARKETDATA",
                "live_options_fetched_at":  _utc_now(),
            }
        return {"live_options_source": "MARKETDATA_NO_QUOTE"}
    except Exception as exc:
        return {"live_options_source": "MARKETDATA_FAILED", "live_options_error": str(exc)}


def _normalise_provider_timestamp(value: Any) -> Optional[str]:
    """Return an observed provider instant; never substitute acquisition time."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).strip().isdigit():
            numeric = float(value)
            while numeric > 10_000_000_000:
                numeric /= 1000.0
            parsed = datetime.fromtimestamp(numeric, tz=timezone.utc)
        else:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return None
            parsed = parsed.astimezone(timezone.utc)
        return parsed.isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _capture_msi_market_observations(
    row: Dict[str, Any],
    live: Dict[str, Any],
    resolver: Any,
    session_date: date,
) -> None:
    """Persist the already-fetched Morning evidence through CDS v2.

    The callbacks below do not perform another network request; they expose the
    licensed responses already obtained by Morning Gate to the canonical
    resolver.  This prevents duplicate calls while retaining one immutable
    dataset identity for Lab and Interpreter lineage.
    """

    ticker = _u(row.get("ticker"))
    contract = _s(
        live.get("selected_contract_symbol")
        or live.get("live_contract_symbol")
        or row.get("contract_symbol")
        or row.get("evening_contract_symbol")
    )
    bid = _f(live.get("live_contract_bid"))
    ask = _f(live.get("live_contract_ask"))
    option_provider_timestamp = _normalise_provider_timestamp(
        live.get("live_contract_provider_updated")
    )
    live["quote_provider_timestamp_utc"] = option_provider_timestamp or ""
    live["quote_fetch_timestamp_utc"] = _s(live.get("live_options_fetched_at"))
    if contract and bid is not None and ask is not None and option_provider_timestamp:
        raw_quote = {
            "s": "ok",
            "optionSymbol": [contract],
            "bid": [bid],
            "ask": [ask],
            "mid": [live.get("live_contract_mid")],
            "bidSize": [live.get("live_contract_bid_size")],
            "askSize": [live.get("live_contract_ask_size")],
            "openInterest": [live.get("live_contract_oi")],
            "volume": [live.get("live_contract_volume")],
            "iv": [live.get("live_contract_iv")],
            "delta": [live.get("live_contract_delta")],
            "gamma": [live.get("live_contract_gamma")],
            "theta": [live.get("live_contract_theta")],
            "vega": [live.get("live_contract_vega")],
            "contractMultiplier": [live.get("live_contract_multiplier")],
            "updated": [option_provider_timestamp],
        }
        observation = resolver.exact_option_quote(
            ticker=ticker,
            symbol=contract,
            session_date=session_date,
            freshness_seconds=60,
            fetch=lambda _ticker, _symbol: raw_quote,
            thesis_id=_s(row.get("thesis_id")),
            trade_idea_id=_s(row.get("trade_idea_id")),
            selected_structure_id=_s(row.get("selected_structure_id")),
            provider="MARKETDATA",
        )
        live["msi_exact_quote_dataset_id"] = observation.dataset_id
        live["quote_source_dataset_id"] = observation.dataset_id
        live["msi_exact_quote_resolution"] = observation.resolution
        if isinstance(observation.payload, dict):
            quote = observation.payload
            live["live_contract_bid_size"] = quote.get("bid_size")
            live["live_contract_ask_size"] = quote.get("ask_size")
            live["contract_bid_size_quality"] = quote.get("bid_size_quality")
            live["contract_ask_size_quality"] = quote.get("ask_size_quality")
            live["contract_quote_quality"] = quote.get("quote_quality")
            live["contract_size_quality"] = (
                "OBSERVED" if quote.get("bid_size") is not None and quote.get("ask_size") is not None
                else "PARTIAL" if quote.get("bid_size") is not None or quote.get("ask_size") is not None
                else "MISSING"
            )
            quote_timestamp = quote.get("quote_timestamp_utc")
            for prefix in ("morning", "current"):
                live[f"{prefix}_contract_symbol"] = contract
                live[f"{prefix}_contract_bid"] = quote.get("bid")
                live[f"{prefix}_contract_ask"] = quote.get("ask")
                live[f"{prefix}_contract_mid"] = quote.get("mid")
                live[f"{prefix}_contract_spread_pct"] = quote.get("spread_fraction_mid")
                live[f"{prefix}_contract_bid_size"] = quote.get("bid_size")
                live[f"{prefix}_contract_ask_size"] = quote.get("ask_size")
                live[f"{prefix}_quote_dataset_id"] = observation.dataset_id
                live[f"{prefix}_quote_timestamp_utc"] = quote_timestamp
            quote_source = getattr(observation, "provider", None) or quote.get("quote_source") or "MARKETDATA"
            live["current_quote_source"] = quote_source
            live["morning_quote_source"] = quote_source
    elif contract and bid is not None and ask is not None:
        live["msi_exact_quote_resolution"] = "CONTRACT_QUOTE_UNAVAILABLE"
        live["contract_quote_quality"] = "MISSING_PROVIDER_TIMESTAMP"
        live["execution_viability_state"] = "CONTRACT_QUOTE_UNAVAILABLE"
        live["execution_viability_eligible"] = False

    underlying_bid = _f(live.get("underlying_bid"))
    underlying_ask = _f(live.get("underlying_ask"))
    underlying_provider_timestamp = _normalise_provider_timestamp(
        live.get("underlying_quote_updated")
    )
    if (
        underlying_bid is not None
        and underlying_ask is not None
        and underlying_bid >= 0
        and underlying_ask > 0
        and underlying_bid <= underlying_ask
        and underlying_provider_timestamp
    ):
        raw_underlying = {
            "bid": underlying_bid,
            "ask": underlying_ask,
            "bidSize": live.get("underlying_bid_size"),
            "askSize": live.get("underlying_ask_size"),
            "updated": underlying_provider_timestamp,
        }
        observation = resolver.underlying_nbbo(
            ticker=ticker,
            session_date=session_date,
            freshness_seconds=30,
            fetch=lambda _ticker: raw_underlying,
            provider="POLYGON",
        )
        live["msi_underlying_quote_dataset_id"] = observation.dataset_id
        live["msi_underlying_quote_resolution"] = observation.resolution
        if isinstance(observation.payload, dict):
            quote = observation.payload
            live["underlying_mid"] = quote.get("mid")
            live["underlying_depth_level"] = quote.get("depth_level")
            live["underlying_nbbo_bid"] = quote.get("bid")
            live["underlying_nbbo_ask"] = quote.get("ask")
            live["underlying_nbbo_mid"] = quote.get("mid")
            live["underlying_nbbo_bid_size"] = quote.get("bid_size")
            live["underlying_nbbo_ask_size"] = quote.get("ask_size")
            live["underlying_nbbo_timestamp_utc"] = quote.get("provider_updated_utc")
            live["underlying_nbbo_source"] = quote.get("source")
            live["underlying_nbbo_dataset_id"] = observation.dataset_id
            live["underlying_nbbo_quality"] = quote.get("depth_level")
    else:
        live["msi_underlying_quote_resolution"] = "PROVIDER_NBBO_NOT_AVAILABLE"


def _iter_repair_alternatives(row: Dict[str, Any], primary_contract: str = "") -> List[str]:
    """Return ordered EOD repair alternatives, de-duped against the primary contract."""
    seen = {_u(primary_contract)}
    out: List[str] = []
    for key in ("alternative_contract_1", "alternative_contract_2", "alternative_contract_3"):
        symbol = _s(row.get(key))
        if not symbol:
            continue
        symbol_key = _u(symbol)
        if symbol_key in seen:
            continue
        seen.add(symbol_key)
        out.append(symbol)
    return out


def _hydrate_live_structure(row: Dict[str, Any], selected: str) -> Dict[str, Any]:
    return hydrate_selected_structure(
        selected,
        _fetch_live_contract,
        ticker=row.get("ticker"),
        direction=(
            row.get("canonical_direction")
            or row.get("resolved_direction")
            or row.get("direction")
        ),
        instrument=row.get("instrument") or row.get("options_strategy"),
        fetched_at_utc=_utc_now(),
    )


def _try_live_repair_alternatives(
    row: Dict[str, Any],
    primary_contract: str,
    spread_threshold: float,
) -> Dict[str, Any]:
    """
    Test EOD-generated repair alternatives against live MarketData quotes.
    The first alternative that passes the same contract gate becomes the executable contract.
    """
    attempts: List[str] = []
    last_live: Dict[str, Any] = {}
    for alt_symbol in _iter_repair_alternatives(row, primary_contract):
        alt_live = _hydrate_live_structure(row, alt_symbol)
        last_live = dict(alt_live)
        alt_pass, alt_reason = _check_contract(alt_live, spread_threshold, row)
        attempts.append(f"{alt_symbol}:{'PASS' if alt_pass else 'FAIL'}:{alt_reason}")
        if alt_pass:
            selected_symbol = _s(alt_live.get("selected_contract_symbol")) or alt_symbol
            alt_live.update({
                "live_contract_symbol": selected_symbol,
                "morning_contract_repair_used": "TRUE",
                "morning_repaired_from_contract": primary_contract,
                "morning_repair_contract_symbol": selected_symbol,
                "morning_repair_reason": alt_reason,
                "morning_repair_attempts": " | ".join(attempts),
            })
            return alt_live
    if attempts:
        last_live.update({
            "morning_contract_repair_used": "FALSE",
            "morning_repaired_from_contract": primary_contract,
            "morning_repair_attempts": " | ".join(attempts),
        })
        return last_live
    return {}


def _fetch_all_live(
    candidates: List[Dict[str, Any]],
    spread_threshold: float = DEFAULT_SPREAD_THRESHOLD,
    liquidity_store: Any = None,
    liquidity_freshness_seconds: int = 60,
    msi_observation_resolver: Any = None,
    msi_session_date: Optional[date] = None,
    execution_mode: str = "POSTOPEN_CONTRACT_REFRESH",
) -> Dict[str, Dict[str, Any]]:
    """Fetch live equity/options data and try EOD repair alternatives when the primary contract fails."""
    results: Dict[str, Dict[str, Any]] = {}

    def fetch_one(row: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        ticker = _u(row.get("ticker", ""))
        live   = _fetch_live_price(ticker)
        live["morning_execution_mode"] = _u(execution_mode)
        time.sleep(0.1)
        preopen = _u(execution_mode) == "PREOPEN_THESIS_CHECK"
        occ = _s(
            row.get("evening_contract_symbol")
            or row.get("contract_symbol")
            or row.get("recommended_contract")
            or row.get("preferred_contract")
        )
        if preopen:
            live.update({
                "morning_execution_mode": "PREOPEN_THESIS_CHECK",
                "morning_quote_evidence_state": "HISTORICAL",
                "live_options_source": "CANONICAL_PRIOR_SESSION",
                "quote_source_dataset_id": _s(
                    row.get("quote_source_dataset_id") or row.get("option_chain_dataset_id")
                ),
                "quote_provider_timestamp_utc": _s(
                    row.get("quote_provider_timestamp_utc")
                    or row.get("contract_quote_timestamp")
                    or row.get("selected_quote_timestamp_utc")
                ),
                "quote_fetch_timestamp_utc": "",
            })
        elif occ:
            cached_quote: Optional[Dict[str, Any]] = None
            thesis_id = _s(row.get("thesis_id"))
            if liquidity_store is not None and thesis_id:
                try:
                    decision = liquidity_store.should_fetch(
                        thesis_id, freshness_seconds=liquidity_freshness_seconds,
                        now=datetime.now(timezone.utc),
                    )
                    observation = decision.latest_observation
                    if (
                        not decision.should_fetch
                        and observation is not None
                        and _u(observation.contract_symbol).replace("O:", "")
                        == _u(occ).replace("O:", "")
                    ):
                        cached_quote = {
                            "live_contract_bid": observation.bid,
                            "live_contract_ask": observation.ask,
                            "live_contract_mid": (
                                (observation.bid + observation.ask) / 2.0
                                if observation.bid is not None and observation.ask is not None
                                else None
                            ),
                            "live_contract_iv": observation.iv,
                            "live_contract_delta": observation.delta,
                            "live_contract_oi": observation.open_interest,
                            "live_contract_volume": observation.volume,
                            "live_contract_provider_updated": observation.quote_as_of.isoformat(),
                            "live_options_source": "MARKETDATA",
                            "live_options_fetched_at": _utc_now(),
                            "live_options_resolution": "CDS_FRESH_QUOTE_HIT",
                        }
                        source_record = liquidity_store.registry.get_dataset(
                            observation.source_dataset_id
                        )
                        if source_record is not None:
                            source_path = Path(source_record.storage_uri)
                            if source_path.exists() and source_path.suffix.lower() == ".json":
                                source_payload = json.loads(
                                    source_path.read_text(encoding="utf-8-sig")
                                )
                                for live_field, *aliases in (
                                    ("live_contract_gamma", "live_contract_gamma", "contract_gamma"),
                                    ("live_contract_theta", "live_contract_theta", "contract_theta"),
                                    ("live_contract_vega", "live_contract_vega", "contract_vega"),
                                    ("live_contract_multiplier", "live_contract_multiplier", "contract_multiplier"),
                                ):
                                    for alias in aliases:
                                        value = source_payload.get(alias)
                                        if value is not None and value != "":
                                            cached_quote[live_field] = value
                                            break
                except Exception as cache_error:
                    log.warning("CDS live-option reuse failed for %s: %s", ticker, cache_error)
            if cached_quote is not None:
                contract_live = hydrate_selected_structure(
                    occ,
                    lambda _symbol: cached_quote or {},
                    ticker=row.get("ticker"),
                    direction=(
                        row.get("canonical_direction")
                        or row.get("resolved_direction")
                        or row.get("direction")
                    ),
                    instrument=row.get("instrument") or row.get("options_strategy"),
                    fetched_at_utc=cached_quote["live_options_fetched_at"],
                )
                contract_live["live_options_resolution"] = "CDS_FRESH_QUOTE_HIT"
            else:
                contract_live = _hydrate_live_structure(row, occ)
                contract_live.setdefault("live_options_resolution", "MARKETDATA_FETCH")
            contract_live["live_contract_symbol"] = (
                contract_live.get("selected_contract_symbol") or occ
            )
            primary_pass, primary_reason = _check_contract(contract_live, spread_threshold, row)
            contract_live["primary_contract_symbol"] = occ
            contract_live["primary_contract_pass"] = "TRUE" if primary_pass else "FALSE"
            contract_live["primary_contract_reason"] = primary_reason
            live.update(contract_live)
            if not primary_pass:
                repair_live = _try_live_repair_alternatives(row, occ, spread_threshold)
                if _s(repair_live.get("morning_contract_repair_used")).upper() == "TRUE":
                    live.update(repair_live)
                elif repair_live.get("morning_repair_attempts"):
                    live.update(repair_live)
        elif not preopen:
            # EOD may provide repair alternatives without promoting one into
            # contract_symbol. Try those alternatives before the row reaches the
            # gate as a blank-contract CONTRACT_REPAIR.
            repair_live = _try_live_repair_alternatives(row, "", spread_threshold)
            if repair_live:
                live.update(repair_live)
        # AG-03: Options skew fetch (call IV / put IV ratio)
        if not preopen:
            skew_data = _fetch_options_skew(ticker)
            live.update(skew_data)
        if msi_observation_resolver is not None and msi_session_date is not None:
            _capture_msi_market_observations(
                row,
                live,
                msi_observation_resolver,
                msi_session_date,
            )
        return ticker, live

    with ThreadPoolExecutor(max_workers=LIVE_FETCH_WORKERS) as ex:
        futures = {ex.submit(fetch_one, row): row for row in candidates}
        for future in as_completed(futures):
            try:
                ticker, data = future.result()
                results[ticker] = data
                price = data.get("live_price", "N/A")
                log.info("  %-6s  price=%-10s  options=%s",
                         ticker, price, data.get("live_options_source", "NONE"))
            except Exception as exc:
                log.warning("Live fetch failed: %s", exc)

    return results


# ---------------------------------------------------------------------------
# Macro regime check
# ---------------------------------------------------------------------------

def _load_macro_state() -> Dict[str, Any]:
    """Load full macro state from macro_intelligence_latest.json.
    Returns a dict with regime_state, vol_mode, macro_conviction, sector_lead,
    sector_avoid, macro_filter, macro_as_of_utc, vix_spot, macro_loaded.
    Never raises â€” degrades to UNKNOWN on any error."""
    if not MACRO_PATH.exists():
        return {"regime_state": "UNKNOWN", "macro_loaded": False}
    try:
        data = json.loads(MACRO_PATH.read_text(encoding="utf-8-sig"))
        regime = _u(
            data.get("regime_state")
            or data.get("regime_label")
            or data.get("macro_regime")
            or "UNKNOWN"
        )
        sector_lead  = data.get("sector_lead")  or data.get("sector_leads")  or []
        sector_avoid = data.get("sector_avoid") or data.get("sectors_avoid") or []
        return {
            "regime_state":     regime,
            "dir_bias":         _u(data.get("dir_bias") or data.get("directional_bias") or ""),
            "risk_on_off_switch": _u(data.get("risk_on_off_switch") or ""),
            "vol_mode":         _u(data.get("vol_mode") or data.get("volatility_mode") or ""),
            "macro_conviction": _f(data.get("macro_conviction") or data.get("conviction")),
            "sector_lead":      sector_lead  if isinstance(sector_lead,  list) else [sector_lead],
            "sector_avoid":     sector_avoid if isinstance(sector_avoid, list) else [sector_avoid],
            "macro_filter":     _u(data.get("macro_filter") or data.get("trade_filter") or ""),
            "size_multiplier":  _f(data.get("size_multiplier")),
            "macro_as_of_utc":  _s(data.get("as_of_utc") or data.get("as_of") or data.get("generated_at") or ""),
            "vix_spot":         _f(data.get("vix_spot")),
            "macro_loaded":     True,
        }
    except Exception:
        return {"regime_state": "UNKNOWN", "macro_loaded": False}


def _load_bond_macro() -> Dict[str, Any]:
    """
    Load bond macro state from bond_macro_state.json sidecar.
    Returns empty dict if file missing, unreadable, or stale.
    Never raises â€” always degrades gracefully.

    Staleness threshold: BOND_MACRO_MAX_AGE_H hours.
    trade_go is returned as a Python bool (not string).
    """
    if not BOND_MACRO_PATH.exists():
        log.warning("bond_macro_state.json not found â€” bond macro check skipped")
        return {}
    try:
        data = json.loads(BOND_MACRO_PATH.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        log.warning("bond_macro_state.json unreadable (%s) â€” bond macro check skipped", exc)
        return {}

    # Staleness check
    generated_at = _s(data.get("generated_at"))
    if generated_at:
        try:
            from datetime import datetime
            gen_dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
            if gen_dt.tzinfo is None:
                from datetime import timezone
                gen_dt = gen_dt.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - gen_dt).total_seconds() / 3600
            if age_h > BOND_MACRO_MAX_AGE_H:
                log.warning(
                    "bond_macro_state.json is %.1fh old (threshold %dh) â€” bond macro check skipped",
                    age_h, BOND_MACRO_MAX_AGE_H,
                )
                return {}
        except Exception:
            pass  # If we can't parse the timestamp, proceed with the data

    composite   = data.get("composite", {})
    yield_curve = data.get("yield_curve", {})
    credit      = data.get("credit_stress", {})
    zn          = data.get("zn_futures", {})
    auction     = data.get("auction", {})
    curve_stale = bool(yield_curve.get("stale_flag", False))

    # Normalise trade_go to Python bool
    raw_trade_go = composite.get("trade_go", True)
    if isinstance(raw_trade_go, str):
        trade_go = raw_trade_go.strip().upper() not in {"FALSE", "0", "NO", ""}
    else:
        trade_go = bool(raw_trade_go)

    return {
        # Gate field
        "bond_trade_go":            True if curve_stale else trade_go,
        # Composite display fields
        "bond_macro_score":         None if curve_stale else composite.get("macro_bond_score"),
        "bond_macro_flag":          "BOND_MACRO_PARTIAL_CONTEXT" if curve_stale else _s(composite.get("morning_manifest_flag")),
        "bond_primary_warning":     (
            "Yield-curve component is stale; current curve state and composite score suppressed"
            if curve_stale else _s(composite.get("primary_warning"))
        ),
        "bond_all_warnings":        "; ".join(composite.get("all_warnings", [])),
        "bond_breakeven_adj_pct":   composite.get("breakeven_adjustment_pct"),
        # Yield curve display fields
        "bond_curve_state":         "STALE_UNAVAILABLE" if curve_stale else _s(yield_curve.get("curve_state")),
        "bond_spread_bps":          None if curve_stale else yield_curve.get("spread_bps"),
        "bond_curve_regime":        "" if curve_stale else _s(yield_curve.get("regime_implication")),
        "bond_curve_move_1d":       "STALE_UNAVAILABLE" if curve_stale else _s(yield_curve.get("curve_move_1d")),
        "bond_curve_freshness":     "STALE" if curve_stale else "CURRENT",
        "bond_curve_as_of_date":    _s(yield_curve.get("as_of_date") or data.get("as_of_date")),
        "bond_composite_freshness": "PARTIAL_STALE_CURVE" if curve_stale else "CURRENT",
        "bond_source_curve_state":  _s(yield_curve.get("curve_state")),
        "bond_source_curve_move_1d": _s(yield_curve.get("curve_move_1d")),
        "bond_source_macro_score":  composite.get("macro_bond_score"),
        "bond_source_macro_flag":   _s(composite.get("morning_manifest_flag")),
        "bond_data_source":         _s(yield_curve.get("data_source")),
        # Credit display fields
        "bond_credit_stress":       _s(credit.get("stress_level")),
        "bond_credit_warning":      credit.get("credit_warning", False),
        # ZN futures display fields
        "bond_zn_direction":        _s(zn.get("zn_direction")),
        "bond_rate_regime_signal":  _s(zn.get("rate_regime_signal")),
        # Auction display fields
        "bond_auction_today":       auction.get("auction_today", False),
        "bond_spread_risk_flag":    auction.get("spread_risk_flag", False),
        # Meta
        "bond_macro_generated_at":  generated_at,
        "bond_macro_loaded":        "TRUE",
    }


def _load_enrichment_delta() -> Dict[str, str]:
    """
    Load ticker bias catalogue from avshunter_macro_enrichment_delta.json.
    Returns dict: {TICKER_UPPER: "BEARISH" | "BULLISH"}
    Only BEARISH and BULLISH are returned; MIXED, NEUTRAL and absent tickers are excluded.
    Actual path: data["market_data_snapshot"]["instrument_snapshot"][ticker]["bias"]
    Graceful: returns {} on any failure.
    """
    if not ENRICHMENT_DELTA_PATH.exists():
        return {}
    try:
        data = json.loads(ENRICHMENT_DELTA_PATH.read_text(encoding="utf-8-sig"))
        instrument_snapshot = data.get("market_data_snapshot", {}).get("instrument_snapshot", {})
        bias_map: Dict[str, str] = {}
        for ticker, ticker_data in instrument_snapshot.items():
            if not isinstance(ticker_data, dict):
                continue
            bias = _u(ticker_data.get("bias", ""))
            if bias in ("BEARISH", "BULLISH"):
                bias_map[_u(ticker)] = bias
        return bias_map
    except Exception as exc:
        log.info("Enrichment delta load skipped: %s", exc)
        return {}


def _load_china_exposure() -> Dict[str, Dict[str, Any]]:
    """Load China revenue exposure lookup from china_revenue_exposure.json.
    Returns dict: {TICKER_UPPER: {china_revenue_pct, china_sensitivity}}
    Graceful: returns {} on any failure."""
    if not CHINA_EXPOSURE_PATH.exists():
        return {}
    try:
        data = json.loads(CHINA_EXPOSURE_PATH.read_text(encoding="utf-8-sig"))
        raw = data.get("tickers", {})
        return {_u(k): v for k, v in raw.items() if isinstance(v, dict)}
    except Exception as exc:
        log.info("China exposure load skipped: %s", exc)
        return {}


def _fetch_options_skew(ticker: str) -> Dict[str, Any]:
    """
    Fetch ATM call and put IV for a ticker from MarketData.app.
    Computes call_iv / put_iv ratio as skew indicator.
    Graceful: returns {skew_available: False} on any failure.
    """
    import urllib.request
    from datetime import timedelta

    today      = datetime.now(timezone.utc).date()
    expiry     = today + timedelta(days=_SKEW_EXPIRY_WINDOW_DAYS)
    expiry_str = expiry.strftime("%Y-%m-%d")

    def get_atm_iv(side: str) -> Optional[float]:
        url = (
            f"https://api.marketdata.app/v1/options/chain/{ticker}/"
            f"?token={MARKETDATA_API_KEY}"
            f"&expiration={expiry_str}&strikeLimit=3&side={side}"
        )
        try:
            with urllib.request.urlopen(url, timeout=LIVE_FETCH_TIMEOUT) as resp:
                data = json.loads(resp.read().decode())
            if data.get("s") != "ok":
                return None
            ivs = data.get("iv", [])
            if ivs:
                clean = [float(v) for v in ivs if v is not None and float(v) > 0]
                return sum(clean) / len(clean) if clean else None
        except Exception:
            return None
        return None

    call_iv = get_atm_iv("call")
    time.sleep(0.1)
    put_iv  = get_atm_iv("put")

    if call_iv is not None and put_iv is not None and put_iv > 0:
        skew_ratio = round(call_iv / put_iv, 4)
        skew_flag  = (
            "CALL_SKEW_HIGH" if skew_ratio > _SKEW_CALL_HIGH else
            "PUT_SKEW_HIGH"  if skew_ratio < _SKEW_PUT_HIGH  else
            "SKEW_NEUTRAL"
        )
        return {
            "skew_call_iv":   round(call_iv, 4),
            "skew_put_iv":    round(put_iv,  4),
            "skew_ratio":     skew_ratio,
            "skew_flag":      skew_flag,
            "skew_available": True,
            "skew_expiry":    expiry_str,
        }
    return {"skew_available": False, "skew_flag": "SKEW_UNAVAILABLE"}


def _regime_flipped(eod_regime: str, current_regime: str) -> bool:
    """
    True only on a material directional flip.
    TRANSITIONAL variants of the same base direction are NOT flips.
    """
    if not eod_regime or not current_regime:
        return False
    if eod_regime == current_regime:
        return False

    def _base(r: str) -> str:
        r = r.upper()
        if "BULL" in r:
            return "BULLISH"
        if "BEAR" in r:
            return "BEARISH"
        if "NEUTRAL" in r:
            return "NEUTRAL"
        return r

    return _base(eod_regime) != _base(current_regime)


def _check_bond_macro(bond_state: Dict[str, Any]) -> tuple[bool, str]:
    """
    Assess bond context for display and review. The result is advisory only
    and is never included in the trade authority decision.
    """
    if not bond_state:
        return True, "Bond macro state unavailable â€” check skipped"

    if not bond_state.get("bond_trade_go", True):
        warning = _s(bond_state.get("bond_primary_warning")) or "Bond macro headwind active"
        score   = bond_state.get("bond_macro_score", "N/A")
        flag    = _s(bond_state.get("bond_macro_flag")) or "BOND_MACRO_WARN"
        return False, f"Bond macro FLAG â€” {flag} score={score}: {warning}"

    score = bond_state.get("bond_macro_score", "N/A")
    flag  = _s(bond_state.get("bond_macro_flag")) or "BOND_MACRO_OK"
    return True, f"Bond macro clear â€” {flag} score={score}"


# ---------------------------------------------------------------------------
# CHECK 1 â€” Invalidation intact
# ---------------------------------------------------------------------------

def _check_invalidation(row: Dict[str, Any], live_price: Optional[float]) -> tuple[bool, str]:
    """
    Returns (passed, reason).
    passed=True means invalidation is intact â€” thesis still valid.
    """
    if live_price is None:
        return False, "CANNOT_VERIFY - live price unavailable; invalidation check not confirmed"

    direction = _u(
        row.get("evening_direction")
        or row.get("canonical_direction")
        or row.get("resolved_direction")
        or row.get("direction")
    )
    if direction not in {"CALL", "PUT"}:
        return False, (
            f"{LifecycleEvaluationState.NOT_EVALUATED_NON_DIRECTIONAL.value} - "
            "directional invalidation is not applicable"
        )

    invalidation = _f(
        row.get("invalidation_spot")
        or row.get("ev3_invalidation_spot")
        or row.get("evening_invalidation_price")
    )
    if not invalidation or invalidation <= 0:
        return False, (
            f"{LifecycleEvaluationState.MISSING_AUTHORITATIVE_STOP.value} - "
            "structure cannot be verified"
        )

    if direction == "CALL" and live_price <= invalidation:
        return False, f"CALL thesis broken â€” price {live_price:.2f} at or below invalidation {invalidation:.2f}"
    if direction == "PUT" and live_price >= invalidation:
        return False, f"PUT thesis broken â€” price {live_price:.2f} at or above invalidation {invalidation:.2f}"

    return True, f"Invalidation intact â€” price {live_price:.2f} vs level {invalidation:.2f}"


# ---------------------------------------------------------------------------
# CHECK 2 â€” Macro regime unchanged
# ---------------------------------------------------------------------------

def _check_macro(row: Dict[str, Any], current_regime: str) -> tuple[bool, str]:
    """
    Returns (passed, reason).
    passed=True means no material regime flip overnight.
    """
    eod_regime = _u(
        row.get("morning_macro_regime_state")
        or row.get("macro_regime_label")
        or row.get("macro_regime")
        or row.get("regime_state")
        or row.get("evening_regime_state")
    )

    if not eod_regime or eod_regime == "UNKNOWN":
        return False, f"EOD regime not recorded - cannot verify change to {current_regime}"

    if _regime_flipped(eod_regime, current_regime):
        return False, f"Regime flipped overnight: {eod_regime} â†’ {current_regime}"

    return True, f"Regime unchanged: {eod_regime} â†’ {current_regime}"


def _check_macro_permission(macro_state: Dict[str, Any]) -> tuple[bool, str]:
    """Publish macro context without granting or denying trade authority."""
    if not macro_state or not macro_state.get("macro_loaded", False):
        return True, "MACRO_ADVISORY_UNAVAILABLE"
    macro_filter = _u(macro_state.get("macro_filter"))
    if not macro_filter:
        return True, "MACRO_ADVISORY_FILTER_MISSING"
    return True, f"MACRO_ADVISORY_ONLY:{macro_filter}"


def _assess_macro_context(
    row: Dict[str, Any],
    macro_state: Dict[str, Any],
) -> Dict[str, Any]:
    """Direction-aware sector-rotation context; never a GO/NO-GO decision."""
    direction = _u(
        row.get("evening_direction")
        or row.get("canonical_direction")
        or row.get("resolved_direction")
        or row.get("direction")
    )
    sector_etf = _u(row.get("sector_etf") or row.get("scanner_sector_etf"))
    leads = {
        _u(value) for value in (macro_state.get("sector_lead") or []) if _u(value)
    }
    avoids = {
        _u(value) for value in (macro_state.get("sector_avoid") or []) if _u(value)
    }
    dir_bias = _u(macro_state.get("dir_bias"))

    role = "UNCLASSIFIED"
    alignment = "NEUTRAL"
    score = 0
    if sector_etf in leads:
        role = "SECTOR_LEADER"
        alignment = "TAILWIND" if direction == "CALL" else "HEADWIND"
        score = 1 if direction == "CALL" else -1
    elif sector_etf in avoids:
        role = "SECTOR_LAGGARD"
        alignment = "TAILWIND" if direction == "PUT" else "HEADWIND"
        score = 1 if direction == "PUT" else -1
    elif dir_bias in {"BULLISH", "BEARISH"}:
        aligned_direction = "CALL" if dir_bias == "BULLISH" else "PUT"
        alignment = "TAILWIND" if direction == aligned_direction else "HEADWIND"
        score = 1 if alignment == "TAILWIND" else -1

    note = (
        f"{direction or 'UNKNOWN'} in {sector_etf or 'UNCLASSIFIED'}: "
        f"{role}, macro {alignment.lower()}. Advisory only; no capital authority."
    )
    return {
        "macro_capital_authority": "ADVISORY_ONLY",
        "macro_direction_alignment": alignment,
        "macro_sector_rotation_role": role,
        "macro_sector_etf": sector_etf,
        "macro_context_score": score,
        "macro_context_note": note,
        "macro_filter_advisory": _u(macro_state.get("macro_filter")),
        "macro_size_multiplier_advisory": macro_state.get("size_multiplier", ""),
    }


# ---------------------------------------------------------------------------
# CHECK 3 â€” Contract liquid
# ---------------------------------------------------------------------------

def _governed_spread_limits(requested_hard_max: Any) -> tuple[float, float]:
    """Return execution/review limits without allowing runtime policy relaxation."""
    execution_max = float(LONG_OPTION_EXECUTION_POLICY["executable_spread_max_pct"])
    governed_hard_max = float(LONG_OPTION_EXECUTION_POLICY["reviewable_spread_max_pct"])
    requested = _f(requested_hard_max, governed_hard_max)
    review_max = min(requested, governed_hard_max) if requested is not None else governed_hard_max
    return execution_max, max(execution_max, review_max)


def _production_strategy_policy(
    live_data: Dict[str, Any],
    row: Optional[Dict[str, Any]] = None,
) -> tuple[bool, str, str, str]:
    """Resolve long-call/long-put production eligibility for the selected object."""
    context = dict(row or {})
    context.update(live_data)
    structure = _u(
        live_data.get("selected_structure")
        or context.get("selected_structure")
        or context.get("contract_structure")
    )
    instrument = _u(context.get("instrument") or context.get("options_strategy"))
    selected_value = (
        live_data.get("selected_contract_symbols")
        or live_data.get("selected_contract_symbol")
        or live_data.get("live_contract_symbol")
        or context.get("contract_symbol")
        or context.get("recommended_contract")
        or context.get("preferred_contract")
    )
    symbol_count = len(selected_contract_symbols_from_value(selected_value))
    exotic_hint = any(
        token in f"{structure}|{instrument}"
        for token in (
            "SPREAD", "VERTICAL", "STRANGLE", "STRADDLE", "IRON_",
            "CONDOR", "BUTTERFLY", "CALENDAR", "DIAGONAL", "RATIO",
            "MULTI_LEG", "COMPOSITE",
        )
    )
    if exotic_hint or symbol_count > 1 or (structure and structure != "LONG_SINGLE"):
        resolved = structure or instrument or "MULTI_LEG"
        return (
            False,
            "RESEARCH_ONLY_UNSUPPORTED_PRODUCTION_STRUCTURE:" + resolved,
            resolved,
            "",
        )

    side = (
        _side(context.get("selected_contract_side"))
        or _contract_side_from_row(context)
        or _side(
            context.get("canonical_direction")
            or context.get("resolved_direction")
            or context.get("direction")
        )
    )
    resolved_structure = structure or "LONG_SINGLE"
    if side not in LONG_OPTION_EXECUTION_POLICY["allowed_sides"]:
        return False, "RESEARCH_ONLY_LONG_OPTION_SIDE_UNRESOLVED", resolved_structure, side
    return (
        True,
        f"PRODUCTION_LONG_{side}_ELIGIBLE",
        resolved_structure,
        side,
    )


def _spread_policy_state(
    live_data: Dict[str, Any],
    requested_hard_max: Any,
) -> tuple[str, str, Optional[float]]:
    execution_max, review_max = _governed_spread_limits(requested_hard_max)
    spread_pct = _f(live_data.get("live_contract_spread_pct"))
    if spread_pct is None:
        return "UNAVAILABLE", "Contract spread unavailable", None
    if spread_pct > review_max:
        return (
            "BLOCKED_SPREAD",
            f"Spread {spread_pct:.1f}% exceeds governed hard maximum {review_max:.1f}%",
            spread_pct,
        )
    if spread_pct > execution_max:
        return (
            "MANUAL_LIQUIDITY_REVIEW",
            f"Spread {spread_pct:.1f}% exceeds executable maximum {execution_max:.1f}% "
            f"but is within review maximum {review_max:.1f}%",
            spread_pct,
        )
    return (
        "EXECUTABLE_SPREAD",
        f"Spread {spread_pct:.1f}% is within executable maximum {execution_max:.1f}%",
        spread_pct,
    )

def _check_contract(
    live_data: Dict[str, Any],
    spread_threshold: float,
    row: Optional[Dict[str, Any]] = None,
) -> tuple[bool, str]:
    """
    Returns (passed, reason).
    passed=True means contract has a live quote with acceptable spread.
    """
    strategy_pass, strategy_reason, _, _ = _production_strategy_policy(live_data, row)
    if not strategy_pass:
        return False, strategy_reason

    if row is not None and _u(row.get("morning_direction_guard_contract_side_conflict")) == "TRUE":
        return False, "Contract side conflicts with preserved thesis direction - repair contract before entry"

    bid = _f(live_data.get("live_contract_bid"))
    ask = _f(live_data.get("live_contract_ask"))
    spread_pct = _f(live_data.get("live_contract_spread_pct"))
    structure = _u(live_data.get("selected_structure"))
    is_vertical = structure in {"BULL_CALL_DEBIT", "BEAR_PUT_DEBIT"}

    long_leg = live_data.get("selected_long_leg")
    short_leg = live_data.get("selected_short_leg")
    if is_vertical and (not isinstance(long_leg, dict) or not isinstance(short_leg, dict)):
        try:
            serialized_legs = json.loads(_s(live_data.get("selected_legs_json")) or "[]")
        except (TypeError, ValueError, json.JSONDecodeError):
            serialized_legs = []
        if len(serialized_legs) == 2:
            long_leg, short_leg = serialized_legs

    if is_vertical:
        if not isinstance(long_leg, dict) or not isinstance(short_leg, dict):
            return False, "Vertical structure missing one or both exact leg quotes"
        for leg_name, leg in (("long", long_leg), ("short", short_leg)):
            leg_bid = _f(leg.get("bid"))
            leg_ask = _f(leg.get("ask"))
            if leg_bid is None or leg_ask is None or leg_bid <= 0 or leg_ask <= 0 or leg_bid > leg_ask:
                return False, f"Vertical {leg_name} leg quote invalid - bid={leg_bid} ask={leg_ask}"
        spread_pct = _f(live_data.get("selected_max_leg_spread_pct"))

    if bid is None or ask is None:
        return False, "No live contract quote â€” repair contract before entry"

    if (not is_vertical and bid <= 0) or ask <= 0:
        return False, f"Contract quote invalid â€” bid={bid} ask={ask}"

    execution_max, review_max = _governed_spread_limits(spread_threshold)
    if spread_pct is not None and spread_pct > review_max:
        return False, f"Spread blocked - {spread_pct:.1f}% exceeds {review_max:.1f}% hard maximum"
    if spread_pct is not None and spread_pct > execution_max:
        return False, (
            f"Manual liquidity review - {spread_pct:.1f}% exceeds "
            f"{execution_max:.1f}% executable maximum"
        )

    # â”€â”€ Greek sub-conditions (require row context) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if row is not None:
        delta = _f(long_leg.get("delta")) if is_vertical and isinstance(long_leg, dict) else _f(live_data.get("live_contract_delta"))
        if delta is not None:
            abs_delta = abs(delta)
            if abs_delta < 0.20:
                return False, (f"Delta too low â€” abs(delta)={abs_delta:.3f} < 0.20 (contract too far OTM, no directional edge)")
            if abs_delta > 0.75:
                return False, (f"Delta too high â€” abs(delta)={abs_delta:.3f} > 0.75 (deep ITM stock-replacement profile outside default mandate)")
        live_iv = _f(long_leg.get("iv")) if is_vertical and isinstance(long_leg, dict) else _f(live_data.get("live_contract_iv"))
        if live_iv is not None:
            if live_iv <= 0:
                return False, (f"IV invalid â€” live_iv={live_iv:.4f} (zero or negative IV indicates broken/stale quote)")
            if live_iv > 2.50:
                return False, (f"IV invalid â€” live_iv={live_iv:.1%} > 250% (extreme IV indicates broken quote)")
        if live_iv is not None:
            eod_iv = _f(row.get("implied_volatility_eod") or row.get("iv_eod") or row.get("contract_iv") or row.get("iv"))
            if eod_iv is not None and eod_iv > 0:
                iv_compression_ratio = live_iv / eod_iv
                if iv_compression_ratio < 0.70:
                    return False, (f"IV compression â€” live_iv={live_iv:.1%} is {(1 - iv_compression_ratio):.1%} below EOD iv={eod_iv:.1%}. Premium actively deflating â€” FLAG for trader review.")

    if is_vertical:
        return True, (
            f"Vertical liquid - entry debit={ask:.2f} "
            f"max leg spread={spread_pct:.1f}%"
        )
    spread_text = f"{spread_pct:.1f}%" if spread_pct is not None else "UNAVAILABLE"
    return True, f"Contract liquid â€” bid={bid:.2f} ask={ask:.2f} spread={spread_text}"


def _morning_hold_sessions(row: Dict[str, Any]) -> Optional[float]:
    # The Horizon Router owns the planned trade hold.  Actuarial L2 hold days
    # describe an outcome window and must not expand the DTE requirement for a
    # shorter governed trade horizon.
    for key in (
        "planned_hold_sessions",
        "remaining_hold_sessions",
        "ev3_horizon_sessions",
        "hold_days",
        "l2_hold_days",
    ):
        value = _f(row.get(key))
        if value is not None and value >= 0:
            return value
    text = _s(row.get("hold_label") or row.get("hold_period") or row.get("time_horizon"))
    values = [float(token) for token in re.findall(r"\d+(?:\.\d+)?", text)]
    return max(values) if values else None


def _morning_forecast_vol(row: Dict[str, Any], live_data: Dict[str, Any]) -> Optional[float]:
    for value in (
        row.get("garch_forecast_vol"), row.get("l3_vol_forecast"),
        row.get("hv_30d"), live_data.get("live_contract_iv"),
        row.get("contract_iv"), row.get("atm_iv"),
    ):
        parsed = _f(value)
        if parsed is None or parsed <= 0:
            continue
        if parsed > 5.0:
            parsed /= 100.0
        if 0 < parsed <= 5.0:
            return parsed
    return None


def _morning_liquidity_lifecycle(
    row: Dict[str, Any],
    live_data: Dict[str, Any],
    *,
    contract_changed: bool,
    economics_recompute_complete: bool,
) -> Dict[str, Any]:
    """Re-evaluate the exact selected contract and overnight thesis runway."""
    side = _side(
        row.get("final_direction") or row.get("canonical_direction")
        or row.get("direction") or row.get("options_direction")
    )
    current_spot = _f(live_data.get("live_price") or row.get("live_price"))
    thesis_spot = _f(
        row.get("thesis_spot") or row.get("signal_price")
        or row.get("underlying_price") or row.get("entry_price") or row.get("entry")
    )
    strike = _f(
        live_data.get("selected_long_leg", {}).get("strike")
        if isinstance(live_data.get("selected_long_leg"), dict) else None
    ) or _f(row.get("contract_strike") or row.get("strike"))
    target = _f(row.get("structural_target") or row.get("target_price") or row.get("target"))
    invalidation = _f(
        row.get("invalidation_spot") or row.get("invalidation_price")
        or row.get("invalidation_level") or row.get("stop_loss") or row.get("stop")
    )
    dte = _f(
        live_data.get("selected_long_leg", {}).get("dte")
        if isinstance(live_data.get("selected_long_leg"), dict) else None
    ) or _f(row.get("contract_dte") or row.get("dte"))
    hold = _morning_hold_sessions(row)
    forecast_vol = _morning_forecast_vol(row, live_data)
    bid = _f(live_data.get("live_contract_bid"))
    ask = _f(live_data.get("live_contract_ask"))
    delta = _f(live_data.get("live_contract_delta") or row.get("contract_delta"))
    thesis_id = _s(row.get("thesis_id")) or (
        f"{_u(row.get('ticker'))}:{side or 'UNRESOLVED'}:"
        f"{_s(row.get('asof_date') or row.get('run_id')) or 'UNKNOWN_SESSION'}"
    )
    selected_symbol = _s(
        row.get("morning_selected_contract_symbol") or row.get("contract_symbol")
        or row.get("recommended_contract")
    )
    previous_symbol = _s(
        row.get("contract_symbol_original") or row.get("previous_contract_symbol")
    )
    base = {
        "thesis_id": thesis_id,
        "previous_contract_symbol": previous_symbol,
        "contract_changed": bool(contract_changed),
        "contract_selection_reason": (
            "MORNING_REPAIR_ALTERNATIVE_SELECTED" if contract_changed
            else "MORNING_EXACT_CONTRACT_REQUOTE"
        ),
        "quote_as_of": live_data.get("live_contract_provider_updated"),
        "maturation_score_is_probability": False,
        "maturation_execution_authority": False,
    }
    required = {
        "side": side if side in {"CALL", "PUT"} else None,
        "current_spot": current_spot,
        "thesis_spot": thesis_spot,
        "strike": strike,
        "target": target,
        "invalidation": invalidation,
        "dte": dte,
        "hold": hold,
        "forecast_vol": forecast_vol,
        "selected_symbol": selected_symbol or None,
    }
    missing = [key for key, value in required.items() if value is None]
    if missing:
        if contract_changed:
            return {
                **base,
                "thesis_state": "DATA_INCOMPLETE",
                "liquidity_state": "LIFECYCLE_DATA_INCOMPLETE",
                "morning_transition_state": "CONTRACT_REPRICE_REQUIRED",
                "recovery_disposition": "CONTRACT_REPAIR",
                "executable_now": False,
                "quote_freshness": "UNKNOWN",
                "liquidity_lifecycle_reason": "REPLACEMENT_INPUT_MISSING:" + ",".join(missing),
            }
        # Archived/unit-test fixtures produced before lifecycle-v1 remain
        # readable. Fresh production EOD rows carry thesis_id/lifecycle fields
        # and therefore fail closed if any required lifecycle input disappears.
        legacy_input = not any(
            _s(row.get(key))
            for key in ("thesis_id", "lifecycle_contract_version", "liquidity_state")
        )
        if legacy_input:
            return {
                **base,
                "thesis_state": "LEGACY_NOT_EVALUATED",
                "liquidity_state": "LEGACY_NOT_EVALUATED",
                "morning_transition_state": "LEGACY_LIFECYCLE_NOT_EVALUATED",
                "recovery_disposition": "LEGACY_COMPATIBILITY",
                "executable_now": False,
                "quote_freshness": "UNKNOWN",
                "liquidity_lifecycle_reason": "LEGACY_INPUT_MISSING:" + ",".join(missing),
            }
        return {
            **base,
            "thesis_state": "DATA_INCOMPLETE",
            "liquidity_state": "LIFECYCLE_DATA_INCOMPLETE",
            "morning_transition_state": "CONTRACT_REPRICE_REQUIRED",
            "recovery_disposition": "CONTRACT_REPAIR",
            "executable_now": False,
            "quote_freshness": "UNKNOWN",
            "liquidity_lifecycle_reason": "MISSING:" + ",".join(missing),
        }
    try:
        assessment = evaluate_options_liquidity_lifecycle(LifecycleInputs(
            side=str(required["side"]),
            spot=float(required["current_spot"]),
            strike=float(required["strike"]),
            delta=delta,
            bid=bid,
            ask=ask,
            dte=float(required["dte"]),
            remaining_hold_sessions=float(required["hold"]),
            forecast_vol_annual=float(required["forecast_vol"]),
            thesis_spot=float(required["thesis_spot"]),
            current_spot=float(required["current_spot"]),
            structural_target=float(required["target"]),
            invalidation_spot=float(required["invalidation"]),
            quote_age_seconds=quote_age_seconds(
                live_data.get("live_contract_provider_updated")
                or live_data.get("live_contract_quote_timestamp")
                or live_data.get("selected_quote_timestamp_utc")
                or live_data.get("live_options_fetched_at")
            ),
            listed_market=True,
        ))
    except (KeyError, TypeError, ValueError) as exc:
        return {
            **base,
            "thesis_state": "DATA_INCOMPLETE",
            "liquidity_state": "LIFECYCLE_DATA_INVALID",
            "morning_transition_state": "CONTRACT_REPRICE_REQUIRED",
            "recovery_disposition": "CONTRACT_REPAIR",
            "executable_now": False,
            "quote_freshness": "INVALID",
            "liquidity_lifecycle_reason": str(exc),
        }

    runway_state = _u(assessment.get("remaining_runway_state"))
    liquidity_state = _u(assessment.get("liquidity_state"))
    if runway_state == "THESIS_INVALIDATED":
        transition = "THESIS_INVALIDATED"
    elif contract_changed and not economics_recompute_complete:
        transition = "CONTRACT_REPRICE_REQUIRED"
    elif runway_state == "MOVE_ALREADY_REALIZED":
        transition = "MOVE_ALREADY_REALIZED"
    elif runway_state in {"WAIT_FOR_PULLBACK", "GAP_CONFIRMATION_EXTENDED"}:
        transition = runway_state
    elif liquidity_state != "EXECUTABLE_NOW":
        transition = "LIQUIDITY_STILL_PENDING"
    elif runway_state == "GAP_CONFIRMATION_WITH_RUNWAY":
        transition = "GAP_CONFIRMATION_WITH_RUNWAY"
    else:
        transition = "EXECUTABLE_NOW"

    runway_factor = _f(assessment.get("remaining_runway_factor"), 0.0) or 0.0
    assessment.update({
        **base,
        "thesis_state": (
            "INVALIDATED" if runway_state == "THESIS_INVALIDATED"
            else "TARGET_REALIZED" if runway_state == "MOVE_ALREADY_REALIZED"
            else "ACTIVE"
        ),
        "morning_transition_state": transition,
        "dte_buffer_sessions": round(float(required["dte"]) - float(assessment.get("minimum_required_dte") or 0), 2),
        "atm_distance_sigma": assessment.get("atm_distance_sigma_1d"),
        "remaining_runway_pct": round(runway_factor * 100.0, 2),
        "quote_freshness": "FRESH",
        "maturation_score_is_probability": False,
        "maturation_execution_authority": False,
    })
    return assessment


# ---------------------------------------------------------------------------
# Core gate function
# ---------------------------------------------------------------------------

def run_gate(
    row: Dict[str, Any],
    live_data: Dict[str, Any],
    current_regime: str,
    spread_threshold: float,
    bond_state: Optional[Dict[str, Any]] = None,
    macro_state: Optional[Dict[str, Any]] = None,
    vix_regime_transition: bool = False,
    vix_move_pct: Optional[float] = None,
    enrichment_bias: Optional[Dict[str, str]] = None,
    china_risk_active: bool = False,
    china_exposure: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Apply governed trade-authority checks and attach advisory context.
    Macro, regime rotation and bond intelligence never grant, deny or alter
    the trade verdict; they explain directional and sector context only.
    """
    out = _ensure_governed_direction_record(row)
    live_price = _f(live_data.get("live_price"))

    # Stamp live data
    for k, v in live_data.items():
        out[k] = v

    repaired_contract = _s(live_data.get("morning_repair_contract_symbol"))
    if repaired_contract:
        repaired_identity = parse_occ_symbol(repaired_contract)
        out["contract_symbol_original"] = _s(
            row.get("contract_symbol")
            or row.get("recommended_contract")
            or row.get("preferred_contract")
        )
        out["contract_symbol"] = repaired_contract
        out["recommended_contract"] = repaired_contract
        out["morning_selected_contract_symbol"] = repaired_contract
        repaired_side = _contract_side_from_row(out)
        out["selected_contract_side"] = repaired_side
        repaired_strike = repaired_identity["strike"]
        repaired_expiry = repaired_identity["expiry"]
        repaired_dte = live_data.get("selected_contract_dte")
        if repaired_dte in (None, ""):
            quote_day = _s(
                live_data.get("live_contract_provider_updated")
                or live_data.get("selected_quote_timestamp_utc")
            )[:10]
            if quote_day:
                repaired_dte = (
                    date.fromisoformat(repaired_expiry) - date.fromisoformat(quote_day)
                ).days
        for field in ("strike", "contract_strike", "live_contract_strike"):
            out[field] = repaired_strike
        for field in ("expiry", "contract_expiry", "live_contract_expiry"):
            out[field] = repaired_expiry
        for field in ("dte", "contract_dte", "live_contract_dte"):
            out[field] = repaired_dte
        prior_trade_idea_id = _s(out.get("trade_idea_id"))
        run_token = _s(out.get("run_id")) or "UNKNOWN_RUN"
        ticker_token = _u(out.get("ticker")) or "UNKNOWN"
        direction_token = _u(
            out.get("governed_direction") or out.get("canonical_direction")
            or out.get("direction") or repaired_identity["side"]
        )
        instrument_token = _u(out.get("instrument")) or f"LONG_{repaired_identity['side']}"
        out["trade_idea_id"] = (
            f"{run_token}:{ticker_token}:{direction_token}:{instrument_token}:"
            f"{repaired_strike}:{repaired_expiry}"
        )
        if prior_trade_idea_id and prior_trade_idea_id != out["trade_idea_id"]:
            out["trade_idea_supersedes_id"] = prior_trade_idea_id
            out["trade_idea_supersession_reason"] = "MORNING_CONTRACT_REPAIR"
        out["contract_repair_resolved_at_open"] = "TRUE"
        # A replacement contract is a new economic object. Hydrate its quote
        # fields immediately, then invalidate all R:R/EV values calculated for
        # the former contract. It cannot become executable until those values
        # are recomputed for this exact OCC symbol.
        live_to_contract = {
            "live_contract_bid": "contract_bid",
            "live_contract_ask": "contract_ask",
            "live_contract_mid": "contract_mid",
            "live_contract_spread_pct": "contract_spread_pct",
            "live_contract_iv": "contract_iv",
            "live_contract_delta": "contract_delta",
            "live_contract_gamma": "contract_gamma",
            "live_contract_theta": "contract_theta",
            "live_contract_vega": "contract_vega",
            "live_contract_oi": "contract_oi",
            "live_contract_volume": "contract_volume",
            "live_contract_multiplier": "contract_multiplier",
            "live_contract_quote_timestamp": "contract_quote_timestamp",
            "live_options_source": "contract_source",
        }
        for source_field, contract_field in live_to_contract.items():
            value = live_data.get(source_field)
            if value is not None and value != "":
                out[contract_field] = value
        out["premium_mid"] = live_data.get("live_contract_mid", "")
        out["selected_contract_symbols"] = json.dumps([repaired_contract.replace("O:", "")])
        for stale_field in (
            "rr_premium_expected", "rr_options", "option_rr", "rr_predicted",
            "rr_contract_symbol", "rr_evaluation_id", "option_gain_at_target", "ev_predicted",
            "ev3_ev_conservative_return", "ev3_ev_lower_bound_return",
            "ev3_uncertainty_total_return", "ev3_p_target", "ev3_p_stop",
            "ev3_p_timeout", "ev3_evaluation_id",
        ):
            out[stale_field] = ""
        out["ev3_status"] = "NOT_EVALUATED_CONTRACT_CHANGED"
        out["ev3_reason_code"] = "MORNING_CONTRACT_CHANGED_RECOMPUTE_REQUIRED"
        out["ev3_reason_detail"] = (
            "Morning contract repair selected a different OCC symbol; "
            "monetisability and advisory economics must be recomputed from the replacement quote."
        )
        out["economics_comparable"] = False
        out["economics_mismatch_reason"] = "MORNING_CONTRACT_CHANGED_RECOMPUTE_REQUIRED"
        out["economics_recompute_required"] = "TRUE"
        out["contract_data_state"] = "AVAILABLE"
    else:
        out["contract_repair_resolved_at_open"] = "FALSE"

    out = _apply_thesis_direction_guard(out)
    hydration_attempted = "selected_structure_hydration_status" in live_data
    economics_recompute_complete = False
    if hydration_attempted:
        economics_recompute_complete = _recompute_selected_contract_economics(out, live_data)
    # Direct live observations and fully hydrated canonical structures resolve
    # through the same policy.  Recompute on every Morning Gate invocation so
    # an EOD viability label can never masquerade as current quote evidence.
    out.update(evaluate_execution_viability(out, live_data))
    if (
        _u(live_data.get("morning_execution_mode")) == "POSTOPEN_CONTRACT_REFRESH"
        and not _normalise_provider_timestamp(
            live_data.get("live_contract_provider_updated")
            or live_data.get("selected_quote_timestamp_utc")
        )
    ):
        out["execution_viability_state"] = "CONTRACT_QUOTE_UNAVAILABLE"
        out["execution_viability_reason"] = "PROVIDER_TIMESTAMP_MISSING"
        out["execution_viability_eligible"] = False
        out["executable_now"] = False

    previous_contract_symbol = _s(
        out.get("contract_symbol_original")
        or row.get("previous_contract_symbol")
        or row.get("contract_symbol")
        or row.get("recommended_contract")
    )
    selected_contract_symbol = _s(
        out.get("morning_selected_contract_symbol")
        or out.get("contract_symbol")
        or out.get("recommended_contract")
    )
    contract_changed = bool(repaired_contract) or bool(
        previous_contract_symbol and selected_contract_symbol
        and previous_contract_symbol.replace("O:", "").upper()
        != selected_contract_symbol.replace("O:", "").upper()
    )
    lifecycle_fields = _morning_liquidity_lifecycle(
        out,
        live_data,
        contract_changed=contract_changed,
        economics_recompute_complete=economics_recompute_complete,
    )
    out.update(lifecycle_fields)

    # Run checks
    direction_pass, direction_reason = _check_direction_integrity(out)
    authority_pass, authority_reason = _check_upstream_authority(out)
    economics_pass, economics_reason = _check_premium_economics(out)
    ev3_pass, ev3_reason = _check_ev3_authority(out)
    out["ev3_authority_requested"] = _truthy(out.get("ev3_authority_active"))
    out["ev3_authority_active"] = False
    out["ev3_authority_effective"] = False
    out["ev3_capital_authority"] = "ADVISORY_ONLY"
    out["ev3_advisory_state"] = _u(
        out.get("ev3_authority_state")
        or out.get("ev3_absolute_state")
        or out.get("ev3_status")
        or "NOT_EVALUATED"
    )
    inv_pass,  inv_reason  = _check_invalidation(out, live_price)
    macro_change_pass, macro_change_reason = _check_macro(out, current_regime)
    macro_permission_pass, macro_permission_reason = _check_macro_permission(macro_state or {})
    macro_context = _assess_macro_context(out, macro_state or {})
    macro_pass = True
    macro_reason = (
        f"{macro_permission_reason}; {macro_change_reason}; "
        f"{macro_context['macro_context_note']}"
    )
    strategy_pass, strategy_reason, selected_structure, selected_side = (
        _production_strategy_policy(live_data, out)
    )
    spread_policy_state, spread_policy_reason, observed_spread_pct = (
        _spread_policy_state(live_data, spread_threshold)
    )
    contract_pass, contract_reason = _check_contract(live_data, spread_threshold, out)
    if hydration_attempted and not economics_recompute_complete:
        contract_pass = False
        contract_reason = (
            "Selected structure quote loaded; exact-contract monetisability "
            f"recomputation incomplete: {out.get('economics_mismatch_reason') or 'UNKNOWN'}"
        )
    bond_pass, bond_reason = _check_bond_macro(bond_state or {})
    model_risk = _layer3_model_risk_guard(out)

    # Regime display fields
    eod_regime = _u(
        row.get("morning_macro_regime_state")
        or row.get("macro_regime_label")
        or row.get("macro_regime")
        or row.get("regime_state")
    )
    out["macro_regime_eod"]     = eod_regime
    out["macro_regime_now"]     = current_regime
    out["regime_changed"]       = "TRUE" if not macro_change_pass else "FALSE"
    out["gate_checked_at_utc"]  = _utc_now()

    # Check results
    out["check_upstream_authority_pass"] = "TRUE" if authority_pass else "FALSE"
    out["check_upstream_authority_reason"] = authority_reason
    out["check_direction_integrity_pass"] = "TRUE" if direction_pass else "FALSE"
    out["check_direction_integrity_reason"] = direction_reason
    out["direction_integrity_status"] = "PASS" if direction_pass else "FAIL"
    out["check_premium_economics_pass"] = "TRUE" if economics_pass else "FALSE"
    out["check_premium_economics_reason"] = economics_reason
    out["check_ev3_authority_pass"] = "TRUE" if ev3_pass else "FALSE"
    out["check_ev3_authority_reason"] = ev3_reason
    out["check_invalidation_pass"]   = "TRUE" if inv_pass else "FALSE"
    out["check_invalidation_reason"] = inv_reason
    out["check_macro_pass"]          = "TRUE" if macro_pass else "FALSE"
    out["check_macro_reason"]        = macro_reason
    out["check_macro_change_pass"]   = "TRUE" if macro_change_pass else "FALSE"
    out["check_macro_change_reason"] = macro_change_reason
    out["check_macro_permission_pass"] = "TRUE" if macro_permission_pass else "FALSE"
    out["check_macro_permission_reason"] = macro_permission_reason
    out.update(macro_context)
    out["check_contract_pass"]       = "TRUE" if contract_pass else "FALSE"
    out["check_contract_reason"]     = contract_reason
    execution_spread_max, review_spread_max = _governed_spread_limits(spread_threshold)
    out["long_option_policy_version"] = LONG_OPTION_EXECUTION_POLICY["policy_version"]
    out["production_strategy_eligible"] = "TRUE" if strategy_pass else "FALSE"
    out["production_strategy_reason"] = strategy_reason
    out["production_selected_structure"] = selected_structure
    out["production_selected_side"] = selected_side
    out["contract_spread_policy_state"] = spread_policy_state
    out["contract_spread_policy_reason"] = spread_policy_reason
    out["contract_spread_observed_pct"] = observed_spread_pct if observed_spread_pct is not None else ""
    out["contract_spread_executable_max_pct"] = execution_spread_max
    out["contract_spread_review_max_pct"] = review_spread_max
    out["check_layer3_model_risk_pass"]   = "TRUE" if model_risk["passed"] else "FALSE"
    out["check_layer3_model_risk_reason"] = model_risk["reason"]
    out["l3_model_risk_flags"]            = model_risk["flag_text"]
    out["l3_model_risk_flag_count"]       = len(model_risk["flags"])
    out["l3_model_risk_capital_guard"]    = "TRUE" if model_risk["flags"] else "FALSE"
    if model_risk["capped_tailwind"] != "":
        out["l3_iv_tailwind_score_capped"] = round(model_risk["capped_tailwind"], 4)

    # Greek gate diagnostics
    out["greek_gate_delta"]            = live_data.get("live_contract_delta", "")
    out["greek_gate_iv_live"]          = live_data.get("live_contract_iv", "")
    out["greek_gate_iv_eod"]           = (
        _f(row.get("implied_volatility_eod") or row.get("iv_eod") or row.get("contract_iv") or row.get("iv")) or ""
    )
    out["greek_gate_iv_compression"]   = (
        round(
            _f(live_data.get("live_contract_iv"), 0) /
            _f(row.get("implied_volatility_eod") or row.get("iv_eod") or row.get("contract_iv") or row.get("iv"), 1),
            4
        )
        if _f(live_data.get("live_contract_iv"))
        and _f(row.get("implied_volatility_eod") or row.get("iv_eod") or row.get("contract_iv") or row.get("iv"))
        else ""
    )

    # Bond macro display fields â€” stamped regardless of trade_go verdict
    if bond_state:
        for _bond_field, _bond_val in bond_state.items():
            if _bond_field != "bond_trade_go":  # gate field â€” not exposed in output
                out[_bond_field] = _bond_val
    out["check_bond_macro_pass"]   = "TRUE" if bond_pass else "FALSE"
    out["check_bond_macro_reason"] = bond_reason

    # CF-01/02/03 + AG-07: Macro context display fields â€” non-blocking, display only
    if macro_state:
        out["macro_dir_bias"]   = macro_state.get("dir_bias", "")
        out["macro_risk_switch"] = macro_state.get("risk_on_off_switch", "")
        out["macro_vol_mode"]    = macro_state.get("vol_mode", "")
        out["macro_conviction"]  = macro_state.get("macro_conviction", "")
        out["macro_filter"]      = macro_state.get("macro_filter", "")
        out["macro_as_of_utc"]   = macro_state.get("macro_as_of_utc", "")
        _sl = macro_state.get("sector_lead",  [])
        _sa = macro_state.get("sector_avoid", [])
        out["macro_sector_lead"]  = "; ".join(_sl)  if isinstance(_sl,  list) else _s(_sl)
        out["macro_sector_avoid"] = "; ".join(_sa) if isinstance(_sa, list) else _s(_sa)
        if macro_state.get("vix_spot") is not None:
            out["macro_vix_spot"] = macro_state["vix_spot"]
        # AG-07: Freshness flag â€” purely informational, never blocks or flags verdict
        _as_of = _s(macro_state.get("macro_as_of_utc"))
        if _as_of:
            try:
                _gen_dt = datetime.fromisoformat(_as_of.replace("Z", "+00:00"))
                if _gen_dt.tzinfo is None:
                    _gen_dt = _gen_dt.replace(tzinfo=timezone.utc)
                _age_h = (datetime.now(timezone.utc) - _gen_dt).total_seconds() / 3600
                out["macro_age_hours_gate"] = round(_age_h, 1)
                out["macro_freshness_flag"] = "STALE" if _age_h > MACRO_MAX_AGE_H else "FRESH"
            except Exception:
                out["macro_age_hours_gate"] = ""
                out["macro_freshness_flag"] = "UNKNOWN"
        else:
            out["macro_age_hours_gate"] = ""
            out["macro_freshness_flag"] = "UNKNOWN"
    else:
        out["macro_vol_mode"]       = ""
        out["macro_conviction"]     = ""
        out["macro_filter"]         = ""
        out["macro_as_of_utc"]      = ""
        out["macro_sector_lead"]    = ""
        out["macro_sector_avoid"]   = ""
        out["macro_age_hours_gate"] = ""
        out["macro_freshness_flag"] = "UNAVAILABLE"

    # AG-02: Volume anomaly flag â€” uses scanner_rvol (relative vol, already in row)
    # avg_volume_20d does not exist in morning_candidates; scanner_rvol is the proxy
    _rvol = _f(live_data.get("scanner_rvol") or row.get("scanner_rvol"))
    if _rvol is not None:
        out["volume_anomaly_ratio"] = round(_rvol, 2)
        out["volume_anomaly_flag"]  = "ANOMALY" if _rvol >= 2.0 else "NORMAL"
    else:
        out["volume_anomaly_ratio"] = ""
        out["volume_anomaly_flag"]  = "NO_DATA"

    # AG-01: Earnings catalyst calendar â€” from Polygon snapshot earningsAnnouncement field
    # No extra API call â€” extracted from existing live price fetch
    try:
        from earnings_calendar_enricher import enrich_from_announcement_str
        _earnings_str = _s(live_data.get("live_earnings_announcement") or row.get("earnings_announcement") or "")
        _earnings_fields = enrich_from_announcement_str(_earnings_str)
        out.update(_earnings_fields)
        # AG-01 Step 3: pre-earnings IV note for Options Intelligence display
        if _earnings_fields.get("earnings_catalyst_flag") == "TRUE":
            _days = _earnings_fields.get("earnings_days_to_event", "?")
            _timing = _earnings_fields.get("earnings_timing", "")
            out["pre_earnings_iv_note"] = (
                f"{_timing}: earnings in {_days} day(s) â€” IV skew check required before entry"
            )
        else:
            out["pre_earnings_iv_note"] = ""
    except Exception as _ecal_exc:
        out["earnings_timing"]        = "MODULE_ERROR"
        out["earnings_catalyst_flag"] = "FALSE"
        out["pre_earnings_iv_note"]   = ""
        log.debug("Earnings enricher error (non-fatal): %s", _ecal_exc)

    # AG-04: GARCH vol regime transition discount â€” DISPLAY ONLY, never modifies verdict
    # Original l3_vol_forecast_conf is preserved; adjusted value is the display field
    _raw_conf = _f(out.get("l3_vol_forecast_conf"))
    if vix_regime_transition:
        out["garch_vol_regime_transition"]   = "TRUE"
        out["garch_transition_discount_pct"] = round((1 - _GARCH_TRANSITION_DISCOUNT) * 100, 1)
        if vix_move_pct is not None:
            out["garch_vix_move_pct"] = round(vix_move_pct, 2)
        out["l3_vol_forecast_conf_adjusted"] = (
            round(_raw_conf * _GARCH_TRANSITION_DISCOUNT, 2) if _raw_conf is not None else ""
        )
    else:
        out["garch_vol_regime_transition"]   = "FALSE"
        out["garch_transition_discount_pct"] = 0
        out["l3_vol_forecast_conf_adjusted"] = _raw_conf if _raw_conf is not None else ""

    # AG-08: Enrichment delta bias â€” DISPLAY ONLY confidence modifier (+/- 5%)
    _ENRICHMENT_BOOST = 5.0
    _ticker_upper = _u(row.get("ticker", ""))
    _enrichment_label = (enrichment_bias or {}).get(_ticker_upper, "")
    if _enrichment_label:
        _raw_score = _f(out.get("scs_score") or out.get("confidence_score") or out.get("conf_pct"))
        _adjustment = _ENRICHMENT_BOOST if _enrichment_label == "BULLISH" else -_ENRICHMENT_BOOST
        out["enrichment_delta_bias"]      = _enrichment_label
        out["enrichment_conf_adjustment"] = _adjustment
        if _raw_score is not None:
            out["enrichment_conf_adjusted"] = round(max(0, min(100, _raw_score + _adjustment)), 2)
        else:
            out["enrichment_conf_adjusted"] = ""
        out["enrichment_delta_note"] = (
            f"Macro terminal bias: {_enrichment_label} "
            f"({'+'  if _enrichment_label == 'BULLISH' else ''}{_adjustment:.0f}% conf modifier)"
        )
    else:
        out["enrichment_delta_bias"]      = ""
        out["enrichment_conf_adjustment"] = 0
        out["enrichment_conf_adjusted"]   = ""
        out["enrichment_delta_note"]      = ""

    # AG-03: Options skew direction alignment â€” skew fields already stamped via live_data
    _skew_flag = _u(live_data.get("skew_flag", ""))
    _direction = _u(out.get("evening_direction") or out.get("direction") or "")
    if _skew_flag and _skew_flag not in ("SKEW_UNAVAILABLE", "SKEW_NEUTRAL", ""):
        _skew_aligned = (
            (_skew_flag == "CALL_SKEW_HIGH" and "CALL" in _direction) or
            (_skew_flag == "PUT_SKEW_HIGH"  and "PUT"  in _direction)
        )
        out["skew_direction_alignment"] = "ALIGNED" if _skew_aligned else "MISALIGNED"
        out["skew_alignment_note"] = (
            f"IV skew {_skew_flag} {'aligns' if _skew_aligned else 'conflicts'} "
            f"with direction {_direction}"
        )
    else:
        out["skew_direction_alignment"] = ""
        out["skew_alignment_note"]      = ""

    # AG-05: China revenue exposure modifier â€” DISPLAY ONLY
    _CHINA_CRITICAL_THRESHOLD = 40
    _CHINA_HIGH_THRESHOLD     = 20
    _china_data    = (china_exposure or {}).get(_ticker_upper, {})
    _china_rev_pct = _china_data.get("china_revenue_pct")
    _china_sens    = _s(_china_data.get("china_sensitivity", ""))
    if china_risk_active and _china_rev_pct is not None:
        if _china_rev_pct >= _CHINA_CRITICAL_THRESHOLD:
            _china_modifier = -10.0
            _china_note = (
                f"CHINA CRITICAL: {_china_rev_pct}% revenue exposure. "
                "HK/FXI bearish. -10% conf modifier."
            )
        elif _china_rev_pct >= _CHINA_HIGH_THRESHOLD:
            _china_modifier = -5.0
            _china_note = (
                f"CHINA HIGH: {_china_rev_pct}% revenue exposure. "
                "HK/FXI bearish. -5% conf modifier."
            )
        else:
            _china_modifier = 0.0
            _china_note = f"CHINA LOW: {_china_rev_pct}% revenue exposure. Monitor."
        out["china_revenue_pct"]   = _china_rev_pct
        out["china_sensitivity"]   = _china_sens
        out["china_conf_modifier"] = _china_modifier
        out["china_risk_active"]   = "TRUE"
        out["china_exposure_note"] = _china_note
    else:
        out["china_revenue_pct"]   = _china_rev_pct if _china_rev_pct is not None else ""
        out["china_sensitivity"]   = _china_sens
        out["china_conf_modifier"] = 0
        out["china_risk_active"]   = "TRUE" if china_risk_active else "FALSE"
        out["china_exposure_note"] = ""

    # Verdict and fail-closed authority result. Morning validation may confirm
    # a governed EOD candidate, but it cannot create live capital authority.
    block_reasons = []
    flag_reasons = []
    invalidation_unverified = live_price is None
    lifecycle_transition = _u(out.get("morning_transition_state"))

    if not authority_pass:
        block_reasons.append(authority_reason)
    if not direction_pass:
        block_reasons.append(direction_reason)
    if not economics_pass and not repaired_contract:
        block_reasons.append(economics_reason)
    if not inv_pass:
        if invalidation_unverified:
            flag_reasons.append(inv_reason)
        else:
            block_reasons.append(inv_reason)
    if not strategy_pass:
        block_reasons.append(strategy_reason)
    elif spread_policy_state == "BLOCKED_SPREAD":
        block_reasons.append(spread_policy_reason)
    elif not contract_pass:
        flag_reasons.append(contract_reason)
    if not model_risk["passed"]:
        flag_reasons.append(model_risk["reason"])
    if lifecycle_transition in {"THESIS_INVALIDATED", "MOVE_ALREADY_REALIZED"}:
        block_reasons.append(lifecycle_transition)
    elif lifecycle_transition not in {
        "EXECUTABLE_NOW", "GAP_CONFIRMATION_WITH_RUNWAY",
        "LEGACY_LIFECYCLE_NOT_EVALUATED",
    }:
        flag_reasons.append(lifecycle_transition or "LIFECYCLE_STATE_MISSING")

    if not authority_pass:
        verdict = "BLOCK"
        permission = "BLOCKED"
        morning_permission = "NOT_ELIGIBLE"
        route = "STAND_DOWN_UPSTREAM_AUTHORITY"
        lane = "UPSTREAM_NOT_AUTHORIZED"
        entry_action = "NO_TRADE"
        unlock_condition = authority_reason
    elif not direction_pass:
        verdict = "BLOCK"
        permission = "BLOCKED"
        morning_permission = "NO_GO_DIRECTION"
        route = "STAND_DOWN_DIRECTION"
        lane = "DIRECTION_INTEGRITY_FAILED"
        entry_action = "NO_TRADE"
        unlock_condition = direction_reason
    elif not strategy_pass:
        verdict = "BLOCK"
        permission = "RESEARCH_ONLY"
        morning_permission = "RESEARCH_ONLY"
        route = "OPTIONS_RESEARCH_ONLY"
        lane = "UNSUPPORTED_PRODUCTION_STRUCTURE"
        entry_action = "NO_TRADE"
        unlock_condition = strategy_reason
    elif lifecycle_transition == "THESIS_INVALIDATED":
        verdict = "BLOCK"
        permission = "BLOCKED"
        morning_permission = "BLOCKED"
        route = "STAND_DOWN"
        lane = "THESIS_INVALIDATED"
        entry_action = "NO_TRADE"
        unlock_condition = "Thesis invalidated by morning price action"
    elif lifecycle_transition == "MOVE_ALREADY_REALIZED":
        verdict = "BLOCK"
        permission = "BLOCKED"
        morning_permission = "NO_GO_MOVE_ALREADY_REALIZED"
        route = "STAND_DOWN_NO_CHASE"
        lane = "MOVE_ALREADY_REALIZED"
        entry_action = "NO_TRADE"
        unlock_condition = "The planned underlying move is already substantially realised"
    elif lifecycle_transition == "CONTRACT_REPRICE_REQUIRED":
        verdict = "FLAG"
        permission = "CONTRACT_REPAIR"
        morning_permission = "CONTRACT_REPAIR"
        route = "REPAIR_CONTRACT"
        lane = "CONTRACT_ECONOMICS_RECOMPUTE"
        entry_action = "RECOMPUTE_SELECTED_CONTRACT_ECONOMICS"
        unlock_condition = (
            out.get("liquidity_lifecycle_reason") or contract_reason
            or "Exact selected-contract economics must be recomputed"
        )
    elif not economics_pass:
        verdict = "BLOCK"
        permission = "BLOCKED"
        morning_permission = "NO_GO_ECONOMICS"
        route = "STAND_DOWN_ECONOMICS"
        lane = "NON_MONETISABLE"
        entry_action = "NO_TRADE"
        unlock_condition = economics_reason
    elif invalidation_unverified:
        verdict = "FLAG"
        permission = "WAIT"
        morning_permission = "WAIT"
        route = "WAIT_LIVE_PRICE"
        lane = "LIVE_PRICE_UNAVAILABLE"
        entry_action = "NO_TRADE"
        unlock_condition = inv_reason
    elif not inv_pass:
        verdict = "BLOCK"
        permission = "BLOCKED"
        morning_permission = "BLOCKED"
        route = "STAND_DOWN"
        lane = "THESIS_INVALIDATED"
        entry_action = "NO_TRADE"
        unlock_condition = "Thesis invalidated by morning price action"
    elif lifecycle_transition in {"WAIT_FOR_PULLBACK", "GAP_CONFIRMATION_EXTENDED"}:
        verdict = "FLAG"
        permission = "WAIT"
        morning_permission = "WAIT"
        route = "WAIT_FOR_PULLBACK"
        lane = lifecycle_transition
        entry_action = "NO_TRADE"
        unlock_condition = "Do not chase the overnight extension; require a governed pullback/reconfirmation"
    elif lifecycle_transition == "LIQUIDITY_STILL_PENDING":
        verdict = "FLAG"
        permission = "WAIT"
        morning_permission = "LIQUIDITY_STILL_PENDING"
        route = "MONITOR_CONTRACT_LIQUIDITY"
        lane = _u(out.get("liquidity_state")) or "LIQUIDITY_PENDING"
        entry_action = "NO_TRADE"
        unlock_condition = "Wait for a fresh executable two-sided quote on the exact contract"
    elif spread_policy_state == "BLOCKED_SPREAD":
        verdict = "BLOCK"
        permission = "BLOCKED"
        morning_permission = "NO_GO_LIQUIDITY"
        route = "STAND_DOWN_LIQUIDITY"
        lane = "SPREAD_ABOVE_HARD_MAXIMUM"
        entry_action = "NO_TRADE"
        unlock_condition = spread_policy_reason
    elif spread_policy_state == "MANUAL_LIQUIDITY_REVIEW":
        verdict = "FLAG"
        permission = "MANUAL_LIQUIDITY_REVIEW"
        morning_permission = "MANUAL_LIQUIDITY_REVIEW"
        route = "MANUAL_LIQUIDITY_REVIEW"
        lane = "SPREAD_REVIEW_18_TO_25"
        entry_action = "NO_TRADE_UNTIL_LIQUIDITY_APPROVED"
        unlock_condition = spread_policy_reason
    elif not contract_pass:
        verdict = "FLAG"
        permission = "CONTRACT_REPAIR"
        morning_permission = "CONTRACT_REPAIR"
        route = "REPAIR_CONTRACT"
        lane = "CONTRACT_REPAIR"
        entry_action = "SELECT_LIQUID_CONTRACT"
        unlock_condition = contract_reason
    elif not model_risk["passed"]:
        verdict = "FLAG"
        permission = "MODEL_RISK_REVIEW"
        morning_permission = "MODEL_RISK_REVIEW"
        route = "MODEL_RISK_REVIEW"
        lane = "MODEL_RISK_REVIEW"
        entry_action = "MANUAL_REVIEW"
        unlock_condition = model_risk["reason"]
    elif flag_reasons:
        verdict = "FLAG"
        permission = "ARMED"
        morning_permission = "REVIEW_REQUIRED"
        route = "REVIEW_BEFORE_ENTRY"
        lane = "REVIEW_BEFORE_ENTRY"
        entry_action = "MANUAL_REVIEW"
        unlock_condition = "; ".join(flag_reasons)
    else:
        verdict = "GO"
        permission = "HUMAN_APPROVAL_REQUIRED"
        # GO_LIMIT is the existing Pipeline Interpreter handoff vocabulary.
        # It means eligible for a human-reviewed limit entry, not live capital
        # authority; execution_permission/final_capital_permission below retain
        # the explicit human-approval boundary.
        morning_permission = "GO_LIMIT"
        route = "GO_LIMIT"
        lane = "MORNING_VALIDATED"
        entry_action = "REVIEW_AND_SIZE_LIMIT"
        unlock_condition = "Live validation passed; human approval and size are still required"

    out["verdict"] = verdict
    out["block_reason"] = "; ".join(block_reasons)
    out["flag_reason"] = "; ".join(flag_reasons)

    # Lab compatibility aliases - field names the Intelligence Lab reads.
    out["morning_gate_verdict"] = verdict
    out["execution_permission"] = permission
    out["morning_execution_permission"] = morning_permission
    out["morning_execution_route"] = route
    out["morning_execution_lane"] = lane
    out["morning_entry_action"] = entry_action
    out["morning_unlock_condition"] = unlock_condition
    out["live_validation_state"] = "CONFIRMED" if verdict == "GO" else morning_permission
    out["evening_capital_permission"] = _u(
        row.get("capital_permission") or row.get("live_capital_permission")
    )
    out["morning_validation_result"] = verdict
    from domain.execution_authority import morning_validation_authority_fields
    out.update(morning_validation_authority_fields(verdict))

    live_mid = _f(out.get("live_contract_mid"))
    live_spread = _f(out.get("live_contract_spread_pct"))
    if live_mid is not None and live_mid > 0:
        out["premium_mid"] = live_mid
        out["contract_mid"] = live_mid
    if live_spread is not None:
        out["spread_pct"] = live_spread / 100.0 if live_spread > 1 else live_spread
        out["contract_spread_pct"] = out["spread_pct"]

    # Nested leg dictionaries are internal calculation objects. The governed
    # JSON representation remains in selected_legs_json for CSV consumers.
    out.pop("selected_long_leg", None)
    out.pop("selected_short_leg", None)

    # v6 actuarial display fields â€” pass-through from EOD manifest
    # These are informational context for the trader and Intelligence Lab.
    # They NEVER gate the verdict.
    for _v6_field in V6_ACTUARIAL_DISPLAY_FIELDS:
        if _v6_field in row and _v6_field not in out:
            out[_v6_field] = row[_v6_field]

    # Current evidence may invalidate, defer or require a new contract episode;
    # it cannot silently rewrite the published direction, horizon or geometry.
    assert_frozen_thesis_fields(row, out)
    return out


def _persist_morning_liquidity_result(
    result: Dict[str, Any],
    run_id: str,
    registry: Any,
    store: Any,
) -> None:
    """Write the fresh MarketData quote and morning lifecycle transition to CDS."""
    from canonical_data import (
        CompletenessStatus,
        ContractLiquidityState,
        DataScope,
        DatasetRecord,
        DatasetType,
        MonitorState,
        ThesisState,
    )

    thesis_id = _s(result.get("thesis_id"))
    ticker = _u(result.get("ticker"))
    side = _side(result.get("final_direction") or result.get("direction"))
    if not thesis_id or not ticker or side not in {"CALL", "PUT"}:
        result["morning_liquidity_persistence_status"] = "SKIPPED_NO_GOVERNED_THESIS"
        return
    transition = _u(result.get("morning_transition_state"))
    thesis_state = (
        ThesisState.INVALIDATED if transition == "THESIS_INVALIDATED"
        else ThesisState.TARGET_REALIZED if transition == "MOVE_ALREADY_REALIZED"
        else ThesisState.ACTIVE
    )
    monitor_state = (
        MonitorState.TERMINAL if thesis_state in {ThesisState.INVALIDATED, ThesisState.TARGET_REALIZED}
        else MonitorState.NOT_REQUIRED if transition in {"EXECUTABLE_NOW", "GAP_CONFIRMATION_WITH_RUNWAY"}
        else MonitorState.ACTIVE
    )
    # A Morning Gate may be rerun against the same EOD run_id as quotes evolve.
    # Make each materially different observation append-only, while retaining
    # idempotency when the exact same result is replayed.
    event_evidence = {
        "transition": transition,
        "contract": result.get("morning_selected_contract_symbol") or result.get("contract_symbol"),
        "provider_updated": result.get("live_contract_provider_updated"),
        "fetched_at": result.get("live_options_fetched_at"),
        "spot": result.get("live_price"),
        "bid": result.get("live_contract_bid"),
        "ask": result.get("live_contract_ask"),
    }
    event_token = hashlib.sha256(
        json.dumps(event_evidence, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    latest_thesis = store.latest_thesis(thesis_id)
    terminal_transition = thesis_state in {
        ThesisState.INVALIDATED,
        ThesisState.TARGET_REALIZED,
    }
    if latest_thesis is not None and latest_thesis.thesis_state in {
        ThesisState.INVALIDATED,
        ThesisState.TARGET_REALIZED,
    }:
        result["morning_liquidity_persistence_status"] = "TERMINAL_REPLAY_REUSED"
        return

    def record_transition(
        state: Any,
        monitor: Any,
        event_key: str,
        reason: str,
    ) -> None:
        current = store.latest_thesis(thesis_id)
        store.record_thesis_event(
            thesis_id=thesis_id,
            event_key=event_key,
            run_id=run_id,
            ticker=ticker,
            direction=side,
            thesis_state=state,
            monitor_state=monitor,
            reason_code=reason,
            structural_target=_f(result.get("structural_target") or result.get("target_price")),
            invalidation_spot=_f(result.get("invalidation_spot") or result.get("invalidation_price") or result.get("invalidation_level")),
            horizon_end_date=current.horizon_end_date if current else None,
            expected_version=current.version if current else None,
            metadata={"execution_authorized": False, "maturation_execution_authority": False},
            calculation_version="options-liquidity-morning-v2",
        )

    def close_terminal_transition() -> None:
        if terminal_transition:
            record_transition(
                thesis_state,
                MonitorState.TERMINAL,
                f"MORNING:{run_id}:{event_token}",
                transition or "MORNING_TERMINAL_LIFECYCLE_RECORDED",
            )

    # A terminal transition's final quote must be appended while the thesis is
    # still active.  Closing first makes the store correctly reject the quote.
    if terminal_transition and latest_thesis is None:
        record_transition(
            ThesisState.ACTIVE,
            MonitorState.ACTIVE,
            f"MORNING_PRE_TERMINAL:{run_id}:{event_token}",
            "MORNING_TERMINAL_OBSERVATION_STAGED",
        )
    elif not terminal_transition:
        record_transition(
            thesis_state,
            monitor_state,
            f"MORNING:{run_id}:{event_token}",
            transition or "MORNING_LIFECYCLE_RECORDED",
        )

    contract_symbol = _s(
        result.get("morning_selected_contract_symbol") or result.get("contract_symbol")
        or result.get("recommended_contract")
    )
    quote_as_of = _parse_utc_datetime(
        result.get("live_contract_provider_updated")
        or result.get("live_options_fetched_at")
        or result.get("quote_as_of")
    )
    if not contract_symbol or quote_as_of is None or _u(result.get("live_options_source")) != "MARKETDATA":
        close_terminal_transition()
        result["morning_liquidity_persistence_status"] = "THESIS_ONLY_NO_CANONICAL_LIVE_QUOTE"
        return
    try:
        occ = parse_occ_symbol(contract_symbol)
        liquidity_state = ContractLiquidityState[_u(result.get("liquidity_state"))]
    except (ValueError, KeyError):
        close_terminal_transition()
        result["morning_liquidity_persistence_status"] = "THESIS_ONLY_QUOTE_IDENTITY_INVALID"
        return
    # MSI has already normalised and registered this exact MarketData response.
    # Reuse that immutable dataset instead of creating a second LIVE_OPTION
    # wrapper with different field names for the same provider quote.
    dataset_id = _s(result.get("msi_exact_quote_dataset_id"))
    exact_record = registry.get_dataset(dataset_id) if dataset_id else None
    exact_dataset_valid = bool(
        exact_record
        and exact_record.dataset_type == DatasetType.EXACT_OPTION_QUOTE
        and _u(exact_record.provider) == "MARKETDATA"
        and _u(exact_record.instrument_id) == ticker
    )
    if not exact_dataset_valid:
        payload = {
            key: result.get(key)
            for key in (
                "ticker", "contract_symbol", "morning_selected_contract_symbol",
                "live_contract_bid", "live_contract_ask", "live_contract_mid",
                "live_contract_spread_pct", "live_contract_delta", "live_contract_gamma",
                "live_contract_theta", "live_contract_vega", "live_contract_iv",
                "live_contract_oi", "live_contract_volume", "live_options_source",
                "live_options_fetched_at", "live_contract_provider_updated",
            )
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        content_hash = hashlib.sha256(encoded).hexdigest()
        dataset_id = hashlib.sha256(
            f"LIVE_OPTION|{ticker}|{contract_symbol}|{quote_as_of.isoformat()}|{content_hash}".encode("utf-8")
        ).hexdigest()
        payload_dir = ROOT / "data" / "canonical" / "live_options" / quote_as_of.date().isoformat() / ticker
        payload_dir.mkdir(parents=True, exist_ok=True)
        payload_path = payload_dir / f"{dataset_id}.json"
        if not payload_path.exists():
            temporary = payload_path.with_suffix(".tmp")
            temporary.write_bytes(encoded)
            os.replace(temporary, payload_path)
        scope = DataScope(
            start_date=quote_as_of.date(),
            end_date=quote_as_of.date(),
            fields=tuple(payload.keys()),
            sides=(side,),
            extra=(("contract_symbol", contract_symbol.replace("O:", "")),),
        )
        registry.register_dataset(DatasetRecord(
            dataset_id=dataset_id,
            dataset_type=DatasetType.LIVE_OPTION,
            instrument_id=ticker,
            session_date=quote_as_of.date(),
            scope=scope,
            provider="MARKETDATA",
            content_hash=content_hash,
            completeness_status=CompletenessStatus.COMPLETE,
            storage_uri=str(payload_path.resolve()),
            # Deterministic observed_at keeps an identical quote replay idempotent.
            observed_at=quote_as_of,
            as_of=quote_as_of,
            adjustment_convention="RAW_OPTION_CONTRACT",
            schema_version="live_option_quote_v1",
            source_run_id=run_id,
        ))
    result["selected_quote_dataset_id"] = dataset_id
    expiration = date.fromisoformat(occ["expiry"])
    dte = max(0, (expiration - quote_as_of.date()).days)
    spread_pct = _f(result.get("live_contract_spread_pct"))
    live_spot = _f(result.get("live_price"))
    if live_spot is None or live_spot <= 0:
        close_terminal_transition()
        result["morning_liquidity_persistence_status"] = "THESIS_ONLY_LIVE_SPOT_INVALID"
        return
    observation = store.record_contract_observation(
        thesis_id=thesis_id,
        run_id=run_id,
        ticker=ticker,
        contract_symbol=contract_symbol,
        option_side=side,
        quote_as_of=quote_as_of,
        source_dataset_id=dataset_id,
        spot=float(live_spot),
        strike=float(occ["strike"]),
        expiration=expiration,
        dte=float(dte),
        delta=_f(result.get("live_contract_delta")),
        bid=_f(result.get("live_contract_bid")),
        ask=_f(result.get("live_contract_ask")),
        spread_pct=(spread_pct / 100.0 if spread_pct is not None and spread_pct > 1 else spread_pct),
        volume=_f(result.get("live_contract_volume")),
        open_interest=_f(result.get("live_contract_oi")),
        iv=_f(result.get("live_contract_iv")),
        liquidity_state=liquidity_state,
        maturation_score_1d=_f(result.get("maturation_score_1d")),
        maturation_score_2d=_f(result.get("maturation_score_2d")),
        maturation_score_3d=_f(result.get("maturation_score_3d")),
        maturation_score_is_probability=False,
        atm_distance_sigma=_f(result.get("atm_distance_sigma")),
        remaining_runway_pct=_f(result.get("remaining_runway_pct")),
        calculation_version="options-liquidity-morning-v2",
    )
    # An unchanged provider quote can legitimately reuse the EOD observation,
    # whose canonical source predates the MSI Morning wrapper.
    result["selected_quote_dataset_id"] = observation.record.source_dataset_id
    economics_value = result.get("selected_contract_economics_ready", True)
    economics_ready = (
        economics_value if isinstance(economics_value, bool) else _truthy(economics_value)
    )
    if _truthy(result.get("contract_changed")) and not economics_ready:
        close_terminal_transition()
        result["morning_liquidity_persistence_status"] = "OBSERVED_REPRICE_REQUIRED"
        return
    latest_selection = store.latest_selection(thesis_id)
    previous_selection_symbol = _s(result.get("previous_contract_symbol"))
    if not previous_selection_symbol and not _truthy(result.get("contract_changed")):
        previous_selection_symbol = contract_symbol
    store.record_selection_event(
        thesis_id=thesis_id,
        event_key=f"MORNING_SELECTION:{run_id}:{event_token}",
        run_id=run_id,
        previous_contract_symbol=previous_selection_symbol or None,
        selected_contract_symbol=contract_symbol,
        selected_observation_id=observation.record.observation_id,
        selection_reason=_s(result.get("contract_selection_reason")) or "MORNING_EXACT_CONTRACT_REQUOTE",
        economics_recomputed=economics_ready,
        expected_version=latest_selection.selection_version if latest_selection else None,
        metadata={"morning_transition_state": transition},
        calculation_version="options-liquidity-morning-v2",
    )
    close_terminal_transition()
    result["morning_liquidity_persistence_status"] = (
        "PERSISTED_TERMINAL_CLOSED" if terminal_transition else "PERSISTED"
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def run_morning_gate(
    run_id: str,
    spread_threshold: float = DEFAULT_SPREAD_THRESHOLD,
    execution_mode: str = "POSTOPEN_CONTRACT_REFRESH",
) -> List[Dict[str, Any]]:

    execution_mode = _u(execution_mode)
    if execution_mode not in {"PREOPEN_THESIS_CHECK", "POSTOPEN_CONTRACT_REFRESH"}:
        raise ValueError(f"unsupported Morning execution_mode: {execution_mode}")
    now_et = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
    minute_of_day = now_et.hour * 60 + now_et.minute
    refresh_window_state = (
        "NOT_APPLICABLE_PREOPEN"
        if execution_mode == "PREOPEN_THESIS_CHECK"
        else "DEFAULT_WINDOW"
        if 9 * 60 + 35 <= minute_of_day <= 9 * 60 + 45
        else "PERMITTED_LATE_REFRESH"
    )

    run_dir    = RUNS_DIR / run_id
    mv_dir     = run_dir / "morning_validation"
    input_path = mv_dir / f"morning_candidates_{run_id}.csv"
    output_path = mv_dir / f"morning_validated_trades_{run_id}.csv"
    summary_path = mv_dir / f"morning_gate_summary_{run_id}.json"

    if not input_path.exists():
        log.error("morning_candidates not found: %s", input_path)
        raise FileNotFoundError(str(input_path))

    candidates = _read_csv(input_path)
    log.info("Loaded %d candidates from %s", len(candidates), input_path.name)

    # Production Morning Gate shares the existing CDS control-plane database.
    # It records observations and transitions only; it cannot authorise trades.
    liquidity_registry = None
    liquidity_store = None
    liquidity_enforced = False
    msi_observation_resolver = None
    msi_session_date: Optional[date] = None
    try:
        from canonical_data import (
            CanonicalFeatureFlags,
            CanonicalRegistry,
            OptionLiquidityLifecycleStore,
        )

        liquidity_flags = CanonicalFeatureFlags.from_environment()
        liquidity_enforced = liquidity_flags.stage_gating_enforced
        if liquidity_flags.enabled and liquidity_flags.write_through:
            liquidity_registry = CanonicalRegistry(
                ROOT / "data" / "canonical" / "control_plane.sqlite"
            )
            liquidity_registry.initialise()
            with liquidity_registry.connection() as connection:
                run_registered = connection.execute(
                    "SELECT 1 FROM run_registry WHERE run_id = ?", (run_id,)
                ).fetchone()
            if run_registered is None:
                liquidity_registry.register_run(
                    run_id,
                    "MORNING",
                    date.today(),
                    metadata={"source": "morning_gate", "execution_authority": False},
                )
            liquidity_store = OptionLiquidityLifecycleStore(liquidity_registry)
            liquidity_store.initialise()
            log.info("Options liquidity lifecycle CDS write-through enabled")
    except Exception as liquidity_setup_error:
        if liquidity_enforced:
            raise RuntimeError(
                f"Morning liquidity lifecycle CDS setup failed closed: {liquidity_setup_error}"
            ) from liquidity_setup_error
        log.warning(
            "Morning liquidity lifecycle CDS unavailable; display evaluation continues: %s",
            liquidity_setup_error,
        )

    msi_flags = active_msi_flags()
    if msi_flags.v2_capture:
        if liquidity_registry is None or liquidity_store is None:
            raise RuntimeError(
                "MSI v2 capture is enabled but the canonical Morning store is unavailable"
            )
        from canonical_data import (
            CanonicalMarketObservationResolver,
            DatasetType,
            publish_observation_worklist,
            session_snapshot,
        )

        snapshot = session_snapshot()
        msi_session_date = snapshot.session_date or snapshot.last_completed_session
        publication = publish_observation_worklist(
            liquidity_registry,
            run_id=run_id,
            stage="MORNING_GATE",
            tickers=(_u(row.get("ticker")) for row in candidates),
            dataset_types=(
                (DatasetType.UNDERLYING_NBBO,)
                if execution_mode == "PREOPEN_THESIS_CHECK"
                else (DatasetType.EXACT_OPTION_QUOTE, DatasetType.UNDERLYING_NBBO)
            ),
        )
        if not publication.reconciled:
            raise RuntimeError("MSI Morning observation worklist did not reconcile")
        msi_observation_resolver = CanonicalMarketObservationResolver(
            registry_path=ROOT / "data" / "canonical" / "control_plane.sqlite",
            payload_root=ROOT / "data" / "canonical" / "market_observations",
            run_id=run_id,
            flags=liquidity_flags,
        )
        log.info(
            "MSI v2 Morning capture enabled: session=%s authorised=%d excluded=%d",
            msi_session_date,
            publication.authorised_count,
            publication.excluded_count,
        )

    # Load current macro state (CF-01/02/03 â€” full dict replaces old string-only load)
    macro_state    = _load_macro_state()
    current_regime = macro_state.get("regime_state", "UNKNOWN")
    log.info(
        "Macro state loaded â€” regime=%s vol_mode=%s conviction=%s loaded=%s",
        current_regime,
        macro_state.get("vol_mode", ""),
        macro_state.get("macro_conviction", ""),
        macro_state.get("macro_loaded", False),
    )

    bond_state = _load_bond_macro()
    if bond_state:
        log.info(
            "Bond macro loaded â€” trade_go=%s score=%s flag=%s",
            bond_state.get("bond_trade_go"),
            bond_state.get("bond_macro_score"),
            bond_state.get("bond_macro_flag"),
        )
    else:
        log.info("Bond macro state not available â€” Check 4 will be skipped")

    # AG-08: Enrichment delta bias catalogue
    enrichment_bias = _load_enrichment_delta()
    log.info(
        "Enrichment delta: %d tickers biased (%d BEARISH, %d BULLISH)",
        len(enrichment_bias),
        sum(1 for v in enrichment_bias.values() if v == "BEARISH"),
        sum(1 for v in enrichment_bias.values() if v == "BULLISH"),
    )

    # AG-05: China risk flag â€” active when FXI or EWH is BEARISH in enrichment delta
    china_risk_active = (
        enrichment_bias.get("FXI") == "BEARISH"
        or enrichment_bias.get("EWH") == "BEARISH"
    )
    china_exposure = _load_china_exposure()
    log.info(
        "China risk: active=%s  exposure_tickers=%d",
        china_risk_active, len(china_exposure),
    )

    # AG-04: VIX regime transition check â€” display modifier for GARCH confidence
    vix_regime_transition = False
    vix_move_pct: Optional[float] = None
    try:
        _macro_raw = json.loads(MACRO_PATH.read_text(encoding="utf-8-sig"))
        _vix_spot  = _f(_macro_raw.get("vix_spot"))
        _vix_prev  = _f(_macro_raw.get("vix_prev_close"))
        if _vix_spot and _vix_spot > 0 and _vix_prev and _vix_prev > 0:
            vix_move_pct = abs((_vix_spot - _vix_prev) / _vix_prev) * 100
            if vix_move_pct >= _VIX_REGIME_THRESHOLD_PCT:
                vix_regime_transition = True
                log.warning(
                    "VIX REGIME TRANSITION: move=%.1f%% (spot=%.2f prev=%.2f) â€” "
                    "GARCH confidence discount %.0f%% applied to display fields",
                    vix_move_pct, _vix_spot, _vix_prev,
                    (1 - _GARCH_TRANSITION_DISCOUNT) * 100,
                )
            else:
                log.info("VIX regime stable: move=%.1f%% (below %.0f%% threshold)", vix_move_pct, _VIX_REGIME_THRESHOLD_PCT)
        else:
            log.info("VIX regime check skipped: vix_spot=%s vix_prev_close=%s (one or both absent)", _vix_spot, _vix_prev)
    except Exception as _vix_exc:
        log.info("VIX regime check skipped: %s", _vix_exc)

    # Fetch all live data
    log.info("Fetching live data for %d tickers...", len(candidates))
    live_map = _fetch_all_live(
        candidates,
        spread_threshold=spread_threshold,
        liquidity_store=liquidity_store,
        msi_observation_resolver=msi_observation_resolver,
        msi_session_date=msi_session_date,
        execution_mode=execution_mode,
    )
    if msi_flags.structure and not msi_flags.minute_bars:
        raise RuntimeError("MSI_STRUCTURE requires MSI_MINUTE_BARS")

    # Run gate
    results: List[Dict[str, Any]] = []
    for row in candidates:
        ticker    = _u(row.get("ticker", ""))
        live_data = live_map.get(ticker, {})
        result    = run_gate(
            row, live_data, current_regime, spread_threshold,
            bond_state=bond_state,
            macro_state=macro_state,
            vix_regime_transition=vix_regime_transition,
            vix_move_pct=vix_move_pct,
            enrichment_bias=enrichment_bias,
            china_risk_active=china_risk_active,
            china_exposure=china_exposure,
        )
        result["morning_execution_mode"] = execution_mode
        if execution_mode == "PREOPEN_THESIS_CHECK":
            result["morning_quote_evidence_state"] = "HISTORICAL"
            result["execution_viability_state"] = "NOT_EVALUATED_PREOPEN"
            result["execution_viability_eligible"] = False
            result["capital_permission"] = "NONE"
        if (
            execution_mode == "POSTOPEN_CONTRACT_REFRESH"
            and liquidity_registry is not None
            and liquidity_store is not None
        ):
            try:
                _persist_morning_liquidity_result(
                    result, run_id, liquidity_registry, liquidity_store
                )
            except Exception as liquidity_persist_error:
                result["morning_liquidity_persistence_status"] = (
                    f"ERROR:{type(liquidity_persist_error).__name__}"
                )
                if liquidity_enforced:
                    raise RuntimeError(
                        "Morning liquidity lifecycle persistence failed closed for "
                        f"{ticker}: {liquidity_persist_error}"
                    ) from liquidity_persist_error
                log.warning(
                    "Morning liquidity lifecycle persistence failed for %s: %s",
                    ticker,
                    liquidity_persist_error,
                )
        results.append(result)

    # Structure is intentionally calculated after the Morning decision.  It is
    # advisory context for the trader and therefore cannot alter GO/BLOCK,
    # direction, contract selection or capital permission.  Request only the
    # governed GO population that the Interpreter/Lab will actually display.
    structure_summary = {"eligible": 0, "calculated": 0, "unavailable": 0}
    if msi_flags.minute_bars and msi_flags.structure:
        if liquidity_registry is None:
            raise RuntimeError(
                "MSI market structure is enabled but the canonical registry is unavailable"
            )
        (
            structure_worklist_tickers,
            structure_candidates,
            structure_live_map,
        ) = _market_structure_populations(results, live_map)
        if structure_candidates:
            structure_summary = _enrich_msi_market_structure(
                run_id=run_id,
                candidates=structure_candidates,
                live_map=structure_live_map,
                worklist_tickers=structure_worklist_tickers,
                registry=liquidity_registry,
                canonical_flags=liquidity_flags,
            )
        log.info(
            "MSI market structure (post-decision advisory): "
            "eligible=%d calculated=%d unavailable=%d",
            structure_summary["eligible"],
            structure_summary["calculated"],
            structure_summary["unavailable"],
        )

    # Write output
    _write_csv(output_path, results)
    log.info("Output written: %s", output_path)

    # Summary
    go_list    = [r for r in results if r["verdict"] == "GO"]
    flag_list  = [r for r in results if r["verdict"] == "FLAG"]
    block_list = [r for r in results if r["verdict"] == "BLOCK"]

    repair_resolved_count = sum(
        1 for r in results
        if _s(r.get("contract_repair_resolved_at_open")).upper() == "TRUE"
    )
    liquidity_persisted_count = sum(
        1 for r in results
        if _u(r.get("morning_liquidity_persistence_status")) == "PERSISTED"
    )

    _sl_summary = macro_state.get("sector_lead",  [])
    _sa_summary = macro_state.get("sector_avoid", [])
    quote_timestamp_distribution: Dict[str, int] = {}
    quote_timestamp_hour_distribution: Dict[str, int] = {}
    quote_timestamp_missing = 0
    for observed in results:
        provider_timestamp = _normalise_provider_timestamp(
            observed.get("quote_provider_timestamp_utc")
            or observed.get("live_contract_provider_updated")
            or observed.get("morning_quote_timestamp_utc")
        )
        if not provider_timestamp:
            quote_timestamp_missing += 1
            continue
        session_key = provider_timestamp[:10]
        hour_key = provider_timestamp[:13] + ":00Z"
        quote_timestamp_distribution[session_key] = quote_timestamp_distribution.get(session_key, 0) + 1
        quote_timestamp_hour_distribution[hour_key] = quote_timestamp_hour_distribution.get(hour_key, 0) + 1

    summary = {
        "run_id":           run_id,
        "validated_at_utc": _utc_now(),
        "morning_execution_mode": execution_mode,
        "postopen_contract_refresh_window_state": refresh_window_state,
        "postopen_contract_refresh_observed_at_et": now_et.isoformat(),
        "quote_provider_timestamp_session_distribution": quote_timestamp_distribution,
        "quote_provider_timestamp_hour_distribution": quote_timestamp_hour_distribution,
        "quote_provider_timestamp_missing_count": quote_timestamp_missing,
        "quote_provider_timestamp_present_count": len(results) - quote_timestamp_missing,
        "input_candidates": len(candidates),
        "go_count":         len(go_list),
        "flag_count":       len(flag_list),
        "block_count":      len(block_list),
        "contract_repair_resolved_count": repair_resolved_count,
        "liquidity_lifecycle_write_through_enabled": liquidity_store is not None,
        "liquidity_lifecycle_persisted_count": liquidity_persisted_count,
        "msi_structure_eligible_count": structure_summary["eligible"],
        "msi_structure_calculated_count": structure_summary["calculated"],
        "msi_structure_unavailable_count": structure_summary["unavailable"],
        "current_regime":      current_regime,
        "macro_vol_mode":      macro_state.get("vol_mode", "UNAVAILABLE"),
        "macro_conviction":    macro_state.get("macro_conviction", "UNAVAILABLE"),
        "macro_filter":        macro_state.get("macro_filter", "UNAVAILABLE"),
        "macro_sector_lead":   "; ".join(_sl_summary)  if isinstance(_sl_summary,  list) else _s(_sl_summary),
        "macro_sector_avoid":  "; ".join(_sa_summary) if isinstance(_sa_summary, list) else _s(_sa_summary),
        "macro_as_of_utc":     macro_state.get("macro_as_of_utc", "UNAVAILABLE"),
        "macro_loaded":        macro_state.get("macro_loaded", False),
        "bond_macro_trade_go":   bond_state.get("bond_trade_go", "UNAVAILABLE"),
        "bond_macro_score":      bond_state.get("bond_macro_score", "UNAVAILABLE"),
        "bond_macro_flag":       bond_state.get("bond_macro_flag", "UNAVAILABLE"),
        "bond_macro_curve":      bond_state.get("bond_curve_state", "UNAVAILABLE"),
        "bond_macro_credit":     bond_state.get("bond_credit_stress", "UNAVAILABLE"),
        "bond_macro_loaded":     bond_state.get("bond_macro_loaded", "FALSE"),
        "go_tickers":       [r.get("ticker") for r in go_list],
        "flag_tickers":     [r.get("ticker") for r in flag_list],
        "block_tickers":    [r.get("ticker") for r in block_list],
        # v6 field coverage â€” confirms pass-through is working
        "v6_field_coverage": {
            field: {
                "present_in_go":    sum(1 for r in go_list    if _s(r.get(field))),
                "present_in_flag":  sum(1 for r in flag_list  if _s(r.get(field))),
                "present_in_block": sum(1 for r in block_list if _s(r.get(field))),
            }
            for field in V6_ACTUARIAL_DISPLAY_FIELDS
        },
        "output_path":      str(output_path),
    }
    _write_json(summary_path, summary)

    # Print
    print("\n" + "=" * 60)
    print("  MORNING GATE RESULTS")
    print("=" * 60)
    _vol_mode   = macro_state.get("vol_mode", "")      if macro_state else ""
    _conviction = macro_state.get("macro_conviction") if macro_state else None
    _macro_filter = macro_state.get("macro_filter", "") if macro_state else ""
    _regime_line = f"  Regime  : {current_regime}"
    if _vol_mode:
        _regime_line += f"  vol_mode={_vol_mode}"
    if _conviction is not None:
        _regime_line += f"  conviction={_conviction:.2f}"
    if _macro_filter:
        _regime_line += f"  filter={_macro_filter}"
    print(f"  Run ID  : {run_id}")
    print(_regime_line)
    bond_flag  = bond_state.get("bond_macro_flag",  "UNAVAILABLE") if bond_state else "UNAVAILABLE"
    bond_score = bond_state.get("bond_macro_score", "N/A")         if bond_state else "N/A"
    bond_go    = bond_state.get("bond_trade_go",    "N/A")         if bond_state else "N/A"
    print(f"  Bond    : {bond_flag}  score={bond_score}  trade_go={bond_go}")
    print(f"  Total   : {len(candidates)}")
    print(f"  GO      : {len(go_list)}")
    print(f"  FLAG    : {len(flag_list)}  (trader reviews before entry)")
    print(f"  BLOCK   : {len(block_list)}  (thesis broken â€” no trade)")
    print(f"  REPAIRED: {repair_resolved_count}  (EOD alternatives passed live contract gate)")
    print()

    if go_list:
        # Group GO list by sector for manual macro alignment review
        sector_map: Dict[str, List[Dict[str, Any]]] = {}
        for r in go_list:
            sector = _s(
                r.get("gics_sector")
                or r.get("sector_name")
                or r.get("sector")
                or r.get("gics_sector_name")
                or r.get("sector_etf")
                or r.get("scanner_sector")
                or "UNKNOWN"
            ).upper() or "UNKNOWN"
            sector_map.setdefault(sector, []).append(r)

        print("  GO LIST â€” BY SECTOR:")
        for sector in sorted(sector_map.keys()):
            tickers = sector_map[sector]
            print(f"\n  [{sector}]  ({len(tickers)} tickers)")
            for r in sorted(tickers, key=lambda x: -(float(_s(x.get("scs_score") or x.get("priority_score") or "0") or 0))):
                tier      = _s(r.get("structural_tier") or r.get("tier") or "?")
                scs       = _s(r.get("scs_score") or r.get("priority_score") or "?")
                direction = _s(r.get("evening_direction") or r.get("direction") or "?")
                print(f"    {r['ticker']:<6} [{tier}]  {direction}  SCS={scs}  {r['check_contract_reason']}")

    if flag_list:
        print()
        print("  FLAG LIST (review before entry):")
        for r in flag_list:
            print(f"    {r['ticker']:<6}  {r['flag_reason']}")

    print()
    print(f"  Output: {output_path}")
    print("=" * 60 + "\n")

    print(json.dumps(summary, indent=2))

    # Morning Gate can only validate the handoff it has completed. The Lab is
    # materialised later, so its comparison is explicitly left to post-Lab QA.
    integrity = _normalise_score_integrity(
        run_dir,
        run_id,
        _check_morning_handoff_score_integrity(run_id, candidates, results),
    )
    log.info(
        "Morning score integrity: compared=%d mismatches=%d rate=%.1f%% pass=%s; Lab=%s",
        integrity.get("compared", 0),
        integrity.get("mismatches", 0),
        integrity.get("mismatch_rate", 0) * 100,
        integrity.get("integrity_pass", "UNKNOWN"),
        integrity.get("lab_score_integrity_status", "UNKNOWN"),
    )

    summary["score_integrity_status"] = integrity.get(
        "integrity_status", "NOT_EVALUATED"
    )
    summary["score_integrity_compared"] = int(integrity.get("compared", 0) or 0)
    summary["score_integrity_pass"] = bool(integrity.get("integrity_pass", False))
    _write_json(summary_path, summary)
    _close_final_run_manifest(run_dir, run_id, summary, integrity)

    return results


def _fetch_marketdata_five_minute_bars(
    ticker: str,
    start_utc: datetime,
    end_utc: datetime,
) -> Any:
    """Fetch governed five-minute MarketData candles for the active session."""
    from canonical_data import MarketDataStockCandleAdapter, session_snapshot

    snapshot = session_snapshot()
    session_date = snapshot.session_date or snapshot.last_completed_session
    return MarketDataStockCandleAdapter(
        MARKETDATA_API_KEY, timeout_seconds=LIVE_FETCH_TIMEOUT
    ).fetch_range(
        ticker,
        start_utc,
        end_utc,
        session_date=session_date,
        interval_minutes=5,
        session_segment="REGULAR",
    )


def _market_structure_populations(
    results: List[Dict[str, Any]],
    live_map: Dict[str, Dict[str, Any]],
) -> tuple[tuple[str, ...], List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Separate stable acquisition authority from the changing GO population.

    A repeated Morning Gate invocation is expected to change GO/FLAG/BLOCK as
    prices develop.  The canonical worklist is therefore the stable Morning
    candidate universe, while provider acquisition and calculation remain
    limited to the current GO subset.  This preserves restart idempotency
    without fetching data for candidates that are not currently displayed.
    """
    worklist_tickers = tuple(
        sorted(
            {
                _u(row.get("ticker"))
                for row in results
                if _u(row.get("ticker")) and _u(row.get("ticker")) in live_map
            }
        )
    )
    calculation_candidates = [
        row
        for row in results
        if _u(row.get("verdict")) == "GO"
        and _u(row.get("ticker")) in live_map
    ]
    calculation_live_map = {
        _u(row.get("ticker")): live_map[_u(row.get("ticker"))]
        for row in calculation_candidates
    }
    return worklist_tickers, calculation_candidates, calculation_live_map


def _enrich_msi_market_structure(
    *,
    run_id: str,
    candidates: List[Dict[str, Any]],
    live_map: Dict[str, Dict[str, Any]],
    worklist_tickers: tuple[str, ...],
    registry: Any,
    canonical_flags: Any,
) -> dict[str, int]:
    """Attach deterministic, advisory-only market structure evidence."""
    from canonical_data import (
        CanonicalMinuteBarResolver,
        DatasetType,
        publish_observation_worklist,
        session_bounds,
        session_snapshot,
    )
    from domain.market_structure_evidence import profile_evidence_state_for_session
    from market_structure import calculate_market_structure_evidence
    from market_structure.service import CanonicalMarketStructureService

    validation_cutoff_utc = datetime.now(timezone.utc).replace(microsecond=0)
    snapshot = session_snapshot(validation_cutoff_utc)
    session_date = snapshot.session_date or snapshot.last_completed_session
    regular_open, regular_close = session_bounds(session_date)
    profile_evidence_state = profile_evidence_state_for_session(snapshot.state).value
    rows_by_ticker = {_u(row.get("ticker")): row for row in candidates}
    if profile_evidence_state == "PENDING_MARKET_OPEN":
        for ticker, row in rows_by_ticker.items():
            pending = {
                "ms_profile_evidence_state": "PENDING_MARKET_OPEN",
                "ms_profile_authority": "ADVISORY_ONLY",
                "ms_profile_can_grant_capital": False,
                "ms_profile_can_reverse_direction": False,
                "ms_profile_reason_code": "REGULAR_SESSION_NOT_YET_OBSERVABLE",
            }
            row.update(pending)
            live_map[ticker].update(pending)
        return {"eligible": len(worklist_tickers), "calculated": 0, "unavailable": 0}
    if snapshot.session_date == session_date and snapshot.last_closed_minute_utc:
        end_utc = min(snapshot.last_closed_minute_utc, regular_close - timedelta(minutes=1))
    else:
        end_utc = regular_close - timedelta(minutes=1)
    if end_utc < regular_open:
        return {"eligible": 0, "calculated": 0, "unavailable": 0}

    tickers = tuple(
        sorted(
            {
                _u(row.get("ticker"))
                for row in candidates
                if _u(row.get("ticker")) and _u(row.get("ticker")) in live_map
            }
        )
    )
    publication = publish_observation_worklist(
        registry,
        run_id=run_id,
        stage="MARKET_STRUCTURE",
        tickers=worklist_tickers,
        dataset_types=(DatasetType.INTRADAY_BAR, DatasetType.MARKET_STRUCTURE),
        allow_monotonic_expansion=True,
    )
    if not publication.reconciled:
        raise RuntimeError("MSI market-structure worklist did not reconcile")

    registry_path = ROOT / "data" / "canonical" / "control_plane.sqlite"
    payload_root = ROOT / "data" / "canonical" / "market_observations"
    minute_resolver = CanonicalMinuteBarResolver(
        registry_path=registry_path,
        payload_root=payload_root,
        run_id=run_id,
        invocation_id=f"{run_id}:developing-profile:{validation_cutoff_utc.isoformat()}",
        evidence_cutoff_utc=validation_cutoff_utc,
        requesting_stage="MARKET_STRUCTURE",
        flags=canonical_flags,
    )
    structure_store = CanonicalMarketStructureService(
        registry_path=registry_path,
        payload_root=payload_root,
    )
    calculated = 0
    unavailable = 0
    for ticker in tickers:
        row = rows_by_ticker[ticker]
        live = live_map[ticker]
        atr14 = _f(row.get("atr14") or row.get("atr") or row.get("atr_14"))
        if atr14 is None or atr14 <= 0:
            unavailable_fields = {
                    "ms_authority": "ADVISORY_ONLY",
                    "ms_reason_code": "MS_ATR_MISSING",
                    "ms_quality_class": "INSUFFICIENT_DATA",
                    "ms_profile_evidence_state": profile_evidence_state,
                }
            live.update(unavailable_fields)
            row.update(unavailable_fields)
            unavailable += 1
            continue
        try:
            minute_result = minute_resolver.resolve(
                ticker=ticker,
                session_date=session_date,
                start_utc=regular_open,
                end_utc=end_utc,
                fetch_missing=_fetch_marketdata_five_minute_bars,
                provider="MARKETDATA",
                interval_minutes=5,
                session_segment="REGULAR",
                evidence_state=profile_evidence_state,
                adjustment_convention="SPLIT_ADJUSTED",
            )
            hashes = []
            for dataset_id in minute_result.dataset_ids:
                record = minute_resolver.registry.get_dataset(dataset_id)
                hashes.append(record.content_hash if record is not None else "MISSING")
            evidence = calculate_market_structure_evidence(
                ticker=ticker,
                session_date=session_date,
                run_id=run_id,
                bars=minute_result.frame,
                exchange_tick=0.01,
                atr14=atr14,
                regular_open_utc=regular_open,
                governed_direction=_u(
                    row.get("governed_direction")
                    or row.get("canonical_direction")
                    or row.get("direction")
                ),
                input_dataset_ids=minute_result.dataset_ids,
                input_hashes=tuple(hashes),
                prior_lifecycle=_s(row.get("ms_lifecycle")) or None,
            )
            record = structure_store.persist(evidence)
            evidence["ms_profile_evidence_state"] = profile_evidence_state
            evidence["ms_profile_authority"] = "ADVISORY_ONLY"
            live.update(evidence)
            live["ms_dataset_id"] = record.dataset_id
            live["ms_minute_resolution"] = minute_result.resolution
            live["ms_physical_fetches"] = minute_result.physical_fetches
            row.update(live)
            calculated += 1
        except Exception as error:
            unavailable_fields = {
                    "ms_authority": "ADVISORY_ONLY",
                    "ms_reason_code": f"MS_DATA_ERROR:{type(error).__name__}",
                    "ms_quality_class": "INSUFFICIENT_DATA",
                    "ms_error": str(error),
                    "ms_profile_evidence_state": profile_evidence_state,
                }
            live.update(unavailable_fields)
            row.update(unavailable_fields)
            unavailable += 1
    return {
        "eligible": publication.authorised_count,
        "calculated": calculated,
        "unavailable": unavailable,
    }


def _get_ev3_barrier_cache() -> tuple[Any, str]:
    """Load the governed EV3 cache once per morning process."""
    global _EV3_BARRIER_CACHE, _EV3_BARRIER_CACHE_ERROR
    if _EV3_BARRIER_CACHE is not None:
        return _EV3_BARRIER_CACHE, ""
    if _EV3_BARRIER_CACHE_ERROR:
        return None, _EV3_BARRIER_CACHE_ERROR
    try:
        from vanguard.ev_engine_v3 import EV3BarrierCache

        if not EV3_BARRIER_CACHE_PATH.exists() or EV3_BARRIER_CACHE_PATH.stat().st_size == 0:
            raise FileNotFoundError(str(EV3_BARRIER_CACHE_PATH))
        _EV3_BARRIER_CACHE = EV3BarrierCache.load(EV3_BARRIER_CACHE_PATH)
        return _EV3_BARRIER_CACHE, ""
    except Exception as exc:
        _EV3_BARRIER_CACHE_ERROR = f"{type(exc).__name__}:{exc}"
        return None, _EV3_BARRIER_CACHE_ERROR


def _ev3_candidate_from_hydration(
    row: Dict[str, Any],
    hydrated: Dict[str, Any],
) -> Dict[str, Any]:
    candidate = dict(row)
    candidate["entry_spot"] = (
        row.get("live_price")
        or row.get("entry_spot")
        or row.get("signal_price")
        or row.get("underlying_price")
    )
    candidate["target_spot"] = (
        row.get("target_spot")
        or row.get("target_price")
        or row.get("structural_target")
    )
    candidate["invalidation_spot"] = (
        row.get("invalidation_spot")
        or row.get("invalidation_price")
        or row.get("invalidation_level")
        or row.get("structural_invalidation")
    )
    candidate["direction_resolution_status"] = (
        row.get("direction_resolution_status")
        or row.get("direction_status")
        or row.get("direction_arbitration_status")
        or row.get("direction_conflict_status")
        or "RESOLVED"
    )
    candidate["state_key"] = (
        row.get("ev3_barrier_state_key")
        or row.get("state_key")
        or row.get("layer2__matched_state_key")
        or row.get("layer2__outcomes__matched_state_key")
    )
    hold = _f(row.get("planned_hold_sessions") or row.get("ev3_horizon_sessions"))
    hold_source = "planned_hold_sessions" if _f(row.get("planned_hold_sessions")) is not None else "ev3_horizon_sessions"
    if hold is None:
        horizon_text = _u(
            row.get("horizon_bucket")
            or row.get("preferred_horizon")
            or row.get("expected_holding_window")
        ).replace("-", "_")
        if "1_5" in horizon_text:
            hold = 5.0
        elif "6_10" in horizon_text:
            hold = 10.0
        elif "11_20" in horizon_text:
            hold = 20.0
        hold_source = "ROUTED_HORIZON_UPPER_BOUND" if hold is not None else "MISSING"
    candidate["planned_hold_sessions"] = int(hold) if hold is not None and float(hold).is_integer() else hold
    candidate["morning_ev3_hold_source"] = hold_source
    # Morning handoff expected-move columns are percentage points (for example
    # 3.78 means 3.78%). EV3's unit contract is a fraction. Normalise at this
    # explicit boundary and leave the governed EV3 validator strict.
    for horizon_days in (5, 10, 20):
        field = f"expected_move_{horizon_days}d"
        move = _f(row.get(field) or row.get(f"l3_{field}"))
        if move is None:
            continue
        if 0.60 <= move <= 60.0:
            candidate[field] = move / 100.0
            candidate[f"morning_{field}_unit_source"] = "PERCENT_POINTS_TO_FRACTION"
        else:
            candidate[field] = move
            candidate[f"morning_{field}_unit_source"] = "FRACTION_PASSTHROUGH"
    candidate["contract_symbol"] = hydrated.get("selected_contract_symbol")
    candidate["contract_structure"] = hydrated.get("selected_structure")
    candidate["contract_quote_timestamp_utc"] = hydrated.get("selected_quote_timestamp_utc")

    long_leg = hydrated.get("selected_long_leg")
    short_leg = hydrated.get("selected_short_leg")
    if isinstance(long_leg, dict):
        candidate.update({
            "contract_strike": long_leg.get("strike"),
            "contract_expiry": long_leg.get("expiry"),
            "contract_dte": long_leg.get("dte"),
            "contract_bid": long_leg.get("bid"),
            "contract_ask": long_leg.get("ask"),
            "contract_delta": long_leg.get("delta"),
            "contract_gamma": long_leg.get("gamma"),
            "contract_theta": long_leg.get("theta"),
            "contract_vega": long_leg.get("vega"),
            "contract_iv": long_leg.get("iv"),
            "contract_oi": long_leg.get("oi"),
            "contract_volume": long_leg.get("volume"),
            "contract_multiplier": long_leg.get("contract_multiplier"),
        })
    if isinstance(short_leg, dict):
        candidate["long_leg"] = long_leg
        candidate["short_leg"] = short_leg
    return candidate


def _evaluate_hydrated_ev3(
    row: Dict[str, Any],
    hydrated: Dict[str, Any],
) -> Dict[str, Any]:
    cache, cache_error = _get_ev3_barrier_cache()
    if cache is None:
        return {
            "ev3_status": "NOT_EVALUATED_DATA_DEFECT",
            "ev3_reason_code": "EV3_BARRIER_CACHE_UNAVAILABLE",
            "ev3_reason_detail": cache_error,
            "ev3_shadow_only": False,
            "ev3_evidence_mode": "PRODUCTION_EVIDENCE",
            "ev3_capital_eligible": False,
        }
    try:
        from vanguard.ev_engine_v3 import EV3Policy, evaluate_contract

        return evaluate_contract(
            _ev3_candidate_from_hydration(row, hydrated),
            cache,
            policy=EV3Policy(),
            phase="MORNING",
            now_utc=_utc_now(),
            max_quote_age_seconds=15 * 60,
        )
    except Exception as exc:
        return {
            "ev3_status": "NOT_EVALUATED_DATA_DEFECT",
            "ev3_reason_code": "EV3_SELECTED_RECOMPUTE_FAILED",
            "ev3_reason_detail": f"{type(exc).__name__}:{exc}",
            "ev3_shadow_only": False,
            "ev3_evidence_mode": "PRODUCTION_EVIDENCE",
            "ev3_capital_eligible": False,
        }


def _recompute_selected_contract_economics(
    row: Dict[str, Any],
    live_data: Dict[str, Any],
) -> bool:
    """Replace inherited economics with calculations for the live structure."""
    for stale_field in (
        "rr_premium_expected", "rr_options", "option_rr", "rr_predicted",
        "rr_contract_symbol", "rr_evaluation_id", "option_gain_at_target",
        "monetisability_status", "monetisability_state", "monetisability_reason",
        "monetisability_eligible", "monetisability_contract_symbol",
        "monetisability_evaluation_id", "monetisability_entry_ask",
        "monetisability_breakeven_spot", "monetisability_structural_target_spot",
        "monetisability_target_intrinsic_per_share",
        "monetisability_target_profit_per_share", "monetisability_target_profit_pct",
        "execution_viability_policy_version", "execution_viability_state",
        "execution_viability_reason", "execution_viability_eligible",
        "execution_viability_reviewable", "execution_viability_contract_symbol",
        "execution_viability_bid", "execution_viability_ask",
        "execution_viability_spread_pct", "execution_viability_spread_denominator",
        "ev_predicted", "ev3_ev_conservative_return", "ev3_ev_lower_bound_return",
        "ev3_uncertainty_total_return", "ev3_p_target", "ev3_p_stop",
        "ev3_p_timeout", "ev3_evaluation_id",
    ):
        row[stale_field] = ""

    hydration_status = _u(live_data.get("selected_structure_hydration_status"))
    if hydration_status != "COMPLETE":
        row["rr_recompute_status"] = "FAILED"
        row["rr_recompute_reason"] = (
            live_data.get("selected_structure_hydration_reason")
            or "SELECTED_STRUCTURE_NOT_HYDRATED"
        )
        row["monetisability_status"] = "FAILED"
        row["monetisability_state"] = "DATA_MISSING"
        row["monetisability_reason"] = row["rr_recompute_reason"]
        row["monetisability_eligible"] = False
        row["economics_comparable"] = False
        row["economics_mismatch_reason"] = "SELECTED_STRUCTURE_HYDRATION_FAILED"
        row["economics_recompute_required"] = "TRUE"
        row["selected_contract_economics_ready"] = False
        row["ev3_selected_contract_aligned"] = False
        return False

    for key in (
        "selected_structure", "selected_structure_id", "selected_contract_symbol",
        "selected_contract_symbols", "selected_quote_snapshot_id",
        "selected_quote_timestamp_utc", "selected_structure_hydration_status",
        "selected_structure_hydration_reason", "selected_structure_hydration_schema_version",
        "selected_legs_json",
    ):
        row[key] = live_data.get(key, "")
    row["contract_symbol"] = live_data.get("selected_contract_symbol", row.get("contract_symbol", ""))
    row["recommended_contract"] = row["contract_symbol"]
    row["morning_selected_contract_symbol"] = row["contract_symbol"]

    live_to_contract = {
        "live_contract_bid": "contract_bid",
        "live_contract_ask": "contract_ask",
        "live_contract_mid": "contract_mid",
        "live_contract_spread_pct": "contract_spread_pct",
        "live_contract_iv": "contract_iv",
        "live_contract_delta": "contract_delta",
        "live_contract_gamma": "contract_gamma",
        "live_contract_theta": "contract_theta",
        "live_contract_vega": "contract_vega",
        "live_contract_oi": "contract_oi",
        "live_contract_volume": "contract_volume",
        "live_contract_multiplier": "contract_multiplier",
        "live_contract_quote_timestamp": "contract_quote_timestamp",
        "live_options_source": "contract_source",
    }
    for source_field, contract_field in live_to_contract.items():
        value = live_data.get(source_field)
        if value is not None and value != "":
            row[contract_field] = value
    row["premium_mid"] = live_data.get("live_contract_mid", "")

    # R:R remains available for research exports, but never gates permission.
    rr_result = recompute_premium_rr(row, live_data)
    row.update(rr_result)

    monetisability_result = evaluate_long_option_monetisability(row, live_data)
    row.update(monetisability_result)
    viability_result = evaluate_execution_viability(row, live_data)
    row.update(viability_result)
    if monetisability_result.get("monetisability_status") != "COMPLETE":
        row["economics_comparable"] = False
        row["economics_mismatch_reason"] = monetisability_result.get(
            "monetisability_reason", "MONETISABILITY_RECOMPUTE_FAILED"
        )
        row["economics_recompute_required"] = "FALSE"
        row["selected_contract_economics_ready"] = bool(
            viability_result.get("execution_viability_state")
            not in {"DATA_MISSING", "INVALID_QUOTE", "UNSUPPORTED_STRUCTURE"}
        )
        row["ev3_selected_contract_aligned"] = False
    else:
        row["selected_contract_economics_ready"] = bool(
            viability_result.get("execution_viability_state")
            not in {"DATA_MISSING", "INVALID_QUOTE", "UNSUPPORTED_STRUCTURE"}
        )

    ev3_result = _evaluate_hydrated_ev3(row, live_data)
    row.update(ev3_result)
    selected_id = _s(live_data.get("selected_structure_id"))
    ev_symbols = selected_contract_symbols_from_value(ev3_result.get("ev3_contract_symbol"))
    ev_id = ""
    if _u(ev3_result.get("ev3_status")).startswith("EVALUATED") and ev_symbols:
        ev_id = selected_economics_evaluation_id(
            row.get("ticker"),
            row.get("canonical_direction") or row.get("direction"),
            ev3_result.get("ev3_structure"),
            ev_symbols,
        )
    row["ev3_evaluation_id"] = ev_id
    comparable = bool(
        selected_id
        and (
            not rr_result.get("rr_evaluation_id")
            or selected_id == rr_result.get("rr_evaluation_id")
        )
        and selected_id == ev_id
    )
    row["economics_comparable"] = comparable
    row["ev3_selected_contract_aligned"] = comparable
    if comparable:
        row["economics_mismatch_reason"] = ""
        row["economics_recompute_required"] = "FALSE"
        row["ev_predicted"] = ev3_result.get("ev3_ev_conservative_return", "")
    else:
        row["economics_mismatch_reason"] = (
            ev3_result.get("ev3_reason_code")
            or "SELECTED_CONTRACT_EV3_RECOMPUTE_INCOMPLETE"
        )
        # The exact-contract EV attempt has completed but produced no comparable
        # advisory estimate. Monetisability is already complete and EV3 has no
        # capital authority.
        row["economics_recompute_required"] = "FALSE"
        row["ev_predicted"] = ""
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="AVSHUNTER fail-closed Morning Gate")
    parser.add_argument("--run-id", default=None, help="Run ID. Auto-resolves from latest.json if omitted.")
    parser.add_argument(
        "--spread-threshold",
        type=float,
        default=DEFAULT_SPREAD_THRESHOLD,
        help=(
            "Legacy hard-review spread ceiling; cannot relax the governed "
            f"{DEFAULT_SPREAD_THRESHOLD:.0f}%% maximum. Executable limit is "
            f"{LONG_OPTION_EXECUTION_POLICY['executable_spread_max_pct']:.0f}%%."
        ),
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--preopen-thesis-check",
        action="store_true",
        help="Validate the underlying thesis without requesting option quotes.",
    )
    mode_group.add_argument(
        "--postopen-contract-refresh",
        action="store_true",
        help="Refresh the selected option contract using observed provider timestamps.",
    )
    args = parser.parse_args()

    cds_runtime = configure_cds_runtime_for_morning_gate()
    msi_flags = active_msi_flags()
    if msi_flags.v2_capture and not (
        cds_runtime["enabled"] and cds_runtime["write_through"]
    ):
        log.error(
            "MSI v2 capture requires canonical data and write-through; "
            "explicit CDS environment overrides disabled the Morning store"
        )
        return 1
    log.info(
        "Canonical Morning runtime â€” enabled=%s write_through=%s "
        "mode=%s enforced=%s",
        cds_runtime["enabled"],
        cds_runtime["write_through"],
        cds_runtime["ohlcv_mode"],
        cds_runtime["stage_gating_enforced"],
    )

    if not POLYGON_API_KEY or not MARKETDATA_API_KEY:
        log.error("POLYGON_API_KEY and MARKETDATA_API_KEY must be set in .env â€” aborting")
        return 1

    run_id = args.run_id or _latest_run_id()
    if not run_id:
        log.error("Cannot resolve run_id. Pass --run-id or run the evening pipeline first.")
        return 1

    log.info("Morning Gate starting â€” run_id=%s", run_id)
    if args.preopen_thesis_check:
        execution_mode = "PREOPEN_THESIS_CHECK"
    elif args.postopen_contract_refresh:
        execution_mode = "POSTOPEN_CONTRACT_REFRESH"
    else:
        try:
            from canonical_data import session_snapshot
            execution_mode = (
                "PREOPEN_THESIS_CHECK"
                if session_snapshot().state.value == "PREMARKET"
                else "POSTOPEN_CONTRACT_REFRESH"
            )
        except Exception:
            execution_mode = "POSTOPEN_CONTRACT_REFRESH"
    results = run_morning_gate(
        run_id=run_id,
        spread_threshold=args.spread_threshold,
        execution_mode=execution_mode,
    )
    try:
        from morning_handoff_finalizer import (
            finalize_morning_handoff,
            sync_verified_morning_handoff,
        )

        # Materialise first, then prove Morning -> Lab integrity before any
        # artifacts are copied into the Pipeline Interpreter input directory.
        handoff = finalize_morning_handoff(
            run_id,
            results,
            sync_interpreter=False,
        )
        log.info(
            "Morning downstream handoff complete â€” %s Lab actionable rows",
            handoff.get("lab_actionable", 0),
        )

        run_dir = RUNS_DIR / run_id
        lab_integrity = _normalise_score_integrity(
            run_dir,
            run_id,
            _check_post_lab_score_integrity(
                run_id,
                results,
                Path(str(handoff.get("lab_csv_path") or "")),
            ),
        )
        summary_path = (
            run_dir / "morning_validation" / f"morning_gate_summary_{run_id}.json"
        )
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
        except Exception:
            summary = {
                "run_id": run_id,
                "validated_at_utc": _utc_now(),
                "input_candidates": len(results),
                "go_count": sum(1 for row in results if _u(row.get("verdict")) == "GO"),
                "flag_count": sum(1 for row in results if _u(row.get("verdict")) == "FLAG"),
                "block_count": sum(1 for row in results if _u(row.get("verdict")) == "BLOCK"),
            }
        summary["score_integrity_status"] = lab_integrity.get(
            "integrity_status", "NOT_EVALUATED"
        )
        summary["score_integrity_scope"] = lab_integrity.get("integrity_scope", "")
        summary["score_integrity_compared"] = int(
            lab_integrity.get("compared", 0) or 0
        )
        summary["score_integrity_pass"] = bool(
            lab_integrity.get("integrity_pass", False)
        )
        summary["lab_score_integrity_status"] = lab_integrity.get(
            "lab_score_integrity_status", "NOT_EVALUATED"
        )
        _write_json(summary_path, summary)
        _close_final_run_manifest(run_dir, run_id, summary, lab_integrity)
        log.info(
            "Post-Lab score integrity: compared=%d mismatches=%d status=%s",
            lab_integrity.get("compared", 0),
            lab_integrity.get("mismatches", 0),
            lab_integrity.get("integrity_status", "NOT_EVALUATED"),
        )
        if lab_integrity.get("integrity_status") != "PASS":
            log.error("Post-Lab score integrity failed - run is not operationally complete")
            return 1
        sync_results = sync_verified_morning_handoff(handoff)
        log.info(
            "Verified Morning handoff published to Interpreter - %d artifacts",
            len(sync_results),
        )
    except Exception as error:
        log.exception("Morning downstream handoff failed â€” run is incomplete: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
