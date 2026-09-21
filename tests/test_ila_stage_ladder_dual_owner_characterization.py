"""AVS-ILA-001 (audit/intelligence_lab/, 20 Sep 2026) follow-up to ILA-RC-08's exclusion note
(tests/test_ila_release_coverage_gate.py), root cause ILA-RC-09: intelligence-lab/
intelligence_lab.py's live stage-ladder recompute (_compute_stage_ladder, called from
_load_run against the raw eil_enriched signal) computed sb_current_stage from
trigger/campaign/EIL/execution verdicts independently of contracts/lab_control.py's
governed readiness_stage (_recompute_governed_lab_fields) - a second implementation of
the same "execution readiness stage" fact, violating CLAUDE.md design rule R2 ("one
owner per fact").

Investigation found the two computations really could disagree (proven below), but
_load_run's result["signals"] is unconditionally replaced by governed-book rows (or
emptied, fail-closed) immediately after the live recompute runs, so its output never
survived to any response the Lab actually serves - it was dead code, not a live
conflict a trader could ever see. Root cause and fix approved by ACK 21 Sep 2026:
remove the dead computation and its call site; readiness_stage/readiness_label/
readiness_enter_now (_recompute_governed_lab_fields) remain the sole owner, exposed to
the UI only through _governed_ui_projection's existing sb_current_stage alias
(ILA-RC-01).
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

from contracts.lab_control import write_final_opportunity_book

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RUN_ID = "20990101_160000"
TICKER = "AAA"


def _load_lab_module():
    path = ROOT / "intelligence-lab" / "intelligence_lab.py"
    spec = importlib.util.spec_from_file_location("intelligence_lab_for_stage_ladder_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_csv(path: Path, columns: list[str], row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = [str(row.get(col, "")) for col in columns]
    path.write_text(",".join(columns) + "\n" + ",".join(values) + "\n", encoding="utf-8")


def _publish_governed_book(tmp_path: Path) -> dict:
    """Publish a governed final book through the real production entry point
    (write_final_opportunity_book) and return the row it wrote, so the test
    asserts against whatever readiness_stage the governed pipeline actually
    computes rather than assuming a specific branch of _recompute_governed_lab_fields
    fires (several upstream guards - direction integrity, invalidation precondition -
    can force lab_tradeable/lab_verdict before that function ever runs)."""
    signal = {
        "ticker": TICKER, "direction": "CALL", "strike": "100",
        "expiry": "2099-01-19", "premium_mid": "1.0",
        "target_price": "110", "invalidation_price": "95",
        # Set both keys build_final_opportunity_book checks so apply_lab_resolution
        # is skipped and these governed inputs are not overwritten by tradeability
        # resolution logic unrelated to this test.
        "lab_verdict": "GO",
        "morning_lab_alignment_status": "ALIGNED",
        "lab_tradeable": True,
        "morning_execution_permission": "GO",
        "pipeline_mode": "MORNING_VALIDATION",
    }
    book = write_final_opportunity_book(
        RUN_ID,
        [signal],
        {"pipeline_mode": "MORNING_VALIDATION", "fatal_flags": [], "stale_flags": []},
        tmp_path / "runs",
        sync_interpreter=False,
    )
    return book["rows"][0]


def _write_eil_enriched_all_stages_true(run_dir: Path) -> None:
    """A raw eil_enriched row whose trigger/campaign/EIL/execution columns would have
    made the now-removed _compute_stage_ladder compute current_stage=4 ("All 4 layers
    aligned - ENTER NOW") - the maximum live-recompute value it used to produce, kept
    here so the regression test still proves that value can never leak into
    sb_current_stage now that the dead computation is gone."""
    eil_path = run_dir / "superbrain" / f"eil_enriched_{RUN_ID}.csv"
    columns = [
        "ticker", "direction", "strike", "expiry", "premium_mid",
        "target_price", "invalidation_price", "lab_verdict",
        "trigger_go_eligible", "campaign_verdict", "eil_v3_verdict", "execution_verdict",
    ]
    _write_csv(eil_path, columns, {
        "ticker": TICKER, "direction": "CALL", "strike": "100", "expiry": "2099-01-19",
        "premium_mid": "1.0", "target_price": "110", "invalidation_price": "95",
        "lab_verdict": "GO",
        "trigger_go_eligible": "TRUE",        # would have been s1 = True
        "campaign_verdict": "READY_EXECUTE",  # would have been s2 = True
        "eil_v3_verdict": "EXECUTE",          # would have been s3 = True
        "execution_verdict": "BUY_NOW",       # would have been s4 = True
    })


def test_compute_stage_ladder_was_removed():
    """The dead live-recompute function must not come back. If this fails, someone
    re-added _compute_stage_ladder - re-open the ILA-RC-09 root-cause investigation
    (it produced an unreachable second owner of the readiness stage) before wiring it
    back in."""
    lab = _load_lab_module()
    assert not hasattr(lab, "_compute_stage_ladder")


def test_load_run_serves_only_the_governed_readiness_stage():
    """What actually reaches a trader through /api/run/<id> (via _load_run and the
    _compact_lab_signal/_governed_ui_projection path _slim_lab_payload uses) carries
    the governed readiness_stage, and nothing derived from raw eil_enriched trigger/
    campaign/EIL/execution columns can appear as sb_current_stage."""
    lab = _load_lab_module()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        lab.RUNS_DIR = tmp_path / "runs"
        lab._run_cache.clear()

        run_dir = lab.RUNS_DIR / RUN_ID
        _write_eil_enriched_all_stages_true(run_dir)
        governed_row = _publish_governed_book(tmp_path)
        governed_stage = governed_row["readiness_stage"]
        assert governed_stage != 4, (
            "test fixture assumption broken: governed pipeline also produced stage 4 "
            "for this minimal signal - pick different governed inputs so this test "
            "can tell the governed value apart from the old live-recompute's maximum"
        )

        result = lab._load_run(RUN_ID, force_reload=True)
        signals = result["signals"]
        assert len(signals) == 1
        row = signals[0]

        # The governed book's readiness_stage is present on the row _load_run
        # actually returns.
        assert row.get("readiness_stage") == governed_stage

        # No live recompute exists anymore to write anything onto sb_current_stage
        # inside _load_run; it is either absent or already the governed value.
        assert row.get("sb_current_stage") in (None, "", governed_stage)
        assert row.get("sb_current_stage") != 4

        # What the browser actually receives from /api/run/<id> (_slim_lab_payload ->
        # _compact_lab_signal -> _governed_ui_projection) aliases sb_current_stage from
        # the governed readiness_stage - the sole owner.
        served = lab._compact_lab_signal(row)
        assert served.get("sb_current_stage") == governed_stage
