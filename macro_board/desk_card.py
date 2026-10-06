"""Desk decision card: the six desk questions answered from the board's own facts, plus checks.

Every check describes evidence; none of them decides. The human records Act / Wait / Skip /
Insufficient information and the reason on the card. Statuses:
SUPPORTS / CONFLICTS / NO_EVIDENCE / NO_PROPOSAL for direction, OK / CAUTION / AGAINST / UNKNOWN
for the entry, the option price and the data.
"""

from __future__ import annotations

from typing import Any, Mapping

_SIDE = {"CALL": 1, "PUT": -1}
_LEAN = {"UP": 1, "DOWN": -1}


def _record(evidence: Mapping | None) -> str:
    """The measured numbers behind a lean, shown even when they are too thin for a lean."""
    analog = (evidence or {}).get("analog") or {}
    base = (evidence or {}).get("base") or {}
    if analog.get("mean_pct") is None:
        return ""
    interval = ""
    if analog.get("ci_low_pct") is not None and analog.get("ci_high_pct") is not None:
        interval = f", 80% interval {analog['ci_low_pct']:+.2f}% to {analog['ci_high_pct']:+.2f}%"
    base_txt = f" vs {base['mean_pct']:+.2f}% for all sessions" if base.get("mean_pct") is not None else ""
    return f" History: {analog['mean_pct']:+.2f}%{base_txt}{interval}, {analog.get('n_eff', 0)} independent windows."


def direction_check(pipeline_direction: str | None, lean: str | None, evidence: Mapping | None = None) -> dict:
    side = _SIDE.get(str(pipeline_direction or "").upper())
    record = _record(evidence)
    if side is None:
        return {"status": "NO_PROPOSAL", "text": "No governed CALL/PUT direction from the pipeline." + record}
    sign = _LEAN.get(str(lean or "").upper())
    if sign is None:
        return {"status": "NO_EVIDENCE", "text": f"No measured lean ({str(lean or 'none').replace('_', ' ').lower()})." + record}
    if sign == side:
        return {"status": "SUPPORTS", "text": "Measured lean points the same way as the proposal." + record}
    return {"status": "CONFLICTS", "text": "Measured lean points against the proposal." + record}


def stale_target_note(pipeline_direction: str | None, room: Mapping, momentum_evidence: Mapping | None,
                      horizon: str) -> str | None:
    """When the measured continuation after similar runs exceeds the room left to the target, the
    pipeline's target (often a prior high or low) may be stale: re-evaluate it, don't just chase or skip."""
    side = _SIDE.get(str(pipeline_direction or "").upper())
    analog = (momentum_evidence or {}).get("analog") or {}
    base = ((momentum_evidence or {}).get("base") or {}).get("mean_pct")
    mean = analog.get("mean_pct")
    if side is None or mean is None or room.get("status") not in ("AGAINST", "CAUTION"):
        return None
    # continuation must be real: interval clear of zero in the proposal's direction, and at
    # least as good as the ETF's ordinary drift (otherwise it is just drift, not momentum)
    bound = analog.get("ci_low_pct") if side > 0 else analog.get("ci_high_pct")
    if bound is None or side * bound <= 0 or (base is not None and side * mean < side * base):
        return None
    reward = room.get("reward_pct") or 0.0
    if side * mean > max(reward, 0.0):
        return (f"After similar runs this ETF moved {mean:+.2f}% on average over {horizon} sessions "
                f"({analog.get('n_eff', 0)} windows), more than the room left to the pipeline target. The target may be "
                f"stale (often a prior high): ask the pipeline/structure for a re-evaluated target rather than chasing "
                f"the old one or dismissing the trend.")
    return None


def entry_room_check(remaining: Mapping | None, cfg: Mapping) -> dict:
    """Reward left to the pipeline target against risk left to its invalidation, from today's close.
    Distances, not probabilities; a target already passed is AGAINST (the setup needs a new target)."""
    remaining = remaining or {}
    reward, risk = remaining.get("to_target_pct"), remaining.get("to_invalidation_pct")
    if reward is None or risk is None or risk <= 0:
        return {"status": "UNKNOWN", "ratio": None, "text": "No target or invalidation to measure room against."}
    if reward <= 0:
        return {"status": "AGAINST", "ratio": None, "reward_pct": reward, "risk_pct": risk,
                "text": "Price is already through the pipeline target; the setup needs a new target."}
    ratio = reward / risk
    if ratio >= float(cfg["room_ok_ratio"]):
        status = "OK"
    elif ratio >= float(cfg["room_caution_ratio"]):
        status = "CAUTION"
    else:
        status = "AGAINST"
    return {"status": status, "ratio": round(ratio, 3), "reward_pct": reward, "risk_pct": risk,
            "text": f"{reward:.2f}% left to target vs {risk:.2f}% to invalidation (ratio {ratio:.2f})."}


def option_price_check(priced_vs_history: float | None, iv_rank: float | None, spread_pct: float | None,
                       cfg: Mapping) -> dict:
    if priced_vs_history is None and iv_rank is None and spread_pct is None:
        return {"status": "UNKNOWN", "text": "No option data for this ETF."}
    notes, status = [], "OK"
    if priced_vs_history is not None:
        if priced_vs_history > float(cfg["priced_vs_history_expensive"]):
            status = "AGAINST"
            notes.append(f"options price {priced_vs_history:.2f}× the move similar sessions delivered")
        elif priced_vs_history > float(cfg["priced_vs_history_ok"]):
            status = "CAUTION"
            notes.append(f"options price {priced_vs_history:.2f}× history")
        else:
            notes.append(f"options price {priced_vs_history:.2f}× history")
    if iv_rank is not None and iv_rank >= float(cfg["iv_rank_high"]):
        status = "CAUTION" if status == "OK" else status
        notes.append(f"IV rank {iv_rank:.0f}")
    if spread_pct is not None and spread_pct > float(cfg["spread_caution_pct"]):
        status = "CAUTION" if status == "OK" else status
        notes.append(f"straddle spread {spread_pct:.1f}% of mid")
    return {"status": status, "text": "; ".join(notes).capitalize() + "."}


def _lean_of(block: Mapping | None, horizon: str) -> Mapping:
    return ((block or {}).get(horizon) or {}) if isinstance(block, Mapping) else {}


def build_card(ticker: str, etf: Mapping[str, Any], *, horizon: str, conditions: Mapping, intel: Mapping,
               external: Mapping, cfg: Mapping, condition_labels: Mapping[str, str]) -> dict:
    """Assemble the six desk questions and the checks for one ETF."""
    pipeline = etf.get("pipeline") or {}
    direction = pipeline.get("canonical_direction")
    macro_ev = _lean_of(etf.get("evidence"), horizon)
    mom = etf.get("momentum") or {}
    mom_ev = {name: _lean_of(block, horizon) for name, block in (mom.get("evidence") or {}).items()}
    decision = etf.get("decision") or {}
    response = (decision.get("response") or {}).get(horizon) or {}
    options = ((etf.get("options") or {}).get("moves") or {}).get(horizon) or {}
    tasty = etf.get("tastytrade") or {}
    metrics = etf.get("metrics") or {}
    sensitivity = (etf.get("sensitivity") or {}).get(horizon) or {}

    measured = sorted(((k, v) for k, v in sensitivity.items() if v.get("t") is not None and abs(v["t"]) >= 1.0
                       and v.get("excess_pct") is not None), key=lambda kv: -abs(kv[1]["t"]))[:4]
    changes = [c for c in conditions.get("changes", [])][:6]
    events = (intel.get("events") or {})
    room = entry_room_check(pipeline.get("remaining"), cfg)
    note = stale_target_note(direction, room, mom_ev.get("streak"), horizon)
    if note:
        room = {**room, "note": note}
    checks = {
        "macro_lean": direction_check(direction, macro_ev.get("lean"), macro_ev),
        "momentum": direction_check(direction, (mom_ev.get("streak") or {}).get("lean"), mom_ev.get("streak")),
        "momentum_ext20": direction_check(direction, (mom_ev.get("ext20") or {}).get("lean"), mom_ev.get("ext20")),
        "entry_room": room,
        "option_price": option_price_check(options.get("priced_vs_history"), tasty.get("iv_rank_pct"),
                                           options.get("spread_pct_of_mid"), cfg),
        "data": {"status": "OK" if metrics.get("status") == "FRESH" and all(
                     (external.get(k) or {}).get("status") == "FRESH" for k in ("macro_packet", "us_money_index"))
                 else "CAUTION",
                 "text": f"Prices {metrics.get('status', 'MISSING').lower()} to {metrics.get('last_session')}; "
                         f"macro packet {(external.get('macro_packet') or {}).get('status', 'MISSING').lower()}; "
                         f"Money Index {(external.get('us_money_index') or {}).get('status', 'MISSING').lower()}."},
        "event_risk": {"status": "CAUTION" if (events.get("verdict") or {}).get("verdict") not in (None, "", "NO_MATERIAL_EVENT")
                       or str((intel.get("enrichment") or {}).get("alert_level") or "").upper() in ("AMBER", "RED")
                       else "OK",
                       "text": f"Event verdict {((events.get('verdict') or {}).get('verdict') or 'none').replace('_', ' ').lower()}; "
                               f"news alert {str((intel.get('enrichment') or {}).get('alert_level') or 'none').lower()}."},
    }
    return {
        "ticker": ticker, "horizon": horizon,
        "q1_changed": {"conditions": changes, "events": [e.get("event_name") for e in (events.get("events") or [])][:3],
                       "news_alert": (intel.get("enrichment") or {}).get("alert_level")},
        "q2_affects": {"measured": [{"condition": condition_labels.get(k, k), "state": v.get("state"),
                                     "excess_pct": v.get("excess_pct"), "t": v.get("t")} for k, v in measured],
                       "holdings_leaders": [r["ticker"] for r in ((((etf.get("holdings") or {}).get("windows") or {}).get(horizon) or {}).get("top_contributors") or [])[:5]]},
        "q3_market": {"response": response.get("label"), "rs_vs_spy_20d": metrics.get("rs_vs_spy_20d"),
                      "streak": mom.get("streak"), "z": mom.get("z"), "momentum_states": mom.get("current"),
                      "participation_pct": ((((etf.get("holdings") or {}).get("windows") or {}).get("20") or {}).get("participation_weight_pct"))},
        "q4_pipeline": pipeline,
        "q5_entry": {"remaining": pipeline.get("remaining"), "options": options, "iv_rank": tasty.get("iv_rank_pct"),
                     "iv_hv_diff": tasty.get("iv_hv_diff_pct")},
        "q6_change_mind": {"invalidation": pipeline.get("invalidation_spot"), "target": pipeline.get("target_spot")},
        "evidence": {"macro": macro_ev, "momentum": mom_ev},
        "checks": checks,
    }
