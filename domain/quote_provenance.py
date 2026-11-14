"""Quote provenance: is this quote the one the assessment should be using? (AVS-TRADE-001 design v4 section 8)

ALIGNED or PROVISIONAL, composed from two existing owners (Codex v4 review R3, 14 Nov 2026):
- canonical_data.session_clock: aware time, no future evidence, and which session a timestamp belongs to;
- domain.long_option_execution: the provider-delay-aware quote age (effective age = raw age net of the disclosed
  feed delay) and its governed window. A delayed quote is never called real-time and is never restamped.
No threshold is defined here. A saved label such as SESSION_ALIGNED, or the mere presence of a timestamp, is never
proof; unknown alignment, feed, spot or IV provenance is PROVISIONAL with its own reason. Label only: nothing here
removes a contract or grants execution.

Kept apart from domain.option_contract_liquidity, which must not depend on the data layer.
"""
from __future__ import annotations

from typing import Any, Dict

from domain.option_contract_liquidity import _governed_constants


def _aware_instant(value: Any):
    from datetime import datetime
    if isinstance(value, datetime):
        return value if value.tzinfo is not None and value.utcoffset() is not None else None
    try:
        instant = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return instant if instant.tzinfo is not None and instant.utcoffset() is not None else None


POLICY_VERSION = "quote_provenance_v2"
OWNERS = "canonical_data.session_clock + domain.long_option_execution.effective_quote_age_seconds"
BINDING_KEYS = ("policy_version", "feed_policy_version", "mode", "expected_symbol", "quote_symbol",
                "quote_timestamp_utc", "assessment_instant_utc", "evidence_session", "quote_feed",
                "disclosed_delay_seconds", "spot_state", "spot_is_fallback", "spot_session", "iv_symbol", "iv_session",
                "close_tolerance_seconds", "freshness_window_seconds")


def saved_assessment_reusable(saved: Any, binding: Any) -> bool:
    """A saved assessment may be reused only when it carries a binding equal to the current one: the same contract,
    observations, assessment instant, mode and policy versions. A bare saved label is never reusable."""
    if not isinstance(saved, dict) or not isinstance(binding, dict):
        return False
    held = saved.get("binding")
    if not isinstance(held, dict) or saved.get("provenance") not in ("ALIGNED", "PROVISIONAL"):
        return False
    return all(key in held and key in binding and held[key] == binding[key] for key in BINDING_KEYS)


def quote_provenance(*, mode: Any, quote_timestamp_utc: Any, assessment_instant_utc: Any, evidence_session: Any,
                     expected_symbol: Any, quote_symbol: Any, spot_session: Any = None, iv_session: Any = None,
                     saved_freshness_label: Any = None, close_tolerance_seconds: Any = None,
                     live_freshness_max_seconds: Any = None, quote_feed: Any = None,
                     disclosed_delay_seconds: Any = None, spot_state: Any = None, spot_is_fallback: Any = None,
                     iv_symbol: Any = None) -> Dict[str, Any]:
    """ALIGNED or PROVISIONAL for the values an assessment combines: the option quote, the spot and the IV.

    Evening: the quote is the evidence session's close quote: not after the assessment instant (no look-ahead, even
    inside the close tolerance), in the evidence session, that session being the last completed one at the
    assessment instant, within the configured tolerance of its close, with spot and IV from the same session. Each
    failure keeps its own reason.
    Morning: the quote is from the assessment's session and its age NET OF THE DISCLOSED FEED DELAY is inside the
    governed feed window (the existing Morning convention). The governed delay applies only to the governed feed;
    another feed must state its own delay; an unknown feed is PROVISIONAL. The spot must be the Morning's own
    CURRENT price, not a fallback, and the IV must be this contract's, both from the assessment's session.
    """
    from datetime import date as _date, datetime as _datetime, timezone as _tz
    from canonical_data.session_clock import (NEW_YORK, FreshnessState, evaluate_freshness, is_xnys_session,
                                              session_bounds)
    from domain.long_option_execution import (EXECUTION_QUOTE_FRESHNESS_MAX_SECONDS, QUOTE_FEED_DELAY_SECONDS,
                                              effective_quote_age_seconds, quote_age_disclosure, quote_age_seconds)
    constants = _governed_constants()
    feed_policy = constants["option_quote_feed"]
    tolerance = float(close_tolerance_seconds if close_tolerance_seconds is not None
                      else constants["contract_crossing_scenario"]["evening_close_quote_tolerance_seconds"])
    window = float(live_freshness_max_seconds if live_freshness_max_seconds is not None
                   else EXECUTION_QUOTE_FRESHNESS_MAX_SECONDS)
    assessed = _aware_instant(assessment_instant_utc)
    quoted = _aware_instant(quote_timestamp_utc)

    def session_of(value: Any):
        if isinstance(value, _datetime):
            return value.date()
        if isinstance(value, _date):
            return value
        try:
            return _date.fromisoformat(str(value)[:10])
        except (TypeError, ValueError):
            return None

    def iso(value: Any):
        day = session_of(value)
        return day.isoformat() if day else None

    feed = str(quote_feed or "").strip().upper() or None
    governed_feed = str(feed_policy.get("provider") or "").strip().upper()
    mode_name = str(mode or "").upper()
    out: Dict[str, Any] = {
        "provenance": "PROVISIONAL", "reason": None, "mode": mode_name,
        "quote_timestamp_utc": quote_timestamp_utc if quote_timestamp_utc is None else str(quote_timestamp_utc),
        "assessment_instant_utc": assessed.isoformat() if assessed else None,
        "quote_session": None, "owner": OWNERS, "policy_version": POLICY_VERSION,
        "feed_policy_version": feed_policy.get("version"), "quote_feed": feed,
        "raw_age_seconds": None, "disclosed_delay_seconds": None, "effective_age_seconds": None,
        "quote_age_state": None, "saved_freshness_label": saved_freshness_label,
    }
    out["binding"] = {
        "policy_version": POLICY_VERSION, "feed_policy_version": feed_policy.get("version"), "mode": mode_name,
        "expected_symbol": str(expected_symbol or "").strip().upper(),
        "quote_symbol": str(quote_symbol or "").strip().upper(), "quote_timestamp_utc": out["quote_timestamp_utc"],
        "assessment_instant_utc": out["assessment_instant_utc"], "evidence_session": iso(evidence_session),
        "quote_feed": feed,
        "disclosed_delay_seconds": None if disclosed_delay_seconds is None else float(disclosed_delay_seconds),
        "spot_state": None if spot_state is None else str(spot_state).strip().upper(),
        "spot_is_fallback": spot_is_fallback, "spot_session": iso(spot_session),
        "iv_symbol": None if iv_symbol is None else str(iv_symbol).strip().upper(), "iv_session": iso(iv_session),
        "close_tolerance_seconds": tolerance, "freshness_window_seconds": window,
    }

    def provisional(reason: str) -> Dict[str, Any]:
        return {**out, "reason": reason}

    if assessed is None:
        return provisional("ASSESSMENT_INSTANT_UNKNOWN")
    if quoted is None:
        return provisional("QUOTE_TIMESTAMP_UNKNOWN")
    expected = out["binding"]["expected_symbol"]
    if not expected or expected != out["binding"]["quote_symbol"]:
        return provisional("IDENTITY_MISMATCH")
    quote_session = quoted.astimezone(NEW_YORK).date()
    out["quote_session"] = quote_session.isoformat()
    out["raw_age_seconds"] = quote_age_seconds(quoted, as_of_utc=assessed)
    if mode_name == "EVENING_AT_EVIDENCE":
        evidence = session_of(evidence_session)
        if evidence is None or not is_xnys_session(evidence):
            return provisional("EVIDENCE_SESSION_UNKNOWN")
        state = evaluate_freshness(as_of=quoted, dataset_session=quote_session, domain="OPTION_CHAIN", now=assessed)
        if state is FreshnessState.INVALID:                     # observed after the assessment instant: look-ahead
            return provisional("QUOTE_AFTER_ASSESSMENT_INSTANT")
        if quote_session != evidence:
            return provisional("QUOTE_SESSION_MISMATCH")
        if state is not FreshnessState.EOD_CURRENT:
            return provisional("EVIDENCE_SESSION_NOT_LAST_COMPLETED")
        close_utc = session_bounds(evidence)[1].astimezone(_tz.utc)
        if abs((quoted.astimezone(_tz.utc) - close_utc).total_seconds()) > tolerance:
            return provisional("QUOTE_NOT_NEAR_CLOSE")
        if session_of(spot_session) != evidence:
            return provisional("SPOT_SESSION_MISMATCH")
        if session_of(iv_session) != evidence:
            return provisional("IV_SESSION_MISMATCH")
        return {**out, "provenance": "ALIGNED", "reason": "EOD_CURRENT_AT_EVIDENCE_CLOSE"}
    if mode_name == "MORNING_FRESH_ENTRY":
        today = assessed.astimezone(NEW_YORK).date()
        state = evaluate_freshness(as_of=quoted, dataset_session=quote_session, domain="LIVE_QUOTE", now=assessed,
                                   live_ttl_seconds=10 ** 9)   # session clock used for time validity only, not the TTL
        if state is FreshnessState.INVALID:
            return provisional("QUOTE_AFTER_ASSESSMENT_INSTANT")
        if quote_session != today:
            return provisional("QUOTE_SESSION_MISMATCH")
        if feed is not None and feed == governed_feed and disclosed_delay_seconds is None:
            delay = float(QUOTE_FEED_DELAY_SECONDS)
            effective = effective_quote_age_seconds(quoted, as_of_utc=assessed)       # the existing Morning owner
        elif feed is not None and feed != governed_feed and disclosed_delay_seconds is not None:
            try:
                delay = float(disclosed_delay_seconds)
            except (TypeError, ValueError):
                return provisional("QUOTE_FEED_UNKNOWN")
            if not (0 <= delay < float("inf")):
                return provisional("QUOTE_FEED_UNKNOWN")
            effective = max(0.0, out["raw_age_seconds"] - delay)
        else:
            return provisional("QUOTE_FEED_UNKNOWN")
        age_state = quote_age_disclosure(effective, raw_age_seconds=out["raw_age_seconds"],
                                         window_seconds=window)["quote_age_state"]
        out.update(disclosed_delay_seconds=delay, effective_age_seconds=effective, quote_age_state=age_state)
        if age_state != "WITHIN_FEED_WINDOW":
            return provisional("QUOTE_BEYOND_FEED_WINDOW")
        if spot_is_fallback is None or spot_state is None:
            return provisional("SPOT_PROVENANCE_UNKNOWN")
        if spot_is_fallback:
            return provisional("SPOT_FALLBACK_NOT_CURRENT")
        if str(spot_state).strip().upper() != "CURRENT":
            return provisional("SPOT_NOT_CURRENT")
        if session_of(spot_session) != today:
            return provisional("SPOT_SESSION_MISMATCH")
        if iv_symbol is None or not str(iv_symbol).strip():
            return provisional("IV_PROVENANCE_UNKNOWN")
        if str(iv_symbol).strip().upper() != expected:
            return provisional("IV_FROM_OTHER_CONTRACT")
        if session_of(iv_session) != today:
            return provisional("IV_SESSION_MISMATCH")
        return {**out, "provenance": "ALIGNED", "reason": "WITHIN_FEED_WINDOW_NET_OF_DISCLOSED_DELAY"}
    return provisional("MODE_UNKNOWN")
