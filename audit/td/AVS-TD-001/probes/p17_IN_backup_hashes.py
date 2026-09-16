"""p17 I4: compare Stage 0 manifest database_snapshots hashes to files under backups/."""
import hashlib, json, os, sys
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
man = json.load(open(os.path.join(ROOT, "audit/avs_fix_002/stage0/STAGE0_BASELINE_MANIFEST.json"), encoding="utf-8-sig"))
snaps = man["database_snapshots"]
out = {"manifest_snapshots": snaps, "files": []}
bdir = os.path.join(ROOT, "backups", "avs_fix_002_stage0_20260912")
for dp, dn, fn in os.walk(bdir):
    for f in fn:
        p = os.path.join(dp, f)
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        out["files"].append({"path": os.path.relpath(p, ROOT).replace("\\", "/"), "size": os.path.getsize(p), "sha256": h.hexdigest()})
json.dump(out, open(os.path.join(ROOT, "audit/td/AVS-TD-001/probes/p17_IN_backup_hashes.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
