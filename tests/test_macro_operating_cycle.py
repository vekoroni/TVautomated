"""Phase-one advisory macro operating cycle: saved-data business acceptance."""
from copy import deepcopy
from datetime import date
import json

import numpy as np
import pandas as pd
import pytest

from macro_board.cycle_evidence import driver_readings, short_windows, forced_calendar
from macro_board.cycle_narrative import assemble, validate, render
from macro_board.cycle_io import publish, append_records, WriterBusy
from macro_board.cycle_scoring import forward_calls, score_forward, score_calls
from macro_board.operating_cycle import load_policy


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import socket
    def forbidden(*args, **kwargs):
        raise AssertionError('Macro cycle must not contact providers')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)


@pytest.fixture
def payload():
    return {'as_of_session': '2026-11-25', 'built_at_utc': '2026-11-26T11:35:33Z',
            'build': {'kind': 'OFF_SESSION'},
            'conditions': {'current': {'credit': 'WIDENING', 'liquidity': 'FLAT'},
                           'observations': {'credit': {'oldest': '2026-11-25'}}},
            'etfs': {t: {'metrics': {'status': 'FRESH', 'rs_vs_spy_20d': v}}
                     for t, v in [('XLP', 13.49), ('XLV', 9.4), ('XLU', 9.8), ('XLRE', 11.3), ('RSP', 6.42)]},
            'opportunity': {'leadership': {'breadth': {'state': 'UNKNOWN'}}}}


@pytest.fixture
def sources():
    return {'packet': {'rates_impulse': 'RESTRICTIVE_HOLD', 'extras': {
                'credit': {'state': 'NEUTRAL', 'risk_score': 50},
                'liquidity': {'regime': 'DRAINING', 'signal': 'STALE_8D_OLD'}}},
            'liquidity': {'HY_OAS': 3.7, 'HY_Z': 2.23, 'Credit_Stress': 'WIDE',
                          'Liquidity_Regime': 'Draining (STALE - 8d old)'},
            'bond': {'yield_curve': {'as_of_date': '2026-11-24', 'curve_move_5d_detail': {'d2y_bp': -17}},
                     'zn_futures': {'rate_regime_signal': 'EASING_BIAS'},
                     'credit_stress': {'stress_level': 'ELEVATED', 'ratio_zscore_20d': 1.983}}}


def test_reconciles_without_erasing_measurement_dimensions(payload, sources):
    d = driver_readings(payload, sources, load_policy())
    assert d['credit']['state'] == 'WIDE_WARNING'
    assert d['credit']['conflicts'][0]['label'] == 'NEUTRAL'
    assert d['rates']['state'] == 'EASING'
    assert d['rates']['dimensions']['policy_stance'] == 'RESTRICTIVE_HOLD'
    assert d['rotation']['state'] == 'DEFENSIVE_BROADENING'
    assert d['rotation']['evidence_status'] == 'PARTIAL_PARTICIPATION_UNAVAILABLE'
    assert d['liquidity']['status'] == 'STALE'
    assert d['liquidity']['age_days'] == 8


def test_missing_is_not_neutral(payload):
    d = driver_readings(payload, {}, load_policy())
    assert d['credit']['state'] == 'MISSING'
    assert d['policy']['state'] == 'MISSING'
    assert d['rates']['state'] == 'MISSING'


def test_short_windows_preserve_sign_history_and_no_future():
    idx = pd.bdate_range('2025-01-01', periods=300)
    x = pd.Series(np.linspace(4.0, 4.5, 300), index=idx)
    x.iloc[-5:] -= np.linspace(.04, .2, 5)
    p = load_policy()
    got = short_windows({'DGS2': x}, idx, p)
    assert got['DGS2']['5']['change'] < 0
    assert got['DGS2']['5']['unusualness_percentile'] >= .9
    cut = short_windows({'DGS2': x}, idx[:-5], p)
    other = short_windows({'DGS2': x.iloc[:-5]}, idx[:-5], p)
    assert cut == other


def test_dead_series_are_excluded_even_if_values_exist():
    idx = pd.bdate_range('2025-01-01', periods=300)
    s = pd.Series(np.arange(300.), index=idx)
    got = short_windows({'USSLIND': s, 'USALOLITONOSTSAM': s}, idx, load_policy())
    assert all(r['status'] == 'EXCLUDED_HISTORICAL_ONLY' for r in got.values())


def test_calendar_holidays_half_days_expiry_and_period_end():
    c = forced_calendar(date(2026, 11, 25), pd.DataFrame(), load_policy())
    seen = {(r['date'], r['kind']) for r in c['events']}
    assert ('2026-11-27', 'HALF_DAY') in seen
    assert ('2026-11-30', 'MONTH_END') in seen
    assert ('2026-12-18', 'MONTHLY_OPTIONS_EXPIRY') in seen
    assert ('2026-12-31', 'YEAR_END') in seen
    assert ('2026-12-31', 'QUARTER_END') in seen
    assert ('2026-12-25', 'MARKET_HOLIDAY') in seen
    assert all(r['prediction'] is None for r in c['events'])


def test_trend_averages_require_contiguous_sessions_and_no_future():
    from avshunter.shared.xnys_calendar import is_xnys_session
    idx = pd.date_range('2025-11-01', '2026-11-25')
    idx = pd.DatetimeIndex([x for x in idx if is_xnys_session(x.date())])
    closes = pd.DataFrame({'SPY': np.arange(len(idx)) + 100.}, index=idx)
    c = forced_calendar(date(2026, 11, 25), closes, load_policy())
    row = c['trend_levels']['SPY']['20']
    assert row['status'] == 'OK'
    assert row['average'] == pytest.approx(closes.SPY.iloc[-20:].mean())
    closes.loc[idx[-2], 'SPY'] = np.nan
    assert forced_calendar(date(2026, 11, 25), closes, load_policy())['trend_levels']['SPY']['20']['status'] == 'MISSING'


def _narrative(payload, sources):
    return assemble(payload, sources, {}, {'events': [], 'trend_levels': {}},
                    load_policy(), {'fixture': {'sha256': 'a' * 64}}, None)


def test_nine_sections_authored_unknowns_and_input_immutability(payload, sources):
    original = deepcopy((payload, sources))
    n = _narrative(payload, sources)
    validate(n)
    assert len(n['sections']) == 9
    assert n['authority'] == 'ADVISORY_ONLY'
    assert n['sections'][2]['data']['probability'] is None
    assert n['status'] == 'INCOMPLETE_AUTHORED_INPUT'
    assert (payload, sources) == original
    assert 'MISSING' in render(n)


def test_rejects_invented_probabilities_invalid_authority_and_equity_book(payload, sources):
    n = _narrative(payload, sources)
    for mutate in [lambda x: x.update(authority='EXECUTE'),
                   lambda x: x['sections'][2]['data'].update(probability=1.2),
                   lambda x: x['sections'][7]['data'].update(expressions=[{'etf': 'NVDA'}])]:
        bad = deepcopy(n); mutate(bad)
        with pytest.raises(ValueError): validate(bad)


def test_immutable_publication_idempotency_and_new_correction_version(tmp_path, payload, sources):
    n = _narrative(payload, sources)
    a = publish(tmp_path, n)
    before = a.read_bytes()
    assert publish(tmp_path, n) == a
    n['correction_reason'] = 'source correction'
    n['supersedes'] = n['narrative_id']
    n['narrative_id'] = 'correction-v2'
    b = publish(tmp_path, n)
    assert a != b and a.read_bytes() == before
    assert json.loads((tmp_path / 'latest.json').read_text())['narrative_id'] == 'correction-v2'
    bad = deepcopy(n); bad['status'] = 'different'
    with pytest.raises(ValueError): publish(tmp_path, bad)


def test_append_only_ids_and_conflicting_receipts_fail(tmp_path):
    path = tmp_path / 'rows.jsonl'
    assert append_records(path, [{'record_id': 'x', 'value': 1}]) == 1
    assert append_records(path, [{'record_id': 'x', 'value': 1}]) == 0
    with pytest.raises(ValueError): append_records(path, [{'record_id': 'x', 'value': 2}])
    assert len(path.read_text().splitlines()) == 1


def test_writer_lock_does_not_steal_or_publish(tmp_path, payload, sources):
    (tmp_path / '.writer.lock').write_text('other writer')
    with pytest.raises(WriterBusy): publish(tmp_path, _narrative(payload, sources))
    assert not (tmp_path / 'latest.json').exists()


def test_forward_scores_are_not_calibrated_probabilities_and_mature_on_sessions():
    rows = [{'horizon': 'short_1_5d', 'direction': 'BEARISH', 'bullish_prob_pct': '26.4', 'score': '-.4719'}]
    calls = forward_calls(rows, '2026-11-25T21:10:00Z', 'a' * 64, load_policy())
    assert calls[0]['probability_status'] == 'UNCALIBRATED_SCORE_TRANSFORM'
    idx = pd.to_datetime(['2026-11-27', '2026-11-30', '2026-12-01', '2026-12-02', '2026-12-03'])
    bars = pd.DataFrame({'open': [100.] * 5, 'close': [99., 98., 97., 96., 95.]}, index=idx)
    out = score_forward(calls, bars, '2026-12-03T21:01:00Z')
    assert out[0]['status'] == 'MATURED' and out[0]['hit'] is True
    assert out[0]['return_pct'] == pytest.approx(-5)
    assert score_forward(calls, bars, '2026-12-02T21:01:00Z')[0]['status'] == 'PENDING'
    assert out[0]['brier_score_descriptive_only'] == pytest.approx(.264 ** 2)


def test_missing_intermediate_bar_is_gap_not_shorter_horizon():
    rows = [{'horizon': 'short_1_5d', 'direction': 'BULLISH'}]
    calls = forward_calls(rows, '2026-11-25T21:10:00Z', 'a' * 64, load_policy())
    idx = pd.to_datetime(['2026-11-27', '2026-12-01', '2026-12-02', '2026-12-03', '2026-12-04'])
    bars = pd.DataFrame({'open': 100., 'close': 105.}, index=idx)
    assert score_forward(calls, bars, '2026-12-04T21:01:00Z')[0]['status'] == 'DATA_GAP'


def test_authored_calls_do_not_turn_unobservable_events_into_losses():
    calls = [{'call_id': 'w1', 'probability': .3, 'due_at_utc': '2026-11-27T18:00:00Z'}]
    assert score_calls(calls, [], '2026-11-27T18:01:00Z')[0]['status'] == 'UNASSESSED_OUTCOME'
    obs = [{'call_id': 'w1', 'observed_at_utc': '2026-11-27T18:00:00Z', 'outcome': True,
            'source': 'saved event', 'source_sha256': 'b' * 64}]
    assert score_calls(calls, obs, '2026-11-27T18:01:00Z')[0]['brier_score'] == pytest.approx(.49)
    assert score_calls(calls, obs, '2026-11-27T17:00:00Z')[0]['status'] == 'PENDING'


@pytest.mark.parametrize('clock,entry', [('2026-07-01T13:29:00Z', '2026-07-01'),
                                      ('2026-11-25T14:29:00Z', '2026-11-25'),
                                      ('2026-11-25T14:31:00Z', '2026-11-27'),
                                      ('2026-11-27T18:01:00Z', '2026-11-30')])
def test_entry_clock_uses_exchange_calendar_and_dst(clock, entry):
    from macro_board.cycle_scoring import expected_sessions, instant
    assert str(expected_sessions(instant(clock), 5)[0]) == entry


def test_scores_not_mature_before_half_day_close():
    call = {'call_id': 'x', 'known_at_utc': '2026-11-25T21:01:00Z', 'horizon_sessions': 1,
            'source_horizon': 'fixture', 'probability_status': 'UNASSESSED', 'direction': 'BULLISH'}
    bars = pd.DataFrame({'open': [100.], 'close': [101.]}, index=pd.to_datetime(['2026-11-27']))
    assert score_forward([call], bars, '2026-11-27T17:59:00Z')[0]['status'] == 'PENDING'
    assert score_forward([call], bars, '2026-11-27T18:00:00Z')[0]['status'] == 'MATURED'


def test_archive_inventory_requires_byte_hash_and_publication_clock(tmp_path):
    from macro_board.operating_cycle import archive_inventory
    import hashlib
    (tmp_path / 'snapshots').mkdir(); (tmp_path / 'inputs').mkdir()
    data = b'horizon,direction\nshort_1_5d,BULLISH\n'
    f = tmp_path / 'inputs/one_forward_bias.csv'; f.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    snap = {'built_at_utc': '2026-11-25T21:10:00Z', 'inputs': {'forward_bias': {'archived_as': f.name, 'sha256': sha}}}
    s = tmp_path / 'snapshots/board_2026-11-25.json'; s.write_text(json.dumps(snap))
    calls, inventory = archive_inventory(tmp_path, load_policy())
    assert len(calls) == 1 and not inventory['unlinked_artifacts']
    snap['inputs']['forward_bias']['sha256'] = 'bad'; s.write_text(json.dumps(snap))
    with pytest.raises(ValueError): archive_inventory(tmp_path, load_policy())


def test_current_cycle_is_sidecar_only_and_retries_are_idempotent(tmp_path, payload):
    from macro_board.operating_cycle import run_cycle
    from avshunter.shared.xnys_calendar import is_xnys_session
    idx = pd.DatetimeIndex([d for d in pd.date_range('2025-01-01', '2026-11-25') if is_xnys_session(d.date())])
    closes = pd.DataFrame({'SPY': np.linspace(100., 150., len(idx))}, index=idx)
    fred = pd.DataFrame(index=idx)
    cfg = json.loads((__import__('pathlib').Path(__file__).parents[1] / 'macro_board/config/macro_board_config_v1.json').read_text())
    original = deepcopy(payload)
    result = run_cycle(payload, opens=closes, closes=closes, fred=fred, raw={}, board_config=cfg, output_dir=tmp_path)
    again = run_cycle(payload, opens=closes, closes=closes, fred=fred, raw={}, board_config=cfg, output_dir=tmp_path)
    assert again['idempotent'] and result['narrative_id'] == again['narrative_id']
    assert payload == original
    assert (tmp_path / 'latest.json').is_file()
    assert not (tmp_path / 'daily_scores.jsonl').exists()  # no invented calls


def test_all_three_research_feeds_are_preserved_in_capture_mapping():
    from macro_board.operating_cycle import _documents
    result = _documents({k: (k + '.json', b'{"source":"fixture"}')
                         for k in ('us_money_index', 'enrichment', 'event_payload')})
    assert {'usmi', 'news', 'events'} <= set(result)


def test_wrong_worlds_require_measurable_tripwires_and_correction_reason():
    from macro_board.cycle_narrative import validate_author_input
    a = {'authority': 'ADVISORY_ONLY', 'author': 'ACK', 'as_of_utc': '2026-11-25T21:00:00Z',
         'wrong_worlds': [{'call_id': 'x', 'event': 'Rates rise', 'due_at_utc': '2026-12-01T21:00:00Z',
                          'resolution_rule': 'DGS2 at deadline', 'probability': .3}]}
    with pytest.raises(ValueError): validate_author_input(a)
    a['wrong_worlds'][0]['tripwire'] = {'series': 'DGS2', 'level': 5.0, 'operator': 'GE'}
    validate_author_input(a)


def test_measured_sheet_publishes_short_and_long_windows():
    from macro_board.measured_sheet import render
    p = {'macro_short_windows': {'DGS2': {'5': {'change': -17., 'unit': 'bp', 'signed_percentile': .01,
         'unusualness_percentile': .917, 'turning_point': True, 'evidence_count': 252, 'status': 'OK'},
         '20': {'change': -7., 'unit': 'bp', 'status': 'OK'}}}}
    cfg = {'title': 'fixture', 'instructions': [], 'needed_from_you': [], 'focus': [], 'release_sessions_ahead': 5}
    text = render(p, cfg)
    assert '-17 bp' in text and '-7 bp' in text and 'TURNING_POINT' in text


def test_existing_scheduler_full_and_budgets_not_reconfigured():
    from pathlib import Path
    root = Path(__file__).parents[1]
    code = (root / 'macro_board/operating_cycle.py').read_text()
    assert 'requests.get' not in code and 'Anthropic(' not in code and 'subprocess' not in code
    assert 'mode=ro' in (root / 'macro_board/sources.py').read_text()


def test_tripwire_alerts_are_exact_series_advisory_and_deduplicated():
    from macro_board.cycle_narrative import tripwires
    a = {'wrong_worlds': [{'call_id': 'w', 'tripwire': {'series': 'DGS2', 'operator': 'GT', 'level': 4.5}}]}
    first = tripwires(a, {'DGS2': {'value': 4.6, 'status': 'OK'}})
    assert first[0]['newly_fired'] and first[0]['authority'] == 'ADVISORY_ONLY'
    assert not tripwires(a, {'DGS2': {'value': 4.6, 'status': 'OK'}}, first)[0]['newly_fired']
    assert tripwires(a, {'DGS2': {'value': 4.6, 'status': 'STALE'}})[0]['fired'] is None
    assert tripwires(a, {'DGS10': {'value': 4.6, 'status': 'OK'}})[0]['status'] == 'UNASSESSED_SOURCE'


def test_incomplete_record_cannot_be_relabelled_complete(payload, sources):
    n = _narrative(payload, sources); n['status'] = 'COMPLETE'
    with pytest.raises(ValueError): validate(n)


def test_complete_authored_cycle_preserves_marks_and_scores_all_call_categories(tmp_path, payload):
    from pathlib import Path
    from macro_board.operating_cycle import run_cycle
    from macro_board.cycle_io import read_records
    from avshunter.shared.xnys_calendar import is_xnys_session
    idx = pd.DatetimeIndex([d for d in pd.date_range('2025-01-01', '2026-11-25') if is_xnys_session(d.date())])
    closes = pd.DataFrame({'SPY': np.linspace(100., 150., len(idx))}, index=idx)
    cfg = json.loads((Path(__file__).parents[1] / 'macro_board/config/macro_board_config_v1.json').read_text())
    def call(cid):
        return {'call_id': cid, 'event': 'fixture outcome', 'due_at_utc': '2026-11-25T21:01:00Z',
                'resolution_rule': 'Independent saved receipt', 'probability': .25,
                'tripwire': {'series': 'SPY.close', 'operator': 'GT', 'level': 140.}}
    author = {'authority': 'ADVISORY_ONLY', 'author': 'FIXTURE_NOT_A_MARKET_CALL', 'as_of_utc': '2026-11-24T21:00:00Z',
              'transmission': {'text': 'Fixture, not production judgement'},
              'house_view': {'statement': 'Fixture house view', 'probability': .5},
              'wrong_worlds': [call('w1'), call('w2')], 'event_calls': [call('e1')],
              'playbook_choices': [call('p1')], 'forced_flow_predictions': [call('f1')],
              'central_bank_vs_price': {'our_call': 'fixture', 'priced_call': None, 'status': 'MISSING_PRICED_PATH'},
              'etf_book': [{'etf': 'SPY', 'killer_event': 'fixture', 'covering_position': None,
                           'world_marks': {'HOUSE': 'WIN', 'w1': 'FLAT', 'w2': 'LOSE'}}],
              'what_changes_our_mind': ['fixture'], 'worlds_partition': 'MUTUALLY_EXCLUSIVE_EXHAUSTIVE'}
    evidence = tmp_path / 'synthetic_outcome_source.json'; evidence.write_text('{"fixture_observation":true}')
    import hashlib
    sha = hashlib.sha256(evidence.read_bytes()).hexdigest()
    obs = [{'call_id': cid, 'observed_at_utc': '2026-11-25T21:01:00Z', 'outcome': True,
            'source': 'synthetic unit-test receipt', 'source_path': str(evidence), 'source_sha256': sha}
           for cid in ('w1', 'w2', 'e1', 'p1', 'f1')]
    original = deepcopy(author)
    r = run_cycle(payload, opens=closes, closes=closes, fred=pd.DataFrame(index=idx), raw={},
                  board_config=cfg, output_dir=tmp_path, author=author, observations=obs)
    assert r['authored_calls'] == 5 and r['authored_status_counts'] == {'MATURED': 5}
    n = json.loads(Path(r['narrative']).read_text())
    assert n['sections'][7]['data']['expressions'][0]['worlds_count'] == 3
    assert n['tripwire_observations'][0]['newly_fired']
    assert author == original
    assert len(read_records(tmp_path / 'daily_scores.jsonl')) == 5
    assert list((tmp_path / 'calendars').glob('forced_flow_calendar_2026-11-25_*.json'))


def test_reused_forward_file_is_one_call_not_a_new_forecast_per_board(tmp_path, payload):
    from pathlib import Path
    from macro_board.operating_cycle import run_cycle
    from macro_board.cycle_io import read_records
    from avshunter.shared.xnys_calendar import is_xnys_session
    idx = pd.DatetimeIndex([d for d in pd.date_range('2025-01-01', '2026-11-25') if is_xnys_session(d.date())])
    prices = pd.DataFrame({'SPY': 100.}, index=idx)
    cfg = json.loads((Path(__file__).parents[1] / 'macro_board/config/macro_board_config_v1.json').read_text())
    kwargs = dict(opens=prices, closes=prices, fred=pd.DataFrame(index=idx),
                  raw={'forward_bias': ('forward.csv', b'horizon,direction\nshort_1_5d,BULLISH\n')},
                  board_config=cfg, output_dir=tmp_path)
    run_cycle(payload, **kwargs)
    later = deepcopy(payload); later['built_at_utc'] = '2026-11-26T12:35:33Z'
    run_cycle(later, **kwargs)
    calls = read_records(tmp_path / 'forward_calls.jsonl')
    assert len(calls) == 1 and calls[0]['known_at_utc'] == payload['built_at_utc']
