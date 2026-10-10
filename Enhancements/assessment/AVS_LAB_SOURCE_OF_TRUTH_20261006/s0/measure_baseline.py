"""S0 (source-of-truth programme, ACK 6 Oct 2026): reproducible baseline of the reference run.

Everything the design and the review register quote as a figure is re-measured here from the frozen artifacts, with
the command recorded, so S7 replay can compare against it (E32, E34, review decision 6). Read-only: it writes only its
own baseline_<run>.json / .md next to this script.

Measures
- population and schema width per stage artifact (rows, columns, bytes)
- Morning verdicts and Lab book verdicts
- option-value state by verdict (RC4 / E12: GO rows without a computed value)
- how often the value models disagree on GO rows (anticipated vs monetisability vs EV3) - disagreement, not defect
- Lab rank vs anticipated-value order (RC3)
- target fields that differ on GO rows (input to S1 mismatch classification, not a defect count)
- H1: columns lost from the saved execution-gate file
- H3/H7: spread unit by stage (fraction vs percent)
- Morning timings from the orchestrator log
- optional: Lab API latency and payload (--lab-url), which takes minutes on today's book

    venv\\Scripts\\python.exe Enhancements\\assessment\\AVS_LAB_SOURCE_OF_TRUTH_20261006\\s0\\measure_baseline.py \\
        --run-id 20261006_060401 [--lab-url http://127.0.0.1:5002]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent

STAGES = {
    "discovery": "discovery/discovery_candidates_ultimate_{r}.csv",
    "options_intelligence": "options/options_intelligence_{r}.csv",
    "vanguard_enriched": "options/vanguard_signals_enriched_{r}.csv",
    "eil_enriched": "superbrain/eil_enriched_{r}.csv",
    "execution_v3_5": "execution/execution_v3_5_{r}.csv",
    "morning_candidates": "morning_validation/morning_candidates_{r}.csv",
    "morning_validated": "morning_validation/morning_validated_trades_{r}.csv",
    "execution_gated": "trades/execution_gated_{r}.csv",
    "lab_book_csv": "intelligence_lab/final_opportunity_book_{r}.csv",
    "lab_book_json": "intelligence_lab/final_opportunity_book_{r}.json",
}


def _cols(path: Path) -> list[str]:
    return list(pd.read_csv(path, nrows=0).columns)


def _rows(path: Path) -> int:
    with open(path, "rb") as f:
        return max(sum(1 for _ in f) - 1, 0)          # physical lines; embedded newlines are reported as-is


def stage_table(run_dir: Path, r: str) -> dict:
    out = {}
    for name, rel in STAGES.items():
        p = run_dir / rel.format(r=r)
        if not p.exists():
            out[name] = {"present": False}
            continue
        entry = {"present": True, "bytes": p.stat().st_size}
        if p.suffix == ".csv":
            entry["columns"] = len(_cols(p))
            entry["data_rows"] = int(len(pd.read_csv(p, usecols=[0], low_memory=False)))
        out[name] = entry
    return out


def _spearman(a: pd.Series, b: pd.Series) -> float | None:
    m = a.notna() & b.notna()
    return None if m.sum() < 3 else round(float(a[m].rank().corr(b[m].rank())), 3)


def go_economics(run_dir: Path, r: str) -> dict:
    mv_path = run_dir / STAGES["morning_validated"].format(r=r)
    want = ["ticker", "morning_gate_verdict", "anticipated_pays_state", "anticipated_value_multiple_q50",
            "trade_lane", "direction"]
    mv = pd.read_csv(mv_path, usecols=lambda c: c in want, low_memory=False)
    verdicts = mv["morning_gate_verdict"].value_counts().to_dict()
    pays_by_verdict = pd.crosstab(mv["anticipated_pays_state"].fillna("MISSING"), mv["morning_gate_verdict"]).to_dict()

    book_path = run_dir / STAGES["lab_book_csv"].format(r=r)
    bwant = ["ticker", "lab_verdict", "lab_rank", "anticipated_value_multiple_q50", "anticipated_pays_state",
             "monetisability_state", "ev3_ev_conservative_return", "ev3_status",
             "target_price", "structural_target", "anticipated_level", "anticipated_level_q50",
             "anticipated_structural_level", "monetisability_structural_target_spot", "thesis_outcome_level"]
    book = pd.read_csv(book_path, usecols=lambda c: c in bwant, low_memory=False)
    go = book[book["lab_verdict"].isin(["GO", "GO_LIMIT"])].copy()
    ev3 = pd.to_numeric(go["ev3_ev_conservative_return"], errors="coerce")
    value = pd.to_numeric(go["anticipated_value_multiple_q50"], errors="coerce")
    targets = [c for c in bwant[8:] if c in go.columns]
    tnum = go[targets].apply(pd.to_numeric, errors="coerce")
    pair_diff = {}
    for i, a in enumerate(targets):
        for b in targets[i + 1:]:
            m = tnum[a].notna() & tnum[b].notna()
            pair_diff[f"{a}~{b}"] = {"both_present": int(m.sum()),
                                     "differ_gt_1pct": int(((tnum[a][m] / tnum[b][m] - 1).abs() > 0.01).sum())}
    return {
        "morning_verdicts": verdicts,
        "pays_state_by_morning_verdict": pays_by_verdict,
        "lab_verdicts": book["lab_verdict"].value_counts().to_dict(),
        "lab_go_rows": int(len(go)),
        "go_without_computed_value": go[go["anticipated_pays_state"].isin(
            ["NOT_COMPUTED", "NOT_ASSESSED_VOLATILITY_ONLY"])]["ticker"].tolist(),
        "go_value_models": {
            "anticipated_pays_and_monetisability_not": int(((go["anticipated_pays_state"] == "PAYS")
                                                            & (go["monetisability_state"] == "NOT_MONETISABLE")).sum()),
            "monetisability_states": go["monetisability_state"].value_counts(dropna=False).to_dict(),
            "ev3_status": go["ev3_status"].value_counts(dropna=False).to_dict(),
            "ev3_negative": int((ev3 < 0).sum()), "ev3_positive": int((ev3 > 0).sum()),
            "note": "disagreement between different measures is not by itself a defect (review register s7)",
        },
        "rank_vs_anticipated_value_spearman": _spearman(pd.to_numeric(go["lab_rank"], errors="coerce"),
                                                       -value),
        "go_target_field_pairs": pair_diff,
    }


def h1_columns_lost(run_dir: Path, r: str) -> dict:
    mv = set(_cols(run_dir / STAGES["morning_validated"].format(r=r)))
    gated = set(_cols(run_dir / STAGES["execution_gated"].format(r=r)))
    lost = sorted(mv - gated)
    return {"morning_columns": len(mv), "execution_gated_columns": len(gated), "lost": len(lost), "lost_names": lost}


def spread_units(run_dir: Path, r: str) -> dict:
    out = {}
    for stage in ("options_intelligence", "morning_validated"):
        p = run_dir / STAGES[stage].format(r=r)
        cols = [c for c in _cols(p) if c in ("spread_pct", "contract_spread_pct")]
        df = pd.read_csv(p, usecols=cols, low_memory=False)
        out[stage] = {c: {"median": round(float(pd.to_numeric(df[c], errors="coerce").median()), 4),
                          "p90": round(float(pd.to_numeric(df[c], errors="coerce").quantile(0.9)), 4)}
                      for c in cols}
    return out


def morning_timings(r: str) -> dict:
    log = ROOT / "logs" / "orchestrator.log"
    marks = {"morning_start": "MORNING VALIDATION", "catalyst_done": "Catalyst Truth complete (pre_morning",
             "gate_done": "Morning gate complete", "handoff_done": "Morning final handoff"}
    found: dict = {}
    pat = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
    with open(log, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    # the last Morning block for this run id
    start = max((i for i, ln in enumerate(lines) if f"--run-id {r}" in ln or f"run_id from CLI argument: {r}" in ln),
                default=0)
    for ln in lines[max(start - 20, 0):]:
        m = pat.match(ln)
        for k, needle in marks.items():
            if m and needle in ln and k not in found:
                found[k] = m.group(1)
    t = {k: datetime.strptime(v, "%Y-%m-%d %H:%M:%S") for k, v in found.items()}
    mins = lambda a, b: round((t[b] - t[a]).total_seconds() / 60, 1) if a in t and b in t else None
    return {"marks": found, "minutes": {"catalyst": mins("morning_start", "catalyst_done"),
                                        "gate": mins("catalyst_done", "gate_done"),
                                        "gate_to_lab_handoff": mins("gate_done", "handoff_done"),
                                        "total": mins("morning_start", "handoff_done")}}


def lab_latency(url: str) -> dict:
    t0 = time.time()
    with urllib.request.urlopen(f"{url}/api/run/latest", timeout=900) as resp:
        n = len(resp.read())
    return {"endpoint": "/api/run/latest", "seconds": round(time.time() - t0, 1), "bytes": n}


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--run-id", required=True)
    a.add_argument("--lab-url")
    args = a.parse_args()
    r = args.run_id
    run_dir = ROOT / "data" / "output" / "runs" / r
    base = {"run_id": r, "measured_at": datetime.now().isoformat(timespec="seconds"),
            "command": " ".join(["measure_baseline.py"] + sys.argv[1:]),
            "stages": stage_table(run_dir, r), "go_economics": go_economics(run_dir, r),
            "h1_execution_gated": h1_columns_lost(run_dir, r), "spread_units": spread_units(run_dir, r),
            "morning_timings": morning_timings(r)}
    if args.lab_url:
        base["lab_api"] = lab_latency(args.lab_url)
    (HERE / f"baseline_{r}.json").write_text(json.dumps(base, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in base.items() if k not in ("go_economics", "h1_execution_gated")},
                     indent=1, default=str)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
