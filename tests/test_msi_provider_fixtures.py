from __future__ import annotations

import json
from pathlib import Path

import pytest

from canonical_data.marketdata_response import parse_marketdata_option_response


FIXTURES = Path(__file__).parent / "fixtures" / "marketdata"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_recorded_provider_error_fails_closed() -> None:
    with pytest.raises(ValueError, match="status is not ok"):
        parse_marketdata_option_response(
            _fixture("option_quote_error.json"),
            ticker="AAPL",
        )


def test_recorded_missing_fields_are_explicitly_missing() -> None:
    frame = parse_marketdata_option_response(
        _fixture("option_quote_missing_fields.json"),
        ticker="AAPL",
    )
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["bid_size_quality"] == "MISSING"
    assert row["ask_size_quality"] == "MISSING"
    assert row["bid_size"] is None
    assert row["ask_size"] is None
