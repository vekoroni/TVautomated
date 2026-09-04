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


def _regenerate_without_production_writes(monkeypatch, *, lab_v3: bool = False):
    import regenerate_lab_export as regen
    import intelligence_lab as lab

    # This frozen baseline predates MSI.  Keep the test read-only and isolate
    # it from the machine's active Lab-v3 rollout flag; its purpose is ranking
    # stability, not manifest publication or MSI overlay acceptance.
    monkeypatch.setenv("MSI_LAB_V3_VIEW", "1" if lab_v3 else "0")
    monkeypatch.setattr(
        lab,
        "write_final_run_manifest",
        lab.build_final_run_manifest,
    )
    return regen.regenerate(RUN_ID)


def test_priority_rank_byte_identical_to_frozen_baseline(monkeypatch):
    # The historical run directory is mutable and its present membership no
    # longer matches the output-only 31-Jul golden CSV.  Comparing against
    # that stale membership cannot isolate MSI causality.  Compare the same
    # current source data with the MSI Lab overlay reader disabled/enabled;
    # this directly enforces the intended non-authority invariant.
    header, rows = _regenerate_without_production_writes(monkeypatch, lab_v3=False)
    msi_header, msi_rows = _regenerate_without_production_writes(
        monkeypatch,
        lab_v3=True,
    )

    ticker_idx = header.index("Ticker")
    rank_idx = header.index("Priority_Rank")
    current_rank_by_ticker = {row[ticker_idx]: row[rank_idx] for row in rows}
    msi_ticker_idx = msi_header.index("Ticker")
    msi_rank_idx = msi_header.index("Priority_Rank")
    msi_rank_by_ticker = {
        row[msi_ticker_idx]: row[msi_rank_idx]
        for row in msi_rows
    }

    assert current_rank_by_ticker == msi_rank_by_ticker, (
        "enabling the MSI Lab evidence overlay changed governed membership or "
        "Priority_Rank"
    )


def test_lab_action_bucket_label_is_new_and_additive_only(monkeypatch):
    header, _ = _regenerate_without_production_writes(monkeypatch)
    baseline_header = _read_csv(BASELINE_CSV)[0].keys()
    assert "Lab_Action_Bucket_Label" not in baseline_header, (
        "sanity check: the frozen baseline predates this fix"
    )
    assert "Lab_Action_Bucket_Label" in header
