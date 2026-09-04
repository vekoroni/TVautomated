from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from morning_gate import _capture_msi_market_observations


@dataclass
class _Result:
    payload: dict
    dataset_id: str
    resolution: str = "PROVIDER_FETCH"


class _Resolver:
    def __init__(self) -> None:
        self.exact = None
        self.underlying = None

    def exact_option_quote(self, **kwargs):
        self.exact = kwargs
        raw = kwargs["fetch"](kwargs["ticker"], kwargs["symbol"])
        assert raw["bidSize"] == [12]
        assert raw["askSize"] == [18]
        return _Result(
            payload={
                "bid_size": 12,
                "ask_size": 18,
                "bid_size_quality": "OBSERVED_POSITIVE",
                "ask_size_quality": "OBSERVED_POSITIVE",
                "quote_quality": "TWO_SIDED",
            },
            dataset_id="OPTION-DATASET",
        )

    def underlying_nbbo(self, **kwargs):
        self.underlying = kwargs
        raw = kwargs["fetch"](kwargs["ticker"])
        assert raw["bid"] == 99.9
        assert raw["ask"] == 100.1
        return _Result(
            payload={"mid": 100.0, "depth_level": "NBBO_ONLY"},
            dataset_id="NBBO-DATASET",
        )


def test_morning_capture_reuses_fetched_values_without_another_provider_client() -> None:
    resolver = _Resolver()
    row = {
        "ticker": "AAA",
        "thesis_id": "THESIS-1",
        "trade_idea_id": "IDEA-1",
        "selected_structure_id": "STRUCT-1",
        "contract_symbol": "AAA260918C00100000",
    }
    live = {
        "live_contract_symbol": "AAA260918C00100000",
        "live_contract_bid": 2.0,
        "live_contract_ask": 2.2,
        "live_contract_mid": 2.1,
        "live_contract_bid_size": 12,
        "live_contract_ask_size": 18,
        "live_options_fetched_at": "2026-08-30T12:00:00+00:00",
        "underlying_bid": 99.9,
        "underlying_ask": 100.1,
        "underlying_bid_size": 500,
        "underlying_ask_size": 600,
        "underlying_quote_updated": "2026-08-30T12:00:00+00:00",
    }

    _capture_msi_market_observations(row, live, resolver, date(2026, 8, 30))

    assert resolver.exact is not None
    assert resolver.underlying is not None
    assert live["msi_exact_quote_dataset_id"] == "OPTION-DATASET"
    assert live["msi_underlying_quote_dataset_id"] == "NBBO-DATASET"
    assert live["contract_bid_size_quality"] == "OBSERVED_POSITIVE"
    assert live["underlying_depth_level"] == "NBBO_ONLY"


def test_morning_capture_records_missing_nbbo_without_fabrication() -> None:
    resolver = _Resolver()
    row = {"ticker": "AAA"}
    live = {"live_price": 100.0}

    _capture_msi_market_observations(row, live, resolver, date(2026, 8, 30))

    assert resolver.exact is None
    assert resolver.underlying is None
    assert live["msi_underlying_quote_resolution"] == "PROVIDER_NBBO_NOT_AVAILABLE"
