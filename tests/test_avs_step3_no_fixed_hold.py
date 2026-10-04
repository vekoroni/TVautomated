"""Step 3 (ACK 4 Oct 2026): retire the fixed 20-session hold.

"if we have this [the anticipated hold] why are we still relying on the 20 session hold dynamics."
Run 20261003_213716: the evidence q80 hold ranged 9 (p10) to 64 (p90) sessions, median 21; a fixed 20 overstates
decay for fast setups and values slow ones after expiry.
Business rules:
- The planned hold for valuation is the row's evidence runway (q80, tested timeframes 1d/1w/1mo); without
  evidence it is not estimable - never 20, never a default.
- Contract analytics, the empirical path EV and the decay hold use that hold.
- A missing theta drag is not computed and is left out of scores - never counted as 100% drag; the expected
  move never assumes a 5-day hold.
- EV3's barrier grid (5/10/20) is a separate decision (ACK).
"""
import inspect

import scripts.avshunter_options_intelligence as oi


def test_planned_hold_comes_from_the_evidence_runway():
    assert oi.planned_hold_from_evidence({"evidence_runway_sessions": 27}) == 27
    assert oi.planned_hold_from_evidence({"evidence_runway_sessions": None}) is None
    assert oi.planned_hold_from_evidence({}) is None


def test_valuation_never_uses_the_fixed_window():
    src = inspect.getsource(oi)
    assert "hold_sessions=governed_thesis_window_sessions(), iv_source" not in src          # contract analytics
    assert "thesis_window_sessions=governed_thesis_window_sessions())" not in src           # empirical path EV
    assert "governed_window=governed_thesis_window_sessions())" not in src                  # decay hold


def test_missing_theta_drag_is_never_worst_case():
    src = inspect.getsource(oi)
    assert "theta_pct    = _drag if _drag is not None else 100" not in src
    assert "theta_pct = 100 if theta_pct is None else theta_pct" not in src
    assert "econ.get('theta_drag_pct', 100)" not in src
    assert "theta_drain_pct = _drag / 100.0 if _drag is not None else 1.0" not in src


def test_expected_move_never_assumes_a_hold():
    assert '_oi_float(ctx.get("hold_days"), 5.0) or 5.0' not in inspect.getsource(oi._estimate_expected_move_pct)


# --- Decision 1 (ACK 4 Oct 2026, option a): EV3 values at the nearest grid point at or below the evidence hold.
def test_ev3_values_at_the_nearest_grid_point_at_or_below_the_evidence_hold():
    from vanguard.ev3_stage0 import grid_hold_for
    assert grid_hold_for(13) == (10, "EV3_GRID_10_OF_13")
    assert grid_hold_for(20) == (20, "EV3_GRID_20_OF_20")
    assert grid_hold_for(27) == (20, "EV3_GRID_CAP_20_OF_27")
    assert grid_hold_for(3) == (None, "BELOW_EV3_GRID_3")
    assert grid_hold_for(None) == (None, "NO_EVIDENCE_HOLD")


# --- Decision 2 (ACK 4 Oct 2026): rows without evidence carry no planned hold.
def _patch(tmp_path, monkeypatch):
    import pandas as pd
    import intelligent_orchestrator as io
    run = "20261002_211641"
    hdir = tmp_path / run / "horizon"
    hdir.mkdir(parents=True)
    pd.DataFrame([{"ticker": t, "horizon_action": "GO", "horizon_size_multiplier": 1.0, "horizon_block_reason": "",
                   "horizon_source": "TEST", "router_version": "t"} for t in ("SOFI", "AMZN", "FAST")]
                 ).to_csv(hdir / f"horizon_1_5d_{run}.csv", index=False)
    target = tmp_path / "oi.csv"
    pd.DataFrame([{"ticker": "SOFI", "horizon_bucket": "1_5d", "evidence_runway_sessions": 27, "evidence_move_sessions": 8,
                   "evidence_runway_basis": "DURATION_EVIDENCE_Q80:1d:n=2067"},
                  {"ticker": "FAST", "horizon_bucket": "1_5d", "evidence_runway_sessions": 13, "evidence_move_sessions": 5,
                   "evidence_runway_basis": "DURATION_EVIDENCE_Q80:1d:n=900"},
                  {"ticker": "AMZN", "horizon_bucket": "1_5d", "evidence_runway_sessions": None,
                   "evidence_move_sessions": None, "evidence_runway_basis": "GOVERNED_WINDOW_NO_LEVEL_EVIDENCE"}]
                 ).to_csv(target, index=False)
    monkeypatch.setattr(io.cfg, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(io, "_governed_thesis_window_sessions", lambda run_id: 20)
    assert io.patch_horizon_fields_into_csv(run, target, "test")
    return pd.read_csv(target).set_index("ticker")


def test_rows_without_evidence_carry_no_planned_hold(tmp_path, monkeypatch):
    out = _patch(tmp_path, monkeypatch)
    assert out.loc["SOFI", "planned_hold_sessions"] == 27
    assert str(out.loc["AMZN", "planned_hold_sessions"]) == "nan"
    assert out.loc["AMZN", "planned_hold_source"] == "NO_EVIDENCE_HOLD|GOVERNED_WINDOW_NO_LEVEL_EVIDENCE"


def test_hold_patch_writes_the_ev3_grid_hold_and_its_basis(tmp_path, monkeypatch):
    out = _patch(tmp_path, monkeypatch)
    assert out.loc["SOFI", "ev3_planned_hold_sessions"] == 20 and out.loc["SOFI", "ev3_hold_basis"] == "EV3_GRID_CAP_20_OF_27"
    assert out.loc["FAST", "ev3_planned_hold_sessions"] == 10 and out.loc["FAST", "ev3_hold_basis"] == "EV3_GRID_10_OF_13"
    assert str(out.loc["AMZN", "ev3_planned_hold_sessions"]) == "nan" and out.loc["AMZN", "ev3_hold_basis"] == "NO_EVIDENCE_HOLD"


def test_morning_ev3_hold_never_falls_back_to_the_horizon_bucket():
    import inspect
    import morning_gate
    src = inspect.getsource(morning_gate)
    assert 'hold_source = "ROUTED_HORIZON_UPPER_BOUND"' not in src
    assert 'row.get("ev3_planned_hold_sessions")' in src


def test_lab_runway_check_uses_the_selection_floor_when_there_is_no_evidence_hold():
    import inspect
    from contracts import lab_control
    src = inspect.getsource(lab_control)
    assert "SELECTION_FLOOR_NO_EVIDENCE_HOLD" in src
