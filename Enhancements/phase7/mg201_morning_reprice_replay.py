"""M-G2-01 acceptance: re-value the 9 Oct Morning GO contracts (run 20261008_220129) through the fixed Morning recompute,
using the Evening candidate rows and the Morning's captured quotes. Read-only; JSON receipt beside."""
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import morning_gate  # noqa: E402

RUN = "20261008_220129"
mv = ROOT / "data/output/runs" / RUN / "morning_validation"
eod = pd.read_csv(mv / f"morning_candidates_{RUN}.csv", low_memory=False, dtype=str)
eod = eod.loc[:, ~eod.columns.duplicated()].set_index("ticker")
mor = pd.read_csv(mv / f"morning_validated_trades_{RUN}.csv", low_memory=False, dtype=str)
mor = mor.loc[:, ~mor.columns.duplicated()]
go = mor[mor["verdict"].eq("GO")]
morning_gate._today_session = lambda: date(2026, 10, 9)
rows, changes = [], {"unchanged": 0, "replacement": 0, "no_quote": 0, "pays_flips": []}
for _, m in go.iterrows():
    row = {k: (None if pd.isna(v) else v) for k, v in eod.loc[m["ticker"]].items()} | {"ticker": m["ticker"]}
    live = {k: (None if pd.isna(v) else v) for k, v in m.items() if str(k).startswith(("live_", "quote_", "morning_repair", "selected_quote"))}
    out = morning_gate._recompute_for_morning_contract(row, live)
    basis = out.get("anticipated_contract_basis", "")
    key = "no_quote" if basis.startswith("EVENING_REFERENCE") else "unchanged" if basis.startswith("MORNING_REPRICED") else "replacement"
    changes[key] += 1
    new_state = out.get("anticipated_pays_state") or row.get("anticipated_pays_state")
    if new_state != row.get("anticipated_pays_state"):
        changes["pays_flips"].append(f'{m["ticker"]}: {row.get("anticipated_pays_state")} -> {new_state}')
    rows.append({"ticker": m["ticker"], "basis": basis, "eod_multiple": out.get("eod_anticipated_value_multiple_q50"),
                 "morning_multiple": out.get("anticipated_value_multiple_q50"), "morning_pays": new_state,
                 "valued_at": out.get("anticipated_valued_at_utc")})
out = {"run": RUN, "go_rows": len(go), **changes, "rows": rows}
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))
for r in rows:
    if r["ticker"] in ("JBLU", "UUUU", "MSFT", "MRVL"):
        print(r)
