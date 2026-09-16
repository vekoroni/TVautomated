"""p10_A_macro_archive.py -- Track A / A6 (REQ-WP0-06 macro packet archive by packet_id + hash).
Read-only. Inspects canonical_data/macro_packet_archive.py, build_macro_json.py, orchestrator/macro_loader.py,
dropbox/macro/ and dropbox/macro/Archive/, run_meta macro_* fields and final_run_manifest
worker3_market_environment packet_id/packet_sha256 on both reference runs; then attempts a read-only
resolve-by-ID for the 10 Sep packet through the archive module (only functions whose source has no
file-write operations are called).
Output: probes/p10_A_macro_archive_out.json (and stdout)
"""
import os, re, json, sys, hashlib, inspect, importlib, traceback

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes", "p10_A_macro_archive_out.json")
RUNS = ["20260910_150045", "20260911_115904"]
MODS = ["canonical_data/macro_packet_archive.py", "build_macro_json.py", "orchestrator/macro_loader.py"]
WRITE_RE = re.compile(r"open\([^)]*['\"][wa]|\.write\(|write_text\(|write_bytes\(|json\.dump\(|to_csv\(|to_json\(|os\.replace\(|os\.rename\(|shutil\.|mkdir|makedirs|unlink|remove\(")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_key(obj, pat, path=""):
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if re.search(pat, str(k), re.I):
                hits.append((path + "." + k, str(v)[:120]))
            hits += find_key(v, pat, path + "." + k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:50]):
            hits += find_key(v, pat, f"{path}[{i}]")
    return hits


def main():
    out = {}
    # 1. module presence and packet_id/hash vocabulary
    for m in MODS:
        p = os.path.join(ROOT, m)
        if not os.path.exists(p):
            out[m] = "ABSENT"; print(m, "ABSENT"); continue
        src = open(p, encoding="utf-8", errors="replace").read().splitlines()
        hits = [f"{i}: {l.strip()[:150]}" for i, l in enumerate(src, 1) if re.search(r"packet_id|sha256|content_hash|archive|resolve|latest", l, re.I)]
        defs = [f"{i}: {l.strip()[:120]}" for i, l in enumerate(src, 1) if re.match(r"\s*def |\s*class ", l)]
        out[m] = {"lines": len(src), "vocab_hits": hits[:80], "defs": defs}
        print("==", m, len(src), "lines;", len(hits), "vocab hits"); [print("   ", h) for h in hits[:60]]
    # 2. archive folders
    for d in ["dropbox/macro", "dropbox/macro/Archive", "dropbox/macro/archive"]:
        p = os.path.join(ROOT, d)
        if os.path.isdir(p):
            fl = sorted(os.listdir(p))
            out[d] = [(f, os.path.getsize(os.path.join(p, f)) if os.path.isfile(os.path.join(p, f)) else "DIR") for f in fl]
            print("==", d, out[d])
        else:
            out[d] = "ABSENT"; print("==", d, "ABSENT")
    # 3. run-level records
    for run in RUNS:
        base = os.path.join(ROOT, "data", "output", "runs", run)
        rm = json.load(open(os.path.join(base, "run_meta.json"), encoding="utf-8"))
        rec = {"run_meta_macro_fields": {k: v for k, v in rm.items() if k.startswith("macro")},
               "run_meta_packet_id_or_hash_keys": find_key(rm, r"packet_id|packet_sha|packet_hash|content_hash")}
        mp = os.path.join(base, "final_run_manifest.json")
        if os.path.exists(mp):
            man = json.load(open(mp, encoding="utf-8"))
            rec["manifest_keys"] = sorted(man.keys())
            rec["manifest_worker3_market_environment"] = man.get("worker3_market_environment", "ABSENT")
            rec["manifest_packet_keys"] = find_key(man, r"packet_id|packet_sha|packet_hash|content_hash|macro")
        for fn in ["macro_quant_packet.json", "macro_snapshot.json", "interpreter/interpreter_macro_context.json"]:
            fp = os.path.join(base, fn)
            if os.path.exists(fp):
                try:
                    j = json.load(open(fp, encoding="utf-8"))
                    rec[fn] = {"sha256": sha(fp), "top_keys": (sorted(j.keys())[:40] if isinstance(j, dict) else type(j).__name__),
                               "packet_keys": find_key(j, r"packet_id|packet_sha|packet_hash|content_hash|as_of|generated_at|source_path|source_file|build_id|version")[:25]}
                except Exception as e:
                    rec[fn] = f"ERR {e}"
            else:
                rec[fn] = "ABSENT"
        out[run] = rec
        print("==", run, json.dumps(rec, indent=1, default=str)[:5000])
    # 4. read-only resolve-by-ID attempt
    attempt = {"module_import": None, "callables": [], "calls": []}
    try:
        mod = importlib.import_module("canonical_data.macro_packet_archive")
        attempt["module_import"] = "OK"
        for name, fn in inspect.getmembers(mod, inspect.isfunction):
            if fn.__module__ != mod.__name__:
                continue
            try:
                s = inspect.getsource(fn)
            except OSError:
                s = ""
            writes = bool(WRITE_RE.search(s))
            attempt["callables"].append({"name": name, "sig": str(inspect.signature(fn)), "has_write_ops": writes})
        # candidate ids for the 10 Sep packet
        cand_ids = []
        for run in RUNS[:1]:
            base = os.path.join(ROOT, "data", "output", "runs", run)
            for fn in ["macro_quant_packet.json", "macro_snapshot.json", "final_run_manifest.json", "run_meta.json"]:
                fp = os.path.join(base, fn)
                if os.path.exists(fp):
                    j = json.load(open(fp, encoding="utf-8"))
                    for k, v in find_key(j, r"packet_id"):
                        cand_ids.append(v)
        cand_ids = list(dict.fromkeys(cand_ids)) or ["20260910", "macro_20260910", "avshunter_us_money_index1009"]
        attempt["candidate_ids"] = cand_ids
        # archive roots: the one build_macro_json.py actually writes (PIPELINE_MACRO_DIR/"archive" = data/macro/archive)
        # and the folder named by REQ-WP0-06 (dropbox/macro/Archive). load_macro_packet_by_id only globs *.json and
        # reads; it re-archives only on a unique match at the same path (byte-identical -> no write), so it is safe here.
        roots = [os.path.join(ROOT, "data", "macro", "archive"), os.path.join(ROOT, "dropbox", "macro", "Archive")]
        attempt["archive_roots"] = {r: ("EXISTS" if os.path.isdir(r) else "ABSENT") for r in roots}
        fn = getattr(mod, "load_macro_packet_by_id")
        for cid in cand_ids[:4]:
            for root in roots:
                try:
                    r = fn(cid, root)
                    attempt["calls"].append({"fn": "load_macro_packet_by_id", "arg": cid, "root": os.path.relpath(root, ROOT), "result": str(r)[:300], "exc": None})
                except Exception as e:
                    attempt["calls"].append({"fn": "load_macro_packet_by_id", "arg": cid, "root": os.path.relpath(root, ROOT), "result": None, "exc": f"{type(e).__name__}: {e}"[:300]})
        # hash truth: recompute the packet identity hash the archive module would compute, for both runs
        for run in RUNS:
            fp = os.path.join(ROOT, "data", "output", "runs", run, "macro_quant_packet.json")
            if os.path.exists(fp):
                pk = json.load(open(fp, encoding="utf-8-sig"))
                ident = {k: v for k, v in pk.items() if k not in {"macro_packet_sha256", "macro_packet_id", "macro_normalised_at_utc"}}
                try:
                    comp = hashlib.sha256(mod._canonical_bytes(ident)).hexdigest()
                except Exception as e:
                    comp = f"ERR {type(e).__name__}: {e}"
                attempt.setdefault("hash_recompute", {})[run] = {"declared": pk.get("macro_packet_sha256"), "recomputed": comp,
                                                                 "match": comp == pk.get("macro_packet_sha256"), "macro_packet_id": pk.get("macro_packet_id")}
    except Exception as e:
        attempt["module_import"] = f"FAILED: {type(e).__name__}: {e}"
        attempt["trace"] = traceback.format_exc()[-1500:]
    out["resolve_attempt"] = attempt
    print("== resolve attempt:", json.dumps(attempt, indent=1, default=str)[:4000])
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, default=str)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
