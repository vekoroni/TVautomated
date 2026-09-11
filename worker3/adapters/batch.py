"""Single-read, immutable native evidence batch. No model or production writer."""
from dataclasses import dataclass
import re

from .native import (NativeSnapshot, read_lab_document, lab_snapshot_from_document,
                     attach_native_document)
from ..domain import ContractError, EvidenceBundle, digest, nonempty, utc


@dataclass(frozen=True, slots=True)
class TickerDocument:
    ticker: str
    status: str
    snapshot: NativeSnapshot | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class NativeBatch:
    run_id: str
    source_hash: str
    captured_at: str
    entries: tuple[TickerDocument, ...]
    source_row_count: int
    source_nonfinite_count: int

    @property
    def batch_id(self):
        return digest({"schema": "native_batch_v1", "run_id": self.run_id,
                       "source_hash": self.source_hash, "captured_at": self.captured_at,
                       "entries": [(e.ticker, e.status, e.snapshot.snapshot_hash if e.snapshot else None, e.reason)
                                   for e in self.entries]})

    def summary(self):
        ready = sum(e.status == "DOCUMENT_READY" for e in self.entries)
        return {"batch_id": self.batch_id, "requested": len(self.entries), "document_ready": ready,
                "data_exceptions": len(self.entries) - ready, "source_rows": self.source_row_count,
                "source_nonfinite_count": self.source_nonfinite_count, "source_reads": 1,
                "authority": "ADVISORY_ONLY", "production_accepted": False}


def load_native_batch(root, reference, *, run_id, tickers, captured_at, max_tickers=5000):
    nonempty(run_id, "run id")
    captured_at = utc(captured_at)
    if type(max_tickers) is not int or max_tickers < 1:
        raise ContractError("positive ticker budget required")
    if type(tickers) is not tuple or not tickers or len(tickers) > max_tickers:
        raise ContractError("nonempty bounded immutable ticker worklist required")
    if any(type(t) is not str or not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]*", t) for t in tickers):
        raise ContractError("exact canonical ticker required")
    if len(set(tickers)) != len(tickers):
        raise ContractError("duplicate worklist ticker")
    document, repairs = read_lab_document(root, reference)
    # Shared corruption must not be disguised as hundreds of ticker exceptions.
    rows = document.get("rows")
    if (document.get("lab_schema_version") != "lab_signal_book_v2" or document.get("run_id") != run_id
            or type(rows) is not list or type(document.get("candidate_count")) is not int
            or len(rows) != document["candidate_count"]):
        raise ContractError("shared native book schema/run/count failure")
    for row in rows:
        if type(row) is not dict or row.get("run_id") != run_id or row.get("lab_schema_version") != "lab_signal_book_v2":
            raise ContractError("shared native book contains mixed run/schema identities")
    from ..domain import instant
    if instant(document.get("created_at_utc")) > instant(captured_at):
        raise ContractError("book creation follows capture")
    entries = []
    for ticker in sorted(tickers):
        try:
            snapshot = lab_snapshot_from_document(document, repairs, reference, run_id=run_id,
                                                   ticker=ticker, captured_at=captured_at)
            entries.append(TickerDocument(ticker, "DOCUMENT_READY", snapshot, None))
        except ContractError as exc:
            entries.append(TickerDocument(ticker, "DATA_EXCEPTION", None, str(exc)))
    return NativeBatch(run_id, reference.expected_sha256, captured_at, tuple(entries), len(rows), len(repairs))


@dataclass(frozen=True, slots=True)
class PreparedTicker:
    ticker: str
    status: str
    bundle: EvidenceBundle | None
    reason: str | None


def prepare_evidence_batch(batch, bundles, *, macro_snapshots=()):
    """Explicit governed bundles only; never resurrect omitted/dropped tickers."""
    if not isinstance(batch, NativeBatch) or type(bundles) is not tuple or not bundles:
        raise ContractError("native batch and governed immutable bundles required")
    if any(not isinstance(b, EvidenceBundle) for b in bundles):
        raise ContractError("invalid governed bundle")
    if type(macro_snapshots) is not tuple or any(not isinstance(s, NativeSnapshot) or s.kind not in
                                               {"MACRO_INTELLIGENCE", "BOND_MACRO"} for s in macro_snapshots):
        raise ContractError("only approved macro snapshots may be shared")
    if len({s.kind for s in macro_snapshots}) != len(macro_snapshots):
        raise ContractError("duplicate macro kind")
    if len({b.identity.ticker for b in bundles}) != len(bundles):
        raise ContractError("duplicate governed ticker")
    index = {e.ticker: e for e in batch.entries}
    results = []
    for bundle in sorted(bundles, key=lambda b: b.identity.ticker):
        ticker = bundle.identity.ticker
        try:
            entry = index.get(ticker)
            if bundle.identity.run_id != batch.run_id:
                raise ContractError("governed bundle run mismatch")
            if entry is None or entry.snapshot is None:
                raise ContractError(entry.reason if entry else "ticker not in authorized batch worklist")
            attached = attach_native_document(bundle, entry.snapshot)
            for snapshot in macro_snapshots:
                attached = attach_native_document(attached, snapshot)
            results.append(PreparedTicker(ticker, "EVIDENCE_PREPARED", attached, None))
        except ContractError as exc:
            results.append(PreparedTicker(ticker, "DATA_EXCEPTION", None, str(exc)))
    return tuple(results)
