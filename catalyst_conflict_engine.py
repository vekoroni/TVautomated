"""
AVSHUNTER Catalyst Conflict Engine — Phantom 3 promoted to production.

Detects structural catalyst conflicts that could invalidate a directional thesis
within the DTE window. Consumed by both the Pipeline Interpreter and EIL Phase 8.

Standard library only: csv, json, pathlib, datetime.
No imports from any AVSHUNTER module.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data contract
# ---------------------------------------------------------------------------

@dataclass
class CatalystConflict:
    """
    Represents a single catalyst event that conflicts with a directional thesis.

    conflict_type: INDEX_INCLUSION | EARNINGS | MACRO_BINARY | DIVIDEND |
                   LOCK_UP_EXPIRY | FDA_DECISION | SPLIT | OTHER
    severity:      CRITICAL | HIGH | MODERATE | LOW
    direction_impact: BULLISH | BEARISH | BINARY | NEUTRAL
    conflict_with:    direction the thesis expects (CALL/PUT)
    """
    ticker:            str
    conflict_type:     str
    event_date:        Optional[str]   # ISO date or empty
    days_until_event:  Optional[int]
    within_dte_window: bool
    severity:          str
    direction_impact:  str
    conflict_with:     str
    description:       str
    source:            str             # catalyst CSV filename or "MANUAL"
    is_blocking:       bool = False    # True for CRITICAL within DTE window


@dataclass
class CatalystConflictResult:
    """Aggregated result for a single ticker."""
    ticker:          str
    thesis_direction: str
    dte_window:      int
    conflicts:       list[CatalystConflict] = field(default_factory=list)
    summary:         str = ""
    highest_severity: str = "NONE"
    has_blocking_conflict: bool = False
    catalyst_override: Optional[str] = None  # GO→GO_LIMIT only, never BLOCKED


# ---------------------------------------------------------------------------
# Severity ranking helpers
# ---------------------------------------------------------------------------

_SEVERITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "LOW": 1, "NONE": 0}


def _highest_severity(conflicts: list[CatalystConflict]) -> str:
    if not conflicts:
        return "NONE"
    return max(conflicts, key=lambda c: _SEVERITY_RANK.get(c.severity, 0)).severity


# ---------------------------------------------------------------------------
# Catalyst CSV loader
# ---------------------------------------------------------------------------

def _load_catalyst_csv(path: Path) -> list[dict]:
    """Load a catalyst calendar CSV. Returns empty list on failure."""
    if not path.exists():
        return []
    rows = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                rows.append(dict(r))
    except (OSError, csv.Error):
        pass
    return rows


def _days_until(event_date_str: str, today: datetime) -> Optional[int]:
    """Return calendar days until event_date_str (YYYY-MM-DD or similar). None if unparseable."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y%m%d"):
        try:
            ev = datetime.strptime(str(event_date_str).strip(), fmt)
            return (ev.replace(tzinfo=None) - today.replace(tzinfo=None)).days
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Core detection logic
# ---------------------------------------------------------------------------

def _classify_event(row: dict) -> tuple[str, str, str]:
    """
    Infer conflict_type, direction_impact, severity from a catalyst row.
    Returns (conflict_type, direction_impact, severity).
    """
    raw = json.dumps(row).upper()

    # Conflict type
    if any(k in raw for k in ("INDEX_INCLUSION", "RUSSELL", "SP500", "S&P 500", "FTSE")):
        conflict_type    = "INDEX_INCLUSION"
        direction_impact = "BULLISH"
        severity         = "HIGH"
    elif any(k in raw for k in ("EARNINGS", "EPS", "QUARTERLY_RESULT")):
        conflict_type    = "EARNINGS"
        direction_impact = "BINARY"
        severity         = "HIGH"
    elif any(k in raw for k in ("FOMC", "FED_DECISION", "CPI", "NFP", "JOBS_REPORT", "GDP")):
        conflict_type    = "MACRO_BINARY"
        direction_impact = "BINARY"
        severity         = "MODERATE"
    elif any(k in raw for k in ("DIVIDEND", "EX_DIV", "RECORD_DATE")):
        conflict_type    = "DIVIDEND"
        direction_impact = "BEARISH"   # ex-div date pulls price down
        severity         = "LOW"
    elif any(k in raw for k in ("LOCK_UP", "LOCKUP", "LOCK-UP")):
        conflict_type    = "LOCK_UP_EXPIRY"
        direction_impact = "BEARISH"
        severity         = "MODERATE"
    elif any(k in raw for k in ("FDA", "PDUFA", "DRUG_APPROVAL")):
        conflict_type    = "FDA_DECISION"
        direction_impact = "BINARY"
        severity         = "CRITICAL"
    elif any(k in raw for k in ("SPLIT", "REVERSE_SPLIT")):
        conflict_type    = "SPLIT"
        direction_impact = "NEUTRAL"
        severity         = "LOW"
    else:
        conflict_type    = "OTHER"
        direction_impact = "NEUTRAL"
        severity         = "LOW"

    # Severity override from explicit severity field if present
    explicit_sev = str(row.get("severity", row.get("event_severity", ""))).upper()
    if explicit_sev in _SEVERITY_RANK:
        severity = explicit_sev

    # Direction impact override
    explicit_dir = str(row.get("direction_impact", row.get("impact", ""))).upper()
    if explicit_dir in ("BULLISH", "BEARISH", "BINARY", "NEUTRAL"):
        direction_impact = explicit_dir

    return conflict_type, direction_impact, severity


def _is_conflicting(direction_impact: str, thesis_direction: str) -> bool:
    """
    True if the catalyst creates a conflict with the thesis direction.
    BINARY events always conflict. NEUTRAL never conflict.
    BULLISH conflicts with PUT. BEARISH conflicts with CALL.
    """
    td = str(thesis_direction).upper()
    if direction_impact == "BINARY":
        return True
    if direction_impact == "NEUTRAL":
        return False
    if direction_impact == "BULLISH" and "PUT" in td:
        return True
    if direction_impact == "BEARISH" and "CALL" in td:
        return True
    return False


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def detect_catalyst_conflicts(
    ticker: str,
    thesis_direction: str,
    dte_window: int,
    catalyst_rows: list[dict],
    catalyst_source: str = "catalyst_csv",
    today: Optional[datetime] = None,
) -> CatalystConflictResult:
    """
    Detect all catalyst conflicts for a ticker within the DTE window.

    ticker:           uppercase ticker symbol
    thesis_direction: "CALL" or "PUT"
    dte_window:       number of calendar days to scan
    catalyst_rows:    list of dicts loaded from catalyst_calendar CSV
    catalyst_source:  filename or label for attribution
    today:            override for testing; defaults to UTC now

    Returns a CatalystConflictResult.
    """
    ticker = str(ticker).strip().upper()
    today  = today or datetime.now(timezone.utc)

    conflicts: list[CatalystConflict] = []

    for row in catalyst_rows:
        # Match ticker — check multiple field names
        row_ticker = (
            str(row.get("ticker", row.get("symbol", row.get("Ticker", "")))).strip().upper()
        )
        if row_ticker != ticker:
            continue

        event_date_str = str(row.get("event_date", row.get("date", ""))).strip()
        days_until     = _days_until(event_date_str, today)
        within_window  = (days_until is not None) and (0 <= days_until <= dte_window)

        conflict_type, direction_impact, severity = _classify_event(row)

        if not _is_conflicting(direction_impact, thesis_direction):
            continue

        # Only surface events within the DTE window (or undated with a flag)
        if days_until is not None and not within_window:
            continue

        is_blocking = (severity == "CRITICAL") and within_window

        description = str(row.get(
            "event_description",
            row.get("description", row.get("catalyst_overlay", conflict_type))
        )).strip()

        conflicts.append(CatalystConflict(
            ticker=ticker,
            conflict_type=conflict_type,
            event_date=event_date_str or None,
            days_until_event=days_until,
            within_dte_window=within_window,
            severity=severity,
            direction_impact=direction_impact,
            conflict_with=thesis_direction,
            description=description[:200],
            source=catalyst_source,
            is_blocking=is_blocking,
        ))

    highest_sev     = _highest_severity(conflicts)
    has_blocking    = any(c.is_blocking for c in conflicts)
    has_within_dte  = any(c.within_dte_window for c in conflicts)

    # Catalyst override: GO → GO_LIMIT only (never BLOCKED — capital denial is trader's decision)
    # Applied only when HIGH or CRITICAL conflict is within DTE window
    if has_within_dte and _SEVERITY_RANK.get(highest_sev, 0) >= _SEVERITY_RANK["HIGH"]:
        catalyst_override = "GO_LIMIT"
    else:
        catalyst_override = None

    # Summary
    if not conflicts:
        summary = f"No catalyst conflicts detected for {ticker} within {dte_window}d DTE window"
    else:
        types = [c.conflict_type for c in conflicts]
        summary = (
            f"{len(conflicts)} conflict(s) detected: {', '.join(set(types))}. "
            f"Highest severity: {highest_sev}. "
            f"{'GO→GO_LIMIT override applied.' if catalyst_override else 'No override.'}"
        )

    return CatalystConflictResult(
        ticker=ticker,
        thesis_direction=thesis_direction,
        dte_window=dte_window,
        conflicts=conflicts,
        summary=summary,
        highest_severity=highest_sev,
        has_blocking_conflict=has_blocking,
        catalyst_override=catalyst_override,
    )


def load_and_detect(
    ticker: str,
    thesis_direction: str,
    dte_window: int,
    catalyst_csv_path: Optional[Path] = None,
    today: Optional[datetime] = None,
) -> CatalystConflictResult:
    """
    Convenience wrapper: loads the catalyst CSV then runs detect_catalyst_conflicts.
    Accepts None for catalyst_csv_path — returns clean result with no conflicts.
    """
    if catalyst_csv_path is None:
        return CatalystConflictResult(
            ticker=str(ticker).upper(),
            thesis_direction=thesis_direction,
            dte_window=dte_window,
            summary="No catalyst CSV path provided",
        )

    rows = _load_catalyst_csv(Path(catalyst_csv_path))
    return detect_catalyst_conflicts(
        ticker=ticker,
        thesis_direction=thesis_direction,
        dte_window=dte_window,
        catalyst_rows=rows,
        catalyst_source=Path(catalyst_csv_path).name,
        today=today,
    )


def format_conflict_block(result: CatalystConflictResult) -> str:
    """
    Format a CatalystConflictResult as a text block for injection into prompts.
    """
    lines = [f"CATALYST_CONFLICTS_{result.ticker}:"]
    lines.append(f"  thesis_direction: {result.thesis_direction}")
    lines.append(f"  dte_window:       {result.dte_window}d")
    lines.append(f"  conflicts_found:  {len(result.conflicts)}")
    lines.append(f"  highest_severity: {result.highest_severity}")
    if result.catalyst_override:
        lines.append(f"  override:         {result.catalyst_override}  [GO→GO_LIMIT only]")
    if result.conflicts:
        for c in result.conflicts:
            lines.append(
                f"  [{c.severity}] {c.conflict_type}: {c.description[:80]}"
                f" | in_window={c.within_dte_window}"
                f" | days_until={c.days_until_event}"
            )
    else:
        lines.append("  status: CLEAN — no catalyst conflicts in DTE window")
    lines.append(f"  summary: {result.summary}")
    return "\n".join(lines)