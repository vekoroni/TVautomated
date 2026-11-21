"""Lane B Fix B, B4 (check_triage.py): triage uses the Lab's target and contract, and the 11 Nov liquidity tiers.

Run (PowerShell, repo root):
    venv\\Scripts\\python.exe -m pytest data\\scratch\\workaround\\test_laneb_check_triage.py -q -p no:cacheprovider --basetemp=%TEMP%\\avs_ct
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_triage  # noqa: E402

SESSION = "2026-11-12"
HANDOFF = [
    # ticker, batch, direction, target, first profit, contract
    ("AAA", "1", "CALL", "107.9199", "103.674", "AAA270115C00090000"),
    ("CPNG", "1", "PUT", "10.9258", "10.9258", "CPNG270219P00017000"),
    ("CCC", "3", "CALL", "50", "48", "CCC270115C00045000"),
]
LEGACY_COLS = ["deep_mine_rank", "ticker", "ledger_id", "side", "trigger", "kill", "trade_contract", "contract_quote", "contract_spread_pct",
               "half_target", "level", "pays_at_half_target", "earnings_tastytrade", "cluster", "main_challenge", "rank_reason",
               "decision", "decision_reason", "contract_taken", "entry_type", "entry_premium"]


def write(path: Path, cols, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def lab_handoff(tmp_path) -> Path:
    folder = tmp_path / "lab_2026-11-12"
    write(folder / "handoff.csv", ["lb_order", "lb_batch", "lb_ledger_id", "ticker", "direction", "anticipated_level", "anticipated_level_q50",
                                   "contract_symbol", "earnings_date"],
          [{"lb_order": str(i + 1), "lb_batch": b, "lb_ledger_id": f"{SESSION}_{t}_{d}", "ticker": t, "direction": d, "anticipated_level": tg,
            "anticipated_level_q50": fp, "contract_symbol": c} for i, (t, b, d, tg, fp, c) in enumerate(HANDOFF)])
    return folder


def legacy_row(rank, ticker, side, contract, quote, half, level):
    return {"deep_mine_rank": str(rank), "ticker": ticker, "ledger_id": f"{SESSION}_{ticker}_{side}", "side": side, "trigger": "1", "kill": "1",
            "trade_contract": contract, "contract_quote": quote, "half_target": half, "level": level, "pays_at_half_target": "yes",
            "cluster": "x", "main_challenge": "x", "rank_reason": "x"}


def run(tmp_path, capsys, triage_rows, batch=1, cols=LEGACY_COLS, extra=()):
    folder = lab_handoff(tmp_path)
    tri = tmp_path / "triage"
    write(tri / f"batch{batch}_triage_{SESSION}.csv", cols, triage_rows)
    code = check_triage.main(["--folder", str(folder), "--triage-folder", str(tri), "--session", SESSION, "--context", str(tmp_path / "none.json"), *extra])
    return code, capsys.readouterr().out


def test_row_that_uses_the_lab_contract_target_and_first_profit_passes(tmp_path, capsys):
    _, out = run(tmp_path, capsys, [legacy_row(1, "AAA", "CALL", "AAA270115C00090000", "3.80/4.00 OI 817", "103.674", "107.9199")])
    assert "AAA:" not in out.split("## Notes")[0], "a matching row raises no line"


def test_triage_contract_that_is_not_the_lab_contract_is_a_warning(tmp_path, capsys):
    _, out = run(tmp_path, capsys, [legacy_row(1, "CPNG", "PUT", "CPNG270319P00018000", "2.69/2.95 OI 161", "10.9258", "10.9258")])
    assert "CPNG: trade_contract CPNG270319P00018000 is not the Lab contract CPNG270219P00017000" in out
    fail_part = out.split("## WARN")[0]
    assert "is not the Lab contract" not in fail_part, "a contract that is not the Lab's is a WARN, never a FAIL"


def test_triage_half_target_that_is_not_the_lab_first_profit_is_a_warning(tmp_path, capsys):
    _, out = run(tmp_path, capsys, [legacy_row(1, "CPNG", "PUT", "CPNG270219P00017000", "1.86/2.23 OI 161", "13.4579", "10.9258")])
    assert "CPNG: triage first profit 13.4579 is not the Lab first profit (anticipated_level_q50) 10.9258" in out
    assert "CPNG: triage target" not in out, "the target itself matches"


def test_spread_rule_is_the_11_nov_tiers_and_the_25_percent_rule_is_gone(tmp_path, capsys):
    _, out = run(tmp_path, capsys, [legacy_row(1, "AAA", "CALL", "AAA270115C00090000", "3.50/4.00 OI 817", "103.674", "107.9199"),
                                    legacy_row(2, "CPNG", "PUT", "CPNG270219P00017000", "1.86/2.23 OI 6", "10.9258", "10.9258")])
    assert "AAA: live liquidity tier B" in out
    assert "CPNG: live liquidity tier C" in out and "OI_6_UNDER_100" in out
    assert "25%" not in out and "25 %" not in out


def test_any_batch_is_checked_not_only_batch_one(tmp_path, capsys):
    _, out = run(tmp_path, capsys, [legacy_row(1, "CCC", "CALL", "CCC270115C00040000", "3.80/4.00 OI 817", "48", "50")], batch=3)
    assert "batch 3" in out and "CCC: trade_contract CCC270115C00040000 is not the Lab contract CCC270115C00045000" in out


def test_triage_built_from_the_old_hand_off_gets_a_note_on_batch_membership_not_a_fail(tmp_path, capsys):
    code, out = run(tmp_path, capsys, [legacy_row(1, "AAA", "CALL", "AAA270115C00090000", "3.80/4.00 OI 817", "103.674", "107.9199")])
    head = out.split("## Notes")[0]
    assert "missing from the triage" not in head
    assert "built from the old hand-off" in out


def test_triage_built_from_the_lab_hand_off_must_carry_every_name_of_its_batch(tmp_path, capsys):
    cols = LEGACY_COLS + ["lab_revision"]
    row = legacy_row(1, "AAA", "CALL", "AAA270115C00090000", "3.80/4.00 OI 817", "103.674", "107.9199")
    row["lab_revision"] = "a" * 32
    code, out = run(tmp_path, capsys, [row], cols=cols)
    assert code == 1 and "hand-off batch-1 names missing from the triage: CPNG" in out


def test_a_name_the_lab_hand_off_does_not_carry_is_named(tmp_path, capsys):
    _, out = run(tmp_path, capsys, [legacy_row(1, "ZZZ", "CALL", "ZZZ270115C00090000", "3.80/4.00 OI 817", "1", "2")])
    assert "ZZZ" in out and "not in the Lab hand-off" in out


def test_a_later_batch_may_continue_the_rank_count_but_gaps_still_fail(tmp_path, capsys):
    _, out = run(tmp_path, capsys, [legacy_row(61, "CCC", "CALL", "CCC270115C00045000", "3.80/4.00 OI 817", "48", "50")], batch=3)
    assert "deep_mine_rank is not" not in out
    _, out = run(tmp_path, capsys, [legacy_row(1, "AAA", "CALL", "AAA270115C00090000", "3.80/4.00 OI 817", "103.674", "107.9199"),
                                    legacy_row(3, "CPNG", "PUT", "CPNG270219P00017000", "1.86/2.23 OI 161", "10.9258", "10.9258")])
    assert "deep_mine_rank is not 1..2 without gaps or duplicates" in out


def test_batch_one_prompts_saved_with_the_b1_suffix_are_found_not_a_missing_fail(tmp_path, capsys):
    # 19 Nov 2026: the batch-1 triage chat saved deep_dive_prompts_<session>_b1.md, and the check failed it as missing.
    (tmp_path / "triage").mkdir()
    (tmp_path / "triage" / f"deep_dive_prompts_{SESSION}_b1.md").write_text("# 1 AAA\n", encoding="utf-8")
    _, out = run(tmp_path, capsys, [legacy_row(1, "AAA", "CALL", "AAA270115C00090000", "3.80/4.00 OI 817", "103.674", "107.9199")])
    assert "is missing: the deep dives have no prompts" not in out


def test_batch_one_prefers_the_unsuffixed_prompts_file_when_both_exist(tmp_path):
    plain, b1 = tmp_path / f"deep_dive_prompts_{SESSION}.md", tmp_path / f"deep_dive_prompts_{SESSION}_b1.md"
    b1.write_text("x", encoding="utf-8")
    assert check_triage.prompts_file(tmp_path, SESSION, 1) == b1
    plain.write_text("x", encoding="utf-8")
    assert check_triage.prompts_file(tmp_path, SESSION, 1) == plain
    assert check_triage.prompts_file(tmp_path, SESSION, 2).name == f"deep_dive_prompts_{SESSION}_b2.md"
