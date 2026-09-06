"""AVS-TST-QT-001 0A - file-level change ledger. READ ONLY."""
import csv, hashlib, json, os, pathlib, subprocess, datetime

ROOT = pathlib.Path(".").resolve()
OUT = ROOT / "audit/pipeline_map/AVS-TST-QT-001"
TAG = "pre-tidy-20260904"
SKIP_TOP = {".git", "_attic", "backups", "venv", ".venv", "data", "dropbox",
            "__pycache__", ".pytest_cache", ".mypy_cache", "logs", "_cleanup_holding",
            "Archive", "node_modules"}
SKIP_ANY = {"__pycache__", ".pytest_cache", ".mypy_cache"}

def sh(p):
    try:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""):
                h.update(b)
        return h.hexdigest()
    except OSError:
        return ""

def tag_hashes():
    out = subprocess.run(["git", "ls-tree", "-r", TAG], capture_output=True, text=True).stdout
    d = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        _, typ, blob = meta.split()
        if typ == "blob":
            d[path.replace("\\", "/")] = blob
    return d

def tag_content_hash(path):
    """sha256 of the blob content at the tag (git blob ids are sha1 over a header)."""
    p = subprocess.run(["git", "show", f"{TAG}:{path}"], capture_output=True)
    if p.returncode != 0:
        return ""
    return hashlib.sha256(p.stdout).hexdigest()

TAGGED = tag_hashes()

# Phase 0 backup manifest (Thursday 13:35)
PHASE0 = {}
p0 = ROOT / "backups/avs_sd_002_rev1_1_phase0_prechange_20260903_133546"
for man in p0.rglob("MANIFEST.json"):
    try:
        j = json.loads(man.read_text(encoding="utf-8-sig"))
    except Exception:
        continue
    entries = j.get("files") or j.get("entries") or j
    if isinstance(entries, dict):
        for k, v in entries.items():
            if isinstance(v, str):
                PHASE0[k.replace("\\", "/")] = v
            elif isinstance(v, dict):
                PHASE0[k.replace("\\", "/")] = v.get("sha256") or v.get("hash") or ""
    elif isinstance(entries, list):
        for e in entries:
            if isinstance(e, dict):
                k = e.get("path") or e.get("file") or ""
                PHASE0[str(k).replace("\\", "/")] = e.get("sha256") or e.get("hash") or ""

rows = []
seen = set()
for dp, dn, fn in os.walk(ROOT):
    rel_dir = pathlib.Path(dp).relative_to(ROOT)
    parts = rel_dir.parts
    if parts and parts[0] in SKIP_TOP:
        dn[:] = []
        continue
    dn[:] = [d for d in dn if d not in SKIP_ANY and not (not parts and d in SKIP_TOP)]
    if parts and parts[0] == "audit" and any(p.startswith("tmp") or p == "tmp" for p in parts):
        dn[:] = []
        continue
    for f in fn:
        p = pathlib.Path(dp, f)
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith("audit/pipeline_map/AVS-TST-QT-001/"):
            continue
        seen.add(rel)
        try:
            st = p.stat()
        except OSError:
            continue
        cur = sh(p)
        at_tag = tag_content_hash(rel) if rel in TAGGED else ""
        if rel not in TAGGED:
            cls = "ADDED"
        elif at_tag and at_tag != cur:
            cls = "MODIFIED"
        else:
            cls = "UNCHANGED"
        rows.append({
            "path": rel, "change_class": cls,
            "sha256_current": cur, "sha256_at_pre_tidy_tag": at_tag,
            "sha256_phase0_backup": PHASE0.get(rel, ""),
            "mtime_utc": datetime.datetime.fromtimestamp(st.st_mtime, datetime.timezone.utc)
                          .isoformat(timespec="seconds"),
            "size_bytes": st.st_size,
            "tracked_at_tag": rel in TAGGED,
        })

for rel in TAGGED:
    if rel in seen:
        continue
    if rel.startswith(("_attic/",)):
        continue
    cur_path = ROOT / rel
    attic = (ROOT / "_attic" / rel).exists()
    rows.append({
        "path": rel, "change_class": "MOVED_TO_ATTIC" if attic else "DELETED",
        "sha256_current": "", "sha256_at_pre_tidy_tag": tag_content_hash(rel),
        "sha256_phase0_backup": PHASE0.get(rel, ""), "mtime_utc": "", "size_bytes": 0,
        "tracked_at_tag": True,
    })

rows.sort(key=lambda r: (r["mtime_utc"] or "0000"), reverse=True)
dest = OUT / "00_changed_files.csv"
with dest.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

from collections import Counter
c = Counter(r["change_class"] for r in rows)
print("00_changed_files.csv rows:", len(rows))
for k, v in c.most_common():
    print(f"   {k}: {v}")
print("\nPhase 0 manifest entries parsed:", len(PHASE0))
ch = [r for r in rows if r["change_class"] in ("MODIFIED", "ADDED")
      and not r["path"].startswith("audit/")]
print("changed/added OUTSIDE audit/:", len(ch))
print("\n--- 30 most recently modified non-audit files ---")
for r in ch[:30]:
    print(f"  {r['mtime_utc']}  {r['change_class']:9s} {r['path']}")
