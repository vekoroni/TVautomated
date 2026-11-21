"""Frozen matched-cohort saved-data experiment. No production model hook."""
from __future__ import annotations
import argparse,json,sys,sqlite3,time
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from contracts.option_profit_cohorts import decorate,evaluate,POLICY
from contracts.option_profit_evidence import digest,instant
from scripts.research_option_profit_evidence import guard,file_hash,db_state
from contracts.phantom_prospective_evidence import availability_index,read_packet

def canonical(p):return Path(p) if Path(p).is_absolute() else ROOT/p

def feature_quotes(conn,ticker,symbol,origins):
    # Exact PK point reads: no whole-history scan and no inferred ticker alias.
    pk=[r[2] for r in conn.execute('PRAGMA index_info(sqlite_autoindex_chain_snapshots_1)')]
    hint=' INDEXED BY sqlite_autoindex_chain_snapshots_1' if pk==['ticker','quote_date','option_symbol'] else ''
    out={}
    for day in sorted(set(origins)):
        rows=conn.execute('SELECT bid,ask,bid_size,ask_size,underlying_price FROM chain_snapshots'+hint+
            ' WHERE ticker=? AND quote_date=? AND option_symbol=?',(ticker,day,symbol)).fetchall()
        if len(rows)==1:out[day]=dict(zip(('bid','ask','bid_size','ask_size','underlying_price'),rows[0]))
    return out

def run(source,database,output,prospective_paths=()):
    source=source.resolve();database=database.resolve();output=output.resolve()
    if output.exists() or output.is_relative_to(ROOT):raise ValueError('New output outside production required')
    started=time.monotonic();raw=json.loads(source.read_text(encoding='utf-8'))
    if raw.get('promotion_enabled') is not False or raw.get('providers')!=0:raise ValueError('Saved-only shadow source required')
    prior={str(canonical(k)):v for k,v in raw['database_after'].items()}
    before=db_state(database)
    if before!=prior:raise ValueError('DATABASE_CHANGED_SINCE_OUTCOME_REPLAY')
    source_hash=file_hash(source)
    code={str(p):file_hash(p) for p in (Path(__file__),ROOT/'contracts/option_profit_cohorts.py',
        ROOT/'contracts/phantom_prospective_evidence.py')}
    source_files={str(canonical(k)):v for k,v in raw['source_hashes_unchanged'].items()}
    if not all(file_hash(p)==v for p,v in source_files.items()):raise ValueError('SOURCE_CODE_OR_INPUT_CHANGED_SINCE_REPLAY')
    # Conservatively use current saved input mtime; never backdate a later
    # selected universe to its historical option prices. Archived ticket dates
    # alone are not proof of contemporaneous selection availability.
    universe_times=[datetime.fromtimestamp(Path(p).stat().st_mtime,timezone.utc).isoformat()
        for p in source_files if Path(p).name.startswith('options_intelligence_') and p.endswith('.csv')]
    universe_at=max(universe_times) if universe_times else None
    prospective=availability_index(prospective_paths)
    prospective_hashes={}
    for p in prospective_paths:
        packet=read_packet(p,kind='PREDICTIONS')
        for path in (Path(p),Path(packet['candidate_packet_path'])):
            prospective_hashes[str(path.resolve())]=file_hash(path)
    grouped=defaultdict(list)
    for record in raw['records']:grouped[(record['ticker'],record['contract_symbol'])].append(record)
    experiments=defaultdict(list);inputs=[];conn=None;count=0
    try:
        for i,((ticker,symbol),records) in enumerate(sorted(grouped.items())):
            if i%100==0:
                if conn:conn.close()
                conn=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=3);conn.execute('PRAGMA query_only=ON')
            origins=[w['origin'] for r in records for w in r['windows']]
            quotes=feature_quotes(conn,ticker,symbol,origins)
            inputs.append({'ticker':ticker,'contract_symbol':symbol,'entry_features_sha256':digest(quotes),
                           'requested_origin_dates':len(set(origins)),'found_origin_dates':len(quotes)})
            for record in records:
                known=universe_at if any(x['source']=='SAVED_PIPELINE_ROW' for x in record['source_identities']) else None
                for window in record['windows']:
                    q=quotes.get(window['origin'],{})
                    if window.get('entry_ask') is not None and q.get('ask')!=window['entry_ask']:
                        raise ValueError('ENTRY_QUOTE_CHANGED_SINCE_OUTCOME_REPLAY')
                    receipt=prospective.get((ticker,symbol))
                    row=decorate(window,ticker,q,universe_known_at=receipt['known_at'] if receipt else known,
                        eligible_from_session=receipt['earliest_entry_session'] if receipt else None)
                    name=f'{round(row["threshold"]*100)}_H{row["horizon"]}_{row["side"]}'
                    experiments[name].append(row);count+=1
            if (i+1)%300==0:print('Entry features',i+1,'/',len(grouped),flush=True)
    finally:
        if conn:conn.close()
    analyses={}
    for name,rows in sorted(experiments.items()):
        print('Chronological matched test',name,'windows',len(rows),flush=True)
        analyses[name]=evaluate(rows)
    after=db_state(database)
    if before!=after or file_hash(source)!=source_hash or not all(file_hash(p)==v for p,v in {**code,**prospective_hashes}.items()):
        raise ValueError('SOURCE_CHANGED_DURING_EXPERIMENT')
    report={'status':'MATCHED_COHORT_SHADOW_TESTED_PROMOTIONS_BLOCKED','promotion_enabled':False,
        'created_at_utc':datetime.now(timezone.utc).isoformat(),'policy':POLICY,'policy_sha256':digest(POLICY),
        'outcome_source':str(source),'outcome_source_sha256':source_hash,'source_code_sha256':code,
        'source_files_sha256':source_files,'entry_feature_receipts':inputs,'experiments':analyses,
        'windows':count,'contract_identities':len(grouped),'database_before':before,'database_after':after,
        'selection_universe_available_at_conservative':universe_at,
        'prospective_publication_references':list(prospective.values()),
        'prospective_packet_file_hashes':prospective_hashes,
        'source_mapping_exclusions':raw['mapping_exclusions'],
        'source_missing_selected_contracts':len(raw['missing_selected_contracts']),
        'providers':0,'pipeline_runs':0,'database_writes':0,'lane_b_changes':0,
        'limitations':['Historical outcome windows are drawn from a later selected universe, not the full contemporaneous opportunity set',
            'Archived historical ticket dates lack independent contemporaneous universe-availability receipts',
            'Snapshot underlying price has no independent spot-timestamp proof; no computed Greek/IV is used as an entry feature',
            'Retrospective availability-unproven diagnostics are never activation evidence',
            'No contemporaneous macro, catalyst or thesis state is fabricated from the current Lab',
            'Daily close observed-bid outcomes are not intraday first passage or actual fills',
            'Distinct thresholds/horizons/sides are separate experiments, not independent sample counts'],
        'elapsed_seconds':round(time.monotonic()-started,3)}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as f:json.dump(report,f,separators=(',',':'),allow_nan=False)
    print(json.dumps({'output':str(output),'windows':count,'seconds':report['elapsed_seconds'],
        'experiments':{k:{'strict_n':v['point_in_time_oos']['n'],
            'retrospective_n':v['retrospective_diagnostic_only']['n'],'validation_passed':v['validation_passed'],
            'blockers':v['promotion_blockers']} for k,v in analyses.items()}},indent=2))
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('source','database','output'):p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--prospective-publication',type=Path,action='append',default=[])
    args=p.parse_args();sys.addaudithook(guard);run(args.source,args.database,args.output,args.prospective_publication)
if __name__=='__main__':main()
