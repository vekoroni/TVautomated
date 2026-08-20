"""QA gate for the Intelligence Lab tradeability resolver.

Pure deterministic checks. No broker calls and no journal writes.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.lab_control import build_final_opportunity_book, resolve_lab_tradeability


def _manifest(mode: str = "EOD", stale_flags=None, fatal_flags=None):
    return {
        "pipeline_mode": mode,
        "stale_flags": stale_flags if stale_flags is not None else [],
        "fatal_flags": fatal_flags if fatal_flags is not None else [],
    }


def _base(**overrides):
    row = {
        "ticker": "AAA",
        "direction": "CALL",
        "strike": 100,
        "expiry": "2099-01-19",
        "premium_mid": 1.25,
        "spread_pct": 0.05,
        "options_verdict": "EXECUTE",
        "campaign_verdict": "READY_EXECUTE",
        "execution_verdict": "BUY_NOW",
        "thesis_decision": "GO",
    }
    row.update(overrides)
    return row


def main() -> int:
    results = []

    def check(name: str, condition: bool, detail: dict):
        results.append({"name": name, "passed": bool(condition), "detail": detail})

    r = resolve_lab_tradeability(_base(eil_v3_verdict="BLOCKED"), _manifest())
    check("EIL BLOCKED + thesis GO => BLOCKED", r["lab_verdict"] == "BLOCKED", r)

    r = resolve_lab_tradeability(_base(), _manifest())
    check("options EXECUTE + campaign READY + execution BUY_NOW => GO", r["lab_verdict"] == "GO" and r["lab_tradeable"], r)

    r = resolve_lab_tradeability(_base(execution_verdict="WAIT_RETEST"), _manifest())
    check("thesis GO + execution WAIT_RETEST is not GO", r["lab_verdict"] in {"ARMED", "WAIT"}, r)

    r = resolve_lab_tradeability(_base(sb_final_verdict="EXECUTE", options_verdict="STAND_DOWN"), _manifest())
    check("legacy EXECUTE + options STAND_DOWN => BLOCKED", r["lab_verdict"] == "BLOCKED", r)

    r = resolve_lab_tradeability(_base(strike="", expiry="", premium_mid=""), _manifest())
    check("missing premium/strike/expiry => BLOCKED", r["lab_verdict"] == "BLOCKED", r)

    r = resolve_lab_tradeability(_base(spread_pct=""), _manifest(stale_flags=["EOD_MORNING_VALIDATION_PENDING"]))
    check("EOD missing live spread => requires live validation", r["lab_verdict"] == "ARMED" and r["requires_live_validation"], r)

    r = resolve_lab_tradeability(_base(), _manifest(mode="LIVE"))
    check("LIVE missing morning validation => BLOCKED", r["lab_verdict"] == "BLOCKED", r)

    r = resolve_lab_tradeability(_base(mv__execution_permission="BLOCKED", mv__live_validation_state="REJECTED"), _manifest(mode="LIVE"))
    check("Morning Validator BLOCKED => BLOCKED", r["lab_verdict"] == "BLOCKED", r)

    r = resolve_lab_tradeability(_base(mv__execution_permission="GO", mv__live_validation_state="CONFIRMED"), _manifest(mode="LIVE"))
    check("Morning Validator GO + no hard veto => GO", r["lab_verdict"] == "GO" and r["lab_tradeable"], r)

    r = resolve_lab_tradeability(
        _base(),
        _manifest(),
        open_trades=[{"ticker": "AAA", "direction": "CALL", "strike": 100, "expiry": "2099-01-19"}],
    )
    check("duplicate open journal trade => BLOCKED", r["lab_verdict"] == "BLOCKED", r)

    signals = [
        _base(ticker="BAD", eil_v3_verdict="BLOCKED"),
        _base(ticker="GOOD"),
    ]
    book = build_final_opportunity_book("qa", signals, _manifest())
    hard_tradeable = [row for row in book if row["conflict_state"] == "HARD_CONFLICT" and row["lab_tradeable"]]
    check("HARD_CONFLICT excluded from actionable shortlist", not hard_tradeable, {"hard_tradeable": hard_tradeable})

    blocked = resolve_lab_tradeability(_base(eil_v3_verdict="BLOCKED"), _manifest())
    check("BLOCKED cannot be entered through resolver gate", not blocked["lab_tradeable"], blocked)

    passed = all(r["passed"] for r in results)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "results": results,
    }
    out_dir = ROOT / "data" / "output" / "qa"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "qa_conflict_resolver_latest.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=True, default=str))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
