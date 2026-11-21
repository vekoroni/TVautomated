"""AVS-ENH-2026-11-21 Wave 0 (ACK go-ahead 21 Nov 2026): the ticket-ready list and the board-row collector.

Business rules:
- F-01: every live card reaches the day's ticket list with an exact order string, whichever session's hand-off folder
  it was written in. The list is advisory: ACK places every order, and the 15:40 ET criteria check stays with ACK.
- F-02 / F-03: the exit travels with the entry. A filled card with no resting exit recorded is listed first.
- F-04: the order string carries the card's size; a fill of a different quantity is flagged unless the card says why.
- F-05: the macro kill state is on the ticket's first line. A card with no kill switch is NOT_ASSESSED, never CLEAR.
- F-09: a macro state from an earlier session is labelled with its date; it never passes as today's.
- F-10: today_context.json is refreshed from what is on disk, without waiting for an avs_day.ps1 step.
- F-29: board rows written in any of the shapes found are collected into one file in one shape; a file that cannot be
  read is listed with the reason, never dropped.

Legacy behaviour replaced: tickets came from one hand-off folder and only when avs_day.ps1 preclose or eod was run
(none on 16 to 20 Nov); the resting-exit, quantity and macro rules were sentences on the ticket sheet; today_context
kept the values of its first write; board rows were pasted by hand from 14 different shapes.

Run (PowerShell, repo root):
    venv\\Scripts\\python.exe -m pytest data\\scratch\\workaround\\test_laneb_ticket_ready.py -q -p no:cacheprovider --basetemp=%TEMP%\\avs_tr
Isolated: temporary folders only; no broker, no provider, no network; nothing in the real hand-off folders is read.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_board_rows  # noqa: E402
import ticket_ready  # noqa: E402

TODAY = date(2026, 11, 20)


def card(ticker, **over):
    base = {"ledger_id": f"2026-11-20_{ticker}_CALL", "ticker": ticker, "card_side": "CALL", "decision": "WATCH",
            "final_action": "TRADE_ON_TRIGGER", "contract": f"{ticker}261218C00025000", "entry_type": "15:50 ET close in the zone",
            "close_zone_low": 23.8, "close_zone_high": 24.4, "limit": 2.24, "max_pay": 2.3, "size": 1, "stop": 23.29,
            "time_stop": "2026-11-24 15:50 ET",
            "one_contract_exit": {"target_stock": 25.85, "target_option_price": 2.8, "stop": 23.29, "time_stop": "2026-11-24"},
            "order_placed": "", "fill": None, "artifact_url": ""}
    base.update(over)
    return base


def handoff(tmp_path, cards_by_folder):
    root = tmp_path / "handoff"
    for folder, cards in cards_by_folder.items():
        d = root / folder / "decisions"
        d.mkdir(parents=True)
        for c in cards:
            (d / f"{c['ticker']}.json").write_text(json.dumps(c), encoding="utf-8")
    return root


def by_ticker(tickets):
    return {t["ticker"]: t for t in tickets}


# ---------------------------------------------------------------- F-01: every live card, whichever folder
def test_a_live_card_from_an_earlier_session_is_on_todays_list(tmp_path):
    root = handoff(tmp_path, {"lab_2026-11-18": [card("OLD")], "lab_2026-11-20": [card("NEW")]})

    tickets = by_ticker(ticket_ready.build_tickets(root, TODAY, macro_state=None))

    assert set(tickets) == {"OLD", "NEW"}
    assert tickets["OLD"]["source_folder"] == "lab_2026-11-18"
    assert tickets["NEW"]["entry_order"] == "BUY TO OPEN 1 NEW261218C00025000 LIMIT 2.24 DAY (never above 2.30)"


def test_the_newest_card_wins_when_a_name_is_carded_twice(tmp_path):
    root = handoff(tmp_path, {"lab_2026-11-18": [card("AAA", max_pay=1.0)], "lab_2026-11-20": [card("AAA", max_pay=2.0)]})

    tickets = ticket_ready.build_tickets(root, TODAY, macro_state=None)

    assert len(tickets) == 1 and tickets[0]["source_folder"] == "lab_2026-11-20" and "2.00" in tickets[0]["entry_order"]


def test_a_passed_card_is_not_a_ticket_and_an_expired_one_is_listed_not_dropped(tmp_path):
    root = handoff(tmp_path, {"lab_2026-11-20": [card("PASSD", decision="PASS"),
                                                 card("LATE", time_stop="2026-11-18 15:50 ET")]})

    tickets = by_ticker(ticket_ready.build_tickets(root, TODAY, macro_state=None))

    assert "PASSD" not in tickets
    assert tickets["LATE"]["state"] == "PAST_TIME_STOP"


def test_a_limit_written_as_words_stays_words_and_is_never_turned_into_a_number(tmp_path):
    root = handoff(tmp_path, {"lab_2026-11-20": [card("MID", limit="live mid")]})

    ticket = ticket_ready.build_tickets(root, TODAY, macro_state=None)[0]

    assert ticket["entry_order"] == "BUY TO OPEN 1 MID261218C00025000 LIMIT live mid DAY (never above 2.30)"


# ---------------------------------------------------------------- F-02 / F-03: the exit travels with the entry
def test_every_ticket_carries_its_exit_order(tmp_path):
    root = handoff(tmp_path, {"lab_2026-11-20": [card("AAA")]})

    ticket = ticket_ready.build_tickets(root, TODAY, macro_state=None)[0]

    assert ticket["exit_order"] == "SELL TO CLOSE 1 AAA261218C00025000 LIMIT 2.80 GTC"


def test_a_filled_card_with_no_resting_exit_is_flagged_and_listed_first(tmp_path):
    filled = card("HELD", order_placed="BTO 1 filled 2.26", fill={"quantity": 1, "price": 2.26, "filled_at_utc": "2026-11-18T20:51:06Z"})
    covered = card("SAFE", order_placed="BTO 1 filled 2.20", fill={"quantity": 1, "price": 2.2},
                   resting_exit={"price": 2.8, "state": "WORKING", "order_id": "typed by ACK"})
    root = handoff(tmp_path, {"lab_2026-11-20": [card("AAA"), covered, filled]})

    tickets = ticket_ready.build_tickets(root, TODAY, macro_state=None)

    assert tickets[0]["ticker"] == "HELD" and "FILLED_NO_RESTING_EXIT" in tickets[0]["flags"]
    assert "FILLED_NO_RESTING_EXIT" not in by_ticker(tickets)["SAFE"]["flags"]
    assert by_ticker(tickets)["HELD"]["state"] == "FILLED"


def test_an_empty_fill_placeholder_is_not_a_fill(tmp_path):
    """Replay finding, 21 Nov: 20 saved cards carry {"quantity": null, "price": null, "filled_at_utc": null}."""
    blank = card("BLNK", fill={"quantity": None, "price": None, "filled_at_utc": None})
    root = handoff(tmp_path, {"lab_2026-11-20": [blank]})

    ticket = ticket_ready.build_tickets(root, TODAY, macro_state=None)[0]

    assert ticket["state"] == "WAITING" and "FILLED_NO_RESTING_EXIT" not in ticket["flags"]


def test_cards_past_their_time_stop_have_their_own_section(tmp_path):
    root = handoff(tmp_path, {"lab_2026-11-20": [card("LIVE"), card("LATE", time_stop="2026-11-18 15:50 ET")]})

    md_path, _ = ticket_ready.write_list(ticket_ready.build_tickets(root, TODAY, macro_state=None),
                                         root / "lab_2026-11-20", "2026-11-20", None, TODAY)

    text = md_path.read_text(encoding="utf-8")
    assert "### LIVE" in text and "### LATE" not in text
    assert "Past their time stop, not filled (1)" in text and "LATE (2026-11-18" in text


def test_a_cancelled_resting_exit_counts_as_none(tmp_path):
    held = card("HELD", fill={"quantity": 1, "price": 2.26}, resting_exit={"price": 2.94, "state": "CANCELLED"})
    root = handoff(tmp_path, {"lab_2026-11-20": [held]})

    assert "FILLED_NO_RESTING_EXIT" in ticket_ready.build_tickets(root, TODAY, macro_state=None)[0]["flags"]


# ---------------------------------------------------------------- F-04: quantity
def test_size_is_read_as_a_number_whatever_its_form():
    assert ticket_ready.parse_size(1) == 1
    assert ticket_ready.parse_size("1 contract") == 1
    assert ticket_ready.parse_size("1 contract (test month); put half size") == 1
    assert ticket_ready.parse_size("") is None and ticket_ready.parse_size(None) is None


def test_a_fill_of_a_different_quantity_is_flagged_unless_the_card_explains_it(tmp_path):
    two = card("TWO", fill={"quantity": 2, "price": 0.15})
    scaled = card("SCAL", fill={"quantity": 2, "price": 0.15}, scaling_note="second contract added per the card")
    root = handoff(tmp_path, {"lab_2026-11-20": [two, scaled]})

    tickets = by_ticker(ticket_ready.build_tickets(root, TODAY, macro_state=None))

    assert "QUANTITY_DIFFERS_FROM_CARD" in tickets["TWO"]["flags"]
    assert "QUANTITY_DIFFERS_FROM_CARD" not in tickets["SCAL"]["flags"]


def test_a_card_with_no_size_says_so(tmp_path):
    root = handoff(tmp_path, {"lab_2026-11-20": [card("NOSZ", size="")]})

    ticket = ticket_ready.build_tickets(root, TODAY, macro_state=None)[0]

    assert "SIZE_NOT_ON_CARD" in ticket["flags"] and "BUY TO OPEN ? " in ticket["entry_order"]


# ---------------------------------------------------------------- F-05 / F-09: macro kill and stale macro state
FRESH = {"session": "2026-11-20", "kill_switches": [{"id": "KS0-VOL-CREDIT", "instrument": "VIX close + HY OAS", "fired": True},
                                                    {"id": "KS1-BREADTH", "instrument": "IWM", "fired": False}]}


def test_a_card_with_no_kill_switch_is_not_assessed_never_clear(tmp_path):
    root = handoff(tmp_path, {"lab_2026-11-20": [card("NOKS"), card("EMPTY", macro_dependency={"gate": "XLF"})]})

    tickets = by_ticker(ticket_ready.build_tickets(root, TODAY, macro_state=FRESH))

    assert tickets["NOKS"]["macro_kill"] == "NOT_ASSESSED" and "no kill switch on the card" in tickets["NOKS"]["macro_kill_reason"]
    assert tickets["EMPTY"]["macro_kill"] == "NOT_ASSESSED"


def test_a_fired_switch_the_card_names_is_fired(tmp_path):
    named = card("NAMD", macro_dependency={"kill_switch": "KS0-VOL-CREDIT: VIX close above 20 with HY OAS widening"})
    other = card("OTHR", macro_dependency={"kill_switch": "KS1-BREADTH: IWM below 2761"})
    root = handoff(tmp_path, {"lab_2026-11-20": [named, other]})

    tickets = by_ticker(ticket_ready.build_tickets(root, TODAY, macro_state=FRESH))

    assert tickets["NAMD"]["macro_kill"] == "FIRED" and "KS0-VOL-CREDIT" in tickets["NAMD"]["macro_kill_reason"]
    assert tickets["OTHR"]["macro_kill"] == "CLEAR"


def test_a_kill_switch_that_cannot_be_matched_asks_for_review_when_any_switch_has_fired(tmp_path):
    free = card("FREE", macro_dependency={"kill_switch": "HYG below 76.39 at 15:50 ET"})
    root = handoff(tmp_path, {"lab_2026-11-20": [free]})

    ticket = ticket_ready.build_tickets(root, TODAY, macro_state=FRESH)[0]

    assert ticket["macro_kill"] == "REVIEW" and "KS0-VOL-CREDIT" in ticket["macro_kill_reason"]


def test_a_macro_state_from_an_earlier_session_is_never_todays(tmp_path):
    named = card("NAMD", macro_dependency={"kill_switch": "KS0-VOL-CREDIT"})
    root = handoff(tmp_path, {"lab_2026-11-20": [named]})
    stale = dict(FRESH, session="2026-11-16")

    ticket = ticket_ready.build_tickets(root, TODAY, macro_state=stale)[0]

    assert ticket["macro_kill"] == "NOT_ASSESSED"
    assert "2026-11-16" in ticket["macro_kill_reason"] and "KS0-VOL-CREDIT" in ticket["macro_kill_reason"]
    assert ticket_ready.macro_state_age(stale, TODAY) == ("STALE", "macro state is from session 2026-11-16, not 2026-11-20")
    assert ticket_ready.macro_state_age(None, TODAY)[0] == "MISSING"
    assert ticket_ready.macro_state_age(FRESH, TODAY)[0] == "CURRENT"


def test_a_kill_written_by_the_monitor_is_shown_as_written(tmp_path):
    root = handoff(tmp_path, {"lab_2026-11-20": [card("MON", macro_kill="FIRED: HYG 76.10 at 16:00 ET (monitor)")]})

    ticket = ticket_ready.build_tickets(root, TODAY, macro_state=None)[0]

    assert ticket["macro_kill"] == "FIRED" and "monitor" in ticket["macro_kill_reason"]


# ---------------------------------------------------------------- the written list
def test_the_list_opens_with_what_needs_action_and_says_it_is_advisory(tmp_path):
    held = card("HELD", fill={"quantity": 1, "price": 2.26})
    root = handoff(tmp_path, {"lab_2026-11-20": [card("AAA"), held]})
    out = root / "lab_2026-11-20"

    md_path, csv_path = ticket_ready.write_list(ticket_ready.build_tickets(root, TODAY, macro_state=None), out, "2026-11-20", None, TODAY)

    text = md_path.read_text(encoding="utf-8")
    assert md_path.name == "ticket_ready_2026-11-20.md" and csv_path.name == "ticket_ready_2026-11-20.csv"
    assert "Advisory" in text and "ACK places every order" in text
    assert text.index("HELD") < text.index("AAA")
    assert "Macro state: MISSING" in text
    assert "SELL TO CLOSE 1 HELD261218C00025000 LIMIT 2.80 GTC" in text


# ---------------------------------------------------------------- F-10: the context follows the disk
def test_today_context_is_refreshed_from_what_is_on_disk(tmp_path):
    folder = tmp_path / "handoff" / "lab_2026-11-20"
    folder.mkdir(parents=True)
    context = tmp_path / "today_context.json"
    context.write_text(json.dumps({"session": "2026-11-20", "handoff": str(folder), "run_id": "R1", "cards": None,
                                   "order_tickets": None, "split_triage_files": [], "deep_dive_prompts": None,
                                   "triage_check": None, "macro_context": None}), encoding="utf-8")
    for name in ("cards_2026-11-20.csv", "order_tickets_2026-11-20.md", "batch1_triage_2026-11-20.csv",
                 "batch2_triage_2026-11-20.csv", "deep_dive_prompts_2026-11-20_b1.md", "triage_macro_context_2026-11-20.csv",
                 "ticket_ready_2026-11-20.md", "board_rows_2026-11-20.json"):
        (folder / name).write_text("x", encoding="utf-8")
    (folder / "check_triage_2026-11-20.md").write_text("# check_triage: PASS WITH WARNINGS\n", encoding="utf-8")

    changed = ticket_ready.refresh_context(context)

    after = json.loads(context.read_text(encoding="utf-8"))
    assert after["run_id"] == "R1"                                    # fields it does not own are untouched
    assert after["cards"].endswith("cards_2026-11-20.csv") and after["order_tickets"].endswith("order_tickets_2026-11-20.md")
    assert after["split_triage_files"] == ["batch1_triage_2026-11-20.csv", "batch2_triage_2026-11-20.csv"]
    assert after["deep_dive_prompts"].endswith("deep_dive_prompts_2026-11-20_b1.md")
    assert after["triage_check"] == "PASS WITH WARNINGS"
    assert after["macro_context"].endswith("triage_macro_context_2026-11-20.csv")
    assert after["ticket_ready"].endswith("ticket_ready_2026-11-20.md") and after["board_rows"].endswith("board_rows_2026-11-20.json")
    assert "refreshed_local" in after and set(changed) >= {"cards", "order_tickets", "ticket_ready"}


def test_a_missing_file_stays_null_and_a_missing_context_is_reported(tmp_path):
    folder = tmp_path / "handoff" / "lab_2026-11-20"
    folder.mkdir(parents=True)
    context = tmp_path / "today_context.json"
    context.write_text(json.dumps({"session": "2026-11-20", "handoff": str(folder), "cards": None}), encoding="utf-8")

    ticket_ready.refresh_context(context)

    assert json.loads(context.read_text(encoding="utf-8"))["cards"] is None
    assert ticket_ready.refresh_context(tmp_path / "absent.json") is None


# ---------------------------------------------------------------- F-29: board rows in one shape
def test_board_rows_in_every_shape_found_become_one_shape(tmp_path):
    folder = tmp_path / "lab_2026-11-20"
    folder.mkdir()
    row = {"ticker": "AAA", "rungs": [1, 2]}
    shapes = {
        "board_row_2026-11-20_A_CALL.json": {"doc_id": "A_CALL", "collection": "cards", "data": dict(row, ticker="A")},
        "board_row_2026-11-20_B.json": {"doc_id": "B_CALL", "collection": "cards", "row": dict(row, ticker="B")},
        "board_row_2026-11-20_C.json": {"rows": [{"doc_id": "C_CALL", "data": dict(row, ticker="C")},
                                               {"doc_id": "C_PUT", "data": dict(row, ticker="C")}]},
        "board_row_2026-11-20_D.json": {"rows": {"D_CALL": dict(row, ticker="D")}},
        "board_row_E.json": dict(row, ticker="E", id="E_CALL"),
        "board_rows_F_2026-11-20.json": {"doc_id": "F_CALL", "data": dict(row, ticker="F"), "call_leg_row": dict(row, ticker="F", id="F_LEG")},
    }
    for name, payload in shapes.items():
        (folder / name).write_text(json.dumps(payload), encoding="utf-8")
    (folder / "board_row_BAD.json").write_text("{not json", encoding="utf-8")
    (folder / "board_row_EMPTY.json").write_text(json.dumps({"doc_id": "X", "data": {}}), encoding="utf-8")

    result = collect_board_rows.collect([folder], "2026-11-20")

    ids = [r["doc_id"] for r in result["rows"]]
    assert sorted(ids) == ["A_CALL", "B_CALL", "C_CALL", "C_PUT", "D_CALL", "E_CALL", "F_CALL", "F_LEG"]
    assert all(set(r) == {"doc_id", "collection", "data", "source_file"} for r in result["rows"])
    assert {r["file"] for r in result["rejected"]} == {"board_row_BAD.json", "board_row_EMPTY.json"}
    assert all(r["reason"] for r in result["rejected"])
    assert result["files_read"] == 8 and result["row_count"] == 8


def test_the_collector_writes_one_file_and_never_touches_the_board(tmp_path):
    folder = tmp_path / "lab_2026-11-20"
    folder.mkdir()
    (folder / "board_row_2026-11-20_A_CALL.json").write_text(json.dumps({"doc_id": "A_CALL", "data": {"ticker": "A"}}), encoding="utf-8")

    out = collect_board_rows.write(collect_board_rows.collect([folder], "2026-11-20"), folder, "2026-11-20")

    saved = json.loads(out.read_text(encoding="utf-8"))
    assert out.name == "board_rows_2026-11-20.json"
    assert saved["rows"][0]["doc_id"] == "A_CALL" and saved["written_to_board"] is False


# ---------------------------------------------------------------- one ticket per branch (ACK 21 Nov 2026)
# Replay finding: all 33 cards of 16, 18 and 20 Nov have two to five branches. The 20 Nov GRAB fill was on the counter
# leg and the NVDA 140 put was a branch; a list of primary contracts only would have shown neither.
def two_sided(ticker="GRB", **over):
    base = card(ticker, card_side="PUT primary + CALL counter", contract=f"{ticker}270115P00003000", limit="live mid", max_pay=0.19,
                one_contract_exit={"target_stock": 2.75, "target_option_price": 0.33},
                branches=[
                    {"side": "CALL", "trigger": "15:50 ET price 2.75-2.85", "targets": [3.06], "contract": f"{ticker}270115C00003000",
                     "max_pay": 0.16, "stop": "15:50 ET price < 2.70",
                     "gtc": [["2026-11-20", 0.25], ["2026-11-25", 0.24], ["2026-11-30", 0.23]]},
                    {"side": "PUT", "trigger": "session high >=3.07, then 15:50 ET price 3.00-3.20", "targets": [2.86],
                     "contract": f"{ticker}270115P00003000", "max_pay": 0.19, "stop": "15:50 ET price > 3.26",
                     "gtc": [["entry", 0.33], ["2026-11-30", 0.32]]}])
    base.update(over)
    return base


def legs(tickets):
    return {(t["ticker"], t["side"]): t for t in tickets}


def test_every_branch_on_the_card_is_its_own_ticket(tmp_path):
    root = handoff(tmp_path, {"lab_2026-11-20": [two_sided()]})

    tickets = legs(ticket_ready.build_tickets(root, TODAY, macro_state=None))

    call, put = tickets[("GRB", "CALL")], tickets[("GRB", "PUT")]
    assert call["entry_order"] == "BUY TO OPEN 1 GRB270115C00003000 LIMIT live mid DAY (never above 0.16)"
    assert put["entry_order"] == "BUY TO OPEN 1 GRB270115P00003000 LIMIT live mid DAY (never above 0.19)"
    assert call["criteria"] == "15:50 ET price 2.75-2.85" and call["stop"] == "15:50 ET price < 2.70"
    assert call["leg"] == "BRANCH" and put["leg"] == "PRIMARY"


def test_the_exit_is_the_branch_step_in_force_today(tmp_path):
    root = handoff(tmp_path, {"lab_2026-11-20": [two_sided()]})

    on_the_20th = legs(ticket_ready.build_tickets(root, date(2026, 11, 20), macro_state=None))
    on_the_26th = legs(ticket_ready.build_tickets(root, date(2026, 11, 26), macro_state=None))

    assert on_the_20th[("GRB", "CALL")]["exit_order"] == "SELL TO CLOSE 1 GRB270115C00003000 LIMIT 0.25 GTC"
    assert on_the_26th[("GRB", "CALL")]["exit_order"] == "SELL TO CLOSE 1 GRB270115C00003000 LIMIT 0.24 GTC"
    assert on_the_20th[("GRB", "PUT")]["exit_order"] == "SELL TO CLOSE 1 GRB270115P00003000 LIMIT 0.33 GTC"   # the "entry" step


def test_a_fill_belongs_to_the_leg_named_on_the_order(tmp_path):
    filled = two_sided(order_placed="BTO 1 GRB270115C00003000 limit 0.15, filled 20:30Z",
                       fill={"quantity": 1, "price": 0.15, "filled_at_utc": "2026-11-20T20:30:42Z"})
    root = handoff(tmp_path, {"lab_2026-11-20": [filled]})

    tickets = legs(ticket_ready.build_tickets(root, TODAY, macro_state=None))

    assert tickets[("GRB", "CALL")]["state"] == "FILLED" and "FILLED_NO_RESTING_EXIT" in tickets[("GRB", "CALL")]["flags"]
    assert tickets[("GRB", "PUT")]["state"] == "WAITING" and not tickets[("GRB", "PUT")]["fill"]


def test_a_fill_with_no_leg_named_goes_to_the_primary_and_says_so(tmp_path):
    filled = two_sided(order_placed="yes", fill={"quantity": 1, "price": 0.18})
    root = handoff(tmp_path, {"lab_2026-11-20": [filled]})

    tickets = legs(ticket_ready.build_tickets(root, TODAY, macro_state=None))

    assert tickets[("GRB", "PUT")]["state"] == "FILLED" and "FILL_LEG_NOT_STATED" in tickets[("GRB", "PUT")]["flags"]
    assert tickets[("GRB", "CALL")]["state"] == "WAITING"


def test_a_branch_that_names_two_contracts_orders_the_first_and_names_the_other(tmp_path):
    nv = card("NVD", contract="NVD261218C00170000", branches=[
        {"side": "CALL", "trigger": "gap up holds VWAP", "targets": ["gap level"],
         "contract": "NVD  261218C00170000 / 261127C00165000", "max_pay": "6.15 / 4.95"},
        {"side": "PUT", "trigger": "gap down fails VWAP", "targets": ["gap level"],
         "contract": "NVD  261218P00140000 / 261127P00145000", "max_pay": "5.90 / 5.05"}])
    root = handoff(tmp_path, {"lab_2026-11-20": [nv]})

    put = legs(ticket_ready.build_tickets(root, TODAY, macro_state=None))[("NVD", "PUT")]

    assert put["contract"] == "NVD261218P00140000"
    assert "(never above 5.90)" in put["entry_order"]
    assert "MORE_THAN_ONE_CONTRACT_ON_BRANCH" in put["flags"] and "261127P00145000" in put["alternatives"]
    assert "EXIT_NOT_ON_CARD" in put["flags"]            # a counter branch with no exit price of its own


def test_a_branch_with_no_contract_is_listed_with_the_gap_named(tmp_path):
    nc = card("NOC", branches=[{"side": "CALL", "trigger": "t", "targets": [1], "contract": "", "max_pay": 1.0},
                               {"side": "PUT", "trigger": "t", "targets": [1], "contract": "NOC261218P00020000", "max_pay": 1.0}])
    root = handoff(tmp_path, {"lab_2026-11-20": [nc]})

    tickets = legs(ticket_ready.build_tickets(root, TODAY, macro_state=None))

    assert "CONTRACT_NOT_ON_CARD" in tickets[("NOC", "CALL")]["flags"]
    assert tickets[("NOC", "PUT")]["contract"] == "NOC261218P00020000"
