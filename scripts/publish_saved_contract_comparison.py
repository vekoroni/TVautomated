"""Reuse-only inventory adapter. Output is new; source bytes are never changed."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from contracts.contract_comparison_inventory import SCHEMA,normalize_inventory

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()

def publish_saved_inventory(source,output):
    source=Path(source).resolve();output=Path(output).resolve()
    receipt=Path(str(output)+'.receipt.json');partial=Path(str(output)+'.partial')
    if source==output or any(p.exists() for p in (output,receipt,partial)):raise ValueError('CREATE_ONLY_OUTPUT_REQUIRED')
    if output.suffixes[-2:]!=['.jsonl','.gz']:raise ValueError('OUTPUT_MUST_BE_JSONL_GZ')
    output.parent.mkdir(parents=True,exist_ok=True)
    before=sha(source);counts=Counter();raw_digest=hashlib.sha256();iv_reasons=Counter()
    opener=gzip.open if source.suffix=='.gz' else open
    with opener(source,'rt',encoding='utf-8') as incoming, gzip.open(partial,'xt',encoding='utf-8',newline='\n') as outgoing:
        for line in incoming:
            raw=json.loads(line);view=normalize_inventory(raw);counts['ticker_records']+=1
            for side in ('CALL','PUT'):
                old=raw['available_contracts_both_sides'].get(side,{}).get('contracts',[])
                new=view['available_contracts_both_sides'][side]['contracts']
                assert len(old)==len(new)
                for q,n in zip(old,new):
                    # Saved JSON must remain exactly representable, never silently sanitized.
                    assert n['raw_observation']==q,'RAW_SAVED_OBSERVATION_CHANGED'
                    raw_digest.update(json.dumps(q,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
                    counts['quotes']+=1;counts[side+'_quotes']+=1
                    counts['raw_zero_iv']+=q.get('iv')==0
                    counts['zero_bid_preserved']+=q.get('bid')==0 and n['bid']==0
                    counts['iv_unavailable']+=n['iv'] is None
                    counts['missing_gate_evidence']+=n['gate_evidence_state']=='NOT_RECORDED_IN_SAVED_SCOPE'
                    if n['iv'] is None:iv_reasons[n['field_reasons']['iv']]+=1
                    if q.get('iv')==0:assert n['iv'] is None and n['field_reasons']['iv']=='NONPOSITIVE_RECORDED_IV'
            outgoing.write(json.dumps(view,separators=(',',':'),allow_nan=False)+'\n')
    if sha(source)!=before:raise ValueError('SOURCE_CHANGED_DURING_INVENTORY_ADAPTER')
    if output.exists():raise ValueError('CREATE_ONLY_OUTPUT_COLLISION')
    os.rename(partial,output)
    result={'schema':SCHEMA,'state':'COMPLETE','source':str(source),'source_sha256':before,
        'source_unchanged':True,'output':str(output),'output_sha256':sha(output),'counts':dict(counts),
        'iv_unavailable_reasons':dict(iv_reasons),'ordered_raw_observations_sha256':raw_digest.hexdigest(),
        'raw_observations_preserved':True,'provider_calls':0,'database_writes':0,
        'scope':'Whole recorded saved artifact; not unrestricted provider chains or reconstructed tested ladder.'}
    with receipt.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(publish_saved_inventory(args.source,args.output),indent=2))
