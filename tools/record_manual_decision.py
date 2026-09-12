"""Operator CLI for append-only AVS-FIX-002 decisions and fills."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from pathlib import Path
from canonical_data.decision_outcome_ledger import DecisionOutcomeLedger, decision_record_v2, fill_record_v1

def main(argv=None) -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--ledger", type=Path, required=True); p.add_argument("--run-id", required=True)
    p.add_argument("--ticker", required=True); p.add_argument("--thesis-id", required=True)
    p.add_argument("--assessment-id", required=True); p.add_argument("--summary", required=True)
    p.add_argument("--response", choices=("TAKEN","NOT_TAKEN","DEFERRED"), required=True)
    p.add_argument("--occ-symbol"); p.add_argument("--price", type=float); p.add_argument("--quantity", type=int)
    args=p.parse_args(argv); now=datetime.now(timezone.utc).isoformat()
    ledger=DecisionOutcomeLedger(args.ledger)
    decision=decision_record_v2(run_id=args.run_id,ticker=args.ticker,thesis_id=args.thesis_id,
        occurred_at_utc=now,preferred_assessment_id=args.assessment_id,presentation_summary=args.summary,
        human_response=args.response)
    ledger.append(decision)
    if args.occ_symbol:
        if args.response != "TAKEN" or args.price is None or args.quantity is None:
            p.error("a fill requires TAKEN, --price and --quantity")
        ledger.append(fill_record_v1(run_id=args.run_id,ticker=args.ticker,thesis_id=args.thesis_id,
            occurred_at_utc=now,occ_symbol=args.occ_symbol,price=args.price,quantity=args.quantity,
            side="BUY",source="MANUAL_CONFIRMATION",previous_event_id=decision.event_id))
    print(ledger.event_counts(args.run_id)); return 0
if __name__ == "__main__": raise SystemExit(main())
