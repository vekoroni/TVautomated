from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

import pytest

from canonical_data.decision_outcome_ledger import (
    DecisionOutcomeLedger,
    candidate_events_from_rows,
)
from canonical_data.historical_prices import HistoricalPriceDatabase
from canonical_data.outcome_learning import (
    STAGE6_OUTCOME_HORIZONS,
    build_temporal_partition_plan,
    build_outcome_learning_snapshot,
    learning_policy_from_config,
)
from canonical_data.outcome_maturation import mature_candidate_outcomes
from domain.decision_outcome import evaluate_outcome_path
from domain.outcome_learning import (
    CompetingEventLabel,
    LearningActivationPolicy,
    LearningStratum,
    ModelActivationState,
    OutcomeAttribution,
    OutcomeLearningRecord,
    assess_model_activation,
    competing_event_label,
)


ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
NOW = "2026-01-02T22:00:00Z"


def _candidate_row(ticker: str = "AAA", direction: str = "CALL") -> dict:
    return {
        "ticker": ticker,
        "thesis_id": f"THESIS:{ticker}",
        "governed_direction": direction,
        "signal_price": 100.0,
        "target_price": 105.0 if direction == "CALL" else 95.0,
        "invalidation_price": 95.0 if direction == "CALL" else 105.0,
        "planned_hold_sessions": 5,
        "hidden_state_label": "COMPRESSED_BALANCED",
        "phase": "C",
        "compression_bucket": "MID",
        "doi_preferred_assessment_id": f"ASSESS:{ticker}",
        "evidence_dataset_ids": [f"DATA:{ticker}"],
    }


def _candidate(
    ledger: DecisionOutcomeLedger,
    *,
    ticker: str = "AAA",
    direction: str = "CALL",
    baseline_eligible: bool = True,
):
    event = candidate_events_from_rows(
        [_candidate_row(ticker, direction)],
        run_id="RUN1",
        occurred_at_utc=NOW,
        decision_stage="EOD_THESIS",
        run_metadata={
            "completed_session": "2026-01-02",
            "evidence_cutoff_utc": NOW,
            "run_condition": "NORMAL_COMPLETED_SESSION",
            "baseline_eligible": baseline_eligible,
            "baseline_ineligibility_reason": (
                None if baseline_eligible else "FORCED_TEST_RUN"
            ),
        },
    )[0]
    ledger.append(event)
    return event


def _bars(count: int = 20, *, direction: str = "CALL") -> list[dict]:
    rows = []
    for index in range(1, count + 1):
        session = date(2026, 1, 2) + timedelta(days=index)
        close = 100 + index if direction == "CALL" else 100 - index
        rows.append({
            "date": session.isoformat(),
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
        })
    return rows


def _record(
    *,
    direction: str = "CALL",
    hold: int = 5,
    label: CompetingEventLabel = CompetingEventLabel.TARGET_FIRST,
    suffix: str = "1",
) -> OutcomeLearningRecord:
    return OutcomeLearningRecord.create(
        candidate_event_id=f"C{suffix}", outcome_event_id=f"O{suffix}",
        run_id="R", ticker=f"T{suffix}", thesis_id=f"TH{suffix}",
        preferred_assessment_id=f"A{suffix}", direction=direction,
        decision_session="2026-01-02", planned_hold_sessions=hold,
        hold_bucket=("1-5" if hold <= 5 else "6-10" if hold <= 10 else "11-20"),
        horizon_sessions=min(hold, 20), hidden_state_label="STATE", phase="C",
        compression_bucket="MID", competing_event_label=label,
        underlying_directional_return=0.05, underlying_mfe=0.07,
        underlying_mae=-0.02, option_data_status="UNDERLYING_ONLY",
        terminal_option_return=None, option_mfe=None, option_mae=None,
        first_two_sided_session=None,
        family_member_outperformance_state="NOT_EVALUATED",
        attribution=OutcomeAttribution.UNCLASSIFIED_UNCERTAINTY,
        feature_cutoff_utc="2026-01-02T22:00:00Z",
        outcome_cutoff_utc="2026-01-09T22:00:00Z",
        baseline_eligible=True, fit_eligible=(label is not CompetingEventLabel.AMBIGUOUS_TOUCH_ORDER),
        exclusion_reasons=("AMBIGUOUS_TOUCH_ORDER",) if label is CompetingEventLabel.AMBIGUOUS_TOUCH_ORDER else (),
        source_dataset_ids=(f"D{suffix}",),
    )


class TestStage6UnitAndProperty:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("TARGET_ONLY", CompetingEventLabel.TARGET_FIRST),
            ("STOP_FIRST", CompetingEventLabel.INVALIDATION_FIRST),
            ("NEITHER", CompetingEventLabel.TIMEOUT),
            ("AMBIGUOUS_SAME_SESSION", CompetingEventLabel.AMBIGUOUS_TOUCH_ORDER),
        ],
    )
    def test_competing_event_vocabulary(self, source, expected):
        assert competing_event_label(source) is expected

    @pytest.mark.parametrize("move", [0.01, 0.03, 0.08, 0.15])
    def test_call_put_path_measurements_are_symmetric(self, move):
        call = evaluate_outcome_path(
            direction="CALL", reference_price=100,
            future_bars=[{"high": 100 * (1 + move), "low": 99, "close": 100 * (1 + move)}],
            horizon_sessions=1, target_price=120, invalidation_price=90,
        )
        put = evaluate_outcome_path(
            direction="PUT", reference_price=100,
            future_bars=[{"high": 101, "low": 100 * (1 - move), "close": 100 * (1 - move)}],
            horizon_sessions=1, target_price=80, invalidation_price=110,
        )
        assert call.directional_return == pytest.approx(put.directional_return)
        assert call.mfe == pytest.approx(put.mfe)

    def test_ambiguous_daily_touch_is_never_fit_eligible(self):
        record = _record(label=CompetingEventLabel.AMBIGUOUS_TOUCH_ORDER)
        assert record.fit_eligible is False
        with pytest.raises(ValueError, match="ambiguous"):
            replace(record, fit_eligible=True, exclusion_reasons=())

    def test_outcome_must_follow_feature_cutoff(self):
        with pytest.raises(ValueError, match="follow"):
            replace(_record(), outcome_cutoff_utc="2026-01-02T21:59:00Z")

    def test_hierarchical_backoff_is_explicit_and_ordered(self):
        chain = LearningStratum(
            "UNAVAILABLE", "C", "MID", "PUT", "6-10"
        ).backoff_chain()
        assert [item["match_level"] for item in chain] == ["0", "1", "2", "3", "4"]
        assert chain[0]["hidden_state_label"] == "UNAVAILABLE"
        assert chain[-1] == {"match_level": "4", "direction": "PUT"}

    def test_time_ordered_partition_has_purge_and_no_overlap(self):
        records = []
        origin = date(2025, 1, 1)
        for index in range(100):
            decision = origin + timedelta(days=index)
            outcome = decision + timedelta(days=1)
            records.append(replace(
                _record(suffix=str(index)),
                decision_session=decision.isoformat(),
                feature_cutoff_utc=f"{decision.isoformat()}T20:00:00Z",
                outcome_cutoff_utc=f"{outcome.isoformat()}T20:00:00Z",
            ))
        plan = build_temporal_partition_plan(records, purge_embargo_sessions=2)
        assert plan.state == "READY"
        assert plan.training_record_ids
        assert plan.validation_record_ids
        assert plan.test_record_ids
        assert plan.excluded_embargo_record_ids
        assert not plan.excluded_boundary_overlap_record_ids


class TestStage6ActivationGate:
    def test_model_is_gated_when_outcomes_are_insufficient(self):
        assessment = assess_model_activation(
            [_record()], expected_observable_outcomes=10,
            policy=LearningActivationPolicy(),
        )
        assert assessment.state is ModelActivationState.INSUFFICIENT_OUTCOMES
        assert assessment.can_activate is False
        assert "MODEL_ACTIVATION_DISABLED_BY_RELEASE_PROFILE" in assessment.reason_codes

    def test_sufficient_data_still_requires_metrics_and_release_approval(self):
        records = []
        directions = ("CALL", "PUT")
        holds = (5, 10, 20)
        for direction in directions:
            for hold in holds:
                for index in range(2):
                    records.append(_record(
                        direction=direction, hold=hold,
                        suffix=f"{direction}{hold}{index}",
                    ))
        policy = LearningActivationPolicy(
            model_activation_enabled=False,
            minimum_fit_outcomes=6,
            minimum_stratum_outcomes=2,
            minimum_coverage=0.6,
        )
        assessment = assess_model_activation(
            records, expected_observable_outcomes=len(records), policy=policy,
        )
        assert assessment.state is ModelActivationState.AWAITING_OUT_OF_SAMPLE_METRICS
        assert assessment.can_activate is False

    def test_all_gates_only_make_model_eligible_for_operator_review(self):
        records = [
            _record(direction=direction, hold=hold, suffix=f"{direction}{hold}")
            for direction in ("CALL", "PUT") for hold in (5, 10, 20)
        ]
        policy = LearningActivationPolicy(
            model_activation_enabled=True, minimum_fit_outcomes=6,
            minimum_stratum_outcomes=1, minimum_coverage=0.6,
        )
        metrics = {
            "time_ordered_partitions": True,
            "confidence_intervals_present": True,
            "stability_report_present": True,
            "multiclass_log_loss": 0.90,
            "held_out_count": 100,
            "maximum_overall_ece": 0.05, "maximum_stratum_ece": 0.10,
            "multiclass_brier_skill": 0.01, "target_roc_auc": 0.51,
            "target_pr_auc": 0.31, "target_base_rate": 0.30,
            "target_top_quintile_lift": 1.01,
        }
        assessment = assess_model_activation(
            records, expected_observable_outcomes=6,
            policy=policy, held_out_metrics=metrics,
        )
        assert assessment.state is ModelActivationState.ELIGIBLE_FOR_OPERATOR_REVIEW
        assert assessment.can_activate is True
        tied = assess_model_activation(
            records, expected_observable_outcomes=6, policy=policy,
            held_out_metrics={**metrics, "target_roc_auc": 0.50},
        )
        assert tied.state is ModelActivationState.METRIC_GATES_FAILED


class TestStage6Integration:
    def test_learning_snapshot_ledger_access_is_genuinely_read_only(self, tmp_path):
        ledger_path = tmp_path / "ledger.sqlite"
        writable = DecisionOutcomeLedger(ledger_path)
        writable.initialise()
        before = ledger_path.stat().st_mtime_ns

        read_only = DecisionOutcomeLedger(ledger_path, read_only=True)
        assert read_only.event_counts() == {}
        assert ledger_path.stat().st_mtime_ns == before
        with pytest.raises(RuntimeError, match="open read-only"):
            read_only.append(None)  # type: ignore[arg-type]

    def test_all_presented_candidates_mature_at_six_horizons(self, tmp_path):
        ledger = DecisionOutcomeLedger(tmp_path / "ledger.sqlite")
        _candidate(ledger)
        summary = mature_candidate_outcomes(
            ledger, read_completed_history=lambda *_: _bars(),
            as_of_utc="2026-02-01T22:00:00Z",
            horizons=STAGE6_OUTCOME_HORIZONS,
        )
        assert summary.expected_candidate_horizons == 6
        assert summary.outcomes_appended == 6
        assert summary.population_reconciled is True
        snapshot = build_outcome_learning_snapshot(
            ledger, policy=LearningActivationPolicy(),
        )
        assert snapshot["summary"]["presented_candidates"] == 1
        assert snapshot["summary"]["complete_outcomes"] == 6
        assert snapshot["summary"]["population_reconciled"] is True
        assert len(snapshot["records"]) == 6
        assert snapshot["model_activation"]["can_activate"] is False

    def test_incomplete_and_bad_candidates_receive_named_observations(self, tmp_path):
        ledger = DecisionOutcomeLedger(tmp_path / "ledger.sqlite")
        _candidate(ledger, ticker="GOOD")
        bad = _candidate_row("BAD")
        bad["target_price"] = None
        bad["structural_target"] = None
        ledger.append(candidate_events_from_rows(
            [bad], run_id="RUN2", occurred_at_utc=NOW,
            decision_stage="EOD_THESIS",
            run_metadata={
                "completed_session": "2026-01-02",
                "evidence_cutoff_utc": NOW,
                "run_condition": "NORMAL_COMPLETED_SESSION",
                "baseline_eligible": True,
            },
        )[0])
        result = mature_candidate_outcomes(
            ledger, read_completed_history=lambda *_: _bars(2),
            as_of_utc="2026-01-06T22:00:00Z",
            horizons=STAGE6_OUTCOME_HORIZONS,
        )
        assert result.expected_candidate_horizons == 12
        assert result.accounted_candidate_horizons == 12
        assert result.population_reconciled is True
        observations = ledger.events_by_type("OUTCOME_OBSERVATION")
        assert any(e.payload["data_status"] == "DATA_EXCEPTION" for e in observations)
        assert any(e.payload["data_status"] == "DEFERRED_NOT_YET_OBSERVABLE" for e in observations)

    def test_option_history_is_joined_only_from_canonical_label(self, tmp_path):
        ledger = DecisionOutcomeLedger(tmp_path / "ledger.sqlite")
        _candidate(ledger)
        mature_candidate_outcomes(
            ledger, read_completed_history=lambda *_: _bars(),
            as_of_utc="2026-02-01T22:00:00Z", horizons=(1,),
        )
        control = tmp_path / "control.sqlite"
        payload = {
            "data_status": "COMPLETE", "terminal_executable_return": 0.25,
            "family_id": "FAMILY:AAA", "horizon_sessions": 1,
            "option_executable_mfe": 0.4, "option_executable_mae": -0.1,
            "first_two_sided_session": 1,
            "source_option_dataset_ids": ["OPTION-DATA"],
        }
        with sqlite3.connect(control) as connection:
            connection.execute(
                "CREATE TABLE doi_outcome_labels(assessment_id TEXT, "
                "horizon_sessions INTEGER, outcome_cutoff_utc TEXT, label_id TEXT, "
                "payload_json TEXT)"
            )
            connection.execute(
                "INSERT INTO doi_outcome_labels VALUES(?,?,?,?,?)",
                ("ASSESS:AAA", 1, "2026-01-03T22:00:00Z", "L1", json.dumps(payload)),
            )
            connection.execute(
                "INSERT INTO doi_outcome_labels VALUES(?,?,?,?,?)",
                ("ASSESS:ALT", 1, "2026-01-03T22:00:00Z", "L2", json.dumps({
                    **payload, "assessment_id": "ASSESS:ALT",
                    "terminal_executable_return": 0.40,
                })),
            )
        snapshot = build_outcome_learning_snapshot(
            ledger, policy=LearningActivationPolicy(), control_plane_path=control,
        )
        record = snapshot["records"][0]
        assert record["option_data_status"] == "COMPLETE"
        assert record["terminal_option_return"] == 0.25
        assert "OPTION-DATA" in record["source_dataset_ids"]
        assert record["family_member_outperformance_state"] == "OUTPERFORMED_BY_ALTERNATIVE"

    def test_governed_config_keeps_activation_disabled(self):
        policy = learning_policy_from_config(
            ROOT / "config" / "governed_constants_v1.json"
        )
        assert policy.model_activation_enabled is False
        assert policy.purge_embargo_sessions == 20


class TestStage6StoredRunReplay:
    @pytest.mark.parametrize(
        ("run_id", "completed_session"),
        [("20260910_150045", "2026-09-09"), ("20260911_115904", "2026-09-10")],
    )
    def test_stored_lab_population_is_replayable_without_model_activation(
        self, tmp_path, run_id, completed_session,
    ):
        book_path = (
            ROOT / "data" / "output" / "runs" / run_id / "intelligence_lab"
            / f"final_opportunity_book_{run_id}.json"
        )
        rows = json.loads(book_path.read_text(encoding="utf-8-sig"))["rows"]
        row = next(item for item in rows if (
            item.get("governed_direction") in {"CALL", "PUT"}
            and item.get("signal_price")
            and (item.get("target_price") or item.get("structural_target"))
            and item.get("invalidation_price")
        ))
        hold_text = str(row.get("hold_period") or row.get("time_horizon") or "")
        row["planned_hold_sessions"] = int(
            "".join(character if character.isdigit() else " " for character in hold_text).split()[-1]
        )
        ledger = DecisionOutcomeLedger(tmp_path / f"{run_id}.sqlite")
        event = candidate_events_from_rows(
            [row], run_id=run_id, occurred_at_utc=f"{completed_session}T22:00:00Z",
            decision_stage="EOD_THESIS",
            run_metadata={
                "completed_session": completed_session,
                "evidence_cutoff_utc": f"{completed_session}T22:00:00Z",
                "run_condition": "TEST",
                "baseline_eligible": False,
                "baseline_ineligibility_reason": "STORED_TEST_REPLAY",
            },
        )[0]
        ledger.append(event)
        prices = HistoricalPriceDatabase(
            ROOT / "data" / "canonical" / "historical_prices.sqlite"
        )
        result = mature_candidate_outcomes(
            ledger,
            read_completed_history=lambda ticker, start: prices.read(
                ticker, start_date=start, completed_only=True
            ),
            as_of_utc="2026-09-12T22:00:00Z",
            horizons=STAGE6_OUTCOME_HORIZONS,
        )
        assert result.population_reconciled is True
        snapshot = build_outcome_learning_snapshot(
            ledger,
            policy=learning_policy_from_config(
                ROOT / "config" / "governed_constants_v1.json"
            ),
        )
        assert snapshot["model_activation"]["can_activate"] is False
        assert snapshot["summary"]["presented_candidates"] == 1
        assert (
            snapshot["summary"]["complete_outcomes"]
            + snapshot["summary"]["data_exceptions"]
            + snapshot["summary"]["deferred_not_yet_observable"]
        ) == 6
