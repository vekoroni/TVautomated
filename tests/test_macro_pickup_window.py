from datetime import datetime
import json
from pathlib import Path
import pytest
from contracts.macro_pickup_window import pickup_window_state

CONFIG=json.loads((Path(__file__).resolve().parents[1]/'config/macro_delivery_v1.json').read_text())


@pytest.mark.parametrize('stamp',[
    '2026-11-16T06:00:00+00:00', '2026-11-16T08:08:00+00:00',
    '2026-11-16T11:20:00+00:00', '2026-11-16T12:20:00+00:00',
    '2026-11-16T19:15:00+00:00', '2026-11-16T21:30:00+00:00',
    '2026-11-14T15:39:00+00:00', '2026-11-15T09:56:00+00:00',
    '2026-07-20T05:00:00+00:00',
])
def test_pickup_covers_preparation_builds_and_weekends_across_clock_changes(stamp):
    assert pickup_window_state(datetime.fromisoformat(stamp),CONFIG)['state']=='PICKUP_OPEN'


@pytest.mark.parametrize('stamp',['2026-11-16T05:59:59+00:00','2026-11-16T23:00:00+00:00'])
def test_outside_window_remains_explicit(stamp):
    assert pickup_window_state(datetime.fromisoformat(stamp),CONFIG)['state']=='OUTSIDE_PICKUP_WINDOW'


def test_naive_clock_rejected_and_funded_build_ownership_unchanged():
    with pytest.raises(ValueError,match='TIMEZONE_AWARE'):
        pickup_window_state(datetime(2026,11,16,8),CONFIG)
    assert CONFIG['publication_mode']=='FULL'
