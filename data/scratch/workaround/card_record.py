#!/usr/bin/env python3
"""The card as one data record: schema, checker and versioning (card_record_v1, 21 Nov 2026).

AVS-ARCH-LB-001 D1, D1a, D1b (ACK accepted 21 Nov 2026). Read-only on every card file: this checks records and writes
one report. It renders nothing yet and writes to no board, ledger or decision file.

Why (verified 21 Nov on this week's 33 decision files and 24 cards): the card was free-form HTML, so its parts drifted
(thesis sentence, notes switch, exit ladder, lifecycle and market-player read were each missing on some cards), an
updated card could drop data without anyone seeing it, and the board row, the decision file and the order ticket were
each typed separately.

The record is the decision file the deep dives already write, made explicit:
    CORE fields      carried by at least 32 of this week's 33 decision files. Missing or wrong = the record is REJECTED.
    STANDARD fields  the card standard's own parts (thesis sentence, lifecycle stage 1-7, market-player read, liquidity,
                     macro kill switch, 52-week check, sources, Lab rank). Missing = a named gap. They become
                     rejections with strict=True; until ACK switches that on they are flags, never a gate.
Versioning: a later version must be higher, must name what it replaces, and may not drop a field the earlier version
had unless the field is listed in dropped_fields with its reason.

Run from the repo root (PowerShell):
    venv\\Scripts\\python.exe data\\scratch\\workaround\\card_record.py --folder data\\scratch\\workaround\\handoff\\lab_2026-11-20
    venv\\Scripts\\python.exe data\\scratch\\workaround\\card_record.py --folder <hand-off folder> --strict --out-folder %TEMP%\\card_check
Writes card_check_<session>.md (and .json) into the hand-off folder, or --out-folder.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import date, datetime
from pathlib import Path

RECORD_VERSION = "card_record_v1"
VERSION = "card_record_check_v1"
OCC = re.compile(r"^([A-Z]{1,6})\s*(\d{6})([CP])(\d{8})$")
OCC_ANY = re.compile(r"([A-Z]{1,6})?\s*(\d{6})([CP])(\d{8})")
LEDGER = re.compile(r"^(\d{4}-\d{2}-\d{2})_([A-Z][A-Z0-9.\-]*)_([A-Z]+)$")
FOLDER_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")

# Carried by at least 32 of the 33 decision files of 16, 18 and 20 Nov 2026.
CORE_FIELDS = ["ledger_id", "ticker", "card_side", "decision", "final_action", "decision_reason", "contract", "entry_type",
               "limit", "max_pay", "size", "stop", "targets", "time_stop", "one_contract_exit", "events_in_hold", "states",
               "branches", "card_version", "challenge", "checked", "created_utc", "handoff_side", "close_zone_low",
               "close_zone_high", "extra_conditions", "discriminator", "invalidation", "lane", "run_id"]
THESIS_PARTS = ["macro", "sector", "ticker", "move", "by", "unless"]     # "Because [macro], [sector] is [X], and [ticker] is [Y],
#                                                                           so this option should [move] by [date], unless [invalidation]"
STANDARD_FIELDS = ["thesis", "lifecycle_stage", "player_read", "liquidity", "macro_dependency.kill_switch", "resistance_test",
                   "sources", "lab_rank"]
EMPTY = (None, "", [], {})


def _issue(rule: str, field: str, detail: str) -> dict:
    return {"rule": rule, "field": field, "detail": detail}


def _get(record: dict, path: str):
    value = record
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _whole_number(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value == int(value) and value > 0:
        return int(value)
    return None


def _contract(text, ticker: str) -> tuple[str, date | None, str]:
    """(option symbol or "", expiry or None, problem or ""). A branch may write "TICK  261218C00170000 / 261127C00165000"."""
    found = OCC_ANY.search(str(text or "").upper())
    if not found:
        return "", None, "NOT_AN_OPTION_SYMBOL"
    underlying = found.group(1) or ticker
    try:
        expiry = datetime.strptime(found.group(2), "%y%m%d").date()
    except ValueError:
        return "", None, "NOT_AN_OPTION_SYMBOL"
    symbol = f"{underlying}{found.group(2)}{found.group(3)}{found.group(4)}"
    return symbol, expiry, ("" if underlying == ticker else "ON_ANOTHER_TICKER")


def from_decision(decision: dict) -> dict:
    """Read a decision file written before the record existed. Known aliases are mapped; nothing absent is invented."""
    record = copy.deepcopy(decision)
    record.setdefault("record_version", RECORD_VERSION)
    record.setdefault("record_origin", "DECISION_FILE")
    if "lifecycle_stage" not in record or record.get("lifecycle_stage") in EMPTY:
        for alias in ("narrative_stage",):
            if record.get(alias) not in EMPTY:
                record["lifecycle_stage"] = record[alias]
        stage = _get(record, "lifecycle.stage")
        if record.get("lifecycle_stage") in EMPTY and stage not in EMPTY:
            record["lifecycle_stage"] = stage
    if isinstance(record.get("lifecycle_stage"), str):
        found = re.match(r"\s*(\d)", record["lifecycle_stage"])
        if found:
            record["lifecycle_stage"] = int(found.group(1))
    if record.get("player_read") in EMPTY:
        for alias in ("controlling_player", "players"):
            if record.get(alias) not in EMPTY:
                record["player_read"] = record[alias]
                break
    if not isinstance(record.get("size"), int) and record.get("size") not in EMPTY:
        found = re.match(r"\s*(\d+)\b", str(record["size"]))
        if found:
            record["size"] = int(found.group(1))
    return record


def check_record(record: dict, *, strict: bool = False) -> dict:
    """{verdict, errors, standard_gaps}. ACCEPTED, ACCEPTED_WITH_GAPS or REJECTED. Every gap is named."""
    errors: list[dict] = []
    gaps: list[dict] = []
    ticker = str(record.get("ticker") or "").upper().strip()

    for field in CORE_FIELDS:
        if field not in record or (record[field] in EMPTY and field not in ("extra_conditions", "events_in_hold")):
            errors.append(_issue("CORE_FIELD_MISSING", field, "the record has no value for this field"))
    if record.get("record_version") not in (RECORD_VERSION,):
        errors.append(_issue("RECORD_VERSION_UNKNOWN", "record_version", f"expected {RECORD_VERSION}"))

    card_day = None
    created = record.get("created_utc")
    if created not in EMPTY:
        try:
            card_day = datetime.fromisoformat(str(created).replace("Z", "+00:00")).date()
        except ValueError:
            errors.append(_issue("CREATED_UTC_NOT_A_DATE", "created_utc", f"cannot read {created!r} as a date and time"))

    ledger = LEDGER.match(str(record.get("ledger_id") or ""))
    if record.get("ledger_id") not in EMPTY:
        if not ledger:
            errors.append(_issue("LEDGER_ID_FORMAT", "ledger_id", "expected YYYY-MM-DD_TICKER_SIDE"))
        elif ticker and ledger.group(2) != ticker:
            errors.append(_issue("LEDGER_ID_DOES_NOT_MATCH_TICKER", "ledger_id", f"ledger id is for {ledger.group(2)}, the card is {ticker}"))

    if "size" in record and record["size"] not in EMPTY and _whole_number(record["size"]) is None:
        errors.append(_issue("SIZE_NOT_A_WHOLE_NUMBER", "size", f"{record['size']!r} is not a whole number of contracts"))

    def check_contract(text, field: str, prefix: str):
        symbol, expiry, problem = _contract(text, ticker)
        if problem == "NOT_AN_OPTION_SYMBOL":
            errors.append(_issue(f"{prefix}_NOT_AN_OPTION_SYMBOL", field, f"{text!r} is not an option symbol"))
        elif problem == "ON_ANOTHER_TICKER":
            errors.append(_issue(f"{prefix}_ON_ANOTHER_TICKER", field, f"{symbol} is not an option on {ticker}"))
        elif card_day and expiry and expiry <= card_day:
            errors.append(_issue(f"{prefix}_EXPIRES_ON_OR_BEFORE_CARD_DAY", field, f"{symbol} expires {expiry}, the card is dated {card_day}"))

    if record.get("contract") not in EMPTY:
        check_contract(record["contract"], "contract", "CONTRACT")

    branches = record.get("branches")
    sides = set()
    if isinstance(branches, list):
        for index, branch in enumerate(branches):
            where = f"branches[{index}]"
            if not isinstance(branch, dict):
                errors.append(_issue("BRANCH_NOT_AN_OBJECT", where, "a branch must be an object"))
                continue
            side = str(branch.get("side") or "").upper()
            if side not in ("CALL", "PUT"):
                errors.append(_issue("BRANCH_SIDE_NOT_CALL_OR_PUT", f"{where}.side", f"{branch.get('side')!r}"))
            else:
                sides.add(side)
            if branch.get("trigger") in EMPTY:
                errors.append(_issue("BRANCH_TRIGGER_MISSING", f"{where}.trigger", "a branch needs its own trigger"))
            if branch.get("contract") in EMPTY:
                errors.append(_issue("BRANCH_CONTRACT_MISSING", f"{where}.contract", "a branch needs its own contract"))
            else:
                check_contract(branch["contract"], f"{where}.contract", "BRANCH_CONTRACT")
        if len(sides) == 1 and record.get("both_sides_reason") in EMPTY:
            errors.append(_issue("ONE_SIDE_WITHOUT_A_REASON", "both_sides_reason",
                                 "the card standard covers both sides; a one-sided card says why"))
    elif "branches" in record and branches not in EMPTY:
        errors.append(_issue("BRANCHES_NOT_A_LIST", "branches", "branches must be a list"))

    # the card standard's own parts
    for field in STANDARD_FIELDS:
        if _get(record, field) in EMPTY:
            gaps.append(_issue("STANDARD_FIELD_MISSING", field, "the card standard asks for this"))
    thesis = record.get("thesis")
    if isinstance(thesis, dict):
        for part in THESIS_PARTS:
            if thesis.get(part) in EMPTY:
                gaps.append(_issue("THESIS_PART_MISSING", f"thesis.{part}", "the thesis sentence needs every part"))
    elif thesis not in EMPTY:
        gaps.append(_issue("THESIS_NOT_IN_PARTS", "thesis", "the thesis is one sentence; the record needs its six parts"))
    stage = record.get("lifecycle_stage")
    if stage not in EMPTY and not (isinstance(stage, int) and not isinstance(stage, bool) and 1 <= stage <= 7):
        gaps.append(_issue("LIFECYCLE_STAGE_OUT_OF_RANGE", "lifecycle_stage", f"{stage!r} is not a stage from 1 to 7"))

    if strict:
        errors, gaps = errors + gaps, []
    verdict = "REJECTED" if errors else ("ACCEPTED_WITH_GAPS" if gaps else "ACCEPTED")
    return {"verdict": verdict, "errors": errors, "standard_gaps": gaps}


def _flatten(record: dict) -> dict:
    """Top-level fields plus one nested level (one_contract_exit.stop). Lists and deeper objects are compared whole."""
    flat = {}
    for key, value in record.items():
        if isinstance(value, dict) and value:
            for inner, inner_value in value.items():
                flat[f"{key}.{inner}"] = inner_value
        else:
            flat[key] = value
    return flat


def check_supersede(old: dict, new: dict) -> dict:
    """A later version of a card: higher version, names what it replaces, and drops nothing without a reason (D1b)."""
    errors: list[str] = []
    old_version, new_version = _whole_number(old.get("card_version")), _whole_number(new.get("card_version"))
    if old_version is None or new_version is None or new_version <= old_version:
        errors.append("VERSION_NOT_HIGHER")
    if new.get("supersedes") in EMPTY:
        errors.append("SUPERSEDES_NOT_STATED")
    reasons = new.get("dropped_fields") if isinstance(new.get("dropped_fields"), dict) else {}
    old_flat, new_flat = _flatten(old), _flatten(new)
    ignore = {"card_version", "supersedes", "dropped_fields", "updated_utc", "update_source"}
    silently, with_reason, changed = [], [], []
    for field, value in old_flat.items():
        if field in ignore or value in EMPTY:
            continue
        if field not in new_flat or new_flat[field] in EMPTY:
            parent = field.split(".")[0]
            # a whole object that is gone is named once, by its own name, not once per inner field
            name = parent if new.get(parent) in EMPTY else field
            if str(reasons.get(field) or reasons.get(parent) or "").strip():
                with_reason.append(field if field in reasons else parent)
            elif name not in silently:
                silently.append(name)
        elif new_flat[field] != value:
            changed.append(field)
    added = sorted(f for f, v in new_flat.items() if f not in old_flat and f not in ignore and v not in EMPTY)
    if silently:
        errors.append("FIELDS_SILENTLY_DROPPED")
    return {"verdict": "REJECTED" if errors else "ACCEPTED", "errors": errors, "silently_dropped": sorted(silently),
            "dropped_with_reason": sorted(set(with_reason)), "changed": sorted(changed), "added": added}


def check_folder(folder: Path, *, strict: bool = False) -> dict:
    """Check every decisions\\<TICKER>.json in a hand-off folder. The card files are read and never changed."""
    cards, counts = [], {}
    for path in sorted((Path(folder) / "decisions").glob("*.json")):
        if "board_row" in path.name:
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(raw, dict):
                raise ValueError("the file is not a JSON object")
        except (OSError, ValueError) as error:
            cards.append({"ticker": path.stem.upper(), "file": path.name, "verdict": "UNREADABLE", "errors": [
                _issue("FILE_UNREADABLE", path.name, f"{type(error).__name__}: {error}"[:160])], "standard_gaps": []})
            counts["UNREADABLE"] = counts.get("UNREADABLE", 0) + 1
            continue
        result = check_record(from_decision(raw), strict=strict)
        cards.append({"ticker": str(raw.get("ticker") or path.stem).upper(), "file": path.name,
                      "record_origin": "RECORD" if raw.get("record_version") else "DECISION_FILE", **result})
        counts[result["verdict"]] = counts.get(result["verdict"], 0) + 1
    return {"version": VERSION, "folder": str(folder), "strict": strict, "cards": cards, "counts": counts}


def write_report(report: dict, out_folder: Path, session: str) -> Path:
    out_folder = Path(out_folder)
    out_folder.mkdir(parents=True, exist_ok=True)
    tally: dict[str, int] = {}
    for card in report["cards"]:
        for issue in card["errors"] + card["standard_gaps"]:
            key = f"{issue['rule']}: {issue['field'].split('[')[0]}"
            tally[key] = tally.get(key, 0) + 1
    lines = [f"# Card check, session {session}", "",
             f"{VERSION}, written {datetime.now().strftime('%Y-%m-%d %H:%M')} local. Folder {report['folder']}. "
             + ("Strict: the card standard's parts are required." if report["strict"] else
                "The card standard's parts are reported as gaps, not rejections.") + " No card file was changed.", "",
             "## Result", "", ", ".join(f"{k} {v}" for k, v in sorted(report["counts"].items())) or "no cards found", ""]
    if tally:
        lines += ["## What is missing or wrong, by how many cards", ""] + [f"- {v} x {k}" for k, v in sorted(tally.items(), key=lambda i: (-i[1], i[0]))] + [""]
    lines += ["## Card by card", ""]
    for card in report["cards"]:
        lines.append(f"### {card['ticker']} - {card['verdict']}")
        lines += [f"- ERROR {i['rule']} ({i['field']}): {i['detail']}" for i in card["errors"]]
        lines += [f"- gap {i['field']}" for i in card["standard_gaps"]]
        lines.append("")
    path = out_folder / f"card_check_{session}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    (out_folder / f"card_check_{session}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--folder", required=True, help="hand-off folder holding decisions\\<TICKER>.json")
    parser.add_argument("--strict", action="store_true", help="treat the card standard's parts as required")
    parser.add_argument("--out-folder", help="write the report here instead of the hand-off folder")
    args = parser.parse_args(argv)
    folder = Path(args.folder)
    found = FOLDER_DATE.search(folder.name)
    session = found.group(1) if found else date.today().isoformat()
    report = check_folder(folder, strict=args.strict)
    path = write_report(report, Path(args.out_folder) if args.out_folder else folder, session)
    print(f"{VERSION}: {report['counts']} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
