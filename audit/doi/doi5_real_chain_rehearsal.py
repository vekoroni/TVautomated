"""Read-only-source DOI-5 rehearsal using a disposable control plane."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

import pandas as pd

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from canonical_data.dynamic_options_bridge import GovernedOptionObservation
from canonical_data.dynamic_options_family import ThesisConditionedContractFamilyGenerator
from canonical_data.dynamic_options_valuation import DeterministicContractValuationService
from canonical_data.option_liquidity_lifecycle import (
    MonitorState, OptionLiquidityLifecycleStore, ThesisState,
)
from canonical_data.registry import CanonicalRegistry
from domain.dynamic_options_intelligence import (
    ObservationAcquisitionDecision, OptionObservationKind, UnderlyingThesisRef,
)


SOURCE_CONTROL_PLANE = REPOSITORY_ROOT / "data/canonical/control_plane.sqlite"
SOURCE_DATASET_ID = "778fe0d37a39194098d0039a0aab3deae7f3a9a5e1a8b41a3b0b5ad18a50b05e"
REHEARSAL_RUN_ID = "20260910_074500"


def main() -> None:
    source_registry = CanonicalRegistry(SOURCE_CONTROL_PLANE)
    dataset = source_registry.get_dataset(SOURCE_DATASET_ID)
    if dataset is None:
        raise RuntimeError("frozen rehearsal dataset is unavailable")
    rows = json.loads(Path(dataset.storage_uri).read_text(encoding="utf-8"))
    frame = pd.DataFrame(rows)
    cutoff = dataset.as_of.astimezone(timezone.utc)

    with tempfile.TemporaryDirectory(prefix="doi5-real-rehearsal-") as temporary:
        registry = CanonicalRegistry(Path(temporary) / "control_plane.sqlite")
        registry.initialise()
        if dataset.source_run_id:
            registry.register_run(dataset.source_run_id, "EVENING", dataset.session_date)
        registry.register_run(REHEARSAL_RUN_ID, "REHEARSAL", dataset.session_date)
        registry.register_dataset(dataset)
        store = OptionLiquidityLifecycleStore(registry)
        store.initialise()
        store.record_thesis_event(
            thesis_id="A-CALL-DOI5-REHEARSAL", event_key="DOI5-REAL-REHEARSAL",
            run_id=REHEARSAL_RUN_ID, ticker="A", direction="CALL",
            thesis_state=ThesisState.ACTIVE, monitor_state=MonitorState.ACTIVE,
            reason_code="FROZEN_REHEARSAL_THESIS", structural_target=160.0,
            invalidation_spot=140.0, horizon_end_date=None,
        )
        thesis = UnderlyingThesisRef(
            thesis_id="A-CALL-DOI5-REHEARSAL", thesis_version=1, ticker="A",
            governed_direction="CALL", origin_spot=146.81,
            origin_timestamp_utc=cutoff, target_spot=160.0,
            invalidation_spot=140.0, planned_hold_sessions=10,
            planned_hold_source="REHEARSAL_FIXED_10_SESSION",
            evidence_cutoff_utc=cutoff,
        )
        observation = GovernedOptionObservation(
            ticker="A", observation_kind=OptionObservationKind.COMPLETED_SESSION,
            dataset_id=dataset.dataset_id, provider="MARKETDATA", as_of_utc=cutoff,
            frame=frame, resolution="FROZEN_CANONICAL_REUSE",
            acquisition=ObservationAcquisitionDecision(
                should_fetch=False, reason="REUSE_CANONICAL_EVIDENCE"
            ),
            physical_fetch_count=0,
        )
        family = ThesisConditionedContractFamilyGenerator(store).generate(
            thesis=thesis, observation=observation, run_id=REHEARSAL_RUN_ID
        )
        service = DeterministicContractValuationService(
            store, risk_free_rate=0.04, dividend_yield=0.01,
            entry_friction_bps=25.0, exit_friction_bps=25.0,
        )
        first = service.evaluate_family(
            generated_family=family, observation=observation
        )
        second = service.evaluate_family(
            generated_family=family, observation=observation
        )
        payload = {
            "ticker": "A", "session_date": dataset.session_date.isoformat(),
            "source_dataset_id": dataset.dataset_id,
            "source_rows": len(frame),
            "family": family.summary.to_dict(),
            "valuation": first.summary.to_dict(),
            "all_replayed_observations_reused": all(
                item.observation_reused for item in second.results
            ),
            "all_replayed_assessments_reused": all(
                item.assessment_reused for item in second.results
            ),
            "probability_fields_populated": sum(
                any(value is not None for value in (
                    item.assessment.p_liquidity_1d,
                    item.assessment.p_liquidity_2d,
                    item.assessment.p_liquidity_3d,
                    item.assessment.p_positive_return_before_horizon,
                    item.assessment.p_return_hurdle_before_horizon,
                    item.assessment.p_target_before_invalidation,
                ))
                for item in first.results
            ),
            "authority_violations": sum(
                item.assessment.can_change_direction
                or item.assessment.can_invalidate_thesis
                or item.assessment.can_grant_capital
                for item in first.results
            ),
            "assumptions": {
                "risk_free_rate": 0.04, "dividend_yield": 0.01,
                "entry_friction_bps": 25.0, "exit_friction_bps": 25.0,
                "source": "REHEARSAL_FIXED_NOT_LIVE_MARKET_INPUT",
            },
            "provider_fetch_count": 0,
            "production_database_modified": False,
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
