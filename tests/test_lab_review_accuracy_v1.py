"""Display corrections never alter the governed trade or invent economics."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def test_sector_aliases_group_for_filter_without_changing_source_labels(tmp_path):
    p=importlib.import_module('contracts.lab_review_projection')
    b={'run_id':'TEST','candidate_count':3,'rows':[
        {'ticker':'A','sector':'Technology','direction':'CALL','lab_rank':1},
        {'ticker':'B','sector':'Information Technology','direction':'PUT','lab_rank':2},
        {'ticker':'C','sector':'Consumer Cyclical','direction':'CALL','lab_rank':3}]}
    frozen=deepcopy(b);receipt=p.publish_review_projection(b,tmp_path)
    rows=p.read_review_rows(tmp_path,'TEST',sector='Information Technology')['rows']
    assert [r['ticker'] for r in rows]==['A','B']
    assert rows[0]['sector']=='Technology' and rows[0]['display_sector']=='Information Technology'
    counts={r['sector']:r['total_theses'] for r in receipt['sector_distribution']}
    assert counts=={'Information Technology':2,'Consumer Discretionary':1}
    assert b==frozen

def test_legacy_value_is_reference_only_and_missing_basis_is_not_invented():
    m=importlib.import_module('contracts.lab_review_display')
    r={'anticipated_value_multiple_q50':3.15,'lab_verdict':'GO','lab_rank':1}
    before=deepcopy(r);state=m.valuation_disclosure(r)
    assert state['state']=='REFERENCE_BASIS_NOT_RECORDED'
    assert 'valuation_cost_basis' in state['missing_fields']
    assert r==before

def priced():
    return {'contract_symbol':'ABC270115C00100000','anticipated_contract_symbol':'ABC270115C00100000',
      'anticipated_value_multiple_q50':1.2,'scenario_target_return_on_premium':.2,
      'valuation_model':'AMERICAN_CRR','valuation_version':'option_valuation_v1',
      'valuation_cost_basis':'ASK_PLUS_FEES','valuation_entry_cost_usd_per_share':4.2,
      'anticipated_contract_basis':'MORNING_REPRICED:ABC270115C00100000',
      'anticipated_valued_at_utc':'2026-10-09T14:00:00Z','valuation_rate_annual':.04,
      'valuation_rate_basis':'TEST_RATE','valuation_dividend_yield_annual':0.,'valuation_dividend_basis':'ASSUMED_ZERO:TEST'}

def test_complete_basis_is_named_reference_and_quote_age_never_vetoes():
    m=importlib.import_module('contracts.lab_review_display');r=priced()
    r['quote_freshness']='VERY_OLD';r['lab_verdict']='GO'
    assert m.valuation_disclosure(r)['state']=='MORNING_REFERENCE'
    assert r['lab_verdict']=='GO'

def test_scenario_contradiction_and_wrong_contract_are_explicit():
    m=importlib.import_module('contracts.lab_review_display');r=priced()
    r['scenario_target_return_on_premium']=.7
    assert m.valuation_disclosure(r)['state']=='VALUE_SCENARIO_MISMATCH'
    r=priced();r['anticipated_contract_symbol']='OTHER'
    assert m.valuation_disclosure(r)['state']=='VALUED_CONTRACT_MISMATCH'

def test_sector_context_alias_attaches_bias_without_fabricating_returns(tmp_path):
    m=importlib.import_module('contracts.lab_review_sources');root=tmp_path/'TEST';root.mkdir()
    (root/'macro_snapshot.json').write_text(json.dumps({'sector_rotation':{
        'sector_bias_map':{'Technology':'TAILWIND'}}}))
    b={'run_id':'TEST','candidate_count':1,'rows':[{'ticker':'A','sector':'Technology'}]}
    _,ctx,_=m.prepare_review_publication(b,root)
    s=ctx['sector']['rows'][0]
    assert s['sector']=='Information Technology' and s['proxy']=='XLK'
    assert s['daily_pct'] is None and s['money_flow'] is None

def test_review_ui_discloses_historical_basis_and_moves_to_selected_card():
    js=(Path(__file__).resolve().parents[1]/'intelligence-lab/static/review-app.js').read_text()
    assert 'valuation_disclosure' in js and 'scrollIntoView' in js
    assert 'Historical/reference value' in js and 'Reference economics' in js
