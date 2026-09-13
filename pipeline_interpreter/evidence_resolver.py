"""Single governed evidence resolver for all production Interpreter commands.

The resolver performs filesystem validation only.  It never imports provider
clients and never makes API calls.  When current evidence is unavailable it
returns a narrow, declarative refresh requirement for the pipeline/CDS owner.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
import json

import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from contracts.interpreter_handoff import (  # noqa: E402
    HandoffValidationError,
    ValidatedHandoff,
    validate_handoff_manifest,
)
from canonical_data.bundle_freshness import derive_bundle_freshness  # noqa: E402
try:  # Support both package imports and direct script execution.
    from .macro_context import MacroContext, load_macro_packet, missing_macro_context  # type: ignore
except ImportError:  # pragma: no cover - direct CLI compatibility
    from macro_context import MacroContext, load_macro_packet, missing_macro_context  # noqa: E402


DEFAULT_RUNS_DIR = REPO_ROOT / "data" / "output" / "runs"
ADVISORY_FRESHNESS_DOMAINS = frozenset({
    "macro", "macro_quant_packet", "news", "bond", "auction_calendar",
    "catalyst", "supplemental_context",
    "market_structure",
})


class IntendedUse(str, Enum):
    EOD_REVIEW = "EOD_REVIEW"
    EXECUTABLE_SESSION = "EXECUTABLE_SESSION"
    INTRADAY_ADVISORY = "INTRADAY_ADVISORY"
    TRAJECTORY = "TRAJECTORY"


class EvidenceResolutionError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(code + (f":{detail}" if detail else ""))


@dataclass(frozen=True, slots=True)
class ResolvedInterpreterRun:
    handoff: ValidatedHandoff
    book_by_ticker: Mapping[str, dict[str, Any]]
    bundle_by_ticker: Mapping[str, dict[str, Any]]

    @property
    def run_id(self) -> str:
        return str(self.handoff.manifest["run_id"])


@dataclass(frozen=True, slots=True)
class ResolvedInterpreterEvidence:
    manifest_path: Path
    manifest: Mapping[str, Any]
    book_row: Mapping[str, Any]
    bundle: Mapping[str, Any]
    macro: MacroContext
    intended_use: IntendedUse
    refresh_required: Mapping[str, Any] | None = None

    @property
    def run_id(self) -> str:
        return str(self.bundle["run_id"])

    @property
    def ticker(self) -> str:
        return str(self.bundle["ticker"])

    @property
    def frozen_thesis(self) -> Mapping[str, Any]:
        return dict(self.bundle.get("frozen_thesis") or {})

    @property
    def current_validation(self) -> Mapping[str, Any]:
        return dict(self.bundle.get("current_validation") or {})


@dataclass(frozen=True, slots=True)
class ResolvedOpportunityEvidence:
    """Non-executable full-book evidence for review and trajectory analysis."""
    run_id: str
    ticker: str
    book_path: Path
    book_row: Mapping[str, Any]
    intended_use: IntendedUse
    authority: str = "ADVISORY_ONLY"
    provider_calls: int = 0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _canonical_contract(value: Any) -> str:
    return _text(value).upper().replace("O:", "").replace(" ", "")


def _latest_accepted_manifest(runs_dir: Path) -> Path:
    accepted: list[tuple[str, Path]] = []
    for candidate in runs_dir.glob("*/interpreter/handoff_manifest.json"):
        try:
            handoff = validate_handoff_manifest(candidate, require_accepted=True)
        except HandoffValidationError:
            continue
        accepted.append((str(handoff.manifest.get("published_at_utc", "")), candidate))
    if not accepted:
        raise EvidenceResolutionError("NO_ACCEPTED_INTERPRETER_HANDOFF")
    return max(accepted, key=lambda item: item[0])[1]


def resolve_interpreter_run(
    *,
    manifest_path: Path | str | None = None,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
) -> ResolvedInterpreterRun:
    path = Path(manifest_path).resolve() if manifest_path else _latest_accepted_manifest(Path(runs_dir))
    try:
        handoff = validate_handoff_manifest(path, require_accepted=True)
    except HandoffValidationError as error:
        raise EvidenceResolutionError("HANDOFF_VALIDATION_FAILED", str(error)) from error
    book_by_ticker: dict[str, dict[str, Any]] = {}
    for raw in handoff.book_rows:
        ticker = _text(raw.get("ticker")).upper()
        if not ticker or ticker in book_by_ticker:
            raise EvidenceResolutionError("BOOK_TICKER_IDENTITY_INVALID", ticker)
        book_by_ticker[ticker] = dict(raw)
    bundle_by_ticker: dict[str, dict[str, Any]] = {}
    for raw in handoff.bundles:
        ticker = _text(raw.get("ticker")).upper()
        if ticker in bundle_by_ticker:
            raise EvidenceResolutionError("BUNDLE_TICKER_DUPLICATE", ticker)
        bundle_by_ticker[ticker] = dict(raw)
    return ResolvedInterpreterRun(handoff, book_by_ticker, bundle_by_ticker)


def _identity_match(book: Mapping[str, Any], bundle: Mapping[str, Any]) -> None:
    for field in (
        "run_id", "ticker", "thesis_id", "trade_idea_id", "selected_structure_id",
        "selected_quote_snapshot_id",
    ):
        if _text(book.get(field)).upper() != _text(bundle.get(field)).upper():
            raise EvidenceResolutionError("BOOK_BUNDLE_IDENTITY_MISMATCH", field)
    book_contract = _canonical_contract(
        book.get("selected_contract_symbol")
        or book.get("contract_symbol")
        or book.get("morning_selected_contract_symbol")
    )
    if book_contract != _canonical_contract(bundle.get("selected_contract_symbol")):
        raise EvidenceResolutionError("BOOK_BUNDLE_IDENTITY_MISMATCH", "selected_contract_symbol")
    for field in (
        "governed_direction", "final_action", "thesis_state", "olm_guard_disposition",
    ):
        governed_value = (bundle.get("governed_record") or {}).get(field)
        if _text(book.get(field)).upper() != _text(governed_value).upper():
            raise EvidenceResolutionError("BOOK_BUNDLE_AUTHORITY_MISMATCH", field)
    validation = bundle.get("current_validation") or {}
    if validation and _text(book.get("validation_event_id")) != _text(
        validation.get("validation_event_id")
    ):
        raise EvidenceResolutionError(
            "BOOK_BUNDLE_IDENTITY_MISMATCH", "validation_event_id"
        )


def _refresh_requirement(
    bundle: Mapping[str, Any], intended_use: IntendedUse
) -> dict[str, Any] | None:
    if intended_use is IntendedUse.TRAJECTORY:
        return None
    allowed = {"FRESH", "EOD_CURRENT"} if intended_use is IntendedUse.EOD_REVIEW else {"FRESH"}
    evidence_record = dict(bundle.get("governed_record") or {})
    quote_change = bundle.get("quote_change_evidence")
    if isinstance(quote_change, Mapping):
        evidence_record.update(quote_change)
    freshness_map = derive_bundle_freshness(evidence_record)
    # Compatibility for already-published v1 handoffs that predate canonical
    # timestamps.  New production v3 books are required by the readiness gate
    # to carry the timestamps, so their freshness can never use this branch.
    legacy_map = dict(bundle.get("freshness_map") or {})
    for domain in ("exact_option_quote", "underlying_quote", "market_structure"):
        legacy = _text(legacy_map.get(domain)).upper()
        if freshness_map.get(domain) in {"MISSING", "INVALID"} and legacy:
            freshness_map[domain] = legacy
    stale_domains = [
        str(domain)
        for domain, state in freshness_map.items()
        if str(domain).lower() not in ADVISORY_FRESHNESS_DOMAINS
        and str(state).upper() not in allowed
    ]
    if not stale_domains:
        return None
    # A successfully validated Morning thesis remains valid for its governed
    # 1-20 session holding horizon, but execution evidence has a much shorter
    # lifetime.  Stale/missing quotes therefore request a narrow refresh while
    # trade_thesis_affected remains false.
    blocking_domains = sorted(stale_domains)
    return {
        "request_type": "CDS_NARROW_REFRESH_REQUIRED",
        "run_id": bundle["run_id"],
        "ticker": bundle["ticker"],
        "selected_contract_symbol": bundle["selected_contract_symbol"],
        "domains": sorted(stale_domains),
        "advisory_domains": [],
        "blocking_domains": blocking_domains,
        "disposition": "BLOCKING_EVIDENCE_REFRESH",
        "trade_thesis_affected": False,
        "intended_use": intended_use.value,
        "provider_calls_made": 0,
    }


def resolve_interpreter_evidence(
    ticker: str,
    *,
    intended_use: IntendedUse | str = IntendedUse.EXECUTABLE_SESSION,
    manifest_path: Path | str | None = None,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
    require_current: bool = True,
) -> ResolvedInterpreterEvidence:
    symbol = _text(ticker).upper()
    if not symbol:
        raise EvidenceResolutionError("TICKER_REQUIRED")
    use = intended_use if isinstance(intended_use, IntendedUse) else IntendedUse(str(intended_use).upper())
    resolved_run = resolve_interpreter_run(manifest_path=manifest_path, runs_dir=runs_dir)
    book = resolved_run.book_by_ticker.get(symbol)
    bundle = resolved_run.bundle_by_ticker.get(symbol)
    if book is None or bundle is None:
        raise EvidenceResolutionError("TICKER_NOT_IN_ACCEPTED_HANDOFF", symbol)
    _identity_match(book, bundle)
    if use in {IntendedUse.EXECUTABLE_SESSION, IntendedUse.INTRADAY_ADVISORY}:
        stages = dict(resolved_run.handoff.manifest.get("required_stage_status") or {})
        morning = str(stages.get("MORNING_GATE") or stages.get("morning_gate") or "").upper()
        if morning not in {"PASS", "COMPLETED", "ACCEPTED"}:
            raise EvidenceResolutionError("MORNING_GATE_NOT_COMPLETED")
    refresh = _refresh_requirement(bundle, use)
    if refresh and refresh.get("blocking_domains") and require_current:
        raise EvidenceResolutionError(
            "EVIDENCE_REFRESH_REQUIRED", ",".join(refresh["blocking_domains"])
        )
    macro = missing_macro_context()
    macro_reference = bundle.get("macro_quant_packet")
    if isinstance(macro_reference, Mapping) and macro_reference:
        macro = load_macro_packet(
            macro_reference,
            run_root=resolved_run.handoff.manifest_path.parent.parent,
            ticker=symbol,
        )
    return ResolvedInterpreterEvidence(
        manifest_path=resolved_run.handoff.manifest_path,
        manifest=resolved_run.handoff.manifest,
        book_row=book,
        bundle=bundle,
        macro=macro,
        intended_use=use,
        refresh_required=refresh,
    )


def resolve_interpreter_opportunity(
    ticker: str,
    *,
    run_id: str | None = None,
    intended_use: IntendedUse | str = IntendedUse.EOD_REVIEW,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
) -> ResolvedOpportunityEvidence:
    """Resolve any governed opportunity without pretending it is executable."""
    symbol = _text(ticker).upper()
    if not symbol:
        raise EvidenceResolutionError("TICKER_REQUIRED")
    use = intended_use if isinstance(intended_use, IntendedUse) else IntendedUse(str(intended_use).upper())
    if use not in {IntendedUse.EOD_REVIEW, IntendedUse.TRAJECTORY}:
        raise EvidenceResolutionError("FULL_BOOK_USE_NOT_ADVISORY", use.value)
    root = Path(runs_dir)
    candidates = [root / run_id] if run_id else sorted(
        (path for path in root.iterdir() if path.is_dir() and path.name.lower() != "latest"),
        key=lambda path: path.name, reverse=True,
    )
    for run_root in candidates:
        rid = run_root.name
        book = run_root / "intelligence_lab" / f"final_opportunity_book_{rid}.json"
        if not book.is_file():
            continue
        try:
            payload = json.loads(book.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceResolutionError("FINAL_BOOK_INVALID", str(error)) from error
        rows = payload.get("rows") if isinstance(payload, Mapping) else None
        if not isinstance(rows, list) or payload.get("candidate_count") not in (None, len(rows)):
            raise EvidenceResolutionError("FINAL_BOOK_RECONCILIATION_FAILED", rid)
        matches = [dict(row) for row in rows if _text(row.get("ticker")).upper() == symbol]
        if len(matches) > 1:
            raise EvidenceResolutionError("FINAL_BOOK_TICKER_DUPLICATE", symbol)
        if matches:
            row = matches[0]
            if _text(row.get("run_id")) != rid:
                raise EvidenceResolutionError("FINAL_BOOK_RUN_ID_MISMATCH", rid)
            return ResolvedOpportunityEvidence(rid, symbol, book, row, use)
        if run_id:
            break
    raise EvidenceResolutionError("TICKER_NOT_IN_FULL_OPPORTUNITY_BOOK", symbol)


def handoff_status(
    *, manifest_path: Path | str | None = None, runs_dir: Path | str = DEFAULT_RUNS_DIR
) -> dict[str, Any]:
    try:
        run = resolve_interpreter_run(manifest_path=manifest_path, runs_dir=runs_dir)
    except EvidenceResolutionError as error:
        return {"status": "BLOCKED", "reason": error.code, "detail": error.detail}
    return {
        "status": "READY",
        "run_id": run.run_id,
        "manifest": str(run.handoff.manifest_path),
        "ticker_count": len(run.book_by_ticker),
        "bundle_count": len(run.bundle_by_ticker),
        "hashes_verified": True,
        "run_status": run.handoff.manifest.get("run_status"),
    }


__all__ = [
    "ADVISORY_FRESHNESS_DOMAINS", "DEFAULT_RUNS_DIR", "EvidenceResolutionError", "IntendedUse",
    "ResolvedInterpreterEvidence", "ResolvedInterpreterRun", "ResolvedOpportunityEvidence",
    "handoff_status", "resolve_interpreter_evidence", "resolve_interpreter_opportunity",
    "resolve_interpreter_run",
]

