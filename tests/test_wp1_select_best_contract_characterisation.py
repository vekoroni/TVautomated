"""WP1 characterisation: pin CURRENT select_best_contract behaviour before it is changed.

These tests document the defects measured in
Enhancements/expression_forensics/EXPRESSION_FORENSIC_AND_TDD_APPROACH_20260917.md (E1, E2).
They assert what the code does today, not what it should do. When WP1 changes the
behaviour, each test here is replaced by the business-rule test that supersedes it
(named in its docstring) — never silently deleted.
"""

from __future__ import annotations

from scripts import avshunter_options_intelligence as oi
import pandas as pd


def _ctx(**overrides) -> dict:
    ctx = {
        "ticker": "WPONE",
        "spot": 100.0,
        "entry": 100.0,
        "structural_target": 112.0,
        "stop": 95.0,
        "atr": 3.0,
        "hold_days": 10,
        "direction": "CALL",
        "preferred_strategy": "LONG_CALL",
        "dte_window": (21, 30, 45),
        "dte_config": {"delta_min": 0.40, "delta_max": 0.60, "spread_max": 0.10},
        "phase": "C",
        "win_prob": 55.0,
    }
    ctx.update(overrides)
    return ctx


def _row(symbol: str, strike: float, **overrides) -> dict:
    bid, ask = overrides.pop("bid", 2.00), overrides.pop("ask", 2.10)
    row = {
        "underlying": "WPONE", "symbol": symbol, "right": "C", "strike": strike,
        "expiration_date": "2026-10-16", "dte": 30.0, "bid": bid, "ask": ask,
        "mark": (bid + ask) / 2 if (bid is not None and ask is not None) else overrides.get("mark", 1.0),
        "spread_pct": (ask - bid) / ((ask + bid) / 2) if (bid is not None and ask) else None,
        "quote_quality": "TWO_SIDED", "quality_flags": [], "quote_fields_complete": True,
        "mark_synthetic": False, "open_interest": 1500, "volume": 300, "implied_vol": 0.45,
        "delta": 0.50, "gamma": 0.03, "theta": -0.05, "vega": 0.12,
        "bid_size": 10, "ask_size": 10, "bid_size_quality": "OBSERVED", "ask_size_quality": "OBSERVED",
        "quote_timestamp_utc": "2026-09-16T19:59:00Z", "quote_timestamp_source": "test",
        "contract_multiplier": 100, "contract_multiplier_source": "test", "md_quote_source": "test",
    }
    row.update(overrides)
    return row


def _select(rows, **ctx):
    return oi.select_best_contract(pd.DataFrame(rows), _ctx(**ctx))


def test_current_spread_limit_is_not_a_selection_filter():
    """E1. Superseded by: test_wp1_rules::test_contract_above_spread_limit_is_not_tradeable."""
    wide = _row("WPONE261016C00100000", 100.0, bid=1.00, ask=3.00, delta=0.50)       # 100% of mid
    chosen = _select([wide])
    assert chosen is not None and chosen["symbol"] == "WPONE261016C00100000"
    assert chosen["spread_pct"] > 0.10


def test_current_zero_volume_zero_open_interest_contract_is_selectable():
    """E1. Superseded by: test_wp1_rules::test_untraded_contract_carries_its_measured_execution_cost."""
    dead = _row("WPONE261016C00100000", 100.0, open_interest=0, volume=0)
    chosen = _select([dead])
    assert chosen is not None and chosen["open_interest"] == 0 and chosen["volume"] == 0
    assert chosen["oi_used_as_hard_gate"] is False and chosen["volume_used_as_hard_gate"] is False


def test_current_one_sided_quote_with_mark_is_selectable():
    """E2. Superseded by: test_wp1_rules::test_contract_without_two_sided_quote_is_not_priceable."""
    one_sided = _row("WPONE261016C00100000", 100.0, bid=None, ask=None, mark=1.50,
                     spread_pct=None, quote_quality="INCOMPLETE", quote_fields_complete=False)
    chosen = _select([one_sided])
    assert chosen is not None and chosen["ask"] is None
    assert chosen["selection_reason"] == "BEST_MONITORABLE_LONG_OPTION_CONTRACT"


def test_current_score_can_prefer_wide_spread_over_tight_spread():
    """E1. Superseded by: test_wp1_rules::test_ranking_uses_expected_net_value_after_execution_cost."""
    wide_on_target_delta = _row("WPONE261016C00100000", 100.0, bid=1.00, ask=2.40, delta=0.50,
                                open_interest=5000, volume=2000)
    tight_off_delta = _row("WPONE261016C00095000", 95.0, bid=4.95, ask=5.00, delta=0.70,
                           open_interest=5000, volume=2000)
    chosen = _select([wide_on_target_delta, tight_off_delta])
    assert chosen["symbol"] == "WPONE261016C00100000"
