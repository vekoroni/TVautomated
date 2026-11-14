"""ACK: exactly 508 frozen path gaps, same shared 30,000-credit cap."""
from datetime import date,datetime
from pathlib import Path
import argparse,json,re,sys
HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))
import phantom_named_contract_supplement_20261113 as m

class PathScope:
    job='PHANTOM_PATH_SUPPLEMENT_20261113'
    count=508
    target_hash='9524678ac5622f201c41cd84611763b7113db6b7e18ee1e95543a80b97eafad3'
    def __init__(self):
        source=m.g.EXTERNAL/'OPTION_PATH_GAP_WORKLIST_20261113.json'
        raw=json.loads(source.read_text());targets=[{k:r[k] for k in ('ticker','day','symbol')} for r in raw['request_keys']]
        if len(targets)!=self.count or m.g.digest(m.g.encoded(targets))!=self.target_hash:raise RuntimeError('FROZEN_508_PATH_WORKLIST_CHANGED')
        self.keys={(t['ticker'],t['day'],t['symbol']) for t in targets}
        self.allowed_days=set(m.ALLOWED_DAYS)|{t['day'] for t in targets}
        if '2026-11-12' in self.allowed_days:raise ValueError('12 November deferred')
        self.manifest={'job':self.job,'entry_count':self.count,'targets':targets,'target_hash':self.target_hash,'cap':m.g.CAP,'source':str(source),'scope':'508 exact absent post-entry path quotes; excludes existing no-bid and 12 November','created':m.g.now()}
    def check_target(self,t):
        if (t['ticker'],t['day'],t['symbol']) not in self.keys or t['day']=='2026-11-12':raise ValueError('Outside approved 508 exact path keys')
        match=re.fullmatch(r'([A-Z0-9.]+)(\d{6})([CP])(\d{8})',t['symbol'])
        if not match:raise ValueError('Malformed exact OCC')
        m.g.check_identity(t['ticker'],match[1],t['symbol'])
        expiry=datetime.strptime(match[2],'%y%m%d').date();dte=(expiry-date.fromisoformat(t['day'])).days
        if dte<0:raise ValueError('Expired path observation cannot be requested')
        return match,expiry,dte

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true')
    raise SystemExit(m.run(parser.parse_args().execute,scope=PathScope()))
