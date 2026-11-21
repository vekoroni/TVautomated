#!/usr/bin/env python3
"""Prefill the batch triage files from the Lab hand-off (v1, 21 Nov 2026).

AVS-ARCH-LB-001 G3 (ACK 21 Nov 2026). The script fills every triage column that files on disk can fill; the chat adds
judgement; live quotes come from the chat or the board. It reads no broker, calls no provider and opens no database.

Why (column map of 21 Nov on the 20 Nov files): a chat built all 84 columns by hand. The macro columns matched the board
context on 52%, 8% and 0% of rows; ATR was estimated on a quarter of rows although the pack held the bars; trigger and
stop existed only inside sentences, so the board had to parse them.

Sources, one per column:
    HANDOFF         copied from handoff.csv as written (ledger id, target and first profit are never rounded)
    MACRO_CONTEXT   copied word for word from triage_macro_context_<session>.csv for the same ledger id
    PACK            measured from the ticker pack's daily bars (ATR14, 15-day and 52-week range, averages, strength vs SPY)
    CALC            a stated rule on hand-off values (lane note, counter side, trigger and stop direction)
    EARLIER CARD    the newest decision file for the name in an earlier hand-off folder
Left blank, always:
    JUDGEMENT       trigger and kill sentences, the chat's own levels, contract reasoning, cluster, narrative, ranking reason
    LIVE QUOTE      contract_bid / contract_ask / contract_oi and everything priced from them. The Lab's saved quote is
                    written as lab_saved_bid / lab_saved_ask / lab_saved_oi, never as the live quote.
    DECISION        filled later by the deep dive or by ACK

Output, in the hand-off folder (never the checker's own file name, so a prefill cannot pass as a finished triage):
    triage_prefill_b<N>_<session>.csv     one per batch, the 84 triage columns plus the numeric and source columns
    triage_prefill_<session>.md           what was filled from where, and what the chat still has to add

Run from the repo root (PowerShell):
    venv\\Scripts\\python.exe data\\scratch\\workaround\\triage_from_lab.py
    venv\\Scripts\\python.exe data\\scratch\\workaround\\triage_from_lab.py --session 2026-11-20 --batches 1 2 3 4 --out-folder %TEMP%\\triage_replay
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

VERSION = "triage_from_lab_v1"
WORK = Path("data") / "scratch" / "workaround"
PACKS_ROOT = Path("data") / "scratch" / "ticker_packs"

# The triage layout in use on 19 and 20 Nov 2026 (84 columns, same order in every batch). The two dated names
# (live_price_1536Z, prev_close_1117) are kept because the deep-dive prompts read them by these names.
TRIAGE_COLUMNS = [
    "deep_mine_rank", "ticker", "batch", "ledger_id", "side", "handoff_state", "timeframe", "money_map_place", "money_tag",
    "macro_sector_agreement", "macro_scenario_ids", "macro_kill_switch", "handoff_sector_etf", "sector_check", "trigger",
    "half_target", "level", "invalidation", "chase_state", "key_level", "entry_criterion", "kill", "earnings_tastytrade",
    "earnings_in_q80", "events_read", "trade_contract", "contract_quote", "contract_spread_pct", "contract_why",
    "ret_at_half_target_at_ask", "pays_at_half_target", "price_line_max_pay_plus20", "handoff_best_contract", "lab_rank",
    "lab_verdict", "lab_contract", "lab_monetisability_state", "lab_opportunity_tier", "split_lane_change",
    "narrative_catalyst", "prev_session_status", "priority_card", "prev_card_date", "prev_card_side", "prev_card_url",
    "prev_card_decision", "cluster", "cluster_role", "main_challenge", "rank_reason", "lab_revision", "target", "first_profit",
    "trigger_state", "contract_bid", "contract_ask", "contract_oi", "contract_tier", "stock_dollar_volume_20d_musd",
    "decision", "decision_reason", "contract_taken", "entry_type", "entry_time", "entry_premium", "exit_time", "exit_premium",
    "counter_side", "counter_ticket", "w52_check", "live_price_1536Z", "prev_close_1117", "atr14", "hi15", "lo15", "sma20",
    "sma50", "hi52w", "lo52w", "rel5_vs_spy", "rel20_vs_spy", "handoff_side", "side_change", "quote_clock"]
EXTRA_COLUMNS = ["trig_kind", "trig_v", "trig_lo", "trig_hi", "stop_dir", "stop_v", "half_v", "inval_v",
                 "lab_saved_bid", "lab_saved_ask", "lab_saved_oi", "lab_saved_quote_tier", "lab_earnings_date", "lb_focus",
                 "pack_as_of", "prefill_gaps", "prefill_state"]
JUDGEMENT_COLUMNS = ["money_map_place", "trigger", "half_target", "level", "invalidation", "key_level", "entry_criterion", "kill",
                     "events_read", "contract_why", "narrative_catalyst", "prev_session_status", "cluster", "cluster_role",
                     "main_challenge", "rank_reason", "earnings_in_q80", "w52_check"]
DECISION_COLUMNS = ["decision", "decision_reason", "contract_taken", "entry_type", "entry_time", "entry_premium", "exit_time",
                    "exit_premium"]
LIVE_QUOTE_COLUMNS = ["chase_state", "earnings_tastytrade", "contract_quote", "contract_spread_pct", "ret_at_half_target_at_ask",
                      "pays_at_half_target", "price_line_max_pay_plus20", "trigger_state", "contract_bid", "contract_ask",
                      "contract_oi", "contract_tier", "counter_ticket", "live_price_1536Z", "quote_clock"]
MACRO_COLUMNS = ["money_tag", "macro_sector_agreement", "macro_scenario_ids", "macro_kill_switch", "sector_check"]
PACK_COLUMNS = ["atr14", "hi15", "lo15", "sma20", "sma50", "hi52w", "lo52w", "rel5_vs_spy", "rel20_vs_spy"]
FOLDER_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
OPPOSITE = {"CALL": "PUT", "PUT": "CALL"}


def _read_csv(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _number(value) -> float | None:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _fmt(value: float, places: int = 2) -> str:
    return f"{value:.{places}f}"


def pack_levels(pack_zip: Path, ticker: str) -> dict:
    """Measured levels from the pack's daily bars. Every value is from the bars; a short history leaves that value blank."""
    with zipfile.ZipFile(pack_zip) as archive:
        names = archive.namelist()
        bars_name = next((n for n in names if n.endswith("prices_ohlcv_daily.csv")), None)
        bench_name = next((n for n in names if n.endswith("prices_benchmarks.csv")), None)
        if not bars_name:
            return {}
        bars = [r for r in csv.DictReader(io.StringIO(archive.read(bars_name).decode("utf-8-sig")))
                if str(r.get("ticker", ticker)).upper() == ticker.upper()]
        bench = list(csv.DictReader(io.StringIO(archive.read(bench_name).decode("utf-8-sig")))) if bench_name else []
    bars = sorted((r for r in bars if _number(r.get("close")) is not None), key=lambda r: r["trading_date"])
    if not bars:
        return {}
    high = [_number(r.get("high")) for r in bars]
    low = [_number(r.get("low")) for r in bars]
    close = [_number(r.get("close")) for r in bars]
    out = {"pack_as_of": bars[-1]["trading_date"]}
    ranges = [max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
              for i in range(1, len(bars)) if None not in (high[i], low[i], close[i - 1])]
    if len(ranges) >= 14:
        out["atr14"] = _fmt(sum(ranges[-14:]) / 14)                      # mean true range of the last 14 sessions
    if len(bars) >= 15 and None not in high[-15:] + low[-15:]:
        out["hi15"], out["lo15"] = _fmt(max(high[-15:])), _fmt(min(low[-15:]))
    for name, window in (("sma20", 20), ("sma50", 50)):
        if len(close) >= window:
            out[name] = _fmt(sum(close[-window:]) / window)
    if len(bars) >= 252 and None not in high[-252:] + low[-252:]:
        out["hi52w"], out["lo52w"] = _fmt(max(high[-252:])), _fmt(min(low[-252:]))
    spy = {r["trading_date"]: _number(r.get("close")) for r in bench if str(r.get("ticker", "")).upper() == "SPY"}
    dates = [r["trading_date"] for r in bars]
    for name, window in (("rel5_vs_spy", 5), ("rel20_vs_spy", 20)):
        if len(close) > window and spy.get(dates[-1]) and spy.get(dates[-1 - window]):
            own = close[-1] / close[-1 - window] - 1
            market = spy[dates[-1]] / spy[dates[-1 - window]] - 1
            out[name] = _fmt((own - market) * 100, 1)                    # percentage points against SPY
    return out


def earlier_card(handoff_root: Path, ticker: str, session: str) -> dict:
    """The newest decision file for the name in a hand-off folder dated before the session."""
    best: tuple[str, dict] | None = None
    root = Path(handoff_root)
    for folder in (root.iterdir() if root.is_dir() else []):
        found = FOLDER_DATE.search(folder.name)
        path = folder / "decisions" / f"{ticker}.json"
        if not found or found.group(1) >= session or not path.is_file():
            continue
        try:
            card = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if isinstance(card, dict) and (best is None or found.group(1) > best[0]):
            best = (found.group(1), card)
    if best is None:
        return {}
    return {"prev_card_date": best[0], "prev_card_side": str(best[1].get("card_side") or ""),
            "prev_card_url": str(best[1].get("artifact_url") or ""), "prev_card_decision": str(best[1].get("decision") or "")}


def _prefill_row(lab: dict, rank: int, macro: dict | None, levels: dict | None, card: dict, lab_revision: str) -> dict:
    row = {column: "" for column in TRIAGE_COLUMNS + EXTRA_COLUMNS}
    gaps: list[str] = []
    ticker = str(lab.get("ticker") or "").upper().strip()
    direction = str(lab.get("direction") or "").upper().strip()
    side = direction if direction in OPPOSITE else ""
    contract = str(lab.get("contract_symbol") or "").strip()
    volume = _number(lab.get("lb_dollar_volume_20d_usd"))
    row.update({
        "deep_mine_rank": str(rank), "ticker": ticker, "batch": str(lab.get("lb_batch") or ""),
        "ledger_id": str(lab.get("lb_ledger_id") or ""), "side": side,
        "handoff_state": str(lab.get("thesis__readiness") or ""),
        "timeframe": str(lab.get("trade_lane_setup") or "").split("|")[0],
        "handoff_sector_etf": str(lab.get("sector_etf") or "").strip() or "NO_ETF",
        "trade_contract": contract, "handoff_best_contract": contract, "lab_contract": contract,
        "lab_rank": str(lab.get("lab_rank") or ""), "lab_verdict": str(lab.get("lab_verdict") or ""),
        "lab_monetisability_state": str(lab.get("monetisation_state") or ""),
        "lab_opportunity_tier": str(lab.get("lb_saved_gate") or ""),
        "split_lane_change": (f"window {lab.get('lb_window_flag') or '-'}; time fit {lab.get('lb_time_fit') or '-'}; "
                              f"gate {lab.get('lb_saved_gate') or '-'}; group {lab.get('lb_group') or '-'} {lab.get('lb_group_role') or ''}").strip(),
        "lab_revision": lab_revision,
        "target": str(lab.get("anticipated_level") or ""), "first_profit": str(lab.get("anticipated_level_q50") or ""),
        "stock_dollar_volume_20d_musd": _fmt(volume / 1e6, 1) if volume is not None else "",
        "counter_side": OPPOSITE.get(side, ""), "prev_close_1117": str(lab.get("signal_price") or ""),
        "handoff_side": direction, "side_change": "N" if side else "",
        "trig_v": str(lab.get("thesis_trigger_level") or ""), "stop_v": str(lab.get("invalidation_price") or ""),
        "half_v": str(lab.get("anticipated_level_q50") or ""), "inval_v": str(lab.get("invalidation_price") or ""),
        "lab_saved_bid": str(lab.get("contract_bid") or ""), "lab_saved_ask": str(lab.get("contract_ask") or ""),
        "lab_saved_oi": str(lab.get("contract_oi") or ""), "lab_saved_quote_tier": str(lab.get("quote_tier") or ""),
        "lab_earnings_date": str(lab.get("earnings_date") or ""), "lb_focus": str(lab.get("lb_focus") or ""),
        "priority_card": "Y" if card else "N",
    })
    row.update(card)
    if side:
        fired = str(lab.get("thesis_event_state") or "").upper() == "ACTIVATED"
        row["trig_kind"] = "fired" if fired else ("above" if side == "CALL" else "below")
        row["stop_dir"] = "below" if side == "CALL" else "above"
    else:
        gaps.append("NO_SINGLE_SIDE")
    if not contract:
        gaps.append("NO_LAB_CONTRACT")
    if not row["trig_v"]:
        gaps.append("NO_LAB_TRIGGER_LEVEL")
    if macro is None:
        gaps.append("MACRO_CONTEXT_MISSING")
    elif not macro:
        gaps.append("MACRO_CONTEXT_ROW_MISSING")
    else:
        row.update({column: str(macro.get(column) or "") for column in MACRO_COLUMNS})
    if levels is None:
        gaps.append("PACK_MISSING")
    else:
        row.update({column: levels.get(column, "") for column in PACK_COLUMNS + ["pack_as_of"]})
        short = [column for column in PACK_COLUMNS if not levels.get(column)]
        if short:
            gaps.append("PACK_SHORT_HISTORY:" + "+".join(short))
    row["prefill_gaps"] = ";".join(gaps)
    row["prefill_state"] = "PREFILLED_BY_CODE: judgement, decision and live-quote columns are blank"
    return row


def build_prefill(folder: Path, session: str, *, batches: list[int], packs_folder: Path | None, handoff_root: Path) -> dict[int, list[dict]]:
    """{batch number: prefilled rows in the Lab order} for one hand-off folder. Reads files only; writes nothing."""
    folder = Path(folder)
    handoff = folder / "handoff.csv"
    if not handoff.is_file():
        raise FileNotFoundError(f"no handoff.csv in {folder}: build the hand-off first")
    lab_rows = _read_csv(handoff)
    receipt_path = folder / "receipt.json"
    lab_revision = ""
    if receipt_path.is_file():
        lab_revision = str(json.loads(receipt_path.read_text(encoding="utf-8-sig")).get("lab_revision") or "")
    macro_path = folder / f"triage_macro_context_{session}.csv"
    macro_by_id = {r.get("ledger_id"): r for r in _read_csv(macro_path)} if macro_path.is_file() else None
    out: dict[int, list[dict]] = {}
    for batch in batches:
        members = sorted((r for r in lab_rows if str(r.get("lb_batch") or "").strip() == str(batch)),
                         key=lambda r: _number(r.get("lb_order")) or 0)
        rows = []
        for rank, lab in enumerate(members, 1):
            ticker = str(lab.get("ticker") or "").upper().strip()
            pack_zip = Path(packs_folder) / f"{ticker}_pack.zip" if packs_folder else None
            levels = None
            if pack_zip is not None and pack_zip.is_file():
                try:
                    levels = pack_levels(pack_zip, ticker)
                except (OSError, zipfile.BadZipFile, KeyError, ValueError):
                    levels = None
            macro = None if macro_by_id is None else (macro_by_id.get(lab.get("lb_ledger_id")) or {})
            rows.append(_prefill_row(lab, rank, macro, levels, earlier_card(handoff_root, ticker, session), lab_revision))
        out[batch] = rows
    return out


def write_prefill(prefill: dict[int, list[dict]], out_folder: Path, session: str) -> list[Path]:
    out_folder = Path(out_folder)
    out_folder.mkdir(parents=True, exist_ok=True)
    paths, counts = [], []
    for batch, rows in sorted(prefill.items()):
        path = out_folder / f"triage_prefill_b{batch}_{session}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=TRIAGE_COLUMNS + EXTRA_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        paths.append(path)
        gaps: dict[str, int] = {}
        for row in rows:
            for gap in filter(None, row["prefill_gaps"].split(";")):
                gaps[gap.split(":")[0]] = gaps.get(gap.split(":")[0], 0) + 1
        counts.append(f"- Batch {batch}: {len(rows)} names. Gaps: " + (", ".join(f"{k} {v}" for k, v in sorted(gaps.items())) or "none"))
    note = [
        f"# Triage prefill, session {session}", "",
        f"{VERSION}, written {datetime.now().strftime('%Y-%m-%d %H:%M')} local. Built by code from files on disk. It reads no broker "
        "and never invents a value: a blank means the files did not hold it.", "",
        "## What is in each batch", "", *counts, "",
        "## Filled by code, and from where", "",
        "- **Lab hand-off (as written, never rounded):** ticker, batch, ledger_id, side and handoff_side (the Lab's side), handoff_state, "
        "timeframe, handoff_sector_etf, trade_contract and lab_contract (the Lab's contract), lab_rank, lab_verdict, "
        "lab_monetisability_state, lab_opportunity_tier, split_lane_change, lab_revision, target, first_profit, "
        "stock_dollar_volume_20d_musd, prev_close_1117, lb_focus.",
        "- **Board macro context, word for word:** " + ", ".join(MACRO_COLUMNS) + ".",
        "- **Ticker pack, measured from daily bars:** " + ", ".join(PACK_COLUMNS) + " (pack_as_of gives the last bar).",
        "- **Numbers for the board:** trig_kind, trig_v, stop_dir, stop_v, half_v, inval_v (the Lab's levels). trig_lo and trig_hi are "
        "for a zone and are left for the chat.",
        "- **Earlier card:** priority_card, prev_card_date, prev_card_side, prev_card_url, prev_card_decision.", "",
        "## Left blank for the chat: judgement", "",
        ", ".join(JUDGEMENT_COLUMNS) + ". Also deep_mine_rank (given here in the Lab order; re-order it and say why in rank_reason), "
        "side and trade_contract where the chat disagrees with the Lab (say why in contract_why and set side_change).", "",
        "## Left blank for the chat: needs a live quote", "",
        ", ".join(LIVE_QUOTE_COLUMNS) + ". The Lab's saved quote is in lab_saved_bid, lab_saved_ask, lab_saved_oi and "
        "lab_saved_quote_tier. It is a saved quote: never copy it into contract_bid or contract_ask. The Lab's earnings date is in "
        "lab_earnings_date; earnings_tastytrade is for the date checked on Tastytrade.", "",
        "## Left blank until the deep dive or ACK: decisions", "", ", ".join(DECISION_COLUMNS) + ".", "",
        "## To finish a batch", "",
        f"Save the completed batch as batch<N>_triage_{session}.csv with the first 84 columns in the same order (the extra columns may "
        "stay). The triage check reads that file name, never this prefill.", ""]
    note_path = out_folder / f"triage_prefill_{session}.md"
    note_path.write_text("\n".join(note), encoding="utf-8")
    return paths + [note_path]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--session", help="session date YYYY-MM-DD (default: the session in today_context.json)")
    parser.add_argument("--folder", help="hand-off folder (default: the handoff in today_context.json, else handoff\\lab_<session>)")
    parser.add_argument("--batches", type=int, nargs="+", default=[1, 2, 3, 4])
    parser.add_argument("--packs-folder", help="default: data\\scratch\\ticker_packs\\<session>")
    parser.add_argument("--handoff-root", default=str(WORK / "handoff"))
    parser.add_argument("--out-folder", help="write here instead of the hand-off folder (replays)")
    args = parser.parse_args(argv)
    context_path = WORK / "today_context.json"
    context = json.loads(context_path.read_text(encoding="utf-8-sig")) if context_path.is_file() else {}
    session = args.session or context.get("session")
    if not session:
        parser.error("no --session and no session in today_context.json")
    folder = Path(args.folder) if args.folder else (
        Path(context["handoff"]) if context.get("handoff") and context.get("session") == session
        else Path(args.handoff_root) / f"lab_{session}")
    packs = Path(args.packs_folder) if args.packs_folder else PACKS_ROOT / session
    prefill = build_prefill(folder, session, batches=args.batches, packs_folder=packs if packs.is_dir() else None,
                            handoff_root=Path(args.handoff_root))
    paths = write_prefill(prefill, Path(args.out_folder) if args.out_folder else folder, session)
    for batch, rows in sorted(prefill.items()):
        filled = sum(1 for r in rows if not r["prefill_gaps"])
        print(f"{VERSION}: batch {batch}: {len(rows)} names, {filled} with no gap")
    print(f"{VERSION}: wrote {len(paths)} file(s) to {paths[-1].parent}")
    if not packs.is_dir():
        print(f"WARNING: no packs folder {packs}: the pack columns are blank (run avs_day.ps1 packs first)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
