"""Evidence comparisons and prior draft provenance; no production persistence."""
from dataclasses import asdict, dataclass
import json
import math

from .application import ProviderResponse, validate_response
from .domain import ContractError, EvidenceBundle, WorkerJob, canonical, digest, instant, utc


@dataclass(frozen=True, slots=True)
class PriorAssessment:
    job: WorkerJob
    response: ProviderResponse
    generated_at: str

    def __post_init__(self):
        validate_response(self.job, self.response)
        object.__setattr__(self, "generated_at", utc(self.generated_at))
        if instant(self.generated_at) < instant(self.job.bundle.evidence_cutoff_utc):
            raise ContractError("assessment cannot precede its evidence cutoff")

    @property
    def payload(self):
        return json.loads(validate_response(self.job, self.response).payload_json)

    @property
    def assessment_id(self):
        return digest({"payload": self.payload, "generated_at": self.generated_at,
                       "provider_request_id": self.response.request_id})

    def to_payload(self):
        return {"assessment_id": self.assessment_id, "generated_at": self.generated_at,
                "validation_status": "STRUCTURAL_ONLY", "assessment": self.payload,
                "evidence_bundle": asdict(self.job.bundle)}


@dataclass(frozen=True, slots=True)
class EvidenceChange:
    scope: str
    field: str
    reason: str
    before_id: str | None
    after_id: str | None
    before_value: str | int | float | bool | None
    after_value: str | int | float | bool | None
    numeric_delta: float | None


@dataclass(frozen=True, slots=True)
class EvidenceComparison:
    before_hash: str
    after_hash: str
    contract_changed: bool
    holding_period_changed: bool
    changes: tuple[EvidenceChange, ...]
    calculation_version: str = "evidence_comparison_v1"
    authority: str = "ADVISORY_ONLY"


def _index(bundle):
    result = {}
    for obs in bundle.observations:
        key = (obs.scope, obs.field)
        if key in result:
            raise ContractError("ambiguous comparison field; resolve source ownership first")
        result[key] = obs
    return result


def compare_evidence(before: EvidenceBundle, after: EvidenceBundle) -> EvidenceComparison:
    left, right = before.identity, after.identity
    if (left.ticker, left.thesis_id, left.direction) != (right.ticker, right.thesis_id, right.direction):
        raise ContractError("comparison requires the same ticker, thesis and governed direction")
    if instant(after.evidence_cutoff_utc) < instant(before.evidence_cutoff_utc):
        raise ContractError("comparison cannot travel backwards in time")
    if right.trading_session < left.trading_session:
        raise ContractError("comparison cannot travel backwards in trading session")
    contract_changed = (left.contract_id, left.contract_symbol, left.selection_version) != (
        right.contract_id, right.contract_symbol, right.selection_version)
    old, new = _index(before), _index(after)
    changes = []
    for key in sorted(old.keys() | new.keys()):
        a, b = old.get(key), new.get(key)
        delta = None
        if key[0] == "CONTRACT" and contract_changed:
            reason = "CONTRACT_CHANGED_NOT_COMPARABLE"
        elif a is None:
            reason = "ADDED"
        elif b is None:
            reason = "REMOVED"
        elif a.status != "AVAILABLE" or b.status != "AVAILABLE":
            reason = "UNAVAILABLE_OR_NOT_APPLICABLE"
        elif a.unit != b.unit:
            reason = "UNIT_CHANGED_NOT_COMPARABLE"
        elif a.source_id != b.source_id:
            reason = "SOURCE_CHANGED_NOT_COMPARABLE"
        elif a.calculation_version != b.calculation_version:
            reason = "RECALCULATED_NOT_COMPARABLE"
        elif canonical(a.value) == canonical(b.value):
            reason = "UNCHANGED" if asdict(a) == asdict(b) else "PROVENANCE_OR_TIME_REFRESHED"
        elif key[0] == "CONTEXT":
            reason = "CONTEXT_UPDATED"
        elif instant(b.observed_at) <= instant(a.observed_at):
            reason = "SAME_OR_EARLIER_OBSERVATION_REVISED"
        else:
            reason = "OBSERVED_VALUE_CHANGED"
            if type(a.value) in (int, float) and type(b.value) in (int, float):
                try:
                    raw_delta = b.value - a.value
                    if math.isfinite(raw_delta):
                        delta = float(raw_delta)
                except OverflowError:
                    pass
        changes.append(EvidenceChange(key[0], key[1], reason, a.evidence_id if a else None,
                                      b.evidence_id if b else None, a.value if a else None,
                                      b.value if b else None, delta))
    return EvidenceComparison(before.evidence_hash, after.evidence_hash, contract_changed,
                              left.planned_hold_sessions != right.planned_hold_sessions, tuple(changes))


def prepare_refresh(job: WorkerJob, prior: PriorAssessment) -> dict:
    if job.task_type not in ("REFRESH_ASSESSMENT", "CONTEXT_UPDATE"):
        raise ContractError("refresh task required")
    if job.previous_assessment_id != prior.assessment_id:
        raise ContractError("wrong previous assessment content identity")
    if instant(prior.generated_at) > instant(job.bundle.evidence_cutoff_utc):
        raise ContractError("previous assessment was not available at the new cutoff")
    comparison = compare_evidence(prior.job.bundle, job.bundle)
    return {"schema_version": "assessment_refresh_v1", "prior": prior.to_payload(),
            "comparison": asdict(comparison), "current_evidence_hash": job.bundle.evidence_hash}
