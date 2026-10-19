(()=>{
'use strict';
const $=id=>document.getElementById(id);
const esc=value=>String(value??'Not recorded').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const human=value=>String(value||'Not recorded').replaceAll('_',' ').toLowerCase();
const pinned=new URLSearchParams(location.search).get('revision');
const sections=['summary','basis','axes','behaviours','changes','attempts','sensitivities','evidence','limits','sources','identity'];
let busy=false;
const refs=ids=>(ids||[]).map(id=>'<a href="#evidence-'+encodeURIComponent(id)+'">'+esc(id)+'</a>').join(' ');
function claim(item,title){
  return '<article><span class="eyebrow">INFERENCE / '+esc(title)+'</span><h3>'+esc(human(item.label))+'</h3><p>'+esc(item.interpretation)+'</p><dl>'+
    '<dt>Supporting observations</dt><dd class="evidence-links">'+(refs(item.supporting_evidence_ids)||'Insufficient evidence')+'</dd>'+
    '<dt>Contrary / qualifying observations</dt><dd class="evidence-links">'+(refs(item.contrary_evidence_ids)||'None identified by this rule; not proof none exist.')+'</dd>'+
    (item.missing_inputs.length?'<dt>Unresolved evidence</dt><dd>'+esc(item.missing_inputs.join(' · '))+'</dd>':'')+
    (item.would_change_view?'<dt>What would change this view?</dt><dd>'+esc(item.would_change_view)+'</dd>':'')+'</dl></article>';
}
function valueText(value){return value===null||value===undefined?'Not recorded':typeof value==='object'?JSON.stringify(value):String(value)}
async function load(){
  if(busy)return;busy=true;$('refresh').disabled=true;
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
  try{
    const response=await fetch('/api/lab/macro-context'+(pinned?'?revision='+encodeURIComponent(pinned):''),{cache:'no-store',signal:controller.signal});
    const data=await response.json();
    if(!response.ok)throw Error(data.reason||data.state);
    if(data.schema_version!=='lab_market_mentality_v2')throw Error('Market Mentality publication requires an update.');
    const mentality=data.mentality;
    $('status').textContent=(pinned?'Archived assessment · ':'Latest published assessment · ')+data.freshness+' · '+data.publication_age_hours+' hours since board build. Observations are saved, not live.';
    $('identity').textContent='Cash session '+data.as_of_session+' · Board built '+data.built_at_utc+' · Interpretation published '+data.published_at_utc+' · Revision '+data.revision.slice(0,12);
    $('headline').textContent=mentality.headline;$('summary').textContent=mentality.summary;
    $('basis').textContent=human(mentality.evidence_basis)+' · '+data.calculation_version+' · Proxy agreement is not certainty about motives.';
    $('method').textContent=data.methodology.explanation+' Daily floor: '+data.methodology.daily_return_floor_pct+'%; five-session floor: '+data.methodology.five_session_return_floor_pct+'%.';
    const titles={confidence:'Confidence / willingness to participate',fear:'Fear / concern',directional_progress:'Directional progress',urgency:'Trading urgency',positioning:'Actual positioning'};
    $('axes').innerHTML=Object.entries(mentality.axes).map(([key,item])=>claim(item,titles[key])).join('');
    $('behaviours').innerHTML=mentality.behaviours.map(item=>'<div class="behaviour-item"><p>'+esc(item.interpretation)+'</p><p class="evidence-links">'+refs(item.supporting_evidence_ids)+'</p><p class="muted">Would change the view: '+esc(item.would_change_view)+'</p></div>').join('')||'<p>No additional behavioural inference is supported. Missing evidence has not been filled.</p>';
    $('changes').innerHTML='<p>'+esc(data.changes.summary)+'</p>'+
      (data.changes.previous_revision?'<p><a href="/market-mentality?revision='+encodeURIComponent(data.changes.previous_revision)+'">Previous archived assessment</a> · '+esc(data.changes.previous_session)+'</p>':'')+
      data.changes.items.map(item=>'<div class="change-item"><strong>'+esc(item.evidence_id)+'</strong><p>'+esc(valueText(item.before.state))+' / '+esc(valueText(item.before.value))+' → '+esc(valueText(item.after.state))+' / '+esc(valueText(item.after.value))+'</p></div>').join('');
    $('attempts').innerHTML=mentality.attempt_response.map(item=>'<article><span class="eyebrow">DAILY PRICE OBSERVATION / '+esc(item.instrument)+'</span><dl><dt>Attempt</dt><dd>'+esc(item.attempt)+'</dd><dt>Response</dt><dd>'+esc(item.response)+'</dd><dt>Possible crowd consequence · inference</dt><dd>'+esc(item.possible_consequence)+'</dd><dt>What would change this reading?</dt><dd>'+esc(item.changes_interpretation)+'</dd></dl><p class="muted">'+esc(item.limit)+'</p><p class="evidence-links">'+refs(item.evidence_ids)+'</p></article>').join('')||'<p>No supported opening-attempt / response pattern is available. Intraday acceptance and failed expectations remain unverified.</p>';
    $('sensitivities').innerHTML=mentality.reaction_sensitivities.map(item=>'<article><h3>'+esc(item.title)+'</h3><dl><dt>Observable evidence to watch</dt><dd>'+esc(item.watch_for)+'</dd><dt>Possible change in mentality</dt><dd>'+esc(item.possible_reaction)+'</dd><dt>What would challenge it?</dt><dd>'+esc(item.would_challenge)+'</dd></dl><p class="muted">'+esc(item.testability)+'</p><p class="evidence-links">'+refs(item.evidence_ids)+'</p></article>').join('')||'<p>No reaction sensitivity is inferred without an evidence basis.</p>';
    $('evidence').innerHTML=data.evidence.map(item=>'<article id="evidence-'+esc(item.id)+'" class="'+(item.usable?'':'excluded')+'"><span class="eyebrow">'+(item.usable?'OBSERVED / CLASSIFIED':'EXCLUDED INPUT')+'</span><h3>'+esc(item.label)+'</h3><p>'+esc(item.state)+' · '+esc(valueText(item.value))+(item.unit?' '+esc(item.unit):'')+'</p><p>'+esc(item.definition)+'</p><p class="muted">'+esc(item.source)+' · '+esc(JSON.stringify(item.observation))+'</p>'+(item.exclusion?'<p>'+esc(item.exclusion)+'</p>':'')+'</article>').join('');
    $('limits').innerHTML=[...data.source_issues,...data.limitations].map(value=>'<li>'+esc(value)+'</li>').join('');
    $('sources').textContent=JSON.stringify({revision:data.revision,source_revision:data.source_revision,calculation_version:data.calculation_version,market_session:data.as_of_session,board_built_at_utc:data.built_at_utc,interpretation_published_at_utc:data.published_at_utc,source_quality_at_build:data.source_quality},null,2);
  }catch(error){
    $('status').textContent='Market Mentality unavailable: '+error.message+'. No fallback, provider call or pipeline run was started.';
    $('headline').textContent='Assessment unavailable';
    [...sections,'method'].forEach(id=>{$(id).innerHTML='';$(id).textContent=''});
  }finally{clearTimeout(timer);busy=false;$('refresh').disabled=false}
}
$('refresh').addEventListener('click',load);
load();
if(!pinned)setInterval(()=>{if(!document.hidden)load()},60000);
})();
