// Trade summary table (ACK 5 Oct 2026): Setup / Option / value at median time / median time / DTE / spread /
// earnings, one row per ticker, tradeable lanes (A and B) first. Display only: nothing here ranks or gates.
// Units are stated (calendar days and trading sessions; fix D), earnings state the hold AND the contract's life
// with the date's confirmation (fix C), and a value that is not a verdict carries its basis (fix B).

function tsEsc(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
}

function tsBlank(value) {
  return value === undefined || value === null || value === '' || (typeof value === 'number' && Number.isNaN(value))
    || ['nan', 'none', 'null'].includes(String(value).trim().toLowerCase());
}

function tsNum(value) {
  const n = parseFloat(value);
  return Number.isFinite(n) ? n : null;
}

function tsMissing() {
  return '<span class="tc-missing">not recorded</span>';
}

function tsYesNo(value) {
  if (tsBlank(value)) return 'unknown';
  return ['true', '1', 'yes'].includes(String(value).trim().toLowerCase()) ? 'yes' : 'no';
}

function tsOption(s) {
  const strike = tsNum(s.strike);
  const right = String(s.direction || '').toUpperCase() === 'PUT' ? 'P' : 'C';
  if (strike === null || tsBlank(s.expiry)) return tsBlank(s.contract_symbol) ? tsMissing() : tsEsc(s.contract_symbol);
  return `${tsEsc(strike)} ${right} ${tsEsc(s.expiry)}`;
}

function tsValue(s) {
  const multiple = tsNum(s.anticipated_value_multiple_q50);
  if (multiple === null) return tsMissing();
  const state = String(s.anticipated_pays_state || '').toUpperCase();
  const basis = state === 'NOT_ASSESSED_VOLATILITY_ONLY' ? ' <span class="tc-note">volatility only, not a verdict</span>'
    : state === 'DOES_NOT_PAY_AT_ANTICIPATED_TIME' ? ' <span class="tc-missing">does not pay</span>' : '';
  return `${multiple.toFixed(2)}× premium${basis}`;
}

function tsDte(s) {
  const cal = tsNum(s.dte);
  const sess = tsNum(s.contract_dte);
  if (cal === null && sess === null) return tsMissing();
  return `${cal === null ? '?' : Math.round(cal)} cal · ${sess === null ? '?' : Math.round(sess)} sess`;
}

function tsSpread(s) {
  const bid = tsNum(s.contract_bid);
  const ask = tsNum(s.contract_ask);
  if (bid === null || ask === null || bid + ask <= 0) return tsMissing();
  return `${((ask - bid) / ((ask + bid) / 2) * 100).toFixed(1)}%`;
}

function tsEarnings(s) {
  const state = String(s.earnings_state || '').toUpperCase();
  if (state === 'NONE_IN_LOOKAHEAD') return 'none in lookahead';
  if (tsBlank(s.earnings_date)) return tsMissing();
  const unconfirmed = String(s.earnings_date_confirmation || '').toUpperCase() === 'CONFIRMED' ? '' : ' (unconfirmed)';
  return `hold: ${tsYesNo(s.earnings_inside_hold)} · contract: ${tsYesNo(s.earnings_inside_expiry)} · `
    + `${tsEsc(s.earnings_date)}${unconfirmed}`;
}

function renderTradeSummaryTable(rows, options = {}) {
  const lanes = options.includeLaneC ? ['A', 'B', 'C'] : ['A', 'B'];
  const picked = (rows || [])
    .filter(s => lanes.includes(String(s.trade_lane || '').toUpperCase()))
    .sort((a, b) => (tsNum(b.anticipated_value_multiple_q50) ?? -1) - (tsNum(a.anticipated_value_multiple_q50) ?? -1));
  if (!picked.length) return '<div class="meta-note">No rows in the selected lanes.</div>';
  const head = ['Ticker', 'Side', 'Lane', 'Setup', 'Option', 'Value at median time', 'Median time', 'DTE', 'Spread',
                'Earnings'];
  const body = picked.map(s => {
    const setup = tsBlank(s.trade_lane_setup) ? tsMissing() : tsEsc(String(s.trade_lane_setup).replaceAll('|', ' · '));
    const median = tsNum(s.anticipated_sessions_q50);
    return `<tr onclick="typeof openModal === 'function' && openModal('${tsEsc(s.ticker)}')">`
      + `<td>${tsEsc(s.ticker)}</td><td>${tsEsc(s.direction || '')}</td><td>${tsEsc(s.trade_lane || '')}</td>`
      + `<td>${setup}</td><td>${tsOption(s)}</td><td>${tsValue(s)}</td>`
      + `<td>${median === null ? tsMissing() : `${Math.round(median)} sessions`}</td><td>${tsDte(s)}</td>`
      + `<td>${tsSpread(s)}</td><td>${tsEarnings(s)}</td></tr>`;
  }).join('');
  return `<table class="dtbl"><thead><tr>${head.map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table>`;
}
