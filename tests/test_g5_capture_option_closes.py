"""G5 minimal, item 4 (ACK approved 17 Oct 2026): every carded and held contract's closing quote is recorded daily.

Design: Enhancements/options_valuation_review/G5_G9_ONE_PRICER_ONE_BASIS_DESIGN_20261017.md (status section);
fix inbox W16-10 / A16-03. Before: option prices were captured once, by hand (monitor\\option_closes.csv holds one
session, 16 Oct), so predicted option prices could not be checked against what the market actually paid.

Business rules:
- After the close, every contract named by a TRADE / WATCH / ENTER card in the last 10 hand-off sessions, and every
  filled (held) contract, gets one row per session with bid, ask, mid, last, IV, OI, stock price and quote time.
- A held contract is marked held=Y.
- Rows go to monitor\\option_closes.csv in its existing columns; running twice in a session adds nothing new.
- A contract with no quote is recorded with the reason, never dropped silently.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "data" / "scratch" / "workaround" / "capture_option_closes.py"
COLUMNS = ["session", "ticker", "ledger_id", "contract", "held", "stock_close", "option_bid", "option_ask", "option_mid",
           "option_last", "iv", "open_interest", "quote_time_utc"]


def _tool():
    spec = importlib.util.spec_from_file_location("capture_option_closes", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _card(folder: Path, ticker: str, **fields):
    (folder / "decisions").mkdir(parents=True, exist_ok=True)
    (folder / "decisions" / f"{ticker}.json").write_text(json.dumps({"ticker": ticker, **fields}))


@pytest.fixture
def handoff(tmp_path):
    root = tmp_path / "handoff"
    _card(root / "split_2026-10-16_cap5", "TEVA", ledger_id="2026-10-16_TEVA_CALL", decision="WATCH",
          contract="TEVA270115C00040000")
    _card(root / "split_2026-10-16_cap5", "ORA", ledger_id="2026-10-16_ORA_PUT", decision="PASS",
          contract="ORA261218P00080000")
    _card(root / "split_2026-10-14_cap5", "BILI", ledger_id="2026-10-14_BILI_PUT", decision="TRADE", contract=None,
          contract_taken="BILI270115P00015000", order_placed="yes", fill={"quantity": 1, "price": 1.8})
    _card(root / "split_2026-09-01_cap5", "OLD", ledger_id="2026-09-01_OLD_CALL", decision="WATCH",
          contract="OLD261218C00010000")
    return root


def _quote(contract):
    if contract.startswith("TEVA"):
        return {"bid": 3.9, "ask": 4.35, "mid": 4.125, "last": 4.05, "iv": 0.41, "open_interest": 7709,
                "underlying_price": 41.5, "updated_utc": "2026-10-16T20:22:00Z"}
    if contract.startswith("BILI"):
        return {"bid": 2.1, "ask": 2.3, "mid": 2.2, "last": 2.2, "iv": 0.6, "open_interest": 900,
                "underlying_price": 13.6, "updated_utc": "2026-10-16T20:22:00Z"}
    return None


def test_carded_and_held_contracts_from_the_last_ten_sessions_are_selected(handoff):
    rows = _tool().carded_contracts(handoff, today=date(2026, 10, 16))
    got = {r["contract"]: r["held"] for r in rows}
    assert got == {"TEVA270115C00040000": "N", "BILI270115P00015000": "Y"}   # PASS and the 1 Sep card are left out


def test_a_held_contract_stays_held_when_a_newer_card_names_it_again(handoff):
    """Found on the real folders 17 Oct: the 16 Oct BILI card re-names the BILI Jan 15P held since 14 Oct."""
    _card(handoff / "split_2026-10-16_cap5", "BILI", ledger_id="2026-10-16_BILI_PUT", decision="WATCH",
          contract="BILI270115P00015000")
    rows = _tool().carded_contracts(handoff, today=date(2026, 10, 16))
    bili = [r for r in rows if r["contract"] == "BILI270115P00015000"]
    assert len(bili) == 1 and bili[0]["held"] == "Y"


def test_one_row_per_contract_per_session_in_the_existing_columns(handoff, tmp_path):
    tool = _tool()
    out = tmp_path / "option_closes.csv"
    rows = tool.carded_contracts(handoff, today=date(2026, 10, 16))
    tool.capture(rows, session="2026-10-16", quote_fn=_quote, out_csv=out)
    tool.capture(rows, session="2026-10-16", quote_fn=_quote, out_csv=out)          # a second run adds nothing
    d = pd.read_csv(out)
    assert list(d.columns) == COLUMNS
    assert len(d) == 2
    teva = d[d["ticker"] == "TEVA"].iloc[0]
    assert (teva["option_bid"], teva["option_ask"], teva["stock_close"]) == (3.9, 4.35, 41.5)
    assert d.loc[d["ticker"] == "BILI", "held"].iloc[0] == "Y"


def test_a_contract_without_a_quote_is_recorded_with_the_reason(handoff, tmp_path):
    tool = _tool()
    out = tmp_path / "option_closes.csv"
    rows = tool.carded_contracts(handoff, today=date(2026, 10, 16))
    tool.capture(rows, session="2026-10-16", quote_fn=lambda c: None, out_csv=out)
    d = pd.read_csv(out)
    assert len(d) == 2 and d["quote_time_utc"].str.startswith("NO_QUOTE").all()


def test_existing_rows_are_kept(handoff, tmp_path):
    tool = _tool()
    out = tmp_path / "option_closes.csv"
    pd.DataFrame([dict(zip(COLUMNS, ["2026-10-15", "GME", "x", "GME261218C00025000", "N", 26.8, 3.8, 4.15, 3.975,
                                     3.9, 0.69, 27960, "2026-10-15T20:22:00Z"]))]).to_csv(out, index=False)
    tool.capture(tool.carded_contracts(handoff, today=date(2026, 10, 16)), session="2026-10-16", quote_fn=_quote,
                 out_csv=out)
    assert len(pd.read_csv(out)) == 3


# --- UAT 17 Oct 2026 (UAT_Report_20261017.txt, ACK: "apply the fixes apart from the Phantom fixes") ---------------

def test_uat01_an_open_holding_is_captured_whatever_the_age_of_its_card(handoff):
    """UAT-01: a filled September card with a January expiry was dropped by the 10-session lookback."""
    _card(handoff / "split_2026-09-01_cap5", "HELD", ledger_id="2026-09-01_HELD_CALL", decision="TRADE",
          contract_taken="HELD270115C00100000", fill={"quantity": 1, "price": 2.0})
    _card(handoff / "split_2026-09-02_cap5", "SOLD", ledger_id="2026-09-02_SOLD_CALL", decision="TRADE",
          contract_taken="SOLD270115C00100000", fill={"quantity": 1, "price": 2.0}, position_state="CLOSED")
    got = {r["contract"]: r["held"] for r in _tool().carded_contracts(handoff, today=date(2026, 10, 16))}
    assert got.get("HELD270115C00100000") == "Y"            # still open: captured until it is closed
    assert "SOLD270115C00100000" not in got                 # explicitly closed: no longer captured
    assert "OLD261218C00010000" not in got                  # an old card that was never filled: outside lookback


def test_uat02_a_quote_from_another_day_is_never_stored_as_this_session_s_close(handoff, tmp_path):
    """UAT-02: a 16 Oct quote was written as the 17 Oct close."""
    tool = _tool()
    out, unverified = tmp_path / "option_closes.csv", tmp_path / "option_quotes_unverified.csv"
    rows = tool.carded_contracts(handoff, today=date(2026, 10, 16))
    added = tool.capture(rows, session="2026-10-17", quote_fn=_quote, out_csv=out, unverified_csv=unverified)
    assert added == 0
    assert not out.is_file() or pd.read_csv(out).empty
    u = pd.read_csv(unverified)
    assert len(u) == 2 and (u["reason"] == "STALE_QUOTE").all()


def test_uat02_an_intraday_quote_is_kept_apart_from_verified_closes(handoff, tmp_path):
    tool = _tool()
    out, unverified = tmp_path / "option_closes.csv", tmp_path / "option_quotes_unverified.csv"
    early = lambda c: {**(_quote(c) or {}), "updated_utc": "2026-10-16T19:30:00Z"}       # 15:30 ET, before the close
    tool.capture(tool.carded_contracts(handoff, today=date(2026, 10, 16)), session="2026-10-16", quote_fn=early,
                 out_csv=out, unverified_csv=unverified)
    assert not out.is_file() or pd.read_csv(out).empty
    assert (pd.read_csv(unverified)["reason"] == "INTRADAY_QUOTE").all()


def test_uat02_the_session_is_the_exchange_session_not_the_wall_clock():
    from datetime import datetime, timezone
    tool = _tool()
    assert tool.closed_session(datetime(2026, 10, 16, 20, 30, tzinfo=timezone.utc)) == (date(2026, 10, 16), None)
    assert tool.closed_session(datetime(2026, 10, 16, 19, 0, tzinfo=timezone.utc))[1] == "BEFORE_THE_CLOSE"
    assert tool.closed_session(datetime(2026, 10, 17, 21, 0, tzinfo=timezone.utc))[1] == "NOT_A_SESSION"   # Saturday
    assert tool.closed_session(datetime(2026, 11, 26, 22, 0, tzinfo=timezone.utc))[1] == "NOT_A_SESSION"   # holiday


def test_uat03_a_missing_quote_is_retried_and_the_failure_is_kept(handoff, tmp_path):
    """UAT-03: a NO_QUOTE row blocked a same-session retry."""
    tool = _tool()
    out, unverified = tmp_path / "option_closes.csv", tmp_path / "option_quotes_unverified.csv"
    rows = tool.carded_contracts(handoff, today=date(2026, 10, 16))
    tool.capture(rows, session="2026-10-16", quote_fn=lambda c: None, out_csv=out, unverified_csv=unverified)
    calls = []
    added = tool.capture(rows, session="2026-10-16", quote_fn=lambda c: calls.append(c) or _quote(c), out_csv=out,
                         unverified_csv=unverified)
    assert added == 2 and len(calls) == 2
    d = pd.read_csv(out)
    assert len(d) == 4                                                  # 2 failures kept + 2 recoveries
    again = tool.capture(rows, session="2026-10-16", quote_fn=_quote, out_csv=out, unverified_csv=unverified)
    assert again == 0 and len(pd.read_csv(out)) == 4                    # complete rows stay idempotent
