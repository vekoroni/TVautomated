"""AVS-ILA-001 (audit/intelligence_lab/, 20 Sep 2026), root cause ILA-RC-04: Morning pre-open
thesis validation and post-open contract refresh were conflated behind a single "Morning
Thesis Check" display (and a single top-of-dossier lifecycle banner) that only ever read
validation_transition / lab_status_banner - fields confirmed entirely absent as columns in the
real morning_validated_trades_20260918_112522.csv, because that run (like every other recent
real run) executed in POSTOPEN_CONTRACT_REFRESH mode, never PREOPEN_THESIS_CHECK. A row
validated GO in post-open mode (morning_transition_state=EXECUTABLE_NOW) therefore displayed
"CURRENT VALIDATION NOT RUN" / "Morning Gate has not validated this thesis" - directly
contradicting its own GO/READY_EXECUTE verdict shown elsewhere on the same dossier.

Fix: pre-open thesis state (validation_transition), post-open contract state
(morning_transition_state) and the event mode (morning_execution_mode) are now three
separate, always-labelled concepts, per the audit's required semantics (section 7.1):
"No single 'Morning' label may infer one state from the other." Source-inspection style,
matching this codebase's established convention for testing intelligence-lab/static/index.html
(see tests/test_options_liquidity_morning_lab.py, tests/test_ila_ev_not_fabricated.py).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "intelligence-lab" / "static" / "index.html"


def _html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def _function_source(html: str, signature: str) -> str:
    start = html.index(signature)
    end = html.index("\n}\n", start) + len("\n}")
    return html[start:end]


def test_preopen_thesis_state_no_longer_claims_morning_never_ran():
    # The renamed, corrected function must say a PRE-OPEN event didn't run, not that
    # Morning as a whole never validated the row (it may well have, in post-open mode).
    html = _html()
    source = _function_source(html, "function getPreopenThesisState(s) {")
    assert "did not perform a pre-open thesis-validation event" in source
    assert "Morning Gate has not validated this thesis." not in source


def test_postopen_contract_state_is_a_separate_labelled_function():
    html = _html()
    # The state->label map lives in a const above the function (mirroring
    # POSTOPEN_CONTRACT_STATE_LABELS), so include both in the searched span.
    start = html.index("const POSTOPEN_CONTRACT_STATE_LABELS")
    end = html.index("\n}\n", html.index("function getPostopenContractState(s) {", start)) + len("\n}")
    source = html[start:end]
    for state in [
        "EXECUTABLE_NOW",
        "CONTRACT_REPRICE_REQUIRED",
        "THESIS_INVALIDATED",
        "MOVE_ALREADY_REALIZED",
        "LIQUIDITY_STILL_PENDING",
        "GAP_CONFIRMATION_WITH_RUNWAY",
        "WAIT_FOR_PULLBACK",
        "GAP_CONFIRMATION_EXTENDED",
        "LEGACY_LIFECYCLE_NOT_EVALUATED",
    ]:
        assert state in source, f"{state} not mapped in getPostopenContractState"
    assert "did not perform a post-open contract-refresh event" in source


def test_event_mode_helper_exists_and_is_rendered_beside_both_states():
    html = _html()
    assert "function getMorningEventMode(s) {" in html
    lifecycle_start = html.index('<div class="m-sec-hdr">Liquidity Lifecycle</div>')
    lifecycle_end = html.index("GEX Levels", lifecycle_start)
    section = html[lifecycle_start:lifecycle_end]
    assert "getPostopenContractState(s)" in section, (
        "post-open contract state must be shown in the Liquidity Lifecycle section"
    )
    assert "getPreopenThesisState(s)" in section, (
        "pre-open thesis state must be shown in the same section, not inferred from the other"
    )
    assert "getMorningEventMode(s)" in section, (
        "the event mode must be shown beside both states so a reader knows which one actually ran"
    )


def test_no_call_site_still_references_the_retired_conflated_function_name():
    html = _html()
    assert "getMorningThesisDisplay" not in html


def test_lifecycle_banner_is_mode_aware_and_never_claims_not_run_when_a_mode_ran():
    # ILA-001 section 7.1's headline example: GO/READY_EXECUTE next to a banner claiming
    # "CURRENT VALIDATION NOT RUN". lab_status_banner is set only by the EOD interpreter
    # handoff path, never by morning_gate.py, so its absence must not be read as "nothing
    # ran" - the banner must fall back to a mode-aware statement instead of a static claim.
    html = _html()
    source = _function_source(html, "function getMorningLifecycleBanner(s) {")
    assert "POSTOPEN_CONTRACT_REFRESH" in source
    assert "PREOPEN_THESIS_CHECK" in source
    assert "getMorningLifecycleBanner(s)" in html
    assert "'THESIS PREPARED — CURRENT VALIDATION NOT RUN'" not in html
