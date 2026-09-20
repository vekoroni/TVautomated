"""AVS-ILA-001 (audit/intelligence_lab/, 20 Sep 2026), root cause ILA-RC-05: getEvInfo() must
never present a fabricated zero as a real EV value. Source-inspection style, matching this
codebase's established convention for testing intelligence-lab/static/index.html (see
tests/test_options_liquidity_morning_lab.py) - no JS test runner exists in this repo and
introducing one for a single function is disproportionate; Node is available locally but not a
project dependency, so this stays consistent with existing practice rather than adding a new one.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "intelligence-lab" / "static" / "index.html"


def _get_ev_info_source() -> str:
    html = INDEX_HTML.read_text(encoding="utf-8")
    start = html.index("function getEvInfo(s) {")
    end = html.index("\n}\n", start) + len("\n}")
    return html[start:end]


def test_no_data_sentinel_is_never_a_fabricated_zero():
    source = _get_ev_info_source()
    # The old bug: `let first = { value: 0, source: '' };` seeded a fake zero-EV record before
    # any real key was ever read, and the function returned it unchanged when nothing resolved -
    # a row with NO validated EV at all rendered as "+0.000", indistinguishable from a real,
    # computed zero-EV row (formatEv already renders NaN as 'NOT COMPARABLE' - only this
    # function's own no-data path was ever broken).
    assert "let first = { value: 0, source: '' }" not in source, (
        "getEvInfo still seeds a fabricated zero-EV sentinel before checking any real key"
    )
    assert "let first = null" in source
    assert "return first || { value: Number.NaN, source: '' }" in source, (
        "getEvInfo must fall back to a NaN sentinel, not a numeric zero, when no EV key resolved"
    )


def test_seen_flag_removed_not_left_as_dead_code():
    # The old `let seen = false; ... if (!seen) { first = info; seen = true; }` pattern is
    # fully superseded by `if (first === null)`; confirm it was replaced, not left dangling
    # alongside the fix (which would silently do nothing and confuse the next reader).
    source = _get_ev_info_source()
    assert "let seen = false" not in source
    assert "if (first === null) { first = info; }" in source
