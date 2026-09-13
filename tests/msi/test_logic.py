"""Independent verification of MSI v1.1 logic/state-machine requirements.

Design under test: audit/solution_design/
MARKET_STRUCTURE_INTERPRETER_DATA_ENHANCEMENT_SOLUTION_DESIGN_20260830.md
(sections cited per test).  Scope: quote-change comparison (S8.8),
double-distribution/lifecycle rules (S10.2-10.4), Interpreter assessment
validator (S12.3), macro adapter non-authority (S12.4), run-history/
trajectory rules (S9.4, S13), quality classification (S8.6) and the
failure-behaviour table (S14).

Written by an independent test engineer against Codex's implementation.
Production code is not modified by this file.  Every test that finds a
design/implementation gap says so in its assertion message rather than
being adjusted to pass.

Run with the runtime the implementer built and tested against:
    PYTHONPATH=<repo>/venv/Lib/site-packages \
        .codex_python313_runtime/python.exe -m pytest tests/msi/test_logic.py -v
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
INTERPRETER_DIR = ROOT / "pipeline_interpreter"
for _p in (ROOT, INTERPRETER_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# --- market_structure package (S10.2-10.4) -------------------------------
from market_structure.lifecycle import direction_relationship, transition_lifecycle  # noqa: E402
from market_structure.params import MS_PARAMS_V1  # noqa: E402
from market_structure.profile import MarketProfile, detect_double_distribution, build_market_profile  # noqa: E402
from market_structure.service import calculate_market_structure_evidence  # noqa: E402

# --- contracts (handoff, materializer) ------------------------------------
from contracts.interpreter_handoff import (  # noqa: E402
    AUTHORITY_MAP_VERSION,
    BUNDLE_SCHEMA_VERSION,
    HandoffValidationError,
    artifact_record,
    publish_handoff_manifest,
    validate_handoff_manifest,
)
from contracts.interpreter_handoff_materializer import materialize_interpreter_handoff  # noqa: E402

# --- pipeline_interpreter (bare-module imports; see evidence_resolver.py's
# own sys.path handling, which requires pipeline_interpreter/ itself on
# sys.path -- mirrors tests/test_msi_interpreter_handoff.py) --------------
from evidence_resolver import (  # noqa: E402
    EvidenceResolutionError,
    IntendedUse,
    resolve_interpreter_evidence,
    resolve_interpreter_run,
)
from assessment_contract import (  # noqa: E402
    AssessmentStatus,
    AssessmentValidationError,
    build_assessment,
    validate_assessment,
)
from macro_context import (  # noqa: E402
    MacroContextState,
    MacroPacketError,
    load_macro_packet,
    missing_macro_context,
)


# ===========================================================================
# Shared fixture builders
# ===========================================================================

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _governed_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "run_id": "RUN1",
        "ticker": "AAA",
        "thesis_id": "THESIS-1",
        "trade_idea_id": "IDEA-1",
        "selected_structure_id": "STRUCT-1",
        "selected_contract_symbol": "AAA260918C00100000",
        "selected_quote_snapshot_id": "QUOTE-1",
        "governed_direction": "CALL",
        "thesis_state": "TRADEABLE_NOW",
        "olm_guard_disposition": "ELIGIBLE",
        "final_action": "BUY_NOW",
        "capital_permission": "CAPITAL_ALLOWED",
    }
    row.update(overrides)
    return row


def _publish_handoff(
    tmp_path: Path,
    *,
    run_id: str = "RUN1",
    rows: list[dict[str, Any]] | None = None,
    pipeline_mode: str = "MORNING_VALIDATION",
    run_kind: str = "PRODUCTION",
    run_status: str = "ACCEPTED",
    required_stage_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish a minimal valid handoff via the real materializer (not a
    hand-rolled substitute) so tests exercise the production code path."""
    rows = rows if rows is not None else [_governed_row(run_id=run_id)]
    stage_status = dict(required_stage_status) if required_stage_status is not None else {
        "EOD": "COMPLETED",
        "MORNING_GATE": "COMPLETED",
        "LAB": "COMPLETED",
    }
    return materialize_interpreter_handoff(
        run_id=run_id,
        rows=rows,
        run_root=tmp_path / run_id,
        pipeline_mode=pipeline_mode,
        session_date="2026-08-30",
        run_kind=run_kind,
        run_status=run_status,
        required_stage_status=stage_status,
        morning_gate_completed_utc="2026-08-30T11:25:00+00:00",
    )


def _write_raw_manifest(manifest_path: Path, artifacts: list[dict[str, Any]], **overrides: Any) -> None:
    """Write a handoff_manifest.json directly, bypassing publish_handoff_manifest's
    own PRODUCTION/ACCEPTED gate, so validate_handoff_manifest's *independent*
    enforcement of run_kind/run_status can be probed on its own terms."""
    payload = {
        "schema_version": "interpreter_handoff_manifest_v1",
        "handoff_status": "READY",
        "run_id": "RUN1",
        "pipeline_mode": "MORNING_VALIDATION",
        "session_date": "2026-08-30",
        "run_kind": "PRODUCTION",
        "run_status": "ACCEPTED",
        "required_stage_status": {"MORNING_GATE": "COMPLETED"},
        "morning_gate_completed_utc": "2026-08-30T11:25:00+00:00",
        "ticker_count": 1,
        "bundle_count": 1,
        "missing_bundle_count": 0,
        "reconciliation_status": "PASS",
        "producer_version": "test",
        "published_at_utc": "2026-08-30T11:30:00+00:00",
        "artifacts": artifacts,
    }
    payload.update(overrides)
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# ===========================================================================
# L-01 / L-02 -- S8.8 quote_change_evidence_v1
# ===========================================================================

class TestL01QuoteChangeComparison:
    """L-01 -- design S8.8: quote-change comparison is emitted only for the
    same exact OCC contract; comparison_status in {SAME_CONTRACT,
    CONTRACT_CHANGED, BASELINE_MISSING, CURRENT_MISSING, STALE}; when the
    contract differs every change field is null."""

    def test_no_active_module_computes_comparison_status(self) -> None:
        """L-01 / S8.8. Grep-level source check: the literal computation of
        comparison_status (SAME_CONTRACT / CONTRACT_CHANGED / BASELINE_MISSING
        / CURRENT_MISSING / STALE) does not exist as an assignment anywhere
        in the active module set. It is only ever *read* (as an allow-listed
        overlay field in contracts/lab_evidence_overlay.py:20, and as a
        pass-through copy key in contracts/interpreter_handoff_materializer.py
        :208-224). This is source evidence; test_bundle_pass_through_does_not_
        compute_anything below is the executed half of the two-level closure.
        """
        materializer_src = (ROOT / "contracts" / "interpreter_handoff_materializer.py").read_text(encoding="utf-8")
        # The only occurrence must be inside the pass-through key tuple, never
        # as an assignment (`comparison_status =` / `["comparison_status"] =`).
        assert "comparison_status =" not in materializer_src
        assert '"comparison_status"] =' not in materializer_src
        overlay_src = (ROOT / "contracts" / "lab_evidence_overlay.py").read_text(encoding="utf-8")
        assert "comparison_status =" not in overlay_src
        morning_gate_src = (ROOT / "morning_gate.py").read_text(encoding="utf-8")
        assert "SAME_CONTRACT" not in morning_gate_src
        assert "CONTRACT_CHANGED" not in morning_gate_src or "MORNING_CONTRACT_CHANGED" in morning_gate_src

    def test_bundle_computes_explicit_missing_quote_comparison(self, tmp_path: Path) -> None:
        """L-01 / S8.8, executed. A row with NO quote-change fields at all
        produces bundle['quote_change_evidence'] == {} -- not `comparison_status:
        null` (BASELINE_MISSING) and not any of the five required states.
        This contradicts S8.8's requirement that comparison_status is always
        one of SAME_CONTRACT/CONTRACT_CHANGED/BASELINE_MISSING/CURRENT_MISSING
        /STALE. Verdict: NOT_IMPLEMENTED -- no active module derives this
        field; interpreter_handoff_materializer.py's _bundle() only forwards
        pre-existing keys (`if key in row`), never computes them.
        """
        row = _governed_row()  # no morning_contract_bid / comparison_status / etc.
        result = _publish_handoff(tmp_path, rows=[row])
        bundle = json.loads(Path(result["bundle_path"]).read_text(encoding="utf-8").splitlines()[0])
        evidence = bundle["quote_change_evidence"]
        assert evidence["comparison_status"] == "BASELINE_MISSING"
        assert evidence["current_contract_bid"] is None
        assert evidence["contract_bid_change"] is None

    def test_bundle_recomputes_and_rejects_unlineaged_precomputed_fields(self, tmp_path: Path) -> None:
        """L-01 / S8.8, executed. Even when a row *does* carry quote-change
        fields, the materializer forwards them byte-for-byte without
        validating comparison_status against the actual contract-identity/
        baseline state (e.g. a `current_contract_bid == 0.0` here should, per
        S8.8, force `change_status = BASELINE_ZERO` on percentage fields --
        nothing in the bundle enforces or recomputes that). This shows the
        field is trusted input, not a governed calculation.
        """
        row = _governed_row(
            run_id="RUN1B",
            ticker="DDD",
            selected_contract_symbol="DDD260918C00100000",
            morning_contract_bid=1.20,
            morning_contract_ask=1.40,
            morning_contract_mid=1.30,
            current_contract_bid=0.0,
            current_contract_ask=0.10,
            current_contract_mid=0.05,
            contract_bid_change=-1.20,
            contract_mid_change=-1.25,
            comparison_status="SAME_CONTRACT",
        )
        result = _publish_handoff(tmp_path, run_id="RUN1B", rows=[row])
        bundle = json.loads(Path(result["bundle_path"]).read_text(encoding="utf-8").splitlines()[0])
        evidence = bundle["quote_change_evidence"]
        assert evidence["comparison_status"] == "BASELINE_MISSING"
        assert evidence["current_contract_bid"] == 0.0
        assert evidence["contract_bid_change"] is None
        assert evidence["change_status"] == "BASELINE_MISSING"


class TestL02BaselineZero:
    """L-02 -- design S8.8: a zero baseline value must produce
    `change_status = BASELINE_ZERO` and a null percentage change."""

    def test_baseline_zero_is_explicit_and_percentage_is_withheld(self, tmp_path: Path) -> None:
        """L-02 / S8.8, executed. A row whose *morning* (baseline) bid is
        0.0 is published through the same pass-through path as L-01. No
        `change_status` field, BASELINE_ZERO or otherwise, is ever added.
        Verdict: NOT_IMPLEMENTED -- the same absent-computation gap as L-01
        (there is exactly one code path, _bundle() in
        contracts/interpreter_handoff_materializer.py:174-228, and it has no
        arithmetic on bid/ask/mid at all).
        """
        row = _governed_row(
            run_id="RUN1C",
            ticker="EEE",
            selected_contract_symbol="EEE260918C00100000",
            morning_quote_dataset_id="EEE-MORNING",
            morning_quote_timestamp_utc="2026-08-30T13:40:00+00:00",
            current_quote_dataset_id="EEE-CURRENT",
            current_quote_timestamp_utc="2026-08-30T13:45:00+00:00",
            morning_contract_bid=0.0,
            morning_contract_ask=0.05,
            current_contract_bid=0.10,
            current_contract_ask=0.20,
        )
        result = _publish_handoff(tmp_path, run_id="RUN1C", rows=[row])
        bundle = json.loads(Path(result["bundle_path"]).read_text(encoding="utf-8").splitlines()[0])
        evidence = bundle["quote_change_evidence"]
        assert evidence["change_status"] == "BASELINE_ZERO"
        assert evidence["comparison_status"] == "BASELINE_ZERO"
        assert evidence["contract_bid_change_pct"] is None
        assert evidence["morning_bid"] == 0.0


# ===========================================================================
# L-03 / L-04 -- S10.3 lifecycle transition table
# ===========================================================================

class TestL03LifecycleTransitions:
    """L-03 -- design S10.3 transition table, tested against
    market_structure/lifecycle.py:transition_lifecycle (the active
    implementation; market_structure/contracts.py named by S22 is missing --
    see audit/msi/00_preflight.md; this is the module that actually performs
    the transition)."""

    def test_none_to_developing_on_second_qualifying_region(self) -> None:
        """L-03 row 1 / S10.3: none/single distribution -> MS_DEVELOPING when
        a second qualifying region is detected but acceptance is not yet met."""
        result = transition_lifecycle(prior=None, detected=True, accepted=False, repair_pct=0.0)
        assert result == "MS_DEVELOPING"

    def test_developing_to_accepted_when_all_rules_pass(self) -> None:
        """L-03 row 2 / S10.3: MS_DEVELOPING -> MS_ACCEPTED only when all
        four acceptance rules pass (represented here by accepted=True)."""
        result = transition_lifecycle(prior="MS_DEVELOPING", detected=True, accepted=True, repair_pct=0.05)
        assert result == "MS_ACCEPTED"

    def test_developing_stays_developing_when_not_yet_accepted(self) -> None:
        """L-03 row 2 (negative case) / S10.3."""
        result = transition_lifecycle(prior="MS_DEVELOPING", detected=True, accepted=False, repair_pct=0.0)
        assert result == "MS_DEVELOPING"

    def test_accepted_to_continuing_when_still_accepted_and_repair_below_020(self) -> None:
        """L-03 row 3 / S10.3: MS_ACCEPTED -> MS_CONTINUING when next
        evaluation remains accepted and repair < 0.20."""
        result = transition_lifecycle(prior="MS_ACCEPTED", detected=True, accepted=True, repair_pct=0.19)
        assert result == "MS_CONTINUING"

    def test_accepted_to_repairing_when_repair_in_020_060_band(self) -> None:
        """L-03 row 4 / S10.3: MS_ACCEPTED or MS_CONTINUING -> MS_REPAIRING
        when repair is 0.20-0.60 (still 'accepted' by the metric, but in the
        repair band)."""
        result = transition_lifecycle(prior="MS_ACCEPTED", detected=True, accepted=True, repair_pct=0.30)
        assert result == "MS_REPAIRING"

    def test_continuing_to_repairing_when_acceptance_temporarily_lost(self) -> None:
        """L-03 row 4 (acceptance-lost variant) / S10.3: MS_CONTINUING ->
        MS_REPAIRING when acceptance is temporarily lost even with low
        repair, per the design's explicit 'OR acceptance is temporarily
        lost' clause."""
        result = transition_lifecycle(prior="MS_CONTINUING", detected=True, accepted=False, repair_pct=0.05)
        assert result == "MS_REPAIRING"

    def test_repairing_to_continuing_on_restoration(self) -> None:
        """L-03 row 5 / S10.3: MS_REPAIRING -> MS_CONTINUING when acceptance
        is restored and repair < 0.20."""
        result = transition_lifecycle(prior="MS_REPAIRING", detected=True, accepted=True, repair_pct=0.10)
        assert result == "MS_CONTINUING"

    @pytest.mark.parametrize("prior", ["MS_ACCEPTED", "MS_CONTINUING", "MS_DEVELOPING", "MS_REPAIRING"])
    def test_any_to_failed_on_repair_above_060(self, prior: str) -> None:
        """L-03 row 6 / S10.3: any detected-double-distribution state ->
        MS_FAILED when repair > 0.60."""
        result = transition_lifecycle(prior=prior, detected=True, accepted=False, repair_pct=0.61)
        assert result == "MS_FAILED"

    def test_any_to_failed_on_invalidation_close(self) -> None:
        """L-03 row 6 (invalidation variant) / S10.3."""
        result = transition_lifecycle(prior="MS_CONTINUING", detected=True, accepted=True, repair_pct=0.05, invalidated=True)
        assert result == "MS_FAILED"

    def test_any_to_failed_when_regions_cease_to_qualify(self) -> None:
        """L-03 row 6 (regions-cease variant) / S10.3: detected=False
        represents 'regions cease to qualify'."""
        result = transition_lifecycle(prior="MS_DEVELOPING", detected=False, accepted=False, repair_pct=0.0)
        assert result == "MS_FAILED"

    def test_DEFECT_none_prior_can_skip_developing_straight_to_accepted(self) -> None:
        """L-03 DEFECT / S10.3. The design's transition table lists exactly
        one destination for the 'none/single distribution' source state:
        MS_DEVELOPING ('second qualifying region detected'). There is no
        table row for none -> MS_ACCEPTED. But
        market_structure/lifecycle.py:12 --
            if previous in {"", "MS_NONE"}: return "MS_ACCEPTED" if accepted else "MS_DEVELOPING"
        -- lets a single evaluation with prior=None jump straight to
        MS_ACCEPTED if the acceptance metric is already true on first
        contact, bypassing MS_DEVELOPING entirely. This is exactly the path
        production hits: morning_gate.py's only call site
        (_enrich_msi_market_structure, morning_gate.py:3261-3277) invokes
        calculate_market_structure_evidence exactly once per ticker per
        Morning Gate run with prior_lifecycle sourced from the EOD candidate
        row (never incrementally re-evaluated -- see test_L04 below), so if
        a session's already-accumulated minute bars already satisfy all four
        acceptance rules by the time Morning Gate first runs, the very first
        evaluation reports MS_ACCEPTED with no MS_DEVELOPING evidence record
        ever having existed. FAIL against S10.3's transition table.
        """
        skip = transition_lifecycle(prior=None, detected=True, accepted=True, repair_pct=0.05, invalidated=False)
        assert skip == "MS_ACCEPTED", "reproduces the defect: no MS_DEVELOPING state exists for the design to require"
        normal = transition_lifecycle(prior=None, detected=True, accepted=False, repair_pct=0.05, invalidated=False)
        assert normal == "MS_DEVELOPING"
        # The defect: two inputs differing only in whether acceptance already
        # holds land on non-adjacent lifecycle states from the SAME "none"
        # origin, with no intermediate evaluation ever producing MS_DEVELOPING
        # for the accepted=True case. Per S10.3's table this is not a valid
        # transition.


class TestL04FailedTerminalAndIntervalEvaluation:
    """L-04 -- design S10.3: MS_FAILED is terminal for the session; a new
    session creates a new evidence record rather than reopening it.
    Transitions are evaluated on completed five-minute intervals only."""

    def test_failed_is_terminal_regardless_of_new_inputs(self) -> None:
        """L-04 / S10.3, executed: once prior == MS_FAILED, no combination of
        detected/accepted/repair/invalidated can move the state within the
        same session (market_structure/lifecycle.py:9: `if previous ==
        "MS_FAILED": return "MS_FAILED"` -- unconditional, checked first)."""
        for detected, accepted, repair, invalidated in (
            (True, True, 0.0, False),
            (True, False, 0.9, True),
            (False, False, 0.0, False),
        ):
            result = transition_lifecycle(
                prior="MS_FAILED", detected=detected, accepted=accepted,
                repair_pct=repair, invalidated=invalidated,
            )
            assert result == "MS_FAILED"

    def test_new_session_produces_a_new_evidence_id(self) -> None:
        """L-04 / S10.3, executed (partial). calculate_market_structure_evidence's
        ms_evidence_id is a uuid5 over a lineage string that includes
        session_date.isoformat() (market_structure/service.py:58-59), so two
        calls differing only in session_date always produce distinct evidence
        records -- consistent with 'a new market session creates a new
        evidence record'. NOTE: this only proves a new *record* is minted; it
        does not prove the *lifecycle state itself* is reset to non-terminal
        for the new session, because that depends on the caller
        (morning_gate.py) sourcing prior_lifecycle=None for a fresh session
        rather than carrying the prior day's MS_FAILED forward through
        row.get("ms_lifecycle") -- not independently traced end-to-end here
        (candidate rows are rebuilt per EOD run by a different, out-of-scope
        module). Mark that sub-claim PARTIAL / source-evidence only.
        """
        empty = pd.DataFrame()
        common = dict(
            ticker="ZZZ", run_id="TESTRUN", bars=empty, exchange_tick=0.01, atr14=4.0,
            regular_open_utc=datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc),
            governed_direction="CALL", input_dataset_ids=("D1",), input_hashes=("H1",),
            prior_lifecycle="MS_FAILED",
        )
        evidence_day1 = calculate_market_structure_evidence(session_date=date(2026, 6, 1), **common)
        evidence_day2 = calculate_market_structure_evidence(session_date=date(2026, 6, 2), **common)
        assert evidence_day1["ms_evidence_id"] != evidence_day2["ms_evidence_id"]
        # Lifecycle stays MS_FAILED here ONLY because the test passed
        # prior_lifecycle="MS_FAILED" explicitly for both -- this is the
        # sub-claim flagged PARTIAL above, reproduced directly:
        assert evidence_day2["ms_lifecycle"] == "MS_FAILED"

    def test_DEFECT_transitions_are_not_evaluated_per_five_minute_interval(self) -> None:
        """L-04 DEFECT / S10.3: 'Transitions are evaluated after every
        completed five-minute interval.' grep across the repository shows
        calculate_market_structure_evidence / transition_lifecycle are
        invoked from exactly ONE production call site
        (morning_gate.py:_enrich_msi_market_structure), and that call site
        invokes calculate_market_structure_evidence exactly once per ticker
        per Morning Gate run (source: morning_gate.py:3261-3277, count
        asserted below), passing the *entire* regular-session-to-date bar
        range in a single call. There is no loop that steps through
        completed 5-minute closes and re-evaluates the state machine at each
        one; no EOD-side call exists either (grepped: eod_candidate_engine.py
        has zero matches for market_structure/ms_lifecycle). FAIL against
        S10.3.
        """
        source = (ROOT / "morning_gate.py").read_text(encoding="utf-8")
        call_count = source.count("calculate_market_structure_evidence(")
        assert call_count == 1, (
            f"expected exactly one call site (confirming no per-5-minute "
            f"evaluation loop exists); found {call_count}"
        )
        # Corroborate there is no other invocation anywhere else in the
        # active tree (excluding backups/ and the implementer's own unit
        # test file, which are not production call sites).
        hits = []
        for path in ROOT.rglob("*.py"):
            text = str(path)
            if "\\backups\\" in text or "\\.codex_test_temp\\" in text or "\\tests\\" in text:
                continue
            if "market_structure" in text or path.name in {"morning_gate.py"}:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "calculate_market_structure_evidence(" in content:
                hits.append(text)
        assert hits == [], f"unexpected additional call sites: {hits}"


# ===========================================================================
# L-05 -- S10.2 double-distribution qualification (each rule necessary)
# ===========================================================================

def _profile_from_counts(counts: list[float], periods: list[tuple[int, ...]], bin_width: float = 1.0) -> MarketProfile:
    n = len(counts)
    prices = [100.0 + i * bin_width for i in range(n)]
    bins = pd.DataFrame({
        "price": prices,
        "tpo_count": counts,
        "volume_estimated": [0.0] * n,
        "tpo_periods": periods,
    })
    return MarketProfile(
        bins=bins, bin_width=bin_width, poc=None, value_area_low=None,
        value_area_high=None, data_quality="ONE_MINUTE_ESTIMATED",
        total_tpo=int(sum(counts)), regular_volume=0.0,
    )


# Baseline: a clean, valid double distribution (verified empirically to be
# DETECTED with MS_PARAMS_V1 defaults and atr14=6.0). Two 3-bin plateaus at
# count=10 separated by a 2-bin valley at count=2 (<=50% of weaker peak),
# each region >=20% of total (30/64 = 46.9% each, well above threshold),
# peak=10 >= 60th percentile of nonzero counts (=10), separation=3 bin-widths
# (>= max(3*1, 0.3*6)=3), and chronology strongly separated (period 3 vs 23).
_BASELINE_COUNTS = [0, 10, 10, 10, 2, 2, 10, 10, 10, 0, 0]
_BASELINE_PERIODS = [
    (),
    tuple(range(0, 10)), tuple(range(0, 10)), tuple(range(0, 10)),
    (15, 16), (15, 16),
    tuple(range(20, 30)), tuple(range(20, 30)), tuple(range(20, 30)),
    (), (),
]
_BASELINE_ATR14 = 6.0


class TestL05DoubleDistributionQualificationRules:
    """L-05 -- design S10.2: each of the double-distribution qualification
    rules is individually necessary. Every sub-test below perturbs exactly
    one rule while leaving the others intact, verified against
    market_structure/profile.py:detect_double_distribution with
    MS_PARAMS_V1 (S10.2's 'proposed calibration seed' -- SEED_VALUE, read
    from market_structure/params.py rather than hard-coded here per the
    NO-HARD-CODED-THRESHOLDS rule)."""

    def test_baseline_is_detected(self) -> None:
        """Sanity check: the unperturbed construction is a valid double
        distribution under every S10.2 rule."""
        profile = _profile_from_counts(_BASELINE_COUNTS, _BASELINE_PERIODS)
        result = detect_double_distribution(profile, atr14=_BASELINE_ATR14, params=MS_PARAMS_V1)
        assert result["detected"] is True
        assert result["reason"] == "DOUBLE_DISTRIBUTION_DETECTED"

    def test_region_share_rule_alone_rejects(self) -> None:
        """L-05 / S10.2: each region must hold >= region_share (SEED_VALUE
        0.20) of regular-session TPO count. Widening the first region's
        plateau to 20 bins (same peak height, same valley, same separation,
        same chronology gap) drives the SECOND region's share to 30/234 =
        12.8% < 20%, with nothing else perturbed."""
        lower_width = 20
        counts = [0] + [10] * lower_width + [2, 2] + [10, 10, 10] + [0]
        periods = (
            [()]
            + [tuple(range(0, 10))] * lower_width
            + [(15, 16), (15, 16)]
            + [tuple(range(20, 30))] * 3
            + [()]
        )
        profile = _profile_from_counts(counts, periods)
        result = detect_double_distribution(profile, atr14=_BASELINE_ATR14, params=MS_PARAMS_V1)
        assert result["detected"] is False
        assert result["reason"] == "NO_QUALIFYING_DOUBLE_DISTRIBUTION"

    def test_peak_percentile_rule_alone_rejects(self) -> None:
        """L-05 / S10.2: local peak must be >= peak_percentile (SEED_VALUE
        0.60) of non-zero bin counts. Lowering only the second region's
        plateau from 10 to 5 drops it below the 60th-percentile threshold
        (still 10, computed from the mixed [2,2,5,5,5,10,10,10] distribution)
        while leaving region width/share, valley and chronology untouched."""
        counts = [0, 10, 10, 10, 2, 2, 5, 5, 5, 0, 0]
        profile = _profile_from_counts(counts, _BASELINE_PERIODS)
        result = detect_double_distribution(profile, atr14=_BASELINE_ATR14, params=MS_PARAMS_V1)
        assert result["detected"] is False

    def test_valley_rule_alone_rejects(self) -> None:
        """L-05 / S10.2: intervening low-participation zone must be >= 2
        bins whose max count is <= valley_ratio (SEED_VALUE 0.50) of the
        weaker regional peak. Raising the valley bins from 2 to 8 (>50% of
        the weaker peak of 10) breaks only this rule."""
        counts = [0, 10, 10, 10, 8, 8, 10, 10, 10, 0, 0]
        profile = _profile_from_counts(counts, _BASELINE_PERIODS)
        result = detect_double_distribution(profile, atr14=_BASELINE_ATR14, params=MS_PARAMS_V1)
        assert result["detected"] is False

    def test_separation_rule_alone_rejects(self) -> None:
        """L-05 / S10.2: regional peak separation must be >=
        max(3*bin_width, 0.30*ATR14) (SEED_VALUE atr coefficient 0.30). The
        bin geometry is untouched; only atr14 is raised to 50.0 so the
        ATR-based half of the threshold (15.0) exceeds the actual 3.0
        price-unit gap between peaks, while region share/peak/valley/
        chronology all still hold exactly as in the baseline."""
        profile = _profile_from_counts(_BASELINE_COUNTS, _BASELINE_PERIODS)
        result = detect_double_distribution(profile, atr14=50.0, params=MS_PARAMS_V1)
        assert result["detected"] is False

    def test_chronology_rule_alone_rejects(self) -> None:
        """L-05 / S10.2: the first region must reach chronology_share
        (SEED_VALUE 0.40) of its final TPO count at least one TPO period
        before the second region does. Giving both regions identical period
        ranges (both 0-9) removes any chronological proof of ordering while
        every count/geometry value is unchanged from the baseline."""
        periods = [
            (),
            tuple(range(0, 10)), tuple(range(0, 10)), tuple(range(0, 10)),
            (15, 16), (15, 16),
            tuple(range(0, 10)), tuple(range(0, 10)), tuple(range(0, 10)),
            (), (),
        ]
        profile = _profile_from_counts(_BASELINE_COUNTS, periods)
        result = detect_double_distribution(profile, atr14=_BASELINE_ATR14, params=MS_PARAMS_V1)
        assert result["detected"] is False

    def test_isolated_single_bin_spike_is_rejected(self) -> None:
        """L-05 / S10.2: 'deterministic rejection of isolated random peaks.'
        A single non-zero bin surrounded by zeros can never form two
        distinct concentration regions with a qualifying valley between
        them."""
        counts = [0, 0, 0, 0, 20, 0, 0, 0, 0, 0, 0]
        periods = [()] * 4 + [tuple(range(0, 20))] + [()] * 6
        profile = _profile_from_counts(counts, periods)
        result = detect_double_distribution(profile, atr14=_BASELINE_ATR14, params=MS_PARAMS_V1)
        assert result["detected"] is False


# ===========================================================================
# L-06 -- S10.4 direction-relationship mapping
# ===========================================================================

class TestL06DirectionRelationshipMapping:
    """L-06 -- design S10.4 deterministic relationship mapping table,
    tested against market_structure/lifecycle.py:direction_relationship."""

    @pytest.mark.parametrize("lifecycle", ["MS_ACCEPTED", "MS_CONTINUING"])
    def test_call_second_above_first_accepted_or_continuing_is_aligned(self, lifecycle: str) -> None:
        """L-06 row 1 / S10.4: CALL + second-above-first + ACCEPTED/CONTINUING -> ALIGNED."""
        result = direction_relationship(
            governed_direction="CALL", structure_direction="ABOVE",
            lifecycle=lifecycle, quality="ONE_MINUTE_ESTIMATED",
        )
        assert result == "ALIGNED"

    @pytest.mark.parametrize("lifecycle", ["MS_ACCEPTED", "MS_CONTINUING"])
    def test_call_second_below_first_is_conflicting(self, lifecycle: str) -> None:
        """L-06 row 2 / S10.4: CALL + second-below-first -> CONFLICTING."""
        result = direction_relationship(
            governed_direction="CALL", structure_direction="BELOW",
            lifecycle=lifecycle, quality="ONE_MINUTE_ESTIMATED",
        )
        assert result == "CONFLICTING"

    @pytest.mark.parametrize("lifecycle", ["MS_ACCEPTED", "MS_CONTINUING"])
    def test_put_second_below_first_is_aligned(self, lifecycle: str) -> None:
        """L-06 row 3 / S10.4: PUT + second-below-first -> ALIGNED."""
        result = direction_relationship(
            governed_direction="PUT", structure_direction="BELOW",
            lifecycle=lifecycle, quality="ONE_MINUTE_ESTIMATED",
        )
        assert result == "ALIGNED"

    @pytest.mark.parametrize("lifecycle", ["MS_ACCEPTED", "MS_CONTINUING"])
    def test_put_second_above_first_is_conflicting(self, lifecycle: str) -> None:
        """L-06 row 4 / S10.4: PUT + second-above-first -> CONFLICTING."""
        result = direction_relationship(
            governed_direction="PUT", structure_direction="ABOVE",
            lifecycle=lifecycle, quality="ONE_MINUTE_ESTIMATED",
        )
        assert result == "CONFLICTING"

    @pytest.mark.parametrize("direction", ["CALL", "PUT"])
    @pytest.mark.parametrize("lifecycle", ["MS_DEVELOPING", "MS_REPAIRING", "MS_FAILED"])
    @pytest.mark.parametrize("structure_direction", ["ABOVE", "BELOW"])
    def test_developing_repairing_failed_is_always_neutral(
        self, direction: str, lifecycle: str, structure_direction: str
    ) -> None:
        """L-06 row 5 / S10.4: CALL or PUT with MS_DEVELOPING/MS_REPAIRING/
        MS_FAILED -> NEUTRAL regardless of structure direction."""
        result = direction_relationship(
            governed_direction=direction, structure_direction=structure_direction,
            lifecycle=lifecycle, quality="ONE_MINUTE_ESTIMATED",
        )
        assert result == "NEUTRAL"

    @pytest.mark.parametrize("lifecycle", ["MS_ACCEPTED", "MS_CONTINUING", "MS_DEVELOPING", "MS_FAILED"])
    @pytest.mark.parametrize("structure_direction", ["ABOVE", "BELOW"])
    def test_unresolved_direction_is_always_neutral(self, lifecycle: str, structure_direction: str) -> None:
        """L-06 row 6 / S10.4: UNRESOLVED -> NEUTRAL always."""
        result = direction_relationship(
            governed_direction="UNRESOLVED", structure_direction=structure_direction,
            lifecycle=lifecycle, quality="ONE_MINUTE_ESTIMATED",
        )
        assert result == "NEUTRAL"

    def test_absent_structure_direction_is_insufficient_data(self) -> None:
        """L-06 row 7 (absent) / S10.4: any + absent quality/structure ->
        INSUFFICIENT_DATA."""
        result = direction_relationship(
            governed_direction="CALL", structure_direction=None,
            lifecycle="MS_ACCEPTED", quality="ONE_MINUTE_ESTIMATED",
        )
        assert result == "INSUFFICIENT_DATA"

    def test_insufficient_quality_is_insufficient_data(self) -> None:
        """L-06 row 7 (insufficient quality) / S10.4."""
        result = direction_relationship(
            governed_direction="CALL", structure_direction="ABOVE",
            lifecycle="MS_ACCEPTED", quality="INSUFFICIENT_DATA",
        )
        assert result == "INSUFFICIENT_DATA"

    def test_NEEDS_CLARIFICATION_coarse_quality_mapped_to_insufficient_data(self) -> None:
        """L-06 NEEDS_DESIGN_CLARIFICATION / S10.4. The design's table only
        lists 'absent/insufficient quality' -> INSUFFICIENT_DATA as the
        catch-all row, without stating whether COARSE_DATA_LOW_CONFIDENCE
        (one of the four S8.6 quality classes) counts as 'insufficient'
        for this specific mapping, or whether COARSE should instead follow
        the ordinary ALIGNED/CONFLICTING/NEUTRAL rows like
        ONE_MINUTE_ESTIMATED does. The implementation
        (market_structure/lifecycle.py:20) treats COARSE_DATA_LOW_CONFIDENCE
        identically to INSUFFICIENT_DATA. This is a reasonable reading but
        is not textually required by S10.4 -- recorded as
        NEEDS_DESIGN_CLARIFICATION rather than asserted as a pass or fail.
        """
        result = direction_relationship(
            governed_direction="CALL", structure_direction="ABOVE",
            lifecycle="MS_ACCEPTED", quality="COARSE_DATA_LOW_CONFIDENCE",
        )
        # Documenting current (plausible, unconfirmed-by-design) behaviour:
        assert result == "INSUFFICIENT_DATA"


# ===========================================================================
# L-07 -- S8.6 / S14 quality classification
# ===========================================================================

class TestL07QualityClassification:
    """L-07 -- design S8.6 (quality classes) and S14 (missing/coarse-bar
    failure behaviour)."""

    def test_one_minute_bars_only_yields_one_minute_estimated(self) -> None:
        """L-07 / S8.6, executed: a valid set of one-minute REGULAR bars
        with no trade-level data produces data_quality ==
        'ONE_MINUTE_ESTIMATED' (S10.1's mandated allocation method)."""
        bars = pd.DataFrame({
            "timestamp_utc": pd.date_range("2026-06-01T13:30:00Z", periods=5, freq="1min"),
            "high": [100.5, 100.6, 100.4, 100.7, 100.5],
            "low": [100.0, 100.1, 100.0, 100.2, 100.0],
            "close": [100.2, 100.3, 100.2, 100.5, 100.3],
            "volume": [1000, 900, 1100, 950, 1000],
            "session_segment": ["REGULAR"] * 5,
        })
        profile = build_market_profile(
            bars, exchange_tick=0.01, atr14=4.0,
            regular_open_utc=datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc),
        )
        assert profile.data_quality == "ONE_MINUTE_ESTIMATED"

    def test_missing_bars_yields_insufficient_data_no_fabricated_profile(self) -> None:
        """L-07 / S14 ('Intraday bars missing | structure INSUFFICIENT_DATA;
        no fabricated profile'), executed: an empty bars frame produces
        data_quality == 'INSUFFICIENT_DATA' with an empty bins frame and a
        None POC -- no profile is invented."""
        profile = build_market_profile(
            pd.DataFrame(), exchange_tick=0.01, atr14=4.0,
            regular_open_utc=datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc),
        )
        assert profile.data_quality == "INSUFFICIENT_DATA"
        assert profile.bins.empty
        assert profile.poc is None
        assert profile.value_area_low is None
        assert profile.value_area_high is None

    def test_corporate_action_on_session_forces_coarse_quality(self) -> None:
        """L-07 / S8.4 + S8.6, executed:
        `corporate_action_on_session=True` must force
        COARSE_DATA_LOW_CONFIDENCE regardless of what the profile
        calculation itself would have produced (market_structure/service.py
        :55: `quality = "COARSE_DATA_LOW_CONFIDENCE" if
        corporate_action_on_session else profile.data_quality`)."""
        evidence = calculate_market_structure_evidence(
            ticker="ZZZ", session_date=date(2026, 6, 1), run_id="TESTRUN",
            bars=pd.DataFrame(), exchange_tick=0.01, atr14=4.0,
            regular_open_utc=datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc),
            governed_direction="CALL", input_dataset_ids=("D1",), input_hashes=("H1",),
            prior_lifecycle=None, corporate_action_on_session=True,
        )
        assert evidence["ms_quality_class"] == "COARSE_DATA_LOW_CONFIDENCE"
        evidence_control = calculate_market_structure_evidence(
            ticker="ZZZ", session_date=date(2026, 6, 1), run_id="TESTRUN",
            bars=pd.DataFrame(), exchange_tick=0.01, atr14=4.0,
            regular_open_utc=datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc),
            governed_direction="CALL", input_dataset_ids=("D1",), input_hashes=("H1",),
            prior_lifecycle=None, corporate_action_on_session=False,
        )
        assert evidence_control["ms_quality_class"] == "INSUFFICIENT_DATA"

    def test_DEFECT_trade_level_confirmed_is_never_produced(self) -> None:
        """L-07 DEFECT / S8.6 + S10.1. S8.6 defines four quality classes
        including TRADE_LEVEL_CONFIRMED, and S10.1 requires 'calculate exact
        VAP only when trade-level records exist' -- implying a code path
        that detects trade-level input and emits TRADE_LEVEL_CONFIRMED.
        market_structure/profile.py:build_market_profile has no such branch
        at all: it always either returns INSUFFICIENT_DATA (empty/invalid
        input) or ONE_MINUTE_ESTIMATED (any valid input), never
        TRADE_LEVEL_CONFIRMED. Repository-wide grep for the literal string
        'TRADE_LEVEL_CONFIRMED' across all *.py finds zero matches. FAIL --
        NOT_IMPLEMENTED.
        """
        source = (ROOT / "market_structure" / "profile.py").read_text(encoding="utf-8")
        assert "TRADE_LEVEL_CONFIRMED" not in source
        hits = []
        for path in ROOT.rglob("*.py"):
            text = str(path)
            if "\\backups\\" in text or "\\.codex_test_temp\\" in text or "\\tests\\" in text:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "TRADE_LEVEL_CONFIRMED" in content:
                hits.append(text)
        assert hits == [], f"TRADE_LEVEL_CONFIRMED unexpectedly referenced in: {hits}"

    def test_coarse_bars_are_detected_from_observed_cadence(self) -> None:
        """L-07 DEFECT / S14 ('Coarse bars only | COARSE_DATA_LOW_CONFIDENCE
        | supporting evidence only'). The only mechanism that can ever
        produce COARSE_DATA_LOW_CONFIDENCE is the caller-supplied
        `corporate_action_on_session` boolean (S8.4); there is no bar-
        interval/granularity check anywhere in market_structure/profile.py
        that would classify e.g. 5-minute or 15-minute bars as 'coarse' on
        their own. Feeding 5-minute-interval bars (timestamps 5 minutes
        apart) produces ONE_MINUTE_ESTIMATED, not COARSE_DATA_LOW_CONFIDENCE,
        because the code never inspects bar cadence. FAIL --
        NOT_IMPLEMENTED for the 'coarse bars' condition independent of
        corporate actions.
        """
        coarse_bars = pd.DataFrame({
            "timestamp_utc": pd.date_range("2026-06-01T13:30:00Z", periods=5, freq="15min"),
            "high": [100.5, 101.0, 100.8, 101.2, 100.9],
            "low": [100.0, 100.4, 100.3, 100.6, 100.4],
            "close": [100.2, 100.8, 100.5, 101.0, 100.6],
            "volume": [50000, 48000, 51000, 47000, 49000],
            "session_segment": ["REGULAR"] * 5,
        })
        profile = build_market_profile(
            coarse_bars, exchange_tick=0.01, atr14=4.0,
            regular_open_utc=datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc),
        )
        assert profile.data_quality == "COARSE_15_MINUTE"


# ===========================================================================
# L-08 -- S9.4 / S13 resolver acceptance and run-kind exclusion
# ===========================================================================

class TestL08ResolverAcceptanceRules:
    """L-08 -- design S9.4 point 3 ('require run_status = ACCEPTED for
    production trajectory analysis and require COMPLETED Morning Gate for
    executable-session interpretation') and S13 (run_kind exclusion of
    TEST/REPLAY/REPAIR/ABORTED unless RESEARCH-labelled; file presence
    never implies acceptance)."""

    def test_file_presence_never_implies_acceptance_bad_status_rejected(self, tmp_path: Path) -> None:
        """L-08 / S13, executed: a manifest that exists on disk with
        handoff_status=READY but run_status=IN_PROGRESS (not ACCEPTED) must
        still be rejected by validate_handoff_manifest -- its mere presence
        on disk is not sufficient."""
        manifest_path = tmp_path / "handoff_manifest.json"
        _write_raw_manifest(manifest_path, artifacts=[], run_status="IN_PROGRESS")
        with pytest.raises(HandoffValidationError):
            validate_handoff_manifest(manifest_path, require_accepted=True)

    def test_test_run_kind_rejected_even_with_accepted_status(self, tmp_path: Path) -> None:
        """L-08 / S13, executed: run_kind=TEST must be excluded from
        production trajectory analysis regardless of run_status."""
        manifest_path = tmp_path / "handoff_manifest.json"
        _write_raw_manifest(manifest_path, artifacts=[], run_kind="TEST", run_status="ACCEPTED")
        with pytest.raises(HandoffValidationError, match="HANDOFF_NOT_PRODUCTION"):
            validate_handoff_manifest(manifest_path, require_accepted=True)

    @pytest.mark.parametrize("run_kind", ["REPLAY", "REPAIR", "ABORTED"])
    def test_replay_repair_aborted_run_kinds_rejected(self, run_kind: str, tmp_path: Path) -> None:
        """L-08 / S13, executed, for the remaining excluded run kinds named
        in the design (note: ABORTED is a RunStatus value per S24, not a
        RunKind value -- tested here as a RunKind string anyway since S13's
        prose lists it alongside TEST/REPLAY/REPAIR as an excluded
        category; RunKind(str) raising on invalid values is itself part of
        what's being verified)."""
        manifest_path = tmp_path / "handoff_manifest.json"
        _write_raw_manifest(manifest_path, artifacts=[], run_kind=run_kind, run_status="ACCEPTED")
        with pytest.raises(HandoffValidationError):
            validate_handoff_manifest(manifest_path, require_accepted=True)

    def test_DEFECT_research_labelled_run_is_not_actually_reachable(self, tmp_path: Path) -> None:
        """L-08 DEFECT / S13: 'excludes test, replay, repair and aborted
        runs unless explicitly labelled research' implies a RESEARCH-labelled
        run CAN be used in trajectory analysis. But
        contracts/interpreter_handoff.py:262-266
        (validate_handoff_manifest, require_accepted branch) hard-requires
        `manifest.get("run_kind") == RunKind.PRODUCTION.value`, and
        publish_handoff_manifest itself (contracts/interpreter_handoff.py
        :350-351) refuses to publish anything but
        PRODUCTION+ACCEPTED. So a RunKind.RESEARCH manifest can neither be
        published nor validated as accepted -- the design's own stated
        carve-out is unreachable dead code from the resolver's point of
        view. FAIL against S13's explicit exception clause.
        """
        manifest_path = tmp_path / "handoff_manifest.json"
        _write_raw_manifest(manifest_path, artifacts=[], run_kind="RESEARCH", run_status="ACCEPTED")
        with pytest.raises(HandoffValidationError, match="HANDOFF_NOT_PRODUCTION"):
            validate_handoff_manifest(manifest_path, require_accepted=True)
        # Confirm the publish path independently enforces the same
        # PRODUCTION-only rule, so RESEARCH can never even reach disk as an
        # accepted, hash-verified handoff:
        with pytest.raises(HandoffValidationError, match="ONLY_ACCEPTED_PRODUCTION_HANDOFF_MAY_PUBLISH"):
            publish_handoff_manifest(
                tmp_path / "other.json", run_id="RUN1", pipeline_mode="MORNING_VALIDATION",
                session_date="2026-08-30", run_kind="RESEARCH", run_status="ACCEPTED",
                required_stage_status={"MORNING_GATE": "COMPLETED"},
                morning_gate_completed_utc="2026-08-30T11:25:00+00:00",
                artifacts=[], ticker_count=0, bundle_count=0,
                reconciliation_status="PASS", producer_version="test",
            )

    def test_executable_session_requires_morning_gate_completed(self, tmp_path: Path) -> None:
        """L-08 / S9.4 point 3, executed: EXECUTABLE_SESSION intended_use
        fails closed when MORNING_GATE is absent from required_stage_status
        (i.e. not COMPLETED/PASS/ACCEPTED)."""
        result = _publish_handoff(
            tmp_path, run_id="RUN2", rows=[_governed_row(run_id="RUN2", ticker="CCC",
                                                          selected_contract_symbol="CCC260918C00100000")],
            pipeline_mode="EOD", required_stage_status={"EOD": "COMPLETED"},
        )
        manifest_path = Path(result["handoff_manifest_path"])
        with pytest.raises(EvidenceResolutionError) as excinfo:
            resolve_interpreter_evidence(
                "CCC", manifest_path=manifest_path, intended_use=IntendedUse.EXECUTABLE_SESSION,
            )
        assert excinfo.value.code == "MORNING_GATE_NOT_COMPLETED"

    def test_trajectory_use_bypasses_morning_gate_requirement(self, tmp_path: Path) -> None:
        """L-08 / S9.4 point 3, executed: TRAJECTORY intended_use does not
        require Morning Gate completion (it requires run_status=ACCEPTED at
        the manifest level instead, already covered above)."""
        result = _publish_handoff(
            tmp_path, run_id="RUN3", rows=[_governed_row(run_id="RUN3", ticker="FFF",
                                                          selected_contract_symbol="FFF260918C00100000")],
            pipeline_mode="EOD", required_stage_status={"EOD": "COMPLETED"},
        )
        manifest_path = Path(result["handoff_manifest_path"])
        evidence = resolve_interpreter_evidence(
            "FFF", manifest_path=manifest_path, intended_use=IntendedUse.TRAJECTORY,
        )
        assert evidence.intended_use == IntendedUse.TRAJECTORY


# ===========================================================================
# L-09 -- S13 trajectory comparison normalisation
# ===========================================================================

class TestL09TrajectoryComparisonNormalisation:
    """L-09 -- design S13: 'Contract quote/Greek trajectories are directly
    comparable only when the exact OCC contract is unchanged. If contracts
    differ, use normalised surface coordinates such as constant DTE and
    delta and label the comparison as normalised.'"""

    def test_DEFECT_no_trajectory_normalisation_logic_exists(self) -> None:
        """L-09 DEFECT / S13. There is no module implementing trajectory
        comparison at all (grepped for 'trajectory', 'normalised
        comparison', 'constant DTE/delta' logic across every active *.py --
        zero purpose-built matches other than unrelated files). This is the
        same underlying gap as L-01/L-02: quote_change_evidence is a
        pass-through of pre-existing row values
        (contracts/interpreter_handoff_materializer.py:174-228), with no
        branch on contract-identity-changed that would ever compute a
        'normalised' (constant-DTE/delta) comparison instead of a direct
        price delta. Verdict: NOT_IMPLEMENTED.
        """
        hits = []
        needles = ("normalised_comparison", "constant_dte", "trajectory_comparison", "NORMALIZED_COMPARISON")
        for path in ROOT.rglob("*.py"):
            text = str(path)
            if "\\backups\\" in text or "\\.codex_test_temp\\" in text or "\\tests\\" in text:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if any(needle in content for needle in needles):
                hits.append(text)
        assert hits == [], f"unexpected trajectory-normalisation code found: {hits}"

    def test_contract_change_produces_no_flagged_normalised_comparison(self, tmp_path: Path) -> None:
        """L-09 / S13, executed: publish a row where the current contract
        differs from the originally-selected one is out of scope for the
        materializer (identity must match at publish time -- see
        contracts/interpreter_handoff.py:BUNDLE_GOVERNED_IDENTITY_MISMATCH),
        so there is no governed artefact anywhere that could even carry a
        'normalised' label. This executes the same pass-through path as
        L-01 to show that even a row explicitly marked
        comparison_status=CONTRACT_CHANGED is forwarded verbatim with no
        added `comparison_basis` / `normalised` marker of any kind.
        """
        row = _governed_row(
            run_id="RUN1D", ticker="GGG", selected_contract_symbol="GGG260918C00100000",
            comparison_status="CONTRACT_CHANGED",
            morning_contract_symbol="GGG260918C00100000",
            current_contract_symbol="GGG260918C00105000",
            morning_quote_dataset_id="GGG-MORNING",
            current_quote_dataset_id="GGG-CURRENT",
            morning_quote_timestamp_utc="2026-08-30T13:40:00+00:00",
            current_quote_timestamp_utc="2026-08-30T13:45:00+00:00",
            morning_contract_bid=1.0, morning_contract_ask=1.2,
            current_contract_bid=0.8, current_contract_ask=1.0,
        )
        result = _publish_handoff(tmp_path, run_id="RUN1D", rows=[row])
        bundle = json.loads(Path(result["bundle_path"]).read_text(encoding="utf-8").splitlines()[0])
        evidence = bundle["quote_change_evidence"]
        assert evidence.get("comparison_status") == "CONTRACT_CHANGED"
        assert "comparison_basis" not in evidence
        assert "normalised" not in json.dumps(evidence).lower()


# ===========================================================================
# L-10 -- S12.3 post-generation validator
# ===========================================================================

_L10_BUNDLE = {
    "bundle_id": str(uuid.uuid4()),
    "run_id": "R1",
    "ticker": "AAA",
    "trade_idea_id": "IDEA-1",
    "freshness_map": {
        "exact_option_quote": "FRESH", "underlying_quote": "FRESH", "market_structure": "FRESH",
    },
    "governed_record": {
        "governed_direction": "CALL",
        "selected_contract_symbol": "AAA260918C00100000",
        "thesis_state": "TRADEABLE_NOW",
        "final_action": "BUY_NOW",
        "capital_permission": "CAPITAL_ALLOWED",
    },
    "selected_contract_symbol": "AAA260918C00100000",
    "market_structure": {"ms_direction_relationship": "ALIGNED"},
}

_L10_MODEL_OUTPUT_BASE = {
    "strengthening_weakening": "STRENGTHENING",
    "agreement_conflict": "ALIGNED",
    "manual_checks": ["confirm wall"],
    "data_gaps": [],
    "plain_language_reason": "Evidence is strengthening; human review remains required.",
}


class TestL10PostGenerationValidator:
    """L-10 -- design S12.3: 'Code, not the model, fills the governed
    fields... A post-generation validator rejects publication if the
    structured output or narrative asserts a different direction, contract,
    lifecycle or permission from the bundle... Temperature is 0.'"""

    def test_governed_fields_are_copied_from_bundle_not_model(self) -> None:
        """L-10 / S12.3, executed: governed_direction, selected_contract_symbol,
        thesis_state, final_action, capital_permission and
        ms_direction_relationship in the assessment come from the bundle
        (assessment_contract.py:_bundle_authority), never from
        model_output, which cannot even supply them (unknown keys are
        rejected -- see below)."""
        assessment = build_assessment(
            bundle=_L10_BUNDLE, model_output=_L10_MODEL_OUTPUT_BASE,
            model_id="gpt-test", prompt_version="msi-1", prompt_hash="a" * 64,
        )
        assert assessment["assessment_status"] == AssessmentStatus.VALID.value
        assert assessment["governed_direction"] == "CALL"
        assert assessment["selected_contract_symbol"] == "AAA260918C00100000"
        assert assessment["final_action"] == "BUY_NOW"
        assert assessment["ms_direction_relationship"] == "ALIGNED"

    def test_structured_field_override_attempt_is_rejected_as_schema_violation(self) -> None:
        """L-10 / S12.3, executed: a model attempting to supply a governed
        field directly (e.g. ms_direction_relationship) in structured output
        is rejected -- MODEL_FIELDS only allows the five narrative keys, so
        any additional key triggers REJECTED_SCHEMA."""
        tampered = dict(_L10_MODEL_OUTPUT_BASE, ms_direction_relationship="CONFLICTING")
        assessment = build_assessment(
            bundle=_L10_BUNDLE, model_output=tampered,
            model_id="gpt-test", prompt_version="msi-1", prompt_hash="a" * 64,
        )
        assert assessment["assessment_status"] == AssessmentStatus.REJECTED_SCHEMA.value
        assert any("MODEL_FIELDS_NOT_ALLOWED" in f for f in assessment["validation_findings"])
        # The governed field in the OUTPUT record is still the true bundle
        # value, never the attempted override:
        assert assessment["ms_direction_relationship"] == "ALIGNED"

    def test_narrative_direction_override_is_rejected(self) -> None:
        """L-10 / S12.3, executed: narrative asserting a different direction
        than governed ('Direction: PUT' when the bundle says CALL) is
        rejected as REJECTED_GOVERNANCE_CONFLICT."""
        tampered = dict(_L10_MODEL_OUTPUT_BASE, plain_language_reason="Direction: PUT. Capital is approved.")
        assessment = build_assessment(
            bundle=_L10_BUNDLE, model_output=tampered,
            model_id="gpt-test", prompt_version="msi-1", prompt_hash="a" * 64,
        )
        assert assessment["assessment_status"] == AssessmentStatus.REJECTED_GOVERNANCE_CONFLICT.value
        assert "NARRATIVE_DIRECTION_OVERRIDE" in assessment["validation_findings"]
        assert "NARRATIVE_CAPITAL_GRANT" in assessment["validation_findings"]

    def test_narrative_contract_override_is_rejected(self) -> None:
        """L-10 / S12.3, executed: narrative asserting a different contract
        than governed is rejected."""
        tampered = dict(
            _L10_MODEL_OUTPUT_BASE,
            plain_language_reason="Contract: AAA260918C00200000 looks better positioned.",
        )
        assessment = build_assessment(
            bundle=_L10_BUNDLE, model_output=tampered,
            model_id="gpt-test", prompt_version="msi-1", prompt_hash="a" * 64,
        )
        assert assessment["assessment_status"] == AssessmentStatus.REJECTED_GOVERNANCE_CONFLICT.value
        assert "NARRATIVE_CONTRACT_OVERRIDE" in assessment["validation_findings"]

    def test_DEFECT_narrative_lifecycle_override_is_not_detected(self) -> None:
        """L-10 DEFECT / S12.3. The design explicitly lists 'lifecycle' as
        one of the four attributes a rejected assessment's narrative must
        not contradict ('asserts a different direction, contract,
        lifecycle or permission from the bundle'). But
        assessment_contract.py:_narrative_conflicts only pattern-matches
        DIRECTION/TRADE DIRECTION, (SELECTED) CONTRACT and CAPITAL/EXECUTION
        APPROVED assertions -- there is no lifecycle pattern at all. A
        narrative explicitly asserting a contradicting lifecycle
        ('Lifecycle: MS_FAILED' when the bundle's
        ms_direction_relationship implies MS_ACCEPTED/MS_CONTINUING) is
        published as VALID. FAIL against S12.3.
        """
        tampered = dict(
            _L10_MODEL_OUTPUT_BASE,
            plain_language_reason=(
                "Lifecycle: MS_FAILED. The structure has actually broken down "
                "despite what governed evidence currently shows."
            ),
        )
        assessment = build_assessment(
            bundle=_L10_BUNDLE, model_output=tampered,
            model_id="gpt-test", prompt_version="msi-1", prompt_hash="a" * 64,
        )
        assert assessment["assessment_status"] == AssessmentStatus.VALID.value, (
            "reproduces the defect: a narrative lifecycle contradiction is "
            "not caught and the assessment is published as VALID"
        )

    def test_missing_model_field_is_rejected_as_schema_violation(self) -> None:
        """L-10 / S12.3, executed: an incomplete model_output (missing a
        required narrative field) is rejected."""
        incomplete = dict(_L10_MODEL_OUTPUT_BASE)
        del incomplete["data_gaps"]
        assessment = build_assessment(
            bundle=_L10_BUNDLE, model_output=incomplete,
            model_id="gpt-test", prompt_version="msi-1", prompt_hash="a" * 64,
        )
        assert assessment["assessment_status"] == AssessmentStatus.REJECTED_SCHEMA.value
        assert "MODEL_FIELD_MISSING:data_gaps" in assessment["validation_findings"]

    def test_nonzero_temperature_is_rejected(self) -> None:
        """L-10 / S12.3, executed: 'Temperature is 0' is enforced."""
        assessment = build_assessment(
            bundle=_L10_BUNDLE, model_output=_L10_MODEL_OUTPUT_BASE,
            model_id="gpt-test", prompt_version="msi-1", prompt_hash="a" * 64,
            temperature=0.7,
        )
        assert assessment["assessment_status"] == AssessmentStatus.REJECTED_SCHEMA.value
        assert "TEMPERATURE_MUST_BE_ZERO" in assessment["validation_findings"]
        # The persisted temperature field is still forced to 0.0, never the
        # attempted value:
        assert assessment["temperature"] == 0.0

    def test_rejected_assessment_is_preserved_not_dropped(self, tmp_path: Path) -> None:
        """L-10 / S12.3, executed: 'A rejected assessment is preserved with
        assessment_status = REJECTED_GOVERNANCE_CONFLICT but is not
        displayed as valid analysis.' append_assessment writes the rejected
        record to the JSONL sidecar; latest_valid_assessment (the
        display-facing reader) does not surface it."""
        from assessment_contract import append_assessment, latest_valid_assessment

        tampered = dict(_L10_MODEL_OUTPUT_BASE, plain_language_reason="Direction: PUT.")
        rejected = build_assessment(
            bundle=_L10_BUNDLE, model_output=tampered,
            model_id="gpt-test", prompt_version="msi-1", prompt_hash="a" * 64,
        )
        sidecar = tmp_path / "assessments.jsonl"
        append_assessment(sidecar, rejected)
        assert sidecar.read_text(encoding="utf-8").strip() != ""
        displayed = latest_valid_assessment(
            sidecar, run_id="R1", ticker="AAA", bundle_id=_L10_BUNDLE["bundle_id"],
        )
        assert displayed is None, "a REJECTED_GOVERNANCE_CONFLICT record must never be surfaced as valid"


# ===========================================================================
# L-11 -- S12.4 macro adapter non-authority
# ===========================================================================

class TestL11MacroAdapter:
    """L-11 -- design S12.4: the macro adapter emits only TAILWIND/NEUTRAL
    /HEADWIND/CONFLICTING_SOURCES/STALE_CONTEXT/DATA_MISSING; macro cannot
    change direction, contract, lifecycle, Morning Gate checks or
    final_action."""

    def test_enum_matches_exactly_the_six_named_states(self) -> None:
        """L-11 / S12.4, executed: MacroContextState has exactly the six
        design-named values, no more, no fewer."""
        values = {member.value for member in MacroContextState}
        assert values == {
            "TAILWIND", "NEUTRAL", "HEADWIND", "CONFLICTING_SOURCES",
            "STALE_CONTEXT", "DATA_MISSING",
        }

    def test_missing_macro_context_is_data_missing(self) -> None:
        """L-11 / S12.4, executed."""
        context = missing_macro_context()
        assert context.state == MacroContextState.DATA_MISSING

    def test_forbidden_authority_keys_never_reach_the_advisory_payload(self, tmp_path: Path) -> None:
        """L-11 / S12.4, executed: a macro packet payload containing
        authority-shaped keys (direction, final_action,
        risk_on_off_switch, ...) has them stripped from `.advisory` and
        surfaced only in `.ignored_authority_fields`, never in the prompt-
        facing advisory context."""
        packet_path = tmp_path / "macro.json"
        packet_path.write_text(json.dumps({
            "packet_id": "MP1", "macro_context_state": "HEADWIND",
            "sector_rotation": "OUT", "final_action": "BLOCK",
            "risk_on_off_switch": "OFF", "governed_direction": "PUT",
        }), encoding="utf-8")
        reference = {
            "packet_id": "MP1", "path": str(packet_path), "sha256": _sha(packet_path),
            "as_of_utc": "2026-08-30T10:00:00Z", "session_date": "2026-08-30", "freshness": "FRESH",
        }
        context = load_macro_packet(reference, run_root=tmp_path)
        assert context.state == MacroContextState.HEADWIND
        assert "final_action" not in context.advisory
        assert "risk_on_off_switch" not in context.advisory
        assert "governed_direction" not in context.advisory
        assert set(context.ignored_authority_fields) == {"final_action", "governed_direction", "risk_on_off_switch"}
        assert "sector_rotation" in context.advisory

    def test_stale_freshness_forces_stale_context_regardless_of_declared_state(self, tmp_path: Path) -> None:
        """L-11 / S12.4, executed: a packet declaring itself TAILWIND but
        whose freshness has degraded to STALE must surface as
        STALE_CONTEXT, not TAILWIND -- staleness overrides the declared
        state so a trader cannot see a fresh-looking macro tailwind label
        backed by expired data."""
        packet_path = tmp_path / "macro.json"
        packet_path.write_text(json.dumps({
            "packet_id": "MP1", "macro_context_state": "TAILWIND",
        }), encoding="utf-8")
        reference = {
            "packet_id": "MP1", "path": str(packet_path), "sha256": _sha(packet_path),
            "as_of_utc": "2026-08-30T10:00:00Z", "session_date": "2026-08-30", "freshness": "STALE",
        }
        context = load_macro_packet(reference, run_root=tmp_path)
        assert context.state == MacroContextState.STALE_CONTEXT

    def test_unrecognised_declared_state_becomes_conflicting_sources(self, tmp_path: Path) -> None:
        """L-11 / S12.4, executed: an out-of-enum declared state is mapped
        to CONFLICTING_SOURCES rather than silently passed through or
        crashing."""
        packet_path = tmp_path / "macro.json"
        packet_path.write_text(json.dumps({
            "packet_id": "MP1", "macro_context_state": "SUPER_BULLISH_NOT_A_REAL_STATE",
        }), encoding="utf-8")
        reference = {
            "packet_id": "MP1", "path": str(packet_path), "sha256": _sha(packet_path),
            "as_of_utc": "2026-08-30T10:00:00Z", "session_date": "2026-08-30", "freshness": "FRESH",
        }
        context = load_macro_packet(reference, run_root=tmp_path)
        assert context.state == MacroContextState.CONFLICTING_SOURCES

    def test_macro_reference_path_escape_is_rejected(self, tmp_path: Path) -> None:
        """L-11 / S12.4, executed: a macro reference pointing outside the
        run root is rejected rather than read (defence against a crafted
        path substituting an unrelated file as 'macro evidence')."""
        outside = tmp_path.parent / "outside_macro.json"
        outside.write_text(json.dumps({"packet_id": "MP1"}), encoding="utf-8")
        run_root = tmp_path / "run"
        run_root.mkdir()
        reference = {
            "packet_id": "MP1", "path": "../outside_macro.json", "sha256": _sha(outside),
            "as_of_utc": "2026-08-30T10:00:00Z", "session_date": "2026-08-30", "freshness": "FRESH",
        }
        with pytest.raises(MacroPacketError, match="MACRO_PACKET_OUTSIDE_RUN"):
            load_macro_packet(reference, run_root=run_root)

    def test_macro_authority_mutation_guard(self) -> None:
        """L-11 / S12.4, executed: assert_macro_did_not_change_authority
        (the design's 'prove every macro state leaves governed outputs
        unchanged' helper) raises when a forbidden authority key's value
        differs before/after a macro-influenced code path."""
        from macro_context import assert_macro_did_not_change_authority

        before = {"final_action": "BUY_NOW", "governed_direction": "CALL"}
        after_unchanged = {"final_action": "BUY_NOW", "governed_direction": "CALL"}
        assert_macro_did_not_change_authority(before, after_unchanged)  # no raise

        after_mutated = {"final_action": "BLOCK", "governed_direction": "CALL"}
        with pytest.raises(MacroPacketError, match="MACRO_AUTHORITY_MUTATION:final_action"):
            assert_macro_did_not_change_authority(before, after_mutated)


# ===========================================================================
# L-12 -- S14 failure behaviour table
# ===========================================================================

class TestL12FailureBehaviourTable:
    """L-12 -- design S14 failure table. Each sub-test targets one row and
    reports whether the exact named result code exists."""

    def test_DEFECT_morning_evidence_missing_literal_code_absent(self, tmp_path: Path) -> None:
        """L-12 row 1 DEFECT / S14: 'Morning bundle missing ->
        MORNING_EVIDENCE_MISSING; no executable interpretation.' When no
        accepted handoff exists at all, evidence_resolver.py raises
        EvidenceResolutionError('NO_ACCEPTED_INTERPRETER_HANDOFF'), not the
        design's literal required code MORNING_EVIDENCE_MISSING. The
        resolver DOES fail closed (no executable interpretation proceeds --
        the functional intent is met) but the required result-code literal
        does not exist anywhere in the active tree (grepped repo-wide, zero
        matches for 'MORNING_EVIDENCE_MISSING'). PARTIAL: behaviour correct,
        literal code missing.
        """
        empty_runs = tmp_path / "empty_runs"
        empty_runs.mkdir()
        with pytest.raises(EvidenceResolutionError) as excinfo:
            resolve_interpreter_evidence("ZZZ", runs_dir=empty_runs)
        assert excinfo.value.code == "NO_ACCEPTED_INTERPRETER_HANDOFF"
        for path in ROOT.rglob("*.py"):
            text = str(path)
            if "\\backups\\" in text or "\\.codex_test_temp\\" in text or "\\tests\\" in text:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            assert "MORNING_EVIDENCE_MISSING" not in content

    def test_DEFECT_contract_requote_required_literal_code_absent(self) -> None:
        """L-12 row 4 DEFECT / S14: 'Contract identity mismatch ->
        CONTRACT_REQUOTE_REQUIRED; suppress contract economics.' A book/
        bundle contract-identity mismatch in the active resolver raises
        EvidenceResolutionError / HandoffValidationError with codes like
        BOOK_BUNDLE_IDENTITY_MISMATCH or
        HANDOFF_BOOK_BUNDLE_IDENTITY_MISMATCH, never
        CONTRACT_REQUOTE_REQUIRED. Repo-wide grep for the literal string
        finds zero matches anywhere. Verdict: NOT_IMPLEMENTED for the named
        result code (a related but differently-named failure path exists).
        """
        for path in ROOT.rglob("*.py"):
            text = str(path)
            if "\\backups\\" in text or "\\.codex_test_temp\\" in text or "\\tests\\" in text:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            assert "CONTRACT_REQUOTE_REQUIRED" not in content

    def test_DEFECT_budget_exhausted_literal_code_and_ceiling_absent(self) -> None:
        """L-12 row 9 DEFECT / S14 + S16.2: 'BUDGET_EXHAUSTED when the
        global ceiling is hit with cache still served.' No configurable
        global daily ceiling, and no BUDGET_EXHAUSTED result code, exist
        anywhere in canonical_data/ or elsewhere in the active tree.
        Per the binding NO-HARD-CODED-THRESHOLDS rule this cannot even be
        SEED_VALUE-tested since S16.2's proposed limits (one chain fetch/
        ticker/session, six exact-quote refreshes/ticker/session, twelve
        underlying refreshes/ticker/session, a global daily ceiling) are
        not present in config/msi_runtime.json or any canonical_data module.
        Verdict: NOT_IMPLEMENTED.
        """
        for path in ROOT.rglob("*.py"):
            text = str(path)
            if "\\backups\\" in text or "\\.codex_test_temp\\" in text or "\\tests\\" in text:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            assert "BUDGET_EXHAUSTED" not in content
        config = json.loads((ROOT / "config" / "msi_runtime.json").read_text(encoding="utf-8"))
        assert "budget" not in json.dumps(config).lower()
        assert "daily_ceiling" not in json.dumps(config).lower()

    def test_DEFECT_refresh_conflict_literal_code_and_lock_timeout_absent(self) -> None:
        """L-12 row 10 DEFECT / S14 + S16.2: 'REFRESH_CONFLICT on a true
        conflicting request.' S16.2 requires a file lock per logical
        observation key with a proposed 30-second acquisition timeout,
        finalised in MSI-0, and a REFRESH_CONFLICT result on a true
        conflict. No lock-acquisition-timeout mechanism and no
        REFRESH_CONFLICT code exist anywhere in canonical_data/ (grepped
        for 'lock', 'timeout', 'coalesc', 'REFRESH_CONFLICT' -- only
        unrelated matches in option_liquidity_lifecycle.py /
        request_ledger.py, none implementing this). Verdict:
        NOT_IMPLEMENTED.
        """
        for path in ROOT.rglob("*.py"):
            text = str(path)
            if "\\backups\\" in text or "\\.codex_test_temp\\" in text or "\\tests\\" in text:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            assert "REFRESH_CONFLICT" not in content

    def test_option_sizes_absent_size_quality_enum_exists(self) -> None:
        """L-12 row 5 / S14 + S8.2: 'Option sizes absent -> retain price
        evidence; label liquidity depth incomplete.' Unlike the rows above,
        the S24 size-quality enum (OBSERVED/OBSERVED_ZERO/MISSING/
        INVALID_SIZE) IS present in canonical_data (market_observation_
        resolver.py, marketdata_response.py) and contracts/lab_evidence_
        overlay.py -- confirming this specific row's supporting vocabulary
        exists, even though full behavioural verification of the size-
        quality pipeline is functionality-test scope (F-series), not this
        logic-test scope. Source-evidence only; not independently executed
        as an end-to-end pipeline test here.
        """
        resolver_src = (ROOT / "canonical_data" / "market_observation_resolver.py").read_text(encoding="utf-8")
        assert "INVALID_SIZE" in resolver_src or "OBSERVED_ZERO" in resolver_src

    def test_ticker_dropped_blocks_provider_request_worklist_gate_exists(self) -> None:
        """L-12 row 8 / S14: 'Ticker dropped -> block provider request and
        record worklist rejection.' This is CDS worklist-gate functionality
        (out of this logic-test's direct scope -- see W/F-series), recorded
        here only to confirm the supporting module exists and is named as
        the design's S22 module map states (canonical_data/worklist_gate.py).
        Source-evidence only.
        """
        assert (ROOT / "canonical_data" / "worklist_gate.py").is_file()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
