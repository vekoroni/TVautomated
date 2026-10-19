"""Readiness report for a manual run of the macro inputs and board (ACK 19 Oct 2026: "we also need a function
where I can run manually").

Says, for the moment a run is started, what the board will and will not have: whether US pre-market is open,
which of today's releases are not out yet, and every input that is stale or missing with its reason. It reuses
the board's own input checks (sources.load_external) and the release list in the latest overnight capture.
Read-only: it never runs or writes anything. Run-MacroInputs.ps1 -Now prints it before asking to start.

    python -m macro_board.readiness --session PreOpen
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

from macro_board import market_prices as mkt

NEW_YORK = ZoneInfo("America/New_York")
BEST_PREOPEN_ET = "08:35"
OPEN_ET = "09:30"


def segment_at(now: datetime) -> str:
    return mkt.segment_of(now)


def _hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def report(*, now: datetime, session: str, segment: str, last_session: str | None,
           releases: Sequence[Mapping], inputs: Mapping) -> dict:
    """{"timing": EARLY | WAIT_RELEASES | GOOD | INTRADAY | EVENING | OFF_SESSION, "lines": [...]}."""
    et = now.astimezone(NEW_YORK)
    local = now.astimezone()
    today = et.date().isoformat()
    t = _hhmm(et)
    last = last_session or "last"
    lines = [f"Now {t} ET ({_hhmm(local)} local). US market: {segment.lower().replace('_', ' ')}."]
    due = [r for r in releases if str(r.get("date")) == today and r.get("time_et")]
    before_open = sorted((r for r in due if str(r["time_et"]) <= OPEN_ET), key=lambda r: str(r["time_et"]))
    in_session = sorted((r for r in due if str(r["time_et"]) > OPEN_ET), key=lambda r: str(r["time_et"]))
    pending = [r for r in before_open if str(r["time_et"]) > t]

    if segment == "REGULAR":
        timing = "INTRADAY"
        lines.append(f"The US market is open: today's bars are partial, so the run measures from the {last} close "
                     "and cannot be the scored record.")
    elif segment in ("AFTER_HOURS",) or (segment == "CLOSED" and t >= "16:00" and last == today):
        timing = "EVENING"
        lines.append("Today's session has closed: a PostClose run now is the scored evening record.")
    elif segment == "CLOSED" and t < "04:00" and et.weekday() < 5:
        timing = "EARLY"
        lines.append(f"US pre-market opens 04:00 ET: no prices after the {last} close yet, so the board will use "
                     "that close. Overnight futures and Asia/Europe are available.")
    elif segment == "CLOSED":
        timing = "OFF_SESSION"
        lines.append(f"No US session today: the run measures from the {last} close (off-session build).")
    else:                                                   # PREMARKET
        timing = "GOOD" if t >= BEST_PREOPEN_ET else "WAIT_RELEASES"
        lines.append("Pre-market is open (since 04:00 ET); volume builds after 07:00 ET.")
    if pending:
        lines.append("Today's releases not out yet: " + ", ".join(f"{r['name']} {r['time_et']}" for r in pending)
                     + " ET. A run now will not include them.")
    if in_session:
        lines.append("Due during the session: " + ", ".join(f"{r['name']} {r['time_et']}" for r in in_session) + " ET.")
    if timing in ("EARLY", "WAIT_RELEASES"):
        best = datetime.combine(et.date(), datetime.strptime(BEST_PREOPEN_ET, "%H:%M").time(), NEW_YORK)
        lines.append(f"Best time for the pre-open run: {BEST_PREOPEN_ET} ET ({_hhmm(best.astimezone())} local), after "
                     "the 08:30 releases and with pre-market prices.")
    weak = [(k, v) for k, v in inputs.items() if getattr(v, "status", "MISSING") != "FRESH"]
    if weak:
        lines.append("Inputs that are not fresh now (a run refreshes the ones it produces):")
        for _, v in weak:
            why = v.note or (f"as of {v.as_of}" if v.as_of else "")
            lines.append(f"  - {v.name.split(' (')[0]}: {v.status}" + (f" ({why})" if why else ""))
    else:
        lines.append("All board inputs are fresh.")
    return {"timing": timing, "lines": lines}


def _releases_from_capture(market_data: Path) -> list[dict]:
    files = sorted(market_data.glob("overnight_*.json"))
    if not files:
        return []
    try:
        doc = json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [r for key in ("releases_today", "releases_ahead") for r in (doc.get(key) or []) if isinstance(r, Mapping)]


def main(argv: Sequence[str] | None = None) -> int:
    from avshunter.shared.xnys_calendar import session_state
    from macro_board import sources as src
    from macro_board.build_board import DEFAULT_CONFIG

    parser = argparse.ArgumentParser(description="What a macro inputs run started now will and will not have.")
    parser.add_argument("--session", default="PreOpen")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    config = json.loads(Path(DEFAULT_CONFIG).read_text(encoding="utf-8"))
    last = str(session_state(now)[2])
    inputs = src.load_external(config, now)
    out = report(now=now, session=args.session, segment=segment_at(now), last_session=last,
                 releases=_releases_from_capture(src.ROOT / "dropbox" / "market_data"), inputs=inputs)
    print(f"READINESS ({args.session}, timing {out['timing']})")
    for line in out["lines"]:
        print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
