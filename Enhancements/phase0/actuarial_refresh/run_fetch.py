"""Run the existing Polygon daily fetch with the key loaded from .env.

- The legacy script ``scripts/backfill_polygon_daily_v7.py`` runs in-process and
  unchanged, except that its module-level ``os`` is replaced by a shim whose
  ``replace`` retries on Windows ``PermissionError`` (antivirus/indexer briefly
  locking ``_source_manifest.json``, which the script rewrites after every ticker).
- The key is never printed: stdout/stderr are redacted, and the tracked
  ``_source_manifest.json`` is scrubbed of the key when the fetch ends.
"""

from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
import re
import sys
import time
import types

from dotenv import dotenv_values

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "backfill_polygon_daily_v7.py"
MANIFEST = REPO / "data" / "daily_history_v7" / "_source_manifest.json"
REDACTED = "<REDACTED_POLYGON_API_KEY>"
REPLACE_ATTEMPTS = 20
REPLACE_WAIT_SECONDS = 0.25


def scrub(text: str, key: str) -> str:
    text = text.replace(key, REDACTED)
    return re.sub(r"(apiKey=)[^&\s\"']+", r"\1" + REDACTED, text)


class RedactingStream(io.TextIOBase):
    def __init__(self, target, key: str) -> None:
        self._target, self._key = target, key

    def write(self, text: str) -> int:
        self._target.write(scrub(text, self._key))
        self._target.flush()
        return len(text)

    def flush(self) -> None:
        self._target.flush()


def retrying_replace(source, target) -> None:
    for attempt in range(REPLACE_ATTEMPTS):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt + 1 == REPLACE_ATTEMPTS:
                raise
            time.sleep(REPLACE_WAIT_SECONDS)


def main() -> int:
    key = (dotenv_values(REPO / ".env").get("POLYGON_API_KEY") or "").strip()
    if not key:
        print("POLYGON_API_KEY missing from .env", flush=True)
        return 2
    os.environ["POLYGON_API_KEY"] = key
    sys.stdout = RedactingStream(sys.__stdout__, key)
    sys.stderr = RedactingStream(sys.__stderr__, key)

    spec = importlib.util.spec_from_file_location("backfill_polygon_daily_v7", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    shim = types.SimpleNamespace(**{name: getattr(os, name) for name in dir(os) if not name.startswith("__")})
    shim.replace = retrying_replace
    module.os = shim

    sys.argv = [
        str(SCRIPT),
        "--universe", "Enhancements/phase0/actuarial_refresh/universe_20260917.csv",
        "--start", "2021-08-01", "--end", "2026-09-16",
        "--output", "data/daily_history_v7", "--workers", "8",
    ]
    os.chdir(REPO)
    code = 0
    try:
        module.main()
    except SystemExit as exit_signal:
        code = int(exit_signal.code or 0)
    except Exception as error:
        print(f"FETCH FAILED: {type(error).__name__}: {error}", flush=True)
        code = 1
    finally:
        if MANIFEST.exists():
            original = MANIFEST.read_text(encoding="utf-8")
            cleaned = scrub(original, key)
            if cleaned != original:
                MANIFEST.write_text(cleaned, encoding="utf-8")
                print("manifest scrubbed of API key occurrences", flush=True)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
