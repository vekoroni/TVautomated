"""G5 minimal, item 2 (ACK approved 17 Oct 2026): the card engine values on the run's observed rate.

Design: Enhancements/options_valuation_review/G5_G9_ONE_PRICER_ONE_BASIS_DESIGN_20261017.md (status section).
Before: every card used the 8 Oct governed fallback (0.0422 on all 2,153 cards of run 20261015_225021) because neither
the Evening (eod_candidate_engine) nor the Morning (morning_gate) passed a rate, although each run's
macro_snapshot.json carries the 3-month T-bill (0.0428 on 15 Oct).

Business rules:
- The card is valued on the rate observed for its run, and says which source and run it came from.
- With no observed rate the governed fallback is used and labelled as the fallback (missing is never neutral).
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from canonical_data.market_rate_observation import rate_inputs  # noqa: E402


def _run_folder(root: Path, name: str = "20261015_225021", t3m=4.28) -> Path:
    run = root / name
    (run / "execution").mkdir(parents=True)
    if t3m is not None:
        (run / "macro_snapshot.json").write_text(json.dumps({"rates": {"t3m": t3m, "rates_data_as_of": "2026-10-15"}}))
    return run


def test_the_rate_comes_from_the_run_s_macro_snapshot(tmp_path):
    run = _run_folder(tmp_path)
    got = rate_inputs(run)
    assert got["rate"] == pytest.approx(0.0428)
    assert got["rate_basis"].startswith("MACRO:T3M")
    assert "20261015_225021" in got["rate_basis"]


def test_a_file_inside_the_run_finds_the_run_s_snapshot(tmp_path):
    run = _run_folder(tmp_path)
    assert rate_inputs(run / "execution" / "execution_v3_5_TEST.csv")["rate"] == pytest.approx(0.0428)


def test_with_no_observed_rate_the_card_falls_back_and_says_so(tmp_path):
    from domain.option_valuation import resolve_rate
    got = rate_inputs(_run_folder(tmp_path, t3m=None))
    assert got["rate"] is None and got["rate_basis"].startswith("RATE_UNAVAILABLE")
    rate, label = resolve_rate(got["rate"], got["rate_basis"])
    assert rate == pytest.approx(0.0422) and label.startswith("GOVERNED_FALLBACK")


def test_the_evening_card_engine_is_given_the_run_s_rate(tmp_path, monkeypatch):
    import eod_candidate_engine
    from test_eod_options_research_handoff import _row
    seen = []

    def spy(**kwargs):
        seen.append(kwargs)
        return {}

    monkeypatch.setattr(eod_candidate_engine, "anticipated_move_fields", spy)
    run = _run_folder(tmp_path)
    eil = run / "execution" / "execution_v3_5_TEST.csv"
    pd.DataFrame([_row("GOOD", route="OPTIONS_GO_REVIEW")]).to_csv(eil, index=False)
    eod_candidate_engine.build_candidate_manifest(eil_path=eil, output_path=run / "m.csv", run_id="TEST",
                                                  max_candidates=10)
    assert seen, "the card engine was not called"
    assert seen[0]["rate"] == pytest.approx(0.0428)
    assert seen[0]["rate_basis"].startswith("MACRO:T3M")


def test_the_morning_reprice_uses_the_run_s_rate(tmp_path, monkeypatch):
    import morning_gate
    from test_m_g2_01_morning_reprice import ROW, _live
    monkeypatch.setattr(morning_gate, "_today_session", lambda: date(2026, 10, 9))
    morning_gate.set_morning_rate_inputs(_run_folder(tmp_path))
    try:
        out = morning_gate._recompute_for_morning_contract(ROW, _live())
    finally:
        morning_gate.set_morning_rate_inputs(None)
    assert out["valuation_rate_annual"] == pytest.approx(0.0428)
    assert out["valuation_rate_basis"].startswith("MACRO:T3M")
