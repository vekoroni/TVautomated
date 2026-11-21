"""Board macro context for each Lane B hand-off name (AVS-MACRO-TRIAGE-001 T2, approved by ACK 20 Nov 2026).

Joins the hand-off (handoff.csv, keyed by lb_ledger_id) to the board's latest per-ETF intelligence
(etf_intelligence_latest.json, T1) and writes triage_macro_context_<session>.csv and .json into the hand-off
folder. The triage chats fill their macro columns from these rows instead of writing macro text by hand.

Rules (CLAUDE.md rule 6): the Lab rank, side and contract are copied, never changed; macro_view_order is display
only and never replaces lab_rank or deep_mine_rank. money_tag: measured and packet agree -> that word; they disagree
-> MIXED (ACK 20 Nov 2026, decision 1); one missing -> the other with a note; a stock-specific name -> MIXED with a
note. Relative performance is called that, never a fund flow. Missing is never neutral.

    venv\\Scripts\\python.exe -m macro_board.triage_context --handoff data\\scratch\\workaround\\handoff\\lab_<session>
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Callable, Mapping, Sequence

import pandas as pd

from macro_board.day_story import candidate_links

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INTEL = ROOT / "macro_board" / "output" / "etf_intelligence" / "etf_intelligence_latest.json"
DEFAULT_CONFIG = ROOT / "macro_board" / "config" / "macro_board_config_v1.json"
DEFAULT_HANDOFF_ROOT = ROOT / "data" / "scratch" / "workaround" / "handoff"
VERSION = "triage_macro_context_v1"
AUTHORITY = ("Board intelligence for the human triage (CLAUDE.md rule 6). Copied Lab fields are unchanged; "
             "macro_view_order is display only. It never changes a gate, score, lab_rank, contract, side or size.")
MEASURED_FIT = {"WITH_FLOW": "WITH", "AGAINST_FLOW": "AGAINST", "STOCK_SPECIFIC": "MIXED", "NO_FLOW_READ": "NEUTRAL"}
VIEW_ORDER = {"WITH": 0, "MIXED": 1, "AGAINST": 2}
COLUMNS = ["session", "ledger_id", "ticker", "side", "lab_rank", "lb_batch", "lb_order", "contract_symbol",
           "sector_etf", "board_as_of_session", "board_build_kind", "board_built_at_utc", "board_session_note",
           "link_corr_60d", "link_beta_60d", "link_state", "side_fit_measured", "side_fit_packet", "money_tag",
           "money_why", "macro_sector_agreement", "macro_scenario_ids", "macro_kill_switch", "sector_check",
           "reasons_for", "reasons_against", "echo_note", "events_next_close", "macro_view_order",
           # T7 (ACK 20 Nov 2026): peer reference beside SPY, the event file's view and the USMI routing, labelled
           "peer_reference", "peer_relative_label", "benchmark_split", "event_sector_view", "usmi_routing"]


class ContextError(RuntimeError):
    """The join cannot run; nothing is written."""


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _blank(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x)) or str(x).strip() in ("", "nan", "None")


def side_fit_packet(stance: str, side: str) -> str:
    if stance in ("NONE", None):
        return "NO_READ"
    if stance in ("NEUTRAL", "CONFLICTED"):
        return "MIXED"
    want = "CALL" if stance == "LEAN_IN" else "PUT"
    return "WITH" if side == want else "AGAINST"


def money_tag(measured_fit: str | None, packet_fit: str) -> tuple[str, str]:
    """(tag, note). measured_fit is WITH / AGAINST / MIXED (stock-specific) / NEUTRAL (no edge) / None (missing)."""
    if measured_fit is None and packet_fit == "NO_READ":
        return "NO_READ", "measured read missing and packet silent"
    if measured_fit is None:
        return packet_fit, "measured read missing: packet only (LLM)"
    if measured_fit == "MIXED":
        return "MIXED", "stock-specific: the sector read carries little"
    if measured_fit == "NEUTRAL":
        return "MIXED", "measured shows no clear edge for the sector" + ("; packet silent" if packet_fit == "NO_READ" else "")
    if packet_fit == "NO_READ":
        return measured_fit, "packet silent: measured only"
    if packet_fit == "MIXED":
        return "MIXED", "packet neutral or self-conflicted; measured leans " + measured_fit
    if measured_fit == packet_fit:
        return measured_fit, "measured and packet agree (not independent: the packet reads our sheet)"
    return "MIXED", "measured and packet differ"


def _kill_text(etf: str, e: Mapping, board: str) -> str:
    kill, stance = e.get("kill_level"), e.get("stance_measured")
    if not kill or stance not in ("LEAN_IN", "AVOID"):
        why = e.get("missing_reason") or ("no clear relative-performance read" if stance == "NEUTRAL" else "no level")
        return f"no measured kill level on {etf}: {why} ({board})"
    side = "above" if stance == "AVOID" else "below"
    return (f"measured {stance.replace('_', ' ')} on {etf} void {side} {float(kill['level']):.2f} "
            f"({kill.get('name')}; {board})")


def _scenario_text(e: Mapping) -> str:
    live = [f"{x['id']} {x['state']} {x.get('side') or ''} ({x.get('verdict') or 'no record'})".replace("  ", " ")
            for x in e.get("live_scenarios") or []]
    decision = [s["kind"] for s in e.get("decision_scenarios") or [] if s.get("applies")]
    return ("live: " + ("; ".join(live) if live else "none") + " | decision scenarios: "
            + (", ".join(decision) if decision else "none"))


def _ratio(x) -> str:
    v = _num(x)
    return "MISSING" if v is None else f"{v:.2f}x"


def _reasons(items: Sequence[Mapping]) -> str:
    return "; ".join(f"[{r['source']}] {r['text']}" for r in items or []) or "none"


def _t7_columns(e: Mapping | None) -> dict:
    """T7: the peer reference, the split against SPY, the event file's view and the USMI routing for the name's ETF.
    A file built before T7 gives MISSING, never blank."""
    if not e:
        return {k: "MISSING" for k in ("peer_reference", "peer_relative_label", "benchmark_split", "event_sector_view",
                                       "usmi_routing")}
    bench = e.get("benchmarks")
    peer = (bench.get("peer") or {}) if isinstance(bench, Mapping) else {}
    split = bench.get("split") if isinstance(bench, Mapping) else None
    view, routing = e.get("event_sector_view", "MISSING"), e.get("usmi_routing", "MISSING")
    return {"peer_reference": peer.get("reference") or (split if split in ("NO_PEER", "NO_READ", "DERIVED") else "MISSING"),
            "peer_relative_label": peer.get("label") or (split or "MISSING"),
            "benchmark_split": split or "MISSING",
            "event_sector_view": ("; ".join(f"{v.get('view')} ({v.get('condition')}) [{v.get('source')}]" for v in view)
                                  if isinstance(view, list) else str(view)),
            "usmi_routing": ("; ".join(f"{r.get('sector')}: {r.get('routing')} [{r.get('source')}]" for r in routing)
                             if isinstance(routing, list) else str(routing))}


def build_rows(handoff: pd.DataFrame, intel: Mapping, links: Mapping[str, Mapping], cfg: Mapping, *,
               session: str) -> list[dict]:
    meta = intel["meta"]
    etfs = intel.get("etfs") or {}
    board = f"{meta.get('build_kind')} build {meta.get('built_at_utc')}"
    built_for = str(meta.get("next_session"))
    note = ("MATCH" if built_for == str(session) else
            f"{'OLDER' if built_for < str(session) else 'NEWER'}_BUILD: board built for {built_for}, "
            f"hand-off session {session}")
    events = "; ".join(f"{e.get('name')} {e.get('time_et') or ''}".strip() for e in intel.get("events_next_close") or []) or "none"
    flows = {t: (e.get("relative_performance") or {}).get("label") or "MISSING" for t, e in etfs.items()}
    min_corr = float(cfg["min_link_corr"])
    rows = []
    for _, h in handoff.iterrows():
        ticker, side = str(h["ticker"]), str(h.get("direction") or "").upper()
        etf = None if _blank(h.get("sector_etf")) else str(h["sector_etf"])
        link = links.get(ticker) or {}
        corr, beta = _num(link.get("corr")), _num(link.get("beta"))
        e = etfs.get(etf) if etf else None
        self_etf = etf is not None and etf == ticker  # T7: the name is its own sector ETF (SPY, TLT, GLD, ...)
        if self_etf:
            corr, beta = None, None
        link_state = ("SELF" if self_etf else "MISSING" if corr is None else
                      "LINKED" if abs(corr) >= min_corr else "WEAK")
        if side not in ("CALL", "PUT"):
            fit_m, fit_p = "NO_SIDE", "NO_SIDE"
        elif etf is None:
            fit_m, fit_p = "NO_SECTOR", "NO_READ"
        elif e is None or e.get("stance_measured") == "MISSING":
            fit_m = "NO_BOARD_READ"
            fit_p = side_fit_packet(e.get("stance_packet") if e else None, side)
        elif corr is None and not self_etf:
            fit_m, fit_p = "LINK_MISSING", side_fit_packet(e.get("stance_packet"), side)
        else:
            rel = candidate_links([{"ticker": ticker, "direction": side, "sector_etf": etf,
                                    "link_corr": 1.0 if self_etf else corr}],
                                  flows, min_link_corr=min_corr)[etf][0]["relation"]
            fit_m, fit_p = rel, side_fit_packet(e.get("stance_packet"), side)
        if side not in ("CALL", "PUT"):
            tag, why = "NO_SIDE", f"side {side or 'blank'}: no side to read against the sector"
        else:
            tag, tag_note = money_tag(MEASURED_FIT.get(fit_m), fit_p)
            measured = (f"{etf} {flows.get(etf, 'MISSING')} -> {fit_m}" if etf else "no sector ETF")
            link_txt = ("link SELF (the name is its own sector ETF)" if self_etf else
                        f"link corr {corr:+.2f} ({link_state})" if corr is not None else f"link {link_state}")
            why = (f"{tag_note}. Measured relative performance ({board}): {measured} for a {side.lower()}, "
                   f"{link_txt}. Packet (LLM): {(e or {}).get('stance_packet', 'NONE')} -> {fit_p}.")
        rows.append({
            "session": session, "ledger_id": h["lb_ledger_id"], "ticker": h["ticker"], "side": h.get("direction"),
            "lab_rank": h.get("lab_rank"), "lb_batch": h.get("lb_batch"), "lb_order": h.get("lb_order"),
            "contract_symbol": h.get("contract_symbol"),
            "sector_etf": etf or "MISSING", "board_as_of_session": meta.get("as_of_session"),
            "board_build_kind": meta.get("build_kind"), "board_built_at_utc": meta.get("built_at_utc"),
            "board_session_note": note,
            "link_corr_60d": corr, "link_beta_60d": beta, "link_state": link_state,
            "side_fit_measured": fit_m, "side_fit_packet": fit_p, "money_tag": tag, "money_why": why,
            "macro_sector_agreement": (f"{e.get('stance_agreement')}: measured {e.get('stance_measured')} (MEASURED), "
                                       f"packet {e.get('stance_packet')} (LLM macro packet)") if e else
                                      ("NO_SECTOR" if etf is None else f"MISSING: {etf} not in the board intelligence"),
            "macro_scenario_ids": _scenario_text(e) if e else "none",
            "macro_kill_switch": _kill_text(etf, e, board) if e else "no board read",
            "sector_check": (f"{etf}: {(e.get('relative_performance') or {}).get('text') or e.get('missing_reason')} "
                             f"Volume {_ratio(e.get('volume_ratio'))} its normal. Record: {e.get('record')}. {board}.")
                            if e else "no board read",
            "reasons_for": _reasons(e.get("reasons_for")) if e else "none",
            "reasons_against": _reasons(e.get("reasons_against")) if e else "none",
            "echo_note": e.get("echo_note") if e else "",
            "events_next_close": events,
            **_t7_columns(e),
        })
    order = sorted(range(len(rows)), key=lambda i: (VIEW_ORDER.get(rows[i]["money_tag"], 3),
                                                    _num(rows[i]["lab_rank"]) if _num(rows[i]["lab_rank"]) is not None
                                                    else math.inf, _num(rows[i]["lb_order"]) or 0))
    for pos, i in enumerate(order, start=1):
        rows[i]["macro_view_order"] = pos
    return rows


def links_from_store(price_db: Path, window: int) -> Callable:
    """Reader of each stock's daily-return link to its sector ETF from the price store (money_index.beta_corr),
    bars up to the board's session."""
    from macro_board import sources as src
    from macro_board.money_index import beta_corr

    def read(pairs: Mapping[str, str], end: str) -> dict:
        tickers = sorted(set(pairs) | {e for e in pairs.values() if e})
        start = (pd.Timestamp(end) - pd.Timedelta(days=int(window * 1.6) + 30)).date().isoformat()
        _, closes, _ = src.load_prices(price_db, tickers, start)
        closes = closes[closes.index <= pd.Timestamp(end)]
        out = {}
        for t, etf in pairs.items():
            if etf and t in closes.columns and etf in closes.columns:
                out[t] = beta_corr(closes[t], closes[etf], window=window)
            else:
                out[t] = {"beta": None, "corr": None, "n": 0}
        return out
    return read


def _atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _changes(csv_path: Path, json_path: Path, rows: Sequence[Mapping]) -> tuple[int | None, str | None]:
    """How many names' money_tag differ from the file this run replaces (None when there is no previous file)."""
    if not csv_path.exists():
        return None, None
    try:
        old = pd.read_csv(csv_path, usecols=["ledger_id", "money_tag"], dtype=str)
        built = json.loads(json_path.read_text(encoding="utf-8")).get("board", {}).get("built_at_utc") \
            if json_path.exists() else None
    except (OSError, ValueError, KeyError):
        return None, None
    before = dict(zip(old["ledger_id"], old["money_tag"]))
    return sum(1 for r in rows if str(r["ledger_id"]) in before and before[str(r["ledger_id"])] != r["money_tag"]), built


def refresh_next_session(handoff_root: Path, intel_path: Path, cfg: Mapping, *, link_reader: Callable) -> dict:
    """After a board build (Run-MacroInputs.ps1): refresh the join for the hand-off of the board's next session,
    or say why it was skipped. The pre-open build (12:00 UK) finds that morning's hand-off (from about 10:40 UK)."""
    intel_path = Path(intel_path)
    if not intel_path.exists():
        raise ContextError(f"board intelligence file not found: {intel_path}; nothing written")
    session = json.loads(intel_path.read_text(encoding="utf-8"))["meta"].get("next_session")
    folder = Path(handoff_root) / f"lab_{session}"
    if not (folder / "handoff.csv").exists():
        return {"skipped": f"no hand-off for {session} yet ({folder}); the packs step builds the context later"}
    return run(folder, intel_path, cfg, link_reader=link_reader)


def run(handoff_dir: Path, intel_path: Path, cfg: Mapping, *, link_reader: Callable) -> dict:
    handoff_dir, intel_path = Path(handoff_dir), Path(intel_path)
    if not (handoff_dir / "handoff.csv").exists():
        raise ContextError(f"handoff.csv not found in {handoff_dir}; nothing written")
    if not intel_path.exists():
        raise ContextError(f"board intelligence file not found: {intel_path}; run a board build first. Nothing written")
    try:
        intel = json.loads(intel_path.read_text(encoding="utf-8"))
        receipt = json.loads((handoff_dir / "receipt.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ContextError(f"cannot read the inputs ({type(exc).__name__}: {exc}); nothing written") from exc
    session = str(receipt["session"])
    handoff = pd.read_csv(handoff_dir / "handoff.csv", low_memory=False,
                          dtype={"lb_ledger_id": str, "ticker": str, "contract_symbol": str})
    if handoff["lb_ledger_id"].isna().any() or not handoff["lb_ledger_id"].is_unique:
        raise ContextError("hand-off ledger ids are blank or repeated; nothing written")
    pairs = {str(t): (None if _blank(e) else str(e)) for t, e in zip(handoff["ticker"], handoff["sector_etf"])}
    links = link_reader(pairs, str(intel["meta"]["as_of_session"]))
    rows = build_rows(handoff, intel, links, cfg, session=session)
    frame = pd.DataFrame(rows, columns=COLUMNS)
    csv_path = handoff_dir / f"triage_macro_context_{session}.csv"
    json_path = handoff_dir / f"triage_macro_context_{session}.json"
    changed, previous_built = _changes(csv_path, json_path, rows)
    sectors = {t: {k: e.get(k) for k in ("stance_measured", "stance_packet", "stance_agreement", "record")}
               | {"relative_performance": (e.get("relative_performance") or {}).get("text"),
                  "kill_switch": _kill_text(t, e, f"{intel['meta'].get('build_kind')} build")}
               for t, e in (intel.get("etfs") or {}).items()}
    meta = {"version": VERSION, "session": session, "rows": len(rows),
            "handoff": {"folder": str(handoff_dir), "built_at_utc": receipt.get("built_at_utc"),
                        "run_id": receipt.get("run_id")},
            "board": {k: intel["meta"].get(k) for k in ("version", "as_of_session", "build_kind", "built_at_utc",
                                                         "next_session")},
            "board_session_note": rows[0]["board_session_note"] if rows else None,
            "changed_money_tag": changed, "previous_board_built_at_utc": previous_built,
            "counts": {"money_tag": dict(Counter(r["money_tag"] for r in rows)),
                       "side_fit_measured": dict(Counter(r["side_fit_measured"] for r in rows)),
                       "link_state": dict(Counter(r["link_state"] for r in rows))},
            "events_next_close": intel.get("events_next_close") or [],
            "sectors": sectors, "csv": csv_path.name, "authority": AUTHORITY,
            # T7: market-wide blocks for the merge (LLM_WITH_NEWS, with their as-of time)
            "event_intelligence": intel.get("event_intelligence") or {"status": "MISSING",
                                                                      "reason": "board file built before T7"},
            "usmi_intelligence": intel.get("usmi_intelligence") or {"status": "MISSING",
                                                                    "reason": "board file built before T7"}}
    tmp_csv = csv_path.with_name(csv_path.name + ".tmp")
    frame.to_csv(tmp_csv, index=False)
    os.replace(tmp_csv, csv_path)
    _atomic(json_path, json.dumps(meta, indent=1, default=str))
    return {"csv": csv_path, "json": json_path, "meta": meta}


IMPACT_FIELDS = ["batch", "deep_mine_rank", "ticker", "ledger_id", "side", "sector_etf", "link_corr_60d", "link_state",
                 "side_fit_measured", "side_fit_packet", "money_tag", "money_why", "macro_sector_agreement",
                 "macro_kill_switch", "macro_scenario_ids", "card"]


def _rank_key(v) -> float:
    m = re.match(r"\s*(\d+)", str(v or ""))
    return float(m.group(1)) if m else math.inf


def _card(folder: Path, ticker: str, session: str, board_dir: Path) -> str | None:
    """The name's deep-dive card in the hand-off folder (plain file first, else the newest version), as a path
    relative to the board HTML so it opens from the board."""
    plain = folder / f"{ticker}_deep_dive_{session}.html"
    found = plain if plain.exists() else max(folder.glob(f"{ticker}_deep_dive_{session}*.html"),
                                             key=lambda p: p.stat().st_mtime, default=None)
    if found is None:
        return None
    try:
        return os.path.relpath(found, board_dir).replace("\\", "/")
    except ValueError:                                     # another drive: an absolute file link
        return found.resolve().as_uri()


def board_ticker_impact(intel: Mapping, handoff_root: Path, cfg: Mapping, *, link_reader: Callable,
                        board_dir: Path) -> dict:
    """AVS-MACRO-TRIAGE-001 T6: the Day story's ticker impact for the board's next session. TRIAGE = the names on
    that session's batch triage files, by batch and deep_mine_rank; HANDOFF_NOT_TRIAGED = the first max_batches
    hand-off batches before the triage runs; NO_HANDOFF = the board keeps the pipeline candidates; FAILED = the reason.
    Each row is this build's macro reading of the name (build_rows). Display only."""
    meta = intel.get("meta") or {}
    session = str(meta.get("next_session"))
    folder = Path(handoff_root) / f"lab_{session}"
    base = {"session": session, "folder": str(folder), "board_built_at_utc": meta.get("built_at_utc"),
            "board_build_kind": meta.get("build_kind"), "rows": [], "counts": {}}
    if not (folder / "handoff.csv").exists():
        return {**base, "status": "NO_HANDOFF",
                "note": f"no Lane B hand-off for {session} yet: the pipeline candidates are shown instead"}
    try:
        handoff = pd.read_csv(folder / "handoff.csv", low_memory=False,
                              dtype={"lb_ledger_id": str, "ticker": str, "contract_symbol": str})
        triaged = []
        for f in sorted(folder.glob(f"batch*_triage_{session}.csv")):
            m = re.match(r"batch(\d+)_triage_", f.name)
            t = pd.read_csv(f, dtype=str, keep_default_na=False)
            for r in t.to_dict("records"):
                triaged.append({"batch": int(m.group(1)), "deep_mine_rank": r.get("deep_mine_rank", ""),
                                "ticker": str(r.get("ticker", "")).upper().strip(), "ledger_id": r.get("ledger_id", "")})
        if triaged:
            status = "TRIAGE"
            triaged.sort(key=lambda r: (r["batch"], _rank_key(r["deep_mine_rank"])))
            by_ledger = handoff.set_index("lb_ledger_id", drop=False)
            keep = [r for r in triaged if r["ledger_id"] in by_ledger.index]
            sub = by_ledger.loc[[r["ledger_id"] for r in keep]].reset_index(drop=True)
            extra = {r["ledger_id"]: r for r in keep}
            missing = len(triaged) - len(keep)
        else:
            status = "HANDOFF_NOT_TRIAGED"
            sub = handoff[pd.to_numeric(handoff["lb_batch"], errors="coerce") <= int(cfg["max_batches"])].reset_index(drop=True)
            extra = {lid: {"batch": int(b), "deep_mine_rank": ""} for lid, b in zip(sub["lb_ledger_id"], sub["lb_batch"])}
            missing = 0
        pairs = {str(t): (None if _blank(e) else str(e)) for t, e in zip(sub["ticker"], sub["sector_etf"])}
        rows = build_rows(sub, intel, link_reader(pairs, str(meta.get("as_of_session"))), cfg, session=session)
    except Exception as exc:  # noqa: BLE001 - the board must still build; say why the triage view is missing
        return {**base, "status": "FAILED", "note": f"{type(exc).__name__}: {exc}"}
    out_rows = []
    for r in rows:
        e = extra[str(r["ledger_id"])]
        out_rows.append({k: r.get(k) for k in IMPACT_FIELDS} | {"batch": e["batch"], "deep_mine_rank": e["deep_mine_rank"],
                        "card": _card(folder, str(r["ticker"]), session, Path(board_dir))})
    note = ("names on the batch triage files" if status == "TRIAGE" else
            f"hand-off batches 1-{int(cfg['max_batches'])}, not triaged yet")
    if missing:
        note += f"; {missing} triage rows whose ledger_id is not in the hand-off are left out"
    return {**base, "status": status, "note": note, "rows": out_rows,
            "counts": {"money_tag": dict(Counter(r["money_tag"] for r in out_rows))}}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Board macro context for each Lane B hand-off name (read-only on inputs).")
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--handoff", help="hand-off folder holding handoff.csv and receipt.json")
    where.add_argument("--next-session", action="store_true",
                       help="the hand-off of the board's next session under --handoff-root; skipped (exit 0) if none yet")
    parser.add_argument("--handoff-root", default=str(DEFAULT_HANDOFF_ROOT))
    parser.add_argument("--intelligence", default=str(DEFAULT_INTEL))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    from macro_board import sources as src
    cfg = {"min_link_corr": float(config["session_plan"]["min_link_corr"]),
           "corr_window_sessions": int(config["money_index"]["corr_window_sessions"])}
    reader = links_from_store(src.resolve(config["sources"]["price_db"]), cfg["corr_window_sessions"])
    try:
        if args.next_session:
            out = refresh_next_session(Path(args.handoff_root), Path(args.intelligence), cfg, link_reader=reader)
        else:
            out = run(Path(args.handoff), Path(args.intelligence), cfg, link_reader=reader)
    except ContextError as exc:
        print(f"[macro context] NOT WRITTEN: {exc}")
        return 2
    if out.get("skipped"):
        print(f"[macro context] skipped: {out['skipped']}")
        return 0
    m = out["meta"]
    print(f"[macro context] {m['rows']} names, board {m['board']['build_kind']} {m['board']['built_at_utc']} "
          f"({m['board_session_note']}); money_tag {m['counts']['money_tag']} -> {out['csv']}")
    if m["changed_money_tag"] is not None:
        print(f"[macro context] refreshed: {m['changed_money_tag']} names changed money_tag since the build of "
              f"{m['previous_board_built_at_utc']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
