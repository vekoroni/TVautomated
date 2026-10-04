"""R-1 golden replay comparison: replayed Discovery rows vs the stored run CSV."""
import json, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ["direction", "discovery_direction_status", "tier", "stop_loss", "structural_target",
          "governed_invalidation_spot", "current_phase", "dominant_event", "precor_intent"]

def compare(run_id: str, replay: Path) -> dict:
    stored = pd.read_csv(ROOT / f"data/output/runs/{run_id}/discovery/discovery_candidates_ultimate_{run_id}.csv", low_memory=False)
    life = pd.read_csv(ROOT / f"data/output/runs/{run_id}/discovery/discovery_lifecycle_{run_id}.csv")
    rows = pd.DataFrame([json.loads(l) for l in replay.read_text(encoding="utf-8").splitlines()])
    rows = rows.rename(columns={f"o__{f}": f"r_{f}" for f in FIELDS})
    merged = life[["ticker", "outcome", "reason_code"]].merge(rows, on="ticker", how="left", suffixes=("_stored", "_replay"))
    merged = merged.merge(stored[["ticker"] + FIELDS], on="ticker", how="left")
    surv_stored = merged["outcome_stored"].eq("SURVIVE")
    surv_replay = merged["outcome_replay"].eq("SURVIVE")
    both = surv_stored & surv_replay
    out = {"run_id": run_id, "lifecycle_rows": len(life), "replayed": int(merged["outcome_replay"].notna().sum()),
           "stored_survivors": int(surv_stored.sum()), "replay_survivors": int(surv_replay.sum()),
           "survivor_set_mismatch": int((surv_stored != surv_replay).sum()),
           "no_bar_at_session": int(merged["outcome_replay"].eq("NO_BAR_AT_SESSION").sum()), "fields": {}}
    for f in FIELDS:
        a, b = merged.loc[both, f], merged.loc[both, f"r_{f}"]
        if a.dtype.kind in "fi" or f in {"stop_loss", "structural_target", "governed_invalidation_spot", "tier"}:
            a = pd.to_numeric(a, errors="coerce"); b = pd.to_numeric(b, errors="coerce")
            same = ((a - b).abs() <= 1e-6 * a.abs().clip(lower=1)) | (a.isna() & b.isna())
        else:
            same = (a.fillna("").astype(str) == b.fillna("").astype(str))
        out["fields"][f] = {"compared": int(both.sum()), "mismatch": int((~same).sum())}
    return out

if __name__ == "__main__":
    base = ROOT / "Enhancements/assessment/AVS_DIR002_STEP1_BASELINE_20261001"
    results = [compare(r, base / f"golden_replay_current_code_{r}.jsonl") for r in sys.argv[1:]]
    print(json.dumps(results, indent=1))
    (base / "golden_replay_comparison.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
