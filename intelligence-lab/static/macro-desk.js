(()=>{'use strict';
const $=id=>document.getElementById(id),esc=v=>String(v??'Not recorded').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let busy=false;
async function load(){if(busy)return;busy=true;const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
try{const response=await fetch('/api/lab/macro-context',{cache:'no-store',signal:controller.signal});const data=await response.json();if(!response.ok)throw Error(data.reason||data.state);
$('status').textContent=`${data.freshness} · ${data.publication_age_hours} hours since board build. Source dates may be older.`;
$('identity').textContent=`Session ${data.as_of_session} · Board built ${data.built_at_utc} · ${data.build_kind||'kind not recorded'} · Macro revision ${data.revision.slice(0,12)} · Trade-book revision unchanged`;
$('evidence').innerHTML=data.evidence.map(e=>`<div><strong>${esc(e.id.replaceAll('_',' '))}</strong><br>${esc(e.state)}</div>`).join('');
$('scenarios').innerHTML=data.scenarios.map(s=>`<article><h3>${esc(s.title)}</h3><p class="muted">Conditional inference · evidence: ${esc(s.evidence_ids.join(', '))}</p><p>${esc(s.interpretation)}</p><dl><dt>Would confirm</dt><dd>${esc(s.confirmation)}</dd><dt>Would invalidate</dt><dd>${esc(s.invalidation)}</dd><dt>Implication for thesis review</dt><dd>${esc(s.thesis_implication)}</dd></dl></article>`).join('')||'<p>No supported scenario rule matches the published conditions. Review the evidence; no scenario has been invented.</p>';
$('limits').innerHTML=[...(data.source_issues||[]),...data.limitations].map(v=>`<li>${esc(v)}</li>`).join('');$('sources').textContent=JSON.stringify({evidence:data.evidence,observations:data.source_observations,source_quality_at_build:data.source_quality},null,2);
}catch(error){$('status').textContent=`Macro context unavailable: ${error.message}. No fallback or pipeline run was started.`;$('evidence').innerHTML='';$('scenarios').innerHTML='';$('identity').textContent='';$('limits').innerHTML='';$('sources').textContent='';}
finally{clearTimeout(timer);busy=false;}}
$('refresh').addEventListener('click',load);load();setInterval(()=>{if(!document.hidden)load()},60000);
})();
