"""Acquire exact completed SPY/QQQ chains through the existing canonical service, then derive advisory GEX."""
from pathlib import Path
from datetime import datetime,timezone,date
import sys,json,argparse
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from canonical_data.session_clock import session_snapshot
from orchestrator.completed_session_gex import refresh_completed_session_gex
from contracts.macro_feed_delivery import atomic_json

def main():
 from dotenv import load_dotenv
 load_dotenv(R/'.env',override=False)
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--session',default='latest-completed');a=p.parse_args()
 session=session_snapshot(datetime.now(timezone.utc)).last_completed_session if a.session=='latest-completed' else date.fromisoformat(a.session)
 result=refresh_completed_session_gex(repository_root=R,run_id='MACRO_REFERENCE_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S'),session_date=session,publish_macro_overlay=False)
 atomic_json(R/'dropbox/market_data/gex_acquisition_receipt.json',result)
 print(json.dumps(result,indent=2,default=str));return 0 if result['status']=='COMPLETE' else 2
if __name__=='__main__':raise SystemExit(main())
