"""Production-shaped contexts, not a fabricated output alias, drive valuation."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import avshunter_options_intelligence as oi
from contracts.contract_rejection import classify_chain

def context(**changes):
    r=dict(ticker='XYZ',direction='CALL',spot=100.,entry=100.,structural_target=110.,
        stop=95.,stop_authoritative=True,stop_source='GOVERNED_TEST',horizon_bucket='1_5d',
        evidence_runway_sessions=10,_signal_row={'ticker':'XYZ','final_direction':'CALL'})
    r.update(changes);return r

@pytest.fixture
def model(monkeypatch):
    calls=[]
    def value(**kw):calls.append(kw);return {'emp_path_quality_flag':'OK','emp_path_r_central':.3}
    m=SimpleNamespace(path_inputs_from_options_row=lambda *a,**kw:
        dict(side='CALL',forecast_vol=.3,rate=.04,hold_sessions=10),compute_path_option_ev=value)
    monkeypatch.setattr(oi,'_contract_value_model',lambda:dict(module=m,settings={'paths':20,'seed':7},calibration={}))
    return calls

def test_actual_context_stop_reaches_valuer_without_output_alias(model):
    ctx=context();before=deepcopy(ctx)
    valuer=oi._default_contract_valuer(ctx)
    assert callable(valuer) and ctx==before and 'invalidation_spot' not in ctx
    valuer(dict(strike=100,dte=40,bid=3.8,ask=4.,iv=.3))
    assert model[0]['invalidation']==95.
    assert model[0]['hold_sessions']==10

@pytest.mark.parametrize('change',[{'stop':None},{'stop_authoritative':False},{'stop':105.},
                                  {'stop':float('nan')},{'stop':-1}])
def test_missing_unauthorised_and_wrong_side_stops_stay_unavailable(model,change):
    assert oi._default_contract_valuer(context(**change)) is None
    assert model==[]

def test_stale_output_alias_cannot_override_governed_stop(model):
    v=oi._default_contract_valuer(context(invalidation_spot=1.))
    v(dict(strike=100,dte=40,bid=3.8,ask=4.,iv=.3))
    assert model[0]['invalidation']==95.

def test_both_side_inventory_retains_raw_quotes_and_does_not_select():
    rows=[dict(symbol='XYZ270219C00100000',right='C',strike=100,expiry='2027-02-19',
        dte=40,delta=.5,bid=3.8,ask=4.,implied_vol=.3,mid=3.9,spread_pct=.05,
        quote_quality='TWO_SIDED',open_interest=500,quote_timestamp_utc='2026-11-20T21:00:00Z'),
        dict(symbol='XYZ270219P00100000',right='P',strike=100,dte=40,delta=-.5,
            bid=2.,ask=2.2,implied_vol=None,mid=2.1,spread_pct=.09,quote_quality='TWO_SIDED')]
    old=deepcopy(rows)
    result=classify_chain(rows,direction='CALL',dte_min=1,dte_max=100,delta_min=.2,delta_max=.75,spread_limit=.2)
    assert rows==old and result['contracts_side_correct_count']==1
    assert len(result['contracts_tested'])==1
    both=result['available_contracts_both_sides']
    assert both['CALL']['contracts'][0]['bid']==3.8
    assert both['CALL']['contracts'][0]['iv']==.3
    assert both['PUT']['contracts'][0]['iv'] is None
    assert both['PUT']['contracts'][0]['ask']==2.2
    assert both['PUT']['contracts'][0]['gate_failed'] is None

def test_inventory_truncation_is_per_side_and_explicit():
    r=dict(symbol='X',right='P',dte=40,delta=-.5,bid=2,ask=2.1,mid=2.05,spread_pct=.05)
    result=classify_chain([r,r,r],direction='CALL',dte_min=1,dte_max=100,delta_min=.2,delta_max=.75,spread_limit=.2,max_recorded=1)
    assert result['available_contracts_both_sides']['PUT']['truncated']
    assert result['available_contracts_both_sides']['PUT']['total_contracts']==3
    assert result['available_contracts_both_sides']['CALL']['state']=='NOT_PRESENT_IN_SAVED_CHAIN'
