"""Item 8 acceptance: dispositions for every row of the live 8 Oct book (run 20261008_220129), written to a scratch
ledger (never the production ledger). Read-only on run data; JSON receipt beside."""
import collections
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from canonical_data.decision_outcome_ledger import DecisionOutcomeLedger  # noqa: E402
from domain.ticker_disposition import disposition_records  # noqa: E402

RUN = "20261008_220129"
book = json.loads((ROOT / "data/output/runs" / RUN / "intelligence_lab" / f"final_opportunity_book_{RUN}.json")
                  .read_text(encoding="utf-8"))
rows = book if isinstance(book, list) else (book.get("rows") or book.get("opportunities"))   # JSON keeps "NAN" a ticker
records = disposition_records(rows, run_id=RUN, stage="EOD", recorded_at_utc="2026-10-08T22:00:00Z")
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
    ledger = DecisionOutcomeLedger(Path(tmp) / "scratch_ledger.sqlite")
    appended, again = ledger.append_dispositions(records), ledger.append_dispositions(records)
out = {"run": RUN, "book_rows": len(rows), "dispositions": len(records), "appended": appended, "re_append": again,
       "with_thesis_id": sum(1 for r in records if r["thesis_identity_state"] == "PRESENT"),
       "thesis_states": dict(collections.Counter(r["thesis_identity_state"] for r in records).most_common(8)),
       "contract_states": dict(collections.Counter(r["contract_identity_state"].split(":")[0] + ":" +
                                                   r["contract_identity_state"].split(":")[1][:40] if ":" in r["contract_identity_state"]
                                                   else r["contract_identity_state"] for r in records).most_common(8))}
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=1))
