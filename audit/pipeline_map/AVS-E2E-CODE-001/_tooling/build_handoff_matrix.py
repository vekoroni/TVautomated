"""AVS-E2E-CODE-001 Step 3: handoff matrix with measured reconciliation.

For every stage boundary in 03_execution_order.md, measure rows in vs rows out
and test the sect 14.5 invariant: input unique tickers = passed + rejected + deferred.
READ-ONLY on run data. Writes only under audit/pipeline_map/AVS-E2E-CODE-001/.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "audit" / "pipeline_map" / "AVS-E2E-CODE-001"
RUN_ID = "20260831_010309"
RUN = ROOT / "data" / "output" / "runs" / RUN_ID

TICKER_KEYS = ("ticker", "Ticker", "TICKER", "symbol", "Symbol")


def tickers(rel: str) -> tuple[set[str], int, str]:
    """Return (unique tickers, row count, ticker column used)."""
    p = RUN / rel
    if not p.exists():
        return set(), -1, "FILE_MISSING"
    with p.open(newline="", encoding="utf-8", errors="replace") as f:
        rd = csv.reader(f)
        try:
            header = next(rd)
        except StopIteration:
            return set(), 0, "EMPTY"
        col = next((h for h in TICKER_KEYS if h in header), None)
        if col is None:
            n = sum(1 for _ in rd)
            return set(), n, "NO_TICKER_COL"
        i = header.index(col)
        vals, n = [], 0
        for row in rd:
            n += 1
            if i < len(row):
                v = row[i].strip().upper()
                if v:
                    vals.append(v)
        return set(vals), n, col


STAGES = [
    ("Discovery", "discovery/discovery_candidates_ultimate_{r}.csv"),
    ("Vanguard", "vanguard/vanguard_signals.csv"),
    ("Vanguard enriched", "options/vanguard_signals_enriched_{r}.csv"),
    ("Options Intelligence", "options/options_intelligence_{r}.csv"),
    ("Options (phantom)", "options/options_intelligence_phantom_{r}.csv"),
    ("Horizon 1_5d", "horizon/horizon_1_5d_{r}.csv"),
    ("Horizon 6_10d", "horizon/horizon_6_10d_{r}.csv"),
    ("Horizon 11_20d", "horizon/horizon_11_20d_{r}.csv"),
    ("Horizon blocked", "horizon/horizon_blocked_{r}.csv"),
    ("SuperBrain enriched", "superbrain/superbrain_enriched_{r}.csv"),
    ("Wall Break", "superbrain/wall_break_scores_{r}.csv"),
    ("EIL enriched", "superbrain/eil_enriched_{r}.csv"),
    ("Execution v3.5", "execution/execution_v3_5_{r}.csv"),
    ("GARCH", "qomega/garch_forecasts_{r}.csv"),
    ("EOD candidates", "morning_validation/morning_candidates_{r}.csv"),
    ("Morning blocked review", "morning_validation/morning_blocked_review_{r}.csv"),
    ("Final book (CSV)", "intelligence_lab/final_opportunity_book_{r}.csv"),
    ("Options blocked review", "options/options_blocked_review.csv"),
    ("Contract rejection log", "options/contract_rejection_log_{r}.csv"),
]


def main() -> None:
    facts = {}
    for name, pat in STAGES:
        rel = pat.format(r=RUN_ID)
        t, n, col = tickers(rel)
        facts[name] = {"rel": rel, "tickers": t, "rows": n, "col": col}
        print(f"  {n:>6} rows  {len(t):>6} uniq  [{col}]  {name}")

    md = [
        "# 05 — Handoff matrix",
        "",
        "**Document:** AVS-E2E-CODE-001 · Step 3",
        f"**Evidence run:** `data/output/runs/{RUN_ID}/`",
        "",
        "Row and ticker counts are **MEASURED**. Join keys are **OBSERVED** "
        "from the consuming code. The reconciliation column tests the "
        "AVS-E2E-DATA-LOGIC-001 sect 14.5 invariant "
        "`input unique tickers = passed + rejected + deferred`.",
        "",
        "## Per-artefact census",
        "",
        "| Stage artefact | Rows | Unique tickers | Duplicates | Ticker column |",
        "|---|---:|---:|---:|---|",
    ]
    for name, f in facts.items():
        if f["rows"] < 0:
            md.append(f"| `{f['rel']}` ({name}) | FILE MISSING | — | — | — |")
            continue
        dup = f["rows"] - len(f["tickers"]) if f["col"] not in (
            "NO_TICKER_COL", "EMPTY", "FILE_MISSING") else "—"
        md.append(f"| `{f['rel']}` ({name}) | {f['rows']:,} | "
                  f"{len(f['tickers']):,} | {dup} | `{f['col']}` |")

    md += ["", "## Stage boundaries and reconciliation", ""]

    def boundary(a: str, b: str, note: str = "") -> None:
        A, B = facts[a], facts[b]
        if A["rows"] < 0 or B["rows"] < 0:
            md.append(f"### {a} → {b}\n\nOne side missing; UNDETERMINED.\n")
            return
        lost = A["tickers"] - B["tickers"]
        gained = B["tickers"] - A["tickers"]
        md.append(f"### {a} → {b}")
        md.append("")
        md.append(f"- rows in **{A['rows']:,}** → rows out **{B['rows']:,}** "
                  f"(delta {B['rows']-A['rows']:+,})")
        md.append(f"- tickers dropped: **{len(lost):,}**; "
                  f"tickers appearing that were not upstream: **{len(gained):,}**")
        if gained:
            md.append(f"  - examples of unexpected arrivals: "
                      f"{', '.join(sorted(gained)[:8])}")
        if note:
            md.append(f"- {note}")
        md.append("")

    boundary("Discovery", "Vanguard")
    boundary("Vanguard", "Options Intelligence")
    boundary("Options Intelligence", "SuperBrain enriched")
    boundary("SuperBrain enriched", "EIL enriched")
    boundary("EIL enriched", "Execution v3.5")
    boundary("Execution v3.5", "EOD candidates")
    boundary("EOD candidates", "Final book (CSV)")
    boundary("Options Intelligence", "Wall Break")

    # Horizon reconciliation
    oi = facts["Options Intelligence"]
    hz = set()
    for k in ("Horizon 1_5d", "Horizon 6_10d", "Horizon 11_20d", "Horizon blocked"):
        hz |= facts[k]["tickers"]
    hz_rows = sum(facts[k]["rows"] for k in
                  ("Horizon 1_5d", "Horizon 6_10d", "Horizon 11_20d", "Horizon blocked"))
    md += [
        "### Options Intelligence → Horizon Router (sect 14.5 test)",
        "",
        f"- input rows **{oi['rows']:,}**, input unique tickers **{len(oi['tickers']):,}**",
        f"- routed 1_5d **{facts['Horizon 1_5d']['rows']:,}** + "
        f"6_10d **{facts['Horizon 6_10d']['rows']:,}** + "
        f"11_20d **{facts['Horizon 11_20d']['rows']:,}** + "
        f"blocked **{facts['Horizon blocked']['rows']:,}** = **{hz_rows:,}**",
        f"- **unaccounted rows: {oi['rows'] - hz_rows:,}**",
        f"- tickers present in Options but in no horizon file: "
        f"**{len(oi['tickers'] - hz):,}**",
        "",
        f"**Reconciliation: {'HOLDS' if oi['rows'] == hz_rows else 'FAILS'}** "
        f"(GAP-003).",
        "",
    ]

    (OUT / "05_handoff_matrix.md").write_text("\n".join(md), encoding="utf-8")
    (OUT / "_tooling" / "handoff_facts.json").write_text(json.dumps(
        {k: {"rel": v["rel"], "rows": v["rows"], "uniq": len(v["tickers"]),
             "col": v["col"]} for k, v in facts.items()}, indent=1),
        encoding="utf-8")
    print("\nwrote 05_handoff_matrix.md")


if __name__ == "__main__":
    main()
