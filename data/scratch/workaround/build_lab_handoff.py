#!/usr/bin/env python3
"""Build the Lane B hand-off from the Intelligence Lab's publication (Lane B Fix B, items B1-B3, 12 Nov 2026).

Principle (ACK, 12 Nov): pipeline output is the input. The hand-off is the Lab's review projection, copied. Lane B adds
flags, an order and batches in columns prefixed lb_. It never recomputes, caps or replaces a Lab field: no half target,
no own target, no own contract. Where Lane B disagrees with the Lab it writes a flag.

Read-only on the run folder, the Lab database (opened mode=ro) and the canonical price store. Writes only under
data/scratch/workaround/handoff/lab_<session>/:
    handoff.csv             one row per Lab row: every Lab card field under its Lab name, then the lb_ columns
    handoff_evidence.jsonl  per row: the card values and the four evidence families (structure, option_risk, context,
                            morning) as stored. The deep-dive input
    handoff.md              counts, the ordering rule, the batch table, the flags summary
    receipt.json            run id, Lab revision, database sha256, created times, settings, counts in and out by reason
    legacy_compare.csv      only when a legacy split_<session>_cap* folder exists: old target / contract beside the Lab's
    pack_commands/ticker_pack_command_<batch>.txt   the full PowerShell line for each batch's packs

Population: lab_verdict GO_LIMIT or MANUAL_REVIEW. Every excluded verdict is counted in the receipt.
Order: GO_LIMIT first, then lab_rank ascending. No weights. Batches of 30 in that order.
Flags (never filters unless the settings say so):
    lb_window_flag   D1 (ACK 12 Nov): the planned hold stays the thesis runway. The trading window is judged on the
                     monetisation clock n when the Lab publishes it; until then on anticipated_sessions_q50, labelled PROXY_Q50
    lb_over_cap      contract_ask above the premium cap (D2): flagged OVER_CAP, kept
    lb_saved_gate    the 11 Nov liquidity tiers on the Lab's SAVED quote (triage re-checks live):
                     A spread <= 10% of mid, OI >= 100, and under a 1.50 premium the spread is <= 0.10 wide; B 10-20%;
                     C over 20%, no bid, or OI < 100
    lb_runway_note   trigger age above the q50 arrival time
    lb_repair_conflict  repair status says required while the repair action says not required (until Codex A4)
    lb_stock_tier    20-day dollar volume from the canonical price store: A >= $50M, B $20-50M, C < $20M (C not tradeable)
Groups: lb_group = sector_etf + direction (the Lab has no cluster field); first row in order is PRIMARY, the rest ALTERNATE.

A changed Lab revision for a session that already has a hand-off is refused unless --refresh, which first copies the
previous set into lab_<session>/_rev_<old revision>/ (triage files and cards stay where they are).

Run (PowerShell, repo root):
    venv\\Scripts\\python.exe data\\scratch\\workaround\\build_lab_handoff.py --run 20261111_231951
    venv\\Scripts\\python.exe data\\scratch\\workaround\\build_lab_handoff.py --run 20261111_231951 --refresh
    venv\\Scripts\\python.exe data\\scratch\\workaround\\build_lab_handoff.py --run 20261111_231951 --spotcheck audit\\laneb_fixB\\B1_spotcheck.csv
Settings: defaults below; overrides in data\\scratch\\workaround\\lab_handoff_settings.json; the premium cap is the one in day_settings.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import sqlite3
import sys
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
import lab_reader  # noqa: E402

VERSION = "build_lab_handoff_v1"
WORK = ROOT / "data" / "scratch" / "workaround"
PRICE_DB = ROOT / "data" / "canonical" / "historical_prices.sqlite"
POPULATION = ("GO_LIMIT", "MANUAL_REVIEW")
GENERATED = ("handoff.csv", "handoff_evidence.jsonl", "handoff.md", "receipt.json", "legacy_compare.csv", "pack_commands")
MONETISATION = ("monetisation_n_q50", "monetisation_n_q80", "monetisation_threshold")
SPOT_NAMES = ("HSBC", "CPNG", "PH", "AZZ", "NXST")
DEFAULTS = {
    # D1 trading window (ACK 12 Nov): flag by default; the planned hold is never capped
    "window_mode": "flag",                    # flag | filter
    "window_max_q50_sessions": 20,
    "window_timeframes": ["1d"],
    "window_include_weekly_monthly": "flag",  # flag = weekly/monthly setups are flagged OUTSIDE_WINDOW; include = judged on the clock alone
    # D2 premium cap: the value comes from day_settings.json (cap); this is the fallback
    "premium_cap": 5.0,
    "over_cap_lane": "flag",
    # 11 Nov liquidity tiers
    "tier_a_spread_pct": 10.0, "tier_b_spread_pct": 20.0, "tier_min_oi": 100,
    "tier_low_premium": 1.50, "tier_low_premium_max_width": 0.10,
    # stock tier
    "stock_tier_a_usd": 50_000_000, "stock_tier_b_usd": 20_000_000, "stock_tier_bars": 20,
    "batch_size": 30,
    "spotcheck_random_rows": 20, "spotcheck_seed": 20261112,
}


# ---------------------------------------------------------------- small helpers

def num(value):
    """A number as stored by the Lab (which mixes numbers and number-strings), else None. Blank is None, never 0."""
    if value is None or isinstance(value, bool):
        return None
    try:
        text = str(value).strip()
        if text == "":
            return None
        result = float(text)
        return result if result == result and abs(result) != float("inf") else None
    except (TypeError, ValueError):
        return None


def cell(value) -> str:
    """How a stored value is written to the CSV: blank for not available (None or ''), the value otherwise. 0 stays 0."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def g(x: float) -> str:
    return f"{x:g}"


def load_settings(settings_file: Path, day_settings_file: Path) -> dict:
    settings = dict(DEFAULTS)
    if settings_file.exists():
        override = json.loads(settings_file.read_text(encoding="utf-8-sig"))
        unknown = sorted(set(override) - set(DEFAULTS))
        if unknown:
            raise SystemExit(f"Unknown setting(s) in {settings_file}: {', '.join(unknown)}")
        settings.update(override)
    if day_settings_file.exists():   # one owner for the premium cap: avs_day.ps1 -Cap
        cap = num(json.loads(day_settings_file.read_text(encoding="utf-8-sig")).get("cap"))
        if cap:
            settings["premium_cap"] = cap
    if settings["window_mode"] not in ("flag", "filter"):
        raise SystemExit("window_mode must be flag or filter")
    return settings


def next_session(day: date) -> date:
    """The first XNYS session after the day (the repo's calendar owner: avshunter.shared.xnys_calendar)."""
    from avshunter.shared.xnys_calendar import is_xnys_session
    current = day + timedelta(days=1)
    while not is_xnys_session(current):
        current += timedelta(days=1)
    return current


def decision_session(rows: list[dict]) -> tuple[str, str]:
    """The session this hand-off is for: the first XNYS session after the Lab's bar date. Returns (session, basis)."""
    bars = Counter(str(r["values"].get("bar_data_asof") or "")[:10] for r in rows)
    bars.pop("", None)
    if not bars:
        raise SystemExit("The Lab rows carry no bar_data_asof: the session cannot be derived. Pass --session YYYY-MM-DD.")
    bar = bars.most_common(1)[0][0]
    session = next_session(date.fromisoformat(bar)).isoformat()
    refs = Counter(str((r["extra"].get("timing_details") or {}).get("expiry_reference_date") or "") for r in rows)
    refs.pop("", None)
    lab_ref = refs.most_common(1)[0][0] if refs else ""
    basis = f"first XNYS session after bar_data_asof {bar}"
    if lab_ref:
        basis += f"; Lab timing reference date {lab_ref} " + ("agrees" if lab_ref == session else "DIFFERS")
    return session, basis


def publication_stage(manifest: dict) -> str:
    for item in (manifest.get("source_receipt") or {}).get("watch_inputs") or []:
        if "morning_validated_trades" in str(item.get("path", "")) and item.get("exists"):
            return "MORNING_PUBLICATION"
    return "EVENING_PUBLICATION"


# ---------------------------------------------------------------- B3 flags (on Lab fields; nothing here changes a Lab field)

def liquidity_tier(bid, ask, oi, settings: dict = DEFAULTS) -> tuple[str, str, float | None]:
    """The 11 Nov tiers on one quote. Returns (tier, reason, spread as % of mid)."""
    bid, ask, oi = num(bid), num(ask), num(oi)
    if ask is None or ask <= 0:
        return "C", "NO_ASK", None
    if bid is None or bid <= 0:
        return "C", "NO_BID", None
    mid = (bid + ask) / 2.0
    width = ask - bid
    pct = width / mid * 100.0
    if oi is None:
        return "C", "OI_NOT_RECORDED", pct
    if oi < settings["tier_min_oi"]:
        return "C", f"OI_{g(oi)}_UNDER_{g(settings['tier_min_oi'])}", pct
    if pct > settings["tier_b_spread_pct"] + 1e-9:
        return "C", f"SPREAD_{pct:.1f}PCT_OVER_{g(settings['tier_b_spread_pct'])}", pct
    if pct > settings["tier_a_spread_pct"] + 1e-9:
        return "B", f"SPREAD_{pct:.1f}PCT", pct
    if mid < settings["tier_low_premium"] and width > settings["tier_low_premium_max_width"] + 1e-9:
        return "B", f"PREMIUM_UNDER_{g(settings['tier_low_premium'])}_SPREAD_{width:.2f}_WIDE", pct
    return "A", f"SPREAD_{pct:.1f}PCT", pct


def window_flag(values: dict, settings: dict) -> tuple[str, str, str]:
    """(flag, reason, basis). The clock is the Lab's monetisation n when published, else the q50 arrival time (PROXY_Q50)."""
    n = num(values.get("monetisation_n_q50"))
    clock, basis = (n, "MONETISATION_N_Q50") if n is not None else (num(values.get("anticipated_sessions_q50")), "PROXY_Q50")
    timeframe = str(values.get("trade_lane_setup") or "").split("|")[0].strip()
    limit = settings["window_max_q50_sessions"]
    if clock is None:
        return "NOT_ASSESSED", "NO_ARRIVAL_TIME_PUBLISHED", basis
    if timeframe not in settings["window_timeframes"] and settings["window_include_weekly_monthly"] == "flag":
        return "OUTSIDE_WINDOW", f"TIMEFRAME_{timeframe or 'UNKNOWN'}_NOT_IN_{'+'.join(settings['window_timeframes'])}; clock {g(clock)} sessions", basis
    if clock > limit:
        return "OUTSIDE_WINDOW", f"CLOCK_{g(clock)}_SESSIONS_OVER_{g(limit)}", basis
    return "IN_WINDOW", f"CLOCK_{g(clock)}_SESSIONS_WITHIN_{g(limit)}", basis


def stock_tiers(tickers: list[str], price_db: Path, settings: dict) -> dict[str, tuple[str, float | None, str]]:
    """{ticker: (tier, mean dollar volume over the last N COMPLETE bars, last bar date)}. Read-only on the price store."""
    out = {t: ("NO_PRICE_HISTORY", None, "") for t in tickers}
    price_db = Path(price_db)
    if not price_db.exists() or not tickers:
        return out
    bars = int(settings["stock_tier_bars"])
    with sqlite3.connect(f"file:{price_db.as_posix()}?mode=ro", uri=True) as con:
        last = con.execute("SELECT MAX(trading_date) FROM ohlcv_daily WHERE bar_status='COMPLETE'").fetchone()[0]
        if not last:
            return out
        since = (date.fromisoformat(last[:10]) - timedelta(days=bars * 3)).isoformat()
        per: dict[str, dict[str, float]] = {}
        for ticker, day, close, volume in con.execute(
                "SELECT ticker, trading_date, close, volume FROM ohlcv_daily WHERE bar_status='COMPLETE' AND trading_date >= ? "
                "ORDER BY ticker, trading_date, adjustment_convention", (since,)):
            per.setdefault(ticker, {})[day] = float(close) * float(volume)   # one value per date (first convention wins on a tie)
    for t in tickers:
        days = sorted(per.get(t, {}))[-bars:]
        if len(days) < bars:
            continue
        mean = sum(per[t][d] for d in days) / bars
        tier = "A" if mean >= settings["stock_tier_a_usd"] else ("B" if mean >= settings["stock_tier_b_usd"] else "C")
        out[t] = (tier, mean, days[-1])
    return out


def lane_b_columns(values: dict, evidence: dict, settings: dict, published: set[str]) -> dict:
    lb: dict = {}
    flag, reason, basis = window_flag(values, settings)
    lb["lb_window_flag"], lb["lb_window_reason"], lb["lb_window_basis"] = flag, reason, basis
    lb["lb_time_fit"] = cell(values.get("anticipated_time_fit"))
    ask = num(values.get("contract_ask"))
    lb["lb_over_cap"] = "NO_QUOTE" if ask is None else ("OVER_CAP" if ask > settings["premium_cap"] + 1e-9 else "WITHIN_CAP")
    if not str(values.get("contract_symbol") or "").strip():
        lb["lb_saved_gate"], lb["lb_saved_gate_reason"], lb["lb_saved_spread_pct"], lb["lb_saved_gate_basis"] = "NO_CONTRACT", "LAB_SELECTED_NO_CONTRACT", "", ""
    else:
        tier, why, pct = liquidity_tier(values.get("contract_bid"), values.get("contract_ask"), values.get("contract_oi"), settings)
        lb["lb_saved_gate"], lb["lb_saved_gate_reason"] = tier, why
        lb["lb_saved_spread_pct"] = "" if pct is None else f"{pct:.2f}"
        lb["lb_saved_gate_basis"] = "SAVED_QUOTE " + (cell(values.get("selected_quote_timestamp_utc")) or "time not recorded")
    age, q50 = num(values.get("thesis__trigger_age_sessions")), num(values.get("anticipated_sessions_q50"))
    lb["lb_trigger_age"] = "" if age is None else g(age)
    lb["lb_runway_note"] = f"TRIGGER_AGE_{g(age)}_EXCEEDS_Q50_{g(q50)}" if age is not None and q50 is not None and age > q50 else ""
    risk = evidence.get("option_risk") or {}
    status, action = str(risk.get("contract_repair_status") or ""), str(risk.get("contract_repair_action") or "")
    lb["lb_repair_status"], lb["lb_repair_action"] = status, action
    lb["lb_repair_conflict"] = "True" if ("REQUIRED" in status and "NOT_REQUIRED" not in status and action == "NOT_REQUIRED") else "False"
    for name in MONETISATION:   # the Lab's clock, when it exists; never computed here
        if name not in published:
            lb[name] = ""
    lb["monetisation_state"] = "PUBLISHED" if "monetisation_n_q50" in published else "NOT_PUBLISHED"
    return lb


# ---------------------------------------------------------------- B2 legacy comparison (reads the old folder, never writes to it)

def read_csv(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def same_number(a, b, tolerance: float = 0.005) -> bool:
    x, y = num(a), num(b)
    return (x is None and y is None) or (x is not None and y is not None and abs(x - y) <= tolerance)


def legacy_compare(session: str, legacy_root: Path, lab_rows: dict[str, dict]) -> tuple[list[dict], str]:
    folders = sorted((p for p in Path(legacy_root).glob(f"split_{session}_cap*") if (p / "handoff.csv").exists()),
                     key=lambda p: p.stat().st_mtime) if Path(legacy_root).exists() else []
    if not folders:
        return [], "LEGACY_NOT_BUILT"
    folder = folders[-1]
    triage = {}
    for f in sorted(folder.glob("batch*_triage_*.csv")):
        for r in read_csv(f):
            triage[str(r.get("ticker", "")).upper().strip()] = r
    out = []
    for r in read_csv(folder / "handoff.csv"):
        t = str(r.get("ticker", "")).upper().strip()
        lab = lab_rows.get(t)
        v = lab["values"] if lab else {}
        legacy_contract = (r.get("best_contract_checked") or r.get("best_contract") or "").replace(" ", "")
        tri = triage.get(t, {})
        row = {"ticker": t, "side": r.get("side", ""), "in_lab_handoff": str(lab is not None),
               "legacy_target": r.get("level", ""), "legacy_half_target": r.get("half_target", ""),
               "legacy_contract": legacy_contract, "legacy_options_tool_contract": (r.get("best_contract") or "").replace(" ", ""),
               "legacy_triage_contract": tri.get("trade_contract", ""),
               "lab_target": cell(v.get("anticipated_level")), "lab_first_profit": cell(v.get("anticipated_level_q50")),
               "lab_contract": cell(v.get("contract_symbol"))}
        if lab is None:
            row.update({"target_differs": "", "first_profit_differs": "", "contract_differs": "", "differs": "NOT_IN_LAB_HANDOFF"})
        else:
            td = not same_number(row["legacy_target"], row["lab_target"])
            fd = not same_number(row["legacy_half_target"], row["lab_first_profit"])
            contracts = {c for c in (legacy_contract, row["legacy_options_tool_contract"]) if c}
            tc = str(tri.get("trade_contract", "")).replace(" ", "")
            if tc and tc[:1].isalpha() and any(ch.isdigit() for ch in tc) and " " not in str(tri.get("trade_contract", "")).strip():
                contracts.add(tc)
            cd = any(c != row["lab_contract"] for c in contracts)
            row.update({"target_differs": str(td), "first_profit_differs": str(fd), "contract_differs": str(cd), "differs": str(td or fd or cd)})
        out.append(row)
    return out, f"legacy folder {folder.name}"


# ---------------------------------------------------------------- B1 acceptance: every copied field against the Lab API

def api_get(url: str):
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def spotcheck(folder: Path, lab_fields: list[str], run_id: str, revision: str, api: str, out_csv: Path, settings: dict) -> int:
    rows = read_csv(folder / "handoff.csv")
    evidence = {}
    with (folder / "handoff_evidence.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            j = json.loads(line)
            evidence[j["row_key"]] = j
    named = [r for r in rows if r["ticker"] in SPOT_NAMES]
    rest = [r for r in rows if r["ticker"] not in SPOT_NAMES]
    random.Random(settings["spotcheck_seed"]).shuffle(rest)
    sample = rest[: settings["spotcheck_random_rows"]] + named
    lines, bad = [], 0
    for r in sample:
        card = api_get(f"{api}/api/lab/{run_id}/rows/{r['lb_row_key']}?revision={revision}")
        if card.get("revision") != revision:
            raise SystemExit(f"Spot check stopped: the Lab API serves revision {card.get('revision')}, the hand-off was built from {revision}")
        for f in lab_fields:
            mine, theirs = r.get(f, ""), cell(card["fields"].get(f))
            ok = mine == theirs
            bad += not ok
            lines.append({"ticker": r["ticker"], "row_key": r["lb_row_key"], "source": "card", "field": f, "handoff_value": mine,
                          "lab_api_value": theirs, "match": str(ok)})
        for family in lab_reader.FAMILIES:
            theirs = api_get(f"{api}/api/lab/{run_id}/rows/{r['lb_row_key']}/evidence/{family}?revision={revision}").get("fields")
            mine = evidence[r["lb_row_key"]]["evidence"].get(family)
            ok = mine == theirs
            bad += not ok
            lines.append({"ticker": r["ticker"], "row_key": r["lb_row_key"], "source": f"evidence:{family}", "field": f"{len(mine or {})} fields",
                          "handoff_value": "(whole family)", "lab_api_value": "(whole family)", "match": str(ok)})
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(lines[0]))
        writer.writeheader(); writer.writerows(lines)
    missing = [n for n in SPOT_NAMES if n not in {r["ticker"] for r in named}]
    print(f"Spot check against {api} revision {revision}: {len(sample)} rows ({len(named)} named, seed {settings['spotcheck_seed']}), "
          f"{len(lines)} comparisons, {bad} differ -> {'PASS' if bad == 0 else 'FAIL'}; {out_csv}")
    if missing:
        print(f"  named rows not in the hand-off population: {', '.join(missing)}")
    return bad


# ---------------------------------------------------------------- build

def archive_previous(folder: Path, old_revision: str, same_revision: bool = False) -> Path:
    target = folder / f"_rev_{old_revision[:8]}"
    if target.exists():
        target = folder / f"_rev_{old_revision[:8]}_{datetime.now():%H%M%S}"
    target.mkdir(parents=True)
    for name in GENERATED:
        src = folder / name
        if same_revision and name == "handoff_evidence.jsonl":
            continue   # same Lab revision = same evidence: the large file is not copied twice
        if src.is_dir():
            shutil.copytree(src, target / name)
        elif src.exists():
            shutil.copy2(src, target / name)
    return target


def write_markdown(folder: Path, receipt: dict, rows: list[dict], settings: dict) -> None:
    c = receipt["counts"]
    md = [f"# Lab hand-off, session {receipt['session']}", "",
          f"{VERSION}. Built {receipt['built_at_utc']} from run {receipt['run_id']}, Lab revision `{receipt['lab_revision']}` "
          f"({receipt['lab_publication_stage']}, published {receipt['lab_created_at_utc']}).", "",
          "Every Lab field is copied as stored. Columns prefixed `lb_` are Lane B flags; they never replace a Lab field. "
          "Target = `anticipated_level`, first profit = `anticipated_level_q50`, contract = `contract_symbol`.", "",
          "## Counts", "",
          f"- Lab rows in: {c['lab_rows_in']}",
          f"- Hand-off rows: {c['handoff_rows']} ({', '.join(f'{k} {v}' for k, v in c['handoff_by_verdict'].items())})",
          f"- Excluded by verdict: {', '.join(f'{k} {v}' for k, v in c['excluded_by_verdict'].items()) or 'none'}",
          f"- Excluded by window filter: {c['excluded_by_window_filter']} (window_mode = {settings['window_mode']})", "",
          "## Order", "", "GO_LIMIT first, then `lab_rank` ascending. No weights. Batches of "
          f"{settings['batch_size']} in that order ({c['batches']} batches).", "",
          "## Flags (counts on the hand-off rows)", ""]
    for name, counts in receipt["flags"].items():
        md.append(f"- **{name}**: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    md += ["", f"Monetisation clock n: {receipt['monetisation_state']}. Window basis: "
           + ", ".join(f"{k} {v}" for k, v in receipt["flags"]["lb_window_basis"].items()) + ".", "",
           "## Batch 1", "", "| # | Ticker | Dir | Verdict | Lab rank | Setup | Target | First profit | Contract | Ask | Window | Gate | Stock | Group |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["lb_batch"] != "1":
            break
        md.append(f"| {r['lb_order']} | {r['ticker']} | {r.get('direction', '')} | {r.get('lab_verdict', '')} | {r.get('lab_rank', '')} | "
                  f"{r.get('trade_lane_setup', '').replace('|', ' / ')} | {r.get('anticipated_level', '')} | {r.get('anticipated_level_q50', '')} | "
                  f"{r.get('contract_symbol', '')} | {r.get('contract_ask', '')} | {r['lb_window_flag']} | {r['lb_saved_gate']} | "
                  f"{r['lb_stock_tier']} | {r['lb_group']} {r['lb_group_role']} |")
    md += ["", "## Packs", "", "One command file per batch in `pack_commands\\`. Or: `avs_day.ps1 packs -Batch N`.", ""]
    if receipt["lab_fields_missing"]:
        md += ["## Lab fields this build wanted and the manifest does not publish", "", ", ".join(receipt["lab_fields_missing"]), ""]
    (folder / "handoff.md").write_text("\n".join(md), encoding="utf-8")


WANTED = ["ticker", "sector_etf", "direction", "lab_rank", "lab_verdict", "final_action", "rank_expected_multiple", "rank_basis",
          "trade_lane_setup", "thesis__readiness", "thesis__event_status", "thesis__trigger_age_sessions", "thesis_trigger_level",
          "invalidation_price", "early_warning_invalidation_level", "anticipated_level", "anticipated_level_basis",
          "anticipated_level_q50", "anticipated_sessions_q50", "anticipated_sessions_q80", "planned_hold_sessions",
          "planned_hold_source", "anticipated_time_fit", "anticipated_evidence_status", "anticipated_evidence_n", "contract_symbol",
          "expiry", "contract_dte", "contract_bid", "contract_ask", "contract_oi", "contract_iv", "contract_delta",
          "selected_quote_timestamp_utc", "scenario_target_return_on_premium", "scenario_stall_return_on_premium",
          "scenario_invalidation_return_on_premium", "scenario_exit_sessions", "bar_data_asof", *MONETISATION]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="run id (default: the newest run whose Lab review projection is COMPLETE)")
    ap.add_argument("--session", help="decision session YYYY-MM-DD (default: first XNYS session after the Lab's bar date)")
    ap.add_argument("--refresh", action="store_true", help="rebuild an existing lab_<session> folder; the previous set is kept in _rev_<revision>")
    ap.add_argument("--spotcheck", help="write the B1 spot check (every copied field against the Lab API) to this CSV")
    ap.add_argument("--api", default="http://localhost:5002", help="Lab app address, used only by --spotcheck")
    ap.add_argument("--runs-dir", default=str(lab_reader.RUNS_DIR))
    ap.add_argument("--out-root", default=str(WORK / "handoff"))
    ap.add_argument("--legacy-root", default=str(WORK / "handoff"))
    ap.add_argument("--price-db", default=str(PRICE_DB))
    ap.add_argument("--settings", default=str(WORK / "lab_handoff_settings.json"))
    ap.add_argument("--day-settings", default=str(WORK / "day_settings.json"))
    a = ap.parse_args(argv)
    settings = load_settings(Path(a.settings), Path(a.day_settings))

    try:
        lab = lab_reader.open_lab(a.run, Path(a.runs_dir))
    except lab_reader.LabUnavailable as error:
        print(f"REFUSED: {error}")
        return 2
    with lab:
        manifest = lab.manifest
        all_rows = list(lab.rows())
        published = set(lab.fields)
        missing_fields = [f for f in WANTED if f not in published]
        verdict = lambda r: str(r["values"].get("lab_verdict") or "")   # noqa: E731
        excluded = Counter(verdict(r) or "(blank)" for r in all_rows if verdict(r) not in POPULATION)
        keep = [r for r in all_rows if verdict(r) in POPULATION]
        if not keep:
            print(f"REFUSED: run {lab.run_id} has no GO_LIMIT or MANUAL_REVIEW row (verdicts: {dict(excluded)})")
            return 2
        session, session_basis = (a.session, "given with --session") if a.session else decision_session(all_rows)
        folder = Path(a.out_root) / f"lab_{session}"
        old_receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8")) if (folder / "receipt.json").exists() else None
        if old_receipt and not a.refresh:
            if old_receipt.get("lab_revision") == lab.revision:
                print(f"Hand-off for session {session} is already built from Lab revision {lab.revision}: {folder} (use --refresh to rebuild)")
                return 0 if not a.spotcheck else (1 if spotcheck(folder, lab.fields, lab.run_id, lab.revision, a.api, Path(a.spotcheck), settings) else 0)
            print(f"REFUSED: {folder} was built from Lab revision {old_receipt.get('lab_revision')}; the Lab now publishes {lab.revision}. "
                  "Run again with --refresh: the previous set is first copied into a _rev_ subfolder, triage files and cards are not touched.")
            return 2

        # order: GO_LIMIT first, then lab_rank ascending. Nothing else.
        keep.sort(key=lambda r: (verdict(r) != "GO_LIMIT", num(r["values"].get("lab_rank")) if num(r["values"].get("lab_rank")) is not None else float("inf"),
                                 r["ordinal"]))
        evidence = {r["row_key"]: lab.evidence(r["row_key"]) for r in keep}
        tiers = stock_tiers([str(r["values"].get("ticker")).upper() for r in keep], Path(a.price_db), settings)
        built, dropped_window = [], 0
        for r in keep:
            v = r["values"]
            lb = lane_b_columns(v, evidence[r["row_key"]], settings, published)
            if settings["window_mode"] == "filter" and lb["lb_window_flag"] == "OUTSIDE_WINDOW":
                dropped_window += 1
                continue
            tier, dollars, last_bar = tiers[str(v.get("ticker")).upper()]
            lb["lb_stock_tier"] = tier
            lb["lb_dollar_volume_20d_usd"] = "" if dollars is None else f"{dollars:.0f}"
            lb["lb_stock_tier_basis"] = f"PRICE_STORE {settings['stock_tier_bars']} bars to {last_bar}" if last_bar else ""
            lb["lb_lab_missing_fields"] = ";".join(r["missing"])
            built.append((r, lb))

        seen_groups, out_rows = set(), []
        for i, (r, lb) in enumerate(built, start=1):
            v = r["values"]
            ticker, side = str(v.get("ticker")).upper().strip(), str(v.get("direction") or "").upper().strip()
            group = f"{cell(v.get('sector_etf')) or 'NO_ETF'}_{side or 'NO_DIRECTION'}"
            head = {"lb_order": str(i), "lb_batch": str((i - 1) // int(settings["batch_size"]) + 1),
                    "lb_ledger_id": f"{session}_{ticker}_{side}", "lb_row_key": r["row_key"]}
            tail = {"lb_group": group, "lb_group_role": "ALTERNATE" if group in seen_groups else "PRIMARY"}
            seen_groups.add(group)
            out_rows.append({**head, **{f: cell(v.get(f)) for f in lab.fields}, **lb, **tail})

        # write (a refresh first keeps the previous set)
        archived = None
        if old_receipt:
            archived = archive_previous(folder, str(old_receipt.get("lab_revision") or "unknown"), old_receipt.get("lab_revision") == lab.revision)
        folder.mkdir(parents=True, exist_ok=True)
        columns = list(out_rows[0])
        with (folder / "handoff.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader(); writer.writerows(out_rows)
        with (folder / "handoff_evidence.jsonl").open("w", encoding="utf-8") as handle:
            for (r, _), o in zip(built, out_rows):
                handle.write(json.dumps({"ticker": o["ticker"], "row_key": r["row_key"], "lb_order": int(o["lb_order"]), "lb_batch": int(o["lb_batch"]),
                                         "lab_revision": lab.revision, "card": r["values"], "card_missing_fields": r["missing"],
                                         "card_extra": r["extra"], "evidence": evidence[r["row_key"]]}, ensure_ascii=False) + "\n")
        commands = folder / "pack_commands"
        if commands.exists():
            shutil.rmtree(commands)   # a generated subfolder of this hand-off; the previous one is already in _rev_
        commands.mkdir()
        batches: dict[str, list[str]] = {}
        for o in out_rows:
            batches.setdefault(o["lb_batch"], []).append(o["ticker"])
        for b, names in batches.items():
            (commands / f"ticker_pack_command_{b}.txt").write_text(
                f"# batch {b} of session {session} (Lab revision {lab.revision})\n"
                f"venv\\Scripts\\python.exe tools\\ticker_pack.py {' '.join(names)} --run {lab.run_id} --session {session}\n", encoding="utf-8")

        compare, compare_state = legacy_compare(session, Path(a.legacy_root), {str(r["values"].get("ticker")).upper(): r for r, _ in built})
        if compare:
            with (folder / "legacy_compare.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(compare[0]))
                writer.writeheader(); writer.writerows(compare)
        elif (folder / "legacy_compare.csv").exists():
            (folder / "legacy_compare.csv").unlink()

        flag_names = ["lab_verdict", "lb_window_flag", "lb_window_basis", "lb_time_fit", "lb_over_cap", "lb_saved_gate", "lb_stock_tier",
                      "lb_repair_conflict", "lb_group_role", "monetisation_state"]
        # "(blank)" not "": a JSON object with an empty key cannot be read by PowerShell 5.1 (avs_day.ps1 reads this receipt)
        flags = {n: dict(Counter(o.get(n, "") or "(blank)" for o in out_rows).most_common()) for n in flag_names}
        flags["lb_runway_note"] = {"TRIGGER_AGE_EXCEEDS_Q50": sum(1 for o in out_rows if o["lb_runway_note"]),
                                   "none": sum(1 for o in out_rows if not o["lb_runway_note"])}
        history = (old_receipt or {}).get("revision_history", [])
        if old_receipt:
            history = history + [{"lab_revision": old_receipt.get("lab_revision"), "built_at_utc": old_receipt.get("built_at_utc"),
                                  "kept_in": archived.name if archived else None}]
        receipt = {
            "version": VERSION, "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "session": session, "session_basis": session_basis, "run_id": lab.run_id,
            "lab_manifest": str(lab.manifest_file), "lab_revision": lab.revision, "lab_database_file": lab.database.name,
            "lab_database_sha256": lab.sha256, "lab_created_at_utc": manifest.get("created_at_utc"),
            "lab_source_created_at_utc": manifest.get("source_created_at_utc"), "lab_publication_state": manifest.get("publication_state"),
            "lab_publication_stage": publication_stage(manifest), "lab_source_issues": (manifest.get("source_receipt") or {}).get("issues", []),
            "evidence_families_copied": list(lab_reader.FAMILIES), "evidence_families_not_copied": ["audit"],
            "settings": settings, "monetisation_state": flags["monetisation_state"] and next(iter(flags["monetisation_state"])),
            "lab_fields_copied": len(lab.fields), "lab_fields_missing": missing_fields,
            "counts": {"lab_rows_in": len(all_rows), "handoff_rows": len(out_rows),
                       "handoff_by_verdict": dict(Counter(o["lab_verdict"] for o in out_rows)),
                       "excluded_by_verdict": dict(sorted(excluded.items())), "excluded_by_window_filter": dropped_window,
                       "batches": len(batches)},
            "flags": flags, "legacy_compare": compare_state,
            "legacy_compare_counts": dict(Counter(r["differs"] for r in compare)) if compare else {},
            "revision_history": history,
        }
        (folder / "receipt.json").write_text(json.dumps(receipt, indent=1), encoding="utf-8")
        write_markdown(folder, receipt, out_rows, settings)
        print(f"{VERSION}: session {session}, run {lab.run_id}, Lab revision {lab.revision} ({receipt['lab_publication_stage']})")
        print(f"  Lab rows {len(all_rows)} -> hand-off {len(out_rows)} in {len(batches)} batches; excluded by verdict {dict(sorted(excluded.items()))}"
              + (f"; by window filter {dropped_window}" if dropped_window else ""))
        if missing_fields:
            print(f"  Lab fields not published (written blank): {', '.join(missing_fields)}")
        print(f"  legacy compare: {compare_state}" + (f" {receipt['legacy_compare_counts']}" if compare else ""))
        print(f"  {folder}")
        if a.spotcheck:
            return 1 if spotcheck(folder, lab.fields, lab.run_id, lab.revision, a.api, Path(a.spotcheck), settings) else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
