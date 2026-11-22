"""Bounded, receipt-verified local recovery. No DB writes/provider clients.

Writes overlays and a dated training pool, never patches stored/raw values or
backdates knowledge. Existing observations win over any conflicting archive.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from contextlib import closing
from datetime import date,datetime,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse,gzip,hashlib,json,sqlite3,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from contracts.option_profit_evidence import outcome,sessions_after,instant,digest
from contracts.option_profit_cohorts import decorate,maturity_coverage
from contracts.phantom_profit_shadow import write_packet,identity_ok
from scripts.research_option_profit_evidence import file_hash,db_state,guard,read_history

def raw_recovery(conn,wanted,journals,*,recorded,max_keys=5000,max_raw=500):
    ordered=sorted(wanted);keys=set(ordered[:max_keys]);missing=set();existing=0
    for ticker,day,symbol in keys:
        if conn.execute('SELECT 1 FROM chain_snapshots WHERE ticker=? AND quote_date=? AND option_symbol=?',
            (ticker,day,symbol)).fetchone():existing+=1
        else:missing.add((ticker,day,symbol))
    pairs={(t,d) for t,d,s in missing};candidates=[];errors=[];journal_refs=[]
    for path in map(Path,journals):
        journal_refs.append({'path':str(path.resolve()),'sha256':file_hash(path)})
        latest={}
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if not line.strip():continue
            r=json.loads(line)
            if (r.get('ticker'),r.get('day')) in pairs:latest[r.get('key') or digest(r)]=r
        for r in latest.values():
            if r.get('status')=='RECEIVED':candidates.append((path,r))
    recovered=defaultdict(list);seen=set();scanned=0
    for journal,r in candidates:
        raw=Path(r.get('raw') or '')
        if str(raw) in seen:continue
        if scanned>=max_raw:break
        seen.add(str(raw));scanned+=1
        try:
            expected=r.get('raw_sha256')
            if not expected:raise ValueError('RAW_RECEIPT_HASH_MISSING')
            if not raw.is_file():raise ValueError('RAW_ARCHIVE_MISSING')
            if file_hash(raw)!=expected:raise ValueError('RAW_RECEIPT_HASH_MISMATCH')
            body=json.loads(gzip.decompress(raw.read_bytes()));data=body.get('data',{})
            if body.get('http') not in (200,203) or data.get('s')!='ok':raise ValueError('UNSUCCESSFUL_RAW_RESPONSE')
            symbols=data.get('optionSymbol',[])
            def field(name,i):
                values=data.get(name,[])
                return values[i] if isinstance(values,list) and i<len(values) else None
            for i,symbol in enumerate(symbols):
                key=(r['ticker'],r['day'],symbol)
                if key not in missing:continue
                if not identity_ok(key[0],symbol):raise ValueError('UNKNOWN_MAPPING')
                updated=field('updated',i)
                if datetime.fromtimestamp(float(updated),ZoneInfo('America/New_York')).date().isoformat()!=key[1]:raise ValueError('RAW_QUOTE_SESSION_MISMATCH')
                underlying=field('underlying',i)
                if underlying and underlying not in (key[0],symbol[:-15]):raise ValueError('RAW_UNDERLYING_MISMATCH')
                q={'bid':field('bid',i),'ask':field('ask',i),'bid_size':field('bidSize',i),
                   'ask_size':field('askSize',i),'underlying_price':field('underlyingPrice',i),
                   'provider_at':datetime.fromtimestamp(float(updated),timezone.utc).isoformat(),
                   'available_at':recorded.isoformat()}
                recovered[key].append({'quote':q,'raw_path':str(raw.resolve()),'raw_sha256':expected,'journal':str(journal.resolve())})
        except (OSError,ValueError,TypeError,KeyError,OverflowError) as exc:errors.append({'raw':str(raw),'reason':str(exc)})
    overlays={};conflicts=[]
    for key,values in recovered.items():
        if len({digest(v['quote']) for v in values})!=1:conflicts.append({'key':list(key),'reason':'CONFLICTING_SAVED_RESPONSES'});continue
        overlays[key]=values[0]
    return overlays,{'wanted_keys':len(wanted),'checked_keys':len(keys),'unchecked_key_remainder':max(0,len(wanted)-len(keys)),
        'existing_rows_preserved':existing,'missing_rows_checked':len(missing),'raw_archives_checked':scanned,
        'raw_archive_remainder':max(0,len({str(r.get('raw')) for _,r in candidates})-scanned),
        'recovered_rows':len(overlays),'conflicts':conflicts,'archive_errors':errors,'journal_refs':journal_refs}

def recover(outcome_path,feature_path,verification,database,store,*,journals=(),max_keys=5000,max_raw=500):
    recorded=datetime.now(timezone.utc);source_sha=file_hash(outcome_path)
    source=json.loads(Path(outcome_path).read_text());proof=json.loads(Path(verification).read_text())
    if str(Path(feature_path).resolve())!=proof['entry_feature_copy'] or file_hash(feature_path)!=proof['entry_feature_copy_sha256']:
        raise ValueError('ENTRY_FEATURE_SOURCE_NOT_VERIFIED')
    matched=json.loads(Path(proof['source_report']).read_text())
    if file_hash(proof['source_report'])!=proof['source_report_sha256'] or source_sha!=matched['outcome_source_sha256']:
        raise ValueError('OUTCOME_SOURCE_NOT_VERIFIED')
    features=json.loads(Path(feature_path).read_text());as_of=date.fromisoformat(source['as_of_session']);wanted=set()
    for r in source['records']:
        for w in r['windows']:
            if w['window_end']>str(as_of) or w['expiry_truncated']:continue
            if w['state']=='UNASSESSED_ENTRY':wanted.add((r['ticker'],w['origin'],r['contract_symbol']))
            wanted.update((r['ticker'],d,r['contract_symbol']) for d in w.get('missing_sessions',[]))
    starts={}
    for r in source['records']:
        key=(r['ticker'],r['contract_symbol'])
        for w in r['windows']:starts[key]=min(starts.get(key,w['origin']),w['origin'])
    before=db_state(Path(database).resolve());rows=[];excluded=Counter();coverage=[]
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True,timeout=3)) as conn:
        conn.execute('PRAGMA query_only=ON')
        overlays,audit=raw_recovery(conn,wanted,journals,recorded=recorded,max_keys=max_keys,max_raw=max_raw)
        affected={(t,s) for t,d,s in overlays};histories={}
        for r in source['records']:
            ticker,symbol=r['ticker'],r['contract_symbol'];quotes=features.get(ticker+'|'+symbol,{})
            for w in r['windows']:
                item=dict(w);q=quotes.get(w['origin'],{})
                if (ticker,symbol) in affected:
                    key=(ticker,symbol)
                    if key not in histories:
                        # Exact bounded contract history, no whole-table scan.
                        hist,_=read_history(conn,ticker,symbol,date.fromisoformat(starts[key]),as_of,recorded)
                        for (t,d,s),v in overlays.items():
                            if (t,s)==key and d not in hist:hist[d]=v['quote']
                        histories[key]=hist
                    hist=histories[key]
                    item=outcome(symbol,date.fromisoformat(w['origin']),hist,as_of=as_of,horizon=r['horizon'],threshold=r['threshold'],
                        open_fee=w['open_fee'],close_fee=w['close_fee'])
                    q=overlays.get((ticker,w['origin'],symbol),{}).get('quote') or q
                item.update(entry_clock='CLOSE_BENCHMARK',assessment_session=str(as_of))
                decorated=decorate(item,ticker,q,training_available_at=recorded.isoformat(),assessment_session=str(as_of))
                coverage.append(decorated)
                if not decorated['fit_eligible']:continue
                if decorated['cohort_key'] is None:excluded.update(decorated['feature_reasons']);continue
                decorated.update(source_outcome_sha256=source_sha,entry_quote=q,
                    training_basis='RECOVERED_COMPLETE_OBSERVATIONS_NOT_HISTORICAL_DECISION_PROOF')
                rows.append(decorated)
    if before!=db_state(Path(database).resolve()):raise ValueError('LIVE_DATABASE_CHANGED_DURING_RECOVERY')
    pool=write_packet(Path(store)/'training_pools','TRAINING_POOL',{'recorded_at_utc':recorded.isoformat(),
        'basis':'RECOVERED_HISTORY_AVAILABLE_NOW_ONLY','source_outcomes_sha256':source_sha,
        'source_features_sha256':file_hash(feature_path),'rows':rows})
    overlay=write_packet(Path(store)/'recovery','RECOVERY_OVERLAY',{'recorded_at_utc':recorded.isoformat(),
        'rows':[{'ticker':k[0],'session':k[1],'symbol':k[2],**v} for k,v in sorted(overlays.items())]})
    report={'status':'BOUNDED_RECOVERY_REMAINDER' if audit['unchecked_key_remainder'] or audit['raw_archive_remainder'] else
        'COMPLETE_SAVED_INVENTORY_WITH_EXCLUSIONS' if audit['archive_errors'] or audit['missing_rows_checked']>audit['recovered_rows'] else 'COMPLETE_SAVED_RECOVERY_PASS',
        'recorded_at_utc':recorded.isoformat(),'training_pool':pool,'recovery_overlay':overlay,'training_rows':len(rows),
        'feature_exclusions':dict(excluded),'recovery':audit,'maturity_coverage':maturity_coverage(coverage),
        'promotions_enabled':False,'database_writes':0,'providers':0,'pipeline_runs':0,'lane_b_changes':0,
        'limitation':'No absent quote, missing size/spot or contemporaneous selection receipt is invented'}
    ref=write_packet(Path(store)/'recovery','RECOVERY_REPORT',{'recorded_at_utc':recorded.isoformat(),'rows':[],**report})
    compact={k:v for k,v in report.items() if k!='recovery'}
    compact['recovery']={k:v for k,v in audit.items() if k not in ('archive_errors','conflicts','journal_refs')}
    compact['archive_exclusions']=dict(Counter(r['reason'] for r in audit['archive_errors']))
    compact['conflicts']=len(audit['conflicts'])
    print(json.dumps({**compact,'report':ref},indent=2));return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('outcomes','features','verification','database','store'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--receipt-journal',action='append',type=Path,default=[])
    p.add_argument('--max-keys',type=int,default=5000);p.add_argument('--max-raw',type=int,default=500)
    a=p.parse_args();sys.addaudithook(guard)
    if a.max_keys<1 or a.max_raw<1:p.error('Positive bounded recovery limits required')
    recover(a.outcomes,a.features,a.verification,a.database,a.store,journals=a.receipt_journal,max_keys=a.max_keys,max_raw=a.max_raw)
if __name__=='__main__':main()
