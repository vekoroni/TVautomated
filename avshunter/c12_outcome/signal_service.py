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

from . import signal_ledger as ledger_io
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
                  issue_session: date, *, ledger=None, bar_root: Path = intraday.DEFAULT_BAR_ROOT, revalue=None,
                  rate: float | None = None, settings_override: sig.SignalSettings | None = None) -> dict:
    """Issue ranked tickets and record every candidate in the Decision and Outcome Ledger (``signal_ledger``)."""
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

    ledger = ledger if ledger is not None else ledger_io.open_ledger()
    decided, rejections, anchors = [], {}, {}
    missing_identity, chain_unavailable = [], []
    for row in book:
        ticker = str(row.get("ticker") or "").upper()
        thesis_id = str(row.get("thesis_id") or "").strip()
        if not thesis_id:
            missing_identity.append(ticker)          # never given a synthetic identity (R1)
            continue
        anchor = ledger_io.chain_anchor(ledger, thesis_id)
        if anchor is None:
            chain_unavailable.append(ticker)         # nothing to chain to: it could not be measured, so not issued
            continue
        anchors[ticker] = anchor
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
    events = [ledger_io.presentation_event(anchor=anchors[t.ticker], run_id=run_id, now=now,
                                           signal_version=s.signal_version, issue_session=issue_session,
                                           config_snapshot_id=snapshot.snapshot_id, ticket=t) for t in tickets]
    ranks = {t.ticker: t.rank for t in held_back}
    events += [ledger_io.presentation_event(anchor=anchors[ticker], run_id=run_id, now=now,
                                            signal_version=s.signal_version, issue_session=issue_session,
                                            config_snapshot_id=snapshot.snapshot_id, ticker=ticker,
                                            reason=reason.split(":")[0], rank=ranks.get(ticker))
               for ticker, reason in rejections.items()]
    new_events = ledger.append_many(events)
    ticket_rows = []
    for t in tickets:
        row = {k: storage._plain(v) for k, v in asdict(t).items()}
        row["h9r_gap_up_event"] = int(t.h9r_gap_up_event)
        ticket_rows.append(row)
    out_dir = run_dir / "signals"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"signal_tickets_{run_id}_{issue_session.isoformat()}"
    with (out_dir / f"{stem}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TICKET_FIELDS)
        writer.writeheader()
        for row in ticket_rows:
            writer.writerow({k: row[k] for k in TICKET_FIELDS})
    watch = sig.watchlist(held_back, s)
    with (out_dir / f"{stem}_watchlist.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["listing"] + TICKET_FIELDS)
        writer.writeheader()
        for t in watch:
            row = {k: storage._plain(v) for k, v in asdict(t).items()}
            row["h9r_gap_up_event"] = int(t.h9r_gap_up_event)
            writer.writerow({"listing": "WATCHLIST_RANKED_NOT_ISSUED", **{k: row[k] for k in TICKET_FIELDS}})
    counts = Counter(r.split(":")[0] for r in rejections.values())
    (out_dir / f"{stem}.md").write_text(_ticket_page(tickets, counts, run_id, issue_session, now, watch=watch),
                                        encoding="utf-8")
    summary = {"status": "ISSUED", "run_id": run_id, "issue_session": issue_session.isoformat(),
               "evidence_session": evidence_session.isoformat(), "book_rows": len(book), "issued": len(tickets),
               "new_events": new_events, "rejections": dict(counts.most_common()),
               "missing_thesis_identity": missing_identity, "ledger_chain_unavailable": chain_unavailable,
               "ranked": len(ranked), "watchlist": len(watch),
               "csv": str(out_dir / f"{stem}.csv"), "watchlist_csv": str(out_dir / f"{stem}_watchlist.csv"),
               "page": str(out_dir / f"{stem}.md")}
    (out_dir / f"{stem}_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _fmt(value, spec: str = ".2f") -> str:
    return "n/a" if value is None else format(value, spec)


def _ticket_rows(tickets) -> list[str]:
    rows = []
    for t in tickets:
        quote = f"{t.quote_state.replace('QUOTE_', '')}, {t.quote_adjustment_state}"
        rows.append(
            f"| {t.rank} | {t.ticker} | {t.direction} | {t.expression}{' ' + t.side if t.expression == 'SHARES' else ''} | "
            f"{t.contract_symbol or '—'} | {t.limit_price:.2f} | {t.scored_entry:.2f} | {t.reference_spot:.2f} | "
            f"{t.stop_spot:.2f} | {t.target_spot:.2f} | {t.hold_sessions} | "
            f"{t.r_cautious:+.1%} / {_fmt(t.r_central, '+.1%')} / {_fmt(t.r_upside, '+.1%')} | {quote} | "
            f"{t.o4_stance} | {'yes' if t.h9r_gap_up_event else 'no'} |")
    return rows


def _ticket_page(tickets, counts: Counter, run_id: str, issue_session: date, now: datetime, *, watch=()) -> str:
    lines = [f"# Signal tickets — issued {issue_session.isoformat()} ({now.strftime('%H:%M')} UTC)", "",
             f"Run `{run_id}`. Decision support only: each ticket is valued forward from the price and premium at "
             "issue and scored at real prices until it exits. No capital authority (G1–G4 not yet passed).", "",
             "Exit rule: first of stop touch, target touch, planned hold, or (options) the last usable session; "
             "options exit at the end-of-day bid.", "",
             "| # | Ticker | Dir | Expression | Contract | Limit | Scored entry | Spot at issue | Stop | Target | Hold | "
             "Cautious / central / upside | Quote | O4 | H9R |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    lines += _ticket_rows(tickets)
    if not tickets:
        lines.append("| — | no ticket passed | | | | | | | | | | | | | |")
    if watch:
        lines += ["", f"## Watchlist — ranked, not issued (ranks {watch[0].rank}–{watch[-1].rank})", "",
                  "Same ranking and valuation as the tickets; shown for manual review only. Not tracked as tickets "
                  "(their rank and reason are recorded in the ledger like every candidate).", "",
                  "| # | Ticker | Dir | Expression | Contract | Limit | Scored entry | Spot at issue | Stop | Target | "
                  "Hold | Cautious / central / upside | Quote | O4 | H9R |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"] + _ticket_rows(watch)
    lines += ["", "## Not issued (reason counts)", ""] + [f"- {k}: {v}" for k, v in counts.most_common()] + [""]
    return "\n".join(lines)


def score_signals(ledger, as_of: date, snapshot: ConfigSnapshot, now: datetime, *,
                  chain_db: Path = chains.DEFAULT_CHAIN_DB, price_db: Path = prices.DEFAULT_PRICE_DB,
                  settings_override: sig.SignalSettings | None = None) -> dict:
    """Score issued tickets at real prices; each result is a counterfactual OUTCOME chained to its presentation."""
    s = settings_override or sig.settings_from_snapshot(snapshot)
    done = {e.previous_event_id for e in ledger_io.signal_outcomes(ledger)}
    open_items = [(e, ledger_io.ticket_from_payload(e.payload)) for e in ledger_io.issued_presentations(ledger, as_of)
                  if e.event_id not in done]
    counts: Counter = Counter()
    if not open_items:
        return {"open_tickets": 0, "new_outcomes": 0, "states": {}, "waiting_on_mark": []}
    start = min(t.issue_session for _, t in open_items)
    bars = prices.load_bars({t.ticker for _, t in open_items}, start, as_of, price_db)
    quotes = chains.ChainQuotes(chain_db)
    events, waiting = [], []
    try:
        for presentation, t in open_items:
            have = {b.session: b for b in bars.get(t.ticker, [])}
            contiguous = []
            for session in _sessions(t.issue_session, as_of):
                if session not in have:
                    break
                contiguous.append(have[session])
            plan = sig.plan_exit(t, contiguous, as_of)
            bid = quotes.bid(t.ticker, t.contract_symbol, plan.session) if (
                plan.state == sig.EXITED and t.expression == sig.OPTION) else None
            outcome = sig.mark_signal(t, plan, bid, s.contract_multiplier)
            counts[outcome.state] += 1
            if outcome.state == sig.MARK_UNAVAILABLE:
                # Exact-session mark missing: listed, never substituted by a nearby date (P0-4, RC3).
                waiting.append({"ticket_id": t.ticket_id, "ticker": t.ticker, "contract": t.contract_symbol,
                                "mark_session": plan.session.isoformat() if plan.session else None})
            if outcome.state != sig.CLOSED:
                continue
            held = len([d for d in _sessions(t.issue_session, outcome.exit_session) if d > t.issue_session])
            events.append(ledger_io.outcome_event(presentation=presentation, outcome=outcome, ticket=t,
                                                  sessions_held=held, now=now,
                                                  config_snapshot_id=snapshot.snapshot_id))
    finally:
        quotes.close()
    written = ledger.append_many(events)
    return {"open_tickets": len(open_items), "new_outcomes": written, "states": dict(counts),
            "waiting_on_mark": waiting}


def _sessions(start: date, end: date) -> list[date]:
    out, day = [], start
    while day <= end:
        if is_xnys_session(day):
            out.append(day)
        day += timedelta(days=1)
    return out


def signal_section(ledger, snapshot: ConfigSnapshot) -> list[str]:
    """Report section read from the Decision and Outcome Ledger; nothing is shown without a ledger."""
    if ledger is None:
        return []
    try:
        s = sig.settings_from_snapshot(snapshot)
    except Exception:  # registry without signal keys: nothing to report
        return []
    presentations = {e.event_id: e for e in ledger.events_by_type("PRESENTATION_DECISION")
                     if e.payload.get("decision_stage") == ledger_io.DECISION_STAGE}
    issued = sum(1 for e in presentations.values() if e.payload.get("presented") is True)
    rows = []
    for outcome in ledger_io.signal_outcomes(ledger):
        p = presentations.get(outcome.previous_event_id)
        if p is None or outcome.payload.get("state") != sig.CLOSED:
            continue
        rows.append((p.payload.get("issue_session"), p.payload.get("expression"), p.payload.get("quote_state"),
                     outcome.payload.get("exit_session"), outcome.payload.get("return_on_capital"),
                     p.payload.get("r_central")))
    rows.sort(key=lambda r: str(r[3]))
    lines = ["", "## Signal track record", "",
             f"Candidates considered {len(presentations)}; tickets issued {issued}; closed {len(rows)} "
             "(Decision and Outcome Ledger, stage SIGNAL_TICKET; every candidate recorded). Returns on capital at "
             "real prices (options: issue-time ask to exit-session bid). Decision support only.", "",
             "| Scope | Closed | Issue sessions | Hit rate | Mean | Interval | Avg win | Avg loss | Worst | Max drawdown | "
             "Predicted central | Verdict |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    scopes = {"ALL": rows, "OPTION": [r for r in rows if r[1] == sig.OPTION],
              "QUOTE_CURRENT_SESSION": [r for r in rows if r[2] == sig.QUOTE_CURRENT_SESSION],
              "QUOTE_PRIOR_SESSION": [r for r in rows if r[2] == sig.QUOTE_PRIOR_SESSION]}
    for scope, items in scopes.items():
        result = sig.evaluate([(date.fromisoformat(r[0]), r[4]) for r in items if r[0]], s)
        predicted = [r[5] for r in items if r[5] is not None]
        interval = "n/a" if result["low"] is None else f"{result['low']:+.1%} to {result['high']:+.1%}"
        lines.append(
            f"| {scope} | {result['closed']} | {result['issue_sessions']} | {_fmt(result['hit_rate'], '.0%')} | "
            f"{_fmt(result['mean'], '+.1%')} | {interval} | {_fmt(result['avg_win'], '+.1%')} | "
            f"{_fmt(result['avg_loss'], '+.1%')} | {_fmt(result['worst'], '+.1%')} | "
            f"{sig.max_drawdown([r[4] for r in items]):.1%} | "
            f"{_fmt(sum(predicted) / len(predicted) if predicted else None, '+.1%')} | {result['verdict']} |")
    return lines
