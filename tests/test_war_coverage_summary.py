"""Gap 5 (ACK, 25 Sep 2026) — per-ticker coverage/contradiction summary:
stale news, absent later-session bars, and an empty calendar are never
conflated with a source read failure or with each other.
"""
from __future__ import annotations

from domain.war_coverage_summary import (
    SourceCoverageEntry, SourceCoverageState, build_ticker_coverage_summary,
    classify_calendar_source,
)


def test_empty_calendar_after_a_successful_read_is_not_a_read_failure():
    entry = classify_calendar_source(was_read_successfully=True, row_count=0)
    assert entry.state == SourceCoverageState.EMPTY_CONFIRMED.value


def test_a_failed_calendar_read_is_distinct_from_an_empty_calendar():
    entry = classify_calendar_source(was_read_successfully=False, row_count=None)
    assert entry.state == SourceCoverageState.READ_FAILURE.value
    assert entry.state != SourceCoverageState.EMPTY_CONFIRMED.value


def test_stale_news_briefing_is_surfaced_as_a_coverage_gap():
    summary = build_ticker_coverage_summary(
        ticker="bull",
        source_states={
            "news_briefing": SourceCoverageEntry("news_briefing", SourceCoverageState.STALE.value,
                                                  "last updated 2 sessions ago"),
        },
    )
    assert "news_briefing" in summary["coverage_gaps"]
    assert summary["narrative_completeness"] == "PARTIAL_NO_DATA"
    assert summary["may_render_full_narrative"] is False


def test_absent_later_session_bars_is_surfaced_as_a_coverage_gap():
    summary = build_ticker_coverage_summary(
        ticker="EWG",
        source_states={
            "later_session_intraday_bars": SourceCoverageEntry(
                "later_session_intraday_bars", SourceCoverageState.NO_DATA.value,
                "opening-window collector only reaches 13:50Z-16:35Z; no rest-of-session bars",
            ),
        },
    )
    assert "later_session_intraday_bars" in summary["coverage_gaps"]


def test_an_unchecked_source_defaults_to_not_checked_never_no_data():
    summary = build_ticker_coverage_summary(ticker="SOFI", source_states={})
    for entry in summary["source_coverage"]:
        assert entry["state"] == SourceCoverageState.NOT_CHECKED.value
    assert set(summary["coverage_gaps"]) == set(entry["source_name"] for entry in summary["source_coverage"])


def test_a_complete_ticker_may_render_a_full_narrative():
    all_available = {
        name: SourceCoverageEntry(name, SourceCoverageState.AVAILABLE.value, "checked")
        for name in ("news_briefing", "later_session_intraday_bars", "catalyst",
                     "exact_option_quote", "participant_identity")
    }
    summary = build_ticker_coverage_summary(ticker="XLF", source_states=all_available)
    assert summary["coverage_gaps"] == []
    assert summary["narrative_completeness"] == "COMPLETE"
    assert summary["may_render_full_narrative"] is True


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
