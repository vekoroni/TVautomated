#!/usr/bin/env python3
"""AVS-MODEL-001 step 0d: the backfill report, written from outcomes\\decision_events.sqlite (read-only on it).

    C:\\Python314\\python.exe C:\\Users\\ACKVerissimo\\AVSHUNTER-Intelligence\\dropbox\\macro\\coaching\\model\\scripts\\backfill_report.py

Writes outcomes\\backfill_report_<date>.md and outcomes\\hand_check_<date>.csv (ten rows drawn with a fixed seed).
"""
from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from datetime import date
from pathlib import Path

import pandas as pd

MODEL = Path(__file__).resolve().parents[1]
DB = MODEL / "outcomes" / "decision_events.sqlite"
HORIZONS = (1, 2, 3, 5, 10)
SEED = 20261113
DECISIONS = ["TRADE", "WATCH", "MISSED", "PASS", "NOT_MINED", "CARD_NO_DECISION", "LEDGER_ONLY"]
PRICE_PASS, CONTRACT_PASS = 95.0, 70.0


def pct(n, d) -> str:
    return "n/a" if not d else f"{100 * n / d:.1f}%"


def rate(s: pd.Series) -> str:
    s = s.dropna()
    return "-" if s.empty else f"{100 * s.mean():.0f}% (n={len(s)})"


def table(df: pd.DataFrame) -> list[str]:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    out += ["| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return out + [""]


def rank_band(r) -> str:
    if pd.isna(r):
        return "not ranked"
    r = int(r)
    return "1-5" if r <= 5 else "6-10" if r <= 10 else "11-30" if r <= 30 else "31-60" if r <= 60 else "61-90"


def by_horizon(o: pd.DataFrame, group: str, value: str, order=None) -> pd.DataFrame:
    """One row per group, one column per horizon: share of rows where `value` is true, with the count."""
    keys = [k for k in (order or sorted(o[group].dropna().unique())) if k in set(o[group])]
    rows = []
    for k in keys:
        g = o[o[group] == k]
        rows.append({group: k, **{f"{h} sess.": rate(g.loc[g.horizon == h, value]) for h in HORIZONS}})
    return pd.DataFrame(rows)


def load(db: Path):
    with closing(sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)) as con:
        e = pd.read_sql("SELECT * FROM decision_events", con)
        o = pd.read_sql("SELECT * FROM outcomes", con)
        x = pd.read_sql("SELECT * FROM option_entry", con)
        f = pd.read_sql("SELECT * FROM source_files", con)
        s = pd.read_sql("SELECT source_kind, source_path, COUNT(*) rows_in_table FROM decision_sources GROUP BY 1, 2", con)
        skipped = pd.read_sql("SELECT * FROM skipped_rows", con)
        nc = pd.read_sql("SELECT * FROM not_collected", con)
        runs = pd.read_sql("SELECT * FROM scorer_runs", con)
        sessions = pd.read_sql("SELECT * FROM sessions", con)
    return e, o, x, f, s, skipped, nc, runs, sessions


def write_report(db: Path = DB, day: str | None = None) -> Path:
    day = day or date.today().isoformat()
    e, o, x, f, s, skipped, nc, runs, sessions = load(db)
    run = runs.iloc[-1]
    e["rank_band"] = e["triage_rank"].map(rank_band)
    o = o.merge(e[["event_id", "decision_session", "ticker", "side", "decision", "rank_band", "in_triage", "contract_scored"]], on="event_id")
    o = o.merge(x[["event_id", "liquidity_tier"]], on="event_id", how="left") if len(x) else o.assign(liquidity_tier=None)
    o["opt_up_mid"] = (o["opt_ret_mid"] > 0).where(o["opt_ret_mid"].notna()).astype(float)
    o["opt_up_ask_bid"] = (o["opt_ret_ask_bid"] > 0).where(o["opt_ret_ask_bid"].notna()).astype(float)
    o["side_right"] = o["thesis_side_right"].astype(float)
    judged = e[e.decision != "LEDGER_ONLY"]            # triaged or carded: the names a person or the triage looked at
    md = [f"# AVS-MODEL-001 step 0 · Outcome backfill report · {day}", "",
          f"Scored to the price session of {run.last_price_session}. {run.scorer_version}, {run.collector_version}. "
          "Paper outcomes only (rule P13): these measure the signal, not trading results. Nothing here is a real fill.", "",
          "## 1. What was collected", "",
          f"{len(e):,} decision events (one per ticker, side and session) from {len(f)} source files and {int(f.rows_in_file.sum()):,} source rows. "
          f"{len(judged):,} of them were triaged or carded; the other {len(e) - len(judged):,} are on a decision ledger or hand-off list only "
          "(labelled LEDGER_ONLY: never triaged, so not one of the five decision types; scored on the stock for context).", ""]
    per = e.groupby(["decision_session", "decision"]).size().unstack(fill_value=0).reindex(columns=[d for d in DECISIONS if d in set(e.decision)], fill_value=0)
    per["all"] = per.sum(axis=1)
    md += ["Decisions per session:", ""] + table(per.reset_index())
    src = e.groupby("decision_session")[["in_ledger", "in_handoff", "in_triage", "in_card"]].sum().astype(int)
    src.columns = ["on ledger", "on hand-off list", "triaged", "decision record"]
    src["card HTML"] = e.groupby("decision_session")["has_card_html"].sum().astype(int)
    md += ["Events per session and per source (an event can be in several):", ""] + table(src.reset_index())
    missing = []
    for d, r in src.iterrows():
        gone = [c for c in ("on ledger", "on hand-off list", "triaged") if r[c] == 0]
        if gone:
            missing.append(f"- {d}: no {', no '.join(gone)}")
    md += ["Sessions with a source missing:", ""] + (missing or ["- none"]) + [""]
    none = sessions.loc[sessions.has_decision_source == 0, "session"].tolist()
    md += [f"Trading sessions from {sessions.session.min()} to {sessions.session.max()} with no decision source at all "
           f"(no hand-off folder and no ledger; {len(none)} of {len(sessions)}): " + (", ".join(none) or "none") + ".", ""]
    rec = f.merge(s, on=["source_kind", "source_path"], how="left").fillna({"rows_in_table": 0})
    rec["rows_in_table"] = rec["rows_in_table"].astype(int)
    by_kind = rec.groupby("source_kind").agg(files=("source_path", "count"), rows_in_files=("rows_in_file", "sum"), rows_in_table=("rows_in_table", "sum")).reset_index()
    left = skipped.assign(source_path=skipped.path).merge(f[["source_path", "source_kind"]], on="source_path").groupby("source_kind").size() if len(skipped) else pd.Series(dtype=int)
    by_kind["rows_left_out_with_reason"] = by_kind.source_kind.map(left).fillna(0).astype(int)
    by_kind["reconciles"] = (by_kind.rows_in_files == by_kind.rows_in_table + by_kind.rows_left_out_with_reason).map({True: "yes", False: "NO"})
    md += ["Row counts, source files against the table:", ""] + table(by_kind)
    bad = rec[(rec.rows_in_file != rec.rows_in_table) & ~rec.source_path.isin(set(skipped.path) if len(skipped) else set())]
    md += ["Files that do not reconcile:", ""] + ([f"- {r.source_path}: {r.rows_in_file} in the file, {r.rows_in_table} in the table ({r.note})" for r in bad.itertuples()] or ["- none"]) + [""]
    if len(skipped):
        md += ["Rows left out, with the reason:", ""] + [f"- {r.path}: {r.reason}" for r in skipped.itertuples()] + [""]
    if len(nc):
        k = nc.groupby("kind")["files"].sum().sort_values(ascending=False).reset_index()
        md += ["Files in the hand-off folders that are not decision sources (counted, not read as decisions):", ""] + table(k)

    # ------------------------------------------------------------------ coverage
    h1 = o[o.horizon == 1]
    has_ref = o.groupby("event_id")["ref_close"].apply(lambda v: v.notna().any())
    mature = o[o.stock_status != "NOT_MATURE"]
    named = e[e.contract_scored.fillna("") != ""]
    xr = x.merge(e[["event_id", "decision_session", "decision"]], on="event_id") if len(x) else x
    with_ref = xr[xr.ref_quote_date.notna()] if len(xr) else xr
    chain_ok = xr[(xr.ref_quote_date.notna()) | (xr.get("ref_status") == "NO_CONTRACT")] if len(xr) else xr
    price_cov = 100 * (mature.stock_status == "SCORED").mean() if len(mature) else float("nan")
    contract_cov = 100 * len(with_ref) / len(named) if len(named) else float("nan")
    md += ["## 2. Coverage", "",
           f"- **Price:** {pct((mature.stock_status == 'SCORED').sum(), len(mature))} of matured decision-horizon rows have a price "
           f"({(mature.stock_status == 'SCORED').sum():,} of {len(mature):,}); {pct(int(has_ref.sum()), len(has_ref))} of decisions have a reference close. "
           f"Pass mark {PRICE_PASS:.0f}%: **{'PASS' if price_cov >= PRICE_PASS else 'FAIL'}**.",
           f"- **Contract named:** {len(named)} of {len(judged)} triaged or carded decisions name an exact option symbol ({pct(len(named), len(judged))}). "
           "The rest name none (the 12 Oct triage wrote the contract as text, and rows marked \"none (spread)\" chose no contract).",
           f"- **Chain on the decision session:** {pct(len(chain_ok), len(named))} of named contracts ({len(chain_ok)} of {len(named)}) have a PHANTOM chain for the ticker that day.",
           f"- **Exact contract on the decision session:** {pct(len(with_ref), len(named))} ({len(with_ref)} of {len(named)}). "
           f"Pass mark {CONTRACT_PASS:.0f}%: **{'PASS' if contract_cov >= CONTRACT_PASS else 'BELOW THE MARK: stop and report before step 1'}**.", ""]
    if len(xr):
        cov = xr.assign(state=xr.ref_quote_date.notna().map({True: "exact contract quoted", False: None}).fillna(xr.get("ref_status")))
        cov = cov.groupby(["decision_session", "state"]).size().unstack(fill_value=0)
        md += ["Named contracts on the decision session, by session:", ""] + table(cov.reset_index())
    oo = o[o.contract_scored.fillna("") != ""]
    st = oo.groupby(["horizon", "opt_status"]).size().unstack(fill_value=0)
    md += ["Option rows by horizon (named contracts only):", ""] + table(st.reset_index())
    ss = o.groupby(["horizon", "stock_status"]).size().unstack(fill_value=0)
    md += ["Stock rows by horizon (all decisions):", ""] + table(ss.reset_index())

    # ------------------------------------------------------------------ hit rates
    md += ["## 3. Hit rates", "",
           "Read with care: the same ticker re-enters on every session, so rows are not independent, and the judged groups are small. "
           "\"n\" is the number of matured, scored rows behind each figure. These are descriptive counts, not an edge verdict.", "",
           "### 3.1 Stock: thesis side right at the close (close-to-close move in the thesis direction)", ""]
    md += ["By decision type:", ""] + table(by_horizon(o, "decision", "side_right", DECISIONS))
    tri = o[o.in_triage == 1]
    md += ["By triage rank band (triaged names only):", ""] + table(by_horizon(tri, "rank_band", "side_right", ["1-5", "6-10", "11-30", "31-60", "61-90", "not ranked"]))
    md += ["By side, triaged or carded:", ""] + table(by_horizon(o[o.decision != "LEDGER_ONLY"], "side", "side_right"))
    md += ["By side, ledger only:", ""] + table(by_horizon(o[o.decision == "LEDGER_ONLY"], "side", "side_right"))
    t = o[(o.stock_status == "SCORED") & (o.decision != "LEDGER_ONLY") & (o.horizon == 10)]
    if len(t):
        md += ["First touch of target vs stop within 10 sessions, triaged or carded (daily high / low; both on one day = AMBIGUOUS, never a win):", ""]
        md += table(t.groupby(["decision", "touch"]).size().unstack(fill_value=0).reset_index())
    md += ["### 3.2 Option: return above zero at the horizon", "", "At mid-to-mid:", ""]
    md += table(by_horizon(oo, "decision", "opt_up_mid", DECISIONS))
    md += ["At ask in, bid out (the honest version):", ""] + table(by_horizon(oo, "decision", "opt_up_ask_bid", DECISIONS))
    md += ["By triage rank band, mid-to-mid:", ""] + table(by_horizon(oo[oo.in_triage == 1], "rank_band", "opt_up_mid", ["1-5", "6-10", "11-30", "31-60", "61-90", "not ranked"]))
    md += ["By triage rank band, ask in / bid out:", ""] + table(by_horizon(oo[oo.in_triage == 1], "rank_band", "opt_up_ask_bid", ["1-5", "6-10", "11-30", "31-60", "61-90", "not ranked"]))
    md += ["By side, mid-to-mid:", ""] + table(by_horizon(oo, "side", "opt_up_mid"))
    md += ["By side, ask in / bid out:", ""] + table(by_horizon(oo, "side", "opt_up_ask_bid"))
    md += ["By liquidity tier at entry (11 Nov rules; tier C is scored but **not tradeable**), mid-to-mid:", ""] + table(by_horizon(oo, "liquidity_tier", "opt_up_mid"))
    md += ["By liquidity tier at entry, ask in / bid out:", ""] + table(by_horizon(oo, "liquidity_tier", "opt_up_ask_bid"))
    if len(with_ref):
        w = with_ref.copy()
        w["tier"] = w.liquidity_tier.fillna("no tier")
        med = oo[oo.opt_status == "SCORED"].groupby("horizon")[["opt_ret_mid", "opt_ret_ask_bid"]].median().round(1).reset_index()
        med.columns = ["horizon (sessions)", "median return at mid, %", "median return ask in / bid out, %"]
        md += ["Median option return by horizon (all scored option rows):", ""] + table(med)
        clock = w.groupby("tier").agg(contracts=("event_id", "count"), full_10_session_path=("path_complete", "sum"),
                                      reached_plus20=("first_p20_session_n", lambda v: int(v.notna().sum())),
                                      reached_plus30=("first_p30_session_n", lambda v: int(v.notna().sum())),
                                      median_first_plus20_session=("first_p20_session_n", "median"),
                                      median_first_plus30_session=("first_p30_session_n", "median")).reset_index()
        md += ["### 3.3 Monetisation clock (feeds fix A12): first session with the mid at +20% and +30%, within 10 sessions", "",
               "Counted on the sessions that have a two-sided quote; a contract with fewer than 10 sessions elapsed or quoted can still reach the mark later.", ""]
        md += table(clock)
        md += ["Liquidity tier at entry, by decision type:", ""] + table(w.groupby(["decision", "tier"]).size().unstack(fill_value=0).reset_index())

    # ------------------------------------------------------------------ hand check
    pool = oo[(oo.opt_status == "SCORED") & oo.opt_ret_mid.notna()].sort_values(["event_id", "horizon"])
    hc = pool.sample(n=min(10, len(pool)), random_state=SEED).sort_values(["decision_session", "ticker"]) if len(pool) else pool
    hc = hc.merge(e[["event_id", "triage_contract_quote_text", "decision_record"]], on="event_id", how="left")
    cols = ["event_id", "decision", "contract_scored", "horizon", "horizon_session", "ref_close", "close_h", "move_pct",
            "opt_ref_bid", "opt_ref_mid", "opt_ref_ask", "opt_h_bid", "opt_h_mid", "opt_h_ask", "opt_ret_mid", "opt_ret_ask_bid"]
    hc_path = db.parent / f"hand_check_{day}.csv"
    hc[cols + ["triage_contract_quote_text", "decision_record"]].assign(ack_tastytrade_check="").to_csv(hc_path, index=False)
    md += ["## 4. Ten rows for the hand check", "",
           f"Drawn at random (seed {SEED}) from the scored option rows; also saved as `{hc_path.name}` with a blank column for the check against "
           "Tastytrade history or screenshots. Prices are the daily close (stock) and the PHANTOM end-of-day quote (option).", ""]
    md += table(hc[cols].rename(columns={"contract_scored": "contract", "horizon_session": "horizon date", "ref_close": "stock ref", "close_h": "stock at h",
                                         "move_pct": "stock %", "opt_ref_bid": "ref bid", "opt_ref_mid": "ref mid", "opt_ref_ask": "ref ask",
                                         "opt_h_bid": "h bid", "opt_h_mid": "h mid", "opt_h_ask": "h ask", "opt_ret_mid": "ret mid %", "opt_ret_ask_bid": "ret ask/bid %"}))
    out = db.parent / f"backfill_report_{day}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    return out


if __name__ == "__main__":
    print(write_report(DB, sys.argv[1] if len(sys.argv) > 1 else None))
