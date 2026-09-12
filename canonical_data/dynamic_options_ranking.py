"""DOI-9 application service and append-only contract ranking persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Mapping

from domain.dynamic_options_intelligence import ModelApplicabilityState
from domain.dynamic_options_probability import ProbabilityTarget
from domain.dynamic_options_ranking import (
    ContractRankingPolicy, FamilyRankingResult, RankedContract,
    RankingCandidateEvidence, RankingMode, RankingPolicyMetrics,
    RankingPolicyStatus, RankingWeights, rank_contract_family,
    family_ranking_identity, ranking_policy_identity,
)

from .dynamic_options_probability import DynamicOptionsProbabilityRepository
from .errors import DatasetValidationError
from .option_liquidity_lifecycle import OptionLifecycleConflict, OptionLiquidityLifecycleStore
from .registry import CanonicalRegistry


DOI_RANKING_SCHEMA_VERSION = "doi_contract_family_ranking_v1"
DOI_RANKING_SERVICE_VERSION = "doi-contract-family-ranking-service-v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(namespace: str, value: Any) -> str:
    return hashlib.sha256(f"{namespace}|{_canonical(value)}".encode("utf-8")).hexdigest()


def _metrics(value: Mapping[str, Any] | None) -> RankingPolicyMetrics | None:
    if not value:
        return None
    return RankingPolicyMetrics(
        cases=int(value["cases"]), selected_cases=int(value["selected_cases"]),
        mean_reward=float(value["mean_reward"]), positive_reward_rate=float(value["positive_reward_rate"]),
        baseline_mean_reward=float(value["baseline_mean_reward"]),
        baseline_positive_reward_rate=float(value["baseline_positive_reward_rate"]),
        reward_lift=float(value["reward_lift"]), coverage=float(value["coverage"]),
        baseline_coverage=float(value["baseline_coverage"]),
        temporal_windows=tuple(value.get("temporal_windows", ())),
    )


def _policy_from_dict(payload: Mapping[str, Any]) -> ContractRankingPolicy:
    value = dict(payload)
    value.pop("domain_version", None)
    value["status"] = RankingPolicyStatus(value["status"])
    value["weights"] = RankingWeights(**value["weights"]) if value.get("weights") else None
    value["created_at_utc"] = datetime.fromisoformat(value["created_at_utc"])
    for name in ("training_cutoff_utc", "validation_cutoff_utc", "holdout_cutoff_utc"):
        value[name] = datetime.fromisoformat(value[name]) if value.get(name) else None
    value["status_reasons"] = tuple(value["status_reasons"])
    value["source_replay_ids"] = tuple(value["source_replay_ids"])
    value["validation_metrics"] = _metrics(value.get("validation_metrics"))
    value["holdout_metrics"] = _metrics(value.get("holdout_metrics"))
    return ContractRankingPolicy(**value)


def _ranking_from_dict(payload: Mapping[str, Any]) -> FamilyRankingResult:
    value = dict(payload)
    value.pop("domain_version", None)
    value["mode"] = RankingMode(value["mode"])
    value["evidence_cutoff_utc"] = datetime.fromisoformat(value["evidence_cutoff_utc"])
    value["ranked_contracts"] = tuple(RankedContract(**item) for item in value["ranked_contracts"])
    value["input_dataset_ids"] = tuple(value["input_dataset_ids"])
    return FamilyRankingResult(**value)


class DynamicOptionsRankingRepository:
    def __init__(self, registry: CanonicalRegistry):
        self.registry = registry

    def initialise(self) -> None:
        with self.registry.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS doi_ranking_policies (
                    policy_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    decision_authority TEXT NOT NULL CHECK(decision_authority='NONE')
                );
                CREATE TABLE IF NOT EXISTS doi_family_rankings (
                    ranking_id TEXT PRIMARY KEY,
                    family_id TEXT NOT NULL,
                    direction TEXT NOT NULL CHECK(direction IN ('CALL','PUT')),
                    evidence_cutoff_utc TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    policy_id TEXT,
                    selected_assessment_id TEXT,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    decision_authority TEXT NOT NULL CHECK(decision_authority='NONE'),
                    execution_authority TEXT NOT NULL CHECK(execution_authority='HUMAN_ONLY'),
                    FOREIGN KEY(family_id) REFERENCES doi_contract_families(family_id),
                    FOREIGN KEY(policy_id) REFERENCES doi_ranking_policies(policy_id),
                    FOREIGN KEY(selected_assessment_id) REFERENCES doi_contract_assessments(assessment_id)
                );
                CREATE TRIGGER IF NOT EXISTS trg_doi_ranking_policy_no_update
                BEFORE UPDATE ON doi_ranking_policies BEGIN
                    SELECT RAISE(ABORT, 'DOI ranking policies are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_doi_ranking_policy_no_delete
                BEFORE DELETE ON doi_ranking_policies BEGIN
                    SELECT RAISE(ABORT, 'DOI ranking policies are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_doi_family_ranking_no_update
                BEFORE UPDATE ON doi_family_rankings BEGIN
                    SELECT RAISE(ABORT, 'DOI family rankings are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS trg_doi_family_ranking_no_delete
                BEFORE DELETE ON doi_family_rankings BEGIN
                    SELECT RAISE(ABORT, 'DOI family rankings are append-only');
                END;
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_metadata(schema_version, installed_at) VALUES (?, ?)",
                (DOI_RANKING_SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
            )

    def record_policy(self, policy: ContractRankingPolicy) -> tuple[ContractRankingPolicy, bool]:
        expected_id = ranking_policy_identity(
            policy_version=policy.policy_version,
            created_at_utc=policy.created_at_utc,
            source_replay_ids=policy.source_replay_ids,
        )
        if policy.policy_id != expected_id:
            raise DatasetValidationError("ranking policy identity does not match immutable inputs")
        payload = policy.to_dict()
        payload_json, payload_hash = _canonical(payload), _hash("DOI_RANKING_POLICY_PAYLOAD_V1", payload)
        with self.registry.connection() as connection:
            existing = connection.execute("SELECT * FROM doi_ranking_policies WHERE policy_id=?", (policy.policy_id,)).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash:
                    raise OptionLifecycleConflict("ranking policy identity has different immutable content")
                return _policy_from_dict(json.loads(existing["payload_json"])), True
            connection.execute(
                "INSERT INTO doi_ranking_policies VALUES (?,?,?,?,?,?)",
                (policy.policy_id, policy.status.value, policy.created_at_utc.isoformat(),
                 payload_json, payload_hash, policy.decision_authority),
            )
        return policy, False

    def policy(self, policy_id: str) -> ContractRankingPolicy | None:
        with self.registry.connection() as connection:
            row = connection.execute("SELECT payload_json FROM doi_ranking_policies WHERE policy_id=?", (policy_id,)).fetchone()
        return _policy_from_dict(json.loads(row["payload_json"])) if row else None

    def record_ranking(self, ranking: FamilyRankingResult) -> tuple[FamilyRankingResult, bool]:
        expected_id = family_ranking_identity(
            family_id=ranking.family_id,
            evidence_cutoff_utc=ranking.evidence_cutoff_utc,
            policy_id=ranking.policy_id,
            previous_contract_symbol=ranking.previous_contract_symbol,
            assessment_ids=tuple(item.assessment_id for item in ranking.ranked_contracts),
        )
        if ranking.ranking_id != expected_id:
            raise DatasetValidationError("family ranking identity does not match immutable inputs")
        payload = ranking.to_dict()
        payload_json, payload_hash = _canonical(payload), _hash("DOI_FAMILY_RANKING_PAYLOAD_V1", payload)
        with self.registry.connection() as connection:
            family = connection.execute(
                "SELECT governed_direction FROM doi_contract_families WHERE family_id=?",
                (ranking.family_id,),
            ).fetchone()
            if family is None or family["governed_direction"] != ranking.direction:
                raise DatasetValidationError("ranking family or direction is invalid")
            if ranking.policy_id and connection.execute(
                "SELECT 1 FROM doi_ranking_policies WHERE policy_id=?", (ranking.policy_id,)
            ).fetchone() is None:
                raise DatasetValidationError("ranking policy does not exist")
            assessment_ids = tuple(item.assessment_id for item in ranking.ranked_contracts)
            if assessment_ids:
                placeholders = ",".join("?" for _ in assessment_ids)
                rows = connection.execute(
                    f"SELECT assessment_id, family_id, input_dataset_ids_json FROM doi_contract_assessments WHERE assessment_id IN ({placeholders})",
                    assessment_ids,
                ).fetchall()
                if len(rows) != len(assessment_ids) or any(row["family_id"] != ranking.family_id for row in rows):
                    raise DatasetValidationError("ranking contains an assessment outside its family")
                assessment_datasets = {item for row in rows for item in json.loads(row["input_dataset_ids_json"])}
                if not set(ranking.input_dataset_ids) <= assessment_datasets:
                    raise DatasetValidationError("ranking lineage exceeds assessment evidence")
            existing = connection.execute("SELECT * FROM doi_family_rankings WHERE ranking_id=?", (ranking.ranking_id,)).fetchone()
            if existing:
                if existing["payload_hash"] != payload_hash:
                    raise OptionLifecycleConflict("family ranking identity has different immutable content")
                return _ranking_from_dict(json.loads(existing["payload_json"])), True
            connection.execute(
                "INSERT INTO doi_family_rankings VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (ranking.ranking_id, ranking.family_id, ranking.direction,
                 ranking.evidence_cutoff_utc.isoformat(), ranking.mode.value,
                 ranking.policy_id, ranking.selected_assessment_id, payload_json,
                 payload_hash, ranking.decision_authority, ranking.execution_authority),
            )
        return ranking, False

    def ranking(self, ranking_id: str) -> FamilyRankingResult | None:
        with self.registry.connection() as connection:
            row = connection.execute("SELECT payload_json FROM doi_family_rankings WHERE ranking_id=?", (ranking_id,)).fetchone()
        return _ranking_from_dict(json.loads(row["payload_json"])) if row else None


@dataclass(frozen=True, slots=True)
class RankingServiceResult:
    ranking: FamilyRankingResult
    ranking_reused: bool
    candidate_count: int
    calibrated_candidate_count: int
    deterministic_candidate_count: int
    no_score_candidate_count: int
    deleted_candidate_count: int = 0
    provider_calls: int = 0

    def __post_init__(self) -> None:
        if self.candidate_count != self.deterministic_candidate_count + self.no_score_candidate_count:
            raise ValueError("ranking candidate population does not reconcile")
        if len(self.ranking.ranked_contracts) != self.candidate_count:
            raise ValueError("every family candidate must remain in ranking output")
        if self.deleted_candidate_count or self.provider_calls:
            raise ValueError("DOI-9 cannot delete candidates or acquire provider data")


class DynamicOptionsContractRankingService:
    def __init__(self, store: OptionLiquidityLifecycleStore):
        self.store = store
        self.probabilities = DynamicOptionsProbabilityRepository(store.registry)
        self.repository = DynamicOptionsRankingRepository(store.registry)

    def rank_family(
        self, *, family_id: str, previous_contract_symbol: str | None = None,
        policy: ContractRankingPolicy | None = None,
    ) -> RankingServiceResult:
        self.probabilities.initialise()
        self.repository.initialise()
        family = self.store.contract_family(family_id)
        if family is None:
            raise DatasetValidationError("ranking family does not exist")
        latest_by_symbol: dict[str, Any] = {}
        for assessment in self.store.assessments_for_family(family_id):
            current = latest_by_symbol.get(assessment.contract_symbol)
            if current is None or (assessment.evidence_cutoff_utc, assessment.assessment_id) > (current.evidence_cutoff_utc, current.assessment_id):
                latest_by_symbol[assessment.contract_symbol] = assessment
        candidates = []
        for assessment in latest_by_symbol.values():
            inference_groups: dict[ProbabilityTarget, list[Any]] = {}
            for inference in self.probabilities.inferences_for_assessment(assessment.assessment_id):
                if inference.applicability_state is ModelApplicabilityState.APPLICABLE:
                    inference_groups.setdefault(inference.target, []).append(inference)

            # Multiple accepted results for the same assessment/target are ambiguous.
            # Do not let database row order choose the contract ranking evidence.
            def unique_inference(target_name: ProbabilityTarget):
                matches = inference_groups.get(target_name, ())
                return matches[0] if len(matches) == 1 else None

            liquidity = unique_inference(ProbabilityTarget.LIQUIDITY_3D)
            positive = unique_inference(ProbabilityTarget.POSITIVE_RETURN)
            target = unique_inference(ProbabilityTarget.TARGET_BEFORE_INVALIDATION)
            selected_inferences = [item for item in (liquidity, positive, target) if item is not None]
            valuation = assessment.metadata.get("valuation", {})
            adverse = valuation.get("adverse_worst_return") if isinstance(valuation, Mapping) else None
            candidates.append(RankingCandidateEvidence(
                assessment_id=assessment.assessment_id,
                contract_symbol=assessment.contract_symbol,
                direction=family.thesis.governed_direction,
                evidence_cutoff_utc=assessment.evidence_cutoff_utc,
                input_dataset_ids=assessment.input_dataset_ids,
                deterministic_score=assessment.ranking_score_uncalibrated,
                p_liquidity_3d=liquidity.probability if liquidity else None,
                p_positive_return=positive.probability if positive else None,
                p_target_before_invalidation=target.probability if target else None,
                model_uncertainty=max((
                    item.uncertainty if item.uncertainty is not None else 1.0
                    for item in selected_inferences
                ), default=None),
                adverse_worst_return=adverse,
                observation_quality=assessment.entry_state.value,
                probability_model_ids=tuple(item.model_id for item in selected_inferences),
            ))
        ranking = rank_contract_family(
            family_id=family.family_id, direction=family.thesis.governed_direction,
            candidates=tuple(candidates), previous_contract_symbol=previous_contract_symbol,
            policy=policy,
        )
        persisted, reused = self.repository.record_ranking(ranking)
        deterministic = sum(item.deterministic_score is not None for item in candidates)
        calibrated = sum(item.calibrated_components_complete for item in candidates)
        return RankingServiceResult(
            ranking=persisted, ranking_reused=reused, candidate_count=len(candidates),
            calibrated_candidate_count=calibrated,
            deterministic_candidate_count=deterministic,
            no_score_candidate_count=len(candidates) - deterministic,
        )


__all__ = [
    "DOI_RANKING_SCHEMA_VERSION", "DOI_RANKING_SERVICE_VERSION",
    "DynamicOptionsContractRankingService", "DynamicOptionsRankingRepository",
    "RankingServiceResult",
]
