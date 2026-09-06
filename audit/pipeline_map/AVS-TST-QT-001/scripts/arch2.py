"""AVS-TST-QT-001 0A - change ledger + backup-manifest chain. READ ONLY."""
import csv, hashlib, json, os, pathlib, subprocess, datetime, re
ROOT = pathlib.Path(".").resolve()
OUT = ROOT / "audit/pipeline_map/AVS-TST-QT-001"
TAG = "pre-tidy-20260904"

def sh_file(p):
    h = hashlib.sha256()
    try:
        with open(p, "rb") as f:
            for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
        return h.hexdigest()
    except OSError: return ""

# --- blob hashes at the tag, in ONE batch call -----------------------------
ls = subprocess.run(["git","ls-tree","-r",TAG], capture_output=True, text=True).stdout
tag_blob = {}
for line in ls.splitlines():
    if not line.strip(): continue
    meta, path = line.split("\t",1)
    _, typ, blob = meta.split()
    if typ=="blob": tag_blob[path.replace("\\","/")] = blob
batch_in = "\n".join(tag_blob.values()).encode()
proc = subprocess.run(["git","cat-file","--batch"], input=batch_in, capture_output=True)
tag_sha = {}
buf = proc.stdout; pos = 0
blobs = list(tag_blob.items())
for (path, oid) in blobs:
    nl = buf.index(b"\n", pos)
    header = buf[pos:nl].decode()
    parts = header.split()
    size = int(parts[2]); pos = nl+1
    content = buf[pos:pos+size]; pos += size + 1
    tag_sha[path] = hashlib.sha256(content).hexdigest()

# --- current tree ----------------------------------------------------------
SKIP_TOP={".git","_attic","backups","venv",".venv","data","dropbox","logs",
          "_cleanup_holding","Archive","node_modules"}
SKIP_ANY={"__pycache__",".pytest_cache",".mypy_cache"}
rows=[]; seen=set()
for dp,dn,fn in os.walk(ROOT):
    rel=pathlib.Path(dp).relative_to(ROOT); parts=rel.parts
    if parts and parts[0] in SKIP_TOP: dn[:]=[]; continue
    dn[:]=[d for d in dn if d not in SKIP_ANY and not(not parts and d in SKIP_TOP)]
    for f in fn:
        p=pathlib.Path(dp,f); r=p.relative_to(ROOT).as_posix()
        if r.startswith("audit/pipeline_map/AVS-TST-QT-001/"): continue
        seen.add(r)
        try: st=p.stat()
        except OSError: continue
        cur=sh_file(p); at=tag_sha.get(r,"")
        cls = "ADDED" if r not in tag_sha else ("MODIFIED" if at!=cur else "UNCHANGED")
        rows.append({"path":r,"change_class":cls,"sha256_current":cur,
            "sha256_at_pre_tidy_tag":at,
            "mtime_utc":datetime.datetime.fromtimestamp(st.st_mtime,datetime.timezone.utc).isoformat(timespec="seconds"),
            "size_bytes":st.st_size,"is_production": not r.startswith("audit/")})
for r in tag_sha:
    if r in seen or r.startswith("_attic/"): continue
    rows.append({"path":r,"change_class":"MOVED_TO_ATTIC" if (ROOT/"_attic"/r).exists() else "DELETED",
        "sha256_current":"","sha256_at_pre_tidy_tag":tag_sha[r],"mtime_utc":"","size_bytes":0,
        "is_production": not r.startswith("audit/")})
rows.sort(key=lambda x:(x["mtime_utc"] or "0"),reverse=True)
with (OUT/"00_changed_files.csv").open("w",newline="",encoding="utf-8") as fh:
    w=csv.DictWriter(fh,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

from collections import Counter
prod=[r for r in rows if r["is_production"]]
print("rows:",len(rows)," production rows:",len(prod))
print("ALL   :",dict(Counter(r["change_class"] for r in rows)))
print("PROD  :",dict(Counter(r["change_class"] for r in prod)))

# --- backup manifest chain -------------------------------------------------
mans=[]
for d in sorted((ROOT/"backups").glob("*")):
    if not d.is_dir(): continue
    mt=datetime.datetime.fromtimestamp(d.stat().st_mtime)
    if mt < datetime.datetime(2026,9,4): continue
    for m in d.rglob("*.json"):
        if "manifest" in m.name.lower():
            mans.append((mt,d.name,m))
mans.sort()
print(f"\n=== backup manifests 4-6 Sep: {len(mans)} ===")
covered=set()
for mt,dname,m in mans:
    try: j=json.loads(m.read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(f"  {mt:%m-%d %H:%M} {dname}/{m.name}: UNPARSEABLE {e}"); continue
    files=[]
    def walk(o):
        if isinstance(o,dict):
            for k,v in o.items():
                if isinstance(v,str) and re.fullmatch(r"[0-9a-f]{64}",v): files.append((k,v))
                else: walk(v)
        elif isinstance(o,list):
            for v in o: walk(v)
    walk(j)
    for k,_ in files: covered.add(k.replace("\\","/").lstrip("./"))
    print(f"  {mt:%m-%d %H:%M}  {dname:52s} files={len(files)}")
changed_prod={r["path"] for r in prod if r["change_class"] in ("MODIFIED","ADDED")
              and (r["path"].endswith((".py",".json")) )}
cov_norm=set()
for c in covered:
    cov_norm.add(c); cov_norm.add(c.split("/")[-1])
nobackup=sorted(p for p in changed_prod
                if p not in cov_norm and p.split("/")[-1] not in cov_norm
                and not p.startswith("tests/"))
print(f"\n=== production .py/.json changed WITHOUT appearing in any 4-6 Sep manifest: {len(nobackup)} ===")
for p in nobackup: print("   ",p)
json.dump({"manifest_covered":sorted(covered),"no_backup":nobackup},
          (OUT/"_manifest_chain.json").open("w",encoding="utf-8"),indent=1)
