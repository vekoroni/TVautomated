// Crossing scenario card section (AVS-TRADE-001 design v4): renders saved fields only, escapes them, never mutates
// its input, says what is missing, and is wired after the identity section.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..'),context={window:{}};
vm.runInNewContext(fs.readFileSync(path.join(root,'intelligence-lab/static/crossing-scenario.js'),'utf8'),context);
const render=context.window.LabCrossingScenario.render;
const fields={crossing_state:'CROSSES_COVERING',crossing_covers_slow30_base:'YES',crossing_n_slow_pace_30:7,
 crossing_n_median_pace_20:0,crossing_contract_symbol:'<AAA>',crossing_shadow_reason:'NO_COVERING_CANDIDATE',
 crossing_candidates_json:JSON.stringify({assessed:2,pool_scored:9,truncated_by_cap:1,candidates:[
  {symbol:'A<1>',role:'SHADOW',state:'CROSSES_COVERING',n_slow_pace_30:3,tier:'B',provenance:'ALIGNED',sessions_to_expiry:40,ask:1.2},
  {symbol:'B',role:'NOT_ELIGIBLE',state:'NOT_ASSESSED_EXIT_COST_UNKNOWN',n_slow_pace_30:null,tier:null,validity:'UNASSESSED_NO_BID',provenance:'PROVISIONAL'}]})};
const frozen=JSON.stringify(fields),html=render(fields);
for(const text of ['CROSSES_COVERING','session 7','session 0','&lt;AAA&gt;','A&lt;1&gt;','NO_COVERING_CANDIDATE',
 'UNASSESSED_NO_BID','no crossing recorded','2 assessed of 9 scored','not a forecast','Shadow only','Invalidation is not modelled'])
 assert.ok(html.includes(text),text);
assert.ok(!html.includes('<AAA>'));
assert.equal(JSON.stringify(fields),frozen);
const empty=render({});
assert.ok(empty.includes('Not recorded')&&empty.includes('no crossing recorded')&&!empty.includes('<table'));
assert.ok(!render({crossing_candidates_json:'{not json'}).includes('<table'));
const app=fs.readFileSync(path.join(root,'intelligence-lab/static/review-app.js'),'utf8');
assert.ok(app.includes('window.LabCrossingScenario.render(f)'));
assert.ok(app.includes('window.LabInstrumentIdentity.render(f)'));
const page=fs.readFileSync(path.join(root,'intelligence-lab/static/review.html'),'utf8');
assert.ok(page.indexOf('/static/instrument-identity.js')<page.indexOf('/static/crossing-scenario.js'));
assert.ok(page.indexOf('/static/crossing-scenario.js')<page.indexOf('/static/review-app.js'));
console.log('PASS: saved crossing scenario display, zero vs missing, escaping, no mutation, bad JSON, wiring');
