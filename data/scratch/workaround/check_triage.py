#!/usr/bin/env python3
"""Check the B3 triage output before any deep dive starts (v1, 16 Oct 2026). Read-only on every input. No credits.

Why: from 19 Oct the triage runs unattended as a scheduled task. Nobody watches it write, so its output is checked here
before ACK starts the manual deep dives. The deep dives read the triage CSV and deep_dive_prompts_<session>.md, so a
wrong rank, a missing name, a stale ledger_id or an unfilled prompt would carry straight into the mining.

FAIL (exit 1)  do not start deep dives: fix the triage (re-run it in a chat) first
WARN           start, but read the line: the deep dive must answer it
Checks
  files      batch1_triage_<session>.csv and deep_dive_prompts_<session>.md exist in today's split hand-off
  names      every hand-off batch-1 name is on the triage once; no name the hand-off does not carry; ledger_id matches
  rank       deep_mine_rank starts with a whole number, 1..N, no gaps, no duplicates
  columns    the standard columns are present and the decision columns are still empty
  contract   OCC symbol, underlying = ticker, expiry after the session, ask within the premium cap; differs from
             best_contract_checked only with a contract_why
  earnings   the triage's Tastytrade date agrees (within 1 day) with the hand-off earnings_date
  prompts    one section per ranked name, headed with its rank and ticker, containing the session and the hand-off
             path, with no unfilled placeholders
  packs      every name has a pack in packs_folder (else the avs_day.ps1 packs -Tickers line to paste)
  inbox      lessons\\fix_inbox\\<session>_triage.md exists

Run (PowerShell, repo root), or let avs_day.ps1 checktriage run it:
    venv\\Scripts\\python.exe data\\scratch\\workaround\\check_triage.py
    venv\\Scripts\\python.exe data\\scratch\\workaround\\check_triage.py --folder data\\scratch\\workaround\\handoff\\split_2026-10-14_cap5 --session 2026-10-14
Writes check_triage_<session>.md into the hand-off folder.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd

VERSION = "check_triage_v1"
WORK = Path("data") / "scratch" / "workaround"
OCC = re.compile(r"\b([A-Z]{1,6})\s*(\d{2})(\d{2})(\d{2})([CP])(\d{8})\b")
NEED = ["deep_mine_rank", "ticker", "ledger_id", "side", "trigger", "kill", "trade_contract", "pays_at_half_target",
        "earnings_tastytrade", "cluster", "main_challenge", "rank_reason"]
EMPTY = ["decision", "decision_reason", "contract_taken", "entry_type", "entry_premium"]
PLACEHOLDER = re.compile(r"<\s*(TICKER|ticker|session|SESSION|rank|path|folder)\s*>|\{(ticker|session|rank)\}|YYYY-MM-DD")


def s(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", help="split hand-off folder (default: split_handoff in today_context.json)")
    ap.add_argument("--session", help="session date (default: session in today_context.json)")
    a = ap.parse_args()
    ctx = {}
    cpath = WORK / "today_context.json"
    if cpath.exists():
        ctx = json.loads(cpath.read_text(encoding="utf-8-sig"))
    folder = Path(a.folder or ctx.get("split_handoff") or ".")
    session = a.session or ctx.get("session")
    cap = float(ctx.get("premium_cap") or 5)
    packs = Path(ctx["packs_folder"]) if ctx.get("packs_folder") else None
    fails, warns, notes = [], [], []

    tri = folder / f"batch1_triage_{session}.csv"
    prm = folder / f"deep_dive_prompts_{session}.md"
    hof = folder / "handoff.csv"
    if not hof.exists():
        fails.append(f"no handoff.csv in {folder}: run avs_day.ps1 evening first")
    if not tri.exists():
        fails.append(f"{tri.name} is missing: the triage did not run or did not save")
    if fails:
        return report(folder, session, fails, warns, notes)

    T = pd.read_csv(tri, dtype=str, keep_default_na=False)
    H = pd.read_csv(hof, dtype=str, keep_default_na=False)
    T["ticker"] = T["ticker"].str.upper().str.strip()
    H["ticker"] = H["ticker"].str.upper().str.strip()
    H1 = H[H["batch"].astype(str) == "1"]

    # columns
    miss = [c for c in NEED if c not in T.columns]
    if miss:
        fails.append("missing columns: " + ", ".join(miss))
    for c in EMPTY:
        if c not in T.columns:
            fails.append(f"decision column {c} is missing (it must exist, empty)")
        elif (T[c].str.strip() != "").any():
            warns.append(f"decision column {c} already filled for: " + ", ".join(T.loc[T[c].str.strip() != "", "ticker"]) +
                         " (the triage must leave decisions to the deep dive)")

    # names and ledger ids
    dup = T["ticker"][T["ticker"].duplicated()].unique().tolist()
    if dup:
        fails.append("name on the triage twice: " + ", ".join(dup))
    gone = sorted(set(H1["ticker"]) - set(T["ticker"]))
    extra = sorted(set(T["ticker"]) - set(H["ticker"]))
    if gone:
        fails.append("hand-off batch-1 names missing from the triage: " + ", ".join(gone))
    if extra:
        fails.append("names on the triage that the hand-off does not carry: " + ", ".join(extra))
    if "ledger_id" in T.columns:
        hid = dict(zip(H["ticker"], H["ledger_id"]))
        bad = [f"{t} ({l} vs hand-off {hid.get(t)})" for t, l in zip(T["ticker"], T["ledger_id"]) if t in hid and l != hid[t]]
        if bad:
            fails.append("ledger_id differs from the hand-off: " + "; ".join(bad))

    # rank
    if "deep_mine_rank" in T.columns:
        nums = T["deep_mine_rank"].str.extract(r"^\s*(\d+)")[0]
        if nums.isna().any():
            fails.append("deep_mine_rank without a leading number: " + ", ".join(T.loc[nums.isna(), "ticker"]))
        r = pd.to_numeric(nums, errors="coerce").dropna().astype(int)
        if len(r) and sorted(r) != list(range(1, len(r) + 1)):
            fails.append(f"deep_mine_rank is not 1..{len(r)} without gaps or duplicates: {sorted(r)}")
        T["_rank"] = pd.to_numeric(nums, errors="coerce")
    else:
        T["_rank"] = range(1, len(T) + 1)

    # contracts
    sess = datetime.strptime(session, "%Y-%m-%d").date()
    best = {t: (s(b) or s(c)) for t, b, c in zip(H["ticker"], H.get("best_contract_checked", H["best_contract"]), H["best_contract"])}
    for _, row in T.iterrows():
        t, raw = row["ticker"], s(row.get("trade_contract"))
        m = OCC.search(raw.upper())
        if not m:
            if raw.lower() in ("", "none", "n/a"):
                warns.append(f"{t}: no contract (reason: {s(row.get('rank_reason'))[:90] or 'not given'})")
            else:
                fails.append(f"{t}: trade_contract '{raw}' is not an OCC symbol")
            continue
        und, yy, mm, dd, cp, strike = m.groups()
        if und != t:
            fails.append(f"{t}: contract underlying {und} is not the ticker")
        exp = date(2000 + int(yy), int(mm), int(dd))
        if exp <= sess:
            fails.append(f"{t}: contract expires {exp}, not after the session")
        side = s(row.get("side")).upper()
        if side in ("CALL", "PUT") and cp != side[0]:
            warns.append(f"{t}: contract is a {'call' if cp == 'C' else 'put'} but the row side is {side} (state the flip in the prompt)")
        q = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", " ".join(s(row.get(c)) for c in T.columns if "quote" in c))
        if q and float(q.group(2)) > cap + 1e-9:
            warns.append(f"{t}: ask {q.group(2)} is over the premium cap {cap:g}")
        b = best.get(t, "")
        if b and und + m.group(2) + m.group(3) + m.group(4) + cp + strike != b.replace(" ", "") and not s(row.get("contract_why")):
            warns.append(f"{t}: contract {raw} differs from best_contract_checked {b} with no contract_why")

    # earnings
    if "earnings_date" in H.columns and "earnings_tastytrade" in T.columns:
        he = dict(zip(H["ticker"], H["earnings_date"]))
        for t, e in zip(T["ticker"], T["earnings_tastytrade"]):
            d1 = re.search(r"\d{4}-\d{2}-\d{2}", s(e))
            d2 = re.search(r"\d{4}-\d{2}-\d{2}", s(he.get(t)))
            if d1 and d2 and abs((date.fromisoformat(d1.group()) - date.fromisoformat(d2.group())).days) > 1:
                warns.append(f"{t}: earnings Tastytrade {d1.group()} vs hand-off {d2.group()}: the deep dive confirms which")

    # prompts
    if not prm.exists():
        fails.append(f"{prm.name} is missing: the deep dives have no prompts (the triage must save it)")
    else:
        text = prm.read_text(encoding="utf-8-sig")
        heads = [(i, ln) for i, ln in enumerate(text.splitlines()) if ln.lstrip().startswith("#")]
        lines = text.splitlines()
        for _, row in T.sort_values("_rank").iterrows():
            t, rk = row["ticker"], row["_rank"]
            hit = [i for i, ln in heads if re.search(rf"\b{t}\b", ln) and (pd.isna(rk) or re.search(rf"\b{int(rk)}\b", ln))]
            if not hit:
                fails.append(f"prompts: no section headed with rank {s(rk)} and {t}")
                continue
            start = hit[0]
            nxt = [i for i, _ in heads if i > start and re.match(r"\s*#{1,2}\s", lines[i])]
            body = "\n".join(lines[start:(nxt[0] if nxt else len(lines))])
            if session not in body:
                fails.append(f"prompts {t}: the session {session} is not in its section")
            if folder.name not in body:
                warns.append(f"prompts {t}: the hand-off folder {folder.name} is not named in its section")
            if PLACEHOLDER.search(body):
                fails.append(f"prompts {t}: unfilled placeholder '{PLACEHOLDER.search(body).group()}'")
            if "OUTPUT" not in body.upper():
                warns.append(f"prompts {t}: no OUTPUT block")
        notes.append(f"prompts file {prm.name}: {len(text):,} characters, {len(heads)} headings")

    # packs and inbox
    if packs and packs.exists():
        nopack = [t for t in T["ticker"] if not (packs / f"{t}_pack.zip").exists()]
        if nopack:
            warns.append("no pack for: " + " ".join(nopack) + f"  ->  avs_day.ps1 packs -Tickers {' '.join(nopack)}")
    else:
        warns.append(f"packs folder not found: {packs}")
    inbox = WORK / "lessons" / "fix_inbox" / f"{session}_triage.md"
    if not inbox.exists():
        warns.append(f"no fix-inbox file {inbox.name} (the triage writes one, 'none' if clean)")

    notes.append(f"{len(T)} names on the triage, {len(H1)} hand-off batch-1 names, premium cap {cap:g}")
    order = T.sort_values("_rank")
    notes.append("deep-dive order: " + ", ".join(f"{s(r)} {t}" for r, t in zip(order["deep_mine_rank"], order["ticker"])))
    return report(folder, session, fails, warns, notes)


def report(folder: Path, session, fails, warns, notes) -> int:
    verdict = "FAIL" if fails else ("PASS WITH WARNINGS" if warns else "PASS")
    md = [f"# Triage check, session {session}: {verdict}", "", f"{VERSION}, {datetime.now():%Y-%m-%d %H:%M} local.", ""]
    if fails:
        md += ["## FAIL: do not start the deep dives", ""] + [f"- {x}" for x in fails] + [""]
    if warns:
        md += ["## WARN: the deep dive must answer these", ""] + [f"- {x}" for x in warns] + [""]
    md += ["## Notes", ""] + [f"- {x}" for x in notes]
    if folder.exists():
        (folder / f"check_triage_{session}.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
