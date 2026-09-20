"""AVS-ILA-001 (audit/intelligence_lab/, 20 Sep 2026), root cause ILA-RC-05: no field the
Intelligence Lab displays may render a fabricated or lost value in place of a real one - covers
both getEvInfo() (a fabricated zero EV when no real value exists) and the four opt() closures
(a real, valid zero, e.g. contract volume, treated as missing by plain OR). Source-inspection
style, matching this codebase's established convention for testing
intelligence-lab/static/index.html (see tests/test_options_liquidity_morning_lab.py) - no JS
test runner exists in this repo and introducing one for a handful of functions is
disproportionate; Node is available locally but not a project dependency, so this stays
consistent with existing practice rather than adding a new one.
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


def _html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def test_no_local_closure_still_uses_plain_or_on_a_field_that_can_be_zero():
    """ILA-RC-05, second half: the `opt` helper was duplicated as a local closure four times
    (execCardHTML, the dossier panel, the execute-pane list, the armed list), each using plain
    OR (`s[opt__k] || s[k] || '—'`), which treats a real, valid 0 - e.g. contract volume -
    the same as missing. All four now delegate to the shared optField(s, k), which uses the
    same missing-value rule as the Python-side project() helper (empty string, 'nan', 'None' are
    "not set"; 0 and false are real values).
    """
    html = _html()
    # The old buggy pattern is still quoted, verbatim, inside this fix's own documentation
    # comment (explaining what was wrong) - check it only as a live assignment, not anywhere
    # in the file, so that legitimate historical documentation doesn't produce a false positive.
    assert "const opt = (k) => s[`opt__${k}`] || s[k] || '—';" not in html
    assert "const opt = (s,k) => s[`opt__${k}`] || s[k] || '—';" not in html
    assert html.count("const opt = (k) => optField(s, k);") == 3
    assert "const opt = optField;" in html


def test_shared_opt_field_helper_preserves_a_real_zero():
    source = _html()
    start = source.index("function _hasValue(v)")
    end = source.index("function getPrice(s)")
    snippet = source[start:end]
    assert "if (_hasValue(a)) return a;" in snippet
    assert "if (_hasValue(b)) return b;" in snippet
    assert "return '—';" in snippet
    # _hasValue's own rule: only null/undefined/''/'nan'/'None' count as missing - a real 0
    # (String(0) === '0') must fall through to "has a value", not "missing".
    assert "t !== '' && t !== 'nan' && t !== 'None'" in snippet
