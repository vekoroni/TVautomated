/* Explicit, saved-manifest-only short-horizon discovery. No provider/full-book load. */
(()=>{'use strict';
let current=null, loaded=null;
const byId=id=>document.getElementById(id),esc=v=>String(v??'Not recorded').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function render(){
if(!loaded)return;
const mode=byId('short-horizon-mode').value,rows=(loaded.short_candidates||[]).filter(r=>r.timing_details[mode==='planned'?'planned_short_1_5':'arrival_short_1_5']);
byId('short-horizon-status').textContent=`${rows.length} saved candidates · ${loaded.planned_1_5_count} short planned holds / ${loaded.arrival_1_5_count} fast median arrivals in this run. Published verdicts and exclusions remain in force; this is not an entry-ready list.`;
byId('short-horizon-results').innerHTML='<table><thead><tr><th>Ticker</th><th>Arrival / planned / remaining</th><th>Published review</th><th>Exclusions / counterevidence</th></tr></thead><tbody>'+rows.map(r=>{const t=r.timing_details;return `<tr><td><button data-short-row="${esc(r.row_key)}" type="button">${esc(r.ticker)}</button></td><td>${esc(t.arrival_median_sessions)} / ${esc(t.planned_hold_sessions)} / ${esc(t.remaining_hold_sessions)} sessions</td><td>${esc(r.lab_verdict)}<br>${esc(t.expiry_session_check_state)}</td><td>${esc((t.exclusion_reasons||[]).join(' · ')||'No additional saved exclusion reason recorded; inspect the card and quote freshness. Entry is not authorised.')}</td></tr>`}).join('')+'</tbody></table>';
}
window.addEventListener('lab-review-loaded',e=>{if(current?.run!==e.detail.run||current?.revision!==e.detail.revision){current=e.detail;loaded=null;byId('short-horizon-results').replaceChildren();byId('short-horizon-status').textContent='Load saved candidates and exclusion reasons; no providers or recalculation.'}});
byId('short-horizon-mode').addEventListener('change',render);
byId('short-horizon-load').addEventListener('click',async()=>{if(!current)return;const pin={...current};try{const response=await fetch(`/api/lab/${encodeURIComponent(pin.run)}/summary`);if(!response.ok)throw Error('Saved summary unavailable');const data=await response.json();if(current.run!==pin.run||current.revision!==pin.revision)return;if(data.revision!==pin.revision)throw Error('Revision changed; use Refresh');if(!data.timing_summary)throw Error('Timing publication not available for this historical run');loaded=data.timing_summary;render()}catch(e){byId('short-horizon-status').textContent=e.message}});
byId('short-horizon-results').addEventListener('click',e=>{const button=e.target.closest('[data-short-row]');if(button&&current)window.dispatchEvent(new CustomEvent('lab-convexity-select',{detail:{...current,rowKey:button.dataset.shortRow}}))});
})();
