"""Earnings date confirmation tiers (output-trust item 9, D7-1; ACK approved 9 Oct 2026).

Root cause: MarketData was the only earnings source; its future dates can be projections and it has no confirmation
field (MSFT: MarketData 4 Nov, tastytrade 28 Oct after close with estimated=false). Tiers:
- VENDOR_ESTIMATE: one vendor only.
- CORROBORATED: MarketData and tastytrade agree on the date.
- ISSUER_CONFIRMED: supplied by the intelligence mining process (ACK 9 Oct: mining is separate; no pipeline fetch).
- SOURCES_DISAGREE: both shown and flagged; the earlier date carries the risk (it is the one that can fall inside a
  hold). A source that cannot be read is stated, never "no earnings". Disclosure only: never a gate or score.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, Mapping, Optional

TASTYTRADE_SOURCE = "TASTYTRADE_MARKET_METRICS"
_TT_TIME = {"AMC": "AFTER_CLOSE", "BMO": "BEFORE_OPEN", "BTO": "BEFORE_OPEN", "DMH": "DURING_MARKET"}
_NAMES = {"MARKETDATA_EARNINGS": "MarketData", TASTYTRADE_SOURCE: "tastytrade"}


def _day(value: Any) -> Optional[date]:
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def parse_tastytrade_earnings(item: Mapping[str, Any], *, as_of: date) -> Dict[str, Any]:
    """The next report from one tastytrade market-metrics item."""
    block = (item or {}).get("earnings") or {}
    report = _day(block.get("expected-report-date"))
    if report is None:
        return {"state": "UNKNOWN", "reason": "TASTYTRADE_NO_EARNINGS_DATE", "source": TASTYTRADE_SOURCE}
    if report < as_of:
        return {"state": "UNKNOWN", "reason": "TASTYTRADE_DATE_IN_PAST", "source": TASTYTRADE_SOURCE}
    estimated = block.get("estimated")
    return {"state": "SCHEDULED", "date": report.isoformat(),
            "report_time": _TT_TIME.get(str(block.get("time-of-day") or "").upper(), "UNKNOWN"),
            "estimated": bool(estimated) if isinstance(estimated, bool) else str(estimated).lower() == "true",
            "updated_at": block.get("updated-at"), "source": TASTYTRADE_SOURCE}


def _describe(src: Mapping[str, Any]) -> str:
    name = _NAMES.get(src.get("source"), str(src.get("source")))
    state = src.get("state")
    if state == "SCHEDULED":
        extra = "" if "estimated" not in src else (" (estimated)" if src["estimated"] else " (not estimated)")
        return f"{name} {src.get('date')}{extra}"
    if state == "NONE_IN_LOOKAHEAD":
        return f"{name} none in {src.get('lookahead_days') or 120} days"
    return f"{name} not checked ({src.get('reason') or 'UNKNOWN'})"


def reconcile_earnings(marketdata: Optional[Mapping[str, Any]], tastytrade: Optional[Mapping[str, Any]], *,
                       issuer: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """One earnings view for earnings_disclosure, with the tier, the conflict and every source as checked."""
    md = dict(marketdata or {"state": "UNKNOWN", "reason": "NOT_FETCHED", "source": "MARKETDATA_EARNINGS"})
    tt = dict(tastytrade or {"state": "UNKNOWN", "reason": "NOT_FETCHED", "source": TASTYTRADE_SOURCE})
    sources = {s.get("source") or name: s for name, s in (("MARKETDATA_EARNINGS", md), (TASTYTRADE_SOURCE, tt))}
    if issuer and _day(issuer.get("date")):
        sources["ISSUER"] = dict(issuer)
    scheduled = [s for s in (md, tt) if s.get("state") == "SCHEDULED" and _day(s.get("date"))]
    out: Dict[str, Any] = {"sources_json": json.dumps(sources, sort_keys=True, default=str), "disagreement": None,
                           "fiscal_quarter": md.get("fiscal_quarter") or ""}
    notes = [_describe(s) for s in (md, tt)]
    if issuer and _day(issuer.get("date")):
        conflicts = [s for s in scheduled if s["date"] != str(issuer["date"])[:10]]
        out.update(state="SCHEDULED", date=str(issuer["date"])[:10],
                   report_time=str(issuer.get("report_time") or "UNKNOWN").upper(),
                   date_confirmation="ISSUER_CONFIRMED", source=str(issuer.get("source") or "ISSUER"),
                   disagreement=("vendors differ from the issuer: " + "; ".join(_describe(s) for s in conflicts))
                   if conflicts else None)
    elif len(scheduled) == 2 and scheduled[0]["date"] == scheduled[1]["date"]:
        times = {s.get("report_time") for s in scheduled if s.get("report_time") not in (None, "UNKNOWN")}
        out.update(state="SCHEDULED", date=scheduled[0]["date"],
                   report_time=(tt.get("report_time") if tt.get("report_time") not in (None, "UNKNOWN")
                                else md.get("report_time") or "UNKNOWN"),
                   date_confirmation="CORROBORATED", source="MARKETDATA_EARNINGS+TASTYTRADE_MARKET_METRICS",
                   disagreement=("timing differs: " + " vs ".join(f"{_NAMES[s['source']]} {s['report_time']}"
                                                                for s in scheduled)) if len(times) > 1 else None)
    elif scheduled:
        first = min(scheduled, key=lambda s: s["date"])
        other = [s for s in (md, tt) if s is not first]
        disagree = bool(other) and other[0].get("state") in ("SCHEDULED", "NONE_IN_LOOKAHEAD")
        out.update(state="SCHEDULED", date=first["date"], report_time=first.get("report_time") or "UNKNOWN",
                   source=first.get("source"),
                   date_confirmation="SOURCES_DISAGREE" if disagree else "VENDOR_ESTIMATE",
                   disagreement=("; ".join(notes)) if disagree else None)
    elif md.get("state") == "NONE_IN_LOOKAHEAD" and tt.get("state") in ("NONE_IN_LOOKAHEAD", "UNKNOWN"):
        out.update(state="NONE_IN_LOOKAHEAD", lookahead_days=md.get("lookahead_days") or 120,
                   source=md.get("source"), date_confirmation="VENDOR_ESTIMATE")
    else:
        out.update(state="UNKNOWN", reason=f"{md.get('reason') or md.get('state')};{tt.get('reason') or tt.get('state')}",
                   source="MARKETDATA_EARNINGS+TASTYTRADE_MARKET_METRICS", date_confirmation="UNKNOWN")
    out["confirmation_note"] = "; ".join(notes)
    return out
