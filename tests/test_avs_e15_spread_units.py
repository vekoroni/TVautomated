"""E15 (ACK 6 Oct 2026, option a, "remove 30%") and the two staleness decisions ("include both").

Business rules:
- Spread is (ask - bid) / mid. Its thresholds live in versioned config (spread_policy), with the unit stated, at the
  values in force today - no contract changes GO / FLAG / size because of this step.
- No reader guesses a unit from the size of the number. Run 20261006_060401 had 79 rows whose spread fraction is
  above 1 (a 140% spread is 1.4); two readers took any value <= 1 as a fraction and anything above as a percent, so
  a 140% spread read as 1.4% - very wide contracts looked tight.
- The EIL "spread <= 30.0" check is removed: it compared a fraction with a percent (always true on fractions) and only
  labelled a reason; the governed 25% reviewable limit is the policy.
- The trigger-age threshold (2 sessions) lives in config; the rule is kept.
- The dormant macro-age haircut (0.85 x macro scores, regime_consensus) is removed: macro is display only (rule 6).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "config" / "governed_constants_v1.json").read_text(encoding="utf-8-sig"))


def test_spread_thresholds_live_in_config_at_todays_values():
    p = CFG["spread_policy"]
    assert p["unit"] == "FRACTION_OF_MID"
    assert (p["executable_max"], p["reviewable_max"]) == (0.18, 0.25)
    assert p["execution_gate_full_size_max"] == 0.08 and p["research_pass_max"] == 0.15
    assert (p["tier_band_short_horizon"], p["tier_band_other"]) == (0.15, 0.25)
    assert (p["eod_repair_tight_max"], p["eod_repair_caution_max"]) == (0.15, 0.25)
    assert CFG["trigger_freshness"]["max_source_age_sessions"] == 2


def test_the_modules_read_their_thresholds_from_config():
    import execution_gate
    import trigger_layer
    from domain import long_option_execution as loe
    p = CFG["spread_policy"]
    assert loe.LONG_OPTION_EXECUTABLE_SPREAD_MAX_PCT == pytest.approx(p["executable_max"] * 100)
    assert loe.LONG_OPTION_REVIEWABLE_SPREAD_MAX_PCT == pytest.approx(p["reviewable_max"] * 100)
    assert execution_gate.ExecutionGateConfig.SPREAD_FULL == p["execution_gate_full_size_max"]
    assert trigger_layer.TRIGGER_MAX_AGE_SESSIONS == CFG["trigger_freshness"]["max_source_age_sessions"]
    src = (ROOT / "scripts" / "avshunter_options_intelligence.py").read_text(encoding="utf-8")
    assert "OPTIONS_SPREAD_PASS_PCT = 0.15" not in src and "OPTIONS_SPREAD_PASS_FRACTION" in src
    tier = (ROOT / "contracts" / "opportunity_tier.py").read_text(encoding="utf-8")
    assert "0.15 if horizon.startswith" not in tier


@pytest.mark.parametrize("row,expected", [({"contract_spread_pct": 1.4}, 140.0),
                                          ({"contract_spread_pct": 0.087}, 8.7),
                                          ({"eil_spread_pct_live": 12.0}, 12.0),
                                          ({}, 0.0)])
def test_the_eod_engine_reads_each_spread_field_in_its_own_unit(row, expected):
    from eod_candidate_engine import _spread_pct_from_row
    assert _spread_pct_from_row(row) == pytest.approx(expected)


def test_a_wide_spread_is_never_scored_as_tight():
    from eod_candidate_engine import _contract_repair_profile
    wide = _contract_repair_profile({"contract_spread_pct": 1.4, "contract_premium": 1.0}, {})
    assert "SPREAD_REPAIR_NEEDED" in wide["contract_repair_reason"]
    assert wide["contract_spread_pct_eod"] == pytest.approx(140.0)          # percent, as the name says


def test_the_probability_features_take_a_supplied_spread_as_a_fraction():
    from canonical_data.dynamic_options_probability import _spread_fraction
    assert _spread_fraction(None, None, 1.4) == pytest.approx(1.4)
    assert _spread_fraction(None, None, 0.2) == pytest.approx(0.2)
    assert _spread_fraction(1.0, 1.2, 99.0) == pytest.approx(0.2 / 1.1)


def test_the_eil_thirty_percent_check_is_gone():
    src = (ROOT / "execution_intelligence_runner.py").read_text(encoding="utf-8")
    assert "spread <= 30.0" not in src and '"SPREAD_REVIEW"' not in src


def test_the_macro_age_haircut_is_gone():
    src = (ROOT / "regime_consensus.py").read_text(encoding="utf-8")
    assert "* 0.85" not in src
