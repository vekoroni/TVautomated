/* Exercise the actual review app in a small DOM harness; no server or provider. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.resolve(__dirname, '../../intelligence-lab/static/review-app.js'), 'utf8');
const families = ['structure', 'option_risk', 'context', 'morning', 'audit'];

class Element {
  constructor() { this.innerHTML = ''; this.textContent = ''; this.dataset = {}; this.options = []; this.value = ''; this.children = new Map(); }
  addEventListener() {}
  insertAdjacentHTML() {}
  scrollIntoView() {}
  setAttribute() {}
  replaceChildren() { this.innerHTML = ''; }
  get parentElement() { return this.querySelector('parent'); }
  querySelector(selector) {
    if (!this.children.has(selector)) this.children.set(selector, new Element());
    return this.children.get(selector);
  }
  querySelectorAll(selector) {
    if (selector !== 'details') return [];
    return [...this.innerHTML.matchAll(/<details\b([^>]*)>/g)].map(([, attributes]) => {
      const element = new Element();
      for (const [, name, value] of attributes.matchAll(/data-([\w-]+)="([^"]*)"/g)) element.dataset[name] = value;
      return element;
    });
  }
}

function harness(respond = () => ({ fields: {} })) {
  const nodes = new Map(), calls = [];
  const document = { hidden: false, addEventListener() {}, getElementById(id) {
    if (!nodes.has(id)) nodes.set(id, new Element());
    return nodes.get(id);
  }};
  const window = {
    addEventListener() {}, dispatchEvent() {},
    LabReviewLive: { createFollower: () => ({ poll() {} }) },
    LabContractDetails: { render: () => '' }, LabTradeTiming: { render: () => '' },
    LabSnapshotDisclosure: { render: () => '' }
  };
  const context = vm.createContext({ window, document, location: { search: '' }, URLSearchParams,
    AbortController, setTimeout, clearTimeout, setInterval() {}, console,
    fetch: async (url, options) => {
      calls.push({ url, options });
      const answer = await respond(url, options);
      return { ok: answer.ok !== false, status: answer.status || 200, json: async () => answer.body || answer };
    }
  });
  const injection = `window.testAccess={openCard,loadDrawer,setState(s){
    if(s.run!==undefined)run=s.run;if(s.revision!==undefined)revision=s.revision;
    if(s.sequence!==undefined)sequence=s.sequence;if(s.cardSequence!==undefined)cardSequence=s.cardSequence;
    if(s.searchSequence!==undefined)searchSequence=s.searchSequence;}};`;
  const end = source.lastIndexOf('})();');
  assert.ok(end > 0);
  vm.runInContext(source.slice(0, end) + injection + source.slice(end), context);
  window.testAccess.setState({ run: 'RUN_ONE', revision: 'rev 1', sequence: 3, cardSequence: 7, searchSequence: 11 });
  return { api: window.testAccess, calls, document };
}

test('current cards expose exactly the five canonical drawers and no retired paid/report controls', async () => {
  const card = { row_key: 'row-one', revision: 'rev 1', fields: { ticker: 'AAA', direction: 'PUT', lab_verdict: 'BLOCKED' } };
  const before = JSON.stringify(card);
  const h = harness(url => url.includes('/mentality?') ? {
    interpretation: 'Saved context', review_revision: 'rev 1', latest_mentality_revision: 'context-1', disclosure: 'Separate context'
  } : card);
  await h.api.openCard('row-one');
  const markup = h.document.getElementById('review-card').innerHTML;
  assert.ok(markup.includes('<article class="trade-card">'), markup);
  assert.deepEqual([...markup.matchAll(/data-family="([^"]+)"/g)].map(m => m[1]), families);
  assert.equal((markup.match(/<details\b/g) || []).length, 5);
  assert.doesNotMatch(markup, /data-reports|Interpreter|interpreter-panel|paid report/i);
  assert.equal(JSON.stringify(card), before, 'rendering must not modify governed source facts');
  assert.ok(h.calls.every(call => !call.url.includes('/api/interpreter/')));
});

test('review source has no retired endpoint or desk-link branch', () => {
  assert.doesNotMatch(source, /\/api\/interpreter\/|data-reports|dataset\.reports|interpreter-panel|legacyDesk/);
});

for (const family of families) {
  test(`${family} drawer loads canonical evidence with the saved revision and preserves zero/escaped facts`, async () => {
    const payload = { fields: { thesis_phase: 'E', zero: 0, absent: null, note: '<b>source text</b>', nested: { proof: '<script>' } } };
    const before = JSON.stringify(payload);
    const h = harness(() => payload), detail = new Element(); detail.dataset.family = family;
    await h.api.loadDrawer(detail, { row_key: 'row-one', revision: 'rev 1', fields: { ticker: 'AAA' } }, 7, 3);
    assert.equal(h.calls.length, 1);
    assert.equal(h.calls[0].url, `/api/lab/RUN_ONE/rows/row-one/evidence/${family}?revision=rev%201`);
    assert.equal(h.calls[0].options.cache, 'no-store');
    assert.equal(h.calls[0].options.method, undefined);
    assert.equal(detail.dataset.loaded, 'complete');
    const markup = detail.querySelector('.drawer').innerHTML;
    assert.match(markup, /<dt>zero<\/dt><dd>0<\/dd>/);
    assert.doesNotMatch(markup, /<dt>absent<\/dt>|<b>source text<\/b>|<script>/);
    assert.match(markup, /&lt;b&gt;source text&lt;\/b&gt;/);
    assert.match(markup, /All published fields in this family/);
    assert.match(markup, /&lt;script&gt;/);
    assert.equal(JSON.stringify(payload), before);
  });
}

test('a genuine canonical read error stays local, is escaped, and can be retried successfully', async () => {
  let attempts = 0;
  const h = harness(() => ++attempts === 1 ? { ok: false, status: 503, body: { reason: '<temporary>' } } : { fields: { valid: 'saved fact' } });
  const detail = new Element(); detail.dataset.family = 'audit';
  const card = { row_key: 'row-one', revision: 'rev 1' };
  await h.api.loadDrawer(detail, card, 7, 3);
  assert.equal(detail.dataset.loaded, '');
  assert.match(detail.querySelector('.drawer').innerHTML, /Evidence unavailable: &lt;temporary&gt;/);
  assert.match(detail.querySelector('.drawer').innerHTML, /trade card remains open/);
  await h.api.loadDrawer(detail, card, 7, 3);
  assert.equal(detail.dataset.loaded, 'complete');
  assert.match(detail.querySelector('.drawer').innerHTML, /saved fact/);
  assert.ok(h.calls.every(call => call.url.includes('/evidence/audit?revision=rev%201')));
});

for (const [multi, change] of [[false, { cardSequence: 8 }], [false, { sequence: 4 }], [true, { searchSequence: 12 }], [true, { sequence: 4 }]]) {
  test(`stale ${multi ? 'search' : 'single-card'} evidence cannot overwrite after ${Object.keys(change)[0]} changes`, async () => {
    let release;
    const h = harness(() => new Promise(resolve => { release = resolve; }));
    const detail = new Element(); detail.dataset.family = 'morning';
    const drawer = detail.querySelector('.drawer'); drawer.innerHTML = 'original card';
    const pending = h.api.loadDrawer(detail, { row_key: 'row-one', revision: 'rev 1' }, multi ? 11 : 7, 3, multi);
    h.api.setState(change); release({ fields: { invalid: 'stale result' } }); await pending;
    assert.equal(drawer.innerHTML, 'original card');
  });
}
