// Pure unit harness, not browser automation. Exercise actual renderer and refresh.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const elements={};const element=id=>elements[id]??=( {innerHTML:'',textContent:'',events:{},addEventListener(name,fn){this.events[name]=fn}} );
let documentData=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),fail=false,calls=0,interval;
const context={document:{getElementById:element,hidden:false},AbortController,setTimeout,clearTimeout,
  setInterval(fn){interval=fn},fetch:async url=>{assert.equal(url,'/api/lab/macro-context');calls++;return {ok:!fail,json:async()=>fail?{reason:'test failure'}:{...documentData,freshness:'TEST',publication_age_hours:1}}}};
vm.runInNewContext(fs.readFileSync('intelligence-lab/static/macro-desk.js','utf8'),context);
const settle=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{await settle();assert.equal(calls,1);assert(elements.scenarios.innerHTML.includes('Would confirm'));assert(elements.evidence.innerHTML.includes('credit'));
  const original=elements.identity.textContent;documentData={...documentData,revision:'NEWREVISION123456'};
  await elements.refresh.events.click();assert.notEqual(elements.identity.textContent,original);
  documentData={...documentData,scenarios:[{title:'<img src=x onerror=evil()>',evidence_ids:['credit'],interpretation:'test',confirmation:'test',invalidation:'test',thesis_implication:'test'}]};
  interval();await settle();assert(!elements.scenarios.innerHTML.includes('<img'));assert(elements.scenarios.innerHTML.includes('&lt;img'));
  fail=true;interval();await settle();assert.equal(elements.scenarios.innerHTML,'');assert(elements.status.textContent.includes('unavailable'));assert(elements.status.textContent.includes('No fallback'));
  console.log('PASS: initial render, evidence/scenario content, refresh, poll, XSS escaping, failure clears stale content');
})().catch(error=>{console.error(error);process.exitCode=1});
