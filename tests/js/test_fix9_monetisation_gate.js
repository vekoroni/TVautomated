'use strict';

const assert = require('assert');
const { loadLabExportContext } = require('./lab_export_harness');

function run() {
  const ctx = loadLabExportContext();
  const base = { display_execution_category: 'GO', lab_verdict: 'GO', final_action: 'BUY_NOW' };

  for (const evDecision of ['WEAK', 'AVOID']) {
    const signal = { ...base, ev2_decision_hint: evDecision, monetisability_state: 'MONETISABLE' };
    assert.strictEqual(ctx.getExecutionCategory(signal), 'GO');
    assert.strictEqual(ctx.finalLabVerdict(signal), 'GO');
  }

  const badLegacyRr = { ...base, rr_premium_expected: '-99', monetisability_state: 'MONETISABLE' };
  assert.strictEqual(ctx.getExecutionCategory(badLegacyRr), 'GO');
  assert.strictEqual(ctx.finalLabVerdict(badLegacyRr), 'GO');

  const limited = { ...base, lab_verdict: 'GO_LIMIT', final_action: 'BUY_SMALL', monetisability_state: 'LIMITED' };
  assert.strictEqual(ctx.getExecutionCategory(limited), 'GO_LIMIT');
  assert.strictEqual(ctx.finalLabVerdict(limited), 'GO_LIMIT');

  const repair = { ...base, final_action: 'CONTRACT_REPAIR', monetisability_state: 'DATA_MISSING' };
  assert.strictEqual(ctx.getExecutionCategory(repair), 'CONTRACT_REPAIR');

  assert.strictEqual(ctx.getMonetisabilityState(base), 'DATA_MISSING');
  assert.strictEqual(ctx.getMonetisabilityState(limited), 'LIMITED');

  console.log('OK: Execution Gate is authoritative and R:R is not a UI decision field');
}

run();
