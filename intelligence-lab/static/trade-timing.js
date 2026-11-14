/* Saved trade timing only: never infer a hold or arrival estimate from option DTE. */
(()=>{'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function sessions(value){
if(value==null||typeof value==='boolean'||String(value).trim()==='')return 'Not recorded';
const n=Number(value);
return Number.isFinite(n)&&n>=0?`${n} trading session${n===1?'':'s'}`:'Not recorded';
}
function basis(value){return value==null||String(value).trim()===''?'Not recorded':String(value);}
function render(fields,timing){
const f=fields||{},t=timing||{},fact=(k,v)=>`<div><dt>${esc(k)}</dt><dd>${sessions(v)}</dd></div>`;
return `<section class="trade-timing" aria-label="Saved trade horizon and planned hold"><h3>Trade horizon &amp; planned hold · 1–n sessions</h3><dl class="trade-timing-facts">${fact('Trade horizon · median arrival (q50)',t.arrival_median_sessions??f.anticipated_sessions_q50)}${fact('Slower-arrival estimate (q80)',t.arrival_q80_sessions??f.anticipated_sessions_q80)}${fact('Planned hold · original budget',t.planned_hold_sessions??f.planned_hold_sessions)}${fact('Remaining hold · saved assessment',t.remaining_hold_sessions)}${fact('Payoff valuation horizon',t.valuation_horizon_sessions??f.scenario_exit_sessions)}${fact('Empirical EV3 scoring horizon',t.empirical_valuation_horizon_sessions)}</dl><p class="muted">Saved estimates in trading sessions — not option DTE, a live countdown or a guaranteed deadline. No fixed maximum hold is imposed.</p><p class="muted timing-basis">Saved assessment: ${esc(basis(t.timing_as_of))} · Hold clock: ${esc(basis(t.hold_clock_state))}<br>Planning reference: ${esc(basis(t.planned_hold_reference_date))} · Valuation reference: ${esc(basis(t.valuation_reference_utc))}<br>Arrival basis: ${esc(basis(f.anticipated_time_basis))}<br>Hold basis: ${esc(basis(f.planned_hold_source))}<br>EV3 horizon: ${esc(basis(t.empirical_horizon_state))} — a grid approximation is not a valuation at the full planned hold.</p><p class="timing-runway"><strong>Exact expiry runway:</strong> ${esc(basis(t.expiry_session_check_state))} · available ${sessions(t.expiry_sessions_remaining)} · required including monitoring/exit buffers ${sessions(t.minimum_required_sessions)}.</p>${t.review_override?'<p class="timing-review-warning">'+esc(t.review_override)+' · Original published verdict: '+esc(t.published_lab_verdict)+'</p>':''}</section>`;
}
window.LabTradeTiming={render};
})();
