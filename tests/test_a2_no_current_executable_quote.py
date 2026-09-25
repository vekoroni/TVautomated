"""A2 — a row with no quote is NO_CURRENT_EXECUTABLE_QUOTE, not PROVIDER_TIMESTAMP_MISSING (ACK, 25 Sep 2026).

Root cause (Enhancements/research/rca/A2_NO_CURRENT_EXECUTABLE_QUOTE_RCA_AND_DESIGN_20260925.md): the post-open
override in morning_gate.run_gate tests only for a provider timestamp, so a row with no quote at all (204 of 205 on
25 Sep) is labelled as if a quote had arrived unstamped, and the governed policy's own reason is discarded.

Business rules (ACK):
- Labels say what was measured: no quote -> NO_CURRENT_EXECUTABLE_QUOTE; a quote without a provider timestamp ->
  PROVIDER_TIMESTAMP_MISSING. The policy's own reason is carried beside the label, never re-derived.
- The state is reversible: the row re-enters when a quote appears (execution_viability_reversible, _recheck).
- Routing is preserved: state, eligibility and executable_now are exactly what the legacy override produced.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import morning_gate as mg

TS = "2026-09-25T13:46:00Z"


def _out(**fields):
    base = {"execution_viability_state": "DATA_MISSING",
            "execution_viability_reason": "SELECTED_STRUCTURE_NOT_HYDRATED"}
    base.update(fields)
    return base


# ── Characterisation: the routing-relevant outputs of the legacy override are unchanged ─────────────────────
@pytest.mark.parametrize("live", [
    {"morning_execution_mode": "POSTOPEN_CONTRACT_REFRESH"},                                     # no quote at all
    {"morning_execution_mode": "POSTOPEN_CONTRACT_REFRESH", "live_contract_bid": 1.0, "live_contract_ask": 1.2},  # quote, no stamp
])
def test_characterisation_state_eligibility_and_executable_now_are_as_the_legacy_override(live):
    result = mg.postopen_quote_unavailable_override(_out(), live)
    assert result["execution_viability_state"] == "CONTRACT_QUOTE_UNAVAILABLE"
    assert result["execution_viability_eligible"] is False
    assert result["executable_now"] is False


# ── Business rules ─────────────────────────────────────────────────────────────────────────────────────────
def test_no_quote_is_no_current_executable_quote_and_carries_the_policy_reason():
    result = mg.postopen_quote_unavailable_override(_out(), {"morning_execution_mode": "POSTOPEN_CONTRACT_REFRESH"})
    assert result["execution_viability_reason"] == "NO_CURRENT_EXECUTABLE_QUOTE"
    assert result["execution_viability_domain_reason"] == "SELECTED_STRUCTURE_NOT_HYDRATED"
    assert result["execution_viability_reversible"] is True
    assert result["execution_viability_recheck"] == "NEXT_QUOTE_REFRESH"


def test_a_one_sided_quote_is_still_no_current_executable_quote():
    out = _out(execution_viability_reason="BID_OR_ASK_MISSING")
    live = {"morning_execution_mode": "POSTOPEN_CONTRACT_REFRESH", "live_contract_ask": 1.2}
    result = mg.postopen_quote_unavailable_override(out, live)
    assert result["execution_viability_reason"] == "NO_CURRENT_EXECUTABLE_QUOTE"
    assert result["execution_viability_domain_reason"] == "BID_OR_ASK_MISSING"


def test_a_two_sided_quote_without_a_provider_timestamp_is_provider_timestamp_missing():
    out = _out(execution_viability_state="CURRENT_QUOTE_UNAVAILABLE",
               execution_viability_reason="PROVIDER_QUOTE_TIMESTAMP_REQUIRED")
    live = {"morning_execution_mode": "POSTOPEN_CONTRACT_REFRESH", "live_contract_bid": 1.0, "live_contract_ask": 1.2}
    result = mg.postopen_quote_unavailable_override(out, live)
    assert result["execution_viability_reason"] == "PROVIDER_TIMESTAMP_MISSING"
    assert result["execution_viability_domain_reason"] == "PROVIDER_QUOTE_TIMESTAMP_REQUIRED"
    assert result["execution_viability_reversible"] is True


def test_a_stamped_quote_is_not_overridden():
    live = {"morning_execution_mode": "POSTOPEN_CONTRACT_REFRESH", "live_contract_bid": 1.0,
            "live_contract_ask": 1.2, "live_contract_provider_updated": TS}
    assert mg.postopen_quote_unavailable_override(_out(), live) == {}


def test_the_eod_quote_timestamp_counts_as_a_provider_timestamp_as_today():
    live = {"morning_execution_mode": "POSTOPEN_CONTRACT_REFRESH", "selected_quote_timestamp_utc": TS}
    assert mg.postopen_quote_unavailable_override(_out(), live) == {}


def test_outside_postopen_mode_nothing_is_overridden():
    assert mg.postopen_quote_unavailable_override(_out(), {"morning_execution_mode": "PREOPEN_THESIS_CHECK"}) == {}
    assert mg.postopen_quote_unavailable_override(_out(), {}) == {}


def test_the_lab_book_projection_carries_the_new_fields():
    from contracts import lab_control
    source = Path(lab_control.__file__).read_text(encoding="utf-8")
    for field in ("execution_viability_domain_reason", "execution_viability_reversible", "execution_viability_recheck"):
        assert field in lab_control.FINAL_BOOK_FIELDS, field
        assert source.count(f'"{field}"') >= 2, field          # the field list and the projection
