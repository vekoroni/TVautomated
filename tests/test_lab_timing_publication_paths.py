"""Both saved/publication paths retain timing and verdicts; no providers."""
import csv
from copy import deepcopy
import json
from pathlib import Path
import pytest
from contracts.lab_review_sources import prepare_review_publication
from contracts.lab_review_projection import publish_review_projection


@pytest.mark.parametrize('trusted_receipt',[False,True])
def test_two_short_holds_and_95_fast_arrivals_survive_both_paths(tmp_path,monkeypatch,trusted_receipt):
    import requests
    def forbidden(*args,**kwargs): raise AssertionError('No provider calls')
    monkeypatch.setattr(requests.sessions.Session,'request',forbidden)
    root=tmp_path/'RUN';root.mkdir()
    (root/'run_meta.json').write_text(json.dumps({'dynamic_plan':{'evidence_cutoff_utc':'2026-11-13T21:05:00Z'}}))
    rows=[]
    for i,ticker in enumerate(['FMC','DKS']+[f'T{i:03}' for i in range(95)]):
        rows.append(dict(run_id='RUN',ticker=ticker,thesis_id=f'TH{i}',trade_idea_id=f'IDEA{i}',
            contract_symbol=f'{ticker}270115P00100000',planned_hold_sessions=3 if i<2 else 9,
            anticipated_sessions_q50=None if i<2 else 3,
            lab_verdict='MANUAL_REVIEW' if i<2 else ['MANUAL_REVIEW','BLOCKED','CONTRACT_REPAIR'][i%3],
            validation_event_id=f'VERIFIED{i}',validation_evidence_cutoff_utc='2026-11-15T12:00:00Z'))
    morning=root/'morning_validation/morning_validated_trades_RUN.csv';morning.parent.mkdir()
    with morning.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['ticker','thesis_id','contract_symbol','verdict','block_reason'])
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(ticker=row['ticker'],thesis_id=row['thesis_id'],contract_symbol=row['contract_symbol'],
                verdict=row['lab_verdict'],block_reason='SAVED_BLOCK_REASON' if row['lab_verdict']=='BLOCKED' else ''))
    if trusted_receipt:
        events=root/'morning_validation/validation_events';events.mkdir()
        (events/'do_not_reopen.json').write_text('{"invalid":"must not reread verified events"}')
        original=Path.read_text
        def read(path,*args,**kwargs):
            if path.parent==events: raise AssertionError('Fast path must not reread event files')
            return original(path,*args,**kwargs)
        monkeypatch.setattr(Path,'read_text',read)
    book=dict(run_id='RUN',candidate_count=len(rows),rows=rows,created_at_utc='2026-11-15T12:00:00Z')
    frozen=deepcopy(book)
    trusted=dict(status='PASS',authority='VALIDATION_ONLY',input_rows=len(rows),lab_projection_issues=[])
    prepared,context,receipt=prepare_review_publication(book,root,
        validation_receipt=trusted if trusted_receipt else None)
    assert book==frozen
    assert [r['lab_verdict'] for r in prepared['rows']]==[r['lab_verdict'] for r in rows]
    assert receipt['timing_assessment_version']=='trade_timing_sessions_v1'
    assert all(r['timing_details']['version']=='trade_timing_sessions_v1' for r in prepared['rows'])
    assert all('SAVED_BLOCK_REASON' in r['timing_details']['exclusion_reasons']
               for r in prepared['rows'] if r['lab_verdict']=='BLOCKED')
    manifest=publish_review_projection(prepared,tmp_path,context=context,source_receipt=receipt)
    timing=manifest['timing_summary']
    assert timing['planned_1_5_count']==2 and timing['arrival_1_5_count']==95
    assert len(timing['short_candidates'])==97
    assert 'NOT_ASSESSED' not in timing['session_check_counts']
    short=[r for r in timing['short_candidates'] if r['timing_details']['planned_short_1_5']]
    assert [r['ticker'] for r in short]==['FMC','DKS']
    assert all(r['lab_verdict']=='MANUAL_REVIEW' for r in short)
    if trusted_receipt:
        assert receipt['validation_events_applied']==97
