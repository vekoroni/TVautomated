"""Growing historical archives cannot grow the analysis prompt; current facts never truncated."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json
import pytest
import build_macro_json as builder
from contracts.macro_prompt_policy import (
    ProjectionBudgetExceeded,canonical,digest,event_window,usmi_view,enforce_request_budget,persist_audit,
)
from contracts.macro_prompt_projection import encode,deduplicate,columnar_records

ASOF='2026-11-26T12:00:00Z'

def event(identity,clock=None,**extra):
    out={'event_id':identity,'event_name':identity,'actual':None,'forecast':False,
        'surprise_score':0,'risks':['active uncertainty'],'counterevidence':'keep exact',**extra}
    if clock is not None:out['release_time_utc']=clock
    return out

def test_current_upcoming_undated_active_revised_and_exact_id_dependencies_retained():
    rows=[event('recent','2026-11-25T13:30:00Z',prior_event_id='dependency'),
        event('upcoming','2026-12-01T13:30:00Z'),event('undated'),
        event('active','2025-01-01T00:00:00Z',active=True),
        event('revised','2025-01-01T00:00:00Z',information_cutoff_utc='2026-11-25T20:00:00Z'),
        event('dependency','2024-01-01T00:00:00Z',related_prior_event_id='root'),
        event('root','2023-01-01T00:00:00Z'),event('archive','2022-01-01T00:00:00Z')]
    original={'events':rows};frozen=deepcopy(original);audit=[]
    out=event_window(original,as_of_utc=ASOF,audit=audit)
    assert out['events']==rows[:-1] and original==frozen
    assert audit[0]['event_id']=='archive' and audit[0]['content_sha256']==digest(rows[-1])
    assert out['event_projection']['window_start_session']=='2026-11-19'
    assert out['event_projection']['retained_undated_count']==1

@pytest.mark.parametrize('clock',[None,'bad','2026-01-01T00:00:00'])
def test_no_clock_is_invented_and_unknowns_are_not_aged_out(clock):
    rows=[event('date-in-id-1999','2024-01-01T00:00:00Z')]
    out=event_window({'events':rows},as_of_utc=clock)
    assert out['events']==rows
    assert out['event_projection']['status']=='CLOCK_UNASSESSED_ALL_RETAINED'

def test_completed_session_window_respects_thanksgiving_and_friday_early_close():
    assert event_window({'events':[]},as_of_utc='2026-11-27T12:00:00Z')['event_projection']['window_start_session']=='2026-11-19'
    assert event_window({'events':[]},as_of_utc='2026-11-27T18:01:00Z')['event_projection']['window_start_session']=='2026-11-20'

def test_thousands_of_historical_events_leave_request_bounded_and_full_audit_complete():
    sizes=[]
    current=[event('current','2026-11-25T13:30:00Z'),event('unknown')]
    for count in (10,1000,5000):
        packet={'events':current+[event('old-'+str(i),'2020-01-01T00:00:00Z',narrative='unique historical '+str(i)*20) for i in range(count)]}
        audit=[];view=event_window(packet,as_of_utc=ASOF,audit=audit)
        assert view['events']==current and len(audit)==count
        assert len(view['event_projection']['omitted_path_examples'])<=8
        assert view['event_projection']['omission_manifest_sha256']==digest(audit)
        sizes.append(len(encode(deduplicate(columnar_records(view))).encode()))
    assert max(sizes)-min(sizes)<100

def test_usmi_archival_growth_does_not_enlarge_inline_receipts_or_discard_current_comparators():
    sizes=[]
    for count in (10,1000,5000):
        packet={'source_payload':{'packet_revision':10000},'current':{'actual':None,'zero':0,'counterevidence':'unchanged'},
            'latest_comparator':{'dated_observation':'keep'},'new_risk_rev73_hint':{'unverified':True},
            'rev10001_future_information':{'unknown':None},
            **{'archived_rev'+str(i):{'old':i} for i in range(count)}}
        frozen=deepcopy(packet);audit=[];view=usmi_view(packet,audit=audit)
        for key in ('current','latest_comparator','new_risk_rev73_hint','rev10001_future_information'):assert view[key]==packet[key]
        assert packet==frozen and len(audit)==count+1
        assert len(view['projection_omitted_paths'])<=8
        sizes.append(len(encode(view).encode()))
    assert max(sizes)-min(sizes)<100

def test_current_evidence_overflow_stops_before_client_construction(monkeypatch):
    monkeypatch.setattr(builder,'_anthropic_client',lambda:pytest.fail('No provider/client allowed'))
    with pytest.raises(ProjectionBudgetExceeded,match='CURRENT_EVIDENCE_EXCEEDS_PROMPT_BUDGET'):
        builder.call_macro_api('current unique evidence '*40000)
    assert enforce_request_budget({'current':'safe','unknown':None})['max_request_bytes']==700000

def test_full_audit_is_immutable_hash_verifiable_and_separate_from_prompt(tmp_path):
    audit=[];event_window({'events':[event('old','2020-01-01T00:00:00Z')]},as_of_utc=ASOF,audit=audit)
    document={'omissions':audit,'analysis_as_of_utc':ASOF}
    receipt=persist_audit(tmp_path,document)
    raw=(tmp_path/(digest(document)+'.json')).read_bytes()
    assert json.loads(raw)==document and hashlib.sha256(raw).hexdigest()==receipt['sha256']
    assert digest(document)==receipt['canonical_sha256']
    assert persist_audit(tmp_path,document)==receipt

def test_projection_policy_and_runtime_changes_invalidate_build_fingerprint(tmp_path):
    from contracts.macro_build_budget import build_fingerprint
    (tmp_path/'config').mkdir();(tmp_path/'contracts').mkdir()
    path=tmp_path/'config/macro_prompt_projection_v2.json';path.write_text('policy v1')
    first=build_fingerprint(tmp_path,'POST_CLOSE','2026-11-26')
    path.write_text('policy v2')
    second=build_fingerprint(tmp_path,'POST_CLOSE','2026-11-26')
    assert first!=second
    (tmp_path/'contracts/macro_prompt_policy.py').write_text('runtime revision')
    assert build_fingerprint(tmp_path,'POST_CLOSE','2026-11-26')!=second
