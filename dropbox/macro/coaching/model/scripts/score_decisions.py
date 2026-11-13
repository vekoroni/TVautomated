#!/usr/bin/env python3
"""AVS-MODEL-001 step 0b / 0c: the nightly forward scorer.

    C:\\Python314\\python.exe C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\dropbox\\macro\\coaching\\model\\scripts\\score_decisions.py

Each run: (1) re-collects the decisions from the hand-off folders and ledgers, so a new session is added;
(2) scores every decision at 1, 2, 3, 5 and 10 sessions; (3) keeps what was already scored and fills in rows that were
NOT_MATURE or had no data on an earlier run; (4) writes the backfill report.

Research package only: every source database is opened read-only; the only file written is
outcomes\\decision_events.sqlite (and the reports). Paper outcomes only (rule P13): this measures the signal, never a
real fill, and never touches trade_journal.db.

Scoring rules (v1, frozen; change only with a new version):
  STOCK    reference = close of the decision session. Move = close-to-close to the horizon session. Thesis side right
           = the move is in the thesis direction. First touch of target vs stop on the daily high / low of the sessions
           after the decision session up to the horizon; both on the same day = AMBIGUOUS, never a win.
  OPTION   the exact option_symbol named on the card (else the triage row), from PHANTOM chain_snapshots on the decision
           session and on each horizon session (options_greeks_history only when the chain has no row). Return at
           mid-to-mid and at ask in / bid out. First session (1 to 10) with the mid at +20% and at +30%.
  TIER     the 11 Nov liquidity tiers on the decision-session quote (liquidity_tier from build_lab_handoff.py, reused).
  FLAGS    NO_PRICE, NO_CHAIN, NO_CONTRACT, NOT_MATURE. A missing value is a flag, never an estimate.
"""
from __future__ import annotations

import argparse
import math
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

import decision_events as de

VERSION = "score_decisions_v1.1_path_completeness"
HORIZONS = (1, 2, 3, 5, 10)
PATH_SESSIONS = 10
PRICE_DB = de.REPO / "data" / "canonical" / "historical_prices.sqlite"
PHANTOM_DB = de.REPO / "data" / "phantom" / "phantom_history.db"
CALENDAR_TICKER = "SPY"
BLH = de.load_module("avs_build_lab_handoff", de.WORK / "build_lab_handoff.py")   # liquidity_tier (11 Nov rules)

STOCK_COLS = ["stock_status", "ref_close", "close_h", "move_pct", "side_move_pct", "thesis_side_right", "touch", "touch_session_n",
              "touch_level", "touch_level_session_n", "stock_data_asof_max"]
OPTION_COLS = ["opt_status", "opt_missing_at", "opt_source", "opt_ref_bid", "opt_ref_mid", "opt_ref_ask", "opt_h_bid", "opt_h_mid", "opt_h_ask",
               "opt_ret_mid", "opt_ret_ask_bid", "opt_data_asof_max"]


def ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)


# ---------------------------------------------------------------------------------------------- stock

def load_prices(tickers, since: str):
    """({ticker: {date: (high, low, close)}}, [session dates]) from COMPLETE bars only. Read-only."""
    bars: dict[str, dict] = {}
    with closing(ro(PRICE_DB)) as con:
        cal = [r[0] for r in con.execute(
            "SELECT trading_date FROM ohlcv_daily WHERE ticker=? AND bar_status='COMPLETE' AND trading_date>=? ORDER BY 1", (CALENDAR_TICKER, since))]
        con.execute("CREATE TEMP TABLE want(ticker TEXT PRIMARY KEY)")
        con.executemany("INSERT OR IGNORE INTO want VALUES (?)", [(t,) for t in tickers])
        for t, d, h, l, c in con.execute(
                "SELECT o.ticker, o.trading_date, o.high, o.low, o.close FROM ohlcv_daily o JOIN want w ON w.ticker=o.ticker "
                "WHERE o.bar_status='COMPLETE' AND o.trading_date>=?", (since,)):
            bars.setdefault(t, {})[d] = (h, l, c)
    return bars, cal


def first_touch(side: str, path: list, target, stop, ref):
    """(result, session number). path = [(high, low, close)] for the sessions after the decision session, None = no bar."""
    if target is None or stop is None:
        return "NO_LEVELS", None
    up = side == "CALL"
    if side not in ("CALL", "PUT"):
        return "NO_SIDE", None
    if (up and not (stop < ref < target)) or (not up and not (target < ref < stop)):
        return "LEVELS_NOT_AROUND_REF_CLOSE", None      # the target or the stop was already passed at the reference close
    for n, bar in enumerate(path, start=1):
        if bar is None:
            return "PATH_INCOMPLETE", None
        high, low, _ = bar
        t_hit = high >= target if up else low <= target
        s_hit = low <= stop if up else high >= stop
        if t_hit and s_hit:
            return "AMBIGUOUS", n
        if t_hit:
            return "TARGET", n
        if s_hit:
            return "STOP", n
    return "NEITHER", None


def score_stock(ev: dict, bars: dict, cal: list, idx: dict) -> list[dict]:
    out = []
    session, side = ev["decision_session"], ev["side"]
    tb = bars.get(ev["ticker"], {})
    i = idx.get(session)
    ref = tb.get(session)
    sign = 1 if side == "CALL" else -1 if side == "PUT" else None
    for h in HORIZONS:
        row = {"event_id": ev["event_id"], "horizon": h, "horizon_session": None, **{c: None for c in STOCK_COLS}}
        if ref is not None:
            row["ref_close"] = ref[2]          # known on the decision session itself, so recorded even while the horizon is not mature
        if i is None:
            row["stock_status"] = "NOT_A_SESSION"
        elif i + h >= len(cal):
            row["stock_status"] = "NOT_MATURE"
        else:
            hs = cal[i + h]
            row["horizon_session"] = hs
            end = tb.get(hs)
            if ref is None or end is None:
                row["stock_status"] = "NO_PRICE"
            else:
                rc, hc = ref[2], end[2]
                move = (hc / rc - 1) * 100
                path = [tb.get(cal[i + n]) for n in range(1, h + 1)]
                touch, tn = first_touch(side, path, ev.get("target_used"), ev.get("stop_used"), rc)
                touch2, tn2 = first_touch(side, path, ev.get("level"), ev.get("invalidation"), rc)
                row.update({"stock_status": "SCORED", "ref_close": rc, "close_h": hc, "move_pct": round(move, 4),
                            "side_move_pct": None if sign is None else round(move * sign, 4),
                            "thesis_side_right": None if sign is None else int(move * sign > 0),
                            "touch": touch, "touch_session_n": tn, "touch_level": touch2, "touch_level_session_n": tn2,
                            "stock_data_asof_max": hs})
        out.append(row)
    return out


# ---------------------------------------------------------------------------------------------- option

def utc_date(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def expiry_of(symbol: str) -> str | None:
    m = de.CD.OCC.search(symbol or "")
    if not m:
        return None
    y = m.group(2)[:6]
    return f"20{y[:2]}-{y[2:4]}-{y[4:6]}"


def quotes_for(con, ticker: str, symbol: str, first: str, last: str):
    """({date: quote}, {dates with any chain for the ticker}). chain_snapshots first; options_greeks_history fills a date it lacks."""
    q = {}
    for d, bid, ask, oi, vol, iv, delta, upd in con.execute(
            "SELECT quote_date, bid, ask, open_interest, volume, iv, delta, updated_ts FROM chain_snapshots "
            "WHERE ticker=? AND option_symbol=? AND quote_date BETWEEN ? AND ?", (ticker, symbol, first, last)):
        q[d] = {"bid": bid, "ask": ask, "oi": oi, "volume": vol, "iv": iv, "delta": delta, "updated_date": utc_date(upd), "source": "chain_snapshots"}
    for d, bid, ask, oi, vol, iv, delta in con.execute(
            "SELECT snapshot_date, bid, ask, open_interest, volume, iv, delta FROM options_greeks_history "
            "WHERE ticker=? AND contract_symbol=? AND snapshot_date BETWEEN ? AND ?", (ticker, symbol, first, last)):
        q.setdefault(d, {"bid": bid, "ask": ask, "oi": oi, "volume": vol, "iv": iv, "delta": delta, "updated_date": None, "source": "options_greeks_history"})
    days = {r[0] for r in con.execute("SELECT DISTINCT quote_date FROM chain_snapshots WHERE ticker=? AND quote_date BETWEEN ? AND ?", (ticker, first, last))}
    days |= {r[0] for r in con.execute("SELECT DISTINCT snapshot_date FROM options_greeks_history WHERE ticker=? AND snapshot_date BETWEEN ? AND ?", (ticker, first, last))}
    return q, days


def mid_of(q):
    """Mid from a two-sided quote; None when there is no bid or no ask (a one-sided quote has no mid)."""
    if not q or q["bid"] is None or q["ask"] is None or q["bid"] <= 0 or q["ask"] <= 0:
        return None
    return round((q["bid"] + q["ask"]) / 2.0, 4)


def usable_path_mid(q):
    """Path evidence requires positive, non-crossed two-sided quotes."""
    mid = mid_of(q)
    return mid if mid is not None and math.isfinite(mid) and mid > 0 and q["ask"] >= q["bid"] else None


def missing_flag(d: str, q: dict, days: set, expiry) -> str:
    if expiry and d > expiry:
        return "EXPIRED"
    return "NO_CONTRACT" if d in days else "NO_CHAIN"       # the chain is there but not this contract / no chain that day


def score_option(ev: dict, con, cal: list, idx: dict):
    """(rows per horizon, entry row). Never estimates: a missing quote is NO_CHAIN / NO_CONTRACT."""
    symbol, session = ev.get("contract_scored") or "", ev["decision_session"]
    i = idx.get(session)
    rows = [{"event_id": ev["event_id"], "horizon": h, **{c: None for c in OPTION_COLS}} for h in HORIZONS]
    entry = {"event_id": ev["event_id"], "contract": symbol, "expiry": expiry_of(symbol)}
    if not symbol:
        for r in rows:
            r["opt_status"] = "NO_CONTRACT_NAMED"
        return rows, None
    if i is None:
        for r in rows:
            r["opt_status"] = "NOT_A_SESSION"
        return rows, entry
    last = cal[min(i + PATH_SESSIONS, len(cal) - 1)]
    q, days = quotes_for(con, ev["ticker"], symbol, session, last)
    if not q and not days:      # the contract root can differ from the ticker (class shares); try the root once
        root = de.CD.OCC.search(symbol).group(1)
        if root != ev["ticker"]:
            q, days = quotes_for(con, root, symbol, session, last)
    ref = q.get(session)
    ref_mid = mid_of(ref)
    if ref:
        tier, reason, pct = BLH.liquidity_tier(ref["bid"], ref["ask"], ref["oi"])
        entry.update({"ref_quote_date": session, "ref_source": ref["source"], "ref_bid": ref["bid"], "ref_ask": ref["ask"], "ref_mid": ref_mid,
                      "ref_oi": ref["oi"], "ref_volume": ref["volume"], "ref_iv": ref["iv"], "ref_delta": ref["delta"],
                      "ref_updated_date": ref["updated_date"], "liquidity_tier": tier, "liquidity_reason": reason,
                      "spread_pct_of_mid": None if pct is None else round(pct, 2), "tradeable": int(tier != "C")})
    else:
        entry.update({"ref_status": missing_flag(session, q, days, entry["expiry"])})
    # the monetisation clock: first session (1..10) with the mid at +20% and at +30%
    elapsed = min(PATH_SESSIONS, len(cal) - 1 - i)
    quoted, best, p20, p30 = 0, None, None, None
    if usable_path_mid(ref) is not None:
        for n in range(1, elapsed + 1):
            m = usable_path_mid(q.get(cal[i + n]))
            if m is None:
                continue
            quoted += 1
            ret = m / ref_mid - 1
            best = ret if best is None else max(best, ret)
            if p20 is None and ret >= 0.20:
                p20 = n
            if p30 is None and ret >= 0.30:
                p30 = n
    entry.update({"path_sessions_elapsed": elapsed, "path_sessions_quoted": quoted,
                  "path_complete": int(elapsed == PATH_SESSIONS and usable_path_mid(ref) is not None and quoted == PATH_SESSIONS),
                  "best_mid_ret_pct": None if best is None else round(best * 100, 2), "first_p20_session_n": p20, "first_p30_session_n": p30})
    for r in rows:
        h = r["horizon"]
        if i + h >= len(cal):
            r["opt_status"] = "NOT_MATURE"
            continue
        hs = cal[i + h]
        end = q.get(hs)
        if not ref:
            r["opt_status"], r["opt_missing_at"] = missing_flag(session, q, days, entry["expiry"]), "REFERENCE"
            continue
        if not end:
            r["opt_status"], r["opt_missing_at"] = missing_flag(hs, q, days, entry["expiry"]), "HORIZON"
            continue
        end_mid = mid_of(end)
        r.update({"opt_source": ref["source"] if ref["source"] == end["source"] else f"{ref['source']} -> {end['source']}",
                  "opt_ref_bid": ref["bid"], "opt_ref_mid": ref_mid, "opt_ref_ask": ref["ask"],
                  "opt_h_bid": end["bid"], "opt_h_mid": end_mid, "opt_h_ask": end["ask"],
                  "opt_data_asof_max": max(x for x in (hs, end.get("updated_date")) if x)})
        if ref["ask"] is None or ref["ask"] <= 0:
            r["opt_status"], r["opt_missing_at"] = "NO_ASK", "REFERENCE"
            continue
        r["opt_status"] = "SCORED"
        r["opt_ret_mid"] = None if (ref_mid is None or end_mid is None) else round((end_mid / ref_mid - 1) * 100, 2)
        r["opt_ret_ask_bid"] = None if end["bid"] is None else round((end["bid"] / ref["ask"] - 1) * 100, 2)
    return rows, entry


# ---------------------------------------------------------------------------------------------- run

def keep_scored(new: pd.DataFrame, old: pd.DataFrame | None):
    """What was already SCORED stays as first recorded; rows that were NOT_MATURE or had no data are filled in. Returns (table, changes)."""
    new = new.copy()
    new["first_scored_utc"] = None
    if old is None or old.empty:
        return new, pd.DataFrame()
    m = new.merge(old, on=["event_id", "horizon"], how="left", suffixes=("", "_old"))
    changes = []
    for status, cols in (("stock_status", STOCK_COLS + ["horizon_session"]), ("opt_status", OPTION_COLS)):
        was = m[f"{status}_old"] == "SCORED"
        for c in cols:
            if f"{c}_old" not in m:
                continue
            a, b = m.loc[was, c], m.loc[was, f"{c}_old"]
            diff = ~((a == b) | (a.isna() & b.isna()))
            if c not in ("stock_status", "opt_status") and pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
                diff &= ~((a - b).abs() < 1e-9)
            for k in a.index[diff]:
                changes.append({"event_id": m.at[k, "event_id"], "horizon": int(m.at[k, "horizon"]), "column": c,
                                "first_scored": b.at[k], "this_run": a.at[k]})
            if was.any():
                m[c] = m[c].astype(object)
                m.loc[was, c] = m.loc[was, f"{c}_old"]
    if "first_scored_utc_old" in m:
        m["first_scored_utc"] = m["first_scored_utc_old"]
    return m[[c for c in new.columns]], pd.DataFrame(changes)


def run(report: bool = True, db: Path = de.OUT_DB) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    c = de.collect()
    de.write(c, db)
    events = list(c.events.values())
    since = min(e["decision_session"] for e in events)
    bars, cal = load_prices(sorted({e["ticker"] for e in events}), since)
    idx = {d: n for n, d in enumerate(cal)}
    stock = pd.DataFrame([r for e in events for r in score_stock(e, bars, cal, idx)])
    opt_rows, entries = [], []
    with closing(ro(PHANTOM_DB)) as ph:
        for e in events:
            rows, entry = score_option(e, ph, cal, idx)
            opt_rows += rows
            if entry:
                entries.append(entry)
    out = stock.merge(pd.DataFrame(opt_rows), on=["event_id", "horizon"], how="left")
    with closing(sqlite3.connect(db)) as con, con:
        has = con.execute("SELECT 1 FROM sqlite_master WHERE name='outcomes'").fetchone()
        old = pd.read_sql("SELECT * FROM outcomes", con) if has else None
        out, changes = keep_scored(out, old)
        done = (out["stock_status"] == "SCORED") & out["first_scored_utc"].isna()
        out.loc[done, "first_scored_utc"] = now
        out["scored_utc"], out["scorer_version"] = now, VERSION
        out.to_sql("outcomes", con, index=False, if_exists="replace")
        con.execute("CREATE UNIQUE INDEX ix_outcomes ON outcomes(event_id, horizon)")
        pd.DataFrame(entries).to_sql("option_entry", con, index=False, if_exists="replace")
        have = {e["decision_session"] for e in events}
        pd.DataFrame([{"session": d, "has_decision_source": int(d in have)} for d in cal]).to_sql("sessions", con, index=False, if_exists="replace")
        if len(changes):
            changes["run_utc"] = now
            changes.to_sql("rescoring_changes", con, index=False, if_exists="append")
        pd.DataFrame([{"run_utc": now, "scorer_version": VERSION, "collector_version": de.VERSION, "events": len(events),
                       "last_price_session": cal[-1], "outcome_rows": len(out), "changed_after_first_scoring": len(changes)}]
                     ).to_sql("scorer_runs", con, index=False, if_exists="append")
    summary = {"events": len(events), "last_price_session": cal[-1], "changed_after_first_scoring": len(changes),
               "stock_status": out["stock_status"].value_counts().to_dict(), "opt_status": out["opt_status"].value_counts().to_dict()}
    if report:
        import backfill_report
        summary["report"] = str(backfill_report.write_report(db, date.today().isoformat()))
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--no-report", action="store_true", help="score only; do not write the backfill report")
    a = ap.parse_args(argv)
    s = run(report=not a.no_report)
    print(f"{VERSION}: {s['events']} decisions scored to the session of {s['last_price_session']}")
    print("  stock rows :", s["stock_status"])
    print("  option rows:", s["opt_status"])
    print(f"  values that differ from their first scoring (kept as first scored, listed in rescoring_changes): {s['changed_after_first_scoring']}")
    if s.get("report"):
        print("  report:", s["report"])


if __name__ == "__main__":
    main()
