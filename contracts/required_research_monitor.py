"""Dated output coverage and event disclosure. Never manufactures a trade row."""
from datetime import datetime, timezone
import json
from pathlib import Path

POLICY = Path(__file__).resolve().parents[1] / "config/required_research_monitor_v1.json"
MONITOR_FIELDS = (
    "required_monitoring", "monitoring_reason", "monitoring_execution_authority",
    "thesis_reassessment_status", "thesis_reassessment_reason",
    "thesis_reassessment_event_time_utc", "thesis_reassessment_source_url",
)


def policy():
    return json.loads(POLICY.read_text(encoding="utf-8"))


def session_date(as_of=None):
    return str(as_of or datetime.now(timezone.utc).date())[:10]


def required_tickers(as_of=None):
    day = session_date(as_of)
    return {m["ticker"] for m in policy()["monitors"]
            if m["start_session"] <= day <= m["end_session"]}


def disclosure(row, as_of=None):
    ticker = str(row.get("ticker") or "").strip().upper()
    day = session_date(as_of)
    p = policy()
    monitor = next((m for m in p["monitors"] if m["ticker"] == ticker
                    and m["start_session"] <= day <= m["end_session"]), None)
    event = next((e for e in p["reassessments"] if e["ticker"] == ticker
                  and e["event_time_utc"][:10] <= day
                  and e["status"] == "REASSESSMENT_REQUIRED"), None)
    return {
        "required_monitoring": bool(monitor),
        "monitoring_reason": monitor["reason"] if monitor else "",
        "monitoring_execution_authority": "NONE",
        "thesis_reassessment_status": event["status"] if event else "",
        "thesis_reassessment_reason": event["reason"] if event else "",
        "thesis_reassessment_event_time_utc": event["event_time_utc"] if event else "",
        "thesis_reassessment_source_url": event["source_url"] if event else "",
    }


def coverage_records(rows, *, as_of=None, stage):
    """Include missing/rejected tickers without synthetic scores."""
    records = list(rows)
    monitored = required_tickers(as_of)
    monitored.update(e["ticker"] for e in policy()["reassessments"]
                     if e["event_time_utc"][:10] <= session_date(as_of)
                     and e["status"] == "REASSESSMENT_REQUIRED")
    output = []
    for ticker in sorted(monitored):
        matches = [r for r in records if str(r.get("ticker", "")).upper() == ticker]
        row = matches[0] if matches else {"ticker": ticker}
        output.append({
            "ticker": ticker, "stage": stage,
            "coverage_state": "PRESENT" if matches else "ABSENT_REQUIRES_ATTENTION",
            "source_row_count": len(matches),
            "analysis_status": str(row.get("eod_candidate_status") or row.get("lab_verdict") or row.get("tier_reason") or "NOT_AVAILABLE"),
            **disclosure(row, as_of),
        })
    return {"schema": "required_research_monitoring_v1", "as_of": session_date(as_of), "rows": output}


def write_coverage(folder, rows, *, as_of=None, stage):
    folder = Path(folder)
    payload = coverage_records(rows, as_of=as_of, stage=stage)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "required_research_monitoring.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
