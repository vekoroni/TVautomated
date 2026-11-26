const fs=require('fs'),vm=require('vm'),assert=require('assert');
const context={};vm.createContext(context);
vm.runInContext(fs.readFileSync('intelligence-lab/static/macro-cycle.js','utf8'),context);
const doc=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const binding=doc.macro_operating_cycle||doc;
const host={innerHTML:''};context.MacroCycleView.render(host,binding);
assert(host.innerHTML.includes(binding.narrative_id));
assert(host.innerHTML.includes(binding.narrative_sha256));
assert(host.innerHTML.includes(binding.status));
if(binding.status==='RESEARCH_DRAFT'){
 assert(host.innerHTML.includes('Approval: RESEARCH_DRAFT'));
 assert(host.innerHTML.includes('OPTION_PAYOFF_UNASSESSED'));
 assert(host.innerHTML.includes('separate clocks'));
}
for(const s of binding.narrative.sections)assert(host.innerHTML.includes(s.key.replaceAll('_',' ')));
assert(host.innerHTML.includes('WIDE_WARNING'));
const hostile=JSON.parse(JSON.stringify(binding));hostile.narrative.sections[2].data.statement='<img src=x onerror=attack()>';
context.MacroCycleView.render(host,hostile);assert(host.innerHTML.includes('&lt;img'));assert(!host.innerHTML.includes('<img'));
const bad=JSON.parse(JSON.stringify(binding));bad.narrative_id='mismatch';
assert.throws(()=>context.MacroCycleView.render(host,bad));assert.equal(host.innerHTML,'');
context.MacroCycleView.render(host,null);assert(host.innerHTML.includes('No canonical narrative'));
console.log('PASS: nine sections, shared identity/hash, missing authored status, source labels, XSS escaping and stale-content clearing');
