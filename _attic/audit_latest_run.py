from pathlib import Path
import json
import pandas as pd

latest = Path(r"""C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\output\runs\20260502_001155""")

print("=" * 80)
print("AVSHUNTER RUN INTEGRITY AUDIT")
print("=" * 80)
print("Run folder:", latest)
print()

# 1. Key files
key_files = [
    "run_meta.json",
    "macro_snapshot.json",
    "scanner_context_20260502_001155.json",
    "packages/index.json",
]

print("KEY FILE CHECK")
for rel in key_files:
    p = latest / rel
    print(f"{rel:45} exists={p.exists()} size={p.stat().st_size if p.exists() else 0}")
print()

# 2. CSV row counts
print("CSV OUTPUT CHECK")
csvs = list(latest.rglob("*.csv"))
if not csvs:
    print("No CSV files found.")
else:
    for f in csvs:
        try:
            df = pd.read_csv(f)
            print(f"{str(f.relative_to(latest)):80} rows={len(df):8} cols={len(df.columns):5}")
        except Exception as e:
            print(f"{str(f.relative_to(latest)):80} READ_ERROR: {e}")
print()

# 3. JSON package count and bad JSON check
print("PACKAGE JSON CHECK")
package_dir = latest / "packages"
packages = list(package_dir.glob("*.package.json")) if package_dir.exists() else []
print("Package count:", len(packages))

bad_json = []
zero_size = []
for f in packages:
    try:
        if f.stat().st_size == 0:
            zero_size.append(f.name)
            continue
        with open(f, "r", encoding="utf-8") as fh:
            json.load(fh)
    except Exception as e:
        bad_json.append((f.name, str(e)))

print("Zero-size packages:", len(zero_size))
print("Bad JSON packages:", len(bad_json))

if zero_size:
    print("ZERO SIZE SAMPLE:", zero_size[:20])
if bad_json:
    print("BAD JSON SAMPLE:", bad_json[:20])
print()

# 4. Look inside packages for dangerous integrity markers
print("INTRADAY / DATA QUALITY CHECK")
intraday_zero = []
missing_price = []
has_macro_false = []

for f in packages:
    try:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        text = json.dumps(data).lower()

        if '"intraday_rows": 0' in text or "'intraday_rows': 0" in text:
            intraday_zero.append(f.stem.replace(".package", ""))

        if '"current_price": null' in text or '"current_price": 0' in text:
            missing_price.append(f.stem.replace(".package", ""))

        if '"has_macro_regime": false' in text:
            has_macro_false.append(f.stem.replace(".package", ""))

    except Exception:
        pass

print("Packages with intraday_rows = 0:", len(intraday_zero))
print("Packages with missing/zero current_price:", len(missing_price))
print("Packages with has_macro_regime = false:", len(has_macro_false))

if intraday_zero:
    print("INTRADAY ZERO SAMPLE:", intraday_zero[:50])
if missing_price:
    print("MISSING PRICE SAMPLE:", missing_price[:50])
if has_macro_false:
    print("MACRO FALSE SAMPLE:", has_macro_false[:50])
print()

# 5. Index file count
print("INDEX CHECK")
index_path = latest / "packages" / "index.json"
if index_path.exists():
    try:
        with open(index_path, "r", encoding="utf-8") as fh:
            idx = json.load(fh)
        if isinstance(idx, list):
            print("index.json type=list count=", len(idx))
        elif isinstance(idx, dict):
            print("index.json type=dict keys=", list(idx.keys())[:20])
            for k, v in idx.items():
                if isinstance(v, list):
                    print(f"  {k}: list count={len(v)}")
                elif isinstance(v, dict):
                    print(f"  {k}: dict keys={list(v.keys())[:10]}")
                else:
                    print(f"  {k}: {type(v).__name__}")
        else:
            print("index.json type=", type(idx).__name__)
    except Exception as e:
        print("index.json READ_ERROR:", e)
else:
    print("index.json missing")

print()
print("=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)
