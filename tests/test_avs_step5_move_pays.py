"""Step 5 (ACK 3 Oct 2026, D-B amended): "does the move pay" replaces stop-based R:R blocks.

Business rules:
- The monetisation policy's "Negative premium RR" FATAL block (option value at the retired structural/3R target
  below cost - 372 rows hard-blocked on 1 Oct) no longer blocks; it is an informational note.
- The anticipated move states whether it pays: PAYS when the contract is worth >= 1.0x the premium at the median
  anticipated time, DOES_NOT_PAY_AT_ANTICIPATED_TIME below 1.0x, NOT_COMPUTED otherwise (stated, not neutral).
- Morning: a row whose move does not pay is FLAGged (no GO), with the reason; it stays in the book.
  NOT_COMPUTED does not block on its own (the card says it was not computed).
- Exit rules carry no stop-based R:R label; they state whether the move pays.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from domain.anticipated_move import anticipated_move_fields


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _rules(policy_module, **row):
    base = {"ticker": "T", "direction": "CALL", "contract_mid": "1.50", "contract_bid": "1.45",
            "contract_ask": "1.55", "spread_pct": "0.03", "contract_dte": "40", "contract_premium": "150"}  # per contract, $
    base.update(row)
    out = policy_module.MonetisationPolicy().evaluate(policy_module.map_options_row_to_policy_input(base))
    return out, {e.rule_id: e for e in out.rule_events}


def test_negative_premium_rr_no_longer_blocks_in_either_policy_copy():
    for path, name in ((ROOT / "avshunter_monetisation_policy.py", "mp5_root"),
                       (ROOT / "scripts" / "avshunter_monetisation_policy.py", "mp5_scripts")):
        mod = _load(path, name)
        out, ev = _rules(mod, rr_options="-0.6")
        assert out.hard_block_reason != "Negative premium RR"
        assert ev["OPT_014"].passed is True and "retired" in ev["OPT_014"].note.lower()


CONTRACT = {"strike": 16.0, "ask": 1.51, "iv": 0.5245, "expiry": "2026-12-18", "as_of": "2026-10-02"}
DUR = {"test": "OUTCOME_FROM_DETECTION", "status": "IN_SAMPLE_REPLAY_NOT_VALIDATED", "n": 2067, "q50_bars": 8,
       "q80_bars": 20, "p_event": 0.38, "p_invalidation": 0.55}


def _am(**kw):
    base = dict(direction="PUT", spot=15.92, outcome_level=15.21, outcome_definition="MEASURED_MOVE", timeframe="1d",
                duration=DUR, vol_annual=0.53, contract=CONTRACT, governed_window_sessions=20)
    base.update(kw)
    return anticipated_move_fields(**base)


def test_pays_state_follows_the_value_multiple_at_the_median_time():
    pays = _am()
    assert pays["anticipated_value_multiple_q50"] >= 1.0 and pays["anticipated_pays_state"] == "PAYS"
    far_otm = _am(contract={**CONTRACT, "strike": 12.0, "ask": 0.30})
    assert far_otm["anticipated_value_multiple_q50"] < 1.0
    assert far_otm["anticipated_pays_state"] == "DOES_NOT_PAY_AT_ANTICIPATED_TIME"
    assert _am(contract=None)["anticipated_pays_state"] == "NOT_COMPUTED"


def test_morning_flags_a_move_that_does_not_pay_and_never_on_not_computed():
    from test_morning_gate_authority import _gate, _row
    out = _gate(_row(anticipated_pays_state="DOES_NOT_PAY_AT_ANTICIPATED_TIME", anticipated_value_multiple_q50=0.7))
    assert out["verdict"] == "FLAG" and out["morning_execution_permission"] == "MOVE_DOES_NOT_PAY"
    assert "0.7" in out["morning_unlock_condition"]
    assert _gate(_row(anticipated_pays_state="NOT_COMPUTED"))["verdict"] == "GO"
    assert _gate(_row(anticipated_pays_state="PAYS"))["verdict"] == "GO"


def test_exit_rules_carry_no_stop_based_rr():
    from scripts.exit_rules_engine import compute_exit_rules
    out = compute_exit_rules({"live_price": 15.92, "anticipated_level": 15.21, "invalidation_spot": 19.495,
                              "contract_theta": -0.0089, "contract_mid": 1.5, "contract_expiry": "2026-12-18",
                              "canonical_direction": "PUT", "anticipated_pays_state": "PAYS"})
    assert "RR_BELOW" not in out["exit_rule_summary"]
    assert out["exit_move_pays"] == "PAYS" and out["exit_rr_valid"] is None
