"""BEH-001 phase 2A: the behavioural candidate packet (pure).

Design: Enhancements/decision_map/AVS_SD_BEH_001_PHASE2_CANDIDATE_HANDOFF_DESIGN_20261001.md §3 2A.
Candidates travel in their own lane beside the ticker spine. Vanguard is a per-ticker
fact and is joined to each candidate by ticker, never duplicated. Discovery's outcome is
an attribute, never a gate. Display and measurement only.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, List, Mapping

PACKET_VERSION = "behavioural_candidate_packet_v1"


def _clean(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _rank_key(c: Mapping) -> tuple:
    q50 = _clean(c.get("Duration_Remaining_Q50_Bars"))
    activated = c.get("Signal_State") == "ACTIVATED"
    return (0 if activated else 1, 0 if activated else (float(q50) if q50 is not None else math.inf),
            str(c["Candidate_ID"]))


def build_candidate_packet(run_id: str, candidates: Iterable[Mapping], vanguard_pass: Iterable[Mapping],
                           vanguard_reject: Iterable[Mapping], policy: Mapping) -> dict:
    live, monitoring = set(policy["live_states"]), set(policy["monitoring_states"])
    fields = list(policy["vanguard_fields"])
    passed = {str(r["ticker"]).upper(): r for r in vanguard_pass}
    rejected = {str(r["ticker"]).upper(): r for r in vanguard_reject}
    records: List[dict] = []
    watch: List[dict] = []
    failed: List[dict] = []
    seen = set()
    for raw in candidates:
        c = {k: _clean(v) for k, v in raw.items()}
        if c["Candidate_ID"] in seen:
            continue
        seen.add(c["Candidate_ID"])
        state = c.get("Signal_State")
        if state == "FAILED":
            failed.append(c)
            continue
        if state in monitoring or c.get("Direction") not in {"BULL", "BEAR"} or state not in live:
            watch.append({**c, "Handoff_Status": "MONITOR_ONLY"})
            continue
        ticker = str(c["Ticker"]).upper()
        if ticker in passed:
            row = passed[ticker]
            c["vanguard__status"] = "PASS"
            c["vanguard__fields_missing"] = [f for f in fields if f not in row]
            for f in fields:
                c[f"vanguard__{f}"] = _clean(row.get(f))
        elif ticker in rejected:
            c["vanguard__status"] = f"REJECT:{rejected[ticker].get('reason_code') or 'UNSPECIFIED'}"
            c["vanguard__fields_missing"] = list(fields)
        else:
            c["vanguard__status"] = "VANGUARD_NOT_RUN"
            c["vanguard__fields_missing"] = list(fields)
        c["Handoff_Status"] = "DIRECTED_LIVE"
        records.append(c)
    records.sort(key=_rank_key)
    for rank, c in enumerate(records, start=1):
        c["Handoff_Rank"] = rank
    tickers = {str(c["Ticker"]).upper() for c in records}
    return {
        "packet_version": PACKET_VERSION, "run_id": run_id, "authority": "DISPLAY_AND_MEASUREMENT_ONLY",
        "policy_version": policy.get("version"),
        "records": records, "monitoring": watch, "failed": failed,
        "counts": {"records": len(records), "monitoring": len(watch), "failed": len(failed),
                   "tickers_with_live_candidates": len(tickers),
                   "activated": sum(c["Signal_State"] == "ACTIVATED" for c in records),
                   "vanguard_rows_joined": len(tickers & set(passed))},
    }
