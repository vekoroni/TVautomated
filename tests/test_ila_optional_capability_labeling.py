"""AVS-ILA-001 (audit/intelligence_lab/, 20 Sep 2026) UI-labeling root causes ILA-RC-06 and
ILA-RC-07, covered together as one "the Lab must label what a field's authority actually is"
test module.

ILA-RC-06: optional/deprecated capabilities are rendered as if they were required, failed
tabs. Section 6.4: "No eil__* telemetry is present in the final book. The EIL pane is
explicitly described in code as legacy advisory telemetry. Showing an instruction to run
execution_intelligence_runner.py makes an optional/deprecated capability appear to be a
production failure. Hide the pane unless a governed EIL artefact is present, or label it
'LEGACY TELEMETRY — NOT ACTIVE FOR THIS RUN'."

ILA-RC-07: advisory authority is not shown beside advisory metrics (PCR, EV3, DOI, target
payoff), so users can misread them as trade authority. This module covers the PCR
(section 7.3 / 9.2 item 13) and target-payoff (section 7.4 / 9.2 item 14) halves.

Source-inspection style, matching this codebase's established convention for testing
intelligence-lab/static/index.html.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "intelligence-lab" / "static" / "index.html"


def _html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def test_eil_empty_state_no_longer_instructs_running_a_script():
    html = _html()
    assert "Run execution_intelligence_runner.py to populate." not in html


def test_eil_empty_state_labels_it_as_inactive_legacy_telemetry():
    html = _html()
    assert "LEGACY TELEMETRY — NOT ACTIVE FOR THIS RUN" in html


def test_pcr_signal_is_labelled_as_oi_positioning_not_flow():
    """ILA-RC-07 / audit section 7.3 + 9.2 item 13: "PCR SIGNAL: BULLISH" reads as a
    directional-flow instruction. Open interest cannot identify buyer/seller direction
    (see scripts/avshunter_options_intelligence.py::compute_pcr's own docstring). The raw
    measured value (e.g. "BULLISH") must not be rewritten - that would fabricate data - but
    the field label and an adjacent advisory disclaimer must make clear it is OI positioning
    evidence, not confirmed flow, using the governed pcr_direction_conflict_reason when
    present (verified real for run 20260918_112522, ticker SA: "OI PCR confirms CALL with
    reduced confidence").
    """
    html = _html()
    assert "PCR Signal (OI Positioning — Not Flow)" in html
    assert "opt('pcr_direction_conflict_reason')" in html or "s.pcr_direction_conflict_reason" in html


def test_conservative_target_profit_carries_a_scenario_disclaimer():
    """ILA-RC-07 / audit section 7.4: the 548.5%-style target-profit scenario is a payoff
    if the structural target is reached, not a probability or executable certainty. Mirrors
    the existing, established disclaimer pattern already used for Maturation scores
    ("monitoring estimate only - not a probability and cannot authorize entry").
    """
    html = _html()
    assert "scenario payoff if target is reached — not a probability and cannot authorize entry" in html
