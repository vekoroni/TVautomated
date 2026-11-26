import copy
import build_macro_json as builder
from contracts.macro_prompt_projection import research_view


def test_only_explicit_older_archive_containers_omitted_with_named_paths():
    original={'source_payload':{'packet_revision':107},'advisory_context':{
        'current':{'actual':None,'counterevidence':'keep'},
        'archived_24nov_intraday_rev103':{'old':'archived'},
        'historical_rev106_quality_arrays':['prior'],
        'historical_revision_73_recovered':True,
        'archived_rev107_current':{'risk':'keep'},
        'latest_24nov_comparator':{'value':3},'rev107_status':{'verified':False}}}
    frozen=copy.deepcopy(original)
    out=builder.current_usmi_prompt_view(original)
    current=out['advisory_context']
    assert 'archived_24nov_intraday_rev103' not in current
    assert 'historical_rev106_quality_arrays' not in current
    for name in ('current','historical_revision_73_recovered','archived_rev107_current',
                 'latest_24nov_comparator','rev107_status'):
        assert current[name]==original['advisory_context'][name]
    assert '/advisory_context/archived_24nov_intraday_rev103' in out['projection_omitted_paths']
    assert original==frozen


def test_unknown_revision_preserves_archive_context():
    original={'advisory_context':{'archived_rev103_rates':{'value':4}}}
    assert builder.current_usmi_prompt_view(original)['advisory_context']==original['advisory_context']


def test_audit_bytes_omitted_explicitly_but_all_events_and_limitations_retained():
    original={'events':[{'event_id':'a','actual':None,'risk':'unverified'}],
              'latest_source_export_lineage':{'original_base64':'AAAA',
                  'original_sha256':'hash','original_byte_length':3,
                  'limitations':['NOT_INDEPENDENTLY_FACT_CHECKED']}}
    view=research_view('events',original)
    assert view['events']==original['events']
    lineage=view['latest_source_export_lineage']
    assert 'original_base64' not in lineage
    assert lineage['original_sha256']=='hash'
    assert lineage['limitations']==original['latest_source_export_lineage']['limitations']
    assert lineage['_projection']['omitted_fields']==['original_base64']
    assert original['latest_source_export_lineage']['original_base64']=='AAAA'
