"""Lane B Fix B, B10: every card has a decision record; decided-but-not-placed names are reported.

Run (PowerShell, repo root):
    venv\\Scripts\\python.exe -m pytest data\\scratch\\workaround\\test_laneb_collect_decisions.py -q -p no:cacheprovider --basetemp=%TEMP%\\avs_cd
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_decisions  # noqa: E402

SESSION = "2026-11-12"


def folder_with_cards(tmp_path) -> Path:
    folder = tmp_path / f"split_{SESSION}_cap5"
    (folder / "decisions").mkdir(parents=True)
    (folder / f"HSBC_deep_dive_{SESSION}_clean.html").write_text(
        '<html><a href="https://claude.ai/artifact/AbC123xyz">card</a></html>', encoding="utf-8")
    (folder / "CPNG_deep_dive_2026-10-19_v1.html").write_text("<html>old</html>", encoding="utf-8")
    (folder / f"CPNG_deep_dive_{SESSION}.html").write_text("<html>new</html>", encoding="utf-8")
    (folder / f"~$BC_deep_dive_{SESSION}.html").write_text("lock", encoding="utf-8")
    (folder / f"QQQ_daily_{SESSION}.html").write_text("<html>not a card</html>", encoding="utf-8")
    (folder / "decisions" / "CPNG.json").write_text(json.dumps(
        {"ticker": "CPNG", "ledger_id": f"{SESSION}_CPNG_PUT", "decision": "WATCH", "final_action": "TRADE_NOW",
         "contract": "CPNG270319P00018000", "order_placed": ""}), encoding="utf-8")
    return folder


def run(folder, capsys, *extra):
    collect_decisions.main(["--folder", str(folder), *extra])
    return capsys.readouterr().out


def test_a_card_without_a_decision_record_gets_one_marked_decision_missing(tmp_path, capsys):
    folder = folder_with_cards(tmp_path)
    out = run(folder, capsys)
    j = json.loads((folder / "decisions" / "HSBC.json").read_text(encoding="utf-8"))
    assert j["state"] == "CARD_BUILT_DECISION_MISSING" and j["ticker"] == "HSBC" and j["decision"] == ""
    assert j["card_path"].endswith(f"HSBC_deep_dive_{SESSION}_clean.html")
    assert j["artifact_url"] == "https://claude.ai/artifact/AbC123xyz"
    assert "HSBC" in out and "CARD_BUILT_DECISION_MISSING" in out


def test_an_existing_decision_record_is_never_touched(tmp_path, capsys):
    folder = folder_with_cards(tmp_path)
    before = (folder / "decisions" / "CPNG.json").read_bytes()
    out = run(folder, capsys)
    assert (folder / "decisions" / "CPNG.json").read_bytes() == before
    assert "CPNG" in out and "decision record present" in out


def test_only_deep_dive_cards_count_and_lock_files_are_skipped(tmp_path, capsys):
    folder = folder_with_cards(tmp_path)
    run(folder, capsys)
    assert sorted(p.stem for p in (folder / "decisions").glob("*.json")) == ["CPNG", "HSBC"]


def test_dry_run_lists_the_missing_record_and_writes_nothing(tmp_path, capsys):
    folder = folder_with_cards(tmp_path)
    out = run(folder, capsys, "--dry-run")
    assert "HSBC" in out and "would create" in out
    assert not (folder / "decisions" / "HSBC.json").exists()
    assert not list(folder.glob("cards_*.csv")) and not list(folder.glob("order_tickets_*.md"))


def test_decided_but_not_placed_names_are_reported(tmp_path, capsys):
    folder = folder_with_cards(tmp_path)
    (folder / "decisions" / "UHS.json").write_text(json.dumps(
        {"ticker": "UHS", "decision": "TRADE_NOW", "contract": "UHS270115C00200000", "order_placed": "yes 15:51 ET"}), encoding="utf-8")
    out = run(folder, capsys)
    line = [ln for ln in out.splitlines() if "Decided, not placed" in ln][0]
    assert "CPNG" in line, "final_action TRADE_NOW with no recorded order"
    assert "UHS" not in line, "an order is recorded"
    tickets = next(folder.glob("order_tickets_*.md")).read_text(encoding="utf-8")
    assert "## Decided, not placed" in tickets and "25%" not in tickets


def test_works_on_a_folder_with_cards_and_no_triage_file(tmp_path, capsys):
    folder = folder_with_cards(tmp_path)
    run(folder, capsys)
    cards = next(folder.glob("cards_*.csv")).read_text(encoding="utf-8")
    assert "HSBC" in cards and "CPNG" in cards and SESSION in next(folder.glob("cards_*.csv")).name


def test_the_newest_card_is_the_one_with_the_latest_date_in_its_name(tmp_path):
    folder = folder_with_cards(tmp_path)
    import os
    old = folder / "CPNG_deep_dive_2026-10-19_v1.html"
    os.utime(old, (old.stat().st_mtime + 5000, old.stat().st_mtime + 5000))   # copied later, still the older card
    assert collect_decisions.find_cards(folder)["CPNG"][-1].name == f"CPNG_deep_dive_{SESSION}.html"
