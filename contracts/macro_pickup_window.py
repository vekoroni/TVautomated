"""Clock-injected local export-pickup window. No providers or writes."""
from datetime import datetime
from zoneinfo import ZoneInfo


def pickup_window_state(clock: datetime, config: dict) -> dict:
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError('PICKUP_CLOCK_MUST_BE_TIMEZONE_AWARE')
    policy=config['pickup_window']
    if policy['authority']!='TRANSFER_EXISTING_EXPORTS_ONLY':
        raise ValueError('PICKUP_AUTHORITY_NOT_APPROVED')
    local=clock.astimezone(ZoneInfo(policy['timezone']))
    first=datetime.strptime(policy['start'],'%H:%M').time()
    last=datetime.strptime(policy['end_exclusive'],'%H:%M').time()
    if first>=last:raise ValueError('PICKUP_WINDOW_MUST_NOT_CROSS_MIDNIGHT')
    opened=local.weekday() in policy['days'] and first<=local.time().replace(tzinfo=None)<last
    return {'state':'PICKUP_OPEN' if opened else 'OUTSIDE_PICKUP_WINDOW',
            'observed_at_local':local.isoformat(),'timezone':policy['timezone'],
            'authority':policy['authority'],'start':policy['start'],'end_exclusive':policy['end_exclusive']}
