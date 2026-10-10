"""Contract runway without the setup's own evidence (ACK 7 Oct 2026: "build C with B fallback").

Contract selection gave rows without a duration-evidence hold the governed 20-session thesis window as their runway
floor (40 calendar days) - a fixed number. 667 of 1,636 rows on run 20261006 had no evidence hold.
Business rules (runway is a floor, never a ceiling):
- Own evidence first (unchanged): the governing setup's q80 time to its level.
- C, pooled evidence: the longest q80 among the setup's broader evidence group - same timeframe, setup type,
  direction and test, across every scope and age bucket (conservative; groups hold quantiles, not samples).
- B, volatility fallback: the sessions a k-sigma move needs to reach the setup's level at current volatility,
  t = 252 x (|level / spot - 1| / (k x vol))^2 - forward-looking, not evidence; labelled.
- Neither (no level): no hold-based floor; only "holdable past issue"; stated NO_RUNWAY_ESTIMATE - never the fixed 20.
- The EOD lifecycle uses the same hold as contract selection.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.anticipated_move import runway_fallback  # noqa: E402
from domain.structure_behaviour.duration import pooled_level_q80  # noqa: E402


def _g(scope, age, q80, n=200, status="IN_SAMPLE_REPLAY_NOT_VALIDATED", direction="BEAR", tf="1w",
       kind="SOW -> LPSY continuation", test="OUTCOME"):
    return {"timeframe": tf, "scope": scope, "signal_type": kind, "direction": direction, "test": test,
            "age_bucket": age, "n": n, "status": status, "remaining_bars_q50": 1, "remaining_bars_q80": q80}


EVIDENCE = {"groups": [_g("CAMPAIGN", "ALL", 3), _g("LOCAL", "0-2", 5), _g("LOCAL", "ALL", 4),
                       _g("CAMPAIGN", "3-5", 9, status="INSUFFICIENT_SAMPLE"),        # not evidence
                       _g("CAMPAIGN", "ALL", 30, direction="BULL")]}                    # other direction


def test_pooled_evidence_takes_the_longest_sufficient_q80_of_the_broader_group():
    q80, basis, n = pooled_level_q80(EVIDENCE, timeframe="1w", signal_type="SOW -> LPSY continuation",
                                     direction="BEAR", test="OUTCOME")
    assert q80 == 5 and basis.startswith("POOLED_EVIDENCE_MAX_Q80") and n == 200
    assert pooled_level_q80(EVIDENCE, timeframe="1d", signal_type="SOW -> LPSY continuation",
                            direction="BEAR", test="OUTCOME") == (None, "NO_POOLED_EVIDENCE", None)


def test_c_pooled_evidence_sizes_the_runway_in_sessions():
    out = runway_fallback(evidence=EVIDENCE, timeframe="1w", signal_type="SOW -> LPSY continuation",
                          direction="PUT", state="ACTIVATED", outcome_level=85.0, spot=100.0, vol_annual=0.30)
    assert out["runway_sessions"] == 25 and out["runway_basis"].startswith("POOLED_EVIDENCE_MAX_Q80")   # 5 bars x 5
    assert out["runway_is_evidence"] is True


CFG = json.loads((ROOT / "config" / "governed_constants_v1.json").read_text(encoding="utf-8-sig"))


def test_b_is_the_volatility_time_to_level_calibrated_to_a_q80_runway():
    """Calibrated B (ACK 7 Oct 2026): uncalibrated B covered 30% of real level hits; x the evidence multiplier it
    covers 83-86% on the held-out panel (config runway_volatility_calibration)."""
    k = CFG["contract_economics"]["sigma_multiple"]
    mult = CFG["runway_volatility_calibration"]["q80_multiplier"]["1d"]
    out = runway_fallback(evidence={"groups": []}, timeframe="1d", signal_type="Spring Candidate", direction="CALL",
                          state="DETECTED", outcome_level=110.0, spot=100.0, vol_annual=0.30)
    base = max(1, math.ceil(252 * (0.10 / (k * 0.30)) ** 2))
    assert out["runway_sessions"] == math.ceil(base * mult)
    assert out["runway_basis"].startswith("VOLATILITY_TIME_TO_LEVEL_CALIBRATED_Q80") and out["runway_is_evidence"] is False


def test_an_uncalibrated_timeframe_gets_no_volatility_runway():
    out = runway_fallback(evidence={"groups": []}, timeframe="60m", signal_type="X", direction="CALL",
                          state="DETECTED", outcome_level=110.0, spot=100.0, vol_annual=0.30)
    assert out["runway_sessions"] is None and out["runway_basis"] == "NO_RUNWAY_ESTIMATE"


def test_the_calibration_is_evidenced_and_inside_the_runway_band():
    cal = CFG["runway_volatility_calibration"]
    for tf in ("1d", "1w", "1mo"):
        assert cal["q80_multiplier"][tf] > 1.0
        assert 0.70 <= cal["evidence"]["holdout_coverage"][tf] <= 0.90


def test_neither_means_no_runway_estimate_never_the_fixed_window():
    out = runway_fallback(evidence={"groups": []}, timeframe="1d", signal_type="Hinge", direction="CALL",
                          state="DETECTED", outcome_level=None, spot=100.0, vol_annual=0.30)
    assert out == {"runway_sessions": None, "runway_basis": "NO_RUNWAY_ESTIMATE", "runway_is_evidence": False}
    wrong_side = runway_fallback(evidence={"groups": []}, timeframe="1d", signal_type="X", direction="CALL",
                                 state="DETECTED", outcome_level=95.0, spot=100.0, vol_annual=0.30)
    assert wrong_side["runway_sessions"] is None


@pytest.fixture(scope="module")
def oi():
    spec = importlib.util.spec_from_file_location("oi_runway", ROOT / "scripts" / "avshunter_options_intelligence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_contract_floor_uses_the_fallback_and_never_the_fixed_window(oi):
    pooled = oi.contract_runway_policy(None, evidence_hold=25, evidence_basis="POOLED_EVIDENCE_MAX_Q80:x")
    assert pooled["contract_runway_hold_sessions"] == 25 and pooled["contract_runway_basis"].startswith("POOLED")
    vol = oi.contract_runway_policy(None, evidence_hold=12, evidence_basis="VOLATILITY_TIME_TO_LEVEL:x",
                                    hold_is_evidence=False)
    assert vol["contract_runway_hold_sessions"] == 12
    none = oi.contract_runway_policy(None, evidence_hold=None, evidence_basis="NO_RUNWAY_ESTIMATE")
    assert none["contract_runway_hold_sessions"] is None and none["contract_runway_basis"] == "NO_RUNWAY_ESTIMATE"
    assert none["contract_runway_floor_days"] == none["contract_min_holdable_dte"]       # holdable past issue only
    src = (ROOT / "scripts" / "avshunter_options_intelligence.py").read_text(encoding="utf-8")
    body = src[src.index("def contract_runway_policy"):src.index("def _runway_from_ctx")]
    assert "governed_thesis_window_sessions()" not in body


def test_the_eod_lifecycle_uses_the_selection_hold(oi):
    src = (ROOT / "scripts" / "avshunter_options_intelligence.py").read_text(encoding="utf-8")
    assert '"remaining_hold_sessions": _repair_alt_float(ctx.get("contract_runway_hold_sessions"))' in src
