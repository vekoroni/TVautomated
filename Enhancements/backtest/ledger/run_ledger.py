"""Backtest ledger — every change measured against the same frozen history (ACK 18 Sep 2026).

Each run applies the CURRENTLY SHIPPED ticket rules (``avshunter.c12_outcome.signals``: prepare-equivalent inputs,
``decide``, ``rank_tickets``, ``apply_daily_cap``, ``plan_exit``) and the shipped value model to a frozen
reference set of point-in-time candidates, marks every exit from the stored chain under three fill models, and
appends one record to ``ledger.jsonl``:

  git commit (and whether the tree was dirty), configuration snapshot id, dataset hash, trial number, label,
  tickets per session, and the headline measures for tickets, all candidates and the top cautious quintile.

Frozen reference: ``Enhancements/backtest/signal_ticket_backtest_rows.csv`` (9 sessions, 31 Aug - 16 Sep 2026,
recorded thesis and quote, Layer 3 forecast recomputed from bars up to each session). Its sha256 is the dataset
hash; a changed file is a different dataset and is reported as such, never compared silently.

Every run increments the trial count — the number the multiple-testing controls need.

Usage:
  python Enhancements/backtest/ledger/run_ledger.py --label "what changed"
  python Enhancements/backtest/ledger/run_ledger.py --show            (comparison table only)
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from avshunter.c12_outcome import signals as sig  # noqa: E402
from avshunter.c12_outcome.adapters import prices  # noqa: E402
from avshunter.config.adapters import load_registry  # noqa: E402
from avshunter.shared.xnys_calendar import is_xnys_session, previous_xnys_session  # noqa: E402
import empirical_option_ev as ev  # noqa: E402

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "ledger.jsonl"
REFERENCE = REPO / "Enhancements" / "backtest" / "signal_ticket_backtest_rows.csv"
PRICE_DB = REPO / "data" / "canonical" / "historical_prices.sqlite"
CHAIN_DB = REPO / "data" / "phantom" / "phantom_history.db"
CALIBRATION = json.loads((REPO / "config" / "calibration" / "volatility_range_calibration_v1.json")
                         .read_text(encoding="utf-8"))
FILL_MODELS = {"quoted": 1.00, "timed": 0.30, "mid": 0.00}   # effective fraction of the half-spread paid
RULES_SESSION = date(2026, 9, 18)                            # resolve the governed rules as they stand today


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git_state() -> tuple[str, bool]:
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPO,
                                capture_output=True, text=True).stdout.strip())
    return commit, dirty


def last_usable(expiry: date, buffer_sessions: int) -> date:
    session = expiry if is_xnys_session(expiry) else previous_xnys_session(expiry)
    for _ in range(buffer_sessions):
        session = previous_xnys_session(session)
    return session


def prepared_for(row, s: sig.SignalSettings) -> tuple[str | None, sig.Prepared | None]:
    """The inputs a live ticket carries, rebuilt from a frozen candidate row, including the shipped contract guard."""
    session = date.fromisoformat(row.session)
    match = sig.OCC.match(row.contract)
    expiry = sig.contract_expiry(row.contract)
    if not match or expiry is None:
        return "CONTRACT_UNPARSEABLE", None
    strike = int(match["strike"]) / 1000.0
    guard = sig.contract_guard(row.direction, strike, row.spot, expiry, int(row.hold), session, s)
    if guard is not None:
        return guard, None
    usable = last_usable(expiry, s.contract_exit_buffer)
    executable = bool(row.entry_bid > 0 and row.entry_ask >= row.entry_bid and usable > session)
    return None, sig.Prepared(
        ticker=row.ticker, direction=row.direction, contract_symbol=row.contract, strike=strike, expiry=expiry,
        last_usable_session=usable, live_spot=row.spot, live_spot_utc=None, stop=row.stop, target=row.target,
        hold_sessions=int(row.hold), quote_bid=row.entry_bid, quote_ask=row.entry_ask, quote_timestamp_utc=None,
        quote_state=sig.QUOTE_CURRENT_SESSION, adjustment_state="EVENING_CLOSE_QUOTE", spot_at_quote=None, delta=None,
        shift=None, bid=row.entry_bid, ask=row.entry_ask, option_executable=executable, iv=row.iv,
        iv_source="EVENING_CONTRACT",
        path_inputs=dict(side="call" if row.direction == "CALL" else "put", spot=row.spot, strike=strike, dte=row.dte,
                         bid=row.entry_bid, ask=row.entry_ask, iv=row.iv, rate=ev.DEFAULT_RISK_FREE_RATE,
                         target=row.target, invalidation=row.stop, hold_sessions=int(row.hold),
                         forecast_vol=row.forecast_vol, share_spread=None))


def fill_price(bid: float, ask: float, fraction: float, entry: bool) -> float | None:
    if bid is None or ask is None or not np.isfinite(bid) or not np.isfinite(ask) or ask <= 0 or ask < bid:
        return None
    mid, half = (bid + ask) / 2.0, (ask - bid) / 2.0
    value = mid + fraction * half if entry else mid - fraction * half
    return value if value > 0 else None


def measure(group: pd.DataFrame, column: str) -> dict:
    values = group[column].dropna()
    if values.empty:
        return {"closed": 0}
    return {"closed": int(len(values)), "mean": round(float(values.mean()), 4),
            "median": round(float(values.median()), 4), "hit_rate": round(float((values > 0).mean()), 4),
            "share_ge_100pct": round(float((values >= 1).mean()), 4)}


def run(label: str, overrides: dict | None = None) -> dict:
    snapshot = load_registry().resolve(RULES_SESSION)
    s = sig.settings_from_snapshot(snapshot)
    if overrides:                      # an experiment, recorded in the ledger; never a production change
        s = replace(s, **overrides)
    frame = pd.read_csv(REFERENCE).dropna(subset=["spot", "stop", "target", "hold", "dte", "iv", "forecast_vol",
                                                  "entry_bid", "entry_ask"])
    frame = frame.drop_duplicates(["session", "ticker"])
    bars = prices.load_bars({str(t).upper() for t in frame.ticker}, date.fromisoformat(min(frame.session)),
                            prices.latest_session(PRICE_DB), PRICE_DB)
    as_of = prices.latest_session(PRICE_DB)
    chain = sqlite3.connect(f"file:{CHAIN_DB.as_posix()}?mode=ro", uri=True)
    decided_by_session: dict[str, list] = {}
    rows, reasons = [], {}
    try:
        for row in frame.itertuples():
            reason, prepared = prepared_for(row, s)
            valuation = None
            if reason is None:
                valuation = ev.compute_path_expression_ev(**prepared.path_inputs, calibration=CALIBRATION,
                                                          paths=ev.PATH_SETTINGS["paths"], seed=ev.PATH_SETTINGS["seed"])
                reason, fields = sig.decide(prepared, valuation, s)
                if reason is None:
                    decided_by_session.setdefault(row.session, []).append((row.ticker, fields, row))
            if reason is not None:
                key = reason.split(":")[0]
                reasons[key] = reasons.get(key, 0) + 1
        issued_rows = []
        tickets_per_session = {}
        for session, decided in sorted(decided_by_session.items()):
            ranked = sig.rank_tickets([(t, f) for t, f, _ in decided], {}, s, run_id="LEDGER",
                                      evidence_session=date.fromisoformat(session),
                                      issue_session=date.fromisoformat(session), h9r_tickers=set())
            issued, held_back = sig.apply_daily_cap(ranked, s)
            reasons["RANK_BELOW_DAILY_CAP"] = reasons.get("RANK_BELOW_DAILY_CAP", 0) + len(held_back)
            tickets_per_session[session] = len(issued)
            issued_tickers = {t.ticker for t in issued}
            for ticket in ranked:
                history = [b for b in bars.get(ticket.ticker, []) if b.session >= ticket.issue_session]
                plan = sig.plan_exit(ticket, history, as_of)
                record = {"session": session, "ticker": ticket.ticker, "rank": ticket.rank,
                          "issued": ticket.ticker in issued_tickers, "cautious": ticket.r_cautious,
                          "exit_reason": plan.reason, "state": plan.state}
                if plan.state == sig.EXITED:
                    quote = chain.execute(
                        "SELECT bid, ask FROM chain_snapshots WHERE ticker = ? AND quote_date = ? AND option_symbol = ?",
                        (ticket.ticker, plan.session.isoformat(), ticket.contract_symbol)).fetchone()
                    for name, fraction in FILL_MODELS.items():
                        entry = fill_price(ticket.quote_bid, ticket.quote_ask, fraction, entry=True)
                        exit_value = None if quote is None else fill_price(quote[0], quote[1], fraction, entry=False)
                        record[f"return_{name}"] = (None if entry is None or exit_value is None
                                                    else exit_value / entry - 1.0)
                issued_rows.append(record)
    finally:
        chain.close()
    scored = pd.DataFrame(issued_rows)
    if scored.empty:
        scored = pd.DataFrame(columns=["issued", "cautious"] + [f"return_{m}" for m in FILL_MODELS])
    tickets = scored[scored.issued] if len(scored) else scored
    top = scored[scored.cautious >= scored.cautious.quantile(0.8)] if len(scored) else scored
    commit, dirty = git_state()
    history = read_ledger()
    record = {
        "trial": len(history) + 1, "label": label,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": commit, "git_dirty": dirty, "config_snapshot_id": snapshot.snapshot_id,
        "signal_version": s.signal_version, "settings_overrides": overrides or {}, "dataset": REFERENCE.name, "dataset_sha256": sha256(REFERENCE),
        "reference_candidates": int(len(frame)), "eligible_candidates": int(len(scored)),
        "tickets_per_session": tickets_per_session,
        "mean_tickets_per_session": round(float(np.mean(list(tickets_per_session.values()))), 2)
        if tickets_per_session else 0.0,
        "sessions_with_zero_tickets": int(sum(1 for v in tickets_per_session.values() if v == 0))
        + int(len(set(frame.session)) - len(tickets_per_session)),
        "rejections": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        "tickets": {m: measure(tickets, f"return_{m}") for m in FILL_MODELS},
        "eligible_all": {m: measure(scored, f"return_{m}") for m in FILL_MODELS},
        "eligible_top_quintile": {m: measure(top, f"return_{m}") for m in FILL_MODELS},
    }
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return record


def read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()]


def show() -> None:
    history = read_ledger()
    if not history:
        print("ledger is empty")
        return
    lines = []
    for r in history:
        t = r["tickets"]["timed"]
        a = r["eligible_all"]["timed"]
        lines.append({
            "trial": r["trial"], "commit": r["git_commit"] + ("*" if r["git_dirty"] else ""),
            "label": r["label"][:40], "overrides": ",".join(f"{k}={v}" for k, v in r.get("settings_overrides", {}).items()) or "-",
            "dataset": r["dataset_sha256"][:8],
            "tickets/session": r["mean_tickets_per_session"], "zero days": r["sessions_with_zero_tickets"],
            "tickets closed": t.get("closed", 0), "tickets mean (timed)": t.get("mean"),
            "tickets hit": t.get("hit_rate"), "eligible closed": a.get("closed", 0),
            "eligible mean (timed)": a.get("mean"), "eligible >=+100%": a.get("share_ge_100pct")})
    print(pd.DataFrame(lines).to_string(index=False))
    datasets = {r["dataset_sha256"] for r in history}
    if len(datasets) > 1:
        print("\nWARNING: more than one reference dataset in the ledger; compare only rows with the same dataset hash.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--override", action="append", default=[],
                        help="experiment only: signal setting=value, e.g. min_dte_cover=0")
    args = parser.parse_args()
    if not args.show:
        if not args.label:
            print("--label is required: say what changed", file=sys.stderr)
            return 2
        overrides = {}
        for item in args.override:
            key, _, value = item.partition("=")
            overrides[key] = type(getattr(sig.settings_from_snapshot(load_registry().resolve(RULES_SESSION)), key))(value)
        record = run(args.label, overrides)
        print(json.dumps({k: record[k] for k in ("trial", "label", "git_commit", "git_dirty",
                                                 "mean_tickets_per_session", "sessions_with_zero_tickets",
                                                 "rejections", "tickets", "eligible_all")}, indent=2))
    print()
    show()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
