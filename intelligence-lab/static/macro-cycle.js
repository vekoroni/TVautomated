/* One saved advisory narrative renderer shared by Lab and self-contained ETF board. */
(()=>{'use strict';
const esc=v=>String(v??'MISSING').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const keys=['what_changed','transmission','house_view','wrong_worlds','central_bank_vs_price','forced_flows','confirmation_divergence','etf_book','what_changes_our_mind'];
const text=v=>v==null?'MISSING — not supplied':typeof v==='object'?JSON.stringify(v,null,2):String(v);
function render(host,b){
 if(!host)return;
 host.innerHTML='';
 if(!b){host.innerHTML='<h2>Macro operating cycle</h2><p>No canonical narrative attached to this archived build. Legacy descriptive evidence only; no new house view is implied.</p>';return}
 const n=b.narrative;
 if(b.authority!=='ADVISORY_ONLY'||n?.authority!=='ADVISORY_ONLY'||b.narrative_id!==n.narrative_id||b.status!==n.status||JSON.stringify((n.sections||[]).map(s=>s.key))!==JSON.stringify(keys))throw Error('Macro narrative binding invalid');
 const drivers=Object.entries(n.driver_readings||{}).map(([k,r])=>'<tr><td>'+esc(k)+'</td><td>'+esc(r.state)+'</td><td>'+esc(r.status)+'<br>'+esc(r.evidence_status)+'</td><td>'+esc(r.freshness?.status)+' · '+esc(r.freshness?.oldest_observation_date)+'<br>'+esc(r.age_days)+' days</td></tr>').join('');
 let html='<h2>Macro operating cycle · canonical advisory record</h2><p><strong>'+esc(n.status)+'</strong> · ADVISORY ONLY — no ticker score, veto, contract or execution authority.</p>'+
 '<p><strong>Approval: '+esc(n.governance?.approval_state||'LEGACY — NOT ASSERTED')+'</strong> · evidence: '+esc(n.governance?.evidence_completeness||'UNASSESSED')+' · option valuation: '+esc(n.governance?.valuation_readiness||'UNASSESSED')+'</p>'+
 '<p>Reference close '+esc(n.as_of_session)+' · information cutoff '+esc(n.information_cutoff_utc)+' · '+esc(n.calc_version)+'</p>'+
 '<p>Narrative <code>'+esc(n.narrative_id)+'</code><br>SHA-256 <code>'+esc(b.narrative_sha256)+'</code></p>'+
 '<p>Accepted feeds → analysis → narrative: <strong>'+esc(b.feed_chain?.status||'UNASSESSED')+'</strong></p>'+
 (n.status==='INCOMPLETE_AUTHORED_INPUT'?'<p role="status"><strong>Authored house view, probabilities or ETF world marks remain incomplete. Missing is not neutral; no calls were invented.</strong></p>':'')+
 '<p>Other board tables and crowd-proxy observations are supporting descriptive views, not another house narrative.</p>'+
 '<table><thead><tr><th>Driver</th><th>Reading</th><th>Evidence / limits</th><th>Freshness at use</th></tr></thead><tbody>'+drivers+'</tbody></table>';
 n.sections.forEach((s,i)=>{
  let content;
  if(s.key==='house_view'){content='<p>'+esc(s.data.statement||'MISSING — no authored house view')+'</p><p>Authored probability: '+(s.data.probability==null?'MISSING':esc((s.data.probability*100).toFixed(1))+'% — judgement, not measured')+'</p>'}
  else if(s.data?.status==='MISSING'){content='<p>MISSING — '+esc(s.data.reason||'Awaiting authored input')+'</p>'}
  else content='<pre style="white-space:pre-wrap;overflow-wrap:anywhere;max-height:32rem;overflow:auto">'+esc(text(s.data))+'</pre>';
  html+='<details><summary><strong>'+(i+1)+'. '+esc(s.key.replaceAll('_',' '))+'</strong></summary>'+content+'</details>';
 });
 html+='<details><summary>Research governance, separate clocks, event forecasts and market scenarios</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(text({clocks:n.clocks,governance:n.governance}))+'</pre></details>'+
 '<details><summary>Tripwires — advisory alerts, not event resolution or trade instructions</summary><pre style="white-space:pre-wrap">'+esc(text(n.tripwire_observations||[]))+'</pre></details>'+
 '<details><summary>Input hashes, sources and limitations</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(text({feed_chain:b.feed_chain,input_manifest:n.input_manifest,limitations:n.limitations}))+'</pre></details>';
 host.innerHTML=html;
}
globalThis.MacroCycleView={render};
})();
