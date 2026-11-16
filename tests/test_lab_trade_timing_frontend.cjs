const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const context={window:{}};
vm.runInNewContext(fs.readFileSync(path.join(root,'intelligence-lab/static/trade-timing.js'),'utf8'),context);
const render=context.window.LabTradeTiming.render;
const saved={anticipated_sessions_q50:22,anticipated_sessions_q80:52,planned_hold_sessions:'52.0',
 anticipated_time_basis:'SAVED_EVIDENCE',planned_hold_source:'DURATION_EVIDENCE_Q80:1d:n=240.0',dte:99,contract_dte:67};
const before=JSON.stringify(saved), html=render(saved);
for(const value of ['Trade horizon','median arrival (q50)','Slower-arrival estimate (q80)','Planned hold',
 '22 trading sessions','52 trading sessions','SAVED_EVIDENCE','DURATION_EVIDENCE_Q80:1d:n=240.0','not option DTE'])assert.ok(html.includes(value),value);
assert.equal(JSON.stringify(saved),before,'render must not mutate saved values');
assert.ok(!html.includes('99 trading sessions')&&!html.includes('67 trading sessions'),'no DTE substitution');
assert.ok(render({anticipated_sessions_q50:0,planned_hold_sessions:1}).includes('0 trading sessions'));
assert.ok(render({planned_hold_sessions:1}).includes('1 trading session</dd>'));
assert.ok(render({planned_hold_sessions:2.5}).includes('2.5 trading sessions'));
for(const invalid of [null,undefined,'','  ','NAN','None',false,-1,Infinity]){
 const output=render({anticipated_sessions_q50:invalid,anticipated_sessions_q80:invalid,planned_hold_sessions:invalid,dte:99});
 assert.equal((output.match(/<dd>Not recorded<\/dd>/g)||[]).length,6,`missing/invalid ${invalid}`);
 assert.ok(!output.includes('NaN trading')&&!output.includes('99 trading'));
}
assert.ok(render({planned_hold_source:'<script>bad</script>',anticipated_time_basis:'<img>'}).includes('&lt;script&gt;'));
assert.ok(!render({planned_hold_source:'<script>bad</script>'}).includes('<script>'));
const app=fs.readFileSync(path.join(root,'intelligence-lab/static/review-app.js'),'utf8');
assert.ok(app.includes("target.querySelector('.card-heading').insertAdjacentHTML('afterend',window.LabTradeTiming.render(f,data.timing_details))"));
const separated=render(saved,{remaining_hold_sessions:50,valuation_horizon_sessions:22,empirical_valuation_horizon_sessions:20,expiry_sessions_remaining:66,minimum_required_sessions:58});
for(const value of ['Remaining hold','50 trading sessions','Payoff valuation horizon','Empirical EV3 scoring horizon','20 trading sessions','66 trading sessions','58 trading sessions'])assert.ok(separated.includes(value),value);
const page=fs.readFileSync(path.join(root,'intelligence-lab/static/review.html'),'utf8');
assert.ok(page.indexOf('/static/trade-timing.js')<page.indexOf('/static/review-app.js'));
console.log('PASS: saved trade horizon/hold prominence, units, no DTE fallback, zero/missing/invalid values, escaping, immutable input and both card paths');
