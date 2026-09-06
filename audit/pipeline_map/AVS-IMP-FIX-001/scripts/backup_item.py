"""AVS-FIX-001 binding rule 4: back up every file an item touches, before touching it.

    python backup_item.py <item> <path> [<path> ...]

Writes backups/avs_fix_001_<item>_prechange_<UTC stamp>/ containing a copy of
each existing file (path structure preserved) and MANIFEST.json holding the
SHA-256, byte count and mtime of every one.  Paths that do not yet exist are
recorded as {"exists": false} so a new-file item still leaves a manifest
proving the file was absent beforehand.

Never copies a file matching a secret pattern (.env and friends) — binding
rule 2 outranks rule 4; such files are recorded by hash only.
"""
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SECRET_NAMES = {".env", ".env.txt"}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv):
    if len(argv) < 3:
        raise SystemExit("usage: backup_item.py <item> <path> [<path> ...]")
    item = argv[1]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = REPO / "backups" / f"avs_fix_001_{item}_prechange_{stamp}"
    dest.mkdir(parents=True, exist_ok=False)

    entries = []
    for raw in argv[2:]:
        path = (REPO / raw).resolve()
        rel = path.relative_to(REPO).as_posix()
        if not path.exists():
            entries.append({"path": rel, "exists": False})
            continue
        entry = {"path": rel, "exists": True, "sha256": sha256(path),
                 "bytes": path.stat().st_size,
                 "mtime_utc": datetime.fromtimestamp(
                     path.stat().st_mtime, timezone.utc).isoformat()}
        if path.name in SECRET_NAMES:
            entry["plaintext_copied"] = False
            entry["reason"] = "binding rule 2: secret-bearing file, hash only"
        else:
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            entry["plaintext_copied"] = True
        entries.append(entry)

    (dest / "MANIFEST.json").write_text(json.dumps(
        {"item": item, "created_utc": datetime.now(timezone.utc).isoformat(),
         "repo": str(REPO), "files": entries}, indent=2), encoding="utf-8")
    print(dest.as_posix())


if __name__ == "__main__":
    main(sys.argv)
