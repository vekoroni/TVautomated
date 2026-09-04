from contracts.governed_states import (
    GOVERNED_DATA_STATE_VALUES,
    LIFECYCLE_EVALUATION_STATE_VALUES,
    GovernedDataState,
    LifecycleEvaluationState,
)


def test_cross_stage_data_state_vocabulary_is_unique_and_stable() -> None:
    assert len(GOVERNED_DATA_STATE_VALUES) == len(GovernedDataState)
    assert GovernedDataState.PENDING_MORNING_REFRESH.value == "PENDING_MORNING_REFRESH"
    assert GovernedDataState.NOT_APPLICABLE.value == "NOT_APPLICABLE"


def test_lifecycle_non_directional_and_correction_states_are_canonical() -> None:
    assert (
        LifecycleEvaluationState.NOT_EVALUATED_NON_DIRECTIONAL.value
        in LIFECYCLE_EVALUATION_STATE_VALUES
    )
    assert (
        LifecycleEvaluationState.SUPERSEDED_DATA_DEFECT.value
        == "SUPERSEDED_DATA_DEFECT"
    )
