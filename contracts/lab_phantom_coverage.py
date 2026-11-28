"""Bounded, read-only current coverage overlay; never a snapshot correction.

No live quotes, revaluation, publication or trading decisions. Missing stored
contracts are scope limitations, not proof of a defective trade or no listing.
"""
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import sqlite3

NOTICE = ('Current stored Phantom coverage, not a live quote or refreshed card. '
          'Historical snapshot, Greeks, verdict and rank remain unchanged. '
          'Missing contracts may be outside the stored 7–60 DTE / 40-strike scope.')


def attach_phantom_coverage(payload, db_path):
    result = deepcopy(payload)
    base = {'state':'UNAVAILABLE', 'coverage_session':None,
            'snapshot_run_id':payload.get('run_id'), 'authority':'DISPLAY_ONLY', 'notice':NOTICE}
    result['phantom_coverage_overlay'] = base
    path = Path(db_path)
    if not path.is_file():
        return result
    try:
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=1)) as c:
            c.execute('PRAGMA query_only=ON')
            day = c.execute('SELECT MAX(quote_date) FROM phantom_pair_health').fetchone()[0]
            base.update(state='DATED_COVERAGE' if day else 'UNASSESSED', coverage_session=day)
            targets = result.get('rows', [result] if 'fields' in result else [])
            if len(targets)>200:
                raise ValueError('Coverage overlay is page/card bounded')
            for target in targets:
                fields = target.get('fields', target)
                ticker, symbol = fields.get('ticker'), fields.get('contract_symbol')
                h = c.execute('SELECT chain_rows,incomplete_greeks,missing_underlying FROM phantom_pair_health WHERE ticker=? AND quote_date=?', (ticker,day)).fetchone()
                q = c.execute('SELECT status FROM phantom_maintenance_pairs WHERE ticker=? AND quote_date=?', (ticker,day)).fetchone()
                exact = c.execute('SELECT iv,delta,gamma,theta,vega,greeks_quality FROM chain_snapshots WHERE ticker=? AND quote_date=? AND option_symbol=?', (ticker,day,symbol)).fetchone() if symbol else None
                detail = {**base, 'ticker':ticker, 'iv_state':q[0] if q else 'UNASSESSED',
                          'chain_rows':h[0] if h else None, 'incomplete_greek_rows':h[1] if h else None,
                          'missing_underlying_rows':h[2] if h else None,
                          'exact_contract_state':('NO_SELECTED_CONTRACT' if not symbol else
                              'NOT_IN_STORED_SESSION_SCOPE' if exact is None else
                              'INCOMPLETE_GREEKS' if any(v is None for v in exact[:5]) else 'STORED_REQUIRES_QUALIFICATION'),
                          'exact_contract_quality':exact[5] if exact else None}
                target['phantom_coverage_overlay'] = detail
                from scripts.phantom_greek_assessment import has_table,session_assessment,FIELDS,effective_rows
                if has_table(c):
                    assessed=session_assessment(c,day,[ticker])
                    detail.update(unassessed_greek_rows=assessed['unassessed_rows'],
                                  assessed_excluded_rows=assessed['excluded_rows'],
                                  assessment_calc_version=assessed['calc_version'])
                    if exact is not None:
                        record=c.execute('SELECT '+','.join(FIELDS)+' FROM chain_snapshots WHERE ticker=? AND quote_date=? AND option_symbol=?',(ticker,day,symbol)).fetchone()
                        analytical=effective_rows(c,[dict(zip(FIELDS,record))])[0]
                        status=analytical.get('assessment_status','UNASSESSED')
                        detail['exact_contract_assessment_status']=status
                        detail['exact_contract_state']=('ASSESSED_MODEL_POINT_ADVISORY' if status=='MODEL_POINT_QUALIFIED' else
                             'ASSESSED_VENDOR_POINT' if status=='VENDOR_POINT_QUALIFIED' else
                             'ASSESSMENT_STALE' if status=='STALE' else
                             'INCOMPLETE_ASSESSMENT' if status=='UNASSESSED' else 'ASSESSED_EXCLUDED')
    except (sqlite3.Error, OSError):
        result['phantom_coverage_overlay'] = {**base, 'state':'UNAVAILABLE',
                                             'reason':'CURRENT_COVERAGE_READ_FAILED'}
    return result
