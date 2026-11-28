from copy import deepcopy
from pathlib import Path
import hashlib,json,sqlite3,sys
from flask import Flask
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from contracts.lab_phantom_coverage import attach_phantom_coverage
from contracts.lab_review_projection import publish_review_projection,register_review_routes

def coverage_db(path):
    with sqlite3.connect(path) as c:
        c.executescript('''CREATE TABLE phantom_pair_health(ticker,quote_date,chain_rows,incomplete_greeks,missing_underlying);
        CREATE TABLE phantom_maintenance_pairs(ticker,quote_date,status);
        CREATE TABLE chain_snapshots(ticker,quote_date,option_symbol,iv,delta,gamma,theta,vega,greeks_quality);
        INSERT INTO phantom_pair_health VALUES('NAN','2026-11-20',10,3,1);
        INSERT INTO phantom_maintenance_pairs VALUES('NAN','2026-11-20','IV_UNAVAILABLE');
        INSERT INTO chain_snapshots VALUES('NAN','2026-11-20','C',NULL,NULL,NULL,NULL,NULL,'NO_VALID_PRICE');''')

def test_dated_overlay_keeps_fields_verdict_revision_and_database_bytes(tmp_path):
    path=tmp_path/'p.db';coverage_db(path)
    payload={'run_id':'20261119_234734','revision':'abc','fields':{'ticker':'NAN','contract_symbol':'C','lab_verdict':'MANUAL_REVIEW','contract_iv':.3}}
    before=deepcopy(payload);digest=hashlib.sha256(path.read_bytes()).hexdigest()
    result=attach_phantom_coverage(payload,path)
    assert result['fields']==before['fields'] and result['revision']=='abc' and payload==before
    overlay=result['phantom_coverage_overlay']
    assert overlay['coverage_session']=='2026-11-20'
    assert overlay['snapshot_run_id']=='20261119_234734'
    assert overlay['exact_contract_state']=='INCOMPLETE_GREEKS'
    assert overlay['iv_state']=='IV_UNAVAILABLE' and overlay['incomplete_greek_rows']==3
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    with sqlite3.connect(path,timeout=.1) as c:c.execute('BEGIN EXCLUSIVE')

def test_missing_contract_is_scope_limitation_not_zero_or_rejection(tmp_path):
    path=tmp_path/'p.db';coverage_db(path)
    out=attach_phantom_coverage({'run_id':'older','rows':[{'ticker':'SYM','contract_symbol':'not_stored'}]},path)
    detail=out['rows'][0]['phantom_coverage_overlay']
    assert detail['exact_contract_state']=='NOT_IN_STORED_SESSION_SCOPE'
    assert detail['incomplete_greek_rows'] is None
    assert detail['iv_state']=='UNASSESSED'

def test_absent_or_broken_coverage_is_explicit_not_false_zero(tmp_path):
    out=attach_phantom_coverage({'run_id':'old'},tmp_path/'none.db')
    assert out['phantom_coverage_overlay']['state']=='UNAVAILABLE'
    path=tmp_path/'bad.db';path.write_bytes(b'not SQLite')
    assert attach_phantom_coverage({},path)['phantom_coverage_overlay']['state']=='UNAVAILABLE'

def test_route_overlay_preserves_immutable_published_review(tmp_path):
    path=tmp_path/'p.db';coverage_db(path)
    book={'run_id':'TEST_RUN','candidate_count':1,'rows':[{'ticker':'NAN','direction':'CALL','contract_symbol':'C','lab_verdict':'MANUAL_REVIEW','lab_rank':7}]}
    receipt=publish_review_projection(book,tmp_path/'runs')
    files=list((tmp_path/'runs').rglob('*'));before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
    app=Flask(__name__);register_review_routes(app,tmp_path/'runs',lambda data:attach_phantom_coverage(data,path))
    client=app.test_client()
    summary=client.get('/api/lab/TEST_RUN/summary').get_json()
    rows=client.get('/api/lab/TEST_RUN/rows').get_json()
    key=rows['rows'][0]['row_key']
    response=client.get('/api/lab/TEST_RUN/rows/'+key)
    assert response.status_code==200
    card=response.get_json()
    assert card['fields']['lab_verdict']=='MANUAL_REVIEW' and card['fields']['lab_rank']==7
    assert card['revision']==summary['revision']==receipt['revision']
    assert card['phantom_coverage_overlay']['coverage_session']=='2026-11-20'
    assert response.headers['Cache-Control']=='no-store'
    assert before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}

def test_ui_dated_warning_is_escaped_and_not_a_frozen_field():
    js=(ROOT/'intelligence-lab/static/review-app.js').read_text(encoding='utf-8-sig')
    assert 'Dated Phantom coverage' in js and 'pairs([[\'Coverage session\'' in js
    assert 'Historical snapshot run' in js and 'not a fresh quote' in js
