"""00_changed_files.csv from the tag..worktree diff. READ ONLY, fast."""
import csv, hashlib, json, os, pathlib, subprocess, datetime, re
ROOT=pathlib.Path(".").resolve(); OUT=ROOT/"audit/pipeline_map/AVS-TST-QT-001"; TAG="pre-tidy-20260904"
def sh(p):
    try:
        h=hashlib.sha256()
        with open(p,"rb") as f:
            for b in iter(lambda:f.read(1<<20),b""):h.update(b)
        return h.hexdigest()
    except OSError: return ""
def tag_sha(path):
    p=subprocess.run(["git","show",f"{TAG}:{path}"],capture_output=True)
    return hashlib.sha256(p.stdout).hexdigest() if p.returncode==0 else ""
raw=subprocess.run(["git","diff","--name-status","-M",TAG,"--","."],capture_output=True,text=True).stdout
# backup manifests 4-6 Sep
covered={}
for d in sorted((ROOT/"backups").glob("*")):
    if not d.is_dir(): continue
    mt=datetime.datetime.fromtimestamp(d.stat().st_mtime)
    if mt<datetime.datetime(2026,9,4): continue
    for f in d.rglob("*"):
        if f.is_file():
            rel=f.relative_to(d).as_posix()
            covered.setdefault(rel,[]).append(d.name)
rows=[]
for line in raw.splitlines():
    if not line.strip(): continue
    parts=line.split("\t")
    code=parts[0]
    if code.startswith("R"):
        src,dst=parts[1],parts[2]; cls="MOVED_TO_ATTIC" if dst.startswith("_attic/") else "RENAMED"; path=src; newp=dst
    else:
        path=parts[1]; newp=""
        cls={"A":"ADDED","M":"MODIFIED","D":"DELETED"}.get(code[0],code)
    if path.startswith("audit/pipeline_map/AVS-TST-QT-001/"): continue
    fp=ROOT/path
    st=None
    try: st=fp.stat()
    except OSError: pass
    rows.append({
        "path":path,"new_path":newp,"change_class":cls,
        "is_production": not path.startswith(("audit/","_attic/")),
        "is_test": path.startswith("tests/"),
        "sha256_current": sh(fp) if st else "",
        "sha256_at_pre_tidy_tag": tag_sha(path) if cls in("MODIFIED","DELETED","MOVED_TO_ATTIC","RENAMED") else "",
        "mtime_utc": datetime.datetime.fromtimestamp(st.st_mtime,datetime.timezone.utc).isoformat(timespec="seconds") if st else "",
        "size_bytes": st.st_size if st else 0,
        "backup_manifests": ";".join(sorted(set(covered.get(path,[])))) or "NONE",
    })
# untracked
un=subprocess.run(["git","status","--porcelain","--untracked-files=all"],capture_output=True,text=True).stdout
for line in un.splitlines():
    if not line.startswith("?? "): continue
    path=line[3:].strip().strip('"')
    if path.startswith("audit/pipeline_map/AVS-TST-QT-001"): continue
    fp=ROOT/path
    if not fp.is_file(): continue
    st=fp.stat()
    rows.append({"path":path,"new_path":"","change_class":"ADDED_UNTRACKED",
        "is_production": not path.startswith(("audit/","_attic/")),
        "is_test": path.startswith("tests/"),
        "sha256_current":sh(fp),"sha256_at_pre_tidy_tag":"",
        "mtime_utc":datetime.datetime.fromtimestamp(st.st_mtime,datetime.timezone.utc).isoformat(timespec="seconds"),
        "size_bytes":st.st_size,"backup_manifests":";".join(sorted(set(covered.get(path,[])))) or "NONE"})
rows.sort(key=lambda r:(r["mtime_utc"] or "0"),reverse=True)
with (OUT/"00_changed_files.csv").open("w",newline="",encoding="utf-8") as fh:
    w=csv.DictWriter(fh,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
from collections import Counter
prod=[r for r in rows if r["is_production"]]
tests=[r for r in rows if r["is_test"]]
print("rows:",len(rows),"| production:",len(prod),"| tests:",len(tests))
print("class(prod):",dict(Counter(r["change_class"] for r in prod)))
nb=[r for r in prod if r["backup_manifests"]=="NONE" and r["change_class"] in("MODIFIED","ADDED","ADDED_UNTRACKED")
    and r["path"].endswith((".py",".json"))]
print(f"\nproduction .py/.json changed WITHOUT any 4-6 Sep backup manifest: {len(nb)}")
for r in nb: print("   ",r["change_class"],r["path"])
