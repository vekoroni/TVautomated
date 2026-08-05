"""Smoke test for Big Bang Phase 6/7 Intelligence Lab wiring.

This script only exercises the local Lab API. It never places broker orders.
If --safe-test-mode is used, it submits a journal/API paper entry only when the
latest run already has a Lab GO candidate.
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen


def call(base: str, path: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(
        base.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    with urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:5002/api")
    parser.add_argument("--safe-test-mode", action="store_true")
    args = parser.parse_args()
    base = args.base_url

    try:
        health = call(base, "/health")
        status = call(base, "/orchestrator/status")
        run = call(base, "/run/latest")
        book = call(base, "/opportunity_book/latest")
    except URLError as exc:
        print(f"FAIL: Intelligence Lab API unavailable: {exc}")
        return 2

    signals = run.get("signals", [])
    missing = [
        s.get("ticker", "?")
        for s in signals
        if not all(k in s for k in ("lab_verdict", "lab_tradeable", "conflict_state"))
    ]
    if missing:
        print(f"FAIL: missing lab fields for {len(missing)} signals")
        print(missing[:20])
        return 1

    counts = {"GO": 0, "ARMED": 0, "WAIT": 0, "BLOCKED": 0}
    for sig in signals:
        verdict = str(sig.get("lab_verdict", "WAIT")).upper()
        counts[verdict] = counts.get(verdict, 0) + 1

    hard_actionable = [
        s.get("ticker")
        for s in signals
        if s.get("conflict_state") == "HARD_CONFLICT" and s.get("lab_tradeable")
    ]
    if hard_actionable:
        print(f"FAIL: hard-conflict signals marked tradeable: {hard_actionable[:20]}")
        return 1

    print("health:", health.get("status"), "latest:", health.get("latest_run"))
    print("orchestrator:", status.get("run_id"), status.get("run_health_score"), status.get("next_action"))
    print("signals:", len(signals), "counts:", counts)
    print("opportunity_book_rows:", (book.get("opportunity_book") or {}).get("candidate_count", 0))

    if args.safe_test_mode:
        go = next((s for s in signals if s.get("lab_verdict") == "GO" and s.get("lab_tradeable")), None)
        if not go:
            print("safe-test-mode: no GO candidate available, journal write skipped")
            return 0
        payload = {
            "run_id": run.get("run_id"),
            "ticker": go.get("ticker"),
            "entry_premium": float(go.get("premium_mid") or go.get("opt__premium_mid") or 0.01),
            "contracts": 1,
            "declared_R": 1.0,
            "invalidation_price": float(go.get("invalidation_price") or go.get("current_price") or 1.0),
            "trade_notes": "Phase 6/7 smoke test paper journal entry",
            "user_confirmed_live_validation": True,
        }
        entered = call(base, "/enter_trade", payload)
        if not entered.get("ok"):
            print("FAIL: safe test entry rejected:", entered)
            return 1
        positions = call(base, "/monitor_positions")
        if not positions.get("open_positions"):
            print("FAIL: entry did not appear in monitor_positions")
            return 1
        trade_id = entered.get("trade_id") or positions["open_positions"][0].get("trade_id")
        exit_payload = {
            "ticker": go.get("ticker"),
            "trade_id": trade_id,
            "exit_premium": payload["entry_premium"],
            "exit_reason": "SMOKE_TEST_FLAT",
            "notes": "Phase 6/7 smoke test close",
        }
        closed = call(base, "/log_exit", exit_payload)
        if not closed.get("ok"):
            print("FAIL: safe test exit failed:", closed)
            return 1
        outcomes = call(base, "/outcomes")
        learning = call(base, "/learning_feedback")
        print("safe-test-mode:", entered.get("trade_id"), closed.get("outcome_class"))
        print("outcomes:", outcomes.get("message"))
        print("learning:", learning.get("closed_trade_count"))

    print("PASS: Big Bang Phase 6/7 smoke checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
