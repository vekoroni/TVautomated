"""
FIX-7 exit criterion: exporting lab_action_bucket_label must not change what
Priority_Rank actually is for any row. This locks that guarantee in against
the real run, not just a synthetic fixture -- Priority_Rank has been
byte-identical across every fix in this sprint so far (confirmed manually at
each Phase 1/2 golden-diff check); this test makes that an enforced fact
going forward rather than something re-verified by hand each time.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = ROOT / "tests" / "golden"
if str(GOLDEN_DIR) not in sys.path:
    sys.path.insert(0, str(GOLDEN_DIR))

RUN_ID = "20260731_083130"
BASELINE_CSV = GOLDEN_DIR / f"lab_export_baseline_{RUN_ID}.csv"


def _read_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def test_priority_rank_byte_identical_to_frozen_baseline():
    import regenerate_lab_export as regen

    header, rows = regen.regenerate(RUN_ID)
    ticker_idx = header.index("Ticker")
    rank_idx = header.index("Priority_Rank")
    current_rank_by_ticker = {row[ticker_idx]: row[rank_idx] for row in rows}

    baseline_rows = _read_csv(BASELINE_CSV)
    baseline_rank_by_ticker = {r["Ticker"]: r["Priority_Rank"] for r in baseline_rows}

    assert set(current_rank_by_ticker) == set(baseline_rank_by_ticker), (
        "row set changed -- this test only asserts ranking stability, a row-count "
        "change here means a different fix altered eligibility, not FIX-7"
    )
    mismatched = {
        t: (baseline_rank_by_ticker[t], current_rank_by_ticker[t])
        for t in baseline_rank_by_ticker
        if baseline_rank_by_ticker[t] != current_rank_by_ticker[t]
    }
    assert not mismatched, f"Priority_Rank changed for {len(mismatched)} ticker(s): {mismatched}"


def test_lab_action_bucket_label_is_new_and_additive_only():
    import regenerate_lab_export as regen

    header, _ = regen.regenerate(RUN_ID)
    baseline_header = _read_csv(BASELINE_CSV)[0].keys()
    assert "Lab_Action_Bucket_Label" not in baseline_header, (
        "sanity check: the frozen baseline predates this fix"
    )
    assert "Lab_Action_Bucket_Label" in header
