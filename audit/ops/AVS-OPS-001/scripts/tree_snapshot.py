r"""AVS-OPS-001 - repository tree snapshot. Read-only.

Scope (identical for the before and after snapshots):
  excluded top-level: .git venv .venv backups data dropbox
  excluded anywhere : __pycache__ .pytest_cache .mypy_cache
                      (build output; the compileall step in the verification
                       matrix legitimately mutates these)
  pruned            : any directory that is a symlink/junction, or that resolves
                      outside the repository root. vanguard/data and
                      vanguard/trades are junctions into C:\Users\ACKVerissimo\vanguard\
                      (~14 GB, external, not repository content).
  sha256            : files < 50 MB only.
"""
import csv, hashlib, os, pathlib, sys, datetime

ROOT = pathlib.Path(".").resolve()
ROOT_S = str(ROOT)
EXCLUDE_TOP = {".git", "venv", ".venv", "backups", "data", "dropbox"}
EXCLUDE_ANY = {"__pycache__", ".pytest_cache", ".mypy_cache"}
HASH_LIMIT = 50 * 1024 * 1024

def sha256(p):
    try:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        return h.hexdigest()
    except OSError:
        return ""

def keep_dir(full):
    """Prune junctions/symlinks and anything resolving outside the repo."""
    try:
        if os.path.islink(full):
            return False
        real = os.path.realpath(full)
        return real == ROOT_S or real.startswith(ROOT_S + os.sep)
    except OSError:
        return False

dest = sys.argv[1]
rows, skipped, pruned = [], 0, []
for dp, dn, fn in os.walk(ROOT_S):
    rel_dir = os.path.relpath(dp, ROOT_S)
    parts = [] if rel_dir == "." else rel_dir.split(os.sep)
    keep = []
    for d in dn:
        if d in EXCLUDE_ANY:
            continue
        if not parts and d in EXCLUDE_TOP:
            continue
        full = os.path.join(dp, d)
        if not keep_dir(full):
            pruned.append(os.path.relpath(full, ROOT_S).replace(os.sep, "/"))
            continue
        keep.append(d)
    dn[:] = keep
    for f in fn:
        p = os.path.join(dp, f)
        try:
            if os.path.islink(p):
                continue
            st = os.stat(p)
        except OSError:
            continue
        rel = os.path.relpath(p, ROOT_S).replace(os.sep, "/")
        h = sha256(p) if st.st_size < HASH_LIMIT else ""
        if not h and st.st_size >= HASH_LIMIT:
            skipped += 1
        rows.append((rel, st.st_size,
                     datetime.datetime.fromtimestamp(st.st_mtime, datetime.timezone.utc)
                     .isoformat(timespec="seconds"), h))

rows.sort()
with open(dest, "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh)
    w.writerow(["path", "size_bytes", "mtime_utc", "sha256"])
    w.writerows(rows)
print(f"{dest}: {len(rows)} files, {sum(r[1] for r in rows)/1e6:.1f} MB, "
      f"{skipped} unhashed (>=50MB), {len(pruned)} dirs pruned")
for x in sorted(set(pruned)):
    print(f"   pruned: {x}")
