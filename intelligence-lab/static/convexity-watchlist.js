/* Saved comparison reader only. No pricing, providers, polling or permission changes. */
(()=>{'use strict';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(v,d=2)=>v==null||v===''||!Number.isFinite(Number(v))?'Unavailable':Number(v).toFixed(d);
const pct=v=>v==null?'Unavailable':`${Number(v)>=0?'+':''}${num(Number(v)*100,1)}%`;
let run='',revision='',sequence=0;
function reset(detail={}){++sequence;run=detail.run||'';revision=detail.revision||'';$('convexity-content').replaceChildren();$('convexity-load').disabled=false;$('convexity-status').textContent='Load the saved comparisons for this run. No provider calls or on-page repricing.';}
window.addEventListener('lab-review-reset',()=>reset());
$('review-refresh').addEventListener('click',()=>reset());
$('review-run').addEventListener('change',()=>reset());
window.addEventListener('lab-review-loaded',e=>{if(run!==e.detail.run||revision!==e.detail.revision)reset(e.detail)});
function table(rows){if(!rows.length)return '<p class="muted">No candidates meet this section’s saved-data requirements.</p>';
return `<div class="table-wrap"><table class="convexity-table"><thead><tr><th>Ticker / exact contract</th><th>Saved entry & levels</th><th>Target profit / loss</th><th>Same-target delay</th><th>IV × 0.8</th><th>Delay + lower IV</th><th>Readiness & restrictions</th></tr></thead><tbody>${rows.map(r=>`<tr>
<td><button type="button" data-convexity-row="${esc(r.row_key)}">${esc(r.ticker)} · ${esc(r.direction)}</button><br>${esc(r.contract_symbol)}<br><span class="muted">${esc(r.thesis_event)}<br>Quote ${esc(r.selected_quote_timestamp_utc||'time not recorded')}</span></td>
<td>$${num(r.entry_per_contract)} / standard contract<br>Trigger $${num(r.thesis_trigger_level)}<br>Target $${num(r.target_spot)}<br>Invalidation $${num(r.invalidation_price)}<br><span class="muted">Spread ${num(r.spread_pct_mid)}% · OI ${esc(r.contract_oi??'?')} · volume ${esc(r.contract_volume??'?')}</span></td>
<td><strong>${pct(r.target_return)}</strong> in ${num(r.target_sessions,0)} sessions<br>Invalidation ${pct(r.invalidation_return)}<br>Stall ${pct(r.stall_return)}<br><span class="muted">Modelled at median horizon; not a stop-fill promise</span></td>
<td>${pct(r.stress.delay_return)}<br><span class="muted">${num(r.stress.delay_sessions,0)} sessions; same target</span></td>
<td>${pct(r.stress.iv_return)}<br><span class="muted">IV ${num(Number(r.stress.iv_original)*100,1)}% → ${num(Number(r.stress.iv_stressed)*100,1)}%</span></td>
<td><strong>${pct(r.stress.combined_return)}</strong><br><span class="muted">${esc(r.stress.state)}${r.stress.reason?'<br>'+esc(r.stress.reason):''}</span></td>
<td>${esc(r['thesis__readiness'])}<br>${esc(r.lab_verdict)} · ${esc(r.morning_entry_action||'entry action not recorded')}<br><span class="muted">${esc(r.geometry_justification||'geometry not recorded')}<br>${esc(r.geometry_reason||'')}<br>${esc(r.execution_lock_reason||'')}<br>Source capital permission: ${esc(r.final_capital_permission||'not recorded')}<br>Automatic execution: never granted here</span></td></tr>
<tr><td colspan="7" class="convexity-caveat">${esc(r.earnings_disclosure||'Earnings evidence not recorded.')} · ${esc(r.anticipated_evidence_status||'Historical validation status not recorded.')} · ${esc(r.valuation_cost_basis||'Cost basis not recorded.')}</td></tr>`).join('')}</tbody></table></div>`;}
async function load(){if(!run||!revision){$('convexity-status').textContent='Wait for a coherent published run, then load comparisons.';return}
const ticket=++sequence,pin=revision,currentRun=run,abort=new AbortController(),timer=setTimeout(()=>abort.abort(),20000);
$('convexity-load').disabled=true;$('convexity-status').textContent='Reading saved comparisons — no pricing or provider request…';
try{const response=await fetch(`/api/lab/${encodeURIComponent(run)}/convexity?revision=${encodeURIComponent(pin)}`,{signal:abort.signal,cache:'no-store'}),d=await response.json();
if(ticket!==sequence)return;if(!response.ok)throw new Error(d.reason||d.state||`HTTP ${response.status}`);
if(d.revision!==pin||d.run_id!==currentRun)throw new Error('Comparison revision does not match the trade review');
const g=d.groups||{};
$('convexity-status').textContent=`Saved run ${d.run_id} · review ${d.revision.slice(0,10)} · source publication ${d.source_publication_utc} · ${d.population} source rows · research display only`;
$('convexity-content').innerHTML=`<div class="notice"><strong>Compare scenarios, not win probabilities.</strong><p>Returns include the saved ask, spread and fees. Every long option can lose its entire premium. Confirmation may cost more; do not assume these pre-trigger economics survive a later entry.</p><p class="muted">Waiting screen: target profit ≥ ${num(d.policy.waiting_min_target_return*100,0)}%, spread ≤ ${num(d.policy.max_spread_pct_mid,0)}%, OI ≥ ${esc(d.policy.min_open_interest)}, expiry beyond q80, and at least ${num(d.policy.min_target_runway_after_trigger*100,0)}% of the modelled price move remains beyond the trigger. These are unvalidated research filters, not trading gates. Entry-ready rows retain the published gate regardless of this payoff threshold.</p></div>
<h3>Waiting for trigger · ${(g.waiting||[]).length}</h3><p class="muted">Early-warning research only. No accepted trigger; geometry/hit-rate evidence may be unmeasured. Recheck price, IV and runway after confirmation.</p>${table(g.waiting||[])}
<h3>Entry-ready in saved gate · human review / sizing only · ${(g.entry_ready||[]).length}</h3><p class="muted">Confirmed published GO/GO_LIMIT gate and justified geometry. Not automatic execution or capital authorisation; not necessarily high-convexity.</p>${table(g.entry_ready||[])}
<details><summary>Other review-only setups · ${(g.review_only||[]).length}</summary><p class="muted">Readiness alone does not override geometry or permission restrictions.</p>${table(g.review_only||[])}</details>
<details><summary>Excluded comparisons & screening reasons · ${d.exclusions.length}</summary><ul>${d.exclusions.map(r=>`<li>${esc(r.ticker)}: ${r.reasons.map(esc).join(' · ')}</li>`).join('')}</ul></details>
<details><summary>Method and limitations</summary><ul>${d.disclosures.map(v=>`<li>${esc(v)}</li>`).join('')}</ul><p class="muted">Sorted within each section by combined-stress return, then target return; published Lab ranks, decisions and source records are unchanged.</p></details>`;
}catch(error){if(ticket===sequence){$('convexity-content').replaceChildren();$('convexity-status').textContent=`Saved watchlist unavailable: ${error.message}. No fallback, provider call or automatic rebuild was started.`}}
finally{clearTimeout(timer);if(ticket===sequence)$('convexity-load').disabled=false}}
$('convexity-load').addEventListener('click',load);
$('convexity-content').addEventListener('click',e=>{const b=e.target.closest('[data-convexity-row]');if(b)window.dispatchEvent(new CustomEvent('lab-convexity-select',{detail:{rowKey:b.dataset.convexityRow,run,revision}}))});
})();
