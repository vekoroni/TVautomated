/* Lab trade card (ACK 2 Oct 2026): the default view of a ticker. The trader reads the card,
   makes an informed decision, then runs the Interpreter from here instead of the output folder.
   Display only: no orders, sizing or capital authority. Field choice and redundancy evidence:
   Enhancements/assessment/AVS_LAB_FIELD_ASSESSMENT_20261002/. */

function tcEsc(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}

function tcBlank(value) {
  // 'NONE' is a real state in this pipeline (e.g. edge quality NONE), so only empty, NaN and null are missing.
  return value == null || String(value).trim() === '' || ['NAN', 'NULL'].includes(String(value).trim().toUpperCase());
}

function tcNum(value, digits = 2) {
  const n = Number(value);
  return tcBlank(value) || !isFinite(n) ? null : n.toFixed(digits);
}

function tcShow(value, fallback = 'not recorded') {
  return tcBlank(value) ? `<span class="tc-missing">${tcEsc(fallback)}</span>` : tcEsc(value);
}

function tcRow(label, value, note) {
  return `<div class="tc-row"><div class="tc-k">${tcEsc(label)}</div><div class="tc-v">${value}${note ? `<div class="tc-note">${note}</div>` : ''}</div></div>`;
}

function tcSection(title, rows) {
  return `<div class="tc-sec"><div class="tc-sec-hdr">${tcEsc(title)}</div>${rows.join('')}</div>`;
}

function tcLevel(name, level, spot) {
  const lv = Number(level), sp = Number(spot);
  if (tcBlank(level) || !isFinite(lv) || !isFinite(sp) || sp <= 0) return tcShow(level);
  const side = sp > lv ? 'above' : sp < lv ? 'below' : 'at';
  const readings = {
    gamma_flip: {above: 'spot above the gamma flip', below: 'spot below the gamma flip'},
    call_wall: {below: 'call wall above spot: overhead resistance', above: 'spot above the call wall: exceeded'},
    put_wall: {above: 'put wall below spot: support below', below: 'spot below the put wall: broken'},
  };
  const pct = ((sp / lv - 1) * 100).toFixed(2);
  return `${tcEsc(lv)} <span class="tc-note">(${(readings[name] || {})[side] || 'spot at level'}, ${pct}%)</span>`;
}

function tcSpread(s) {
  const bid = Number(s.contract_bid), ask = Number(s.contract_ask);
  if (!isFinite(bid) || !isFinite(ask) || ask <= 0 || bid > ask) return tcShow(s.spread_pct);
  return `${((ask - bid) / ask * 100).toFixed(2)}% of ask <span class="tc-note">(bid ${bid} / ask ${ask})</span>`;
}

function tcTrigger(s) {
  const t = String(s.trigger_primary || '');
  if (!t) return tcShow(null, 'no trigger');
  const flag = t === 'VOL_COMPRESSION_IV_RICH' ? ' <span class="tc-flag">IV rich: options are not cheap</span>'
    : t === 'VOL_COMPRESSION_IV_UNVERIFIED' ? ' <span class="tc-flag">IV unverified</span>' : '';
  return `${tcEsc(t)} · ${tcShow(s.trigger_quality)}${flag}`;
}

// N3 (ACK 3 Oct 2026): quotes are always old by design (Evening close, delayed Morning feed). Say how old
// the quote was when the pipeline checked it, which feed it came from, and that the trader re-quotes at the
// broker; never a bare STALE or "current". Age is disclosure, not a gate.
function tcQuote(s) {
  const stamp = s.current_quote_timestamp_utc || s.morning_quote_timestamp_utc || s.selected_quote_timestamp_utc;
  const raw = tcNum(s.execution_viability_quote_raw_age_seconds);
  const feed = String(s.execution_viability_quote_feed_state || '').toUpperCase() === 'DELAYED_PROVIDER_FEED'
    ? 'delayed feed' : (s.execution_viability_quote_feed_state ? 'real-time feed' : 'feed not recorded');
  const age = raw === null ? 'age at check not recorded' : `${Math.round(raw / 60)} min old at the Morning check`;
  const when = tcBlank(stamp) ? '<span class="tc-missing">quote time not recorded</span>' : tcEsc(stamp);
  return `${when} · ${tcEsc(age)} (${tcEsc(feed)})<div class="tc-note">re-quote at broker before entry</div>`;
}

function tcAnticipatedLevel(s) {
  if (tcBlank(s.anticipated_move_state)) {
    const reach = tcBlank(s.target_reachable) ? '' : ` · volatility-reachable level ${tcEsc(tcNum(s.target_reachable))}`;
    return `<span class="tc-missing">anticipated move not computed in this run</span>${reach}`;
  }
  if (tcBlank(s.anticipated_level)) return `<span class="tc-missing">${tcEsc(s.anticipated_move_state)}</span>`;
  const p = tcBlank(s.anticipated_p_outcome_by_limit) ? '' :
    `<div class="tc-note">reached before failing in ${Math.round(Number(s.anticipated_p_outcome_by_limit) * 100)}% of ${tcEsc(s.anticipated_evidence_n)} replay cases (in-sample)</div>`;
  return `${tcEsc(tcNum(s.anticipated_level))} <span class="tc-note">${tcEsc(s.anticipated_level_basis)} · ${tcEsc(tcNum(s.anticipated_move_pct))}% in the trade's direction</span>${p}`;
}

// Trade lane (ACK 4 Oct 2026): A trade now / B early entry / C watch - never mixed.
function tcPct(value) {
  return tcBlank(value) || Number.isNaN(Number(value)) ? '?' : `${Math.round(Number(value) * 100)}%`;
}

function tcLane(s) {
  const lane = String(s.trade_lane || '').toUpperCase();
  const setup = tcBlank(s.trade_lane_setup) ? '' : ` · ${tcEsc(String(s.trade_lane_setup).replaceAll('|', ' · '))}`;
  const hits = `${tcPct(s.trade_lane_hit_original)} / ${tcPct(s.trade_lane_hit_holdout)} reached the level first (original / held out)`;
  if (lane === 'A') return `<strong>Lane A · trade now</strong>${setup} <span class="tc-note">${hits}</span>`;
  if (lane === 'B') return `<strong>Lane B · early entry</strong>${setup} <span class="tc-missing">about 1 in 4 fail</span> `
    + `<span class="tc-note">${hits}; offered only if the option is worth at least ${tcEsc(tcNum(s.trade_lane_required_multiple))}× premium at the anticipated time</span>`;
  if (lane === 'C') return `<strong>Lane C · watch</strong>${setup} <span class="tc-note">awaiting trigger or your judgement · ${tcEsc(s.trade_lane_basis)}</span>`;
  return tcShow(null, 'not assigned in this run');
}

function renderTradeCard(s, profile) {
  const dir = String(s.direction || s.final_direction || 'UNRESOLVED').toUpperCase();
  const spot = s.live_price || s.current_price || s.signal_price || s.underlying_price;
  const sections = [
    tcSection('1 · What and which side', [
      tcRow('Ticker / side', `<strong>${tcEsc(s.ticker)}</strong> · ${tcEsc(dir)} · tier ${tcShow(s.tier)}`),
      tcRow('Structure (Phase · Event)', tcShow(s.thesis_category, 'not categorised in this run'),
            tcBlank(s.thesis_structure_alignment) ? '' : `alignment ${tcEsc(s.thesis_structure_alignment)}`),
      tcRow('Lane', tcLane(s), tcBlank(s.intake_flags) || s.intake_flags === 'NONE' ? '' : `intake labels ${tcEsc(s.intake_flags)}`),
    ]),
    tcSection('2 · Why now', [
      tcRow('Trigger', tcTrigger(s), tcBlank(s.trigger_go_eligible) ? '' : `GO-eligible trigger: ${tcEsc(s.trigger_go_eligible)}`),
      tcRow('Morning validation', tcShow(s.validation_transition, 'Morning not run'),
            tcBlank(s.remaining_runway_state) ? '' : `runway ${tcEsc(s.remaining_runway_state)}`),
    ]),
    // Anticipated move (ACK 3 Oct 2026): R:R and the 3R target leave the card (audit tier only); the invalidation
    // is the thesis exit, never part of the move. Display only until the replay validation.
    tcSection('3 · Where wrong, where right', [
      tcRow('Thesis exit (invalidation)', tcShow(tcNum(s.invalidation_price)), 'structure is wrong beyond this level'),
      tcRow('Anticipated level', tcAnticipatedLevel(s)),
      tcRow('Structural level', tcShow(tcNum(s.anticipated_structural_level), 'none on the trade side (no level is invented)'),
            tcBlank(s.anticipated_structural_definition) ? '' : tcEsc(s.anticipated_structural_definition)),
    ]),
    tcSection('4 · How long', [
      tcRow('Time fit', tcBlank(s.anticipated_time_fit) ? tcShow(null, 'not computed in this run')
            : ({CONTRACT_OUTLASTS_Q80: 'contract outlasts the 80% time',
                CONTRACT_EXPIRES_BEFORE_Q80: '<span class="tc-missing">contract expires before the 80% time</span>',
                CONTRACT_EXPIRES_BEFORE_MEDIAN_TIME: '<span class="tc-missing">contract expires before the median anticipated time</span>'}[s.anticipated_time_fit] || tcEsc(s.anticipated_time_fit))),
      tcRow('Anticipated time', tcBlank(s.anticipated_sessions_q50) ? '<span class="tc-missing">not estimated (thin evidence)</span>'
            : `${tcEsc(s.anticipated_sessions_q50)} / ${tcEsc(s.anticipated_sessions_q80)} sessions`, 'median / 80% to the level · ' + tcEsc(s.anticipated_time_basis || 'not computed in this run')
              + (tcBlank(s.thesis_activation_q50_bars) ? '' : `<br>activation (trigger) typically within ${tcEsc(s.thesis_activation_q50_bars)} / ${tcEsc(s.thesis_activation_q80_bars)} bars (${tcEsc(s.thesis_event_timeframe || '')})`)),
      tcRow('Planned hold', `${tcShow(s.planned_hold_sessions)} sessions`, 'governed window (runway floor)'),
      tcRow('Contract expiry', `${tcShow(s.expiry)} · ${tcShow(s.contract_dte)} DTE`),
      tcRow('Catalyst', tcShow(s.catalyst_date, 'none recorded'), tcBlank(s.catalyst_inside_dte) ? '' : `inside DTE: ${tcEsc(s.catalyst_inside_dte)}`),
      // Earnings disclosure (ACK 3 Oct 2026): position risk against the hold and expiry; never a gate.
      tcRow('Earnings', tcBlank(s.earnings_state) ? '<span class="tc-missing">earnings not checked in this run</span>' : tcEsc(s.earnings_disclosure || s.earnings_state)),
    ]),
    tcSection('5 · Which contract, at what cost', [
      tcRow('Contract', `${tcShow(s.contract_symbol)} · strike ${tcShow(s.strike)}`),
      tcRow('Spread', tcSpread(s)),
      tcRow('Delta / IV / IV level', `${tcShow(tcNum(s.contract_delta, 3))} / ${tcShow(tcNum(s.contract_iv, 3))} / ${tcShow(s.ivp_label)}`),
      tcRow('OI / volume / breakeven', `${tcShow(s.contract_oi)} / ${tcShow(s.contract_volume)} / ${tcShow(tcNum(s.breakeven_price))}`),      tcRow('Does the move pay', tcBlank(s.anticipated_move_coverage) ? '<span class="tc-missing">not computed in this run</span>'
            : ({PAYS: '<b>pays at the anticipated time</b> · ', DOES_NOT_PAY_AT_ANTICIPATED_TIME: '<span class="tc-missing">does not pay at the anticipated time (no GO)</span> · '}[s.anticipated_pays_state] || '') + `coverage ${tcEsc(tcNum(s.anticipated_move_coverage))}× breakeven move (${tcEsc(tcNum(s.anticipated_breakeven_move_pct))}%) · value ${tcShow(tcNum(s.anticipated_value_multiple_q50))}× premium at median time`,
            tcBlank(s.anticipated_stress_basis) ? '' : `stress: ${tcShow(tcNum(s.anticipated_value_multiple_q80))}× at ${tcEsc(s.anticipated_stress_basis)}${tcBlank(s.anticipated_value_multiple_earnings_stress) ? '' : ` · ${tcEsc(tcNum(s.anticipated_value_multiple_earnings_stress))}× with earnings IV stress`}`),
    ]),
    tcSection('6 · Context (advisory)', [
      tcRow('Sector', `${tcShow(s.sector)} · ${tcShow(s.sector_etf)}`),
      tcRow('Money Index / macro', `${tcShow(s.usmi_sector_alignment)} / ${tcShow(s.macro_sector_alignment)}`),
      tcRow('Gamma flip', tcLevel('gamma_flip', s.gamma_flip, spot)),
      tcRow('Call wall', tcLevel('call_wall', s.call_wall, spot)),
      tcRow('Put wall', tcLevel('put_wall', s.put_wall, spot)),
    ]),
    tcSection('7 · Decision state', [
      tcRow('Lab verdict / action', `${tcShow(s.lab_verdict)} / ${tcShow(s.final_action)}`),
      tcRow('Conflict / evening bucket', `${tcShow(s.conflict_state)} / ${tcShow(s.evening_thesis_bucket)}`),
      tcRow('Open position', tcBlank(s.governance__verdict) ? 'none' : `governance ${tcEsc(s.governance__verdict)}: ${tcEsc(s.governance__reason || '')}`),
    ]),
    tcSection('8 · Can I trust the data', [
      tcRow('Quote', tcQuote(s)),
      tcRow('Price bars as of', tcShow(s.bar_data_asof)),
    ]),
  ];
  const ticker = tcEsc(s.ticker);
  return `<div class="tc">${sections.join('')}
    <div class="tc-actions">
      <button class="fb" onclick="tradeCardRunInterpreter('${ticker}')" title="Advisory Interpreter report for this ticker (paid model call; you confirm the cost first)">Run Interpreter report</button>
      <button class="fb" onclick="tradeCardSavedReports('${ticker}')" title="Open stored Interpreter reports for this ticker; no model call">View saved reports</button>
    </div>
    <div class="tc-note">Advisory only. No order, sizing or capital authority.</div>
    ${profile ? `<div class="tc-tiers">${renderEvidenceTiers(s, profile)}</div>` : ''}</div>`;
}

function tradeCardSelect(ticker) {
  INTERPRETER_SELECTED.clear();
  INTERPRETER_SELECTED.add(ticker);
  document.querySelectorAll('input[data-interpreter-ticker]').forEach(input => {
    input.checked = input.dataset.interpreterTicker === ticker;
  });
  updateInterpreterSelection();
  if (typeof closeModal === 'function') closeModal();
  const panel = document.getElementById('interpreter-panel') || document.getElementById('interpreter-status');
  if (panel) panel.scrollIntoView({behavior: 'smooth', block: 'start'});
}

function tradeCardRunInterpreter(ticker) {
  tradeCardSelect(ticker);
  previewInterpreterDesk();
}

function tradeCardSavedReports(ticker) {
  tradeCardSelect(ticker);
  viewSavedInterpreterReports();
}

/* Evidence drawer and audit tier (ACK 2 Oct 2026). The run's book is profiled once in the browser:
   empty -> listed for tracing; duplicate (identical to an earlier field on every row), lineage
   (authority, version, policy, ids, hashes) and constant fields -> hidden audit tier; every other
   informative field not on the card -> collapsed evidence drawer grouped by family. */

const TC_CARD_FIELDS = new Set([
  'ticker', 'direction', 'tier', 'thesis_category', 'thesis_structure_alignment', 'trigger_primary', 'trigger_quality',
  'trade_lane', 'trade_lane_basis', 'trade_lane_setup', 'trade_lane_hit_original', 'trade_lane_hit_holdout',
  'trade_lane_required_multiple', 'intake_flags', 'price_band',
  'trigger_go_eligible', 'validation_transition', 'remaining_runway_state', 'invalidation_price',
  'anticipated_move_state', 'anticipated_level', 'anticipated_level_basis', 'anticipated_move_pct',
  'anticipated_structural_level', 'anticipated_structural_definition', 'anticipated_p_outcome_by_limit',
  'anticipated_evidence_n', 'anticipated_sessions_q50', 'anticipated_sessions_q80', 'anticipated_time_basis',
  'anticipated_move_coverage', 'anticipated_breakeven_move_pct', 'anticipated_value_multiple_q50',
  'anticipated_value_multiple_q80', 'anticipated_value_multiple_earnings_stress', 'anticipated_stress_basis', 'anticipated_time_fit', 'anticipated_pays_state', 'thesis_activation_q50_bars', 'thesis_activation_q80_bars',
  'planned_hold_sessions', 'expiry', 'contract_dte', 'catalyst_date', 'catalyst_inside_dte', 'contract_symbol', 'strike',
  'contract_bid', 'contract_ask', 'spread_pct', 'contract_delta', 'contract_iv', 'ivp_label', 'contract_oi',
  'contract_volume', 'breakeven_price', 'sector', 'sector_etf', 'usmi_sector_alignment', 'macro_sector_alignment',
  'gamma_flip', 'call_wall', 'put_wall', 'lab_verdict', 'final_action', 'conflict_state', 'evening_thesis_bucket',
  'governance__verdict', 'governance__reason', 'quote_freshness', 'earnings_state', 'earnings_disclosure', 'selected_quote_timestamp_utc', 'bar_data_asof',
  'signal_price', 'live_price', 'current_price', 'underlying_price']);
const TC_SKIP = new Set(['source_payload_json']);
// ACK 3 Oct 2026: stop-based R:R and invented 3R targets are retired from decisions; kept for audit only.
const TC_LEGACY = /^(rr|rr_.*|target_3r.*|structural_target|target_zone|target_price|target_price_source|option_gain_at_target|estimated_r|max_convex_r_multiple|runway_to_target)$/i;
const TC_LINEAGE = /(authority|version|policy|sha256|hash|calculation|lineage|_id$|_ids$|dataset_id|snapshot_id|_run_id$|source_path)/i;
const TC_FAMILIES = [
  [/^(wyckoff|phase|dominant_event|truth_confidence|event_)/, 'Wyckoff structure'],
  [/^(crabel|compression|precor|fusion)/, 'Crabel / Precor'],
  [/^(beh__|thesis_|thesis__|shadow_thesis)/, 'Behaviour (BEH-001)'],
  [/^(layer1|layer2|vanguard|edge_|side_|actuarial)/, 'Vanguard'],
  [/^(doi_|dynamic_)/, 'DOI'],
  [/^(ev3_|ev_|c8_|expected_value)/, 'EV3 / valuation'],
  [/^(catalyst|earnings|event_risk)/, 'Catalyst'],
  [/^(wbs)/, 'Wall-break score'],
  [/^(macro|usmi|regime|sector_|bond)/, 'Macro / sector'],
  [/^(morning|validation|live_|mv_|current_)/, 'Morning'],
  [/^(contract|option|options_|ca_|monetis|selected_|premium|spread|olm|liquidity)/, 'Contract detail'],
  [/^(forecast|c4_|c5_|c6_|expression)/, 'Forecast / expression'],
  [/^(direction|governed_|canonical_|discovery_direction|final_direction)/, 'Direction'],
  [/^(trigger|trap|vwap|range_)/, 'Trigger'],
  [/^(gex|gamma|pcr|dw_|iv_|hv_|garch|vol_|atm_)/, 'Volatility / gamma'],
  [/^(eod_|lab_|exec|pretrade|evening|scenario|rank|priority)/, 'Lab / EOD state'],
  [/^(entropy|market_energy|force_alignment|trend_inertia|state_transition|hidden_state|behaviour_state|activity_|volume_activity|oi_positioning)/, 'Market physics'],
  [/^(ms_)/, 'Market profile'],
  [/^(opt__|max_pain|alternative_contract|delta_band|moneyness|breakeven|economics_|dte|minimum_required_dte|research_ev|runway|remaining_runway|target_zone|put_wall_state|ivp_source|quote_timestamp|previous_contract|instrument)/, 'Options layer'],
  [/^(ts_|sb_|hold_|maturation|readiness|expected_move)/, 'Timing / exits'],
  [/^(invalidation_|target_state|structure_evidence)/, 'Thesis geometry'],
  [/^(action_category|campaign|convexity|display_|eil_|final_capital|gate_|hard_vetoes|conflict_flags|advisory_flags|data_quality|negative_factors|opportunity_tier|requires_live|check_direction|recovery_disposition|entry_|intent|composite|win_prob|field_provenance|scanner_price|gics_sector)/, 'Decision / gates'],
];

function tcFamily(field) {
  for (const [re, name] of TC_FAMILIES) if (re.test(field)) return name;
  return 'Other';
}

function tcProfile(rows) {
  const fields = [];
  const seen = new Set();
  for (const row of rows) for (const k of Object.keys(row)) if (!seen.has(k) && !TC_SKIP.has(k)) { seen.add(k); fields.push(k); }
  const SEP = String.fromCharCode(1);
  const profile = {evidence: [], constant: [], lineage: [], legacy: [], empty: [], duplicateOf: {}};
  const firstByVector = new Map();
  for (const f of fields) {
    // one pass per field: normalised value vector, populated count and distinct set together
    const parts = new Array(rows.length);
    const distinct = new Set();
    let populated = 0;
    for (let i = 0; i < rows.length; i++) {
      const raw = rows[i][f];
      const text = raw == null ? '' : String(raw).trim();
      const upper = text.toUpperCase();
      const norm = text === '' || upper === 'NAN' || upper === 'NULL' ? '' : text.toLowerCase();
      parts[i] = norm;
      if (norm) { populated++; if (distinct.size < 2) distinct.add(norm); }
    }
    if (!populated) { profile.empty.push(f); continue; }
    if (TC_LEGACY.test(f) && !TC_CARD_FIELDS.has(f)) { profile.legacy.push(f); continue; }   // legacy is named, never a "duplicate"
    const values = distinct;
    const key = parts.join(SEP);
    if (firstByVector.has(key)) {
      if (!TC_CARD_FIELDS.has(f)) profile.duplicateOf[f] = firstByVector.get(key);
      continue;
    }
    firstByVector.set(key, f);
    if (TC_CARD_FIELDS.has(f)) continue;
    if (TC_LINEAGE.test(f)) profile.lineage.push(f);
    else if (values.size === 1) profile.constant.push(f);
    else profile.evidence.push(f);
  }
  return profile;
}

const TC_PROFILE_CACHE = {};
function tcProfileFor(rows, runId) {
  const key = `${runId || 'NO_RUN'}:${(rows || []).length}`;
  if (!TC_PROFILE_CACHE[key]) TC_PROFILE_CACHE[key] = tcProfile(rows || []);
  return TC_PROFILE_CACHE[key];
}

function tcFieldList(s, fields, note) {
  return fields.map(f => `<div class="tc-row"><div class="tc-k">${tcEsc(f)}</div><div class="tc-v">${tcShow(s[f], 'blank on this row')}${note ? `<div class="tc-note">${note(f)}</div>` : ''}</div></div>`).join('');
}

function renderEvidenceTiers(s, profile) {
  const groups = {};
  for (const f of profile.evidence) (groups[tcFamily(f)] = groups[tcFamily(f)] || []).push(f);
  const groupHtml = Object.keys(groups).sort().map(name =>
    `<details class="tc-group"><summary>${tcEsc(name)} (${groups[name].length})</summary>${tcFieldList(s, groups[name].sort())}</details>`).join('');
  const dups = Object.keys(profile.duplicateOf).sort();
  const audit = `<details class="tc-audit"><summary>Audit tier: ${profile.legacy.length} legacy · ${profile.lineage.length} lineage · ${profile.constant.length} constant · ${dups.length} duplicate · ${profile.empty.length} always empty</summary>
      <details class="tc-group"><summary>Legacy stop-based R:R and 3R targets (retired, not used)</summary>${tcFieldList(s, [...profile.legacy].sort())}</details>
      <details class="tc-group"><summary>Lineage (authority, version, policy, ids, hashes)</summary>${tcFieldList(s, [...profile.lineage].sort())}</details>
      <details class="tc-group"><summary>Constant across this run</summary>${tcFieldList(s, [...profile.constant].sort())}</details>
      <details class="tc-group"><summary>Duplicates (same value as another field on every row)</summary>${tcFieldList(s, dups, f => `same as ${tcEsc(profile.duplicateOf[f])}`)}</details>
      <details class="tc-group"><summary>Always empty in this run (to trace)</summary><div class="tc-note">${profile.empty.map(tcEsc).join(', ') || 'none'}</div></details>
    </details>`;
  return `<details class="tc-evidence"><summary>Evidence drawer: ${profile.evidence.length} further informative fields by family</summary>${groupHtml}</details>${audit}`;
}
