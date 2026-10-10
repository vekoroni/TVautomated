"""L4 (ACK 7 Oct 2026, "4 = follow recommendation"): execution-gate GEX/wall warnings are display only.

D6 (19 Sep 2026) removed the size penalty from WARN_LOW_RUNWAY, WARN_ABOVE_GAMMA and WARN_TARGET_EXCEEDS_RUNWAY, but
the action rule still read "BUY_NOW only when there are no warnings at all", so any of these display-only GEX
warnings still turned BUY_NOW into BUY_SMALL - CLAUDE.md rule 6 (GEX/macro never gates). The runway check also used
the put wall for calls as well as puts, and the "above gamma flip" warning keyed off rcs_label, which the disabled
Phase 9B layer used to write - always empty.
Business rules:
- GEX/wall warnings are disclosed (gate_display_warnings) and never change final_action.
- Decision warnings (spread, IV, delta) still shape the action as before.
- A call's runway is measured to the call wall (resistance above); a put's to the put wall (support below).
- The gate thresholds live in config (execution_gate) at their current values.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from execution_gate import ExecutionGateConfig, execution_gate  # noqa: E402
from test_olm_execution_authority import _row  # noqa: E402  (a clean BUY_NOW row)


def test_a_clean_row_is_buy_now():
    assert execution_gate(_row(), require_olm=True)["final_action"] == "BUY_NOW"


def test_gex_warnings_are_disclosed_and_never_downgrade_buy_now():
    out = execution_gate(_row(call_wall=100.5, gamma_flip=95.0), require_olm=True)   # runway 0.5%, above flip
    assert out["final_action"] == "BUY_NOW"
    shown = out["gate_display_warnings"]
    assert "WARN_LOW_RUNWAY" in shown and "WARN_ABOVE_GAMMA" in shown
    assert "WARN_LOW_RUNWAY" not in out["gate_warnings"]


def test_a_decision_warning_still_shapes_the_action():
    wide = execution_gate(_row(live_contract_bid=4.50, live_contract_ask=5.00, live_contract_mid=4.75,
                               contract_bid=4.50, contract_ask=5.00, execution_viability_bid=4.50,
                               execution_viability_ask=5.00, execution_viability_spread_pct=0.105263),
                          require_olm=True)
    assert "WARN_WIDE_SPREAD" in wide["gate_warnings"] and wide["final_action"] != "BUY_NOW"


def test_a_call_runway_is_measured_to_the_call_wall():
    out = execution_gate(_row(call_wall=100.5, put_wall=50.0), require_olm=True)
    assert out["runway_source"] == "CALL_WALL" and out["runway_pct"] == pytest.approx(0.005, abs=1e-4)


def test_the_gate_thresholds_live_in_config():
    cfg = json.loads((ROOT / "config" / "governed_constants_v1.json").read_text(encoding="utf-8-sig"))["execution_gate"]
    assert cfg["authority_of_gex_warnings"] == "DISPLAY_ONLY"
    assert (ExecutionGateConfig.MIN_RUNWAY_PCT, ExecutionGateConfig.TARGET_GAIN_MULTIPLE) == \
        (cfg["min_runway_fraction"], cfg["target_gain_multiple"])
    assert (ExecutionGateConfig.DELTA_HARD_MIN, ExecutionGateConfig.DELTA_HARD_MAX) == \
        (cfg["delta_hard_min"], cfg["delta_hard_max"])
    assert (ExecutionGateConfig.IV_ELEVATED, ExecutionGateConfig.IV_EXTREME) == (cfg["iv_elevated"], cfg["iv_extreme"])
    assert (cfg["min_runway_fraction"], cfg["target_gain_multiple"], cfg["delta_hard_min"], cfg["delta_soft_min"],
            cfg["delta_soft_max"], cfg["delta_hard_max"], cfg["iv_elevated"], cfg["iv_extreme"]) == \
        (0.015, 2.0, 0.20, 0.30, 0.60, 0.85, 0.60, 1.00)          # today's values, unchanged
