"""Saved/synthetic counterexamples are tests, never approved market judgements."""
from copy import deepcopy
import socket

import pytest

from macro_board.cycle_governance import validate_input, resolve, classify, option_payoff, governance
from macro_board.cycle_io import digest
from macro_board.cycle_narrative import assemble, validate, tripwires
from macro_board.operating_cycle import load_policy
from macro_board.cycle_scoring import score_calls


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Network forbidden'))


def rule(**extra):
    return {'series': 'HY_OAS', 'unit': 'percent', 'source': 'saved_FRED',
            'window_start_utc': '2026-11-26T12:00:00Z', 'window_end_utc': '2026-12-18T21:00:00Z',
            'sampling': 'AT_DEADLINE', 'vintage': 'AS_READ', 'operator': 'GE', 'level': 4.47, **extra}


def observation(**extra):
    return {'series': 'HY_OAS', 'unit': 'percent', 'source': 'saved_FRED', 'value': 4.47,
            'observed_at_utc': '2026-12-18T21:00:00Z', 'published_at_utc': '2026-12-19T12:00:00Z',
            'status': 'OK', 'source_sha256': 'a' * 64, 'vintage': 'AS_READ', **extra}


def author():
    return {'input_contract_version': 'macro_research_input_v2', 'authority': 'ADVISORY_ONLY',
            'author': 'TEST_FIXTURE', 'as_of_utc': '2026-11-26T12:00:00Z',
            'authored_at_utc': '2026-11-26T12:00:00Z', 'evidence_cutoff_utc': '2026-11-25T21:00:00Z',
            'approval': {'state': 'RESEARCH_DRAFT'}, 'event_forecasts': [], 'market_scenarios': {'partition': 'NOT_ASSERTED'}, 'etf_book': []}


def test_draft_is_never_approval_and_forged_legacy_label_is_ignored():
    a = author(); validate_input(a)
    assert governance(a, {}, load_policy())['approval_state'] == 'RESEARCH_DRAFT'
    a.pop('input_contract_version'); a['approval'] = {'state': 'ACK_APPROVED_ADVISORY'}
    assert governance(a, {}, load_policy())['approval_state'] == 'RESEARCH_DRAFT'


def test_approval_binds_contents_and_clock():
    a = author(); content = deepcopy(a); content.pop('approval')
    a['approval'] = {'state': 'ACK_APPROVED_ADVISORY', 'approved_by': 'ACK',
                     'approved_at_utc': '2026-11-26T13:00:00Z', 'content_sha256': digest(content)}
    validate_input(a)
    a['author'] = 'Changed'
    with pytest.raises(ValueError, match='bind'): validate_input(a)


def test_probability_contradiction_is_rejected_not_renormalised():
    a = author()
    a['event_forecasts'] = [{'call_id': k, 'probability': p, 'resolution': rule()} for k, p in [('cool', .6), ('hot', .4), ('hawkish_OR', .2)]]
    a['probability_constraints'] = [{'left': 'cool', 'right': 'hot', 'relationship': 'COMPLEMENT'},
                                    {'left': 'hot', 'right': 'hawkish_OR', 'relationship': 'IMPLIES'}]
    with pytest.raises(ValueError, match='smaller'): validate_input(a)
    a['event_forecasts'][2]['probability'] = .5; validate_input(a)


def test_credit_uses_direct_spread_not_alert_proxy_and_exact_baseline():
    r = rule(change_from_baseline=True, baseline={'value': 3.72, 'observed_at_utc': '2026-11-24T21:00:00Z', 'source_sha256': 'b' * 64}, level=.75)
    now = '2026-12-19T13:00:00Z'
    assert resolve(r, [observation()], now)['outcome'] is True
    assert resolve(r, [observation(series='VIXCLS', value=40)], now)['status'] == 'UNASSESSED_OUTCOME'
    alert = tripwires({'wrong_worlds': [{'call_id': 'credit', 'tripwire': {'series': 'VIXCLS', 'operator': 'GE', 'level': 32}}]}, {'VIXCLS': {'status': 'OK', 'value': 40}})
    assert alert[0]['fired'] is True


@pytest.mark.parametrize('change', [{'source': 'other'}, {'unit': 'bp'}, {'status': 'STALE'}, {'source_sha256': 'bad'}, {'published_at_utc': '2026-12-20T00:00:00Z'}])
def test_missing_wrong_stale_or_late_sources_never_resolve(change):
    assert resolve(rule(), [observation(**change)], '2026-12-19T13:00:00Z')['outcome'] is None


def test_first_release_is_not_latest_revision():
    assert resolve(rule(vintage='FIRST_PUBLISHED'), [observation()], '2026-12-19T13:00:00Z')['outcome'] is None
    assert resolve(rule(vintage='FIRST_PUBLISHED'), [observation(vintage='FIRST_PUBLISHED')], '2026-12-19T13:00:00Z')['outcome'] is True


def test_crossing_requires_complete_path_for_a_negative_not_positive():
    r = rule(sampling='ANY_CROSSING')
    assert resolve(r, [observation(value=4)], '2026-12-19T13:00:00Z')['status'] == 'UNASSESSED_INCOMPLETE_PATH'
    assert resolve(r, [observation(value=5)], '2026-12-19T13:00:00Z')['outcome'] is True


def test_oil_requires_benchmark_and_cannot_resolve_on_yields():
    with pytest.raises(ValueError, match='Oil'): resolve(rule(asset_class='OIL'), [], '2026-12-19T13:00:00Z')
    r = rule(asset_class='OIL', benchmark='BRENT', contract='F27', roll_rule='NO_ROLL', settlement='ICE_CLOSE')
    assert resolve(r, [observation(series='DGS10')], '2026-12-19T13:00:00Z')['outcome'] is None


def scenarios():
    return {'partition': 'ORDERED_EXHAUSTIVE', 'horizon_utc': '2026-12-18T21:00:00Z',
        'metric_definitions': {'SPY_return': {'kind': 'ABSOLUTE_RETURN', 'etf': 'SPY', 'baseline_session': '2026-11-25'},
                               'SMH_relative_SPY': {'kind': 'RELATIVE_RETURN', 'etf': 'SMH', 'benchmark': 'SPY', 'baseline_session': '2026-11-25'}}, 'worlds': [
        {'world_id': 'riskoff', 'probability': .25, 'conditions': [{'metric': 'SPY_return', 'operator': 'LE', 'level': -.05}]},
        {'world_id': 'rotation', 'probability': .25, 'conditions': [{'metric': 'SMH_relative_SPY', 'operator': 'LE', 'level': -.02}]},
        {'world_id': 'recovery', 'probability': .25, 'conditions': [{'metric': 'SMH_relative_SPY', 'operator': 'GE', 'level': .02}]},
        {'world_id': 'mixed', 'probability': .25, 'residual': True}]}


def test_overlap_precedence_none_residual_and_missing_not_residual():
    s = scenarios(); now = '2026-12-19T00:00:00Z'
    assert classify(s, {'SPY_return': -.06, 'SMH_relative_SPY': -.03}, now)['world_id'] == 'riskoff'
    assert classify(s, {'SPY_return': 0, 'SMH_relative_SPY': 0}, now)['world_id'] == 'mixed'
    assert classify(s, {}, now)['world_id'] is None
    assert classify({}, {}, now)['status'] == 'NOT_ASSERTED'


def test_event_calls_may_all_be_true_without_claiming_a_world_partition():
    a = author(); a['event_forecasts'] = [{'call_id': k, 'probability': .5, 'resolution': rule()} for k in ('policy', 'hot_CPI', 'credit')]
    validate_input(a)
    rows = score_calls([{**c, 'due_at_utc': c['resolution']['window_end_utc']} for c in a['event_forecasts']], [observation()], '2026-12-19T13:00:00Z')
    assert all(r['outcome'] is True for r in rows)


def expression(tmp_path):
    e = {'etf': 'SMH', 'saved_option_quote': {'occ_symbol': 'SMH270115P00400000', 'underlying': 'SMH', 'right': 'P', 'strike': 400,
        'expiry': '2027-01-15', 'expiry_close_utc': '2027-01-15T21:00:00Z', 'bid': 9, 'ask': 10,
        'quote_at_utc': '2026-11-25T21:00:00Z', 'source_sha256': 'c' * 64},
        'option_scenario': {'at_utc': '2027-01-14T21:00:00Z', 'spot': 410, 'iv': .1, 'rate': .04, 'rate_basis': 'SYNTHETIC_TEST', 'dividend_basis': 'SYNTHETIC_TEST', 'iv_basis': 'SYNTHETIC_STRESS', 'dividend_yield': .01, 'exit_spread_multiple': 1}}
    import json, hashlib
    path = tmp_path / 'synthetic_quote.json'
    path.write_text(json.dumps(e['saved_option_quote']))
    e['saved_option_quote'].update(source_path=str(path), source_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    return e


def test_correct_relative_call_is_not_put_profit_and_delay_iv_can_lose(tmp_path):
    s = classify(scenarios(), {'SPY_return': .04, 'SMH_relative_SPY': -.03}, '2026-12-19T00:00:00Z')
    assert s['world_id'] == 'rotation'
    result = option_payoff(expression(tmp_path))
    assert result['status'] == 'CONDITIONAL_MODEL_NOT_REALISED'
    assert result['net_return_on_premium'] < 0
    assert result['conditional_mark'] == 'LOSE'


@pytest.mark.parametrize('field,value', [('bid', 11), ('ask', 0), ('right', 'C'), ('strike', 390), ('source_sha256', None), ('expiry_close_utc', None)])
def test_option_identity_quote_gaps_are_unassessed(tmp_path, field, value):
    e = expression(tmp_path); e['saved_option_quote'][field] = value
    assert option_payoff(e)['status'] == 'OPTION_PAYOFF_UNASSESSED'


def test_governed_registry_includes_kre_without_granting_ticker_authority():
    a = {'etf_book': [{'etf': 'KRE'}]}
    assert governance(a, {}, load_policy())['expressions'][0]['option_payoff']['status'] == 'OPTION_PAYOFF_UNASSESSED'
    a['etf_book'][0]['etf'] = 'AAPL'
    with pytest.raises(ValueError): governance(a, {}, load_policy())


def test_saved_scenario_classification_has_exact_baselines_and_no_gap_fill():
    import pandas as pd
    from macro_board.cycle_governance import classify_saved
    closes = pd.DataFrame({'SPY': [100., 104.], 'SMH': [100., 101.]}, index=pd.to_datetime(['2026-11-25', '2026-12-18']))
    result = classify_saved(scenarios(), closes, '2026-12-19T00:00:00Z', 'a' * 64)
    assert result['world_id'] == 'rotation'
    assert result['metrics']['SMH_relative_SPY'] == pytest.approx(-.03)
    assert classify_saved(scenarios(), closes.iloc[:1], '2026-12-19T00:00:00Z', 'a' * 64)['world_id'] is None


def test_draft_assembly_keeps_authorship_distinct_and_cannot_be_relabelled_complete():
    a = author(); a['house_view'] = {'statement': 'Synthetic research only', 'probability': .55}
    payload = {'as_of_session': '2026-11-25', 'built_at_utc': '2026-11-25T21:00:00Z', 'cycle_assembly_utc': '2026-11-26T13:00:00Z', 'conditions': {}, 'etfs': {}}
    n = assemble(payload, {}, {}, {}, load_policy(), {'fixture': {'sha256': 'a' * 64}}, a)
    assert n['status'] == 'RESEARCH_DRAFT'
    assert n['clocks']['authored_at_utc'] != n['clocks']['market_publication_utc']
    n['status'] = 'COMPLETE'
    with pytest.raises(ValueError, match='Draft'): validate(n)


def test_approved_structured_input_remains_advisory_and_discloses_missing_option_payoff():
    a = author(); a.update(house_view={'statement': 'Synthetic only', 'probability': .5}, transmission={'status': 'AUTHORED'},
        central_bank_vs_price={'our_call': 'Synthetic', 'priced_call': None}, what_changes_our_mind=['Synthetic'], market_scenarios=scenarios())
    a['event_forecasts'] = [{'call_id': 'test', 'probability': .5, 'resolution': rule()}]
    a['etf_book'] = [{'expression_id': 'SMH-test', 'etf': 'SMH', 'forecast_basis': 'RELATIVE', 'benchmark': 'SPY',
                     'deadline_utc': '2026-12-18T21:00:00Z', 'invalidation': 'Synthetic recovery', 'killer_event': 'Synthetic only',
                     'covering_position': None, 'world_marks': {w['world_id']: 'UNASSESSED' for w in scenarios()['worlds']}}]
    content = deepcopy(a); content.pop('approval')
    a['approval'] = {'state': 'ACK_APPROVED_ADVISORY', 'approved_by': 'ACK', 'approved_at_utc': '2026-11-26T13:00:00Z', 'content_sha256': digest(content)}
    n = assemble({'as_of_session': '2026-11-25', 'built_at_utc': '2026-11-25T21:00:00Z', 'cycle_assembly_utc': '2026-11-26T14:00:00Z', 'conditions': {}, 'etfs': {}}, {}, {}, {}, load_policy(), {'fixture': {'sha256': 'a' * 64}}, a)
    assert n['authority'] == 'ADVISORY_ONLY'
    assert n['status'] == 'COMPLETE_WITH_EVIDENCE_LIMITATIONS'
    assert n['governance']['valuation_readiness'] == 'OPTION_PAYOFF_UNASSESSED'
    assert n['governance']['central_bank_comparison'] == 'AUTHORED_CALL_PRESENT_PRICED_PATH_MISSING'


def test_backdated_prospective_call_is_rejected():
    a = author(); a['event_forecasts'] = [{'call_id': 'x', 'probability': .5, 'resolution': rule(window_start_utc='2026-11-25T21:00:00Z')}]
    with pytest.raises(ValueError, match='authorship'): validate_input(a)


def test_world_payoffs_and_authored_stress_comparisons_do_not_inherit_win_marks(tmp_path):
    e = expression(tmp_path)
    early = {**e['option_scenario'], 'at_utc': '2026-12-01T21:00:00Z', 'iv': .8}
    e['option_scenarios_by_world'] = {'rotation': early}
    e['option_stress_scenarios'] = {'early_high_iv': early, 'late_iv_crush': e['option_scenario']}
    a = {'etf_book': [e], 'market_scenarios': scenarios()}
    g = governance(a, {}, load_policy()); result = g['expressions'][0]
    assert result['option_stress_comparisons']['early_high_iv']['net_return_on_premium'] > 0
    assert result['option_stress_comparisons']['late_iv_crush']['net_return_on_premium'] < 0
    assert result['option_payoff_by_world']['mixed']['status'] == 'OPTION_PAYOFF_UNASSESSED'
    assert g['valuation_readiness'] == 'OPTION_PAYOFF_UNASSESSED'


def test_saved_forecast_survives_governance_upgrade_but_not_horizon_reinterpretation(tmp_path):
    import json
    from pathlib import Path
    import pandas as pd
    from macro_board.operating_cycle import run_cycle
    from macro_board.cycle_io import read_records
    prices = pd.DataFrame({'SPY': [100., 101.]}, index=pd.to_datetime(['2026-11-24', '2026-11-25']))
    payload = {'as_of_session': '2026-11-25', 'built_at_utc': '2026-11-26T12:00:00Z', 'conditions': {}, 'etfs': {}}
    cfg = json.loads((Path(__file__).parents[1] / 'macro_board/config/macro_board_config_v1.json').read_bytes())
    policy = load_policy()
    kwargs = dict(opens=prices, closes=prices, fred=pd.DataFrame(index=prices.index),
                  raw={'forward_bias': ('forward.csv', b'horizon,direction\nshort_1_5d,BULLISH\n')},
                  board_config=cfg, output_dir=tmp_path)
    run_cycle(payload, policy=policy, **kwargs)
    before = (tmp_path / 'forward_calls.jsonl').read_bytes()
    changed = deepcopy(policy); changed.update(calc_version='SYNTHETIC_UPGRADE', max_option_stress_scenarios=8)
    run_cycle({**payload, 'built_at_utc': '2026-11-26T13:00:00Z'}, policy=changed, **kwargs)
    assert (tmp_path / 'forward_calls.jsonl').read_bytes() == before
    assert len(read_records(tmp_path / 'forward_calls.jsonl')) == 1
    changed['horizon_map']['short_1_5d'] = 6
    with pytest.raises(ValueError, match='identity conflict'):
        run_cycle({**payload, 'built_at_utc': '2026-11-26T14:00:00Z'}, policy=changed, **kwargs)


@pytest.mark.parametrize('model,bid,ask,multiple', [(12., 9., 10., 0.), (12., 9., 10., 1.), (12., 9., 10., 2.), (.1, 9., 10., 3.)])
def test_macro_adapter_preserves_governed_costs_and_unrounded_spread_stress(model, bid, ask, multiple):
    from macro_board.cycle_option_compat import net_return_on_premium_raw
    from domain.option_valuation import valuation_policy, return_on_premium
    pol = valuation_policy()
    expected = max(model - (ask - bid) * multiple / 2 - pol['fee_usd_per_contract_close'] / 100, 0) / (ask + pol['fee_usd_per_contract_open'] / 100) - 1
    actual = net_return_on_premium_raw(model, bid=bid, ask=ask, exit_spread_multiple=multiple)
    assert actual == pytest.approx(expected, abs=1e-12)
    assert actual >= -1
    if multiple == 1:
        assert round(actual, 4) == return_on_premium(model, bid=bid, ask=ask)


@pytest.mark.parametrize('model,bid,ask', [(None, 9., 10.), (float('nan'), 9., 10.), (-1., 9., 10.), (12., None, 10.), (12., 11., 10.), (12., 0., 0.)])
def test_macro_adapter_does_not_invent_returns_for_missing_or_invalid_inputs(model, bid, ask):
    from macro_board.cycle_option_compat import net_return_on_premium_raw
    assert net_return_on_premium_raw(model, bid=bid, ask=ask) is None


@pytest.mark.parametrize('multiple', [-1, float('nan'), float('inf'), 'bad'])
def test_macro_adapter_rejects_invalid_stress_assumptions(multiple):
    from macro_board.cycle_option_compat import net_return_on_premium_raw
    with pytest.raises(ValueError):
        net_return_on_premium_raw(12., bid=9., ask=10., exit_spread_multiple=multiple)
