"""AVS-E2E-CODE-001 Step 7: outputs catalogue from the evidence run.

For every artefact in data/output/runs/20260831_010309/ (excluding the
per-ticker packages/ subtree, which is catalogued in aggregate): path pattern,
row count, column count, mtime, and — for JSON — top-level keys.
Producer attribution is done separately by grepping writers; this script
records the measurable facts only.
READ-ONLY on run data. Writes only under audit/pipeline_map/AVS-E2E-CODE-001/.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "audit" / "pipeline_map" / "AVS-E2E-CODE-001"
RUN_ID = "20260831_010309"
RUN = ROOT / "data" / "output" / "runs" / RUN_ID

VERSIONISH = {"schema_version", "version", "calculation_version",
              "contract_version", "lifecycle_contract_version",
              "manifest_version", "pipeline_mode", "run_id"}


def csv_facts(p: Path) -> dict:
    try:
        with p.open("r", newline="", encoding="utf-8", errors="replace") as fh:
            rd = csv.reader(fh)
            try:
                header = next(rd)
            except StopIteration:
                return {"rows": 0, "cols": 0, "header": [], "version_fields": []}
            n = sum(1 for _ in rd)
        return {
            "rows": n, "cols": len(header), "header": header,
            "version_fields": sorted(set(header) & VERSIONISH),
        }
    except Exception as e:
        return {"rows": -1, "cols": -1, "header": [], "version_fields": [],
                "error": str(e)}


def json_facts(p: Path) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        return {"top_keys": [], "error": str(e)}
    if isinstance(d, dict):
        return {"top_keys": sorted(d.keys())[:60],
                "version_fields": sorted(set(d.keys()) & VERSIONISH)}
    if isinstance(d, list):
        return {"top_keys": [f"<list len={len(d)}>"], "version_fields": []}
    return {"top_keys": [f"<{type(d).__name__}>"], "version_fields": []}


def main() -> None:
    rows = []
    pkg_n = 0
    for p in sorted(RUN.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(RUN).as_posix()
        if rel.startswith("packages/"):
            pkg_n += 1
            continue
        st = p.stat()
        rec = {
            "artefact": rel,
            "pattern": rel.replace(RUN_ID, "{run_id}"),
            "bytes": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc)
                     .astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "ext": p.suffix.lower(),
        }
        if p.suffix.lower() == ".csv":
            rec.update(csv_facts(p))
        elif p.suffix.lower() == ".json":
            rec.update(json_facts(p))
        rows.append(rec)

    # machine-readable dump (full headers)
    (OUT / "_tooling" / "outputs_catalogue_raw.json").write_text(
        json.dumps({"run_id": RUN_ID, "package_files": pkg_n,
                    "artefacts": rows}, indent=1), encoding="utf-8")

    md = [
        "# 09 — Outputs catalogue",
        "",
        "**Document:** AVS-E2E-CODE-001 · Step 7",
        f"**Evidence run:** `data/output/runs/{RUN_ID}/`",
        "",
        "Row/column counts and version-field presence are **MEASURED** from "
        "the evidence run. Producer attribution is **OBSERVED** from the "
        "orchestrator call order in `03_execution_order.md`. `mtime` is the "
        "**last** write — see the rewrite caveat in `03_execution_order.md` §1.",
        "",
        f"Per-ticker package files under `packages/` are catalogued in "
        f"aggregate: **{pkg_n} files** (one JSON per ticker, written at "
        "evening stage 9 and patched by Trigger Layer pass 1 at stage 27).",
        "",
        "| Artefact (pattern) | Rows | Cols | Bytes | Last write | Version/identity fields present |",
        "|---|---:|---:|---:|---|---|",
    ]
    for r in sorted(rows, key=lambda x: x["artefact"]):
        vf = ", ".join(r.get("version_fields") or []) or "—"
        rowsv = r.get("rows", "")
        colsv = r.get("cols", "")
        md.append(
            f"| `{r['pattern']}` | {rowsv if rowsv != '' else '—'} | "
            f"{colsv if colsv != '' else '—'} | {r['bytes']:,} | {r['mtime']} | {vf} |")

    md += [
        "",
        "## JSON artefacts — top-level keys",
        "",
    ]
    for r in sorted(rows, key=lambda x: x["artefact"]):
        if r["ext"] == ".json" and r.get("top_keys"):
            md.append(f"- `{r['pattern']}` → {', '.join('`'+k+'`' for k in r['top_keys'])}")
    md.append("")

    (OUT / "09_outputs_catalogue.md").write_text("\n".join(md), encoding="utf-8")

    csvs = [r for r in rows if r["ext"] == ".csv"]
    jsons = [r for r in rows if r["ext"] == ".json"]
    print(f"artefacts (excl packages) = {len(rows)}  csv={len(csvs)} json={len(jsons)}")
    print(f"package files             = {pkg_n}")
    nov = [r for r in csvs if not r.get("version_fields")]
    print(f"CSV artefacts with NO version/identity field = {len(nov)}/{len(csvs)}")
    for r in sorted(csvs, key=lambda x: -(x.get('cols') or 0))[:12]:
        print(f"   {r.get('rows'):>6} rows {r.get('cols'):>4} cols  {r['artefact']}")


if __name__ == "__main__":
    main()
