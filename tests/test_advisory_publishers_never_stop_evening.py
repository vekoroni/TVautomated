"""Advisory packets describe; they never decide, so they never end the Evening.

Business rule (ACK, 21 Nov 2026: "we do not want the pipeline to stop"; TEV-001 P0(a),
approved 27 Sep 2026 and not built until now):

  The pre-option ticker description (C5), the option candidate set (C6) and the
  valuation disposition (C8) carry no trading authority. When one of them cannot be
  published, the Evening records what is missing and why, and carries on.

  A description that could not be frozen before options is never published later
  and passed off as the pre-option view.

Legacy behaviour replaced: both publishers sat inline in ``evening_workflow`` and
returned False on any exception ("Evening workflow aborted: pre-option forecast
publication failed" / "C6 candidate publication failed"), ending the run.

Isolated: temporary run folders only; no provider, no live data, no network.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import intelligent_orchestrator as orch
from contracts import descriptive_forecast_packet as c5

RUN_ID = "20261119_234734"


@pytest.fixture
def run_root(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    root = runs / RUN_ID
    (root / "vanguard").mkdir(parents=True)
    (root / "vanguard" / "vanguard_run_summary.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(orch.cfg, "RUNS_DIR", runs)
    return root


def _status(root: Path) -> dict:
    return json.loads((root / "forecast" / c5.ADVISORY_STATUS_FILE).read_text(encoding="utf-8"))


def test_pre_option_description_failure_is_recorded_and_the_evening_continues(run_root, monkeypatch):
    def broken(_root):
        raise c5.DescriptivePacketError("Vanguard/Discovery population does not reconcile")

    monkeypatch.setattr(c5, "load_or_publish_descriptive_packet", broken)

    state = orch._publish_pre_option_forecast_packet(RUN_ID)

    assert state == "UNAVAILABLE"
    recorded = _status(run_root)["stages"]["C5_DESCRIPTIVE_FORECAST"]
    assert recorded["state"] == "UNAVAILABLE"
    assert "does not reconcile" in recorded["reason"]
    assert recorded["authority"] == "ADVISORY_ONLY"


def test_missing_vanguard_summary_is_recorded_not_fatal(run_root):
    (run_root / "vanguard" / "vanguard_run_summary.json").unlink()

    assert orch._publish_pre_option_forecast_packet(RUN_ID) == "UNAVAILABLE"
    assert "Vanguard terminal summary missing" in _status(run_root)["stages"]["C5_DESCRIPTIVE_FORECAST"]["reason"]


def test_a_healthy_publication_writes_no_failure_record(run_root, monkeypatch):
    monkeypatch.setattr(
        c5, "load_or_publish_descriptive_packet",
        lambda _root: {"row_count": 3, "vanguard_present_count": 2, "vanguard_rejected_count": 1},
    )

    assert orch._publish_pre_option_forecast_packet(RUN_ID) == "PUBLISHED"
    assert not (run_root / "forecast" / c5.ADVISORY_STATUS_FILE).exists()
    assert c5.advisory_publication_state(run_root, "C5_DESCRIPTIVE_FORECAST") is None


def test_candidate_set_failure_is_recorded_and_valuation_is_not_attempted(run_root, monkeypatch):
    from contracts import expression_candidate_packet as c6
    from contracts import expression_valuation_packet as c8

    def broken(*_args, **_kwargs):
        raise RuntimeError("frozen C5 packet unavailable")

    monkeypatch.setattr(c6, "publish_expression_candidates", broken)
    monkeypatch.setattr(c8, "publish_expression_valuations",
                        lambda *a, **k: pytest.fail("C8 must not run without its C6 input"))

    states = orch._publish_option_expression_packets(RUN_ID)

    assert states == {"C6_EXPRESSION_CANDIDATES": "UNAVAILABLE", "C8_EXPRESSION_VALUATION": "NOT_ATTEMPTED"}
    stages = _status(run_root)["stages"]
    assert stages["C6_EXPRESSION_CANDIDATES"]["state"] == "UNAVAILABLE"
    assert "frozen C5 packet unavailable" in stages["C6_EXPRESSION_CANDIDATES"]["reason"]
    assert stages["C8_EXPRESSION_VALUATION"]["state"] == "NOT_ATTEMPTED"


def test_valuation_failure_keeps_the_published_candidate_set(run_root, monkeypatch):
    from contracts import expression_candidate_packet as c6
    from contracts import expression_valuation_packet as c8

    monkeypatch.setattr(c6, "publish_expression_candidates", lambda *a, **k: {"row_count": 5})

    def broken(*_args, **_kwargs):
        raise OSError("historical_prices.sqlite is locked")

    monkeypatch.setattr(c8, "publish_expression_valuations", broken)

    states = orch._publish_option_expression_packets(RUN_ID)

    assert states == {"C6_EXPRESSION_CANDIDATES": "PUBLISHED", "C8_EXPRESSION_VALUATION": "UNAVAILABLE"}
    stages = _status(run_root)["stages"]
    assert "C6_EXPRESSION_CANDIDATES" not in stages
    assert "locked" in stages["C8_EXPRESSION_VALUATION"]["reason"]


def test_an_unfrozen_description_is_never_published_late(run_root):
    """After a recorded pre-option failure nobody may publish C5 from post-option files."""
    assert c5.may_publish_descriptive_packet(run_root) is True

    c5.record_advisory_publication(run_root, "C5_DESCRIPTIVE_FORECAST", "UNAVAILABLE", reason="test")

    assert c5.may_publish_descriptive_packet(run_root) is False
    with pytest.raises(c5.DescriptivePacketError, match="not frozen before options"):
        c5.load_or_publish_descriptive_packet(run_root)


def test_the_evening_no_longer_aborts_on_an_advisory_packet():
    source = inspect.getsource(orch.evening_workflow)

    assert "pre-option forecast publication failed" not in source
    assert "C6 candidate publication failed" not in source
    assert "_publish_pre_option_forecast_packet(canonical_run_id)" in source
    assert "_publish_option_expression_packets(canonical_run_id)" in source


def test_the_lab_asks_before_publishing_the_description():
    from contracts import lab_control

    assert "may_publish_descriptive_packet(packet_root)" in inspect.getsource(lab_control)
