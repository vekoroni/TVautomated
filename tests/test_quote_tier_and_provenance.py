"""Quote validity, liquidity tier and provenance (AVS-TRADE-001 design v4 section 8; ACK 11 and 14 Nov 2026).

Business rules:
- Validity comes before the tier: a crossed quote is invalid and is never graded on its (negative) spread.
- The 11 Nov tiers in full: A = spread <= 10% of mid, OI >= 100, and (mid >= 1.50 or width <= 0.10);
  B = 10-20%, or a narrow-percent quote under 1.50 that is more than 0.10 wide; C = over 20% or OI under 100.
- A quote is ALIGNED only when a session-aware check says so. The text SESSION_ALIGNED or the presence of a
  timestamp is not proof; unknown alignment is PROVISIONAL; a quote is never restamped.
"""
from datetime import date, datetime, timezone

import pytest

from domain.option_contract_liquidity import liquidity_tier_settings, quote_tier
from domain.quote_provenance import quote_provenance

S = liquidity_tier_settings()


def test_the_governed_tier_thresholds_are_the_11_nov_rule():
    assert (S["a_spread_pct"], S["b_spread_pct"], S["min_oi"], S["low_premium"], S["low_premium_max_width"]) == (
        10.0, 20.0, 100, 1.50, 0.10)


@pytest.mark.parametrize("bid,ask,oi,validity,tier,code", [
    (2.00, 2.10, 500, "VALID", "A", "WITHIN_TIER_A"),                     # 4.9% of mid
    (2.00, 2.30, 500, "VALID", "B", "SPREAD_OVER_TIER_A"),                # 14%
    (2.00, 2.60, 500, "VALID", "C", "SPREAD_OVER_TIER_B"),                # 26%
    (2.00, 2.10, 99, "VALID", "C", "OI_UNDER_MINIMUM"),
    (2.00, 2.10, 100, "VALID", "A", "WITHIN_TIER_A"),                     # OI boundary is inclusive
    (1.00, 1.12, 500, "VALID", "B", "SPREAD_OVER_TIER_A"),                # 11.3%
    (1.20, 1.32, 500, "VALID", "B", "LOW_PREMIUM_WIDE"),                  # 9.5% but under 1.50 and 0.12 wide
    (1.20, 1.30, 500, "VALID", "A", "WITHIN_TIER_A"),                     # 8% and exactly 0.10 wide
    (None, 2.10, 500, "UNASSESSED_NO_BID", None, "NO_BID"),
    (0.0, 2.10, 500, "UNASSESSED_NO_BID", None, "NO_BID"),
    (-0.5, 2.10, 500, "UNASSESSED_NO_BID", None, "NO_BID"),
    (2.00, None, 500, "UNASSESSED_NO_ASK", None, "NO_ASK"),
    (2.00, 0.0, 500, "UNASSESSED_NO_ASK", None, "NO_ASK"),
    (float("nan"), 2.10, 500, "UNASSESSED_NO_BID", None, "NO_BID"),
    (2.00, float("inf"), 500, "UNASSESSED_NO_ASK", None, "NO_ASK"),
    (2.20, 2.00, 500, "INVALID_CROSSED_QUOTE", None, "CROSSED_QUOTE"),    # the defect: was graded on a negative spread
    (2.00, 2.10, None, "UNASSESSED_NO_OI", None, "OI_NOT_RECORDED"),
])
def test_validity_comes_before_tier(bid, ask, oi, validity, tier, code):
    out = quote_tier(bid, ask, oi)
    assert (out["validity"], out["tier"], out["code"]) == (validity, tier, code)
    if validity != "VALID":
        assert out["spread_pct"] is None or validity == "UNASSESSED_NO_OI"


def test_exact_spread_boundaries_use_the_existing_tolerance():
    # width / mid exactly 10% and exactly 20%: inclusive, with the 1e-9 tolerance Lane B has always applied.
    assert quote_tier(1.90, 2.10, 500)["tier"] == "A"          # 0.20 / 2.00 = 10.0%
    assert quote_tier(1.80, 2.20, 500)["tier"] == "B"          # 0.40 / 2.00 = 20.0%


def test_caller_settings_are_honoured():
    strict = {**S, "a_spread_pct": 3.0}
    assert quote_tier(2.00, 2.10, 500, strict)["tier"] == "B"


# ---------------------------------------------------------------- provenance

D0 = date(2026, 11, 11)
CLOSE = datetime(2026, 11, 11, 21, 0, tzinfo=timezone.utc)               # 16:00 ET


def _evening(**over):
    base = dict(mode="EVENING_AT_EVIDENCE", quote_timestamp_utc="2026-11-11T21:00:00Z", assessment_instant_utc=CLOSE,
                evidence_session=D0, spot_session=D0, iv_session=D0, expected_symbol="AAA261218C00100000",
                quote_symbol="AAA261218C00100000")
    base.update(over)
    return quote_provenance(**base)


def test_a_close_quote_of_the_evidence_session_is_aligned():
    out = _evening()
    assert (out["provenance"], out["reason"]) == ("ALIGNED", "EOD_CURRENT_AT_EVIDENCE_CLOSE")


@pytest.mark.parametrize("over,reason", [
    ({"quote_timestamp_utc": None}, "QUOTE_TIMESTAMP_UNKNOWN"),
    ({"quote_timestamp_utc": "2026-11-11 21:00:00"}, "QUOTE_TIMESTAMP_UNKNOWN"),        # no timezone: not accepted
    ({"quote_timestamp_utc": "2026-11-10T21:00:00Z"}, "QUOTE_SESSION_MISMATCH"),        # the day before
    ({"quote_timestamp_utc": "2026-11-11T18:00:00Z"}, "QUOTE_NOT_NEAR_CLOSE"),          # 13:00 ET
    ({"quote_symbol": "AAA261218C00105000"}, "IDENTITY_MISMATCH"),
])
def test_anything_short_of_a_proved_close_quote_is_provisional(over, reason):
    out = _evening(**over)
    assert (out["provenance"], out["reason"]) == ("PROVISIONAL", reason)


def test_an_early_close_day_uses_its_own_close():
    early = date(2026, 11, 27)                                             # day after Thanksgiving, 13:00 ET close
    out = quote_provenance(mode="EVENING_AT_EVIDENCE", quote_timestamp_utc="2026-11-27T18:00:00Z",
                           assessment_instant_utc=datetime(2026, 11, 27, 18, 0, tzinfo=timezone.utc),
                           evidence_session=early, spot_session=early, iv_session=early,
                           expected_symbol="X", quote_symbol="X")
    assert out["provenance"] == "ALIGNED"


def test_the_saved_label_alone_is_not_proof():
    out = _evening(quote_timestamp_utc=None, saved_freshness_label="SESSION_ALIGNED")
    assert out["provenance"] == "PROVISIONAL"


def _morning(quote_ts, now="2026-11-12T14:40:00Z", **over):
    base = dict(mode="MORNING_FRESH_ENTRY", quote_timestamp_utc=quote_ts,
                assessment_instant_utc=datetime.fromisoformat(now.replace("Z", "+00:00")),
                evidence_session=D0, expected_symbol="X", quote_symbol="X", quote_feed="MARKETDATA",
                spot_state="CURRENT", spot_is_fallback=False, spot_session=date(2026, 11, 12), iv_symbol="X",
                iv_session=date(2026, 11, 12))
    base.update(over)
    return quote_provenance(**base)


def test_a_morning_quote_inside_the_governed_window_is_aligned_and_an_older_one_is_not():
    assert _morning("2026-11-12T14:30:00Z")["provenance"] == "ALIGNED"            # 600 s old
    stale = _morning("2026-11-12T14:05:00Z")                                       # 2,100 s old, 1,200 s net of delay
    assert (stale["provenance"], stale["reason"]) == ("PROVISIONAL", "QUOTE_BEYOND_FEED_WINDOW")
    other = _morning("2026-11-11T21:00:00Z")                                       # yesterday's close
    assert (other["provenance"], other["reason"]) == ("PROVISIONAL", "QUOTE_SESSION_MISMATCH")


def test_the_quote_time_is_reported_as_given_never_restamped():
    out = _evening(quote_timestamp_utc="2026-11-11T18:00:00Z")
    assert out["quote_timestamp_utc"] == "2026-11-11T18:00:00Z"
    assert out["assessment_instant_utc"] == CLOSE.isoformat()


# ------------------------------------------------ Codex v4 review, R3 (14 Nov 2026): compose with the feed policy

def _morning_full(raw_age_seconds, **over):
    """A Morning quote `raw_age_seconds` old on the governed delayed feed, with current spot and own-contract IV."""
    from datetime import timedelta
    now = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)
    base = dict(mode="MORNING_FRESH_ENTRY", quote_timestamp_utc=(now - timedelta(seconds=raw_age_seconds)).isoformat(),
                assessment_instant_utc=now, evidence_session=D0, expected_symbol="X", quote_symbol="X",
                quote_feed="MARKETDATA", spot_state="CURRENT", spot_is_fallback=False,
                spot_session=date(2026, 11, 12), iv_symbol="X", iv_session=date(2026, 11, 12))
    base.update(over)
    return quote_provenance(**base)


@pytest.mark.parametrize("raw,provenance,reason,effective", [
    (900, "ALIGNED", "WITHIN_FEED_WINDOW_NET_OF_DISCLOSED_DELAY", 0.0),
    (1200, "ALIGNED", "WITHIN_FEED_WINDOW_NET_OF_DISCLOSED_DELAY", 300.0),     # raw-age TTL would have called this stale
    (1800, "ALIGNED", "WITHIN_FEED_WINDOW_NET_OF_DISCLOSED_DELAY", 900.0),     # the window boundary is inclusive
    (1801, "PROVISIONAL", "QUOTE_BEYOND_FEED_WINDOW", 901.0),
])
def test_morning_freshness_is_judged_on_age_net_of_the_disclosed_feed_delay(raw, provenance, reason, effective):
    out = _morning_full(raw)
    assert (out["provenance"], out["reason"]) == (provenance, reason)
    assert out["raw_age_seconds"] == pytest.approx(raw)
    assert out["disclosed_delay_seconds"] == 900.0
    assert out["effective_age_seconds"] == pytest.approx(effective)
    assert out["quote_feed"] == "MARKETDATA" and out["feed_policy_version"] == "option_quote_feed_v1"


def test_a_real_time_feed_gets_no_delay_allowance():
    out = _morning_full(1200, quote_feed="BROKER_REALTIME", disclosed_delay_seconds=0)
    assert (out["provenance"], out["reason"], out["effective_age_seconds"]) == (
        "PROVISIONAL", "QUOTE_BEYOND_FEED_WINDOW", pytest.approx(1200.0))
    assert _morning_full(600, quote_feed="BROKER_REALTIME", disclosed_delay_seconds=0)["provenance"] == "ALIGNED"


def test_an_unknown_feed_is_never_given_the_governed_delay():
    for feed in (None, "", "SOMEONE_ELSE"):
        out = _morning_full(1200, quote_feed=feed)
        assert (out["provenance"], out["reason"]) == ("PROVISIONAL", "QUOTE_FEED_UNKNOWN")
        assert out["disclosed_delay_seconds"] is None and out["effective_age_seconds"] is None


def test_a_future_quote_is_not_evidence_in_either_mode():
    out = _morning_full(-120)
    assert (out["provenance"], out["reason"]) == ("PROVISIONAL", "QUOTE_AFTER_ASSESSMENT_INSTANT")
    # Evening: ten minutes after the close is inside the 1,800 s tolerance but after the assessment instant.
    late = _evening(quote_timestamp_utc="2026-11-11T21:10:00Z")
    assert (late["provenance"], late["reason"]) == ("PROVISIONAL", "QUOTE_AFTER_ASSESSMENT_INSTANT")


@pytest.mark.parametrize("over,reason", [
    ({"spot_is_fallback": True}, "SPOT_FALLBACK_NOT_CURRENT"),               # signal-price fallback beside a fresh quote
    ({"spot_state": "AGED_REFERENCE"}, "SPOT_NOT_CURRENT"),
    ({"spot_state": None}, "SPOT_PROVENANCE_UNKNOWN"),
    ({"spot_is_fallback": None}, "SPOT_PROVENANCE_UNKNOWN"),
    ({"spot_session": D0}, "SPOT_SESSION_MISMATCH"),
    ({"iv_symbol": "OLD_CONTRACT"}, "IV_FROM_OTHER_CONTRACT"),               # repaired OCC, IV of the old contract
    ({"iv_symbol": None}, "IV_PROVENANCE_UNKNOWN"),
    ({"iv_session": D0}, "IV_SESSION_MISMATCH"),
])
def test_a_fresh_morning_quote_does_not_make_stale_spot_or_other_contract_iv_aligned(over, reason):
    out = _morning_full(1000, **over)
    assert (out["provenance"], out["reason"]) == ("PROVISIONAL", reason)


@pytest.mark.parametrize("over,reason", [
    ({"spot_session": date(2026, 11, 10)}, "SPOT_SESSION_MISMATCH"),
    ({"iv_session": None}, "IV_SESSION_MISMATCH"),
    ({"assessment_instant_utc": datetime(2026, 11, 13, 21, 0, tzinfo=timezone.utc)},
     "EVIDENCE_SESSION_NOT_LAST_COMPLETED"),
])
def test_evening_failures_keep_their_own_reason(over, reason):
    out = _evening(**over)
    assert (out["provenance"], out["reason"]) == ("PROVISIONAL", reason)


def test_a_saved_assessment_is_reusable_only_for_the_same_inputs_instant_mode_and_policy():
    from domain.quote_provenance import saved_assessment_reusable
    saved = _morning_full(1000)
    assert saved_assessment_reusable(saved, _morning_full(1000)["binding"])
    assert not saved_assessment_reusable(saved, _morning_full(1001)["binding"])                 # another quote
    assert not saved_assessment_reusable(saved, _morning_full(1000, spot_state="AGED_REFERENCE")["binding"])
    assert not saved_assessment_reusable(saved, {**saved["binding"], "policy_version": "other"})
    assert not saved_assessment_reusable(saved, {**saved["binding"], "mode": "EVENING_AT_EVIDENCE"})
    assert not saved_assessment_reusable({"provenance": "ALIGNED"}, saved["binding"])           # a bare saved label
    assert not saved_assessment_reusable("SESSION_ALIGNED", saved["binding"])
