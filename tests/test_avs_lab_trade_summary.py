"""Lab trade summary table (ACK 5 Oct 2026): "include Setup / Option / value at median time / Median time / DTE /
Spread / Earnings inside hold in the Intelligence Lab".

Business rules:
- One row per ticker: Ticker, Side, Lane, Setup, Option, Value at median time, Median time, DTE, Spread, Earnings.
- Default rows are the tradeable lanes (A and B), best value first; lane C only when asked for.
- DTE states both units (calendar days and trading sessions) - never a bare "DTE" (fix D).
- Earnings states the hold AND the contract's life, with the date and whether it is unconfirmed - the external
  review read "inside hold: No" as "no earnings in the contract's life" (fix C).
- Value at median time is shown with its basis when it is not a verdict (volatility only, fix B).
- Missing values are stated, never blank or zero.
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "intelligence-lab" / "static" / "trade-summary.js"

ROWS = """[
 {ticker:'SMR', direction:'PUT', trade_lane:'A', trade_lane_setup:'1d|SOW -> LPSY continuation|ACTIVATED',
  contract_symbol:'SMR261120P00008000', strike:8, expiry:'2026-11-20', dte:46, contract_dte:35,
  contract_bid:0.99, contract_ask:1.07, anticipated_value_multiple_q50:1.59, anticipated_sessions_q50:3,
  anticipated_pays_state:'PAYS', earnings_inside_hold:false, earnings_inside_expiry:true, earnings_date:'2026-11-05',
  earnings_date_confirmation:'PROVIDER_DATE_UNCONFIRMED'},
 {ticker:'SMH', direction:'CALL', trade_lane:'A', trade_lane_setup:'1d|Change-of-Behaviour Reversal|DETECTED',
  contract_symbol:'SMH261218C00650000', strike:650, expiry:'2026-12-18', dte:74, contract_dte:54,
  contract_bid:32.4, contract_ask:33.65, anticipated_value_multiple_q50:1.72, anticipated_sessions_q50:10,
  anticipated_pays_state:'NOT_ASSESSED_VOLATILITY_ONLY', earnings_state:'NONE_IN_LOOKAHEAD'},
 {ticker:'XYZ', direction:'CALL', trade_lane:'C', trade_lane_setup:'1d|Upthrust Candidate|DETECTED'}
]"""


def _run(js):
    out = subprocess.run(["node", "-e", SCRIPT.read_text(encoding="utf-8") + js], capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_columns_and_default_rows():
    r = _run(f"""
const rows = {ROWS};
const html = renderTradeSummaryTable(rows);
const heads = ['Ticker','Side','Lane','Setup','Option','Value at median time','Median time','DTE','Spread','Earnings'];
console.log(JSON.stringify({{heads: heads.every(h => html.includes('<th>' + h + '</th>')),
  smhFirst: html.indexOf('SMH') < html.indexOf('SMR'), noC: !html.includes('XYZ'),
  withC: renderTradeSummaryTable(rows, {{includeLaneC: true}}).includes('XYZ')}}));""")
    assert r == {"heads": True, "smhFirst": True, "noC": True, "withC": True}


def test_units_earnings_spread_and_basis_are_stated():
    r = _run(f"""
const html = renderTradeSummaryTable({ROWS});
console.log(JSON.stringify({{dte: html.includes('46 cal · 35 sess'),
  earnings: html.includes('hold: no') && html.includes('contract: yes') && html.includes('2026-11-05')
            && html.includes('unconfirmed'),
  none: html.includes('none in lookahead'),
  spread: html.includes('7.8%'),
  basis: html.includes('volatility only'),
  option: html.includes('8 P 2026-11-20')}}));""")
    assert r == {"dte": True, "earnings": True, "none": True, "spread": True, "basis": True, "option": True}


def test_missing_values_are_stated():
    r = _run("""
const html = renderTradeSummaryTable([{ticker:'NIL', direction:'CALL', trade_lane:'A'}]);
console.log(JSON.stringify({stated: (html.match(/not recorded/g) || []).length >= 5}));""")
    assert r == {"stated": True}


def test_the_lab_page_loads_and_renders_the_summary():
    html = (ROOT / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    assert '<script src="/static/trade-summary.js"></script>' in html
    assert 'id="trade-summary"' in html and "renderTradeSummary()" in html
