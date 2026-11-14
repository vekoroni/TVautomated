"""ACK 13 Nov: isolate bad market observations, never hide systemic corruption."""
from copy import deepcopy
import json
from pathlib import Path
import pandas as pd
import pytest
from domain.station_inspection import (StationDefect, station_policy, prepare_station,
    commit_station_quarantine, station_quarantines, enforce)

def frame(n=100):
    return pd.DataFrame({'ticker':[f'T{i}' for i in range(n)],
        'entry_price':['10']*n,'contract_bid':['1']*n,'contract_ask':['1.1']*n})

def prepare(data,**kwargs):
    return prepare_station('discovery',data,run_id='R',previous_tickers=None,
        accounted_tickers=None,now_utc='2026-11-13T02:00:00Z',**kwargs)

def test_single_bad_price_is_quarantined_without_mutating_other_facts():
    data=frame();data.loc[4,'entry_price']='0';before=data.copy(deep=True)
    clean,report=prepare(data)
    pd.testing.assert_frame_equal(data,before)
    pd.testing.assert_frame_equal(clean,data.drop(index=4).reset_index(drop=True))
    enforce(report)
    assert report['quarantine']['tickers']==['T4']
    assert report['input_rows']==100 and report['rows']==99
    assert report['quarantine']['records'][0]['checks']==['positive_prices']

@pytest.mark.parametrize('price',['-1','NaN','inf','garbage'])
def test_explicit_invalid_prices_are_not_usable(price):
    data=frame();data.loc[0,'entry_price']=price
    assert prepare(data)[1]['quarantine']['tickers']==['T0']

def test_tiny_positive_price_and_zero_bid_are_not_invented_defects():
    data=frame();data.loc[0,'entry_price']='0.0001';data.loc[1,'contract_bid']='0'
    clean,report=prepare(data)
    pd.testing.assert_frame_equal(clean,data)
    assert not report['quarantine']['records']

def test_crossed_quote_is_collated_for_any_ticker_including_nan_sym():
    data=frame(300);data.loc[0,'ticker']='NAN';data.loc[1,'ticker']='SYM'
    data.loc[:1,'contract_bid']='2'
    clean,report=prepare(data)
    assert report['quarantine']['tickers']==['NAN','SYM']
    assert len(clean)==298

@pytest.mark.parametrize('kind',['many','duplicate','invented','future','all_bad'])
def test_systemic_or_identity_failures_still_stop_without_filtering(kind):
    data=frame();kwargs={}
    if kind=='many':data.loc[:4,'entry_price']='0'
    if kind=='duplicate':data.loc[0,'ticker']='T1'
    if kind=='invented':kwargs['previous_tickers']={'OTHER'}
    if kind=='future':data['quote_timestamp_utc']='2099-01-01T00:00:00Z'
    if kind=='all_bad':data['entry_price']='0'
    base=dict(run_id='R',previous_tickers=None,accounted_tickers=None,now_utc='2026-11-13T02:00:00Z')
    base.update(kwargs)
    clean,report=prepare_station('discovery',data,**base)
    with pytest.raises(StationDefect):enforce(report)
    pd.testing.assert_frame_equal(clean,data)

def test_cumulative_quarantine_limit_cannot_be_reset_between_stations():
    data=frame(1000);data.loc[0,'entry_price']='0'
    _,report=prepare(data,prior_quarantined={'A','B','C','D','E'})
    with pytest.raises(StationDefect):enforce(report)

@pytest.mark.parametrize('suffix',['csv','json'])
def test_delivery_retains_exact_preimage_and_receipt_and_cannot_reintroduce(tmp_path,suffix):
    data=frame();data.loc[0,'entry_price']='0'
    clean,report=prepare(data)
    path=tmp_path/f'stage.{suffix}'
    if suffix=='csv':data.to_csv(path,index=False)
    else:path.write_text(json.dumps({'rows':data.to_dict('records'),'candidate_count':100,'other':'preserved'}))
    original=path.read_bytes()
    commit_station_quarantine(path,data,report,tmp_path)
    records=station_quarantines(tmp_path)
    assert len(records)==1 and records[0]['ticker']=='T0'
    assert (tmp_path/'diagnostics'/report['quarantine']['preimage_file']).read_bytes()==original
    if suffix=='csv':assert len(pd.read_csv(path))==99
    else:
        payload=json.loads(path.read_text());assert payload['candidate_count']==99 and payload['other']=='preserved'
    again,second=prepare_station('options',data,run_id='R',previous_tickers=None,accounted_tickers=None,
        prior_quarantined={'T0'},now_utc='2026-11-13T02:00:00Z')
    assert 'T0' not in again.ticker.tolist()

def test_missing_or_corrupt_quarantine_receipts_fail_closed(tmp_path):
    p=tmp_path/'diagnostics';p.mkdir()
    (p/'station_quarantine_discovery_R.json').write_text('{}')
    with pytest.raises((ValueError,KeyError)):station_quarantines(tmp_path)

def test_partial_delivery_is_not_a_committed_receipt(tmp_path,monkeypatch):
    data=frame();data.loc[0,'entry_price']='0';clean,report=prepare(data)
    path=tmp_path/'stage.csv';data.to_csv(path,index=False)
    import domain.station_inspection as module
    def fail(*args):raise OSError('simulated replacement failure')
    monkeypatch.setattr(module.os,'replace',fail)
    with pytest.raises(OSError):commit_station_quarantine(path,data,report,tmp_path)
    with pytest.raises(ValueError):station_quarantines(tmp_path)
    assert len(pd.read_csv(path))==100

def test_downstream_cannot_resurrect_previously_quarantined_identity():
    data=frame();data.loc[0,'entry_price']='10'
    clean,report=prepare_station('book',data,run_id='R',previous_tickers=set(data.ticker)-{'T0'},
        accounted_tickers={'T0'},prior_quarantined={'T0'},now_utc='2026-11-13T02:00:00Z')
    enforce(report)
    assert len(clean)==99 and report['quarantine']['records'][0]['checks']==['PREVIOUSLY_QUARANTINED_IN_RUN']

def test_bad_quote_nonfinite_and_secondary_geometry_does_not_hide_unrelated_defect():
    data=frame();data.loc[0,'contract_ask']='inf'
    assert prepare(data)[1]['quarantine']['tickers']==['T0']
    data=frame();data.loc[0,'entry_price']='0';data['direction']='CALL'
    data['target_price']='8';data['invalidation_price']='9'
    _,report=prepare(data)
    with pytest.raises(StationDefect):enforce(report)

def test_discovery_never_rounds_a_positive_reference_to_zero():
    # Pin the business expression without importing/running Discovery or providers.
    import ast
    tree=ast.parse((Path(__file__).parents[1]/'avshunter_discovery_ULTIMATE.py').read_text(encoding='utf-8-sig'))
    assignments=[n for n in ast.walk(tree) if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='current_price' for t in n.targets)]
    for node in assignments:
        if any(isinstance(x,ast.Name) and x.id=='px' for x in ast.walk(node.value)):
            assert eval(compile(ast.Expression(node.value),'<price>','eval'),{'px':0.0001})==0.0001

def test_lifecycle_records_exclusion_and_keeps_every_input():
    from domain.station_inspection import quarantine_lifecycle_rows
    rows=[{'ticker':t,'outcome':'SURVIVE','reason_code':'DISCOVERY_SURVIVOR',
        'lifecycle_state':'ACTIVE_CORE','next_stage':'PACKAGES'} for t in ('RBOT','NAN','SYM')]
    original=deepcopy(rows)
    out=quarantine_lifecycle_rows(rows,[{'ticker':'RBOT','station':'discovery','checks':['positive_prices']}])
    assert rows==original and len(out)==3
    assert out[0]['outcome']=='DROP' and out[0]['next_stage']==''
    assert out[1:]==rows[1:]
    with pytest.raises(ValueError):quarantine_lifecycle_rows(rows,[{'ticker':'OTHER','station':'discovery','checks':[]}])

def test_morning_score_integrity_accounts_for_known_exclusions_only():
    from morning_gate import _check_morning_handoff_score_integrity
    rows=[{'ticker':t,'scs_score':'10'} for t in ('RBOT','AAA','BBB')]
    result=_check_morning_handoff_score_integrity('R',rows,rows[1:],quarantined_tickers={'RBOT'})
    assert result['integrity_pass'] and result['accounted_quarantined_tickers']==['RBOT']
    assert not _check_morning_handoff_score_integrity('R',rows,rows[2:],quarantined_tickers={'RBOT'})['integrity_pass']

def test_orchestrator_boundary_commits_exclusion_instead_of_only_reporting(tmp_path):
    import ast,logging
    from types import SimpleNamespace
    path=Path(__file__).parents[1]/'intelligent_orchestrator.py'
    tree=ast.parse(path.read_text(encoding='utf-8-sig'))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_run_station_inspection')
    scope={'Path':Path,'Optional':__import__('typing').Optional,
        'cfg':SimpleNamespace(RUNS_DIR=tmp_path),'logger':logging.getLogger('quarantine_test'),
        '_read_stage_frame':lambda p:pd.read_csv(p,dtype=str,keep_default_na=False)}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),scope)
    data=frame();data.loc[0,'entry_price']='0';out=tmp_path/'output.csv';data.to_csv(out,index=False)
    assert scope['_run_station_inspection']('R','discovery',out)
    assert len(pd.read_csv(out))==99
    assert station_quarantines(tmp_path/'R')[0]['ticker']=='T0'

def test_source_change_after_inspection_is_not_quietly_filtered(tmp_path):
    data=frame();data.loc[0,'entry_price']='0';_,report=prepare(data)
    changed=data.copy();changed.loc[3,'entry_price']='999'
    path=tmp_path/'stage.csv';changed.to_csv(path,index=False)
    with pytest.raises(ValueError,match='SOURCE_VALUES_CHANGED'):
        commit_station_quarantine(path,data,report,tmp_path)
    assert len(pd.read_csv(path))==100

def test_quarantine_is_excluded_from_real_temporary_governed_worklist(tmp_path):
    from datetime import date
    from canonical_data.registry import CanonicalRegistry
    from canonical_data.discovery_publisher import publish_discovery_outcomes
    from canonical_data.lifecycle import LifecycleManager
    from canonical_data.contracts import DatasetType
    from domain.station_inspection import quarantine_lifecycle_rows
    rows=[{'ticker':t,'outcome':'SURVIVE','reason_code':'DISCOVERY_SURVIVOR',
        'lifecycle_state':'ACTIVE_CORE','next_stage':'PACKAGES'} for t in ('RBOT','NAN','SYM')]
    accepted=quarantine_lifecycle_rows(rows,[{'ticker':'RBOT','station':'discovery','checks':['positive_prices']}])
    registry=CanonicalRegistry(tmp_path/'control.sqlite')
    report=publish_discovery_outcomes(registry,run_id='R',session_date=date(2026,11,12),rows=accepted)
    worklist=LifecycleManager(registry).stage_worklist_tickers('R','PACKAGES',DatasetType.DAILY_OHLCV)
    assert set(worklist)=={'NAN','SYM'}
    assert report.input_count==3 and report.survivor_count==2 and report.drop_count==1

def test_early_entry_output_also_retains_subcent_precision():
    import ast
    tree=ast.parse((Path(__file__).parents[1]/'avshunter_discovery_ULTIMATE.py').read_text(encoding='utf-8-sig'))
    matched=0
    for node in ast.walk(tree):
        if not isinstance(node,ast.Dict):continue
        for key,value in zip(node.keys,node.values):
            if isinstance(key,ast.Constant) and key.value=='entry_price' and any(
                    isinstance(n,ast.Name) and n.id=='current_price' for n in ast.walk(value)):
                assert eval(compile(ast.Expression(value),'<early_price>','eval'),{'current_price':0.0001})==0.0001
                matched+=1
    assert matched>=1

def test_accepted_book_counts_match_delivered_rows(tmp_path):
    data=frame();data['lab_verdict']='GO';data.loc[0,'entry_price']='0'
    _,report=prepare(data);path=tmp_path/'book.json'
    path.write_text(json.dumps({'rows':data.to_dict('records'),'candidate_count':100,
        'verdict_counts':{'GO':100,'WAIT':0},'reconciliation':{'input_rows':100,'output_rows':100}}))
    commit_station_quarantine(path,data,report,tmp_path)
    book=json.loads(path.read_text())
    assert book['candidate_count']==book['verdict_counts']['GO']==book['reconciliation']['output_rows']==99
    assert book['reconciliation']['population_reconciled_with_quarantine']
    assert book['pre_quarantine_source_reconciliation']['output_rows']==100
