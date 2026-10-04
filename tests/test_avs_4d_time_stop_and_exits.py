"""Step 4d (ACK 3 Oct 2026): the time stop and exit rules use the selected contract and the evidence.

Defects: the time stop was computed from the input row before contract selection (ts_dte_used 30/45, an expiry
invented as today + DTE; 140 of 144 GO rows had a ts expiry different from the contract's), its rule text quoted the
old structural (3R) target, and the exit-rules theta date ran past expiry (SOFI 19 Dec vs an 18 Dec expiry).
Business rules:
- Time stop: the selected contract's real expiry. Daily evidence rows: checkpoint at q50, stop at q80, never later
  than expiry minus the exit buffer. Other rows: the governed fractions of the real contract life, labelled.
- The rule text names the anticipated level, never the 3R target.
- Exit rules: DTE from the contract's expiry; the theta exit date is never after expiry; the exit target is the
  anticipated level; the invalidation is the thesis exit.
"""
from datetime import date

import scripts.avshunter_options_intelligence as oi
from scripts.exit_rules_engine import compute_exit_rules

ROW = {"asof_date": "2026-10-02", "structural_target": 4.875, "stock_price": 15.92}
CONTRACT = {"expiry": "2026-12-18", "strike": 16.0, "dte": 77}


def test_time_stop_uses_the_contract_expiry_and_the_evidence():
    ts = oi.compute_time_stop_oi(ROW, contract=CONTRACT, evidence_move_sessions=8, evidence_runway_sessions=20,
                                 anticipated_level=15.21)
    assert ts["expiry_date"] == "2026-12-18"
    assert ts["time_stop_basis"] == "DURATION_EVIDENCE_Q50_Q80"
    assert ts["checkpoint_date"] < ts["time_stop_date"] < "2026-12-18"
    assert "15.21" in ts["checkpoint_rule"] and "4.88" not in ts["checkpoint_rule"]


def test_without_evidence_the_governed_fraction_of_the_real_contract_life_is_used():
    ts = oi.compute_time_stop_oi(ROW, contract=CONTRACT, evidence_move_sessions=None, evidence_runway_sessions=None,
                                 anticipated_level=None)
    assert ts["time_stop_basis"] == "GOVERNED_FRACTION_OF_CONTRACT_LIFE"
    assert ts["expiry_date"] == "2026-12-18" and ts["dte_used"] == 77
    assert "4.88" not in ts["checkpoint_rule"]


def test_exit_theta_date_never_passes_expiry_and_target_is_the_anticipated_level():
    out = compute_exit_rules({"live_price": 15.92, "anticipated_level": 15.21, "structural_target": 4.875,
                              "invalidation_spot": 19.495, "contract_theta": -0.0005, "contract_mid": 1.5,
                              "dte": 78, "contract_expiry": "2026-12-18", "canonical_direction": "PUT"})
    assert out["exit_target_price"] == 15.21
    assert out["exit_theta_date"] <= "2026-12-18"
    assert out["exit_stop_price"] == 19.495


def _plan(**kw):
    from eod_candidate_engine import anticipated_exit_plan
    base = dict(direction="PUT", entry=15.92, anticipated_level=14.2, structural_level=None, invalidation=19.495,
                call_wall=20.0, put_wall=15.0, wbs_grade="UNLIKELY")
    base.update(kw)
    return anticipated_exit_plan(**base)


def test_exit_plan_targets_the_anticipated_level_with_a_trade_side_wall_first():
    p = _plan()
    assert (p["exit_t1"], p["exit_t2"], p["exit_t3"]) == (15.0, 14.2, 0.0)      # put wall below, on the path
    assert p["exit_invalidation_price"] == 19.495
    assert "ANTICIPATED_LEVEL" in p["exit_plan_reason"]


def test_wrong_side_or_off_path_walls_are_ignored():
    p = _plan(direction="CALL", entry=100.0, anticipated_level=108.0, call_wall=120.0, put_wall=95.0)
    assert (p["exit_t1"], p["exit_t2"]) == (108.0, 108.0)                   # put wall is below a call; call wall beyond T2


def test_t3_is_the_structural_level_only_beyond_a_capped_anticipated_level():
    assert _plan(anticipated_level=14.2, structural_level=12.0)["exit_t3"] == 12.0
    assert _plan(anticipated_level=14.2, structural_level=14.5)["exit_t3"] == 0.0


def test_no_anticipated_level_invents_no_target():
    p = _plan(anticipated_level=None)
    assert (p["exit_t1"], p["exit_t2"], p["exit_t3"]) == (0.0, 0.0, 0.0)
    assert "NO_ANTICIPATED_LEVEL" in p["exit_plan_reason"]
