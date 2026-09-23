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
from pipeline_interpreter.interactive_snapshot import SnapshotError, load_eod_snapshot
from pipeline_interpreter.openai_desk_provider import (
    ProviderOutcomeUnknown, ProviderRequestRejected, ProviderUnavailable,
)


REPORT_VERSION = "interpreter_desk_report_v1"
PROMPT_VERSION = "interpreter_desk_prompt_v1"
SECTION_KEYS = ("macro", "gamma", "liquidity", "thesis", "chart", "options_flow", "risk", "verdict")
EVIDENCE_CLASSES = frozenset({"OBSERVED", "DERIVED", "INFERRED", "UNKNOWN"})
_SAFE_NAME = re.compile(r"^[A-Z0-9.^-]{1,24}$")
_SAFE_SHA = re.compile(r"^[0-9a-f]{64}$")

# The complete source row is retained in the frozen EOD snapshot. Only these
# domain facts go into a model request; omissions are counted and disclosed.
EVIDENCE_FIELDS = (
    "canonical_direction", "direction", "thesis_id", "thesis_state", "target_price",
    "invalidation_spot", "planned_hold_sessions", "planned_hold_source", "signal_price",
    "last_price", "current_price", "evening_thesis_bucket", "evening_thesis_reason",
    "pretrade_thesis_state", "pretrade_focus_lane", "trigger_go_eligible",
    "trigger_price", "trigger_evidence", "direction_conflict_status", "conflict_state",
    "profile_type", "poc", "vah", "val", "market_profile_type", "market_profile_poc",
    "market_profile_vah", "market_profile_val", "vwap", "volume", "relative_volume",
    "wyckoff_phase_bucket", "wyckoff_entry_trigger", "wyckoff_execution_bias",
    "wyckoff_validation_last_confirmed_event", "wyckoff_validation_next_expected_event",
    "wyckoff_validation_contradicting_evidence", "call_wall", "put_wall",
    "gamma_flip", "gex", "contract_symbol", "selected_contract_symbol", "strike",
    "expiry", "contract_dte", "contract_bid", "contract_ask", "contract_delta",
    "contract_gamma", "contract_iv", "contract_oi", "contract_volume",
    "contract_quote_quality", "selected_quote_timestamp_utc", "selected_quote_dataset_id",
    "monetisability_state", "liquidity_thesis_state", "sector", "sector_etf",
    "macro_packet_id", "macro_packet_sha256", "macro_context_state",
    "macro_sector_alignment", "usmi_sector_alignment", "catalyst_type",
    "catalyst_date", "catalyst_event_status", "positive_factors", "negative_factors",
)


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
                            *, evidence_cutoff_utc: str, eod_technical_health: str) -> dict[str, Any]:
    """Bound a one-ticker prompt without quietly losing required evidence."""

    retained: dict[str, Any] = {}
    omitted: list[str] = []
    for key in EVIDENCE_FIELDS:
        if key not in row:
            continue
        value = _clean(row[key])
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, default=str)
        if len(encoded) > 1200:
            omitted.append(f"{key}:oversize")
        else:
            retained[key] = value
    digest = {
        "run_id": bundle["run_id"], "ticker": bundle["ticker"],
        "authority": "ADVISORY_ONLY", "source_action": bundle.get("source_action"),
        "selected_contract_symbol": bundle.get("selected_contract_symbol"),
        "eod_bundle_id": bundle["bundle_id"],
        "eod_manifest_sha256": bundle["source_manifest_sha256"],
        "eod_technical_health": eod_technical_health,
        "evidence_cutoff_utc": morning.get("evidence_cutoff_utc") if morning else evidence_cutoff_utc,
        "eod_fields": retained,
        "morning_evidence": _clean(morning) if morning else None,
        "evidence_refs": ["EOD_BOOK"] + (["MORNING_HANDOFF"] if morning else []),
        "omitted_fields": omitted,
        "available_field_count": len(row), "included_field_count": len(retained),
        "unavailable_depth_or_prints": True,
    }
    if len(json.dumps(digest, ensure_ascii=False, allow_nan=False, default=str)) > 20000:
        raise DeskError("bounded evidence exceeds 20,000 characters; no silent truncation")
    return digest


def _instant(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError) as exc:
        raise DeskError("invalid point-in-time event timestamp") from exc
    if parsed.tzinfo is None:
        raise DeskError("event timestamp has no timezone")
    return parsed


def _validate_report(output: Mapping[str, Any], allowed_refs: set[str], evidence_cutoff_utc: str) -> dict[str, Any]:
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
    fields = {key: _clean(governed[key]) for key in (
        "thesis_state", "final_action", "morning_thesis_result", "current_price",
        "validation_price", "selected_contract_symbol", "selected_quote_snapshot_id",
        "selected_quote_timestamp_utc", "quote_change_evidence", "market_structure",
    ) if key in governed}
    return {"bundle_id": bundle.get("bundle_id"), "fields": fields,
            "evidence_cutoff_utc": resolved.manifest.get("morning_gate_completed_utc"),
            "refresh_required": resolved.refresh_required}


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
                    stage: str, error: Exception) -> dict[str, Any]:
    """Classify only provable failures as FAILED; uncertainty never permits retry."""

    receipt: dict[str, Any] = {
        "run_id": run_id, "ticker": ticker, "report_id": report_id,
        "authority": "ADVISORY_ONLY", "retry_allowed": False,
        "failure_stage": stage, "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if isinstance(error, ProviderRequestRejected):
        receipt.update(status="FAILED", failure_code="PROVIDER_HTTP_REJECTED",
                       provider_http_status=error.http_status,
                       error=f"Provider rejected request (HTTP {error.http_status}); no automatic retry.")
        if error.request_id:
            receipt["provider_request_id"] = error.request_id
    elif isinstance(error, ProviderOutcomeUnknown):
        receipt.update(status="UNKNOWN", failure_code="PROVIDER_OUTCOME_UNKNOWN",
                       error="Provider outcome not yet reconciled; do not retry automatically.")
    elif isinstance(error, ProviderUnavailable):
        receipt.update(status="FAILED", failure_code="PROVIDER_CONTROLLED_FAILURE",
                       error="Provider did not return a valid governed report; no automatic retry.")
    elif stage == "REPORT_VALIDATION" and isinstance(error, DeskError):
        receipt.update(status="FAILED", failure_code="REPORT_VALIDATION_FAILED",
                       error="Provider response failed controlled validation; no automatic retry.")
    else:
        receipt.update(status="UNKNOWN", failure_code="UNCLASSIFIED_OUTCOME",
                       error="Report outcome could not be proven; do not retry automatically.")
    return receipt


def install_interpreter_desk(app, runs_dir: Path | str, *, provider=None) -> None:
    """Mount isolated advisory endpoints on the existing Lab Flask app."""

    base = Path(runs_dir).resolve()
    if provider is None:
        from pipeline_interpreter.openai_desk_provider import OpenAIResponsesProvider
        provider = OpenAIResponsesProvider.from_environment()

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
                        "model_id": getattr(provider, "model_id", "UNCONFIGURED")})

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
                content = _validate_report(raw, set(digest["evidence_refs"]), digest["evidence_cutoff_utc"])
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
                    failure = _report_failure(root.name, choice.ticker, report_id, stage, exc)
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
