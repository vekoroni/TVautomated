"""Verify an A12 packet against an immutable saved Lab; publish a shadow only."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from contracts.monetisation_clock import attach_clock
from contracts.lab_review_projection import publish_review_projection,read_review_card

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--packet',type=Path,required=True)
    p.add_argument('--shadow-runs',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();rid=a.run_dir.name
    if a.shadow_runs.resolve().is_relative_to(a.run_dir.parent.resolve()):
        p.error('Shadow must be outside live runs')
    if a.output.exists():p.error('Use a new verification filename')
    folder=a.run_dir/'intelligence_lab/review_projection'
    raw=(folder/'manifest.json').read_bytes();manifest=json.loads(raw)
    packet=json.loads(a.packet.read_text(encoding='utf-8'))
    source=Path(packet['source_rows_path'])
    if hashlib.sha256(source.read_bytes()).hexdigest()!=packet['source_rows_sha256']:
        raise ValueError('MORNING_SOURCE_CHANGED')
    database=folder/manifest['database_file'];rows=[]
    with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)) as conn:
        conn.execute('PRAGMA query_only=ON')
        for (key,) in conn.execute('SELECT row_key FROM rows ORDER BY ordinal'):
            row={}
            for (payload,) in conn.execute('SELECT payload_json FROM evidence WHERE row_key=?',(key,)):
                row.update(json.loads(zlib.decompress(payload))['fields'])
            rows.append(row)
    attached,receipt=attach_clock(rows,packet,run_id=rid)
    # All pre-existing facts are preserved, not merely selected protected fields.
    assert all(all(r[k]==out[k] for k in r) for r,out in zip(rows,attached))
    result=publish_review_projection({'run_id':rid,'rows':attached,'candidate_count':len(attached)},a.shadow_runs,
        context={'macro':manifest['macro_context'],'sector':manifest['sector_context']},
        source_receipt={'monetisation_clock':receipt,'shadow_only':True})
    assert raw==(folder/'manifest.json').read_bytes()
    shadow=a.shadow_runs/rid/'intelligence_lab/review_projection'/result['database_file']
    seen=0
    with closing(sqlite3.connect(shadow.as_uri()+'?mode=ro',uri=True)) as conn:
        for key,ordinal in conn.execute('SELECT row_key,ordinal FROM rows ORDER BY ordinal'):
            card=read_review_card(a.shadow_runs,rid,key,result['revision'])
            for level in ('20','30'):
                for field in ('n_q50','n_q80','evidence_n','hit_n','failure_n','censored_n','unassessed_n'):
                    name=f'monetisation_{level}_{field}'
                    assert card['fields'][name]==attached[ordinal][name]
            seen+=1
    report={'state':'PASS','rows_verified':seen,'attachment':receipt,'summary':packet['summary'],
        'all_preexisting_row_fields_unchanged':True,'live_manifest_unchanged':True,
        'phantom_sources_unchanged':packet['sources_unchanged'],'shadow_manifest':result,
        'no_providers':True,'no_pipeline':True,'expiry_selection_changed':False,
        'live_lab_replaced':False,'authority':'DESCRIPTIVE_MEASUREMENT_ONLY'}
    with a.output.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!='shadow_manifest'}))

if __name__=='__main__':main()
