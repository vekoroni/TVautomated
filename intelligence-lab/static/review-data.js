/* Explicit, saved-data-only filtering and attribute export. */
(function(){
'use strict';
const $=id=>document.getElementById(id), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let dataset=null, matches=[],fields=[],filters=[];
function renderFilters(){
 $('data-conditions').innerHTML=filters.map((filter,i)=>`<div class="data-condition"><label>Attribute <select data-index="${i}" data-key="field">${fields.map(k=>`<option value="${esc(k)}" ${k===filter.field?'selected':''}>${esc(k)}</option>`).join('')}</select></label> <label>Condition <select data-index="${i}" data-key="operator">${[['contains','contains'],['equals','equals'],['gte','at least (number)'],['lte','at most (number)']].map(([key,label])=>`<option value="${key}" ${key===filter.operator?'selected':''}>${label}</option>`).join('')}</select></label> <label>Value <input type="text" data-index="${i}" data-key="value" value="${esc(filter.value)}"></label> <button type="button" data-remove="${i}">Remove condition</button></div>`).join('');
}
function matchCondition(row,filter){const input=filter.value.trim();if(!input)return true;const value=row[filter.field];if(value===null||value===undefined||value==='')return false;if(filter.operator==='contains')return String(value).toLowerCase().includes(input.toLowerCase());if(filter.operator==='equals')return String(value).toLowerCase()===input.toLowerCase();const n=Number(value),limit=Number(input);return Number.isFinite(n)&&Number.isFinite(limit)&&(filter.operator==='gte'?n>=limit:n<=limit);}

const state=message=>$('data-status').textContent=message;
async function request(url){const response=await fetch(url,{cache:'no-store'});const data=await response.json();if(!response.ok)throw Error(data.error?.message||data.message||'Saved review unavailable');return data;}
function current(){return $('review-run').value;}
function draw(){
 const active=filters.filter(f=>f.value.trim());
 if(active.some(f=>['gte','lte'].includes(f.operator)&&!Number.isFinite(Number(f.value.trim())))){$('data-download').disabled=true;state('Enter a valid number for each numeric condition.');return;}
 matches=dataset.rows.filter(row=>active.every(filter=>matchCondition(row,filter)));
 const columns=[...new Set(['ticker','sector','direction','thesis__readiness','lab_verdict','lab_rank','anticipated_move_pct','anticipated_sessions_q50',...active.map(f=>f.field)])];
 $('data-preview').innerHTML='<table><thead><tr>'+columns.map(k=>'<th>'+esc(k)+'</th>').join('')+'</tr></thead><tbody>'+matches.slice(0,100).map(r=>'<tr>'+columns.map(k=>'<td>'+esc(r[k])+'</td>').join('')+'</tr>').join('')+'</tbody></table>';
 state(`${matches.length} matching / ${dataset.rows.length} published rows · ${fields.length} attributes · run ${dataset.run_id}. Preview shows up to 100; CSV includes every match.`);
 $('data-download').disabled=false;
}
$('data-load').addEventListener('click',async()=>{const selected=current();$('data-load').disabled=true;$('data-download').disabled=true;try{state('Loading all saved review pages…');const summary=await request(`/api/lab/${encodeURIComponent(selected)}/summary`);const data=await window.LabReviewLive.allRows(request,selected,summary.revision,(done,total)=>state(`Loading saved attributes: ${done}/${total} rows…`));if(current()!==selected)throw Error('Run changed; load the selected run again');dataset={...data,rows:data.rows.map(row=>window.LabReviewLive.flattenRow({...row,export_run_id:selected,export_revision:summary.revision}))};fields=[...new Set(dataset.rows.flatMap(Object.keys))];filters=['sector','direction','thesis__readiness','anticipated_move_pct'].filter(field=>fields.includes(field)).map(field=>({field,operator:field==='anticipated_move_pct'?'gte':'equals',value:''}));renderFilters();$('data-filter').hidden=false;draw();}catch(e){dataset=null;state(e.message);}finally{$('data-load').disabled=false;}});
$('data-conditions').addEventListener('input',event=>{const {index,key}=event.target.dataset;if(key&&filters[index]){filters[index][key]=event.target.value;$('data-download').disabled=true;state('Conditions changed. Apply filters to update the preview and export.');}});
$('data-conditions').addEventListener('change',event=>{const {index,key}=event.target.dataset;if(key&&filters[index]){filters[index][key]=event.target.value;$('data-download').disabled=true;}});
$('data-conditions').addEventListener('click',event=>{const index=event.target.dataset.remove;if(index!==undefined){filters.splice(Number(index),1);renderFilters();if(dataset)draw();}});
$('data-add').addEventListener('click',()=>{filters.push({field:fields[0]||'ticker',operator:'contains',value:''});renderFilters();});
$('data-apply').addEventListener('click',()=>{if(dataset)draw();});
$('data-clear').addEventListener('click',()=>{filters=[];renderFilters();if(dataset)draw();});
$('data-download').addEventListener('click',()=>{if(!dataset||current()!==dataset.run_id){state('Run changed; load the selected run again before exporting.');return;}const blob=new Blob([window.LabReviewLive.rowsCSV(matches,fields)],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`lab_attributes_${dataset.run_id}_${dataset.revision.slice(0,10)}.csv`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);state(`Downloaded ${matches.length} rows with ${fields.length} attributes from run ${dataset.run_id}.`);});
})();
