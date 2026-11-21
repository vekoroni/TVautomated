const test=require('node:test');
const assert=require('node:assert/strict');
const live=require('../intelligence-lab/static/review-live.js');

function fixture({state={},summary={run_id:'NEW',revision:'r2'},fail=false}={}){
  let current={run:'OLD',revision:'r1',token:1,followLatest:true,...state};
  const calls=[],applied=[],errors=[];
  const follower=live.createFollower({
    request:async url=>{calls.push(url);if(url==='/api/runs')return {runs:['NEW','OLD'],published_review_runs:['NEW','OLD'],latest_review_run:'OLD'};if(fail)throw new Error('publication pending');return summary;},
    current:()=>current,updateRuns:()=>{},apply:async id=>applied.push(id),onError:e=>errors.push(e.message),
  });
  return {follower,calls,applied,errors,set:value=>Object.assign(current,value)};
}
test('newest completed publication wins over an older Morning-validated run',async()=>{
  const f=fixture();await f.follower.poll();assert.deepEqual(f.applied,['NEW']);
});
test('same run is refreshed when its publication revision changes',async()=>{
  const f=fixture({state:{run:'NEW'}});await f.follower.poll();assert.deepEqual(f.applied,['NEW']);
});
test('unchanged revision does not reset a user view',async()=>{
  const f=fixture({state:{run:'NEW',revision:'r2'}});await f.follower.poll();assert.deepEqual(f.applied,[]);
});
test('historical run selection is retained when following is off',async()=>{
  const f=fixture({state:{followLatest:false},summary:{run_id:'OLD',revision:'r1'}});
  await f.follower.poll();assert.deepEqual(f.applied,[]);assert.equal(f.calls[1],'/api/lab/OLD/summary');
});
test('stale or incomplete publication does not replace displayed data',async()=>{
  const f=fixture({fail:true});await f.follower.poll();assert.deepEqual(f.applied,[]);assert.equal(f.errors.length,1);
});
test('a failed check is retried successfully on the next poll',async()=>{
  let attempts=0,applied=0;
  const f=live.createFollower({request:async url=>{if(url==='/api/runs')return {published_review_runs:['NEW']};if(++attempts===1)throw Error('temporary');return {run_id:'NEW',revision:'r2'};},
    current:()=>({run:'OLD',revision:'r1',token:1,followLatest:true}),updateRuns:()=>{},apply:async()=>applied++,onError:()=>{}});
  await f.poll();await f.poll();assert.equal(applied,1);
});
test('manual selection during an in-flight check cannot be overwritten',async()=>{
  let release,current={run:'OLD',revision:'r1',token:1,followLatest:true},applied=0;
  const f=live.createFollower({request:()=>new Promise(resolve=>release=resolve),current:()=>current,
    updateRuns:()=>{},apply:async()=>applied++,onError:()=>{}});
  const running=f.poll();current={...current,token:2,followLatest:false};release({published_review_runs:['NEW']});
  await running;assert.equal(applied,0);
});
test('polls never overlap',async()=>{
  let calls=0,release;
  const f=live.createFollower({request:()=>{calls++;return new Promise(resolve=>release=resolve);},
    current:()=>({token:1,followLatest:true}),updateRuns:()=>{},apply:async()=>{},onError:()=>{}});
  const running=f.poll();await f.poll();assert.equal(calls,1);release({});await running;
});
test('missing context is reloaded even when the revision is unchanged',async()=>{
  const f=fixture({state:{run:'NEW',revision:'r2',ready:false}});await f.follower.poll();assert.deepEqual(f.applied,['NEW']);
});
function page(rows,total=rows.length,revision='pin'){
  return {run_id:'RUN',revision,total_rows:total,filtered_rows:total,rows};
}
test('export includes all pages and deduplicates ticker theses',async()=>{
  const rows=Array.from({length:205},(_,i)=>({row_key:String(i+1),ticker:i===204?'t0':`T${i}`}));
  const urls=[];const result=await live.allTickers(async url=>{urls.push(url);return page(url.includes('page=1&')?rows.slice(0,200):rows.slice(200),205);},'RUN','pin');
  assert.equal(result.total_rows,205);assert.equal(result.tickers.length,204);assert.ok(result.tickers.includes('T203'));
  assert.equal(urls.length,2);assert.ok(urls.every(u=>u.includes('revision=pin')&&!u.includes('sector=')));
});
test('an empty published book exports an empty list without looping',async()=>{
  assert.deepEqual((await live.allTickers(async()=>page([]),'RUN','pin')).tickers,[]);
});
test('export refuses mixed revisions',async()=>{
  await assert.rejects(live.allTickers(async()=>page([],0,'other'),'RUN','pin'),/changed/);
});
test('export refuses repeated pages rather than returning an incomplete ticker list',async()=>{
  await assert.rejects(live.allTickers(async()=>page([{row_key:'one',ticker:'A'}],2),'RUN','pin'),/row identity/);
});
test('export refuses filtered response, absent ticker, and disappearing rows',async()=>{
  await assert.rejects(live.allTickers(async()=>({...page([],2),filtered_rows:1}),'RUN','pin'),/all-run/);
  await assert.rejects(live.allTickers(async()=>page([{row_key:'one',ticker:''}]),'RUN','pin'),/no ticker/);
  await assert.rejects(live.allTickers(async()=>page([],2),'RUN','pin'),/counts/);
});
test('CSV preserves ticker punctuation and quotes while protecting formula prefixes',()=>{
  assert.equal(live.tickerCSV(['BRK.B','NAN','A"B','=1+1']),'ticker\r\n"BRK.B"\r\n"NAN"\r\n"A""B"\r\n"\'=1+1"\r\n');
});
