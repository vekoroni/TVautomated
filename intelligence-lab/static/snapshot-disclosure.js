/* Saved snapshot provenance only; no provider calls, repricing or decisions. */
(()=>{'use strict';
const esc=v=>String(v??'Not recorded').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const shown=v=>v==null||String(v).trim()===''?'Not recorded':esc(v);
const costs=v=>shown(typeof v==='string'?v.replace('ENTRY_AT_ASK_PLUS_FEE|EXIT_AT_MODEL_LESS_HALF_QUOTED_SPREAD|','Entry at saved ask plus opening fee; exit at model value less half the saved quoted spread. '):v);
function render(d){
if(!d)return '<section class="notice"><h3>Saved snapshot provenance</h3><p>Snapshot audit not published for this historical view. No live entry quote is verified.</p></section>';
const c=d.current_scenario||{},h=d.historical_timevalue||{},q=d.quote||{},t=d.timing||{},doi=d.doi_scenario||{};
return `<section class="notice snapshot-disclosure" aria-label="Saved snapshot provenance" style="overflow-wrap:anywhere">
<h3>Saved snapshot provenance · not live execution</h3>
<p><strong>Current-contract conditional scenario:</strong> ${shown(c.state)} · ${shown(c.contract_symbol)} · valued ${shown(c.valued_at_utc)} · ${shown(c.exit_sessions)} sessions to ${shown(c.exit_date)}. Model ${shown(c.model)}. This is a conditional payoff, not an expected or realised return.</p>
<p>Costs: ${costs(c.cost_basis)}</p>
<p><strong>Separate DOI scenario family:</strong> ${shown(doi.state)} · ${shown(doi.reason)}. Its status does not describe the current conditional payoff above.</p>
<p><strong>Historical time-value reference:</strong> ${shown(h.state)} · as of ${shown(h.as_of_session)} · expiry ${shown(h.expiry)} · historical return ${shown(h.return_pct)}%. ${h.state==='REFERENCE_ONLY'?'Excluded from current-contract fields; not repriced. '+esc((h.mismatch_reasons||[]).join(' · ')):''}</p>
<p><strong>Timing evidence:</strong> ${shown(t.hold_basis)} · ${shown(t.arrival_state)} · evidence ${shown(t.evidence_status)}, n=${shown(t.evidence_n)}. ${shown(t.warning)} EV3 ${shown(t.ev3_status)}: ${shown(t.ev3_reason)}</p>
<p><strong>Saved quote reference:</strong> ${shown(q.state)} · ${shown(q.provider)} · observed ${shown(q.observation_at_utc)}. Configured feed delay ${shown(q.configured_delay_seconds)} seconds; effective assessment window ${shown(q.configured_effective_window_seconds)} seconds beyond that delay. Saved feed-window status: ${shown(q.saved_assessment_state)}. Raw age at saved assessment: ${shown(q.saved_raw_age_minutes)} minutes; effective age after delay: ${shown(q.saved_effective_age_seconds)} seconds. These are historical assessment ages, not ages now.</p>
<p><strong>Live broker re-quote required before entry.</strong> No live quote or execution permission is granted by this publication.</p></section>`;
}
window.LabSnapshotDisclosure={render};
})();
