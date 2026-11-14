/* Published identity disclosure only: no fetching, classification or ranking. */
(()=>{'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const show=v=>v==null||v===''?'Not recorded':v===true?'Yes':v===false?'No':String(v);
function render(f){f=f||{};
const facts=[['Instrument type (source reported)',f.instrument_type],['Identity assessment',f.instrument_identity_state],
 ['Identity review reason',f.instrument_identity_reason],['Reported wrapper',f.instrument_wrapper],
 ['Leverage / inverse / volatility exposure',[f.instrument_leveraged,f.instrument_inverse,f.instrument_volatility].map(show).join(' / ')],
 ['Product review policy',f.instrument_review_policy],['Policy reason',f.instrument_review_policy_reason],
 ['Policy source',f.instrument_policy_source],['Policy source SHA-256',f.instrument_policy_source_sha256],
 ['Classification as of',f.instrument_identity_asof],
 ['Saved reference date',f.instrument_identity_reference_date],['Source',f.instrument_identity_source],
 ['Source SHA-256',f.instrument_identity_source_sha256],['Policy version',f.instrument_policy_version]];
return `<section class="notice instrument-identity" aria-label="Instrument identity and product policy"><h3>Instrument identity & product policy</h3><dl class="facts">${facts.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(show(v))}</dd>`).join('')}</dl><p class="muted">Source-reported classification, not independent issuer verification. Unknown is not unleveraged. Research-only policy is displayed for human review; canonical rank, selected contract and published decisions are unchanged.</p></section>`;
}
window.LabInstrumentIdentity={render};
})();
