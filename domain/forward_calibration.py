"""Forward calibration state per setup (output-trust item 10, part 10.2; C-1).

Design: Enhancements/phase7/ITEM10_CALIBRATION_AND_STATIONS_DESIGN_20261010.md. The replay calibration (part 10.1)
says how the stated rates held up out of sample; this measures them on the predictions the pipeline actually
surfaced, read from the C12 outcome store. Event: target before invalidation within the setup's hold - the hold the
stated rate was measured on (bars, converted to XNYS sessions). Per outcome:
- TARGET_FIRST resolved within the hold: hit; resolved after it, STOP_FIRST or AMBIGUOUS: miss;
- TIMEOUT at the scorer window: miss when the hold fits the window, else BEYOND_SCORER_WINDOW (never a miss);
- OPEN_CENSORED: miss once the hold has been observed in full, else pending; DATA_GAP / NOT_SCORABLE: not scorable.
Only matured outcomes count: the hold (capped at the scorer window) has fully elapsed since the evidence session.
Counting earlier terminal outcomes would favour fast resolutions - hits and stops land early, timeouts never do.
State per setup: UNCALIBRATED_FORWARD until the governed minimum of resolved outcomes over a minimum of distinct
sessions; then CALIBRATED when the mean stated rate lies inside the observed Wilson interval, else MISCALIBRATED.
Report and display only.
"""
from __future__ import annotations

import contextlib
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from domain.setup_calibration import calibration_summary, wilson

_MISS_STATES = {"STOP_FIRST", "AMBIGUOUS"}
_NOT_SCORABLE = {"DATA_GAP", "NOT_SCORABLE"}


def forward_policy() -> Dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "config" / "governed_constants_v1.json"
    return dict(json.loads(path.read_text(encoding="utf-8-sig"))["forward_calibration"])


def _num(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def hold_sessions(setup: Any, hold_bars: Any, policy: Mapping[str, Any]) -> Optional[int]:
    """The setup's hold in XNYS sessions (its timeframe is the setup label's first part); None when not convertible."""
    bars = _num(hold_bars)
    per_bar = (policy.get("sessions_per_bar") or {}).get(str(setup or "").split("|")[0])
    if not bars or per_bar is None:
        return None
    return int(math.ceil(bars * float(per_bar)))


def forward_calibration(rows: Iterable[Mapping[str, Any]], *, policy: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    pol = dict(forward_policy() if policy is None else policy)
    window = int(pol.get("scorer_window_sessions") or 0)
    acc: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"resolved": 0, "hits": 0, "pending": 0, "beyond": 0,
                                                          "not_scorable": 0, "stated": [], "sessions": set(),
                                                          "tickers": set()})
    for r in rows:
        setup, hold = r.get("setup"), _num(r.get("planned_hold_sessions"))
        if not setup or not hold:
            continue
        a = acc[f'{setup}|{r["side"]}' if r.get("side") else str(setup)]
        state = str(r.get("state") or "").upper()
        to_resolve, observed = _num(r.get("sessions_to_resolution")), _num(r.get("sessions_observed")) or 0
        if state in _NOT_SCORABLE:
            a["not_scorable"] += 1
            continue
        elapsed = _num(r.get("sessions_elapsed"))
        if elapsed is None or elapsed < min(hold, window or hold):
            a["pending"] += 1                                       # cohort not matured: never counted early
            continue
        if state == "TARGET_FIRST" and to_resolve is not None:
            hit = to_resolve <= hold
        elif state in _MISS_STATES:
            hit = False
        elif state == "TIMEOUT" and hold > window:
            a["beyond"] += 1
            continue
        elif state == "TIMEOUT" or observed >= hold:
            hit = False
        else:
            a["pending"] += 1
            continue
        a["resolved"] += 1
        a["hits"] += int(hit)
        stated = _num(r.get("stated_rate"))
        if stated is not None:
            a["stated"].append(stated)
        a["sessions"].add(r.get("evidence_session"))
        a["tickers"].add(r.get("ticker"))
    setups: Dict[str, Any] = {}
    groups = []
    for setup, a in acc.items():
        stated = sum(a["stated"]) / len(a["stated"]) if a["stated"] else None
        observed = a["hits"] / a["resolved"] if a["resolved"] else None
        ci = wilson(a["hits"], a["resolved"]) if a["resolved"] else None
        enough = a["resolved"] >= int(pol["min_resolved"]) and len(a["sessions"]) >= int(pol["min_sessions"])
        if not enough or stated is None:
            state = "UNCALIBRATED_FORWARD"
        else:
            state = "CALIBRATED" if ci[0] <= stated <= ci[1] else "MISCALIBRATED"
            groups.append({"predicted": stated, "n": a["resolved"], "hits": a["hits"]})
        setups[setup] = {"state": state, "resolved": a["resolved"], "hits": a["hits"], "pending": a["pending"],
                         "beyond_scorer_window": a["beyond"], "not_scorable": a["not_scorable"],
                         "observed_rate": round(observed, 4) if observed is not None else None, "ci": ci,
                         "stated_rate": round(stated, 4) if stated is not None else None,
                         "sessions": len(a["sessions"]), "tickers": len(a["tickers"])}
    return {"policy": pol, "setups": setups,
            "calibration": calibration_summary(groups) if groups else None,
            "state": "CALIBRATED_SETUPS_PRESENT" if groups else "UNCALIBRATED_FORWARD"}


def load_forward_rows(db_path: Path | str, *, policy: Optional[Mapping[str, Any]] = None) -> List[Dict[str, Any]]:
    """Read-only: each prediction's setup labels as first issued, with its latest underlying outcome."""
    pol = dict(forward_policy() if policy is None else policy)
    path = Path(db_path)
    if not path.is_file():
        return []
    sql = """
        SELECT p.prediction_id, p.ticker, p.evidence_session, s.labels_json, o.state, o.sessions_observed,
               o.resolution_session, o.latest
          FROM prediction_records p
          JOIN (SELECT prediction_id, labels_json, MIN(ingested_at_utc) AS first_seen FROM prediction_sightings
                 WHERE labels_json LIKE '%trade_lane_setup%' GROUP BY prediction_id) s USING (prediction_id)
          JOIN (SELECT prediction_id, state, sessions_observed, resolution_session, MAX(as_of_session) AS latest
                  FROM underlying_outcomes GROUP BY prediction_id) o USING (prediction_id)"""
    rows: List[Dict[str, Any]] = []
    with contextlib.closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as conn:
        for pid, ticker, session, labels_json, state, observed, resolution, as_of in conn.execute(sql):
            labels = json.loads(labels_json or "{}")
            setup = labels.get("trade_lane_setup")
            rows.append({"prediction_id": pid, "ticker": ticker, "evidence_session": session, "setup": setup,
                         "side": labels.get("trade_lane_side"), "stated_rate": labels.get("setup_rate_within_hold"),
                         "planned_hold_sessions": hold_sessions(setup, labels.get("setup_hold_bars"), pol),
                         "state": state, "sessions_observed": observed, "sessions_to_resolution": resolution,
                         "sessions_elapsed": sessions_elapsed(session, as_of)})
    return rows


def sessions_elapsed(evidence_session: Any, as_of_session: Any) -> Optional[int]:
    """XNYS sessions after the evidence session up to the store's latest as-of session."""
    from datetime import date
    from avshunter.shared.xnys_calendar import xnys_sessions_between
    try:
        return xnys_sessions_between(date.fromisoformat(str(evidence_session)[:10]),
                                     date.fromisoformat(str(as_of_session)[:10]))
    except ValueError:
        return None


def forward_label(setup_report: Optional[Mapping[str, Any]], policy: Mapping[str, Any]) -> str:
    """Card text: 'forward: uncalibrated (n 0 of 100)' or 'forward: 61% (n 120, 40 sessions) - calibrated'."""
    need = int(policy["min_resolved"])
    if not setup_report or setup_report.get("state") == "UNCALIBRATED_FORWARD":
        n = int((setup_report or {}).get("resolved") or 0)
        return f"forward: uncalibrated (n {n} of {need})"
    return (f'forward: {setup_report["observed_rate"]:.0%} (n {setup_report["resolved"]}, '
            f'{setup_report["sessions"]} sessions) - {setup_report["state"].lower()}')
