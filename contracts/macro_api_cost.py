"""Atomic local USD reservations and provider usage receipts. Never calls a provider itself."""
from datetime import datetime, timezone
from contextlib import contextmanager
from decimal import Decimal, ROUND_CEILING, InvalidOperation
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import uuid
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
LOG = logging.getLogger(__name__)


class ApiCostLimit(RuntimeError):
    pass


def policy(root, day=None):
    p = json.loads((Path(root) / 'config/macro_api_cost_v1.json').read_text())
    if Decimal(str(p['daily_cap_usd'])) <= 0:
        raise ApiCostLimit('Invalid daily USD cap')
    day = day or datetime.now(timezone.utc).astimezone(ET).date().isoformat()
    from datetime import date
    date.fromisoformat(day)
    overrides = p.get('one_off_daily_caps', {})
    if not isinstance(overrides, dict):raise ApiCostLimit('Invalid one-off USD cap policy')
    if day in overrides:
        grant = overrides[day]
        if not isinstance(grant, dict) or not grant.get('authority'):
            raise ApiCostLimit('One-off USD cap authority missing')
        try:cap = Decimal(str(grant.get('daily_cap_usd')))
        except (InvalidOperation,TypeError,ValueError) as error:
            raise ApiCostLimit('Invalid one-off daily USD cap') from error
        if not cap.is_finite() or cap <= 0:raise ApiCostLimit('Invalid one-off daily USD cap')
        p['standing_daily_cap_usd'] = p['daily_cap_usd']
        p['daily_cap_usd'] = float(cap)
        p['one_off_cap_day'] = day
    return p


@contextmanager
def _db(root):
    path = Path(root) / 'data/macro/delivery/api_usage.sqlite'
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.execute('''CREATE TABLE IF NOT EXISTS requests (
        id TEXT PRIMARY KEY, day TEXT, started TEXT, build_id TEXT, stage TEXT,
        model TEXT, request_sha256 TEXT, reserved_microusd INTEGER,
        charged_microusd INTEGER, status TEXT, receipt TEXT)''')
    try:
        yield db
    finally:
        db.close()


def _micro(dollars):
    return int((Decimal(str(dollars)) * 1000000).to_integral_value(rounding=ROUND_CEILING))


def _legacy_spend_unknown(root, day, activation):
    path = Path(root) / 'data/macro/delivery/full_build_attempts.sqlite'
    if not path.exists():
        return False
    with sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True) as db:
        return bool(db.execute('''SELECT 1 FROM attempts a WHERE day=? AND started<?
            AND (reason='HISTORICAL_FULL' OR EXISTS (SELECT 1 FROM stages s WHERE s.id=a.id)) LIMIT 1''',
            (day, activation)).fetchone())


def _quote(root, request, input_token_estimate=None, *, day=None):
    p = policy(root, day)
    if set(request) - {'model', 'max_tokens', 'system', 'messages', 'timeout'}:
        raise ApiCostLimit('Unsupported API request options: no unpriced routing/tools')
    model = request['model']
    if model not in p['models']:
        raise ApiCostLimit('API_MODEL_NOT_PRICED:' + model)
    if not isinstance(request['max_tokens'], int) or not 0 < request['max_tokens'] <= p['max_output_tokens']:
        raise ApiCostLimit('API_OUTPUT_LIMIT')
    if not isinstance(request.get('system', ''), str) or any(
        set(m) != {'role', 'content'} or not isinstance(m['content'], str) for m in request['messages']
    ):
        raise ApiCostLimit('Only text messages are budgeted')
    raw = json.dumps(request, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(raw) > p['max_request_bytes']:
        raise ApiCostLimit(f'API_INPUT_TOO_LARGE:{len(raw)}>{p["max_request_bytes"]}')
    prices = p['models'][model]
    if any(Decimal(str(prices[k])) < 0 for k in ('input_per_million_usd', 'output_per_million_usd',
                                              'cache_write_per_million_usd', 'cache_read_per_million_usd')):
        raise ApiCostLimit('Invalid negative token price')
    if input_token_estimate is not None and (type(input_token_estimate) is not int or input_token_estimate < 0):
        raise ApiCostLimit('Invalid provider token-count estimate')
    bound = int(((len(raw) if input_token_estimate is None else input_token_estimate) + 8192) * 1.25) + 1
    maximum = _micro((Decimal(bound) * Decimal(str(prices['input_per_million_usd'])) +
                      Decimal(request['max_tokens']) * Decimal(str(prices['output_per_million_usd']))) / 1000000)
    return p, raw, prices, bound, maximum


def reserve_request(root, stage, request, *, now=None, input_token_estimate=None):
    """Atomically reserve input tokens with 25% + framing headroom and the whole output cap.

    Without a free provider count, use the more conservative UTF-8 byte bound.
    Failed/unknown usage keeps the reservation, including across process restarts.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ApiCostLimit('Aware clock required')
    day = now.astimezone(ET).date().isoformat()
    p, raw, prices, bound, maximum = _quote(root, request, input_token_estimate, day=day)
    from contracts.macro_postclose_exception import build_authorization
    exception = build_authorization(root, os.environ.get('AVSH_FULL_BUILD_ID'), now=now)
    if exception and stage != 'MACRO_SYNTHESIS':
        raise ApiCostLimit('POST_CLOSE_EXCEPTION_SYNTHESIS_ONLY')
    if _legacy_spend_unknown(root, day, p['activated_at_utc']) and not exception:
        raise ApiCostLimit('API_UNTRACKED_PRIOR_SPEND: same-day legacy usage unknown; wait for next ET day')
    with _db(root) as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM requests WHERE day=? AND status='BOUND_EXCEEDED' LIMIT 1", (day,)).fetchone():
            raise ApiCostLimit('API_COST_BOUND_BREACHED: review ledger before further spending')
        used = db.execute('SELECT COALESCE(SUM(charged_microusd),0) FROM requests WHERE day=?', (day,)).fetchone()[0]
        if used + maximum > _micro(p['daily_cap_usd']):
            raise ApiCostLimit('DAILY_API_DOLLAR_CAP_REACHED')
        if exception:
            extra_used = db.execute('SELECT COALESCE(SUM(charged_microusd),0) FROM requests WHERE build_id=?',
                                    (os.environ['AVSH_FULL_BUILD_ID'],)).fetchone()[0]
            if extra_used + maximum > _micro(exception['additional_request_cap_usd']):
                raise ApiCostLimit('POST_CLOSE_EXCEPTION_DOLLAR_CAP_REACHED')
        token = str(uuid.uuid4())
        db.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                   (token, day, now.isoformat(), os.environ.get('AVSH_FULL_BUILD_ID'), stage, request['model'],
                    hashlib.sha256(raw).hexdigest(), maximum, maximum, 'RESERVED',
                    json.dumps({'pricing': prices, 'input_token_bound': bound, 'provider_input_token_estimate': input_token_estimate, 'max_output_tokens': request['max_tokens']})))
        db.execute('COMMIT')
    return token


def _finish(root, token, status, receipt, charge=None):
    with _db(root) as db:
        db.execute('BEGIN IMMEDIATE')
        original = json.loads(db.execute('SELECT receipt FROM requests WHERE id=?', (token,)).fetchone()[0])
        receipt = {**original, **receipt}
        if charge is None:
            db.execute('UPDATE requests SET status=?,receipt=? WHERE id=?', (status, json.dumps(receipt), token))
        else:
            db.execute('UPDATE requests SET status=?,receipt=?,charged_microusd=? WHERE id=?',
                       (status, json.dumps(receipt), charge, token))
        db.execute('COMMIT')


def record_response(root, token, response):
    """Missing/invalid usage retains the full reservation; never invents zero usage."""
    usage = getattr(response, 'usage', None)
    usage = usage.model_dump() if hasattr(usage, 'model_dump') else (usage if isinstance(usage, dict) else vars(usage) if usage else {})
    receipt = {'usage': usage, 'request_id': getattr(response, '_request_id', None),
               'response_id': getattr(response, 'id', None), 'model': getattr(response, 'model', None),
               'stop_reason': getattr(response, 'stop_reason', None)}
    with _db(root) as db:
        model, reserved, original = db.execute('SELECT model,reserved_microusd,receipt FROM requests WHERE id=?', (token,)).fetchone()
    original = json.loads(original)
    prices = original['pricing']
    names = ('input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')
    counts = {k: usage.get(k, 0) for k in names}
    # The SDK defaults non-applicable cache counters to None. These requests
    # contain only strings and cannot enable prompt caching; preserve the raw
    # receipt while treating absent cache activity as zero for pricing.
    for key in names[2:]:
        if counts[key] is None:
            counts[key] = 0
    if any(k not in usage for k in names[:2]) or any(type(v) is not int or v < 0 for v in counts.values()) or receipt['model'] != model:
        _finish(root, token, 'USAGE_UNKNOWN_RESERVED', receipt)
        raise ApiCostLimit('API usage missing or returned model unpriced; maximum reservation retained')
    charge = _micro((Decimal(counts['input_tokens']) * Decimal(str(prices['input_per_million_usd'])) +
                     Decimal(counts['output_tokens']) * Decimal(str(prices['output_per_million_usd'])) +
                     Decimal(counts['cache_creation_input_tokens']) * Decimal(str(prices['cache_write_per_million_usd'])) +
                     Decimal(counts['cache_read_input_tokens']) * Decimal(str(prices['cache_read_per_million_usd']))) / 1000000)
    receipt['estimated_cost_usd'] = charge / 1000000
    breached = charge > reserved or sum(counts[k] for k in names if k != 'output_tokens') > original['input_token_bound'] or counts['output_tokens'] > original['max_output_tokens']
    _finish(root, token, 'BOUND_EXCEEDED' if breached else 'COMPLETE', receipt, charge)
    LOG.info('API usage: %s', json.dumps(receipt))
    if breached:
        raise ApiCostLimit('API reservation bound exceeded; recorded actual usage')
    return receipt


def budgeted_message(root, stage, request, client_factory, *, authorize=True):
    # Validate the request and stop an exhausted/unknown day before even making
    # the free token-count call. The later SQLite reservation handles races.
    day = datetime.now(timezone.utc).astimezone(ET).date().isoformat()
    p, _, prices, _, _ = _quote(root, request, day=day)
    state = usage_status(root, day)
    from contracts.macro_postclose_exception import build_authorization
    exception = build_authorization(root, os.environ.get('AVSH_FULL_BUILD_ID'))
    if state['legacy_usage_unknown'] and not exception:
        raise ApiCostLimit('API_UNTRACKED_PRIOR_SPEND: wait for next ET day')
    minimum = request['max_tokens'] * float(prices['output_per_million_usd']) / 1000000
    if state['accounted_usd'] + minimum > p['daily_cap_usd']:
        raise ApiCostLimit('DAILY_API_DOLLAR_CAP_REACHED')
    # No generation, tools or synthesis occurs in this free endpoint.
    client = client_factory().with_options(max_retries=0)
    count = client.messages.count_tokens(timeout=15,
        **{k: request[k] for k in ('model', 'system', 'messages') if k in request})
    estimate = getattr(count, 'input_tokens', None)
    if type(estimate) is not int or estimate < 0:
        raise ApiCostLimit('Invalid free token count; no generation request sent')
    token = reserve_request(root, stage, request, input_token_estimate=estimate)
    try:
        if authorize:
            from contracts.macro_build_budget import authorize_stage
            build_id = authorize_stage(root, stage)
            with _db(root) as db:
                db.execute('UPDATE requests SET build_id=? WHERE id=?', (build_id, token))
    except Exception as exc:
        _finish(root, token, 'NOT_SENT', {'error_type': type(exc).__name__}, 0)
        raise
    try:
        # Disable SDK retries: every potential paid request needs its own reservation.
        response = client.messages.create(**request)
    except Exception as exc:
        status = getattr(exc, 'status_code', None)
        rejected = status in (400, 401, 403, 404, 413, 422, 429)
        _finish(root, token, 'REJECTED' if rejected else 'UNCERTAIN_RESERVED',
                {'http_status': status, 'error_type': type(exc).__name__}, 0 if rejected else None)
        raise
    record_response(root, token, response)
    return response


def usage_status(root, day):
    path = Path(root) / 'data/macro/delivery/api_usage.sqlite'
    result = {'day': day, 'daily_cap_usd': policy(root, day)['daily_cap_usd'], 'requests': [], 'accounted_usd': 0}
    result['legacy_usage_unknown'] = _legacy_spend_unknown(root, day, policy(root, day)['activated_at_utc'])
    result['scope'] = 'LOCAL_MACRO_ANTHROPIC_REQUESTS_ONLY_NOT_ORGANISATION_BILLING'
    result['remaining_usd'] = None if result['legacy_usage_unknown'] else result['daily_cap_usd']
    if not path.exists():
        return result
    with sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute('SELECT * FROM requests WHERE day=? ORDER BY started', (day,)).fetchall()
    result['requests'] = [{**dict(r), 'receipt': json.loads(r['receipt'])} for r in rows]
    result['accounted_usd'] = sum(r['charged_microusd'] for r in rows) / 1000000
    if not result['legacy_usage_unknown']:
        result['remaining_usd'] = max(0, result['daily_cap_usd'] - result['accounted_usd'])
    return result
