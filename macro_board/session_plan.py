"""Next session plan (ACK 10 Oct 2026): the board's pieces in a veteran's order.

1. The call - what the market did, whether it accepted the news, breadth, measured macro pressure.
2. Scenarios per index ETF - base / up / down with triggers from the board's own levels, size from
   the daily move and the option market, what followed the same reaction in history, expression.
3. A time-ordered checklist for the next session.
4. Where the opportunity is - leaders, sectors whose strength holds on every window, pipeline
   candidates with or against the tape.
5. What would change the view.
6. The jigsaw - every input with what it points to, whether it agrees with the tape, how fresh it is.

Sentences are assembled from measured fields (ACK: templates, not an LLM); wording lives in
config["session_plan"]. Research only: the plan never scores, ranks for the pipeline or gates, and a
scenario is marked only where history measured a lean. Missing input is MISSING, never neutral.
"""

from __future__ import annotations

import math
from typing import Mapping, Sequence

from macro_board.decision_points import LEVEL_LABELS

PHASES = ["PRE_OPEN", "OPEN", "INTRADAY", "CLOSE", "WATCH"]
GROUPS = ["MEASURED", "MODEL", "LLM"]
STANCES = ["SUPPORTS", "OPPOSES", "NEUTRAL", "MISSING"]

# A reaction key -> which way the session closed. A rejected down gap means buyers took it back.
CLOSED = {"ACCEPTED_UP": "UP", "REJECTED_GAP_DOWN": "UP", "ACCEPTED_DOWN": "DOWN", "REJECTED_GAP_UP": "DOWN",
          "ABSORBED": "NONE"}
LABELS = {**LEVEL_LABELS, "one_implied_move": "one implied move", "one_daily_move": "one daily move"}


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _pct(x, digits=2):
    return "n/a" if x is None else f"{x:+.{digits}f}%"


def _pp(x, digits=1):
    return "n/a" if x is None else f"{x:+.{digits}f} pts"


def _fmt(x, digits=2):
    x = _num(x)
    return "n/a" if x is None else f"{x:.{digits}f}"


# -- 1. the call ---------------------------------------------------------------------------------------

def tape(instruments: Mapping, focus: Sequence[str], *, majority: int) -> dict:
    """Which way the index ETFs closed, read from the review's reaction keys."""
    rows = {}
    for t in focus:
        r = instruments.get(t) or {}
        key = r.get("key") or r.get("label") or "UNKNOWN"
        rows[t] = {"key": key, "closed": CLOSED.get(key, "UNKNOWN"), "close_pct": r.get("close_pct")}
    up = [t for t, r in rows.items() if r["closed"] == "UP"]
    down = [t for t, r in rows.items() if r["closed"] == "DOWN"]
    known = [t for t, r in rows.items() if r["closed"] != "UNKNOWN"]
    if len(known) < majority:
        direction = "UNKNOWN"
    elif len(up) >= majority:
        direction = "UP"
    elif len(down) >= majority:
        direction = "DOWN"
    else:
        direction = "MIXED"
    return {"direction": direction, "up": up, "down": down,
            "absorbed": [t for t, r in rows.items() if r["closed"] == "NONE"],
            "unknown": [t for t, r in rows.items() if r["closed"] == "UNKNOWN"], "rows": rows}


def _condition_labels(payload: Mapping) -> dict:
    return {m["key"]: m.get("label", m["key"]) for m in (payload.get("conditions") or {}).get("meta") or []}


def market_call(payload: Mapping, tp: Mapping, instruments: Mapping, cfg: Mapping) -> dict:
    breadth = (((payload.get("opportunity") or {}).get("leadership") or {}).get("breadth") or {})
    state = breadth.get("state") or "UNKNOWN"
    qual = {"BROAD": "BROAD", "CONCENTRATED": "NARROW"}.get(state, "UNKNOWN")
    key = tp["direction"] if tp["direction"] in ("MIXED", "UNKNOWN") else f"{tp['direction']}_{qual}"
    labels = _condition_labels(payload)
    spy = (payload.get("etfs") or {}).get("SPY") or {}
    resp = (((spy.get("decision") or {}).get("response") or {}).get("20") or {})
    head = [labels.get(h, h) for h in resp.get("headwinds") or []]
    tail = [labels.get(h, h) for h in resp.get("tailwinds") or []]
    sentences = [(payload.get("review") or {}).get("headline") or "No reaction reading."]
    gap = _num(breadth.get("rsp_minus_spy_20d_pp"))
    if state == "CONCENTRATED":
        sentences.append(f"Participation is narrow: equal-weight RSP {'lagged' if (gap or 0) < 0 else 'trailed'} SPY by "
                         f"{abs(gap or 0):.1f} pts over 20 sessions.")
    elif state == "BROAD":
        sentences.append(f"Participation is broad: equal-weight RSP kept pace with SPY ({_pp(gap)} over 20 sessions).")
    else:
        sentences.append("Breadth is unknown (no RSP or holdings reading).")
    if head or tail:
        sentences.append(f"Measured macro pressure on SPY (20 sessions): headwinds {', '.join(head) or 'none'}; "
                         f"tailwinds {', '.join(tail) or 'none'}.")
    else:
        sentences.append("No measured macro pressure on SPY over 20 sessions.")
    spy_s = instruments.get("SPY")
    if spy_s:
        implied = spy_s.get("implied_move_pct")
        sentences.append(f"A normal day for SPY is ±{spy_s['daily_move_pct']:.2f}%"
                         + (f"; options price ±{implied:.2f}% for the next session ({spy_s['implied_source']})."
                            if implied is not None else "; no option pricing for the next session."))
    return {"key": key, "tape": tp, "breadth": state, "headwinds": head, "tailwinds": tail,
            "sentences": sentences, "approach": (cfg.get("approach") or {}).get(key), "conflict": None}


# -- 2. scenarios -----------------------------------------------------------------------------------------

GEX_LEVELS = ("call_wall", "put_wall", "gamma_flip")


def _level(name: str, level: float, ref: float, daily: float | None, dated: str | None = None) -> dict:
    pct = (level / ref - 1.0) * 100.0
    label = LABELS.get(name, name) + (f" ({dated})" if dated and name in GEX_LEVELS else "")
    return {"name": name, "label": label, "level": round(level, 4), "distance_pct": round(pct, 4),
            "distance_daily_moves": round(abs(pct) / daily, 2) if daily else None}


def _implied(etf: Mapping) -> tuple[float | None, str | None]:
    opt = etf.get("options") or {}
    move = ((opt.get("moves") or {}).get("1") or {})
    if opt.get("status") == "FRESH" and _num(move.get("implied_move_pct")) is not None:
        return float(move["implied_move_pct"]), f"ATM straddle quoted {opt.get('quote_date')}"
    tt = ((etf.get("tastytrade") or {}).get("iv_expected_abs_move_pct") or {}).get("1")
    if _num(tt) is not None:
        return float(tt), "tastytrade IV"
    return None, None


def expression(etf: Mapping, cfg: Mapping) -> dict:
    """How the option market prices the move against history; runway longer than the move."""
    h = str(cfg["expression_horizon"])
    opt = etf.get("options") or {}
    move = ((opt.get("moves") or {}).get(h) or {})
    ratio = _num(move.get("priced_vs_history"))
    if opt.get("status") != "FRESH" or ratio is None:
        pricing = "UNKNOWN"
    elif ratio < float(cfg["options_cheap_below"]):
        pricing = "CHEAP"
    elif ratio > float(cfg["options_rich_above"]):
        pricing = "RICH"
    else:
        pricing = "FAIR"
    tt = etf.get("tastytrade") or {}
    return {"horizon": h, "pricing": pricing, "priced_vs_history": ratio,
            "implied_move_pct": _num(move.get("implied_move_pct")), "analog_mean_abs_pct": _num(move.get("analog_mean_abs_pct")),
            "quote_date": opt.get("quote_date"), "iv_rank_pct": _num(tt.get("iv_rank_pct")),
            "iv_minus_hv_pp": _num(tt.get("iv_hv_diff_pct")),
            "runway_sessions": max(1, math.ceil(int(h) * float(cfg["runway_multiple"]))),
            "text": (cfg.get("expression_text") or {}).get(pricing)}


def _history(scored: Mapping, etf: Mapping, cfg: Mapping) -> tuple[list, str | None]:
    rows, leans = [], None
    key = ((scored.get("today") or {}).get("key")) or "UNKNOWN"
    for h in cfg["history_horizons"]:
        ev = ((scored.get("evidence") or {}).get(str(h)) or {})
        a = ev.get("analog") or {}
        lean = ev.get("lean") or "MISSING"
        if a.get("n"):
            lean_text = {"UP": "history leans up", "DOWN": "history leans down",
                         "NO_CLEAR_LEAN": "no clear lean"}.get(lean, "too few cases to say")
            text = (f"After {a['n']} past sessions with the same reaction ({key}), the next {h} session"
                    f"{'s' if str(h) != '1' else ''} averaged {_pct(_num(a.get('mean_pct')))} and rose "
                    f"{(_num(a.get('hit_rate')) or 0):.0%} of the time: {lean_text}.")
        else:
            text = f"No history for the reaction {key} over {h} session(s)."
        rows.append({"source": "reaction history", "horizon": str(h), "lean": lean, "text": text,
                     "n": a.get("n"), "mean_pct": a.get("mean_pct"), "hit_rate": a.get("hit_rate")})
        if leans is None and lean in ("UP", "DOWN"):
            leans = lean
    for h in cfg["history_horizons"]:
        ev = ((etf.get("evidence") or {}).get(str(h)) or {})
        a = ev.get("analog") or {}
        lean = ev.get("lean") or "MISSING"
        if a.get("n"):
            rows.append({"source": "macro analogs", "horizon": str(h), "lean": lean, "n": a.get("n"),
                         "mean_pct": a.get("mean_pct"), "hit_rate": a.get("hit_rate"),
                         "text": f"Past sessions with today's macro conditions ({a['n']}): next {h} averaged "
                                 f"{_pct(_num(a.get('mean_pct')))}, up {(_num(a.get('hit_rate')) or 0):.0%} "
                                 f"({'lean ' + lean.lower() if lean in ('UP', 'DOWN') else 'no clear lean'})."})
    return rows, leans


def scenarios(ticker: str, etf: Mapping, room: Mapping, scored: Mapping, cfg: Mapping,
              as_of: str | None = None) -> dict | None:
    ref = _num(room.get("current")) or _num(room.get("close"))
    if ref is None:
        return None
    daily = _num(room.get("daily_move_pct"))
    implied, source = _implied(etf)
    step = implied or daily
    levels = [(n, float(v)) for n, v in (room.get("levels") or {}).items() if _num(v) and float(v) > 0]
    above = sorted([x for x in levels if x[1] > ref], key=lambda x: x[1])
    below = sorted([x for x in levels if x[1] < ref], key=lambda x: -x[1])
    fallback = "one_implied_move" if implied else "one_daily_move"
    gex_date = room.get("gex_as_of") if room.get("gex_as_of") and room.get("gex_as_of") != as_of else None
    far = _num(cfg.get("max_target_daily_moves"))

    def side(ladder, sign):
        """(trigger, target, next mapped level when it is too far to be the target)."""
        trigger = _level(*ladder[0], ref, daily, gex_date) if ladder else None
        mapped = _level(*ladder[1], ref, daily, gex_date) if len(ladder) > 1 else None
        if mapped and not (far and mapped["distance_daily_moves"] is not None and mapped["distance_daily_moves"] > far):
            return trigger, mapped, None
        if step is None:
            return trigger, mapped, None
        base = trigger["level"] if trigger else ref
        return trigger, _level(fallback, base * (1 + sign * step / 100.0), ref, daily), mapped

    up_t, up_target, up_far = side(above, +1)
    dn_t, dn_target, dn_far = side(below, -1)
    history, leans = _history(scored or {}, etf, cfg)
    expr = expression(etf, cfg)
    f = lambda x: f"{x['label']} {x['level']:.2f} ({_pct(x['distance_pct'])}" + (
        f", {x['distance_daily_moves']} daily moves)" if x["distance_daily_moves"] is not None else ")")
    base = {"low": dn_t, "high": up_t, "history_leans_here": False,
            "text": (f"Holds between {f(dn_t) if dn_t else 'no level below'} and {f(up_t) if up_t else 'no level above'}: "
                     "two-way trade inside the range; no new position until a level breaks.")}
    up = {"trigger": up_t, "target": up_target, "history_leans_here": leans == "UP",
          "text": (f"Clears {f(up_t)} → next {f(up_target)}." if up_t and up_target else
                   "No level above in the board's map."),
          "expression": "long calls or shares", "invalidation": dn_t, "next_mapped": up_far}
    down = {"trigger": dn_t, "target": dn_target, "history_leans_here": leans == "DOWN",
            "text": (f"Loses {f(dn_t)} → next {f(dn_target)}." if dn_t and dn_target else
                     "No level below in the board's map."),
            "expression": "long puts, or stand aside", "invalidation": up_t, "next_mapped": dn_far}
    return {"ticker": ticker, "reference": round(ref, 4), "basis": room.get("current_basis") or "CLOSE",
            "gex_as_of": room.get("gex_as_of"),
            "daily_move_pct": daily, "implied_move_pct": implied, "implied_source": source,
            "base": base, "up": up, "down": down, "history": history, "history_leans": leans, "expression": expr}


# -- 3. checklist ------------------------------------------------------------------------------------------

def _clock(time_et) -> tuple[str, str | None]:
    """(phase, sort key) for an ET time; BMO/AMC earnings map to before the open / after the close."""
    t = str(time_et or "").strip().upper()
    if t in ("BMO", "BEFORE OPEN", "PRE"):
        return "PRE_OPEN", "07:00"
    if t in ("AMC", "AFTER CLOSE", "POST"):
        return "CLOSE", "16:05"
    if len(t) == 5 and t[2] == ":" and t.replace(":", "").isdigit():
        return ("PRE_OPEN" if t < "09:30" else "INTRADAY" if t < "16:00" else "CLOSE"), t
    return "INTRADAY", None


def checklist(payload: Mapping, instruments: Mapping, tp: Mapping, cfg: Mapping) -> list:
    items = []
    dp = payload.get("decision_points") or {}
    ov = payload.get("overnight") or {}
    if ov.get("status") in (None, "MISSING", "UNREADABLE") or ov.get("us_reference_session") != payload.get("as_of_session"):
        items.append({"phase": "PRE_OPEN", "time_et": None, "sort": "00:00", "source": "runner",
                      "item": "No overnight capture after this close: run the PreOpen inputs (Run-MacroInputs.ps1 -Session PreOpen) "
                              "before the open for futures, VIX, FX, Asia/Europe and the 08:30 prints."})
    else:
        for row in ((ov.get("groups") or {}).get("us_futures") or []):
            ch = _num(row.get("change_pct"))
            if ch is None:
                continue
            items.append({"phase": "PRE_OPEN", "time_et": None, "sort": "00:01", "source": "overnight capture",
                          "item": f"{row.get('name')}: {_pct(ch)} vs the close. A move with the tape ({tp['direction'].lower()}) "
                                  f"keeps the base case; against it by more than {cfg['gap_daily_moves']} daily moves puts the "
                                  "opposite scenario in play."})
    for c in dp.get("calendar") or []:
        if c.get("sessions_ahead") != 1:
            continue
        phase, key = _clock(c.get("time_et"))
        when = c.get("time_et") if key and key not in ("07:00", "16:05") else None
        note = {"07:00": " (before the open)", "16:05": " (after the close)"}.get(key or "", "")
        items.append({"phase": phase, "time_et": when, "sort": key or "12:00", "source": c.get("source"),
                      "item": f"{c.get('name')}{note}" + (f" at {when} ET" if when else "") + f" [{c.get('kind')}]"})
    for t, s in instruments.items():
        lo, hi = s["down"]["trigger"], s["up"]["trigger"]
        parts = []
        if lo:
            parts.append(f"holds above {lo['label']} {lo['level']:.2f} = base/up intact; loses it = down case"
                         + (f" toward {s['down']['target']['label']} {s['down']['target']['level']:.2f}" if s["down"]["target"] else ""))
        if hi:
            parts.append(f"clears {hi['label']} {hi['level']:.2f} = up case"
                         + (f" toward {s['up']['target']['label']} {s['up']['target']['level']:.2f}" if s["up"]["target"] else ""))
        items.append({"phase": "OPEN", "time_et": "09:30", "sort": "09:30", "source": "board levels",
                      "item": f"{t}: " + "; ".join(parts) if parts else f"{t}: no levels mapped"})
    items.append({"phase": "OPEN", "time_et": "09:30", "sort": "09:31", "source": "board breadth",
                  "item": "First hour: equal-weight RSP keeping pace with SPY confirms a broad move; RSP lagging means "
                          "the move is carried by a few large names."})
    for u in ((dp.get("unscheduled") or {}).get("items") or [])[: int(cfg["max_unscheduled"])]:
        items.append({"phase": "WATCH", "time_et": None, "sort": "99:99", "source": u.get("source"),
                      "item": f"{u.get('name')}: confirms if {u.get('confirms')}; fails if {u.get('fails')}"})
    words = cfg["scenario_verdict_text"]
    names = {sc.get("id"): sc.get("name") for sc in ((payload.get("scenario_watch") or {}).get("library") or [])}
    for s in ((payload.get("scenario_watch") or {}).get("live") or []):
        if s.get("ticker") not in cfg["focus"] or s.get("state") not in ("TRIGGERED", "WATCHING"):
            continue
        rec = s.get("record") or {}
        history = words.get(rec.get("verdict"), words["THIN"])
        if rec.get("n"):
            history += f" ({rec['n']} triggers, {rec.get('n_eff', 0)} independent)"
        if rec.get("verdict") in ("EDGE", "OPPOSITE"):
            history += "; " + cfg["scenario_fdr_text"]["pass" if rec.get("survives_fdr") else "fail"]
        phase = "OPEN" if s["state"] == "TRIGGERED" else "CLOSE"
        items.append({"phase": phase, "time_et": "09:30" if phase == "OPEN" else "16:00",
                      "sort": "09:32" if phase == "OPEN" else "16:00", "source": "scenario watch",
                      "item": f"{s['ticker']} {names.get(s['scenario'], s['scenario'])} ({s.get('side')}): {s.get('text')} "
                              f"{history[0].upper() + history[1:]}."})
    items.sort(key=lambda i: (PHASES.index(i["phase"]), i["sort"]))
    for i in items:
        i.pop("sort", None)
    return items


# -- 4. opportunity ----------------------------------------------------------------------------------------

def opportunity(payload: Mapping, tp: Mapping, cfg: Mapping) -> dict:
    opp = payload.get("opportunity") or {}
    windows = cfg["strength_windows"]
    strength, weakness, defensive = [], [], []
    for row in opp.get("sectors") or []:
        w = row.get("windows") or {}
        labels = [((w.get(x) or {}).get("label")) for x in windows]
        rel = (w.get(windows[-1]) or {}).get("relative_pp")
        entry = {"ticker": row.get("ticker"), "labels": dict(zip(windows, labels)), "relative_pp": rel,
                 "constituents": {x: (w.get(x) or {}).get("constituents") for x in windows}}
        if all(lab == "OUTPERFORMING_AND_RISING" for lab in labels):
            strength.append(entry)
        elif all(lab == "UNDERPERFORMING_AND_FALLING" for lab in labels):
            weakness.append(entry)
        if any(lab == "OUTPERFORMING_WHILE_FALLING" for lab in labels):
            defensive.append(entry)
    strength.sort(key=lambda e: -(e["relative_pp"] or 0))
    weakness.sort(key=lambda e: e["relative_pp"] or 0)
    sides = {"CALL": "UP", "PUT": "DOWN"}
    cands = []
    for t, etf in (payload.get("etfs") or {}).items():
        p = etf.get("pipeline") or {}
        side = sides.get(p.get("canonical_direction"))
        if not side:
            continue
        agrees = (side == tp["direction"]) if tp["direction"] in ("UP", "DOWN") else None
        cands.append({"ticker": t, "direction": p.get("canonical_direction"), "verdict": p.get("options_verdict"),
                      "agrees_with_tape": agrees})
    focus = list(cfg["focus"])
    cands.sort(key=lambda c: (c["verdict"] != "ARMED", c["ticker"] not in focus,
                              focus.index(c["ticker"]) if c["ticker"] in focus else 0,
                              c["agrees_with_tape"] is not True, c["ticker"]))
    lead = (opp.get("leadership") or {}).get("windows") or {}
    leader = {h: {"leader": v.get("leader"), "qqq_minus_spy_pp": v.get("qqq_minus_spy_pp")} for h, v in lead.items()}
    return {"leadership": leader, "strength": strength[: int(cfg["max_sectors"])],
            "weakness": weakness[: int(cfg["max_sectors"])], "defensive": defensive[: int(cfg["max_sectors"])],
            "pipeline": cands[: int(cfg["max_pipeline"])]}


# -- 5. what would change the view ---------------------------------------------------------------------------

def change_view(payload: Mapping, instruments: Mapping, tp: Mapping, cfg: Mapping) -> list:
    items = []
    for t in ("SPY", "QQQ"):
        s = instruments.get(t)
        if not s:
            continue
        if tp["direction"] in ("UP", "MIXED", "UNKNOWN") and s["down"]["trigger"]:
            lvl = s["down"]["trigger"]
            items.append({"source": "board levels", "text": f"{t} closes below {lvl['label']} {lvl['level']:.2f}: the up case is off."})
        if tp["direction"] in ("DOWN", "MIXED", "UNKNOWN") and s["up"]["trigger"]:
            lvl = s["up"]["trigger"]
            items.append({"source": "board levels", "text": f"{t} closes above {lvl['label']} {lvl['level']:.2f}: the down case is off."})
    if (payload.get("opportunity") or {}).get("leadership", {}).get("breadth", {}).get("state") == "CONCENTRATED":
        items.append({"source": "board breadth", "text": "Equal-weight RSP starts beating SPY: the move is broadening."})
    counter = ((payload.get("intel") or {}).get("events") or {}).get("counter_case") or {}
    if isinstance(counter, Mapping):
        for c in (counter.get("reversal_or_neutralisation_conditions") or [])[: int(cfg["max_counter_conditions"])]:
            items.append({"source": "event payload (LLM)", "text": str(c)})
    return items


# -- 6. jigsaw --------------------------------------------------------------------------------------------------

def _dir_word(text) -> str:
    t = str(text or "").upper()
    if "BULL" in t or "RISK_ON" in t:
        return "UP"
    if "BEAR" in t or "RISK_OFF" in t:
        return "DOWN"
    return "NEUTRAL"


def _fresh(payload: Mapping, name: str | None) -> tuple[str, str | None]:
    if name is None:
        return "FRESH", payload.get("as_of_session")
    e = (payload.get("external") or {}).get(name) or {}
    return e.get("status") or "MISSING", (str(e["as_of"])[:10] if e.get("as_of") else None)


def jigsaw(payload: Mapping, tp: Mapping, instruments: Mapping, cfg: Mapping) -> dict:
    intel = payload.get("intel") or {}
    etfs = payload.get("etfs") or {}
    spy = etfs.get("SPY") or {}
    labels = _condition_labels(payload)
    pieces = []

    def add(key, label, group, points, says, external=None, tab="Daily review"):
        freshness, as_of = _fresh(payload, external)
        if points == "MISSING":
            freshness = "MISSING" if freshness == "FRESH" else freshness
        pieces.append({"key": key, "piece": label, "group": group, "points": points, "says": says,
                       "freshness": freshness, "as_of": as_of, "tab": tab})

    add("reaction", "Market reaction", "MEASURED", tp["direction"] if tp["direction"] in ("UP", "DOWN") else
        ("NEUTRAL" if tp["direction"] == "MIXED" else "MISSING"),
        f"Closed up: {', '.join(tp['up']) or 'none'}; down: {', '.join(tp['down']) or 'none'}; absorbed: {', '.join(tp['absorbed']) or 'none'}.")
    breadth = (((payload.get("opportunity") or {}).get("leadership") or {}).get("breadth") or {})
    b = breadth.get("state")
    add("breadth", "Breadth (RSP vs SPY)", "MEASURED",
        {"BROAD": "CONFIRMS", "CONCENTRATED": "WEAKENS"}.get(b, "MISSING"),
        f"{b or 'UNKNOWN'}: RSP minus SPY {_pp(_num(breadth.get('rsp_minus_spy_20d_pp')))} over 20 sessions.")
    trend = ((payload.get("conditions") or {}).get("current") or {}).get("market_trend")
    add("trend", "SPY trend", "MEASURED",
        {"ABOVE_BOTH": "UP", "BELOW_BOTH": "DOWN"}.get(trend, "NEUTRAL" if trend else "MISSING"),
        f"{trend or 'MISSING'} (close vs 50- and 200-session averages).", tab="Overview")
    resp = (((spy.get("decision") or {}).get("response") or {}).get("20") or {})
    head, tail = resp.get("headwinds") or [], resp.get("tailwinds") or []
    add("macro_response", "Measured macro pressure on SPY", "MEASURED",
        "MISSING" if not resp else "UP" if len(tail) > len(head) else "DOWN" if len(head) > len(tail) else "NEUTRAL",
        f"Headwinds: {', '.join(labels.get(h, h) for h in head) or 'none'}; tailwinds: {', '.join(labels.get(h, h) for h in tail) or 'none'}.",
        tab="Overview")
    for t in ("SPY", "QQQ"):
        ev = ((etfs.get(t) or {}).get("evidence") or {})
        leans = {h: (ev.get(h) or {}).get("lean") for h in ("1", "5", "20")}
        known = [v for v in leans.values() if v]
        pts = "MISSING" if not known else ("UP" if "UP" in known and "DOWN" not in known else
                                           "DOWN" if "DOWN" in known and "UP" not in known else "NEUTRAL")
        add(f"lean_{t.lower()}", f"{t} macro-analog lean", "MEASURED", pts,
            "; ".join(f"{h}d {v or 'MISSING'}" for h, v in leans.items()), tab="ETF matrix")
    scored = (((payload.get("review") or {}).get("scored") or {}).get("SPY") or {})
    s_lean = (((scored.get("evidence") or {}).get("1") or {}).get("lean"))
    add("reaction_history", "What followed the same reaction (SPY)", "MEASURED",
        {"UP": "UP", "DOWN": "DOWN"}.get(s_lean, "NEUTRAL" if s_lean else "MISSING"),
        (instruments.get("SPY") or {}).get("history", [{}])[0].get("text", "No history.") if instruments.get("SPY") else "No history.")
    mom = ((((spy.get("momentum") or {}).get("evidence") or {}).get("streak") or {}).get("1") or {}).get("lean")
    add("momentum", "SPY streak history", "MEASURED", {"UP": "UP", "DOWN": "DOWN"}.get(mom, "NEUTRAL" if mom else "MISSING"),
        f"What followed similar streaks: {mom or 'MISSING'}.", tab="ETF matrix")
    ex = (instruments.get("SPY") or {}).get("expression") or expression(spy, cfg)
    add("options", "Option pricing (SPY)", "MEASURED", "NEUTRAL" if ex["pricing"] != "UNKNOWN" else "MISSING",
        f"{ex['pricing']}: implied vs history {ex['priced_vs_history']}; shapes the expression, not the direction.", tab="ETF matrix")

    mi_block = payload.get("money_index") or {}
    mi_read = mi_block.get("reading") or {}
    h_mi = str(cfg.get("check_horizon", "5"))
    spy_band = ((((mi_block.get("per_etf") or {}).get("SPY") or {}).get("band_evidence") or {}).get(h_mi) or {})
    if mi_read.get("score") is None:
        add("money_index_local", "Money Index (measured here)", "MEASURED", "MISSING",
            f"No measured score (missing: {', '.join(mi_read.get('missing') or []) or 'all'}).", tab="Macro intelligence")
    else:
        lean = spy_band.get("lean")
        a_, b_ = spy_band.get("analog") or {}, spy_band.get("base") or {}
        add("money_index_local", "Money Index (measured here)", "MEASURED",
            {"UP": "UP", "DOWN": "DOWN"}.get(lean, "NEUTRAL" if lean else "MISSING"),
            f"Risk-off {mi_read.get('score')}/100 ({mi_read.get('band')}); after past {mi_read.get('band')} sessions SPY next "
            f"{h_mi}d averaged {_pct(_num(a_.get('mean_pct')))} vs {_pct(_num(b_.get('mean_pct')))} on all days.",
            tab="Macro intelligence")

    p = (payload.get("overnight") or {})
    if p.get("status") in (None, "MISSING", "UNREADABLE") or p.get("us_reference_session") != payload.get("as_of_session"):
        add("overnight", "Overnight capture", "MEASURED", "MISSING",
            f"No capture after the {payload.get('as_of_session')} close (latest refers to {p.get('us_reference_session') or 'none'}).",
            external="overnight", tab="Overview")
    else:
        es = next((r for r in ((p.get("groups") or {}).get("us_futures") or []) if r.get("symbol") == "ES=F"), {})
        ch = _num(es.get("change_pct"))
        add("overnight", "Overnight capture", "MEASURED",
            "MISSING" if ch is None else "UP" if ch > 0 else "DOWN" if ch < 0 else "NEUTRAL",
            f"S&P futures {_pct(ch)} vs the close.", external="overnight", tab="Overview")

    gex = next((r for r in intel.get("gex") or [] if r.get("Ticker") == "SPY"), None)
    add("gex", "Dealer gamma (SPY)", "MODEL", "NEUTRAL" if gex else "MISSING",
        (f"{gex.get('Regime')} gamma, flip {_fmt(gex.get('Gamma_Flip'))}: negative gamma tends to amplify moves (convention, "
         "not measured here)." if gex else "No GEX record."), external="gex", tab="Macro intelligence")
    vix = (intel.get("vix_engine") or [None])[-1]
    structure = (vix or {}).get("VIX_Structure")
    add("vix", "VIX term structure", "MODEL",
        {"CONTANGO": "UP", "BACKWARDATION": "DOWN"}.get(str(structure).upper(), "NEUTRAL" if vix else "MISSING"),
        f"VIX {_fmt((vix or {}).get('VIX_Direct'))} in {structure or 'MISSING'} (contango = calm carry; convention, uncalibrated).",
        external="vix_engine", tab="Macro intelligence")
    comp = ((intel.get("bond") or {}).get("composite") or {})
    add("bond", "Bond macro score", "MODEL",
        "MISSING" if not comp else "UP" if comp.get("trade_go") else "DOWN",
        f"Score {comp.get('macro_bond_score')}/100, trade_go {comp.get('trade_go')}." if comp else "No bond state.",
        external="bond_state", tab="Macro intelligence")
    fb = next((r for r in intel.get("forward_bias") or [] if str(r.get("horizon", "")).startswith("short")), None) \
        or (intel.get("forward_bias") or [None])[-1]
    add("forward_bias", "Forward bias model", "MODEL", _dir_word((fb or {}).get("direction")) if fb else "MISSING",
        f"{(fb or {}).get('horizon')}: {(fb or {}).get('direction')}." if fb else "No forward-bias record.",
        external="forward_bias", tab="Macro intelligence")
    pipe = (spy.get("pipeline") or {})
    side = {"CALL": "UP", "PUT": "DOWN"}.get(pipe.get("canonical_direction"))
    add("pipeline", "Pipeline proposal (SPY)", "MODEL", side or "MISSING",
        f"{pipe.get('canonical_direction') or 'none'} · {pipe.get('options_verdict') or ''}".strip(" ·"), tab="Desk card")

    pk = intel.get("packet")
    add("packet", "Macro packet", "LLM", _dir_word(pk.get("dir_bias")) if pk else "MISSING",
        f"{pk.get('dir_bias')} · {pk.get('risk_on_off_switch')}" if pk else "No macro packet.",
        external="macro_packet", tab="Macro intelligence")
    u = intel.get("usmi")
    if u and _num(u.get("score")) is not None:
        score = float(u["score"])
        pts = "DOWN" if score >= float(cfg["usmi_risk_off_min"]) else "UP" if score <= float(cfg["usmi_risk_on_max"]) else "NEUTRAL"
        says = f"Risk-off transmission {score:.0f}/100 · {u.get('transmission_state')}"
    else:
        pts, says = "MISSING", "No US Money Index."
    add("usmi", "US Money Index", "LLM", pts, says, external="us_money_index", tab="Macro intelligence")
    verdict = (((intel.get("events") or {}).get("verdict")) or {})
    v = verdict.get("verdict") if isinstance(verdict, Mapping) else verdict
    add("event_payload", "Event payload", "LLM", _dir_word(v) if v else "MISSING", f"Verdict {v or 'MISSING'}.",
        external="event_payload")
    en = intel.get("enrichment")
    add("enrichment", "News enrichment", "LLM",
        {"GREEN": "UP", "RED": "DOWN"}.get(str((en or {}).get("alert_level")).upper(), "NEUTRAL" if en else "MISSING"),
        f"Alert {(en or {}).get('alert_level')} · fragility {(en or {}).get('fragility_score')}." if en else "No news enrichment.",
        external="enrichment", tab="Macro intelligence")

    direction = tp["direction"]
    for x in pieces:
        if x["points"] == "MISSING":
            x["stance"] = "MISSING"
        elif x["points"] in ("CONFIRMS", "WEAKENS"):
            x["stance"] = ("SUPPORTS" if x["points"] == "CONFIRMS" else "OPPOSES") if direction in ("UP", "DOWN") else "NEUTRAL"
        elif x["points"] == "NEUTRAL" or direction not in ("UP", "DOWN"):
            x["stance"] = "NEUTRAL"
        else:
            x["stance"] = "SUPPORTS" if x["points"] == direction else "OPPOSES"
    agreement = {g: {s: sum(1 for x in pieces if x["group"] == g and x["stance"] == s) for s in STANCES} for g in GROUPS}
    agreement["all"] = {s: sum(1 for x in pieces if x["stance"] == s) for s in STANCES}
    return {"pieces": pieces, "agreement": agreement, "tape": direction,
            "note": "Agreement is a count of inputs, not a probability; it is uncalibrated."}


def _conflict(jig: Mapping, cfg: Mapping) -> str | None:
    a = jig["agreement"]
    measured, llm = a["MEASURED"], a["LLM"]
    if measured["SUPPORTS"] > measured["OPPOSES"] and llm["OPPOSES"] > llm["SUPPORTS"]:
        names = [x["piece"] for x in jig["pieces"] if x["group"] == "LLM" and x["stance"] == "OPPOSES"]
    elif measured["OPPOSES"] > measured["SUPPORTS"] and llm["SUPPORTS"] > llm["OPPOSES"]:
        names = [x["piece"] for x in jig["pieces"] if x["group"] == "LLM" and x["stance"] == "SUPPORTS"]
    else:
        return None
    return str(cfg["conflict_note"]).format(pieces=", ".join(names))


# -- 7. per ETF, with correlation, and the pipeline's candidates (ACK 10 Oct 2026) ------------------------------

SIDE = {"CALL": "UP", "PUT": "DOWN"}


def _check(name: str, state: str, text: str) -> dict:
    return {"check": name, "state": state, "text": text}


def _versus(direction: str | None, side: str) -> str:
    if direction in (None, "UNKNOWN", "MISSING"):
        return "MISSING"
    if direction in ("NONE", "NEUTRAL", "MIXED", "NO_CLEAR_LEAN"):
        return "NEUTRAL"
    return "WITH" if direction == side else "AGAINST"


def _alignment(checks: list) -> str:
    w = sum(1 for c in checks if c["state"] == "WITH")
    a = sum(1 for c in checks if c["state"] == "AGAINST")
    if a > w:
        return "AGAINST"
    return "ALIGNED" if a == 0 and w >= 2 else "MIXED"


PIPELINE_LEVELS = ("pipeline_target", "pipeline_invalidation")


def _market_room(room: Mapping) -> dict:
    """The room with the nearest market levels only: a pipeline's own target or invalidation is not a level the
    market has to confirm (10 Oct 2026 real build: 'XBI to clear pipeline target')."""
    if not room:
        return {}
    ref, daily = _num(room.get("current")) or _num(room.get("close")), _num(room.get("daily_move_pct"))
    levels = {n: _num(v) for n, v in (room.get("levels") or {}).items() if n not in PIPELINE_LEVELS and _num(v)}
    if ref is None or not levels:
        keep = lambda x: x if x and x.get("name") not in PIPELINE_LEVELS else None
        return {**room, "above": keep(room.get("above")), "below": keep(room.get("below"))}
    above = min(((n, v) for n, v in levels.items() if v > ref), key=lambda x: x[1], default=None)
    below = max(((n, v) for n, v in levels.items() if v < ref), key=lambda x: x[1], default=None)
    return {**room, "above": _level(*above, ref, daily) if above else None, "below": _level(*below, ref, daily) if below else None}


def _etf_read(t: str, payload: Mapping, cfg: Mapping) -> dict:
    """What the board knows about one ETF, independent of any proposal."""
    etf = (payload.get("etfs") or {}).get(t) or {}
    reaction = ((payload.get("etf_reactions") or {}).get(t) or {})
    per = (((payload.get("money_index") or {}).get("per_etf") or {}).get(t) or {})
    h = str(cfg["check_horizon"])
    be = ((per.get("band_evidence") or {}).get(h) or {})
    rel = None
    for row in ((payload.get("opportunity") or {}).get("sectors") or []):
        if row.get("ticker") == t:
            rel = ((row.get("windows") or {}).get(h) or {}).get("label")
    return {"ticker": t, "etf": etf, "metrics": etf.get("metrics") or {}, "reaction": reaction.get("key") or "UNKNOWN",
            "closed": CLOSED.get(reaction.get("key"), "UNKNOWN"), "close_pct": reaction.get("close_pct"),
            "room": _market_room((payload.get("etf_levels") or {}).get(t) or {}), "per": per,
            "band_lean": be.get("lean") if be else None, "band_evidence": be or None,
            "macro_lean": (((etf.get("evidence") or {}).get(h) or {}).get("lean")), "relative": rel}


def _checks(read: Mapping, side: str, tp: Mapping, cfg: Mapping, *, own: str) -> list:
    """Evidence for or against a proposal's side; each check says what was measured."""
    h = str(cfg["check_horizon"])
    t = read["ticker"]
    out = [_check(f"{own}_tape", _versus(read["closed"], side) if read["reaction"] != "UNKNOWN" else "MISSING",
                  f"{t} {read['reaction'].replace('_', ' ').lower()} ({_pct(_num(read['close_pct']))})."),
           _check("market_tape", _versus(tp["direction"], side), f"Index ETFs closed {tp['direction'].lower()}.")]
    lean = read["band_lean"]
    be = read["band_evidence"] or {}
    a, b = be.get("analog") or {}, be.get("base") or {}
    out.append(_check("money_index_band", "MISSING" if not lean else _versus(lean, side),
                      (f"After past sessions in today's Money Index band, {t} next {h}d averaged {_pct(_num(a.get('mean_pct')))} "
                       f"vs {_pct(_num(b.get('mean_pct')))} on all days ({lean.replace('_', ' ').lower()}).") if lean else
                      f"No measured Money Index history for {t}."))
    ml = read["macro_lean"]
    out.append(_check("macro_analogs", "MISSING" if not ml else _versus(ml, side) if ml in ("UP", "DOWN") else "NEUTRAL",
                      f"Macro-analog lean {h}d: {(ml or 'MISSING').replace('_', ' ').lower()}."))
    if read["relative"]:
        rel_dir = {"OUTPERFORMING_AND_RISING": "UP", "UNDERPERFORMING_AND_FALLING": "DOWN"}.get(read["relative"], "NEUTRAL")
        out.append(_check("relative_strength", _versus(rel_dir, side),
                          f"{t} vs SPY {h}d: {read['relative'].replace('_', ' ').lower()}."))
    room = read["room"]
    obstacle = (room.get("above") if side == "UP" else room.get("below")) if room else None
    if obstacle and obstacle.get("distance_daily_moves") is not None:
        near = obstacle["distance_daily_moves"] < float(cfg["room_min_daily_moves"])
        out.append(_check("room", "AGAINST" if near else "WITH",
                          f"{LABELS.get(obstacle.get('name'), obstacle.get('name'))} {obstacle['level']:.2f} is "
                          f"{obstacle['distance_daily_moves']} daily moves {'above' if side == 'UP' else 'below'}."))
    else:
        out.append(_check("room", "MISSING", "No mapped level in the trade's direction."))
    return out


def _action(alignment: str, side: str | None, read: Mapping, cfg: Mapping, etf_name: str) -> str:
    texts = cfg.get("action_text") or {}
    room = read.get("room") or {}
    if alignment == "ALIGNED":
        lvl = room.get("below") if side == "UP" else room.get("above")
    else:
        lvl = room.get("above") if side == "UP" else room.get("below")
    level = f"{LABELS.get(lvl.get('name'), lvl.get('name'))} {lvl['level']:.2f}" if lvl else "its nearest level"
    confirm, fail = ("clear", "loses") if side == "UP" else ("break below", "climbs back above")
    return str(texts.get(alignment, "")).format(etf=etf_name, level=level, confirm=confirm, fail=fail)


def etf_rows(payload: Mapping, tp: Mapping, instruments: Mapping, cfg: Mapping) -> list:
    spy = instruments.get("SPY") or {}
    down_t = ((spy.get("down") or {}).get("target") or {}).get("distance_pct")
    up_t = ((spy.get("up") or {}).get("target") or {}).get("distance_pct")
    names = list(dict.fromkeys(list((payload.get("etfs") or {}).keys()) + list((payload.get("etf_levels") or {}).keys())))
    rows = []
    for t in names:
        read = _etf_read(t, payload, cfg)
        if read["metrics"].get("status") == "MISSING":
            continue
        per = read["per"]
        beta = _num(((per.get("spy") or {}).get("beta")))
        prop = (read["etf"].get("pipeline") or {})
        side = SIDE.get(prop.get("canonical_direction"))
        checks = _checks(read, side, tp, cfg, own="own") if side else []
        alignment = _alignment(checks) if side else "NO_PROPOSAL"
        room = read["room"]
        rows.append({"ticker": t, "reaction": read["reaction"], "close_pct": read["close_pct"],
                     "ret_5d": read["metrics"].get("ret_5d"), "ret_20d": read["metrics"].get("ret_20d"),
                     "current": room.get("current"), "basis": room.get("current_basis"), "daily_move_pct": room.get("daily_move_pct"),
                     "above": room.get("above"), "below": room.get("below"),
                     "beta_spy": beta, "corr_spy": _num((per.get("spy") or {}).get("corr")),
                     "beta_qqq": _num((per.get("qqq") or {}).get("beta")), "corr_qqq": _num((per.get("qqq") or {}).get("corr")),
                     "ic": _num((per.get("ic") or {}).get("ic")),
                     "if_spy_down_target_pct": round(beta * down_t, 2) if beta is not None and down_t is not None else None,
                     "if_spy_up_target_pct": round(beta * up_t, 2) if beta is not None and up_t is not None else None,
                     "implied_note": "beta estimate from 60 sessions of daily returns, not a forecast",
                     "band_lean": read["band_lean"], "macro_lean": read["macro_lean"], "relative": read["relative"],
                     "pipeline": {"direction": prop.get("canonical_direction"), "verdict": prop.get("options_verdict")} if prop else None,
                     "checks": checks, "alignment": alignment,
                     "action": _action(alignment, side, read, cfg, t) if side else (cfg.get("action_text") or {}).get("NO_PROPOSAL")})
    return rows


def candidate_rows(payload: Mapping, tp: Mapping, cfg: Mapping) -> list:
    """The pipeline's candidates (mostly stocks) read through their sector ETF and their measured link to it."""
    cands = ((payload.get("pipeline_candidates") or {}).get("rows") or [])[: int(cfg["max_candidates"])]
    board = set((payload.get("etfs") or {}).keys()) | set((payload.get("etf_levels") or {}).keys())
    texts = cfg.get("action_text") or {}
    out = []
    for c in cands:
        side = SIDE.get(c.get("canonical_direction"))
        etf = c.get("sector_etf")
        link = c.get("link") or {}
        corr = _num(link.get("corr"))
        row = {"rank": c.get("rank"), "ticker": c.get("ticker"), "direction": c.get("canonical_direction"),
               "verdict": c.get("options_verdict"), "horizon_bucket": c.get("horizon_bucket"), "sector_etf": etf,
               "entry_spot": c.get("entry_spot"), "target_spot": c.get("target_spot"), "invalidation_spot": c.get("invalidation_spot"),
               "link_corr": corr, "link_beta": _num(link.get("beta")),
               "weak_link": corr is None or corr < float(cfg["min_link_corr"])}
        if not side:
            row.update({"checks": [], "alignment": "NO_PROPOSAL", "action": texts.get("NO_PROPOSAL")})
        elif not etf or etf not in board:
            row.update({"checks": [], "alignment": "NO_SECTOR_READ", "action": texts.get("NO_SECTOR_READ")})
        else:
            read = _etf_read(etf, payload, cfg)
            checks = _checks(read, side, tp, cfg, own="sector")
            checks.append(_check("link", "NEUTRAL",
                                 f"{c.get('ticker')} vs {etf}: correlation {corr if corr is not None else 'n/a'} over "
                                 f"{link.get('n') or 0} sessions" + (" - weak link, the sector read carries little." if row["weak_link"] else ".")))
            if row["weak_link"]:
                market = next(c["state"] for c in checks if c["check"] == "market_tape")
                alignment = "STOCK_SPECIFIC"
                action = str(texts.get("STOCK_SPECIFIC", "")).format(
                    etf=etf, market={"WITH": "with it", "AGAINST": "against", "NEUTRAL": "mixed"}.get(market, "unknown"))
            else:
                alignment = _alignment(checks)
                action = _action(alignment, side, read, cfg, etf)
            row.update({"checks": checks, "alignment": alignment, "action": action})
        out.append(row)
    return out


# -- the plan ---------------------------------------------------------------------------------------------------

def build(payload: Mapping, cfg: Mapping) -> dict:
    review = payload.get("review") or {}
    tp = tape(review.get("instruments") or {}, cfg["focus"], majority=int(cfg["tape_majority"]))
    room = ((payload.get("opportunity") or {}).get("room") or {})
    instruments = {}
    for t in cfg["focus"]:
        etf = (payload.get("etfs") or {}).get(t)
        if not etf or t not in room:
            continue
        s = scenarios(t, etf, room[t], ((review.get("scored") or {}).get(t) or {}), cfg, as_of=payload.get("as_of_session"))
        if s:
            instruments[t] = s
    call = market_call(payload, tp, instruments, cfg)
    jig = jigsaw(payload, tp, instruments, cfg)
    call["conflict"] = _conflict(jig, cfg)
    return {"as_of_session": payload.get("as_of_session"),
            "next_session": (payload.get("decision_points") or {}).get("next_session"),
            "call": call, "instruments": instruments,
            "checklist": checklist(payload, instruments, tp, cfg),
            "opportunity": opportunity(payload, tp, cfg),
            "change_view": change_view(payload, instruments, tp, cfg),
            "jigsaw": jig,
            "etfs": etf_rows(payload, tp, instruments, cfg),
            "candidates": candidate_rows(payload, tp, cfg),
            "candidates_source": {k: (payload.get("pipeline_candidates") or {}).get(k) for k in ("status", "run_id", "file", "written_utc")},
            "unresolved": (review.get("unresolved") or {}),
            "authority": "RESEARCH_ONLY: display for the human; never a score, rank or gate."}
