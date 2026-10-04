"""EV v2 out of the Lab ranking and the journal (ACK 30 Sep 2026: "approved, remove EV v2 from priority score").

Legacy EV v2 is not an expected value (CLAUDE.md rule 5; wrong for puts, IV sign inverted — verified 29 Sep). It
was 10 % of the Lab's research priority score and the EV recorded on journal entries.

Business rules:
- The priority score does not depend on EV v2. The remaining weights are scaled by 1 / 0.90 so they still sum to 1
  and a row that maxes every remaining dimension still scores 100.
- A journal entry records the EV3 advisory value the Lab book published for that row (`ev_predicted`, which the book
  sets only when EV3 valued the selected contract), or no EV at all; never EV v2.
- The Vanguard trade contract accepts a missing entry EV (recorded as null, never a fabricated 0).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
LAB_PATH = ROOT / "intelligence-lab" / "intelligence_lab.py"


@pytest.fixture(scope="module")
def lab():
    spec = importlib.util.spec_from_file_location("intelligence_lab_priority_test", LAB_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BEST = {"options_verdict": "EXECUTE", "campaign_verdict": "READY_EXECUTE", "execution_verdict": "BUY_NOW",
        "eil_composite_score": 100, "rr_options": 3.0, "rr_options_reachable": 3.0, "options_score": 100, "wbs__wbs_grade": "PROBABLE",
        "wbs__wbs": 100, "garch__l3_iv_tailwind_score": -0.10}


def test_the_priority_score_does_not_depend_on_ev_v2(lab):
    low = lab._compute_priority_score({**BEST, "options_score": 40, "ev2_ev_conf_adj": -0.25})
    high = lab._compute_priority_score({**BEST, "options_score": 40, "ev2_ev_conf_adj": 0.25})
    assert low == high


def test_a_row_that_maxes_every_remaining_dimension_still_scores_100(lab):
    assert lab._compute_priority_score(BEST) == 100.0


def test_the_remaining_weights_keep_their_relative_order(lab):
    # options verdict (0.22 / 0.90) is still the largest single dimension
    only_verdict = lab._compute_priority_score({"options_verdict": "EXECUTE"})
    only_campaign = lab._compute_priority_score({"campaign_verdict": "READY_EXECUTE"})
    assert only_verdict == pytest.approx(22 / 0.90, abs=0.1)
    assert only_campaign == pytest.approx(16 / 0.90, abs=0.1)


@pytest.mark.parametrize("sig,expected", [
    ({"ev_predicted": -0.12, "ev2_ev_conf_adj": 0.31, "ev": 0.31}, -0.12),
    ({"ev_predicted": "", "ev2_ev_conf_adj": 0.31, "ev": 0.31}, None),
    ({"ev2_ev_conf_adj": 0.31}, None),
    ({"ev_predicted": "nan"}, None),
])
def test_the_journal_records_the_books_ev3_value_or_none(lab, sig, expected):
    assert lab._journal_ev(sig) == expected


def test_the_trade_contract_accepts_a_missing_entry_ev(tmp_path, monkeypatch):
    from vanguard import trade_contract as tc
    monkeypatch.setattr(tc, "OPEN_DIR", tmp_path / "open")
    monkeypatch.setattr(tc, "CLOSED_DIR", tmp_path / "closed")
    monkeypatch.setattr(tc, "GOV_LOG_DIR", tmp_path / "log")
    contract = tc.create_contract(
        ticker="TEST", entry_price=100.0, direction="CALL", horizon_type="20D", edge_quality="MODERATE",
        entry_ev=None, entry_win_rate=0.5, entry_state_hash="", entry_vol_regime="", entry_trend_direction="",
        entry_trend_maturity="", entry_structure_quality="", entry_macro_regime="", entry_catalyst_proximity="",
        entry_adx=20.0, entry_atr_percentile=50.0, invalidation_price=95.0, max_expected_mae=0.05)
    assert contract["entry_ev"] is None
