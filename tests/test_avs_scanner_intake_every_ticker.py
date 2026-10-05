"""Scanner intake (ACK 4 Oct 2026): every scanned ticker runs the line; an old scan is used and its age stated.

Found on run 20261003_213716:
- A manifest more than 24h old was discarded whole: no scanner context reached any of the 1,557 rows (6 of the
  last 15 Evening runs).
- The age compared the scanner's local time with UTC, adding an hour in UK summer time.
- Only NEW GO/PROBE tickers were added to the run; GOOG, TQQQ, SQQQ, ARKF, ARKG were scanned but never ran
  because the scanner called them "known" while the universe file did not hold them.
ACK: "even if they not in the universe the scanner should run."
Business rules:
- Every ticker the scanner scanned enters the run, whatever its VMS decision and universe membership.
- An old scan is used, flagged stale, with its age measured in UTC.
"""
import json
from datetime import datetime, timedelta, timezone

import pandas as pd

import intelligent_orchestrator as orch


def _manifest(tmp_path, monkeypatch, *, hours_old, tickers):
    at_utc = datetime.now(timezone.utc) - timedelta(hours=hours_old)
    local = at_utc.astimezone().replace(tzinfo=None)                 # the scanner writes local time here
    board = tmp_path / "vms.csv"
    pd.DataFrame({"ticker": list(tickers), "decision": list(tickers.values())}).to_csv(board, index=False)
    manifest = {"run_id": "S1", "timestamp": local.isoformat(), "max_age_hours": 24,
                "scanner_manifest_at": at_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "go_new": [], "go_known": [t for t, d in tickers.items() if d == "GO"],
                "probe_new": [], "probe_known": [], "tiers_run": ["TIER1"],
                "files": {"vms_scoreboard": str(board)},
                "tickers": {t: {"signal_run_id": "S1"} for t in tickers}}
    path = tmp_path / "scanner_manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(orch.cfg, "UNIVERSE_SCANNER_MANIFEST", path, raising=False)


def test_old_scan_is_used_and_flagged_with_its_utc_age(tmp_path, monkeypatch):
    _manifest(tmp_path, monkeypatch, hours_old=47.0, tickers={"AAA": "GO"})
    scanner = orch.load_scanner_manifest()
    assert scanner["available"] is True
    assert scanner["scanner_stale"] is True
    assert abs(scanner["age_hrs"] - 47.0) < 0.2


def test_fresh_scan_is_not_flagged(tmp_path, monkeypatch):
    _manifest(tmp_path, monkeypatch, hours_old=2.0, tickers={"AAA": "GO"})
    scanner = orch.load_scanner_manifest()
    assert scanner["scanner_stale"] is False and abs(scanner["age_hrs"] - 2.0) < 0.2


def test_every_scanned_ticker_enters_the_run(tmp_path, monkeypatch):
    _manifest(tmp_path, monkeypatch, hours_old=2.0,
              tickers={"GOOG": "GO", "TQQQ": "WAIT", "SQQQ": "BLOCK", "AAPL": "PROBE"})
    universe = tmp_path / "universe.csv"
    pd.DataFrame({"ticker": ["AAPL", "MSFT"]}).to_csv(universe, index=False)
    monkeypatch.setattr(orch.cfg, "UNIVERSE_FILE", universe, raising=False)
    monkeypatch.setattr(orch.cfg, "RUNS_DIR", tmp_path / "runs", raising=False)
    scanner = orch.load_scanner_manifest()
    assert set(scanner["all_scanned"]) == {"GOOG", "TQQQ", "SQQQ", "AAPL"}
    path = orch.build_augmented_universe(scanner, "R1")
    tickers = pd.read_csv(path).iloc[:, 0].tolist()
    assert set(tickers) == {"GOOG", "TQQQ", "SQQQ", "AAPL", "MSFT"} and len(tickers) == 5


def test_the_stale_flag_travels_with_the_scanner_fields_to_the_book():
    # Change 4 (ACK 5 Oct 2026): run 20261005_072245 carried scanner_age_hrs but not scanner_stale into the book.
    from contracts.handoff_contract import SCANNER_FIELD_NAMES
    assert "scanner_stale" in SCANNER_FIELD_NAMES and "scanner_age_hrs" in SCANNER_FIELD_NAMES
