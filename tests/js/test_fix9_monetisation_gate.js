'use strict';

const assert = require('assert');
const { loadLabExportContext } = require('./lab_export_harness');

function run() {
  const ctx = loadLabExportContext();
  const base = { display_execution_category: 'GO', lab_verdict: 'GO' };

  for (const evDecision of ['WEAK', 'AVOID']) {
    const signal = { ...base, ev2_decision_hint: evDecision, rr: '2.0' };
    assert.strictEqual(ctx.getExecutionCategory(signal), 'NON_MONETISABLE');
    assert.strictEqual(ctx.finalLabVerdict(signal), 'NON_MONETISABLE');
  }

  const zeroRr = { ...base, ev2_decision_hint: 'MODERATE', rr: '0' };
  assert.strictEqual(ctx.getExecutionCategory(zeroRr), 'NON_MONETISABLE');
  assert.strictEqual(ctx.finalLabVerdict(zeroRr), 'NON_MONETISABLE');

  for (const evDecision of ['MODERATE', 'STRONG']) {
    const signal = { ...base, ev2_decision_hint: evDecision, rr: '1.25' };
    assert.strictEqual(ctx.getExecutionCategory(signal), 'GO');
    assert.strictEqual(ctx.finalLabVerdict(signal), 'GO');
  }

  console.log('OK: FIX-9 — GO requires MODERATE/STRONG EV and positive RR');
}

run();
