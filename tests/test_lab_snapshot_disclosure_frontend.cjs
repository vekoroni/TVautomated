const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.resolve(__dirname,'..'),context={window:{}};vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(root,'intelligence-lab/static/snapshot-disclosure.js'),'utf8'),context);
const data={current_scenario:{state:'MORNING_REFERENCE',contract_symbol:'DKS261204P00150000',exit_sessions:3},
historical_timevalue:{state:'REFERENCE_ONLY',expiry:'2026-12-11',as_of_session:'2026-11-13',return_pct:15.4621,mismatch_reasons:['EXPIRY_MISMATCH']},
doi_scenario:{state:'NOT_ASSESSED',reason:'DOI_SCENARIOS_ABSENT'},timing:{hold_basis:'VOLATILITY_PLANNING_FALLBACK'},
quote:{provider:'<script>unsafe</script>',configured_delay_seconds:900,configured_effective_window_seconds:900,saved_raw_age_minutes:27.5,saved_effective_age_seconds:748.17}};
const before=JSON.stringify(data),html=context.window.LabSnapshotDisclosure.render(data);
for(const text of ['Current-contract conditional scenario','Separate DOI scenario family','Historical time-value reference','Excluded from current-contract fields','VOLATILITY_PLANNING_FALLBACK','effective assessment window 900','not ages now','Live broker re-quote required'])assert.ok(html.includes(text),text);
assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes('<script>unsafe'));
assert.equal(JSON.stringify(data),before);
assert.ok(context.window.LabSnapshotDisclosure.render(null).includes('No live entry quote'));
const page=fs.readFileSync(path.join(root,'intelligence-lab/static/review.html'),'utf8');
assert.ok(page.indexOf('/static/snapshot-disclosure.js')<page.indexOf('/static/review-app.js'));
const js=fs.readFileSync(path.join(root,'intelligence-lab/static/review-app.js'),'utf8');
assert.ok(js.includes('planning fallback, median arrival unassessed'));
assert.ok(js.includes('window.LabSnapshotDisclosure.render(data.snapshot_disclosure)'));
console.log('PASS: saved/current/DOI separation, timing and delayed-feed labels, escaping, immutable metadata, load order');
