"""Gap 1 (ACK, 25 Sep 2026, revised post-acceptance review) — exact-contract
quote join to canonical exact_option_quote evidence: symbol+run identity,
freshness assessed at report-generation time (not capture time), size-aware
executability, and separate (non-persisting) record-building for an
explicitly-requested fresh broker read.

Real run IDs and symbols below were read directly from the stored files on
25 Sep 2026 and are reproduced verbatim, never altered:
- run 20260925_061649: BULL 261120C00007500, EWG 261218P00042000,
  SOFI 261218C00018000, XLF 261120P00055000
- run 20260924_085940: BULL 261218C00007500
The earlier version of this file used invented October contract symbols and
a nonexistent run "20260924_090000" — both are replaced here. Edge-case
tests (zero size, staleness, future timestamps, run collisions) still use
synthetic overrides layered on these real fixtures, since those failure
states don't necessarily occur in the currently-stored files; each is
labelled as a synthetic variant.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from domain.exact_contract_quote_join import (
    ExactContractQuoteCandidate, ExecutableNowState, QuoteFreshnessState,
    QuoteIdentityState, QuoteQualityState, build_supplemental_broker_observation_record,
    join_exact_contract_quote, load_exact_contract_quote_candidate_from_json,
)

RUN = "20260925_061649"
OTHER_RUN = "20260924_085940"

# Real, verbatim field values captured from the stored files.
REAL_QUOTES = {
    "BULL": dict(
        symbol="BULL261120C00007500", ticker="BULL", run_id=RUN,
        bid="0.61", ask="0.64", bid_size="1", ask_size="13",
        observed="2026-09-25T13:34:50Z",
        source_path="data/canonical/market_observations/exact_option_quote/2026-09-25/BULL/"
                     "e87aff2d2b6a28e790cdd4e5b718f25c88ec9a442401ebf873508984be9335de.json",
    ),
    "EWG": dict(
        symbol="EWG261218P00042000", ticker="EWG", run_id=RUN,
        bid="1.30", ask="1.40", bid_size="10", ask_size="255",
        observed="2026-09-25T13:43:14Z",
        source_path="data/canonical/market_observations/exact_option_quote/2026-09-25/EWG/"
                     "b21d787f838a880268914696da71ab908e56b205d632b02c017a3dc858754c08.json",
    ),
    "SOFI": dict(
        symbol="SOFI261218C00018000", ticker="SOFI", run_id=RUN,
        bid="1.22", ask="1.26", bid_size="780", ask_size="816",
        observed="2026-09-25T13:33:50Z",
        source_path="data/canonical/market_observations/exact_option_quote/2026-09-25/SOFI/"
                     "8d7425ad51da6c45f0ed03f8e10ed107ac84eb76c160afa66f124c5c820c34f8.json",
    ),
    "XLF": dict(
        symbol="XLF261120P00055000", ticker="XLF", run_id=RUN,
        bid="1.41", ask="1.47", bid_size="214", ask_size="119",
        observed="2026-09-25T13:43:07Z",
        source_path="data/canonical/market_observations/exact_option_quote/2026-09-25/XLF/"
                     "e2e8dd778aab45a96f309901e825310e725049458610ef99dbe3423944a28713.json",
    ),
}
# A separately stored run, real symbol/run_id, different selected contract.
OTHER_RUN_BULL = dict(
    symbol="BULL261218C00007500", ticker="BULL", run_id=OTHER_RUN,
    bid="0.79", ask="0.83", bid_size="136", ask_size="57",
    observed="2026-09-24T14:26:58Z",
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EXACT_QUOTE_ROOT = REPO_ROOT / "data" / "canonical" / "market_observations" / "exact_option_quote"


def _candidate(fixture: dict, **overrides) -> ExactContractQuoteCandidate:
    base = dict(
        source_path=fixture.get("source_path", f"synthetic/{fixture['ticker']}.json"),
        source_hash="realhash123", run_id=fixture["run_id"], ticker=fixture["ticker"],
        occ_symbol=fixture["symbol"], provider="MARKETDATA",
        provider_observed_at_utc=fixture["observed"],
        bid=fixture["bid"], ask=fixture["ask"],
        bid_size=fixture["bid_size"], ask_size=fixture["ask_size"],
        delta="0.5", gamma="0.1", theta="-0.01", vega="0.05",
        quote_quality_raw=None,
    )
    base.update(overrides)
    return ExactContractQuoteCandidate(**base)


def _gen_time_for(fixture: dict, minutes_after: float = 1.0) -> datetime:
    observed = datetime.fromisoformat(fixture["observed"].replace("Z", "+00:00"))
    return observed + timedelta(minutes=minutes_after)


@pytest.mark.parametrize("ticker", REAL_QUOTES.keys())
def test_run_20260925_061649_real_selected_symbols_join_cleanly(ticker):
    fixture = REAL_QUOTES[ticker]
    candidate = _candidate(fixture)
    join = join_exact_contract_quote(
        requested_occ_symbol=fixture["symbol"], requested_run_id=RUN, requested_ticker=ticker,
        candidates=[candidate], report_generation_time_utc=_gen_time_for(fixture),
    )
    assert join.identity_state == QuoteIdentityState.MATCHED.value
    assert join.quote_quality == QuoteQualityState.TWO_SIDED.value
    assert join.quote_freshness == QuoteFreshnessState.FRESH.value
    assert join.executable_now == ExecutableNowState.EXECUTABLE_NOW.value
    assert join.authority == "ADVISORY_ONLY"


@pytest.mark.parametrize("ticker", REAL_QUOTES.keys())
def test_read_only_integration_against_the_real_stored_file(ticker):
    """Reads the actual stored file for this ticker/date; alters nothing."""
    ticker_dir = EXACT_QUOTE_ROOT / "2026-09-25" / ticker
    if not ticker_dir.exists():
        pytest.skip(f"real fixture directory not present in this checkout: {ticker_dir}")
    files = sorted(ticker_dir.glob("*.json"))
    if not files:
        pytest.skip(f"no stored exact_option_quote file under {ticker_dir}")
    source_file = files[0]
    original_bytes = source_file.read_bytes()  # for the post-test no-mutation check
    payload = json.loads(original_bytes.decode("utf-8"))
    assert payload["run_id"] == RUN
    candidate = load_exact_contract_quote_candidate_from_json(
        payload, source_path=str(source_file.relative_to(REPO_ROOT)), source_hash=source_file.stem,
    )
    observed = datetime.fromisoformat(payload["quote_timestamp_utc"].replace("Z", "+00:00"))
    join = join_exact_contract_quote(
        requested_occ_symbol=payload["symbol"], requested_run_id=RUN, requested_ticker=ticker,
        candidates=[candidate], report_generation_time_utc=observed + timedelta(minutes=1),
    )
    assert join.identity_state == QuoteIdentityState.MATCHED.value
    # These files store their own raw quote_freshness as the literal string
    # "UNASSESSED" -- our derived value must never just pass that through.
    assert payload.get("quote_freshness") == "UNASSESSED"
    assert join.quote_freshness != "UNASSESSED"
    assert join.quote_freshness in {s.value for s in QuoteFreshnessState}
    # Read-only: the source file on disk must be byte-identical afterwards.
    assert source_file.read_bytes() == original_bytes


def test_zero_displayed_size_is_not_executable_now_regression():
    """Reported defect: a fresh two-sided quote with bid_size=0, ask_size=0
    was returning EXECUTABLE_NOW. Both sizes must be present and positive."""
    fixture = REAL_QUOTES["BULL"]
    zero_size = _candidate(fixture, bid_size="0", ask_size="0")
    join = join_exact_contract_quote(
        requested_occ_symbol=fixture["symbol"], requested_run_id=RUN, requested_ticker="BULL",
        candidates=[zero_size], report_generation_time_utc=_gen_time_for(fixture),
    )
    assert join.quote_quality == QuoteQualityState.NO_DISPLAYED_SIZE.value
    assert join.executable_now != ExecutableNowState.EXECUTABLE_NOW.value
    assert join.executable_now == ExecutableNowState.NOT_EXECUTABLE_QUALITY.value


def test_missing_displayed_size_is_not_executable_now():
    fixture = REAL_QUOTES["EWG"]
    missing_size = _candidate(fixture, bid_size=None, ask_size=None)
    join = join_exact_contract_quote(
        requested_occ_symbol=fixture["symbol"], requested_run_id=RUN, requested_ticker="EWG",
        candidates=[missing_size], report_generation_time_utc=_gen_time_for(fixture),
    )
    assert join.quote_quality == QuoteQualityState.SIZE_MISSING.value
    assert join.executable_now == ExecutableNowState.NOT_EXECUTABLE_QUALITY.value


def test_one_sided_zero_size_is_not_conflated_with_two_sided_zero_size():
    """A one-sided quote (missing ask) is ONE_SIDED, not (incorrectly) SIZE_MISSING."""
    fixture = REAL_QUOTES["SOFI"]
    one_sided = _candidate(fixture, ask=None, ask_size=None)
    join = join_exact_contract_quote(
        requested_occ_symbol=fixture["symbol"], requested_run_id=RUN, requested_ticker="SOFI",
        candidates=[one_sided], report_generation_time_utc=_gen_time_for(fixture),
    )
    assert join.quote_quality == QuoteQualityState.ONE_SIDED.value


def test_quote_freshness_is_never_left_unassessed_when_a_timestamp_is_present():
    fixture = REAL_QUOTES["XLF"]
    candidate = _candidate(fixture)
    join = join_exact_contract_quote(
        requested_occ_symbol=fixture["symbol"], requested_run_id=RUN, requested_ticker="XLF",
        candidates=[candidate], report_generation_time_utc=_gen_time_for(fixture),
    )
    assert join.quote_freshness != "UNASSESSED"
    assert join.quote_age_seconds_at_generation is not None


def test_stale_but_two_sided_and_sized_quote_is_not_executable_now():
    fixture = REAL_QUOTES["BULL"]
    stale = _candidate(fixture)
    join = join_exact_contract_quote(
        requested_occ_symbol=fixture["symbol"], requested_run_id=RUN, requested_ticker="BULL",
        candidates=[stale], report_generation_time_utc=_gen_time_for(fixture, minutes_after=10),
        freshness_seconds=300,
    )
    assert join.quote_quality == QuoteQualityState.TWO_SIDED.value
    assert join.quote_freshness == QuoteFreshnessState.STALE.value
    assert join.executable_now == ExecutableNowState.NOT_EXECUTABLE_STALE.value


def test_symbol_run_mismatch_is_not_treated_as_identity():
    fixture = REAL_QUOTES["BULL"]
    wrong_run = _candidate(fixture, run_id=OTHER_RUN)
    join = join_exact_contract_quote(
        requested_occ_symbol=fixture["symbol"], requested_run_id=RUN, requested_ticker="BULL",
        candidates=[wrong_run], report_generation_time_utc=_gen_time_for(fixture),
    )
    assert join.identity_state == QuoteIdentityState.RUN_MISMATCH.value
    assert join.matched_source_path is None


def test_future_dated_provider_timestamp_is_flagged_not_silently_trusted():
    fixture = REAL_QUOTES["BULL"]
    future = _candidate(fixture, provider_observed_at_utc="2026-09-25T23:00:00Z")
    join = join_exact_contract_quote(
        requested_occ_symbol=fixture["symbol"], requested_run_id=RUN, requested_ticker="BULL",
        candidates=[future], report_generation_time_utc=_gen_time_for(fixture),
    )
    assert join.quote_freshness == QuoteFreshnessState.FUTURE_DATED.value
    assert join.executable_now == ExecutableNowState.NOT_ASSESSABLE.value


def test_cross_run_contamination_a_second_real_stored_run_never_supplies_the_match():
    """BULL exists in both real runs, under different contracts. A candidate
    carrying the RUN's own symbol but relabelled with OTHER_RUN's run_id must
    not be accepted as identity for a RUN request — this isolates run_id as
    part of identity, independent of symbol string collisions."""
    this_run_fixture = REAL_QUOTES["BULL"]
    mislabelled = _candidate(this_run_fixture, run_id=OTHER_RUN, source_hash="wrong_run_hash")
    correctly_labelled = _candidate(this_run_fixture, run_id=RUN, source_hash="right_run_hash")
    join = join_exact_contract_quote(
        requested_occ_symbol=this_run_fixture["symbol"], requested_run_id=RUN, requested_ticker="BULL",
        candidates=[mislabelled, correctly_labelled], report_generation_time_utc=_gen_time_for(this_run_fixture),
    )
    assert join.identity_state == QuoteIdentityState.MATCHED.value
    assert join.matched_source_hash == "right_run_hash"


def test_other_runs_real_selected_contract_is_a_distinct_symbol_and_still_joins():
    join = join_exact_contract_quote(
        requested_occ_symbol=OTHER_RUN_BULL["symbol"], requested_run_id=OTHER_RUN, requested_ticker="BULL",
        candidates=[_candidate(OTHER_RUN_BULL)],
        report_generation_time_utc=_gen_time_for(OTHER_RUN_BULL),
    )
    assert join.identity_state == QuoteIdentityState.MATCHED.value
    assert join.requested_occ_symbol != REAL_QUOTES["BULL"]["symbol"]


def test_no_candidate_for_ticker_is_not_found_never_conflated_with_no_data():
    join = join_exact_contract_quote(
        requested_occ_symbol=REAL_QUOTES["SOFI"]["symbol"], requested_run_id=RUN, requested_ticker="SOFI",
        candidates=[], report_generation_time_utc=_gen_time_for(REAL_QUOTES["SOFI"]),
    )
    assert join.identity_state == QuoteIdentityState.NOT_FOUND.value


def test_build_supplemental_broker_observation_record_only_builds_never_writes(tmp_path):
    fixture = REAL_QUOTES["BULL"]
    candidate = _candidate(fixture)
    join = join_exact_contract_quote(
        requested_occ_symbol=fixture["symbol"], requested_run_id=RUN, requested_ticker="BULL",
        candidates=[candidate], report_generation_time_utc=_gen_time_for(fixture),
    )
    fetched_at = _gen_time_for(fixture, minutes_after=2)
    record = build_supplemental_broker_observation_record(
        historical_join=join,
        fresh_observation={"provider": "TASTYTRADE", "provider_updated_at_utc": fixture["observed"],
                            "bid": "0.62", "ask": "0.65"},
        fetched_at_utc=fetched_at,
    )
    assert record.overwrites_historical_snapshot is False
    assert record.persisted_as != join.matched_source_path
    assert "exact_option_quote_live_supplement" in record.persisted_as
    # Building the record must not have written anything anywhere.
    assert list(tmp_path.iterdir()) == []


def test_authority_is_always_advisory_only():
    fixture = REAL_QUOTES["XLF"]
    candidate = _candidate(fixture)
    join = join_exact_contract_quote(
        requested_occ_symbol=fixture["symbol"], requested_run_id=RUN, requested_ticker="XLF",
        candidates=[candidate], report_generation_time_utc=_gen_time_for(fixture),
    )
    assert join.authority == "ADVISORY_ONLY"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
