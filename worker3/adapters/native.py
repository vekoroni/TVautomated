"""Native, source-preserving document evidence. Never execution authority.

Mappings verified against lab_control.py, build_macro_json.py and
bond_macro_intelligence.py on 2026-09-05. No producer modules are imported.
"""
from dataclasses import dataclass, replace
from datetime import datetime
import json
import math

from .artifacts import read_artifact, read_verified_bytes
from ..application import _pairs
from ..domain import ContractError, Observation, canonical, digest, instant, nonempty, utc


def timing_findings(value, path=""):
    """Preserve source timing uncertainty instead of assigning the machine zone."""
    result = []
    if isinstance(value, dict):
        for key, child in value.items():
            location = path + "/" + key
            if key in {"as_of_utc", "generated_at", "created_at_utc", "normalised_at_utc", "built_at"}:
                try:
                    parsed = datetime.fromisoformat(str(child).replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        result.append("TIMEZONE_UNSPECIFIED:" + location)
                except ValueError:
                    result.append("INVALID_SOURCE_TIMESTAMP:" + location)
            if key == "stale_flag" and child is True:
                result.append("SOURCE_MARKED_STALE:" + path)
            if key in {"as_of_date", "report_date"}:
                result.append("DATE_ONLY_NOT_INTRADAY_TIME:" + location)
            result.extend(timing_findings(child, location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(timing_findings(child, path + "/" + str(index)))
    return result


@dataclass(frozen=True, slots=True)
class NativeSnapshot:
    kind: str
    source_id: str
    source_hash: str
    captured_at: str
    document_json: str
    findings: tuple[str, ...]
    run_id: str | None = None
    ticker: str | None = None

    @property
    def snapshot_hash(self):
        return digest(self.payload())

    def payload(self):
        import json
        return {"schema_version": "worker3_native_document_v1", "kind": self.kind,
                "source_id": self.source_id, "source_hash": self.source_hash,
                "captured_at": self.captured_at, "run_id": self.run_id, "ticker": self.ticker,
                "authority": "ADVISORY_ONLY", "execution_permission": False,
                "timing_basis": "DOCUMENT_CAPTURE_NOT_MARKET_OBSERVATION",
                "source_freshness": "NOT_INFERRED_FROM_CAPTURE",
                "findings": list(self.findings), "source_document": json.loads(self.document_json)}


def load_native_macro(root, reference, *, kind, captured_at):
    captured_at = utc(captured_at)  # Caller attests frozen-file capture, not publication.
    document = read_artifact(root, reference).payload()
    if kind == "MACRO_INTELLIGENCE":
        if document.get("contract_version") != "macro_contract_v1_0":
            raise ContractError("unsupported native macro contract")
        required = {"regime_state", "as_of_utc", "sector_lead", "sector_avoid", "horizon_routing"}
    elif kind == "BOND_MACRO":
        if document.get("schema_version") != "2.1.0":
            raise ContractError("unsupported native bond contract")
        required = {"generated_at", "yield_curve", "auction", "zn_futures", "credit_stress", "composite"}
    else:
        raise ContractError("native macro kind requires an approved mapping")
    if not required <= document.keys():
        raise ContractError("native macro missing required structure")
    if kind == "MACRO_INTELLIGENCE":
        if (type(document["sector_lead"]) is not list or type(document["sector_avoid"]) is not list
                or type(document["horizon_routing"]) is not dict):
            raise ContractError("invalid native macro section types")
    elif any(type(document[key]) is not dict for key in required - {"generated_at"}):
        raise ContractError("invalid native bond section types")
    findings = timing_findings(document)
    findings.append("SOURCE_RECOMMENDATIONS_ARE_QUOTED_NOT_WORKER_AUTHORITY")
    return NativeSnapshot(kind, reference.source_id, reference.expected_sha256, captured_at,
                          canonical(document), tuple(sorted(set(findings))))


class _NonFinite:
    def __init__(self, marker):
        self.marker = marker


def read_lab_document(root, reference, *, max_bytes=32_000_000):
    """Explicit native-only NaN normalization with JSON-pointer disclosures.

    Legacy producer writes nonstandard numeric constants. Never weaken the
    general reader, lose the original byte hash, or silently turn these into zero.
    """
    data = read_verified_bytes(root, reference, max_bytes=max_bytes)
    try:
        document = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_NonFinite)
    except (ValueError, UnicodeError) as exc:
        raise ContractError("invalid native Lab JSON") from exc
    repairs = []
    def normalize(value, path):
        if isinstance(value, _NonFinite) or (type(value) is float and not math.isfinite(value)):
            repairs.append({"path": path, "source_marker": value.marker if isinstance(value, _NonFinite) else "NUMERIC_OVERFLOW",
                            "normalized_status": "UNAVAILABLE", "reason": "SOURCE_NONFINITE"})
            return None
        if type(value) is dict:
            return {k: normalize(v, path + "/" + k.replace("~", "~0").replace("/", "~1")) for k, v in value.items()}
        if type(value) is list:
            return [normalize(v, path + "/" + str(i)) for i, v in enumerate(value)]
        return value
    document = normalize(document, "")
    if type(document) is not dict:
        raise ContractError("native Lab root must be an object")
    return document, repairs


def load_native_lab(root, reference, *, run_id, ticker, captured_at, max_bytes=32_000_000):
    nonempty(run_id, "run id")
    nonempty(ticker, "ticker")
    captured_at = utc(captured_at)
    document, repairs = read_lab_document(root, reference, max_bytes=max_bytes)
    return lab_snapshot_from_document(document, repairs, reference, run_id=run_id,
                                      ticker=ticker, captured_at=captured_at)


def lab_snapshot_from_document(document, repairs, reference, *, run_id, ticker, captured_at):
    """Internal mapping seam for a verified, single-read batch. No file IO."""
    nonempty(run_id, "run id")
    nonempty(ticker, "ticker")
    captured_at = utc(captured_at)
    if document.get("lab_schema_version") != "lab_signal_book_v2" or document.get("run_id") != run_id:
        raise ContractError("native Lab schema/run mismatch")
    created = utc(document.get("created_at_utc"))
    if instant(created) > instant(captured_at):
        raise ContractError("Lab creation follows attested capture")
    rows = document.get("rows")
    if type(rows) is not list or type(document.get("candidate_count")) is not int or len(rows) != document["candidate_count"]:
        raise ContractError("Lab candidate reconciliation failed")
    selected = []
    selected_index = None
    for index, row in enumerate(rows):
        if type(row) is not dict or row.get("run_id") != run_id or row.get("lab_schema_version") != "lab_signal_book_v2":
            raise ContractError("mixed or invalid Lab row identity")
        if row.get("ticker") == ticker:
            selected.append(row)
            selected_index = index
    if len(selected) != 1:
        raise ContractError("native Lab requires one exact ticker row")
    row = selected[0]
    # Carry provenance and source errors, not other tickers' data or aggregate permission.
    source = {k: document[k] for k in ("lab_schema_version", "run_id", "created_at_utc", "source_manifest", "source_errors", "reconciliation") if k in document}
    source["row"] = row
    selected_repairs = [r for r in repairs if r["path"].startswith(f"/rows/{selected_index}/") or not r["path"].startswith("/rows/")]
    source["normalization"] = {"version": "lab_nonfinite_to_unavailable_v1", "selected_source_repairs": selected_repairs,
                               "artifact_nonfinite_count": len(repairs)}
    findings = timing_findings(source)
    if selected_repairs:
        findings.append("SOURCE_NONFINITE_VALUES_EXPLICITLY_UNAVAILABLE")
    if document.get("source_errors"):
        findings.append("LAB_SOURCE_ERRORS_PRESENT")
    for field in ("thesis_id", "contract_symbol", "hold_window", "governed_direction"):
        if row.get(field) in (None, ""):
            findings.append("MISSING_IDENTITY_FIELD:" + field)
    findings += ["FILE_CREATION_IS_NOT_QUOTE_TIME", "RUN_COMPLETION_NOT_PROVEN_BY_BOOK_EXISTENCE"]
    return NativeSnapshot("LAB_SIGNAL_BOOK", reference.source_id, reference.expected_sha256,
                          captured_at, canonical(source), tuple(sorted(set(findings))), run_id, ticker)


def attach_native_document(bundle, snapshot):
    """Attach source-document evidence, not typed live quotes or execution approval.

    The caller must already hold a governed identity and evidence bundle. This
    adapter never creates an invocation/session/contract ID from file timestamps.
    """
    if not isinstance(snapshot, NativeSnapshot):
        raise ContractError("native snapshot required")
    if instant(snapshot.captured_at) > instant(bundle.evidence_cutoff_utc):
        raise ContractError("native document captured after evidence cutoff")
    if snapshot.kind == "LAB_SIGNAL_BOOK":
        identity = bundle.identity
        if snapshot.run_id != identity.run_id or snapshot.ticker != identity.ticker:
            raise ContractError("Lab/bundle run or ticker mismatch")
        row = snapshot.payload()["source_document"]["row"]
        source_direction = row.get("governed_direction")
        if source_direction in {"STRANGLE", "UNRESOLVED"}:
            source_direction = "NON_DIRECTIONAL"
        if row.get("thesis_id") != identity.thesis_id or source_direction != identity.direction.value:
            raise ContractError("Lab/bundle thesis or direction mismatch")
        for field in ("canonical_direction", "final_direction", "direction"):
            if row.get(field) not in (None, "", identity.direction.value):
                raise ContractError("conflicting Lab direction")
        if (row.get("contract_symbol") or None) != identity.contract_symbol:
            raise ContractError("Lab/bundle selected symbol mismatch")
        endpoints = {"1_5d": 5, "6_10d": 10, "11_20d": 20}
        if endpoints.get(row.get("hold_window")) != identity.planned_hold_sessions:
            raise ContractError("Lab hold bucket endpoint does not match governed planned hold")
        scope = "TICKER"
    elif snapshot.kind in {"MACRO_INTELLIGENCE", "BOND_MACRO"}:
        scope = "CONTEXT"
    else:
        raise ContractError("unapproved native document kind")
    field = "native_document_" + snapshot.kind.lower()
    if any(o.field == field for o in bundle.observations):
        raise ContractError("native document already attached; refresh must replace the bundle")
    observation = Observation(
        "native:" + snapshot.snapshot_hash, field, canonical(snapshot.payload()), "structured_json",
        snapshot.source_id + ":native-map-v1", snapshot.source_hash,
        snapshot.captured_at, snapshot.captured_at, scope=scope,
        ticker=bundle.identity.ticker if scope == "TICKER" else None,
        calculation_version="native_document_capture_v1")
    return replace(bundle, observations=bundle.observations + (observation,))
