"""p33 - finalise artefact_inventory.csv from p03 raw + p20 M9 counts + reader/track greps. Read-only on repo.
Pass 1 (this script) writes probes/p33_artefact_inventory_pass1.csv; notes are merged from p33_unexamined_notes.csv if present."""
import csv, os, re, glob, json
import pandas as pd
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001")
PR = os.path.join(OUT, "probes")
raw = pd.read_csv(os.path.join(PR, "p03_artefact_inventory_raw.csv"), dtype=str).fillna("")
m9 = pd.read_csv(os.path.join(PR, "p20_M9_artefact_aggregate.csv"), dtype=str).fillna("")
prim = raw[raw.role == "PRIMARY"].copy(); comp = raw[raw.role == "COMPARISON"]
comp_keys = set(comp.stem.str.replace(r"^completed_thesis_receipt.*", "completed_thesis_receipt", regex=True) + "|" + comp.type)
m9["key"] = m9.artefact.str.split(r" \[").str[0]
m9d = m9.set_index("key").to_dict("index")
# production sources (same exclusions as p20)
EXCL = {"tests","backups","_attic","audit","Archive","venv",".venv","__pycache__",".codex_python313_runtime",".testdeps","data","dropbox","logs",".git","_cleanup_holding","decommissioned","legacy","node_modules"}
prod = {}
for dp, dn, fn in os.walk(ROOT):
    dn[:] = [d for d in dn if d not in EXCL]
    for f in fn:
        if f.endswith(".py"):
            p = os.path.join(dp, f)
            try: prod[os.path.relpath(p, ROOT)] = open(p, encoding="utf-8", errors="ignore").read().splitlines()
            except Exception: pass
print("prod files", len(prod))
READ = re.compile(r"read_csv|read_parquet|read_json|json\.load|json\.loads|open\(|Path\(|glob|read_text|load_json|_load|_read|scandir|listdir|pq\.|ParquetFile|jsonl")
WRITE_ONLY = re.compile(r"to_csv|json\.dump|write_text|to_parquet|\.write\(|DictWriter|csv\.writer")
def stem_rx(stem):
    if stem == "package": return re.compile(r"\.package\.json|package\.json")
    if stem == "validation_events": return re.compile(r"validation_events")
    return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(stem) + r"(?![A-Za-z0-9]|_(?!path|file|dir|csv|json)[A-Za-z])")
def readers(stem):
    rx = stem_rx(stem); out = []
    for f, lines in prod.items():
        hit = False
        for i, l in enumerate(lines):
            if rx.search(l):
                win = lines[max(0, i-5): i+6]
                w = "\n".join(win)
                if READ.search(w):
                    # reject pure writer windows (write token present, no explicit read call)
                    if WRITE_ONLY.search(w) and not re.search(r"read_csv|read_parquet|read_json|json\.load|read_text|load_json|glob|ParquetFile", w):
                        continue
                    hit = True; break
        if hit: out.append(f)
    return out
# tracks
TRACKS = ["A","B","C","D","E","F","G","H","I","N","M1","M2","M3","M4","M5","M6","M7","M8","M9"]
md = {t: open(os.path.join(OUT, f"track_{t}.md"), encoding="utf-8").read() for t in TRACKS}
md["census"] = open(os.path.join(OUT, "outcome_census.md"), encoding="utf-8").read()
PMAP = {"p10_A":["A"],"p11_B":["B"],"p12_C":["C"],"p13_D":["D"],"p14_EH":["E","H"],"p14_E_":["E"],"p15_F":["F"],"p16_G":["G"],
        "p17_IN":["I","N"],"p17_test":["I","N"],"p20_M9":["M9"],"p21_M9":["M9"],"p22_M9":["M9"],"p21_M1":["M1"],"p22_M2":["M2"],"p23_M3":["M3"],
        "p24_M4":["M4"],"p25_M5":["M5"],"p26_M6":["M6"],"p27_M7":["M7"],"p28_M8":["M8"],"p30_":["census"],"p31_":["census"],"p32_":["census"]}
probe_src = {}
for p in glob.glob(os.path.join(PR, "**", "*.py"), recursive=True):
    b = os.path.basename(p)
    if b.startswith("p20_M9_field_census"): continue   # generic walk of every artefact; recorded separately
    ts = [v for k, v in PMAP.items() if b.startswith(k)]
    if not ts: continue
    probe_src[p] = (ts[0], open(p, encoding="utf-8", errors="ignore").read())
ORDER = TRACKS + ["census"]
rows = []
for _, r in prim.iterrows():
    stem, path, typ = r.stem, r.path, r.type
    if stem.startswith("completed_thesis_receipt"): stem = "completed_thesis_receipt"
    ext = os.path.splitext(path)[1].lstrip(".")
    rx = stem_rx(stem)
    used_md, used_probe = set(), set()
    # extension-aware for stems shared by two files (csv/json, json/md)
    shared = ((prim.stem == r.stem).sum() > 1)
    def match(text):
        if not shared: return bool(rx.search(text))
        for m in rx.finditer(text):
            tail = text[m.end(): m.end()+40]
            mext = re.match(r"(?:_[0-9{<*][^\s.`'\"|,)]*)?\.(csv|json|md|parquet|jsonl|txt)", tail)
            if mext is None or mext.group(1) == ext: return True
        return False
    for t, txt in md.items():
        if match(txt): used_md.add(t)
    for p, (ts, src) in probe_src.items():
        if match(src): used_probe.update(ts)
    # wildcard-glob readers the stem grep cannot see (verified by reading the probe source)
    if path.startswith("ev3_shadow/") and typ in ("csv", "json"): used_probe.add("D")      # p13_D_d8 / d8b: ev3_shadow glob, probability columns/keys
    if re.match(r"horizon/horizon_(1_5d|6_10d|11_20d|blocked)_", path): used_probe.add("M8")  # p28_M8_cells: horizon_*_{rid}.csv
    used = [t for t in ORDER if t in used_md or t in used_probe]
    label = [t if t in used_md else t + "(probe)" for t in used]
    # generic scans: recorded but not counted as examination
    if typ == "csv": label.append("F(scan:header)")                                  # p15_F_04 rglob *.csv header-only
    if typ == "csv" and int(r.size_bytes) <= 60_000_000: label.append("M1(scan:vocab)")  # p21_M1_joinability 4-label text search
    if path in m9d: label.append("M9(scan:field census)")
    key = path.replace("<TICKER>", "<TICKER>")
    m = m9d.get(path, {})
    if typ in ("csv", "parquet"):
        rec = m.get("n_rows", ""); recsrc = "M9 pandas"
    elif typ == "jsonl":
        mm = re.search(r"records=(\d+)", m.get("load_note", "")); rec = mm.group(1) if mm else r.records; recsrc = "M9 jsonl records"
    elif typ == "json":
        rec = m.get("n_rows", ""); recsrc = "M9 flattened json rows"
        if "KEYS_ONLY" in m.get("load_note", ""): rec, recsrc = "", "not loaded (>100MB; M9 keys only)"
    elif typ in ("txt", "md"):
        rec, recsrc = r.records, "physical lines"
    else:  # families
        nf = re.search(r"n_files=(\d+)", next((k for k in m9.artefact if k.startswith(path)), ""))
        rec = r.records.split(" files")[0]; recsrc = f"files (raw walk); M9 census n_files={nf.group(1) if nf else '?'}"
        m = next((v for k, v in m9d.items() if k == path), m)
    ncols = r.columns_or_keys
    rd = readers(stem)
    in_census = path in m9d
    rows.append({"relative_path": path, "type": typ, "size_bytes": r.size_bytes, "record_count": rec, "record_count_basis": recsrc,
                 "column_or_key_count": ncols, "production_readers": ";".join(rd[:5]), "n_production_readers": len(rd),
                 "written_unread": "TRUE" if not rd else "FALSE",
                 "present_in_comparison_run": "TRUE" if (stem + "|" + typ) in comp_keys else "FALSE",
                 "tracks_using": ";".join(label), "m9_generic_census": "TRUE" if in_census else "FALSE",
                 "unexamined_by_test": "TRUE" if not [t for t in used if t != "M9"] else "FALSE", "unexamined_note": ""})
df = pd.DataFrame(rows)
notes_p = os.path.join(PR, "p33_unexamined_notes.csv")
if os.path.exists(notes_p):
    n = pd.read_csv(notes_p, dtype=str).fillna("").set_index("relative_path")["unexamined_note"].to_dict()
    df["unexamined_note"] = df.relative_path.map(n).fillna("")
    df.loc[df.unexamined_by_test == "FALSE", "unexamined_note"] = ""
    df.to_csv(os.path.join(OUT, "artefact_inventory.csv"), index=False)
    print("wrote artefact_inventory.csv", len(df))
df.to_csv(os.path.join(PR, "p33_artefact_inventory_pass1.csv"), index=False)
print("rows", len(df), "WRITTEN_UNREAD", (df.written_unread == "TRUE").sum(), "UNEXAMINED", (df.unexamined_by_test == "TRUE").sum(),
      "primary_only", (df.present_in_comparison_run == "FALSE").sum())
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 70)
print(df[["relative_path", "record_count", "n_production_readers", "written_unread", "present_in_comparison_run", "tracks_using"]].to_string())
