"""Saved SQLite fixtures; no providers, live writes or historical relabelling."""
from datetime import datetime,timezone
from pathlib import Path
import json,sqlite3
import pytest
from contracts import phantom_prospective_evidence as cap

NOW=datetime(2026,11,22,12,tzinfo=timezone.utc)
RUN='test'

def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(cap,'_utc_now',lambda:NOW)
    db=tmp_path/'q.db';c=sqlite3.connect(db);c.execute('PRAGMA journal_mode=WAL')
    c.execute('CREATE TABLE chain_snapshots('+','.join(cap.QUOTE_FIELDS)+',PRIMARY KEY(ticker,quote_date,option_symbol))')
    c.execute('CREATE TABLE unrelated (n)');c.execute('INSERT INTO unrelated VALUES (0)')
    rows=[]
    for ticker in ('NAN','SYM'):
        sym=ticker+'261218C00100000';rows.append(dict(ticker=ticker,contract_symbol=sym))
        q=dict.fromkeys(cap.QUOTE_FIELDS)
        q.update(ticker=ticker,quote_date='2026-11-20',option_symbol=sym,bid=1.,ask=1.1,bid_size=10,ask_size=10,
            underlying_price=100.,updated_ts=1795208400,created_at_utc='2026-11-20T21:01:00Z')
        c.execute('INSERT INTO chain_snapshots VALUES ('+','.join('?' for _ in cap.QUOTE_FIELDS)+')',[q[k] for k in cap.QUOTE_FIELDS])
    c.commit();c.close()
    run=tmp_path/RUN;run.mkdir();source=tmp_path/'saved.json';source.write_text(json.dumps(rows))
    return db,run,source,rows

def capture(f):
    db,run,source,rows=f
    return cap.capture_candidates(run,source,rows,run_id=RUN,session='2026-11-20',database=db,score_version='test',replay_only=True)

def publish(f,receipt):
    return cap.capture_predictions(f[1],receipt,[dict(ticker=r['ticker'],run_id=RUN,
        phantom_promoted_verdict='NONE',phantom_ois_adjustment=0) for r in f[3]],run_id=RUN)

def test_unrelated_wal_commit_no_longer_causes_false_capture_failure(tmp_path,monkeypatch):
    f=setup(tmp_path,monkeypatch);original=cap._fetch_quote;writer=sqlite3.connect(f[0]);changed=False
    def fetch(*args):
        nonlocal changed
        result=original(*args)
        if not changed:
            writer.execute('UPDATE unrelated SET n=n+1');writer.commit();changed=True
        return result
    monkeypatch.setattr(cap,'_fetch_quote',fetch)
    before=cap.db_fingerprint(f[0]);receipt=capture(f);packet=cap.read_packet(receipt['path'])
    assert before!=cap.db_fingerprint(f[0]) # The old guard would have aborted.
    assert packet['source_snapshot']['physical_metadata_changed']
    assert packet['source_snapshot']['unique_keys']==2
    assert publish(f,receipt)['status']=='CAPTURED'
    writer.close()

def test_transaction_never_mixes_candidate_rows_from_different_commits(tmp_path,monkeypatch):
    f=setup(tmp_path,monkeypatch);original=cap._fetch_quote;writer=sqlite3.connect(f[0]);changed=False
    def fetch(*args):
        nonlocal changed
        result=original(*args)
        if not changed:
            writer.execute("UPDATE chain_snapshots SET bid=.8 WHERE ticker='SYM'");writer.commit();changed=True
        return result
    monkeypatch.setattr(cap,'_fetch_quote',fetch)
    receipt=capture(f);packet=cap.read_packet(receipt['path'])
    assert [r['quote']['bid'] for r in packet['rows']]==[1.,1.]
    with pytest.raises(ValueError,match='Selected quote rows changed'):publish(f,receipt)
    writer.close()

@pytest.mark.parametrize('sql',["UPDATE chain_snapshots SET bid=.7 WHERE ticker='NAN'",
    "DELETE FROM chain_snapshots WHERE ticker='SYM'",
    "UPDATE chain_snapshots SET created_at_utc='2026-11-22T11:00:00Z' WHERE ticker='SYM'"])
def test_real_selected_row_mutations_still_block_publication(tmp_path,monkeypatch,sql):
    f=setup(tmp_path,monkeypatch);receipt=capture(f)
    c=sqlite3.connect(f[0]);c.execute(sql);c.commit();c.close()
    with pytest.raises(ValueError,match='Selected quote rows changed'):publish(f,receipt)

def test_captured_absence_becoming_present_is_not_silently_replaced(tmp_path,monkeypatch):
    f=setup(tmp_path,monkeypatch);c=sqlite3.connect(f[0]);c.execute("DELETE FROM chain_snapshots WHERE ticker='SYM'");c.commit();c.close()
    receipt=capture(f);packet=cap.read_packet(receipt['path'])
    assert packet['rows'][1]['quote'] is None
    c=sqlite3.connect(f[0]);c.execute("INSERT INTO chain_snapshots (ticker,quote_date,option_symbol) VALUES ('SYM','2026-11-20','SYM261218C00100000')");c.commit();c.close()
    with pytest.raises(ValueError,match='Selected quote rows changed'):publish(f,receipt)

def test_metadata_only_changes_and_checkpoint_do_not_invalidate_equal_quotes(tmp_path,monkeypatch):
    f=setup(tmp_path,monkeypatch);receipt=capture(f)
    c=sqlite3.connect(f[0]);c.execute('UPDATE unrelated SET n=2');c.commit();c.execute('PRAGMA wal_checkpoint(TRUNCATE)');c.close()
    assert publish(f,receipt)['status']=='CAPTURED'

def test_legacy_packets_keep_their_original_guard(tmp_path,monkeypatch):
    f=setup(tmp_path,monkeypatch);receipt=capture(f);p=cap.read_packet(receipt['path']);p.pop('source_snapshot');p.pop('content_sha256')
    old=cap._write(f[1],p)
    monkeypatch.setattr(cap,'db_fingerprint',lambda *a:{'changed':True})
    with pytest.raises(ValueError,match='Quote store changed'):publish(f,old)
