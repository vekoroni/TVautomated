"""Pure DOI-9 contract-family ranking and chronological policy evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import itertools
import json
import math
from typing import Any, Mapping, Sequence

from .dynamic_options_intelligence import DOI_DECISION_AUTHORITY, DOI_EXECUTION_AUTHORITY


DOI_RANKING_DOMAIN_VERSION = "doi-contract-family-ranking-v1"
DOI_RANKING_POLICY_VERSION = "doi-ranking-policy-v1"


class RankingMode(str, Enum):
    CALIBRATED_POLICY = "CALIBRATED_POLICY"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"
    NO_COMPARABLE_SCORE = "NO_COMPARABLE_SCORE"


class RankingPolicyStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    INSUFFICIENT_REPLAY_SUPPORT = "INSUFFICIENT_REPLAY_SUPPORT"
    REJECTED_NO_OUT_OF_SAMPLE_LIFT = "REJECTED_NO_OUT_OF_SAMPLE_LIFT"
    REJECTED_TEMPORAL_INSTABILITY = "REJECTED_TEMPORAL_INSTABILITY"


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _required(value: Any, name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{name} is required")
    return result


def _token(value: Any, name: str) -> str:
    return _required(value, name).upper()


def _finite_optional(value: Any, name: str) -> float | None:
    if value is None:
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _identity(namespace: str, value: Any) -> str:
    return hashlib.sha256(f"{namespace}|{_canonical(value)}".encode("utf-8")).hexdigest()


def ranking_policy_identity(**values: Any) -> str:
    """Reproduce a policy identity without trusting a supplied identifier."""

    identity = {
        "policy_version": _required(values["policy_version"], "policy_version"),
        "created_at_utc": _utc(values["created_at_utc"], "created_at_utc").isoformat(),
        "source_replay_ids": sorted({
            _required(item, "source_replay_id")
            for item in values.get("source_replay_ids", ())
        }),
    }
    return _identity("DOI_RANKING_POLICY_V1", identity)


def family_ranking_identity(
    *, family_id: str, evidence_cutoff_utc: datetime, policy_id: str | None,
    previous_contract_symbol: str | None, assessment_ids: Sequence[str],
) -> str:
    """Reproduce a family ranking identity from its immutable natural key."""

    identity = {
        "family_id": _required(family_id, "family_id"),
        "cutoff": _utc(evidence_cutoff_utc, "evidence_cutoff_utc").isoformat(),
        "policy_id": str(policy_id).strip() if policy_id else None,
        "previous": str(previous_contract_symbol).strip() if previous_contract_symbol else None,
        "assessment_ids": sorted({
            _required(item, "assessment_id") for item in assessment_ids
        }),
    }
    return _identity("DOI_FAMILY_RANKING_V1", identity)


@dataclass(frozen=True, slots=True)
class RankingWeights:
    deterministic: float
    liquidity: float
    positive_return: float
    target_before_invalidation: float
    uncertainty_penalty: float

    def __post_init__(self) -> None:
        values = [float(getattr(self, name)) for name in self.__dataclass_fields__]
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("ranking weights must be finite and non-negative")
        if not math.isclose(sum(values), 1.0, abs_tol=1e-9):
            raise ValueError("ranking weights must sum to one")

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RankingCandidateEvidence:
    assessment_id: str
    contract_symbol: str
    direction: str
    evidence_cutoff_utc: datetime
    input_dataset_ids: tuple[str, ...]
    deterministic_score: float | None
    p_liquidity_3d: float | None = None
    p_positive_return: float | None = None
    p_target_before_invalidation: float | None = None
    model_uncertainty: float | None = None
    adverse_worst_return: float | None = None
    observation_quality: str = "UNKNOWN"
    probability_model_ids: tuple[str, ...] = ()
    decision_authority: str = DOI_DECISION_AUTHORITY

    def __post_init__(self) -> None:
        object.__setattr__(self, "assessment_id", _required(self.assessment_id, "assessment_id"))
        object.__setattr__(self, "contract_symbol", _token(self.contract_symbol, "contract_symbol"))
        direction = _token(self.direction, "direction")
        if direction not in {"CALL", "PUT"}:
            raise ValueError("direction must be CALL or PUT")
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "evidence_cutoff_utc", _utc(self.evidence_cutoff_utc, "evidence_cutoff_utc"))
        datasets = tuple(sorted({_required(item, "input_dataset_id") for item in self.input_dataset_ids}))
        if not datasets:
            raise ValueError("candidate ranking lineage is required")
        object.__setattr__(self, "input_dataset_ids", datasets)
        object.__setattr__(self, "probability_model_ids", tuple(sorted({_required(item, "model_id") for item in self.probability_model_ids})))
        for name in (
            "deterministic_score", "p_liquidity_3d", "p_positive_return",
            "p_target_before_invalidation", "model_uncertainty", "adverse_worst_return",
        ):
            object.__setattr__(self, name, _finite_optional(getattr(self, name), name))
        for name in ("p_liquidity_3d", "p_positive_return", "p_target_before_invalidation", "model_uncertainty"):
            value = getattr(self, name)
            if value is not None and not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between zero and one")
        object.__setattr__(self, "observation_quality", _token(self.observation_quality, "observation_quality"))
        if self.decision_authority != DOI_DECISION_AUTHORITY:
            raise ValueError("ranking evidence has no decision authority")

    @property
    def calibrated_components_complete(self) -> bool:
        return (
            self.deterministic_score is not None
            and self.p_liquidity_3d is not None
            and self.p_positive_return is not None
            and self.p_target_before_invalidation is not None
            and self.model_uncertainty is not None
            and len(self.probability_model_ids) >= 3
        )

    def calibrated_utility(self, weights: RankingWeights) -> float | None:
        if not self.calibrated_components_complete:
            return None
        return (
            weights.deterministic * float(self.deterministic_score)
            + weights.liquidity * float(self.p_liquidity_3d)
            + weights.positive_return * float(self.p_positive_return)
            + weights.target_before_invalidation * float(self.p_target_before_invalidation)
            - weights.uncertainty_penalty * float(self.model_uncertainty)
        )


@dataclass(frozen=True, slots=True)
class RankingPolicyMetrics:
    cases: int
    selected_cases: int
    mean_reward: float
    positive_reward_rate: float
    baseline_mean_reward: float
    baseline_positive_reward_rate: float
    reward_lift: float
    coverage: float
    baseline_coverage: float
    temporal_windows: tuple[Mapping[str, float | int | bool], ...] = ()

    def __post_init__(self) -> None:
        if self.cases < 0 or not 0 <= self.selected_cases <= self.cases:
            raise ValueError("ranking metric population is invalid")
        for name in (
            "mean_reward", "positive_reward_rate", "baseline_mean_reward",
            "baseline_positive_reward_rate", "reward_lift", "coverage", "baseline_coverage",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if not 0 <= self.coverage <= 1 or not 0 <= self.baseline_coverage <= 1:
            raise ValueError("ranking coverage must be between zero and one")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["temporal_windows"] = [dict(item) for item in self.temporal_windows]
        return result


@dataclass(frozen=True, slots=True)
class ContractRankingPolicy:
    policy_id: str
    policy_version: str
    status: RankingPolicyStatus
    status_reasons: tuple[str, ...]
    weights: RankingWeights | None
    minimum_switch_margin: float | None
    created_at_utc: datetime
    training_cutoff_utc: datetime | None
    validation_cutoff_utc: datetime | None
    holdout_cutoff_utc: datetime | None
    training_cases: int
    validation_cases: int
    holdout_cases: int
    source_replay_ids: tuple[str, ...]
    validation_metrics: RankingPolicyMetrics | None
    holdout_metrics: RankingPolicyMetrics | None
    decision_authority: str = DOI_DECISION_AUTHORITY
    can_change_direction: bool = False
    can_invalidate_thesis: bool = False
    can_grant_capital: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _required(self.policy_id, "policy_id"))
        object.__setattr__(self, "policy_version", _required(self.policy_version, "policy_version"))
        object.__setattr__(self, "status", self.status if isinstance(self.status, RankingPolicyStatus) else RankingPolicyStatus(str(self.status)))
        object.__setattr__(self, "status_reasons", tuple(_token(item, "status_reason") for item in self.status_reasons))
        object.__setattr__(self, "created_at_utc", _utc(self.created_at_utc, "created_at_utc"))
        for name in ("training_cutoff_utc", "validation_cutoff_utc", "holdout_cutoff_utc"):
            if getattr(self, name) is not None:
                object.__setattr__(self, name, _utc(getattr(self, name), name))
        for name in ("training_cases", "validation_cases", "holdout_cases"):
            if int(getattr(self, name)) < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.minimum_switch_margin is not None:
            margin = float(self.minimum_switch_margin)
            if not math.isfinite(margin) or margin < 0:
                raise ValueError("minimum_switch_margin must be finite and non-negative")
        object.__setattr__(self, "source_replay_ids", tuple(sorted({_required(item, "source_replay_id") for item in self.source_replay_ids})))
        if self.status is RankingPolicyStatus.ACCEPTED:
            if (
                self.weights is None or self.minimum_switch_margin is None
                or self.validation_metrics is None or self.holdout_metrics is None
            ):
                raise ValueError("accepted ranking policy requires weights, margin, validation and holdout metrics")
            if (
                self.validation_metrics.reward_lift < 0
                or self.validation_metrics.coverage < self.validation_metrics.baseline_coverage
            ):
                raise ValueError("accepted ranking policy cannot regress on validation")
            if self.holdout_metrics.reward_lift <= 0 or self.holdout_metrics.coverage < self.holdout_metrics.baseline_coverage:
                raise ValueError("accepted ranking policy must improve reward without reducing coverage")
            if not self.holdout_metrics.temporal_windows or any(
                not bool(item.get("baseline_not_worse"))
                for item in self.holdout_metrics.temporal_windows
            ):
                raise ValueError("accepted ranking policy must be temporally stable")
        if self.decision_authority != DOI_DECISION_AUTHORITY:
            raise ValueError("ranking policy has no decision authority")
        if self.can_change_direction or self.can_invalidate_thesis or self.can_grant_capital:
            raise ValueError("ranking policy cannot possess trading authority")

    @classmethod
    def create(cls, **values: Any) -> "ContractRankingPolicy":
        return cls(policy_id=ranking_policy_identity(**values), **values)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = self.status.value
        result["weights"] = self.weights.to_dict() if self.weights else None
        result["created_at_utc"] = self.created_at_utc.isoformat()
        for name in ("training_cutoff_utc", "validation_cutoff_utc", "holdout_cutoff_utc"):
            result[name] = getattr(self, name).isoformat() if getattr(self, name) else None
        result["status_reasons"] = list(self.status_reasons)
        result["source_replay_ids"] = list(self.source_replay_ids)
        result["validation_metrics"] = self.validation_metrics.to_dict() if self.validation_metrics else None
        result["holdout_metrics"] = self.holdout_metrics.to_dict() if self.holdout_metrics else None
        result["domain_version"] = DOI_RANKING_DOMAIN_VERSION
        return result


@dataclass(frozen=True, slots=True)
class RankedContract:
    assessment_id: str
    contract_symbol: str
    rank: int
    score: float | None
    score_kind: str
    explanation: str
    selected: bool


@dataclass(frozen=True, slots=True)
class FamilyRankingResult:
    ranking_id: str
    family_id: str
    direction: str
    evidence_cutoff_utc: datetime
    mode: RankingMode
    policy_id: str | None
    previous_contract_symbol: str | None
    selected_assessment_id: str | None
    selected_contract_symbol: str | None
    selection_reason: str
    switched_contract: bool
    hysteresis_applied: bool
    hysteresis_suppressed_switch: bool
    score_margin: float | None
    ranked_contracts: tuple[RankedContract, ...]
    input_dataset_ids: tuple[str, ...]
    retain_opportunity: bool = True
    decision_authority: str = DOI_DECISION_AUTHORITY
    execution_authority: str = DOI_EXECUTION_AUTHORITY

    def __post_init__(self) -> None:
        object.__setattr__(self, "ranking_id", _required(self.ranking_id, "ranking_id"))
        object.__setattr__(self, "family_id", _required(self.family_id, "family_id"))
        direction = _token(self.direction, "direction")
        if direction not in {"CALL", "PUT"}:
            raise ValueError("direction must be CALL or PUT")
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "evidence_cutoff_utc", _utc(self.evidence_cutoff_utc, "evidence_cutoff_utc"))
        object.__setattr__(self, "mode", self.mode if isinstance(self.mode, RankingMode) else RankingMode(str(self.mode)))
        if len({item.assessment_id for item in self.ranked_contracts}) != len(self.ranked_contracts):
            raise ValueError("each assessment must appear once in ranking")
        expected_ranks = tuple(range(1, len(self.ranked_contracts) + 1))
        if tuple(item.rank for item in self.ranked_contracts) != expected_ranks:
            raise ValueError("ranking rows must have consecutive one-based ranks")
        selected = [item for item in self.ranked_contracts if item.selected]
        if self.selected_assessment_id is None:
            if selected:
                raise ValueError("ranking without selection cannot mark a selected row")
        elif len(selected) != 1 or selected[0].assessment_id != self.selected_assessment_id:
            raise ValueError("selected ranking population does not reconcile")
        if selected and selected[0].contract_symbol != self.selected_contract_symbol:
            raise ValueError("selected contract symbol does not reconcile")
        object.__setattr__(self, "input_dataset_ids", tuple(sorted({
            _required(item, "input_dataset_id") for item in self.input_dataset_ids
        })))
        if not self.retain_opportunity:
            raise ValueError("contract ranking cannot remove an opportunity")
        if self.decision_authority != DOI_DECISION_AUTHORITY or self.execution_authority != DOI_EXECUTION_AUTHORITY:
            raise ValueError("contract ranking cannot possess decision or execution authority")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["mode"] = self.mode.value
        result["evidence_cutoff_utc"] = self.evidence_cutoff_utc.isoformat()
        result["ranked_contracts"] = [asdict(item) for item in self.ranked_contracts]
        result["input_dataset_ids"] = list(self.input_dataset_ids)
        result["domain_version"] = DOI_RANKING_DOMAIN_VERSION
        return result


def rank_contract_family(
    *, family_id: str, direction: str, candidates: Sequence[RankingCandidateEvidence],
    previous_contract_symbol: str | None = None,
    policy: ContractRankingPolicy | None = None,
    deterministic_fallback_margin: float = 0.05,
    deterministic_fallback_relative_margin: float = 0.10,
) -> FamilyRankingResult:
    """Rank all candidates; incomplete models trigger a whole-family fallback."""

    if len({item.assessment_id for item in candidates}) != len(candidates):
        raise ValueError("duplicate assessment in family ranking")
    if any(item.direction != direction.upper() for item in candidates):
        raise ValueError("ranking candidate direction conflicts with thesis")
    enhanced = bool(
        policy and policy.status is RankingPolicyStatus.ACCEPTED and candidates
        and all(item.calibrated_components_complete for item in candidates if item.deterministic_score is not None)
    )
    mode = RankingMode.CALIBRATED_POLICY if enhanced else RankingMode.DETERMINISTIC_FALLBACK
    scored: list[tuple[RankingCandidateEvidence, float | None, str, str]] = []
    for item in candidates:
        if enhanced:
            score = item.calibrated_utility(policy.weights)  # type: ignore[arg-type]
            explanation = (
                f"calibrated utility: deterministic={item.deterministic_score}; "
                f"liquidity_3d={item.p_liquidity_3d}; positive_return={item.p_positive_return}; "
                f"target_first={item.p_target_before_invalidation}; uncertainty={item.model_uncertainty}"
            )
            kind = "CALIBRATED_POLICY_UTILITY"
        else:
            score = item.deterministic_score
            explanation = (
                "DOI-5 deterministic fallback; calibrated family coverage or accepted "
                "DOI-9 policy unavailable"
            )
            kind = (
                "CONTRACT_ECONOMICS_V2_DETERMINISTIC_UTILITY"
                if score is not None else "NO_COMPARABLE_SCORE"
            )
        scored.append((item, score, kind, explanation))
    ordered = sorted(scored, key=lambda row: (row[1] is None, -(row[1] or 0.0), row[0].contract_symbol))
    comparable = [row for row in ordered if row[1] is not None]
    selected = comparable[0] if comparable else None
    applied = previous_contract_symbol is not None and any(row[0].contract_symbol == previous_contract_symbol for row in ordered)
    suppressed = False
    switched = False
    margin = None
    reason = "NO_COMPARABLE_CONTRACT_UTILITY"
    if selected is not None:
        reason = "CALIBRATED_POLICY_TOP_RANK" if enhanced else "DETERMINISTIC_FALLBACK_TOP_RANK"
        previous = next((row for row in comparable if row[0].contract_symbol == previous_contract_symbol), None)
        threshold = float(policy.minimum_switch_margin) if enhanced else float(deterministic_fallback_margin)  # type: ignore[arg-type]
        if previous is not None and previous[0].contract_symbol != selected[0].contract_symbol:
            margin = float(selected[1]) - float(previous[1])
            if not enhanced:
                threshold = max(
                    threshold,
                    float(deterministic_fallback_relative_margin)
                    * abs(float(previous[1])),
                )
            if margin < threshold:
                selected = previous
                suppressed = True
                reason = "RETAIN_CURRENT_HYSTERESIS"
            else:
                switched = True
                reason = "SUPERSEDE_RANKING_MARGIN"
        elif previous_contract_symbol and previous is None:
            switched = selected[0].contract_symbol != previous_contract_symbol
            reason = "SUPERSEDE_CONTRACT_OUTSIDE_CURRENT_FAMILY"
        elif previous is not None:
            reason = "RETAIN_CURRENT_TOP_RANK"
    if not comparable:
        mode = RankingMode.NO_COMPARABLE_SCORE
    selected_id = selected[0].assessment_id if selected else None
    ranked_rows = tuple(
        RankedContract(
            assessment_id=item.assessment_id, contract_symbol=item.contract_symbol,
            rank=index, score=score, score_kind=kind, explanation=explanation,
            selected=item.assessment_id == selected_id,
        )
        for index, (item, score, kind, explanation) in enumerate(ordered, 1)
    )
    cutoff = max((item.evidence_cutoff_utc for item in candidates), default=datetime.now(timezone.utc))
    datasets = tuple(sorted({dataset for item in candidates for dataset in item.input_dataset_ids}))
    return FamilyRankingResult(
        ranking_id=family_ranking_identity(
            family_id=family_id, evidence_cutoff_utc=cutoff,
            policy_id=policy.policy_id if enhanced and policy else None,
            previous_contract_symbol=previous_contract_symbol,
            assessment_ids=tuple(item.assessment_id for item in candidates),
        ), family_id=family_id,
        direction=direction, evidence_cutoff_utc=cutoff, mode=mode,
        policy_id=policy.policy_id if enhanced and policy else None,
        previous_contract_symbol=previous_contract_symbol,
        selected_assessment_id=selected_id,
        selected_contract_symbol=selected[0].contract_symbol if selected else None,
        selection_reason=reason, switched_contract=switched,
        hysteresis_applied=applied, hysteresis_suppressed_switch=suppressed,
        score_margin=margin, ranked_contracts=ranked_rows, input_dataset_ids=datasets,
    )


@dataclass(frozen=True, slots=True)
class RankingReplayCase:
    replay_id: str
    feature_cutoff_utc: datetime
    outcome_cutoff_utc: datetime
    candidates: tuple[RankingCandidateEvidence, ...]
    future_reward_by_assessment: Mapping[str, float]
    previous_contract_symbol: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "replay_id", _required(self.replay_id, "replay_id"))
        object.__setattr__(self, "feature_cutoff_utc", _utc(self.feature_cutoff_utc, "feature_cutoff_utc"))
        object.__setattr__(self, "outcome_cutoff_utc", _utc(self.outcome_cutoff_utc, "outcome_cutoff_utc"))
        if self.outcome_cutoff_utc <= self.feature_cutoff_utc:
            raise ValueError("ranking replay outcome must follow feature cutoff")
        ids = {item.assessment_id for item in self.candidates}
        if set(self.future_reward_by_assessment) != ids:
            raise ValueError("every ranking candidate requires exactly one future reward")
        object.__setattr__(self, "future_reward_by_assessment", {
            key: float(value) for key, value in self.future_reward_by_assessment.items()
        })


@dataclass(frozen=True, slots=True)
class RankingReplayPolicy:
    min_training_cases: int = 100
    min_validation_cases: int = 30
    min_holdout_cases: int = 30
    weight_grid_step: float = 0.25
    minimum_temporal_window: int = 10

    def __post_init__(self) -> None:
        for name in (
            "min_training_cases", "min_validation_cases", "min_holdout_cases",
            "minimum_temporal_window",
        ):
            if int(getattr(self, name)) < 1:
                raise ValueError(f"{name} must be positive")
        step = float(self.weight_grid_step)
        if not math.isfinite(step) or not 0 < step <= 1:
            raise ValueError("weight_grid_step must be finite and in (0, 1]")


def _split_cases(cases: Sequence[RankingReplayCase]):
    ordered = tuple(sorted(cases, key=lambda item: (item.feature_cutoff_utc, item.replay_id)))
    if len(ordered) < 3:
        return ordered, (), (), ()
    v = max(1, int(len(ordered) * 0.60))
    h = min(max(v + 1, int(len(ordered) * 0.80)), len(ordered) - 1)
    validation_start, holdout_start = ordered[v].feature_cutoff_utc, ordered[h].feature_cutoff_utc
    training = tuple(item for item in ordered[:v] if item.outcome_cutoff_utc < validation_start)
    validation = tuple(item for item in ordered[v:h] if item.outcome_cutoff_utc < holdout_start)
    holdout = ordered[h:]
    kept = {item.replay_id for item in training + validation + holdout}
    return training, validation, holdout, tuple(item for item in ordered if item.replay_id not in kept)


def _weight_grid(step: float) -> tuple[RankingWeights, ...]:
    units = round(1.0 / step)
    if units < 1 or not math.isclose(units * step, 1.0, abs_tol=1e-9):
        raise ValueError("weight_grid_step must divide one exactly")
    result = []
    for parts in itertools.product(range(units + 1), repeat=5):
        if sum(parts) == units:
            result.append(RankingWeights(*(part / units for part in parts)))
    return tuple(result)


def _case_choice(case: RankingReplayCase, weights: RankingWeights | None, margin: float):
    if weights is None:
        values = [(item, item.deterministic_score) for item in case.candidates]
    else:
        values = [(item, item.calibrated_utility(weights)) for item in case.candidates]
    ranked = sorted((row for row in values if row[1] is not None), key=lambda row: (-float(row[1]), row[0].contract_symbol))
    if not ranked:
        return None
    best = ranked[0]
    previous = next((row for row in ranked if row[0].contract_symbol == case.previous_contract_symbol), None)
    if previous and previous[0].assessment_id != best[0].assessment_id and float(best[1]) - float(previous[1]) < margin:
        return previous[0]
    return best[0]


def _evaluate_cases(
    cases: Sequence[RankingReplayCase], weights: RankingWeights, margin: float, *,
    temporal: bool = False, minimum_temporal_window: int = 10,
) -> RankingPolicyMetrics:
    rewards, baseline_rewards = [], []
    for case in cases:
        selected = _case_choice(case, weights, margin)
        baseline = _case_choice(case, None, 0.10)
        if selected:
            rewards.append(case.future_reward_by_assessment[selected.assessment_id])
        if baseline:
            baseline_rewards.append(case.future_reward_by_assessment[baseline.assessment_id])
    count = len(cases)
    mean = sum(rewards) / len(rewards) if rewards else 0.0
    base_mean = sum(baseline_rewards) / len(baseline_rewards) if baseline_rewards else 0.0
    windows = []
    if temporal and count >= 2 * minimum_temporal_window:
        midpoint = count // 2
        for number, subset in enumerate((cases[:midpoint], cases[midpoint:]), 1):
            if not subset:
                continue
            window = _evaluate_cases(subset, weights, margin, temporal=False)
            windows.append({
                "window": number, "cases": len(subset), "reward_lift": window.reward_lift,
                "coverage": window.coverage, "baseline_coverage": window.baseline_coverage,
                "baseline_not_worse": window.reward_lift >= 0 and window.coverage >= window.baseline_coverage,
            })
    return RankingPolicyMetrics(
        cases=count, selected_cases=len(rewards), mean_reward=mean,
        positive_reward_rate=sum(value > 0 for value in rewards) / len(rewards) if rewards else 0.0,
        baseline_mean_reward=base_mean,
        baseline_positive_reward_rate=sum(value > 0 for value in baseline_rewards) / len(baseline_rewards) if baseline_rewards else 0.0,
        reward_lift=mean - base_mean, coverage=len(rewards) / count if count else 0.0,
        baseline_coverage=len(baseline_rewards) / count if count else 0.0,
        temporal_windows=tuple(windows),
    )


def tune_ranking_policy(
    cases: Sequence[RankingReplayCase], *, created_at_utc: datetime,
    policy: RankingReplayPolicy = RankingReplayPolicy(),
) -> ContractRankingPolicy:
    training, validation, holdout, _ = _split_cases(cases)
    source_ids = tuple(item.replay_id for item in cases)
    base = dict(
        policy_version=DOI_RANKING_POLICY_VERSION, created_at_utc=created_at_utc,
        training_cutoff_utc=max((item.outcome_cutoff_utc for item in training), default=None),
        validation_cutoff_utc=max((item.outcome_cutoff_utc for item in validation), default=None),
        holdout_cutoff_utc=max((item.outcome_cutoff_utc for item in holdout), default=None),
        training_cases=len(training), validation_cases=len(validation), holdout_cases=len(holdout),
        source_replay_ids=source_ids,
    )
    if (
        len(training) < policy.min_training_cases
        or len(validation) < policy.min_validation_cases
        or len(holdout) < policy.min_holdout_cases
        or any(not all(item.calibrated_components_complete for item in case.candidates) for case in cases)
    ):
        return ContractRankingPolicy.create(
            status=RankingPolicyStatus.INSUFFICIENT_REPLAY_SUPPORT,
            status_reasons=("INSUFFICIENT_CHRONOLOGICAL_CALIBRATED_REPLAY",),
            weights=None, minimum_switch_margin=None,
            validation_metrics=None, holdout_metrics=None, **base,
        )
    best = None
    for weights in _weight_grid(policy.weight_grid_step):
        raw_differences = []
        for case in training:
            scores = sorted((item.calibrated_utility(weights) for item in case.candidates), reverse=True)
            if len(scores) >= 2:
                raw_differences.append(float(scores[0]) - float(scores[1]))
        margins = {0.0}
        if raw_differences:
            ordered = sorted(raw_differences)
            margins.update(ordered[int((len(ordered) - 1) * quantile)] for quantile in (0.25, 0.50, 0.75))
        for margin in margins:
            train_metrics = _evaluate_cases(training, weights, margin)
            validation_metrics = _evaluate_cases(validation, weights, margin)
            key = (validation_metrics.mean_reward, train_metrics.mean_reward, -margin, weights.deterministic)
            if best is None or key > best[0]:
                best = (key, weights, margin, validation_metrics)
    _, weights, margin, validation_metrics = best
    holdout_metrics = _evaluate_cases(
        holdout, weights, margin, temporal=True,
        minimum_temporal_window=policy.minimum_temporal_window,
    )
    validation_ok = validation_metrics.reward_lift >= 0 and validation_metrics.coverage >= validation_metrics.baseline_coverage
    holdout_ok = holdout_metrics.reward_lift > 0 and holdout_metrics.coverage >= holdout_metrics.baseline_coverage
    temporal_ok = bool(holdout_metrics.temporal_windows) and all(bool(item["baseline_not_worse"]) for item in holdout_metrics.temporal_windows)
    if not validation_ok or not holdout_ok:
        status = RankingPolicyStatus.REJECTED_NO_OUT_OF_SAMPLE_LIFT
        reasons = ("VALIDATION_OR_HOLDOUT_LIFT_NOT_CONFIRMED",)
    elif not temporal_ok:
        status = RankingPolicyStatus.REJECTED_TEMPORAL_INSTABILITY
        reasons = ("HOLDOUT_TEMPORAL_WINDOW_UNSTABLE",)
    else:
        status = RankingPolicyStatus.ACCEPTED
        reasons = ("CHRONOLOGICAL_RANKING_LIFT_ACCEPTED",)
    return ContractRankingPolicy.create(
        status=status, status_reasons=reasons, weights=weights,
        minimum_switch_margin=margin, validation_metrics=validation_metrics,
        holdout_metrics=holdout_metrics, **base,
    )


__all__ = [
    "DOI_RANKING_DOMAIN_VERSION", "DOI_RANKING_POLICY_VERSION",
    "ContractRankingPolicy", "FamilyRankingResult", "RankedContract",
    "RankingCandidateEvidence", "RankingMode", "RankingPolicyMetrics",
    "RankingPolicyStatus", "RankingReplayCase", "RankingReplayPolicy",
    "RankingWeights", "rank_contract_family", "tune_ranking_policy",
]
