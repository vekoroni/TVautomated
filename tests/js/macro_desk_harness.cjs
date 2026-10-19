// Pure renderer unit harness. No browser interaction or provider access.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const elements={};const element=id=>elements[id]??=({innerHTML:'',textContent:'',disabled:false,events:{},addEventListener(name,fn){this.events[name]=fn}});
let documentData=JSON.parse(fs.readFileSync(process.argv[2],'utf8')),fail=false,calls=0,interval;
const context={document:{getElementById:element,hidden:false},location:{search:''},URLSearchParams,AbortController,setTimeout,clearTimeout,
setInterval(fn,ms){assert.equal(ms,60000);interval=fn},
fetch:async url=>{assert.equal(url,'/api/lab/macro-context');calls++;return{ok:!fail,json:async()=>fail?{reason:'test failure'}:{...documentData,freshness:'TEST',publication_age_hours:1}}}};
vm.runInNewContext(fs.readFileSync('intelligence-lab/static/macro-desk.js','utf8'),context);
const settle=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
await settle();assert.equal(calls,1);assert(elements.axes.innerHTML.includes('Supporting observations'));
assert(elements.evidence.innerHTML.includes('credit'));assert(elements.summary.textContent);
assert(elements.axes.innerHTML.includes('positioning'));assert.equal(elements.refresh.disabled,false);
const original=elements.identity.textContent;documentData={...documentData,revision:'NEWREVISION123456'};
await elements.refresh.events.click();assert.notEqual(elements.identity.textContent,original);
documentData.mentality.axes.confidence.interpretation='<img src=x onerror=evil()>';
interval();await settle();assert(!elements.axes.innerHTML.includes('<img'));assert(elements.axes.innerHTML.includes('&lt;img'));
context.document.hidden=true;const prior=calls;interval();await settle();assert.equal(calls,prior);
context.document.hidden=false;fail=true;interval();await settle();
for(const id of ['axes','summary','evidence','attempts','changes','sensitivities'])assert.equal(elements[id].innerHTML,'');
assert(elements.status.textContent.includes('unavailable'));assert.equal(elements.refresh.disabled,false);
console.log('PASS: mentality renderer, evidence links, unknown positioning, refresh, visible-only 60-second polling, XSS escaping, failure clearing');
})().catch(error=>{console.error(error);process.exitCode=1});
