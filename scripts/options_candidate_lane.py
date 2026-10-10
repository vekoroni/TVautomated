"""BEH-001 phase 2B: expression search per behavioural candidate (Options stage).

Design: Enhancements/decision_map/AVS_SD_BEH_001_PHASE2_CANDIDATE_HANDOFF_DESIGN_20261001.md §3 2B.
A separate pass after the per-ticker Options loop; it never changes the per-ticker
outputs. For each routed candidate it reuses the chain the existing path already acquired
(a same-session canonical cache hit, no new provider request), swaps in the candidate's
side, outcome level and invalidation, and runs the existing contract selection. Runway
stays the existing policy (C-06 is phase 3). Measurement only.

Phase 5.4 (ACK 8 Oct 2026, "Governing + all priced"): every routed thesis is priced - no resource cap unless the
policy sets one - and an unresolved thesis with both conditional boundaries (CONDITIONAL_BOTH_SIDES) is priced on
both sides: CALL above its bull boundary with the bear boundary as invalidation, PUT the mirror; no target is invented.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

SIDE_TO_RIGHT = {"BULL": "CALL", "BEAR": "PUT"}
_RECORD_FIELDS = ("Candidate_ID", "Ticker", "Timeframe", "Signal_Type", "Signal_State", "Direction", "Handoff_Rank",
                  "Handoff_Status", "Trigger_Level", "Invalidation_Level", "Outcome_Level", "Duration_Test",
                  "Duration_Remaining_Q50_Bars", "Duration_Remaining_Q80_Bars", "Discovery_Outcome",
                  "vanguard__status", "Adoption_State", "Readiness")


def _plain(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _number(value: Any):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def _rank(record: Mapping) -> int:
    value = _number(record.get("Handoff_Rank"))
    return 10 ** 9 if value is None else int(value)


def _expressions(record: Mapping) -> List[Dict[str, Any]]:
    """The side(s) to price for one routed record: (right, target, invalidation, condition)."""
    if record.get("Handoff_Status") == "CONDITIONAL_BOTH_SIDES":
        bull, bear = _number(record.get("Conditional_Bull_Trigger")), _number(record.get("Conditional_Bear_Trigger"))
        return [{"right": "CALL", "target": None, "invalidation": bear,
                 "condition": f"CONDITIONAL: BULL if accepted above {bull:g}"},
                {"right": "PUT", "target": None, "invalidation": bull,
                 "condition": f"CONDITIONAL: BEAR if accepted below {bear:g}"}]
    right = SIDE_TO_RIGHT.get(str(record.get("Direction")))
    return [{"right": right, "target": _number(record.get("Outcome_Level")),
             "invalidation": _number(record.get("Invalidation_Level")), "condition": "DIRECTED"}]


def evaluate_candidate_expressions(records: Iterable[Mapping], rows_by_ticker: Mapping[str, Any],
                                   results_by_ticker: Mapping[str, Mapping], *, fetch_chain: Callable,
                                   parse_context: Callable, select_contract: Callable,
                                   max_candidates: Optional[int] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    chains: Dict[str, Any] = {}
    for record in sorted(records, key=lambda r: (_rank(r), str(r["Candidate_ID"]))):
        base = {k: record.get(k) for k in _RECORD_FIELDS}
        ticker = str(record.get("Ticker") or "").upper()
        rank = _rank(record)
        for expression in _expressions(record):
            row = {**base, "Expression_Side": expression["right"], "Expression_Condition": expression["condition"]}
            out.append(row)
            if max_candidates is not None and rank > max_candidates:
                row["Expression_Status"] = f"DEFERRED_RESOURCE:{rank}"
                continue
            if ticker not in rows_by_ticker:
                row["Expression_Status"] = "NOT_ROUTED:TICKER_OUTSIDE_OPTIONS_SCOPE"
                continue
            result = results_by_ticker.get(ticker) or {}
            if not str(result.get("option_chain_dataset_id") or "").strip():
                row["Expression_Status"] = "NOT_ROUTED:CHAIN_NOT_AUTHORISED_BY_GDR"
                row["ticker_stand_down_reason"] = result.get("stand_down_reason") or result.get("options_verdict")
                continue
            if expression["right"] is None:
                row["Expression_Status"] = "NOT_ROUTED:NO_DIRECTED_SIDE"
                continue
            try:
                if ticker not in chains:
                    chains[ticker] = fetch_chain(ticker)
                ctx = copy.copy(parse_context(rows_by_ticker[ticker]))
                ctx["direction"] = expression["right"]
                ctx["structural_target"] = expression["target"]
                ctx["invalidation_spot"] = expression["invalidation"]
                row["runway_authority"] = f"EXISTING_OPTIONS_POLICY:{ctx.get('horizon_bucket')}"
                contract = select_contract(chains[ticker], ctx)
            except Exception as error:
                row["Expression_Status"] = f"ERROR:{type(error).__name__}"
                continue
            if not contract:
                row["Expression_Status"] = "NO_CONTRACT_FIT"
                continue
            row["Expression_Status"] = "CONTRACT_FOUND"
            for key, value in contract.items():
                if not str(key).startswith("_") and _plain(value):
                    row[f"contract__{key}"] = value
    return out


def summarise_by_ticker(lane: Iterable[Mapping]) -> Dict[str, Dict[str, Any]]:
    """Per-ticker summary of the priced theses for the Options row (Phase 5.4): how many were tested, how many found
    a contract, and the compact list of found contracts with each thesis's identity, side and condition."""
    import json
    tested: Dict[str, int] = {}
    found: Dict[str, List[Dict[str, Any]]] = {}
    for row in lane:
        ticker = str(row.get("Ticker") or "").upper()
        if not ticker:
            continue
        tested[ticker] = tested.get(ticker, 0) + 1
        if row.get("Expression_Status") == "CONTRACT_FOUND":
            found.setdefault(ticker, []).append({
                "candidate_id": row.get("Candidate_ID"), "timeframe": row.get("Timeframe"),
                "side": row.get("Expression_Side"), "condition": row.get("Expression_Condition"),
                "symbol": row.get("contract__symbol"), "dte": row.get("contract__dte"),
                "delta": row.get("contract__delta")})
    return {t: {"thesis_alternatives_count": len(found.get(t, [])), "thesis_alternatives_tested": n,
                "thesis_alternatives_json": json.dumps(found.get(t, []), separators=(",", ":"), default=str)}
            for t, n in tested.items()}
