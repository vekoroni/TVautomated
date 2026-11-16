"""Exercise the packaged refresher/collector API with injected saved bars only."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest
from scripts import refresh_futures_snapshot as refresh
from contracts.macro_market_refresh_gate import verify_refresh


@pytest.mark.parametrize('future',[False,True])
def test_packaged_collector_refresh_and_gate_without_network(tmp_path,future):
    start=datetime(2026,11,16,9,25,tzinfo=timezone.utc)
    finish=start+timedelta(seconds=10)
    quote=finish+timedelta(seconds=1) if future else start+timedelta(seconds=5)
    close=datetime(2026,11,13,21,tzinfo=timezone.utc)
    reference=close-timedelta(minutes=5)
    def history(symbol,period,interval):
        return pd.DataFrame({'Close':[100.,101.]},index=pd.to_datetime([reference,quote],utc=True))
    class Response:
        status_code=200
        def json(self):
            return {'s':'ok','t':[int(reference.timestamp()),int(quote.timestamp())],
                    'c':[100.,101.],'v':[1,1],
                    'data':{'current_price':101.,'prev_day_close':100.}}
    def offline_get(*args,**kwargs): return Response()
    parent=tmp_path/'overnight_20261116_080000.json'
    parent.write_text(json.dumps({'us_reference_close_utc':close.isoformat(),'groups':{}}))
    doc=refresh.refresh_document(json.loads(parent.read_text()),history=history,
        http_get=offline_get,marketdata_key='offline-fixture-only',now=start,
        all_market_data=True,completion_clock=lambda:finish)
    assert doc['as_of_utc']==finish.isoformat().replace('+00:00','Z')
    assert doc['market_refresh']['errors']==[]
    assert doc['groups']['fx'][0]['last_bar_utc']==quote.isoformat().replace('+00:00','Z')
    doc['futures_refresh'].update(parent_file=parent.name,
        parent_sha256=hashlib.sha256(parent.read_bytes()).hexdigest())
    (tmp_path/'overnight_20261116_092510.json').write_text(json.dumps(doc))
    if future:
        with pytest.raises(ValueError,match='MARKET_SOURCE_TIMESTAMP_INVALID'):
            verify_refresh(tmp_path,not_before=start,now=finish)
    else:
        assert verify_refresh(tmp_path,not_before=start,now=finish)['status']=='READY_FOR_FULL'
