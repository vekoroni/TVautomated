/* Unit-test the standalone renderer with a minimal DOM; no browser/network. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'intelligence-lab/static/convexity-watchlist.js'), 'utf8');
function env(payload) {
  const elements = new Map(); const events = new Map(); const calls = [];
  function el(id) {
    if (!elements.has(id)) elements.set(id, {innerHTML:'',textContent:'',disabled:false,listeners:{},
      addEventListener(k,f){this.listeners[k]=f}, replaceChildren(){this.innerHTML=''}});
    return elements.get(id);
  }
  const window = {addEventListener(k,f){events.set(k,f)},dispatchEvent(e){events.get(e.type)?.(e)}};
  const context = {document:{getElementById:el},window,AbortController,setTimeout,clearTimeout,
    CustomEvent:class {constructor(type,init){this.type=type;this.detail=init.detail}},
    fetch:async url=>{calls.push(url);return {ok:true,json:async()=>payload}}};
  vm.runInNewContext(source,context);
  return {el,events,calls};
}
const item={ticker:'<script>bad</script>',direction:'CALL',contract_symbol:'TEST270115C00100000',
  row_key:'key',stress:{delay_return:1,iv_return:.8,combined_return:.6,delay_sessions:20,
  iv_original:.4,iv_stressed:.32,state:'COMPLETE'},target_return:1.2,target_sessions:10,
  invalidation_return:-.5,stall_return:-.2,entry_per_contract:501.1};
const payload={run_id:'TEST',revision:'abc',source_publication_utc:'2026-10-20T15:00Z',population:2,
  groups:{waiting:[item],entry_ready:[{...item,ticker:'READY'}],review_only:[]},
  exclusions:[],disclosures:['No automatic capital authority'],policy:{waiting_min_target_return:.75,
  max_spread_pct_mid:15,min_open_interest:500,min_target_runway_after_trigger:.5}};
(async()=>{
  const a=env(payload);
  await a.el('convexity-load').listeners.click();
  assert.match(a.el('convexity-status').textContent,/Wait for a coherent/);
  a.events.get('lab-review-loaded')({detail:{run:'TEST',revision:'abc'}});
  await a.el('convexity-load').listeners.click();
  assert.deepEqual(a.calls,['/api/lab/TEST/convexity?revision=abc']);
  const html=a.el('convexity-content').innerHTML;
  for (const expected of ['Waiting for trigger · 1','Entry-ready in saved gate','+120.0%',
    '-50.0%','Same-target delay','IV × 0.8','+60.0%','not trading gates']) assert.ok(html.includes(expected),expected);
  assert.ok(!html.includes('<script>bad</script>'));
  assert.ok(html.includes('&lt;script&gt;bad&lt;/script&gt;'));
  assert.ok(!html.includes('NaN'));
  a.el('review-run').listeners.change();
  assert.equal(a.el('convexity-content').innerHTML,'');
  const b=env({...payload,revision:'wrong'});
  b.events.get('lab-review-loaded')({detail:{run:'TEST',revision:'abc'}});
  await b.el('convexity-load').listeners.click();
  assert.match(b.el('convexity-status').textContent,/revision does not match/);
  assert.equal(b.el('convexity-content').innerHTML,'');
  assert.equal(b.el('convexity-load').disabled,false);
  console.log('PASS: saved renderer, lane separation, percentages, escaping, reset, revision mismatch; zero real network calls');
})().catch(e=>{console.error(e);process.exitCode=1});
