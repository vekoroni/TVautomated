"""Acceptance and controlled-promotion contract for dynamic orchestration.

The release guard is deliberately independent from signal calculation.  It
turns the acceptance gates in AVS-SD-002 Rev 1.1 into machine-checkable
evidence and refuses to produce production feature settings until every gate
is supported by an existing, hash-bound artefact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping

from contracts.dynamic_session_contract import FEATURE_FLAG_ENV_VARS


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"


class ReleaseStatus(str, Enum):
    NOT_READY = "NOT_READY"
    READY_FOR_LIVE_CYCLE = "READY_FOR_LIVE_CYCLE"
    READY_FOR_CONTROLLED_PROMOTION = "READY_FOR_CONTROLLED_PROMOTION"


class PromotionStage(str, Enum):
    PLAN_ONLY = "PLAN_ONLY"
    EXPLICIT_COMMANDS = "EXPLICIT_COMMANDS"
    DYNAMIC_VIEWS = "DYNAMIC_VIEWS"
    AUTO = "AUTO"


# Gates 01-17, 19 and 20 correspond one-for-one with section 19 of the
# design. Gate 18 is split into four separately observable live transitions.
REQUIRED_GATE_IDS = (
    "G01_P0_BLOCKERS_CLOSED",
    "G02_SINGLE_SESSION_CLOCK",
    "G03_SEPARATE_EVIDENCE_IDENTITIES",
    "G04_DETERMINISTIC_AUTO_PLAN",
    "G05_CURRENT_THESIS_REUSE",
    "G06_NO_PREMARKET_PROFILE_FABRICATION",
    "G07_RTH_MISSING_INTERVALS_ONLY",
    "G08_PROVIDER_CONFIRMED_FINALISATION",
    "G09_RESTART_AND_SCOPE_IDENTITY",
    "G10_MACRO_ADVISORY_AND_REFRESHABLE",
    "G11_FROZEN_DIRECTION_HORIZON_GEOMETRY",
    "G12_CURRENT_PRICE_TRANSITION_ONLY",
    "G13_QUOTE_REQUIRED_ONLY_FOR_EXECUTION",
    "G14_LAB_INTERPRETER_EVENT_PARITY",
    "G15_POPULATION_AND_REQUEST_RECONCILIATION",
    "G16_REPLAY_NO_FUTURE_DATA",
    "G17_NO_UNEXPLAINED_P0_P1_REGRESSIONS",
    "G18A_LIVE_COMPLETED_THESIS",
    "G18B_LIVE_PREMARKET_VALIDATION",
    "G18C_LIVE_RTH_VALIDATION",
    "G18D_LIVE_AFTER_HOURS_FINALISATION",
    "G19_RUNTIME_API_DISK_BUDGET",
    "G20_BACKUP_RESTORE_VERIFIED",
)

LIVE_GATE_IDS = frozenset(
    {
        "G18A_LIVE_COMPLETED_THESIS",
        "G18B_LIVE_PREMARKET_VALIDATION",
        "G18C_LIVE_RTH_VALIDATION",
        "G18D_LIVE_AFTER_HOURS_FINALISATION",
        "G19_RUNTIME_API_DISK_BUDGET",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class EvidenceArtifact:
    path: str
    sha256: str

    @classmethod
    def from_path(cls, path: Path, *, repo_root: Path) -> "EvidenceArtifact":
        resolved = path.resolve()
        root = repo_root.resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError("release evidence must remain inside the repository")
        if not resolved.is_file() or resolved.stat().st_size == 0:
            raise ValueError(f"release evidence is missing or empty: {resolved}")
        return cls(resolved.relative_to(root).as_posix(), _sha256(resolved))


@dataclass(frozen=True, slots=True)
class GateEvidence:
    gate_id: str
    status: str
    artifacts: tuple[EvidenceArtifact, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        if self.gate_id not in REQUIRED_GATE_IDS:
            raise ValueError(f"unknown dynamic release gate: {self.gate_id}")
        GateStatus(self.status)


@dataclass(frozen=True, slots=True)
class ReleaseAssessment:
    release_id: str
    assessed_at_utc: str
    status: str
    gate_results: tuple[GateEvidence, ...]
    missing_gates: tuple[str, ...]
    failed_gates: tuple[str, ...]
    invalid_artifacts: tuple[str, ...]
    live_cycle_complete: bool

    @property
    def promotable(self) -> bool:
        return self.status == ReleaseStatus.READY_FOR_CONTROLLED_PROMOTION.value

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_evidence(path: Path | str) -> tuple[GateEvidence, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    rows = payload.get("gates") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("release evidence must contain a gates list")
    results: list[GateEvidence] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("each gate evidence entry must be an object")
        artifacts = tuple(
            EvidenceArtifact(str(item["path"]), str(item["sha256"]).lower())
            for item in row.get("artifacts", ())
        )
        results.append(
            GateEvidence(
                gate_id=str(row.get("gate_id") or ""),
                status=str(row.get("status") or "NOT_RUN").upper(),
                artifacts=artifacts,
                detail=str(row.get("detail") or ""),
            )
        )
    return tuple(results)


def assess_release(
    evidence: Iterable[GateEvidence],
    *,
    repo_root: Path | str,
    release_id: str = "AVS-SD-002-REV1.1",
) -> ReleaseAssessment:
    root = Path(repo_root).resolve()
    indexed: dict[str, GateEvidence] = {}
    invalid: list[str] = []
    for gate in evidence:
        if gate.gate_id in indexed:
            raise ValueError(f"duplicate release gate evidence: {gate.gate_id}")
        indexed[gate.gate_id] = gate
        if GateStatus(gate.status) is GateStatus.PASS and not gate.artifacts:
            invalid.append(f"{gate.gate_id}:PASS_WITHOUT_ARTIFACT")
        for artifact in gate.artifacts:
            candidate = (root / artifact.path).resolve()
            if candidate != root and root not in candidate.parents:
                invalid.append(f"{gate.gate_id}:{artifact.path}:OUTSIDE_REPOSITORY")
            elif not candidate.is_file():
                invalid.append(f"{gate.gate_id}:{artifact.path}:MISSING")
            elif _sha256(candidate) != artifact.sha256.lower():
                invalid.append(f"{gate.gate_id}:{artifact.path}:HASH_MISMATCH")

    missing = tuple(gate for gate in REQUIRED_GATE_IDS if gate not in indexed)
    failed = tuple(
        gate
        for gate in REQUIRED_GATE_IDS
        if gate in indexed and GateStatus(indexed[gate].status) is not GateStatus.PASS
    )
    offline_gate_ids = tuple(gate for gate in REQUIRED_GATE_IDS if gate not in LIVE_GATE_IDS)
    offline_complete = all(
        gate in indexed and GateStatus(indexed[gate].status) is GateStatus.PASS
        for gate in offline_gate_ids
    ) and not any(item.split(":", 1)[0] in offline_gate_ids for item in invalid)
    live_complete = all(
        gate in indexed and GateStatus(indexed[gate].status) is GateStatus.PASS
        for gate in LIVE_GATE_IDS
    ) and not any(item.split(":", 1)[0] in LIVE_GATE_IDS for item in invalid)
    if offline_complete and live_complete and not missing and not failed and not invalid:
        status = ReleaseStatus.READY_FOR_CONTROLLED_PROMOTION
    elif offline_complete:
        status = ReleaseStatus.READY_FOR_LIVE_CYCLE
    else:
        status = ReleaseStatus.NOT_READY
    ordered_results = tuple(indexed[gate] for gate in REQUIRED_GATE_IDS if gate in indexed)
    return ReleaseAssessment(
        release_id=release_id,
        assessed_at_utc=datetime.now(timezone.utc).isoformat(),
        status=status.value,
        gate_results=ordered_results,
        missing_gates=missing,
        failed_gates=failed,
        invalid_artifacts=tuple(invalid),
        live_cycle_complete=live_complete,
    )


_PROMOTION_FLAGS = {
    PromotionStage.PLAN_ONLY: ("AVSHUNTER_DYNAMIC_PLAN_ENABLED",),
    PromotionStage.EXPLICIT_COMMANDS: (
        "AVSHUNTER_DYNAMIC_PLAN_ENABLED",
        "AVSHUNTER_DYNAMIC_THESIS_ENABLED",
        "AVSHUNTER_DYNAMIC_VALIDATION_ENABLED",
        "AVSHUNTER_PROFILE_LIFECYCLE_ENABLED",
        "AVSHUNTER_DECISION_LEDGER_ENABLED",
    ),
    PromotionStage.DYNAMIC_VIEWS: (
        "AVSHUNTER_DYNAMIC_PLAN_ENABLED",
        "AVSHUNTER_DYNAMIC_THESIS_ENABLED",
        "AVSHUNTER_DYNAMIC_VALIDATION_ENABLED",
        "AVSHUNTER_PROFILE_LIFECYCLE_ENABLED",
        "AVSHUNTER_LAB_DYNAMIC_VIEW_ENABLED",
        "AVSHUNTER_INTERPRETER_DYNAMIC_RESOLVER_ENABLED",
        "AVSHUNTER_DECISION_LEDGER_ENABLED",
    ),
    PromotionStage.AUTO: FEATURE_FLAG_ENV_VARS,
}

# The acceptance cycle must exercise every explicit-command service that will
# participate in the Evening -> Morning handoff. Autonomous resolution remains
# withheld until the live gates have passed.
CONTROLLED_LIVE_CYCLE_FLAGS = frozenset(FEATURE_FLAG_ENV_VARS) - {
    "AVSHUNTER_DYNAMIC_AUTO_ENABLED"
}


def controlled_live_cycle_environment(
    assessment: ReleaseAssessment,
) -> dict[str, str]:
    """Return the governed settings for a supervised live acceptance cycle.

    This is intentionally distinct from promotion. It is available only after
    all offline gates are clean, enables explicit Evening/Morning commands and
    refuses autonomous dispatch.
    """

    if assessment.status not in {
        ReleaseStatus.READY_FOR_LIVE_CYCLE.value,
        ReleaseStatus.READY_FOR_CONTROLLED_PROMOTION.value,
    }:
        raise RuntimeError(
            f"dynamic session release is {assessment.status}; live cycle refused"
        )
    return {
        name: "1" if name in CONTROLLED_LIVE_CYCLE_FLAGS else "0"
        for name in FEATURE_FLAG_ENV_VARS
    }


def promotion_environment(
    assessment: ReleaseAssessment, stage: PromotionStage | str
) -> dict[str, str]:
    """Return complete feature settings, refusing premature promotion."""

    if not assessment.promotable:
        raise RuntimeError(
            f"dynamic session release is {assessment.status}; controlled promotion refused"
        )
    selected = PromotionStage(str(getattr(stage, "value", stage)).upper())
    enabled = set(_PROMOTION_FLAGS[selected])
    return {name: "1" if name in enabled else "0" for name in FEATURE_FLAG_ENV_VARS}


def write_assessment_atomic(assessment: ReleaseAssessment, path: Path | str) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(assessment.to_dict(), indent=2), encoding="utf-8"
    )
    temporary.replace(destination)
    return destination

