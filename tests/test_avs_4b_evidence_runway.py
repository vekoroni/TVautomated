"""Step 4b (ACK 3 Oct 2026, option B): the contract runway follows the evidence for daily events only.

Characterisation (replay, last 3 months): the 80% time to the level is a median 27 sessions for daily events but 135
(weekly) and 252 (monthly). ACK chose B: daily trade-side events with level evidence size the runway from q80;
weekly/monthly events and events without evidence keep the governed window (outcome.window_sessions), labelled;
the card's time fit states when the contract expires before q80. The median move time is published for any
timeframe (display). Runway stays a floor, never a ceiling.
"""
import pytest

from domain.anticipated_move import evidence_runway
from domain.option_contract_liquidity import calculate_dte_requirement

DAILY = dict(timeframe="1d", alignment="ALIGNED", status="IN_SAMPLE_REPLAY_NOT_VALIDATED", q50_bars=8, q80_bars=20, n=2067)


def test_daily_event_with_level_evidence_sizes_the_runway():
    r = evidence_runway(**DAILY)
    assert r["evidence_runway_sessions"] == 20 and r["evidence_move_sessions"] == 8
    assert r["evidence_runway_basis"] == "DURATION_EVIDENCE_Q80:1d:n=2067"


def test_weekly_and_monthly_events_size_the_runway_from_their_own_evidence():
    # Superseded 4 Oct 2026 (ACK: weekly/monthly are core; retire the fixed 20). Held-out timing by timeframe:
    # 1w 58.7% by q50 / 83.3% by q80, 1mo 64.9% / 87.5% (events arrive earlier than predicted: conservative).
    r = evidence_runway(**{**DAILY, "timeframe": "1w", "q50_bars": 27, "q80_bars": 66})
    assert r["evidence_runway_sessions"] == 330 and r["evidence_move_sessions"] == 135
    assert r["evidence_runway_basis"] == "DURATION_EVIDENCE_Q80:1w:n=2067"
    m = evidence_runway(**{**DAILY, "timeframe": "1mo", "q50_bars": 3, "q80_bars": 6})
    assert m["evidence_runway_sessions"] == 126 and m["evidence_runway_basis"] == "DURATION_EVIDENCE_Q80:1mo:n=2067"


def test_intraday_events_have_no_tested_runway_yet():
    r = evidence_runway(**{**DAILY, "timeframe": "15m", "q50_bars": 10, "q80_bars": 30})
    assert r["evidence_runway_sessions"] is None
    assert r["evidence_runway_basis"] == "NO_TESTED_EVIDENCE_TIMEFRAME:15m"


@pytest.mark.parametrize("change,basis", [({"alignment": "OPPOSING_ONLY"}, "GOVERNED_WINDOW_NO_TRADE_SIDE_EVENT"),
                                          ({"status": "INSUFFICIENT_SAMPLE"}, "GOVERNED_WINDOW_NO_LEVEL_EVIDENCE"),
                                          ({"q80_bars": None}, "GOVERNED_WINDOW_NO_LEVEL_EVIDENCE")])
def test_without_daily_level_evidence_the_window_is_used_and_labelled(change, basis):
    r = evidence_runway(**{**DAILY, **change})
    assert r["evidence_runway_sessions"] is None and r["evidence_runway_basis"] == basis


def test_dte_requirement_accepts_an_evidence_hold_but_still_guards_routed_holds():
    assert calculate_dte_requirement(27, evidence_hold=True)["minimum_required_dte"] > calculate_dte_requirement(20)["minimum_required_dte"]
    with pytest.raises(ValueError):
        calculate_dte_requirement(27)                       # an unrouted, unevidenced hold is still refused
    with pytest.raises(ValueError):
        calculate_dte_requirement(0, evidence_hold=True)


def test_runway_policy_uses_the_evidence_hold_and_labels_it():
    import scripts.avshunter_options_intelligence as oi
    ev = oi.contract_runway_policy("1_5d", evidence_hold=27, evidence_basis="DURATION_EVIDENCE_Q80:1d:n=2067")
    gov = oi.contract_runway_policy("1_5d")
    assert ev["contract_runway_hold_sessions"] == 27 and ev["contract_runway_basis"].startswith("DURATION_EVIDENCE_Q80")
    assert ev["contract_runway_floor_days"] > gov["contract_runway_floor_days"]
    assert gov["contract_runway_basis"].startswith("THESIS_WINDOW_D2")


def test_hold_patch_keeps_the_evidence_runway_and_labels_the_window(tmp_path, monkeypatch):
    import pandas as pd
    import intelligent_orchestrator as io
    run = "20261002_211641"
    hdir = tmp_path / run / "horizon"
    hdir.mkdir(parents=True)
    pd.DataFrame([{"ticker": t, "horizon_action": "GO", "horizon_size_multiplier": 1.0, "horizon_block_reason": "",
                   "horizon_source": "TEST", "router_version": "t"} for t in ("SOFI", "AMZN")]).to_csv(hdir / f"horizon_1_5d_{run}.csv", index=False)
    target = tmp_path / "oi.csv"
    pd.DataFrame([{"ticker": "SOFI", "horizon_bucket": "1_5d", "evidence_runway_sessions": 20, "evidence_move_sessions": 8,
                   "evidence_runway_basis": "DURATION_EVIDENCE_Q80:1d:n=2067"},
                  {"ticker": "AMZN", "horizon_bucket": "1_5d", "evidence_runway_sessions": None, "evidence_move_sessions": 135,
                   "evidence_runway_basis": "GOVERNED_WINDOW_NON_DAILY_EVENT:1w"}]).to_csv(target, index=False)
    monkeypatch.setattr(io.cfg, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(io, "_governed_thesis_window_sessions", lambda run_id: 20)
    assert io.patch_horizon_fields_into_csv(run, target, "test")
    out = pd.read_csv(target).set_index("ticker")
    assert out.loc["SOFI", "planned_hold_sessions"] == 20 and out.loc["SOFI", "planned_hold_source"] == "DURATION_EVIDENCE_Q80:1d:n=2067"
    assert out.loc["SOFI", "anticipated_move_sessions"] == 8 and out.loc["SOFI", "anticipated_move_source"] == "DURATION_EVIDENCE_Q50"
    # Superseded 4 Oct 2026 (ACK step 3, decision 2): no fixed window - a row without evidence carries no hold.
    assert pd.isna(out.loc["AMZN", "planned_hold_sessions"])
    assert out.loc["AMZN", "planned_hold_source"] == "NO_EVIDENCE_HOLD|GOVERNED_WINDOW_NON_DAILY_EVENT:1w"
    assert out.loc["AMZN", "anticipated_move_sessions"] == 135


def test_lifecycle_accepts_an_evidence_hold_when_flagged():
    from domain.option_contract_liquidity import LifecycleInputs, evaluate_options_liquidity_lifecycle
    base = dict(side="PUT", spot=15.92, strike=16.0, dte=55, remaining_hold_sessions=27, bid=1.49, ask=1.51,
                bid_size=10, ask_size=10, delta=-0.45, structural_target=15.21, invalidation_spot=19.5,
                forecast_vol_annual=0.5, thesis_spot=15.84, current_spot=15.92)
    out = evaluate_options_liquidity_lifecycle(LifecycleInputs(**base, hold_is_evidence=True))
    assert out["minimum_required_dte"] > 0
    with pytest.raises(ValueError):
        evaluate_options_liquidity_lifecycle(LifecycleInputs(**base))


def test_callers_flag_evidence_holds_from_the_hold_source():
    import inspect
    import morning_gate
    import scripts.avshunter_options_intelligence as oi
    from contracts import lab_control
    for module in (morning_gate, oi, lab_control):
        assert "hold_is_evidence" in inspect.getsource(module), module.__name__


def test_ev3_keeps_valuing_at_the_governed_window():
    """ACK 28 Sep 2026: EV3 values at the 20-session hold (+ move window); its barrier cache holds 5/10/20 only.
    A daily evidence runway (e.g. 27) must not become EV3's horizon."""
    from vanguard.ev3_stage0 import FIELD_ALIASES
    import scripts.run_ev3_shadow_phase as shadow
    assert FIELD_ALIASES["planned_hold_sessions"][0] == "ev3_planned_hold_sessions"
    assert shadow.COVERAGE_ALIASES["planned_hold_sessions"][0] == "ev3_planned_hold_sessions"


def test_hold_patch_writes_the_ev3_window(tmp_path, monkeypatch):
    test_hold_patch_keeps_the_evidence_runway_and_labels_the_window(tmp_path, monkeypatch)
    import pandas as pd
    out = pd.read_csv(tmp_path / "oi.csv").set_index("ticker")
    # Superseded 4 Oct 2026 (ACK decision 1a): EV3 values at the nearest grid point at or below the evidence hold.
    assert out.loc["SOFI", "ev3_planned_hold_sessions"] == 20 and out.loc["SOFI", "ev3_hold_basis"] == "EV3_GRID_20_OF_20"
    assert pd.isna(out.loc["AMZN", "ev3_planned_hold_sessions"]) and out.loc["AMZN", "ev3_hold_basis"] == "NO_EVIDENCE_HOLD"


def test_eod_candidates_carry_the_ev3_window_for_the_morning():
    import inspect
    import eod_candidate_engine
    assert '"ev3_planned_hold_sessions": _first_optional_flt(row, "ev3_planned_hold_sessions")' in inspect.getsource(eod_candidate_engine)
