"""
AVSHUNTER Exit Discipline Engine — Sprint 1
Reads open positions from trade journal (read-only) and cross-references
morning validated trades to produce exit signals for each open position.

Output: data/output/runs/<run_id>/morning_exit_signals.csv
CLI:    python avshunter_exit_engine.py [--run-id RID] [--test-mode]
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = ROOT / "data" / "journal" / "trade_journal.db"
DEFAULT_RUNS_DIR = ROOT / "data" / "output" / "runs"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EXIT_ENGINE] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("avshunter.exit_engine")


# ── Exit verdict constants ─────────────────────────────────────────────────────

TAKE_PARTIAL = "TAKE_PARTIAL"
TAKE_FULL = "TAKE_FULL"
TRAIL = "TRAIL"
HOLD = "HOLD"
EMERGENCY_EXIT = "EMERGENCY_EXIT"
DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _f(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip().replace("$", "").replace("%", "").replace(",", "")
    if text.upper() in {"", "NONE", "NAN", "NULL", "N/A"}:
        return default
    try:
        return float(text)
    except Exception:
        return default


def _s(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _u(value: Any) -> str:
    return _s(value).upper()


def _today_date() -> date:
    return datetime.now(timezone.utc).date()


def _days_held(entry_date_str: str) -> int:
    try:
        entry = date.fromisoformat(str(entry_date_str)[:10])
        return (_today_date() - entry).days
    except Exception:
        return 0


def _latest_run_id(runs_dir: Path) -> Optional[str]:
    latest_json = runs_dir.parent / "latest.json"
    if latest_json.exists():
        try:
            import json
            payload = json.loads(latest_json.read_text(encoding="utf-8-sig"))
            rid = payload.get("run_id") or payload.get("latest_run_id")
            if rid:
                return str(rid)
        except Exception:
            pass
    if not runs_dir.exists():
        return None
    dirs = [p.name for p in runs_dir.iterdir() if p.is_dir()]
    return sorted(dirs)[-1] if dirs else None


def _read_csv(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    for row in rows[1:]:
        for k in row:
            if k not in fields:
                fields.append(k)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ── Journal read (read-only) ──────────────────────────────────────────────────

def _get_open_positions(db_path: Path) -> List[Dict[str, Any]]:
    if not db_path.exists():
        log.info("Trade journal not found at %s — no open positions", db_path)
        return []
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM trades ORDER BY entry_date DESC, trade_id DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as exc:
        log.warning("Could not read open positions from journal: %s", exc)
        return []


# ── Morning validated trades lookup ──────────────────────────────────────────

def _find_morning_validated_csv(run_id: str, runs_dir: Path) -> Optional[Path]:
    candidates = [
        runs_dir / run_id / "morning_validation" / f"morning_validated_trades_{run_id}.csv",
        runs_dir / run_id / f"morning_validated_trades_{run_id}.csv",
    ]
    for p in candidates:
        if p.exists():
            return p
    # glob fallback
    run_dir = runs_dir / run_id
    if run_dir.exists():
        matches = sorted(run_dir.rglob("morning_validated_trades_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if matches:
            return matches[0]
    return None


def _build_morning_index(morning_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for row in morning_rows:
        ticker = _u(row.get("ticker"))
        if ticker and ticker not in index:
            index[ticker] = row
    return index


# ── Trigger evaluation ────────────────────────────────────────────────────────

def _evaluate_triggers(
    pos: Dict[str, Any],
    morning_row: Optional[Dict[str, Any]],
    current_premium: float,
) -> Tuple[str, str, float, str, str]:
    """
    Returns (verdict, trigger_name, exit_size_pct, reason, urgency).
    Triggers evaluated in priority order: T1 → T2 → T3 → T4 → T5.
    """
    entry_premium = float(pos.get("entry_premium") or 0)
    dte_at_entry = int(pos.get("dte_at_entry") or 0)
    entry_date_str = _s(pos.get("entry_date"))
    days_held_n = _days_held(entry_date_str)
    dte_remaining = max(0, dte_at_entry - days_held_n)
    direction = _u(pos.get("options_direction") or pos.get("direction") or "")

    if entry_premium <= 0:
        return HOLD, "NO_TRIGGER", 0.0, "Entry premium invalid — cannot evaluate", "MONITOR"

    gain_pct = (current_premium - entry_premium) / entry_premium
    r_realised = round(gain_pct, 3)

    # ── TRIGGER 1 — Time Stop ────────────────────────────────────────────────
    if dte_remaining <= 5:
        return (
            TAKE_FULL,
            "TRIGGER_1_TIME_STOP",
            1.0,
            f"DTE remaining {dte_remaining} <= 5 — time stop breached regardless of P&L",
            "TODAY",
        )
    if dte_at_entry > 0 and days_held_n > dte_at_entry * 0.75:
        return (
            TAKE_PARTIAL,
            "TRIGGER_1_TIME_DECAY",
            0.5,
            f"Days held ({days_held_n}) exceeds 75% of DTE at entry ({dte_at_entry}) — front-loaded edge closing",
            "TODAY",
        )

    # ── TRIGGER 2 — Profit Capture ───────────────────────────────────────────
    if gain_pct >= 2.5:
        return (
            TAKE_FULL,
            "TRIGGER_2_TARGET_HIT",
            1.0,
            f"2.5R target achieved — gain {gain_pct:.1%} (entry ${entry_premium:.2f} → current ${current_premium:.2f})",
            "TODAY",
        )
    if gain_pct >= 1.0:
        return (
            TAKE_PARTIAL,
            "TRIGGER_2_PROFIT_CAPTURE",
            0.5,
            f"1R achieved — gain {gain_pct:.1%}. Exit 50%, trail remainder to 2.5R target",
            "TODAY",
        )
    if gain_pct >= 0.5 and days_held_n > 10:
        return (
            TAKE_PARTIAL,
            "TRIGGER_2_FRONT_LOADED",
            0.5,
            f"50%+ gain ({gain_pct:.1%}) with {days_held_n} days held — front-loaded edge window closing",
            "TODAY",
        )

    # ── TRIGGER 3 — Thesis Integrity ─────────────────────────────────────────
    if morning_row is not None:
        morning_perm = _u(morning_row.get("morning_execution_permission") or morning_row.get("execution_permission"))
        thesis_state = _u(morning_row.get("thesis_validity_state") or "")
        validation_state = _u(morning_row.get("live_validation_state") or "")

        if morning_perm in {"BLOCKED"} or thesis_state in {"THESIS_FAILED", "INVALIDATED"}:
            return (
                TAKE_FULL,
                "TRIGGER_3_MORNING_GATE_BLOCKED",
                1.0,
                f"Morning gate returned {morning_perm} — thesis integrity failed. Exit position",
                "TODAY",
            )

        evening_phase = _u(morning_row.get("evening_hidden_state_label") or pos.get("hidden_state_label") or "")
        entry_phase_stored = _u(pos.get("wyckoff_phase") or pos.get("evening_hidden_state_label") or "")
        if (
            entry_phase_stored
            and evening_phase
            and entry_phase_stored != evening_phase
            and "PHASE" in entry_phase_stored
        ):
            return (
                TAKE_FULL,
                "TRIGGER_3_PHASE_CHANGE",
                1.0,
                f"Wyckoff phase changed from {entry_phase_stored} to {evening_phase} — thesis invalidated",
                "TODAY",
            )

        control_state = _u(morning_row.get("control_state") or morning_row.get("evening_hidden_state_label") or "")
        if direction == "CALL" and "BEARISH" in control_state and "SHIFTING" in control_state:
            return (
                TAKE_FULL,
                "TRIGGER_3_CONTROL_ADVERSE",
                1.0,
                f"Control state {control_state} is adverse to CALL thesis — exit",
                "TODAY",
            )
        if direction == "PUT" and "BULLISH" in control_state and "SHIFTING" in control_state:
            return (
                TAKE_FULL,
                "TRIGGER_3_CONTROL_ADVERSE",
                1.0,
                f"Control state {control_state} is adverse to PUT thesis — exit",
                "TODAY",
            )

    # ── TRIGGER 4 — IV Crush Warning ─────────────────────────────────────────
    ivp: Optional[float] = None
    if morning_row is not None:
        ivp = _f(morning_row.get("morning_iv_rank"), None)
        if ivp is None:
            ivp = _f(morning_row.get("iv_rank") or morning_row.get("ivp") or morning_row.get("morning_iv_rank"), None)
    if ivp is None:
        ivp = _f(pos.get("ivp_at_entry"), None)

    iv_hv_ratio = _f(pos.get("iv_vs_hv_at_entry"), None)

    if ivp is not None and ivp > 70 and dte_remaining <= 10:
        return (
            TAKE_FULL,
            "TRIGGER_4_IV_CRUSH_IMMINENT",
            1.0,
            f"IVP {ivp:.0f} > 70 with only {dte_remaining} DTE remaining — IV crush imminent",
            "TODAY",
        )
    if iv_hv_ratio is not None and iv_hv_ratio > 1.5 and days_held_n > 5:
        return (
            TAKE_PARTIAL,
            "TRIGGER_4_IV_HV_ELEVATED",
            0.5,
            f"IV/HV ratio {iv_hv_ratio:.2f} > 1.5 with {days_held_n} days held — trim exposure",
            "THIS_WEEK",
        )

    # ── TRIGGER 5 — Wall Dynamics ─────────────────────────────────────────────
    live_price: Optional[float] = None
    if morning_row is not None:
        live_price = _f(morning_row.get("live_price") or morning_row.get("live_mid"), None)

    call_wall = _f(pos.get("call_wall"), None)
    put_wall = _f(pos.get("put_wall"), None)

    if live_price is not None and live_price > 0:
        if direction == "CALL" and call_wall is not None and live_price > call_wall * 1.005:
            return (
                EMERGENCY_EXIT,
                "TRIGGER_5_CALL_WALL_BROKEN",
                1.0,
                f"Price ${live_price:.2f} has breached call wall ${call_wall:.2f} — EMERGENCY EXIT",
                "TODAY",
            )
        if direction == "PUT" and put_wall is not None and live_price < put_wall * 0.995:
            return (
                EMERGENCY_EXIT,
                "TRIGGER_5_PUT_WALL_BROKEN",
                1.0,
                f"Price ${live_price:.2f} has breached put wall ${put_wall:.2f} — EMERGENCY EXIT",
                "TODAY",
            )

    # ── No trigger fired ─────────────────────────────────────────────────────
    if gain_pct > 0.25:
        return (
            TRAIL,
            "NO_TRIGGER",
            0.0,
            f"Position up {gain_pct:.1%} — no exit trigger. Trail with thesis intact",
            "MONITOR",
        )
    return (
        HOLD,
        "NO_TRIGGER",
        0.0,
        f"Position within normal parameters — gain {gain_pct:.1%}, DTE remaining {dte_remaining}",
        "MONITOR",
    )


# ── Core engine ───────────────────────────────────────────────────────────────

def build_exit_signals(
    run_id: str,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    db_path: Path = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    open_positions = _get_open_positions(db_path)
    if not open_positions:
        log.info("No open positions in trade journal — exit engine complete with no signals")
        return []

    log.info("Exit engine: evaluating %d open position(s)", len(open_positions))

    morning_csv = _find_morning_validated_csv(run_id, runs_dir)
    if morning_csv:
        morning_rows = _read_csv(morning_csv)
        morning_index = _build_morning_index(morning_rows)
        log.info("Morning validated trades loaded: %d rows from %s", len(morning_rows), morning_csv.name)
    else:
        morning_index = {}
        log.warning("Morning validated trades CSV not found for run %s — live premium unavailable", run_id)

    exit_signals: List[Dict[str, Any]] = []
    today = _today_date()

    for pos in open_positions:
        ticker = _u(pos.get("ticker") or "")
        trade_id = pos.get("trade_id")
        entry_premium = _f(pos.get("entry_premium"), None)
        dte_at_entry = int(pos.get("dte_at_entry") or 0)
        days_held_n = _days_held(_s(pos.get("entry_date")))
        dte_remaining = max(0, dte_at_entry - days_held_n)
        direction = _u(pos.get("options_direction") or "")

        morning_row = morning_index.get(ticker)

        # Resolve current premium from morning live data
        current_premium: Optional[float] = None
        if morning_row is not None:
            current_premium = _f(
                morning_row.get("live_contract_mid")
                or morning_row.get("live_mid")
                or morning_row.get("live_contract_ask"),
                None,
            )

        if current_premium is None or current_premium <= 0:
            signal: Dict[str, Any] = {
                "ticker": ticker,
                "trade_id": trade_id,
                "direction": direction,
                "entry_premium": entry_premium,
                "current_premium": None,
                "gain_pct": None,
                "days_held": days_held_n,
                "dte_remaining": dte_remaining,
                "exit_verdict": DATA_UNAVAILABLE,
                "exit_trigger": "NO_TRIGGER",
                "exit_size_pct": 0.0,
                "reason": "Current premium unavailable from morning live data — cannot evaluate exit",
                "urgency": "MONITOR",
                "r_realised": None,
                "r_remaining": None,
                "run_id": run_id,
                "evaluated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            }
            exit_signals.append(signal)
            log.warning("[%s] trade_id=%s — DATA_UNAVAILABLE: no live contract mid", ticker, trade_id)
            continue

        if entry_premium is None or entry_premium <= 0:
            log.warning("[%s] trade_id=%s — entry_premium missing, skipping", ticker, trade_id)
            continue

        gain_pct = (current_premium - entry_premium) / entry_premium
        r_realised = round(gain_pct, 3)

        # 2.5R target premium
        r25_target_premium = entry_premium * 3.5
        r_remaining = round(max(0.0, (r25_target_premium - current_premium) / entry_premium), 3)

        verdict, trigger_name, exit_size_pct, reason, urgency = _evaluate_triggers(
            pos, morning_row, current_premium
        )

        signal = {
            "ticker": ticker,
            "trade_id": trade_id,
            "direction": direction,
            "entry_premium": round(entry_premium, 4),
            "current_premium": round(current_premium, 4),
            "gain_pct": round(gain_pct, 4),
            "days_held": days_held_n,
            "dte_remaining": dte_remaining,
            "exit_verdict": verdict,
            "exit_trigger": trigger_name,
            "exit_size_pct": exit_size_pct,
            "reason": reason,
            "urgency": urgency,
            "r_realised": r_realised,
            "r_remaining": r_remaining if verdict in {TRAIL, TAKE_PARTIAL} else 0.0,
            "run_id": run_id,
            "evaluated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        }
        exit_signals.append(signal)

        log.info(
            "[%s] trade_id=%s  verdict=%-15s  trigger=%s  gain=%+.1f%%  DTE_rem=%d",
            ticker,
            trade_id,
            verdict,
            trigger_name,
            gain_pct * 100,
            dte_remaining,
        )

        # Print suggested exit command for actionable verdicts
        if verdict in {TAKE_PARTIAL, TAKE_FULL, EMERGENCY_EXIT}:
            _print_exit_command(signal)

    return exit_signals


def _print_exit_command(signal: Dict[str, Any]) -> None:
    verdict = signal["exit_verdict"]
    trade_id = signal["trade_id"]
    current_premium = signal.get("current_premium") or 0.0
    trigger = signal["exit_trigger"]
    ticker = signal["ticker"]
    gain_pct = (signal.get("gain_pct") or 0) * 100

    border = "═" * 70
    print(f"\n{border}")
    print(f"  EXIT SIGNAL — {ticker}  |  {verdict}  |  gain={gain_pct:+.1f}%")
    print(f"{border}")
    print(f"  {signal['reason']}")
    print(f"\n  SUGGESTED EXIT COMMAND:")
    print(
        f"  python avshunter_trade_journal.py log-exit "
        f"--trade-id {trade_id} "
        f"--exit-premium {current_premium:.2f} "
        f'--exit-reason "{trigger} — {signal["reason"][:60]}"'
    )
    print(f"{border}\n")


def run_exit_engine(
    run_id: Optional[str] = None,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    db_path: Path = DEFAULT_DB_PATH,
    output_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    rid = run_id or _latest_run_id(runs_dir)
    if not rid:
        log.warning("No run_id found — exit engine aborted")
        return []

    signals = build_exit_signals(rid, runs_dir, db_path)

    if not signals:
        log.info("Exit engine: no signals produced (no open positions or all DATA_UNAVAILABLE)")
        return signals

    out = output_path or (runs_dir / rid / "morning_exit_signals.csv")
    _write_csv(out, signals)
    log.info("Exit signals written: %d row(s) → %s", len(signals), out)

    # Summary print
    verdicts: Dict[str, int] = {}
    for s in signals:
        v = s.get("exit_verdict", "UNKNOWN")
        verdicts[v] = verdicts.get(v, 0) + 1
    print(f"\n[EXIT ENGINE] run_id={rid}  positions={len(signals)}  verdicts={verdicts}", flush=True)

    return signals


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="AVSHUNTER Exit Discipline Engine")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Run against latest run_id, print signals to console, exit",
    )
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir)
    db_path = Path(args.db)
    output_path = Path(args.output) if args.output else None

    if args.test_mode:
        log.info("TEST MODE — exit engine dry-run against latest available run")

    signals = run_exit_engine(
        run_id=args.run_id,
        runs_dir=runs_dir,
        db_path=db_path,
        output_path=output_path,
    )

    if args.test_mode:
        import json
        print(json.dumps(signals, indent=2, default=str))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
