"""Read-only adapters for explicitly normalized, frozen artifacts, not live CSVs.

The caller supplies a trusted expected byte hash. A matching hash proves byte
integrity, not source truth, provenance authentication or trading suitability.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path

from ..application import _constant, _pairs
from ..context import ContextFact, ContextRecord
from ..domain import (ContractError, Direction, EvidenceBundle, Identity,
                      Observation, canonical, digest, nonempty, sha)


def exact(value, keys, name):
    if type(value) is not dict or set(value) != set(keys):
        raise ContractError(f"{name}: unexpected or missing fields")


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    relative_path: str
    expected_sha256: str
    source_id: str

    def __post_init__(self):
        nonempty(self.relative_path, "artifact path")
        nonempty(self.source_id, "artifact source")
        sha(self.expected_sha256)
        path = Path(self.relative_path)
        if path.is_absolute() or path.drive or ".." in path.parts or ":" in self.relative_path:
            raise ContractError("artifact path must be relative and confined")


@dataclass(frozen=True, slots=True)
class VerifiedArtifact:
    reference: ArtifactRef
    byte_count: int
    payload_json: str

    def payload(self):
        return json.loads(self.payload_json)


def read_verified_bytes(root, reference: ArtifactRef, *, max_bytes=8_000_000):
    """Bounded binary read; reject links, changed files, invalid JSON and bad hashes.

    Root must be a caller-approved frozen folder. This is not an OS security
    boundary against an adversary concurrently replacing directory components.
    """
    if not isinstance(reference, ArtifactRef) or type(max_bytes) is not int or max_bytes <= 0:
        raise ContractError("explicit artifact reference and positive byte limit required")
    try:
        root = Path(root).resolve(strict=True)
        candidate = root / reference.relative_path
        for component in (candidate, *candidate.parents):
            if component == root:
                break
            if component.is_symlink() or component.is_junction():
                raise ContractError("linked artifacts are not accepted")
        path = candidate.resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise ContractError("artifact is outside root or not a regular file")
        path_before = path.stat()
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if before.st_size > max_bytes:
                raise ContractError("artifact exceeds byte limit")
            data = handle.read(max_bytes + 1)
            after = os.fstat(handle.fileno())
        now = path.stat()
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        # Windows stat/fstat can expose different ctime semantics. Compare ctime
        # only within the same API, while identity/size/mtime bridge both APIs.
        if (signature(path_before) != signature(before) or signature(before) != signature(after)
                or signature(after) != signature(now) or before.st_ctime_ns != after.st_ctime_ns
                or path_before.st_ctime_ns != now.st_ctime_ns):
            raise ContractError("artifact changed during read")
        if len(data) > max_bytes or len(data) != before.st_size:
            raise ContractError("artifact read length is invalid")
        if hashlib.sha256(data).hexdigest() != reference.expected_sha256:
            raise ContractError("artifact byte hash mismatch")
        return data
    except OSError as exc:
        raise ContractError(f"artifact could not be verified: {type(exc).__name__}") from exc


def read_artifact(root, reference: ArtifactRef, *, max_bytes=8_000_000):
    data = read_verified_bytes(root, reference, max_bytes=max_bytes)
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_constant)
        payload_json = canonical(value)  # Also rejects numeric overflow to infinity.
        if type(value) is not dict:
            raise ContractError("artifact must contain a JSON object")
        return VerifiedArtifact(reference, len(data), payload_json)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        if isinstance(exc, ContractError):
            raise
        raise ContractError(f"artifact could not be verified: {type(exc).__name__}") from exc


@dataclass(frozen=True, slots=True)
class FieldMapping:
    source_field: str
    evidence_id: str
    field: str
    unit: str
    scope: str

    def __post_init__(self):
        for name in ("source_field", "evidence_id", "field", "unit"):
            nonempty(getattr(self, name), name)
        if self.scope not in ("TICKER", "CONTRACT"):
            raise ContractError("pipeline mapping requires ticker or contract scope")


def load_pipeline_bundle(root, reference, *, identity: Identity, cutoff: str,
                         mapping: tuple[FieldMapping, ...], mapping_version: str,
                         max_bytes=8_000_000):
    """No implicit aliases, coercion, unit conversion, derived stops or defaults."""
    nonempty(mapping_version, "mapping version")
    if not isinstance(identity, Identity):
        raise ContractError("validated requested identity required")
    if type(mapping) is not tuple or not mapping or any(not isinstance(m, FieldMapping) for m in mapping):
        raise ContractError("nonempty immutable mapping required")
    for key in (lambda m: m.source_field, lambda m: m.evidence_id, lambda m: (m.scope, m.field)):
        if len({key(m) for m in mapping}) != len(mapping):
            raise ContractError("ambiguous field mapping")
    artifact = read_artifact(root, reference, max_bytes=max_bytes)
    document = artifact.payload()
    exact(document, ("schema_version", "run_id", "invocation_id", "rows"), "pipeline artifact")
    if document["schema_version"] != "worker3_frozen_pipeline_v1":
        raise ContractError("unsupported pipeline artifact schema")
    if document["run_id"] != identity.run_id or document["invocation_id"] != identity.invocation_id:
        raise ContractError("pipeline run/invocation mismatch")
    if type(document["rows"]) is not list:
        raise ContractError("pipeline rows must be a list")
    matches = []
    identity_keys = asdict(identity).keys()
    for row in document["rows"]:
        exact(row, ("identity", "values"), "pipeline row")
        exact(row["identity"], identity_keys, "row identity")
        try:
            row_identity = Identity(**{**row["identity"], "direction": Direction(row["identity"]["direction"])})
        except (ValueError, TypeError) as exc:
            raise ContractError("invalid source identity") from exc
        if row_identity.run_id != identity.run_id or row_identity.invocation_id != identity.invocation_id:
            raise ContractError("mixed run identities in artifact")
        if type(row["values"]) is not dict:
            raise ContractError("row values must be an object")
        if row_identity.ticker == identity.ticker:
            matches.append((row_identity, row["values"]))
    if len(matches) != 1:
        raise ContractError("expected exactly one row for requested ticker")
    found_identity, values = matches[0]
    if found_identity != identity:
        raise ContractError("thesis/session/direction/hold/contract identity mismatch")
    mapping_hash = digest({"version": mapping_version,
                           "fields": sorted((asdict(m) for m in mapping), key=lambda x: x["evidence_id"])})
    observations = []
    for m in mapping:
        if m.source_field not in values:
            raise ContractError(f"mapped field absent: {m.source_field}; explicit unavailable cell required")
        cell = values[m.source_field]
        exact(cell, ("value", "unit", "status", "observed_at", "available_at", "calculation_version"), "evidence cell")
        if cell["unit"] != m.unit:
            raise ContractError("source unit differs from mapping; conversion is not implicit")
        observations.append(Observation(
            evidence_id=m.evidence_id, field=m.field, value=cell["value"], unit=m.unit,
            source_id=reference.source_id + ":mapping:" + mapping_hash,
            source_hash=reference.expected_sha256, observed_at=cell["observed_at"],
            available_at=cell["available_at"], status=cell["status"], scope=m.scope,
            ticker=identity.ticker, contract_id=identity.contract_id if m.scope == "CONTRACT" else None,
            calculation_version=cell["calculation_version"]))
    return EvidenceBundle(identity, cutoff, tuple(observations))


def load_context_records(root, reference, *, max_bytes=8_000_000):
    """Read normalized macro/economic/news records with actual file-byte lineage.

    This schema is an explicit staging interface, NOT a claimed mapping of the
    existing dropbox/macro files. Native schemas require separate approved maps.
    """
    artifact = read_artifact(root, reference, max_bytes=max_bytes)
    document = artifact.payload()
    exact(document, ("schema_version", "records"), "context artifact")
    if document["schema_version"] != "worker3_frozen_context_v1" or type(document["records"]) is not list:
        raise ContractError("unsupported context artifact schema")
    records = []
    record_keys = {"event_id", "kind", "source_reference", "revision", "observed_at",
                   "published_at", "available_at", "event_at", "scope", "tickers", "facts", "commentary"}
    for row in document["records"]:
        exact(row, record_keys, "context record")
        if type(row["tickers"]) is not list or type(row["facts"]) is not list:
            raise ContractError("context tickers/facts must be arrays")
        facts = []
        for fact in row["facts"]:
            exact(fact, ("name", "value", "unit", "definition_id", "reference_period", "known_at"), "context fact")
            facts.append(ContextFact(**fact))
        records.append(ContextRecord(**{**row, "source_id": reference.source_id,
                                       "source_hash": reference.expected_sha256,
                                       "tickers": tuple(row["tickers"]), "facts": tuple(facts)}))
    return tuple(records)
