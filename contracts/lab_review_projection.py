"""AVS-SD-LAB-004: indexed, immutable, display-only Lab publication.

No providers, domain decisions, pricing, live database access or legacy loader.
The SQLite file is a generated presentation artifact, not a trading database.
Writer receives already governed rows; it does not manufacture an accepted
handoff. Readers pin a generation and query only home/card/evidence records.
"""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4
import zlib
from contracts.lab_review_display import display_sector, display_policy, valuation_disclosure

SCHEMA = "lab_review_projection_v1"
FAMILIES = ("structure", "option_risk", "context", "morning", "audit")
HOME_FIELDS = tuple("ticker sector sector_etf direction thesis_id trade_lane_candidate_id contract_symbol lab_rank rank_basis rank_group rank_expected_multiple lab_verdict final_action trade_lane trade_lane_setup thesis__readiness thesis__event_status thesis__trigger_age_sessions validation_transition anticipated_move_pct anticipated_sessions_q50 anticipated_value_multiple_q50 anticipated_contract_basis planned_hold_sessions earnings_disclosure".split())
CARD_FIELDS = tuple(dict.fromkeys((*HOME_FIELDS, *"thesis_phase thesis_event thesis_event_state thesis_event_timeframe thesis_event_scope thesis_event_candidate_id thesis_structure_alignment thesis_trigger_level thesis_trigger_candidate_id thesis__readiness_reason thesis__last_event thesis__last_event_date thesis__last_event_level thesis__top_timeframe thesis__conflicting_count thesis__event_id thesis__event_evidence thesis__entry_opportunity_id thesis__trigger_close_date thesis__event_occurred_at thesis__event_confirmed_at thesis__event_failed_at thesis__policy_qualified_at thesis__setup_first_detected_at thesis__source_bar_end_at thesis__data_received_at thesis__data_provider thesis__discovery_read_at thesis__contract_prepared_at thesis__last_revalidated_at thesis__delivered_at thesis_invalidation_setup_id invalidation_price early_warning_invalidation_level early_warning_setup_id anticipated_level_q50 anticipated_level anticipated_level_basis anticipated_structural_level anticipated_structural_definition anticipated_reachable_level anticipated_sessions_q80 anticipated_time_basis anticipated_evidence_status anticipated_evidence_n anticipated_time_fit anticipated_pays_state anticipated_contract_symbol anticipated_valued_at_utc anticipated_value_multiple_q80 anticipated_value_multiple_earnings_stress anticipated_stress_basis anticipated_move_coverage anticipated_breakeven_move_pct anticipated_authority anticipated_version planned_hold_source expiry dte contract_dte contract_bid contract_ask contract_iv contract_delta contract_oi contract_volume selected_quote_timestamp_utc quote_provider_timestamp_utc quote_freshness bar_data_asof live_price live_price_state live_price_age_seconds live_price_source live_price_as_of live_price_error signal_price validation_event_id morning_execution_mode remaining_runway_state conflict_state evening_thesis_bucket earnings_state earnings_date earnings_report_time earnings_date_confirmation earnings_source earnings_sessions_to_event earnings_inside_hold earnings_inside_contract earnings_unknown_reason valuation_model valuation_version valuation_rate_annual valuation_rate_basis valuation_dividend_yield_annual valuation_dividend_basis valuation_cost_basis valuation_entry_cost_usd_per_share scenario_exit_sessions scenario_iv_basis scenario_target_exit_spot scenario_target_return_on_premium scenario_invalidation_exit_spot scenario_invalidation_return_on_premium scenario_stall_return_on_premium scenario_target_earnings_iv_return_on_premium eod_anticipated_value_multiple_q50 eod_anticipated_pays_state eod_scenario_target_return_on_premium eod_anticipated_valued_at_utc direction_edge_state direction_evidence_state compression_state compression_source compression_timeframe vanguard_context_flags".split())))
_VERIFY_LOCK = RLock()
CARD_FIELDS = (*CARD_FIELDS, "review_validation_state", "lab_actionable_overlay_state", "lab_actionable_overlay_reason")


class ReviewRevisionConflict(ValueError):
    pass


class ReviewIntegrityError(ValueError):
    pass


def _safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(f"Unsupported presentation value: {type(value).__name__}")


def _json(value: Any) -> str:
    return json.dumps(_safe(value), ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _token(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip().lower() in {"", "nan", "null"})


def _folder(runs_dir: Path | str, run_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id):
        raise ValueError("Invalid run identity")
    base = Path(runs_dir).resolve()
    folder = (base / run_id / "intelligence_lab" / "review_projection").resolve()
    if not folder.is_relative_to(base):
        raise ValueError("Run path escapes runs directory")
    return folder


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def source_file_receipt(path: Path) -> dict[str, Any]:
    """Streaming lineage receipt, called at publication, never on a GET."""
    stat = path.stat()
    return {"source_book_file": path.name, "source_book_bytes": stat.st_size,
            "source_book_mtime_ns": stat.st_mtime_ns, "source_book_sha256": _digest(path)}


def _spread(row: Mapping[str, Any]) -> tuple[float | None, str]:
    try:
        bid, ask = float(row.get("contract_bid")), float(row.get("contract_ask"))
    except (ValueError, TypeError):
        return None, "QUOTE_NOT_RECORDED"
    if not (math.isfinite(bid) and math.isfinite(ask) and 0 <= bid <= ask and ask > 0):
        return None, "INVALID_QUOTE"
    return (ask - bid) / ((ask + bid) / 2) * 100.0, "AVAILABLE"


def _family(field: str) -> str:
    if field.startswith(("ev3_", "monetisability_", "rr_", "research_ev_")):
        return "audit"
    if field.startswith(("thesis_", "trade_lane_", "beh__", "compression", "crabel", "precor", "ib_", "ms_")):
        return "structure"
    if field.startswith(("contract_", "iv_", "ivp", "hv_", "atm_", "theta", "vega", "valuation_", "scenario_", "anticipated_")):
        return "option_risk"
    if field.startswith(("macro_", "usmi_", "sector", "gex", "gamma_flip", "call_wall", "put_wall", "pcr", "max_pain", "wbs_", "earnings_", "vanguard_context")):
        return "context"
    if field.startswith(("morning_", "validation_", "review_validation_", "live_", "mv_", "remaining_runway", "execution_")):
        return "morning"
    return "audit"


def _atomic_manifest(folder: Path, manifest: Mapping[str, Any]) -> None:
    temp = folder / f"manifest-{uuid4().hex}.tmp"
    try:
        with temp.open("w", encoding="utf-8") as f:
            f.write(_json(manifest))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, folder / "manifest.json")
    finally:
        if temp.exists():
            temp.unlink()  # only this writer's exact temporary file


def publish_review_projection(book: Mapping[str, Any], runs_dir: Path | str, *,
                              context: Mapping[str, Any] | None = None,
                              source_receipt: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Materialise an already governed population without decisions or joins.

    Generations are append-only; the manifest is switched only after validation.
    No previous generation is deleted. Publication failures do not select a
    partially written database. Caller decides how to disclose such failures.
    """
    run_id = _token(book.get("run_id"))
    folder = _folder(runs_dir, run_id)
    rows = book.get("rows")
    if not isinstance(rows, list) or book.get("candidate_count") != len(rows):
        raise ValueError("Governed population count mismatch")
    if any(not isinstance(r, Mapping) or r.get("run_id") not in (None, "", run_id) for r in rows):
        raise ValueError("Cross-run or malformed governed row")
    folder.mkdir(parents=True, exist_ok=True)
    revision = uuid4().hex
    database = folder / f"review-{revision}.sqlite"
    distribution: dict[str, dict[str, Any]] = {}
    identity_counts: Counter[str] = Counter()
    verdict_counts: Counter[str] = Counter()
    with closing(sqlite3.connect(database)) as conn:
        conn.executescript("""
          CREATE TABLE rows(row_key TEXT PRIMARY KEY, ordinal INTEGER UNIQUE NOT NULL,
            sector TEXT NOT NULL, home_json TEXT NOT NULL, card_json TEXT NOT NULL);
          CREATE INDEX sector_page ON rows(sector, ordinal);
          CREATE TABLE evidence(row_key TEXT NOT NULL, family TEXT NOT NULL,
            payload_json TEXT NOT NULL, PRIMARY KEY(row_key, family));
          CREATE TABLE publication(schema TEXT, run_id TEXT, revision TEXT, row_count INTEGER);
        """)
        for ordinal, source in enumerate(rows):
            row = _safe(source)
            identity = [row.get(k) for k in ("ticker", "thesis_id", "trade_lane_candidate_id", "contract_symbol")]
            identity_counts[_json(identity)] += 1
            # Ordinal conserves duplicate source identities; it is not a thesis ID.
            key = hashlib.sha256(_json([run_id, identity, ordinal]).encode("utf-8")).hexdigest()
            fields = {f: row.get(f) for f in CARD_FIELDS}
            home = {f: row.get(f) for f in HOME_FIELDS}
            spread, state = _spread(row)
            home.update(row_key=key, spread_pct_mid=spread, spread_state=state)
            sector = display_sector(row.get("sector"))
            home["sector"] = _token(row.get("sector")) or "UNKNOWN"
            home["display_sector"] = sector
            home["valuation_disclosure"] = valuation_disclosure(row)
            # Field names live once in the versioned schema. A single-card GET
            # expands this typed vector; missing values/reasons remain explicit.
            card = {"values": [fields[f] for f in CARD_FIELDS],
                    "missing_fields": [i for i, f in enumerate(CARD_FIELDS) if _missing(fields[f])],
                    "identity_state": "THESIS_ID_MISSING" if _missing(row.get("thesis_id")) else "SOURCE_IDENTITY_PRESENT",
                    "source_row_ordinal": ordinal, "spread_pct_mid": spread, "spread_state": state,
                    "authority": "DISPLAY_ONLY", "evidence_families": list(FAMILIES),
                    "display_sector": sector, "valuation_disclosure": home["valuation_disclosure"]}
            conn.execute("INSERT INTO rows VALUES(?,?,?,?,?)", (key, ordinal, sector, _json(home), _json(card)))
            families: dict[str, dict[str, Any]] = {f: {} for f in FAMILIES}
            for field, value in row.items():
                if field == "source_payload_json":
                    continue  # raw source remains in the existing full artifact
                families[_family(field)][field] = value
            for family, values in families.items():
                conn.execute("INSERT INTO evidence VALUES(?,?,?)", (key, family, zlib.compress(_json({
                    "fields": values, "source_row_ordinal": ordinal,
                    "full_source_reference": f"intelligence_lab/final_opportunity_book_{run_id}.json",
                }).encode("utf-8"), level=1)))
            summary = distribution.setdefault(sector, {"sector": sector, "total_theses": 0,
                "bull_theses": 0, "bear_theses": 0, "unresolved_theses": 0, "selected_expressions": 0})
            summary["total_theses"] += 1
            side = _token(row.get("direction")).upper()
            if side in {"BULL", "BULLISH", "CALL"}: summary["bull_theses"] += 1
            elif side in {"BEAR", "BEARISH", "PUT"}: summary["bear_theses"] += 1
            else: summary["unresolved_theses"] += 1
            summary["selected_expressions"] += int(not _missing(row.get("contract_symbol")))
            verdict_counts[_token(row.get("lab_verdict")) or "NOT_RECORDED"] += 1
        conn.execute("INSERT INTO publication VALUES(?,?,?,?)", (SCHEMA, run_id, revision, len(rows)))
        conn.commit()
        if conn.execute("SELECT COUNT(*) FROM rows").fetchone()[0] != len(rows):
            raise ReviewIntegrityError("Projection population mismatch")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ReviewIntegrityError("Projection index integrity failed")
    manifest = {"schema": SCHEMA, "run_id": run_id, "revision": revision,
        "publication_state": "COMPLETE", "authority": "DISPLAY_ONLY", "row_count": len(rows),
        "card_fields": list(CARD_FIELDS), "display_policy_version": display_policy()["version"],
        "evidence_storage": "ZLIB_JSON_LOSSLESS_V1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "source_created_at_utc": book.get("created_at_utc"),
        "source_schema": book.get("lab_schema_version"), "source_receipt": _safe(source_receipt or {}),
        "overlay_state": (source_receipt or {}).get("overlay_state", "SOURCE_BOOK_ONLY_NO_ADDITIONAL_OVERLAY"), "database_file": database.name,
        "database_bytes": database.stat().st_size, "database_sha256": _digest(database),
        "duplicate_source_identities": sum(n - 1 for n in identity_counts.values()),
        "sector_distribution": list(distribution.values()), "verdict_counts": dict(verdict_counts),
        "macro_context": _safe((context or {}).get("macro", {"state": "NOT_PUBLISHED"})),
        "sector_context": _safe((context or {}).get("sector", {"state": "NOT_PUBLISHED"})),
        "reconciliation": _safe(book.get("reconciliation", {})),
    }
    # Derived, saved-input research is built at publication, never on a page request.
    # It has separate display authority and cannot alter the governed rows above.
    from contracts.lab_convexity_watchlist import publish_convexity
    manifest["convexity_watchlist"] = publish_convexity(manifest, database, rows)
    _atomic_manifest(folder, manifest)
    return manifest


@lru_cache(maxsize=32)
def _verified_hash(path: str, size: int, mtime: int, ctime: int, digest: str,
                   run_id: str, revision: str, row_count: int) -> bool:
    # Stat participates in the cache key; a changed artifact is verified again.
    if _digest(Path(path)) != digest:
        return False
    with closing(_connect(Path(path))) as conn:
        metadata = conn.execute("SELECT schema,run_id,revision,row_count FROM publication").fetchall()
        actual_count = conn.execute("SELECT COUNT(*) FROM rows").fetchone()[0]
    return metadata == [(SCHEMA, run_id, revision, row_count)] and actual_count == row_count


def _read_manifest(runs_dir: Path | str, run_id: str, revision: str | None = None) -> tuple[dict, Path]:
    folder = _folder(runs_dir, run_id)
    try:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ReviewIntegrityError("Malformed projection manifest") from error
    if (not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA
            or manifest.get("run_id") != run_id or manifest.get("publication_state") != "COMPLETE"
            or not re.fullmatch(r"[0-9a-f]{32}", str(manifest.get("revision", "")))
            or manifest.get("card_fields") != list(CARD_FIELDS)
            or manifest.get("evidence_storage") != "ZLIB_JSON_LOSSLESS_V1"):
        raise ReviewIntegrityError("Projection manifest identity mismatch")
    if revision and manifest["revision"] != revision:
        raise ReviewRevisionConflict("Review publication changed; reload a coherent revision")
    source = manifest.get("source_receipt", {})
    run_root = folder.parent.parent
    for watched in source.get("watch_inputs", []):
        candidate = (run_root / watched["path"]).resolve()
        if not candidate.is_relative_to(run_root.resolve()):
            raise ReviewIntegrityError("Watched source escapes exact run")
        exists = candidate.exists()
        if exists != watched["exists"]:
            raise ReviewRevisionConflict("Review evidence sources changed; publication required")
        if exists:
            current = candidate.stat()
            if (current.st_mtime_ns != watched["mtime_ns"]
                    or (watched.get("kind") == "file" and current.st_size != watched["bytes"])):
                raise ReviewRevisionConflict("Review evidence sources changed; publication required")
    if source.get("source_book_file"):
        if source["source_book_file"] != f"final_opportunity_book_{run_id}.json":
            raise ReviewIntegrityError("Source-book identity mismatch")
        original = folder.parent / source["source_book_file"]
        stat_source = original.stat()
        if (stat_source.st_size != source.get("source_book_bytes")
                or stat_source.st_mtime_ns != source.get("source_book_mtime_ns")):
            raise ReviewRevisionConflict("Source book changed after projection; projection requires publication")
    expected = f"review-{manifest['revision']}.sqlite"
    if manifest.get("database_file") != expected:
        raise ReviewIntegrityError("Projection artifact identity mismatch")
    path = (folder / expected).resolve()
    if not path.is_relative_to(folder):
        raise ReviewIntegrityError("Projection artifact escapes run")
    stat = path.stat()
    if stat.st_size != manifest.get("database_bytes"):
        raise ReviewIntegrityError("Projection artifact size mismatch")
    with _VERIFY_LOCK:
        if not _verified_hash(str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns,
                              manifest.get("database_sha256", ""), run_id,
                              manifest["revision"], manifest.get("row_count")):
            raise ReviewIntegrityError("Projection artifact digest mismatch")
    return manifest, path


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    return conn


def read_review_summary(runs_dir: Path | str, run_id: str) -> dict:
    manifest, _ = _read_manifest(runs_dir, run_id)
    return manifest


def _published_rank(value):
    try:
        rank = float(value)
        return rank if math.isfinite(rank) else 1e99
    except (TypeError, ValueError):
        return 1e99


def read_review_rows(runs_dir: Path | str, run_id: str, *, revision: str | None = None,
                     sector: str | None = None, page: int = 1, page_size: int = 50,
                     tickers: list[str] | None = None) -> dict:
    if not (isinstance(page, int) and page >= 1 and isinstance(page_size, int) and 1 <= page_size <= 200):
        raise ValueError("Invalid page or page size")
    ticker_filter = None
    if tickers is not None:
        if not isinstance(tickers, list) or not tickers or any(not isinstance(t, str) for t in tickers):
            raise ValueError("Provide between one and five tickers")
        ticker_filter = list(dict.fromkeys(t.strip().upper() for t in tickers))
        if len(ticker_filter) > 5 or any(not re.fullmatch(r"[A-Z0-9.^/_-]{1,32}", t) for t in ticker_filter):
            raise ValueError("Provide up to five valid ticker symbols")
    manifest, path = _read_manifest(runs_dir, run_id, revision)
    conditions, args = [], []
    if sector is not None:
        conditions.append("sector=?")
        args.append(display_sector(sector))
    if ticker_filter is not None:
        conditions.append("UPPER(json_extract(home_json, '$.ticker')) IN (" +
                          ",".join("?" for _ in ticker_filter) + ")")
        args.extend(ticker_filter)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    with closing(_connect(path)) as conn:
        conn.create_function("published_rank", 1, _published_rank, deterministic=True)
        count = conn.execute("SELECT COUNT(*) FROM rows" + where, args).fetchone()[0]
        result = conn.execute("SELECT home_json, card_json FROM (SELECT home_json, card_json, ordinal, "
            "CASE UPPER(TRIM(json_extract(home_json, '$.lab_verdict'))) "
            "WHEN 'GO' THEN 0 WHEN 'GO_LIMIT' THEN 1 WHEN 'GO_LMT' THEN 1 "
            "WHEN 'GO_WITH_LIMIT' THEN 1 ELSE 2 END AS review_bucket FROM rows" + where + ") "
            "ORDER BY review_bucket, CASE WHEN review_bucket < 2 THEN "
            "published_rank(json_extract(home_json, '$.lab_rank')) ELSE ordinal END, ordinal LIMIT ? OFFSET ?",
                              [*args, page_size, (page - 1) * page_size]).fetchall()
    rows = []
    for home_json, card_json in result:
        home, card = json.loads(home_json), json.loads(card_json)
        values = card.get("values", [])
        if len(values) != len(CARD_FIELDS):
            raise ReviewIntegrityError("Card schema mismatch")
        # Read only this page's indexed card vectors. Existing frozen publications
        # remain immutable; no full-book load, republishing or quote acquisition.
        for field in ("contract_ask", "selected_quote_timestamp_utc", "quote_provider_timestamp_utc",
                      "live_price", "live_price_as_of", "live_price_state", "signal_price", "bar_data_asof"):
            home[field] = values[CARD_FIELDS.index(field)]
        rows.append(home)
    return {"run_id": run_id, "revision": manifest["revision"], "rows": rows,
            "total_rows": manifest["row_count"], "filtered_rows": count, "page": page,
            "page_size": page_size, "ticker_filter": ticker_filter,
            "order_basis": "GO_THEN_LIMIT_PUBLISHED_RANK", "authority": "DISPLAY_ONLY"}


def _record(runs_dir, run_id, row_key, revision, family=None):
    if not re.fullmatch(r"[0-9a-f]{64}", row_key):
        raise ValueError("Invalid row key")
    if family is not None and family not in FAMILIES:
        raise ValueError("Unsupported evidence family")
    manifest, path = _read_manifest(runs_dir, run_id, revision)
    with closing(_connect(path)) as conn:
        result = (conn.execute("SELECT payload_json FROM evidence WHERE row_key=? AND family=?", (row_key, family))
                  if family else conn.execute("SELECT card_json FROM rows WHERE row_key=?", (row_key,))).fetchone()
    if result is None:
        raise FileNotFoundError("Review row unavailable")
    try:
        record = json.loads(zlib.decompress(result[0]).decode("utf-8") if family else result[0])
    except (zlib.error, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReviewIntegrityError("Indexed record could not be decoded") from error
    if family is None:
        values, missing = record.pop("values"), record.pop("missing_fields")
        if len(values) != len(CARD_FIELDS) or any(type(i) is not int or not 0 <= i < len(CARD_FIELDS) for i in missing):
            raise ReviewIntegrityError("Card schema mismatch")
        record["fields"] = dict(zip(CARD_FIELDS, values))
        record["field_states"] = {CARD_FIELDS[i]: "NOT_RECORDED" for i in missing}
    return {**record, "run_id": run_id, "revision": manifest["revision"],
            "row_key": row_key, "authority": "DISPLAY_ONLY"}


def read_review_card(runs_dir, run_id, row_key, revision=None):
    return _record(runs_dir, run_id, row_key, revision)


def read_review_evidence(runs_dir, run_id, row_key, family, revision=None):
    return _record(runs_dir, run_id, row_key, revision, family)


def register_review_routes(app, runs_dir):
    """Additive routes: never call _load_run or launch a background build."""
    from flask import jsonify, request

    def answer(function, *args, **kwargs):
        try:
            root = runs_dir() if callable(runs_dir) else runs_dir
            payload = function(root, *args, **kwargs)
            response = jsonify(payload)
            response.headers["Cache-Control"] = "no-store"
            return response
        except FileNotFoundError:
            return jsonify(state="PROJECTION_UNAVAILABLE", reason="Projection or indexed row not published"), 404
        except ReviewRevisionConflict as error:
            return jsonify(state="REVISION_CONFLICT", reason=str(error)), 409
        except (ReviewIntegrityError, sqlite3.DatabaseError):
            return jsonify(state="PROJECTION_INTEGRITY_FAILED", reason="Published review artifact failed verification"), 409
        except (ValueError, TypeError) as error:
            return jsonify(state="INVALID_REQUEST", reason=str(error)), 400
        except OSError:
            return jsonify(state="PROJECTION_READ_FAILED", reason="Published review artifact could not be read"), 503

    @app.get("/api/lab/<run_id>/summary", endpoint="lab_review_summary")
    def summary(run_id):
        return answer(read_review_summary, run_id)

    @app.get("/api/lab/<run_id>/convexity", endpoint="lab_review_convexity")
    def convexity(run_id):
        from contracts.lab_convexity_watchlist import read_convexity
        return answer(read_convexity, run_id, request.args.get("revision"))

    @app.get("/api/lab/<run_id>/rows", endpoint="lab_review_rows")
    def rows(run_id):
        try:
            page, size = int(request.args.get("page", 1)), int(request.args.get("page_size", 50))
        except ValueError:
            return jsonify(state="INVALID_REQUEST", reason="Page parameters must be integers"), 400
        return answer(read_review_rows, run_id, revision=request.args.get("revision"),
                      sector=request.args.get("sector"), page=page, page_size=size,
                      tickers=request.args.get("tickers").split(",") if "tickers" in request.args else None)

    @app.get("/api/lab/<run_id>/rows/<row_key>", endpoint="lab_review_card")
    def card(run_id, row_key):
        return answer(read_review_card, run_id, row_key, request.args.get("revision"))

    @app.get("/api/lab/<run_id>/rows/<row_key>/evidence/<family>", endpoint="lab_review_evidence")
    def evidence(run_id, row_key, family):
        return answer(read_review_evidence, run_id, row_key, family, request.args.get("revision"))
