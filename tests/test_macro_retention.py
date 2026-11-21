"""Rolling 10-session clean-up of macro JSON archives (ACK 20 Nov 2026: "yes add the 10-session clean-up").

Raw copies older than 10 completed US sessions are removed. Anything still in use is never removed: files a
board build of the last 10 sessions used, the currently accepted feed files and every source the events ledger
cites. If what is in use cannot be read, that folder is left alone. The macro packet archive is not touched
(pipeline replays bind to it). Business rules, written before the code."""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from scripts import macro_retention as mr

SESSIONS = [date(2026, 11, d) for d in (2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 16, 17, 18, 19, 20)]
OLD = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc).timestamp()      # before the 10-session window
NEW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc).timestamp()     # inside it


def _file(path: Path, when: float, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.utime(path, (when, when))
    return path


CONFIG = {"sessions": 10, "targets": [
    {"name": "board_inputs", "dir": "macro_board/output/inputs", "rule": "board_inputs",
     "snapshots_dir": "macro_board/output/snapshots"},
    {"name": "feed_archive", "dir": "data/macro/delivery/archive", "rule": "feed_blobs",
     "accepted": "data/macro/delivery/accepted.json", "events_ledger": "data/macro/delivery/events.json"},
    {"name": "quarantine", "dir": "data/macro/delivery/quarantine", "rule": "age"},
]}


def test_the_window_starts_at_the_tenth_most_recent_completed_session():
    start = mr.keep_from(SESSIONS, 10)
    assert start.astimezone(mr.NEW_YORK).date() == date(2026, 11, 9)
    assert start.astimezone(mr.NEW_YORK).hour == 0


def test_board_input_copies_are_kept_when_a_recent_build_used_them_however_old_the_file(tmp_path):
    inputs = tmp_path / "macro_board/output/inputs"
    used_old = _file(inputs / "aaaa_SPY_latest.json", OLD)
    unused_old = _file(inputs / "bbbb_XLK_latest.json", OLD)
    unused_new = _file(inputs / "cccc_XLF_latest.json", NEW)
    snaps = tmp_path / "macro_board/output/snapshots"
    _file(snaps / "board_2026-11-18.json", NEW, json.dumps(
        {"as_of_session": "2026-11-18", "inputs": {"holdings_SPY": {"archived_as": "aaaa_SPY_latest.json"}}}))
    _file(snaps / "board_2026-11-03.json", OLD, json.dumps(                 # an old build protects nothing
        {"as_of_session": "2026-11-03", "inputs": {"holdings_XLK": {"archived_as": "bbbb_XLK_latest.json"}}}))
    plan = mr.plan(CONFIG, tmp_path, mr.keep_from(SESSIONS, 10))
    doomed = {Path(p["path"]).name for p in plan["delete"]}
    assert doomed == {"bbbb_XLK_latest.json"}
    assert used_old.exists() and unused_new.exists() and unused_old.exists()   # planning deletes nothing


def test_feed_files_in_use_are_kept_and_old_unused_ones_go(tmp_path):
    arch = tmp_path / "data/macro/delivery/archive"
    for sha in ("acc", "evt", "old", "new"):
        _file(arch / f"{sha}.json", NEW if sha == "new" else OLD)
    _file(tmp_path / "data/macro/delivery/accepted.json", NEW, json.dumps({"usmi": {"sha256": "acc"}}))
    _file(tmp_path / "data/macro/delivery/events.json", NEW, json.dumps({"e1": {"source_sha256": "evt"}}))
    plan = mr.plan(CONFIG, tmp_path, mr.keep_from(SESSIONS, 10))
    assert {Path(p["path"]).name for p in plan["delete"]} == {"old.json"}


def test_a_folder_whose_in_use_list_cannot_be_read_is_left_alone(tmp_path):
    _file(tmp_path / "data/macro/delivery/archive/old.json", OLD)
    (tmp_path / "data/macro/delivery").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data/macro/delivery/accepted.json").write_text("{not json", encoding="utf-8")
    plan = mr.plan(CONFIG, tmp_path, mr.keep_from(SESSIONS, 10))
    assert plan["delete"] == []
    assert plan["skipped"]["feed_archive"].startswith("cannot read")


def test_age_only_folders_lose_files_older_than_the_window(tmp_path):
    _file(tmp_path / "data/macro/delivery/quarantine/a.json", OLD)
    _file(tmp_path / "data/macro/delivery/quarantine/b.json", NEW)
    plan = mr.plan(CONFIG, tmp_path, mr.keep_from(SESSIONS, 10))
    assert {Path(p["path"]).name for p in plan["delete"]} == {"a.json"}


def test_apply_deletes_only_planned_files_inside_their_folder_and_logs_each_one(tmp_path):
    old = _file(tmp_path / "data/macro/delivery/quarantine/a.json", OLD)
    outside = _file(tmp_path / "keep_me.json", OLD)
    plan = mr.plan(CONFIG, tmp_path, mr.keep_from(SESSIONS, 10))
    plan["delete"].append({"target": "quarantine", "path": str(outside), "bytes": 1})   # tampered entry
    log = tmp_path / "retention.jsonl"
    summary = mr.apply(plan, CONFIG, tmp_path, log)
    assert not old.exists() and outside.exists()
    assert summary["deleted"] == 1 and summary["refused"] == 1
    lines = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert {x["action"] for x in lines} == {"DELETED", "REFUSED"}


def test_the_shipped_config_never_touches_the_macro_packet_archive():
    config = json.loads((Path(__file__).resolve().parents[1] / "config" / "macro_retention_v1.json").read_text(encoding="utf-8"))
    dirs = [t["dir"].replace("\\", "/").rstrip("/") for t in config["targets"]]
    assert "data/macro/archive" not in dirs and config["sessions"] == 10


def test_an_age_folder_keeps_the_files_it_names_however_old(tmp_path):
    # AVS-MACRO-TRIAGE-001 T1: dated ETF intelligence files go with age; the latest file the triage join reads stays
    cfg = {"sessions": 10, "targets": [{"name": "etf_intelligence", "dir": "macro_board/output/etf_intelligence",
                                        "rule": "age", "keep": ["etf_intelligence_latest.json"]}]}
    folder = tmp_path / "macro_board/output/etf_intelligence"
    _file(folder / "etf_intelligence_latest.json", OLD)
    _file(folder / "etf_intelligence_2026-11-03_EVENING.json", OLD)
    _file(folder / "etf_intelligence_2026-11-18_EVENING.json", NEW)
    plan = mr.plan(cfg, tmp_path, mr.keep_from(SESSIONS, 10))
    assert {Path(p["path"]).name for p in plan["delete"]} == {"etf_intelligence_2026-11-03_EVENING.json"}


def test_the_shipped_config_ages_out_dated_etf_intelligence_but_keeps_latest():
    cfg = json.loads((Path(__file__).resolve().parents[1] / "config" / "macro_retention_v1.json").read_text(encoding="utf-8"))
    target = {t["name"]: t for t in cfg["targets"]}["etf_intelligence"]
    assert target["rule"] == "age" and "etf_intelligence_latest.json" in target["keep"]
