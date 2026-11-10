"""Publish validated data-only macro and an offline board; no model calls or new AI decisions."""
from pathlib import Path
from datetime import datetime,timezone
import copy,hashlib,json,sys,shutil
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R))
import build_macro_json as builder
from contracts.macro_health import capture_research_context,attach_research_context,assess_macro_health
from contracts.us_money_index_contract import load_us_money_index_sidecar,attach_us_money_index
from contracts.macro_feed_delivery import atomic_json
from domain.macro_input_governance import build_macro_input_manifest,build_macro_prompt_context
from canonical_data.macro_input_manifest import publish_macro_input_manifest
from canonical_data.macro_publication import publish_macro_projections
from canonical_data.macro_packet_archive import archive_macro_packet
from scripts.macro_quant_packet import build_macro_quant_packet

class DataOnlyPublicationDisabled(ValueError):
    """FULL publication belongs exclusively to the scheduled AI runner."""

def publication_mode(root):
    config=json.loads((root/'config/macro_delivery_v1.json').read_bytes())
    mode=config.get('publication_mode')
    if mode not in {'FULL','DATA_ONLY'}:
        raise ValueError('publication_mode must explicitly be FULL or DATA_ONLY')
    return mode

def require_data_only_mode(root):
    if publication_mode(root)!='DATA_ONLY':
        raise DataOnlyPublicationDisabled('publication_mode is FULL; data-only publication is disabled')

def accepted_hashes(root):
    p=root/'data/macro/delivery/accepted.json'
    return {k:v['sha256'] for k,v in json.loads(p.read_bytes()).items()} if p.exists() else {}

def load_publication_seed(root):
    """Recover only the previously receipted, hash-verified AI base; never synthesize."""
    require_data_only_mode(root)
    target=root/'dropbox/macro/macro_intelligence_latest.json'
    if target.is_file():
        return json.loads(target.read_bytes())
    receipt=json.loads((root/'data/macro/delivery/data_only_publication_receipt.json').read_bytes())
    digest=receipt['prior_ai_packet_sha256']
    if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('Invalid receipted AI base identity')
    raw=(root/'data/macro/publication_bases'/(digest+'.json')).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest:
        raise ValueError('AI recovery archive hash mismatch')
    seed=json.loads(raw)
    if seed.get('_builder_metadata',{}).get('build_mode')=='DATA_ONLY' or not builder.validate_macro_json(seed)[0]:
        raise ValueError('AI recovery archive is not a validated original analysis')
    seed=copy.deepcopy(seed)
    seed['_builder_metadata'].update(build_mode='DATA_ONLY',prior_ai_packet_sha256=digest)
    return seed

def publication_is_current(current,root,macro_hash,*,require_board):
    if current.get('_builder_metadata',{}).get('delivery_accepted_hashes')!=accepted_hashes(root):return False
    if not require_board:return True
    receipt=root/'data/macro/delivery/data_only_board_receipt.json'
    return receipt.exists() and json.loads(receipt.read_bytes()).get('macro_sha256')==macro_hash

def resolve_analysis_base(current, root):
    require_data_only_mode(root)
    meta=current.get('_builder_metadata',{})
    if meta.get('build_mode')!='DATA_ONLY':
        raise ValueError('Data-only publication requires an explicitly archived AI base')
    digest=meta['prior_ai_packet_sha256']
    path=root/'data/macro/publication_bases'/(digest+'.json')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('AI archive hash mismatch')
    base=json.loads(raw)
    if base.get('_builder_metadata',{}).get('build_mode')=='DATA_ONLY':raise ValueError('Cannot chain data-only AI bases')
    if not builder.validate_macro_json(base)[0]:raise ValueError('AI archive schema invalid')
    return base,digest

def publish():
    require_data_only_mode(R)
    macro_dir=R/'dropbox/macro';target=macro_dir/'macro_intelligence_latest.json'
    current=load_publication_seed(R)
    prior,prior_hash=resolve_analysis_base(current,R)
    analysis_at=prior['_builder_metadata']['built_at']
    payload=builder.load_data_payload(R/'dropbox/market_data')
    bound=capture_research_context(macro_dir)
    for feed,entry in bound.items():
     assert entry['status']=='AVAILABLE'
     key=feed+'_research_advisory';payload['data'][key]=entry['packet']
     payload['files_found'].append(Path(entry['source_path']).name)
     payload.setdefault('files_found_by_key',{})[key]=entry['source_path']
    usmi_path=macro_dir/'avshunter_us_money_index.json';usmi=load_us_money_index_sidecar(usmi_path)
    payload['data']['us_money_index_advisory']=usmi
    payload['files_found'].append(usmi_path.name);payload['files_found_by_key']['us_money_index_advisory']=str(usmi_path)
    payload['input_manifest']=build_macro_input_manifest(payload['files_found_by_key'],payload['files_missing'],data=payload['data'])
    m=builder.apply_market_data_overrides(copy.deepcopy(prior),payload)
    m=builder.apply_macro_input_governance(m,payload)
    m=attach_us_money_index(m,usmi);m=attach_research_context(m,macro_dir,bound=bound)
    protected=['regime_label','regime_state','regime_probability','macro_conviction','risk_on_off_switch','dir_bias','sector_lead','sector_avoid','horizon_routing','macro_filter','trigger_required','size_multiplier','capital_grade','execution_permission']
    assert all(m.get(key)==prior.get(key) for key in protected),'A source refresh must not generate new AI decisions or permissions'
    builder.validate_macro_output_coherence(m,payload)
    assert builder.validate_macro_json(m)[0]
    now=datetime.now(timezone.utc).isoformat()
    ledger=build_macro_prompt_context(payload)['input_consumption_ledger']
    for entry in ledger.values():entry.update(model_consumed=False,data_consumed=entry.get('status')=='CONSUMED')
    metadata=copy.deepcopy(prior['_builder_metadata']);metadata.update(built_at=now,built_by='validated data-only refresh through existing macro builder/publication functions',build_mode='DATA_ONLY',analysis_built_at=analysis_at,data_refreshed_at_utc=now,model_called=False,synthesis_status='NOT_REFRESHED_USER_REQUESTED_DATA_ONLY',prior_ai_packet_sha256=prior_hash,prior_ai_input_manifest_id=prior['_builder_metadata']['input_manifest_id'],files_used=payload['files_found'],files_used_by_key=payload['files_found_by_key'],files_missing=payload['files_missing'],input_manifest_id=payload['input_manifest']['manifest_id'],input_manifest_sha256=payload['input_manifest']['manifest_sha256'],input_manifest=payload['input_manifest'],input_consumption_ledger=ledger,input_consumption_status='DATA_REFRESH_COMPLETE_AI_NOT_REFRESHED',schema_validation='PASS',validation='DEGRADED',update_mode='DATA_ONLY_PRIOR_AI_ANALYSIS_REUSED')
    metadata['delivery_accepted_hashes']=accepted_hashes(R)
    m['_builder_metadata']=metadata
    report=payload['data'].get('report_json') or {};report=json.loads(report) if isinstance(report,str) else report
    m['macro_health']=assess_macro_health(m,report=report)
    m['macro_health']['status']='DEGRADED';m['macro_health']['issues'].append('AI_SYNTHESIS_NOT_REFRESHED')
    m['macro_health']['source_health']['synthesis']={'status':'NOT_REFRESHED','analysis_built_at':analysis_at,'data_refreshed_at_utc':now,'reason':'USER_REQUESTED_DATA_ONLY'}
    require_data_only_mode(R)  # Recheck before the first publication write.
    manifest=publish_macro_input_manifest(payload['input_manifest'],builder.PIPELINE_MACRO_DIR/'input_manifests',macro_dir/'macro_input_manifest_latest.json',evidence_root=builder.PIPELINE_MACRO_DIR/'input_evidence')
    atomic_json(target,m)
    archive=archive_macro_packet(build_macro_quant_packet(m,target),builder.PIPELINE_MACRO_DIR/'archive')
    projection=publish_macro_projections(target)
    cfg=json.loads((R/'macro_board/config/macro_board_config_v1.json').read_text(encoding='utf-8'))
    cfg['day_story']['ai_narrative']['enabled']=False
    atomic_json(R/'data/macro/delivery/data_only_board_config.json',cfg)
    receipt={'status':'DATA_REFRESH_COMPLETE_AI_NOT_REFRESHED','data_refreshed_at_utc':now,'analysis_built_at':analysis_at,'prior_ai_packet_sha256':prior_hash,'current_packet_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'input_manifest':manifest,'archive':archive,'projection':projection,'protected_ai_decisions_unchanged':protected}
    atomic_json(R/'data/macro/delivery/data_only_publication_receipt.json',receipt)
    print(json.dumps({k:receipt[k] for k in ['status','data_refreshed_at_utc','analysis_built_at','current_packet_sha256']},indent=2))


def main():
    import argparse,os,subprocess
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--board',action='store_true');p.add_argument('--if-changed',action='store_true');args=p.parse_args()
    if publication_mode(R)=='FULL':
        print('SKIPPED: publication_mode is FULL; the scheduled Windows runner owns AI and board publication')
        return 0
    target=R/'dropbox/macro/macro_intelligence_latest.json'
    current=load_publication_seed(R)
    current_hash=hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
    if args.if_changed and current_hash and publication_is_current(current,R,current_hash,require_board=args.board):
        print('UNCHANGED: accepted feeds already published');return 0
    lock=R/'data/macro/delivery/data_only_publication.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:print('DEFERRED: data-only publication already locked');return 3
    try:
        os.write(fd,str(os.getpid()).encode());os.close(fd)
        publish()
        if args.board:
            require_data_only_mode(R)
            subprocess.run([sys.executable,'-B','-m','macro_board','--config',str(R/'data/macro/delivery/data_only_board_config.json')],cwd=R,check=True)
            board=R/'macro_board/output/etf_macro_board.html'
            require_data_only_mode(R)
            atomic_json(R/'data/macro/delivery/data_only_board_receipt.json',{'macro_sha256':hashlib.sha256((R/'dropbox/macro/macro_intelligence_latest.json').read_bytes()).hexdigest(),'board_sha256':hashlib.sha256(board.read_bytes()).hexdigest(),'published_at_utc':datetime.now(timezone.utc).isoformat(),'mode':'DATA_ONLY_OFFLINE'})
        return 0
    except DataOnlyPublicationDisabled as error:
        print('SKIPPED: '+str(error));return 0
    finally:lock.unlink(missing_ok=True)

if __name__=='__main__':raise SystemExit(main())
