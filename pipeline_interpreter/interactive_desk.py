"""Governed Lab-to-Interpreter report and question service.

Only explicit human selections enter this advisory context. Reports and Q&A
have no path to the execution gate, capital allocator, or broker write tools.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Mapping
from urllib.parse import urlsplit

from flask import jsonify, request

from contracts.interpreter_eod_review import build_eod_review_bundle
from domain.interpreter_review_selection import ReviewSelectionError, select_review_batch
from pipeline_interpreter.confluence_evidence import CHAIN_KEYS, build_confluence_evidence
from pipeline_interpreter.interactive_snapshot import SnapshotError, load_eod_snapshot
from pipeline_interpreter.desk_provider_common import (
    ProviderOutcomeUnknown, ProviderReplyUnusable, ProviderRequestRejected, ProviderUnavailable,
)


REPORT_VERSION = "interpreter_desk_report_v2"
PROMPT_VERSION = "interpreter_desk_prompt_v3"
DEEP_REPORT_VERSION = "interpreter_desk_deep_report_v1"
SECTION_KEYS = ("macro", "gamma", "liquidity", "thesis", "chart", "options_flow", "risk", "verdict")
EVIDENCE_CLASSES = frozenset({"OBSERVED", "DERIVED", "INFERRED", "UNKNOWN"})
_SAFE_NAME = re.compile(r"^[A-Z0-9.^-]{1,24}$")
_SAFE_SHA = re.compile(r"^[0-9a-f]{64}$")

# The complete source row is retained in the frozen EOD snapshot. Only these
# domain facts go into a model request; omissions are counted and disclosed.
EVIDENCE_FIELDS = (
    "canonical_direction", "direction", "thesis_id", "thesis_state", "target_price",
    "invalidation_price", "planned_hold_sessions", "planned_hold_source", "signal_price",
    "last_price", "current_price", "evening_thesis_bucket", "evening_thesis_reason",
    "pretrade_thesis_state", "pretrade_focus_lane", "trigger_go_eligible",
    "trigger_price", "trigger_quality", "trigger_evidence", "direction_conflict_status", "conflict_state",
    "profile_type", "poc", "vah", "val", "market_profile_type", "market_profile_poc",
    "market_profile_vah", "market_profile_val", "vwap", "volume", "relative_volume",
    "wyckoff_phase_bucket", "wyckoff_entry_trigger", "wyckoff_execution_bias",
    "wyckoff_validation_last_confirmed_event", "wyckoff_validation_next_expected_event",
    "wyckoff_validation_contradicting_evidence", "call_wall", "put_wall",
    "gamma_flip", "gex", "contract_symbol", "selected_contract_symbol", "strike",
    "expiry", "contract_dte", "contract_bid", "contract_ask", "contract_delta",
    "contract_gamma", "contract_iv", "contract_oi", "contract_volume",
    "contract_bid_size", "contract_ask_size",
    "contract_quote_quality", "selected_quote_timestamp_utc", "selected_quote_dataset_id",
    "monetisability_state", "liquidity_thesis_state", "sector", "sector_etf",
    "macro_packet_id", "macro_packet_sha256", "macro_context_state",
    "macro_sector_alignment", "usmi_sector_alignment", "catalyst_type",
    "catalyst_date", "catalyst_event_status", "positive_factors", "negative_factors",
)

# Deep-dive widening — additive only, never used by the standard report/ask
# routes below. Field names are copied verbatim from where each is written:
#   - physics_* / *_state_id / *_score etc.: intelligence-lab/intelligence_lab.py PHYSICS_FIELDS
#   - iv_gex_* / move_theta_* / crowd_arrival_*: mcmillan_advisory_layer.py MCMILLAN_FIELDS
#   - wbs*: wall_break_scorer.py score_wall_break() output merged into the row
# A name that isn't actually present on a given row is silently skipped by
# compile_evidence_digest below (same behaviour as EVIDENCE_FIELDS today) —
# an unconfirmed or renamed column here costs nothing and breaks nothing.
DEEP_DIVE_EXTRA_FIELDS = (
    "physics_state_id", "market_energy_score", "compression_energy",
    "directional_force", "force_alignment_score", "trend_inertia",
    "volatility_pressure", "entropy_score", "regime_instability_score",
    "phase_transition_probability", "shock_sensitivity",
    "liquidity_friction_score", "hidden_state_label",
    "state_transition_label", "future_state_5d", "future_state_10d",
    "future_state_20d", "transition_success_5d",
    "transition_success_10d", "transition_success_20d",
    "iv_gex_entry_quality", "iv_gex_entry_quality_label",
    "iv_gex_entry_quality_narrative", "gamma_island_on_path",
    "move_theta_ratio", "move_theta_margin_label", "move_theta_narrative",
    "crowd_arrival_state", "crowd_arrival_score", "crowd_arrival_narrative",
    "wbs", "wbs_grade", "wbs_wall_price", "wbs_wall_distance_pct",
    "wbs_phase_b_trigger", "wbs_phase_c_trigger", "wbs_rejection_stop", "wbs_notes",
)
EXTENDED_EVIDENCE_FIELDS = EVIDENCE_FIELDS + DEEP_DIVE_EXTRA_FIELDS

DEEP_PROMPT_VERSION = "interpreter_desk_deep_prompt_v1"


class DeskError(ValueError):
    pass


def _clean(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_clean(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def compile_evidence_digest(row: Mapping[str, Any], bundle: Mapping[str, Any], morning: Mapping[str, Any] | None = None,
                            *, evidence_cutoff_utc: str, eod_technical_health: str,
                            confluence: Mapping[str, Any] | None = None,
                            fields: tuple[str, ...] = EVIDENCE_FIELDS,
                            max_chars: int = 20000) -> dict[str, Any]:
    """Bound a one-ticker prompt without quietly losing required evidence.

    ``fields``/``max_chars`` default to the standard report/ask bound exactly
    as before; the deep-dive route is the only caller that overrides them.
    """

    retained: dict[str, Any] = {}
    omitted: list[str] = []
    for key in fields:
        if key not in row:
            continue
        value = _clean(row[key])
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, default=str)
        if len(encoded) > 1200:
            omitted.append(f"{key}:oversize")
        else:
            retained[key] = value
    chain = dict(confluence) if confluence is not None else build_confluence_evidence(
        row, session_date=None, evidence_cutoff_utc=evidence_cutoff_utc,
        historical_prices_path=Path(__file__).resolve().parents[1] / "data" / "canonical" / "historical_prices.sqlite",
        morning=morning,
    )
    refs = ["EOD_BOOK"] + (["MORNING_HANDOFF"] if morning else [])
    if chain.get("price_path", {}).get("state") == "OBSERVED":
        refs.append("PIT_PRICE_BARS")
    digest = {
        "run_id": bundle["run_id"], "ticker": bundle["ticker"],
        "authority": "ADVISORY_ONLY", "source_action": bundle.get("source_action"),
        "selected_contract_symbol": bundle.get("selected_contract_symbol"),
        "eod_bundle_id": bundle["bundle_id"],
        "eod_manifest_sha256": bundle["source_manifest_sha256"],
        "eod_technical_health": eod_technical_health,
        "evidence_cutoff_utc": _latest_accepted_cutoff(evidence_cutoff_utc, morning),
        "eod_fields": retained,
        "confluence": _clean(chain),
        "morning_evidence": _clean(morning) if morning else None,
        "evidence_refs": refs,
        "omitted_fields": omitted,
        "available_field_count": len(row), "included_field_count": len(retained),
        "unavailable_depth_or_prints": True,
    }
    if len(json.dumps(digest, ensure_ascii=False, allow_nan=False, default=str)) > max_chars:
        raise DeskError(f"bounded evidence exceeds {max_chars:,} characters; no silent truncation")
    return digest


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError) as exc:
        raise DeskError("invalid point-in-time event timestamp") from exc
    if parsed.tzinfo is None:
        raise DeskError("event timestamp has no timezone")
    return parsed


def _latest_accepted_cutoff(eod_cutoff_utc: str, morning: Mapping[str, Any] | None) -> str:
    """Use the newest accepted handoff, never an ungoverned fetch or wall clock."""

    eod_cutoff = _instant(eod_cutoff_utc)
    if morning is None:
        return eod_cutoff_utc
    morning_cutoff_utc = morning.get("evidence_cutoff_utc")
    morning_cutoff = _instant(morning_cutoff_utc)
    if morning_cutoff < eod_cutoff:
        raise DeskError("Morning evidence cutoff predates the frozen Evening run")
    return morning_cutoff_utc


def _validate_report(output: Mapping[str, Any], allowed_refs: set[str], evidence_cutoff_utc: str,
                     confluence: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(output, Mapping):
        raise DeskError("provider report is not an object")
    sections = output.get("sections")
    if not isinstance(sections, list) or len(sections) != len(SECTION_KEYS):
        raise DeskError("provider report is missing analytical sections")
    seen = set()
    clean_sections = []
    for section in sections:
        if not isinstance(section, Mapping):
            raise DeskError("invalid report section")
        key = section.get("key")
        text = section.get("text")
        category = section.get("evidence_class")
        refs = section.get("evidence_refs")
        if key not in SECTION_KEYS or key in seen or not isinstance(text, str) or not text.strip() or len(text) > 6000:
            raise DeskError("invalid or duplicate report section")
        if category not in EVIDENCE_CLASSES or not isinstance(refs, list) or not set(refs).issubset(allowed_refs):
            raise DeskError("report section has invalid evidence classification")
        seen.add(key)
        clean_sections.append({"key": key, "text": text.strip(), "evidence_class": category, "evidence_refs": refs})
    if seen != set(SECTION_KEYS):
        raise DeskError("report sections do not reconcile")
    chain_review = output.get("evidence_chain_review")
    if not isinstance(chain_review, list) or len(chain_review) != len(CHAIN_KEYS):
        raise DeskError("report must account for every confluence link")
    reviewed = []
    seen_links: set[str] = set()
    for item in chain_review:
        if not isinstance(item, Mapping) or item.get("key") not in CHAIN_KEYS or item["key"] in seen_links:
            raise DeskError("invalid or duplicate confluence link")
        key = item["key"]
        expected = confluence.get(key)
        refs = item.get("evidence_refs")
        if (not isinstance(expected, Mapping) or item.get("status") != expected.get("status")
                or not isinstance(item.get("text"), str) or not item["text"].strip()
                or len(item["text"]) > 2500 or item.get("evidence_class") not in EVIDENCE_CLASSES
                or not isinstance(refs, list) or not set(refs).issubset(allowed_refs)
                or expected.get("evidence_ref") not in refs):
            raise DeskError("report confluence link contradicts governed evidence contract")
        seen_links.add(key)
        reviewed.append({"key": key, "status": item["status"], "text": item["text"].strip(),
                         "evidence_class": item["evidence_class"], "evidence_refs": refs})
    counter_case = output.get("counter_case")
    if not isinstance(counter_case, Mapping):
        raise DeskError("report counter-case missing")
    counter_links = counter_case.get("links")
    counter_refs = counter_case.get("evidence_refs")
    required_counter_links = {
        key for key in CHAIN_KEYS
        if confluence[key]["status"] not in {"SUPPORTS", "STRONG_TRIGGER", "EOD_ACTIVE_QUOTE_TRAIT",
                                            "THESIS_CONFIRMED"}
    }
    if (not isinstance(counter_links, list) or not all(isinstance(key, str) for key in counter_links)
            or len(counter_links) != len(set(counter_links))
            or not set(counter_links).issubset(CHAIN_KEYS)
            or not required_counter_links.issubset(counter_links)
            or not isinstance(counter_case.get("text"), str) or not counter_case["text"].strip()
            or len(counter_case["text"]) > 4000 or not isinstance(counter_refs, list)
            or not set(counter_refs).issubset(allowed_refs)
            or any(confluence[key]["evidence_ref"] not in counter_refs for key in counter_links)):
        raise DeskError("report counter-case does not cover opposing or unknown evidence")
    summary = output.get("executive_summary")
    if not isinstance(summary, str) or not summary.strip():
        raise DeskError("report summary missing")
    if len(summary) + sum(len(section["text"]) for section in clean_sections) > 40000:
        raise DeskError("provider report exceeds bounded conversation size")
    events = output.get("external_events")
    if not isinstance(events, list):
        raise DeskError("external event list missing")
    verified_urls = set(output.get("_verified_web_urls") or [])
    for event in events:
        if not isinstance(event, Mapping) or event.get("url") not in verified_urls or not event.get("asof_utc"):
            raise DeskError("external event lacks a verified source and event time")
        parsed_url = urlsplit(event["url"])
        if parsed_url.scheme != "https" or not parsed_url.hostname:
            raise DeskError("external event URL is not a secure source")
        if _instant(event["asof_utc"]) > _instant(evidence_cutoff_utc):
            raise DeskError("external event postdates the frozen evidence cutoff")
    unresolved = output.get("unresolved")
    if not isinstance(unresolved, list):
        raise DeskError("unresolved evidence list missing")
    return {
        "executive_summary": summary.strip(), "sections": clean_sections,
        "evidence_chain_review": reviewed,
        "counter_case": {"links": counter_links, "text": counter_case["text"].strip(),
                         "evidence_refs": counter_refs},
        "external_events": events, "unresolved": [str(x) for x in unresolved],
    }


def _validate_answer(value: Mapping[str, Any], allowed_refs: set[str], question: str) -> dict[str, Any]:
    if (not isinstance(value, Mapping) or not isinstance(value.get("answer"), str)
            or not value["answer"].strip() or len(value["answer"]) > 6000):
        raise DeskError("provider answer missing")
    category = value.get("evidence_class")
    refs = value.get("evidence_refs")
    limitations = value.get("limitations")
    if category not in EVIDENCE_CLASSES or not isinstance(refs, list) or not set(refs).issubset(allowed_refs):
        raise DeskError("question answer has invalid evidence lineage")
    if not isinstance(limitations, list):
        raise DeskError("question answer lacks limitations")
    if any(term in question.lower() for term in ("hiding", "hidden order", "buyers hiding", "sellers hiding")) and not limitations:
        raise DeskError("hidden-order answer must disclose observation limits")
    return {"answer": value["answer"].strip(), "evidence_class": category,
            "evidence_refs": refs, "limitations": [str(x) for x in limitations]}


def _morning_evidence(root: Path, ticker: str) -> dict[str, Any] | None:
    handoff = root / "interpreter" / "handoff_manifest.json"
    if not handoff.is_file():
        return None
    from pipeline_interpreter.evidence_resolver import (
        EvidenceResolutionError, IntendedUse, resolve_interpreter_evidence,
    )
    try:
        resolved = resolve_interpreter_evidence(
            ticker, intended_use=IntendedUse.EXECUTABLE_SESSION,
            manifest_path=handoff, runs_dir=root.parent, require_current=False,
        )
    except EvidenceResolutionError as exc:
        if "TICKER_NOT_IN_ACCEPTED_HANDOFF" in str(exc):
            return None
        raise DeskError(f"Morning handoff cannot be trusted: {exc}") from exc
    bundle = dict(resolved.bundle)
    governed = dict(bundle.get("governed_record") or {})
    # Governed Morning names (validation event owner): transition, reason, event id
    # and the observed underlying price at validation.
    fields = {key: _clean(governed[key]) for key in (
        "thesis_state", "final_action", "validation_transition", "validation_reason",
        "validation_event_id", "validation_current_price",
        "selected_contract_symbol", "selected_quote_snapshot_id",
        "selected_quote_timestamp_utc", "quote_change_evidence", "market_structure",
    ) if key in governed}
    return {"bundle_id": bundle.get("bundle_id"), "fields": fields,
            "evidence_cutoff_utc": resolved.manifest.get("morning_gate_completed_utc"),
            "refresh_required": resolved.refresh_required}


def _confluence_for(row: Mapping[str, Any], frozen: Mapping[str, Any],
                    morning: Mapping[str, Any] | None) -> dict[str, Any]:
    return build_confluence_evidence(
        row, session_date=frozen["meta"].get("session_date"),
        evidence_cutoff_utc=_latest_accepted_cutoff(
            frozen["receipt"]["evidence_cutoff_utc"], morning),
        historical_prices_path=Path(__file__).resolve().parents[1] / "data" / "canonical" / "historical_prices.sqlite",
        morning=morning,
    )


def _report_root(root: Path, ticker: str) -> Path:
    if not _SAFE_NAME.fullmatch(ticker):
        raise DeskError("unsafe ticker")
    return root / "interpreter" / "interactive_desk" / ticker


def _report_id(digest: Mapping[str, Any], model_id: str) -> str:
    key = {"digest": digest, "model_id": model_id, "prompt_version": PROMPT_VERSION}
    return hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _persist_attempt(path: Path, record: Mapping[str, Any]) -> None:
    """Replace the pending marker atomically; never expose a partial receipt."""

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".interpreter-attempt-", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(record, handle, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _report_failure(run_id: str, ticker: str, report_id: str,
                    stage: str, error: Exception, *, elapsed_ms: int | None = None) -> dict[str, Any]:
    """Classify only provable failures as FAILED; uncertainty never permits retry."""

    receipt: dict[str, Any] = {
        "run_id": run_id, "ticker": ticker, "report_id": report_id,
        "authority": "ADVISORY_ONLY", "retry_allowed": False,
        "failure_stage": stage, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if isinstance(error, ProviderRequestRejected):
        message = f"Provider rejected request (HTTP {error.http_status}); no automatic retry."
        if getattr(error, "detail", None):
            message = f"{message} Provider said: {error.detail}"
        receipt.update(status="FAILED", failure_code="PROVIDER_HTTP_REJECTED",
                       provider_http_status=error.http_status, error=message)
        if error.request_id:
            receipt["provider_request_id"] = error.request_id
        if getattr(error, "detail", None):
            receipt["provider_error_detail"] = error.detail
    elif isinstance(error, ProviderOutcomeUnknown):
        receipt.update(status="UNKNOWN", failure_code="PROVIDER_OUTCOME_UNKNOWN",
                       error="Provider outcome not yet reconciled; do not retry automatically.")
        if elapsed_ms is not None:
            # Measured, so a timeout is read from the receipt (ACK 24 Sep 2026).
            receipt["provider_elapsed_ms"] = int(elapsed_ms)
    elif isinstance(error, ProviderUnavailable):
        receipt.update(status="FAILED", failure_code="PROVIDER_CONTROLLED_FAILURE",
                       error="Provider did not return a valid governed report; no automatic retry.")
        if isinstance(error, ProviderReplyUnusable):
            # Typed, bounded fields only (ACK 24 Sep 2026): they name the case
            # without carrying provider prose, evidence or credentials.
            receipt.update(provider_failure_reason=error.reason_code,
                           provider_stop_reason=error.stop_reason,
                           provider_block_types=list(error.block_types))
    elif stage == "REPORT_VALIDATION" and isinstance(error, DeskError):
        receipt.update(status="FAILED", failure_code="REPORT_VALIDATION_FAILED",
                       error="Provider response failed controlled validation; no automatic retry.")
    else:
        receipt.update(status="UNKNOWN", failure_code="UNCLASSIFIED_OUTCOME",
                       error="Report outcome could not be proven; do not retry automatically.")
    return receipt


def _default_provider():
    """Selects the Desk's model transport from AVSHUNTER_INTERPRETER_PROVIDER.

    Defaults to Anthropic (Claude) so the Desk's report/ask endpoints use the
    same vendor as the terminal Pipeline Interpreter (/triage, /ticker) by
    default. Set AVSHUNTER_INTERPRETER_PROVIDER=openai to use GPT instead;
    either way the digest, schemas, validation and failure classification in
    this module are unchanged — only the transport differs.
    """
    choice = os.environ.get("AVSHUNTER_INTERPRETER_PROVIDER", "anthropic").strip().lower()
    if choice == "openai":
        from pipeline_interpreter.openai_desk_provider import OpenAIResponsesProvider
        return OpenAIResponsesProvider.from_environment()
    if choice == "anthropic":
        from pipeline_interpreter.anthropic_desk_provider import AnthropicDeskProvider
        return AnthropicDeskProvider.from_environment()
    raise DeskError(f"unknown AVSHUNTER_INTERPRETER_PROVIDER: {choice!r} (use 'anthropic' or 'openai')")


def install_interpreter_desk(app, runs_dir: Path | str, *, provider=None) -> None:
    """Mount isolated advisory endpoints on the existing Lab Flask app."""

    base = Path(runs_dir).resolve()
    if provider is None:
        provider = _default_provider()

    def local_request_allowed() -> bool:
        if request.remote_addr not in {"127.0.0.1", "::1", "localhost"}:
            return False
        origin = request.headers.get("Origin")
        if not origin:
            return True
        try:
            parsed = urlsplit(origin)
            return parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"} and parsed.port == 5002
        except ValueError:
            return False

    def selected(body):
        run_id = str(body.get("run_id") or "").strip()
        if not re.fullmatch(r"\d{8}_\d{6}", run_id):
            raise DeskError("explicit run_id required")
        root = base / run_id
        frozen = load_eod_snapshot(root)
        tickers = body.get("tickers")
        if not isinstance(tickers, list):
            raise DeskError("ticker list required")
        choices = select_review_batch(frozen["rows"], run_id=run_id, tickers=tickers)
        rows = {str(row.get("ticker") or "").upper(): row for row in frozen["rows"]}
        return root, frozen, choices, rows

    @app.route("/api/interpreter/control")
    def interpreter_control():
        if not local_request_allowed():
            return jsonify({"error": "local Lab origin required"}), 403
        return jsonify({"authority": "ADVISORY_ONLY", "max_tickers": 5,
                        "provider_ready": bool(getattr(provider, "ready", True)),
                        "model_id": getattr(provider, "model_id", "UNCONFIGURED"),
                        "deep_dive_ready": hasattr(provider, "deep_report")})

    @app.route("/api/interpreter/preview", methods=["POST"])
    def interpreter_preview():
        if not local_request_allowed():
            return jsonify({"error": "local Lab origin required"}), 403
        try:
            root, frozen, choices, rows = selected(request.get_json(silent=True) or {})
            entries = []
            for choice in choices:
                row = rows[choice.ticker]
                bundle = build_eod_review_bundle(
                    run_id=root.name,
                    source_manifest_sha256=frozen["receipt"]["source_manifest_sha256"],
                    row=row,
                    evidence_refs=[{"dataset_id": "EOD_BOOK", "sha256": frozen["receipt"]["source_book_sha256"]}],
                )
                morning = _morning_evidence(root, choice.ticker)
                digest = compile_evidence_digest(
                    row, bundle, morning,
                    evidence_cutoff_utc=frozen["receipt"]["evidence_cutoff_utc"],
                    eod_technical_health=frozen["receipt"]["eod_technical_health"],
                    confluence=_confluence_for(row, frozen, morning),
                )
                input_chars = len(json.dumps(digest, default=str))
                estimate = getattr(provider, "estimate_report_bound", None)
                bound = estimate(input_chars) if callable(estimate) else None
                entries.append({"ticker": choice.ticker, "source_action": choice.source_action,
                                "phase": "MORNING_DELTA" if morning else "EOD_REVIEW",
                                "input_chars": input_chars, "configured_cost_bound_usd": bound,
                                "omitted_fields": digest["omitted_fields"]})
            return jsonify({"run_id": root.name, "authority": "ADVISORY_ONLY",
                            "model_id": getattr(provider, "model_id", "UNCONFIGURED"),
                            "cost_estimate": "CONFIGURED_CONSERVATIVE_BOUND" if all(
                                e["configured_cost_bound_usd"] is not None for e in entries
                            ) else "UNAVAILABLE_VERIFY_PROVIDER_PRICING",
                            "batch_cost_bound_usd": round(sum(e["configured_cost_bound_usd"] or 0 for e in entries), 6)
                            if all(e["configured_cost_bound_usd"] is not None for e in entries) else None,
                            "entries": entries})
        except (DeskError, ReviewSelectionError, SnapshotError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/interpreter/reports", methods=["POST"])
    def interpreter_reports():
        if not local_request_allowed():
            return jsonify({"error": "local Lab origin required"}), 403
        body = request.get_json(silent=True) or {}
        if body.get("confirmed") is not True:
            return jsonify({"error": "explicit paid-request confirmation required"}), 400
        if not getattr(provider, "ready", True):
            return jsonify({"error": "GPT provider not configured; no request sent"}), 503
        try:
            root, frozen, choices, rows = selected(body)
        except (DeskError, ReviewSelectionError, SnapshotError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        results = []
        for choice in choices:
            error_file: Path | None = None
            marker_written = False
            started: float | None = None
            stage = "PREPARE"
            try:
                row = rows[choice.ticker]
                bundle = build_eod_review_bundle(
                    run_id=root.name,
                    source_manifest_sha256=frozen["receipt"]["source_manifest_sha256"],
                    row=row,
                    evidence_refs=[{"dataset_id": "EOD_BOOK", "sha256": frozen["receipt"]["source_book_sha256"]}],
                )
                morning = _morning_evidence(root, choice.ticker)
                digest = compile_evidence_digest(
                    row, bundle, morning,
                    evidence_cutoff_utc=frozen["receipt"]["evidence_cutoff_utc"],
                    eod_technical_health=frozen["receipt"]["eod_technical_health"],
                    confluence=_confluence_for(row, frozen, morning),
                )
                report_id = _report_id(digest, getattr(provider, "model_id", "UNKNOWN"))
                folder = _report_root(root, choice.ticker)
                report_file = folder / f"{report_id}.json"
                error_file = folder / f"{report_id}.error.json"
                if report_file.is_file():
                    results.append(json.loads(report_file.read_text(encoding="utf-8")))
                    continue
                if error_file.is_file():
                    results.append(json.loads(error_file.read_text(encoding="utf-8")))
                    continue
                # Persistent UNKNOWN marker precedes the paid call. An
                # interrupted request is not silently retried on refresh.
                folder.mkdir(parents=True, exist_ok=True)
                unknown = {"status": "UNKNOWN", "run_id": root.name,
                           "ticker": choice.ticker, "report_id": report_id,
                           "authority": "ADVISORY_ONLY", "retry_allowed": False,
                           "failure_code": "PROVIDER_OUTCOME_PENDING",
                           "error": "Provider outcome not yet reconciled; do not retry automatically."}
                with error_file.open("x", encoding="utf-8") as handle:
                    json.dump(unknown, handle, allow_nan=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                marker_written = True
                stage = "PROVIDER_RESPONSE"
                started = time.monotonic()
                raw = provider.report(digest)
                provider_latency_ms = round((time.monotonic() - started) * 1000)
                provider_retrieved_at_utc = datetime.now(timezone.utc).isoformat()
                stage = "REPORT_VALIDATION"
                content = _validate_report(raw, set(digest["evidence_refs"]),
                                           digest["evidence_cutoff_utc"], digest["confluence"])
                report = {
                    "schema_version": REPORT_VERSION, "status": "COMPLETE",
                    "report_id": report_id, "run_id": root.name, "ticker": choice.ticker,
                    "phase": "MORNING_DELTA" if morning else "EOD_REVIEW",
                    "authority": "ADVISORY_ONLY", "source_action": choice.source_action,
                    "selected_contract_symbol": bundle["selected_contract_symbol"],
                    "eod_bundle_id": bundle["bundle_id"],
                    "morning_bundle_id": morning["bundle_id"] if morning else None,
                    "model_id": getattr(provider, "model_id", "UNKNOWN"),
                    "prompt_version": PROMPT_VERSION, "evidence_digest": digest,
                    "provider_latency_ms": provider_latency_ms,
                    "provider_retrieved_at_utc": provider_retrieved_at_utc,
                    "provider_usage": _clean(raw.get("_provider_usage") or {}),
                    **content,
                }
                stage = "PERSIST_REPORT"
                with report_file.open("x", encoding="utf-8") as handle:
                    json.dump(report, handle, ensure_ascii=False, allow_nan=False)
                error_file.unlink(missing_ok=True)
                results.append(report)
            except Exception as exc:
                if marker_written and error_file is not None:
                    elapsed = round((time.monotonic() - started) * 1000) if started is not None else None
                    failure = _report_failure(root.name, choice.ticker, report_id, stage, exc,
                                              elapsed_ms=elapsed)
                    try:
                        _persist_attempt(error_file, failure)
                    except OSError:
                        # The pre-dispatch UNKNOWN marker remains authoritative.
                        failure = {"status": "UNKNOWN", "run_id": root.name,
                                   "ticker": choice.ticker, "report_id": report_id,
                                   "authority": "ADVISORY_ONLY", "retry_allowed": False,
                                   "failure_code": "DURABLE_STATUS_WRITE_FAILED",
                                   "error": "Durable outcome update failed; inspect the original marker before any retry."}
                else:
                    failure = {"status": "FAILED", "ticker": choice.ticker,
                               "run_id": root.name, "authority": "ADVISORY_ONLY",
                               "retry_allowed": False, "failure_code": "LOCAL_PREPARATION_FAILED",
                               "error": "Local report preparation failed; no provider call was made."}
                results.append(failure)
        return jsonify({"run_id": root.name, "results": results,
                        "authority": "ADVISORY_ONLY"})

    @app.route("/api/interpreter/deep_reports", methods=["POST"])
    def interpreter_deep_reports():
        """Same governed pattern as /reports, widened evidence, one Claude call.

        No junior-briefing layer, no screenshots, no session/triage state —
        reads the same frozen per-run snapshot as every other Desk route.
        Deliberately duplicated from interpreter_reports() rather than
        parameterising it, so nothing here can change that route's behaviour.
        """
        if not local_request_allowed():
            return jsonify({"error": "local Lab origin required"}), 403
        body = request.get_json(silent=True) or {}
        if body.get("confirmed") is not True:
            return jsonify({"error": "explicit paid-request confirmation required"}), 400
        if not getattr(provider, "ready", True):
            return jsonify({"error": "model provider not configured; no request sent"}), 503
        if not hasattr(provider, "deep_report"):
            return jsonify({"error": "configured provider does not support deep-dive reports"}), 503
        try:
            root, frozen, choices, rows = selected(body)
        except (DeskError, ReviewSelectionError, SnapshotError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
        results = []
        for choice in choices:
            error_file: Path | None = None
            marker_written = False
            started: float | None = None
            stage = "PREPARE"
            try:
                row = rows[choice.ticker]
                bundle = build_eod_review_bundle(
                    run_id=root.name,
                    source_manifest_sha256=frozen["receipt"]["source_manifest_sha256"],
                    row=row,
                    evidence_refs=[{"dataset_id": "EOD_BOOK", "sha256": frozen["receipt"]["source_book_sha256"]}],
                )
                morning = _morning_evidence(root, choice.ticker)
                digest = compile_evidence_digest(
                    row, bundle, morning,
                    evidence_cutoff_utc=frozen["receipt"]["evidence_cutoff_utc"],
                    eod_technical_health=frozen["receipt"]["eod_technical_health"],
                    confluence=_confluence_for(row, frozen, morning),
                    fields=EXTENDED_EVIDENCE_FIELDS, max_chars=40000,
                )
                report_id = _report_id(digest, getattr(provider, "model_id", "UNKNOWN"))
                folder = _report_root(root, choice.ticker)
                report_file = folder / f"{report_id}.json"
                error_file = folder / f"{report_id}.error.json"
                if report_file.is_file():
                    results.append(json.loads(report_file.read_text(encoding="utf-8")))
                    continue
                if error_file.is_file():
                    results.append(json.loads(error_file.read_text(encoding="utf-8")))
                    continue
                # Persistent UNKNOWN marker precedes the paid call. An
                # interrupted request is not silently retried on refresh.
                folder.mkdir(parents=True, exist_ok=True)
                unknown = {"status": "UNKNOWN", "run_id": root.name,
                           "ticker": choice.ticker, "report_id": report_id,
                           "authority": "ADVISORY_ONLY", "retry_allowed": False,
                           "failure_code": "PROVIDER_OUTCOME_PENDING",
                           "error": "Provider outcome not yet reconciled; do not retry automatically."}
                with error_file.open("x", encoding="utf-8") as handle:
                    json.dump(unknown, handle, allow_nan=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                marker_written = True
                stage = "PROVIDER_RESPONSE"
                started = time.monotonic()
                raw = provider.deep_report(digest)
                provider_latency_ms = round((time.monotonic() - started) * 1000)
                provider_retrieved_at_utc = datetime.now(timezone.utc).isoformat()
                stage = "REPORT_VALIDATION"
                content = _validate_report(raw, set(digest["evidence_refs"]),
                                           digest["evidence_cutoff_utc"], digest["confluence"])
                report = {
                    "schema_version": DEEP_REPORT_VERSION, "status": "COMPLETE", "mode": "DEEP_DIVE",
                    "report_id": report_id, "run_id": root.name, "ticker": choice.ticker,
                    "phase": "MORNING_DELTA" if morning else "EOD_REVIEW",
                    "authority": "ADVISORY_ONLY", "source_action": choice.source_action,
                    "selected_contract_symbol": bundle["selected_contract_symbol"],
                    "eod_bundle_id": bundle["bundle_id"],
                    "morning_bundle_id": morning["bundle_id"] if morning else None,
                    "model_id": getattr(provider, "model_id", "UNKNOWN"),
                    "prompt_version": DEEP_PROMPT_VERSION, "evidence_digest": digest,
                    "provider_latency_ms": provider_latency_ms,
                    "provider_retrieved_at_utc": provider_retrieved_at_utc,
                    "provider_usage": _clean(raw.get("_provider_usage") or {}),
                    **content,
                }
                stage = "PERSIST_REPORT"
                with report_file.open("x", encoding="utf-8") as handle:
                    json.dump(report, handle, ensure_ascii=False, allow_nan=False)
                error_file.unlink(missing_ok=True)
                results.append(report)
            except Exception as exc:
                if marker_written and error_file is not None:
                    elapsed = round((time.monotonic() - started) * 1000) if started is not None else None
                    failure = _report_failure(root.name, choice.ticker, report_id, stage, exc,
                                              elapsed_ms=elapsed)
                    try:
                        _persist_attempt(error_file, failure)
                    except OSError:
                        # The pre-dispatch UNKNOWN marker remains authoritative.
                        failure = {"status": "UNKNOWN", "run_id": root.name,
                                   "ticker": choice.ticker, "report_id": report_id,
                                   "authority": "ADVISORY_ONLY", "retry_allowed": False,
                                   "failure_code": "DURABLE_STATUS_WRITE_FAILED",
                                   "error": "Durable outcome update failed; inspect the original marker before any retry."}
                else:
                    failure = {"status": "FAILED", "ticker": choice.ticker,
                               "run_id": root.name, "authority": "ADVISORY_ONLY",
                               "retry_allowed": False, "failure_code": "LOCAL_PREPARATION_FAILED",
                               "error": "Local report preparation failed; no provider call was made."}
                results.append(failure)
        return jsonify({"run_id": root.name, "results": results,
                        "authority": "ADVISORY_ONLY"})

    @app.route("/api/interpreter/ask", methods=["POST"])
    def interpreter_ask():
        if not local_request_allowed():
            return jsonify({"error": "local Lab origin required"}), 403
        body = request.get_json(silent=True) or {}
        if body.get("confirmed") is not True:
            return jsonify({"error": "explicit paid-question confirmation required"}), 400
        if not getattr(provider, "ready", True):
            return jsonify({"error": "GPT provider not configured; no request sent"}), 503
        run_id = str(body.get("run_id") or "")
        ticker = str(body.get("ticker") or "").upper()
        report_id = str(body.get("report_id") or "")
        question = str(body.get("question") or "").strip()
        if not re.fullmatch(r"\d{8}_\d{6}", run_id) or not _SAFE_NAME.fullmatch(ticker) or not _SAFE_SHA.fullmatch(report_id):
            return jsonify({"error": "invalid report identity"}), 400
        if not question or len(question) > 500:
            return jsonify({"error": "question must be 1-500 characters"}), 400
        path = _report_root(base / run_id, ticker) / f"{report_id}.json"
        if not path.is_file():
            return jsonify({"error": "report not found for this ticker"}), 409
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("ticker") != ticker or report.get("run_id") != run_id or report.get("report_id") != report_id:
            return jsonify({"error": "report identity mismatch"}), 409
        try:
            journal = path.parent / f"{report_id}.questions.jsonl"
            history = []
            if journal.is_file():
                with journal.open(encoding="utf-8") as handle:
                    for line in handle:
                        if line.strip():
                            item = json.loads(line)
                            if item.get("report_id") == report_id and item.get("ticker") == ticker:
                                history.append({"question": item.get("question"), "answer": item.get("answer")})
            question_digest = dict(report["evidence_digest"])
            question_digest["conversation_history"] = history[-5:]
            if len(json.dumps(question_digest, ensure_ascii=False, default=str)) > 30000:
                raise DeskError("conversation context exceeds bound; start a fresh question")
            started = time.monotonic()
            raw = provider.answer(question_digest, report, question)
            answer = _validate_answer(raw, set(report["evidence_digest"]["evidence_refs"]), question)
            record = {"report_id": report_id, "run_id": run_id, "ticker": ticker,
                      "question": question, "authority": "ADVISORY_ONLY",
                      "provider_latency_ms": round((time.monotonic() - started) * 1000),
                      "provider_usage": _clean(raw.get("_provider_usage") or {}), **answer}
            with journal.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            return jsonify(record)
        except Exception as exc:
            return jsonify({"error": f"controlled question failure: {type(exc).__name__}: {exc}"}), 502

    @app.route("/api/interpreter/saved_reports", methods=["POST"])
    def interpreter_saved_reports():
        """List existing completed JSON reports; never dispatch a provider request."""
        if not local_request_allowed():
            return jsonify({"error": "local Lab origin required"}), 403
        body = request.get_json(silent=True) or {}
        run_id = str(body.get("run_id") or "").strip()
        tickers = body.get("tickers")
        if (not re.fullmatch(r"\d{8}_\d{6}", run_id)
                or not isinstance(tickers, list) or not 1 <= len(tickers) <= 5
                or any(not isinstance(t, str) or not _SAFE_NAME.fullmatch(t) for t in tickers)
                or len(set(tickers)) != len(tickers)):
            return jsonify({"error": "valid run and one to five distinct tickers required"}), 400
        reports = []
        for ticker in tickers:
            folder = _report_root(base / run_id, ticker)
            if not folder.is_dir():
                continue
            # Bound the listing without touching error receipts or the JSON files.
            paths = sorted(folder.glob("*.json"), key=lambda path: path.stat().st_mtime,
                           reverse=True)[:50]
            for path in paths:
                if not _SAFE_SHA.fullmatch(path.stem):
                    continue
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if (not isinstance(value, dict) or value.get("status") != "COMPLETE"
                        or value.get("run_id") != run_id or value.get("ticker") != ticker
                        or value.get("report_id") != path.stem):
                    continue
                reports.append({
                    "run_id": run_id, "ticker": ticker, "report_id": path.stem,
                    "phase": value.get("phase"), "mode": value.get("mode", "STANDARD"),
                    "model_id": value.get("model_id"),
                    "provider_retrieved_at_utc": value.get("provider_retrieved_at_utc"),
                })
        return jsonify({"run_id": run_id, "reports": reports, "authority": "ADVISORY_ONLY"})

    @app.route("/api/interpreter/report/<run_id>/<ticker>/<report_id>")
    def interpreter_get_report(run_id, ticker, report_id):
        if not local_request_allowed():
            return jsonify({"error": "local Lab origin required"}), 403
        ticker = ticker.upper()
        if not re.fullmatch(r"\d{8}_\d{6}", run_id) or not _SAFE_NAME.fullmatch(ticker) or not _SAFE_SHA.fullmatch(report_id):
            return jsonify({"error": "invalid report identity"}), 400
        path = _report_root(base / run_id, ticker) / f"{report_id}.json"
        if not path.is_file():
            return jsonify({"error": "report not found"}), 404
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("run_id") != run_id or value.get("ticker") != ticker or value.get("report_id") != report_id:
            return jsonify({"error": "report identity mismatch"}), 409
        return jsonify(value)
