"""p21_M1_structure.py -- read-only discovery of USMI packet structure.
Prints: run dirs with macro_snapshot.json / macro_quant_packet.json, the JSON path to
sector routing, the label vocabulary, and packet_id/as_of for every dated dropbox packet.
Writes p21_M1_structure_out.json beside itself. Never writes outside audit/td/AVS-TD-001/.
"""
import json, os, glob, sys
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes", "p21_M1_structure_out.json")
out = {}

def walk(obj, path="", depth=0, hits=None, maxdepth=8):
    if hits is None: hits = []
    if depth > maxdepth: return hits
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if any(s in k.lower() for s in ("routing", "priority", "sector_routing", "route")):
                hits.append((p, type(v).__name__, (list(v.keys())[:20] if isinstance(v, dict) else (v[:5] if isinstance(v, list) else v))))
            walk(v, p, depth+1, hits, maxdepth)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            walk(v, f"{path}[{i}]", depth+1, hits, maxdepth)
    return hits

# 1. runs carrying macro files
runs = sorted(glob.glob(os.path.join(ROOT, "data", "output", "runs", "*")))
runs_with = []
for r in runs:
    ms = os.path.join(r, "macro_snapshot.json"); mq = os.path.join(r, "macro_quant_packet.json")
    if os.path.exists(ms) or os.path.exists(mq):
        runs_with.append({"run": os.path.basename(r), "macro_snapshot": os.path.exists(ms), "macro_quant_packet": os.path.exists(mq),
                          "ms_size": os.path.getsize(ms) if os.path.exists(ms) else None})
out["runs_with_macro"] = runs_with
print("runs with macro files:", len(runs_with))

# 2. primary snapshot structure
prim = os.path.join(ROOT, "data", "output", "runs", "20260911_115904", "macro_snapshot.json")
snap = json.load(open(prim, encoding="utf-8"))
print("top keys:", list(snap.keys())[:30])
ex = snap.get("extras", {})
print("extras keys:", list(ex.keys())[:30] if isinstance(ex, dict) else type(ex))
usmi = ex.get("us_money_index", {}) if isinstance(ex, dict) else {}
print("usmi keys:", list(usmi.keys())[:30] if isinstance(usmi, dict) else type(usmi))
sp = usmi.get("source_payload", {}) if isinstance(usmi, dict) else {}
print("source_payload keys:", list(sp.keys())[:40] if isinstance(sp, dict) else type(sp))
out["primary_snapshot_top_keys"] = list(snap.keys())
out["primary_usmi_keys"] = list(usmi.keys()) if isinstance(usmi, dict) else None
out["primary_source_payload_keys"] = list(sp.keys()) if isinstance(sp, dict) else None
hits = walk(sp)
out["routing_paths_in_source_payload"] = [(p, t, str(v)[:300]) for p, t, v in hits]
for p, t, v in hits: print("HIT", p, t, str(v)[:300])
om = sp.get("options_monetisation", {}) if isinstance(sp, dict) else {}
print("options_monetisation keys:", list(om.keys())[:40] if isinstance(om, dict) else type(om))
sr = om.get("sector_routing", {}) if isinstance(om, dict) else {}
print("sector_routing keys:", list(sr.keys())[:40] if isinstance(sr, dict) else type(sr))
out["sector_routing_dump"] = sr
print(json.dumps(sr, indent=1)[:4000])
# packet id / as_of fields of primary
for k in ("packet_id", "as_of", "as_of_utc", "generated_at", "packet_date", "date", "version", "state", "scenario"):
    if isinstance(sp, dict) and k in sp: print("primary sp", k, "=", sp[k])
    if isinstance(usmi, dict) and k in usmi: print("primary usmi", k, "=", usmi[k])
out["primary_usmi_meta"] = {k: usmi.get(k) for k in usmi if not isinstance(usmi.get(k), (dict, list))} if isinstance(usmi, dict) else None
out["primary_sp_meta"] = {k: sp.get(k) for k in sp if not isinstance(sp.get(k), (dict, list))} if isinstance(sp, dict) else None

# 3. macro_quant_packet structure
mq = json.load(open(os.path.join(ROOT, "data", "output", "runs", "20260911_115904", "macro_quant_packet.json"), encoding="utf-8"))
print("mq top keys:", list(mq.keys())[:40])
out["primary_mq_top_keys"] = list(mq.keys())
mhits = walk(mq)
out["routing_paths_in_mq"] = [(p, t, str(v)[:300]) for p, t, v in mhits]
for p, t, v in mhits[:20]: print("MQHIT", p, t, str(v)[:200])

# 4. dropbox packets
pk = []
files = [os.path.join(ROOT, "dropbox", "macro", "avshunter_us_money_index.json"),
         os.path.join(ROOT, "dropbox", "macro", "avshunter_us_money_indexold1109pm.json")]
files += sorted(glob.glob(os.path.join(ROOT, "dropbox", "macro", "Archive", "avshunter_us_money_index*.json")))
for f in files:
    try:
        d = json.load(open(f, encoding="utf-8"))
    except Exception as e:
        pk.append({"file": os.path.relpath(f, ROOT), "error": str(e)}); continue
    meta = {k: d.get(k) for k in d if not isinstance(d.get(k), (dict, list))}
    om = d.get("options_monetisation", {})
    sr = om.get("sector_routing", {}) if isinstance(om, dict) else {}
    pk.append({"file": os.path.relpath(f, ROOT), "meta": meta, "top_keys": list(d.keys()),
               "sector_routing_keys": list(sr.keys()) if isinstance(sr, dict) else None,
               "routing": sr.get("routing") if isinstance(sr, dict) else None,
               "mtime": os.path.getmtime(f)})
    print("PKT", os.path.relpath(f, ROOT), {k: meta[k] for k in meta if k in ("packet_id", "as_of", "as_of_utc", "generated_at", "packet_date", "date", "version")})
out["dropbox_packets"] = pk

# 5. all run snapshots: packet ids
per_run = []
for r in runs_with:
    p = os.path.join(ROOT, "data", "output", "runs", r["run"], "macro_snapshot.json")
    if not os.path.exists(p): continue
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        per_run.append({"run": r["run"], "error": str(e)}); continue
    u = d.get("extras", {}).get("us_money_index", {}) if isinstance(d.get("extras"), dict) else {}
    s = u.get("source_payload", {}) if isinstance(u, dict) else {}
    sr = s.get("options_monetisation", {}).get("sector_routing", {}) if isinstance(s, dict) and isinstance(s.get("options_monetisation"), dict) else {}
    per_run.append({"run": r["run"],
                    "usmi_meta": {k: u.get(k) for k in u if not isinstance(u.get(k), (dict, list))} if isinstance(u, dict) else None,
                    "sp_meta": {k: s.get(k) for k in s if not isinstance(s.get(k), (dict, list))} if isinstance(s, dict) else None,
                    "routing": sr.get("routing") if isinstance(sr, dict) else None,
                    "sector_routing_keys": list(sr.keys()) if isinstance(sr, dict) else None})
    print("RUN", r["run"], per_run[-1]["usmi_meta"], "routing:", str(per_run[-1]["routing"])[:200])
out["per_run_snapshot"] = per_run
json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, default=str)
print("wrote", OUT)
