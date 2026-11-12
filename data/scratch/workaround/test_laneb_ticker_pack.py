"""Lane B Fix B, B6: packs start from the Lab card and live in one folder per session.

Synthetic Lab publication in a temp folder: no live data, no network.
Run (PowerShell, repo root):
    venv\\Scripts\\python.exe -m pytest data\\scratch\\workaround\\test_laneb_ticker_pack.py -q -p no:cacheprovider --basetemp=%TEMP%\\avs_lp
"""
from __future__ import annotations

import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "tools"))
import ticker_pack                                      # noqa: E402
from test_laneb_lab_handoff import RUN, publish         # noqa: E402


@pytest.fixture
def world(tmp_path, monkeypatch):
    runs = publish(tmp_path)
    monkeypatch.setattr(ticker_pack, "RUNS_DIR", runs)
    monkeypatch.setattr(ticker_pack, "OUT_ROOT", tmp_path / "packs")
    monkeypatch.setattr(ticker_pack, "PRICE_DB", tmp_path / "no_prices.sqlite")
    monkeypatch.setattr(ticker_pack, "BOARD_SNAPSHOTS", tmp_path / "no_board")
    return tmp_path


def pack(*tickers, session="2026-11-12"):
    ticker_pack.main([*tickers, "--run", RUN, "--session", session])


def test_pack_opens_with_the_lab_card_equal_to_the_published_row(world):
    pack("AAA")
    folder = world / "packs" / "2026-11-12"
    with zipfile.ZipFile(folder / "AAA_pack.zip") as zf:
        assert zf.namelist()[0] == "AAA/lab_card.json", "the Lab card is the first file of the pack"
        card = json.loads(zf.read("AAA/lab_card.json"))
    assert card["card"]["anticipated_level"] == 107.9199 and card["card"]["contract_symbol"] == "AAA270115C00090000"
    assert set(card["evidence"]) == {"structure", "option_risk", "context", "morning"}
    assert card["lab_revision"] == "a" * 32 and len(card["lab_database_sha256"]) == 64
    manifest = json.loads((folder / "AAA" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["lab_revision"] == "a" * 32
    assert manifest["files"]["lab_card.json"]["status"] == "PRESENT"


def test_a_later_batch_lands_in_the_same_session_folder(world):
    pack("AAA", "GOO")
    pack("BBB")
    folders = [p.name for p in (world / "packs").iterdir()]
    assert folders == ["2026-11-12"], "one folder per session, never a second one"
    names = {p.name for p in (world / "packs" / "2026-11-12").glob("*_pack.zip")}
    assert names == {"AAA_pack.zip", "GOO_pack.zip", "BBB_pack.zip"}
    index = json.loads((world / "packs" / "2026-11-12" / "packs_index.json").read_text(encoding="utf-8"))
    assert set(index["tickers"]) == {"AAA", "GOO", "BBB"} and index["lab_revision"] == "a" * 32


def test_a_ticker_the_lab_does_not_publish_still_gets_a_pack_and_says_so(world):
    pack("ZZZ")
    manifest = json.loads((world / "packs" / "2026-11-12" / "ZZZ" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"]["lab_card.json"]["status"] == "TICKER_ABSENT_FROM_LAB"
    assert not (world / "packs" / "2026-11-12" / "ZZZ" / "lab_card.json").exists()


def test_refuses_when_the_lab_publication_is_not_complete(world):
    m = world / "runs" / RUN / "intelligence_lab" / "review_projection" / "manifest.json"
    j = json.loads(m.read_text()); j["publication_state"] = "BUILDING"; m.write_text(json.dumps(j))
    with pytest.raises(SystemExit) as stop:
        pack("AAA")
    assert "COMPLETE" in str(stop.value)
    assert not (world / "packs").exists()


def test_refuses_when_the_lab_was_published_before_the_morning_run_finished(world):
    morning = world / "runs" / RUN / "morning_validation"
    morning.mkdir()
    f = morning / f"morning_validated_trades_{RUN}.csv"
    f.write_text("ticker\nAAA\n", encoding="utf-8")
    late = 1794700000   # 2026-11-14, after the publication time in the manifest (2026-11-12T20:19Z)
    os.utime(f, (late, late))
    with pytest.raises(SystemExit) as stop:
        pack("AAA")
    assert "older than the run's Morning" in str(stop.value)


def test_the_ticker_nan_is_found_in_run_files(world):
    src = world / "t.csv"
    src.write_text("ticker,x\nNAN,1\nAAA,2\nNA,3\n", encoding="utf-8")
    hits, problem = ticker_pack.filter_csv(src, {"NAN", "NA"})
    assert problem is None and len(hits["NAN"]) == 1 and len(hits["NA"]) == 1
