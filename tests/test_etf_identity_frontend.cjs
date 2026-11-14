const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..'),context={window:{}};
vm.runInNewContext(fs.readFileSync(path.join(root,'intelligence-lab/static/instrument-identity.js'),'utf8'),context);
const render=context.window.LabInstrumentIdentity.render;
const fields={instrument_type:'LEVERAGED_VOL_ETF',instrument_identity_state:'REVIEW_REQUIRED',
 instrument_review_policy:'RESEARCH_ONLY',instrument_identity_source:'<saved>',instrument_inverse:false};
const frozen=JSON.stringify(fields),html=render(fields);
for(const text of ['LEVERAGED_VOL_ETF','RESEARCH_ONLY','REVIEW_REQUIRED','&lt;saved&gt;',
 'Not recorded / No / Not recorded','Unknown is not unleveraged','canonical rank'])assert.ok(html.includes(text),text);
assert.equal(JSON.stringify(fields),frozen);
assert.ok(render({instrument_type:'NAN'}).includes('<dd>NAN</dd>'));
assert.ok(render({}).includes('Not recorded'));
const app=fs.readFileSync(path.join(root,'intelligence-lab/static/review-app.js'),'utf8');
assert.ok(app.includes('window.LabInstrumentIdentity.render(f)'));
const page=fs.readFileSync(path.join(root,'intelligence-lab/static/review.html'),'utf8');
assert.ok(page.indexOf('/static/instrument-identity.js')<page.indexOf('/static/review-app.js'));
console.log('PASS: saved identity display, uncertainty, research policy, escaping, no mutation, wiring');
