from __future__ import annotations

from contracts.lab_control import resolve_lab_tradeability


def _signal(ev_decision: str, rr: object) -> dict:
    return {
        "ticker": "AAA",
        "options_verdict": "EXECUTE",
        "campaign_verdict": "READY_EXECUTE",
        "execution_verdict": "BUY_NOW",
        "thesis_decision": "GO",
        "strike": 100,
        "expiry": "2099-02-01",
        "premium_mid": 1.25,
        "spread_pct": 0.05,
        "mv__morning_execution_permission": "GO",
        "mv__execution_permission": "GO",
        "mv__live_validation_state": "CONFIRMED",
        "ev2_decision_hint": ev_decision,
        "rr_options": rr,
    }


def _resolve(ev_decision: str, rr: object) -> dict:
    return resolve_lab_tradeability(
        _signal(ev_decision, rr),
        {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
    )


def test_only_monetisable_economics_can_be_go() -> None:
    for ev_decision in ("MODERATE", "STRONG"):
        result = _resolve(ev_decision, 1.5)
        assert result["lab_verdict"] == "GO"
        assert result["lab_tradeable"] is True

    for ev_decision in ("WEAK", "AVOID"):
        result = _resolve(ev_decision, 1.5)
        assert result["lab_verdict"] != "GO"
        assert result["lab_tradeable"] is False

    for rr in (0, "", None):
        result = _resolve("MODERATE", rr)
        assert result["lab_verdict"] != "GO"
        assert result["lab_tradeable"] is False
