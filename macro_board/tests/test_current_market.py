from copy import deepcopy
from macro_board import session_plan as sp

def payload():
    return {'built_at_utc':'2026-10-22T11:30:50Z','as_of_session':'2026-10-21',
            'settings':{'latest_stale_after_minutes':20},
            'review':{'session':'2026-10-21','headline':'QQQ accepted (up)',
                      'instruments':{'QQQ':{'key':'ACCEPTED_UP','close_pct':1.0549}}},
            'latest':{'segment':'PREMARKET','rows':{'QQQ':{'close':725.2,'price':712.75,
                'close_session':'2026-10-21','time_utc':'2026-10-22T11:15:00Z',
                'supersedes_close':True,'stale':False,'segment':'PREMARKET'}}}}

def test_qqq_gap_down_reassesses_bullish_completed_session():
    p=payload(); out=sp.current_market(p,['QQQ'])
    assert out['status']=='CURRENT'
    assert out['direction']=='DOWN'
    assert out['rows']['QQQ']['reversal'] is True
    assert out['rows']['QQQ']['erased_prior_move'] is True
    assert round(out['rows']['QQQ']['change_vs_close_pct'],2)==-1.72
    assert out['completed_session']=='2026-10-21'
    assert out['market_session']=='2026-10-22'
    assert out['acceptance']=='UNCONFIRMED'
    c=sp.market_call(p,{'direction':'UP'}, {}, {'approach':{'UP_UNKNOWN':'Buy pullbacks'},'focus':['QQQ']})
    assert c['key']=='CURRENT_DOWN'
    assert 'Buy pullbacks' not in c['approach']
    assert '2026-10-21' in c['sentences'][0]

def test_stale_missing_future_or_wrong_session_never_become_current_guidance():
    for mutation in ['stale','missing','future','wrong_session','expired','negative']:
        p=payload(); q=p['latest']['rows']['QQQ']
        if mutation=='stale': q['stale']=True
        if mutation=='missing': p['latest']['rows']={}
        if mutation=='future': q['time_utc']='2026-10-22T12:00:00Z'
        if mutation=='wrong_session': q['close_session']='2026-10-20'
        if mutation=='expired': q['time_utc']='2026-10-22T10:00:00Z'
        if mutation=='negative': q['price']=-1
        assert sp.current_market(p,['QQQ'])['status']=='UNAVAILABLE', mutation

def test_partial_focus_coverage_is_explicit_and_no_bullish_fallback():
    p=payload(); o=sp.current_market(p,['QQQ','SPY'])
    assert o['status']=='PARTIAL'
    assert o['missing']==['SPY']
    c=sp.market_call(p,{'direction':'UP'}, {}, {'focus':['QQQ','SPY'],'approach':{'UP_UNKNOWN':'Buy'}})
    assert c['key']=='CURRENT_UNAVAILABLE'

def test_matching_and_opposite_directions_are_symmetric():
    p=payload(); p['latest']['rows']['QQQ']['price']=730
    o=sp.current_market(p,['QQQ']); assert o['direction']=='UP' and not o['rows']['QQQ']['reversal']
    p['review']['instruments']['QQQ']={'key':'ACCEPTED_DOWN','close_pct':-1}
    assert sp.current_market(p,['QQQ'])['rows']['QQQ']['reversal']

def test_current_market_expires_at_the_exchange_session_boundary():
    p=payload()
    assert sp.current_market(p,['QQQ'])['segment_end_utc']=='2026-10-22T13:30:00+00:00'
    p['built_at_utc']='2026-10-22T13:31:00Z'
    p['latest']['rows']['QQQ']['time_utc']='2026-10-22T13:29:00Z'
    assert sp.current_market(p,['QQQ'])['status']=='UNAVAILABLE'

def test_historical_build_is_explicitly_historical():
    p=payload(); p['latest']={'status':'NOT_APPLICABLE_AS_OF_BUILD','rows':{}}
    assert sp.current_market(p,['QQQ'])['status']=='HISTORICAL'

def test_entire_plan_uses_current_prices_and_preserves_historical_reaction():
    from macro_board.tests.test_session_plan import _payload, CFG
    p=_payload(); live=payload()
    p.update({k:live[k] for k in ['built_at_utc','as_of_session','settings','latest']})
    p['decision_points']['next_session']='2026-10-22'
    q=p['latest']['rows']['QQQ']
    for t in ['SPY','IWM','DIA']:
        p['latest']['rows'][t]={**q,'price':98,'close':100}
    plan=sp.build(p,CFG)
    assert plan['call']['key']=='CURRENT_DOWN'
    assert plan['call']['tape']['direction']=='DOWN'
    assert plan['historical_tape']['direction']=='UP'
    assert plan['instruments']['QQQ']['reference']==712.75
    assert plan['instruments']['QQQ']['basis'].startswith('PREMARKET')
    reaction=next(x for x in plan['jigsaw']['pieces'] if x['key']=='reaction')
    assert reaction['points']=='UP' and reaction['stance']=='OPPOSES'
    p['latest']['rows']['QQQ']['stale']=True
    plan=sp.build(p,CFG)
    assert plan['call']['key']=='CURRENT_UNAVAILABLE'
    assert 'QQQ' not in plan['instruments']
