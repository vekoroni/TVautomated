"""S0 (source-of-truth programme, ACK 6 Oct 2026): freeze a reference run by content hash.

Writes a manifest of every file in the run folder (relative path, size, sha256, mtime). It changes nothing in the run.
Re-running with --verify compares the folder against the manifest, so later stages can prove they replay the same
inputs (E32). The run itself stays where it is: archive retention prunes data/archive only, never data/output/runs.

    venv\\Scripts\\python.exe Enhancements\\assessment\\AVS_LAB_SOURCE_OF_TRUTH_20261006\\s0\\freeze_run.py \\
        --run-id 20261006_060401 [--verify]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(run_dir: Path) -> dict:
    files = {}
    for p in sorted(run_dir.rglob("*")):
        if p.is_file():
            st = p.stat()
            files[p.relative_to(run_dir).as_posix()] = {
                "bytes": st.st_size, "sha256": sha256(p),
                "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds")}
    return files


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--run-id", required=True)
    a.add_argument("--verify", action="store_true")
    args = a.parse_args()
    run_dir = ROOT / "data" / "output" / "runs" / args.run_id
    out = HERE / f"frozen_manifest_{args.run_id}.json"
    files = snapshot(run_dir)
    if args.verify:
        frozen = json.loads(out.read_text(encoding="utf-8"))["files"]
        changed = sorted(k for k in frozen if k not in files or files[k]["sha256"] != frozen[k]["sha256"])
        added = sorted(set(files) - set(frozen))
        print(json.dumps({"run_id": args.run_id, "frozen": len(frozen), "changed_or_missing": changed[:50],
                          "n_changed_or_missing": len(changed), "n_added": len(added)}, indent=1))
        return 1 if changed else 0
    manifest = {"run_id": args.run_id, "frozen_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "file_count": len(files), "total_bytes": sum(v["bytes"] for v in files.values()), "files": files}
    out.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("run_id", "file_count", "total_bytes")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
