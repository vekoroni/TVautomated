"""The measured sheet for ChatGPT (ACK 10 Oct 2026).

Every board build writes one page of facts AVSHUNTER measured itself, with instructions, for ACK to
paste into ChatGPT before asking for the US Money Index, the event payload and the news enrichment.
ChatGPT then adds only the news layer and works from these numbers instead of finding its own: one
owner per fact. The sheet is assembled from the board's payload (no LLM), carries measured facts only -
never an LLM's published numbers - and writes MISSING where a fact is missing. Wording and
instructions live in config["measured_sheet"].
"""

from __future__ import annotations

import math
from typing import Mapping

KEY_TXT = {"ACCEPTED_UP": "accepted up", "ACCEPTED_DOWN": "accepted down", "REJECTED_GAP_UP": "rejected a gap up",
           "REJECTED_GAP_DOWN": "rejected a gap down", "ABSORBED": "absorbed", "UNKNOWN": "unknown"}


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _pct(x, digits=2):
    x = _num(x)
    return "MISSING" if x is None else f"{x:+.{digits}f}%"


def _value(v, unit):
    v = _num(v)
    if v is None:
        return "MISSING"
    if unit == "bp":
        return f"{v:+.0f} bp"
    if unit == "%":
        return f"{v:+.2f}%"
    if unit == "share":
        return f"{v * 100:.1f}%"
    return f"{v:.2f}"


def _ordinal(pct) -> str:
    pct = _num(pct)
    if pct is None:
        return "MISSING"
    n = round(pct * 100)
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _reaction_key(r: Mapping) -> str:
    label, direction = r.get("label") or "UNKNOWN", r.get("direction") or "NONE"
    if label == "ACCEPTED":
        return f"ACCEPTED_{direction}"
    if label == "REJECTED":
        return f"REJECTED_GAP_{direction}"
    return label


def _money_index(payload: Mapping, lines: list) -> None:
    mi = payload.get("money_index") or {}
    r = mi.get("reading") or {}
    lines += ["## 1. US Money Index - measured components", "",
              "| Component | Published key | Today | Past-year percentile | Points / weight |", "|---|---|---|---|---|"]
    for c in r.get("components") or []:
        pts = _num(c.get("points"))
        lines.append(f"| {c.get('label')} | {c.get('published_key')} | {_value(c.get('value'), c.get('unit'))} | "
                     f"{_ordinal(c.get('percentile'))} | "
                     f"{'MISSING' if pts is None else f'{pts:.1f}'} / {_num(c.get('weight')) or 0:.0f} |")
    score = _num(r.get("score"))
    if score is None:
        lines.append(f"\nMeasured total: MISSING (missing: {', '.join(r.get('missing') or []) or 'all'})")
    else:
        lines.append(f"\nMeasured total: {score:.1f} / 100 over {r.get('measured_weight')} weight ({r.get('band')})")
    spy = ((((mi.get("per_etf") or {}).get("SPY") or {}).get("band_evidence") or {}).get("5") or {})
    if spy:
        a, b = spy.get("analog") or {}, spy.get("base") or {}
        lines.append(f"After past {r.get('band')} sessions, SPY's next 5 sessions averaged {_pct(a.get('mean_pct'))} vs "
                     f"{_pct(b.get('mean_pct'))} on all days ({a.get('n_eff')} independent windows; "
                     f"{ {'UP': 'history leans up', 'DOWN': 'history leans down'}.get(spy.get('lean'), 'no clear lean') }).")
    lines.append("Scoring: each component against its own past 252 sessions; 0 points at or below the median, full weight at "
                 "the 95th percentile.")
    lines.append("")


def _market(payload: Mapping, cfg: Mapping, lines: list) -> None:
    review = payload.get("review") or {}
    lines += ["## 2. How markets reacted at the close", "", "| Instrument | Reaction | Gap | Close |", "|---|---|---|---|"]
    for t, r in (review.get("instruments") or {}).items():
        lines.append(f"| {t} | {KEY_TXT.get(_reaction_key(r), _reaction_key(r).lower())} | {_pct(r.get('gap_pct'))} | {_pct(r.get('close_pct'))} |")
    lead = (payload.get("opportunity") or {}).get("leadership") or {}
    br = lead.get("breadth") or {}
    gap = _num(br.get("rsp_minus_spy_20d_pp"))
    lines.append("")
    lines.append(f"Breadth: {br.get('state') or 'MISSING'} (equal-weight RSP minus SPY over 20 sessions: "
                 f"{'MISSING' if gap is None else f'{gap:+.1f} pts'}).")
    lw = (lead.get("windows") or {})
    if lw:
        lines.append("Leadership QQQ vs SPY: " + "; ".join(
            f"{h}d {w.get('leader')} ({_num(w.get('qqq_minus_spy_pp')) or 0:+.1f} pts)" for h, w in lw.items()) + ".")
    vix = ((payload.get("intel") or {}).get("vix_engine") or [None])[-1]
    if vix:
        lines.append(f"Volatility: VIX {_num(vix.get('VIX_Direct')) or 0:.2f}, VIX3M {_num(vix.get('VIX3M_Proxy')) or 0:.2f}, "
                     f"term structure {vix.get('VIX_Structure')} (as of {vix.get('Date')}).")
    cond = payload.get("conditions") or {}
    labels = {m["key"]: m.get("label", m["key"]) for m in cond.get("meta") or []}
    current, values = cond.get("current") or {}, cond.get("current_values") or {}
    if current:
        lines.append("Conditions (20-session readings): " + "; ".join(f"{labels.get(k, k)} {v}" for k, v in current.items()) + ".")
    ten, curve = _num(values.get("yields")), _num(values.get("curve_level"))
    if ten is not None or curve is not None:
        lines.append("Rates: " + "; ".join(x for x in (f"10Y {ten:.2f}%" if ten is not None else None,
                                                       f"2s10s {curve:+.2f} pts" if curve is not None else None) if x)
                     + " (FRED, publication-lagged).")
    lines.append("")
    lines += ["## 3. Levels for the next session", ""]
    for t, s in ((payload.get("session_plan") or {}).get("instruments") or {}).items():
        if t not in cfg["focus"]:
            continue
        up, dn = (s.get("up") or {}).get("trigger"), (s.get("down") or {}).get("trigger")
        basis = "close" if (s.get("basis") or "CLOSE") == "CLOSE" else s.get("basis")
        lines.append(f"- {t} {(_num(s.get('reference')) or 0):.2f} ({basis}): "
                     f"above {up['label'] + ' ' + format(up['level'], '.2f') if up else 'none mapped'}, "
                     f"below {dn['label'] + ' ' + format(dn['level'], '.2f') if dn else 'none mapped'}; "
                     f"normal day ±{(_num(s.get('daily_move_pct')) or 0):.2f}%"
                     + (f", options price ±{_num(s.get('implied_move_pct')):.2f}% next session" if _num(s.get('implied_move_pct')) else "") + ".")
    lines.append("")


def _calendar(payload: Mapping, cfg: Mapping, lines: list) -> None:
    session = payload.get("as_of_session")
    ov = payload.get("overnight") or {}
    lines += ["## 4. Overnight and scheduled releases", ""]
    sched = payload.get("scheduled_events") or {}
    local_released = sched.get("released") or []
    for e in local_released:
        if e.get("actual") is None:
            lines.append(f"- Released {e.get('time_et')} ET: {e.get('name')} - not read from FRED.")
            continue
        s = e.get("surprise") or {}
        rev = _num(e.get("revision_of_previous"))
        spy = ((e.get("event_day") or {}).get("SPY") or {})
        z = _num(s.get("z"))
        lines.append(f"- Released {e.get('time_et')} ET: {e.get('name')} {_num(e.get('actual')):g} (observation {e.get('observation_date')}; "
                     f"change {(_num(e.get('change')) or 0):+g} {e.get('unit') or ''}".rstrip()
                     + (f"; previous {_num(e.get('previous')):g}" if _num(e.get("previous")) is not None else "")
                     + (f", revised {rev:+g} since first published" if rev else "") + "); "
                     + f"{str(s.get('label') or 'MISSING').replace('_', ' ').lower()}"
                     + (f" (z {z:+.1f})" if z is not None else "") + ", not a consensus surprise"
                     + (f"; SPY moves {round(spy['ratio'], 2):g}x a normal day on its release days ({spy.get('n')} days)" if spy.get("ratio") is not None else "")
                     + ".")
    if ov.get("status") in (None, "MISSING", "UNREADABLE") or ov.get("us_reference_session") != session:
        lines.append(f"Overnight: not captured after the {session} close (run the PreOpen inputs for futures, VIX, FX, Asia/Europe).")
    else:
        for group, rows in (ov.get("groups") or {}).items():
            items = [f"{r.get('name')} {_pct(r.get('change_pct'))}" for r in rows if r.get("state") in ("OK", "CLOSED", None)
                     and _num(r.get("change_pct")) is not None]
            if items:
                lines.append(f"- {group.replace('_', ' ')}: " + ", ".join(items))
        for r in ov.get("releases_today") or []:
            if r.get("state") == "RELEASED" and r.get("name") not in {e.get("name") for e in local_released}:
                lines.append(f"- Released {r.get('time_et')} ET: {r.get('name')} {(_num(r.get('value')) or 0):.6g} "
                             f"(prior {(_num(r.get('prior')) or 0):.6g}).")
    limit = int(cfg["release_sessions_ahead"])
    if sched.get("upcoming") is not None and sched.get("status") not in ("UNAVAILABLE", "NO_KEY", "NOT_APPLICABLE_AS_OF_BUILD"):
        def tag(c):
            spy = ((c.get("event_day") or {}).get("SPY") or {})
            return f" (SPY {round(spy['ratio'], 2):g}x a normal day)" if spy.get("ratio") is not None else ""
        ahead = [f"{c.get('date')} {c.get('time_et') or ''} {c.get('name')}{tag(c)}".replace("  ", " ")
                 for c in sched.get("upcoming") or [] if (c.get("sessions_ahead") or 99) <= limit]
    else:
        ahead = [f"{c.get('date')} {c.get('time_et') or ''} {c.get('name')}".replace("  ", " ")
                 for c in (payload.get("decision_points") or {}).get("calendar") or []
                 if (c.get("sessions_ahead") or 99) <= limit]
    lines.append(f"Scheduled (next {limit} sessions): " + ("; ".join(ahead) or "none") + ".")
    lines.append("")


def render(payload: Mapping, cfg: Mapping) -> str:
    build = payload.get("build") or {}
    mi_settings = ((payload.get("money_index") or {}).get("settings") or {})
    llm = mi_settings.get("published_only") or []
    llm_components = ", ".join(c["key"] for c in llm) or "none"
    llm_weight = int(sum(_num(c.get("weight")) or 0 for c in llm))
    lines = [f"# {cfg['title']}", "",
             f"Close described: {payload.get('as_of_session')} · build {build.get('kind') or 'UNKNOWN'} "
             f"({build.get('run_session') or build.get('source') or 'manual'}) · measured {payload.get('built_at_utc')}", "",
             "## Instructions", ""]
    for i, text in enumerate(cfg["instructions"], 1):
        lines.append(f"{i}. " + str(text).format(llm_components=llm_components, llm_weight=llm_weight,
                                                 measured_weight=(payload.get("money_index") or {}).get("reading", {}).get("measured_weight"),
                                                 session=payload.get("as_of_session")))
    lines += ["", "What we need from you:"] + [f"- {x}" for x in cfg["needed_from_you"]] + [""]
    _money_index(payload, lines)
    _market(payload, cfg, lines)
    _calendar(payload, cfg, lines)
    lines.append("End of measured sheet. Everything above was measured by AVSHUNTER from market data, FRED and Cboe; no LLM wrote it.")
    return "\n".join(lines) + "\n"
