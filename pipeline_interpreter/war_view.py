"""Optional, local WAR view over an already-saved Interpreter assessment.

This is a read-only evidence projection, not a second model, trade selector,
Morning Gate, or broker client. Generation writes only its own versioned view;
reopening it reads persisted JSON and makes no provider requests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from urllib.parse import urlsplit

from flask import Response, jsonify, request

from domain.exact_contract_quote_join import (
    join_exact_contract_quote, load_exact_contract_quote_candidate_from_json,
)


SCHEMA_VERSION = "interpreter_war_view_v1"
_RUN = re.compile(r"^\d{8}_\d{6}$")
_TICKER = re.compile(r"^[A-Z0-9.^-]{1,24}$")
_REPORT = re.compile(r"^[0-9a-f]{64}$")


class WarViewError(ValueError):
    pass


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise WarViewError("evidence timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _read(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise WarViewError(f"expected JSON object: {path.name}")
    return value, sha256(raw).hexdigest()


def _identities(run_id: str, ticker: str, report_id: str) -> None:
    if not (_RUN.fullmatch(run_id) and _TICKER.fullmatch(ticker)
            and _REPORT.fullmatch(report_id)):
        raise WarViewError("invalid saved-report identity")


def _quote_join(repo_root: Path, run_id: str, ticker: str, symbol: str,
                generated: datetime) -> dict[str, Any]:
    folder = (repo_root / "data" / "canonical" / "market_observations"
              / "exact_option_quote" / f"{run_id[:4]}-{run_id[4:6]}-{run_id[6:8]}" / ticker)
    candidates = []
    if folder.is_dir():
        for path in sorted(folder.glob("*.json")):
            value, digest = _read(path)
            candidates.append(load_exact_contract_quote_candidate_from_json(
                value, source_path=str(path), source_hash=digest))
    return join_exact_contract_quote(
        requested_occ_symbol=symbol, requested_run_id=run_id,
        requested_ticker=ticker, candidates=candidates,
        report_generation_time_utc=generated,
    ).to_dict()


def build_war_view(run_dir: Path, repo_root: Path, ticker: str, report_id: str,
                   *, generated_at_utc: str | None = None) -> dict[str, Any]:
    """Project one stored Interpreter report without network or model calls."""
    run_id = run_dir.name
    _identities(run_id, ticker, report_id)
    report_path = run_dir / "interpreter" / "interactive_desk" / ticker / f"{report_id}.json"
    report, report_hash = _read(report_path)
    if (report.get("status") != "COMPLETE" or report.get("run_id") != run_id
            or report.get("ticker") != ticker or report.get("report_id") != report_id
            or report.get("authority") != "ADVISORY_ONLY"):
        raise WarViewError("saved Interpreter report identity or authority mismatch")
    generated = (_instant(generated_at_utc) if generated_at_utc
                 else datetime.now(timezone.utc))
    if generated < _instant(report.get("provider_retrieved_at_utc") or ""):
        raise WarViewError("WAR generation precedes the saved Interpreter report")

    digest = report.get("evidence_digest") or {}
    if not isinstance(digest, dict):
        raise WarViewError("saved evidence digest is invalid")
    cutoff = digest.get("evidence_cutoff_utc")
    if not cutoff or _instant(cutoff) > generated:
        raise WarViewError("accepted evidence cutoff is missing or after generation")
    eod = digest.get("eod_fields") or {}
    morning = digest.get("morning_evidence") or {}
    if not isinstance(eod, dict) or not isinstance(morning, dict):
        raise WarViewError("saved Evening or Morning evidence is invalid")

    sources: list[dict[str, Any]] = [{
        "name": "SAVED_INTERPRETER", "path": str(report_path),
        "sha256": report_hash, "as_of_utc": report.get("provider_retrieved_at_utc"),
    }]
    gaps: list[str] = list(report.get("unresolved") or [])
    symbol = str(report.get("selected_contract_symbol") or "")
    quote: dict[str, Any] | None = None
    if symbol:
        quote = _quote_join(repo_root, run_id, ticker, symbol, generated)
        if quote.get("matched_source_path"):
            sources.append({
                "name": "EXACT_OPTION_QUOTE", "path": quote["matched_source_path"],
                "sha256": quote["matched_source_hash"],
                "as_of_utc": quote["provider_observed_at_utc"],
            })
        if quote["identity_state"] != "MATCHED":
            gaps.append(f"Exact selected-contract quote: {quote['identity_state']}")
        elif quote["quote_freshness"] != "FRESH":
            gaps.append(f"Exact selected-contract quote: {quote['quote_freshness']} at report generation")
    else:
        gaps.append("No exact selected contract in saved Interpreter report")

    macro_path = run_dir / "interpreter" / "interpreter_macro_context.json"
    macro_summary: dict[str, Any] = {"state": "NOT_AVAILABLE"}
    if macro_path.is_file():
        macro, macro_hash = _read(macro_path)
        macro_asof = macro.get("as_of_utc")
        if macro_asof and _instant(macro_asof) <= generated:
            macro_summary = {
                "state": "AVAILABLE", "as_of_utc": macro_asof,
                "freshness_at_capture": macro.get("freshness"),
                "age_hours_at_generation": round(
                    (generated - _instant(macro_asof)).total_seconds() / 3600, 2),
                "quality": macro.get("quality"),
                "conflicts": macro.get("conflicts") or [],
                "regime_state": macro.get("regime_state"),
                "sector_rotation": macro.get("sector_rotation"),
            }
            sources.append({"name": "RUN_BOUND_MACRO", "path": str(macro_path),
                            "sha256": macro_hash, "as_of_utc": macro_asof})
            if macro_summary["conflicts"]:
                gaps.append("Run-bound macro packet has unresolved conflicts")
        else:
            gaps.append("Run-bound macro as-of time unavailable or future-dated")
    else:
        gaps.append("Run-bound macro context unavailable")
    if not report.get("external_events"):
        gaps.append("No sourced company/news event in saved Interpreter report")
    gaps.append("Economic Event Engine payload is not bound to this saved run evidence")
    if digest.get("unavailable_depth_or_prints"):
        gaps.append("Participant identity cannot be inferred without depth or trade prints")
    gaps.append("Sector-to-ticker money flow not independently measured by this view")

    return {
        "schema_version": SCHEMA_VERSION, "authority": "ADVISORY_ONLY",
        "run_id": run_id, "ticker": ticker, "interpreter_report_id": report_id,
        "generated_at_utc": generated.isoformat().replace("+00:00", "Z"),
        "accepted_evidence_cutoff_utc": cutoff,
        "eod_manifest_sha256": digest.get("eod_manifest_sha256"),
        "selected_contract_symbol": symbol or None,
        "evening_thesis": eod, "morning_update": morning,
        "macro_context": macro_summary, "exact_option_quote": quote,
        "interpreter_assessment": {
            "executive_summary": report.get("executive_summary"),
            "sections": report.get("sections") or [],
            "evidence_chain_review": report.get("evidence_chain_review"),
            "counter_case": report.get("counter_case"),
            "external_events": report.get("external_events") or [],
        },
        "coverage_gaps": list(dict.fromkeys(str(item) for item in gaps)),
        "source_references": sources,
        "judgment": "HUMAN_REVIEW_ONLY",
    }


def render_war_view_html(payload: dict[str, Any]) -> str:
    """Render only persisted WAR JSON; no live data access."""
    def value(item: Any) -> str:
        return escape(json.dumps(item, ensure_ascii=False, indent=2, default=str))

    assessment = payload.get("interpreter_assessment") or {}
    quote = payload.get("exact_option_quote") or {}

    parts = ["<!doctype html><html><head><meta charset='utf-8'>",
             "<title>AVSHUNTER WAR assessment</title>",
             "<style>body{font:16px system-ui;max-width:1000px;margin:30px auto;"
             "background:#101820;color:#eee;line-height:1.5}pre{white-space:pre-wrap;"
             "background:#1b2932;padding:14px;border-radius:6px}h2{color:#85d7dc}"
             ".warn{color:#ffcf78}</style></head><body>",
             f"<h1>{escape(str(payload['ticker']))} · Pre-trade WAR assessment</h1>",
             "<p>Advisory only — human review; no trade or capital authority.</p>",
             f"<p>Run {escape(str(payload['run_id']))} · Generated "
             f"{escape(str(payload['generated_at_utc']))} · Accepted evidence cutoff "
             f"{escape(str(payload['accepted_evidence_cutoff_utc']))}</p>",
             "<h2>Coverage and contradictions</h2><ul class='warn'>"]
    parts.extend(f"<li>{escape(str(gap))}</li>" for gap in payload["coverage_gaps"])
    parts.extend([
        "</ul><h2>Interpreter synthesis</h2>",
        f"<p>{escape(str(assessment.get('executive_summary') or 'Not available'))}</p>",
    ])
    for section in assessment.get("sections") or []:
        parts.append(f"<h3>{escape(str(section.get('key') or 'Evidence'))} · "
                     f"{escape(str(section.get('evidence_class') or 'UNKNOWN'))}</h3>"
                     f"<p>{escape(str(section.get('text') or 'Not available'))}</p>")
    parts.append(f"<h2>Strongest counter-case</h2><pre>{value(assessment.get('counter_case'))}</pre>")
    parts.append("<h2>Exact selected-contract quote</h2>")
    parts.append(f"<p>Contract {escape(str(payload.get('selected_contract_symbol') or 'NONE'))} · "
                 f"Identity {escape(str(quote.get('identity_state') or 'UNAVAILABLE'))} · "
                 f"Freshness {escape(str(quote.get('quote_freshness') or 'UNAVAILABLE'))} · "
                 f"Capture time {escape(str(quote.get('provider_observed_at_utc') or 'UNAVAILABLE'))} · "
                 f"Execution context {escape(str(quote.get('executable_now') or 'NOT_ASSESSABLE'))}</p>")
    parts.append(f"<pre>{value(quote)}</pre>")
    for title, key in (("Frozen Evening thesis", "evening_thesis"),
                       ("Morning update", "morning_update"),
                       ("Run-bound macro", "macro_context"),
                       ("Evidence-chain review", "evidence_chain_review"),
                       ("Source provenance", "source_references")):
        item = assessment.get(key) if key == "evidence_chain_review" else payload.get(key)
        parts.append(f"<details><summary>{title}</summary><pre>{value(item)}</pre></details>")
    return "".join(parts) + "</body></html>"


def _validate_saved_view(payload: dict[str, Any], run_id: str, ticker: str,
                         report_id: str) -> None:
    if (payload.get("schema_version") != SCHEMA_VERSION
            or payload.get("run_id") != run_id or payload.get("ticker") != ticker
            or payload.get("interpreter_report_id") != report_id
            or payload.get("authority") != "ADVISORY_ONLY"
            or not isinstance(payload.get("coverage_gaps"), list)
            or not isinstance(payload.get("source_references"), list)
            or not isinstance(payload.get("interpreter_assessment"), dict)):
        raise WarViewError("saved WAR schema, identity or authority mismatch")


def _write_once(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".war_", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        if not path.exists():
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def install_war_view(app, runs_dir: Path | str, repo_root: Path | str) -> None:
    """Mount a local, explicit action downstream of the saved Interpreter."""
    runs = Path(runs_dir).resolve()
    repo = Path(repo_root).resolve()

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

    @app.route("/api/interpreter/war", methods=["POST"])
    def interpreter_war_generate():
        if not local_request_allowed():
            return jsonify({"error": "local Lab origin required"}), 403
        body = request.get_json(silent=True) or {}
        run_id, ticker, report_id = (str(body.get(k) or "") for k in ("run_id", "ticker", "report_id"))
        try:
            _identities(run_id, ticker, report_id)
        except WarViewError as exc:
            return jsonify({"error": str(exc)}), 400
        report_path = runs / run_id / "interpreter" / "interactive_desk" / ticker / f"{report_id}.json"
        if not report_path.is_file():
            return jsonify({"error": "completed Interpreter report not found"}), 404
        output = runs / run_id / "interpreter" / "war_views" / ticker / f"{report_id}.json"
        try:
            if not output.is_file():
                payload = build_war_view(runs / run_id, repo, ticker, report_id)
                _write_once(output, json.dumps(payload, ensure_ascii=False, allow_nan=False,
                                               indent=2).encode("utf-8"))
            payload, _ = _read(output)
            _validate_saved_view(payload, run_id, ticker, report_id)
        except (OSError, ValueError, TypeError) as exc:
            return jsonify({"error": str(exc)}), 409
        return jsonify({"status": "COMPLETE", "authority": "ADVISORY_ONLY",
                        "run_id": run_id, "ticker": ticker, "report_id": report_id,
                        "html_url": f"/api/interpreter/war/{run_id}/{ticker}/{report_id}.html",
                        "coverage_gaps": payload["coverage_gaps"],
                        "quote_freshness": (payload.get("exact_option_quote") or {}).get("quote_freshness")})

    @app.route("/api/interpreter/war/<run_id>/<ticker>/<report_id>.html")
    def interpreter_war_html(run_id: str, ticker: str, report_id: str):
        if not local_request_allowed():
            return jsonify({"error": "local Lab origin required"}), 403
        try:
            _identities(run_id, ticker, report_id)
        except WarViewError as exc:
            return jsonify({"error": str(exc)}), 400
        output = runs / run_id / "interpreter" / "war_views" / ticker / f"{report_id}.json"
        if not output.is_file():
            return jsonify({"error": "WAR assessment not generated"}), 404
        try:
            payload, _ = _read(output)
            _validate_saved_view(payload, run_id, ticker, report_id)
            response = Response(render_war_view_html(payload), mimetype="text/html")
            response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"
            return response
        except (OSError, ValueError, TypeError) as exc:
            return jsonify({"error": str(exc)}), 409


__all__ = ["SCHEMA_VERSION", "WarViewError", "build_war_view",
           "render_war_view_html", "install_war_view"]
