/* Display-only run following and revision-pinned ticker extraction. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.LabReviewLive=api;})(globalThis,function(){
'use strict';
function latestPublished(data){return data.published_review_runs?.[0]||data.latest_review_run||null;}
function createFollower({request,current,updateRuns,apply,onError}){
  let pending=false;
  async function poll(){
    if(pending||current().loading)return;
    pending=true;
    const start=current();
    const unchanged=()=>{const now=current();return now.token===start.token&&now.followLatest===start.followLatest;};
    try{
      const data=await request('/api/runs',{cache:'no-store'});
      if(!unchanged())return;
      updateRuns(data.runs||[]);
      const target=start.followLatest?latestPublished(data):start.run;
      if(!target)return;
      // Check that the publication is actually readable before replacing a view.
      const saved=await request(`/api/lab/${encodeURIComponent(target)}/summary`,{cache:'no-store'});
      if(!unchanged())return;
      if(saved.run_id!==target||!saved.revision)throw new Error('Published review identity is missing');
      if(target!==start.run||saved.revision!==start.revision||start.ready===false)await apply(target,saved);
    }catch(error){if(unchanged())onError(error);}
    finally{pending=false;}
  }
  return {poll};
}
async function allRows(request,run,revision,onProgress=()=>{}){
  if(!run||!revision)throw new Error('Wait for a published run to load');
  const rows=[],rowKeys=new Set();
  let total=null,read=0,page=1;
  do{
    const data=await request(`/api/lab/${encodeURIComponent(run)}/rows?page=${page}&page_size=200&revision=${encodeURIComponent(revision)}`,{cache:'no-store'});
    if(data.run_id!==run||data.revision!==revision)throw new Error('Review changed during export; retry with the current run');
    if(!Number.isInteger(data.total_rows)||data.total_rows<0||data.filtered_rows!==data.total_rows||!Array.isArray(data.rows))throw new Error('Incomplete all-run export response');
    if(total===null)total=data.total_rows;
    if(data.total_rows!==total||(!data.rows.length&&read<total))throw new Error('Review row counts changed during export');
    for(const row of data.rows){
      if(!row.row_key||rowKeys.has(row.row_key))throw new Error('Review paging repeated or omitted a row identity');
      rowKeys.add(row.row_key);
      const ticker=String(row.ticker??'').trim().toUpperCase();
      if(!ticker)throw new Error('Published row has no ticker; export needs review');
      rows.push(row);
    }
    read+=data.rows.length;
    if(read>total)throw new Error('Review paging exceeded the published row count');
    onProgress(read,total);page++;
  }while(read<total);
  return {run_id:run,revision,total_rows:total,rows};
}
async function allTickers(request,run,revision,onProgress){const data=await allRows(request,run,revision,onProgress);return {...data,rows:undefined,tickers:[...new Set(data.rows.map(r=>String(r.ticker).trim().toUpperCase()))]};}
function flattenRow(row,prefix='',out={}){for(const [key,value] of Object.entries(row)){const name=prefix?prefix+'.'+key:key;if(value&&typeof value==='object'&&!Array.isArray(value))flattenRow(value,name,out);else out[name]=Array.isArray(value)?JSON.stringify(value):value;}return out;}
function rowsCSV(rows,fields){fields=fields||[...new Set(rows.flatMap(Object.keys))];const cell=value=>{let s=value==null?'':String(value);if(typeof value!=='number'&&/^[=+\-@\t\r]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};return '\uFEFF'+[fields.map(cell).join(','),...rows.map(r=>fields.map(k=>cell(r[k])).join(','))].join('\r\n')+'\r\n';}
function tickerCSV(tickers){return 'ticker\r\n'+tickers.map(t=>{
  const value=/^[=+\-@\t\r]/.test(t)?"'"+t:t;
  return '"'+value.replaceAll('"','""')+'"';
}).join('\r\n')+(tickers.length?'\r\n':'');}
return {latestPublished,createFollower,allRows,allTickers,tickerCSV,flattenRow,rowsCSV};
});
