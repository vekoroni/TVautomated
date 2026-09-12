const WORKER3_SELECTED = new Set();
let WORKER3_BUSY = false;
let WORKER3_DISPLAY_VERSION = 0;
function updateWorker3Selection() {
  const b=document.getElementById('worker3-launch');
  b.textContent=`Worker 3: preview selected (${WORKER3_SELECTED.size}/5)`; b.disabled=WORKER3_BUSY;
  const clear=document.getElementById('worker3-clear');if(clear)clear.disabled=WORKER3_BUSY;
}
function clearWorker3Display() {
  if (WORKER3_BUSY) return;
  WORKER3_DISPLAY_VERSION++;
  WORKER3_SELECTED.clear();
  document.querySelectorAll('input[data-worker3-ticker]').forEach(input=>{input.checked=false;});
  localStorage.removeItem('worker3-last-batch');
  document.getElementById('worker3-status').textContent='';
  updateWorker3Selection();
}
function selectWorker3(input) {
  const ticker=input.dataset.worker3Ticker;
  if(input.checked && WORKER3_SELECTED.size>=5){input.checked=false;document.getElementById('worker3-status').textContent='Select at most five tickers.';return;}
  if(input.checked)WORKER3_SELECTED.add(ticker);else WORKER3_SELECTED.delete(ticker);
  updateWorker3Selection();
  if (!WORKER3_BUSY) {
    document.getElementById('worker3-status').textContent = WORKER3_SELECTED.size
      ? `Selected: ${[...WORKER3_SELECTED].join(', ')}. Click "Worker 3: preview selected" above to continue.`
      : 'Select one to five tickers using their checkboxes.';
  }
}
async function worker3Request(path,body,token) {
  const response=await fetch(`/api/worker3/${path}`,body?{method:'POST',headers:{'Content-Type':'application/json','X-Worker3-Token':token},body:JSON.stringify(body)}:{});
  if(response.status===404)throw new Error('Worker 3 browser controls are unavailable. Restart Intelligence Lab to load the updated server.');
  if(response.status===403)throw new Error('Open Intelligence Lab on localhost to launch Worker 3.');
  const data=await response.json();if(!response.ok)throw new Error(data.error||'Worker 3 request failed');return data;
}
async function previewWorker3() {
  if(WORKER3_BUSY)return;
  const status=document.getElementById('worker3-status'),tickers=[...WORKER3_SELECTED],run=RUN_DATA&&RUN_DATA.run_id;
  if(!tickers.length||tickers.length>5){status.textContent='Select one to five tickers using their checkboxes.';return;}
  if(!run){status.textContent='The displayed run has not loaded. Refresh the Lab, then select your tickers again.';return;}
  WORKER3_BUSY=true;updateWorker3Selection();let launched=false;
  try {
    status.textContent=`Counting tokens for ${tickers.join(', ')} in ${run}. No paid generation yet.`;
    const control=await worker3Request('control');if(control.report_profile!=='interpreter_detailed_v1')throw new Error('Restart Intelligence Lab to enable detailed reports before launching.');if(!control.enabled)throw new Error('Worker 3 release is disabled.');
    let previous_assessment_ids=null;
    const usePrior=document.getElementById('worker3-use-prior');
    if(usePrior&&usePrior.checked){
      const priorBatchId=localStorage.getItem('worker3-last-batch');
      if(!priorBatchId)throw new Error('No prior Worker 3 batch is available in this browser.');
      const priorBatch=await worker3Request('batch/'+encodeURIComponent(priorBatchId));
      previous_assessment_ids={};
      for(const ticker of tickers){
        const prior=priorBatch.results.find(row=>row.ticker===ticker&&row.assessment_id);
        if(!prior)throw new Error(`The prior batch has no completed assessment for ${ticker}.`);
        previous_assessment_ids[ticker]=prior.assessment_id;
      }
    }
    const preview=await worker3Request('preview',{run_id:run,tickers,previous_assessment_ids},control.token);
    const mode=previous_assessment_ids?'Morning/context refresh using the explicitly selected prior batch':'Initial assessment';
    const summary=`Mode: ${mode}\nRun: ${run}\nTickers: ${preview.entries.map(e=>e.ticker).join(', ')}\nConservative API cost bound: $${(preview.cost_bound_microusd/1e6).toFixed(4)}\nReserved ceiling: $${(preview.reserved_microusd/1e6).toFixed(2)} ($1 per ticker)\nProduction cumulative limit: $${(control.total_cap_microusd/1e6).toFixed(2)}\nNo automatic retries. Human review required.`;
    status.textContent=summary;if(RUN_DATA.run_id!==run)throw new Error('Displayed run changed. Create a fresh preview.');
    if(!window.confirm(summary+'\n\nConfirm launch and authorize these paid requests?'))return;
    const result=await worker3Request('launch',{batch_id:preview.batch_id},control.token);launched=true;
    localStorage.setItem('worker3-last-batch',result.batch_id);await pollWorker3(result.batch_id);
  }catch(error){status.textContent=error.message;}
  finally{if(!launched)WORKER3_BUSY=false;updateWorker3Selection();}
}
async function pollWorker3(batchId) {
  const displayVersion=WORKER3_DISPLAY_VERSION;
  const status=document.getElementById('worker3-status'),batch=await worker3Request('batch/'+encodeURIComponent(batchId));
  if(displayVersion!==WORKER3_DISPLAY_VERSION)return;
  status.textContent=`Worker 3 ${batch.state}: ${batch.tickers.join(', ')} — ${batch.results.length}/${batch.tickers.length} reports — run ${batch.run_id}`;
  const all=document.createElement('a');all.href=batch.batch_url||('/worker3/batch/'+encodeURIComponent(batchId));all.textContent='Open combined batch report (all selected tickers)';all.target='_blank';all.rel='noopener';status.appendChild(document.createElement('br'));status.appendChild(all);
  for(const result of batch.results){const line=document.createElement('div'),link=document.createElement('a');link.href=result.report_url;link.textContent=`${result.ticker}: ${result.semantic_status} — $${(result.cost_microusd/1e6).toFixed(4)} — open report`;link.target='_blank';link.rel='noopener';line.appendChild(link);status.appendChild(line);}
  if(batch.error)status.appendChild(document.createTextNode('\n'+batch.error));
  WORKER3_BUSY=batch.state==='RUNNING';updateWorker3Selection();
  if(WORKER3_BUSY)setTimeout(()=>pollWorker3(batchId).catch(e=>{status.textContent=e.message+'\nCheck the batch after reconnecting; do not resubmit.';WORKER3_BUSY=false;updateWorker3Selection();}),3000);
}
window.addEventListener('load',()=>{const clear=document.createElement('button');clear.id='worker3-clear';clear.className='fb';clear.textContent='Clear Worker 3 display';clear.title='Clear selections and displayed results. Saved reports and history remain available.';clear.onclick=clearWorker3Display;document.getElementById('worker3-launch').after(clear);updateWorker3Selection();const history=document.createElement('a');history.href='/worker3/batches';history.textContent='Worker 3 batch history';history.style.marginLeft='12px';document.getElementById('worker3-launch').after(history);const prior=document.createElement('label');prior.style.marginLeft='12px';prior.title='Compare current governed evidence with the matching assessments in the last completed browser batch.';prior.innerHTML='<input id="worker3-use-prior" type="checkbox"> Refresh from last batch';history.after(prior);const batch=localStorage.getItem('worker3-last-batch');if(batch)pollWorker3(batch).catch(()=>{});});
