"""AVS-ILA-001 (audit/intelligence_lab/, 20 Sep 2026), root cause ILA-RC-06: optional/
deprecated capabilities are rendered as if they were required, failed tabs. Section 6.4:
"No eil__* telemetry is present in the final book. The EIL pane is explicitly described in
code as legacy advisory telemetry. Showing an instruction to run
execution_intelligence_runner.py makes an optional/deprecated capability appear to be a
production failure. Hide the pane unless a governed EIL artefact is present, or label it
'LEGACY TELEMETRY — NOT ACTIVE FOR THIS RUN'."

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
