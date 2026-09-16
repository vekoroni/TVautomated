import re, csv, os
OUT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\audit\td\AVS-TD-001"
rows = []
pat = re.compile(r"TRACE:\s*(.+)")
def split_trace(t):
    t = t.strip().strip("`").strip()
    parts = [p.strip() for p in t.split("|")]
    d = dict(req="", alg="", wp="", stage="", track="", evidence="", n="")
    keys = ["req", "alg", "wp", "stage", "track", "evidence", "n"]
    for k, p in zip(keys, parts):
        p = re.sub(r"^(REQ|ALG|WP|STAGE|TRACK|EVIDENCE)-", "", p)
        p = re.sub(r"^N=", "", p)
        d[k] = p
    return d
def scan(fname, idpat, kind):
    path = os.path.join(OUT, fname)
    if not os.path.exists(path): return
    cur = ""
    for line in open(path, encoding="utf-8"):
        if line.startswith("#"):
            m = re.search(idpat, line)
            if m: cur = m.group(0)
        tm = pat.search(line)
        if tm and cur:
            d = split_trace(tm.group(1))
            rows.append(dict(kind=kind, id=cur, source_file=fname, **d))
scan("defects.md", r"UAT-D\d{2}", "DEFECT")
scan("findings.md", r"DISC-F\d{2}", "FINDING")
# track-level traces not yet renumbered (deviations, premise-like) kept for completeness
for f in sorted(os.listdir(OUT)):
    if f.startswith("track_") and f.endswith(".md"):
        scan(f, r"(UAT-D-[A-Z]+\d+|DISC-F-M\d-\d+|DEV-[A-Z0-9]+|PN-\d+)", "TRACK_LINE")
seen = set(); uniq = []
for r in rows:
    k = (r["kind"], r["id"], r["req"], r["alg"], r["evidence"])
    if k in seen: continue
    seen.add(k); uniq.append(r)
for r in uniq:
    r["unmapped"] = "TRUE" if ("UNMAPPED" in r["req"] or "UNMAPPED" in r["alg"]) else "FALSE"
with open(os.path.join(OUT, "trace_index.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["kind","id","source_file","req","alg","wp","stage","track","evidence","n","unmapped"])
    w.writeheader(); w.writerows(uniq)
import collections
c = collections.Counter(r["kind"] for r in uniq)
print("rows", len(uniq), dict(c))
print("defects with trace:", len({r['id'] for r in uniq if r['kind']=='DEFECT'}), " findings with trace:", len({r['id'] for r in uniq if r['kind']=='FINDING'}))
print("UNMAPPED (defect+finding):", sum(1 for r in uniq if r['kind']!='TRACK_LINE' and r['unmapped']=='TRUE'))
print("UNMAPPED ids:", sorted({r['id'] for r in uniq if r['kind']!='TRACK_LINE' and r['unmapped']=='TRUE'}))
print("defect ids missing trace:", sorted(set(re.findall(r"UAT-D\d{2}", open(os.path.join(OUT,'defects.md'),encoding='utf-8').read())) - {r['id'] for r in uniq if r['kind']=='DEFECT'}))
