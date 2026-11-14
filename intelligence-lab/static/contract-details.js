/* Shared, saved-only contract identity display. No parsing, clocks, fetching or pricing. */
(()=>{'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const count=v=>v==null?'Not recorded':Number.isInteger(Number(v))?String(Number(v)):String(v);
const strike=v=>v==null?'Not recorded':'$'+Number(v).toFixed(Number(v)*100===Math.round(Number(v)*100)?2:3);
function render(d){d=d||{};const facts=[['Strike',strike(d.strike)],['Call/Put',d.call_put||'Not recorded'],
['Expiry',d.expiry||'Not recorded'],['Calendar DTE',count(d.calendar_dte)],
['Trading sessions remaining',count(d.trading_sessions_remaining)],
['Saved reference date',d.saved_reference_date||'Not recorded']];
return `<div class="saved-contract-details" aria-label="Saved exact contract details"><dl>${facts.map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl><p class="muted">Saved snapshot — not a live countdown. ${esc(d.reference_basis||'Reference basis not recorded.')}<br>Session count: ${esc(d.trading_sessions_basis||'Not recorded')}<br>Quote/valuation: ${esc(d.saved_quote_timestamp||'Not recorded')}<br>${esc(d.strike_basis||'Strike basis not recorded.')}${d.issues?.length?'<br>Review: '+d.issues.map(esc).join(' · '):''}</p></div>`;}
window.LabContractDetails={render};
})();
