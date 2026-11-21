"""AVS-ARCH-LB-001 D1, D1a, D1b (ACK accepted 21 Nov 2026; "Yes, card record"): the card is one data record.

Business rules:
- D1: one record per card is the single source of truth. Its fields are the ones this week's 33 decision files already
  carry, plus the card standard's own parts (thesis sentence, lifecycle stage, market-player read, liquidity, macro
  kill switch, 52-week check, sources).
- D1a: the checker rejects a record whose core fields are missing or wrong: no ticker or ledger id, a contract that is
  not an option symbol or not on this ticker, an expiry on or before the card day, a size that is not a whole number,
  a branch with no contract or side. Missing is never neutral: every gap is named.
- The card standard's parts are reported as gaps. They become rejections when the checker is run strict; until ACK
  switches that on they are flags, in line with "no step is a hard gate until confidence is earned".
- D1b: a later version of a card cannot silently drop a field the earlier one had. A dropped field must be listed with
  its reason; otherwise the new version is rejected and the dropped fields are named.
- A decision file written before the record existed is read as it is; nothing is invented to make it pass.

Run (PowerShell, repo root):
    venv\\Scripts\\python.exe -m pytest data\\scratch\\workaround\\test_laneb_card_record.py -q -p no:cacheprovider --basetemp=%TEMP%\\avs_cr
Isolated: in-memory records and temporary files only.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import card_record as cr  # noqa: E402


def record(**over):
    base = {
        "record_version": "card_record_v1", "ledger_id": "2026-11-20_GRAB_CALL", "ticker": "GRAB", "handoff_side": "CALL",
        "card_side": "PUT primary + CALL counter", "decision": "WATCH", "final_action": "TRADE_ON_TRIGGER",
        "decision_reason": "Plugins LONG/Medium; vs hand-off PARTLY", "states": {"direction": "UNRESOLVED", "contract": "SUITABLE"},
        "contract": "GRAB270115P00003000", "entry_type": "15:50 ET price 3.00-3.20", "close_zone_low": 3.0, "close_zone_high": 3.2,
        "extra_conditions": ["Never hold both legs"], "limit": "live mid", "max_pay": 0.19, "size": 1, "stop": 3.26,
        "targets": [2.86, 2.75], "time_stop": "2026-12-18 15:50 ET",
        "one_contract_exit": {"target_stock": 2.75, "target_option_price": 0.33, "stop": 3.26},
        "events_in_hold": ["2026-11-25 PCE"], "discriminator": {"up": 3.26, "down": 2.7},
        "invalidation": {"trade": {"v": 3.26, "on": "15:50 ET price above"}},
        "branches": [{"side": "CALL", "trigger": "15:50 ET price 2.75-2.85", "targets": [3.06], "contract": "GRAB270115C00003000", "max_pay": 0.16},
                     {"side": "PUT", "trigger": "session high >=3.07", "targets": [2.86], "contract": "GRAB270115P00003000", "max_pay": 0.19}],
        "lane": "base", "card_version": 1, "challenge": "self", "checked": "self", "run_id": "20261119_234734",
        "created_utc": "2026-11-20T15:48:51+00:00",
        # the card standard's own parts
        "thesis": {"macro": "credit is tightening", "sector": "SE-Asia internet is offered", "ticker": "GRAB failed at 3.07",
                   "move": "gain 70% at 2.75", "by": "2026-12-04", "unless": "a 15:50 ET price above 3.26"},
        "lifecycle_stage": 4, "player_read": "macro EM sellers in control; company buyback is the floor",
        "liquidity": {"tier": "A", "spread_pct_mid": 6.1, "oi": 2350},
        "macro_dependency": {"kill_switch": "KS0-VOL-CREDIT: VIX close above 20 with HY OAS widening"},
        "resistance_test": {"extreme": 2.67, "verdict": "pays if the level holds"},
        "sources": ["Lab card 20261119_234734", "Tastytrade live 15:36Z", "pack 2026-11-20"], "lab_rank": 412,
    }
    base.update(over)
    return base


def rules(result):
    return {issue["rule"] for issue in result["errors"]}


# ---------------------------------------------------------------- D1a: the checker
def test_a_complete_record_is_accepted():
    result = cr.check_record(record())
    assert result["verdict"] == "ACCEPTED" and result["errors"] == [] and result["standard_gaps"] == []


def test_core_fields_missing_are_each_named_and_the_record_is_rejected():
    broken = record()
    for field in ("ticker", "contract", "branches", "size"):
        broken.pop(field)
    result = cr.check_record(broken)
    assert result["verdict"] == "REJECTED"
    assert {issue["field"] for issue in result["errors"] if issue["rule"] == "CORE_FIELD_MISSING"} >= {"ticker", "contract", "branches", "size"}


def test_the_contract_must_be_an_option_on_this_ticker_expiring_after_the_card_day():
    assert "CONTRACT_NOT_AN_OPTION_SYMBOL" in rules(cr.check_record(record(contract="the Jan 3 put")))
    assert "CONTRACT_ON_ANOTHER_TICKER" in rules(cr.check_record(record(contract="SE270115P00003000")))
    assert "CONTRACT_EXPIRES_ON_OR_BEFORE_CARD_DAY" in rules(cr.check_record(record(contract="GRAB261120P00003000")))


def test_numbers_are_numbers_and_dates_are_dates():
    assert "SIZE_NOT_A_WHOLE_NUMBER" in rules(cr.check_record(record(size="1 contract (test month)")))
    assert "CREATED_UTC_NOT_A_DATE" in rules(cr.check_record(record(created_utc="yesterday afternoon")))
    assert "LEDGER_ID_DOES_NOT_MATCH_TICKER" in rules(cr.check_record(record(ledger_id="2026-11-20_SE_CALL")))


def test_every_branch_needs_a_side_a_trigger_and_a_contract_on_this_ticker():
    bad = record()
    bad["branches"] = [{"side": "LONG", "trigger": "", "contract": "", "max_pay": 0.1},
                       {"side": "PUT", "trigger": "t", "contract": "SE270115P00003000", "max_pay": 0.1}]
    found = rules(cr.check_record(bad))
    assert {"BRANCH_SIDE_NOT_CALL_OR_PUT", "BRANCH_TRIGGER_MISSING", "BRANCH_CONTRACT_MISSING", "BRANCH_CONTRACT_ON_ANOTHER_TICKER"} <= found


def test_one_sided_card_must_say_why():
    one = record()
    one["branches"] = one["branches"][:1]
    assert "ONE_SIDE_WITHOUT_A_REASON" in rules(cr.check_record(one))
    assert "ONE_SIDE_WITHOUT_A_REASON" not in rules(cr.check_record(dict(one, both_sides_reason="put side has no contract under the cap")))


def test_the_card_standards_parts_are_gaps_until_strict_is_switched_on():
    thin = record()
    for field in ("thesis", "lifecycle_stage", "player_read", "liquidity", "macro_dependency", "resistance_test", "sources", "lab_rank"):
        thin.pop(field)
    relaxed = cr.check_record(thin)
    assert relaxed["verdict"] == "ACCEPTED_WITH_GAPS" and relaxed["errors"] == []
    assert {gap["field"] for gap in relaxed["standard_gaps"]} == {"thesis", "lifecycle_stage", "player_read", "liquidity",
                                                                 "macro_dependency.kill_switch", "resistance_test", "sources", "lab_rank"}
    assert cr.check_record(thin, strict=True)["verdict"] == "REJECTED"


def test_thesis_parts_lifecycle_range_and_kill_switch_are_checked_inside():
    gaps = lambda r: {gap["field"] for gap in cr.check_record(r)["standard_gaps"]}   # noqa: E731
    assert "thesis.unless" in gaps(record(thesis={k: v for k, v in record()["thesis"].items() if k != "unless"}))
    assert "lifecycle_stage" in gaps(record(lifecycle_stage=9))
    assert "macro_dependency.kill_switch" in gaps(record(macro_dependency={"gate": "XLF"}))


# ---------------------------------------------------------------- reading a decision file written before the record
def test_an_older_decision_file_is_read_as_it_is_and_nothing_is_invented():
    old = record()
    for field in ("record_version", "thesis", "lifecycle_stage", "player_read", "sources", "lab_rank"):
        old.pop(field)
    old.update(narrative_stage=4, controlling_player="macro EM sellers", size="1 contract")
    read = cr.from_decision(old)
    assert read["record_version"] == "card_record_v1" and read["record_origin"] == "DECISION_FILE"
    assert read["lifecycle_stage"] == 4 and read["player_read"] == "macro EM sellers" and read["size"] == 1
    assert "thesis" not in read and "sources" not in read                       # absent stays absent
    assert old["size"] == "1 contract" and "record_version" not in old           # the input is not changed


# ---------------------------------------------------------------- D1b: versions cannot silently drop data
def test_a_new_version_that_silently_drops_a_field_is_rejected_and_the_field_is_named():
    first = record()
    second = record(card_version=2, supersedes=first["ledger_id"])
    second.pop("resistance_test")
    second["one_contract_exit"] = {"target_stock": 2.75}                         # dropped target_option_price and stop
    result = cr.check_supersede(first, second)
    assert result["verdict"] == "REJECTED"
    assert set(result["silently_dropped"]) == {"resistance_test", "one_contract_exit.target_option_price", "one_contract_exit.stop"}


def test_a_dropped_field_with_a_reason_is_allowed_and_changes_are_listed():
    first = record()
    second = record(card_version=2, supersedes=first["ledger_id"], max_pay=0.21,
                    dropped_fields={"resistance_test": "52-week low broken on 21 Nov; test no longer applies"})
    second.pop("resistance_test")
    result = cr.check_supersede(first, second)
    assert result["verdict"] == "ACCEPTED" and result["silently_dropped"] == []
    assert "max_pay" in result["changed"] and "resistance_test" in result["dropped_with_reason"]


def test_a_version_must_move_forward_and_name_what_it_replaces():
    first = record()
    assert "VERSION_NOT_HIGHER" in cr.check_supersede(first, record(card_version=1, supersedes=first["ledger_id"]))["errors"]
    assert "SUPERSEDES_NOT_STATED" in cr.check_supersede(first, record(card_version=2))["errors"]


# ---------------------------------------------------------------- files
def test_the_checker_reads_a_folder_and_writes_one_report(tmp_path):
    folder = tmp_path / "lab_2026-11-20" / "decisions"
    folder.mkdir(parents=True)
    (folder / "GRAB.json").write_text(json.dumps(record()), encoding="utf-8")
    broken = copy.deepcopy(record(ticker="SE", ledger_id="2026-11-20_SE_PUT", contract="not a contract"))
    (folder / "SE.json").write_text(json.dumps(broken), encoding="utf-8")
    (folder / "BAD.json").write_text("{not json", encoding="utf-8")

    report = cr.check_folder(folder.parent)

    by_ticker = {row["ticker"]: row for row in report["cards"]}
    assert by_ticker["GRAB"]["verdict"] == "ACCEPTED" and by_ticker["SE"]["verdict"] == "REJECTED"
    assert by_ticker["BAD"]["verdict"] == "UNREADABLE"
    assert report["counts"] == {"ACCEPTED": 1, "REJECTED": 1, "UNREADABLE": 1}
    out = cr.write_report(report, tmp_path / "out", "2026-11-20")
    assert out.name == "card_check_2026-11-20.md" and "SE" in out.read_text(encoding="utf-8")
    assert json.loads((folder / "GRAB.json").read_text(encoding="utf-8")) == record()   # the card files are never changed


# ---------------------------------------------------------------- the board row comes from the record (D5 of the fix list)
# Board row shape read from the 36 hand-written rows of 16, 18 and 20 Nov and from board_page_v19.html:
# t, side, group, url, occ, con, rungs[{lo, hi, max{fixed | ladder}, label}], stop{dir, v}, targetStock, gtcSteps,
# exit, exitWhy, from, until, cardDay, at1550, manual, gates, review, built, stockDvM, supersedes.
def board_record(**over):
    base = record(artifact_url="https://claude.ai/artifact/abc", window_start="2026-11-20", window_end="2026-12-04",
                  liquidity={"tier": "A", "spread_pct_mid": 6.1, "oi": 2350, "stock_dv_m": 259.7},
                  extra_conditions=["Never hold both legs", "Put spread no wider than 0.03 at entry"])
    base["branches"] = [
        {"side": "CALL", "trigger": "15:50 ET price 2.75-2.85, session low >=2.71", "targets": [3.06, 3.18],
         "contract": "GRAB270115C00003000", "max_pay": 0.16, "stop": 2.7, "zone_low": 2.75, "zone_high": 2.85,
         "gtc": [["2026-11-20", 0.25], ["2026-11-25", 0.24]], "time_stop": "2026-12-08 15:50 ET", "from": "2026-11-20", "until": "2026-11-25"},
        {"side": "PUT", "trigger": "session high >=3.07, then 15:50 ET price 3.00-3.20", "targets": [2.86, 2.75],
         "contract": "GRAB270115P00003000", "max_pay": 0.19, "gtc": [["entry", 0.33], ["2026-11-30", 0.32]],
         "gates": [{"s": "KWEB", "op": "<=", "v": 21.31, "label": "KWEB at or under 21.31"}]}]
    base.update(over)
    return base


def rows_by_side(rec):
    return {row["data"]["side"]: row for row in cr.to_board_rows(rec)}


def test_every_branch_becomes_one_board_row_named_by_its_side():
    rows = cr.to_board_rows(board_record())
    assert [row["doc_id"] for row in rows] == ["2026-11-20_GRAB_CALL", "2026-11-20_GRAB_PUT"]
    assert all(row["collection"] == "cards" and row["derived_from"] == "card_record_v1" for row in rows)
    call = rows[0]["data"]
    assert (call["t"], call["side"], call["group"], call["occ"], call["con"]) == ("GRAB", "CALL", "today", "GRAB270115C00003000", "Jan 15 3C")
    assert call["url"] == "https://claude.ai/artifact/abc" and call["cardDay"] == "2026-11-20"


def test_the_entry_rung_stop_target_and_exit_ladder_are_numbers_from_the_branch():
    call = rows_by_side(board_record())["CALL"]["data"]
    assert call["rungs"] == [{"lo": 2.75, "hi": 2.85, "max": {"fixed": 0.16}, "label": "15:50 ET price 2.75-2.85, session low >=2.71",
                              "from": "2026-11-20", "until": "2026-11-25"}]
    assert call["stop"] == {"dir": "below", "v": 2.7} and call["targetStock"] == 3.06
    assert call["gtcSteps"] == [["2026-11-20", 0.25], ["2026-11-25", 0.24]]
    assert call["exit"] == "2026-12-08" and call["at1550"] is True
    assert call["from"] == "2026-11-20" and call["until"] == "2026-11-25" and call["stockDvM"] == 259.7
    assert call["manual"] == ["Never hold both legs", "Put spread no wider than 0.03 at entry"]


def test_the_primary_branch_takes_the_cards_own_zone_stop_and_exit():
    put = rows_by_side(board_record())["PUT"]
    data = put["data"]
    assert data["rungs"][0]["lo"] == 3.0 and data["rungs"][0]["hi"] == 3.2 and data["rungs"][0]["max"] == {"fixed": 0.19}
    assert data["stop"] == {"dir": "above", "v": 3.26} and data["exit"] == "2026-12-18"
    assert data["gates"] == [{"s": "KWEB", "op": "<=", "v": 21.31, "label": "KWEB at or under 21.31"}]
    assert data["from"] == "2026-11-20" and data["until"] == "2026-12-04"          # the card's own window


def test_a_step_dated_entry_is_not_given_a_date_it_does_not_have():
    put = rows_by_side(board_record())["PUT"]
    assert put["data"]["gtcSteps"] == [["2026-11-30", 0.32]]
    assert any("gtcSteps" in gap and "entry" in gap for gap in put["missing"])


def test_what_the_record_does_not_hold_is_listed_never_invented():
    thin = board_record()
    thin["branches"][0] = {"side": "CALL", "trigger": "15:50 ET price 2.75-2.85", "contract": "GRAB270115C00003000",
                           "max_pay": "live mid", "stop": "15:50 ET price < 2.70"}
    thin.pop("artifact_url")
    call = rows_by_side(thin)["CALL"]
    for field in ("rungs", "stop", "targetStock", "url", "gtcSteps"):
        assert field not in call["data"]
        assert any(gap.startswith(field) for gap in call["missing"]), field
    assert call["data"]["exit"] == "2026-12-18"                                    # falls back to the card's own time stop


def test_supersedes_and_the_build_snapshot_travel_when_the_record_has_them():
    rec = board_record(supersedes="2026-11-18_GRAB_CALL", built={"px": 2.9, "bid": 0.14, "ask": 0.16, "mid": 0.15, "spr": 13.3},
                       review={"date": "2026-11-25", "text": "day-3 review"})
    call = rows_by_side(rec)["CALL"]["data"]
    assert call["supersedes"] == "2026-11-18_GRAB_CALL" and call["built"]["mid"] == 0.15 and call["review"]["date"] == "2026-11-25"
    assert "supersedes" not in rows_by_side(board_record())["CALL"]["data"]


def test_a_record_with_no_branches_gives_one_row_from_the_card_itself():
    rec = board_record()
    rec["branches"] = []
    rows = cr.to_board_rows(rec)
    assert len(rows) == 1 and rows[0]["data"]["occ"] == "GRAB270115P00003000" and rows[0]["data"]["side"] == "PUT"


def test_two_branches_on_one_side_are_two_rungs_of_one_row_each_with_its_own_contract():
    rec = board_record()
    rec["branches"].insert(1, {"side": "CALL", "trigger": "15:50 ET price 2.85-2.95", "contract": "GRAB270115C00003500",
                               "max_pay": 0.09, "zone_low": 2.85, "zone_high": 2.95, "limit": 0.08})
    rows = cr.to_board_rows(rec)
    assert [row["doc_id"] for row in rows] == ["2026-11-20_GRAB_CALL", "2026-11-20_GRAB_PUT"]      # no second CALL row
    rungs = rows[0]["data"]["rungs"]
    assert [(r["lo"], r["hi"], r["occ"], r["con"]) for r in rungs] == [
        (2.75, 2.85, "GRAB270115C00003000", "Jan 15 3C"), (2.85, 2.95, "GRAB270115C00003500", "Jan 15 3.5C")]
    assert rungs[1]["limit"] == 0.08 and rows[0]["data"]["occ"] == "GRAB270115C00003000"
    assert "occ" not in rows[1]["data"]["rungs"][0]                                                 # one contract: said once


def test_a_ladder_written_as_a_sentence_or_one_price_is_named_not_guessed():
    rec = board_record()
    rec["branches"][0]["gtc"] = "0.25 to 25 Nov, 0.24 after"
    rec["branches"][1]["gtc"] = 0.33
    for row in cr.to_board_rows(rec):
        assert "gtcSteps" not in row["data"] and any(gap.startswith("gtcSteps") for gap in row["missing"])


def test_a_stop_already_in_the_boards_shape_is_kept():
    rec = board_record()
    rec["branches"][0]["stop"] = {"dir": "below", "v": 2.7}
    assert rows_by_side(rec)["CALL"]["data"]["stop"] == {"dir": "below", "v": 2.7}


def test_board_row_files_are_named_by_doc_id_and_never_written_over(tmp_path):
    paths = cr.write_board_rows(board_record(), tmp_path)
    assert [p.name for p in paths] == ["board_row_2026-11-20_GRAB_CALL.json", "board_row_2026-11-20_GRAB_PUT.json"]
    saved = json.loads(paths[0].read_text(encoding="utf-8"))
    assert saved["doc_id"] == "2026-11-20_GRAB_CALL" and saved["collection"] == "cards" and saved["data"]["t"] == "GRAB"
    with pytest.raises(FileExistsError):
        cr.write_board_rows(board_record(), tmp_path)
