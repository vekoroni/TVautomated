"""Offline business replay: exact three delivered feeds through intake and desk context."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

import pytest
from contracts.macro_feed_delivery import deliver, validate_feed, _check_url
from contracts.macro_health import attach_research_context, assess_macro_health, capture_research_context
from contracts.us_money_index_contract import attach_us_money_index, load_us_money_index_sidecar

FIXTURES = Path(__file__).parent / 'fixtures' / 'macro_delivery_20261022'
NOW = datetime(2026,10,22,12,tzinfo=timezone.utc)
CONFIG = {'expected_feeds':['usmi','news','events'],'max_packet_bytes':10485760,
          'timeout_seconds':1,'max_attempts':1,'https_hosts':[],
          'state_directory':'state','macro_directory':'macro'}

def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding='utf-8')

def setup(tmp_path):
    inbox = tmp_path/'incoming';inbox.mkdir()
    packets=[]
    for feed in CONFIG['expected_feeds']:
        source=FIXTURES/(feed+'.json'); target=inbox/(feed+'.json')
        shutil.copyfile(source,target)
        packets.append({'feed':feed,'revision':51 if feed=='usmi' else 1,
                        'generated_at_utc':'2026-10-21T23:00:00Z','material_change':True,
                        'source':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    path=inbox/'manifest.json'
    doc={'contract_version':'macro_delivery_manifest_v1','packets':packets};write(path,doc)
    return path,doc

def test_all_three_feeds_reach_delivery_and_health_without_authority(tmp_path):
    path,doc=setup(tmp_path)
    receipt=deliver(path,root=tmp_path,config=CONFIG,now=NOW)
    assert receipt['status']=='COMPLETE' and receipt['material_change']
    assert {v['status'] for v in receipt['feeds'].values()}=={'ACCEPTED'}
    raw=json.loads((FIXTURES/'usmi.json').read_text())
    usmi=validate_feed('usmi',raw)
    assert usmi['state']['risk_off_transition'] is None
    assert usmi['source_payload']==raw
    base=json.loads((FIXTURES/'macro.json').read_text())
    base=attach_us_money_index(base,load_us_money_index_sidecar(tmp_path/'macro/avshunter_us_money_index.json'))
    base=attach_research_context(base,tmp_path/'macro')
    base['macro_health']=assess_macro_health(base,report={'data_quality':{'fred_series_retrieved':0}},now=NOW)
    assert base['macro_health']['status']=='DEGRADED'
    assert 'FRED_NO_COVERAGE' in base['macro_health']['issues']
    assert all(v!='UNAVAILABLE' for v in base['macro_health']['feeds'].values())
    assert set(base['extras']['research_source_manifest'])=={'usmi','news','events'}
    for feed in CONFIG['expected_feeds']:
        entry=base['extras']['research_source_manifest'][feed]
        accepted=doc['packets'][CONFIG['expected_feeds'].index(feed)]['sha256']
        assert entry.get('accepted_source_sha256',entry['sha256'])==accepted
        assert entry['sha256']==hashlib.sha256(Path(entry['source_path']).read_bytes()).hexdigest()
        assert hashlib.sha256((tmp_path/'state/archive'/(accepted+'.json')).read_bytes()).hexdigest()==accepted
    bound=capture_research_context(tmp_path/'macro')
    rebound=attach_research_context({},tmp_path/'macro',bound=bound)
    for key in ('sha256','accepted_source_sha256'):
        assert rebound['extras']['research_source_manifest']['events'][key]==base['extras']['research_source_manifest']['events'][key]


def test_duplicate_no_change_and_out_of_order_do_not_regress_latest(tmp_path):
    path,doc=setup(tmp_path);deliver(path,root=tmp_path,config=CONFIG,now=NOW)
    assert not deliver(path,root=tmp_path,config=CONFIG,now=NOW)['material_change']
    old=(tmp_path/'macro/avshunter_us_money_index.json').read_bytes()
    doc['packets'][0]['revision']=50;write(path,doc)
    rejected=deliver(path,root=tmp_path,config=CONFIG,now=NOW)
    assert rejected['feeds']['usmi']['error']=='OUT_OF_ORDER'
    assert (tmp_path/'macro/avshunter_us_money_index.json').read_bytes()==old
    doc['packets'][0]['revision']=51
    for item in doc['packets']:item['no_material_change']=True
    write(path,doc)
    retained=deliver(path,root=tmp_path,config=CONFIG,now=NOW)
    assert {v['status'] for v in retained['feeds'].values()}=={'RETAINED'}
    assert not retained['material_change']

def test_checksum_and_schema_rejection_preserve_previous_and_quarantine(tmp_path):
    path,doc=setup(tmp_path);deliver(path,root=tmp_path,config=CONFIG,now=NOW)
    for e in doc['packets']: e['sha256']='0'*64
    write(path,doc)
    result=deliver(path,root=tmp_path,config=CONFIG,now=NOW)
    assert result['status']=='DEGRADED'
    assert all(x['status']=='REJECTED' for x in result['feeds'].values())
    assert len(list((tmp_path/'state/quarantine').glob('*.receipt.json')))==3
    assert (tmp_path/'macro/avshunter_us_money_index.json').is_file()

def test_unrelated_events_survive_and_same_identity_is_corrected(tmp_path):
    path,doc=setup(tmp_path);deliver(path,root=tmp_path,config=CONFIG,now=NOW)
    packet=json.loads((path.parent/'events.json').read_text())
    old_id=packet['events'][0]['event_id']
    correction=copy.deepcopy(packet['events'][0]);correction['actual']='Scope corrected'
    other=copy.deepcopy(correction);other['event_id']='unrelated_eia_release';other['event_name']='EIA release'
    packet['events']=[correction,other];write(path.parent/'events.json',packet)
    doc['packets'][2].update(revision=2,sha256=hashlib.sha256((path.parent/'events.json').read_bytes()).hexdigest())
    write(path,doc);result=deliver(path,root=tmp_path,config=CONFIG,now=NOW)
    assert result['status']=='COMPLETE'
    events=json.loads((tmp_path/'macro/economic_events_latest.json').read_text())['events']
    assert {e['event_id'] for e in events}=={old_id,'unrelated_eia_release'}
    assert next(e for e in events if e['event_id']==old_id)['actual']=='Scope corrected'

def test_missing_manifest_and_partial_manifest_are_visible(tmp_path):
    result=deliver(tmp_path/'absent.json',root=tmp_path,config=CONFIG,now=NOW)
    assert result['status']=='WAITING_FOR_MANIFEST'
    path,doc=setup(tmp_path);doc['packets']=doc['packets'][:1];write(path,doc)
    result=deliver(path,root=tmp_path,config=CONFIG,now=NOW)
    assert result['status']=='DEGRADED' and result['feeds']['events']['status']=='NOT_DELIVERED'

def test_transport_refuses_unsafe_hosts_and_path_escape(tmp_path):
    with pytest.raises(ValueError):_check_url('http://example.com/a',{'example.com'})
    with pytest.raises(ValueError):_check_url('https://example.com/a',set())
    path,doc=setup(tmp_path);doc['packets'][0]['source']='../../outside.json';write(path,doc)
    result=deliver(path,root=tmp_path,config=CONFIG,now=NOW)
    assert 'inside manifest directory' in result['feeds']['usmi']['error']

def test_future_data_and_writer_collision_fail_visibly(tmp_path):
    path,doc=setup(tmp_path);doc['packets'][0]['generated_at_utc']='2099-01-01T00:00:00Z';write(path,doc)
    assert deliver(path,root=tmp_path,config=CONFIG,now=NOW)['feeds']['usmi']['error']=='FUTURE_TIMESTAMP'
    (tmp_path/'state/writer.lock').write_text('1234')
    with pytest.raises(ValueError,match='writer already locked'):deliver(path,root=tmp_path,config=CONFIG,now=NOW)

def test_invalid_manifest_replaces_old_success_with_failed_receipt(tmp_path):
    path,doc=setup(tmp_path);deliver(path,root=tmp_path,config=CONFIG,now=NOW)
    path.write_text('<html>expired session</html>')
    result=deliver(path,root=tmp_path,config=CONFIG,now=NOW)
    assert result['status']=='FAILED'
    assert json.loads((tmp_path/'state/latest_receipt.json').read_text())['status']=='FAILED'

def test_https_download_is_bounded_and_checks_allowed_host(monkeypatch):
    import contracts.macro_feed_delivery as delivery
    calls=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):calls.append(n);return b'{"ok":true}'
    class Opener:
        def open(self,request,timeout):
            assert request.full_url=='https://exports.example.org/feed.json'
            assert request.get_header('Authorization')=='Bearer unit-test-token'
            return Response()
    monkeypatch.setenv('AVSH_MACRO_DELIVERY_TOKEN','unit-test-token')
    monkeypatch.setattr(delivery,'build_opener',lambda *args:Opener())
    config=dict(CONFIG,https_hosts=['exports.example.org'])
    assert delivery._read('feed.json',base='https://exports.example.org/manifest.json',config=config)==b'{"ok":true}'
    assert calls==[config['max_packet_bytes']+1]

def test_nonfinite_usmi_confidence_is_rejected():
    packet=json.loads((FIXTURES/'usmi.json').read_text())
    packet['current_state']['state_confidence']=float('nan')
    with pytest.raises(ValueError,match='finite'):validate_feed('usmi',packet)
