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

// Phase 5.3 (ACK 8 Oct 2026): the trigger-layer state category is a state reading, not the trigger.
function tcTrigger(s) {
  const t = String(s.trigger_primary || '');
  if (!t) return tcShow(null, 'no state reading');
  const flag = t === 'VOL_COMPRESSION_IV_RICH' ? ' <span class="tc-flag">IV rich: options are not cheap</span>'
    : t === 'VOL_COMPRESSION_IV_UNVERIFIED' ? ' <span class="tc-flag">IV unverified</span>' : '';
  return `${tcEsc(t)} · ${tcShow(s.trigger_quality)}${flag}`;
}

// Phase 5.5: the thesis's own trigger and its readiness from its own events (one candidate, one story).
const TC_READINESS = {
  READY_FOR_HUMAN_REVIEW: '<b>trigger accepted: ready for your review</b>',
  WAIT_TRIGGER: 'waiting for the trigger to be accepted',
  CLOSED_INVALIDATED: '<span class="tc-missing">closed: invalidated</span>',
  CLOSED_RETEST_FAILED: '<span class="tc-missing">closed: retest failed</span>',
  CLOSED_OUTCOME_REACHED: '<span class="tc-missing">closed: outcome already reached</span>',
  NOT_MEASURED: '<span class="tc-missing">events not measured</span>',
  NOT_ADOPTED: '<span class="tc-missing">no adopted thesis</span>',
};

function tcThesisTrigger(s) {
  const level = tcBlank(s.thesis_trigger_level) ? '<span class="tc-missing">no thesis trigger</span>'
    : tcEsc(tcNum(s.thesis_trigger_level, 4));
  const readiness = TC_READINESS[String(s.thesis__readiness || '').toUpperCase()]
    || tcShow(s.thesis__readiness, 'readiness not recorded');
  return `${level} · ${readiness}`;
}

function tcThesisNote(s) {
  const parts = [];
  if (!tcBlank(s.thesis__readiness_reason)) parts.push(`deciding event ${tcEsc(s.thesis__readiness_reason)}`);
  if (!tcBlank(s.thesis__last_event)) parts.push(`last event ${tcEsc(s.thesis__last_event)}`);
  if (!tcBlank(s.thesis_trigger_candidate_id)) parts.push(`setup ${tcEsc(s.thesis_trigger_candidate_id)}`);
  return parts.join(' · ');
}

function tcThesisSpine(s) {
  if (tcBlank(s.thesis__top_timeframe)) return tcShow(null, 'no adopted thesis on a tested timeframe');
  const n = Number(s.thesis__conflicting_count);
  const conflicts = isFinite(n) && n > 0 ? ` · <span class="tc-flag">${n} conflicting</span>` : ' · no conflicting thesis';
  return `side set on ${tcEsc(s.thesis__top_timeframe)}${conflicts}`;
}

// Phase 5.4: the other live theses Options priced on their own side and levels (labelled alternatives).
function tcAlternatives(s) {
  if (tcBlank(s.thesis_alternatives_tested)) return tcShow(null, 'not priced in this run');
  let alts = [];
  try { alts = JSON.parse(s.thesis_alternatives_json || '[]'); } catch (e) { alts = []; }
  const head = `${tcEsc(s.thesis_alternatives_count)} of ${tcEsc(s.thesis_alternatives_tested)} found a contract`;
  const list = alts.slice(0, 6).map(a => `${tcEsc(a.timeframe)} ${tcEsc(a.side)} ${tcEsc(a.symbol)}`
    + (String(a.condition || '').startsWith('CONDITIONAL') ? ` <span class="tc-note">(${tcEsc(a.condition)})</span>` : '')).join('<br>');
  return list ? `${head}<div class="tc-note">${list}${alts.length > 6 ? '<br>…' : ''}</div>` : head;
}

function tcIntraday(s) {
  if (tcBlank(s.ib_state)) return tcShow(null, 'not measured in this run');
  const last = tcBlank(s.ib_last_event) ? '' : ` · last ${tcEsc(s.ib_last_event)}`;
  return `${tcEsc(s.ib_state)}${last}`;
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
  // Output-trust item 10.1 (ACK 10 Oct 2026): the setup's own rate within the planned hold, held out, with n and
  // interval, and the replay calibration (display only).
  const pct = v => `${Math.round(Number(v) * 100)}%`;
  const within = tcBlank(s.setup_rate_within_hold) ? '' : `<br>within the planned hold (${tcEsc(Math.round(Number(s.setup_hold_bars)))} bars): ${pct(s.setup_rate_within_hold)} held out (n ${tcEsc(s.setup_rate_n)}, ${pct(s.setup_rate_ci_low)}–${pct(s.setup_rate_ci_high)}; shrunk ${pct(s.setup_rate_shrunk)})`
    + (tcBlank(s.setup_calibration_slope) ? '' : ` · replay calibration slope ${tcEsc(Number(s.setup_calibration_slope).toFixed(2))}`)
    // Output-trust item 10.2: the setup's forward state as measured by the outcome scorer, never assumed.
    + ` · ${tcEsc(tcBlank(s.setup_forward_text) ? 'forward: not measured' : s.setup_forward_text)}`;
  if (lane === 'A') return `<strong>Lane A · trade now</strong>${setup} <span class="tc-note">${hits}${within}</span>`;
  if (lane === 'B') return `<strong>Lane B · early entry</strong>${setup} <span class="tc-missing">about 1 in 4 fail</span> `
    + `<span class="tc-note">${hits}; offered only if the option is worth at least ${tcEsc(tcNum(s.trade_lane_required_multiple))}× premium at the anticipated time</span>`;
  if (lane === 'C') return `<strong>Lane C · watch</strong>${setup} <span class="tc-note">awaiting trigger or your judgement · ${tcEsc(s.trade_lane_basis)}</span>`;
  return tcShow(null, 'not assigned in this run');
}

function tcSharePrice(s) {
  const px = tcNum(s.live_price);
  if (px === null) return tcShow(null);
  const age = tcBlank(s.live_price_age_seconds) || !isFinite(Number(s.live_price_age_seconds)) ? null : Number(s.live_price_age_seconds);
  const ageText = age === null ? 'age not recorded' : (age >= 60 ? `${Math.round(age / 60)} min old` : `${Math.round(age)} s old`);
  const aged = String(s.live_price_state || '').toUpperCase() === 'AGED_REFERENCE' ? ' · aged reference' : '';
  return `${tcEsc(px)} · ${ageText}${aged}`;
}

// Output-trust item 1 (ACK 9 Oct 2026): what the predictive-edge test found, in words (display only).
const TC_EDGE_LABELS = {TESTED_NO_EDGE: 'tested: no edge found', NOT_TESTED: 'not tested',
  INSUFFICIENT_EVIDENCE: 'insufficient evidence', UNVALIDATED: 'unvalidated', VALIDATED: 'validated'};

function tcEdgeLabel(state) {
  if (tcBlank(state)) return null;
  return TC_EDGE_LABELS[String(state).toUpperCase()] || String(state).toLowerCase();
}

function tcStructuralBias(s) {
  const side = String(s.thesis__side || '').toUpperCase();
  if (!['BULL', 'BEAR'].includes(side)) return tcShow(null, 'no adopted thesis side (unresolved)');
  return `${tcEsc(side)}${tcBlank(s.thesis__top_timeframe) ? '' : ` · set on ${tcEsc(s.thesis__top_timeframe)}`}`;
}

// Output-trust item 2 (D2-1 Step A, ACK 9 Oct 2026): the card's structure comes from one engine, the thesis engine.
// Scope, phase and event, event status with the last observation, failure evidence and other-timeframe conflicts.
// Nothing is forced to agree with the trade; display only.
function tcStructureScope(s) {
  if (tcBlank(s.thesis_event_timeframe) && tcBlank(s.thesis_event_scope)) return tcShow(null, 'no thesis structure in this run');
  const since = String(s.thesis_event_candidate_id || '').split('|').pop();
  const sinceText = /^\d{4}-\d{2}-\d{2}/.test(since) ? ` · since ${tcEsc(since)}` : '';
  return `${tcShow(s.thesis_event_timeframe)} · ${tcShow(s.thesis_event_scope)}${sinceText}`;
}

function tcStructurePhaseEvent(s) {
  if (tcBlank(s.thesis_phase) && tcBlank(s.thesis_event)) return tcShow(s.thesis_category, 'not categorised in this run');
  return `Phase ${tcShow(s.thesis_phase)} · ${tcShow(s.thesis_event)}`;
}

const TC_EVENT_STATUS = {
  READY_FOR_HUMAN_REVIEW: 'observed (activated)',
  WAIT_TRIGGER: 'candidate (not yet activated)',
  CLOSED_INVALIDATED: '<span class="tc-missing">failed (invalidated)</span>',
  CLOSED_RETEST_FAILED: '<span class="tc-missing">failed (retest failed)</span>',
  CLOSED_OUTCOME_REACHED: 'historical (outcome already reached)',
};

function tcStructureStatus(s) {
  const readiness = String(s.thesis__readiness || '').toUpperCase();
  const status = TC_EVENT_STATUS[readiness]
    || (tcBlank(s.thesis_event_state) ? tcShow(null, 'event status not recorded') : `${tcEsc(String(s.thesis_event_state).toLowerCase())} (events not measured)`);
  if (tcBlank(s.thesis__last_event)) return status;
  const when = tcBlank(s.thesis__last_event_date) ? '' : ` on ${tcEsc(s.thesis__last_event_date)}`;
  const level = tcNum(s.thesis__last_event_level);
  return `${status}<div class="tc-note">last observed ${tcEsc(s.thesis__last_event)}${when}${level === null ? '' : ` at ${tcEsc(level)}`}</div>`;
}

function tcStructureFailure(s) {
  const readiness = String(s.thesis__readiness || '').toUpperCase();
  if (['CLOSED_INVALIDATED', 'CLOSED_RETEST_FAILED'].includes(readiness))
    return `<span class="tc-missing">failed: ${tcEsc(s.thesis__readiness_reason || readiness)}</span>`;
  if (readiness === 'CLOSED_OUTCOME_REACHED') return `outcome reached: ${tcEsc(s.thesis__readiness_reason || readiness)}`;
  if (['READY_FOR_HUMAN_REVIEW', 'WAIT_TRIGGER'].includes(readiness)) return 'invalidation not reached';
  return tcShow(null, 'not measured in this run');
}

function tcStructureOthers(s) {
  const n = Number(s.thesis__conflicting_count);
  if (tcBlank(s.thesis__conflicting_count) || !isFinite(n)) return tcShow(null, 'other timeframes not recorded');
  if (n <= 0) return 'no conflicting thesis on another timeframe';
  return `<span class="tc-flag">${n} conflicting thesis${n === 1 ? '' : 'es'} on other timeframes</span> (shown with scope, not forced to agree)`;
}

// Output-trust item 3 (D2-3, ACK decision 1, 9 Oct 2026): geometry from the planned entry; break-even hit rate against
// the setup's measured hit rate (n, interval). Not justified or invalid geometry cannot be GO; the row stays visible.
const TC_GEOMETRY = {JUSTIFIED: 'justified', GEOMETRY_NOT_JUSTIFIED: '<span class="tc-flag">not justified: cannot be GO</span>',
  INVALID_GEOMETRY: '<span class="tc-flag">invalid geometry: cannot be GO</span>',
  NOT_MEASURED: '<span class="tc-missing">no measured hit rate (judgement)</span>',
  NOT_ASSESSABLE: '<span class="tc-missing">not assessable</span>'};

function tcGeometry(s) {
  if (tcBlank(s.geometry_justification)) return tcShow(null, 'geometry not computed in this run');
  const state = TC_GEOMETRY[String(s.geometry_justification).toUpperCase()] || tcEsc(s.geometry_justification);
  const atr = v => tcBlank(v) ? '?' : Number(v).toFixed(1);
  const entry = `from ${tcEsc(String(s.geometry_entry_basis || '').toLowerCase().replace('_', ' '))} ${tcShow(tcNum(s.geometry_entry_price))}`;
  if (tcBlank(s.geometry_reward_price)) return `${state} · ${entry}<div class="tc-note">${tcEsc(s.geometry_reason || '')}</div>`;
  const legs = `reward ${tcEsc(tcNum(s.geometry_reward_price))} (${atr(s.geometry_reward_atr)} ATR) · risk ${tcEsc(tcNum(s.geometry_risk_price))} (${atr(s.geometry_risk_atr)} ATR)`
    + (tcBlank(s.geometry_early_warning_risk_atr) ? '' : ` · early-warning risk ${atr(s.geometry_early_warning_risk_atr)} ATR`);
  const pct = v => `${Math.round(Number(v) * 100)}%`;
  const be = tcBlank(s.geometry_breakeven_hit_rate) ? '' : `break-even ${pct(s.geometry_breakeven_hit_rate)}`;
  const measured = tcBlank(s.geometry_measured_hit_rate) ? '' : ` vs measured ${pct(s.geometry_measured_hit_rate)} (n ${tcEsc(s.geometry_hit_n)}`
    + (tcBlank(s.geometry_hit_low) ? ')' : `, ${pct(s.geometry_hit_low)}–${pct(s.geometry_hit_high)})`);
  return `${state} · ${entry}<div class="tc-note">${legs}<br>${be}${measured}<br>${tcEsc(s.geometry_reason || '')}</div>`;
}

// Output-trust item 4 (D5-1, ACK decision 2, 9 Oct 2026): one valuation engine, labelled scenarios, return on premium
// after spread and fees. The legacy payoff numbers (EV3, monetisability, option_gain_at_target) are in the legacy tier.
function tcScenarios(s) {
  if (tcBlank(s.scenario_exit_sessions) && tcBlank(s.scenario_target_return_on_premium)) return tcShow(null, 'not valued in this run');
  const pct = v => tcBlank(v) ? null : `${Number(v) >= 0 ? '+' : '-'}${Math.abs(Math.round(Number(v) * 100))}%`;
  const leg = (name, v, at) => pct(v) === null ? `${name} <span class="tc-missing">not valued</span>`
    : `${name} ${pct(v)}${tcBlank(at) ? '' : ` at ${tcEsc(tcNum(at))}`}`;
  const parts = [leg('target', s.scenario_target_return_on_premium, s.scenario_target_exit_spot),
                 leg('invalidation', s.scenario_invalidation_return_on_premium, s.scenario_invalidation_exit_spot),
                 leg('stall', s.scenario_stall_return_on_premium, null)];
  if (!tcBlank(s.scenario_target_earnings_iv_return_on_premium)) parts.push(leg('target with earnings IV drop', s.scenario_target_earnings_iv_return_on_premium, null));
  const model = String(s.valuation_model || '') === 'BSM_EUROPEAN' ? 'European (BSM) model' : 'American (CRR) model';
  const rate = tcBlank(s.valuation_rate_annual) ? 'rate not recorded' : `r ${(Number(s.valuation_rate_annual) * 100).toFixed(2)}%`;
  const basis = String(s.valuation_dividend_basis || '');
  const div = basis.startsWith('ASSUMED_ZERO') ? `dividend assumed 0 (${tcEsc(basis.split(':')[1] || 'not supplied')})`
    : basis.startsWith('DIVIDEND_NONE') ? 'no dividend (tastytrade)'
    : `dividend yield ${(Number(s.valuation_dividend_yield_annual || 0) * 100).toFixed(2)}% (tastytrade${basis.includes('next_ex') ? ', next ex ' + tcEsc(basis.split('next_ex ')[1].slice(0, 10)) : ''})`;
  return `${parts.join(' · ')}<div class="tc-note">return on premium after spread and fees · exit after ${tcShow(s.scenario_exit_sessions)} sessions (median time) · ${tcEsc(s.scenario_iv_basis || 'IV not recorded')} · ${model}, ${rate}, ${div}</div>`;
}

// Output-trust item 6 (D5-5, 9 Oct 2026): IV rank and IV percentile are different numbers, each with its definition and
// the samples actually used; SHORT_HISTORY below the governed full window (no fixed "252 days" label).
function tcIvHistory(s) {
  if (tcBlank(s.iv_percentile) && tcBlank(s.iv_rank)) return tcShow(null, `not measured (${tcEsc(s.ivp_source || 'source not recorded')})`);
  const n = tcBlank(s.iv_rank_window_sessions) ? '?' : tcEsc(s.iv_rank_window_sessions);
  const parts = [];
  if (!tcBlank(s.iv_percentile)) parts.push(`percentile ${Math.round(Number(s.iv_percentile) * 100)}% (share of ${n} samples below today)`);
  if (!tcBlank(s.iv_rank)) parts.push(`rank ${Math.round(Number(s.iv_rank))} (position in the range of ${n} samples)`);
  const state = String(s.iv_history_state || '').toUpperCase();
  const since = tcBlank(s.iv_history_first_date) ? '' : ` since ${tcEsc(s.iv_history_first_date)}`;
  const note = state === 'SHORT_HISTORY' ? `<span class="tc-flag">short history: ${n} samples${since}</span>`
    : state === 'FULL_WINDOW' ? `full window: ${n} samples${since}`
    : `source ${tcEsc(s.ivp_source || 'not recorded')} (not the ticker's own IV history)`;
  return `${parts.join(' · ')} · ${tcShow(s.ivp_label)}<div class="tc-note">${note}</div>`;
}

// M-G2-01 (ACK 10 Oct 2026): which quote valued the contract and when; the frozen Evening value beside a Morning one.
function tcValuedOn(s) {
  const basis = String(s.anticipated_contract_basis || '');
  const when = tcBlank(s.anticipated_valued_at_utc) ? 'time not recorded' : tcEsc(String(s.anticipated_valued_at_utc).slice(0, 16));
  const ref = tcBlank(s.eod_anticipated_value_multiple_q50) ? '' : ` · Evening reference ${tcEsc(tcNum(s.eod_anticipated_value_multiple_q50))}× (${tcEsc(s.eod_anticipated_pays_state || 'state not recorded')})`;
  if (basis.startsWith('MORNING_REPRICED')) return `Morning quote ${when}${ref}`;
  if (basis.startsWith('MORNING_CONTRACT_RECOMPUTED')) return `Morning quote ${when} (replacement contract)${ref}`;
  if (basis.startsWith('EVENING_REFERENCE')) return `<span class="tc-missing">Evening quote - no Morning quote for this contract</span>${ref}`;
  if (basis === 'EVENING_COMPLETED_SESSION_QUOTE') return `Evening close quote ${when}`;
  return tcShow(null, 'valuation basis not recorded');
}

// Output-trust item 7 (ACK's call-wall review, 10 Oct 2026): three separate conclusions - concentration, estimated
// dealer influence, observed price response. Display chain: instrument -> zone -> expiry basket -> method ->
// timestamps -> dealer-sign assumption -> observed price response -> status.
function tcWords(v) { return String(v || '').toLowerCase().replace(/_/g, ' '); }

function tcWallLine(s, basket, side, label) {
  const k = `wall_${basket}_${side}_`;
  const state = String(s[k + 'state'] || '');
  if (state !== 'QUALIFIED') return `${label}: <span class="tc-missing">${tcEsc(tcWords(state) || 'not computed in this run')}</span>`;
  const lo = tcNum(s[k + 'low']), hi = tcNum(s[k + 'high']);
  const zone = lo === hi ? lo : `${lo}–${hi}`;
  return `${label}: ${tcEsc(s.wall_instrument || s.ticker)} · ${side} zone ${tcEsc(zone)} (peak ${tcEsc(tcNum(s[k + 'peak']))})`
    + ` · ${Math.round(Number(s[k + 'share']) * 100)}% of basket · <b>${tcEsc(tcWords(s[k + 'price_status']))}</b>`
    + `<div class="tc-note">${tcEsc(s[k + 'price_note'] || '')}</div>`;
}

function tcWall(s, side) {
  if (tcBlank(s.wall_method)) return tcShow(null, 'not computed in this run');
  const exit = tcBlank(s.wall_exit_date) ? 'exit date not set' : `through ${tcEsc(s.wall_exit_date)}`;
  const chain = tcBlank(s.wall_chain_asof_utc) ? 'chain time not recorded' : `chain ${tcEsc(String(s.wall_chain_asof_utc).slice(0, 10))}`;
  const oi = tcBlank(s.wall_oi_clearing_date) ? 'OI date not recorded' : `OI ${tcEsc(s.wall_oi_clearing_date)}`;
  return tcWallLine(s, 'hold', side, exit) + tcWallLine(s, 'post', side, 'after exit')
    + `<div class="tc-note">gamma x OI x multiplier (${tcEsc(tcWords(s.wall_multiplier_basis))}) · ${chain}, ${oi}`
    + ` · dealer sign not estimated (concentration is unsigned)</div>`;
}

function tcGammaFlip(s, spot) {
  const level = tcLevel('gamma_flip', s.gamma_flip, spot);
  const state = String(s.gamma_flip_confidence_state || '').toUpperCase();
  const conf = tcBlank(s.gamma_flip_conf) ? '?' : Number(s.gamma_flip_conf).toFixed(2);
  const reading = state === 'LOW_CONFIDENCE' ? `<span class="tc-missing">indicative only (confidence ${conf}, below the governed minimum)</span>`
    : state === 'CONFIDENT' ? `confidence ${conf}` : tcShow(null, 'confidence not recorded');
  return `${level} · ${reading}<div class="tc-note">dealer sign assumed (customers long puts, short calls), unverified</div>`;
}

function renderTradeCard(s, profile) {
  const dir = String(s.direction || s.final_direction || 'UNRESOLVED').toUpperCase();
  // ACK 7 Oct 2026 / 9 Oct 2026: the side carries what the predictive-edge test found (display only); missing is stated.
  const edge = tcEdgeLabel(s.direction_validation_state);
  const side = edge ? `${tcEsc(dir)} · ${tcEsc(edge)}` : `${tcEsc(dir)} · <span class="tc-missing">direction validation not recorded</span>`;
  const spot = s.live_price || s.current_price || s.signal_price || s.underlying_price;
  const sections = [
    tcSection('1 · What and which side', [
      tcRow('Ticker / side', `<strong>${tcEsc(s.ticker)}</strong> · ${side} · tier ${tcShow(s.tier)}`),
      // Three separate claims: what the structure says, whether the trigger happened, whether an edge was measured.
      tcRow('Structural bias', tcStructuralBias(s), 'the side the top-down thesis takes'),
      tcRow('Trigger state', TC_READINESS[String(s.thesis__readiness || '').toUpperCase()] || tcShow(s.thesis__readiness, 'readiness not recorded')),
      tcRow('Predictive edge', edge ? tcEsc(edge) : tcShow(null, 'not recorded'),
            tcBlank(s.direction_validation_basis) ? '' : tcEsc(s.direction_validation_basis)),
      tcRow('Structure scope', tcStructureScope(s), 'thesis engine: timeframe · scope · since'),
      tcRow('Structure (Phase · Event)', tcStructurePhaseEvent(s),
            tcBlank(s.thesis_structure_alignment) ? '' : `alignment ${tcEsc(s.thesis_structure_alignment)}`),
      tcRow('Event status', tcStructureStatus(s)),
      tcRow('Failure evidence', tcStructureFailure(s)),
      tcRow('Other timeframes', tcStructureOthers(s)),
      tcRow('Lane', tcLane(s), tcBlank(s.intake_flags) || s.intake_flags === 'NONE' ? '' : `intake labels ${tcEsc(s.intake_flags)}`),
      tcRow('Thesis (top-down)', tcThesisSpine(s)),
    ]),
    tcSection('2 · Why now', [
      tcRow('Thesis trigger', tcThesisTrigger(s), tcThesisNote(s)),
      tcRow('State reading', tcTrigger(s), 'state reading, not the trigger'),
      tcRow('Intraday build-up', tcIntraday(s), 'advisory: untested, never decides'),
      tcRow('Morning validation', tcShow(s.validation_transition, 'Morning not run'),
            tcBlank(s.remaining_runway_state) ? '' : `runway ${tcEsc(s.remaining_runway_state)}`),
    ]),
    // Anticipated move (ACK 3 Oct 2026): R:R and the 3R target leave the card (audit tier only); the invalidation
    // is the thesis exit, never part of the move. Display only until the replay validation.
    tcSection('3 · Where wrong, where right', [
      tcRow('Geometry', tcGeometry(s), 'underlying levels only; the option is valued separately'),
      tcRow('Thesis exit (invalidation)', tcShow(tcNum(s.invalidation_price)),
            'the qualifying setup is wrong beyond this level (decides)'),
      // S2-1 / I-c (ACK 6 Oct 2026): the daily primary's nearer level, when it is a different setup, is a warning only.
      tcRow('Early warning (daily)', tcShow(tcNum(s.early_warning_invalidation_level), 'none (the daily setup is the qualifying setup)'),
            'a nearer daily level; watch it, it does not decide'),
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
      // Fix D (ACK 5 Oct 2026): units stated - contract_dte counts XNYS trading sessions, dte calendar days.
      tcRow('Contract expiry', `${tcShow(s.expiry)} · ${tcShow(s.dte)} calendar days · ${tcShow(s.contract_dte)} trading sessions`),
      tcRow('Catalyst', tcShow(s.catalyst_date, 'none recorded'), tcBlank(s.catalyst_inside_dte) ? '' : `inside DTE: ${tcEsc(s.catalyst_inside_dte)}`),
      // Earnings disclosure (ACK 3 Oct 2026): position risk against the hold and expiry; never a gate.
      tcRow('Earnings', tcBlank(s.earnings_state) ? '<span class="tc-missing">earnings not checked in this run</span>' : tcEsc(s.earnings_disclosure || s.earnings_state)),
    ]),
    tcSection('5 · Which contract, at what cost', [
      tcRow('Contract', `${tcShow(s.contract_symbol)} · strike ${tcShow(s.strike)}`),
      tcRow('Spread', tcSpread(s)),
      tcRow('Other theses priced', tcAlternatives(s), 'each on its own side and levels; alternatives, not the governing trade'),
      tcRow('Delta / IV', `${tcShow(tcNum(s.contract_delta, 3))} / ${tcShow(tcNum(s.contract_iv, 3))}`),
      tcRow('IV percentile / rank', tcIvHistory(s), 'own ATM IV history of the ticker'),
      tcRow('OI / volume / breakeven', `${tcShow(s.contract_oi)} / ${tcShow(s.contract_volume)} / ${tcShow(tcNum(s.breakeven_price))}`),      tcRow('Does the move pay', tcBlank(s.anticipated_move_coverage) ? '<span class="tc-missing">not computed in this run</span>'
            : ({PAYS: '<b>pays if the level is reached by the median time</b> · ', DOES_NOT_PAY_AT_ANTICIPATED_TIME: '<span class="tc-missing">does not pay even if the level is reached by the median time (no GO)</span> · ', NOT_ASSESSED_VOLATILITY_ONLY: '<span class="tc-missing">not assessed: no structural target on the trade side (volatility reach only)</span> · '}[s.anticipated_pays_state] || '') + `coverage ${tcEsc(tcNum(s.anticipated_move_coverage))}× breakeven move (${tcEsc(tcNum(s.anticipated_breakeven_move_pct))}%) · value ${tcShow(tcNum(s.anticipated_value_multiple_q50))}× premium after spread and fees at median time (one engine), at the level reachable by then (${tcShow(tcNum(s.anticipated_level_q50))}) - conditional on the level being reached, not an expected outcome`,
            tcBlank(s.anticipated_stress_basis) ? '' : `stress: ${tcShow(tcNum(s.anticipated_value_multiple_q80))}× at ${tcEsc(s.anticipated_stress_basis)}${tcBlank(s.anticipated_value_multiple_earnings_stress) ? '' : ` · ${tcEsc(tcNum(s.anticipated_value_multiple_earnings_stress))}× with earnings IV stress`}`),
      tcRow('Scenarios', tcScenarios(s), 'one engine; conditional on each path, not an expected value'),
      tcRow('Valued on', tcValuedOn(s), 'the quote behind the value and scenarios'),
    ]),
    tcSection('6 · Context (advisory)', [
      tcRow('Sector', `${tcShow(s.sector)} · ${tcShow(s.sector_etf)}`),
      tcRow('Vanguard history', tcShow(s.vanguard_context_flags, 'no flags recorded'),
            'context only, never decides' + (tcBlank(s.legacy_execution_permission_context) ? ''
              : ` · legacy execution label ${tcEsc(s.legacy_execution_permission_context)} (context only)`)),
      tcRow('Money Index / macro', `${tcShow(s.usmi_sector_alignment)} / ${tcShow(s.macro_sector_alignment)}`),
      tcRow('Gamma flip (estimated dealer influence)', tcGammaFlip(s, spot)),
      tcRow('Call concentration', tcWall(s, 'call'), 'an options concentration, not support or resistance until price shows it'),
      tcRow('Put concentration', tcWall(s, 'put'), 'an options concentration, not support or resistance until price shows it'),
    ]),
    tcSection('7 · Decision state', [
      tcRow('Lab verdict / action', `${tcShow(s.lab_verdict)} / ${tcShow(s.final_action)}`),
      tcRow('Conflict / evening bucket', `${tcShow(s.conflict_state)} / ${tcShow(s.evening_thesis_bucket)}`),
      tcRow('Open position', tcBlank(s.governance__verdict) ? 'none' : `governance ${tcEsc(s.governance__verdict)}: ${tcEsc(s.governance__reason || '')}`),
    ]),
    tcSection('8 · Can I trust the data', [
      tcRow('Quote', tcQuote(s)),
      tcRow('Price bars as of', tcShow(s.bar_data_asof)),
      // A1 (ACK 6 Oct 2026): an aged share price is used and its age shown - never discarded, never a gate.
      tcRow('Share price', tcSharePrice(s)),
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
  'ticker', 'direction', 'tier', 'thesis_category', 'thesis_structure_alignment', 'thesis_phase', 'thesis_event',
  'thesis_event_state', 'thesis_event_timeframe', 'thesis_event_scope', 'thesis_event_candidate_id', 'thesis__last_event_date',
  'thesis__last_event_level',
  'wall_method', 'wall_instrument', 'wall_chain_asof_utc', 'wall_oi_clearing_date', 'wall_multiplier_basis', 'wall_exit_date', 'wall_hold_call_peak', 'wall_hold_call_low', 'wall_hold_call_high', 'wall_hold_call_share', 'wall_hold_call_state', 'wall_hold_call_price_status', 'wall_hold_call_price_note', 'wall_hold_put_peak', 'wall_hold_put_low', 'wall_hold_put_high', 'wall_hold_put_share', 'wall_hold_put_state', 'wall_hold_put_price_status', 'wall_hold_put_price_note', 'wall_post_call_peak', 'wall_post_call_low', 'wall_post_call_high', 'wall_post_call_share', 'wall_post_call_state', 'wall_post_call_price_status', 'wall_post_call_price_note', 'wall_post_put_peak', 'wall_post_put_low', 'wall_post_put_high', 'wall_post_put_share', 'wall_post_put_state', 'wall_post_put_price_status', 'wall_post_put_price_note',
  'anticipated_contract_basis', 'anticipated_valued_at_utc', 'eod_anticipated_value_multiple_q50', 'eod_anticipated_pays_state',
  'iv_percentile', 'iv_rank', 'ivp_source', 'iv_rank_window_sessions', 'iv_history_state', 'iv_history_first_date',
  'valuation_model', 'valuation_rate_annual', 'valuation_dividend_yield_annual', 'valuation_dividend_basis',
  'scenario_exit_sessions', 'scenario_iv_basis', 'scenario_target_exit_spot', 'scenario_target_return_on_premium',
  'scenario_invalidation_exit_spot', 'scenario_invalidation_return_on_premium', 'scenario_stall_return_on_premium',
  'scenario_target_earnings_iv_return_on_premium',
  'geometry_justification', 'geometry_reason', 'geometry_entry_basis', 'geometry_entry_price', 'geometry_reward_price',
  'geometry_risk_price', 'geometry_reward_atr', 'geometry_risk_atr', 'geometry_early_warning_risk_atr',
  'geometry_breakeven_hit_rate', 'geometry_measured_hit_rate', 'geometry_hit_n', 'geometry_hit_low', 'geometry_hit_high', 'trigger_primary', 'trigger_quality',
  'thesis_trigger_level', 'thesis_trigger_candidate_id', 'thesis__top_timeframe', 'thesis__conflicting_count',
  'thesis__readiness', 'thesis__readiness_reason', 'thesis__last_event', 'ib_state', 'ib_last_event',
  'vanguard_context_flags', 'thesis_alternatives_count', 'thesis_alternatives_tested', 'thesis_alternatives_json',
  'trade_lane', 'trade_lane_basis', 'trade_lane_setup', 'trade_lane_hit_original', 'trade_lane_hit_holdout',
  'setup_forward_state', 'setup_forward_text',
  'trade_lane_required_multiple', 'intake_flags', 'price_band',
  'trigger_go_eligible', 'validation_transition', 'remaining_runway_state', 'invalidation_price',
  'early_warning_invalidation_level', 'trade_lane_candidate_id', 'daily_event',
  'anticipated_move_state', 'anticipated_level', 'anticipated_level_q50', 'anticipated_level_basis', 'anticipated_move_pct',
  'anticipated_structural_level', 'anticipated_structural_definition', 'anticipated_p_outcome_by_limit',
  'anticipated_evidence_n', 'anticipated_sessions_q50', 'anticipated_sessions_q80', 'anticipated_time_basis',
  'anticipated_move_coverage', 'anticipated_breakeven_move_pct', 'anticipated_value_multiple_q50',
  'anticipated_value_multiple_q80', 'anticipated_value_multiple_earnings_stress', 'anticipated_stress_basis', 'anticipated_time_fit', 'anticipated_pays_state', 'thesis_activation_q50_bars', 'thesis_activation_q80_bars',
  'planned_hold_sessions', 'expiry', 'dte', 'contract_dte', 'catalyst_date', 'catalyst_inside_dte', 'contract_symbol', 'strike',
  'contract_bid', 'contract_ask', 'spread_pct', 'contract_delta', 'contract_iv', 'ivp_label', 'contract_oi',
  'contract_volume', 'breakeven_price', 'sector', 'sector_etf', 'usmi_sector_alignment', 'macro_sector_alignment',
  'gamma_flip', 'gamma_flip_conf', 'gamma_flip_confidence_state', 'call_wall', 'put_wall', 'call_wall_state',
  'put_wall_state', 'call_wall_level_confirmed', 'put_wall_level_confirmed', 'wall_basis', 'lab_verdict', 'final_action', 'conflict_state', 'evening_thesis_bucket',
  'governance__verdict', 'governance__reason', 'quote_freshness', 'earnings_state', 'earnings_disclosure', 'selected_quote_timestamp_utc', 'bar_data_asof',
  'signal_price', 'live_price', 'current_price', 'underlying_price']);
const TC_SKIP = new Set(['source_payload_json']);
// ACK 3 Oct 2026: stop-based R:R and invented 3R targets are retired from decisions; kept for audit only.
// ACK 9 Oct 2026 (D2-1 Step A): the legacy structure producers (Wyckoff engine labels, Wyckoff validation heuristics,
// forecast structure stage, structure evidence) are inactive on the card; the thesis engine owns structure.
// ACK 9 Oct 2026 (D5-1): EV3, monetisability and option_gain_at_target (USD per share, not %) are legacy payoffs; the
// one valuation engine's scenarios replace them.
const TC_LEGACY = /^(rr|rr_.*|target_3r.*|structural_target|target_zone|target_price|target_price_source|option_gain_at_target|estimated_r|max_convex_r_multiple|runway_to_target|wyckoff_.*|phase|forecast_structure_stage|structure_evidence.*|lab_v4_structure_evidence.*|ev3_.*|ev_predicted|monetisability_.*|economics_comparable|option_gain_at_target_usd_per_share|legacy_oi_.*|oi_max_call_strike|oi_max_put_strike)$/i;
const TC_LINEAGE = /(authority|version|policy|sha256|hash|calculation|lineage|_id$|_ids$|dataset_id|snapshot_id|_run_id$|source_path)/i;
const TC_FAMILIES = [
  [/^(wyckoff|phase|dominant_event|truth_confidence|event_)/, 'Wyckoff structure (legacy engine)'],
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
      <details class="tc-group"><summary>Legacy (inactive): stop-based R:R, 3R targets, legacy Wyckoff structure, EV3 and monetisability payoffs - not evidence</summary>${tcFieldList(s, [...profile.legacy].sort())}</details>
      <details class="tc-group"><summary>Lineage (authority, version, policy, ids, hashes)</summary>${tcFieldList(s, [...profile.lineage].sort())}</details>
      <details class="tc-group"><summary>Constant across this run</summary>${tcFieldList(s, [...profile.constant].sort())}</details>
      <details class="tc-group"><summary>Duplicates (same value as another field on every row)</summary>${tcFieldList(s, dups, f => `same as ${tcEsc(profile.duplicateOf[f])}`)}</details>
      <details class="tc-group"><summary>Always empty in this run (to trace)</summary><div class="tc-note">${profile.empty.map(tcEsc).join(', ') || 'none'}</div></details>
    </details>`;
  return `<details class="tc-evidence"><summary>Evidence drawer: ${profile.evidence.length} further informative fields by family</summary>${groupHtml}</details>${audit}`;
}
