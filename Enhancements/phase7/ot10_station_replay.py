"""Item 10.3 acceptance: the station inspections on the healthy 8 Oct run (20261008_220129), read exactly as the run
reads them. No station may stop. Read-only on run data; reports are not written into the run folder."""
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from domain.station_inspection import inspect_station, station_policy  # noqa: E402

RUN = "20261008_220129"
R = ROOT / "data/output/runs" / RUN


def read(path):
    if str(path).endswith(".json"):
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return pd.DataFrame(payload if isinstance(payload, list) else (payload.get("rows") or []))
    return pd.read_csv(path, low_memory=False, dtype=str, keep_default_na=False, na_values=[""])


pol = station_policy()
audit = read(R / "diagnostics" / f"dropoff_audit_{RUN}.csv")
paths = {"discovery": R / "discovery" / f"discovery_candidates_ultimate_{RUN}.csv",
         "options": R / "options" / f"options_intelligence_{RUN}.csv",
         "eod": R / "morning_validation" / f"morning_candidates_{RUN}.csv",
         "book": R / "intelligence_lab" / f"final_opportunity_book_{RUN}.json",
         "morning": R / "morning_validation" / f"morning_validated_trades_{RUN}.csv"}
order = list(paths)
out = {}
for i, station in enumerate(order):
    frame = read(paths[station])
    prev = set(read(paths[order[i - 1]])["ticker"].astype(str).str.strip().str.upper()) if i else None
    stages = set(pol["accounted_drop_stages"].get(station) or [])
    accounted = set(audit.loc[audit["dropoff_stage"].isin(stages), "ticker"].astype(str).str.upper()) if prev else None
    rep = inspect_station(station, frame, run_id=RUN, previous_tickers=prev, accounted_tickers=accounted,
                          now_utc="2026-10-09T16:00:00Z", policy=pol)
    out[station] = {"rows": rep["rows"], "stop_defects": rep["stop_defects"], "other_defects": rep["other_defects"]}
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps({k: (v["rows"], len(v["stop_defects"]), [d["check"] for d in v["stop_defects"]]) for k, v in out.items()}))
