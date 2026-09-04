from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from scripts import avshunter_options_intelligence as options


def _records() -> list[dict[str, object]]:
    return [
        {
            "underlying": "AAA",
            "symbol": "AAA260918C00100000",
            "right": "C",
            "strike": 100.0,
            "expiration_date": "2026-09-18",
            "dte": 19.0,
            "bid": 2.0,
            "ask": 2.2,
            "mid": 2.1,
            "bid_size": 12,
            "ask_size": 18,
            "bid_size_quality": "OBSERVED_POSITIVE",
            "ask_size_quality": "OBSERVED_POSITIVE",
            "spread_pct": 0.095238,
            "open_interest": 80,
            "volume": 4,
            "implied_vol": 0.3,
            "delta": 0.45,
            "gamma": 0.02,
            "theta": -0.03,
            "vega": 0.08,
            "underlying_price": 100.0,
            "contract_multiplier": 100,
            "quote_timestamp_utc": "2026-08-30T19:59:00Z",
            "quote_freshness": "EOD_CURRENT",
            "quote_quality": "TWO_SIDED",
        }
    ]


@dataclass
class _Result:
    payload: list[dict[str, object]]
    dataset_id: str = "DATASET-V2"
    provider: str = "MARKETDATA"
    resolution: str = "EXACT_HIT"


class _Resolver:
    def __init__(self) -> None:
        self.calls = []

    def option_chain(self, **kwargs):
        self.calls.append(kwargs)
        return _Result(_records())


def test_v2_frame_preserves_sizes_quotes_and_legacy_calculation_fields() -> None:
    frame = options._chain_v2_to_options_frame(_records())
    row = frame.iloc[0]
    assert row["symbol"] == "AAA260918C00100000"
    assert row["mark"] == 2.1
    assert row["bid_size"] == 12
    assert row["ask_size"] == 18
    assert bool(row["mark_synthetic"]) is False
    assert bool(row["quote_fields_complete"]) is True


def test_fetch_chain_routes_to_v2_resolver_when_enabled(monkeypatch) -> None:
    resolver = _Resolver()
    monkeypatch.setattr(options, "_CDS_V2_CHAIN_RESOLVER", resolver)
    monkeypatch.setattr(options, "_CDS_V2_SESSION", date(2026, 8, 30))
    monkeypatch.setattr(options, "_CDS_CHAIN_SERVICE", None)

    frame = options.fetch_chain("AAA")

    assert len(resolver.calls) == 1
    assert frame.attrs["canonical_dataset_id"] == "DATASET-V2"
    assert frame.attrs["canonical_schema_version"] == "option_chain_v2"
