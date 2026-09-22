"""Domain rules for a coherent, advisory-only macro evidence package.

This module owns meaning and invariants.  It does not call providers, mutate
market data, or decide trades.  Infrastructure code may persist the immutable
manifest, while the macro builder may use the normalised prompt context.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Mapping


MACRO_INPUT_CONTRACT_VERSION = "macro_input_manifest_v2"
MACRO_PROMPT_CONTEXT_VERSION = "macro_prompt_context_v1"
MACRO_AUTHORITY = "ADVISORY_ONLY"
REQUIRED_CAPTURE_COHORT_MAX_SECONDS = 15 * 60


class MacroInputContractError(ValueError):
    """Raised when published evidence violates a macro-domain invariant."""


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False, default=str,
    ).encode("utf-8")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _csv_records(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        return [dict(row) for row in csv.DictReader(io.StringIO(value))]
    except (csv.Error, UnicodeError):
        return []


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    return str(value).strip().upper() not in {"", "NAN", "NONE", "NULL", "N/A", "MISSING"}


def _safe_float(value: Any) -> float | None:
    if not _present(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _observation_dates(value: Any) -> list[str]:
    found: set[str] = set()
    if isinstance(value, str):
        for row in _csv_records(value):
            for key in ("Date", "date", "obs_date", "session_date", "As_Of", "as_of"):
                parsed = _parse_date(row.get(key))
                if parsed:
                    found.add(parsed.isoformat())
                    break
    elif isinstance(value, Mapping):
        for key in ("session_date", "report_date", "timestamp", "as_of_utc", "as_of"):
            parsed = _parse_date(value.get(key))
            if parsed:
                found.add(parsed.isoformat())
    return sorted(found)


def _capture_batch(path: Path) -> str:
    match = re.search(r"(?<!\d)(\d{8}_\d{6})(?!\d)", path.name)
    return match.group(1) if match else ""


def _capture_batch_time(value: str) -> datetime:
    try:
        # Colab runtime/IP identity is deliberately irrelevant.  The token is
        # interpreted only as a producer-local capture clock for elapsed-time
        # comparison; no timezone claim is made here.
        return datetime.strptime(value, "%Y%m%d_%H%M%S")
    except ValueError as error:
        raise MacroInputContractError(f"invalid macro capture batch: {value}") from error


def _validate_required_capture_coherence(
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate one scheduled capture cohort without conflating producers.

    Required files may be emitted by separate Colab runtimes, with unrelated
    runtime identifiers and IP addresses.  Those attributes are not evidence
    of market-time coherence.  Every producer-local capture timestamp must
    instead fall inside one bounded scheduled-capture window.  Original file
    identities and hashes remain immutable and visible in the manifest.
    """

    required = [entry for entry in entries if entry.get("required")]
    batched = [entry for entry in required if entry.get("capture_time") or entry.get("capture_batch")]
    unbatched = sorted(
        str(entry.get("key") or "")
        for entry in required
        if not (entry.get("capture_time") or entry.get("capture_batch"))
    )
    if not batched:
        return {
            "status": "NO_BATCH_IDENTITIES",
            "max_span_seconds": REQUIRED_CAPTURE_COHORT_MAX_SECONDS,
            "span_seconds": None,
            "earliest_batch": "",
            "latest_batch": "",
            "required_batches": {},
            "unbatched_required_keys": unbatched,
            "coherence_basis": "FILENAME_CAPTURE_TIME_WINDOW",
            "runtime_identity_policy": "IGNORED_NON_EVIDENTIARY",
        }

    captured = [
        (_capture_batch_time(str(entry.get("capture_time") or entry["capture_batch"])), entry)
        for entry in batched
    ]
    earliest = min(captured, key=lambda item: item[0])
    latest = max(captured, key=lambda item: item[0])
    span_seconds = int((latest[0] - earliest[0]).total_seconds())
    if span_seconds > REQUIRED_CAPTURE_COHORT_MAX_SECONDS:
        raise MacroInputContractError(
            "required macro inputs exceed capture cohort window: "
            f"{earliest[1].get('capture_time') or earliest[1]['capture_batch']}.."
            f"{latest[1].get('capture_time') or latest[1]['capture_batch']} "
            f"span={span_seconds}s limit={REQUIRED_CAPTURE_COHORT_MAX_SECONDS}s"
        )
    distinct_batches = sorted(
        {str(entry.get("capture_time") or entry["capture_batch"]) for entry in batched}
    )
    return {
        "status": "COHERENT_SINGLE_CAPTURE" if len(distinct_batches) == 1 else "COHERENT_MULTI_RUNTIME",
        "max_span_seconds": REQUIRED_CAPTURE_COHORT_MAX_SECONDS,
        "span_seconds": span_seconds,
        "earliest_batch": str(earliest[1].get("capture_time") or earliest[1]["capture_batch"]),
        "latest_batch": str(latest[1].get("capture_time") or latest[1]["capture_batch"]),
        "required_batches": {
            str(entry.get("key") or ""): str(entry.get("capture_time") or entry.get("capture_batch") or "")
            for entry in required
        },
        "unbatched_required_keys": unbatched,
        "capture_dates": sorted({moment.date().isoformat() for moment, _ in captured}),
        "coherence_basis": "FILENAME_CAPTURE_TIME_WINDOW",
        "runtime_identity_policy": "IGNORED_NON_EVIDENTIARY",
    }


def _validate_gex(
    paths: Mapping[str, str], data: Mapping[str, Any],
) -> dict[str, Any]:
    relevant = {"gex_proxy_csv", "gex_by_strike_csv", "gex_manifest_json"}
    present = relevant.intersection(paths)
    if not present:
        return {"status": "SOURCE_NOT_PUBLISHED", "authority": MACRO_AUTHORITY}
    manifest = data.get("gex_manifest_json")
    if not isinstance(manifest, Mapping):
        raise MacroInputContractError("GEX manifest is not a JSON object")
    publication_status = str(manifest.get("status") or "").upper()
    if publication_status != "COMPLETE":
        # A failed collector is evidence of an unavailable *advisory* domain,
        # not a reason to suppress otherwise valid macro inputs.  Only an
        # explicit per-ticker failure receipt qualifies; an absent/ambiguous
        # status or a changed component still fails closed.
        ticker_status = manifest.get("ticker_status")
        if not isinstance(ticker_status, Mapping) or not ticker_status:
            raise MacroInputContractError("GEX manifest status is not COMPLETE")
        states = {str(value).upper() for value in ticker_status.values()}
        if not states.issubset({"OK", "MISSING", "FAILED", "ERROR", "NO_DATA", "UNAVAILABLE"}) or states == {"OK"}:
            raise MacroInputContractError("GEX failure receipt has ambiguous ticker status")
        outputs = manifest.get("outputs")
        if not isinstance(outputs, Mapping):
            raise MacroInputContractError("GEX failure receipt lacks output hashes")
        for key, filename in (
            ("gex_proxy_csv", "avshunter_gex_proxy.csv"),
            ("gex_by_strike_csv", "avshunter_gex_by_strike.csv"),
        ):
            receipt = outputs.get(filename)
            if key not in present:
                if receipt is not None:
                    raise MacroInputContractError(f"GEX {key} declared but missing")
                continue
            path = Path(paths[key])
            expected = receipt.get("sha256") if isinstance(receipt, Mapping) else None
            if not expected or _sha256_path(path) != str(expected).lower():
                raise MacroInputContractError(f"GEX {key} hash does not match failure receipt")
        return {
            "status": "SOURCE_UNAVAILABLE",
            "authority": MACRO_AUTHORITY,
            "publication_status": publication_status or "NOT_COMPLETE",
            "run_id": str(manifest.get("run_id") or ""),
            "run_date": str(manifest.get("run_date") or ""),
            "ticker_status": {str(key): str(value) for key, value in ticker_status.items()},
            "missing_components": sorted(relevant - present),
            "reason": "GEX collector did not publish a complete observation",
        }
    if present != relevant:
        raise MacroInputContractError(
            "GEX publication is incomplete; proxy, by-strike and manifest are one atomic unit"
        )
    proxy_hash = _sha256_path(Path(paths["gex_proxy_csv"]))
    strike_hash = _sha256_path(Path(paths["gex_by_strike_csv"]))
    if proxy_hash != str(manifest.get("proxy_sha256") or "").lower():
        raise MacroInputContractError("GEX proxy hash does not match its manifest")
    if strike_hash != str(manifest.get("by_strike_sha256") or "").lower():
        raise MacroInputContractError("GEX by-strike hash does not match its manifest")
    session = str(manifest.get("session_date") or "")
    proxy_dates = {
        str(row.get("Date") or row.get("session_date") or "")[:10]
        for row in _csv_records(data.get("gex_proxy_csv"))
        if _present(row.get("Date") or row.get("session_date"))
    }
    strike_dates = {
        str(row.get("Date") or row.get("session_date") or "")[:10]
        for row in _csv_records(data.get("gex_by_strike_csv"))
        if _present(row.get("Date") or row.get("session_date"))
    }
    if not session or proxy_dates != {session} or strike_dates != {session}:
        raise MacroInputContractError("GEX component sessions do not match the manifest")
    return {
        "status": "VALIDATED",
        "authority": MACRO_AUTHORITY,
        "session_date": session,
        "run_id": str(manifest.get("run_id") or ""),
        "dataset_ids": list(manifest.get("dataset_ids") or []),
        "proxy_sha256": proxy_hash,
        "by_strike_sha256": strike_hash,
    }


def build_macro_input_manifest(
    files_found_by_key: Mapping[str, str],
    files_missing: list[str],
    *,
    data: Mapping[str, Any],
    required_keys: tuple[str, ...] = ("report_json", "macro_csv", "forward_bias_csv"),
) -> dict[str, Any]:
    """Create a deterministic identity for the exact evidence bytes."""

    required = set(required_keys)
    effective_data = dict(data)
    for key, raw_path in files_found_by_key.items():
        if key in effective_data:
            continue
        path = Path(raw_path)
        if not path.is_file():
            continue
        try:
            effective_data[key] = (
                json.loads(path.read_text(encoding="utf-8-sig"))
                if path.suffix.lower() == ".json"
                else path.read_text(encoding="utf-8-sig")
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise MacroInputContractError(f"cannot read manifest source {key}: {error}") from error
    entries: list[dict[str, Any]] = []
    for key, raw_path in sorted(files_found_by_key.items()):
        path = Path(raw_path).resolve()
        if not path.is_file():
            raise MacroInputContractError(f"input path no longer exists: {key}:{path}")
        stat = path.stat()
        observations = _observation_dates(effective_data.get(key))
        capture_time = _capture_batch(path)
        entries.append({
            "key": key,
            "filename": path.name,
            "path": str(path),
            "sha256": _sha256_path(path),
            "bytes": stat.st_size,
            "modified_utc": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat().replace("+00:00", "Z"),
            "required": key in required,
            # capture_batch is retained for v1 readers; v2 names the actual
            # semantic field explicitly and never treats it as runtime/IP ID.
            "capture_batch": capture_time,
            "capture_time": capture_time,
            "observation_dates": observations,
            "latest_observation": observations[-1] if observations else "",
        })
    capture_coherence = _validate_required_capture_coherence(entries)
    gex_validation = _validate_gex(files_found_by_key, effective_data)
    identity = {
        "contract_version": MACRO_INPUT_CONTRACT_VERSION,
        "authority": MACRO_AUTHORITY,
        "entries": entries,
        "missing": sorted(str(item) for item in files_missing),
        "capture_coherence": capture_coherence,
        "gex_validation": gex_validation,
    }
    digest = hashlib.sha256(_canonical_bytes(identity)).hexdigest()
    return {
        **identity,
        "manifest_sha256": digest,
        "manifest_id": f"MACRO_INPUT:{digest[:20]}",
    }


def validate_manifest_lineage(
    manifest: Mapping[str, Any],
    *,
    allow_changed_keys: tuple[str, ...] = (),
) -> dict[str, Any]:
    errors: list[str] = []
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        return {"valid": False, "errors": ["ENTRIES_INVALID"]}
    identity_keys = ["contract_version", "authority", "entries", "missing"]
    # Keep already-published v1 manifests replayable.  v2 adds the capture
    # coherence decision to the immutable identity rather than rewriting old
    # evidence.
    if "capture_coherence" in manifest:
        identity_keys.append("capture_coherence")
    identity_keys.append("gex_validation")
    identity = {key: manifest.get(key) for key in identity_keys}
    digest = hashlib.sha256(_canonical_bytes(identity)).hexdigest()
    if digest != str(manifest.get("manifest_sha256") or ""):
        errors.append("MANIFEST_SHA256_MISMATCH")
    allowed = set(allow_changed_keys)
    superseded: list[str] = []
    for entry in entries:
        key = str(entry.get("key") or "UNKNOWN")
        path = Path(str(entry.get("path") or ""))
        if not path.is_file():
            errors.append(f"{key}:FILE_MISSING")
            continue
        if _sha256_path(path) != str(entry.get("sha256") or ""):
            if key in allowed:
                superseded.append(key)
            else:
                errors.append(f"{key}:SHA256_MISMATCH")
    return {
        "valid": not errors,
        "errors": errors,
        "superseded_keys": sorted(superseded),
    }


def _inferred_cadence(observation_dates: list[date]) -> str:
    if len(observation_dates) < 2:
        return "UNKNOWN"
    gaps = [
        (right - left).days
        for left, right in zip(observation_dates, observation_dates[1:])
        if right > left
    ]
    if not gaps:
        return "UNKNOWN"
    typical = median(gaps[-12:])
    if typical <= 4:
        return "DAILY"
    if typical <= 12:
        return "WEEKLY"
    if typical <= 45:
        return "MONTHLY"
    return "QUARTERLY_OR_SLOWER"


def latest_fred_observations(text: str) -> dict[str, dict[str, Any]]:
    rows = _csv_records(text)
    if not rows:
        return {}
    date_key = next((key for key in rows[0] if key in {"", "Date", "date"}), "")
    series = [key for key in rows[0] if key != date_key]
    parsed_rows = [(_parse_date(row.get(date_key)), row) for row in rows]
    result: dict[str, dict[str, Any]] = {}
    all_dates = [parsed for parsed, _ in parsed_rows if parsed]
    package_date = max(all_dates) if all_dates else None
    for name in series:
        observations = [
            (observed, row.get(name))
            for observed, row in parsed_rows
            if observed and _present(row.get(name))
        ]
        if not observations:
            result[name] = {
                "value": None, "observation_date": "", "cadence": "UNKNOWN",
                "age_days": None, "status": "SOURCE_NOT_PUBLISHED",
            }
            continue
        observed, value = observations[-1]
        dates = [item[0] for item in observations]
        age = (package_date - observed).days if package_date else None
        status = "OBSERVED"
        if name.upper() == "USSLIND" and age is not None and age > 180:
            status = "STALE_BY_CADENCE"
        result[name] = {
            "value": _safe_float(value) if _safe_float(value) is not None else value,
            "observation_date": observed.isoformat(),
            "cadence": _inferred_cadence(dates),
            "age_days": age,
            "status": status,
        }
    return result


def _regime_model_summary(records: list[dict[str, str]]) -> dict[str, Any]:
    if not records:
        return {"latest": {}, "regime_counts": {}}
    return {
        "latest": records[-1],
        "regime_counts": dict(Counter(str(row.get("Regime") or "UNKNOWN") for row in records)),
        "row_count": len(records),
    }


def _gex_context(data: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    if validation.get("status") != "VALIDATED":
        return dict(validation)
    proxy_rows = _csv_records(data.get("gex_proxy_csv"))
    strike_rows = _csv_records(data.get("gex_by_strike_csv"))
    tickers: dict[str, Any] = {}
    for row in proxy_rows:
        ticker = str(row.get("Ticker") or row.get("ticker") or "").upper()
        if not ticker:
            continue
        candidates = []
        for strike in strike_rows:
            if str(strike.get("Ticker") or strike.get("ticker") or "").upper() != ticker:
                continue
            net = _safe_float(strike.get("net_gex_usd_1pct"))
            strike_value = _safe_float(strike.get("strike"))
            if net is not None and strike_value is not None:
                candidates.append({"strike": strike_value, "net_gex_usd_1pct": net})
        candidates.sort(key=lambda item: abs(item["net_gex_usd_1pct"]), reverse=True)
        tickers[ticker] = {
            "session_date": str(row.get("Date") or "")[:10],
            "as_of": row.get("As_Of") or row.get("Snapshot_UTC") or "",
            "data_mode": row.get("Data_Mode") or row.get("Mode") or "",
            "data_status": row.get("Data_Status") or row.get("Status") or "",
            "net_gex_bn": _safe_float(row.get("Net_GEX_Bn")),
            "regime": row.get("Regime") or "UNKNOWN",
            "gamma_flip": _safe_float(row.get("Gamma_Flip")),
            "call_wall": _safe_float(row.get("Call_Wall")),
            "put_wall": _safe_float(row.get("Put_Wall")),
            "run_id": row.get("Run_Id") or "",
            "dataset_id": row.get("Dataset_Id") or "",
            "top_absolute_strikes": candidates[:10],
        }
    return {**dict(validation), "tickers": tickers}


def _domain_coverage(data: Mapping[str, Any], gex: Mapping[str, Any]) -> dict[str, str]:
    mappings = {
        "rates": ("macro_master_csv", "fred_master_csv", "bonds_csv"),
        "credit": ("macro_master_csv", "bonds_csv"),
        "liquidity": ("liquidity_csv", "fred_master_csv"),
        "volatility": ("vix_engine_csv", "vol_complex_csv"),
        "breadth": ("breadth_csv",),
        "fx": ("fx_csv", "vol_dollar_csv"),
        "commodities": ("metals_csv", "energy_csv", "agriculture_csv"),
        "sectors": ("sectors_csv",),
        "global_risk": ("global_indices_csv",),
    }
    coverage = {
        domain: "OBSERVED" if any(_present(data.get(key)) for key in keys) else "NOT_CONFIGURED"
        for domain, keys in mappings.items()
    }
    coverage["gex"] = "OBSERVED" if gex.get("status") == "VALIDATED" else str(gex.get("status") or "NOT_CONFIGURED")
    coverage["events"] = "OBSERVED" if _present(data.get("event_calendar_json")) else "NOT_CONFIGURED"
    coverage["rates_volatility"] = "OBSERVED" if _present(data.get("move_index_csv")) else "NOT_CONFIGURED"
    coverage["correlation"] = "OBSERVED" if _present(data.get("correlation_csv")) else "NOT_CONFIGURED"
    coverage["dispersion"] = "OBSERVED" if _present(data.get("dispersion_csv")) else "NOT_CONFIGURED"
    return coverage


def build_macro_prompt_context(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Produce complete, schema-aware records; never character-truncate CSV."""

    data = payload.get("data") if isinstance(payload.get("data"), Mapping) else {}
    manifest = payload.get("input_manifest") if isinstance(payload.get("input_manifest"), Mapping) else {}
    gex = _gex_context(data, manifest.get("gex_validation") or {})
    sources: dict[str, Any] = {}
    excluded = {"fred_master_csv", "gex_by_strike_csv", "gex_proxy_csv", "gex_manifest_json", "prior_macro_json", "us_money_index_advisory"}
    for key, value in sorted(data.items()):
        if key in excluded:
            continue
        if isinstance(value, str):
            records = _csv_records(value)
            if key == "regime_model_csv":
                sources[key] = _regime_model_summary(records)
            else:
                sources[key] = {"records": records, "record_count": len(records)}
        elif isinstance(value, Mapping):
            sources[key] = dict(value)
    report = data.get("report_json")
    if isinstance(report, Mapping):
        sources["report_json"] = dict(report)
    context = {
        "contract_version": MACRO_PROMPT_CONTEXT_VERSION,
        "authority": MACRO_AUTHORITY,
        "manifest_id": manifest.get("manifest_id", ""),
        "manifest_sha256": manifest.get("manifest_sha256", ""),
        "domain_coverage": _domain_coverage(data, gex),
        "sources": sources,
        "fred_latest_observations": latest_fred_observations(str(data.get("fred_master_csv") or "")),
        "gex": gex,
        "missing_inputs": list(payload.get("files_missing") or []),
        "policy": {
            "macro_authority": MACRO_AUTHORITY,
            "candidate_authority": "NONE",
            "direction_authority": "NONE",
            "contract_authority": "NONE",
            "capital_authority": "NONE",
        },
    }
    ledger: dict[str, dict[str, str]] = {}
    for entry in manifest.get("entries", []):
        key = str(entry.get("key") or "")
        if key in sources:
            mode = "SEMANTIC_SUMMARY" if key == "regime_model_csv" else "FULL_RECORDS_OR_DOCUMENT"
            target = f"sources.{key}"
        elif key == "fred_master_csv":
            mode, target = "LATEST_OBSERVATION_PER_SERIES", "fred_latest_observations"
        elif key in {"gex_proxy_csv", "gex_by_strike_csv", "gex_manifest_json"}:
            mode = (
                "VALIDATED_SEMANTIC_GEX" if gex.get("status") == "VALIDATED"
                else "UNAVAILABLE_PUBLICATION_DIAGNOSTIC"
            )
            target = "gex"
        elif key == "us_money_index_advisory":
            mode, target = "BOUNDED_ADVISORY_CONTEXT", "US_MONEY_INDEX_CONSOLIDATED_ADVISORY"
        elif key == "prior_macro_json":
            mode, target = "PRIOR_BASELINE_CONTEXT", "PRIOR_MACRO_JSON"
        else:
            mode, target = "UNCONSUMED", ""
        ledger[key] = {"status": "CONSUMED" if mode != "UNCONSUMED" else mode, "mode": mode, "target": target}
    unconsumed = sorted(key for key, item in ledger.items() if item["status"] == "UNCONSUMED")
    if unconsumed:
        raise MacroInputContractError(
            "loaded macro inputs are not represented in the prompt contract: "
            + ",".join(unconsumed)
        )
    context["input_consumption_ledger"] = ledger
    context["input_consumption_status"] = "COMPLETE"
    return context


__all__ = [
    "MACRO_AUTHORITY",
    "MACRO_INPUT_CONTRACT_VERSION",
    "MACRO_PROMPT_CONTEXT_VERSION",
    "MacroInputContractError",
    "build_macro_input_manifest",
    "build_macro_prompt_context",
    "latest_fred_observations",
    "validate_manifest_lineage",
]
