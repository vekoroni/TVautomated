"""Output-trust item 10, part 10.1 (C-1; ACK approved 9-10 Oct 2026): per-setup rates and calibration from the replay.

Design: Enhancements/phase7/ITEM10_CALIBRATION_AND_STATIONS_DESIGN_20261010.md. Today every rate the trader sees is a
pooled replay figure (lane B: one rate for three setup types), with no shrinkage, no calibration slope or intercept.

Business rules:
- The event is stated exactly: the setup's outcome level reached before its invalidation WITHIN THE PLANNED HOLD (the
  setup's own q80 time from the original panel - never peeking at the held-out panel). Censored or later = not reached.
- Per setup (timeframe x state x type x side): n, hits, rate and Wilson interval on both panels; lane B split by type.
- Shrinkage: beta-binomial toward the parent pool (timeframe x state); small setups borrow strength, large keep theirs.
- Calibration: the shrunk original-panel rate predicts, the held-out panel is reality: slope and intercept (binomial
  logistic fit on logit(predicted)), ECE and Brier - reported, not only "within +/-10".
"""
from __future__ import annotations

import math
import random

import pytest

from domain.setup_calibration import (build_setup_rates, calibration_summary, event_within_hold, shrink_to_parent,
                                      wilson)


def _records(tf, kind, n, p_hit, hold=10, seed=1, state="ACTIVATED", side="BULL", panel_offset=0):
    rng = random.Random(seed)
    out = []
    for i in range(n):
        u = rng.random()
        if u < p_hit:
            cause, t = "EVENT", rng.randint(1, hold + 4)            # some hits arrive after the hold
        elif u < p_hit + 0.3:
            cause, t = "INVALIDATION", rng.randint(1, 20)
        else:
            cause, t = "CENSORED", 20
        out.append({"timeframe": tf, "signal_type": kind, "direction": side, "cause": cause, "time_bars": t,
                    "test": "OUTCOME" if state == "ACTIVATED" else "OUTCOME_FROM_DETECTION",
                    "ticker": f"T{(i + panel_offset) % 50}", "cut": f"2024-01-{(i % 28) + 1:02d}"})
    return out


def test_the_event_counts_only_hits_within_the_planned_hold():
    recs = [{"cause": "EVENT", "time_bars": 5}, {"cause": "EVENT", "time_bars": 12}, {"cause": "INVALIDATION",
             "time_bars": 3}, {"cause": "CENSORED", "time_bars": 20}]
    assert [event_within_hold(r, hold_bars=10) for r in recs] == [True, False, False, False]


def test_wilson_and_shrinkage_behave():
    lo, hi = wilson(60, 100)
    assert lo < 0.6 < hi and 0.49 < lo < 0.51
    small = shrink_to_parent(hits=3, n=4, parent_rate=0.5, prior_strength=20)
    large = shrink_to_parent(hits=750, n=1000, parent_rate=0.5, prior_strength=20)
    assert abs(small - 0.5) < abs(0.75 - 0.5) and abs(large - 0.75) < 0.01


def test_setup_rates_use_the_original_panel_hold_and_split_lane_b_by_type():
    original = _records("1d", "SOS -> LPS continuation", 800, 0.7) + _records("1d", "Spring Candidate", 400, 0.5, seed=2) \
        + _records("1d", "Buyer Absorption Breakout", 30, 0.6, seed=3)
    holdout = _records("1d", "SOS -> LPS continuation", 800, 0.68, seed=4, panel_offset=7) \
        + _records("1d", "Spring Candidate", 400, 0.52, seed=5) + _records("1d", "Buyer Absorption Breakout", 30, 0.55, seed=6)
    table = build_setup_rates(original, holdout)
    by = {(s["timeframe"], s["signal_type"]): s for s in table["setups"]}
    sos = by[("1d", "SOS -> LPS continuation")]
    assert sos["hold_bars"] > 0 and sos["n_original"] == 800 and sos["n_holdout"] == 800
    assert sos["rate_original"] < 0.7                                    # hits after the hold no longer count
    assert sos["ci_original"][0] < sos["rate_original"] < sos["ci_original"][1]
    tiny = by[("1d", "Buyer Absorption Breakout")]
    parent = table["parents"]["1d|ACTIVATED|BULL"]["rate"]
    assert abs(tiny["rate_shrunk"] - parent) < abs(tiny["rate_original"] - parent)  # 30 records borrow strength
    assert table["event"].startswith("outcome level before invalidation within the planned hold")


def test_calibration_reports_slope_intercept_ece_and_brier():
    # perfectly calibrated predictions: slope ~1, intercept ~0
    rng = random.Random(9)
    groups = []
    for p in (0.2, 0.35, 0.5, 0.65, 0.8):
        n = 4000
        groups.append({"predicted": p, "n": n, "hits": sum(rng.random() < p for _ in range(n))})
    good = calibration_summary(groups)
    assert abs(good["slope"] - 1) < 0.1 and abs(good["intercept"]) < 0.1 and good["ece"] < 0.02
    # overconfident predictions (spread too wide): slope below 1
    over = calibration_summary([{"predicted": min(0.95, max(0.05, 0.5 + 1.8 * (g["predicted"] - 0.5))), "n": g["n"],
                                 "hits": g["hits"]} for g in groups])
    assert over["slope"] < 0.8 and over["brier"] > good["brier"]
    assert math.isfinite(over["intercept"])


def test_the_governing_setup_carries_its_within_hold_rate_for_display():
    import json
    import subprocess
    from pathlib import Path
    from domain.structure_behaviour.trade_lane import TRADE_LANE_FIELDS, setup_rate_fields
    cand = {"Timeframe": "1d", "Signal_Type": "SOS -> LPS continuation", "Signal_State": "ACTIVATED", "Direction": "BULL"}
    f = setup_rate_fields(cand)
    assert {"setup_rate_within_hold", "setup_rate_n", "setup_hold_bars", "setup_rate_shrunk",
            "setup_calibration_slope"} <= set(TRADE_LANE_FIELDS)
    assert 0.5 < f["setup_rate_within_hold"] < 0.65 and f["setup_rate_n"] == 1099 and f["setup_hold_bars"] == 30.0
    assert setup_rate_fields({**cand, "Signal_Type": "Unknown"})["setup_rate_within_hold"] is None
    card = (Path(__file__).resolve().parents[1] / "intelligence-lab" / "static" / "trade-card.js").read_text(encoding="utf-8")
    row = {"ticker": "SMCI", "direction": "CALL", "trade_lane": "A", "trade_lane_setup": "1d|SOS -> LPS continuation|ACTIVATED",
           "trade_lane_hit_original": 0.726, "trade_lane_hit_holdout": 0.678, **f}
    out = subprocess.run(["node"], input=card + f"\nconsole.log(JSON.stringify(renderTradeCard({json.dumps(row)})"
                         ".includes('within the planned hold (30 bars): 58% held out')));",
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.stdout.strip().splitlines()[-1] == "true", out.stderr
