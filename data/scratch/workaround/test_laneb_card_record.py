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
