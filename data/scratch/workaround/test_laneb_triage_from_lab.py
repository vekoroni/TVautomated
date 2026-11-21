"""AVS-ARCH-LB-001 G3 (ACK 21 Nov 2026: "we need to build this"): the triage file is prefilled by code from the Lab hand-off.

Business rules:
- The script fills every triage column that files on disk can fill: the Lab hand-off, the board macro context, the ticker
  pack and earlier decision files. The chat adds judgement; live quotes come from the chat or the board.
- It never invents. A judgement column, a decision column and every column that needs a live quote is left blank. The
  Lab's saved quote is written under its own name (lab_saved_*), never as the live contract_bid / contract_ask, so the
  checker cannot grade a saved quote as live.
- Lab values are copied as written: ledger id, target and first profit are not rounded or rewritten.
- Macro columns come from the board macro context for the same ledger id, word for word.
- The trigger, stop, half target and invalidation exist as numbers (trig_v, stop_v, half_v, inval_v) with their direction.
- The prefill is written under its own file name, so a prefill can never pass the triage check as a finished triage.

Legacy behaviour replaced: a chat built every column by hand. On 20 Nov the macro columns matched the board context on
52%, 8% and 0% of rows, ATR was estimated although the pack had the bars, and trigger and stop existed only as sentences.

Run (PowerShell, repo root):
    venv\\Scripts\\python.exe -m pytest data\\scratch\\workaround\\test_laneb_triage_from_lab.py -q -p no:cacheprovider --basetemp=%TEMP%\\avs_tfl
Isolated: temporary folders only; no broker, no provider, no network; no database.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import triage_from_lab as tfl  # noqa: E402

SESSION = "2026-11-20"
HANDOFF_COLS = ["ticker", "lb_batch", "lb_order", "lb_ledger_id", "thesis__readiness", "trade_lane_setup", "sector_etf",
                "contract_symbol", "lab_rank", "lab_verdict", "monetisation_state", "lb_saved_gate", "anticipated_level",
                "anticipated_level_q50", "lb_dollar_volume_20d_usd", "signal_price", "direction", "thesis_trigger_level",
                "thesis_event_state", "invalidation_price", "earnings_date", "lb_window_flag", "lb_time_fit", "lb_group",
                "lb_group_role", "lb_focus", "contract_bid", "contract_ask", "contract_oi", "quote_tier"]


def lab_row(ticker, order, direction="PUT", **over):
    row = {"ticker": ticker, "lb_batch": "1", "lb_order": str(order), "lb_ledger_id": f"{SESSION}_{ticker}_{direction}",
           "thesis__readiness": "WAIT_TRIGGER", "trade_lane_setup": "1w|BREAK_DOWN", "sector_etf": "XLF",
           "contract_symbol": f"{ticker}270115P00085000", "lab_rank": str(order + 3), "lab_verdict": "MANUAL_REVIEW",
           "monetisation_state": "NOT_PUBLISHED", "lb_saved_gate": "B", "anticipated_level": "70.9553",
           "anticipated_level_q50": "76.12345", "lb_dollar_volume_20d_usd": "168123456.7", "signal_price": "83.35",
           "direction": direction, "thesis_trigger_level": "84.38", "thesis_event_state": "DETECTED",
           "invalidation_price": "86.83", "earnings_date": "2027-02-23", "lb_window_flag": "OUTSIDE_WINDOW",
           "lb_time_fit": "CONTRACT_EXPIRES_BEFORE_MEDIAN_TIME", "lb_group": "XLF_PUT", "lb_group_role": "PRIMARY",
           "lb_focus": "", "contract_bid": "3.1", "contract_ask": "3.5", "contract_oi": "1019.0", "quote_tier": "B"}
    row.update(over)
    return row


def pack(folder: Path, ticker: str, days: int = 260):
    """A pack with `days` daily bars: close rises 1.00 a day from 100, range is close +/- 1; SPY is flat at 500."""
    import datetime as dt
    start = dt.date(2025, 11, 1)
    bars, bench = ["ticker,trading_date,adjustment_convention,open,high,low,close,volume"], ["ticker,trading_date,open,close,volume"]
    for i in range(days):
        day = (start + dt.timedelta(days=i)).isoformat()
        close = 100 + i
        bars.append(f"{ticker},{day},X,{close - 0.5},{close + 1},{close - 1},{close},1000")
        bench.append(f"SPY,{day},500,500,1000")
    folder.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(folder / f"{ticker}_pack.zip", "w") as archive:
        archive.writestr(f"{ticker}/prices_ohlcv_daily.csv", "\n".join(bars))
        archive.writestr(f"{ticker}/prices_benchmarks.csv", "\n".join(bench))


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "handoff"
    folder = root / f"lab_{SESSION}"
    folder.mkdir(parents=True)
    rows = [lab_row("AAA", 1), lab_row("BBB", 2, direction="CALL", contract_symbol="BBB270115C00020000", lb_focus="FOCUS"),
            lab_row("CCC", 3, direction="UNRESOLVED", contract_symbol="", anticipated_level="", anticipated_level_q50="",
                    thesis_trigger_level="", invalidation_price="", contract_bid="", contract_ask="", contract_oi=""),
            lab_row("DDD", 31, lb_batch="2", thesis_event_state="ACTIVATED")]
    with (folder / "handoff.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HANDOFF_COLS)
        writer.writeheader()
        writer.writerows(rows)
    (folder / "receipt.json").write_text(json.dumps({"session": SESSION, "lab_revision": "rev-1", "run_id": "R1"}), encoding="utf-8")
    with (folder / f"triage_macro_context_{SESSION}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ledger_id", "money_tag", "macro_sector_agreement", "macro_scenario_ids",
                                                    "macro_kill_switch", "sector_check"])
        writer.writeheader()
        writer.writerow({"ledger_id": f"{SESSION}_AAA_PUT", "money_tag": "WITH", "macro_sector_agreement": "AGREE: measured LEAN_IN",
                         "macro_scenario_ids": "A; C4", "macro_kill_switch": "measured LEAN IN on XLF void below 55.10",
                         "sector_check": "XLF -0.4% vs SPY 5d"})
    earlier = root / "lab_2026-11-18" / "decisions"
    earlier.mkdir(parents=True)
    (earlier / "AAA.json").write_text(json.dumps({"ticker": "AAA", "card_side": "PUT", "decision": "WATCH",
                                                  "artifact_url": "https://claude.ai/artifact/abc"}), encoding="utf-8")
    packs = tmp_path / "packs" / SESSION
    pack(packs, "AAA")
    return {"root": root, "folder": folder, "packs": packs}


def build(world, batches=(1,)):
    out = tfl.build_prefill(world["folder"], SESSION, batches=list(batches), packs_folder=world["packs"], handoff_root=world["root"])
    return {b: {r["ticker"]: r for r in rows} for b, rows in out.items()}


def test_lab_values_are_copied_as_written(world):
    aaa = build(world)[1]["AAA"]
    assert aaa["ledger_id"] == f"{SESSION}_AAA_PUT" and aaa["batch"] == "1" and aaa["lab_rank"] == "4"
    assert aaa["target"] == "70.9553" and aaa["first_profit"] == "76.12345"            # never rounded
    assert aaa["handoff_state"] == "WAIT_TRIGGER" and aaa["timeframe"] == "1w" and aaa["handoff_sector_etf"] == "XLF"
    assert aaa["lab_contract"] == aaa["handoff_best_contract"] == "AAA270115P00085000"
    assert aaa["lab_revision"] == "rev-1" and aaa["stock_dollar_volume_20d_musd"] == "168.1"
    assert aaa["handoff_side"] == "PUT" and aaa["side"] == "PUT" and aaa["side_change"] == "N" and aaa["counter_side"] == "CALL"
    assert aaa["prev_close_1117"] == "83.35"


def test_the_layout_is_the_triage_layout_with_the_new_columns_after_it(world):
    out = tfl.build_prefill(world["folder"], SESSION, batches=[1], packs_folder=world["packs"], handoff_root=world["root"])
    columns = list(out[1][0])
    assert columns[:len(tfl.TRIAGE_COLUMNS)] == tfl.TRIAGE_COLUMNS and len(tfl.TRIAGE_COLUMNS) == 84
    assert columns[len(tfl.TRIAGE_COLUMNS):] == tfl.EXTRA_COLUMNS


def test_trigger_stop_and_targets_exist_as_numbers(world):
    rows = build(world, batches=(1, 2))
    aaa, bbb, ddd = rows[1]["AAA"], rows[1]["BBB"], rows[2]["DDD"]
    assert (aaa["trig_kind"], aaa["trig_v"], aaa["stop_dir"], aaa["stop_v"]) == ("below", "84.38", "above", "86.83")
    assert (bbb["trig_kind"], bbb["stop_dir"]) == ("above", "below")
    assert aaa["half_v"] == "76.12345" and aaa["inval_v"] == "86.83"
    assert ddd["trig_kind"] == "fired"                                                  # the Lab says the event is activated


def test_judgement_decision_and_live_quote_columns_are_left_blank(world):
    aaa = build(world)[1]["AAA"]
    for column in tfl.JUDGEMENT_COLUMNS + tfl.DECISION_COLUMNS + tfl.LIVE_QUOTE_COLUMNS:
        assert aaa[column] == "", column
    assert aaa["contract_bid"] == "" and aaa["contract_ask"] == "" and aaa["contract_oi"] == ""
    assert (aaa["lab_saved_bid"], aaa["lab_saved_ask"], aaa["lab_saved_oi"], aaa["lab_saved_quote_tier"]) == ("3.1", "3.5", "1019.0", "B")
    assert aaa["earnings_tastytrade"] == "" and aaa["lab_earnings_date"] == "2027-02-23"


def test_macro_columns_come_from_the_board_context_word_for_word(world):
    rows = build(world)[1]
    aaa, bbb = rows["AAA"], rows["BBB"]
    assert aaa["money_tag"] == "WITH" and aaa["macro_sector_agreement"] == "AGREE: measured LEAN_IN"
    assert aaa["macro_kill_switch"] == "measured LEAN IN on XLF void below 55.10" and aaa["macro_scenario_ids"] == "A; C4"
    assert bbb["money_tag"] == "" and "MACRO_CONTEXT_ROW_MISSING" in bbb["prefill_gaps"]


def test_pack_levels_are_measured_not_estimated(world):
    rows = build(world)[1]
    aaa, bbb = rows["AAA"], rows["BBB"]
    # 260 bars, close 100..359, high = close + 1, low = close - 1, true range = 2 on every bar
    assert float(aaa["atr14"]) == pytest.approx(2.0)
    assert float(aaa["hi15"]) == 360.0 and float(aaa["lo15"]) == 344.0
    assert float(aaa["sma20"]) == pytest.approx(349.5) and float(aaa["sma50"]) == pytest.approx(334.5)
    assert float(aaa["hi52w"]) == 360.0 and float(aaa["lo52w"]) == 107.0               # the last 252 sessions
    assert float(aaa["rel5_vs_spy"]) == pytest.approx((359 / 354 - 1) * 100, abs=0.05)
    assert aaa["pack_as_of"] == "2026-07-18"
    assert bbb["atr14"] == "" and "PACK_MISSING" in bbb["prefill_gaps"]                 # no pack: blank, and said so


def test_a_name_with_no_single_side_is_listed_with_the_gap_named(world):
    ccc = build(world)[1]["CCC"]
    assert ccc["side"] == "" and ccc["handoff_side"] == "UNRESOLVED" and ccc["counter_side"] == ""
    assert ccc["trade_contract"] == "" and ccc["trig_v"] == "" and ccc["target"] == ""
    assert "NO_SINGLE_SIDE" in ccc["prefill_gaps"] and "NO_LAB_CONTRACT" in ccc["prefill_gaps"]


def test_an_earlier_card_is_found_and_a_focus_name_is_flagged(world):
    rows = build(world)[1]
    aaa, bbb = rows["AAA"], rows["BBB"]
    assert (aaa["priority_card"], aaa["prev_card_date"], aaa["prev_card_side"], aaa["prev_card_decision"]) == ("Y", "2026-11-18", "PUT", "WATCH")
    assert aaa["prev_card_url"] == "https://claude.ai/artifact/abc"
    assert bbb["priority_card"] == "N" and bbb["lb_focus"] == "FOCUS" and aaa["lb_focus"] == ""


def test_rows_keep_the_lab_order_and_are_ranked_from_one_in_each_batch(world):
    out = tfl.build_prefill(world["folder"], SESSION, batches=[1, 2], packs_folder=world["packs"], handoff_root=world["root"])
    assert [(r["ticker"], r["deep_mine_rank"]) for r in out[1]] == [("AAA", "1"), ("BBB", "2"), ("CCC", "3")]
    assert [(r["ticker"], r["deep_mine_rank"]) for r in out[2]] == [("DDD", "1")]


def test_the_prefill_cannot_be_mistaken_for_a_finished_triage(world):
    out = tfl.build_prefill(world["folder"], SESSION, batches=[1], packs_folder=world["packs"], handoff_root=world["root"])
    paths = tfl.write_prefill(out, world["folder"], SESSION)
    names = [p.name for p in paths]
    assert f"triage_prefill_b1_{SESSION}.csv" in names and f"triage_prefill_{SESSION}.md" in names
    assert not list(world["folder"].glob(f"batch*_triage_{SESSION}.csv"))               # the checker's own pattern finds nothing
    note = (world["folder"] / f"triage_prefill_{SESSION}.md").read_text(encoding="utf-8")
    assert "live quote" in note and "judgement" in note and "never" in note.lower()
    saved = list(csv.DictReader((world["folder"] / f"triage_prefill_b1_{SESSION}.csv").open(encoding="utf-8", newline="")))
    assert [r["ticker"] for r in saved] == ["AAA", "BBB", "CCC"] and saved[0]["target"] == "70.9553"


def test_a_missing_hand_off_stops_with_its_name(tmp_path):
    with pytest.raises(FileNotFoundError, match="handoff.csv"):
        tfl.build_prefill(tmp_path / "nowhere", SESSION, batches=[1], packs_folder=tmp_path, handoff_root=tmp_path)
