"""Immutable advisory context; no filesystem, network, or provider dependency."""
from dataclasses import asdict, dataclass
import math
import re

from .domain import (ContractError, EvidenceBundle, Observation, canonical, digest,
                     instant, nonempty, sha, utc)


@dataclass(frozen=True, slots=True)
class ContextFact:
    name: str
    value: str | int | float | bool | None
    unit: str
    definition_id: str
    reference_period: str
    known_at: str | None = None

    def __post_init__(self):
        for field in ("name", "unit", "definition_id", "reference_period"):
            nonempty(getattr(self, field), field)
        if type(self.value) not in (str, int, float, bool, type(None)):
            raise ContractError("context fact must be a JSON scalar")
        if type(self.value) is float and not math.isfinite(self.value):
            raise ContractError("non-finite context fact")
        if self.known_at is not None:
            object.__setattr__(self, "known_at", utc(self.known_at))


@dataclass(frozen=True, slots=True)
class ContextRecord:
    event_id: str
    kind: str
    source_id: str
    source_reference: str
    source_hash: str
    revision: int
    observed_at: str
    published_at: str
    available_at: str
    event_at: str  # A scheduled future event is allowed; not its future actual.
    scope: str
    tickers: tuple[str, ...]
    facts: tuple[ContextFact, ...]
    commentary: str

    def __post_init__(self):
        for field in ("event_id", "source_id", "source_reference"):
            nonempty(getattr(self, field), field)
        sha(self.source_hash)
        if self.kind not in ("MACRO", "ECONOMIC", "NEWS"):
            raise ContractError("unknown context kind")
        if type(self.revision) is not int or self.revision < 0:
            raise ContractError("revision must be a nonnegative integer")
        if self.scope not in ("GLOBAL", "TICKERS") or type(self.tickers) is not tuple:
            raise ContractError("explicit immutable entity scope required")
        if self.scope == "GLOBAL" and self.tickers:
            raise ContractError("global record cannot contain ticker mapping")
        if self.scope == "TICKERS" and not self.tickers:
            raise ContractError("ticker record needs exact entities")
        if any(type(t) is not str or not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]*", t) for t in self.tickers):
            raise ContractError("noncanonical context ticker")
        if len(set(self.tickers)) != len(self.tickers):
            raise ContractError("duplicate context ticker")
        object.__setattr__(self, "tickers", tuple(sorted(self.tickers)))
        if type(self.facts) is not tuple or any(not isinstance(f, ContextFact) for f in self.facts):
            raise ContractError("immutable context facts required")
        if len({f.name for f in self.facts}) != len(self.facts):
            raise ContractError("duplicate context fact name")
        object.__setattr__(self, "facts", tuple(sorted(self.facts, key=lambda f: f.name)))
        if type(self.commentary) is not str or len(self.commentary) > 50_000:
            raise ContractError("invalid or oversized context commentary")
        for field in ("observed_at", "published_at", "available_at", "event_at"):
            object.__setattr__(self, field, utc(getattr(self, field)))
        if not instant(self.observed_at) <= instant(self.published_at) <= instant(self.available_at):
            raise ContractError("invalid source chronology")
        if any(f.known_at is not None and instant(f.known_at) > instant(self.available_at) for f in self.facts):
            raise ContractError("fact was not known when source became available")
        if self.kind == "ECONOMIC" and instant(self.event_at) > instant(self.observed_at):
            if any(f.name == "actual" and f.value is not None for f in self.facts):
                raise ContractError("scheduled future economic event cannot have an actual")

    @property
    def record_hash(self):
        return digest(asdict(self))


@dataclass(frozen=True, slots=True)
class SelectedContext:
    record: ContextRecord
    age_seconds: float
    freshness: str
    source_disagreement: bool


@dataclass(frozen=True, slots=True)
class ContextSnapshot:
    ticker: str
    cutoff: str
    policy_version: str
    max_age_seconds: int
    selected: tuple[SelectedContext, ...]
    # Audit only: excluded records never go into model inputs or evidence hashes.
    excluded: tuple[tuple[str, str], ...]

    @property
    def snapshot_hash(self):
        return digest(self.to_payload())

    def to_payload(self):
        return {"schema_version": "context_snapshot_v1", "ticker": self.ticker,
                "cutoff": self.cutoff, "policy_version": self.policy_version,
                "max_age_seconds": self.max_age_seconds,
                "authority": "ADVISORY_ONLY",
                "event_count": len({(r.record.kind, r.record.event_id) for r in self.selected}),
                "selected": [asdict(row) for row in self.selected]}


def select_context(records: tuple[ContextRecord, ...], *, ticker: str, cutoff: str,
                   max_age_seconds: int, policy_version: str) -> ContextSnapshot:
    nonempty(policy_version, "freshness policy version")
    if type(ticker) is not str or not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]*", ticker):
        raise ContractError("canonical ticker required")
    if type(max_age_seconds) is not int or max_age_seconds <= 0:
        raise ContractError("explicit positive freshness window required")
    if type(records) is not tuple or any(not isinstance(r, ContextRecord) for r in records):
        raise ContractError("immutable validated context records required")
    cutoff = utc(cutoff)
    groups, excluded, seen = {}, [], set()
    for record in sorted(records, key=lambda r: r.record_hash):
        if instant(record.available_at) > instant(cutoff):
            excluded.append((record.record_hash, "AFTER_CUTOFF"))
            continue
        if record.scope == "TICKERS" and ticker not in record.tickers:
            excluded.append((record.record_hash, "NO_EXACT_ENTITY_MATCH"))
            continue
        if record.record_hash in seen:
            excluded.append((record.record_hash, "DUPLICATE"))
            continue
        seen.add(record.record_hash)
        key = (record.kind, record.event_id, record.source_id)
        groups.setdefault(key, []).append(record)
    retained = []
    for versions in groups.values():
        highest = max(r.revision for r in versions)
        # Same source/event/revision with changed content is an integrity error,
        # not a cross-source opinion conflict to be silently resolved.
        revisions = {}
        for r in versions:
            revisions.setdefault(r.revision, set()).add(r.record_hash)
        if any(len(hashes) > 1 for hashes in revisions.values()):
            raise ContractError("same source revision has conflicting immutable content")
        ordered = sorted(versions, key=lambda r: r.revision)
        if any(instant(a.available_at) > instant(b.available_at) for a, b in zip(ordered, ordered[1:])):
            raise ContractError("revision chronology is reversed")
        for record in versions:
            if record.revision == highest:
                retained.append(record)
            else:
                excluded.append((record.record_hash, "SUPERSEDED_AT_CUTOFF"))
    evidence_by_event = {}
    for record in retained:
        key = (record.kind, record.event_id)
        signature = digest({"facts": [asdict(f) for f in record.facts], "commentary": record.commentary})
        evidence_by_event.setdefault(key, set()).add(signature)
    selected = []
    for record in sorted(retained, key=lambda r: (r.kind, r.event_id, r.source_id, r.record_hash)):
        age = (instant(cutoff) - instant(record.observed_at)).total_seconds()
        selected.append(SelectedContext(record, age, "WITHIN_WINDOW" if age <= max_age_seconds else "STALE",
                                        len(evidence_by_event[(record.kind, record.event_id)]) > 1))
    return ContextSnapshot(ticker, cutoff, policy_version, max_age_seconds, tuple(selected), tuple(sorted(excluded)))


def attach_context(bundle: EvidenceBundle, snapshot: ContextSnapshot) -> EvidenceBundle:
    """Bind whole dated context as one immutable observation; hash changes job identity."""
    if snapshot.ticker != bundle.identity.ticker or snapshot.cutoff != bundle.evidence_cutoff_utc:
        raise ContractError("context belongs to a different ticker/cutoff")
    checked = select_context(tuple(row.record for row in snapshot.selected), ticker=snapshot.ticker,
                             cutoff=snapshot.cutoff, max_age_seconds=snapshot.max_age_seconds,
                             policy_version=snapshot.policy_version)
    if checked.to_payload() != snapshot.to_payload():
        raise ContractError("context selection/freshness was tampered with")
    obs = Observation("context:" + snapshot.snapshot_hash, "advisory_context_snapshot",
                      canonical(snapshot.to_payload()), "structured_json", "context-service",
                      snapshot.snapshot_hash, snapshot.cutoff, snapshot.cutoff,
                      scope="CONTEXT", calculation_version=snapshot.policy_version)
    if any(o.field == obs.field for o in bundle.observations):
        raise ContractError("context already bound; create a new bundle for refresh")
    # This is a derived assembly timestamp, not the freshness of its nested sources.
    return EvidenceBundle(bundle.identity, bundle.evidence_cutoff_utc, bundle.observations + (obs,))


@dataclass(frozen=True, slots=True)
class EconomicSurprise:
    value: float | None
    unit: str | None
    status: str
    source_record_hash: str
    calculation_version: str = "actual_minus_consensus_v1"


def economic_surprise(record: ContextRecord) -> EconomicSurprise:
    if record.kind != "ECONOMIC":
        raise ContractError("economic event required")
    facts = {f.name: f for f in record.facts}
    actual, consensus = facts.get("actual"), facts.get("consensus")
    if any(f is None or f.value is None for f in (actual, consensus)):
        return EconomicSurprise(None, None, "MISSING_INPUT", record.record_hash)
    if type(actual.value) not in (int, float) or type(consensus.value) not in (int, float):
        return EconomicSurprise(None, None, "NON_NUMERIC", record.record_hash)
    if actual.known_at is None or consensus.known_at is None:
        return EconomicSurprise(None, None, "TIMING_UNVERIFIED", record.record_hash)
    if instant(consensus.known_at) > instant(record.event_at) or instant(actual.known_at) < instant(record.event_at):
        return EconomicSurprise(None, None, "INCOMPARABLE_VINTAGE", record.record_hash)
    if (actual.unit, actual.definition_id, actual.reference_period) != (
            consensus.unit, consensus.definition_id, consensus.reference_period):
        return EconomicSurprise(None, None, "INCOMPARABLE", record.record_hash)
    result = actual.value - consensus.value
    try:
        finite = math.isfinite(result)
    except OverflowError:
        finite = False
    if not finite:
        return EconomicSurprise(None, None, "NON_FINITE_RESULT", record.record_hash)
    return EconomicSurprise(float(result), actual.unit, "COMPUTED", record.record_hash)
