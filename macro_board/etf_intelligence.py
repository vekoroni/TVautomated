"""Per-ETF intelligence written by every board build (AVS-MACRO-TRIAGE-001 T1, approved by ACK 20 Nov 2026).

A compact projection of what the board already measured, one entry per sector and industry ETF in the rotation
universe, for the Lane B triage to read (T2 joins it to the hand-off by ledger id). Nothing new is measured here.

T7 (approved by ACK 20 Nov 2026) adds, to the same projection: the event file read with a tolerant field-name
reader, the US Money Index triggers, counter-evidence and sector routing (both labelled LLM_WITH_NEWS), a peer
reference beside SPY, and a read for every ETF in the board universe (not only the 26 rotation ETFs).

Rules (CLAUDE.md rule 6):
- every item says where it came from: MEASURED (the board's own numbers), LLM_PACKET (the ChatGPT macro packet) or
  LLM_FROM_OUR_SHEET (an LLM item written from our measured sheet); agreement between them is not independent;
- relative performance against the benchmark is called that, never a fund flow;
- missing is MISSING, never neutral; a disagreement is DISAGREE, never averaged;
- it orders and explains for the human; it never changes a pipeline gate, score, rank, contract, side or size.

    out = project(payload, config); write(out, output_dir / "etf_intelligence", as_of=None)
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Mapping, Sequence

from macro_board.day_story import FLOW_SIGN, _level_text, _pp, money_flow, relative_returns

MISSING = "MISSING"
MEASURED = "MEASURED"
LLM_PACKET = "LLM_PACKET"
LLM_FROM_OUR_SHEET = "LLM_FROM_OUR_SHEET"
AUTHORITY = ("Intelligence for human review (CLAUDE.md rule 6): it orders and explains. It never changes a pipeline "
             "gate, score, rank, contract selection, side or size.")
PACKET_BIAS = {"TAILWIND": "LEAN_IN", "HEADWIND": "AVOID", "MIXED": "NEUTRAL", "NEUTRAL": "NEUTRAL"}
ECHO_NOTE = ("The packet stance is an LLM read written from our own measured sheet; when it agrees with the measured "
             "read that is not independent confirmation.")
ONE_SOURCE_NOTE = "The packet does not name this ETF: one measured source only."
SCENARIO_KINDS = ("CONTINUATION", "REVERSAL", "ALTERNATIVE", "STAND_ASIDE")
LLM_WITH_NEWS = "LLM_WITH_NEWS"
NOT_NAMED = "NOT_NAMED"
FLIP_STANCE = {"LEAN_IN": "AVOID", "AVOID": "LEAN_IN"}
FLIP_LABEL = {"INFLOW": "OUTFLOW", "OUTFLOW": "INFLOW", "TURNING_IN": "TURNING_OUT", "TURNING_OUT": "TURNING_IN"}
ABSOLUTE_TEXT = {"INFLOW": "Rising", "TURNING_IN": "Rising after a weak stretch", "OUTFLOW": "Falling",
                 "TURNING_OUT": "Falling after a strong stretch", "NONE": "No clear move"}


def measured_stance(label: str | None) -> str:
    """LEAN_IN (outperforming / improving), AVOID (underperforming / weakening), NEUTRAL (measured, no clear edge),
    MISSING (no read)."""
    if label in FLOW_SIGN:
        return "LEAN_IN" if FLOW_SIGN[label] > 0 else "AVOID"
    return "NEUTRAL" if label == "NONE" else MISSING


def packet_stance(ticker: str, lead: Sequence[str], avoid: Sequence[str], bias: Mapping[str, str]) -> tuple[str, dict]:
    """The packet's view from its lead/avoid lists and its rotation bias. Both named and opposed: CONFLICTED."""
    detail = {"lead_list": ticker in lead, "avoid_list": ticker in avoid, "bias": bias.get(ticker)}
    votes = set()
    if detail["lead_list"]:
        votes.add("LEAN_IN")
    if detail["avoid_list"]:
        votes.add("AVOID")
    if detail["bias"] in PACKET_BIAS:
        votes.add(PACKET_BIAS[detail["bias"]])
    directional = votes - {"NEUTRAL"}
    if len(directional) > 1:
        return "CONFLICTED", detail
    if directional:
        return directional.pop(), detail
    return ("NEUTRAL" if votes else "NONE"), detail


def agreement(measured: str, packet: str) -> str:
    """AGREE / PARTIAL (one side neutral) / DISAGREE / ONE_SOURCE (packet silent) / PACKET_CONFLICTED / MISSING."""
    if measured == MISSING:
        return MISSING
    if packet == "NONE":
        return "ONE_SOURCE"
    if packet == "CONFLICTED":
        return "PACKET_CONFLICTED"
    if measured == packet:
        return "AGREE"
    if "NEUTRAL" in (measured, packet):
        return "PARTIAL"
    return "DISAGREE"


def _reasons(story: Mapping, side: str | None, packet: str, measured: str, cap: int) -> tuple[list, list, dict]:
    for_, against = [], []
    record = (story.get("trade") or {}).get("record")
    if record == "FOLLOWS":
        for_.append({"source": MEASURED, "text": "History: this read has tended to follow through."})
    elif record == "REVERSES":
        against.append({"source": MEASURED,
                        "text": "History: this read has more often reversed than followed through."})
    for d in story.get("drivers") or []:
        item = {"source": MEASURED, "text": str(d.get("text") or "")}
        if d.get("fit") == "CONSISTENT":
            for_.append(item)
        elif d.get("fit") == "AGAINST":
            against.append(item)
    fp = story.get("footprint") or {}
    if side in ("CALL", "PUT") and fp.get("status") == "OK" and fp.get("lean") in ("PUT_SIDE", "CALL_SIDE"):
        item = {"source": MEASURED, "text": "Options footprint: " + str(fp.get("text") or fp.get("lean"))}
        (for_ if (fp["lean"] == "PUT_SIDE") == (side == "PUT") else against).append(item)
    if measured in ("LEAN_IN", "AVOID") and packet in ("LEAN_IN", "AVOID"):
        item = {"source": LLM_PACKET, "text": f"Macro packet: {packet.replace('_', ' ')} (an LLM read of our sheet)."}
        (for_ if packet == measured else against).append(item)
    return for_[:cap], against[:cap], {"for": len(for_), "against": len(against)}


def _scenarios(ticker: str, trade: Mapping, against: Sequence[Mapping], counts: Mapping, horizon: int) -> list[dict]:
    side = trade.get("side")
    trigger, inval = trade.get("trigger"), trade.get("invalidation")
    if side not in ("CALL", "PUT"):
        idle = {"applies": False, "trigger": None, "invalidation": None, "horizon_sessions": horizon,
                "text": "Not offered: no clear relative-performance read."}
        return [dict(idle, kind="CONTINUATION"), dict(idle, kind="REVERSAL"), dict(idle, kind="ALTERNATIVE"),
                {"kind": "STAND_ASIDE", "applies": True, "trigger": None, "invalidation": None,
                 "horizon_sessions": horizon,
                 "text": f"{ticker}: stand aside; no clear relative-performance edge on this build. Look again when "
                         "a later build shows one."}]
    other = "PUT" if side == "CALL" else "CALL"
    lose, win = ("loses", "clears") if side == "PUT" else ("clears", "loses")
    direction = "underperforming" if side == "PUT" else "outperforming"
    out = [{"kind": "CONTINUATION", "applies": True, "trigger": trigger, "invalidation": inval,
            "horizon_sessions": horizon,
            "text": (f"{ticker} keeps {direction}: {side.lower()}s if it {lose} {_level_text(trigger)}; wrong back "
                     f"through {_level_text(inval)}.")},
           {"kind": "REVERSAL", "applies": True, "trigger": inval, "invalidation": trigger,
            "horizon_sessions": horizon,
            "text": (f"{ticker} turns: {other.lower()}s if it {win} {_level_text(inval)}; wrong if it then {lose} "
                     f"{_level_text(trigger)}.")}]
    if against:
        out.append({"kind": "ALTERNATIVE", "applies": True, "trigger": {"kind": "EVIDENCE", "text": against[0]["text"]},
                    "invalidation": trigger, "horizon_sessions": horizon,
                    "text": f"Another explanation ({against[0]['source']}): {against[0]['text']}"})
    else:
        out.append({"kind": "ALTERNATIVE", "applies": False, "trigger": None, "invalidation": None,
                    "horizon_sessions": horizon, "text": "No measured evidence against the read on this build."})
    balanced = counts["against"] >= counts["for"]
    out.append({"kind": "STAND_ASIDE", "applies": balanced, "trigger": None, "invalidation": trigger,
                "horizon_sessions": horizon,
                "text": (f"Stand aside while {ticker} stays between {_level_text(trigger)} and {_level_text(inval)}; "
                         f"evidence {counts['for']} for, {counts['against']} against.")})
    return out


def _published(items: Sequence[Mapping]) -> list[dict]:
    out = []
    for item in items or []:
        detail = str(item.get("source") or "")
        out.append({"name": item.get("name"), "institution": item.get("institution"),
                    "what_changed": item.get("what_changed"), "time_utc": item.get("time_utc"),
                    "source": LLM_FROM_OUR_SHEET if "llm" in detail.lower() else "PUBLISHED_UNLABELLED",
                    "source_detail": detail or None})
    return out


def _live(items: Sequence[Mapping]) -> list[dict]:
    return [{"id": x.get("scenario"), "state": x.get("state"), "side": x.get("side"),
             "verdict": (x.get("record") or {}).get("verdict"),
             "beats_the_tries": (x.get("record") or {}).get("survives_fdr")} for x in items or []]


# --- T7a: event file, tolerant field-name reader --------------------------------------------------------------------

def _empty(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, (list, tuple, dict)) and not v)


def _dig(obj, dotted: str):
    for part in str(dotted).split("."):
        if not isinstance(obj, Mapping):
            return None
        obj = obj.get(part)
    return obj


def pick(obj: Mapping, aliases: Sequence[str]) -> tuple:
    """The first alias that is present and non-empty, and the field it came from; (None, None) when none is."""
    for alias in aliases or []:
        value = _dig(obj, alias)
        if not _empty(value):
            return value, alias
    return None, None


def _as_list(v) -> list:
    """A list, also when the file stores it as the text of a list."""
    if _empty(v):
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    if isinstance(v, str) and v.strip().startswith("["):
        text = v.strip()
        # the list may be followed by more text (US Money Index rev 91): parse the shortest leading list that is
        # valid, keep what follows as one more item
        for end in [i for i, ch in enumerate(text) if ch == "]"]:
            try:
                parsed = ast.literal_eval(text[:end + 1])
            except (ValueError, SyntaxError):
                continue
            if isinstance(parsed, (list, tuple)):
                rest = text[end + 1:].strip().lstrip(";|,").strip()
                return list(parsed) + ([rest] if rest else [])
    return [v]


def event_intelligence(doc: Mapping, ordered_events: Sequence[Mapping], cfg: Mapping) -> dict:
    """The event file's market perception, alternative explanation, invalidation, consensus and beneficiaries for the
    latest events (already ordered latest first), its sector impacts per named ETF, its per-ETF cases and its counter
    case. Every item is LLM_WITH_NEWS; a part the file does not carry is MISSING."""
    fields, limit = cfg["event_fields"], int(cfg["max_events"])
    ordered = [e for e in ordered_events or [] if isinstance(e, Mapping)]
    events = []
    for e in ordered[:limit]:
        item, used = {"source": LLM_WITH_NEWS}, {}
        for key, aliases in fields.items():
            value, field = pick(e, aliases)
            item[key] = MISSING if value is None else value
            used[key] = field
        item["fields_used"] = used
        events.append(item)
    views = cfg["sector_impact_views"]
    impacts = doc.get("sector_impacts") if isinstance(doc.get("sector_impacts"), Mapping) else {}
    per_etf: dict = {}
    for group, view in views.items():
        for entry in impacts.get(group) or []:
            if not isinstance(entry, Mapping):
                continue
            for etf in entry.get("etfs") or []:
                per_etf.setdefault(str(etf).upper(), []).append(
                    {"view": view, "sector": entry.get("sector"), "condition": entry.get("condition"),
                     "source": LLM_WITH_NEWS})
    cases: dict = {}
    for e in ordered:  # latest event first: its case wins
        name = pick(e, fields.get("name") or [])[0]
        for case in e.get("conditional_etf_cases") or []:
            if not isinstance(case, Mapping) or _empty(case.get("instrument")):
                continue
            cases.setdefault(str(case["instrument"]).upper(),
                             {"bullish": case.get("bullish") or MISSING, "bearish": case.get("bearish") or MISSING,
                              "wait": case.get("wait") or MISSING, "event": name or MISSING, "source": LLM_WITH_NEWS})
    counter = doc.get("counter_case")
    if isinstance(counter, Mapping):
        counter_case = {"summary": counter.get("summary") or MISSING,
                        "reversal_conditions": _as_list(counter.get("reversal_or_neutralisation_conditions"))}
    else:
        counter_case = {"summary": MISSING if _empty(counter) else str(counter), "reversal_conditions": []}
    return {"status": "OK", "source": LLM_WITH_NEWS, "events": events, "events_total": len(ordered),
            "sector_impacts": per_etf, "unmapped_impact_groups": [g for g in impacts if g not in views],
            "etf_cases": cases, "counter_case": counter_case}


# --- T7b: US Money Index ------------------------------------------------------------------------------------------

def usmi_intelligence(doc: Mapping, cfg: Mapping) -> dict:
    """The US Money Index forward triggers, counter-evidence, leadership invalidation and sector routing per ETF.
    An empty score is MISSING with its reason, never 0; a routing sector without an ETF mapping is listed."""
    score = doc.get("risk_off_transmission_score") if isinstance(doc.get("risk_off_transmission_score"), Mapping) else {}
    current = score.get("current_score")
    if _empty(current):
        state = MISSING
        note = ("the USMI file carries no current score" + ("" if score.get("components") else " and no components")
                + "; nothing is read from its score")
    else:
        state, note = current, None
    triggers = doc.get("forward_triggers") if isinstance(doc.get("forward_triggers"), Mapping) else {}
    lead = doc.get("leadership") if isinstance(doc.get("leadership"), Mapping) else {}
    routing_src = _dig(doc, "options_monetisation.sector_routing")
    routing_src = routing_src if isinstance(routing_src, Mapping) else {}
    sector_map = cfg["usmi_sector_map"]
    routing: dict = {}
    unmapped = []
    for sector, text in routing_src.items():
        etfs = sector_map.get(sector)
        if not etfs:
            unmapped.append(sector)
            continue
        for etf in etfs:
            routing.setdefault(etf, []).append({"sector": sector, "routing": text, "source": LLM_WITH_NEWS})
    return {"status": "OK", "source": LLM_WITH_NEWS, "score": state, "score_note": note,
            "triggers": {k: (MISSING if _empty(triggers.get(k)) else triggers.get(k)) for k in cfg["usmi_trigger_keys"]},
            "counterevidence": [str(x) for x in _as_list(lead.get("counterevidence"))],
            "leadership_invalidation": lead.get("leadership_invalidation") or MISSING,
            "routing": routing, "unmapped_routing_sectors": unmapped}


# --- T7c/T7d: peer reference and the universe reads ---------------------------------------------------------------

def _horizons(windows: Mapping) -> list:
    return sorted({str(windows["day"]), str(windows["short"]), str(windows["long"])}, key=int)


def _basket_metrics(metrics: Mapping, members: Sequence[str], windows: Mapping) -> dict:
    """An equal-weight basket's return per window: the plain mean of its members' returns. Every member must be
    fresh; otherwise the basket is not fresh and names the stale members (ACK 20 Nov 2026: the sector peer is the
    equal-weight average of the 11 sector ETFs, because RSP is stale in the price store)."""
    horizons = _horizons(windows)
    stale = [f"{m} (last session {(metrics.get(m) or {}).get('last_session') or 'unknown'}, "
             f"{(metrics.get(m) or {}).get('status') or MISSING})"
             for m in members if (metrics.get(m) or {}).get("status") != "FRESH"
             or any((metrics.get(m) or {}).get(f"ret_{h}d") is None for h in horizons)]
    if stale or not members:
        return {"status": "STALE_MEMBERS", "note": "stale members: " + (", ".join(stale) or "none configured")}
    out = {"status": "FRESH", "members": list(members),
           "last_session": max(str((metrics.get(m) or {}).get("last_session") or "") for m in members) or None}
    for h in horizons:
        out[f"ret_{h}d"] = sum(float(metrics[m][f"ret_{h}d"]) for m in members) / len(members)
    return out


def _bench_read(metrics: Mapping, ticker: str, reference: str | None, windows: Mapping, bands: Mapping,
                names: Mapping | None = None) -> dict:
    """The ticker against one reference (or, with reference None, its absolute return), with the Day story windows
    and bands. MEASURED; relative performance, never a fund flow. ``names`` gives a basket its display name."""
    horizons = _horizons(windows)
    shown = (names or {}).get(reference, reference)
    stale = [(metrics.get(x) or {}).get("note") or
             f"{x} (last session {(metrics.get(x) or {}).get('last_session') or 'unknown'}, "
             f"{(metrics.get(x) or {}).get('status') or MISSING})"
             for x in ([ticker] + ([reference] if reference else []))
             if (metrics.get(x) or {}).get("status") != "FRESH"]
    if stale:  # fresh or flagged: never compare returns that end on different sessions
        return {"reference": reference or "ABSOLUTE", "label": MISSING, "relative_pp": None, "source": MEASURED,
                "text": f"{ticker} vs {shown or 'its own history'}: no read, price data not fresh for "
                        + ", ".join(stale) + "."}
    if reference is None:
        m = metrics.get(ticker) or {}
        ok = m.get("status") not in (MISSING, None)
        rel = {h: (round(float(m[f"ret_{h}d"]), 4) if ok and m.get(f"ret_{h}d") is not None else None) for h in horizons}
    else:
        rel = relative_returns(metrics, ticker, reference, horizons)
    flow = money_flow(rel, bands, windows)
    short, long_ = rel.get(str(windows["short"])), rel.get(str(windows["long"]))
    if flow["label"] == MISSING:
        text = f"{ticker}: " + flow["text"]
    elif reference is None:
        text = (f"{ABSOLUTE_TEXT[flow['label']]} (absolute return; {ticker} is the market reference): {_pp(short)}% "
                f"over {windows['short']} sessions, {_pp(long_)}% over {windows['long']}.")
    else:
        text = flow["text"].replace("the benchmark", shown)
    return {"reference": reference or "ABSOLUTE", "label": flow["label"], "relative_pp": rel, "text": text,
            "source": MEASURED}


def _peer_of(ticker: str, group: str | None, sectors: Sequence[str], b: Mapping) -> str | None:
    peer = ((b.get("ticker_peer") or {}).get(ticker) or (b.get("industry_parent") or {}).get(ticker)
            or (b.get("sector_peer") if ticker in sectors else None) or (b.get("group_peer") or {}).get(group))
    return None if peer == ticker else peer


def _benchmarks(metrics, ticker, group, sectors, b, windows, bands) -> dict:
    absolute = ticker in (b.get("absolute_read") or [])
    names = {k: v.get("label") or k for k, v in (b.get("baskets") or {}).items()}
    market = _bench_read(metrics, ticker, None if absolute else b["market"], windows, bands, names)
    peer_ref = _peer_of(ticker, group, sectors, b)
    if peer_ref is None:
        peer = {"reference": None, "label": "NO_PEER", "relative_pp": None, "source": MEASURED,
                "text": f"No peer reference is configured for {ticker}."}
        split = "NO_PEER"
    else:
        peer = _bench_read(metrics, ticker, peer_ref, windows, bands, names)
        split = (MISSING if MISSING in (market["label"], peer["label"]) else
                 "SAME" if market["label"] == peer["label"] else "SPLIT")
    return {"market": market, "peer": peer, "split": split}


def _no_idea(ticker: str, horizon: int) -> list[dict]:
    idle = {"applies": False, "trigger": None, "invalidation": None, "horizon_sessions": horizon,
            "text": "Not offered: the board has no trade idea for this ETF (it is outside the 26 rotation ETFs)."}
    return [dict(idle, kind="CONTINUATION"), dict(idle, kind="REVERSAL"), dict(idle, kind="ALTERNATIVE"),
            {"kind": "STAND_ASIDE", "applies": True, "trigger": None, "invalidation": None, "horizon_sessions": horizon,
             "text": (f"{ticker}: the board has no trade idea for this ETF; its relative-performance read is context "
                      "for the human, not a setup.")}]


def _universe_entry(ticker: str, group: str | None, *, coverage: str, read: Mapping | None, pstance: str,
                    pdetail: Mapping, horizon: int, missing_reason: str | None = None,
                    derived_from: str | None = None) -> dict:
    label = (read or {}).get("label") or MISSING
    mstance = measured_stance(label) if read else MISSING
    if mstance == MISSING and not missing_reason:
        missing_reason = (read or {}).get("text") or f"{ticker}: no read"
    return {"name": None, "kind": group, "coverage": coverage, "derived_from": derived_from,
            "stance_measured": mstance, "stance_measured_source": MEASURED,
            "missing_reason": None if mstance != MISSING else missing_reason,
            "stance_packet": pstance, "stance_packet_source": LLM_PACKET, "packet_detail": pdetail,
            "stance_agreement": agreement(mstance, pstance),
            "relative_performance": None if read is None else dict(read),
            "volume_ratio": None, "record": None, "reasons_for": [], "reasons_against": [],
            "evidence_count": {"for": 0, "against": 0},
            "echo_note": ECHO_NOTE if pstance != "NONE" else ONE_SOURCE_NOTE, "published": [], "live_scenarios": [],
            "decision_scenarios": _no_idea(ticker, horizon), "kill_level": None}


def _attach_t7(entry: dict, ticker: str, ev: Mapping | None, usmi: Mapping | None) -> None:
    if ev is None:
        entry["event_sector_view"], entry["event_etf_case"] = MISSING, MISSING
    else:
        entry["event_sector_view"] = (ev.get("sector_impacts") or {}).get(ticker) or NOT_NAMED
        entry["event_etf_case"] = (ev.get("etf_cases") or {}).get(ticker)
    entry["usmi_routing"] = MISSING if usmi is None else ((usmi.get("routing") or {}).get(ticker) or NOT_NAMED)


def project(payload: Mapping, config: Mapping) -> dict:
    """The etf_intelligence_v1 document for one board build."""
    cfg = config["etf_intelligence"]
    cap = int(cfg["max_reasons"])
    horizon = int(config["day_story"]["driver_horizon"])
    rotation = config["rotation"]
    rotation_tickers = list(dict.fromkeys(list(rotation["sectors"]) + list(rotation.get("industries") or [])))
    b = cfg.get("benchmarks")
    groups = {t: g.get("group") for g in (config.get("universe") or []) for t in g.get("tickers") or []}
    universe = list(groups) if b else []
    tickers = list(dict.fromkeys(rotation_tickers + universe))
    metrics = {t: (v or {}).get("metrics") or {} for t, v in (payload.get("etfs") or {}).items()}
    windows = (config.get("day_story") or {}).get("flow_windows")
    bands = (config.get("opportunity") or {}).get("relative_band_pp")
    for basket, spec in ((b or {}).get("baskets") or {}).items():  # equal-weight baskets used as a peer
        metrics[basket] = _basket_metrics(metrics, spec["members"], windows)
    intel = payload.get("intel") or {}
    ev = intel.get("event_intelligence") if (intel.get("event_intelligence") or {}).get("status") == "OK" else None
    usmi = intel.get("usmi_intelligence") if (intel.get("usmi_intelligence") or {}).get("status") == "OK" else None
    stories = {s["ticker"]: s for s in ((payload.get("day_story") or {}).get("stories") or [])}
    packet = (payload.get("intel") or {}).get("packet") or {}
    lead, avoid = list(packet.get("sector_lead") or []), list(packet.get("sector_avoid") or [])
    bias = ((payload.get("rotation") or {}).get("packet") or {}).get("bias") or {}
    next_session = (payload.get("session_plan") or {}).get("next_session")
    calendar = (payload.get("decision_points") or {}).get("calendar") or []
    events = [{k: e.get(k) for k in ("kind", "name", "date", "time_et", "detail", "source")}
              for e in calendar if next_session and str(e.get("date")) == str(next_session)]
    external = payload.get("external") or {}

    etfs = {}
    derived = (b or {}).get("derived") or {}
    no_read = (b or {}).get("no_read") or {}
    for t in tickers:
        story = stories.get(t)
        pstance, pdetail = packet_stance(t, lead, avoid, bias)
        if t not in rotation_tickers:  # T7d: a board-universe ETF outside the 26 rotation ETFs
            if t in derived:
                continue  # after the others: it takes its underlying's read
            if t in no_read:
                etfs[t] = _universe_entry(t, groups.get(t), coverage="NO_READ", read=None, pstance=pstance,
                                          pdetail=pdetail, horizon=horizon, missing_reason=no_read[t])
                etfs[t]["benchmarks"] = {"market": None, "peer": None, "split": "NO_READ"}
                continue
            bench = _benchmarks(metrics, t, groups.get(t), rotation["sectors"], b, windows, bands)
            absolute = t in (b.get("absolute_read") or [])
            etfs[t] = _universe_entry(t, groups.get(t), coverage="ABSOLUTE_READ" if absolute else "UNIVERSE_READ",
                                      read=bench["market"], pstance=pstance, pdetail=pdetail, horizon=horizon,
                                      missing_reason=(f"{t}: no fresh price metrics on this build "
                                                      f"({bench['market']['text']})")
                                      if bench["market"]["label"] == MISSING else None)
            etfs[t]["benchmarks"] = bench
            continue
        if story is None:
            etfs[t] = {"stance_measured": MISSING, "stance_measured_source": MEASURED,
                       "missing_reason": "no board read for this ETF on this build (day story missing it)",
                       "stance_packet": pstance, "stance_packet_source": LLM_PACKET, "packet_detail": pdetail,
                       "stance_agreement": MISSING, "relative_performance": None, "reasons_for": [],
                       "reasons_against": [], "evidence_count": None, "echo_note": ECHO_NOTE if pstance != "NONE"
                       else ONE_SOURCE_NOTE, "published": [], "live_scenarios": [], "decision_scenarios": [],
                       "kill_level": None, "coverage": "DAY_STORY"}
            if b:
                etfs[t]["benchmarks"] = _benchmarks(metrics, t, groups.get(t), rotation["sectors"], b, windows, bands)
            continue
        flow = story.get("flow") or {}
        trade = story.get("trade") or {}
        mstance = measured_stance(flow.get("label"))
        side = trade.get("side")
        for_, against, counts = _reasons(story, side, pstance, mstance, cap)
        etfs[t] = {
            "name": story.get("name"), "kind": story.get("kind"),
            "stance_measured": mstance, "stance_measured_source": MEASURED,
            "missing_reason": None if mstance != MISSING else str(flow.get("text") or "relative performance missing"),
            "stance_packet": pstance, "stance_packet_source": LLM_PACKET, "packet_detail": pdetail,
            "stance_agreement": agreement(mstance, pstance),
            "relative_performance": {"label": flow.get("label"), "text": flow.get("text"),
                                     "relative_pp": flow.get("relative_pp"), "source": MEASURED},
            "volume_ratio": (story.get("volume") or {}).get("ratio"),
            "record": trade.get("record"),
            "reasons_for": for_, "reasons_against": against, "evidence_count": counts,
            "echo_note": ECHO_NOTE if pstance != "NONE" else ONE_SOURCE_NOTE,
            "published": _published(story.get("published") or []),
            "live_scenarios": _live(story.get("live") or []),
            "decision_scenarios": _scenarios(t, trade, against, counts, horizon) if mstance != MISSING else [],
            "kill_level": trade.get("invalidation") if side in ("CALL", "PUT") else None,
            "coverage": "DAY_STORY",
        }
        if b:
            etfs[t]["benchmarks"] = _benchmarks(metrics, t, groups.get(t), rotation["sectors"], b, windows, bands)

    for t, spec in derived.items():  # T7d: leveraged and inverse ETFs take their underlying's read
        if t not in tickers:
            continue
        pstance, pdetail = packet_stance(t, lead, avoid, bias)
        und, sign = spec["underlying"], int(spec.get("sign", 1))
        base = etfs.get(und) or {}
        src_read = base.get("relative_performance") or None
        read = None
        if src_read and src_read.get("label") not in (None, MISSING):
            label = FLIP_LABEL.get(src_read["label"], src_read["label"]) if sign < 0 else src_read["label"]
            read = {"reference": src_read.get("reference", "SPY"), "label": label,
                    "relative_pp": src_read.get("relative_pp"), "source": MEASURED,
                    "text": (f"Read of {und}" + (", inverted" if sign < 0 else "") + f": {src_read.get('text')}")}
        etfs[t] = _universe_entry(t, groups.get(t), coverage="DERIVED", read=read, pstance=pstance, pdetail=pdetail,
                                  horizon=horizon, derived_from=f"{und} (x{sign})",
                                  missing_reason=None if read else f"{t}: its underlying {und} has no read on this build")
        etfs[t]["benchmarks"] = {"market": None, "peer": None, "split": "DERIVED", "derived_from": f"{und} (x{sign})"}

    for t, entry in etfs.items():
        entry.setdefault("coverage", "DAY_STORY")
        entry.setdefault("benchmarks", MISSING)
        _attach_t7(entry, t, ev, usmi)

    return {
        "meta": {"version": cfg["version"], "as_of_session": payload.get("as_of_session"),
                 "build_kind": (payload.get("build") or {}).get("kind"), "built_at_utc": payload.get("built_at_utc"),
                 "next_session": next_session, "horizon_sessions": horizon,
                 "benchmark": rotation.get("benchmark"),
                 "relative_performance_note": ("Relative return against the benchmark; not reported ETF creations "
                                               "or redemptions."),
                 "sources": {name: {"name": r.get("name"), "status": r.get("status"), "as_of": r.get("as_of"),
                                    "note": r.get("note")} for name, r in external.items() if isinstance(r, Mapping)},
                 "authority": AUTHORITY},
        "events_next_close": events,
        "event_intelligence": (dict(ev, as_of=(external.get("event_payload") or {}).get("as_of")) if ev else
                               {"status": MISSING, "reason": (intel.get("event_intelligence") or {}).get("reason")
                                or "no event file read on this build"}),
        "usmi_intelligence": (dict(usmi, as_of=(external.get("us_money_index") or {}).get("as_of")) if usmi else
                              {"status": MISSING, "reason": (intel.get("usmi_intelligence") or {}).get("reason")
                               or "no USMI file read on this build"}),
        "etfs": etfs,
    }


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write(doc: Mapping, target_dir: Path, *, as_of: str | None) -> Path:
    """Current builds write the dated file and replace etf_intelligence_latest.json; an --as-of rebuild writes its
    own file only and never replaces latest."""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    meta = doc["meta"]
    text = json.dumps(doc, indent=1, default=str)
    if as_of:
        path = target_dir / f"etf_intelligence_asof_{as_of}.json"
        _atomic_write(path, text)
        return path
    path = target_dir / f"etf_intelligence_{meta['as_of_session']}_{meta['build_kind']}.json"
    _atomic_write(path, text)
    _atomic_write(target_dir / "etf_intelligence_latest.json", text)
    return path
