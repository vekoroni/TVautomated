"""Export saved pipeline evidence, not a Lane B strategy or a pipeline run.

Usage: python -B scripts/export_claude_evidence_handoff.py --run-dir <saved run>
       --output <new research/handoff JSON path>
Never calls providers, writes databases, or overwrites a previous export.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from contracts.handoff_reliability import reliability_fields
from domain.macro_advisory_context import project_usmi_context
from domain.sector_resolution import resolve_sector


def _receipt(path, root):
    if not path.is_file(): return {'path':path.relative_to(root).as_posix(),'state':'MISSING'}
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda:stream.read(1024*1024),b''):digest.update(part)
    return {'path':path.relative_to(root).as_posix(),'state':'SAVED',
            'sha256':digest.hexdigest(),'bytes':path.stat().st_size}


def build_saved_handoff(run_dir):
    root=Path(run_dir).resolve(); rid=root.name
    candidate=root/'forecast/behavioural_candidate_packet_v1/candidates.csv'
    morning=root/'morning_validation'/f'morning_validated_trades_{rid}.csv'
    macro=root/'interpreter/interpreter_macro_context.json'
    catalyst=root/'catalysts'/f'catalyst_truth_{rid}.csv'
    sources=[candidate,morning,macro,catalyst]
    before=[_receipt(p,root) for p in sources]
    out={'schema':'pipeline_claude_evidence_v1','run_id':rid,'authority':'DATA_AND_DISCLOSURE_ONLY',
         'strategy_owner':'CLAUDE_LANE_B','source_receipts':before,
         'pre_option_candidates':[],'morning_assessments':[],'typed_catalysts':[], 'macro_context':None,
         'clock_rule':'Evidence, quote and assessment epochs are independent; no implied live countdown.',
         'valuation_rule':'Conditional modelled payoff is not expected return or an observed fill.'}
    old_limit=csv.field_size_limit();csv.field_size_limit(max(old_limit,64*1024*1024))
    try:
        if macro.is_file():out['macro_context']=json.loads(macro.read_text(encoding='utf-8-sig'))
        if candidate.is_file():
            with candidate.open(encoding='utf-8-sig',newline='') as stream:
                for row in csv.DictReader(stream):
                    fields={k:v for k,v in row.items() if k in {'Ticker','Thesis_ID','Thesis_Side','Spine_Role','As_Of','Timeframe','Readiness','Trigger_Level','Invalidation_Level','Outcome_Level','Data_Status','Direction_Status'} or k.startswith(('Duration_Level_','Duration_'))}
                    out['pre_option_candidates'].append({'source':before[0], 'values':fields})
        if morning.is_file():
            with morning.open(encoding='utf-8-sig',newline='') as stream:
                for row in csv.DictReader(stream):
                    facts={k:v for k,v in row.items() if k in {'ticker','thesis_id','contract_symbol','verdict','trade_idea_id','bar_data_asof','expiry','dte','contract_dte','selected_quote_timestamp_utc','quote_provider_timestamp_utc','anticipated_valued_at_utc','validation_evidence_cutoff_utc','valuation_model','valuation_cost_basis','valuation_rate_basis','valuation_dividend_basis','scenario_exit_sessions','scenario_exit_date','valuation_time_basis'} or k.startswith(('anticipated_evidence_','scenario_','contract_repair_','contract_bid','contract_ask'))}
                    usmi=project_usmi_context(packet=out['macro_context'] or {}, sector=resolve_sector(row),
                        industry=str(row.get('industry') or ''), direction=str(row.get('final_direction') or row.get('direction') or ''))
                    out['morning_assessments'].append({'source':before[1],'values':facts,'reliability':reliability_fields(row),
                        'usmi_advisory':usmi,'macro_source':before[2]})
        if catalyst.is_file():
            with catalyst.open(encoding='utf-8-sig',newline='') as stream:
                for row in csv.DictReader(stream):
                    out['typed_catalysts'].append({k:row.get(k) for k in ('ticker','catalyst_type','catalyst_date','catalyst_data_quality','catalyst_requires_live_confirmation','catalyst_source_fields')})
    finally:csv.field_size_limit(old_limit)
    after=[_receipt(p,root) for p in sources]
    if before!=after:raise ValueError('SOURCE_CHANGED_DURING_EXPORT')
    out['state']='PARTIAL_MISSING_SOURCES' if any(r['state']=='MISSING' for r in before) else 'SAVED_EVIDENCE_EXPORTED_NOT_VALIDATION'
    out['counts']={k:len(out[k]) for k in ('pre_option_candidates','morning_assessments','typed_catalysts')}
    out['content_sha256']=hashlib.sha256(json.dumps(out,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.resolve().is_relative_to(args.run_dir.resolve()):
        parser.error('Use a new output outside the saved run; source artifacts must stay immutable.')
    result=build_saved_handoff(args.run_dir)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,allow_nan=False)
    print(json.dumps({'state':result['state'],'counts':result['counts'],'content_sha256':result['content_sha256'],'output':str(args.output)}))

if __name__=='__main__':main()
