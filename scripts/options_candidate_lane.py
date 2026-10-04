"""BEH-001 phase 2B: expression search per behavioural candidate (Options stage).

Design: Enhancements/decision_map/AVS_SD_BEH_001_PHASE2_CANDIDATE_HANDOFF_DESIGN_20261001.md §3 2B.
A separate pass after the per-ticker Options loop; it never changes the per-ticker
outputs. For each routed candidate it reuses the chain the existing path already acquired
(a same-session canonical cache hit, no new provider request), swaps in the candidate's
side, outcome level and invalidation, and runs the existing contract selection. Runway
stays the existing policy (C-06 is phase 3). Measurement only.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Callable, Dict, Iterable, List, Mapping

SIDE_TO_RIGHT = {"BULL": "CALL", "BEAR": "PUT"}


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


def evaluate_candidate_expressions(records: Iterable[Mapping], rows_by_ticker: Mapping[str, Any],
                                   results_by_ticker: Mapping[str, Mapping], *, fetch_chain: Callable,
                                   parse_context: Callable, select_contract: Callable,
                                   max_candidates: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    chains: Dict[str, Any] = {}
    for record in sorted(records, key=lambda r: (_rank(r), str(r["Candidate_ID"]))):
        row = {k: record.get(k) for k in ("Candidate_ID", "Ticker", "Timeframe", "Signal_Type", "Signal_State",
                                          "Direction", "Handoff_Rank", "Trigger_Level", "Invalidation_Level",
                                          "Outcome_Level", "Duration_Test", "Duration_Remaining_Q50_Bars",
                                          "Duration_Remaining_Q80_Bars", "Discovery_Outcome", "vanguard__status")}
        ticker = str(record.get("Ticker") or "").upper()
        rank = _rank(record)
        out.append(row)
        if rank > max_candidates:
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
        right = SIDE_TO_RIGHT.get(str(record.get("Direction")))
        if right is None:
            row["Expression_Status"] = "NOT_ROUTED:NO_DIRECTED_SIDE"
            continue
        try:
            if ticker not in chains:
                chains[ticker] = fetch_chain(ticker)
            ctx = copy.copy(parse_context(rows_by_ticker[ticker]))
            ctx["direction"] = right
            ctx["structural_target"] = _number(record.get("Outcome_Level"))
            ctx["invalidation_spot"] = _number(record.get("Invalidation_Level"))
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
