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
