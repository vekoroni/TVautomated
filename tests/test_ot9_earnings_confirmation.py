"""Output-trust item 9 (D7-1; ACK approved 9 Oct 2026): earnings dates carry their confirmation tier.

Root cause: the only source is MarketData, whose future dates can be projections and which has no confirmation field
(MSFT: MarketData 4 Nov; tastytrade 10 Oct shows 28 Oct after close, estimated=false). The card said "provider date,
not confirmed" and could not show the conflict.

Business rules (disclosure only - earnings never gate or score):
- Tiers: VENDOR_ESTIMATE (one vendor), CORROBORATED (MarketData and tastytrade agree on the date), ISSUER_CONFIRMED
  (from the intelligence mining process; accepted when supplied, no pipeline fetch), and SOURCES_DISAGREE (flagged,
  both dates shown; the earlier date is used for risk because it is the one that can fall inside the hold).
- Timing (before open / after close) and the date each source was checked are carried; a timing conflict is flagged.
- A source that cannot be read is stated, never treated as "no earnings".
"""
from __future__ import annotations

import json
from datetime import date

from domain.earnings_confirmation import parse_tastytrade_earnings, reconcile_earnings
from earnings_calendar_enricher import EARNINGS_DISCLOSURE_FIELDS, earnings_disclosure

AS_OF = date(2026, 10, 9)
MD_MSFT = {"state": "SCHEDULED", "date": "2026-11-04", "report_time": "AFTER_CLOSE", "fiscal_quarter": "2027Q1",
           "source": "MARKETDATA_EARNINGS", "date_confirmation": "PROVIDER_DATE_UNCONFIRMED"}
TT_ITEM = {"symbol": "MSFT", "earnings": {"visible": True, "expected-report-date": "2026-10-28", "estimated": False,
                                          "time-of-day": "AMC", "updated-at": "2026-10-08T10:15:52.594Z"}}


def test_tastytrade_earnings_are_parsed_with_timing_and_estimate_flag():
    tt = parse_tastytrade_earnings(TT_ITEM, as_of=AS_OF)
    assert tt == {"state": "SCHEDULED", "date": "2026-10-28", "report_time": "AFTER_CLOSE", "estimated": False,
                  "updated_at": "2026-10-08T10:15:52.594Z", "source": "TASTYTRADE_MARKET_METRICS"}
    past = parse_tastytrade_earnings({"earnings": {"expected-report-date": "2026-07-29", "estimated": False}}, as_of=AS_OF)
    assert past["state"] == "UNKNOWN" and past["reason"] == "TASTYTRADE_DATE_IN_PAST"
    assert parse_tastytrade_earnings({"symbol": "X"}, as_of=AS_OF)["state"] == "UNKNOWN"


def test_msft_disagreement_is_flagged_and_the_earlier_date_carries_the_risk():
    out = reconcile_earnings(MD_MSFT, parse_tastytrade_earnings(TT_ITEM, as_of=AS_OF))
    assert out["state"] == "SCHEDULED" and out["date_confirmation"] == "SOURCES_DISAGREE"
    assert out["date"] == "2026-10-28"
    assert "MarketData 2026-11-04" in out["disagreement"] and "tastytrade 2026-10-28 (not estimated)" in out["disagreement"]
    assert json.loads(out["sources_json"])["TASTYTRADE_MARKET_METRICS"]["date"] == "2026-10-28"


def test_agreement_is_corroborated_and_a_single_source_is_a_vendor_estimate():
    agree = reconcile_earnings({**MD_MSFT, "date": "2026-10-28"}, parse_tastytrade_earnings(TT_ITEM, as_of=AS_OF))
    assert agree["date_confirmation"] == "CORROBORATED" and agree["disagreement"] is None
    assert agree["report_time"] == "AFTER_CLOSE"
    alone = reconcile_earnings(MD_MSFT, {"state": "UNKNOWN", "reason": "TASTYTRADE_CREDENTIALS_UNAVAILABLE",
                                         "source": "TASTYTRADE_MARKET_METRICS"})
    assert alone["date_confirmation"] == "VENDOR_ESTIMATE" and alone["date"] == "2026-11-04"
    assert "tastytrade not checked (TASTYTRADE_CREDENTIALS_UNAVAILABLE)" in alone["confirmation_note"]


def test_timing_conflict_is_flagged_and_issuer_confirmation_wins():
    bmo = {**MD_MSFT, "date": "2026-10-28", "report_time": "BEFORE_OPEN"}
    out = reconcile_earnings(bmo, parse_tastytrade_earnings(TT_ITEM, as_of=AS_OF))
    assert out["date_confirmation"] == "CORROBORATED" and "timing differs" in out["disagreement"]
    issuer = reconcile_earnings(MD_MSFT, parse_tastytrade_earnings(TT_ITEM, as_of=AS_OF),
                                issuer={"date": "2026-10-28", "report_time": "AFTER_CLOSE", "source": "INTELLIGENCE_MINING"})
    assert issuer["date_confirmation"] == "ISSUER_CONFIRMED" and issuer["date"] == "2026-10-28"


def test_one_source_saying_none_is_not_a_none():
    out = reconcile_earnings({"state": "NONE_IN_LOOKAHEAD", "source": "MARKETDATA_EARNINGS", "lookahead_days": 120},
                             parse_tastytrade_earnings(TT_ITEM, as_of=AS_OF))
    assert out["state"] == "SCHEDULED" and out["date_confirmation"] == "SOURCES_DISAGREE"
    assert "MarketData none in 120 days" in out["disagreement"]


def test_the_disclosure_states_the_tier_and_carries_the_conflict():
    merged = reconcile_earnings(MD_MSFT, parse_tastytrade_earnings(TT_ITEM, as_of=AS_OF))
    out = earnings_disclosure(merged, as_of=AS_OF, hold_sessions=20, expiry="2026-11-20")
    assert {"earnings_disagreement", "earnings_sources_json", "earnings_confirmation_note"} <= set(EARNINGS_DISCLOSURE_FIELDS)
    assert out["earnings_date"] == "2026-10-28" and out["earnings_date_confirmation"] == "SOURCES_DISAGREE"
    assert "sources disagree" in out["earnings_disclosure"] and "2026-11-04" in out["earnings_disclosure"]
    assert out["earnings_disagreement"] == merged["disagreement"]


def test_the_evening_step_reads_both_sources_and_the_morning_keeps_the_reconciliation():
    import inspect
    import intelligent_orchestrator
    import morning_gate
    eod = inspect.getsource(intelligent_orchestrator.patch_earnings_fields_into_csv)
    assert "fetch_tastytrade_earnings(" in eod and "reconcile_earnings(" in eod
    src = inspect.getsource(morning_gate)
    assert src.count('"disagreement": row.get("earnings_disagreement")') == 2


class _FakeBroker:
    def __init__(self, fail_batches=False, no_credentials=False):
        self.fail_batches, self.no_credentials, self.calls = fail_batches, no_credentials, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def market_metrics(self, symbols):
        from bridge.tastytrade_readonly_mcp import BrokerCredentialUnavailable, BrokerMcpError
        self.calls.append(list(symbols))
        if self.no_credentials:
            raise BrokerCredentialUnavailable("missing broker OAuth environment")
        if self.fail_batches and len(symbols) > 1:
            raise BrokerMcpError("schema rejected")
        return {"items": [{**TT_ITEM, "symbol": s} for s in symbols if s != "BAD"]}


def test_the_tastytrade_fetch_batches_retries_and_states_missing_credentials(tmp_path):
    from canonical_data.tastytrade_earnings import fetch_tastytrade_earnings
    ok = fetch_tastytrade_earnings(["MSFT", "AAPL"], as_of=AS_OF, broker_factory=lambda: _FakeBroker())
    assert ok["MSFT"]["date"] == "2026-10-28" and ok["AAPL"]["state"] == "SCHEDULED"
    broker = _FakeBroker(fail_batches=True)
    retried = fetch_tastytrade_earnings(["MSFT", "BAD"], as_of=AS_OF, broker_factory=lambda: broker,
                                        cache_dir=tmp_path)
    assert broker.calls == [["BAD", "MSFT"], ["BAD"], ["MSFT"]]
    assert retried["MSFT"]["state"] == "SCHEDULED" and retried["BAD"]["reason"] == "TASTYTRADE_NO_METRICS_FOR_SYMBOL"
    cached = fetch_tastytrade_earnings(["MSFT"], as_of=AS_OF, broker_factory=lambda: _FakeBroker(no_credentials=True),
                                       cache_dir=tmp_path)
    assert cached["MSFT"]["state"] == "SCHEDULED"                          # served from the session cache
    none = fetch_tastytrade_earnings(["AAPL"], as_of=AS_OF, broker_factory=lambda: _FakeBroker(no_credentials=True))
    assert none["AAPL"] == {"state": "UNKNOWN", "reason": "TASTYTRADE_CREDENTIALS_UNAVAILABLE",
                            "source": "TASTYTRADE_MARKET_METRICS"}
