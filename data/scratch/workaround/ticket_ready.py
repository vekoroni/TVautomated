#!/usr/bin/env python3
"""Ticket-ready list: every live card, with its exact entry and exit order strings (v1, 21 Nov 2026).

AVS-ENH-2026-11-21 Wave 0 (ACK go-ahead 21 Nov 2026). Advisory only: this writes a list. It places nothing, reads no
broker and calls no provider. ACK places every order and checks each ticket's criteria at 15:40 ET.

Why (20 Nov fix inbox, verified 21 Nov): order tickets came from one hand-off folder and only when avs_day.ps1 preclose
or eod was run, which produced nothing on 16 to 20 Nov; on 19 Nov four criteria-met cards had no order. The resting-exit,
quantity and macro rules were sentences on the ticket sheet with nothing checking them.

What it does:
  F-01  reads decisions\\<TICKER>.json in every hand-off folder, so a card from an earlier session that is still live is listed
  F-02  each ticket carries its exit order beside its entry order
  F-03  a filled card with no resting exit recorded is flagged FILLED_NO_RESTING_EXIT and listed first
  F-04  the order carries the card's size; a fill of a different quantity is flagged unless the card has a scaling_note
  F-05  macro_kill on the first line: FIRED / REVIEW / CLEAR / NOT_ASSESSED (a card with no kill switch is never CLEAR)
  F-09  a macro state from an earlier session is labelled with its date and never treated as today's
  F-10  today_context.json is refreshed from what is on disk
  one ticket per branch on the card (both sides): the branch's own contract, max pay, trigger, stop and exit step

Run from the repo root (PowerShell):
    venv\\Scripts\\python.exe data\\scratch\\workaround\\ticket_ready.py
    venv\\Scripts\\python.exe data\\scratch\\workaround\\ticket_ready.py --today 2026-11-20 --out-folder %TEMP%\\ticket_replay
Writes into the day's hand-off folder: ticket_ready_<session>.md, ticket_ready_<session>.csv, board_rows_<session>.json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import date, datetime
from pathlib import Path

VERSION = "ticket_ready_v1"
WORK = Path("data") / "scratch" / "workaround"
OCC = re.compile(r"\b([A-Z]{1,6})\s*(\d{6}[CP]\d{8})\b")
ISO_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
FOLDER_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
LIVE_DECISIONS = ("TRADE", "ENTER", "WATCH")
CLOSED_ACTIONS = ("PASS", "CLOSED", "EXITED", "SOLD", "CANCELLED", "CANCELED", "EXPIRED", "NO_TRADE", "STAND_ASIDE")
WORKING_EXIT_STATES = ("WORKING", "RESTING", "OPEN", "RECEIVED", "LIVE")
CONTRACT_KEYS = ("contract_taken", "contract", "planned_contract", "contract_planned")
ORDER = {"FILLED_NO_RESTING_EXIT": 0, "MACRO": 1, "FILLED": 2, "WAITING": 3, "PAST_TIME_STOP": 4, "OLD_CARD_NO_TIME_STOP": 5,
         "UNREADABLE": 6}
OLD_CARD_DAYS = 30   # an unfilled card with no dated time stop, from a hand-off older than this, is listed apart (never dropped)


def parse_size(value) -> int | None:
    """The card's size as a whole number of contracts: 1, "1 contract", "1 contract (test month); ..." -> 1."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if value == int(value) and value > 0 else None
    found = re.match(r"\s*(\d+)\b", str(value))
    return int(found.group(1)) if found and int(found.group(1)) > 0 else None


def _number(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _price(value, missing: str) -> str:
    """A number is shown to two decimals; words written on the card stay words and are never turned into a number."""
    number = _number(value)
    if number is not None:
        return f"{number:.2f}"
    text = "" if value is None else str(value).strip()
    return text if text else missing


def _contract(card: dict) -> str:
    for key in CONTRACT_KEYS:
        found = OCC.search(str(card.get(key) or ""))
        if found:
            return found.group(1) + found.group(2)
    return ""


def _first_date(*values) -> date | None:
    for value in values:
        found = ISO_DATE.search(str(value or ""))
        if found:
            try:
                return date.fromisoformat(found.group(1))
            except ValueError:
                continue
    return None


CODE = re.compile(r"\d{6}[CP]\d{8}")


def _real_fill(card: dict) -> dict | None:
    """A fill counts only when it records a price or a quantity. Cards carry an all-null placeholder until ACK fills it in."""
    raw = card.get("fill") if isinstance(card.get("fill"), dict) else {}
    return raw if (_number(raw.get("price")) is not None or _number(raw.get("quantity")) is not None) else None


def _gtc_price(gtc, today: date):
    """The resting-exit price in force today from a branch's gtc: a number, words, or dated steps [[date | "entry", price], ..]."""
    if isinstance(gtc, (int, float)) and not isinstance(gtc, bool):
        return float(gtc)
    if isinstance(gtc, str) and gtc.strip():
        return _number(gtc) if _number(gtc) is not None else gtc.strip()
    if not isinstance(gtc, list):
        return None
    in_force = first = None
    dated = []
    for step in gtc:
        if not isinstance(step, (list, tuple)) or len(step) < 2:
            continue
        if first is None:
            first = step[1]
        when = _first_date(step[0])
        if when is None:
            in_force = step[1] if in_force is None else in_force      # "entry": the price from the fill until a dated step
        else:
            dated.append((when, step[1]))
    for when, price in sorted(dated, key=lambda item: item[0]):
        if when <= today:
            in_force = price
    return in_force if in_force is not None else first


def _legs(card: dict, today: date) -> list[dict]:
    """One leg per branch written on the card (ACK 21 Nov 2026); a card with no branches is one leg.

    Each leg is the card with the branch's own contract, max pay, trigger, stop and exit. A recorded fill belongs to the
    leg whose contract is named in order_placed; when no leg is named it goes to the primary and is flagged.
    """
    branches = [b for b in (card.get("branches") or []) if isinstance(b, dict)]
    if not branches:
        return [dict(card, _leg="PRIMARY", _alternatives=[], _extra_flags=[])]
    ticker = str(card.get("ticker") or "").upper()
    primary = _contract(card)
    legs = []
    for branch in branches:
        codes = CODE.findall(str(branch.get("contract") or ""))
        contract = ticker + codes[0] if codes else ""
        max_pay = branch.get("max_pay")
        if isinstance(max_pay, str) and "/" in max_pay and len(codes) > 1:
            parts = [part.strip() for part in max_pay.split("/")]
            if len(parts) == len(codes):                             # "6.15 / 4.95" beside "A / B": paired as written
                max_pay = parts[0]
        is_primary = bool(contract) and contract == primary
        exit_price = _gtc_price(branch.get("gtc"), today)
        if exit_price is not None:
            exit_plan = {"target_option_price": exit_price}
        else:
            exit_plan = card.get("one_contract_exit") if is_primary and isinstance(card.get("one_contract_exit"), dict) else {}
        leg = dict(card)
        leg.update({
            "contract": contract, "contract_taken": None, "planned_contract": None, "contract_planned": None,
            "card_side": str(branch.get("side") or card.get("card_side") or ""),
            "max_pay": max_pay,
            "limit": branch.get("limit") if branch.get("limit") is not None else (card.get("limit") if is_primary else None),
            "entry_type": branch.get("trigger") or card.get("entry_type"),
            "stop": branch.get("stop") if branch.get("stop") is not None else card.get("stop"),
            "time_stop": branch.get("time_stop") if branch.get("time_stop") is not None else card.get("time_stop"),
            "one_contract_exit": exit_plan, "fill": None,
            "_leg": "PRIMARY" if is_primary else "BRANCH",
            "_alternatives": [ticker + code for code in codes[1:]],
            "_extra_flags": ["MORE_THAN_ONE_CONTRACT_ON_BRANCH"] if len(codes) > 1 else [],
        })
        legs.append(leg)
    fill = _real_fill(card)
    if fill:
        placed = set(CODE.findall(str(card.get("order_placed") or "")))
        named = [leg for leg in legs if leg["contract"] and leg["contract"][len(ticker):] in placed]
        if named:
            for leg in named:
                leg["fill"] = fill
        else:
            target = next((leg for leg in legs if leg["_leg"] == "PRIMARY"), legs[0])
            target["fill"] = fill
            target["_extra_flags"] = target["_extra_flags"] + ["FILL_LEG_NOT_STATED"]
    return legs


def macro_state_age(macro_state: dict | None, today: date) -> tuple[str, str]:
    """(CURRENT | STALE | MISSING, plain reason). A state from an earlier session is never today's (F-09)."""
    if not isinstance(macro_state, dict):
        return "MISSING", "macro_state.json is missing or unreadable"
    session = str(macro_state.get("session") or "")
    if session == today.isoformat():
        return "CURRENT", f"macro state is from session {session}"
    return "STALE", f"macro state is from session {session or 'unknown'}, not {today.isoformat()}"


def _macro_kill(card: dict, macro_state: dict | None, today: date) -> tuple[str, str]:
    written = card.get("macro_kill")
    if isinstance(written, str) and written.strip():            # the monitor wrote it during the session: shown as written
        return written.split(":")[0].strip().upper() or "REVIEW", written.strip()
    dependency = card.get("macro_dependency")
    kill = str(dependency.get("kill_switch") or "").strip() if isinstance(dependency, dict) else ""
    if not kill:
        return "NOT_ASSESSED", "no kill switch on the card (macro_dependency.kill_switch)"
    age, why = macro_state_age(macro_state, today)
    switches = [k for k in (macro_state or {}).get("kill_switches", []) if isinstance(k, dict) and k.get("id")]
    fired = [str(k["id"]) for k in switches if k.get("fired")]
    if age != "CURRENT":
        return "NOT_ASSESSED", why + (f"; switches fired then: {', '.join(fired)}" if fired else "") + f". Card: {kill[:120]}"
    text = kill.upper()
    named_fired = [i for i in fired if i.upper() in text]
    if named_fired:
        return "FIRED", f"{', '.join(named_fired)} fired at the triage. Card: {kill[:120]}"
    if any(str(k["id"]).upper() in text for k in switches):
        return "CLEAR", f"the card's switch has not fired at the triage. Card: {kill[:120]}"
    if fired:
        return "REVIEW", f"the card's switch is not one of the triage's ids; fired at the triage: {', '.join(fired)}. Card: {kill[:120]}"
    return "CLEAR", f"no kill switch fired at the triage. Card: {kill[:120]}"


def _ticket(card: dict, folder: Path, macro_state: dict | None, today: date) -> dict:
    ticker = str(card.get("ticker") or "").upper()
    contract = _contract(card)
    size = parse_size(card.get("size"))
    fill = _real_fill(card)
    exit_plan = card.get("one_contract_exit") if isinstance(card.get("one_contract_exit"), dict) else {}
    flags: list[str] = list(card.get("_extra_flags") or [])
    if size is None:
        flags.append("SIZE_NOT_ON_CARD")
    if not contract:
        flags.append("CONTRACT_NOT_ON_CARD")
    quantity = f"{size}" if size is not None else "?"
    symbol = contract or "CONTRACT-NOT-ON-CARD"
    max_pay = _price(card.get("max_pay"), "")
    entry_order = (f"BUY TO OPEN {quantity} {symbol} LIMIT {_price(card.get('limit'), 'live mid')} DAY "
                   + (f"(never above {max_pay})" if max_pay else "(max pay not on the card)"))
    target = exit_plan.get("target_option_price")
    if _number(target) is not None:
        exit_order = f"SELL TO CLOSE {quantity} {symbol} LIMIT {_number(target):.2f} GTC"
    elif str(target or "").strip():
        exit_order = f"SELL TO CLOSE {quantity} {symbol} GTC at the card's price: {str(target).strip()[:140]}"
    else:
        exit_order = "EXIT PRICE NOT ON THE CARD (one_contract_exit.target_option_price)"
        flags.append("EXIT_NOT_ON_CARD")

    if fill:
        state = "FILLED"
        resting = card.get("resting_exit") if isinstance(card.get("resting_exit"), dict) else None
        if not resting or str(resting.get("state") or "").upper() not in WORKING_EXIT_STATES:
            flags.append("FILLED_NO_RESTING_EXIT")
        filled_quantity = _number(fill.get("quantity"))
        if size is not None and filled_quantity is not None and int(filled_quantity) != size and not str(card.get("scaling_note") or "").strip():
            flags.append("QUANTITY_DIFFERS_FROM_CARD")
    else:
        last_day = _first_date(card.get("time_stop"), card.get("window_end"))
        folder_day = _first_date(folder.name)
        if last_day and last_day < today:
            state = "PAST_TIME_STOP"
        elif last_day is None and folder_day and (today - folder_day).days > OLD_CARD_DAYS:
            state = "OLD_CARD_NO_TIME_STOP"
        else:
            state = "WAITING"

    macro_kill, macro_reason = _macro_kill(card, macro_state, today)
    if macro_kill == "FIRED":
        flags.append("MACRO_KILL_FIRED")
    zone = (f"{card.get('close_zone_low')}-{card.get('close_zone_high')}"
            if card.get("close_zone_low") is not None and card.get("close_zone_high") is not None else "")
    return {
        "ticker": ticker, "side": str(card.get("card_side") or card.get("handoff_side") or ""),
        "decision": str(card.get("decision") or "").upper(), "final_action": str(card.get("final_action") or "").upper(),
        "state": state, "flags": flags, "contract": contract, "size": size,
        "leg": str(card.get("_leg") or "PRIMARY"), "alternatives": ", ".join(card.get("_alternatives") or []),
        "entry_order": entry_order, "exit_order": exit_order,
        "criteria": str(card.get("entry_type") or "NOT STATED ON THE CARD"), "close_zone": zone,
        "stop": "" if card.get("stop") is None else str(card.get("stop")),
        "time_stop": "" if card.get("time_stop") is None else str(card.get("time_stop")),
        "macro_kill": macro_kill, "macro_kill_reason": macro_reason,
        "fill": json.dumps(fill) if fill else "", "order_placed": str(card.get("order_placed") or ""),
        "resting_exit": json.dumps(card.get("resting_exit")) if isinstance(card.get("resting_exit"), dict) else "",
        "source_folder": folder.name, "decision_file": str(folder / "decisions" / f"{ticker}.json"),
        "artifact_url": str(card.get("artifact_url") or ""),
    }


def _handoff_folders(handoff_root: Path) -> list[Path]:
    """Hand-off folders that hold decisions, oldest first by the date in the name (so the newest card wins)."""
    folders = [f for f in Path(handoff_root).iterdir() if f.is_dir() and (f / "decisions").is_dir()] if Path(handoff_root).is_dir() else []
    return sorted(folders, key=lambda f: ((FOLDER_DATE.search(f.name) or [None, ""])[1] if FOLDER_DATE.search(f.name) else "", f.name))


def build_tickets(handoff_root: Path, today: date, macro_state: dict | None) -> list[dict]:
    """One ticket per live card across every hand-off folder; what needs action is first."""
    newest: dict[str, tuple[dict, Path]] = {}
    unreadable: list[dict] = []
    for folder in _handoff_folders(handoff_root):
        for path in sorted((folder / "decisions").glob("*.json")):
            if "board_row" in path.name:                       # a stray board-row file saved beside the decisions
                continue
            try:
                card = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as error:
                unreadable.append({"ticker": path.stem.upper(), "state": "UNREADABLE", "flags": ["DECISION_FILE_UNREADABLE"],
                                   "source_folder": folder.name, "decision_file": str(path),
                                   "macro_kill": "NOT_ASSESSED", "macro_kill_reason": f"decision file unreadable: {type(error).__name__}"})
                continue
            if isinstance(card, dict):
                newest[str(card.get("ticker") or path.stem).upper()] = (card, folder)
    tickets = []
    for card, folder in newest.values():
        decision = str(card.get("decision") or "").upper()
        if not decision.startswith(LIVE_DECISIONS) or str(card.get("final_action") or "").upper().startswith(CLOSED_ACTIONS):
            continue
        for leg in _legs(card, today):
            tickets.append(_ticket(leg, folder, macro_state, today))

    def rank(ticket: dict):
        if "FILLED_NO_RESTING_EXIT" in ticket["flags"]:
            first = ORDER["FILLED_NO_RESTING_EXIT"]
        elif ticket["macro_kill"] in ("FIRED", "REVIEW"):
            first = ORDER["MACRO"]
        else:
            first = ORDER.get(ticket["state"], 9)
        return first, ticket["ticker"], ticket.get("leg") != "PRIMARY", ticket.get("side", "")

    return sorted(tickets, key=rank) + sorted(unreadable, key=lambda t: t["ticker"])


def write_list(tickets: list[dict], folder: Path, session: str, macro_state: dict | None, today: date) -> tuple[Path, Path]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    age, why = macro_state_age(macro_state, today)
    counts: dict[str, int] = {}
    for ticket in tickets:
        counts[ticket["state"]] = counts.get(ticket["state"], 0) + 1
    action = [t for t in tickets if t["flags"] and t["state"] != "UNREADABLE"]
    md = [f"# Ticket ready list, session {session}", "",
          f"{VERSION}, written {datetime.now().strftime('%Y-%m-%d %H:%M')} local. **Advisory.** ACK places every order. "
          "Check each ticket's criteria at 15:40 ET; a ticket here is live, not yet criteria-met.", "",
          f"**Macro state: {age}** ({why})." + ("" if age == "CURRENT" else " Every macro kill below is NOT_ASSESSED until the triage rewrites it."), "",
          f"{len(tickets)} live card(s): " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) + f". Needing action: {len(action)}.", ""]
    if action:
        md += ["## Needs action first", ""] + [f"- **{t['ticker']}**: {', '.join(t['flags'])}" for t in action] + [""]
    past = [t for t in tickets if t["state"] in ("PAST_TIME_STOP", "OLD_CARD_NO_TIME_STOP")]
    md += ["## Tickets", ""]
    for t in [t for t in tickets if t not in past]:
        if t["state"] == "UNREADABLE":
            md += [f"### {t['ticker']} - decision file unreadable ({t['source_folder']})", f"- {t['macro_kill_reason']}", ""]
            continue
        md += [f"### {t['ticker']} {t['side']} ({'primary' if t.get('leg') == 'PRIMARY' else 'branch'}) - {t['state']}" + (f" - {', '.join(t['flags'])}" if t["flags"] else "")
               + (f" ([card]({t['artifact_url']}))" if t["artifact_url"] else ""),
               f"- **Macro kill: {t['macro_kill']}** - {t['macro_kill_reason']}",
               f"- Entry: `{t['entry_order']}`" + (f" (also on the card: {t['alternatives']})" if t.get("alternatives") else ""),
               f"- Exit, placed with the entry or within 5 minutes of the fill: `{t['exit_order']}`",
               f"- Criteria: {t['criteria']}" + (f" | Close zone: {t['close_zone']}" if t["close_zone"] else ""),
               f"- Stop: {t['stop'] or 'see card'} | Time stop: {t['time_stop'] or 'see card'} | Card from: {t['source_folder']}"]
        if t["state"] == "FILLED":
            md += [f"- Fill recorded: {t['fill']} | Resting exit recorded: {t['resting_exit'] or 'NONE'}"]
        md += ["- [ ] order placed (time, limit) ________   - [ ] resting exit placed (price, order id) ________   - reason if not placed: ________", ""]
    if past:
        md += [f"## Past their time stop, not filled ({len(past)}): not tickets; close the card or re-date it", "",
               ", ".join(f"{t['ticker']} ({t['time_stop'][:10] or 'no dated time stop'}, {t['source_folder']})" for t in past), ""]
    md_path = folder / f"ticket_ready_{session}.md"
    md_path.write_text("\n".join(md), encoding="utf-8")
    csv_path = folder / f"ticket_ready_{session}.csv"
    columns = ["ticker", "side", "leg", "state", "flags", "macro_kill", "macro_kill_reason", "contract", "alternatives", "size", "entry_order", "exit_order",
               "criteria", "close_zone", "stop", "time_stop", "decision", "final_action", "order_placed", "fill", "resting_exit",
               "source_folder", "decision_file", "artifact_url"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for t in tickets:
            writer.writerow({**{c: "" for c in columns}, **t, "flags": ";".join(t.get("flags", []))})
    return md_path, csv_path


def refresh_context(context_path: Path, base: Path | None = None) -> list[str] | None:
    """Refresh today_context.json from what is on disk (F-10). Returns the keys that changed, or None when there is no context.

    Only the keys named here are touched; everything else avs_day.ps1 wrote is kept. A file that is absent stays null.
    """
    context_path = Path(context_path)
    if not context_path.is_file():
        return None
    context = json.loads(context_path.read_text(encoding="utf-8-sig"))
    handoff = context.get("handoff") or context.get("split_handoff")
    session = context.get("session")
    if not handoff or not session:
        return []
    folder = Path(handoff) if Path(handoff).is_absolute() or base is None else Path(base) / handoff

    def path_or_none(name: str):
        return str(Path(handoff) / name) if (folder / name).is_file() else None

    prompts = path_or_none(f"deep_dive_prompts_{session}.md") or path_or_none(f"deep_dive_prompts_{session}_b1.md")
    check = folder / f"check_triage_{session}.md"
    verdict = None
    if check.is_file():
        first_line = (check.read_text(encoding="utf-8-sig").splitlines() or [""])[0]
        verdict = first_line.split(": ")[-1].strip() or None
    fresh = {
        "split_triage_files": sorted(p.name for p in folder.glob("batch*_triage_*.csv")) if folder.is_dir() else [],
        "deep_dive_prompts": prompts,
        "cards": path_or_none(f"cards_{session}.csv"),
        "order_tickets": path_or_none(f"order_tickets_{session}.md"),
        "ticket_ready": path_or_none(f"ticket_ready_{session}.md"),
        "board_rows": path_or_none(f"board_rows_{session}.json"),
        "macro_context": path_or_none(f"triage_macro_context_{session}.csv"),
        "triage_check": verdict,
    }
    changed = [key for key, value in fresh.items() if context.get(key) != value]
    context.update(fresh)
    context["refreshed_local"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    context["refreshed_by"] = VERSION
    context_path.write_text(json.dumps(context, indent=2), encoding="utf-8")
    markdown = context_path.with_suffix(".md")
    if markdown.is_file():
        lines = ["# AVSHUNTER today context", ""] + [
            f"- **{key}**: {', '.join(map(str, value)) if isinstance(value, list) else ('' if value is None else value)}"
            for key, value in context.items()]
        markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed


def _load_macro_state(path: Path) -> dict | None:
    try:
        state = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    return state if isinstance(state, dict) else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--handoff-root", default=str(WORK / "handoff"))
    parser.add_argument("--today", help="session date YYYY-MM-DD (default: the session in today_context.json, else today)")
    parser.add_argument("--out-folder", help="write the list here instead of the day's hand-off folder (replays)")
    parser.add_argument("--no-context", action="store_true", help="do not refresh today_context.json (replays)")
    args = parser.parse_args(argv)
    context_path = WORK / "today_context.json"
    context = json.loads(context_path.read_text(encoding="utf-8-sig")) if context_path.is_file() else {}
    session = args.today or context.get("session") or date.today().isoformat()
    today = date.fromisoformat(session)
    macro_state = _load_macro_state(WORK / "macro_state.json")
    tickets = build_tickets(Path(args.handoff_root), today, macro_state)
    out_folder = Path(args.out_folder) if args.out_folder else Path(context.get("handoff") or Path(args.handoff_root) / f"lab_{session}")
    md_path, _ = write_list(tickets, out_folder, session, macro_state, today)
    print(f"{VERSION}: {len(tickets)} live card(s) -> {md_path}")
    age, why = macro_state_age(macro_state, today)
    if age != "CURRENT":
        print(f"WARNING: macro state {age}: {why}")
    for ticket in tickets:
        if ticket["flags"]:
            print(f"  {ticket['ticker']}: {', '.join(ticket['flags'])}")
    try:
        import collect_board_rows
        folders = [f for f in Path(args.handoff_root).iterdir() if f.is_dir() and session in f.name]
        result = collect_board_rows.collect(folders, session)
        board_path = collect_board_rows.write(result, out_folder, session)
        print(f"board rows: {result['row_count']} row(s) from {result['files_read']} file(s), {len(result['rejected'])} rejected -> {board_path.name}")
    except Exception as error:                                   # the board file is a convenience; the ticket list stands without it
        print(f"WARNING: board rows not collected: {type(error).__name__}: {error}")
    if not args.no_context and not args.out_folder:
        changed = refresh_context(context_path)
        print("today_context.json: " + ("not found" if changed is None else ("refreshed " + (", ".join(changed) or "(no change)"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
