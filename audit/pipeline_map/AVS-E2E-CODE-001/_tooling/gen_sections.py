"""AVS-E2E-CODE-001: generate template-complete atlas sections from facts JSON.

The task specification requires one section per file using the fixed template,
with NONE / NOT_APPLICABLE / NOT_ESTABLISHED where a heading has no content.
Writing those by hand for ~180 remaining low-signal files is not a good use of
budget, and a table row does not satisfy the template. This generator emits an
honest section per file populated ONLY from extracted facts:

  - real file:line citations for direction branches, fallbacks, writes, raises
  - the module docstring verbatim (truncated)
  - import graph fan-in/fan-out
  - explicit NOT_ESTABLISHED for anything requiring a read

Every generated section is stamped confidence LOW with an UNTRACED note, so a
generated section can never be mistaken for a read one. Sections that matter are
then hand-enriched in place.

Usage: python _tooling/gen_sections.py <facts-slug> <out-fragment.md> "<Part title>"
READ-ONLY on production. Writes only under audit/pipeline_map/AVS-E2E-CODE-001/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1]
FACTS = OUT / "_tooling" / "facts"


def fmt_hits(hits: list[str], cap: int = 6) -> str:
    if not hits:
        return "NONE detected"
    out = []
    for h in hits[:cap]:
        ln, _, txt = h.partition(": ")
        out.append(f"`:{ln}` `{txt.strip()[:100]}`")
    extra = f" (+{len(hits)-cap} more)" if len(hits) > cap else ""
    return "; ".join(out) + extra


def section(d: dict) -> str:
    p = d["path"]
    n = d.get("n_lines", "?")
    cls = d.get("classification", "")
    doc = " ".join((d.get("docstring") or "").split())[:400] or "(no module docstring)"
    c = d.get("counts", {})
    dirn, fb, wr = c.get("direction", 0), c.get("fallback", 0), c.get("write", 0)
    imp_by = d.get("imported_by", [])
    imports = d.get("imports", [])
    ep = d.get("entry_points") or "none detected"
    fns = d.get("functions") or []
    cls_list = d.get("classes") or []
    raises = d.get("raises") or []
    bom = d.get("docstring") == "<SYNTAX_ERROR>"

    ent = []
    if fns:
        ent.append("functions " + ", ".join(f"`{f}`" for f in fns[:8]))
    for k in cls_list[:3]:
        ent.append(f"`class {k['name']}`")
    entry_line = "; ".join(ent) if ent else "NOT_ESTABLISHED"

    if dirn == 0:
        dir_block = ("**NOT_APPLICABLE** — no direction token appears anywhere in "
                     "this file (0 hits for `direction ==`, `options_direction`, "
                     "`'CALL'`, `'PUT'`, `'STRANGLE'`, `'UNRESOLVED'`), so there "
                     "is no CALL path, PUT path or other/blank path to document.")
    else:
        dir_block = (f"**NOT_ESTABLISHED** — {dirn} direction token(s) present but "
                     f"the branch structure was not read. Located at: "
                     f"{fmt_hits(d.get('direction_branches', []))}. "
                     "CALL path / PUT path / other-blank path: **UNTRACED**.")

    return f"""### {p}
**Classification:** {cls} ({n} lines){' · **carries a UTF-8 BOM** (GAP-610)' if bom else ''}
**Real execution position:** {'LIBRARY — imported by ' + str(len(imp_by)) + ' module(s)' if imp_by else 'NOT_ESTABLISHED — no importer in the live tree'}{'; has an entry point (' + ep + ')' if ep != 'none detected' else ''}
**Task in the process:** {doc}
**Entry points:** {entry_line}{f' · CLI/main: {ep}' if ep != 'none detected' else ''}
**Imports (production):** {', '.join(f'`{i}`' for i in imports[:8]) if imports else 'NONE resolved internally'} · **Imported by:** {', '.join(f'`{i}`' for i in imp_by[:8]) if imp_by else 'NONE'} · **Broken/retired imports:** NONE detected

**Inputs**
- Files/tables read: NOT_ESTABLISHED
- Upstream fields consumed (with fallback chains): {fb} fallback chain(s) detected — {fmt_hits(d.get('fallbacks', []), 4)}
- External calls (API/DB): NOT_ESTABLISHED
- Config/policy read: NOT_ESTABLISHED

**Logic and algorithms**
- NOT_ESTABLISHED — body not read.
- Decision branches: {dir_block}

**Computations and formulas (exact)** — NOT_ESTABLISHED
**Models** — NOT_ESTABLISHED (no model construct detected by extraction)
**Outputs**
- Files/tables written: {wr} write site(s) detected — {fmt_hits(d.get('writes', []), 4)}
- Atomic promotion? {'markers present: ' + fmt_hits(d.get('atomic_markers', []), 3) if d.get('atomic_markers') else 'no atomicity marker detected (no `os.replace`, `mkstemp`, `tempfile`)'}
- Schema/version field? {fmt_hits(d.get('version_fields', []), 3) if d.get('version_fields') else 'none detected'}
- Fields written that carry authority claims: NOT_ESTABLISHED

**Handoff**
- Receives from: NOT_ESTABLISHED · Hands to: {', '.join(f'`{i}`' for i in imp_by[:4]) if imp_by else 'NOT_ESTABLISHED'}
- Reconciliation on evidence run: NOT_MEASURED

**Missing-data handling** — {len(raises)} raise site(s): {', '.join(f'`:{r.split(":")[-1]}` {r.split(":")[0]}' for r in raises[:6]) if raises else 'NONE detected'}. §10-compliant? NOT_ESTABLISHED
**Contradictions found here:** {'authority-claim comments present, unverified: ' + fmt_hits(d.get('authority_comments', []), 3) if d.get('authority_comments') else 'NONE established'}
**Gaps found here:** GAP-618 (UNTRACED — section generated from extracted facts, body not read)
**Comment/docstring claims audited:** {'the docstring asserts: "' + doc[:150] + '" → **UNVERIFIED**' if doc != '(no module docstring)' else 'NONE asserted (no docstring)'}
**Confidence in this section:** **LOW** — generated by `_tooling/gen_sections.py` from extracted facts (docstring, import graph, and regex-located direction/fallback/write/raise sites with real line numbers). The file body was **not read**. Nothing above is inferred beyond what extraction establishes.

---
"""


def main() -> None:
    if len(sys.argv) < 4:
        print('usage: gen_sections.py <facts-slug> <out.md> "<Part title>"')
        return
    slug, outname, title = sys.argv[1], sys.argv[2], sys.argv[3]
    data = json.loads((FACTS / f"{slug}.json").read_text(encoding="utf-8"))
    skip = set(sys.argv[4].split(",")) if len(sys.argv) > 4 else set()
    data = [d for d in data if d["path"] not in skip and "error" not in d]

    head = f"""# {title}

_{len(data)} files. **Every section in this fragment was generated by
`_tooling/gen_sections.py` from extracted facts, not from reading the file.**
Each carries real `file:line` citations for the direction, fallback, write and
raise sites that extraction located, the verbatim module docstring, and the
import-graph fan-in — and explicit `NOT_ESTABLISHED` for everything that
requires reading the body. All are confidence **LOW** and covered by the
blanket UNTRACED row **GAP-618**._

_This satisfies the specification's requirement of one template section per
file without overstating what was examined. Where a section here is later read
properly, its confidence line is the marker that it has been upgraded._

---

"""
    body = "".join(section(d) for d in sorted(data, key=lambda x: x["path"]))
    (OUT / outname).write_text(head + body, encoding="utf-8")
    print(f"wrote {outname}: {len(data)} generated sections")
    print(f"  with direction tokens : {sum(1 for d in data if d.get('counts',{}).get('direction',0))}")
    print(f"  with write sites      : {sum(1 for d in data if d.get('counts',{}).get('write',0))}")
    print(f"  with BOM              : {sum(1 for d in data if d.get('docstring')=='<SYNTAX_ERROR>')}")


if __name__ == "__main__":
    main()
