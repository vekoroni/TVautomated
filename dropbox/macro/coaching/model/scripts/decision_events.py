#!/usr/bin/env python3
"""AVS-MODEL-001 step 0a: collect every decision since 12 Oct 2026 into one table, decision_events.

Research package only. Reads the hand-off folders and the decision ledgers; writes nothing outside
dropbox\\macro\\coaching\\model\\. Never opens trade_journal.db.

One row per ticker, side and session. Every source row is kept in decision_sources with its path, its row number and
its original values (raw_json), so the row counts reconcile with the source files.

Reused (imported, not copied) from data\\scratch\\workaround\\collect_decisions.py:
    OCC / first()      the contract-symbol finder (four different field names for the contract)
    find_cards()       the deep-dive HTML finder
Sources, in order of authority for the decision label: decision record (decisions\\<TICKER>.json) > triage row >
ledger row. A triaged name with no decision is NOT_MINED; a card with no decision is CARD_NO_DECISION; a name that
is only on the ledger is LEDGER_ONLY (it was never triaged, so it is not one of the brief's five decision types).
"""
from __future__ import annotations

import importlib.util
import json
import re
import sqlite3
from contextlib import closing
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

VERSION = "decision_events_v1"
REPO = Path(__file__).resolve().parents[5]
MODEL = Path(__file__).resolve().parents[1]
WORK = REPO / "data" / "scratch" / "workaround"
HANDOFF = WORK / "handoff"
OUT_DB = MODEL / "outcomes" / "decision_events.sqlite"
FIRST_SESSION = "2026-10-12"
DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
PACK = re.compile(r"_(CALL|PUT)\.json$")


sys.dont_write_bytecode = True      # importing the two reused scripts must not leave a cache file beside them


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


CD = load_module("avs_collect_decisions", WORK / "collect_decisions.py")


def rel(p: Path) -> str:
    return str(Path(p).resolve().relative_to(REPO)).replace("/", "\\")


def read_csv(p: Path) -> pd.DataFrame:
    # keep_default_na=False: the ticker NAN is a real ticker; blank stays blank (same rule as collect_decisions)
    return pd.read_csv(p, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def num(v):
    """A number, else None. Blank is None, never 0."""
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(str(v).replace(",", "").strip())
    except ValueError:
        return None
    return x if x == x else None


def occ(text) -> str:
    m = CD.OCC.search("" if text is None else str(text))
    return (m.group(1) + m.group(2)) if m else ""


def side_of(*values) -> str:
    for v in values:
        s = str(v or "").upper().strip()
        if s in ("CALL", "PUT"):
            return s
        if s.endswith("_CALL") or s.endswith("_PUT"):
            return s.rsplit("_", 1)[1]
    return ""


def session_of(*values) -> str:
    for v in values:
        m = DATE.match(str(v or ""))
        if m:
            return m.group(1)
    return ""


def norm_decision(raw: str) -> str:
    d = str(raw or "").upper().strip()
    if d.startswith(("TRADE", "ENTER")):
        return "TRADE"
    for k in ("WATCH", "MISSED", "PASS", "NOT_MINED"):
        if d.startswith(k):
            return k
    return ""


STOP_LEVEL = re.compile(r"(?:close[sd]?|closing)?\s*(?:above|below|over|under|>=|<=|>|<)\s*\$?(\d+(?:\.\d+)?)", re.I)


def card_stop_level(text):
    """The stock level in a card's stop sentence ("Daily close above 13.15 ...") when it is stated that way, else None."""
    text = str(text or "").strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", text):      # the stop written as the bare level ("59.01")
        return float(text)
    m = STOP_LEVEL.search(text)
    return float(m.group(1)) if m else None


class Collector:
    def __init__(self):
        self.events: dict[tuple, dict] = {}
        self.sources: list[dict] = []
        self.skipped: list[dict] = []
        self.files: list[dict] = []
        self.card_in_folder: dict[tuple, dict] = {}     # (hand-off folder, ticker) -> the event of that folder's decision record

    def event(self, session, ticker, side) -> dict:
        key = (session, ticker, side)
        if key not in self.events:
            self.events[key] = {"event_id": f"{session}|{ticker}|{side}", "decision_session": session, "ticker": ticker, "side": side,
                                "in_ledger": 0, "in_handoff": 0, "in_triage": 0, "in_card": 0, "source_paths": []}
        return self.events[key]

    def add_source(self, ev, kind, path, row, raw):
        p = rel(path)
        if p not in ev["source_paths"]:
            ev["source_paths"].append(p)
        self.sources.append({"event_id": ev["event_id"], "source_kind": kind, "source_path": p, "source_row": row,
                             "raw_json": json.dumps(raw, default=str, ensure_ascii=False)})

    def file(self, kind, path, rows, collected, note=""):
        self.files.append({"source_kind": kind, "source_path": rel(path), "rows_in_file": rows, "rows_collected": collected, "note": note})

    # ------------------------------------------------------------------ ledgers
    def ledgers(self):
        for f in sorted(WORK.glob("decision_ledger_????-??-??.csv")):
            d = read_csv(f)
            n = 0
            for i, r in enumerate(d.to_dict("records")):
                session, t, s = session_of(r.get("decision_session"), r.get("ledger_id")), r["ticker"].upper().strip(), side_of(r.get("side"))
                if session < FIRST_SESSION:
                    self.skipped.append({"path": rel(f), "row": i, "reason": "before 12 Oct 2026"})
                    continue
                ev = self.event(session, t, s)
                ev["in_ledger"] = 1
                ev.update({"ledger_id": r.get("ledger_id"), "ledger_decision_raw": r.get("decision", ""), "ledger_contract": occ(r.get("contract_symbol")),
                           "ledger_state": r.get("state"), "ledger_readiness": r.get("readiness"),
                           "ref_price_source": num(r.get("ref_price")), "trigger": num(r.get("trigger")), "atr": num(r.get("atr")),
                           "half_target": num(r.get("half_target")), "level": num(r.get("level")), "invalidation": num(r.get("invalidation")),
                           "practical_stop": num(r.get("practical_stop")), "levels_source": "ledger",
                           "feature_asof": r.get("evidence_as_of") or None, "feature_asof_basis": "ledger evidence_as_of",
                           "source_run": r.get("source_run")})
                self.add_source(ev, "ledger", f, i, r)
                n += 1
            self.file("ledger", f, len(d), n)

    # ------------------------------------------------------------------ hand-off lists (provenance and the hand-off contract)
    def handoffs(self):
        for folder in sorted(p for p in HANDOFF.iterdir() if p.is_dir()):
            f = folder / "handoff.csv"
            if not f.exists():
                continue
            d = read_csv(f)
            lab = folder.name.startswith("lab_")
            n = 0
            for i, r in enumerate(d.to_dict("records")):
                lid = r.get("lb_ledger_id") if lab else r.get("ledger_id")
                session = session_of(lid) or session_of(DATE.search(folder.name).group(1) if DATE.search(folder.name) else "")
                t, s = r["ticker"].upper().strip(), side_of(r.get("direction") if lab else r.get("side"), lid)
                if session < FIRST_SESSION:
                    self.skipped.append({"path": rel(f), "row": i, "reason": "before 12 Oct 2026"})
                    continue
                ev = self.event(session, t, s)
                ev["in_handoff"] = 1
                if lab:
                    ev.update({"lab_rank": num(r.get("lab_rank")), "lab_final_action": r.get("final_action"), "lab_verdict": r.get("lab_verdict"),
                               "lab_contract": occ(r.get("contract_symbol"))})
                    ev.setdefault("feature_asof", r.get("bar_data_asof") or None)
                    ev.setdefault("feature_asof_basis", "lab bar_data_asof")
                    if ev.get("half_target") is None and ev.get("level") is None:
                        ev.update({"level": num(r.get("anticipated_level")), "invalidation": num(r.get("invalidation_price")),
                                   "trigger": num(r.get("thesis_trigger_level")), "levels_source": "lab_handoff"})
                else:
                    ev["handoff_contract"] = occ(r.get("best_contract"))
                    ev["handoff_class"] = r.get("handoff_class")
                    if ev.get("half_target") is None and ev.get("level") is None:
                        ev.update({"half_target": num(r.get("half_target")), "level": num(r.get("level")), "invalidation": num(r.get("invalidation")),
                                   "trigger": num(r.get("trigger")), "ref_price_source": num(r.get("ref_price")), "levels_source": "handoff"})
                self.add_source(ev, "lab_handoff" if lab else "handoff", f, i, r)
                n += 1
            self.file("lab_handoff" if lab else "handoff", f, len(d), n)

    # ------------------------------------------------------------------ triage files
    def triage(self):
        files = sorted(set(HANDOFF.glob("*/batch*_triage_*.csv")) | set(HANDOFF.glob("*/triage_morning_*.csv")))
        for f in files:
            d = read_csv(f)
            file_session = session_of(DATE.search(f.name).group(1))
            n = 0
            for i, r in enumerate(d.to_dict("records")):
                session = session_of(r.get("ledger_id")) or file_session
                t, s = r["ticker"].upper().strip(), side_of(r.get("side"), r.get("ledger_id"))
                ev = self.event(session, t, s)
                contract = occ(r.get("contract_taken")) or occ(r.get("trade_contract")) or occ(r.get("best_contract_le5"))
                rank = num(r.get("deep_mine_rank"))
                if rank is None:
                    rank = num(r.get("carry_rank"))
                first_triage = not ev["in_triage"]
                ev["in_triage"] = 1
                if first_triage or (contract and not ev.get("triage_contract")):
                    ev.update({"triage_file": rel(f), "triage_rank": rank if rank is not None else ev.get("triage_rank"),
                               "triage_rank_basis": ("deep_mine_rank" if num(r.get("deep_mine_rank")) is not None else
                                                     "carry_rank" if rank is not None else "NOT_RANKED_IN_FILE"),
                               "triage_contract": contract, "triage_contract_text": r.get("trade_contract") or r.get("best_contract_le5") or r.get("best_contract_payoff") or "",
                               "triage_contract_quote_text": r.get("contract_quote") or next((r[k] for k in r if k.startswith("contract_quote_")), ""),
                               "triage_decision_raw": r.get("decision", ""), "triage_tier": r.get("tier", ""),
                               "ledger_id": ev.get("ledger_id") or r.get("ledger_id")})
                if r.get("decision", "").strip():
                    ev["triage_decision_raw"] = r["decision"]
                if ev.get("half_target") is None and ev.get("level") is None:
                    ev.update({"half_target": num(r.get("half_target")), "level": num(r.get("level")), "invalidation": num(r.get("invalidation")),
                               "trigger": num(r.get("trigger")), "levels_source": "triage"})
                self.add_source(ev, "triage", f, i, r)
                n += 1
            self.file("triage", f, len(d), n, "" if "deep_mine_rank" in d.columns else "no deep_mine_rank column")

    # ------------------------------------------------------------------ decision records, cards CSV and card HTML
    def lookup_side(self, session, ticker) -> str:
        found = [k[2] for k in self.events if k[0] == session and k[1] == ticker and k[2]]
        for flag in ("in_card", "in_triage", "in_handoff", "in_ledger"):
            hit = [s for s in found if self.events[(session, ticker, s)][flag]]
            if len(hit) == 1:
                return hit[0]
        return ""

    def decisions(self):
        for f in sorted(HANDOFF.glob("*/decisions/*.json")):
            folder = f.parent.parent
            try:
                j = json.loads(f.read_text(encoding="utf-8-sig"))
            except Exception as e:
                self.skipped.append({"path": rel(f), "row": 0, "reason": f"unreadable: {type(e).__name__}"})
                self.file("decision_record", f, 1, 0, "unreadable")
                continue
            if "decision" not in j and "state" not in j:
                self.skipped.append({"path": rel(f), "row": 0, "reason": "not a decision record (no decision or state field)"})
                self.file("decision_record", f, 1, 0, "not a decision record")
                continue
            t = str(j.get("ticker") or f.stem).upper().strip()
            folder_date = DATE.search(folder.name)
            session = session_of(j.get("ledger_id"), j.get("session"), folder_date.group(1) if folder_date else "")
            contract = CD.first(j, CD.CONTRACT_KEYS)
            s = side_of(j.get("card_side"), j.get("ledger_id"), j.get("handoff_side")) or self.lookup_side(session, t) \
                or ({"C": "CALL", "P": "PUT"}.get(contract[-9]) if contract else "") or "UNKNOWN"
            ev = self.event(session, t, s)
            ev["in_card"] = 1
            self.card_in_folder[(folder.name, t)] = ev
            targets = j.get("targets")
            targets = [x for x in (num(v) for v in targets) if x is not None] if isinstance(targets, list) else []
            fill = j.get("fill")
            real_fill = bool(isinstance(fill, dict) and any(fill.get(k) not in (None, "") for k in ("price", "quantity", "filled_at_utc")))
            ev.update({"card_decision_raw": "" if j.get("decision") is None else str(j.get("decision")),
                       "card_final_action": j.get("final_action") or "", "card_state": j.get("state") or "",
                       "card_side": j.get("card_side") or "", "handoff_side": j.get("handoff_side") or "",
                       "card_contract": contract, "card_limit": num(j.get("limit")), "card_max_pay": num(j.get("max_pay")),
                       "card_stop_text": "" if j.get("stop") is None else str(j.get("stop")), "card_stop_level": card_stop_level(j.get("stop")),
                       "card_targets_json": json.dumps(j.get("targets"), default=str), "card_target_first": targets[0] if targets else None,
                       "card_time_stop": "" if j.get("time_stop") is None else str(j.get("time_stop")),
                       "card_entry_type": "" if j.get("entry_type") is None else str(j.get("entry_type")),
                       "card_created_utc": j.get("created_utc") or j.get("written_utc") or "",
                       "card_updated_utc": j.get("updated_utc") or "", "card_artifact_url": j.get("artifact_url") or "",
                       "card_order_placed_raw": "" if j.get("order_placed") is None else str(j.get("order_placed")),
                       "real_fill_recorded": int(real_fill), "decision_record": rel(f),
                       "ledger_id": ev.get("ledger_id") or j.get("ledger_id")})
            self.add_source(ev, "decision_record", f, 0, j)
            self.file("decision_record", f, 1, 1)

    def cards_csv(self):
        for f in sorted(HANDOFF.glob("*/cards_*.csv")):
            d = read_csv(f)
            file_session = DATE.search(f.name).group(1)
            n = 0
            for i, r in enumerate(d.to_dict("records")):
                t = r["ticker"].upper().strip()
                session = session_of(r.get("ledger_id")) or file_session
                s = side_of(r.get("handoff_side"), r.get("ledger_id"), r.get("card_side")) or self.lookup_side(session, t) or "UNKNOWN"
                ev = self.event(session, t, s)
                ev["cards_csv_status"] = r.get("status", "")
                if r.get("decision", "").strip() and not ev.get("card_decision_raw"):
                    ev["cards_csv_decision_raw"] = r["decision"]
                    ev["cards_csv_contract"] = occ(r.get("contract"))
                self.add_source(ev, "cards_csv", f, i, r)
                n += 1
            self.file("cards_csv", f, len(d), n, "derived by collect_decisions.py from the triage file and the decision records")

    def card_html(self):
        for folder in sorted(p for p in HANDOFF.iterdir() if p.is_dir()):
            for t, files in sorted(CD.find_cards(folder).items()):
                for f in files:
                    d = DATE.search(f.name)
                    session = d.group(1) if d else (DATE.search(folder.name).group(1) if DATE.search(folder.name) else "")
                    # a folder's decision record covers every version of that ticker's card kept in the folder (as collect_decisions reads it)
                    ev = self.card_in_folder.get((folder.name, t)) or self.event(session, t, self.lookup_side(session, t) or "UNKNOWN")
                    ev["card_html_count"] = ev.get("card_html_count", 0) + 1
                    ev["has_card_html"] = 1
                    self.add_source(ev, "card_html", f, 0, {"file": f.name, "folder": folder.name, "bytes": f.stat().st_size})
                    self.file("card_html", f, 1, 1)

    # ------------------------------------------------------------------ finish
    def finish(self):
        for ev in self.events.values():
            card, tri, led = norm_decision(ev.get("card_decision_raw")), norm_decision(ev.get("triage_decision_raw")), norm_decision(ev.get("ledger_decision_raw"))
            csvd = norm_decision(ev.get("cards_csv_decision_raw"))
            if card:
                dec, basis = card, "decision_record"
            elif csvd:
                dec, basis = csvd, "cards_csv"
            elif tri:
                dec, basis = tri, "triage"
            elif led:
                dec, basis = led, "ledger"
            elif ev["in_card"] or ev.get("has_card_html"):
                dec, basis = "CARD_NO_DECISION", "card without a decision"
            elif ev["in_triage"]:
                dec, basis = "NOT_MINED", "triaged, no card and no decision"
            else:
                dec, basis = "LEDGER_ONLY", "on the ledger or hand-off list only"
            ev["decision"], ev["decision_basis"] = dec, basis
            # the contract to score: the exact symbol named on the card, else on the triage row (brief 0b)
            for name, src in (("card_contract", "card"), ("cards_csv_contract", "cards_csv"), ("triage_contract", "triage"), ("ledger_contract", "ledger")):
                if ev.get(name):
                    ev["contract_scored"], ev["contract_source"] = ev[name], src
                    break
            else:
                ev["contract_scored"], ev["contract_source"] = "", "NO_CONTRACT_NAMED"
            # the stock target and stop used for first touch: the card's when it states them as stock levels, else the half target and invalidation
            ev["target_used"] = ev.get("card_target_first") if ev.get("card_target_first") is not None else ev.get("half_target")
            ev["target_basis"] = "card targets[0]" if ev.get("card_target_first") is not None else ("half_target" if ev.get("half_target") is not None else "")
            ev["stop_used"] = ev.get("card_stop_level") if ev.get("card_stop_level") is not None else ev.get("invalidation")
            ev["stop_basis"] = "card stop level" if ev.get("card_stop_level") is not None else ("invalidation" if ev.get("invalidation") is not None else "")
            # point in time: the decision is dated to its session; the card's own timestamp is kept when it has one
            ev["decision_ts"] = ev.get("card_created_utc") or ev["decision_session"]
            ev["decision_ts_basis"] = "card created_utc" if ev.get("card_created_utc") else "decision session date"
            ev["source_paths"] = json.dumps(ev["source_paths"])


def collect() -> Collector:
    c = Collector()
    c.ledgers()
    c.handoffs()
    c.triage()
    c.decisions()
    c.cards_csv()
    c.card_html()
    c.finish()
    return c


def not_collected() -> list[dict]:
    """Files in the hand-off folders that are not decision sources, by kind, so nothing is dropped silently."""
    out = []
    for folder in sorted(p for p in HANDOFF.iterdir() if p.is_dir()):
        kinds: dict[str, int] = {}
        for f in folder.rglob("*"):
            if not f.is_file():
                continue
            relp = f.relative_to(folder)
            top = relp.parts[0]
            if top.startswith("_rev_"):
                k = "earlier Lab hand-off revision (copy)"
            elif top in ("pack_commands", "screenshots"):
                k = top
            elif PACK.search(f.name):
                k = "ticker evidence pack (<TICKER>_<SIDE>.json)"
            elif f.name == "handoff.csv" or top == "decisions" or "_deep_dive_" in f.name and f.suffix == ".html" \
                    or re.match(r"(batch\d+_triage_|triage_morning_|cards_)", f.name):
                continue
            else:
                k = re.sub(r"\d{4}-\d{2}-\d{2}", "<date>", re.sub(r"^[A-Z]+_daily", "<TICKER>_daily", f.name))
            kinds[k] = kinds.get(k, 0) + 1
        out += [{"folder": folder.name, "kind": k, "files": n} for k, n in sorted(kinds.items())]
    return out


EVENT_COLS = ["event_id", "decision_session", "ticker", "side", "decision", "decision_basis", "in_ledger", "in_handoff", "in_triage", "in_card",
              "has_card_html", "card_html_count", "ledger_id", "source_run", "triage_file", "triage_rank", "triage_rank_basis", "triage_tier",
              "contract_scored", "contract_source", "card_contract", "cards_csv_contract", "triage_contract", "triage_contract_text",
              "triage_contract_quote_text", "ledger_contract", "handoff_contract", "lab_contract", "lab_rank", "lab_final_action", "lab_verdict",
              "handoff_class", "ledger_state", "ledger_readiness", "ref_price_source", "trigger", "atr", "half_target", "level", "invalidation",
              "practical_stop", "levels_source", "target_used", "target_basis", "stop_used", "stop_basis",
              "card_decision_raw", "card_final_action", "card_state", "card_side", "handoff_side", "card_limit", "card_max_pay", "card_stop_text",
              "card_stop_level", "card_targets_json", "card_target_first", "card_time_stop", "card_entry_type", "card_created_utc", "card_updated_utc",
              "card_artifact_url", "card_order_placed_raw", "real_fill_recorded", "decision_record", "cards_csv_status", "cards_csv_decision_raw",
              "triage_decision_raw", "ledger_decision_raw", "decision_ts", "decision_ts_basis", "feature_asof", "feature_asof_basis", "source_paths"]


def write(c: Collector, db: Path = OUT_DB) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db)) as con, con:
        con.execute("PRAGMA journal_mode=DELETE")
        for t in ("decision_events", "decision_sources", "source_files", "skipped_rows", "not_collected"):
            con.execute(f"DROP TABLE IF EXISTS {t}")
        ev = pd.DataFrame([{k: e.get(k) for k in EVENT_COLS} for e in c.events.values()])
        ev["collected_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        ev["collector_version"] = VERSION
        ev.to_sql("decision_events", con, index=False)
        con.execute("CREATE UNIQUE INDEX ix_events ON decision_events(event_id)")
        pd.DataFrame(c.sources).to_sql("decision_sources", con, index=False)
        con.execute("CREATE INDEX ix_sources ON decision_sources(event_id)")
        pd.DataFrame(c.files).to_sql("source_files", con, index=False)
        pd.DataFrame(c.skipped or [{"path": None, "row": None, "reason": None}]).dropna(how="all").to_sql("skipped_rows", con, index=False)
        pd.DataFrame(not_collected()).to_sql("not_collected", con, index=False)


def main():
    c = collect()
    write(c)
    ev = pd.DataFrame(list(c.events.values()))
    print(f"{VERSION}: {len(ev)} decision events, {len(c.sources)} source rows, {len(c.files)} source files -> {OUT_DB}")
    print(ev.groupby(["decision_session", "decision"]).size().unstack(fill_value=0).to_string())


if __name__ == "__main__":
    main()
