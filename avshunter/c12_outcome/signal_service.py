"""Application service for signal tickets: issue from the morning book, score each evening, report (ACK 17 Sep 2026)."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import asdict, fields
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sqlite3
from typing import Callable, Mapping

from avshunter.config import ConfigSnapshot
from avshunter.shared.xnys_calendar import is_xnys_session, previous_xnys_session

from . import signals as sig
from .adapters import chains, intraday, prices, storage
from .expression import contract_expiry

REPO = Path(__file__).resolve().parents[2]
CALIBRATION_PATH = REPO / "config" / "calibration" / "volatility_range_calibration_v1.json"
TICKET_FIELDS = [f.name for f in fields(sig.SignalTicket)]


def _read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _last_usable(expiry: date, buffer_sessions: int) -> date:
    session = expiry if is_xnys_session(expiry) else previous_xnys_session(expiry)
    for _ in range(buffer_sessions):
        session = previous_xnys_session(session)
    return session


def default_revaluer() -> Callable[[dict], dict]:
    """The empirical value model with its governed calibration and path settings (no network, deterministic)."""
    import empirical_option_ev as ev

    calibration = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    if calibration.get("version") != "volatility_range_calibration_v1":
        raise ValueError("unsupported volatility range calibration")

    def revalue(inputs: dict) -> dict:
        return ev.compute_path_expression_ev(**inputs, calibration=calibration, paths=ev.PATH_SETTINGS["paths"],
                                             seed=ev.PATH_SETTINGS["seed"])
    return revalue


def default_rate() -> float:
    import empirical_option_ev as ev
    return float(ev.DEFAULT_RISK_FREE_RATE)


def _run_session(run_id: str) -> date | None:
    try:
        return date(int(run_id[:4]), int(run_id[4:6]), int(run_id[6:8]))
    except (TypeError, ValueError):
        return None


def issue_signals(connection: sqlite3.Connection, runs_dir: Path, run_id: str, snapshot: ConfigSnapshot, now: datetime,
                  issue_session: date, *, bar_root: Path = intraday.DEFAULT_BAR_ROOT, revalue=None, rate: float | None = None,
                  settings_override: sig.SignalSettings | None = None) -> dict:
    s = settings_override or sig.settings_from_snapshot(snapshot)
    evidence_session = previous_xnys_session(issue_session)
    run_day = _run_session(run_id)
    if run_day not in (evidence_session, evidence_session + timedelta(days=1)):
        return {"status": "STALE_BOOK", "run_id": run_id, "issue_session": issue_session.isoformat(),
                "evidence_session": evidence_session.isoformat(), "issued": 0, "new_tickets": 0}
    run_dir = Path(runs_dir) / run_id
    book = _read_csv(run_dir / "intelligence_lab" / f"final_opportunity_book_{run_id}.csv")
    gate = {r["ticker"].upper(): r for r in _read_csv(run_dir / "morning_validation" / f"morning_validated_trades_{run_id}.csv")}
    valuations = {r["ticker"].upper(): r for r in _read_csv(run_dir / "options" / f"options_intelligence_{run_id}.csv")}
    revalue = revalue or default_revaluer()
    rate = default_rate() if rate is None else rate
    h9r = {r[0] for r in connection.execute(
        "SELECT ticker FROM hypothesis_events WHERE event_session = ? AND direction = 'UP'", (evidence_session.isoformat(),))}
    last_usable_for = lambda expiry: _last_usable(expiry, s.contract_exit_buffer)  # noqa: E731

    decided, rejections = [], {}
    for row in book:
        ticker = str(row.get("ticker") or "").upper()
        g, v = gate.get(ticker), valuations.get(ticker)
        reason, prepared = sig.prepare(row, g, v, None, s, issue_session=issue_session,
                                       last_usable_for=last_usable_for, rate=rate)
        if reason is None and prepared.contract_symbol and prepared.quote_timestamp_utc:
            spot = intraday.spot_at(ticker, issue_session, prepared.quote_timestamp_utc, bar_root)
            if spot is not None:
                reason, prepared = sig.prepare(row, g, v, spot, s, issue_session=issue_session,
                                               last_usable_for=last_usable_for, rate=rate)
        if reason is None:
            reason, fields_ = sig.decide(prepared, revalue(dict(prepared.path_inputs)), s)
        if reason is not None:
            rejections[ticker] = reason
            continue
        decided.append((ticker, fields_))
    ranked = sig.rank_tickets(decided, valuations, s, run_id=run_id, evidence_session=evidence_session,
                              issue_session=issue_session, h9r_tickers=h9r)
    tickets, held_back = sig.apply_daily_cap(ranked, s)
    for t in held_back:
        rejections[t.ticker] = f"RANK_BELOW_DAILY_CAP:{t.rank}"
    ticket_rows = []
    for t in tickets:
        row = {k: storage._plain(v) for k, v in asdict(t).items()}
        row["h9r_gap_up_event"] = int(t.h9r_gap_up_event)
        row.update(config_snapshot_id=snapshot.snapshot_id, recorded_at_utc=now.isoformat())
        ticket_rows.append(row)
    new_tickets = storage.insert_ignore(connection, "signal_tickets", ticket_rows)
    storage.insert_ignore(connection, "signal_rejections", [
        {"run_id": run_id, "issue_session": issue_session.isoformat(), "ticker": t, "signal_version": s.signal_version,
         "reason": r, "recorded_at_utc": now.isoformat()} for t, r in rejections.items()])
    connection.commit()
    out_dir = run_dir / "signals"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"signal_tickets_{run_id}_{issue_session.isoformat()}"
    with (out_dir / f"{stem}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TICKET_FIELDS)
        writer.writeheader()
        for row in ticket_rows:
            writer.writerow({k: row[k] for k in TICKET_FIELDS})
    counts = Counter(r.split(":")[0] for r in rejections.values())
    (out_dir / f"{stem}.md").write_text(_ticket_page(tickets, counts, run_id, issue_session, now), encoding="utf-8")
    summary = {"status": "ISSUED", "run_id": run_id, "issue_session": issue_session.isoformat(),
               "evidence_session": evidence_session.isoformat(), "book_rows": len(book), "issued": len(tickets),
               "new_tickets": new_tickets, "rejections": dict(counts.most_common()),
               "csv": str(out_dir / f"{stem}.csv"), "page": str(out_dir / f"{stem}.md")}
    (out_dir / f"{stem}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _fmt(value, spec: str = ".2f") -> str:
    return "n/a" if value is None else format(value, spec)


def _ticket_page(tickets, counts: Counter, run_id: str, issue_session: date, now: datetime) -> str:
    lines = [f"# Signal tickets — issued {issue_session.isoformat()} ({now.strftime('%H:%M')} UTC)", "",
             f"Run `{run_id}`. Decision support only: each ticket is valued forward from the price and premium at "
             "issue and scored at real prices until it exits. No capital authority (G1–G4 not yet passed).", "",
             "Exit rule: first of stop touch, target touch, planned hold, or (options) the last usable session; "
             "options exit at the end-of-day bid.", "",
             "| # | Ticker | Dir | Expression | Contract | Limit | Scored entry | Spot at issue | Stop | Target | Hold | "
             "Cautious / central / upside | Quote | O4 | H9R |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in tickets:
        quote = f"{t.quote_state.replace('QUOTE_', '')}, {t.quote_adjustment_state}"
        lines.append(
            f"| {t.rank} | {t.ticker} | {t.direction} | {t.expression}{' ' + t.side if t.expression == 'SHARES' else ''} | "
            f"{t.contract_symbol or '—'} | {t.limit_price:.2f} | {t.scored_entry:.2f} | {t.reference_spot:.2f} | "
            f"{t.stop_spot:.2f} | {t.target_spot:.2f} | {t.hold_sessions} | "
            f"{t.r_cautious:+.1%} / {_fmt(t.r_central, '+.1%')} / {_fmt(t.r_upside, '+.1%')} | {quote} | "
            f"{t.o4_stance} | {'yes' if t.h9r_gap_up_event else 'no'} |")
    if not tickets:
        lines.append("| — | no ticket passed | | | | | | | | | | | | | |")
    lines += ["", "## Not issued (reason counts)", ""] + [f"- {k}: {v}" for k, v in counts.most_common()] + [""]
    return "\n".join(lines)


def _ticket_from_row(row: Mapping) -> sig.SignalTicket:
    data = {k: row[k] for k in TICKET_FIELDS}
    for key in ("evidence_session", "issue_session", "expiry", "last_usable_session"):
        data[key] = date.fromisoformat(data[key]) if data[key] else None
    data["h9r_gap_up_event"] = bool(data["h9r_gap_up_event"])
    return sig.SignalTicket(**data)


def score_signals(connection: sqlite3.Connection, as_of: date, snapshot: ConfigSnapshot, now: datetime, *,
                  chain_db: Path = chains.DEFAULT_CHAIN_DB, price_db: Path = prices.DEFAULT_PRICE_DB,
                  settings_override: sig.SignalSettings | None = None) -> dict:
    s = settings_override or sig.settings_from_snapshot(snapshot)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        "SELECT t.* FROM signal_tickets t WHERE t.issue_session <= ? AND NOT EXISTS "
        "(SELECT 1 FROM signal_outcomes o WHERE o.ticket_id = t.ticket_id AND o.signal_version = t.signal_version)",
        (as_of.isoformat(),)).fetchall()
    connection.row_factory = None
    tickets = [_ticket_from_row(dict(r)) for r in rows]
    counts: Counter = Counter()
    if not tickets:
        return {"open_tickets": 0, "new_outcomes": 0, "states": {}}
    start = min(t.issue_session for t in tickets)
    bars = prices.load_bars({t.ticker for t in tickets}, start, as_of, price_db)
    quotes = chains.ChainQuotes(chain_db)
    out_rows = []
    try:
        for t in tickets:
            expected = [d for d in _sessions(t.issue_session, as_of)]
            have = {b.session: b for b in bars.get(t.ticker, [])}
            contiguous = []
            for session in expected:
                if session not in have:
                    break
                contiguous.append(have[session])
            plan = sig.plan_exit(t, contiguous, as_of)
            bid = quotes.bid(t.ticker, t.contract_symbol, plan.session) if (
                plan.state == sig.EXITED and t.expression == sig.OPTION) else None
            outcome = sig.mark_signal(t, plan, bid, s.contract_multiplier)
            counts[outcome.state] += 1
            if outcome.state not in (sig.CLOSED,):
                continue
            out_rows.append({"ticket_id": t.ticket_id, "signal_version": t.signal_version,
                             "as_of_session": as_of.isoformat(), "state": outcome.state,
                             "exit_session": outcome.exit_session.isoformat(), "exit_reason": outcome.exit_reason,
                             "entry_price": outcome.entry_price, "exit_price": outcome.exit_price,
                             "return_on_capital": outcome.return_on_capital, "pnl_per_unit": outcome.pnl_per_unit,
                             "reason": outcome.reason, "config_snapshot_id": snapshot.snapshot_id,
                             "scored_at_utc": now.isoformat()})
    finally:
        quotes.close()
    written = storage.insert_ignore(connection, "signal_outcomes", out_rows)
    connection.commit()
    return {"open_tickets": len(tickets), "new_outcomes": written, "states": dict(counts)}


def _sessions(start: date, end: date) -> list[date]:
    out, day = [], start
    while day <= end:
        if is_xnys_session(day):
            out.append(day)
        day += timedelta(days=1)
    return out


def signal_section(connection: sqlite3.Connection, snapshot: ConfigSnapshot) -> list[str]:
    try:
        s = sig.settings_from_snapshot(snapshot)
    except Exception:  # registry without signal keys: nothing to report
        return []
    rows = connection.execute(
        "SELECT t.issue_session, t.expression, t.quote_state, o.exit_session, o.return_on_capital, t.r_central, "
        "o.exit_reason FROM signal_outcomes o JOIN signal_tickets t USING (ticket_id, signal_version) "
        "WHERE o.state = 'CLOSED' ORDER BY o.exit_session").fetchall()
    issued = connection.execute("SELECT COUNT(*) FROM signal_tickets").fetchone()[0]
    lines = ["", "## Signal track record", "",
             f"Tickets issued {issued}; closed {len(rows)}. Returns on capital at real prices (options: issue-time ask "
             f"→ exit-session bid). Trust gate: ≥ {s.min_closed_signals} closed signals over ≥ {s.min_issue_sessions} "
             f"issue sessions and a lower interval bound (z = {s.interval_z}, clustered by issue session) above zero. "
             "Decision support only.", "",
             "| Scope | Closed | Issue sessions | Hit rate | Mean | Interval | Avg win | Avg loss | Worst | Max drawdown | "
             "Predicted central | Verdict |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    scopes = {"ALL": rows, "OPTION": [r for r in rows if r[1] == sig.OPTION], "SHARES": [r for r in rows if r[1] == sig.SHARES],
              "QUOTE_CURRENT_SESSION": [r for r in rows if r[2] == sig.QUOTE_CURRENT_SESSION],
              "QUOTE_PRIOR_SESSION": [r for r in rows if r[2] == sig.QUOTE_PRIOR_SESSION]}
    for scope, items in scopes.items():
        result = sig.evaluate([(date.fromisoformat(r[0]), r[4]) for r in items], s)
        predicted = [r[5] for r in items if r[5] is not None]
        interval = "n/a" if result["low"] is None else f"{result['low']:+.1%} … {result['high']:+.1%}"
        lines.append(
            f"| {scope} | {result['closed']} | {result['issue_sessions']} | {_fmt(result['hit_rate'], '.0%')} | "
            f"{_fmt(result['mean'], '+.1%')} | {interval} | {_fmt(result['avg_win'], '+.1%')} | "
            f"{_fmt(result['avg_loss'], '+.1%')} | {_fmt(result['worst'], '+.1%')} | "
            f"{sig.max_drawdown([r[4] for r in items]):.1%} | "
            f"{_fmt(sum(predicted) / len(predicted) if predicted else None, '+.1%')} | {result['verdict']} |")
    return lines
