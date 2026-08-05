"""Live UAT API smoke test for the Intelligence Lab.

This uses only the local Flask API and journal simulation. It never connects to
a broker and never places a real trade.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def call(base: str, path: str, payload: dict | None = None, timeout: int = 60) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(
        base.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body) if body else {}
        except Exception:
            payload = {"error": body}
        return exc.code, payload


def wait_health(base: str, seconds: int = 60) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            status, payload = call(base, "/health", timeout=5)
            if status == 200 and payload:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def start_server() -> subprocess.Popen:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    log_dir = ROOT / "data" / "output" / "qa"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = (log_dir / "live_uat_lab_server.log").open("a", encoding="utf-8")
    return subprocess.Popen(
        [sys.executable, str(ROOT / "intelligence-lab" / "intelligence_lab.py")],
        cwd=str(ROOT / "intelligence-lab"),
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
    )


def _f(value, default=0.0) -> float:
    try:
        text = str(value).replace("$", "").replace("%", "").strip()
        if text.lower() in {"", "none", "nan", "null"}:
            return default
        return float(text)
    except Exception:
        return default


def _entry_candidates(signals: list[dict]) -> list[dict]:
    candidates = []
    for sig in signals:
        if sig.get("lab_verdict") != "GO" or not sig.get("lab_tradeable"):
            continue
        premium = _f(sig.get("premium_mid") or sig.get("opt__premium_mid") or sig.get("contract_premium"), 0)
        strike = sig.get("strike") or sig.get("contract_strike") or sig.get("opt__contract_strike")
        expiry = sig.get("expiry") or sig.get("contract_expiry") or sig.get("opt__contract_expiry")
        if premium > 0 and strike and expiry:
            candidates.append(sig)
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:5002/api")
    parser.add_argument("--start-server", action="store_true")
    parser.add_argument("--test-journal-loop", action="store_true")
    args = parser.parse_args()

    server = None
    if args.start_server:
        try:
            call(args.base_url, "/health", timeout=3)
        except Exception:
            server = start_server()
    try:
        if not wait_health(args.base_url, seconds=90 if args.start_server else 10):
            print("FAIL: Intelligence Lab API unavailable")
            return 2

        checks: list[dict] = []

        def check(name: str, condition: bool, detail: dict | None = None):
            checks.append({"name": name, "passed": bool(condition), "detail": detail or {}})

        status, health = call(args.base_url, "/health")
        check("/api/health", status == 200 and bool(health), health)

        status, runs = call(args.base_url, "/runs")
        check("/api/runs", status == 200 and bool(runs), runs if isinstance(runs, dict) else {"payload": runs})

        status, run = call(args.base_url, "/run/latest", timeout=120)
        signals = run.get("signals", []) if isinstance(run, dict) else []
        check("/api/run/latest", status == 200 and bool(signals), {"signals": len(signals), "run_id": run.get("run_id") if isinstance(run, dict) else ""})

        status, orch = call(args.base_url, "/orchestrator/status", timeout=120)
        check("/api/orchestrator/status", status == 200 and bool(orch), orch)

        status, manifest = call(args.base_url, "/orchestrator/manifest/latest", timeout=120)
        check("/api/orchestrator/manifest/latest", status == 200 and bool(manifest), {"keys": list(manifest)[:10] if isinstance(manifest, dict) else []})

        status, book = call(args.base_url, "/opportunity_book/latest", timeout=120)
        check("/api/opportunity_book/latest", status == 200 and bool(book), {"status": status})

        missing_lab = [s.get("ticker", "?") for s in signals if not all(k in s for k in ("lab_verdict", "lab_tradeable", "conflict_state", "execution_lock_reason"))]
        check("every signal has lab fields", not missing_lab, {"missing_count": len(missing_lab), "sample": missing_lab[:10]})

        counts = {"GO": 0, "ARMED": 0, "WAIT": 0, "BLOCKED": 0}
        for sig in signals:
            verdict = str(sig.get("lab_verdict", "WAIT")).upper()
            counts[verdict] = counts.get(verdict, 0) + 1
        hard_tradeable = [s.get("ticker") for s in signals if s.get("conflict_state") == "HARD_CONFLICT" and s.get("lab_tradeable")]
        check("GO/ARMED/BLOCKED counts consistent", sum(counts.values()) == len(signals), {"counts": counts, "signals": len(signals)})
        check("HARD_CONFLICT cannot be tradeable", not hard_tradeable, {"hard_tradeable": hard_tradeable[:10]})

        blocked = next((s for s in signals if s.get("lab_verdict") == "BLOCKED" or s.get("conflict_state") == "HARD_CONFLICT"), None)
        if blocked:
            payload = {
                "run_id": run.get("run_id"),
                "ticker": blocked.get("ticker"),
                "entry_premium": max(_f(blocked.get("premium_mid"), 1.0), 0.01),
                "contracts": 1,
                "declared_R": 100,
                "invalidation_price": max(_f(blocked.get("invalidation_price") or blocked.get("current_price"), 1.0), 0.01),
                "user_confirmed_live_validation": True,
                "trade_notes": "LIVE_UAT_BLOCKED_ENTRY_TEST",
            }
            code, response = call(args.base_url, "/enter_trade", payload, timeout=120)
            check("BLOCKED cannot be entered through /api/enter_trade", code >= 400 or response.get("ok") is False, {"status": code, "response": response})
        else:
            check("BLOCKED cannot be entered through /api/enter_trade", False, {"error": "no blocked candidate available"})

        journal_detail = {"skipped": not args.test_journal_loop}
        if args.test_journal_loop:
            candidates = _entry_candidates(signals)
            candidate = None
            entered = None
            last_entry = None
            for maybe in candidates[:10]:
                candidate = maybe
                premium = _f(candidate.get("premium_mid") or candidate.get("opt__premium_mid") or candidate.get("contract_premium"), 0.01)
                payload = {
                    "run_id": run.get("run_id"),
                    "ticker": candidate.get("ticker"),
                    "entry_premium": premium,
                    "contracts": 1,
                    "declared_R": round(premium * 100, 2),
                    "invalidation_price": max(_f(candidate.get("invalidation_price") or candidate.get("current_price"), 1.0), 0.01),
                    "user_confirmed_live_validation": True,
                    "competition_trade_id": f"LIVE_UAT_SMOKE_{int(time.time())}",
                    "trade_notes": "LIVE UAT smoke test journal simulation only",
                }
                code, entered = call(args.base_url, "/enter_trade", payload, timeout=120)
                last_entry = {"ticker": candidate.get("ticker"), "status": code, "response": entered}
                if code < 400 and entered.get("ok"):
                    break
                candidate = None
            journal_detail["entry_attempts_available"] = len(candidates)
            journal_detail["entry_response"] = last_entry
            check("test-mode enter_trade writes journal OPEN row", bool(entered and entered.get("ok")), journal_detail)
            if entered and entered.get("ok"):
                code, positions = call(args.base_url, "/monitor_positions", timeout=120)
                trade_id = entered.get("trade_id")
                open_rows = positions.get("open_positions", []) if isinstance(positions, dict) else []
                found = any(str(r.get("trade_id")) == str(trade_id) for r in open_rows)
                check("/api/monitor_positions sees entered trade", code == 200 and found, {"trade_id": trade_id, "open_count": len(open_rows)})

                exit_payload = {
                    "ticker": candidate.get("ticker"),
                    "trade_id": trade_id,
                    "exit_premium": payload["entry_premium"],
                    "exit_reason": "LIVE_UAT_SMOKE_FLAT",
                    "notes": "Closed by live UAT smoke test",
                }
                code, closed = call(args.base_url, "/log_exit", exit_payload, timeout=120)
                check("/api/log_exit closes test trade", code == 200 and closed.get("ok"), {"status": code, "response": closed})

                code, outcomes = call(args.base_url, "/outcomes", timeout=120)
                check("/api/outcomes returns realised results", code == 200 and outcomes.get("ok"), {"status": code, "message": outcomes.get("message")})

                code, learning = call(args.base_url, "/learning_feedback", timeout=120)
                check("/api/learning_feedback returns feedback", code == 200 and learning.get("ok"), {"status": code, "closed_trade_count": learning.get("closed_trade_count")})

        passed = all(c["passed"] for c in checks)
        report = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "passed": passed,
            "base_url": args.base_url,
            "run_id": run.get("run_id") if isinstance(run, dict) else "",
            "counts": counts,
            "checks": checks,
        }
        out_dir = ROOT / "data" / "output" / "qa"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "smoke_test_live_uat_pipeline_latest.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=True, default=str), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=True, default=str))
        return 0 if passed else 1
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except Exception:
                server.kill()


if __name__ == "__main__":
    raise SystemExit(main())
