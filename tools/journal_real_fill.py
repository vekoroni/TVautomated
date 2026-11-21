"""Record a real option fill (entry, and optionally its exit) in the trade journal with the
contract actually traded (22 Oct 2026).

avshunter_trade_journal.py log-entry takes strike, expiry and direction from the pipeline run's
contract. When the trade used a different contract (VALE: Nov 13 weekly 13P, not the run's), this
wrapper passes the real contract as overrides, then logs the exit. It writes only through the
journal's own log_entry / log_exit functions.

PowerShell, from the repo root:
  venv\\Scripts\\python.exe tools\\journal_real_fill.py --ticker VALE --run-id 20261017_155512 `
     --occ VALE261113P00013000 --entry 0.49 --entry-date 2026-10-19 --entry-time 12:53 `
     --exit 0.74 --exit-date 2026-10-22 --exit-time 09:30 --exit-reason "GTC target 0.71 filled at the open" `
     --notes "card 2026-10-19_VALE_PUT" --dry-run
Drop --dry-run to write.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import avshunter_trade_journal as tj  # noqa: E402  (the journal owns the writes)


def parse_occ(occ: str) -> dict:
    m = re.match(r"^([A-Z.]+)\s*(\d{2})(\d{2})(\d{2})([CP])(\d{8})$", occ.strip().upper())
    if not m:
        raise SystemExit(f"Not an OCC symbol: {occ}")
    root, yy, mm, dd, cp, k = m.groups()
    return {"root": root, "expiry": f"20{yy}-{mm}-{dd}", "options_direction": "CALL" if cp == "C" else "PUT",
            "strike": int(k) / 1000}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--occ", required=True, help="the contract actually traded, OCC format")
    ap.add_argument("--entry", required=True, type=float, help="fill price per share")
    ap.add_argument("--contracts", type=int, default=1)
    ap.add_argument("--entry-date", required=True)
    ap.add_argument("--entry-time", default="")
    ap.add_argument("--exit", type=float, help="exit fill per share (omit for an open trade)")
    ap.add_argument("--exit-date", default="")
    ap.add_argument("--exit-time", default="")
    ap.add_argument("--exit-reason", default="")
    ap.add_argument("--outcome-class", default="")
    ap.add_argument("--notes", default="")
    ap.add_argument("--thesis-id", default="", help="the hand-off thesis_id, so the decision ledger can link the outcome")
    ap.add_argument("--db", default="")
    ap.add_argument("--runs-dir", default=str(ROOT / "data" / "output" / "runs"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    c = parse_occ(a.occ)
    if c["root"] != a.ticker.upper():
        raise SystemExit(f"OCC root {c['root']} does not match ticker {a.ticker}")
    dte = (date.fromisoformat(c["expiry"]) - date.fromisoformat(a.entry_date)).days
    overrides = {"options_direction": c["options_direction"], "strike": c["strike"], "expiry": c["expiry"], "dte_at_entry": dte}
    if a.thesis_id: overrides["thesis_id"] = a.thesis_id
    db = Path(a.db) if a.db else tj.DEFAULT_DB_PATH
    notes = (a.notes + " | " if a.notes else "") + f"real contract {a.occ.upper()} (journal_real_fill)"

    print(f"Entry: {a.ticker} {c['options_direction']} {c['strike']} {c['expiry']} (DTE {dte}) x{a.contracts} at {a.entry} on {a.entry_date} {a.entry_time}")
    if a.exit is not None:
        pnl = (a.exit - a.entry) * 100 * a.contracts
        print(f"Exit:  {a.exit} on {a.exit_date} {a.exit_time} ({a.exit_reason}) -> {pnl:+.2f} USD, {(a.exit / a.entry - 1) * 100:+.1f}% on premium")
    print(f"Journal: {db}\nRuns dir: {a.runs_dir}")
    if a.dry_run:
        print("Dry run: nothing written.")
        return
    already = [t for t in tj.get_open_positions(db) if str(t.get("ticker", "")).upper() == a.ticker.upper()]
    if already:
        print(f"Note: {a.ticker} already has open journal trade(s): {[t.get('trade_id') for t in already]}")
    trade_id = tj.log_entry(db_path=db, runs_dir=Path(a.runs_dir), ticker=a.ticker.upper(), run_id=a.run_id,
                            entry_premium=a.entry, contracts=a.contracts, entry_date=a.entry_date,
                            entry_time=a.entry_time, notes=notes, **overrides)
    print(f"Entry logged: trade_id={trade_id}")
    if a.exit is not None:
        out = tj.log_exit(db_path=db, trade_id=trade_id, exit_premium=a.exit, exit_reason=a.exit_reason,
                          exit_date=a.exit_date, exit_time=a.exit_time, outcome_class=a.outcome_class, notes=notes)
        print(f"Exit logged: P&L {out['pnl_usd']:+.2f} USD ({out['pnl_pct_premium']:+.1f}%), hold {out['hold_days']} days")


if __name__ == "__main__":
    main()
