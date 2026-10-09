"""Daily review, section 2: tomorrow's decision points (ACK 9 Oct 2026). Display only.

Scheduled (known in advance), placed by sessions ahead of the board's closing session:
  releases       the overnight capture's FRED calendar with ET times (market intelligence L-06)
  FOMC           decision days from config (Federal Reserve calendar; tentative until confirmed)
  earnings       top issuer holdings of the index / sector ETFs, MarketData earnings dates
                 (canonical_data.marketdata_earnings; an unknown date is stated, never "none")
  calendar       holidays and shortened sessions from the repo trading calendar
Unscheduled (kept apart): news-enrichment event guards and red-team question, the event
payload's counter-case and verdict (both LLM-made, shown as published). Central-bank speakers
come from the event payload only (ACK 9 Oct 2026).
Per focus ETF: what could force participants to reassess it in the next session.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
LEVEL_LABELS = {"high_252": "252d high", "low_252": "252d low", "sma50": "50d avg", "sma200": "200d avg",
                "call_wall": "GEX call wall", "put_wall": "GEX put wall", "gamma_flip": "GEX flip",
                "pipeline_target": "pipeline target", "pipeline_invalidation": "pipeline invalidation"}


def upcoming_sessions(as_of_session: str, count: int) -> tuple[list[date], list[date], dict]:
    """(sessions after as_of, weekday holidays among them, {session: close 'HH:MM' ET if shortened})."""
    from avshunter.shared.xnys_calendar import is_xnys_session, session_bounds
    day, sessions, holidays, shortened = date.fromisoformat(as_of_session), [], [], {}
    while len(sessions) < count:
        day += timedelta(days=1)
        if is_xnys_session(day):
            sessions.append(day)
            close = session_bounds(day)[1].astimezone(NY)
            if (close.hour, close.minute) != (16, 0):
                shortened[day] = close.strftime("%H:%M")
        elif day.weekday() < 5:
            holidays.append(day)
    return sessions, holidays, shortened


def constituent_tickers(holdings: Mapping, cfg: Mapping, sectors: Sequence[str]) -> dict:
    """{ticker: {etf: weight_pct}} for the top holdings of the index ETFs and the sector ETFs."""
    out: dict = {}
    plan = [(etf, int(cfg["constituent_top_n"])) for etf in cfg["constituent_etfs"]]
    plan += [(etf, int(cfg["sector_top_n"])) for etf in sectors]
    for etf, n in plan:
        for row in ((holdings.get(etf) or {}).get("top") or [])[:n]:
            weight = row.get("weight_pct")
            out.setdefault(row["ticker"], {})[etf] = round(weight, 2) if isinstance(weight, (int, float)) else weight
    return out


def _windows(ahead: int, horizons: Sequence[int]) -> list[int]:
    return [h for h in horizons if ahead <= h]


def build(*, as_of_session: str, overnight: Mapping | None, holdings: Mapping, earnings: Mapping | None,
          enrichment: Mapping | None, event_payload: Mapping | None, room: Mapping, focus: Sequence[str],
          sectors: Sequence[str], cfg: Mapping, horizons: Sequence[int] = (1, 5, 20)) -> dict:
    max_s = int(cfg["max_sessions"])
    sessions, holidays, shortened = upcoming_sessions(as_of_session, max_s)
    position = {d: i + 1 for i, d in enumerate(sessions)}

    close_day = date.fromisoformat(as_of_session)

    def ahead_of(day: date):
        """Sessions ahead of the board's close; a non-session day counts toward the next session.
        Anything dated on or before the close has already happened (None)."""
        if day <= close_day:
            return None
        for s in sessions:
            if s >= day:
                return position[s]
        return None

    calendar = []

    def add(kind, day, name, time_et=None, detail="", source="", **extra):
        ahead = ahead_of(day)
        if ahead is None:
            return
        calendar.append({"kind": kind, "date": day.isoformat(), "sessions_ahead": ahead,
                         "windows": _windows(ahead, horizons), "name": name, "time_et": time_et,
                         "detail": detail, "source": source, **extra})

    for d in holidays:
        add("HOLIDAY", d, "US market holiday (closed)", source="XNYS calendar")
    for d, close in shortened.items():
        add("SHORTENED_SESSION", d, f"Shortened session, closes {close} ET", close, source="XNYS calendar")

    coverage = {"speakers": "EVENT_PAYLOAD_ONLY", "consensus": "NOT_AVAILABLE_FREE_SOURCE"}
    if not overnight:
        coverage["releases"] = "MISSING"
    else:
        coverage["releases"] = "OBSERVED"
        stamp = overnight.get("as_of_utc") or overnight.get("as_of")
        today = (datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone(NY).date()
                 if stamp else None)
        for r in overnight.get("releases_today") or []:
            if today and today > date.fromisoformat(as_of_session):
                add("RELEASE", today, r.get("name"), r.get("time_et"), f"state {r.get('state')}", "FRED",
                    value=r.get("value"), prior=r.get("prior"))
        for r in overnight.get("releases_ahead") or []:
            add("RELEASE", date.fromisoformat(r["date"]), r.get("name"), r.get("time_et"), "", "FRED release calendar")

    fomc = cfg.get("fomc") or {}
    for d in fomc.get("decisions") or []:
        add("FOMC", date.fromisoformat(d["date"]), "FOMC rate decision", fomc.get("time_et"),
            "statement; press conference 30 min later" + ("; with economic projections (SEP)" if d.get("sep") else ""),
            "Federal Reserve calendar (config)")
    for d in fomc.get("minutes") or []:
        add("FOMC", date.fromisoformat(d), "FOMC minutes", fomc.get("time_et"), "", "Federal Reserve calendar (config)")

    owners = constituent_tickers(holdings, cfg, sectors)
    if earnings is None:
        coverage["earnings"] = "MISSING"
        coverage["earnings_unknown"] = sorted(owners)
    else:
        coverage["earnings"] = "OBSERVED"
        coverage["earnings_unknown"] = sorted(t for t in owners if (earnings.get(t) or {}).get("state") in (None, "UNKNOWN"))
        for t, weights in owners.items():
            e = earnings.get(t) or {}
            if e.get("state") != "SCHEDULED" or not e.get("date"):
                continue
            when = e.get("report_time") or "UNKNOWN"
            detail = ("reaction next session" if when == "AFTER_CLOSE" else
                      "reaction at the open" if when == "BEFORE_OPEN" else "time not given")
            if e.get("date_confirmation"):
                detail += "; provider date, unconfirmed"
            add("EARNINGS", date.fromisoformat(e["date"]), f"{t} earnings", when, detail, "MarketData earnings",
                weights=weights, ticker=t)

    calendar.sort(key=lambda e: (e["sessions_ahead"], e["date"], e["kind"], str(e["name"])))

    en = enrichment or {}
    ev = event_payload or {}
    unscheduled = {
        "items": [{"name": g.get("event_name"), "importance": g.get("importance"),
                   "confirms": (g.get("scenario_map") or {}).get("confirms"),
                   "fails": (g.get("scenario_map") or {}).get("fails"),
                   "source": "news enrichment (LLM)", "as_of": en.get("as_of_utc")}
                  for g in en.get("event_guard_deltas") or []],
        "red_team": (en.get("trading_risk_overlay") or {}).get("red_team_challenge"),
        "counter_conditions": list((ev.get("counter_case") or {}).get("reversal_or_neutralisation_conditions") or []),
        "verdict": (ev.get("final_verdict") or {}).get("verdict"),
        "verdict_scope": (ev.get("final_verdict") or {}).get("scope"),
        "status": "OBSERVED" if (enrichment or event_payload) else "MISSING",
    }

    near = float(cfg["near_level_daily_moves"])
    reassess = {}
    for t in focus:
        items = []
        for e in calendar:
            if e["sessions_ahead"] != 1:
                continue
            if e["kind"] == "EARNINGS":
                w = (e.get("weights") or {}).get(t)
                if w is None:
                    continue
                items.append({"kind": "EARNINGS", "time_et": e["time_et"],
                              "text": f"{e['name']} ({e['time_et']}), {w:.1f}% of {t}"})
            else:
                items.append({"kind": e["kind"], "time_et": e["time_et"],
                              "text": f"{e['name']}" + (f" at {e['time_et']} ET" if e["time_et"] and e["kind"] != "SHORTENED_SESSION" else "")})
        r = room.get(t) or {}
        for side in ("above", "below"):
            lvl = r.get(side)
            if lvl and lvl.get("distance_daily_moves") is not None and lvl["distance_daily_moves"] <= near:
                label = LEVEL_LABELS.get(lvl["name"], lvl["name"])
                items.append({"kind": "LEVEL", "time_et": None, "level_name": lvl["name"],
                              "text": f"Price near {label} {lvl['level']:.2f} ({lvl['distance_pct']:+.2f}%, "
                                      f"{lvl['distance_daily_moves']} daily moves {side})"})
        high = sum(1 for g in unscheduled["items"] if str(g.get("importance") or "").upper() == "HIGH")
        if high:
            items.append({"kind": "UNSCHEDULED", "time_et": None,
                          "text": f"{high} high-importance unresolved development{'s' if high > 1 else ''} (listed under Unscheduled)"})
        reassess[t] = items

    return {"as_of_session": as_of_session, "next_session": sessions[0].isoformat() if sessions else None,
            "next_session_close_et": shortened.get(sessions[0], "16:00") if sessions else None,
            "calendar": calendar, "unscheduled": unscheduled, "reassess": reassess, "coverage": coverage}
