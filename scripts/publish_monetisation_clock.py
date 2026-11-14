"""A12 saved-data measurement export. No providers, pipeline or database writes.

Creates a NEW sidecar outside the saved run; never replaces a previous packet.
"""
from __future__ import annotations
import argparse
import csv
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from avshunter.c12_outcome.monetisation import measure_contract_history
from avshunter.c12_outcome.adapters.monetisation_history import SavedMonetisationHistory,instant
from domain.option_valuation import valuation_policy
from contracts.monetisation_clock import clock_fields

def _metadata(path):
    if not path.exists():return None
    s=path.stat()
    with path.open('rb') as f:head=hashlib.sha256(f.read(4096)).hexdigest()
    return {'bytes':s.st_size,'mtime_ns':s.st_mtime_ns,'header_sha256':head}

def _digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda:stream.read(1024*1024),b''):h.update(part)
    return h.hexdigest()

def publish_saved_clock(run_dir,database,*,as_of,decision_cutoff,observation_sessions=None):
    root=Path(run_dir).resolve();rid=root.name;db=Path(database).resolve()
    cfg=json.loads((ROOT/'config/monetisation_clock_v1.json').read_text(encoding='utf-8'))
    horizon=cfg['observation_sessions'] if observation_sessions is None else observation_sessions
    if type(horizon) is not int or horizon<1:raise ValueError('Positive observation sessions required')
    if decision_cutoff is None or decision_cutoff.tzinfo is None:raise ValueError('Decision cutoff must have a timezone')
    if as_of>decision_cutoff.date():raise ValueError('Evidence session cannot follow the decision cutoff')
    source=root/'morning_validation'/f'morning_validated_trades_{rid}.csv'
    pol=valuation_policy();before={str(p):_metadata(p) for p in (db,Path(str(db)+'-wal'),source)}
    source_hash=_digest(source);records=[];cache={};start=time.monotonic()
    old=csv.field_size_limit();csv.field_size_limit(max(old,64*1024*1024))
    try:
        with source.open(encoding='utf-8-sig',newline='') as stream:
            inputs=list(csv.DictReader(stream))
        reader=None
        try:
            for i,row in enumerate(inputs):
                if i%100==0:
                    if reader:reader.__exit__()
                    reader=SavedMonetisationHistory(db,lookback_days=cfg['lookback_calendar_days'],close_tolerance_seconds=cfg['close_quote_tolerance_seconds'])
                    reader.__enter__()
                ticker=row.get('ticker','');symbol=row.get('contract_symbol') or ''
                stamp=instant(row.get('validation_evidence_cutoff_utc') or row.get('quote_provider_timestamp_utc') or row.get('anticipated_valued_at_utc'))
                cutoff=min(stamp,decision_cutoff) if stamp else decision_cutoff
                bar=str(row.get('bar_data_asof') or '')[:10]
                bad_reference=False
                try:observed=min(as_of,date.fromisoformat(bar)) if bar else as_of
                except ValueError:observed=as_of;bad_reference=True
                key=(ticker,symbol,observed.isoformat(),cutoff.isoformat(),horizon,bad_reference)
                if key not in cache:
                    history,receipt=reader.read(ticker,symbol,as_of=observed,decision_cutoff=cutoff) if symbol and not bad_reference else ({},{'saved_exact_rows':0,'reason':'INVALID_REFERENCE_OR_NO_SELECTED_CONTRACT'})
                    measurement=measure_contract_history(symbol,history,as_of=observed,observation_sessions=horizon,
                        open_fee=pol['fee_usd_per_contract_open'],close_fee=pol['fee_usd_per_contract_close'])
                    if bad_reference:measurement['state']='UNASSESSED_INVALID_EVIDENCE_SESSION'
                    cache[key]={'measurement':measurement,'source_receipt':receipt}
                records.append({'source_row_ordinal':i,'ticker':ticker,'thesis_id':row.get('thesis_id'),
                    'trade_idea_id':row.get('trade_idea_id'),'contract_symbol':symbol,**cache[key],
                    'published_fields':clock_fields(cache[key]['measurement'])})
                if (i+1)%250==0:print('A12 measured',i+1,'rows in',round(time.monotonic()-start,1),'seconds',flush=True)
        finally:
            if reader:reader.__exit__()
    finally:csv.field_size_limit(old)
    after={str(p):_metadata(p) for p in (db,Path(str(db)+'-wal'),source)}
    if before!=after or _digest(source)!=source_hash:raise ValueError('SOURCE_CHANGED_DURING_MEASUREMENT')
    summary={}
    for level in ('20','30'):
        rr=[r['measurement']['levels'][level] for r in records]
        summary[level]={'rows_with_n':sum(r['n_q50'] is not None for r in rr),
            'row_states':dict(Counter(r['state'] for r in rr)),
            **{f:sum(r[f] for r in rr) for f in ('evidence_n','hit_n','failure_n','censored_n','unassessed_n')}}
    packet={'schema':'monetisation_clock_packet_v1','item':'A12','run_id':rid,'authority':'DESCRIPTIVE_MEASUREMENT_ONLY',
        'state':'SAVED_MEASUREMENT_NOT_VALIDATED_FORECAST','as_of_session':as_of.isoformat(),
        'decision_cutoff_utc':decision_cutoff.isoformat(),'observation_sessions':horizon,
        'observation_window_is_not_a_hold_limit':True,'expiry_selection_owner':'CLAUDE_LANE_B',
        'fees':{'open_per_contract':pol['fee_usd_per_contract_open'],'close_per_contract':pol['fee_usd_per_contract_close'],'basis':pol['fee_basis']},
        'config':cfg,'source_rows_sha256':source_hash,'source_rows_path':str(source),
        'source_database_before':before,'source_database_after':after,'sources_unchanged':True,
        'row_count':len(records),'summary':summary,'records':records,
        'limitations':['No actual fill or intraday first-passage proof.',
            'Quantiles condition on observed historical hits, not an 80% success probability.',
            'Exact contract history spans changing DTE/moneyness; not a row-conditioned predictive model.',
            'Missing paths may be informative; counts stay visible and no calibrated probability is published.',
            'No Lane B stop, scale, roll, trigger or expiry policy is reconstructed.',
            'Evidence totals across current rows are not independent observations.']}
    packet['content_sha256']=hashlib.sha256(json.dumps(packet,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return packet

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--database',type=Path,required=True);p.add_argument('--as-of-session',required=True)
    p.add_argument('--decision-cutoff-utc',required=True);p.add_argument('--observation-sessions',type=int)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.resolve().is_relative_to(a.run_dir.resolve()):p.error('Output must be outside the immutable saved run')
    if a.output.exists():p.error('Output exists; use a new revision filename')
    packet=publish_saved_clock(a.run_dir,a.database,as_of=date.fromisoformat(a.as_of_session),
        decision_cutoff=instant(a.decision_cutoff_utc),observation_sessions=a.observation_sessions)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as stream:json.dump(packet,stream,separators=(',',':'),allow_nan=False)
    print(json.dumps({'output':str(a.output),'rows':packet['row_count'],'summary':packet['summary'],'sources_unchanged':True}))

if __name__=='__main__':main()
