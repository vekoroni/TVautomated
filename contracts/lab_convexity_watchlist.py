"""Immutable revision-pinned convexity sidecar. GET never builds or reprices."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4
import zlib


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))


def publish_convexity(manifest, database, rows=None):
    """Explicit saved-input publication only; never called by a read endpoint."""
    from contracts.lab_review_projection import _connect
    from domain.lab_convexity import build_watchlist, VERSION
    database = Path(database)
    folder = database.parent
    data_path = folder / f"convexity-{manifest['revision']}-{VERSION}.json"
    receipt_path = data_path.with_suffix(".receipt.json")
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("sha256") != hashlib.sha256(data_path.read_bytes()).hexdigest():
            raise ValueError("Existing convexity publication failed digest verification")
        return receipt
    # Connections are short-lived and read-only. Existing published databases are immutable.
    with closing(_connect(database)) as conn:
        indexed = conn.execute("SELECT row_key,ordinal FROM rows ORDER BY ordinal").fetchall()
        if rows is None:
            rows = []
            for key, ordinal in indexed:
                fields = {}
                for (payload,) in conn.execute("SELECT payload_json FROM evidence WHERE row_key=?", (key,)):
                    fields.update(json.loads(zlib.decompress(payload))["fields"])
                rows.append(fields)
    if len(rows) != manifest["row_count"] or len(indexed) != len(rows):
        raise ValueError("Convexity source population mismatch")
    payload = build_watchlist(rows)
    keys = {ordinal:key for key, ordinal in indexed}
    for group in payload["groups"].values():
        for item in group:
            item["row_key"] = keys[item["source_row_ordinal"]]
    payload.update(run_id=manifest["run_id"], revision=manifest["revision"],
                   source_database_sha256=manifest["database_sha256"],
                   source_publication_utc=manifest["created_at_utc"],
                   built_at_utc=datetime.now(timezone.utc).isoformat(),
                   provider_calls=0, pipeline_run=False)
    encoded = _json(payload).encode("utf-8")
    # Immutable name: an existing generation is never overwritten.
    with data_path.open("xb") as stream:
        stream.write(encoded)
    receipt = {"schema": VERSION, "file": data_path.name, "bytes": len(encoded),
               "sha256": hashlib.sha256(encoded).hexdigest(), "run_id": manifest["run_id"],
               "revision": manifest["revision"], "source_database_sha256": manifest["database_sha256"]}
    temp = folder / f"convexity-{uuid4().hex}.tmp"
    try:
        temp.write_text(_json(receipt), encoding="utf-8")
        os.replace(temp, receipt_path)
    finally:
        if temp.exists():
            temp.unlink()
    return receipt


def publish_saved_convexity(runs_dir, run_id):
    from contracts.lab_review_projection import _read_manifest
    manifest, database = _read_manifest(runs_dir, run_id)
    receipt = publish_convexity(manifest, database)
    _read_manifest(runs_dir, run_id, manifest["revision"])
    return receipt


def read_convexity(runs_dir, run_id, revision=None):
    from contracts.lab_review_projection import _read_manifest, ReviewIntegrityError
    from domain.lab_convexity import VERSION
    manifest, database = _read_manifest(runs_dir, run_id, revision)
    path = database.parent / f"convexity-{manifest['revision']}-{VERSION}.json"
    try:
        receipt = json.loads(path.with_suffix(".receipt.json").read_text(encoding="utf-8"))
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ReviewIntegrityError("Malformed convexity publication") from exc
    expected = {"schema": VERSION, "file": path.name, "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(), "run_id": run_id,
                "revision": manifest["revision"], "source_database_sha256": manifest["database_sha256"]}
    if receipt != expected or any(payload.get(k) != expected[k] for k in
                                  ("schema", "run_id", "revision", "source_database_sha256")):
        raise ReviewIntegrityError("Convexity publication identity/digest mismatch")
    if payload.get("authority") != "RESEARCH_DISPLAY_ONLY" or payload.get("population") != manifest["row_count"]:
        raise ReviewIntegrityError("Convexity population/authority mismatch")
    return payload
