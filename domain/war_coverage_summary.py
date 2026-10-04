"""Per-ticker coverage/contradiction summary for the WAR report.

Gap 5 (ACK, 25 Sep 2026): missing or stale News Briefing, later-session
intraday bars, catalyst, exact option quote and participant-identity evidence
must be surfaced prominently rather than folded into a confident narrative.
An unsupported answer stays PARTIAL/NO DATA; this module never manufactures a
complete narrative. An empty auction/economic-event calendar is a distinct
state from a read failure against that source — the two are never conflated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping


class SourceCoverageState(str, Enum):
    AVAILABLE = "AVAILABLE"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    NO_DATA = "NO_DATA"
    NOT_CHECKED = "NOT_CHECKED"
    EMPTY_CONFIRMED = "EMPTY_CONFIRMED"      # source was read; it legitimately has nothing
    READ_FAILURE = "READ_FAILURE"            # source could not be read at all


COVERAGE_SOURCES = (
    "news_briefing", "later_session_intraday_bars", "catalyst",
    "exact_option_quote", "participant_identity",
)

_GAP_STATES = {
    SourceCoverageState.NO_DATA.value, SourceCoverageState.STALE.value,
    SourceCoverageState.PARTIAL.value, SourceCoverageState.NOT_CHECKED.value,
    SourceCoverageState.READ_FAILURE.value,
}


@dataclass(frozen=True, slots=True)
class SourceCoverageEntry:
    source_name: str
    state: str
    detail: str


def classify_calendar_source(
    *, was_read_successfully: bool, row_count: int | None,
) -> SourceCoverageEntry:
    """Distinguish an empty calendar from a failed read of that source."""
    if not was_read_successfully:
        return SourceCoverageEntry(
            "auction_or_economic_event_calendar", SourceCoverageState.READ_FAILURE.value,
            "the calendar source could not be read",
        )
    if row_count == 0:
        return SourceCoverageEntry(
            "auction_or_economic_event_calendar", SourceCoverageState.EMPTY_CONFIRMED.value,
            "the calendar was read successfully and has no scheduled events",
        )
    return SourceCoverageEntry(
        "auction_or_economic_event_calendar", SourceCoverageState.AVAILABLE.value,
        f"{row_count} scheduled event(s) found",
    )


def build_ticker_coverage_summary(
    *, ticker: str, source_states: Mapping[str, SourceCoverageEntry],
) -> dict[str, Any]:
    """Assemble the per-ticker coverage/contradiction summary.

    Any source not present in ``source_states`` is recorded NOT_CHECKED — a
    caller must positively assert a source was checked; absence never
    silently defaults to NO_DATA.
    """
    entries = []
    gaps = []
    for name in COVERAGE_SOURCES:
        entry = source_states.get(name) or SourceCoverageEntry(
            name, SourceCoverageState.NOT_CHECKED.value, "not checked for this report"
        )
        entries.append(asdict(entry))
        if entry.state in _GAP_STATES:
            gaps.append(name)
    narrative_completeness = "COMPLETE" if not gaps else "PARTIAL_NO_DATA"
    return {
        "ticker": ticker.strip().upper(),
        "source_coverage": entries,
        "coverage_gaps": gaps,
        "narrative_completeness": narrative_completeness,
        "may_render_full_narrative": narrative_completeness == "COMPLETE",
    }


__all__ = ["SourceCoverageState", "COVERAGE_SOURCES", "SourceCoverageEntry",
           "classify_calendar_source", "build_ticker_coverage_summary"]
