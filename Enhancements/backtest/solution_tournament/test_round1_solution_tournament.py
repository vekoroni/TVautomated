from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pandas as pd


HERE = Path(__file__).resolve().parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


round1 = load("round1_solution_tournament", "round1_solution_tournament.py")
validation = load("round1_validation", "round1_validation.py")
round2 = load("round2_contract_family", "round2_contract_family.py")
round2_validation = load("round2_validation", "round2_validation.py")
round3 = load("round3_direction_holdout", "round3_direction_holdout.py")
round4 = load("round4_end_to_end_stress", "round4_end_to_end_stress.py")


def test_occ_strike_parser_is_exact():
    assert round1.parse_strike("AAPL260918C00150000") == 150.0
    assert round1.parse_strike("AAPL260918P00097500") == 97.5
    assert round1.parse_strike("not-an-occ-symbol") is None


def test_rank_top_selects_each_session_independently():
    frame = pd.DataFrame({
        "session": ["a", "a", "b", "b"],
        "score": [1.0, 2.0, 3.0, 1.0],
    })
    selected = round1.rank_top(frame, "score", n=1)
    assert selected["score"].tolist() == [2.0, 3.0]


def test_spread_drag_is_paired_and_positive_when_quotes_hurt():
    frame = pd.DataFrame({
        "session": ["a", "b"],
        "option_ask_to_bid": [-0.20, -0.10],
        "option_mid_to_mid": [-0.05, 0.05],
    })
    result = validation.paired_spread_drag(frame)
    assert result["n"] == 2
    assert result["mean"] == 0.15


def test_population_masks_do_not_certify_unknown_legacy_runs():
    frame = pd.DataFrame({"run_id": ["normal", "test", "legacy"]})
    manifest = {"run_truth": [
        {"run_id": "normal", "run_condition": "NORMAL_COMPLETED_SESSION", "dirty": False, "baseline_eligible": True},
        {"run_id": "test", "run_condition": "TEST", "dirty": True, "baseline_eligible": False},
        {"run_id": "legacy", "run_condition": None, "dirty": None, "baseline_eligible": None},
    ]}
    masks = validation.population_masks(frame, manifest)
    assert masks["all_h_pre_fix"].tolist() == [True, True, True]
    assert masks["exclude_explicit_test_or_dirty"].tolist() == [True, False, True]
    assert masks["certified_normal_completed_only"].tolist() == [True, False, False]


def test_round2_no_quote_contract_is_not_executable():
    chain = pd.DataFrame({
        "option_symbol": ["NOQUOTE", "VALID"],
        "side": ["call", "call"],
        "strike": [100.0, 100.0],
        "dte": [30, 30],
        "bid": [0.0, 1.0],
        "ask": [1.0, 1.1],
        "open_interest": [1000, 0],
        "volume": [1000, 0],
        "iv": [0.20, 0.20],
        "delta": [0.50, 0.50],
    })
    normalized = round2.normalize_chain(chain, spot=100.0, forecast_vol=0.25, hold=5)
    assert normalized["common_eligible"].tolist() == [False, True]
    selected = round2.choose(normalized, "F1_TIGHTEST_SPREAD", hold=5)
    assert selected is not None
    assert selected["option_symbol"] == "VALID"


def test_round2_low_open_interest_is_ranking_evidence_not_a_gate():
    chain = pd.DataFrame({
        "option_symbol": ["LOW_OI", "WIDE"],
        "side": ["put", "put"],
        "strike": [100.0, 100.0],
        "dte": [30, 30],
        "bid": [1.0, 1.0],
        "ask": [1.02, 1.20],
        "open_interest": [0, 10000],
        "volume": [0, 10000],
        "iv": [0.20, 0.20],
        "delta": [-0.45, -0.45],
    })
    normalized = round2.normalize_chain(chain, spot=100.0, forecast_vol=0.25, hold=5)
    assert normalized["common_eligible"].tolist() == [True, True]
    selected = round2.choose(normalized, "F1_TIGHTEST_SPREAD", hold=5)
    assert selected is not None
    assert selected["option_symbol"] == "LOW_OI"


def test_round2_ask_bid_and_mid_mid_are_separate():
    ask_bid, mid_mid = round2.outcome(1.0, 1.2, round2.Mark(1.1, 1.3))
    assert round(ask_bid, 6) == round(1.1 / 1.2 - 1.0, 6)
    assert round(mid_mid, 6) == round(1.2 / 1.1 - 1.0, 6)


def test_round2_empty_family_is_named_and_non_selectable():
    empty = pd.DataFrame(columns=[
        "option_symbol", "side", "strike", "dte", "bid", "ask",
        "open_interest", "volume", "iv", "delta",
    ])
    normalized = round2.normalize_chain(empty, spot=100.0, forecast_vol=0.25, hold=5)
    assert "common_eligible" in normalized
    assert normalized.empty
    assert round2.choose(normalized, "F1_TIGHTEST_SPREAD", hold=5) is None


def test_round2_paired_comparison_uses_common_marks_only():
    frame = pd.DataFrame([
        {"session": "a", "run_id": "r", "ticker": "X", "horizon": 1, "strategy": "F0_RECORDED", "ask_to_bid": -0.5},
        {"session": "a", "run_id": "r", "ticker": "X", "horizon": 1, "strategy": "ALT", "ask_to_bid": -0.2},
        {"session": "b", "run_id": "r", "ticker": "Y", "horizon": 1, "strategy": "F0_RECORDED", "ask_to_bid": -0.4},
        {"session": "b", "run_id": "r", "ticker": "Y", "horizon": 1, "strategy": "ALT", "ask_to_bid": None},
    ])
    result = round2_validation.paired(frame, "ALT", "ask_to_bid")
    assert result["pairs"] == 1
    assert result["improvement"]["mean"] == 0.3


def test_round3_deterministic_directions_are_explicit():
    frame = pd.DataFrame({
        "ret20": [0.1, -0.1],
        "ret5": [0.2, -0.2],
        "spy20": [-0.1, 0.1],
    })
    result = round3.deterministic_scores(frame)
    assert result["ALWAYS_CALL"].tolist() == [1.0, 1.0]
    assert result["MOMENTUM_20"].tolist() == [1.0, -1.0]
    assert result["MEAN_REVERSION_5"].tolist() == [-1.0, 1.0]
    assert result["SPY_REGIME"].tolist() == [-1.0, 1.0]


def test_round4_stable_dropout_draw_is_reproducible():
    first = round4.stable_fraction("candidate|scenario|1")
    second = round4.stable_fraction("candidate|scenario|1")
    assert first == second
    assert 0.0 <= first <= 1.0


def test_round4_spread_stress_cannot_improve_option_return():
    row = pd.Series({"entry_bid": 1.0, "entry_ask": 1.2, "exit_bid": 1.1, "exit_ask": 1.3})
    base = round4.stressed_option_return(row, 1.0)
    stress_25 = round4.stressed_option_return(row, 1.25)
    stress_50 = round4.stressed_option_return(row, 1.50)
    assert stress_50 <= stress_25 <= base


def test_round4_missing_quote_remains_missing_not_zero():
    row = pd.Series({"entry_bid": 1.0, "entry_ask": 1.2, "exit_bid": None, "exit_ask": None})
    assert round4.stressed_option_return(row, 1.5) is None


def test_round4_dynamic_choice_does_not_look_at_future_exit_quote():
    rows = []
    for index, ratio in enumerate((0.5, 1.0, 2.0)):
        rows.append({
            "candidate_id": f"c{index}", "session": "2026-01-02", "run_id": "r",
            "ticker": f"T{index}", "horizon": 1, "end_session": "2026-01-05",
            "direction_rule": "D0_CURRENT", "side": "CALL", "expression": "E1_CORE",
            "scenario": "D0_CURRENT|E1_CORE", "instrument": "OPTION", "symbol": f"O{index}",
            "entry_session": "2026-01-02", "entry_bid": 1.0, "entry_ask": 1.1,
            "entry_iv": ratio * 0.2, "forecast_vol": 0.2, "iv_over_forecast": ratio,
            "entry_spread": 0.1, "exit_bid": None, "exit_ask": None,
            "base_return": None, "mid_to_mid": None, "underlying_return": 0.05,
            "spy_bull": True, "spy_vol_high": False,
        })
    dynamic = round4.build_dynamic_rows(pd.DataFrame(rows)).set_index("candidate_id")
    assert dynamic.loc["c0", "instrument"] == "OPTION"
    assert pd.isna(dynamic.loc["c0", "base_return"])
