"""Read-only-source DOI-6 lifecycle rehearsal in a disposable control plane."""

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
from canonical_data.dynamic_options_lifecycle import DynamicOptionsLifecycleService
from canonical_data.dynamic_options_valuation import DeterministicContractValuationService
from canonical_data.option_liquidity_lifecycle import MonitorState, OptionLiquidityLifecycleStore, ThesisState
from canonical_data.registry import CanonicalRegistry
from domain.dynamic_options_intelligence import ObservationAcquisitionDecision, OptionObservationKind, UnderlyingThesisRef


SOURCE_CONTROL_PLANE = REPOSITORY_ROOT / "data/canonical/control_plane.sqlite"
SOURCE_DATASET_ID = "778fe0d37a39194098d0039a0aab3deae7f3a9a5e1a8b41a3b0b5ad18a50b05e"
REHEARSAL_RUN_ID = "20260910_083000"


def main() -> None:
    source_registry = CanonicalRegistry(SOURCE_CONTROL_PLANE)
    dataset = source_registry.get_dataset(SOURCE_DATASET_ID)
    if dataset is None:
        raise RuntimeError("frozen rehearsal dataset is unavailable")
    frame = pd.DataFrame(json.loads(Path(dataset.storage_uri).read_text(encoding="utf-8")))
    cutoff = dataset.as_of.astimezone(timezone.utc)

    with tempfile.TemporaryDirectory(prefix="doi6-real-rehearsal-") as temporary:
        registry = CanonicalRegistry(Path(temporary) / "control_plane.sqlite")
        registry.initialise()
        if dataset.source_run_id:
            registry.register_run(dataset.source_run_id, "EVENING", dataset.session_date)
        registry.register_run(REHEARSAL_RUN_ID, "REHEARSAL", dataset.session_date)
        registry.register_dataset(dataset)
        store = OptionLiquidityLifecycleStore(registry)
        store.initialise()
        thesis_id = "A-CALL-DOI6-REHEARSAL"
        store.record_thesis_event(
            thesis_id=thesis_id, event_key="DOI6-ORIGIN", run_id=REHEARSAL_RUN_ID,
            ticker="A", direction="CALL", thesis_state=ThesisState.ACTIVE,
            monitor_state=MonitorState.ACTIVE, reason_code="FROZEN_REHEARSAL_THESIS",
            structural_target=160.0, invalidation_spot=140.0,
        )
        thesis = UnderlyingThesisRef(
            thesis_id=thesis_id, thesis_version=1, ticker="A",
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
            acquisition=ObservationAcquisitionDecision(False, "REUSE_CANONICAL_EVIDENCE"),
            physical_fetch_count=0,
        )
        family = ThesisConditionedContractFamilyGenerator(store).generate(
            thesis=thesis, observation=observation, run_id=REHEARSAL_RUN_ID,
        )
        valuation = DeterministicContractValuationService(
            store, risk_free_rate=0.04, dividend_yield=0.01,
            entry_friction_bps=25.0, exit_friction_bps=25.0,
        ).evaluate_family(generated_family=family, observation=observation)
        lifecycle = DynamicOptionsLifecycleService(store)
        first = lifecycle.evaluate_completed_session(
            generated_family=family, valuation_result=valuation,
            evaluation_session=dataset.session_date, horizon_end_date=None,
            event_key="DOI6-EOD-REHEARSAL", current_spot=146.81,
        )
        replay = lifecycle.evaluate_completed_session(
            generated_family=family, valuation_result=valuation,
            evaluation_session=dataset.session_date, horizon_end_date=None,
            event_key="DOI6-EOD-REHEARSAL", current_spot=146.81,
        )
        morning = lifecycle.evaluate_morning_gate(
            generated_family=family, valuation_result=valuation,
            evaluation_session=dataset.session_date, horizon_end_date=None,
            event_key="DOI6-MORNING-NO-QUOTE", current_spot=139.50,
            options_observation_refreshed=False,
        )
        print(json.dumps({
            "ticker": "A",
            "session_date": dataset.session_date.isoformat(),
            "source_dataset_id": dataset.dataset_id,
            "source_rows": len(frame),
            "family_candidates": family.summary.family_candidates,
            "assessed_contracts": valuation.summary.assessed_contracts,
            "lifecycle": first.summary.to_dict(),
            "selected_contract": (
                first.preferred_decision.selected_contract_symbol
                if first.preferred_decision else None
            ),
            "selected_assessment_id": (
                first.preferred_decision.selected_assessment_id
                if first.preferred_decision else None
            ),
            "event_replay_reused": replay.event_reused,
            "decision_replay_reused": replay.preferred_decision_reused,
            "morning_without_option_refresh": {
                "condition_state": morning.lifecycle_event.condition_state.value,
                "opportunity_retained": morning.lifecycle_event.retain_opportunity,
                "new_preferred_decision": morning.preferred_decision is not None,
            },
            "authority_violations": int(
                first.lifecycle_event.can_change_direction
                or first.lifecycle_event.can_grant_capital
                or first.lifecycle_event.decision_authority != "NONE"
            ),
            "provider_fetch_count": 0,
            "production_database_modified": False,
            "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
