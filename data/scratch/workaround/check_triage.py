#!/usr/bin/env python3
"""Check the triage output before any deep dive starts (v4, 12 Nov 2026, Lane B Fix B4). Read-only on every input. No credits.

Why: the triage runs unattended as a scheduled task. Nobody watches it write, so its output is checked here before ACK
starts the manual deep dives. The deep dives read the triage CSV and the deep-dive prompts, so a wrong rank, a missing
name, a contract or target that is not the Lab's, or an unfilled prompt would carry straight into the mining.

v4 (12 Nov, Fix B4): the hand-off is the Lab's publication (handoff\\lab_<session>). The triage must use the Lab's
contract and the Lab's target; the 25% spread rule is replaced by the 11 Nov liquidity tiers; every batch is checked.

FAIL (exit 1)  advisory: fix the triage (re-run it in a chat) first
WARN           start, but read the line: the deep dive must answer it
Checks (per batch triage file)
  files      batch<N>_triage_<session>.csv exists; the deep-dive prompts file for the batch exists
  names      Lab-built triage (it carries a lab_revision column): every hand-off name of the batch is on the triage once,
             none the hand-off does not carry, ledger_id matches. Triage built from the old hand-off: membership is a note
  rank       deep_mine_rank starts with a whole number; consecutive, no gaps, no duplicates (batch 1 starts at 1; a later batch may continue the count)
  columns    the standard columns are present and the decision columns are still empty
  contract   OCC symbol, underlying = ticker, expiry after the session, ask within the premium cap.
             Lab hand-off: trade_contract must be the Lab contract (contract_symbol) or a named Lab alternative (when the
             Lab publishes alternatives, Codex A8); anything else is WARN
  target     Lab hand-off: the triage target must equal anticipated_level and its first profit anticipated_level_q50
  liquidity  the 11 Nov tiers on the triage's live quote: A spread <= 10% of mid, OI >= 100, and under a 1.50 premium the
             spread is <= 0.10 wide; B 10-20% (WARN); C over 20%, no bid or OI < 100 (WARN: not tradeable at this quote)
  earnings   the triage's Tastytrade date agrees (within 1 day) with the hand-off earnings_date
  prompts    one section per ranked name, headed with its rank and ticker, containing the session, no unfilled placeholders
  packs      every name has a pack in packs_folder (else the avs_day.ps1 packs -Tickers line to paste)
  inbox      lessons\\fix_inbox\\<session>_triage.md exists
  strategy   old hand-off layout only: strategy_layer_<session>.csv challenges become WARN lines

Run (PowerShell, repo root), or let avs_day.ps1 checktriage run it:
    venv\\Scripts\\python.exe data\\scratch\\workaround\\check_triage.py --all
    venv\\Scripts\\python.exe data\\scratch\\workaround\\check_triage.py --folder data\\scratch\\workaround\\handoff\\lab_2026-11-12 --session 2026-11-12 --batch 2
    venv\\Scripts\\python.exe data\\scratch\\workaround\\check_triage.py --folder data\\scratch\\workaround\\handoff\\lab_2026-11-12 --triage-folder data\\scratch\\workaround\\handoff\\split_2026-11-12_cap5 --session 2026-11-12 --all
Writes check_triage_<session>.md into the hand-off folder (--folder).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_lab_handoff import liquidity_tier, num, same_number  # noqa: E402  (one owner of the 11 Nov tiers)

VERSION = "check_triage_v4"   # v2 17 Oct spread gate; v3 18 Oct strategy layer; v4 12 Nov Lab contract/target, 11 Nov tiers, any batch
WORK = Path("data") / "scratch" / "workaround"
OCC = re.compile(r"\b([A-Z]{1,6})\s*(\d{2})(\d{2})(\d{2})([CP])(\d{8})\b")
NEED = ["deep_mine_rank", "ticker", "ledger_id", "side", "trigger", "kill", "trade_contract", "pays_at_half_target",
        "earnings_tastytrade", "cluster", "main_challenge", "rank_reason"]
# what a triage built from the Lab hand-off must carry (audit\laneb_fixB\triage_interface.md)
NEED_LAB = ["deep_mine_rank", "ticker", "ledger_id", "side", "lab_revision", "target", "first_profit", "trigger_state", "chase_state",
            "trade_contract", "contract_bid", "contract_ask", "contract_oi", "main_challenge", "rank_reason"]
EMPTY = ["decision", "decision_reason", "contract_taken", "entry_type", "entry_premium"]
PLACEHOLDER = re.compile(r"<\s*(TICKER|ticker|session|SESSION|rank|path|folder)\s*>|\{(ticker|session|rank)\}|YYYY-MM-DD")
QUOTE = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)")
QUOTE_OI = re.compile(r"\bOI\s*([\d,]+)", re.I)


def s(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()


def live_quote(row) -> tuple:
    """(bid, ask, oi) the triage wrote: the contract_bid / contract_ask / contract_oi columns, else the text of contract_quote."""
    bid, ask, oi = num(row.get("contract_bid")), num(row.get("contract_ask")), num(row.get("contract_oi"))
    text = " ".join(s(row.get(c)) for c in row.index if "quote" in c)
    if bid is None and ask is None:
        q = QUOTE.search(text)
        if q:
            bid, ask = float(q.group(1)), float(q.group(2))
    if oi is None:
        o = QUOTE_OI.search(text)
        if o:
            oi = float(o.group(1).replace(",", ""))
    return bid, ask, oi


def batch_number(path: Path) -> int:
    m = re.match(r"batch(\d+)_triage_", path.name)
    return int(m.group(1)) if m else 0


def prompts_file(folder: Path, session: str, batch: int) -> Path:
    first = folder / f"deep_dive_prompts_{session}.md"
    return first if batch == 1 else folder / f"deep_dive_prompts_{session}_b{batch}.md"


def check_batch(tri: Path, H: pd.DataFrame, lab: bool, session: str, cap: float, packs, handoff_folder: Path,
                fails: list, warns: list, notes: list) -> None:
    b = batch_number(tri)
    tag = f"batch {b}"
    T = pd.read_csv(tri, dtype=str, keep_default_na=False)   # keep_default_na=False: the ticker NAN is a real ticker
    if "ticker" not in T.columns:
        fails.append(f"{tag}: {tri.name} has no ticker column")
        return
    T["ticker"] = T["ticker"].str.upper().str.strip()
    batch_col, ledger_col = ("lb_batch", "lb_ledger_id") if lab else ("batch", "ledger_id")
    Hb = H[H[batch_col].astype(str) == str(b)]
    by = {t: r for t, r in zip(H["ticker"], H.to_dict("records"))}
    lab_built = lab and "lab_revision" in T.columns   # the triage was built from the Lab hand-off (it says which revision)

    # columns
    miss = [c for c in (NEED_LAB if lab_built else NEED) if c not in T.columns]
    if miss:
        fails.append(f"{tag}: missing columns: " + ", ".join(miss))
    for c in EMPTY:
        if c not in T.columns:
            fails.append(f"{tag}: decision column {c} is missing (it must exist, empty)")
        elif (T[c].str.strip() != "").any():
            warns.append(f"{tag}: decision column {c} already filled for: " + ", ".join(T.loc[T[c].str.strip() != "", "ticker"]) +
                         " (the triage must leave decisions to the deep dive)")

    # names and ledger ids
    dup = T["ticker"][T["ticker"].duplicated()].unique().tolist()
    if dup:
        fails.append(f"{tag}: name on the triage twice: " + ", ".join(dup))
    gone = sorted(set(Hb["ticker"]) - set(T["ticker"]))
    extra = sorted(set(T["ticker"]) - set(H["ticker"]))
    other = sorted(t for t in set(T["ticker"]) & set(H["ticker"]) if t not in set(Hb["ticker"]))
    if lab and not lab_built:
        notes.append(f"{tag}: {tri.name} was built from the old hand-off (no lab_revision column): batch membership is not checked. "
                     f"{len(set(T['ticker']) & set(Hb['ticker']))} of its {len(T)} names are in the Lab hand-off's batch {b}, "
                     f"{len(other)} are in another Lab batch, {len(extra)} are not in the Lab hand-off")
        if extra:
            warns.append(f"{tag}: not in the Lab hand-off (the Lab does not publish them as GO_LIMIT or MANUAL_REVIEW): " + ", ".join(extra))
    else:
        if gone:
            fails.append(f"{tag}: hand-off batch-{b} names missing from the triage: " + ", ".join(gone))
        if extra:
            fails.append(f"{tag}: names on the triage that the hand-off does not carry: " + ", ".join(extra)
                         + (" (not in the Lab hand-off)" if lab else ""))
        if other and lab:
            warns.append(f"{tag}: names that belong to another Lab batch: " + ", ".join(other))
    if "ledger_id" in T.columns:
        bad = [f"{t} ({l} vs hand-off {by[t].get(ledger_col)})" for t, l in zip(T["ticker"], T["ledger_id"]) if t in by and l != by[t].get(ledger_col)]
        if bad:
            (fails if (lab_built or not lab) else warns).append(f"{tag}: ledger_id differs from the hand-off: " + "; ".join(bad))

    # rank
    if "deep_mine_rank" in T.columns:
        nums = T["deep_mine_rank"].str.extract(r"^\s*(\d+)")[0]
        if nums.isna().any():
            fails.append(f"{tag}: deep_mine_rank without a leading number: " + ", ".join(T.loc[nums.isna(), "ticker"]))
        r = pd.to_numeric(nums, errors="coerce").dropna().astype(int)
        # consecutive whole numbers, no gaps, no duplicates. A later batch may continue the count (batch 2 = 31..60).
        if len(r) and sorted(r) != list(range(min(r), min(r) + len(r))):
            fails.append(f"{tag}: deep_mine_rank is not {min(r)}..{min(r) + len(r) - 1} without gaps or duplicates: {sorted(r)}")
        elif len(r) and min(r) != 1 and b == 1:
            fails.append(f"{tag}: deep_mine_rank starts at {min(r)}, not 1")
        T["_rank"] = pd.to_numeric(nums, errors="coerce")
    else:
        T["_rank"] = range(1, len(T) + 1)

    # per row: contract, Lab contract, Lab target, liquidity tier (11 Nov)
    sess = datetime.strptime(session, "%Y-%m-%d").date()
    alt_cols = [c for c in H.columns if c.startswith("contract_alternative")]   # appear when the Lab publishes alternatives (Codex A8)
    for _, row in T.sort_values("_rank").iterrows():
        t, raw = row["ticker"], s(row.get("trade_contract"))
        h = by.get(t)
        m = OCC.search(raw.upper())
        symbol = ""
        if not m:
            if raw.lower() in ("", "none", "n/a") or raw.lower().startswith("none"):
                warns.append(f"{t}: no contract ({raw or 'blank'}; reason: {s(row.get('rank_reason'))[:90] or 'not given'})")
            else:
                fails.append(f"{t}: trade_contract '{raw}' is not an OCC symbol")
        else:
            und, yy, mm, dd, cp, strike = m.groups()
            symbol = und + yy + mm + dd + cp + strike
            if und != t:
                fails.append(f"{t}: contract underlying {und} is not the ticker")
            exp = date(2000 + int(yy), int(mm), int(dd))
            if exp <= sess:
                fails.append(f"{t}: contract expires {exp}, not after the session")
            side = s(row.get("side")).upper()
            if side in ("CALL", "PUT") and cp != side[0]:
                warns.append(f"{t}: contract is a {'call' if cp == 'C' else 'put'} but the row side is {side} (state the flip in the prompt)")

        bid, ask, oi = live_quote(row)
        if symbol:
            if ask is not None and ask > cap + 1e-9:
                warns.append(f"{t}: ask {ask:g} is over the premium cap {cap:g} (OVER_CAP: flagged, not dropped)")
            if bid is None and ask is None:
                warns.append(f"{t}: no live quote on the triage row (contract_bid / contract_ask / contract_oi): the 11 Nov liquidity tier is not shown")
            else:
                tier, why, _ = liquidity_tier(bid, ask, oi)
                if tier == "B":
                    warns.append(f"{t}: live liquidity tier B ({why}; quote {bid:g}/{ask:g}, OI {'not recorded' if oi is None else format(oi, 'g')}): tradeable with care")
                elif tier == "C":
                    warns.append(f"{t}: live liquidity tier C ({why}; quote {'no bid' if bid is None else format(bid, 'g')}/{ask:g}, "
                                 f"OI {'not recorded' if oi is None else format(oi, 'g')}): not tradeable at this quote; a Lab alternative, or no trade")

        if h is None:
            continue
        if lab:
            lab_contract = s(h.get("contract_symbol")).replace(" ", "")
            if symbol and symbol != lab_contract:
                named = [c for c in alt_cols if symbol in s(h.get(c)).replace(" ", "")]
                if named:
                    notes.append(f"{t}: trade_contract {symbol} is a named Lab alternative ({named[0]})")
                else:
                    warns.append(f"{t}: trade_contract {symbol} is not the Lab contract {lab_contract or '(the Lab selected none)'}"
                                 + ("" if alt_cols else " (the Lab does not publish contract alternatives yet, Codex A8)"))
            target = s(row.get("target")) or s(row.get("level"))
            if target and not same_number(target, h.get("anticipated_level")):
                warns.append(f"{t}: triage target {target} is not the Lab target (anticipated_level) {s(h.get('anticipated_level')) or 'not published'}")
            first = s(row.get("first_profit")) or s(row.get("half_target"))
            if first and not same_number(first, h.get("anticipated_level_q50")):
                warns.append(f"{t}: triage first profit {first} is not the Lab first profit (anticipated_level_q50) "
                             f"{s(h.get('anticipated_level_q50')) or 'not published'}")
        else:
            best = (s(h.get("best_contract_checked")) or s(h.get("best_contract"))).replace(" ", "")
            if symbol and best and symbol != best and not s(row.get("contract_why")):
                warns.append(f"{t}: contract {raw} differs from best_contract_checked {best} with no contract_why")

    # earnings
    if "earnings_date" in H.columns and "earnings_tastytrade" in T.columns:
        for t, e in zip(T["ticker"], T["earnings_tastytrade"]):
            d1 = re.search(r"\d{4}-\d{2}-\d{2}", s(e))
            d2 = re.search(r"\d{4}-\d{2}-\d{2}", s((by.get(t) or {}).get("earnings_date")))
            if d1 and d2 and abs((date.fromisoformat(d1.group()) - date.fromisoformat(d2.group())).days) > 1:
                warns.append(f"{t}: earnings Tastytrade {d1.group()} vs hand-off {d2.group()}: the deep dive confirms which")

    # prompts
    prm = prompts_file(tri.parent, session, b)
    if not prm.exists():
        fails.append(f"{tag}: {prm.name} is missing: the deep dives have no prompts (the triage must save it)")
    else:
        text = prm.read_text(encoding="utf-8-sig")
        lines = text.splitlines()
        heads = [(i, ln) for i, ln in enumerate(lines) if ln.lstrip().startswith("#")]
        for _, row in T.sort_values("_rank").iterrows():
            t, rk = row["ticker"], row["_rank"]
            hit = [i for i, ln in heads if re.search(rf"\b{re.escape(t)}\b", ln) and (pd.isna(rk) or re.search(rf"\b{int(rk)}\b", ln))]
            if not hit:
                fails.append(f"{tag} prompts: no section headed with rank {s(rk)} and {t}")
                continue
            start = hit[0]
            nxt = [i for i, _ in heads if i > start and re.match(r"\s*#{1,2}\s", lines[i])]
            body = "\n".join(lines[start:(nxt[0] if nxt else len(lines))])
            if session not in body:
                fails.append(f"{tag} prompts {t}: the session {session} is not in its section")
            if handoff_folder.name not in body and (lab_built or not lab):
                warns.append(f"{tag} prompts {t}: the hand-off folder {handoff_folder.name} is not named in its section")
            if PLACEHOLDER.search(body):
                fails.append(f"{tag} prompts {t}: unfilled placeholder '{PLACEHOLDER.search(body).group()}'")
            if "OUTPUT" not in body.upper():
                warns.append(f"{tag} prompts {t}: no OUTPUT block")
        notes.append(f"{tag}: prompts file {prm.name}: {len(text):,} characters, {len(heads)} headings")

    # strategy layer (old hand-off layout only: it reads <TICKER>_<SIDE>.json, which the Lab hand-off does not write)
    if not lab:
        sl = handoff_folder / f"strategy_layer_{session}.csv"
        if not sl.exists():
            warns.append(f"{sl.name} is missing: run avs_day.ps1 strategy before the deep dives (cards will have no S1-S6 row)")
        else:
            L = pd.read_csv(sl, dtype=str, keep_default_na=False)
            L["ticker"] = L["ticker"].str.upper().str.strip()
            sby = {t: r for t, r in zip(L["ticker"], L.to_dict("records"))}
            nos = [t for t in T["ticker"] if t not in sby]
            if nos:
                warns.append("no strategy-layer row for: " + ", ".join(nos))
            for t in T.sort_values("_rank")["ticker"]:
                r = sby.get(t)
                if r and r.get("challenge"):
                    for c in r["challenge"].split(" | "):
                        warns.append(f"{t} strategy [{r.get('strategy_tags')}]: {c}")
            conf = [t for t in T["ticker"] if sby.get(t, {}).get("confluence") == "CONFLUENCE"]
            notes.append(f"strategy confluence (2+ families): {', '.join(conf) or 'none'}")

    # packs
    if packs and packs.exists():
        nopack = [t for t in T["ticker"] if not (packs / f"{t}_pack.zip").exists()]
        if nopack:
            warns.append(f"{tag}: no pack for: " + " ".join(nopack) + f"  ->  avs_day.ps1 packs -Tickers {' '.join(nopack)}")
    else:
        warns.append(f"{tag}: packs folder not found: {packs}")

    notes.append(f"{tag}: {len(T)} names on the triage, {len(Hb)} hand-off batch-{b} names, premium cap {cap:g}")
    order = T.sort_values("_rank")
    notes.append(f"{tag} deep-dive order: " + ", ".join(f"{s(r)} {t}" for r, t in zip(order.get("deep_mine_rank", order["_rank"]), order["ticker"])))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", help="hand-off folder (default: handoff, else split_handoff, in today_context.json)")
    ap.add_argument("--triage-folder", help="folder holding the batch<N>_triage_<session>.csv files (default: the hand-off folder)")
    ap.add_argument("--session", help="session date (default: session in today_context.json)")
    ap.add_argument("--batch", type=int, action="append", help="batch number to check (repeat for several)")
    ap.add_argument("--all", action="store_true", help="check every batch triage file found (the default for a Lab hand-off)")
    ap.add_argument("--context", default=str(WORK / "today_context.json"))
    a = ap.parse_args(argv)
    ctx = {}
    cpath = Path(a.context)
    if cpath.exists():
        ctx = json.loads(cpath.read_text(encoding="utf-8-sig"))
    folder = Path(a.folder or ctx.get("handoff") or ctx.get("split_handoff") or ".")
    tfolder = Path(a.triage_folder) if a.triage_folder else folder
    session = a.session or ctx.get("session")
    cap = float(ctx.get("premium_cap") or 5)
    packs = Path(ctx["packs_folder"]) if ctx.get("packs_folder") else None
    fails, warns, notes = [], [], []

    hof = folder / "handoff.csv"
    if not hof.exists():
        fails.append(f"no handoff.csv in {folder}: run avs_day.ps1 evening first")
        return report(folder, session, fails, warns, notes)
    H = pd.read_csv(hof, dtype=str, keep_default_na=False)
    H["ticker"] = H["ticker"].str.upper().str.strip()
    lab = "lb_batch" in H.columns
    notes.append(f"hand-off {folder.name}: {'Lab publication' if lab else 'old split layout'}, {len(H)} names; triage files read from {tfolder}")

    found = {batch_number(f): f for f in sorted(tfolder.glob(f"batch*_triage_{session}.csv"))}
    if a.batch:
        wanted = a.batch
    elif a.all or lab:
        wanted = sorted(found) or [1]
    else:
        wanted = [1]
    for b in wanted:
        if b not in found:
            fails.append(f"batch{b}_triage_{session}.csv is missing in {tfolder}: the triage did not run or did not save")
            continue
        check_batch(found[b], H, lab, session, cap, packs, folder, fails, warns, notes)
    unchecked = sorted(set(found) - set(wanted))
    if unchecked:
        notes.append("batch triage files not checked in this run: " + ", ".join(f"batch {b}" for b in unchecked) + " (use --all or --batch N)")

    inbox = WORK / "lessons" / "fix_inbox" / f"{session}_triage.md"
    if not inbox.exists():
        warns.append(f"no fix-inbox file {inbox.name} (the triage writes one, 'none' if clean)")
    return report(folder, session, fails, warns, notes)


def report(folder: Path, session, fails, warns, notes) -> int:
    verdict = "FAIL" if fails else ("PASS WITH WARNINGS" if warns else "PASS")
    md = [f"# Triage check, session {session}: {verdict}", "", f"{VERSION}, {datetime.now():%Y-%m-%d %H:%M} local.", ""]
    if fails:
        md += ["## FAIL (advisory): fix the triage before the deep dives", ""] + [f"- {x}" for x in fails] + [""]
    if warns:
        md += ["## WARN: the deep dive must answer these", ""] + [f"- {x}" for x in warns] + [""]
    md += ["## Notes", ""] + [f"- {x}" for x in notes]
    if folder.exists():
        (folder / f"check_triage_{session}.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
