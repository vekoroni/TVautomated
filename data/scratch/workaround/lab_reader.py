#!/usr/bin/env python3
"""Read-only reader for the Intelligence Lab review projection (Lane B Fix B, 12 Nov 2026).

One way to read the Lab for every Lane B script (hand-off, packs, triage check). It never writes into a run folder:
the SQLite database is opened with mode=ro and the manifest is only read.

Publication (written by the pipeline, contracts/lab_review_projection.py):
    data/output/runs/<run>/intelligence_lab/review_projection/manifest.json
        database_file, database_sha256, revision, card_fields, publication_state, created_at_utc, ...
    review-<revision>.sqlite
        rows(row_key, ordinal, sector, home_json, card_json)   card_json.values is aligned to manifest.card_fields
        evidence(row_key, family, payload_json)                zlib JSON with a "fields" dict
        publication(schema, run_id, revision, row_count)

Refuses (LabUnavailable, with the reason) when the manifest is missing, the publication is not COMPLETE, the database
file is missing, its sha256 is not the manifest's, or the publication table names another run or revision.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNS_DIR = ROOT / "data" / "output" / "runs"
FAMILIES = ("structure", "option_risk", "context", "morning")   # the audit family (600+ fields) is not carried by Lane B
RUN_NAME = re.compile(r"^\d{8}_\d{6}$")


class LabUnavailable(Exception):
    """The Lab publication cannot be used. The message says why."""


def manifest_path(run_id: str, runs_dir: Path = RUNS_DIR) -> Path:
    return Path(runs_dir) / run_id / "intelligence_lab" / "review_projection" / "manifest.json"


def read_manifest(run_id: str, runs_dir: Path = RUNS_DIR) -> dict:
    path = manifest_path(run_id, runs_dir)
    if not path.exists():
        raise LabUnavailable(f"no Lab review projection manifest for run {run_id}: {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LabUnavailable(f"Lab manifest for run {run_id} is unreadable ({type(error).__name__}): {path}") from error
    state = manifest.get("publication_state")
    if state != "COMPLETE":
        raise LabUnavailable(f"Lab publication for run {run_id} is {state or 'without a state'}, not COMPLETE")
    if not isinstance(manifest.get("card_fields"), list) or not manifest.get("database_file"):
        raise LabUnavailable(f"Lab manifest for run {run_id} names no card_fields or no database_file")
    return manifest


def newest_complete_run(runs_dir: Path = RUNS_DIR) -> str:
    """The newest run whose review projection manifest says COMPLETE."""
    runs_dir = Path(runs_dir)
    names = sorted((p.name for p in runs_dir.iterdir() if p.is_dir() and RUN_NAME.match(p.name)), reverse=True) if runs_dir.exists() else []
    reasons = []
    for name in names:
        try:
            read_manifest(name, runs_dir)
            return name
        except LabUnavailable as error:
            reasons.append(str(error))
            if len(reasons) >= 5:
                break
    raise LabUnavailable("no run with a COMPLETE Lab review projection under " + str(runs_dir)
                         + ("; newest tried: " + " | ".join(reasons[:3]) if reasons else ""))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class Lab:
    """One verified Lab publication. rows() and evidence() return what is stored; nothing is converted or filled."""

    def __init__(self, run_id: str, manifest: dict, database: Path, connection: sqlite3.Connection):
        self.run_id = run_id
        self.manifest = manifest
        self.database = database
        self.fields: list[str] = list(manifest["card_fields"])
        self.revision: str = manifest.get("revision", "")
        self.sha256: str = manifest.get("database_sha256", "")
        self.manifest_file = database.parent / "manifest.json"
        self._con = connection

    def close(self) -> None:
        self._con.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _card(self, row_key: str, ordinal, card_json: str) -> dict:
        card = json.loads(card_json)
        values = card.get("values") or []
        if len(values) != len(self.fields):
            raise LabUnavailable(f"card schema mismatch on row {row_key}: {len(values)} values for {len(self.fields)} card_fields")
        missing = [self.fields[i] for i in card.get("missing_fields") or [] if isinstance(i, int) and 0 <= i < len(self.fields)]
        extra = {k: v for k, v in card.items() if k not in ("values", "missing_fields")}
        return {"row_key": row_key, "ordinal": ordinal, "values": dict(zip(self.fields, values)), "missing": missing, "extra": extra}

    def rows(self):
        """Every published row in Lab ordinal order."""
        for row_key, ordinal, card_json in self._con.execute("SELECT row_key, ordinal, card_json FROM rows ORDER BY ordinal"):
            yield self._card(row_key, ordinal, card_json)

    def row_for_ticker(self, ticker: str) -> dict | None:
        ticker = str(ticker).upper().strip()
        index = self.fields.index("ticker") if "ticker" in self.fields else None
        if index is None:
            return None
        if not hasattr(self, "_by_ticker"):
            self._by_ticker = {}
            for row_key, card_json in self._con.execute("SELECT row_key, card_json FROM rows ORDER BY ordinal"):
                name = str((json.loads(card_json).get("values") or [None] * (index + 1))[index]).upper().strip()
                self._by_ticker.setdefault(name, row_key)
        row_key = self._by_ticker.get(ticker)
        if row_key is None:
            return None
        ordinal, card_json = self._con.execute("SELECT ordinal, card_json FROM rows WHERE row_key=?", (row_key,)).fetchone()
        return self._card(row_key, ordinal, card_json)

    def evidence(self, row_key: str, families=FAMILIES) -> dict:
        """{family: fields dict} for the row. A family the Lab did not publish for the row is None."""
        out = {family: None for family in families}
        marks = ",".join("?" for _ in families)
        for family, payload in self._con.execute(
                f"SELECT family, payload_json FROM evidence WHERE row_key=? AND family IN ({marks})", (row_key, *families)):
            raw = zlib.decompress(payload).decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
            out[family] = (json.loads(raw) or {}).get("fields")
        return out


def open_lab(run_id: str | None = None, runs_dir: Path = RUNS_DIR, verify_sha: bool = True) -> Lab:
    runs_dir = Path(runs_dir)
    run_id = run_id or newest_complete_run(runs_dir)
    manifest = read_manifest(run_id, runs_dir)
    database = manifest_path(run_id, runs_dir).parent / str(manifest["database_file"])
    if not database.exists():
        raise LabUnavailable(f"Lab database named by the manifest is missing: {database}")
    if verify_sha and manifest.get("database_sha256"):
        actual = sha256_file(database)
        if actual != manifest["database_sha256"]:
            raise LabUnavailable(f"Lab database sha256 {actual[:12]} is not the manifest's {str(manifest['database_sha256'])[:12]}: "
                                 "the publication changed while it was read, or the file is damaged")
    connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    try:
        published = connection.execute("SELECT run_id, revision, row_count FROM publication").fetchall()
    except sqlite3.Error as error:
        connection.close()
        raise LabUnavailable(f"Lab database has no readable publication table ({error})") from error
    if len(published) != 1 or published[0][0] != run_id or published[0][1] != manifest.get("revision"):
        connection.close()
        raise LabUnavailable(f"Lab database publication {published} does not match manifest run {run_id} revision {manifest.get('revision')}")
    return Lab(run_id, manifest, database, connection)
