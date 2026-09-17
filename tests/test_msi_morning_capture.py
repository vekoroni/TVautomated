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
        "live_contract_provider_updated": "2026-08-30T12:00:00+00:00",
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


# --- ACK 17 Sep 2026: provider timestamp from the hydrated structure -----------------------------------------------
# Since c1f651b quotes arrive through hydrate_selected_structure, which records the provider instant as
# selected_quote_timestamp_utc / live_contract_quote_timestamp, not live_contract_provider_updated. The capture must
# read the same timestamp chain as the rest of Morning Gate, or every quote is marked CONTRACT_QUOTE_UNAVAILABLE and
# the morning quote fields never reach the Lab book.

class _QuoteResolver:
    def __init__(self) -> None:
        self.exact = None

    def exact_option_quote(self, **kwargs):
        self.exact = kwargs
        raw = kwargs["fetch"](kwargs["ticker"], kwargs["symbol"])
        return _Result(
            payload={"bid": raw["bid"][0], "ask": raw["ask"][0], "mid": 2.1, "spread_fraction_mid": 0.095,
                     "quote_timestamp_utc": raw["updated"][0], "quote_quality": "TWO_SIDED"},
            dataset_id="OPTION-DATASET",
        )

    def underlying_nbbo(self, **kwargs):
        return _Result(payload={}, dataset_id="NBBO-DATASET")


def _hydrated_live(**timestamps) -> dict:
    live = {"live_contract_symbol": "AAA260918C00100000", "live_contract_bid": 2.0, "live_contract_ask": 2.2,
            "live_contract_mid": 2.1, "live_options_fetched_at": "2026-09-17T16:44:00+00:00"}
    live.update(timestamps)
    return live


def test_capture_uses_hydrated_provider_timestamp_and_keeps_morning_quote() -> None:
    resolver = _QuoteResolver()
    live = _hydrated_live(selected_quote_timestamp_utc="2026-09-17T16:29:20Z")
    _capture_msi_market_observations({"ticker": "AAA", "contract_symbol": "AAA260918C00100000"}, live, resolver,
                                     date(2026, 9, 17))
    assert resolver.exact is not None
    assert live["quote_provider_timestamp_utc"] == "2026-09-17T16:29:20Z"
    assert live["morning_contract_bid"] == 2.0 and live["morning_contract_ask"] == 2.2
    assert live["msi_exact_quote_dataset_id"] == "OPTION-DATASET"
    assert "execution_viability_state" not in live


def test_capture_accepts_live_contract_quote_timestamp() -> None:
    resolver = _QuoteResolver()
    live = _hydrated_live(live_contract_quote_timestamp="2026-09-17T16:29:20+00:00")
    _capture_msi_market_observations({"ticker": "AAA"}, live, resolver, date(2026, 9, 17))
    assert resolver.exact is not None and live["morning_contract_bid"] == 2.0


def test_capture_without_any_provider_timestamp_stays_unavailable() -> None:
    resolver = _QuoteResolver()
    live = _hydrated_live()
    _capture_msi_market_observations({"ticker": "AAA"}, live, resolver, date(2026, 9, 17))
    assert resolver.exact is None
    assert live["execution_viability_state"] == "CONTRACT_QUOTE_UNAVAILABLE"
    assert live["contract_quote_quality"] == "MISSING_PROVIDER_TIMESTAMP"
