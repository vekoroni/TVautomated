"""Read-only source preparation for LAB-004, at publication rather than GET.

Reuse the existing accepted-handoff verifier and allowlisted evidence merge.
Keep separate source dates and missing context. No providers, new decisions,
money-flow inference, ticker-only event matching or full stage-file joins.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime
import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from domain.dynamic_options_projection import merge_all_opportunities
from domain.macro_advisory_context import GICS_TO_ETF
from contracts.lab_review_display import display_sector


def _text(value):
    return str(value or "").strip()


def _contract(row):
    return _text(row.get("selected_contract_symbol") or row.get("contract_symbol")).upper().removeprefix("O:")


def _key(row):
    return tuple(_text(row.get(f)).upper() for f in ("run_id", "ticker", "thesis_id", "trade_idea_id"))


def overlay_verified_rows(full_rows, actionable_rows):
    """Composite identity locates the row; existing merge verifies protected facts.

    Delegating one matched pair preserves the existing merge's semantics while
    supporting several distinct theses for one ticker in the complete book.
    """
    output = [dict(r) for r in full_rows]
    indexes = defaultdict(list)
    for n, row in enumerate(output): indexes[_key(row)].append(n)
    seen = set(); applied = 0; rejected = []
    for overlay in actionable_rows:
        key = _key(overlay); matches = indexes.get(key, [])
        if key in seen or len(matches) != 1 or any(not part for part in key):
            rejected.append({"ticker": overlay.get("ticker"), "reason": "AMBIGUOUS_OR_MISSING_OVERLAY_IDENTITY"})
            continue
        seen.add(key); n = matches[0]
        if _contract(output[n]) != _contract(overlay):
            rejected.append({"ticker": overlay.get("ticker"), "reason": "OVERLAY_CONTRACT_MISMATCH"})
            continue
        left_candidate = output[n].get("trade_lane_candidate_id")
        right_candidate = overlay.get("trade_lane_candidate_id")
        if left_candidate and right_candidate and left_candidate != right_candidate:
            rejected.append({"ticker": overlay.get("ticker"), "reason": "OVERLAY_CANDIDATE_MISMATCH"})
            continue
        merged, receipt = merge_all_opportunities([output[n]], [overlay])
        output[n] = merged[0]
        applied += receipt["actionable_rows_overlaid"]
        rejected.extend(receipt["overlay_exceptions"])
    return output, {"status": "PARTIAL" if rejected else "PASS", "population_preserved": len(output) == len(full_rows),
                    "actionable_rows_overlaid": applied, "actionable_rows_rejected": len(rejected),
                    "overlay_exceptions": rejected}


def _load(path, issues, label):
    if not path.is_file(): return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, dict): raise ValueError("not an object")
        return value
    except (OSError, ValueError) as error:
        issues.append(f"{label}:{type(error).__name__}:{error}")
        return {}


def _watch(root, path, watches):
    if not path.exists():
        # Also watch absence: a later published source invalidates this view.
        watches.append({"path": path.relative_to(root).as_posix(), "exists": False})
        return
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Review input path escapes exact run")
    stat = path.stat()
    watches.append({"path": path.relative_to(root).as_posix(), "exists": True,
                    "bytes": stat.st_size if path.is_file() else None, "mtime_ns": stat.st_mtime_ns,
                    "kind": "directory" if path.is_dir() else "file"})


def _context(root, run_id, issues, watches):
    # An explicit schema adapter selects the run's Morning advisory snapshot;
    # older/EOD runs use their pinned EOD snapshot. Never read dropbox/latest.
    morning = root / "interpreter/interpreter_macro_context.json"
    evening = root / "macro_snapshot.json"
    _watch(root, morning, watches); _watch(root, evening, watches)
    path = morning if morning.is_file() else evening
    packet = _load(path, issues, "MACRO_CONTEXT_INVALID")
    if path == morning and packet.get("schema_version") != "interpreter_macro_context_v1":
        issues.append("MACRO_CONTEXT_SCHEMA_UNSUPPORTED"); packet = {}
    stamp = packet.get("as_of_utc")
    macro = {"state": "AVAILABLE" if packet else "NOT_PUBLISHED", "source": path.relative_to(root).as_posix(),
             "as_of_utc": stamp, "session_date": packet.get("session_date") or packet.get("report_date"),
             "regime_state": packet.get("regime_state"), "context_state": packet.get("macro_context_state"),
             "freshness": packet.get("freshness"), "quality": packet.get("quality"),
             "authority": "ADVISORY_ONLY", "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest() if packet else None}
    rotation = packet.get("sector_rotation") if isinstance(packet.get("sector_rotation"), dict) else {}
    raw_bias = rotation.get("sector_bias_map") if isinstance(rotation.get("sector_bias_map"), dict) else {}
    bias = {}
    for name, value in raw_bias.items():
        canonical = display_sector(name)
        if canonical in bias and bias[canonical] != value:
            issues.append(f"SECTOR_BIAS_ALIAS_CONFLICT:{canonical}")
            bias[canonical] = "CONFLICTING_PUBLISHED_BIASES"
        else: bias[canonical] = value
    breadth_path = root / "diagnostics" / f"market_breadth_diagnostic_{run_id}.json"
    _watch(root, breadth_path, watches)
    diagnostic = _load(breadth_path, issues, "BREADTH_INVALID")
    if diagnostic and (diagnostic.get("run_id") != run_id or diagnostic.get("diagnostic") != "P10_MARKET_BREADTH_READ_ONLY"):
        issues.append("BREADTH_RUN_MISMATCH"); diagnostic = {}
    breadth = diagnostic.get("breadth") or {}
    observations = {}
    for item in [*(breadth.get("leaders") or []), *(breadth.get("laggards") or [])]:
        if isinstance(item, dict) and item.get("name"):
            canonical = display_sector(item["name"])
            observations[canonical.upper()] = {**item, "name": canonical}
    names = list(bias)
    folded = {_text(n).upper() for n in names}
    names.extend(item["name"] for k, item in observations.items() if k not in folded)
    rows = []
    for name in names:
        observed = observations.get(_text(name).upper(), {})
        rows.append({"sector": name, "proxy": observed.get("ticker") or GICS_TO_ETF.get(_text(name).upper()), "bias": bias.get(name),
            "daily_pct": observed.get("daily_pct"), "weekly_pct": observed.get("weekly_pct"),
            "bias_as_of_utc": stamp, "breadth_generated_at_utc": diagnostic.get("generated_at_utc"),
            "breadth_source": diagnostic.get("source_files", {}).get("sectors"),
            "breadth_state": "PUBLISHED_OBSERVATION" if observed else "NOT_PUBLISHED_FOR_SECTOR",
            "money_flow": None, "money_flow_state": "NOT_PUBLISHED"})
    sector = {"state": "AVAILABLE_PARTIAL" if rows else "NOT_PUBLISHED", "authority": "ADVISORY_ONLY",
              "rotation_signal": rotation.get("rotation_signal"), "as_of_utc": stamp,
              "source": macro["source"], "rows": rows, "breadth_status": breadth.get("status"),
              "breadth_scope": "Published P10 leaders/laggards only; absent sector returns not inferred"}
    return {"macro": macro, "sector": sector}


def _canonical_structure_readings(root, run_id, rows, issues, watches, receipt):
    """Carry existing Discovery compression facts, never legacy scores/calculations.

    Current wide book drops these canonical columns. Match the exact governing
    setup and timeframe against this run's Discovery publication, once at write
    time, instead of manufacturing them or reading Discovery during a GET.
    """
    path = root / "discovery" / f"discovery_candidates_ultimate_{run_id}.csv"
    _watch(root, path, watches)
    if not path.is_file(): return
    readings = defaultdict(list)
    old_limit = csv.field_size_limit()
    try:
        csv.field_size_limit(max(old_limit, 64 * 1024 * 1024))
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for source in csv.DictReader(stream):
                readings[_text(source.get("ticker")).upper()].append({k: v for k, v in source.items()
                    if k in {"ticker", "trade_lane_candidate_id", "bar_data_asof"}
                    or (k.startswith("beh__") and "compression_" in k)})
    except (OSError, csv.Error) as error:
        issues.append(f"DISCOVERY_CONTEXT_UNAVAILABLE:{error}"); return
    finally:
        csv.field_size_limit(old_limit)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
    receipt["discovery_context_sha256"] = digest.hexdigest()
    receipt["compression_readings_applied"] = 0
    for row in rows:
        matches = readings.get(_text(row.get("ticker")).upper(), [])
        candidate = _text(row.get("trade_lane_candidate_id"))
        tf = _text(row.get("thesis_event_timeframe"))
        if len(matches) != 1 or not candidate or candidate != _text(matches[0].get("trade_lane_candidate_id")):
            row["compression_projection_state"] = "SETUP_IDENTITY_MISMATCH"; continue
        source = matches[0]; key = f"beh__{tf}_compression_state"
        if not tf or not _text(source.get(key)):
            row["compression_projection_state"] = "CANONICAL_READING_NOT_PUBLISHED"; continue
        row.update(compression_state=source[key], compression_timeframe=tf,
                   compression_source="DISCOVERY_BEH001_CANONICAL", compression_asof=source.get("bar_data_asof"),
                   compression_projection_state="MATCHED_GOVERNING_SETUP_TIMEFRAME")
        for name in ("box_high", "box_low", "episode_start", "location", "contracting_side"):
            row[f"compression_{name}"] = source.get(f"beh__{tf}_compression_{name}") or None
        receipt["compression_readings_applied"] += 1


def prepare_review_publication(book: Mapping[str, Any], run_dir: Path | str, *, handoff_validator=None,
                               validation_receipt: Mapping[str, Any] | None = None):
    root = Path(run_dir).resolve(); run_id = _text(book.get("run_id"))
    if root.name != run_id: raise ValueError("Review run-root identity mismatch")
    output = {**book, "rows": [dict(r) for r in book.get("rows", [])]}
    if book.get("candidate_count") != len(output["rows"]): raise ValueError("Review population mismatch")
    issues = []; watches = []
    context = _context(root, run_id, issues, watches)
    receipt = {"overlay_state": "NOT_PUBLISHED", "issues": issues, "watch_inputs": watches,
               "validation_events_applied": 0, "validation_event_state": "NOT_PUBLISHED"}
    _canonical_structure_readings(root, run_id, output["rows"], issues, watches, receipt)
    handoff_path = root / "interpreter/handoff_manifest.json"
    _watch(root, handoff_path, watches)
    if handoff_path.is_file():
        try:
            if handoff_validator is None:
                from contracts.interpreter_handoff import validate_handoff_manifest
                handoff_validator = validate_handoff_manifest
            handoff = handoff_validator(handoff_path, require_accepted=True)
            if handoff.manifest.get("run_id") != run_id: raise ValueError("HANDOFF_RUN_MISMATCH")
            for artifact in handoff.artifacts.values(): _watch(root, Path(artifact), watches)
            output["rows"], merge = overlay_verified_rows(output["rows"], handoff.book_rows)
            receipt.update(overlay_state="VERIFIED" if merge["status"] == "PASS" else "PARTIAL_REJECTED",
                           handoff_reconciliation=merge, handoff_sha256=hashlib.sha256(handoff_path.read_bytes()).hexdigest())
        except (OSError, ValueError, KeyError) as error:
            receipt["overlay_state"] = "REJECTED"; issues.append(f"HANDOFF_REJECTED:{error}")
    event_dir = root / "morning_validation/validation_events"
    _watch(root, event_dir, watches)
    _watch(root, root / "morning_validation" / f"morning_handoff_summary_{run_id}.json", watches)
    if validation_receipt is not None:
        # Trusted internal caller is the finalizer which has just attached and
        # identity-checked persisted events, then reconciled gated -> Lab rows.
        # Do not reread thousands of immutable files to redo its calculation.
        if (validation_receipt.get("status") != "PASS"
                or validation_receipt.get("authority") != "VALIDATION_ONLY"
                or validation_receipt.get("input_rows") != len(output["rows"])
                or not isinstance(validation_receipt.get("lab_projection_issues"), list)):
            raise ValueError("Invalid upstream validation projection receipt")
        rejected_tickers = {str(item).split(":", 1)[0] for item in validation_receipt["lab_projection_issues"]}
        for row in output["rows"]:
            verified = bool(row.get("validation_event_id")) and _text(row.get("ticker")) not in rejected_tickers
            row["review_validation_state"] = "UPSTREAM_IDENTITY_VERIFIED" if verified else "EVENT_NOT_VERIFIED"
            receipt["validation_events_applied"] += int(verified)
        receipt["validation_unmatched_rows"] = len(output["rows"]) - receipt["validation_events_applied"]
        receipt["validation_event_state"] = "UPSTREAM_IDENTITY_VERIFIED_RECEIPT"
        receipt["issues"].extend(validation_receipt["lab_projection_issues"])
        return output, context, receipt
    events = defaultdict(list)
    for path in sorted(event_dir.glob("*.json")):
        event = _load(path, issues, "VALIDATION_EVENT_INVALID")
        if not event or event.get("invocation_id") != run_id: continue
        key = (_text(event.get("ticker")).upper(), _text(event.get("thesis_id")),
               _text(event.get("selected_contract")).upper().removeprefix("O:"))
        events[key].append(event)
    if events:
        from morning_handoff_finalizer import _project_validation_event
        for row in output["rows"]:
            key = (_text(row.get("ticker")).upper(), _text(row.get("thesis_id")), _contract(row))
            matching = events.get(key)
            if not matching:
                row["review_validation_state"] = "MATCHING_EVENT_NOT_FOUND"
                issues.append(f"{row.get('ticker')}:MATCHING_VALIDATION_EVENT_NOT_FOUND")
                continue
            try:
                event = max(matching, key=lambda e: datetime.fromisoformat(_text(e.get("evidence_cutoff_utc")).replace("Z", "+00:00")))
                _project_validation_event(row, event, run_id=run_id)
                row["review_validation_state"] = "IDENTITY_VERIFIED"
                receipt["validation_events_applied"] += 1
            except (ValueError, TypeError) as error:
                row["review_validation_state"] = "EVENT_REJECTED"; issues.append(f"VALIDATION_EVENT_REJECTED:{row.get('ticker')}:{error}")
        receipt["validation_event_state"] = "VERIFIED_IDENTITY_PROJECTED"
    receipt["validation_unmatched_rows"] = len(output["rows"]) - receipt["validation_events_applied"]
    return output, context, receipt


def republish_saved_review(run_id: str, runs_dir: Path | str, *, book=None):
    """Explicit display publication after run evidence is final; never called by GET.

    Only the review generation/manifest is written. The source book, decision
    artifacts and providers are untouched. EOD can reuse its governed in-memory
    book; an operator repair reads only the explicitly selected saved book.
    """
    from contracts.lab_review_projection import (
        _folder, publish_review_projection, source_file_receipt,
    )
    runs = Path(runs_dir).resolve()
    folder = _folder(runs, run_id)  # validates exact run identity/path
    root = folder.parent.parent
    source = root / 'intelligence_lab' / f'final_opportunity_book_{run_id}.json'
    before = source_file_receipt(source)
    if book is None:
        book = json.loads(source.read_text(encoding='utf-8-sig'))
    if book.get('run_id') != run_id:
        raise ValueError('Saved review run identity mismatch')
    prepared, context, receipt = prepare_review_publication(book, root)
    if source_file_receipt(source) != before:
        raise ValueError('Source book changed during review preparation')
    return publish_review_projection(prepared, runs, context=context,
        source_receipt={**before, **receipt})
