/* Published crossing scenario only (AVS-TRADE-001 design v4, ACK 14 Nov 2026): no fetching, pricing or ranking. */
(()=>{'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const show=v=>v==null||v===''?'Not recorded':String(v);
const sessions=v=>v==null||v===''?'no crossing recorded':`session ${v}`;
function candidates(text){try{const d=JSON.parse(text||'null');return d&&Array.isArray(d.candidates)?d:null;}catch(e){return null;}}
function render(f){f=f||{};
const facts=[
 ['Scenario state (slow pace, +30%, base)',f.crossing_state],
 ['Covers its crossing (slow pace, +30%, base)',f.crossing_covers_slow30_base],
 ['Median pace · +20% / +30%',`${sessions(f.crossing_n_median_pace_20)} / ${sessions(f.crossing_n_median_pace_30)}`],
 ['Slow pace · +20% / +30%',`${sessions(f.crossing_n_slow_pace_20)} / ${sessions(f.crossing_n_slow_pace_30)}`],
 ['Slow pace +30% · IV down / wider exit spread',`${sessions(f.crossing_n_slow_pace_30_iv_down)} / ${sessions(f.crossing_n_slow_pace_30_wide_exit)}`],
 ['Search ended at / because',`${sessions(f.crossing_search_end_session)} (${show(f.crossing_search_end_date)}) · ${show(f.crossing_search_limit)} · cap ${show(f.crossing_search_cap)} sessions`],
 ['Sessions to expiry / last usable exit session',`${show(f.crossing_sessions_to_expiry)} / ${show(f.crossing_usable_deadline_session)} (${show(f.crossing_usable_deadline_date)})`],
 ['Monitoring deadline',`${show(f.crossing_monitor_deadline_session)} (${show(f.crossing_monitor_deadline_date)})`],
 ['Mode / assessed at',`${show(f.crossing_mode)} · ${show(f.crossing_assessment_instant_utc)}`],
 ['Thesis origin / sessions elapsed / first grid session',`${show(f.crossing_thesis_origin_date)} / ${show(f.crossing_elapsed_sessions)} / ${show(f.crossing_grid_first_date)}`],
 ['Quote spot → frozen target',`${show(f.crossing_quote_spot)} → ${show(f.crossing_frozen_target_level)}`],
 ['Contract / quote time',`${show(f.crossing_contract_symbol)} · ${show(f.crossing_quote_timestamp_utc)}`],
 ['IV used / IV-down / exit-spread multiple',`${show(f.crossing_iv_used)} / ${show(f.crossing_iv_down_used)} / ${show(f.crossing_exit_spread_multiple)}`],
 ['Rate / dividend basis',`${show(f.crossing_rate_basis)} / ${show(f.crossing_dividend_basis)}`],
 ['Selected quote · validity / tier / provenance',`${show(f.quote_tier_validity)} / ${show(f.quote_tier)} (${show(f.quote_tier_reason)}) / ${show(f.quote_provenance)} (${show(f.quote_provenance_reason)})`],
 ['Shadow comparison',`${show(f.crossing_shadow_symbol)} · ${show(f.crossing_shadow_reason)}`],
 ['Shadow · tier / crossing / sessions to expiry / entry cost',`${show(f.crossing_shadow_tier)} / ${sessions(f.crossing_shadow_n_slow_pace_30)} / ${show(f.crossing_shadow_sessions_to_expiry)} / ${show(f.crossing_shadow_entry_cost)}`],
 ['Set / complete',`${show(f.crossing_shadow_set)} · ${show(f.crossing_shadow_set_complete)}`]];
const set=candidates(f.crossing_candidates_json);
const table=set?`<table class="crossing-candidates"><thead><tr><th>Contract</th><th>Role</th><th>State</th><th>+30% slow</th><th>Tier</th><th>Quote</th><th>Sessions to expiry</th><th>Ask</th></tr></thead><tbody>${set.candidates.map(c=>`<tr><td>${esc(show(c.symbol))}</td><td>${esc(show(c.role))}</td><td>${esc(show(c.state))}</td><td>${esc(sessions(c.n_slow_pace_30))}</td><td>${esc(show(c.tier??c.validity))}</td><td>${esc(show(c.provenance))}</td><td>${esc(show(c.sessions_to_expiry))}</td><td>${esc(show(c.ask))}</td></tr>`).join('')}</tbody></table><p class="muted">${esc(show(set.assessed))} assessed of ${esc(show(set.pool_scored))} scored contracts; ${esc(show(set.truncated_by_cap))} cut short by the search cap. Candidates are assessed on the slow pace at base IV and with a wider exit only.</p>`:'';
return `<section class="notice crossing-scenario" aria-label="Crossing scenario"><h3>Crossing scenario · when would this contract show +20% / +30%?</h3><dl class="facts">${facts.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(show(v))}</dd>`).join('')}</dl>${table}<p class="muted">A scenario on an assumed path from the quote to the thesis target, not a forecast, a probability of profit or a measured clock. It answers what a new entry at this quote would need. Invalidation is not modelled. Model values are not fills. Shadow only: the selected contract, rank and published decisions are unchanged.</p></section>`;
}
window.LabCrossingScenario={render};
})();
