"""Display identities and economics disclosures; never decisions or repricing."""
import json
import math
from datetime import datetime
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=1)
def display_policy():
    return json.loads((Path(__file__).resolve().parents[1]/'config/lab_review_display_v1.json').read_text(encoding='utf-8-sig'))

def display_sector(value):
    raw=str(value or '').strip()
    return display_policy()['sector_aliases'].get(raw.upper(),raw or 'UNKNOWN')

def _number(value):
    try:
        n=float(value);return n if math.isfinite(n) else None
    except (TypeError,ValueError):return None

def valuation_disclosure(row):
    required=('valuation_model','valuation_version','valuation_cost_basis','valuation_entry_cost_usd_per_share',
              'anticipated_contract_basis','anticipated_valued_at_utc',
              'valuation_rate_annual','valuation_rate_basis','valuation_dividend_yield_annual','valuation_dividend_basis')
    absent=[k for k in required if row.get(k) in (None,'')]
    out={'authority':'DISPLAY_ONLY','missing_fields':absent,'state':'NOT_COMPUTED'}
    value=_number(row.get('anticipated_value_multiple_q50'))
    if value is None:return out
    if absent:return {**out,'state':'REFERENCE_BASIS_NOT_RECORDED'}
    selected=str(row.get('contract_symbol') or '').upper().removeprefix('O:')
    priced=str(row.get('anticipated_contract_symbol') or '').upper().removeprefix('O:')
    if not selected or selected!=priced:return {**out,'state':'VALUED_CONTRACT_MISMATCH'}
    net=_number(row.get('scenario_target_return_on_premium'))
    if net is None:return {**out,'state':'SCENARIO_NOT_RECORDED'}
    if abs(value-(1+net))>.00011:return {**out,'state':'VALUE_SCENARIO_MISMATCH'}
    try:datetime.fromisoformat(str(row['anticipated_valued_at_utc']).replace('Z','+00:00'))
    except ValueError:return {**out,'state':'VALUATION_TIME_INVALID'}
    basis=str(row['anticipated_contract_basis']).upper()
    return {**out,'state':'MORNING_REFERENCE' if basis.startswith(('MORNING_REPRICED:','MORNING_CONTRACT_RECOMPUTED:')) else 'DOCUMENTED_REFERENCE'}
