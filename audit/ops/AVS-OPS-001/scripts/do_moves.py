"""AVS-OPS-001 commit 2 - git mv every MOVE row of 03_candidates.csv into _attic/.
Moves only. No file content is read, edited or deleted here.
.env.txt is handled separately by the caller (git rm - the one permitted deletion).
Usage: do_moves.py [--apply]
"""
import csv, os, pathlib, subprocess, sys

APPLY = "--apply" in sys.argv
ROOT = pathlib.Path(".").resolve()
rows = list(csv.DictReader(open("audit/ops/AVS-OPS-001/03_candidates.csv", encoding="utf-8")))
moves = [r for r in rows if r["decision"] == "MOVE"]

done, failed = [], []
for r in moves:
    src = r["path"]
    dst = pathlib.Path("_attic") / src          # preserve the original relative path
    if not os.path.exists(src):
        failed.append((src, "SOURCE_MISSING")); continue
    if os.path.exists(dst):
        failed.append((src, f"DEST_EXISTS:{dst}")); continue
    if not APPLY:
        print(f"DRY-RUN git mv {src!r} -> {dst.as_posix()!r}")
        continue
    dst.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(["git", "mv", "--", src, str(dst)],
                       capture_output=True, text=True, errors="replace")
    if p.returncode == 0:
        done.append((src, dst.as_posix()))
        print(f"moved  {src}  ->  {dst.as_posix()}")
    else:
        failed.append((src, (p.stderr or p.stdout).strip()[:160]))
        print(f"FAILED {src}: {(p.stderr or p.stdout).strip()[:160]}")

print(f"\n{'APPLIED' if APPLY else 'DRY-RUN'}: candidates={len(moves)} moved={len(done)} failed={len(failed)}")
for s, e in failed:
    print(f"  FAIL {s}: {e}")
if APPLY:
    pathlib.Path("audit/ops/AVS-OPS-001/_moves_applied.csv").write_text(
        "src,dst\n" + "\n".join(f"{a},{b}" for a, b in done), encoding="utf-8")
