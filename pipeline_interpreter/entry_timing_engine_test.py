from entry_timing_engine import (
    compute_first_passage_probability,
    estimate_crowd_arrival_window,
    compute_kill_switch_breach_probability,
    build_pre_trade_probability_block,
)

result = compute_first_passage_probability(
    current_price=75.0, trigger_level=72.0, kill_switch_level=78.0,
    dte=7, garch_daily_vol=0.80, direction="PUT"
)
assert isinstance(result["p_trigger"], float)
assert 0.0 <= result["p_trigger"] <= 1.0
assert isinstance(result["p_kill_first"], float)
assert 0.0 <= result["p_kill_first"] <= 1.0
assert result["entry_edge_window"] in ("TODAY", "1-3D", "3-7D", "UNLIKELY_IN_WINDOW")
print("TEST 1 PASS:", result)

result = estimate_crowd_arrival_window(
    ivp=25.0, options_flow_zscore=0.2,
    days_since_phase_signal=2, volume_vs_20d_avg=0.9
)
assert result["crowd_stage"] == "PRE_CROWD"
assert result["freshness_score"] >= 75.0
print("TEST 2 PASS:", result)

result = compute_kill_switch_breach_probability(
    current_price=74.50, kill_switch_level=76.0,
    dte_remaining=5, garch_daily_vol=0.80, direction="PUT"
)
assert isinstance(result["p_breach_today"], float)
assert 0.0 <= result["p_breach_today"] <= 1.0
assert len(result["warning_tier"]) > 0
print("TEST 3 PASS:", result)

pipeline_row = {
    "ticker": "NEE", "direction": "PUT",
    "current_price": "83.50", "trigger_level": "81.00",
    "kill_switch_level": "86.00", "dte": "7",
    "ivp": "38.0", "volume_vs_20d_avg": "1.1"
}
garch_row = {"daily_vol": "0.75"}
result = build_pre_trade_probability_block("NEE", pipeline_row, garch_row, {}, 3)
assert "PRE_TRADE_PROBABILITY_NEE" in result
assert "crowd_stage" in result
print("TEST 4 PASS:")
print(result)

