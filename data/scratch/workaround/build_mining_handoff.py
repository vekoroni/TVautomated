#!/usr/bin/env python3
"""Build the hand-off from the opportunity work to the per-ticker data-mining function (v2, 14 Oct 2026).

v2 (14 Oct fix inbox): earnings_date filled from the run's catalyst_truth when the ledger has none (it was null on every
row), with earnings_sessions, an IV-term-structure cross-check and a flag when the print falls inside q80 or within
2 sessions; a CONFIRMED row whose reference close is not beyond its trigger is demoted to NEAR (WIX 71.74 vs 71.75);
each contract is flagged against the +20% minimum at the half target (GME +14.5% was shown as paying); every shortlist
contract is checked (>= +20% at the half target, >= 14 days left at the q80 exit, not expiring within 14 days after a
print inside the hold, open interest not thin, spread <= 25% of mid) and the first clean contract is named as
best_contract_checked. The pipeline's own best_contract fields are left as they were.

Joins, by ledger_id, the newest decision ledger, the newest options-intelligence run and (when present) the newest
outcome-tracker file, picks the names ready for mining, and writes one folder the mining chat reads:

    data/scratch/workaround/handoff/<YYYY-MM-DD>/
        handoff.csv            one row per candidate, everything already known (the mining step does not redo it)
        <TICKER>_<SIDE>.json   the same, per candidate, plus the option shortlist and expiry context
        handoff.md             the ordered list, the reason each name is on it, and the line to start each mining chat
        ticker_pack_command.txt  the ticker_pack.py command for these names

Run from the repo root after the options tool (and, from Tuesday, after the outcome tracker):
    venv\\Scripts\\python.exe data\\scratch\\workaround\\build_mining_handoff.py
Options: --max (names in the hand-off, default all), --batch-size 30 (triage batches), --ledger, --options-run, --outcomes, --out.\nMANUAL rows (readiness MANUAL) carry a thesis written by a mining chat for a ticker the pipeline did not hand over.

Who is "ready for mining":
    CONFIRMED   READY thesis (break already accepted), or a WAIT thesis whose trigger the tracker shows confirmed on a close
    NEAR        WAIT thesis within 0.5 ATR of its trigger: prepared now, traded only if it closes beyond the trigger
Excluded: no usable contract or no expiry covering the median time; the best contract loses money even if the stock
reaches the level by the median time (it does not mirror the move); invalidated or finished per the tracker.
Order (no weights): CONFIRMED before NEAR > best contract pays at the half target > quicker realisation > half-target-first odds.
"""
from __future__ import annotations

import argparse
import glob
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

WORK = Path("data") / "scratch" / "workaround"
OPTS = Path("data") / "scratch" / "options_intel"
RUNS = Path("data") / "output" / "runs"
MIN_PAY = 0.20            # the pipeline's monetisability minimum at the half target
MIN_DAYS_AT_EXIT = 14     # calendar days left at the planned (q80) exit
MAX_SPREAD = 0.25         # spread as a share of mid
HOLIDAYS = ["2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
            "2027-06-18", "2027-07-05"]   # NYSE full closures (Good Friday 2027 = 26 Mar; Juneteenth and 4 Jul observed)
REAL_ORDER = {"1-3 sessions": 0, "4-10 sessions": 1, "11-20 sessions": 2, "21-60 sessions": 3, ">60 sessions": 4}


def newest(pattern: str) -> Path | None:
    hits = sorted(glob.glob(pattern))
    return Path(hits[-1]) if hits else None


def sessions_between(a: str, b) -> float:
    """NYSE sessions from session a (exclusive) to date b (inclusive of b's session)."""
    try:
        return float(np.busday_count(np.datetime64(a[:10], 'D'), np.datetime64(str(b)[:10], 'D') + np.timedelta64(1, 'D'), holidays=HOLIDAYS) - 1)
    except Exception:
        return np.nan


def load_event_dates(source_runs, after: str) -> dict:
    """ticker -> next dated catalyst from the run's catalyst_truth (it carries the earnings date; Tastytrade agreed on
    all 13 names checked on 14 Oct). Requires live confirmation, so the source is written beside it."""
    out = {}
    for rid in sorted({str(r) for r in source_runs if pd.notna(r)}, reverse=True):   # newest run wins
        f = newest(str(RUNS / rid / "catalysts" / "catalyst_truth_*.csv"))
        if f is None:
            continue
        ct = pd.read_csv(f, usecols=lambda c: c in ("ticker", "catalyst_date", "catalyst_type"), low_memory=False)
        ct = ct.dropna(subset=["catalyst_date"])
        ct = ct[ct["catalyst_date"].astype(str).str[:10] >= after]          # a date already passed is not the next print
        typ = ct["catalyst_type"].astype(str) if "catalyst_type" in ct else pd.Series("", index=ct.index)
        for t, d, k in zip(ct["ticker"].astype(str), ct["catalyst_date"].astype(str), typ):
            out.setdefault(t, (d[:10], f"catalyst_truth {rid}, type {k} (dated catalyst; confirm the print date live)"))
    return out


def iv_jump_expiry(ex: pd.DataFrame, rel: float = 0.15):
    """First expiry whose ATM IV is >= 15% above the previous expiry's: a dated event is priced between the two."""
    if ex is None or not len(ex) or "atm_iv" not in ex:
        return None, None
    e = ex.sort_values("expiry")
    iv = pd.to_numeric(e["atm_iv"], errors="coerce").values
    exp = e["expiry"].astype(str).values
    for i in range(1, len(iv)):
        if iv[i - 1] > 0 and iv[i] >= iv[i - 1] * (1 + rel):
            return exp[i - 1], exp[i]
    return None, None


def check_shortlist(sl: pd.DataFrame, q80: float, earn: str | None) -> pd.DataFrame:
    if not len(sl):
        return sl
    sl = sl.copy()
    oi = pd.to_numeric(sl.get("oi"), errors="coerce")
    max_oi = oi.max() if oi.notna().any() else np.nan
    flags = []
    for _, c in sl.iterrows():
        f = []
        ret = pd.to_numeric(c.get("ret_half_target_q50"), errors="coerce")
        if pd.isna(ret) or ret < MIN_PAY:
            f.append("UNDER_20PCT_AT_HALF")
        dte, ste = pd.to_numeric(c.get("dte_calendar_days"), errors="coerce"), pd.to_numeric(c.get("sessions_to_expiry"), errors="coerce")
        if pd.notna(dte) and pd.notna(ste) and pd.notna(q80) and ste > 0:
            days_left = dte - q80 * dte / ste
            if days_left < MIN_DAYS_AT_EXIT:
                f.append("UNDER_14D_AT_Q80_EXIT")
        if earn and pd.notna(c.get("expiry")):
            gap = (pd.Timestamp(str(c["expiry"])[:10]) - pd.Timestamp(earn)).days
            if 0 <= gap < MIN_DAYS_AT_EXIT:
                f.append("EXPIRES_WITHIN_14D_AFTER_PRINT")
        o = pd.to_numeric(c.get("oi"), errors="coerce")
        if pd.notna(o) and o < 500 and pd.notna(max_oi) and o < 0.1 * max_oi:
            f.append("THIN_OI")
        sp = pd.to_numeric(c.get("spread_fraction_of_mid"), errors="coerce")
        if pd.notna(sp) and sp > MAX_SPREAD:
            f.append("WIDE_SPREAD")
        flags.append(";".join(f))
    sl["check_flags"] = flags
    # fewest failed checks first, then the options tool's own rank
    sl["check_rank"] = sl["check_flags"].map(lambda f: len([x for x in f.split(";") if x])) * 1000 \
        + pd.to_numeric(sl.get("shortlist_rank"), errors="coerce").fillna(999)
    return sl.sort_values("check_rank")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger")
    ap.add_argument("--options-run")
    ap.add_argument("--outcomes")
    ap.add_argument("--max", type=int, default=100000)
    ap.add_argument("--batch-size", type=int, default=30)
    ap.add_argument("--out", help="output folder (default data\\scratch\\workaround\\handoff\\<today>)")
    a = ap.parse_args()

    ledger = Path(a.ledger) if a.ledger else next(iter(sorted((h for h in glob.glob(str(WORK / "decision_ledger_*.csv"))
                                                                if not h.endswith(("_outcomes.csv", "_summary.csv"))), reverse=True)), None)
    ledger = Path(ledger) if ledger else None
    run = Path(a.options_run) if a.options_run else newest(str(OPTS / "*"))
    outcomes = Path(a.outcomes) if a.outcomes else newest(str(WORK / "decision_ledger_*_outcomes.csv"))
    if ledger is None or run is None:
        raise SystemExit("Need a decision ledger and an options-intelligence run (run the options tool first)")
    L = pd.read_csv(ledger)
    S = pd.read_csv(run / "thesis_summary.csv")
    SL = pd.read_csv(run / "shortlist.csv") if (run / "shortlist.csv").exists() else pd.DataFrame()
    EX = pd.read_csv(run / "expiry_context.csv") if (run / "expiry_context.csv").exists() else pd.DataFrame()
    O = pd.read_csv(outcomes) if outcomes is not None and outcomes.exists() else pd.DataFrame()

    d = L[L["focus_v3"].astype(str).str.upper() == "TRUE"].merge(
        S.drop(columns=[c for c in ["ticker", "side", "level", "half_target", "invalidation", "q50_sessions", "q80_sessions"] if c in S]),
        on="ledger_id", how="left")
    if len(O):
        d = d.merge(O[["ledger_id", "status", "entry_session", "entry_price", "status_half_vs_invalidation"]].rename(
            columns={"status": "tracker_status"}), on="ledger_id", how="left")
    else:
        d["tracker_status"] = np.nan

    # earnings: the ledger column was null on every row (14 Oct); fill from the run's catalyst_truth
    sess0 = str(d["decision_session"].iloc[0]) if "decision_session" in d and len(d) else date.today().isoformat()
    ev = load_event_dates(d["source_run"], sess0[:10]) if "source_run" in d else {}
    if "earnings_date" not in d:
        d["earnings_date"] = pd.Series(None, index=d.index, dtype=object)
    d["earnings_date"] = d["earnings_date"].astype(object)   # an all-null column is float: pandas 3 refuses date strings in it
    miss = d["earnings_date"].isna()
    d["earnings_source"] = np.where(miss, "", "ledger")
    fill = d.loc[miss, "ticker"].astype(str).map(lambda t: ev.get(t, (None, None)))
    d.loc[miss, "earnings_date"] = fill.map(lambda x: x[0])
    d.loc[miss, "earnings_source"] = fill.map(lambda x: x[1] or "MISSING: confirm on Tastytrade")
    d["earnings_sessions"] = [sessions_between(sess0, e) if isinstance(e, str) and e[:2] == "20" else np.nan for e in d["earnings_date"]]
    d["earnings_in_q80"] = (d["earnings_sessions"] >= 0) & (d["earnings_sessions"] <= pd.to_numeric(d["q80_sessions"], errors="coerce"))
    d["earnings_within_2_sessions"] = (d["earnings_sessions"] >= 0) & (d["earnings_sessions"] <= 2)

    ready = d["readiness"].astype(str).str.startswith("READY")
    wait_confirmed = d["readiness"].eq("WAIT_TRIGGER") & d["tracker_status"].notna() & ~d["tracker_status"].isin(["NOT_TRIGGERED", "NO_DATA_YET"])
    near = d["readiness"].eq("WAIT_TRIGGER") & d["state"].eq("WAIT_TRIGGER_0.5ATR") & ~wait_confirmed
    manual = d["readiness"].eq("MANUAL")  # a thesis written by a mining chat, not by the pipeline
    d["handoff_class"] = np.select([ready | wait_confirmed, near, manual], ["CONFIRMED", "NEAR", "MANUAL"], "")
    # CONFIRMED means a close beyond the trigger: demote a READY row whose reference close is not beyond it (WIX, 14 Oct)
    sgn = np.where(d["side"].astype(str) == "CALL", 1, -1)
    ref, trg = pd.to_numeric(d["ref_price"], errors="coerce"), pd.to_numeric(d["trigger"], errors="coerce")
    not_beyond = ready & ref.notna() & trg.notna() & ((ref - trg) * sgn < 0)
    d["class_note"] = np.where(not_beyond, "demoted: reference close not beyond the trigger", "")
    d.loc[not_beyond & (d["handoff_class"] == "CONFIRMED"), "handoff_class"] = "NEAR"
    finished = d["tracker_status"].isin(["TARGET", "STOP", "INVALIDATED", "STOP_SAME_BAR_AS_TARGET", "EXPIRED"])
    usable = d["contract_state"].isin(["COVERS_PLANNED_HOLD", "COVERS_MEDIAN_ONLY", "SHORT_DATED_EXCEPTION"])
    pays_level = pd.to_numeric(d["best_ret_level_q50"], errors="coerce") > 0
    c = d[(d["handoff_class"] != "") & usable & pays_level & ~finished].copy()
    c["real_order"] = c["realisation"].map(REAL_ORDER).fillna(9)
    c["class_order"] = c["handoff_class"].map({"CONFIRMED": 0, "NEAR": 1, "MANUAL": 2})
    # ordering unchanged from v1 (> 0): the +20% minimum is a flag on each contract, not a reason to reorder discovery
    c["pays_half"] = pd.to_numeric(c["best_ret_half_target_q50"], errors="coerce") > 0
    c["cap_order"] = 0 if "best_within_cap" not in c else np.where(c["best_within_cap"].astype(str).str.upper() == "FALSE", 1, 0)
    c = c.sort_values(["class_order", "cap_order", "pays_half", "real_order", "p_half_target_first"], ascending=[True, True, False, True, False])
    pick = c.head(a.max).copy()
    pick["batch"] = np.arange(len(pick)) // a.batch_size + 1
    checked = {}
    for r in pick.itertuples() if len(pick) else []:
        sl = SL[SL["ledger_id"] == r.ledger_id] if len(SL) else pd.DataFrame()
        e = r.earnings_date if isinstance(r.earnings_date, str) and bool(r.earnings_in_q80) else None
        checked[r.ledger_id] = check_shortlist(sl, pd.to_numeric(r.q80_sessions, errors="coerce"), e)
    def first_clean(lid):
        sl = checked.get(lid)
        if sl is None or not len(sl):
            return pd.Series({"best_contract_checked": None, "best_contract_flags": "NO_SHORTLIST"})
        top = sl.iloc[0]
        return pd.Series({"best_contract_checked": top.get("contract"), "best_contract_flags": top["check_flags"] or "clean"})
    if len(pick):
        pick = pick.join(pick["ledger_id"].apply(first_clean))
        pick["pipeline_best_flags"] = [((checked[l].loc[checked[l]["contract"] == b, "check_flags"].iloc[0] or "clean")
                                        if l in checked and len(checked[l]) and (checked[l]["contract"] == b).any() else "NOT_ON_SHORTLIST")
                                       for l, b in zip(pick["ledger_id"], pick["best_contract"])]
    else:
        pick["best_contract_checked"], pick["best_contract_flags"], pick["pipeline_best_flags"] = None, "", ""
    if len(EX):
        jumps = {t: iv_jump_expiry(g) for t, g in EX.groupby("ticker")}
        pick["iv_jump_between"] = pick["ticker"].map(lambda t: " -> ".join(x for x in jumps.get(t, (None, None)) if x) or "")

    out = Path(a.out) if a.out else WORK / "handoff" / date.today().isoformat()
    out.mkdir(parents=True, exist_ok=True)
    keep = ["batch", "ledger_id", "handoff_class", "ticker", "side", "state", "size_note", "realisation", "setup", "timeframe",
            "ref_price", "trigger", "half_target", "level", "invalidation", "q50_sessions", "q80_sessions",
            "p_half_target_first", "p_invalidation_first", "p_timeout", "conditions_rank_for_side", "checks3",
            "structure_evidence", "intraday_alignment", "vanguard_structure", "money", "sector_etf",
            "earnings_date", "earnings_source", "earnings_sessions", "earnings_in_q80", "earnings_within_2_sessions",
            "iv_jump_between", "class_note", "best_contract_checked", "best_contract_flags", "pipeline_best_flags", "contract_state", "best_contract", "best_expiry", "best_strike",
            "best_bid", "best_ask", "best_spread_fraction", "best_delta", "best_iv", "best_ret_half_target_q50",
            "best_ret_level_q50", "best_ret_invalidation_q50", "best_within_cap", "premium_cap", "near_atm_iv", "near_implied_move_pct",
            "call_oi_wall_near", "put_oi_wall_near", "put_call_oi_ratio_all", "level_flag", "tracker_status",
            "thesis_id", "source_run"]
    keep = [k for k in keep if k in pick.columns]
    pick[keep].to_csv(out / "handoff.csv", index=False)

    lines = [f"# Mining hand-off {date.today().isoformat()}", "",
             f"Ledger `{ledger.name}` · options run `{run.name}` · tracker `{outcomes.name if outcomes is not None else 'none yet'}`",
             f"{len(c)} candidates qualified; the first {len(pick)} are below. CONFIRMED = break accepted on a close; "
             "NEAR = within 0.5 ATR of the trigger, trade only after a close beyond it; "
             "MANUAL = thesis written by a mining chat (entry rule on its card).", ""]
    last_batch = None
    for i, r in enumerate(pick.itertuples(), 1):
        rid = r.ledger_id
        if r.batch != last_batch:
            b = pick[pick["batch"] == r.batch]
            lines += [f"# Batch {r.batch} ({len(b)} names: {int((b.handoff_class == 'CONFIRMED').sum())} confirmed, "
                      f"{int((b.side == 'CALL').sum())} calls / {int((b.side == 'PUT').sum())} puts)", "",
                      f"Packs: `venv\\Scripts\\python.exe tools\\ticker_pack.py {' '.join(b.ticker.unique())}`", ""]
            last_batch = r.batch
        js = {k: (None if pd.isna(getattr(r, k)) else getattr(r, k)) for k in keep}
        if len(SL):
            js["option_shortlist"] = checked[rid].drop(columns=[c for c in SL.columns if c.startswith("value_at_")], errors="ignore").to_dict("records") \
                if rid in checked and len(checked[rid]) else []
        if len(EX):
            js["expiry_context"] = EX[EX["ticker"] == r.ticker].to_dict("records")
        (out / f"{r.ticker}_{r.side}.json").write_text(json.dumps(js, indent=1, default=str))
        lines += [f"## {i}. {r.ticker} {r.side} - {r.handoff_class}",
                  f"- {r.setup} ({r.timeframe}); median {r.q50_sessions:.0f} / planned {r.q80_sessions:.0f} sessions; {r.size_note}",
                  f"- trigger {r.trigger} · half target {r.half_target} · level {r.level} · invalidation {r.invalidation}",
                  f"- earnings {r.earnings_date if isinstance(r.earnings_date, str) else 'MISSING'} ({r.earnings_source}; {'' if pd.isna(r.earnings_sessions) else int(r.earnings_sessions)} sessions"
                  f"{'; INSIDE q80' if r.earnings_in_q80 else ''}{'; WITHIN 2 SESSIONS' if r.earnings_within_2_sessions else ''})"
                  + (f"; IV term jump {r.iv_jump_between}" if getattr(r, 'iv_jump_between', '') else "")
                  + (f"; {r.class_note}" if r.class_note else ""),
                  f"- contract check: pipeline best {r.pipeline_best_flags}; "
                  + (f"first clean contract on the shortlist {r.best_contract_checked}" if r.best_contract_flags == "clean"
                     else f"no clean contract; least-flagged {r.best_contract_checked} ({r.best_contract_flags})"),
                  f"- half target before invalidation {r.p_half_target_first} vs {r.p_invalidation_first} (Vanguard store, in-sample)",
                  f"- best contract {r.best_contract} {r.best_bid}/{r.best_ask}: half target {r.best_ret_half_target_q50:+.0%}, "
                  f"level {r.best_ret_level_q50:+.0%}, invalidation {r.best_ret_invalidation_q50:+.0%}"
                  + (" - OVER THE PREMIUM CAP" if str(getattr(r, "best_within_cap", "")).upper() == "FALSE" else "") if pd.notna(r.best_ret_half_target_q50) else "- no option payoff computed",
                  f"- start the mining chat with: `/avshunter-ticker-mining TICKER - {r.ticker} - hand-off {str(out).replace('/', chr(92))}\\{r.ticker}_{r.side}.json - ledger_id {rid}`",
                  ""]
    (out / "handoff.md").write_text("\n".join(lines), encoding="utf-8")
    cmds = [f"# batch {b}\nvenv\\Scripts\\python.exe tools\\ticker_pack.py {' '.join(g.ticker.unique())}" for b, g in pick.groupby("batch")]
    (out / "ticker_pack_command.txt").write_text("\n".join(cmds) + "\n")
    tickers = " ".join(pick.loc[pick["batch"] == 1, "ticker"].unique())
    print(f"{len(c)} qualified ({(c.handoff_class == 'CONFIRMED').sum()} confirmed, {(c.handoff_class == 'NEAR').sum()} near); "
          f"{len(pick)} in the hand-off -> {out}")
    print("batches:", pick.groupby("batch").size().to_dict())
    print("batch 1 packs:", f"venv\\Scripts\\python.exe tools\\ticker_pack.py {tickers}")


if __name__ == "__main__":
    main()
