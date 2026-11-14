const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=path.resolve(__dirname,'..');
const context={window:{}};
vm.runInNewContext(fs.readFileSync(path.join(root,'intelligence-lab/static/contract-details.js'),'utf8'),context);
const render=context.window.LabContractDetails.render;
const html=render({strike:35,call_put:'Put',expiry:'2027-01-15',calendar_dte:87,
 trading_sessions_remaining:61,saved_reference_date:'2026-10-20',issues:['<bad>']});
for(const s of ['$35.00','Put','2027-01-15','87','61','2026-10-20','not a live countdown','&lt;bad&gt;'])assert.ok(html.includes(s),s);
assert.ok(render({strike:35.125}).includes('$35.125'));
assert.ok(render({calendar_dte:0,trading_sessions_remaining:0}).includes('<dd>0</dd>'));
assert.ok(!render({}).includes('NaN'));
const app=fs.readFileSync(path.join(root,'intelligence-lab/static/review-app.js'),'utf8');
assert.ok(app.includes('window.LabContractDetails.render(contractDisplay)'));
console.log('PASS: shared trade-card/watchlist contract details, exact strike, zero/missing DTE, escaped disclosures');
