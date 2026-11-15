"""Two repairs found by the 14 Nov 2026 Evening run (ACK approved 15 Nov 2026).

Business rules:
- The opportunity book names every column once. A name listed twice writes two identical columns and leaves any
  reader to pick one arbitrarily (verifier rule R02_DUPLICATE_HEADERS).
- The ETFs the pipeline and the macro board actually trade have an identity in the instrument master: TQQQ, SQQQ,
  ARKF and ARKG were missing, and QQQ was left unresolved. A classification applies only from the day it was
  recorded: earlier sessions keep what was known then (no hindsight).
"""
from collections import Counter

import pytest

from canonical_data.instrument_identity import load_registry
from contracts.lab_control import FINAL_BOOK_FIELDS

RECORDED = "2026-11-15"
FROM_NEXT_SESSION = "2026-11-16"
BEFORE = "2026-11-13"


def test_the_book_names_every_column_once():
    repeated = sorted(name for name, count in Counter(FINAL_BOOK_FIELDS).items() if count > 1)
    assert repeated == []


def test_the_macro_alignment_columns_are_still_on_the_book():
    for name in ("usmi_sector_alignment", "usmi_alignment_priority", "usmi_alignment_reason", "usmi_authority",
                 "usmi_scenario", "usmi_packet_id", "usmi_state"):
        assert name in FINAL_BOOK_FIELDS, name


@pytest.fixture(scope="module")
def registry():
    return load_registry()


@pytest.mark.parametrize("ticker,kind,leveraged,inverse", [
    ("QQQ", "EQUITY_INDEX_ETF", None, None),
    ("ARKF", "THEMATIC_ETF", None, None),
    ("ARKG", "THEMATIC_ETF", None, None),
    ("TQQQ", "LEVERAGED_EQUITY_ETF", True, None),
    ("SQQQ", "LEVERAGED_INVERSE_ETF", True, True),
])
def test_the_traded_etfs_have_an_identity_from_the_day_it_was_recorded(registry, ticker, kind, leveraged, inverse):
    found = registry.fields(ticker, FROM_NEXT_SESSION)
    assert found["instrument_identity_state"] == "SOURCE_REPORTED", found["instrument_identity_reason"]
    assert (found["instrument_type"], found["instrument_wrapper"]) == (kind, "ETF")
    assert (found["instrument_leveraged"], found["instrument_inverse"]) == (leveraged, inverse)
    assert found["instrument_identity_asof"] == RECORDED


@pytest.mark.parametrize("ticker", ["TQQQ", "SQQQ"])
def test_leveraged_products_stay_research_only(registry, ticker):
    assert registry.fields(ticker, FROM_NEXT_SESSION)["instrument_review_policy"] == "RESEARCH_ONLY"


def test_an_earlier_session_keeps_what_was_known_then(registry):
    qqq = registry.fields("QQQ", BEFORE)
    assert (qqq["instrument_identity_state"], qqq["instrument_type"]) == ("REVIEW_REQUIRED", "ETF_OTHER")
    for ticker in ("TQQQ", "SQQQ", "ARKF", "ARKG"):
        assert registry.fields(ticker, BEFORE)["instrument_identity_state"] == "NO_ASOF_CLASSIFICATION"


def test_no_ticker_has_two_classifications_on_the_same_day(registry):
    for day in (BEFORE, RECORDED, FROM_NEXT_SESSION):
        for ticker in ("QQQ", "SPY", "TQQQ", "SQQQ", "ARKF", "ARKG"):
            assert registry.fields(ticker, day)["instrument_identity_state"] != "AMBIGUOUS_MASTER_ROWS", (ticker, day)
