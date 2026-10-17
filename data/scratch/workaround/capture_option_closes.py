#!/usr/bin/env python3
"""RETIRED 17 Oct 2026 (ACK): the post-close monitor is the one writer of monitor\\option_closes.csv. This script is no
longer run by avs_day.ps1 eod, and main() refuses to write unless --run-retired is given. Its rules stay as the
reference for the monitor's capture (tests/test_g5_capture_option_closes.py): held contracts with no age limit
(UAT-01), exchange-session closes only from quotes stamped at/after the close (UAT-02), retries of missing quotes (UAT-03).

Daily option close capture (v2, 17 Oct 2026; G5 minimal item 4 + UAT-01/02/03 fixes; v1 in prev\\).

After the close, record the closing quote of every contract named by a TRADE / WATCH / ENTER card in the last 10
hand-off sessions, and of every contract still held (whatever the age of its card, until the card records it closed),
so predicted option prices can be checked against what the market actually paid. Local only: no Claude credits; about
one MarketData credit per contract.

Run from the repo root (avs_day.ps1 eod does this after 21:00 UK):
    venv\\Scripts\\python.exe data\\scratch\\workaround\\capture_option_closes.py
Writes only verified session closes to data\\scratch\\workaround\\monitor\\option_closes.csv (existing columns):
  - the session is the XNYS session that has closed (exchange calendar, early closes included), never the wall clock;
    a weekend or holiday captures nothing;
  - a quote counts as that session's close only if it is stamped on that session, at or after its close;
    stale (an earlier day) and intraday quotes go to monitor\\option_quotes_unverified.csv with the reason;
  - a contract with no quote is written with quote_time_utc = NO_QUOTE:<reason> and is retried on the next run for the
    same session; a verified close is never written twice (UAT-03).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from canonical_data.session_clock import is_xnys_session, session_bounds  # noqa: E402

W = Path(__file__).resolve().parent
NEW_YORK = ZoneInfo("America/New_York")
COLUMNS = ["session", "ticker", "ledger_id", "contract", "held", "stock_close", "option_bid", "option_ask", "option_mid",
           "option_last", "iv", "open_interest", "quote_time_utc"]
UNVERIFIED_COLUMNS = COLUMNS + ["reason"]
LOOKBACK_SESSIONS = 10
CARD_DECISIONS = {"TRADE", "WATCH", "ENTER"}
CLOSED_STATES = {"CLOSED", "EXITED"}
OCC = re.compile(r"^[A-Z.]{1,6}\d{6}[CP]\d{8}$")
CLOSE_TOLERANCE = timedelta(minutes=1)        # a quote stamped from one minute before the close counts as the close


def _contract_of(card: dict, held: bool) -> Optional[str]:
    order = ("contract_taken", "contract", "contract_planned", "planned_contract") if held else \
            ("contract", "contract_planned", "planned_contract", "contract_taken")
    for key in order:
        value = str(card.get(key) or "").strip().upper().replace(" ", "")
        if OCC.match(value):
            return value
    return None


def _is_held(card: dict) -> bool:
    fill = card.get("fill")
    if not isinstance(fill, dict):
        return False
    try:
        quantity = float(fill.get("quantity") or 0)
    except (TypeError, ValueError):
        quantity = 0
    return quantity > 0 and str(card.get("position_state") or "").upper() not in CLOSED_STATES


def carded_contracts(handoff_root: Path, *, today: date) -> list[dict]:
    """Contracts to capture. Held contracts from every hand-off folder (UAT-01: an open holding is followed until its
    card records it closed); other TRADE / WATCH / ENTER cards from the last LOOKBACK_SESSIONS sessions. Newest first;
    a held contract keeps held=Y even when a newer card names it again."""
    folders = []
    for folder in Path(handoff_root).glob("split_*"):
        m = re.match(r"split_(\d{4}-\d{2}-\d{2})", folder.name)
        if not m or not (folder / "decisions").is_dir():
            continue
        day = date.fromisoformat(m.group(1))
        if day <= today:
            folders.append((day, folder, np.busday_count(day, today) <= LOOKBACK_SESSIONS))
    cards = []
    for _, folder, recent in sorted(folders, reverse=True):
        for path in sorted((folder / "decisions").glob("*.json")):
            try:
                cards.append((path, json.loads(path.read_text(encoding="utf-8")), recent))
            except (OSError, json.JSONDecodeError):
                continue
    rows, seen = [], set()
    for want_held in (True, False):
        for path, card, recent in cards:
            held = _is_held(card)
            if held != want_held:
                continue
            if not held and (not recent or str(card.get("decision") or "").upper() not in CARD_DECISIONS):
                continue
            contract = _contract_of(card, held)
            if not contract or contract in seen:
                continue
            seen.add(contract)
            rows.append({"ticker": str(card.get("ticker") or path.stem).upper(), "ledger_id": card.get("ledger_id"),
                         "contract": contract, "held": "Y" if held else "N"})
    return rows


def closed_session(now_utc: datetime) -> tuple[Optional[date], Optional[str]]:
    """The XNYS session whose close has passed at now_utc (UAT-02), or (None, reason)."""
    day = now_utc.astimezone(NEW_YORK).date()
    if not is_xnys_session(day):
        return None, "NOT_A_SESSION"
    if now_utc < session_bounds(day)[1]:
        return None, "BEFORE_THE_CLOSE"
    return day, None


def quote_reason(quote_time_utc: Optional[str], session: str) -> Optional[str]:
    """None when the quote is the session's close; else STALE_QUOTE / INTRADAY_QUOTE / NO_QUOTE_TIME."""
    if not quote_time_utc:
        return "NO_QUOTE_TIME"
    try:
        stamp = datetime.fromisoformat(str(quote_time_utc).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return "NO_QUOTE_TIME"
    day = date.fromisoformat(session)
    if not is_xnys_session(day):
        return "STALE_QUOTE"
    close = session_bounds(day)[1]
    if stamp < close - CLOSE_TOLERANCE:
        start_of_day = session_bounds(day)[0] - timedelta(hours=6)
        return "INTRADAY_QUOTE" if stamp >= start_of_day else "STALE_QUOTE"
    return None


def marketdata_quote(contract: str) -> Optional[dict]:
    """One option quote from MarketData (reuses the pipeline interpreter's reader; key from the environment)."""
    from pipeline_interpreter.live_market_reader import _marketdata_get, _take_array
    payload = _marketdata_get(f"options/quotes/{contract}/")
    if not payload or payload.get("s") != "ok":
        return None

    def one(key):
        arr = _take_array(payload, key)
        return arr[0] if arr else None

    updated = one("updated")
    when = (datetime.fromtimestamp(float(updated), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            if updated not in (None, "") else None)
    return {"bid": one("bid"), "ask": one("ask"), "mid": one("mid"), "last": one("last"), "iv": one("iv"),
            "open_interest": one("openInterest"), "underlying_price": one("underlyingPrice"), "updated_utc": when}


def _append(path: Path, rows: list[dict], columns: list[str]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).reindex(columns=columns).to_csv(path, mode="a", header=not path.is_file(), index=False)


def capture(rows: list[dict], *, session: str, quote_fn: Callable[[str], Optional[dict]], out_csv: Path,
            unverified_csv: Optional[Path] = None) -> int:
    """Append each contract's verified close for the session; returns how many verified closes were added.
    Contracts already holding a verified close for the session are skipped (no quote request); a NO_QUOTE row does
    not count as done, so the next run retries it and both rows stay as the audit trail (UAT-03)."""
    out_csv = Path(out_csv)
    unverified_csv = Path(unverified_csv) if unverified_csv else out_csv.with_name("option_quotes_unverified.csv")
    existing = pd.read_csv(out_csv, dtype=str) if out_csv.is_file() else pd.DataFrame(columns=COLUMNS)
    verified = existing[~existing["quote_time_utc"].fillna("").str.startswith("NO_QUOTE")] if len(existing) else existing
    done = set(zip(verified.get("session", []), verified.get("contract", [])))
    closes, failures, unverified = [], [], []
    for r in rows:
        if (session, r["contract"]) in done:
            continue
        base = {"session": session, **{k: r[k] for k in ("ticker", "ledger_id", "contract", "held")}}
        q = quote_fn(r["contract"])
        if not q:
            failures.append({**base, "quote_time_utc": "NO_QUOTE:PROVIDER_RETURNED_NONE"})
            continue
        row = {**base, "stock_close": q.get("underlying_price"), "option_bid": q.get("bid"),
               "option_ask": q.get("ask"), "option_mid": q.get("mid"), "option_last": q.get("last"),
               "iv": q.get("iv"), "open_interest": q.get("open_interest"), "quote_time_utc": q.get("updated_utc")}
        reason = quote_reason(q.get("updated_utc"), session)
        if reason:
            unverified.append({**row, "reason": reason})
        else:
            closes.append(row)
    _append(out_csv, failures + closes, COLUMNS)
    _append(unverified_csv, unverified, UNVERIFIED_COLUMNS)
    return len(closes)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--handoff", type=Path, default=W / "handoff")
    ap.add_argument("--out", type=Path, default=W / "monitor" / "option_closes.csv")
    ap.add_argument("--run-retired", action="store_true", help="run anyway (retired 17 Oct: the monitor owns the file)")
    a = ap.parse_args(argv)
    if not a.run_retired:
        print("capture_option_closes: RETIRED 17 Oct 2026 - the post-close monitor writes monitor\\option_closes.csv; "
              "nothing written (pass --run-retired only if ACK reinstates it)")
        return 0
    session, reason = closed_session(datetime.now(timezone.utc))
    if session is None:
        print(f"capture_option_closes: nothing captured ({reason}); closes are recorded only after an XNYS session close")
        return 0
    rows = carded_contracts(a.handoff, today=session)
    added = capture(rows, session=session.isoformat(), quote_fn=marketdata_quote, out_csv=a.out)
    held = sum(r["held"] == "Y" for r in rows)
    print(f"capture_option_closes: {len(rows)} carded/held contracts ({held} held); {added} verified closes for "
          f"{session} -> {a.out} (stale/intraday quotes: {a.out.with_name('option_quotes_unverified.csv').name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
