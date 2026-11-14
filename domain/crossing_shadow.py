"""Shadow comparison of contracts by their crossing scenario (AVS-TRADE-001 design v4 section 7; ACK 14 Nov 2026).

SHADOW AND DISPLAY ONLY. The selected contract, its score, the existing value choice (`contract_value_*`), the rank
and every gate are untouched; this module is handed copies and returns extra fields.

Pool        the scored contracts the selector hands over (already through its own filters; the counts of what each
            filter removed are published with the result, and never imply the whole chain was assessed).
Set         for each of the nearest N expiries: the top M by existing score, plus that expiry's best-liquidity
            contract with a valid, aligned quote; plus the selected contract; de-duplicated by OCC symbol.
Objective   the earliest slow-pace +30% base crossing among contracts that cover it and are tradeable.
Eligible    crossing covers; quote VALID; quote ALIGNED (not provisional); tier A or B.
Order       earliest crossing, then better tier, then lower entry cost, then nearer expiry, then OCC symbol.
            Tier is an eligibility test and a tie-break, never the first key.
Blank       with a reason, never an implicit fallback. Covering contracts that are tier C or provisional are listed
            separately as research rows.

The result is labelled BEST_WITHIN_BOUNDED_SET_V1: it is the best of the set assessed, not the best contract.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional, Sequence

from domain.crossing_scenario import HEADLINE, crossing_config, scenario_crossing
from domain.option_contract_liquidity import quote_tier
from domain.quote_provenance import quote_provenance

SET_LABEL = "BEST_WITHIN_BOUNDED_SET_V1"
POOL_BASIS = "SCORED_CONTRACTS_AFTER_SELECTION_FILTERS"
TIER_RANK = {"A": 0, "B": 1, "C": 2}
CANDIDATE_PACES = ("SLOW",)
CANDIDATE_VARIANTS = ("BASE", "WIDE_EXIT")

#: Fields added to the selected contract's row. None is read by any selector, rank, gate or Lane B flag.
CROSSING_SHADOW_FIELDS = (
    "quote_tier_validity", "quote_tier", "quote_tier_reason", "quote_tier_spread_share",
    "quote_provenance", "quote_provenance_reason",
    "crossing_selection_mode", "crossing_shadow_set", "crossing_shadow_set_complete", "crossing_shadow_reason",
    "crossing_shadow_symbol", "crossing_shadow_tier", "crossing_shadow_provenance",
    "crossing_shadow_n_slow_pace_30", "crossing_shadow_n_slow_pace_30_wide_exit",
    "crossing_shadow_sessions_to_expiry", "crossing_shadow_entry_cost", "crossing_shadow_expiry",
    "crossing_shadow_selected_n_slow_pace_30", "crossing_shadow_selected_state",
    "crossing_pool_basis", "crossing_candidates_json",
)


def blank_shadow(reason: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {field: None for field in CROSSING_SHADOW_FIELDS}
    out.update(crossing_selection_mode="SHADOW", crossing_shadow_set=SET_LABEL, crossing_shadow_reason=reason,
               crossing_pool_basis=POOL_BASIS)
    return out


def _f(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def build_candidate_set(scores: Sequence[Mapping[str, Any]], selected_symbol: Any, *, expiries: int, per_expiry: int,
                        assess) -> List[Dict[str, Any]]:
    """The bounded set, in a deterministic order, de-duplicated by OCC symbol. `assess(contract)` returns the
    liquidity assessment used to pick each expiry's best-liquidity contract."""
    by_expiry: Dict[str, List[Mapping[str, Any]]] = {}
    for contract in scores:
        by_expiry.setdefault(str(contract.get("expiry")), []).append(contract)
    chosen: List[Dict[str, Any]] = []
    seen: set = set()

    def add(contract: Mapping[str, Any], why: str) -> None:
        symbol = str(contract.get("symbol") or "")
        if symbol and symbol not in seen:
            seen.add(symbol)
            chosen.append({**contract, "_set_reason": why})

    for expiry in sorted(by_expiry)[:max(int(expiries), 0)]:
        rows = by_expiry[expiry]
        top = sorted(rows, key=lambda c: (-(_f(c.get("contract_score")) or 0.0), str(c.get("symbol"))))[:max(int(per_expiry), 0)]
        for contract in top:
            add(contract, "TOP_SCORE_IN_EXPIRY")
        liquid = []
        for contract in rows:
            tier, provenance = assess(contract)
            if tier["validity"] == "VALID" and provenance["provenance"] == "ALIGNED":
                liquid.append((TIER_RANK[tier["tier"]], tier["spread_pct"], -(tier["open_interest"] or 0.0),
                               str(contract.get("symbol")), contract))
        if liquid:
            add(sorted(liquid, key=lambda item: item[:4])[0][4], "BEST_LIQUIDITY_IN_EXPIRY")
    for contract in scores:
        if str(contract.get("symbol") or "") == str(selected_symbol or ""):
            add(contract, "SELECTED_CONTRACT")
    return chosen


def crossing_shadow_fields(scores: Sequence[Mapping[str, Any]], selected: Mapping[str, Any], *,
                           anchors: Mapping[str, Any], pool_counts: Optional[Mapping[str, Any]] = None,
                           config: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """The shadow comparison for one row. `anchors`: side, thesis_id, thesis_origin_date, origin_spot,
    frozen_target_level, arrival_sessions_median, arrival_sessions_slow, assessment_instant_utc, quote_spot,
    thesis_active, evidence_session, underlying, rate, rate_basis, dividend_yield, dividend_basis."""
    cfg = dict(config) if config is not None else crossing_config()
    a = dict(anchors)
    selected_symbol = str(selected.get("symbol") or "")
    cache: Dict[str, Any] = {}

    def assess(contract: Mapping[str, Any]):
        symbol = str(contract.get("symbol") or "")
        if symbol not in cache:
            tier = quote_tier(contract.get("bid"), contract.get("ask"),
                              contract.get("open_interest", contract.get("oi")))
            provenance = quote_provenance(
                mode="EVENING_AT_EVIDENCE", quote_timestamp_utc=contract.get("quote_timestamp_utc"),
                assessment_instant_utc=a.get("assessment_instant_utc"), evidence_session=a.get("evidence_session"),
                spot_session=a.get("evidence_session"), iv_session=provenance_iv_session(contract, a),
                expected_symbol=symbol, quote_symbol=contract.get("md_occ_symbol") or symbol)
            cache[symbol] = (tier, provenance)
        return cache[symbol]

    candidates = build_candidate_set(scores, selected_symbol, expiries=cfg["candidate_expiries"],
                                     per_expiry=cfg["candidate_contracts_per_expiry"], assess=assess)
    out = blank_shadow("NO_CANDIDATES")
    sel_tier, sel_prov = assess(selected) if selected_symbol else (None, None)
    if sel_tier:
        out.update(quote_tier_validity=sel_tier["validity"], quote_tier=sel_tier["tier"], quote_tier_reason=sel_tier["code"],
                   quote_tier_spread_share=None if sel_tier["spread_pct"] is None else round(sel_tier["spread_pct"] / 100.0, 6),
                   quote_provenance=sel_prov["provenance"], quote_provenance_reason=sel_prov["reason"])
    assessed: List[Dict[str, Any]] = []
    for contract in candidates:
        tier, provenance = assess(contract)
        crossing = scenario_crossing(
            side=a.get("side"), mode="EVENING_AT_EVIDENCE", thesis_id=a.get("thesis_id"),
            contract_symbol=contract.get("symbol"), thesis_origin_date=a.get("thesis_origin_date"),
            origin_spot=a.get("origin_spot"), frozen_target_level=a.get("frozen_target_level"),
            arrival_sessions_median=a.get("arrival_sessions_median"), arrival_sessions_slow=a.get("arrival_sessions_slow"),
            assessment_instant_utc=a.get("assessment_instant_utc"), quote_timestamp_utc=contract.get("quote_timestamp_utc"),
            quote_spot=a.get("quote_spot"), strike=contract.get("strike"), expiry=contract.get("expiry"),
            bid=contract.get("bid"), ask=contract.get("ask"), iv=contract.get("iv", contract.get("implied_vol")),
            thesis_active=a.get("thesis_active"), underlying=a.get("underlying"), rate=a.get("rate"),
            rate_basis=a.get("rate_basis"), dividend_yield=a.get("dividend_yield"),
            dividend_basis=a.get("dividend_basis"), config=cfg, paces=CANDIDATE_PACES, variants=CANDIDATE_VARIANTS)
        records = {(r["pace"], r["threshold_pct"], r["variant"]): r for r in json.loads(crossing["crossing_records_json"])}
        head = records[HEADLINE]
        wide = records[("SLOW", 30, "WIDE_EXIT")]
        assessed.append({
            "symbol": contract.get("symbol"), "expiry": str(contract.get("expiry")), "strike": contract.get("strike"),
            "set_reason": contract["_set_reason"], "contract_score": contract.get("contract_score"),
            "ask": contract.get("ask"), "bid": contract.get("bid"),
            "state": head["state"], "n_slow_pace_30": head["crossing_session"], "covers": head["covers"],
            "n_slow_pace_20": records[("SLOW", 20, "BASE")]["crossing_session"],
            "n_slow_pace_30_wide_exit": wide["crossing_session"], "wide_exit_state": wide["state"],
            "search_limit": head["search_limit"], "search_end_session": head["search_end_session"],
            "sessions_to_expiry": crossing["crossing_sessions_to_expiry"],
            "validity": tier["validity"], "tier": tier["tier"], "tier_reason": tier["code"],
            "spread_pct": tier["spread_pct"], "provenance": provenance["provenance"],
            "provenance_reason": provenance["reason"],
            "scope": "SLOW_PACE_BASE_AND_WIDE_EXIT_ONLY",
        })
    selected_row = next((c for c in assessed if c["symbol"] == selected_symbol), None)
    if selected_row:
        out.update(crossing_shadow_selected_n_slow_pace_30=selected_row["n_slow_pace_30"],
                   crossing_shadow_selected_state=selected_row["state"])
    truncated = [c for c in assessed if c["state"] == "SEARCH_TRUNCATED_AT_CONFIG_CAP"]
    crossing_any = [c for c in assessed if c["n_slow_pace_30"] is not None]
    covering = [c for c in assessed if c["state"] == "CROSSES_COVERING"]
    tradeable = [c for c in covering if c["validity"] == "VALID" and c["provenance"] == "ALIGNED" and c["tier"] in ("A", "B")]
    research = [c for c in covering if c not in tradeable]
    for c in assessed:
        c["role"] = ("ELIGIBLE" if c in tradeable else "RESEARCH_ROW_COVERS_BUT_NOT_TRADEABLE" if c in research
                     else "NOT_ELIGIBLE")
    if not assessed:
        reason = "NO_CANDIDATES"
    elif not crossing_any:
        states = {c["state"] for c in assessed}
        reason = next(iter(states)) if len(states) == 1 and next(iter(states)).startswith(("NOT_ASSESSED", "THESIS", "TARGET", "PACE")) \
            else "NO_CROSSING_IN_SET"
    elif not covering:
        reason = "NO_COVERING_CANDIDATE"
    elif not tradeable:
        reason = "NO_TRADEABLE_COVERING_CANDIDATE"
    else:
        best = sorted(tradeable, key=lambda c: (c["n_slow_pace_30"], TIER_RANK[c["tier"]], _f(c["ask"]) or float("inf"),
                                                c["expiry"], str(c["symbol"])))[0]
        best["role"] = "SHADOW"
        reason = "SAME_AS_SELECTED" if best["symbol"] == selected_symbol else "EARLIEST_COVERING_TRADEABLE_CROSSING"
        out.update(crossing_shadow_symbol=best["symbol"], crossing_shadow_tier=best["tier"],
                   crossing_shadow_provenance=best["provenance"], crossing_shadow_n_slow_pace_30=best["n_slow_pace_30"],
                   crossing_shadow_n_slow_pace_30_wide_exit=best["n_slow_pace_30_wide_exit"],
                   crossing_shadow_sessions_to_expiry=best["sessions_to_expiry"], crossing_shadow_entry_cost=best["ask"],
                   crossing_shadow_expiry=best["expiry"])
    out.update(crossing_shadow_reason=reason, crossing_shadow_set_complete="NO" if truncated else "YES")
    out["crossing_candidates_json"] = json.dumps({
        "set": SET_LABEL, "objective": "EARLIEST_SLOW_PACE_30_BASE_CROSSING_AMONG_COVERING_TRADEABLE",
        "pool_basis": POOL_BASIS, "pool_filter_counts": dict(pool_counts or {}), "pool_scored": len(scores),
        "expiries_limit": cfg["candidate_expiries"], "per_expiry_limit": cfg["candidate_contracts_per_expiry"],
        "search_cap": cfg["search_cap_sessions"], "considered": len(candidates), "assessed": len(assessed),
        "not_in_set": max(len({str(c.get("symbol")) for c in scores}) - len(assessed), 0),
        "truncated_by_cap": len(truncated), "thesis_status_basis": a.get("thesis_status_basis"),
        "candidates": assessed}, sort_keys=True, default=str)
    return out


def provenance_iv_session(contract: Mapping[str, Any], anchors: Mapping[str, Any]) -> Any:
    """The IV on a chain row is observed with its quote: its session is the quote's session when a timestamp exists."""
    stamp = contract.get("quote_timestamp_utc")
    if stamp in (None, ""):
        return None
    try:
        from datetime import datetime
        from canonical_data.session_clock import NEW_YORK
        instant = datetime.fromisoformat(str(stamp).strip().replace("Z", "+00:00"))
        return instant.astimezone(NEW_YORK).date() if instant.tzinfo is not None else None
    except ValueError:
        return None
