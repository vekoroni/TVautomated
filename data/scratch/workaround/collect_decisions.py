#!/usr/bin/env python3
"""Collect the day's card decisions into one list and one order-ticket sheet (v4, 12 Nov 2026; v2 16 Oct; 18 Oct: carries strategy_tags / strategy_primary).

v4 (12 Nov, Lane B Fix B10): a decision record for every card. The hand-off folder is scanned for *_deep_dive_*.html; a card
with no decisions\\<TICKER>.json gets one with state CARD_BUILT_DECISION_MISSING, the card path and any artifact link found in
the HTML (an existing decision file is never touched). "Decided, not placed" names (a TRADE / ENTER decision with no recorded
order) are reported. Works on a folder with no triage CSV. The spread rule on the ticket sheet is the 11 Nov liquidity tiers.
--dry-run lists what would be created and writes nothing. Read-only on every input except the decision stubs it creates.

v2 (16 Oct, approved by ACK): every ticket sheet opens with the execution rules from the week review (mid first, one lift
to the card line at 15:55 ET, the 11 Nov liquidity tiers (which replaced the 16 Oct spread gate), no orders 09:30-09:45 ET, resting exit within 5 minutes of a fill,
no trade without a card, take the believed card when its criteria are met); each ticket shows the card's limit, max pay,
close zone and one-contract exit when the decisions file has them; decisions files missing standard fields are listed
(warn only, never rejected).

Why (14 Oct fix inbox): card decisions sat in 14 separate decisions\\<TICKER>.json files with four different names for the
contract field; six top-ranked triage names had no card and no decision; resting legs and close entries never reached
the broker (BILI, EWG, IGV on 13-14 Oct) and nobody could see it before the close.

For every name on the split hand-off's triage list it writes one row:
    CARDED          a card exists and a decision is recorded (decisions\\<TICKER>.json, else the triage row)
    CARD_NO_DECISION a card HTML exists but no decision: write the decision before the close
    NOT_MINED       no card and no decision: record NOT_MINED with the reason, or run the deep dive
and an order-ticket sheet for every TRADE / WATCH card: the contract, the entry rule, the stop, the time stop and blank
boxes for "order placed / filled at / reason if not", to be filled before 21:00 UK (end-of-day recording, E1).

Run from the repo root (PowerShell), or let avs_day.ps1 preclose run it:
    venv\\Scripts\\python.exe data\\scratch\\workaround\\collect_decisions.py
    venv\\Scripts\\python.exe data\\scratch\\workaround\\collect_decisions.py --folder data\\scratch\\workaround\\handoff\\split_2026-10-14_cap5
    venv\\Scripts\\python.exe data\\scratch\\workaround\\collect_decisions.py --folder data\\scratch\\workaround\\handoff\\split_2026-11-12_cap5 --dry-run
Writes into the hand-off folder: cards_<session>.csv and order_tickets_<session>.md
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

VERSION = "collect_decisions_v4"
WORK = Path("data") / "scratch" / "workaround"
CONTRACT_KEYS = ("contract_taken", "contract", "planned_contract", "contract_planned")
STANDARD_FIELDS = ("ledger_id", "ticker", "handoff_side", "card_side", "decision", "decision_reason", "contract", "contract_alternative",
                   "entry_type", "close_zone_low", "close_zone_high", "extra_conditions", "limit", "max_pay", "size", "stop", "targets",
                   "time_stop", "one_contract_exit", "events_in_hold", "artifact_url", "artifact_file", "run_id", "created_utc", "checked",
                   "order_placed", "fill", "macro_dependency")
OPTIONAL_UNTIL_FILLED = ("order_placed", "fill", "contract_alternative")   # blank is normal until ACK records the order
EXECUTION_RULES = [
    "## Execution rules (approved 16 Oct; apply to every ticket)",
    "",
    "1. **Mid first, then the line.** Buy and sell with a limit at the mid. One lift to the card's line / max pay at 15:55 ET, never above it. "
    "Not filled at the line = NOT_FILLED (price), recorded as such. Sell at the mid too, unless a stop has fired.",
    "2. **Liquidity tiers (11 Nov).** A: spread within 10% of the mid, OI 100 or more, and under a 1.50 premium no more than 0.10 wide. "
    "B: 10-20% of the mid, with care. C: over 20%, no bid, or OI under 100: no order; a Lab alternative that passes, or no trade.",
    "3. **No option orders 09:30-09:45 ET** unless a stop fired at the previous close.",
    "4. **Resting exit within 5 minutes of a fill:** the card's one-contract target as a good-till sell; re-set it each Monday.",
    "5. **No trade without a card.** Anything else gets a one-line tactical card first (contract, max pay, target, stop, time stop).",
    "6. **Take the believed card when its criteria are met:** resting legs go to the broker when the card is made; close entries at 15:45 ET.",
    "",
]


OCC = re.compile(r"\b([A-Z]{1,6})\s*(\d{6}[CP]\d{8})\b")   # also the padded form "BILI  270115P00015000"


def s(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def first(j: dict, keys) -> str:
    """The OCC contract symbol from the contract fields, then from entry_type (WIX, REPX wrote it only in notes)."""
    for k in list(keys) + ["entry_type", "decision_reason"]:
        m = OCC.search(s(j.get(k)))
        if m:
            return m.group(1) + m.group(2)
    return ""


CARD_NAME = re.compile(r"^(?P<ticker>[A-Za-z][A-Za-z0-9.\-]*)_deep_dive_(?P<rest>.+)\.html$")
ARTIFACT_URL = re.compile(r"https://claude\.(?:ai|site)/(?:public/)?artifacts?/[A-Za-z0-9_\-]+")
SESSION_IN_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})")
DECIDED = ("TRADE", "ENTER")   # a decision to take the trade: TRADE, TRADE_NOW, TRADE_AT_CLOSE, ENTER ...


def find_cards(folder: Path) -> dict:
    """{TICKER: [card html paths, newest last]} for every *_deep_dive_*.html in the folder (Office lock files ~$ skipped)."""
    out: dict[str, list[Path]] = {}
    def card_date(p: Path):   # the date in the file name decides which card is the newest; the file time only breaks a tie
        d = SESSION_IN_NAME.search(p.name)
        return (d.group(1) if d else "", p.stat().st_mtime, p.name)
    for f in sorted(folder.glob("*_deep_dive_*.html"), key=card_date):
        m = CARD_NAME.match(f.name)
        if not m or f.name.startswith("~$"):
            continue
        out.setdefault(m.group("ticker").upper(), []).append(f)
    return out


def ensure_decision_records(folder: Path, cards: dict, session: str, ledger_ids: dict, dry_run: bool) -> list[dict]:
    """A decisions\\<TICKER>.json for every card. An existing file is never touched. Returns one line per card."""
    out = []
    for t, files in sorted(cards.items()):
        target = folder / "decisions" / f"{t}.json"
        newest = files[-1]
        if target.exists():
            out.append({"ticker": t, "card": newest.name, "record": "decision record present", "created": False})
            continue
        html = newest.read_text(encoding="utf-8", errors="ignore")
        url = ARTIFACT_URL.search(html)
        stub = {"ticker": t, "ledger_id": ledger_ids.get(t, ""), "state": "CARD_BUILT_DECISION_MISSING", "decision": "",
                "decision_reason": "", "card_path": str(newest), "card_files": [f.name for f in files],
                "artifact_url": url.group(0) if url else "", "artifact_file": str(newest), "session": session,
                "order_placed": "", "fill": None, "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "created_by": f"{VERSION}: a card was found with no decision record. Write the decision (TRADE / WATCH / PASS) and the reason here."}
        if not dry_run:
            target.parent.mkdir(exist_ok=True)
            target.write_text(json.dumps(stub, indent=1), encoding="utf-8")
        out.append({"ticker": t, "card": newest.name, "created": not dry_run,
                    "record": ("would create" if dry_run else "created") + " decisions\\" + target.name + " with state CARD_BUILT_DECISION_MISSING"
                              + (f", artifact {stub['artifact_url']}" if stub["artifact_url"] else ", no artifact link in the HTML")})
    return out


def decided(c: dict) -> bool:
    return any(str(c.get(k) or "").upper().startswith(DECIDED) for k in ("decision", "final_action"))


def placed(c: dict) -> bool:
    return str(c.get("order_placed") or "").strip().lower() not in ("", "no", "false", "none", "null", "n")


def load_cards(folder: Path) -> dict:
    out = {}
    for f in sorted((folder / "decisions").glob("*.json")) if (folder / "decisions").exists() else []:
        try:
            j = json.loads(f.read_text(encoding="utf-8-sig"))
        except Exception as e:
            out[f.stem.upper()] = {"decision": "", "note": f"unreadable decisions file: {type(e).__name__}"}
            continue
        out[str(j.get("ticker", f.stem)).upper()] = {
            "decision": str(j.get("decision") or "").upper(),
            "final_action": str(j.get("final_action") or "").upper(),
            "state": str(j.get("state") or ""),
            "card_side": j.get("card_side") or "",
            "contract": first(j, CONTRACT_KEYS),
            "contract_alternative": j.get("contract_alternative") or "",
            "entry_type": j.get("entry_type") or "",
            "size": j.get("size") or "",
            "stop": j.get("stop") or "",
            "time_stop": j.get("time_stop") or "",
            "artifact_url": j.get("artifact_url") or "",
            "order_placed": "" if j.get("order_placed") is None else str(j.get("order_placed")),
            "decision_source": f"decisions\\{f.name}",
            "decision_reason": j.get("decision_reason") or "",
            "limit": "" if j.get("limit") is None else str(j.get("limit")),
            "max_pay": "" if j.get("max_pay") is None else str(j.get("max_pay")),
            "close_zone": (f"{j.get('close_zone_low')}-{j.get('close_zone_high')}"
                           if j.get("close_zone_low") is not None and j.get("close_zone_high") is not None else ""),
            "window_end": j.get("window_end") or "",
            "macro_dependency": json.dumps(j["macro_dependency"]) if isinstance(j.get("macro_dependency"), (dict, list)) else s(j.get("macro_dependency")),
            "one_contract_exit": json.dumps(j["one_contract_exit"]) if isinstance(j.get("one_contract_exit"), dict) else s(j.get("one_contract_exit")),
            "strategy_tags": s(j.get("strategy_tags")),          # 18 Oct: S1-S6 strategy layer, so outcomes can be scored by strategy
            "strategy_primary": s(j.get("strategy_primary")),
            "schema_missing": ", ".join(k for k in STANDARD_FIELDS if k not in OPTIONAL_UNTIL_FILLED and j.get(k) in (None, "", [], {})
                                        and not (k == "contract" and first(j, CONTRACT_KEYS))),
        }
    return out


def macro_line() -> str:
    """One line from macro_state.json (written by the triage, 16 Oct v3): the macro read every ticket depends on."""
    f = WORK / "macro_state.json"
    if not f.exists():
        return "**Macro state: MISSING** (macro_state.json not written by the triage): treat every money tag as provisional."
    try:
        m = json.loads(f.read_text(encoding="utf-8-sig"))
    except Exception as e:
        return f"**Macro state: UNREADABLE** ({type(e).__name__})"
    fired = [k.get("id") for k in m.get("kill_switches", []) if isinstance(k, dict) and k.get("fired")]
    return (f"**Macro state:** thesis {m.get('thesis_date')} ({'fresh' if m.get('thesis_fresh') else 'STALE'}), "
            f"board vs Money Index {m.get('agreement_overall')}, regime: {m.get('regime')}. "
            f"Kill switches fired at the triage: {', '.join(map(str, fired)) or 'none'}. The monitors re-check them live.")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", help="hand-off folder (default: handoff, else split_handoff, in today_context.json)")
    ap.add_argument("--dry-run", action="store_true", help="list the cards and the decision records that would be created; write nothing")
    a = ap.parse_args(argv)
    if a.folder:
        folder = Path(a.folder)
    else:
        ctx = json.loads((WORK / "today_context.json").read_text(encoding="utf-8-sig"))
        folder = Path(ctx.get("handoff") or ctx["split_handoff"])
    triage_files = sorted(folder.glob("batch*_triage_*.csv"))
    # keep_default_na=False: the ticker NAN is a real ticker; blank stays blank
    T = (pd.concat([pd.read_csv(f, dtype=str, keep_default_na=False).assign(triage_file=f.name) for f in triage_files], ignore_index=True)
         if triage_files else pd.DataFrame(columns=["ticker", "ledger_id", "side", "deep_mine_rank", "triage_file"]))
    in_name = SESSION_IN_NAME.search(folder.name)
    session = (str(T["ledger_id"].iloc[0])[:10] if len(T) and "ledger_id" in T and str(T["ledger_id"].iloc[0])[:10].count("-") == 2
               else (in_name.group(1) if in_name else datetime.now().strftime("%Y-%m-%d")))
    T["ticker"] = T["ticker"].astype(str).str.upper().str.strip()

    # B10: a decision record for every card (before the decisions are read, so a new record is counted)
    html_cards = find_cards(folder)
    ledger_ids = dict(zip(T["ticker"], T["ledger_id"])) if "ledger_id" in T else {}
    card_lines = ensure_decision_records(folder, html_cards, session, ledger_ids, a.dry_run)
    print(f"{VERSION}: {len(html_cards)} card(s) in {folder}" + (" (dry run: nothing written)" if a.dry_run else ""))
    for c in card_lines:
        print(f"  {c['ticker']}: card {c['card']} -> {c['record']}")
    cards = load_cards(folder)
    not_placed = sorted(t for t, c in cards.items() if decided(c) and not placed(c))
    print("Decided, not placed (a TRADE / ENTER decision with no recorded order): " + (", ".join(not_placed) or "none"))
    if a.dry_run:
        return
    prompts = folder / f"deep_dive_prompts_{session}.md"

    rows = []
    for _, r in T.iterrows():
        t = str(r["ticker"]).upper()
        has_card = t in html_cards
        c = dict(cards.get(t, {}))
        if not c.get("decision") and str(r.get("decision") or "").strip():
            c.update({"decision": str(r["decision"]).upper(), "contract": first({"c": s(r.get("contract_taken"))}, ["c"]) or s(r.get("contract_taken")),
                      "entry_type": s(r.get("entry_type")), "decision_source": f"triage {r['triage_file']}",
                      "decision_reason": s(r.get("decision_reason"))})
        status = "CARDED" if c.get("decision") else ("CARD_NO_DECISION" if has_card else "NOT_MINED")
        rows.append({"deep_mine_rank": r.get("deep_mine_rank"), "ticker": t, "ledger_id": r.get("ledger_id"),
                     "handoff_side": r.get("side"), "status": status, "has_card_html": has_card, **c})
    for t in sorted((set(html_cards) | set(cards)) - set(T["ticker"])):   # carded or decided, but not on a triage file in this folder
        c = dict(cards.get(t, {}))
        status = "CARDED" if c.get("decision") else ("CARD_NO_DECISION" if t in html_cards else "NOT_MINED")
        rows.append({"deep_mine_rank": "", "ticker": t, "ledger_id": "", "handoff_side": "", "status": status,
                     "has_card_html": t in html_cards, **c})
    D = pd.DataFrame(rows)
    if "ticker" not in D:
        D = pd.DataFrame(columns=["deep_mine_rank", "ticker", "ledger_id", "handoff_side", "status", "has_card_html"])
    for col in ["final_action", "state", "card_side", "decision", "contract", "entry_type", "size", "stop", "time_stop", "artifact_url", "order_placed",
                "decision_source", "decision_reason", "contract_alternative", "limit", "max_pay", "close_zone", "window_end", "macro_dependency",
                "one_contract_exit", "schema_missing"]:
        if col not in D:
            D[col] = ""
    D = D.fillna("")
    out_csv = folder / f"cards_{session}.csv"
    D.to_csv(out_csv, index=False)

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    n = D["status"].value_counts().to_dict()
    md = [f"# Cards and order tickets, session {session}", "",
          f"{VERSION}, written {now} local. {len(D)} names (triaged or carded): CARDED {n.get('CARDED', 0)}, CARD_NO_DECISION {n.get('CARD_NO_DECISION', 0)}, "
          f"NOT_MINED {n.get('NOT_MINED', 0)}. Deep-dive prompts file: {'present' if prompts.exists() else 'MISSING (B3 did not save it)'}.", "",
          "Fill the boxes before 21:00 UK and copy the result into the decision ledger (E1). A decision without a recorded order "
          "outcome is scored as MISSED, never as TRADE.", "", macro_line(), ""] + EXECUTION_RULES
    live = D[D["decision"].isin(["TRADE", "ENTER", "WATCH"])]
    md += [f"## Order tickets ({len(live)})", ""]
    for _, r in live.iterrows():
        side = r["card_side"] or r["handoff_side"]
        md += [f"### {r['ticker']} {side} - {r['decision']}" + (f" ([card]({r['artifact_url']}))" if r["artifact_url"] else ""),
               f"- Contract: `{r['contract'] or 'NOT STATED ON THE CARD'}`" + (f" (alternative {r['contract_alternative']})" if r["contract_alternative"] else ""),
               f"- Entry: {r['entry_type'] or 'NOT STATED'}",
               f"- Limit: {r['limit'] or 'mid (see card)'} | Max pay / line: {r['max_pay'] or 'see card'}"
               + (f" | Close zone: {r['close_zone']}" if r["close_zone"] else "") + (f" | Window to: {r['window_end']}" if r["window_end"] else ""),
               f"- Size: {r['size'] or 'see card'} | Stop: {r['stop'] or 'see card'} | Time stop: {r['time_stop'] or 'see card'}",
               f"- One-contract exit (resting good-till sell within 5 minutes of the fill): {r['one_contract_exit'] or 'see card'}",
               f"- Macro dependency: {r['macro_dependency'] or 'NOT RECORDED (infer from the card; check macro_state.json)'} - no order if the monitor flags MACRO BROKEN",
               "- [ ] order placed (time, limit, good-till) ________   - [ ] filled at ______   - reason if not placed / not filled: ________",
               ""]
    for st, title in [("CARD_NO_DECISION", "Cards with no decision (write TRADE / WATCH / PASS before the close)"),
                      ("NOT_MINED", "Triaged but not mined (record NOT_MINED + reason, or run the deep dive)")]:
        g = D[D["status"] == st]
        if len(g):
            md += [f"## {title} ({len(g)})", "", ", ".join(f"{a} (rank {b})" for a, b in zip(g["ticker"], g["deep_mine_rank"])), ""]
    md += [f"## Decided, not placed ({len(not_placed)})", "",
           "A TRADE / ENTER decision with no recorded order. Record order_placed and the fill (or the reason it was not placed) in "
           "decisions\\<TICKER>.json.", ""]
    md += [f"- {t}: decision {cards[t].get('decision') or '-'}" + (f", final action {cards[t]['final_action']}" if cards[t].get("final_action") else "")
           + f", contract `{cards[t].get('contract') or 'not stated'}`" + (f", [card]({cards[t]['artifact_url']})" if cards[t].get("artifact_url") else "")
           for t in not_placed] + ([""] if not_placed else ["none", ""])
    made = [c for c in card_lines if c["created"]]
    if made:
        md += [f"## Decision records created for cards that had none ({len(made)})", ""] + [f"- {c['ticker']}: {c['card']}" for c in made] + [""]
    warn = D[(D["decision"] != "") & (D["schema_missing"] != "")]
    if len(warn):
        md += [f"## Decisions files missing standard fields ({len(warn)}; warning only)", ""]
        md += [f"- {t}: {m}" for t, m in zip(warn["ticker"], warn["schema_missing"])] + [""]
    (folder / f"order_tickets_{session}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"{VERSION}: {n} -> {out_csv.name}, order_tickets_{session}.md in {folder}")
    if len(warn):
        print(f"WARNING: {len(warn)} decisions file(s) miss standard fields (listed at the end of order_tickets_{session}.md)")
    if not prompts.exists():
        print(f"WARNING: {prompts.name} is missing: the triage (B3) must save the deep-dive prompts")


if __name__ == "__main__":
    main()
