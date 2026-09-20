"""AVS-SD-MON-003 item E: DOI population reconciliation check.

Read-only research script, no production side effects. Runs run_completed_session_doi() against a
SCRATCH COPY of the canonical registry (never the live data/canonical/control_plane.sqlite), using
tonight's real, already-stored options CSV and provider-finality evidence as inputs.

DOIProductionSummary.__post_init__() already enforces these population balances as hard, raising
invariants (canonical_data/dynamic_options_production.py) - if this script completes without
raising, reconciliation holds by construction under real data, now that item D's identity fix has
landed. If it raises, that is a second, independent defect worth its own root-cause pass, per the
fix spec's own instruction not to bundle it with D.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from canonical_data.dynamic_options_production import run_completed_session_doi  # noqa: E402

RUN_ID = "20260919_205844"
SCRATCH_REGISTRY = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if SCRATCH_REGISTRY is None:
    raise SystemExit("usage: item_e_reconciliation_check.py <scratch_control_plane.sqlite> [max_tickers]")
MAX_TICKERS = int(sys.argv[2]) if len(sys.argv) > 2 else None

OPTIONS_CSV = REPO / "data" / "output" / "runs" / RUN_ID / "options" / f"options_intelligence_{RUN_ID}.csv"
REPORT_PATH = REPO / "Enhancements" / "backtest" / f"item_e_doi_reconciliation_{RUN_ID}.json"
MACRO_PATH = REPO / "data" / "output" / "runs" / RUN_ID / "macro_snapshot.json"
GOVERNED_CONSTANTS = REPO / "config" / "governed_constants_v1.json"


def main() -> int:
    summary = run_completed_session_doi(
        run_id=RUN_ID,
        options_csv=OPTIONS_CSV,
        registry_path=SCRATCH_REGISTRY,
        report_path=REPORT_PATH,
        macro_path=MACRO_PATH if MACRO_PATH.is_file() else None,
        governed_constants_path=GOVERNED_CONSTANTS if GOVERNED_CONSTANTS.is_file() else None,
        max_tickers=MAX_TICKERS,
    )
    print("RECONCILED - no exception raised, populations balance by construction.")
    print(json.dumps({
        "input_rows": summary.input_rows,
        "unique_tickers": summary.unique_tickers,
        "retained_opportunities": summary.retained_opportunities,
        "family_rows": summary.family_rows,
        "assessed_families": summary.assessed_families,
        "unassessed_families": summary.unassessed_families,
        "ranked_families": summary.ranked_families,
        "unranked_assessed_families": summary.unranked_assessed_families,
        "exception_count": summary.exception_count,
        "population_reconciled": summary.population_reconciled,
        "population_equation": summary.to_dict()["population_equation"],
        "counts_by_state": summary.counts_by_state,
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
