"""WP1 characterisation: pin CURRENT select_best_contract behaviour before it is changed.

These tests document the defects measured in
Enhancements/expression_forensics/EXPRESSION_FORENSIC_AND_TDD_APPROACH_20260917.md (E1, E2).
They assert what the code does today, not what it should do. When WP1 changes the
behaviour, each test here is replaced by the business-rule test that supersedes it.

Superseded on 17 Sep 2026 by tests/test_wp1_expression_tradeability_rules.py:
- spread limit not a selection filter (E1)  -> T2 / T4
- one-sided quote selectable with a mark (E2) -> T1
- wide spread preferred over tight spread (E1) -> T4
Still current behaviour (kept, consistent with the execution-cost probe): volume and open interest
are ranking evidence, not gates.
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


def test_current_zero_volume_zero_open_interest_contract_is_selectable():
    """Volume / open interest are not hard gates (kept by design: once the spread is known they add little to cost)."""
    dead = _row("WPONE261016C00100000", 100.0, open_interest=0, volume=0)
    chosen = _select([dead])
    assert chosen is not None and chosen["open_interest"] == 0 and chosen["volume"] == 0
    assert chosen["oi_used_as_hard_gate"] is False and chosen["volume_used_as_hard_gate"] is False
