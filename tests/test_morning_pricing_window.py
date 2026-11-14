"""Morning may start pricing at any time during XNYS market hours (ACK, 14 Nov 2026).

A start outside the preferred 09:35-09:45 ET window is priced and labelled; only a start
outside market hours (before the open, after the close, weekend, holiday) is refused.

Offline entry-point tests: forbidden I/O is a sentinel, never a real run.
"""
from datetime import datetime, timezone
import ast
import logging
from pathlib import Path
from typing import Optional

import pytest
import morning_gate as gate


class NoPricingPerformed(Exception):
    pass


def clock(value):
    instant = datetime.fromisoformat(value)
    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
    return Frozen


def forbid_setup(*args, **kwargs):
    raise NoPricingPerformed("I/O boundary reached")


@pytest.mark.parametrize("instant", [
    "2026-11-13T14:29:59+00:00",  # 09:29:59 ET, before the open
    "2026-11-13T21:00:00+00:00",  # 16:00 ET, the close
    "2026-11-14T14:40:00+00:00",  # Saturday
    "2026-11-26T14:40:00+00:00",  # Thanksgiving
    "2026-11-27T18:00:00+00:00",  # 13:00 ET on an early-close day
    "2026-10-30T13:29:00+00:00",  # 09:29 EDT, before the US autumn clock change
])
def test_outside_market_hours_stops_before_any_setup_or_provider_work(monkeypatch, instant):
    monkeypatch.setattr(gate, "datetime", clock(instant))
    monkeypatch.setattr(gate, "set_morning_rate_inputs", forbid_setup)
    with pytest.raises(RuntimeError, match="MORNING_PRICING_WINDOW_CLOSED"):
        gate.run_morning_gate("SAVED_ONLY_NO_RUN")


@pytest.mark.parametrize("instant", [
    "2026-11-13T14:30:00+00:00",  # 09:30 ET, the open
    "2026-11-13T14:35:00+00:00", "2026-11-13T14:45:59+00:00",
    "2026-11-13T14:46:00+00:00",  # 09:46 ET, one minute late: still priced
    "2026-11-13T15:42:00+00:00",  # 10:42 ET, as the 12 Nov Morning ran
    "2026-11-13T18:42:00+00:00",  # 13:42 ET, as the 22 Oct Morning ran
    "2026-11-13T20:59:00+00:00",  # 15:59 ET, last minute of the session
    "2026-10-30T13:46:00+00:00",  # 09:46 EDT
    "2026-11-27T17:59:00+00:00",  # 12:59 ET on an early-close day
])
def test_any_start_during_market_hours_reaches_setup_without_performing_it(monkeypatch, instant):
    monkeypatch.setattr(gate, "datetime", clock(instant))
    monkeypatch.setattr(gate, "set_morning_rate_inputs", forbid_setup)
    with pytest.raises(NoPricingPerformed):
        gate.run_morning_gate("SAVED_ONLY_NO_RUN")


@pytest.mark.parametrize("instant,state", [
    ("2026-11-13T14:30:00+00:00", "BEFORE_PREFERRED_WINDOW"),
    ("2026-11-13T14:35:00+00:00", "DEFAULT_WINDOW"),
    ("2026-11-13T14:45:59+00:00", "DEFAULT_WINDOW"),
    ("2026-11-13T14:46:00+00:00", "AFTER_PREFERRED_WINDOW"),
    ("2026-11-13T18:42:00+00:00", "AFTER_PREFERRED_WINDOW"),
])
def test_start_outside_the_preferred_window_is_priced_and_labelled_never_refused(instant, state):
    from domain.morning_pricing_window import require_morning_pricing_start
    decision = require_morning_pricing_start("POSTOPEN_CONTRACT_REFRESH", datetime.fromisoformat(instant))
    assert decision["state"] == state
    assert decision["policy_version"] == "morning_pricing_policy_v2"


def test_preopen_thesis_only_mode_is_not_blocked_by_pricing_window(monkeypatch):
    monkeypatch.setattr(gate, "datetime", clock("2026-11-13T13:00:00+00:00"))
    monkeypatch.setattr(gate, "set_morning_rate_inputs", forbid_setup)
    with pytest.raises(NoPricingPerformed):
        gate.run_morning_gate("SAVED_ONLY_NO_RUN", execution_mode="PREOPEN_THESIS_CHECK")


def test_orchestrator_rejects_a_start_after_the_close_before_catalyst_or_other_stages():
    # Load only this function's AST: no orchestrator bootstrap or pipeline work.
    source = (Path(gate.__file__).parent / "intelligent_orchestrator.py").read_text(encoding="utf-8-sig")
    function = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "premarket_workflow")
    namespace = {"Optional": Optional, "datetime": clock("2026-11-13T21:01:00+00:00"),
                 "timezone": timezone, "logger": logging.getLogger("window_test")}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "orchestrator_function_only", "exec"), namespace)
    assert namespace["premarket_workflow"]("SAVED_ONLY_NO_RUN") is False


def test_preferred_window_matches_existing_verifier_window():
    import json
    from domain.morning_pricing_window import POLICY_PATH
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8-sig"))
    rules = json.loads((Path(gate.__file__).parent / "tools/avs_verify/avs_verify_rules.json").read_text(encoding="utf-8-sig"))
    assert [policy["preferred_start_et"], policy["preferred_last_start_minute_et"]] == rules["timing"]["morning_quote_window_et"]


def test_naive_clock_is_not_silently_interpreted_as_local_time():
    from domain.morning_pricing_window import require_morning_pricing_start
    with pytest.raises(ValueError, match="aware"):
        require_morning_pricing_start("POSTOPEN_CONTRACT_REFRESH", datetime(2026, 11, 13, 9, 40))


def test_missing_or_unsupported_policy_fails_closed(tmp_path):
    from domain.morning_pricing_window import require_morning_pricing_start
    policy = tmp_path / "policy.json"
    with pytest.raises(FileNotFoundError):
        require_morning_pricing_start("POSTOPEN_CONTRACT_REFRESH", datetime(2026, 11, 13, 14, 40, tzinfo=timezone.utc), policy_path=policy)
    policy.write_text('{"version":"unknown"}', encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        require_morning_pricing_start("POSTOPEN_CONTRACT_REFRESH", datetime(2026, 11, 13, 14, 40, tzinfo=timezone.utc), policy_path=policy)


def test_preparation_cannot_delay_pricing_past_the_close(monkeypatch, tmp_path):
    from types import SimpleNamespace
    class Delayed(datetime):
        calls = 0
        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            instant = datetime.fromisoformat("2026-11-13T14:40:00+00:00" if cls.calls == 1
                                            else "2026-11-13T21:00:00+00:00")
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
    run_id = "SAVED_ONLY_NO_RUN"
    folder = tmp_path / run_id / "morning_validation"
    folder.mkdir(parents=True)
    input_path = folder / f"morning_candidates_{run_id}.csv"
    input_path.write_text("ticker\nSPY\n", encoding="utf-8")
    before = input_path.read_bytes()
    monkeypatch.setattr(gate, "datetime", Delayed)
    monkeypatch.setattr(gate, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(gate, "MACRO_PATH", tmp_path / "absent_macro.json")
    monkeypatch.setattr(gate, "set_morning_rate_inputs", lambda *_: None)
    monkeypatch.setattr(gate, "active_msi_flags", lambda: SimpleNamespace(v2_capture=False))
    monkeypatch.setattr(gate, "_load_macro_state", lambda: {})
    monkeypatch.setattr(gate, "_load_bond_macro", lambda: {})
    monkeypatch.setattr(gate, "_load_enrichment_delta", lambda: {})
    monkeypatch.setattr(gate, "_load_china_exposure", lambda: {})
    monkeypatch.setattr(gate, "_fetch_all_live", forbid_setup)
    monkeypatch.setenv("AVSHUNTER_CANONICAL_DATA_ENABLED", "0")
    monkeypatch.setenv("AVSHUNTER_CANONICAL_WRITE_THROUGH", "0")
    import canonical_data
    monkeypatch.setattr(canonical_data, "CanonicalRegistry", forbid_setup)
    with pytest.raises(RuntimeError, match="MORNING_PRICING_WINDOW_CLOSED"):
        gate.run_morning_gate(run_id)
    assert input_path.read_bytes() == before
    assert list(folder.iterdir()) == [input_path]


def verifier_timing(manifest):
    import json
    from tools.avs_verify import avs_verify as verify
    cfg = json.loads((Path(gate.__file__).parent / "tools/avs_verify/avs_verify_rules.json").read_text(encoding="utf-8-sig"))
    findings = verify.F({})
    age_clock = verify.r_timing("20261112_230902", "morning", manifest, cfg, findings)
    return findings.book[0], age_clock


def test_verifier_separates_valid_pricing_start_from_later_verdict():
    finding, quote_age_clock = verifier_timing({
        "created_at_utc": "2026-11-12T23:09:02Z",  # old Evening timestamp
        "morning_pricing_started_at_utc": "2026-11-13T14:45:59Z",
        "morning_validation_completed_at_utc": "2026-11-13T14:57:00Z",
    })
    assert finding["status"] == "PASS"
    assert quote_age_clock == datetime(2026, 11, 13, 14, 57, tzinfo=timezone.utc)
    assert finding["evidence"]["source"] == "manifest.morning_pricing_started_at_utc"


def test_verifier_does_not_hide_a_late_or_invalid_start():
    late, _ = verifier_timing({"morning_pricing_started_at_utc": "2026-11-13T14:46:00Z",
                              "morning_validation_completed_at_utc": "2026-11-13T14:57:00Z"})
    assert late["status"] == "WARN"
    invalid, _ = verifier_timing({"morning_pricing_started_at_utc": "2026-11-13T15:00:00Z",
                                 "morning_validation_completed_at_utc": "2026-11-13T14:57:00Z"})
    assert invalid["status"] == "FAIL"


def test_independent_quote_age_uses_completion_not_start_or_evening_creation():
    import json
    from tools.avs_verify import avs_verify as verify
    _, quote_age_clock = verifier_timing({
        "created_at_utc": "2026-11-12T23:09:02Z",
        "morning_pricing_started_at_utc": "2026-11-13T14:40:00Z",
        "morning_validation_completed_at_utc": "2026-11-13T15:00:00Z",
    })
    cfg = json.loads((Path(gate.__file__).parent / "tools/avs_verify/avs_verify_rules.json").read_text(encoding="utf-8-sig"))
    cm = {key: None for key in cfg["columns"]}
    cm["quote_ts"] = "stamp"
    findings = verify.F({})
    verify.r_rows([{"stamp": "2026-11-13T14:40:00Z"}], [0], cm, cfg, "morning", quote_age_clock, findings)
    quote_check = next(item for item in findings.book if item["rule"] == "R19_QUOTE_FRESH")
    assert quote_check["status"] == "FAIL"
    assert "1/1 tradeable rows" in quote_check["message"]


def test_manifest_carries_both_clocks_without_overwriting_evening_creation(tmp_path):
    import json
    manifest_path = tmp_path / "final_run_manifest.json"
    manifest_path.write_text(json.dumps({"created_at_utc": "2026-11-12T23:09:02Z"}), encoding="utf-8")
    gate._close_final_run_manifest(tmp_path, "SAVED_FIXTURE", {
        "morning_pricing_started_at_utc": "2026-11-13T14:40:00+00:00",
        "morning_pricing_policy_version": "morning_pricing_policy_v1",
        "validated_at_utc": "2026-11-13T15:00:00Z",
    }, {"integrity_status": "PASS"})
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    assert manifest["created_at_utc"] == "2026-11-12T23:09:02Z"
    assert manifest["morning_pricing_started_at_utc"] == "2026-11-13T14:40:00+00:00"
    assert manifest["morning_validation_completed_at_utc"] == "2026-11-13T15:00:00Z"
    assert manifest["run_tradeable"] is False
