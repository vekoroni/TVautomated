#!/usr/bin/env python3
"""Compare today's split hand-off with yesterday's (v1, 14 Oct 2026). Read-only on every input.

Answers, name by name (matched on ticker + side, because ledger_id carries the date):
    CARRIED   in both hand-offs: did the thesis, state, levels or contract change overnight?
    NEW       only today: which theses the latest run added
    DROPPED   only yesterday: why it left (gone from today's ledger, invalidated, no paying contract, ...)
and joins what was done with yesterday's names: the batch triage row (deep-mine rank, entry criterion, decision)
and, when the tracker has run, the session outcome (entry, status, 1-day return).

Run from the repo root (PowerShell):
    venv\\Scripts\\python.exe data\\scratch\\workaround\\compare_split_handoffs.py
        (today = newest split_* hand-off folder, prev = the one before it)
    venv\\Scripts\\python.exe data\\scratch\\workaround\\compare_split_handoffs.py --today data\\scratch\\workaround\\handoff\\split_2026-10-14_cap5 --prev data\\scratch\\workaround\\handoff\\split_2026-10-13_cap5
Writes into the today folder: compare_vs_<prev folder>.csv and compare_vs_<prev folder>.md

v2 (14 Oct): also reads yesterday's card decisions (decisions\\<TICKER>.json written by the deep dives, normalised by
collect_decisions.py) so a card that said enter but was never placed shows as "decided, order not recorded" instead of
a blank (BILI 13 Oct).
"""
from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

VERSION = "compare_split_handoffs_v2"
WORK = Path("data") / "scratch" / "workaround"
HAND = WORK / "handoff"
LEVELS = ["trigger", "half_target", "level", "invalidation"]


def folder_date(p: Path) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", p.name)
    return m.group(1) if m else ""


def default_pair(today: Path | None = None) -> tuple[Path, Path]:
    dirs = [Path(d) for d in glob.glob(str(HAND / "*")) if Path(d, "handoff.csv").exists()]
    if len(dirs) < 2:
        raise SystemExit("need two hand-off folders with handoff.csv under data\\scratch\\workaround\\handoff")
    # newest date first; for the same date prefer the capped folder, then the newest file
    dirs.sort(key=lambda d: (folder_date(d), "_cap" in d.name, Path(d, "handoff.csv").stat().st_mtime))
    today = today or dirs[-1]
    older = [d for d in dirs if folder_date(d) < folder_date(today)]
    if not older:
        raise SystemExit(f"no hand-off folder dated before {today.name}")
    return today, older[-1]


def load_handoff(d: Path) -> pd.DataFrame:
    h = pd.read_csv(d / "handoff.csv", low_memory=False)
    h["key"] = h["ticker"].astype(str) + "_" + h["side"].astype(str)
    return h.drop_duplicates("key")


def load_triage(dirs: list[Path]) -> pd.DataFrame:
    frames = []
    for f in [f for d in dirs if d.exists() for f in sorted(d.glob("*triage*.csv"))]:
        t = pd.read_csv(f, low_memory=False)
        if {"ticker", "side"} <= set(t.columns):
            t["triage_file"] = f.name
            frames.append(t)
    if not frames:
        return pd.DataFrame(columns=["key"])
    t = pd.concat(frames, ignore_index=True)
    t["key"] = t["ticker"].astype(str) + "_" + t["side"].astype(str)
    keep = ["key", "triage_file", "deep_mine_rank", "cluster", "entry_criterion", "entry_state", "trade_contract",
            "decision", "decision_reason", "contract_taken", "entry_premium"]
    t = t[[c for c in keep if c in t.columns]]
    # a name triaged in both lanes keeps the row with a decision, else the deep-mine pick, else the first
    t["_r"] = t.get("decision", pd.Series(index=t.index)).notna() * 2 + t.get("deep_mine_rank", pd.Series(index=t.index)).notna()
    return t.sort_values("_r", ascending=False).drop_duplicates("key").drop(columns="_r")


def load_cards(d: Path) -> pd.DataFrame:
    """Yesterday's card decisions from decisions\\*.json (the deep-dive agents' sidecar files)."""
    cards = sorted(d.glob("cards_*.csv"))
    if cards:   # collect_decisions.py output: decisions already normalised (JSON and triage-only decisions)
        c = pd.read_csv(cards[-1], low_memory=False).fillna("")
        c["key"] = c["ticker"].astype(str) + "_" + c["handoff_side"].astype(str)
        c = c[c["decision"].astype(str) != ""]
        return pd.DataFrame({"key": c["key"], "card_decision": c["decision"], "card_side": c.get("card_side", ""),
                             "card_contract": c.get("contract", ""), "card_entry": c.get("entry_type", ""),
                             "card_url": c.get("artifact_url", ""), "card_order_placed": c.get("order_placed", "")})
    rows = []
    for f in sorted((d / "decisions").glob("*.json")) if (d / "decisions").exists() else []:
        try:
            j = json.loads(f.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        side = j.get("handoff_side") or str(j.get("ledger_id", "")).rsplit("_", 1)[-1]
        contract = next((j.get(k) for k in ("contract_taken", "contract", "planned_contract", "contract_planned") if j.get(k)), "")
        rows.append({"key": f"{j.get('ticker', f.stem)}_{side}", "card_decision": j.get("decision"), "card_side": j.get("card_side", side),
                     "card_contract": contract, "card_entry": j.get("entry_type"), "card_url": j.get("artifact_url"),
                     "card_order_placed": "" if j.get("order_placed") is None else str(j.get("order_placed"))})
    return pd.DataFrame(rows, columns=["key", "card_decision", "card_side", "card_contract", "card_entry", "card_url", "card_order_placed"])


def load_ledger(date: str, suffix: str = "") -> pd.DataFrame:
    f = WORK / f"decision_ledger_{date}{suffix}.csv"
    if not date or not f.exists():
        return pd.DataFrame(columns=["key"])
    x = pd.read_csv(f, low_memory=False)
    x["key"] = x["ticker"].astype(str) + "_" + x["side"].astype(str)
    return x.drop_duplicates("key")


def pct(a, b):
    try:
        a, b = float(a), float(b)
        return round((b / a - 1) * 100, 2) if a else np.nan
    except (TypeError, ValueError):
        return np.nan


def dropped_reason(key: str, L: pd.DataFrame, O: pd.DataFrame) -> str:
    o = O[O.key == key] if len(O) else O
    if len(o):
        st = str(o.iloc[0].get("status", ""))
        if st in ("INVALIDATED", "STOP", "TARGET", "EXPIRED"):
            return f"tracker: {st}"
    r = L[L.key == key] if len(L) else L
    if not len(r):
        return "thesis not in today's ledger (run no longer carries it)"
    r = r.iloc[0]
    st = str(r.get("state", ""))
    if st.startswith("WAIT_TRIGGER_FAR"):
        return f"today's state {st}: trigger moved out of the 0.5 ATR window"
    if st == "READY_OLD_EVENT":
        return "today's state READY_OLD_EVENT: break is no longer fresh"
    if str(r.get("focus_v3")) not in ("True", "1", "true"):
        return f"not a focus name today (state {st})"
    return f"in today's ledger ({st}) but not handed over: no contract that pays, or no expiry covering q50"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today")
    ap.add_argument("--prev")
    a = ap.parse_args()
    if a.today and a.prev:
        today, prev = Path(a.today), Path(a.prev)
    else:
        dt, dp = default_pair(Path(a.today) if a.today else None)
        today, prev = dt, Path(a.prev) if a.prev else dp
    T, P = load_handoff(today), load_handoff(prev)
    # the ledger date comes from the ledger_id (the 12 Oct hand-off sits in a folder named 2026-10-11)
    d_today = str(T["ledger_id"].iloc[0])[:10]
    d_prev = str(P["ledger_id"].iloc[0])[:10]
    L_today = load_ledger(d_today)
    # yesterday's triage rows: the split batch triage plus the Morning Gate lane's triage of the same date
    tri = load_triage([prev, HAND / f"morning_{d_prev}"])
    O_prev = load_ledger(d_prev, "_outcomes")
    K_prev = load_cards(prev)

    keys = sorted(set(T.key) | set(P.key))
    rows = []
    for k in keys:
        t = T[T.key == k].iloc[0] if k in set(T.key) else None
        p = P[P.key == k].iloc[0] if k in set(P.key) else None
        s = t if t is not None else p
        r = {"ticker": s["ticker"], "side": s["side"],
             "status": "CARRIED" if t is not None and p is not None else ("NEW" if t is not None else "DROPPED"),
             "ledger_id_today": t["ledger_id"] if t is not None else "", "ledger_id_prev": p["ledger_id"] if p is not None else "",
             "batch_prev": p["batch"] if p is not None else np.nan, "batch_today": t["batch"] if t is not None else np.nan,
             "class_prev": p["handoff_class"] if p is not None else "", "class_today": t["handoff_class"] if t is not None else "",
             "state_prev": p["state"] if p is not None else "", "state_today": t["state"] if t is not None else ""}
        flags = []
        if t is not None and p is not None:
            # thesis_id formats differ between ledger builders, so the thesis is compared on what defines it
            trig = pct(p.get("trigger"), t.get("trigger"))
            r["setup_prev"], r["setup_today"] = f"{p.get('timeframe')} {p.get('setup')}", f"{t.get('timeframe')} {t.get('setup')}"
            r["same_thesis"] = r["setup_prev"] == r["setup_today"] and (pd.isna(trig) or abs(trig) <= 0.1)
            if not r["same_thesis"]:
                flags.append("THESIS_CHANGED")
            for c in LEVELS:
                r[f"{c}_prev"], r[f"{c}_today"] = p.get(c), t.get(c)
                r[f"{c}_chg_pct"] = pct(p.get(c), t.get(c))
            if any(abs(r[f"{c}_chg_pct"]) > 0.5 for c in LEVELS if pd.notna(r[f"{c}_chg_pct"])):
                flags.append("LEVELS_MOVED")
            if r["class_prev"] == "NEAR" and r["class_today"] == "CONFIRMED":
                flags.append("TRIGGER_CONFIRMED_OVERNIGHT")
            if r["class_prev"] == "CONFIRMED" and r["class_today"] == "NEAR":
                flags.append("FELL_BACK_TO_NEAR")
            r["ref_price_prev"], r["ref_price_today"] = p.get("ref_price"), t.get("ref_price")
            r["ref_move_pct"] = pct(p.get("ref_price"), t.get("ref_price"))
            r["contract_prev"], r["contract_today"] = p.get("best_contract"), t.get("best_contract")
            r["ask_prev"], r["ask_today"] = p.get("best_ask"), t.get("best_ask")
            if str(r["contract_prev"]) != str(r["contract_today"]):
                flags.append("CONTRACT_CHANGED")
            r["ret_half_prev"], r["ret_half_today"] = p.get("best_ret_half_target_q50"), t.get("best_ret_half_target_q50")
        elif t is not None:
            r["contract_today"], r["ask_today"] = t.get("best_contract"), t.get("best_ask")
            r["ret_half_today"] = t.get("best_ret_half_target_q50")
            for c in LEVELS:
                r[f"{c}_today"] = t.get(c)
        else:
            r["contract_prev"], r["ask_prev"] = p.get("best_contract"), p.get("best_ask")
            r["dropped_reason"] = dropped_reason(k, L_today, O_prev)
        tr = tri[tri.key == k] if len(tri) else tri
        if len(tr):
            for c in tr.columns:
                if c != "key":
                    r[f"prev_{c}"] = tr.iloc[0][c]
            if pd.notna(r.get("prev_deep_mine_rank")):
                flags.append("DEEP_DIVE_NAME_DROPPED" if r["status"] == "DROPPED" else "DEEP_DIVE_NAME")
        kc = K_prev[K_prev.key == k] if len(K_prev) else K_prev
        if len(kc):
            for c in kc.columns:
                if c != "key":
                    r[f"prev_{c}"] = kc.iloc[0][c]
            dec = str(kc.iloc[0]["card_decision"] or "").upper()
            placed = str(kc.iloc[0]["card_order_placed"] if pd.notna(kc.iloc[0]["card_order_placed"]) else "").strip()
            if dec in ("TRADE", "ENTER", "WATCH") and placed == "":   # nothing recorded at all ("no" + reason counts as recorded)
                flags.append("CARD_DECIDED_ORDER_NOT_RECORDED")
        o = O_prev[O_prev.key == k] if len(O_prev) else O_prev
        if len(o):
            for c in ["entry_rule", "entry_session", "entry_price", "status", "status_half_vs_invalidation", "close_ret_pct_1d",
                      "mfe_atr_1d", "mae_atr_1d"]:
                if c in o.columns:
                    r[f"prev_outcome_{c}"] = o.iloc[0][c]
        r["flags"] = ";".join(flags)
        rows.append(r)
    C = pd.DataFrame(rows)
    order = {"CARRIED": 0, "NEW": 1, "DROPPED": 2}
    C["_o"] = C.status.map(order)
    C = C.sort_values(["_o", "batch_today", "batch_prev", "ticker"]).drop(columns="_o")
    out_csv = today / f"compare_vs_{prev.name}.csv"
    C.to_csv(out_csv, index=False)

    n = C.status.value_counts().to_dict()
    md = [f"# Split hand-off {today.name} vs {prev.name}", "",
          f"{VERSION}. Matched on ticker + side. CARRIED {n.get('CARRIED', 0)}, NEW {n.get('NEW', 0)}, DROPPED {n.get('DROPPED', 0)} "
          f"(today {len(T)} names, yesterday {len(P)}).", ""]
    if not len(O_prev):
        md += [f"No outcomes file for {d_prev} yet: run track_outcomes.py on decision_ledger_{d_prev}.csv first for what each name did.", ""]
    dd = C[C["flags"].str.contains("DEEP_DIVE_NAME", na=False)]
    if len(dd):
        md += ["## Yesterday's deep-dive names", "", "| Name | Today | Flags | Yesterday's pick and decision | Card (side, contract) | Outcome, 1-day return % |", "|---|---|---|---|---|---|"]
        for _, r in dd.iterrows():
            v = lambda c: "" if pd.isna(r.get(c)) else r.get(c)
            md.append(f"| {r['ticker']} {r['side']} | {r['status']} {v('class_today')} | {v('flags')} | rank {v('prev_deep_mine_rank')} {v('prev_decision') or v('prev_card_decision')} | "
                      f"{v('prev_card_side')} {v('prev_card_contract')} | {v('prev_outcome_status')} {v('prev_outcome_close_ret_pct_1d')} |")
        md.append("")
    for flag, title in [("CARD_DECIDED_ORDER_NOT_RECORDED", "Cards with a decision but no recorded order (check Tastytrade, record filled / not placed + why)"),
                        ("TRIGGER_CONFIRMED_OVERNIGHT", "Confirmed overnight (NEAR to CONFIRMED)"), ("THESIS_CHANGED", "Thesis changed"),
                        ("CONTRACT_CHANGED", "Contract changed"), ("FELL_BACK_TO_NEAR", "Fell back to NEAR")]:
        x = C[C["flags"].str.contains(flag, na=False)]
        if len(x):
            md += [f"## {title} ({len(x)})", "", ", ".join(f"{a} {b}" for a, b in zip(x.ticker, x.side)), ""]
    new1 = C[(C.status == "NEW") & (C.batch_today == 1)]
    if len(new1):
        md += [f"## New in batch 1 ({len(new1)})", "", ", ".join(f"{a} {b}" for a, b in zip(new1.ticker, new1.side)), ""]
    dr = C[C.status == "DROPPED"]
    if len(dr):
        md += ["## Dropped, by reason", ""]
        for why, g in dr.groupby("dropped_reason"):
            md.append(f"- {why}: {len(g)} ({', '.join(g.ticker.head(12))}{'...' if len(g) > 12 else ''})")
        md.append("")
    (today / f"compare_vs_{prev.name}.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[:3]))
    print(f"wrote {out_csv} and .md")


if __name__ == "__main__":
    main()
