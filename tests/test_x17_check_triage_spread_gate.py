"""X17-02, rewritten 21 Nov 2026 (ACK, AVS-ARCH-LB-001 CF-03): the triage checker shows the 11 Nov liquidity tier.

History: on 17 Oct this file tested a 25% spread gate read from a contract_spread_pct column (W16-02). ACK replaced that
gate on 11 Nov with liquidity tiers read from the live quote on the triage row, and check_triage.py followed
(Lane B Fix B4, 60d0511). These tests were left asserting text the checker no longer writes, so all four would fail.

Business rules (the 11 Nov tiers; flags, never a gate):
- Tier A: spread within 10% of the mid and open interest of 100 or more. Nothing is raised.
- Tier B: spread between 10% and 20% of the mid. A WARN: tradeable with care.
- Tier C: spread over 20%, no bid, or open interest under 100. A WARN: not tradeable at this quote.
- A triage row with no live quote is a WARN saying the tier is not shown. Missing is never neutral.
- The retired contract_spread_pct column is not read: its value changes nothing.

Isolated: a temporary hand-off folder; the checker is run on it by path; no provider, no network.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "data" / "scratch" / "workaround" / "check_triage.py"
SESSION = "2026-10-19"
NAMES = [("AAA", "AAA261218P00010000", "PUT"), ("BBB", "BBB261218C00020000", "CALL")]


def _run(tmp_path: Path, quotes: dict[str, dict], extra: dict[str, dict] | None = None) -> str:
    """Run the checker on a two-name hand-off. `quotes` gives each name's contract_bid / contract_ask / contract_oi."""
    folder = tmp_path / "split"
    folder.mkdir(parents=True)
    pd.DataFrame([{"ticker": t, "ledger_id": f"L-{t}", "batch": "1", "best_contract": c, "best_contract_checked": c}
                  for t, c, _ in NAMES]).to_csv(folder / "handoff.csv", index=False)
    rows = []
    for i, (t, c, side) in enumerate(NAMES, 1):
        row = {"deep_mine_rank": str(i), "ticker": t, "ledger_id": f"L-{t}", "side": side, "trigger": "x", "kill": "x",
               "trade_contract": c, "pays_at_half_target": "Y", "earnings_tastytrade": "", "cluster": "", "main_challenge": "x",
               "rank_reason": "x", "decision": "", "decision_reason": "", "contract_taken": "", "entry_type": "",
               "entry_premium": "", "contract_bid": "", "contract_ask": "", "contract_oi": ""}
        row.update(quotes.get(t, {}))
        row.update((extra or {}).get(t, {}))
        rows.append(row)
    pd.DataFrame(rows).to_csv(folder / f"batch1_triage_{SESSION}.csv", index=False)
    (folder / f"deep_dive_prompts_{SESSION}.md").write_text(
        "".join(f"## {i} {t}\nsession {SESSION} {folder}\n" for i, t in [(1, "AAA"), (2, "BBB")]), encoding="utf-8")
    subprocess.run([sys.executable, str(TOOL), "--folder", str(folder), "--session", SESSION,
                    "--context", str(tmp_path / "no_context.json")], cwd=tmp_path, capture_output=True, text=True)
    return (folder / f"check_triage_{SESSION}.md").read_text(encoding="utf-8")


TIGHT = {"contract_bid": "1.95", "contract_ask": "2.05", "contract_oi": "850"}       # 5% of the mid, deep open interest
WIDE = {"contract_bid": "1.85", "contract_ask": "2.15", "contract_oi": "850"}        # 15% of the mid
VERY_WIDE = {"contract_bid": "1.70", "contract_ask": "2.30", "contract_oi": "850"}   # 30% of the mid
THIN = {"contract_bid": "1.95", "contract_ask": "2.05", "contract_oi": "40"}         # tight, but open interest under 100


def test_a_tight_liquid_contract_raises_nothing(tmp_path):
    report = _run(tmp_path, {"AAA": TIGHT, "BBB": TIGHT})
    assert "liquidity tier" not in report and "no live quote" not in report


def test_a_spread_between_ten_and_twenty_percent_is_tier_b_with_care(tmp_path):
    report = _run(tmp_path, {"AAA": WIDE, "BBB": TIGHT})
    assert "AAA: live liquidity tier B" in report and "tradeable with care" in report
    assert "BBB: live liquidity tier" not in report


def test_a_spread_over_twenty_percent_is_tier_c_not_tradeable_at_this_quote(tmp_path):
    report = _run(tmp_path, {"AAA": VERY_WIDE, "BBB": TIGHT})
    assert "AAA: live liquidity tier C" in report and "not tradeable at this quote" in report


def test_open_interest_under_one_hundred_is_tier_c_even_when_the_spread_is_tight(tmp_path):
    report = _run(tmp_path, {"AAA": TIGHT, "BBB": THIN})
    assert "BBB: live liquidity tier C" in report
    assert "AAA: live liquidity tier" not in report


def test_a_row_with_no_live_quote_says_the_tier_is_not_shown(tmp_path):
    report = _run(tmp_path, {"AAA": TIGHT, "BBB": {}})
    assert "BBB: no live quote on the triage row" in report and "liquidity tier is not shown" in report


def test_the_tier_is_a_flag_and_the_check_never_fails_on_it(tmp_path):
    report = _run(tmp_path, {"AAA": VERY_WIDE, "BBB": THIN})
    assert not report.splitlines()[0].rstrip().endswith("FAIL")


def test_the_retired_spread_column_changes_nothing(tmp_path):
    without = _run(tmp_path / "a", {"AAA": TIGHT, "BBB": TIGHT})
    with_old = _run(tmp_path / "b", {"AAA": TIGHT, "BBB": TIGHT}, extra={"AAA": {"contract_spread_pct": "31.5"}})
    assert "25% gate" not in with_old and "contract_spread_pct" not in with_old
    strip = lambda text: [line for line in text.splitlines() if "split" not in line and "written" not in line.lower()]   # noqa: E731
    assert strip(without) == strip(with_old)
