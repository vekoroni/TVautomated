from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from flask import Flask
from contracts.lab_macro_desk import project, publish, read_publication, register_routes
from contracts.lab_market_mentality import trade_context


def observed_board(up=False):
    session = '2026-10-16'
    sign = 1 if up else -1
    states = {'market_breadth': 'HIGH' if up else 'LOW', 'credit': 'TIGHTENING' if up else 'WIDENING',
              'market_trend': 'ABOVE_LONG_ONLY', 'market_vol': 'LOW'}
    return {'board_version': 'macro-board-v1.0.0', 'as_of_session': session,
            'built_at_utc': '2026-10-18T12:00:00Z', 'build': {'kind': 'OFF_SESSION'},
            'conditions': {'current': states,
                           'observations': {k: {'inputs': [{'input': 'fixture', 'observed': session}], 'sessions_old': 0} for k in states}},
            'etfs': {t: {'metrics': {'status': 'FRESH', 'last_session': session,
                                    'ret_1d': sign if t in ('SPY','QQQ','IWM','DIA') else 1,
                                    'ret_5d': sign*2}}
                     for t in ('SPY','QQQ','IWM','DIA','XLP','XLU','XLE')},
            'review': {'session': session, 'instruments': {'DIA': {'gap_pct': .8, 'open_to_close_pct': -1.2, 'threshold_pct': .3}}},
            'intel': {'vix_engine': [{'VIX_Obs_Date': session, 'VIX_Direct': 20, 'VIX_Momentum': 'RISING'}]},
            'external': {'vix_engine': {'status': 'FRESH', 'as_of': '2026-10-16T20:00:00Z'}}}


def test_separate_axes_do_not_turn_quiet_vol_into_complacency_or_urgency():
    result = project(observed_board())['mentality']
    assert result['axes']['confidence']['label'] == 'FRAGILE_SELECTIVE'
    assert result['axes']['fear']['label'] == 'CONCERN_SUGGESTED'
    assert result['axes']['directional_progress']['label'] == 'SELLING_PROGRESS_1D_5D'
    assert result['axes']['urgency']['label'] == 'INSUFFICIENT_EXECUTION_EVIDENCE'
    assert result['axes']['positioning']['label'] == 'UNKNOWN'
    assert 'selectivity' in result['headline'].lower()
    assert result['axes']['fear']['contrary_evidence_ids'] == ['condition:market_vol']


def test_broad_buying_is_descriptive_not_prediction():
    result = project(observed_board(True))['mentality']
    assert result['axes']['confidence']['label'] == 'BROAD_PARTICIPATION'
    assert result['axes']['directional_progress']['label'] == 'BUYING_PROGRESS_1D_5D'


@pytest.mark.parametrize('changes',[{'built_at_utc':'2026-10-16T12:00:00Z'},
                                    {'as_of_session':'2026-10-17'}])
def test_future_cash_response_is_not_inferred_before_session_close(changes):
    data=observed_board();data.update(changes)
    with pytest.raises(ValueError,match='closed XNYS session'):project(data)


def test_daily_attempt_does_not_assert_intraday_acceptance_or_actual_trapped_positions():
    item = project(observed_board())['mentality']['attempt_response'][0]
    assert item['instrument'] == 'DIA'
    assert 'actual positions are unknown' in item['possible_consequence']
    assert 'Intraday acceptance' in item['limit']


@pytest.mark.parametrize('missing', ['date', 'future', 'stale'])
def test_bad_clocks_are_excluded_from_interpretation(missing):
    data = observed_board()
    if missing == 'date':
        data['conditions']['observations'] = {}
    elif missing == 'future':
        for item in data['conditions']['observations'].values(): item['inputs'][0]['observed']='2026-10-19'
    else:
        for item in data['conditions']['observations'].values(): item['sessions_old']=50
    out = project(data)
    assert out['mentality']['axes']['confidence']['label']=='UNRESOLVED'
    assert not any(e['usable'] for e in out['evidence'] if e['id'].startswith('condition:'))


def test_future_or_undated_vix_is_not_used_as_observed_fear():
    for change in ({'VIX_Obs_Date':'2026-10-19'}, {'VIX_Obs_Date':None}):
        data=observed_board();data['intel']['vix_engine'][0].update(change)
        assert project(data)['mentality']['axes']['fear']['label']=='NOT_DIRECTLY_MEASURED'
    data=observed_board();data['external']['vix_engine']['as_of']='2026-10-19T20:00:00Z'
    assert project(data)['mentality']['axes']['fear']['label']=='NOT_DIRECTLY_MEASURED'


def test_partial_price_coverage_and_small_moves_do_not_invent_conviction():
    data=observed_board()
    for ticker in ('SPY','QQQ'):
        data['etfs'][ticker]['metrics']['last_session']='2026-10-15'
    assert project(data)['mentality']['axes']['directional_progress']['label']=='UNRESOLVED'
    data=observed_board()
    for item in data['etfs'].values(): item['metrics']['ret_1d']=-.25
    assert project(data)['mentality']['axes']['directional_progress']['label']=='UNRESOLVED'


def test_news_positioning_narrative_and_authority_fields_are_not_independent_evidence():
    data=observed_board();before=deepcopy(data)
    first=project(data)
    data['intel']['packet']={'notes':'PANIC CAPITULATION BUY NOW', 'regime_probability':.999}
    data['positioning']={'crowded':True, 'forced_sellers':True}
    data['authority']='AUTOMATIC_EXECUTION'
    second=project(data)
    assert first==second
    assert before['conditions']==data['conditions']


def test_evidence_references_are_resolvable_and_usable():
    out=project(observed_board());ids={item['id'] for item in out['evidence'] if item['usable']}
    claims=list(out['mentality']['axes'].values())+out['mentality']['behaviours']
    for item in claims:
        assert set(item['supporting_evidence_ids']+item['contrary_evidence_ids']) <= ids
    assert all(set(item['evidence_ids'])<=ids for item in out['mentality']['attempt_response']+out['mentality']['reaction_sensitivities'])
    credit=next(e for e in out['evidence'] if e['id']=='condition:credit')
    assert 'not a measured credit spread' in credit['definition']


def test_same_data_republication_is_idempotent_and_refresh_is_not_a_new_reaction(tmp_path):
    data=observed_board();first=publish(data,tmp_path)
    assert publish(data,tmp_path)==first
    data['built_at_utc']='2026-10-19T08:00:00Z'
    second=publish(data,tmp_path)
    assert second['revision']!=first['revision']
    assert second['changes']['state']=='UNCHANGED_OBSERVATIONS'
    assert read_publication(tmp_path,first['revision'])==first
    assert second['changes']['previous_revision']==first['revision']
    assert len(list((tmp_path/'mentality_history').glob('*.json')))==2


def test_same_session_correction_is_not_described_as_new_market_reaction(tmp_path):
    data=observed_board();publish(data,tmp_path)
    data['etfs']['SPY']['metrics']['ret_1d']=-1.2
    out=publish(data,tmp_path)
    assert out['changes']['state']=='SAME_SESSION_DATA_REVISION'


def test_invalid_older_and_concurrent_publication_preserves_last_good(tmp_path):
    data=observed_board();first=publish(data,tmp_path)
    data['built_at_utc']='2026-10-17T12:00:00Z'
    with pytest.raises(ValueError,match='Older board'):publish(data,tmp_path)
    assert read_publication(tmp_path)==first
    (tmp_path/'lab_mentality_publish.lock').write_text('another writer')
    with pytest.raises(FileExistsError):publish(observed_board(),tmp_path)
    assert read_publication(tmp_path)==first


def test_tampering_rejected_and_get_is_read_only(tmp_path):
    first=publish(observed_board(),tmp_path)
    app=Flask(__name__);register_routes(app,tmp_path);client=app.test_client()
    with patch('socket.socket',side_effect=AssertionError('No providers')):
        assert client.get('/api/lab/macro-context').status_code==200
        assert client.get('/api/lab/macro-context?revision='+first['revision']).status_code==200
    first['mentality']['headline']='FORGED'
    (tmp_path/'lab_macro_latest.json').write_text(json.dumps(first))
    assert client.get('/api/lab/macro-context').status_code==503
    assert client.get('/api/lab/macro-context?revision=../../secrets').status_code==503


@pytest.mark.parametrize('side',['CALL','PUT','',None,'STRANGLE'])
def test_trade_overlay_never_assigns_direction_or_rewrites_frozen_fields(side):
    fields={'ticker':'NAN','direction':side,'lab_verdict':'MANUAL_REVIEW'};before=deepcopy(fields)
    out=trade_context(project(observed_board()),fields,'FROZENREV')
    assert fields==before and out['saved_direction']==side
    assert out['frozen_mentality_state']=='NOT_RECORDED_WITH_THIS_REVIEW'
    assert out['review_revision']=='FROZENREV' and 'not evidence used' in out['disclosure']


def test_trade_overlay_is_pinned_to_exact_frozen_row_and_does_not_republish(tmp_path):
    from contracts.lab_review_projection import publish_review_projection,read_review_rows
    runs=tmp_path/'runs';output=tmp_path/'macro'
    receipt=publish_review_projection({'run_id':'TEST','candidate_count':1,'rows':[{'ticker':'SYM','direction':'CALL','sector':'Technology'}]},runs)
    row=read_review_rows(runs,'TEST')['rows'][0]
    first=publish(observed_board(),output)
    app=Flask(__name__);register_routes(app,output,runs);client=app.test_client()
    url='/api/lab/TEST/rows/'+row['row_key']+'/mentality?revision='+receipt['revision']
    reply=client.get(url)
    assert reply.status_code==200 and reply.json['ticker']=='SYM'
    assert reply.json['latest_mentality_revision']==first['revision']
    assert client.get(url.replace(receipt['revision'],'0'*32)).status_code==409
    assert read_review_rows(runs,'TEST')['revision']==receipt['revision']
