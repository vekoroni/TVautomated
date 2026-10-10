"""Per-ticker disposition record for every surfaced idea (output-trust item 8, D6-1 / G2-05).

Root cause: the EOD decision append keys events by thesis, so book rows without a thesis identity (run 20261008_220129:
418 unresolved direction + 90 directed with no contract = 508) never reached the journal although the Lab showed them.

One record per run, ticker and stage, traded or not. The decision-time snapshot is frozen: setup, levels, contract (or
the stated reason there is none), price and quote time, stated probabilities, value scenarios, the decision and why,
and the model versions. Nothing is invented: a missing thesis or contract identity is null with its state, and every
snapshot field is present (null when the row did not carry it). Observation only; it never decides.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping

DISPOSITION_VERSION = "ticker_disposition_v1"
DISPOSITION_FIELDS = (
    # identity and decision
    "ticker", "direction", "thesis_id", "lab_verdict", "final_action", "verdict", "morning_unlock_condition",
    "evening_thesis_bucket", "trigger_go_eligible", "trigger_go_reason", "lab_rank", "rank_group",
    "legacy_execution_permission_context",
    # setup
    "thesis__side", "thesis_category", "thesis_phase", "thesis_event", "thesis_event_timeframe",
    "thesis_event_candidate_id", "thesis__readiness", "thesis__readiness_reason", "trade_lane", "trade_lane_setup",
    "trade_lane_basis",
    # levels and geometry
    "thesis_trigger_level", "target_price", "structural_target", "invalidation_price", "early_warning_invalidation_level",
    "geometry_justification", "geometry_entry_price", "geometry_breakeven_hit_rate", "call_wall", "put_wall",
    "call_wall_level_confirmed", "put_wall_level_confirmed",
    # contract and price
    "contract_symbol", "expiry", "strike", "contract_bid", "contract_ask", "contract_iv", "contract_rejection_reason",
    "option_expression_state", "contract_repair_reason",
    "signal_price", "live_price", "bar_data_asof", "selected_quote_timestamp_utc", "anticipated_contract_basis",
    "anticipated_valued_at_utc",
    # stated probabilities and value
    "trade_lane_hit_original", "trade_lane_hit_holdout", "geometry_measured_hit_rate", "geometry_hit_n",
    "anticipated_p_outcome_by_limit", "anticipated_p_invalidation_by_limit", "anticipated_value_multiple_q50",
    "anticipated_pays_state", "scenario_target_return_on_premium", "scenario_invalidation_return_on_premium",
    "scenario_stall_return_on_premium",
    # model versions
    "trade_lane_version", "valuation_version", "anticipated_version", "thesis__side_assignment_policy_version",
    "wall_method", "direction_validation_state",
)


def _present(value: Any) -> bool:
    return value is not None and str(value).strip().upper() not in {"", "NAN", "NONE", "NULL"}


def _clean(value: Any) -> Any:
    return value if _present(value) else None


def _thesis_state(row: Mapping[str, Any]) -> str:
    """A thesis exists only with a side and a governing thesis candidate. The book's thesis_id is a row key
    (live 8 Oct: unresolved rows keyed "<TICKER>:UNRESOLVED:<run>") and is never presented as a thesis."""
    direction = str(row.get("direction") or row.get("governed_direction") or "").strip().upper()
    if direction not in {"CALL", "PUT"}:
        return "NO_THESIS:UNRESOLVED_DIRECTION"
    if not _present(row.get("thesis_event_candidate_id")):
        readiness = str(row.get("thesis__readiness") or "").strip().upper()
        return f"NO_THESIS:NO_GOVERNING_CANDIDATE:{readiness or 'NOT_RECORDED'}"
    return "PRESENT"


def _contract_state(row: Mapping[str, Any]) -> str:
    if _present(row.get("contract_symbol")):
        return "PRESENT"
    direction = str(row.get("direction") or row.get("governed_direction") or "").strip().upper()
    if direction not in {"CALL", "PUT"}:
        return "NO_CONTRACT:NO_TRADE_SIDE"
    reason = next((row.get(k) for k in ("contract_rejection_reason", "option_expression_state",
                                         "contract_repair_reason", "stand_down_reason") if _present(row.get(k))), None)
    return f"NO_CONTRACT:{reason}" if _present(reason) else "NO_CONTRACT:REASON_NOT_RECORDED"


def disposition_record(row: Mapping[str, Any], *, run_id: str, stage: str, recorded_at_utc: str) -> Dict[str, Any]:
    ticker = str(row.get("ticker") if row.get("ticker") is not None else "").strip().upper()   # "NAN" is a ticker
    if not ticker:
        raise ValueError("a disposition needs the ticker the book surfaced")
    snapshot = {field: _clean(row.get(field)) for field in DISPOSITION_FIELDS}
    snapshot["ticker"] = ticker
    record = {
        "disposition_version": DISPOSITION_VERSION,
        "run_id": str(run_id),
        "ticker": ticker,
        "stage": str(stage).strip().upper(),
        "recorded_at_utc": recorded_at_utc,
        "thesis_identity_state": _thesis_state(row),
        "book_row_key": _clean(row.get("thesis_id")),
        "contract_symbol": _clean(row.get("contract_symbol")),
        "contract_identity_state": _contract_state(row),
        "authority": "OBSERVATION_ONLY",
        "snapshot": snapshot,
    }
    record["thesis_id"] = record["book_row_key"] if record["thesis_identity_state"] == "PRESENT" else None
    record["thesis_candidate_id"] = _clean(row.get("thesis_event_candidate_id"))
    content = {k: v for k, v in record.items() if k != "recorded_at_utc"}
    record["disposition_id"] = hashlib.sha256(f"{run_id}|{ticker}|{record['stage']}".encode()).hexdigest()[:32]
    record["payload_hash"] = hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()
    return record


def disposition_records(rows, *, run_id: str, stage: str, recorded_at_utc: str) -> list:
    """Every surfaced row with a ticker; a row without one is reported by the caller, never invented."""
    return [disposition_record(r, run_id=run_id, stage=stage, recorded_at_utc=recorded_at_utc)
            for r in rows if str((r or {}).get("ticker") if (r or {}).get("ticker") is not None else "").strip()]


__all__ = ("DISPOSITION_FIELDS", "DISPOSITION_VERSION", "disposition_record", "disposition_records")
