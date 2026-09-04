"""AVS-E2E-CODE-001 Deliverable 12: claims ledger.

Extracts every tagged claim (OBSERVED / MEASURED / INFERRED) from the atlas,
the execution-order doc, the handoff matrix, the cross-verification report and
the doc-delta, and emits one ledger row per claim with its evidence anchor.
READ-ONLY on production. Writes only under audit/pipeline_map/AVS-E2E-CODE-001/.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

OUT = Path(__file__).resolve().parents[1]

SOURCES = [
    "03_execution_order.md",
    "04_atlas.md",
    "04_appendix_standalone_orphan_retired.md",
    "05_handoff_matrix.md",
    "09_outputs_catalogue.md",
    "10_cross_verification.md",
    "11_doc_vs_code_delta.md",
]

TAG = re.compile(r"\b(OBSERVED|MEASURED|INFERRED)\b")
# Verdict vocabularies that are themselves measurements/observations even when
# the line carries no OBSERVED/MEASURED word (Lane A's cross-verification table).
VERDICT = re.compile(r"\b(CONFIRMED|NOT_CONFIRMED|NOT_MEASURABLE)\b")
CLAIMVERD = re.compile(r"\b(HOLDS|FALSE|PARTIAL|UNTRACED)\b")
# file:line anchors, e.g. foo/bar.py:123 or foo.py:12-34
ANCHOR = re.compile(r"[\w./\\-]+\.py:\d+(?:-\d+)?")
# bare module path (appendix entries anchor on the file itself, no line)
BARE_PY = re.compile(r"[\w./\\-]+\.py\b")
ARTEFACT = re.compile(r"[\w./{}-]+\.(?:csv|json|sqlite|parquet)")
CONF = re.compile(r"\b(HIGH|MEDIUM|LOW)\b")
CURRENT_FILE = re.compile(r"^###\s+`?(\S+?\.py)`?\s*$")


def main() -> None:
    rows = []
    n = 0
    for src in SOURCES:
        p = OUT / src
        if not p.exists():
            continue
        current = ""
        for i, line in enumerate(
                p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            m = CURRENT_FILE.match(line.strip())
            if m:
                current = m.group(1)
            tags = TAG.findall(line)
            verds = VERDICT.findall(line)
            cverds = CLAIMVERD.findall(line)
            if not tags and not verds and not cverds:
                continue
            text = line.strip().lstrip("|-*# ").strip()
            if len(text) < 25:
                continue
            n += 1
            anchors = ANCHOR.findall(line)
            arts = ARTEFACT.findall(line)
            confs = CONF.findall(line)
            # Fall back to a bare module path, then to the enclosing section's
            # file, so an appendix or verdict row still carries an anchor.
            if not anchors:
                bare = [b for b in BARE_PY.findall(line) if b.endswith(".py")]
                if bare:
                    anchors = bare
                elif current:
                    anchors = [current]
            # a line may carry several tags; strongest evidence wins for the row
            if "MEASURED" in tags or verds:
                tag = "MEASURED"
            elif "OBSERVED" in tags:
                tag = "OBSERVED"
            elif "INFERRED" in tags:
                tag = "INFERRED"
            else:
                # a HOLDS/FALSE/PARTIAL verdict with no explicit tag is an
                # observation about code unless it cites an artefact
                tag = "MEASURED" if arts and not anchors else "OBSERVED"
            rows.append({
                "id": f"CLM-{n:04d}",
                "source_doc": src,
                "source_line": i,
                "subject_file": current,
                "text": text[:600],
                "tag": tag,
                "all_tags": "|".join(sorted(set(tags + verds + cverds))),
                "code_anchor": ";".join(sorted(set(anchors))[:6]),
                "artefact_anchor": ";".join(sorted(set(arts))[:6]),
                "confidence": confs[0] if confs else "",
            })

    cols = ["id", "source_doc", "source_line", "subject_file", "text", "tag",
            "all_tags", "code_anchor", "artefact_anchor", "confidence"]
    with (OUT / "12_claims_ledger.csv").open(
            "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    by_tag: dict[str, int] = {}
    for r in rows:
        by_tag[r["tag"]] = by_tag.get(r["tag"], 0) + 1
    unanchored = [r for r in rows
                  if not r["code_anchor"] and not r["artefact_anchor"]]

    print(f"claims extracted = {len(rows)}")
    for k, v in sorted(by_tag.items()):
        print(f"  {k:<10} {v:>5}")
    print(f"claims with no file:line or artefact anchor = {len(unanchored)}")
    print("\nby source doc:")
    per: dict[str, int] = {}
    for r in rows:
        per[r["source_doc"]] = per.get(r["source_doc"], 0) + 1
    for k, v in sorted(per.items(), key=lambda kv: -kv[1]):
        print(f"  {v:>5}  {k}")


if __name__ == "__main__":
    main()
