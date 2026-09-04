"""AVS-RCA-002 A5d - per-stage size and runtime. READ ONLY."""
import os, pathlib, re, sys
for rid in ("20260904_004338","20260902_232526"):
    root=pathlib.Path("data/output/runs")/rid
    tot=0; files=0; rows=[]
    for d in sorted(root.iterdir()):
        if d.is_dir():
            s=0; n=0
            for dp,_,fn in os.walk(d):
                for f in fn:
                    try: s+=os.path.getsize(os.path.join(dp,f)); n+=1
                    except OSError: pass
            rows.append((d.name,s,n)); tot+=s; files+=n
        else:
            try: tot+=d.stat().st_size; files+=1
            except OSError: pass
    print(f"\n### {rid}: total {tot/1e9:.3f} GB, {files} files ###")
    for n,s,c in sorted(rows,key=lambda r:-r[1]):
        print(f"   {n:22s} {s/1e6:10.1f} MB  {c:6d} files")
