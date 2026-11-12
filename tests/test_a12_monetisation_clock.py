from datetime import date
from copy import deepcopy
import pytest

from avshunter.c12_outcome.monetisation import measure_origin, summarise_origins, measure_contract_history


def quote(bid=1, ask=1.1):
    return {'bid':bid,'ask':ask,'bid_size':10,'ask_size':10}


def test_first_profit_includes_both_sides_costs_and_session_count():
    # Entry cost 1.011; +20% requires bid >=1.2142 including close fee.
    p=[('2026-11-02',quote(1.2,1.3)),('2026-11-03',quote(1.2142,1.3))]
    r=measure_origin('2026-10-30',quote(.9,1),p,threshold=.2,open_fee=1.1,close_fee=.1)
    assert r['state']=='HIT' and r['n_sessions']==2


def test_zero_bid_not_a_total_loss_or_early_exit():
    p=[('2026-11-02',quote(0,1.15)),('2026-11-03',quote(1.4,1.5))]
    r=measure_origin('2026-10-30',quote(.9,1),p,threshold=.3,open_fee=1.1,close_fee=.1)
    assert r['state']=='HIT' and r['n_sessions']==2
    assert 'realised_return' not in r


def test_missing_before_hit_is_not_exact_first_passage():
    r=measure_origin('2026-10-30',quote(.9,1),[('2026-11-02',None),('2026-11-03',quote(1.4,1.5))],threshold=.3,open_fee=1.1,close_fee=.1)
    assert r['state']=='UNASSESSED_GAP_BEFORE_HIT'
    assert r['first_observed_hit_session']==2 and r['n_sessions'] is None


def test_no_hit_failure_is_not_zero_bid_pnl():
    r=measure_origin('2026-10-30',quote(.9,1),[('2026-11-02',quote(0,.1))],threshold=.3,open_fee=1.1,close_fee=.1)
    assert r['state']=='NO_OBSERVED_HIT'
    assert r['terminal_zero_bid'] is True


def test_censor_and_failure_and_unknown_remain_in_denominator():
    origins=[{'state':'HIT','n_sessions':2},{'state':'HIT','n_sessions':4},
             {'state':'NO_OBSERVED_HIT'},{'state':'RIGHT_CENSORED'}, {'state':'UNASSESSED_ENTRY'}]
    r=summarise_origins(origins)
    assert (r['n_q50'],r['n_q80'])==(2,4)
    assert (r['evidence_n'],r['hit_n'],r['failure_n'],r['censored_n'],r['unassessed_n'])==(5,2,1,1,1)
    assert r['quantile_basis']=='CONDITIONAL_ON_OBSERVED_HITS_NOT_SUCCESS_PROBABILITY'


def test_no_hits_is_null_not_zero():
    r=summarise_origins([{'state':'NO_OBSERVED_HIT'}])
    assert r['n_q50'] is None and r['n_q80'] is None


def test_exact_identity_and_no_future_quotes_and_nonoverlap():
    history={'2026-10-30':quote(.9,1),'2026-11-02':quote(1.4,1.5),
             '2026-11-03':quote(1.4,1.5),'2026-11-04':quote(10,11)}
    original=deepcopy(history)
    r=measure_contract_history('ABC261218C00100000',history,as_of=date(2026,11,3),observation_sessions=2,open_fee=1.1,close_fee=.1)
    assert len(r['origins'])==1
    assert r['levels']['30']['n_q50']==1
    assert history==original


def test_invalid_adjusted_contract_not_guessed():
    r=measure_contract_history('ABC1261218C00100000',{},as_of=date(2026,11,3),observation_sessions=20,open_fee=1.1,close_fee=.1)
    assert r['state']=='UNASSESSED_NONSTANDARD_OR_INVALID_CONTRACT'


def test_newer_quote_cannot_turn_censor_into_hit():
    r=measure_contract_history('ABC261218C00100000',{'2026-11-02':quote(.9,1),'2026-11-04':quote(4,5)},as_of=date(2026,11,3),observation_sessions=3,open_fee=1.1,close_fee=.1)
    assert r['levels']['30']['hit_n']==0
    assert r['levels']['30']['censored_n']+r['levels']['30']['unassessed_n']==1


def test_adapter_never_uses_a_receipt_after_the_cutoff(tmp_path):
    import sqlite3
    from avshunter.c12_outcome.adapters.monetisation_history import SavedMonetisationHistory,instant
    p=tmp_path/'quotes.db';c=sqlite3.connect(p)
    c.execute('create table chain_snapshots(ticker,quote_date,option_symbol,bid,ask,bid_size,ask_size,updated_ts,created_at_utc)')
    c.execute('insert into chain_snapshots values(?,?,?,?,?,?,?,?,?)',('NAN','2026-11-02','NAN261218C00010000',1,1.1,10,10,1793653200,'2026-11-10T00:00:00Z'))
    c.commit();c.close()
    with SavedMonetisationHistory(p,lookback_days=365,close_tolerance_seconds=1800) as reader:
        import pytest
        with pytest.raises(sqlite3.OperationalError):reader.conn.execute('delete from chain_snapshots')
        hist,receipt=reader.read('NAN','NAN261218C00010000',as_of=date(2026,11,3),decision_cutoff=instant('2026-11-04T14:00:00Z'))
    assert hist['2026-11-02'] is None
    assert receipt['quarantine_counts']['RECEIPT_AFTER_DECISION_CUTOFF']==1


def test_attachment_never_changes_expiry_rank_or_permission():
    import hashlib,json
    from contracts.monetisation_clock import attach_clock
    measurement=measure_contract_history('ABC261218C00100000',{'2026-11-02':quote(.9,1)},as_of=date(2026,11,3),observation_sessions=3,open_fee=1.1,close_fee=.1)
    packet={'schema':'monetisation_clock_packet_v1','run_id':'R','authority':'DESCRIPTIVE_MEASUREMENT_ONLY',
            'records':[{'ticker':'ABC','thesis_id':'T','contract_symbol':'ABC261218C00100000','measurement':measurement}]}
    packet['content_sha256']=hashlib.sha256(json.dumps(packet,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    row={'ticker':'ABC','thesis_id':'T','contract_symbol':'ABC261218C00100000','expiry':'2026-12-18','lab_rank':4,'verdict':'BLOCK'}
    original=deepcopy(row);out,receipt=attach_clock([row],packet,run_id='R')
    assert row==original and all(out[0][k]==v for k,v in row.items())
    assert receipt['matched_rows']==1
    wrong={**row,'contract_symbol':'ABC270115C00100000'}
    assert attach_clock([wrong],packet,run_id='R')[0][0]['monetisation_clock_state']=='UNASSESSED_NO_UNIQUE_EXACT_IDENTITY'


def test_invalid_calendar_contract_is_unassessed_not_batch_failure():
    r=measure_contract_history('ABC261332C00100000',{},as_of=date(2026,11,3),observation_sessions=20,open_fee=1.1,close_fee=.1)
    assert r['state']=='UNASSESSED_NONSTANDARD_OR_INVALID_CONTRACT'


def test_corrupt_publication_packet_is_rejected():
    import pytest
    from contracts.monetisation_clock import validate_packet
    with pytest.raises(ValueError,match='HASH_MISMATCH'):
        validate_packet({'schema':'monetisation_clock_packet_v1','run_id':'R','authority':'DESCRIPTIVE_MEASUREMENT_ONLY','content_sha256':'bad'},'R')


def test_publication_requires_the_exact_morning_source(tmp_path):
    from contracts.lab_review_sources import prepare_review_publication
    root=tmp_path/'R';root.mkdir()
    source={'run_id':'R','rows':[],'candidate_count':0}
    with pytest.raises(ValueError,match='MONETISATION_MORNING_SOURCE_HASH_MISMATCH'):
        prepare_review_publication(source,root,monetisation_packet={'source_rows_sha256':'wrong'})
