"""AVS-SD-ILA-003: the governed selected-contract identity is published once and read everywhere.

Business rules (docs/AVS-SD-ILA-003-SELECTED-CONTRACT-IDENTITY-CONTRACT.md):
- The full book publishes ``selected_contract_symbol`` from the governed
  ``selected_contract_symbols`` list, with a typed ``selected_contract_identity_state``.
- The accepted handoff, materialised from that book, overlays every actionable row.
- The Lab reports the merge's own reconciliation outcome and flags a rejected overlay.
- The fix adds only the two identity fields; every other published field is unchanged.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from contracts.interpreter_handoff_materializer import _identity  # noqa: E402
from contracts.lab_control import (  # noqa: E402
    FINAL_BOOK_FIELDS, _economics_identity, write_final_opportunity_book,
)
from domain.dynamic_options_projection import merge_all_opportunities  # noqa: E402
from test_ila_release_coverage_gate import OCC, RUN_ID, _base_signal  # noqa: E402

MANIFEST = {"pipeline_mode": "EOD", "fatal_flags": [], "stale_flags": []}
GOLDEN = ROOT / "tests" / "fixtures" / "ila003_prefix_book_rows.json"
NEW_FIELDS = {"selected_contract_symbol", "selected_contract_identity_state"}
# Additive book fields published after the ILA-003 golden was captured (Fix Spec Fix 2, 24 Sep 2026).
LATER_ADDITIVE_FIELDS = {"iv_percentile", "ivp_source", "iv_rank_definition", "iv_rank_window_sessions",
                         # INT-001: canonical cumulative move and its horizon convention.
                         "expected_move_5d_fraction", "expected_move_10d_fraction",
                         "expected_move_20d_fraction", "horizon_convention",
                         "call_wall_state", "put_wall_state", "gamma_flip_state",
                         # B1 (ACK 25 Sep 2026): provenance of the Layer 3 forecast the shadow valuer used.
                         "contract_value_forecast_source", "contract_value_forecast_run_id",
                         "contract_value_forecast_age_sessions",
                         # A2 (ACK 25 Sep 2026): the policy's own reason and reversibility of a no-quote state.
                         "execution_viability_domain_reason", "execution_viability_reversible",
                         "execution_viability_recheck",
                         # A1 (ACK 25 Sep 2026): what the invalidation selector measured.
                         "invalidation_candidate_state",
                         # C1 (ACK 25 Sep 2026): scenario disclosure with its assumptions.
                         "scenario_state", "scenario_reason", "scenario_contract_symbol", "scenario_basis",
                         "scenario_pricing_model_version", "scenario_valuation_version",
                         "payoff_flat_net_return_fraction", "payoff_1sigma_net_return_fraction",
                         "payoff_2sigma_net_return_fraction", "payoff_reachable_net_return_fraction",
                         "payoff_structural_net_return_fraction", "payoff_invalidation_net_return_fraction",
                         "payoff_reachable_iv_stress_range", "friction_assumption", "friction_spread_cap",
                         "volatility_budget_validation_state", "volatility_budget_bias_multiplier",
                         "breakeven_p_target_two_outcome", "breakeven_basis", "scenario_is_expected_return",
                         "legacy_rr_basis", "legacy_rr_is_expected_return"}


def _publish(tmp_path, *signals):
    return write_final_opportunity_book(RUN_ID, list(signals), MANIFEST, tmp_path, sync_interpreter=False)


def _single(**overrides):
    defaults = dict(
        contract_symbol=OCC, strike=100, expiry="2099-01-19", dte=30,
        thesis_id="TH-1", trade_idea_id="TI-1", selected_quote_snapshot_id="QS-1",
    )
    return _base_signal(**{**defaults, **overrides})


def _handoff_row(book_row):
    """The materializer's handoff row: the governed record plus its identity block."""
    return {**dict(book_row), **_identity(book_row, RUN_ID, "EOD")}


def _provenance(row):
    return json.loads(row.get("field_provenance_json") or "{}")


def test_published_single_contract_row_carries_governed_singular_identity(tmp_path):
    row = _publish(tmp_path, _single())["rows"][0]
    assert row["selected_contract_symbol"] == json.loads(row["selected_contract_symbols"])[0]
    assert row["selected_contract_symbol"] == "AAA990119C00100000"
    assert row["selected_contract_identity_state"] == "SINGLE"
    provenance = _provenance(row)
    assert provenance["selected_contract_symbol"] == "economics_identity:selected_contract_symbols"
    assert provenance["selected_contract_identity_state"] == "economics_identity:selected_contract_symbols"


def test_absent_and_multi_leg_contracts_publish_typed_state_not_blank(tmp_path):
    absent = _publish(tmp_path, _base_signal(ticker="BBB", thesis_id="TH-2", trade_idea_id="TI-2"))["rows"][0]
    assert absent["selected_contract_symbol"] == ""
    assert absent["selected_contract_identity_state"] == "NOT_SELECTED"

    multi = _economics_identity({
        "ticker": "CCC", "canonical_direction": "CALL", "selected_structure": "STRANGLE",
        "selected_contract_symbols": '["CCC990119C00100000", "CCC990119P00090000"]',
    })
    assert multi["selected_contract_symbol"] == ""
    assert multi["selected_contract_identity_state"] == "MULTI_LEG"


def test_reselected_contract_publishes_the_governed_symbol_not_a_copied_alias(tmp_path):
    row = _publish(tmp_path, _single(
        previous_contract_symbol="O:AAA990119C00095000",
        recommended_contract="O:AAA990119C00095000",
        contract_repair_status="CONTRACT_REPAIR_REQUIRED",
    ))["rows"][0]
    assert row["selected_contract_symbol"] == "AAA990119C00100000"
    assert row["selected_contract_identity_state"] == "SINGLE"


def test_accepted_handoff_overlays_every_actionable_row_of_its_own_book(tmp_path):
    book = _publish(
        tmp_path,
        _single(),
        _single(ticker="DDD", thesis_id="TH-4", trade_idea_id="TI-4", selected_quote_snapshot_id="QS-4",
                contract_symbol="O:DDD990119C00050000"),
        _single(ticker="EEE", thesis_id="TH-5", trade_idea_id="TI-5", selected_quote_snapshot_id="QS-5",
                contract_symbol="O:EEE990119C00020000",
                previous_contract_symbol="O:EEE990119C00025000",
                contract_repair_status="CONTRACT_REPAIR_REQUIRED"),
        _base_signal(ticker="BBB", thesis_id="TH-2", trade_idea_id="TI-2"),
        _base_signal(ticker="FFF", thesis_id="TH-6", trade_idea_id="TI-6"),
    )
    by_ticker = {row["ticker"]: row for row in book["rows"]}
    actionable = [
        {**_handoff_row(by_ticker[ticker]), "quote_timestamp_utc": "2099-01-03T14:26:46Z"}
        for ticker in ("AAA", "DDD", "EEE")
    ]
    rows, reconciliation = merge_all_opportunities(book["rows"], actionable)
    assert reconciliation["actionable_rows_overlaid"] == 3
    assert reconciliation["actionable_rows_rejected"] == 0
    assert reconciliation["full_opportunity_count"] == 5
    assert reconciliation["status"] == "PASS"
    overlaid = {row["ticker"] for row in rows if row.get("lab_actionable_handoff_member") is True}
    assert overlaid == {"AAA", "DDD", "EEE"}
    for row in rows:
        expected = "2099-01-03T14:26:46Z" if row["ticker"] in overlaid else ""
        assert (row.get("quote_timestamp_utc") or "") == expected


def test_both_identity_fields_are_allow_listed_in_the_book_contract():
    assert NEW_FIELDS <= set(FINAL_BOOK_FIELDS)
    fields = list(FINAL_BOOK_FIELDS)
    assert fields.index("selected_contract_symbol") == fields.index("selected_contract_symbols") + 1


def _lab_module(tmp_path, monkeypatch):
    monkeypatch.setenv("MSI_LAB_V3_VIEW", "1")
    monkeypatch.setenv("MSI_CONFIG_PATH", str(tmp_path / "no_msi_config.json"))
    spec = importlib.util.spec_from_file_location(
        "lab_ila003_test", ROOT / "intelligence-lab" / "intelligence_lab.py")
    lab = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(lab)
    monkeypatch.setattr(lab, "RUNS_DIR", tmp_path)
    return lab


def _fake_handoff(monkeypatch, book_rows, manifest_status="PASS"):
    import contracts.interpreter_handoff as handoff_contract

    def fake_validate(path, require_accepted=True):
        return SimpleNamespace(
            manifest={"run_id": RUN_ID, "reconciliation_status": manifest_status},
            book_rows=book_rows,
        )
    monkeypatch.setattr(handoff_contract, "validate_handoff_manifest", fake_validate)


def test_lab_reports_merge_status_and_flags_rejected_overlay(tmp_path, monkeypatch):
    lab = _lab_module(tmp_path, monkeypatch)
    book = _publish(tmp_path, _single())
    (tmp_path / RUN_ID / "interpreter").mkdir(parents=True, exist_ok=True)
    (tmp_path / RUN_ID / "interpreter" / "handoff_manifest.json").write_text("{}", encoding="utf-8")
    handoff_row = _handoff_row(book["rows"][0])

    # Identity reconciles: the Lab reports the merge outcome, not the manifest's word.
    _fake_handoff(monkeypatch, [handoff_row])
    governed = lab._governed_lab_book(RUN_ID)
    assert governed["reconciliation"]["status"] == "PASS"
    assert governed["reconciliation"]["handoff_reconciliation_status"] == "PASS"
    assert governed["reconciliation"]["actionable_rows_overlaid"] == 1

    # A handoff row whose identity no longer matches is rejected and visibly flagged,
    # even though the manifest still says PASS.
    _fake_handoff(monkeypatch, [{**handoff_row, "selected_contract_symbol": "AAA990119C00105000"}])
    governed = lab._governed_lab_book(RUN_ID)
    assert governed["reconciliation"]["status"] == "PARTIAL"
    assert governed["reconciliation"]["handoff_reconciliation_status"] == "PASS"
    assert governed["reconciliation"]["actionable_rows_rejected"] == 1
    payload = lab._load_run(RUN_ID, force_reload=True)
    assert payload["lab_reconciliation"]["status"] == "PARTIAL"
    assert "LAB_HANDOFF_OVERLAY_REJECTED:1" in payload["run_health"]["conflict_flags"]
    assert "overlay rejected" in payload["lab_data_notice"].lower()


def test_fix_adds_only_the_two_identity_fields(tmp_path):
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    rows = _publish(
        tmp_path,
        _single(),
        _base_signal(ticker="BBB", thesis_id="TH-2", trade_idea_id="TI-2"),
    )["rows"]
    volatile = set(golden["volatile_keys"])
    assert set(rows[0]) - set(golden["rows"][0]) == NEW_FIELDS | LATER_ADDITIVE_FIELDS
    for published, expected in zip(rows, golden["rows"]):
        actual = {k: v for k, v in published.items()
                  if k not in volatile and k not in NEW_FIELDS and k not in LATER_ADDITIVE_FIELDS}
        # Provenance gains exactly the two new labels and nothing else.
        actual_provenance = {k: v for k, v in _provenance(published).items()
                             if k not in NEW_FIELDS and k not in LATER_ADDITIVE_FIELDS}
        expected_provenance = json.loads(expected.pop("field_provenance_json", "{}"))
        actual.pop("field_provenance_json", None)
        # INT-001 represents absent/unqualified convexity as JSON null rather
        # than the old empty string; both are missing, neither is measured zero.
        for key in ("convexity_score", "convexity_score_max"):
            if actual.get(key) is None and expected.get(key) == "":
                actual[key] = ""
        assert actual_provenance == expected_provenance
        assert actual == expected
