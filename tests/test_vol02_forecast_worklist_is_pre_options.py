"""VOL-02 (runner half): the price forecast needs prices, not the Options output.

Business rule (ACK, 21 Nov 2026: worklist approved; Codex brief BF-01 / VOL-02):

  The volatility forecast is produced from the run's pinned Discovery candidates, the same file
  Options Intelligence reads, so it can run before Options and covers the same tickers. It does
  not need the SuperBrain file, the Options file or the execution layer to exist. A missing 30-day
  IV leaves the price forecast usable. Prices are read up to the run's evidence session, never
  "today". The runner records which worklist and session it actually used.

Legacy behaviour replaced: the ticker list came from superbrain_enriched_<run>.csv, which is
written after Options Intelligence, and the provider fallback asked for bars up to date.today().

Not covered here: moving the stage in the Evening workflow (intelligent_orchestrator.py), which
is the other half of VOL-02.

Isolated: temporary run folder, synthetic bars, no provider, no network.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import garch_runner as runner

RUN_ID = "20261119_234734"
SESSION = "2026-11-19"


def _bars(n: int = 320) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
    days = pd.bdate_range(end=SESSION, periods=n)
    return pd.DataFrame({"date": days, "open": close * 0.998, "high": close * 1.01,
                         "low": close * 0.99, "close": close, "volume": 1_000_000})


@pytest.fixture
def run(tmp_path, monkeypatch):
    root = tmp_path / RUN_ID
    (root / "discovery").mkdir(parents=True)
    worklist = root / "discovery" / f"discovery_candidates_ultimate_{RUN_ID}.csv"
    worklist.write_text("ticker,phase\nAAA,C\nbbb,D\n", encoding="utf-8")
    (root / "run_meta.json").write_text(
        json.dumps({"canonical_run_id": RUN_ID, "dynamic_plan": {"last_completed_session": SESSION}}),
        encoding="utf-8")
    seen: list = []

    def fetch(ticker, bars=runner.PRICE_BARS, as_of=None):
        seen.append((ticker, as_of))
        return _bars()

    monkeypatch.setattr(runner, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(runner, "_fetch_ohlcv", fetch)
    monkeypatch.setattr(runner, "RATE_SLEEP", 0)
    monkeypatch.setattr(runner, "_load_regime", lambda _base: "UNKNOWN")
    return root, worklist, seen


def test_forecast_runs_from_the_discovery_worklist_with_no_options_or_superbrain_file(run):
    root, worklist, _ = run

    out = runner.run_garch_batch(RUN_ID)

    rows = pd.read_csv(out)
    assert sorted(rows["ticker"]) == ["AAA", "BBB"]
    assert not (root / "superbrain").exists() and not (root / "options").exists()
    # a price forecast exists although no 30-day IV was available yet
    assert rows["l3_forward_realised_vol"].notna().all()
    assert set(rows["l3_iv_input_state"]) == {"IV_MISSING"}


def test_prices_are_read_up_to_the_evidence_session_not_today(run):
    _, _, seen = run

    runner.run_garch_batch(RUN_ID)

    assert {as_of for _, as_of in seen} == {date(2026, 11, 19)}


def test_the_runner_records_what_it_actually_consumed(run):
    root, worklist, _ = run

    runner.run_garch_batch(RUN_ID)

    receipt = json.loads((root / "qomega" / f"garch_forecast_receipt_{RUN_ID}.json").read_text(encoding="utf-8"))
    assert receipt["worklist_kind"] == "DISCOVERY_CANDIDATES"
    assert receipt["worklist_sha256"] == hashlib.sha256(worklist.read_bytes()).hexdigest()
    assert receipt["worklist_ticker_count"] == 2
    assert receipt["evidence_session"] == SESSION
    assert receipt["iv_benchmark_rows_available"] == 0


def test_a_missing_worklist_stops_with_its_name_and_never_falls_back(run):
    root, worklist, _ = run
    worklist.unlink()
    (root / "superbrain").mkdir()
    (root / "superbrain" / f"superbrain_enriched_{RUN_ID}.csv").write_text("ticker\nZZZ\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="discovery_candidates_ultimate"):
        runner.run_garch_batch(RUN_ID)


def test_an_explicit_legacy_list_is_still_honoured_and_labelled(run, tmp_path):
    root, _, _ = run
    legacy = tmp_path / "legacy.csv"
    legacy.write_text("ticker\nZZZ\n", encoding="utf-8")

    out = runner.run_garch_batch(RUN_ID, superbrain_csv=legacy)

    assert list(pd.read_csv(out)["ticker"]) == ["ZZZ"]
    receipt = json.loads((root / "qomega" / f"garch_forecast_receipt_{RUN_ID}.json").read_text(encoding="utf-8"))
    assert receipt["worklist_kind"] == "EXPLICIT_LEGACY_LIST"


def test_no_run_metadata_is_stated_not_guessed(run):
    root, _, seen = run
    (root / "run_meta.json").unlink()

    runner.run_garch_batch(RUN_ID)

    assert {as_of for _, as_of in seen} == {None}
    receipt = json.loads((root / "qomega" / f"garch_forecast_receipt_{RUN_ID}.json").read_text(encoding="utf-8"))
    assert receipt["evidence_session"] is None
    assert receipt["evidence_session_state"] == "RUN_METADATA_UNAVAILABLE"
