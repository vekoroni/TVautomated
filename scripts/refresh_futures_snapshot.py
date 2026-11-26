"""Refresh delayed futures and, optionally, all live market groups before publication.

Append a snapshot with parent lineage. Other source timestamps are untouched.
During reopening poll until a new-session bar arrives or the bounded deadline;
on failure publish the explicit pending/stale/missing state.
"""
import argparse,copy,hashlib,importlib.util,json,sys,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from contracts.futures_freshness import CONFIG,classify_futures_quote

def collector():
    spec=importlib.util.spec_from_file_location('futures_capture',ROOT/'Enhancements/colab/avshunter_market_intelligence_v5_4_3.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def refresh_document(document, *, history=None, now=None, all_market_data=False, marketdata_key=None, http_get=None, completion_clock=None):
    m=collector();now=now or datetime.now(timezone.utc)
    result=copy.deepcopy(document)
    if all_market_data:
        from canonical_data.session_clock import session_snapshot,session_bounds
        session=session_snapshot(now).last_completed_session
        result['us_reference_session']=session.isoformat()
        result['us_reference_close_utc']=session_bounds(session)[1].isoformat().replace('+00:00','Z')
    close=datetime.fromisoformat(result['us_reference_close_utc'].replace('Z','+00:00'))
    ext=m.OvernightExtractor(now_utc=now,history=history,marketdata_key=marketdata_key,http_get=http_get)
    observed={}
    for group in (m.OVERNIGHT_SINCE_US_CLOSE if all_market_data else ('us_futures','rates_commodities')):
        observed[group]=[(sym,name,ext._closes(sym,'5d','5m')) for sym,name in m.OVERNIGHT_SINCE_US_CLOSE[group]]
        result.setdefault('groups',{})[group]=[
            m.measure_since_us_close(sym,name,bars,close,now)
            for sym,name,bars in observed[group]]
        result.setdefault('summary',{})[group]=m.summarise_group(result['groups'][group])
    if all_market_data:
        session=result['us_reference_session']
        result['groups']['volatility']=ext._volatility(session,close)
        result['groups']['us_premarket']=ext._premarket(session,close)
        for region,items in m.OVERNIGHT_SESSIONS.items():
            result['groups'][region]=[m.local_session_reading(sym,name,ext._closes(sym,'10d','1d'),now,tz,o,c,
                intraday=ext._closes(sym,'1d','5m')) for sym,name,tz,o,c in items]
        if completion_clock is not None:
            completed=completion_clock()
            if completed < now: raise ValueError('Collection completion precedes collection start')
            now=completed
            # Reclassify the same captured bars against actual completion, without
            # changing their timestamps or admitting quotes beyond that clock.
            for group,items in observed.items():
                result['groups'][group]=[m.measure_since_us_close(sym,name,bars,close,now) for sym,name,bars in items]
        result['summary']={group:m.summarise_group(rows) for group,rows in result['groups'].items()}
        result['as_of_utc']=now.isoformat().replace('+00:00','Z')
        result['market_refresh']={'as_of_utc':result['as_of_utc'],'groups_refetched':list(result['groups']),
            'observation_time_policy':'SOURCE_TIMESTAMPS_UNCHANGED_BY_TRANSPORT','errors':list(ext.errors)}
    result['futures_refresh']={'as_of_utc':now.isoformat().replace('+00:00','Z'),
        'authority':'DISPLAY_ONLY','errors':ext.errors}
    if all_market_data:
        import os
        if os.environ.get('AVSH_RUN_SESSION')=='OffSession':
            from contracts.macro_closed_market import capture
            closed=capture(ROOT/'dropbox/market_data',now)
            if closed:result['closed_market']=closed
        else:
            result.pop('closed_market',None)
        from contracts.macro_collection_health import assess_collection
        result['market_refresh']['collection_assessment']=assess_collection(result,now)
    return result

def refresh_until_ready(document, *, history=None, clock=None, sleep=None, max_wait_seconds=0, all_market_data=False, marketdata_key=None):
    clock=clock or (lambda:datetime.now(timezone.utc));sleep=sleep or time.sleep
    start=clock();attempts=0
    while True:
        now=clock();result=refresh_document(document,history=history,now=now,all_market_data=all_market_data,marketdata_key=marketdata_key,completion_clock=clock if all_market_data else None);attempts+=1
        rows=[x for g in ('us_futures','rates_commodities') for x in result['groups'][g]]
        in_reopening=classify_futures_quote(now,now-timedelta(days=1))['state']=='REOPEN_PENDING'
        pending=any(x['state']=='REOPEN_PENDING' for x in rows) or (in_reopening and any(x['state']!='OK' for x in rows))
        remaining=max_wait_seconds-(clock()-start).total_seconds()
        if not pending or remaining<=0: break
        sleep(min(CONFIG['refresh_poll_seconds'],remaining))
    result['futures_refresh']['attempts']=attempts
    result['futures_refresh']['status']='AVAILABLE' if all(x['state']=='OK' and not x['stale'] for x in rows) else 'DEGRADED'
    return result

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir',type=Path,default=ROOT/'dropbox/market_data')
    p.add_argument('--max-wait-seconds',type=int,default=CONFIG['refresh_max_wait_seconds'])
    p.add_argument('--all-market-data',action='store_true',help='Refetch FX, volatility, ETF quotes and regional sessions as well as futures')
    args=p.parse_args(argv)
    marketdata_key=None
    if args.all_market_data:
        from dotenv import load_dotenv
        import os
        load_dotenv(ROOT/'.env',override=False)
        marketdata_key=os.environ.get('MARKETDATA_API_KEY')
    paths=sorted(args.input_dir.glob('overnight_????????_??????.json'),key=lambda x:x.stat().st_mtime,reverse=True)
    if not paths:
        print('FUTURES MISSING: no overnight snapshot; macro health will report missing coverage');return 2
    raw=paths[0].read_bytes();document=json.loads(raw.decode('utf-8-sig'))
    result=refresh_until_ready(document,max_wait_seconds=max(0,min(args.max_wait_seconds,CONFIG['refresh_max_wait_seconds'])),all_market_data=args.all_market_data,marketdata_key=marketdata_key)
    result['futures_refresh']['parent_file']=paths[0].name
    result['futures_refresh']['parent_sha256']=hashlib.sha256(raw).hexdigest()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    target=args.input_dir/f'overnight_{stamp}.json'
    if target.exists():
        print('FUTURES refresh collision; original preserved');return 2
    temporary=target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    temporary.replace(target)
    print('FUTURES '+result['futures_refresh']['status']+': '+str(target))
    for warning in (result.get('market_refresh',{}).get('collection_assessment') or {}).get('warnings',[]):
        print('WARNING: '+warning['code']+'; fallback='+warning['fallback_source']+'; observed='+str(warning.get('observed_session') or warning.get('fallback_last_bar_utc')))
    return 0 if result['futures_refresh']['status']=='AVAILABLE' else 2

if __name__=='__main__': raise SystemExit(main())
