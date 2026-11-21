"""VOL-03: the 30-day IV benchmark is a fact about the ticker's chain, not about the contract.

Business rule (ACK-approved build, 21 Nov 2026; Codex brief BF-01 / VOL-03):

  Whenever a governed option chain was read for a ticker, the 30-calendar-day ATM implied
  volatility is published for that ticker, whether or not a contract was selected and whether
  or not the ticker has one governed side. When it cannot be estimated the row says why.
  A missing benchmark is never a blank: missing is never neutral.

  The estimate itself does not change in this slice: same strike band (spot +/-5%), same expiry
  window (3 to 90 days), same IV range (0.03 to 3.0), same total-variance interpolation to 30 days.

Legacy behaviour replaced: the benchmark was computed only on the main output path. The
direction-alternative return, the no-contract return and every failure returned nothing, and all
failure reasons collapsed to an empty result (1,075 of 2,746 rows on the 19 Nov run had none;
956 of those had a registered chain).

Isolated: in-memory chains only; the chain fetch is replaced; no provider, no network.
"""
from __future__ import annotations

import inspect
import sys
from datetime import date
from math import sqrt
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import avshunter_options_intelligence as oi  # noqa: E402

SESSION = date(2026, 11, 19)
SPOT = 100.0
VALUE_FIELDS = ("atm_iv_30d", "atm_iv_30d_unit", "atm_iv_30d_as_of", "atm_iv_30d_source")


def _chain(rows, *, lineage=True) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["expiry", "strike", "implied_vol"])
    if lineage:
        frame.attrs["canonical_dataset_id"] = "ds-1"
        frame.attrs["canonical_provider"] = "MARKETDATA"
    return frame


def _bracketing_chain() -> pd.DataFrame:
    # 21 and 49 days out, at-the-money strike 100, IV 0.30 and 0.40
    return _chain([("2026-12-10", 100.0, 0.30), ("2027-01-07", 100.0, 0.40),
                   ("2026-12-10", 120.0, 0.90)])


def test_the_estimate_is_unchanged_and_now_says_it_is_ok():
    result = oi._layer3_atm_iv_fields(_bracketing_chain(), SPOT, SESSION)

    expected = sqrt((0.30 ** 2 * 21 + (0.40 ** 2 * 49 - 0.30 ** 2 * 21) * (30 - 21) / (49 - 21)) / 30)
    assert result["atm_iv_30d"] == pytest.approx(expected)
    assert result["atm_iv_30d_unit"] == "ANNUALISED_FRACTION"
    assert result["atm_iv_30d_as_of"] == "2026-11-19"
    assert result["atm_iv_30d_source"] == "MARKETDATA:ds-1"
    assert result["atm_iv_30d_state"] == "OK" and result["atm_iv_30d_reason"] == ""


@pytest.mark.parametrize("chain, spot, session, state", [
    (_chain([]), SPOT, SESSION, "NO_CHAIN"),
    (_chain([("2026-12-10", 100.0, 0.30)], lineage=False), SPOT, SESSION, "MISSING_LINEAGE"),
    (_bracketing_chain(), 0.0, SESSION, "SPOT_UNAVAILABLE"),
    (_bracketing_chain(), SPOT, None, "SESSION_UNAVAILABLE"),
    (_chain([("2026-12-10", 150.0, 0.30), ("2027-01-07", 150.0, 0.40)]), SPOT, SESSION, "NO_ATM_QUOTES"),
    (_chain([("2026-12-10", 100.0, 4.5), ("2027-01-07", 100.0, 0.01)]), SPOT, SESSION, "IV_OUT_OF_RANGE"),
    (_chain([("2026-12-03", 100.0, 0.30), ("2026-12-10", 100.0, 0.31)]), SPOT, SESSION, "NO_TENOR_BRACKET"),
])
def test_every_failure_has_its_own_reason_and_no_invented_value(chain, spot, session, state):
    result = oi._layer3_atm_iv_fields(chain, spot, session)

    assert result["atm_iv_30d_state"] == state
    assert result["atm_iv_30d_reason"]
    assert not any(field in result for field in VALUE_FIELDS)


def test_missing_columns_are_named():
    chain = _chain([("2026-12-10", 100.0, 0.30)]).drop(columns=["implied_vol"])
    chain.attrs.update(canonical_dataset_id="ds-1", canonical_provider="MARKETDATA")

    result = oi._layer3_atm_iv_fields(chain, SPOT, SESSION)

    assert result["atm_iv_30d_state"] == "MISSING_COLUMNS" and "implied_vol" in result["atm_iv_30d_reason"]


@pytest.fixture
def undirected(monkeypatch):
    """A ticker with no single governed side: the path that returns before contract selection."""
    monkeypatch.setattr(oi, "parse_structural_context",
                        lambda _row: {"ticker": "CNR", "spot": SPOT, "direction": "UNRESOLVED"})
    monkeypatch.setattr(oi, "_stand_down", lambda _ctx, reason: {"stand_down_reason": reason})
    monkeypatch.setattr(oi, "_CDS_V2_SESSION", SESSION)
    return monkeypatch


def test_a_ticker_with_priceable_alternatives_but_no_single_side_keeps_its_benchmark(undirected):
    undirected.setattr(oi, "_thesis_alternatives_priceable", lambda _row: True)
    undirected.setattr(oi, "fetch_chain", lambda _ticker: _bracketing_chain())

    row = oi.process_ticker(pd.Series({"ticker": "CNR"}))

    assert row["atm_iv_30d_state"] == "OK" and row["atm_iv_30d"] > 0
    assert row["atm_iv_30d_source"] == "MARKETDATA:ds-1"


def test_a_suppressed_chain_request_says_so_and_makes_no_extra_call(undirected):
    undirected.setattr(oi, "_thesis_alternatives_priceable", lambda _row: False)
    undirected.setattr(oi, "fetch_chain", lambda _ticker: pytest.fail("no chain call when the request is suppressed"))

    row = oi.process_ticker(pd.Series({"ticker": "CNR"}))

    assert row["atm_iv_30d_state"] == "CHAIN_REQUEST_SUPPRESSED"
    assert "atm_iv_30d" not in row


def test_a_failed_chain_fetch_is_no_chain_with_the_reason(undirected):
    undirected.setattr(oi, "_thesis_alternatives_priceable", lambda _row: True)

    def broken(_ticker):
        raise RuntimeError("MarketData chain unavailable")

    undirected.setattr(oi, "fetch_chain", broken)

    row = oi.process_ticker(pd.Series({"ticker": "CNR"}))

    assert row["atm_iv_30d_state"] == "NO_CHAIN"
    assert "MarketData chain unavailable" in row["atm_iv_30d_reason"]


def test_every_return_of_the_per_ticker_function_carries_the_assessment():
    """The directed paths need a full chain pipeline to run, so their wiring is read from source."""
    source = inspect.getsource(oi.process_ticker)

    # main output, no-contract return, direction-alternative return, empty-chain return
    assert source.count("_layer3_atm_iv_fields(") >= 4
    # the directed chain-fetch failure
    assert source.count("_layer3_iv_unavailable(") >= 3


def test_the_state_and_reason_reach_the_published_file():
    source = inspect.getsource(oi.run_options_layer)

    assert "'atm_iv_30d_state'" in source and "'atm_iv_30d_reason'" in source
