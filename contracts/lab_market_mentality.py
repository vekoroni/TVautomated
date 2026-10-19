"""Evidence-first crowd interpretation, not a forecast or trade authority.

v1 rules: at least three of four current-session index returns beyond +/-0.25%
describe daily progress; matching five-session returns beyond +/-0.50% describe
multi-session progress. These are provisional descriptive noise floors, not
calibrated predictors. No narrative packet, OI, scenario probabilities, trade
scores or Worker 3 output is accepted as independent evidence.
"""
from datetime import date, datetime
import math

VERSION = 'market_mentality_rules_v1'
INDICES = ('SPY', 'QQQ', 'IWM', 'DIA')
CONDITIONS = {
    'market_trend': ('ABOVE_BOTH', 'ABOVE_LONG_ONLY', 'ABOVE_SHORT_ONLY', 'BELOW_BOTH'),
    'market_breadth': ('LOW', 'MID', 'HIGH'), 'market_vol': ('LOW', 'MID', 'HIGH'),
    'credit': ('WIDENING', 'STABLE', 'TIGHTENING'),
    'liquidity': ('EXPANDING', 'FLAT', 'CONTRACTING'),
    'yields': ('RISING', 'STABLE', 'FALLING'),
    'dollar': ('STRENGTHENING', 'STABLE', 'WEAKENING'),
    'oil': ('RISING', 'STABLE', 'FALLING'),
    'curve_level': ('INVERTED', 'FLAT', 'STEEP'),
    'curve_move': ('STEEPENING', 'STABLE', 'FLATTENING'),
}


def mapping(value):
    return value if isinstance(value, dict) else {}


def number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def evidence_from_board(payload, session, built):
    """Whitelist measured fields. All observations require a usable session clock."""
    block = mapping(payload.get('conditions'))
    states, values, observations = (mapping(block.get(k)) for k in ('current', 'current_values', 'observations'))
    meta = {item.get('key'): item for item in block.get('meta', []) if isinstance(item, dict)}
    evidence = []
    issues = []
    receipts = mapping(payload.get('external'))
    bad_sources = set()
    for key, receipt in receipts.items():
        receipt = mapping(receipt)
        if receipt.get('status') in {'MISSING', 'UNREADABLE', 'STALE'}:
            bad_sources.add(key)
            issues.append(f"{key}: {receipt['status']} at board build")
        try:
            observed = datetime.fromisoformat(str(receipt.get('as_of', '')).replace('Z', '+00:00'))
            if observed.tzinfo and observed > built:
                bad_sources.add(key)
                issues.append(f'{key}: timestamp later than board build; excluded from interpretation')
        except ValueError:
            pass
    for key in CONDITIONS:
        state = states.get(key)
        obs = mapping(observations.get(key))
        inputs = obs.get('inputs') or []
        dates = [item.get('observed') for item in inputs if isinstance(item, dict)]
        if not dates and obs.get('oldest'):
            dates = [obs['oldest']]
        reason = ''
        if state not in CONDITIONS[key]:
            reason = 'Missing or unsupported measured state'
        elif not dates:
            reason = 'Observation dates not supplied'
        else:
            try:
                if any(date.fromisoformat(str(d)) > date.fromisoformat(session) for d in dates):
                    reason = 'Observation later than cash-session cutoff'
            except (ValueError, TypeError):
                reason = 'Invalid observation date'
        if number(obs.get('sessions_old')) is not None and obs['sessions_old'] > (12 if key in {'liquidity', 'dollar'} else 6):
            reason = 'Observation exceeds mentality age guard'
        definition = mapping(meta.get(key)).get('measured')
        if key == 'credit':
            # Board v1 defines this as relative ETF performance, not OAS.
            definition = definition or '20-session HYG vs LQD relative log return; board appetite proxy, not a measured credit spread'
        evidence.append({'id': 'condition:' + key, 'label': mapping(meta.get(key)).get('label', key.replace('_', ' ')),
                         'state': state if state in CONDITIONS[key] else 'UNAVAILABLE',
                         'value': number(values.get(key)), 'definition': definition or 'Classified by the Macroboard condition rules',
                         'source': mapping(meta.get(key)).get('source', 'Macroboard measured conditions'),
                         'observation': obs, 'usable': not reason, 'exclusion': reason,
                         'classification': 'MEASURED_CLASSIFICATION'})
    etfs = mapping(payload.get('etfs'))
    for ticker in (*INDICES, 'XLP', 'XLU', 'XLE'):
        metrics = mapping(mapping(etfs.get(ticker)).get('metrics'))
        for horizon in (1, 5):
            value = number(metrics.get(f'ret_{horizon}d'))
            if value is None:
                continue
            usable = metrics.get('status') == 'FRESH' and metrics.get('last_session') == session
            evidence.append({'id': f'return:{ticker}:{horizon}d', 'label': f'{ticker} {horizon}-session return',
                             'value': value, 'state': 'OBSERVED', 'unit': 'percent',
                             'definition': f'{horizon}-session close-to-close return; not intraday path or investor intent',
                             'source': f'board.etfs.{ticker}.metrics',
                             'observation': {'session': metrics.get('last_session')},
                             'usable': usable, 'exclusion': '' if usable else 'Stale or mismatched price session',
                             'classification': 'OBSERVATION'})
    vix = mapping(payload.get('intel')).get('vix_engine', [])
    for item in reversed(vix if isinstance(vix, list) else []):
        item = mapping(item)
        if item.get('VIX_Obs_Date') != session or number(item.get('VIX_Direct')) is None:
            continue
        usable = 'vix_engine' not in bad_sources and mapping(receipts.get('vix_engine')).get('status') == 'FRESH'
        evidence.append({'id': 'protection:vix', 'label': 'Option-implied volatility context',
                         'value': item['VIX_Direct'], 'state': item.get('VIX_Momentum', 'UNAVAILABLE'),
                         'definition': 'VIX level and producer momentum classification; not a direct measure of fear or hedge flows',
                         'source': 'board.intel.vix_engine', 'observation': {'session': session},
                         'usable': usable, 'exclusion': '' if usable else 'VIX source freshness/cutoff not verified',
                         'classification': 'OBSERVATION'})
        break
    review = mapping(payload.get('review'))
    if review.get('session') == session:
        for ticker in INDICES:
            reaction = mapping(mapping(review.get('instruments')).get(ticker))
            gap, move, threshold = (number(reaction.get(k)) for k in ('gap_pct', 'open_to_close_pct', 'threshold_pct'))
            if None in (gap, move, threshold) or threshold <= 0:
                continue
            failed_up = gap > threshold and move < -threshold
            failed_down = gap < -threshold and move > threshold
            if not failed_up and not failed_down:
                continue
            evidence.append({'id': 'reaction:' + ticker, 'label': ticker + ' opening move versus close',
                             'state': 'OPENING_STRENGTH_FADED' if failed_up else 'OPENING_WEAKNESS_RECOVERED',
                             'value': {'gap_pct': gap, 'open_to_close_pct': move, 'threshold_pct': threshold},
                             'definition': 'Daily opening gap and open-to-close movement against board volatility threshold. No subsequent intraday tests verified.',
                             'source': 'board.review.instruments.' + ticker, 'observation': {'session': session},
                             'usable': True, 'exclusion': '', 'classification': 'MEASURED_CLASSIFICATION'})
    return evidence, issues


def assessment(evidence):
    available = {item['id']: item for item in evidence if item['usable']}
    def state(key):
        return available.get('condition:' + key, {}).get('state')
    def refs(*keys):
        return [key for key in keys if key in available]
    def claim(key, label, text, support=(), contrary=(), missing=(), change=''):
        return {'rule_id': VERSION + ':' + key, 'label': label, 'interpretation': text,
                'classification': 'INFERENCE_NOT_OBSERVED_INTENT',
                'supporting_evidence_ids': refs(*support), 'contrary_evidence_ids': refs(*contrary),
                'missing_inputs': list(missing), 'would_change_view': change}
    daily = {side: [f'return:{ticker}:1d' for ticker in INDICES
                    if f'return:{ticker}:1d' in available and sign * available[f'return:{ticker}:1d']['value'] > .25]
             for side, sign in (('up', 1), ('down', -1))}
    multi = {side: [f'return:{ticker}:5d' for ticker in INDICES
                    if f'return:{ticker}:5d' in available and sign * available[f'return:{ticker}:5d']['value'] > .50]
             for side, sign in (('up', 1), ('down', -1))}
    side = next((side for side in ('up', 'down') if len(daily[side]) >= 3), None)
    persistent = side is not None and len(multi[side]) >= 3
    direction = claim('direction', 'UNRESOLVED', 'The supplied evidence does not establish broad directional progress.',
                      missing=('Three of four current-session index returns beyond the descriptive noise floor',))
    if side:
        direction = claim('direction', ('BUYING' if side == 'up' else 'SELLING') + ('_PROGRESS_1D_5D' if persistent else '_PROGRESS_1D'),
                          f"{'Buying' if side == 'up' else 'Selling'} produced broad daily price progress" +
                          (' with matching five-session progress. This describes results, not a forecast or proof of conviction.' if persistent else '. Persistence across the five-session window is not established.'),
                          daily[side] + (multi[side] if persistent else []), daily['down' if side == 'up' else 'up'],
                          change='A later completed session showing broad progress in the opposite direction would challenge this reading.')
    positive = [key for key in ('return:XLP:1d', 'return:XLU:1d', 'return:XLE:1d') if key in available and available[key]['value'] > .25]
    defensive = len(positive) >= 2 and side == 'down'
    confidence = claim('confidence', 'UNRESOLVED', 'Confidence cannot be inferred reliably from the supplied observations.',
                       missing=('Dated participation and corroborating price/risk-appetite evidence',))
    if state('market_breadth') == 'LOW' and (side or state('credit') == 'WIDENING'):
        support = ['condition:market_breadth'] + daily[side or 'down'] + (['condition:credit'] if state('credit') == 'WIDENING' else [])
        confidence = claim('confidence', 'FRAGILE_SELECTIVE',
                           'Weak participation suggests confidence is selective rather than broadly shared. ' +
                           ('Relative HYG/LQD weakness adds a risk-appetite headwind; it is not a direct spread reading.' if state('credit') == 'WIDENING' else 'Price direction alone does not identify motives.'),
                           support, positive, change='Broader participation together with sustained index buying would challenge this assessment.')
    elif state('market_breadth') == 'HIGH' and side == 'up':
        confidence = claim('confidence', 'BROAD_PARTICIPATION',
                           'Broad participation alongside index gains is consistent with more widely shared willingness to take equity risk.',
                           ['condition:market_breadth'] + daily['up'],
                           ['condition:credit'] if state('credit') == 'WIDENING' else [],
                           change='Narrowing participation or failure of index gains would weaken this interpretation.')
    fear = claim('fear', 'NOT_DIRECTLY_MEASURED', 'Fear is not directly measured. Realised volatility alone cannot establish panic or complacency.',
                 missing=('Current, dated protection-demand or positioning evidence',))
    if available.get('protection:vix', {}).get('state') == 'RISING':
        fear = claim('fear', 'CONCERN_SUGGESTED',
                     'Rising option-implied volatility is consistent with greater concern about price variation. It does not establish hedge buying, panic or participant motives.',
                     ['protection:vix'], ['condition:market_vol'] if state('market_vol') == 'LOW' else [],
                     change='Easing implied volatility alongside improved participation would challenge the concern interpretation.')
    urgency = claim('urgency', 'INSUFFICIENT_EXECUTION_EVIDENCE',
                    'Trading urgency cannot be classified as orderly or dislocated from daily returns and volatility alone.',
                    ['condition:market_vol'], missing=('Intraday trading speed', 'Bid/ask spread evolution', 'Executable liquidity'),
                    change='Dated intraday speed and liquidity observations are required to assess urgency.')
    positioning = claim('positioning', 'UNKNOWN',
                        'Actual crowd holdings, crowdedness and forced-liquidation exposure are not established. Sector returns, OI and price moves are not ownership records.',
                        missing=('Validated, dated positioning or ownership evidence',))
    headline = 'Crowd mentality unresolved'
    if defensive:
        headline = 'Defensive selectivity; sellers making daily progress'
    elif confidence['label'] == 'FRAGILE_SELECTIVE':
        headline = 'Fragile confidence; participation is selective'
    elif confidence['label'] == 'BROAD_PARTICIPATION':
        headline = 'Broader confidence supported by participation'
    elif side:
        headline = 'Price progress is visible; crowd motives remain uncertain'
    summary = confidence['interpretation'] + ' ' + direction['interpretation']
    if defensive:
        summary += ' Gains in defensive/energy proxies alongside index weakness suggest selectivity, not proof of indiscriminate liquidation or verified fund flows.'
    behaviours = []
    if defensive:
        behaviours.append(claim('selectivity', 'RISK_PREFERENCE_DIFFERENTIATION',
                                'Some defensive/energy prices advanced while major indices fell. This is consistent with selective risk preference, not a measurement of money rotating between holders.',
                                positive + daily['down'], change='Broad losses across those proxies as well would weaken the selectivity reading.'))
    if state('market_trend') in {'ABOVE_BOTH', 'ABOVE_LONG_ONLY'} and side == 'down':
        behaviours.append(claim('horizons', 'TIME_HORIZON_DISAGREEMENT',
                                'Recent selling coexists with a longer-term trend reference that is still positive. Participants operating over different horizons may respond differently; one crowd consensus is not established.',
                                ['condition:market_trend'] + daily['down'], change='The trend reference and recent price progress aligning would reduce this disagreement.'))
    attempts = []
    for key, item in available.items():
        if not key.startswith('reaction:'):
            continue
        faded = item['state'] == 'OPENING_STRENGTH_FADED'
        attempts.append({'instrument': key.split(':')[1], 'evidence_ids': [key],
                         'attempt': 'The session opened above the previous close.' if faded else 'The session opened below the previous close.',
                         'response': 'The opening strength was followed by a material open-to-close decline.' if faded else 'The opening weakness was followed by a material open-to-close recovery.',
                         'possible_consequence': 'Buyers of opening strength may become less willing to chase a subsequent rebound; their actual positions are unknown.' if faded else 'Sellers of opening weakness may reassess further downside expectations; actual short positions and covering are unobserved.',
                         'changes_interpretation': 'A subsequent sustained recovery would challenge the failed-strength reading.' if faded else 'A subsequent sustained decline would challenge the recovered-weakness reading.',
                         'limit': 'Daily-bar evidence only. Intraday acceptance, subsequent tests and a news-driven expectation are not verified.'})
    sensitivities = []
    if confidence['supporting_evidence_ids']:
        sensitivities.append({'title': 'What could restore or sustain confidence?',
                              'watch_for': 'Wider participation and broad index gains that persist beyond a single opening move.',
                              'possible_reaction': 'Greater willingness to participate could become more broadly shared; that response must be observed, not assumed.',
                              'would_challenge': 'Another narrowing rally or failure to hold progress.',
                              'evidence_ids': confidence['supporting_evidence_ids'], 'testability': 'Subsequent completed-session observations required'})
    if side:
        sensitivities.append({'title': 'What could expose a failed directional expectation?',
                              'watch_for': 'Broad opposite-direction price progress with matching participation, rather than an isolated index bounce.',
                              'possible_reaction': 'Participants may reassess continuation expectations. Squeezes and forced exits cannot be asserted without positioning evidence.',
                              'would_challenge': 'Continued same-direction progress without broad opposing participation.',
                              'evidence_ids': direction['supporting_evidence_ids'], 'testability': 'Subsequent completed-session observations required'})
    return {'headline': headline, 'summary': summary,
            'axes': {'confidence': confidence, 'fear': fear, 'directional_progress': direction, 'urgency': urgency, 'positioning': positioning},
            'behaviours': behaviours, 'attempt_response': attempts, 'reaction_sensitivities': sensitivities,
            'evidence_basis': 'CORROBORATED_PROXY_INTERPRETATION' if confidence['label'] != 'UNRESOLVED' and side else 'LIMITED_OR_MIXED_EVIDENCE'}


def compare_previous(document, previous):
    if not previous or previous.get('calculation_version') != VERSION:
        return {'state': 'NO_COMPARABLE_BASELINE', 'summary': 'No comparable Market Mentality assessment has been published yet.', 'items': []}
    old = {item['id']: item for item in previous.get('evidence', [])}
    changes = []
    for item in document['evidence']:
        prior = old.get(item['id'])
        if not prior or not prior['usable'] or not item['usable'] or prior.get('definition') != item.get('definition'):
            continue
        if (prior.get('state'), prior.get('value')) != (item.get('state'), item.get('value')):
            changes.append({'evidence_id': item['id'], 'before': {'state': prior.get('state'), 'value': prior.get('value')},
                            'after': {'state': item.get('state'), 'value': item.get('value')}})
    same_session = document['as_of_session'] == previous['as_of_session']
    if changes:
        summary = 'Saved observations were revised within the same session; this is not a new observed market reaction.' if same_session else 'Observed behaviour changed across completed-session assessments.'
        state = 'SAME_SESSION_DATA_REVISION' if same_session else 'OBSERVATIONS_CHANGED'
    else:
        summary = 'No change in compared observations. A refreshed publication is not a new crowd reaction.' if same_session else 'New session; comparable observations retain the same classifications and values.'
        state = 'UNCHANGED_OBSERVATIONS'
    return {'state': state, 'summary': summary, 'previous_revision': previous.get('revision'),
            'previous_session': previous.get('as_of_session'), 'compared_changes': len(changes), 'items': changes[:12]}


def trade_context(document, fields, review_revision):
    """Advisory overlay only: never rewrite the frozen thesis or claim past use."""
    side = fields.get('direction')
    axes = document['mentality']['axes']
    caution = 'No assigned thesis direction is recorded; no direction has been inferred.'
    if side == 'CALL':
        caution = ('Broad confidence is fragile: check that this bullish thesis has its own buying/participation evidence.'
                   if axes['confidence']['label'] == 'FRAGILE_SELECTIVE' else
                   'Review whether observed participation supports this bullish thesis; the backdrop does not validate its entry or option price.')
    elif side == 'PUT':
        caution = ('Saved index selling provides context consistent with a downside thesis, not evidence that this ticker or its put is a viable trade.'
                   if axes['directional_progress']['label'].startswith('SELLING_') else
                   'Broad selling progress is not established; this downside thesis needs its own evidence.')
    return {'ticker': fields.get('ticker'), 'saved_direction': side, 'review_revision': review_revision,
            'latest_mentality_revision': document['revision'], 'latest_market_session': document['as_of_session'],
            'frozen_mentality_state': 'NOT_RECORDED_WITH_THIS_REVIEW',
            'interpretation': caution, 'authority': 'ADVISORY_ONLY',
            'disclosure': 'Latest post-run context, not evidence used to produce the frozen decision. Confirm entry, invalidation, spread, volatility exposure and price path separately.'}
