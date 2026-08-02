'use strict';
/**
 * FIX-6 — Vol_State is derived from GARCH's forward tailwind score, not IV
 * percentile, but shares a CHEAP/FAIR/EXPENSIVE vocabulary with the
 * genuinely-different IVP_Label, which reads as a bug (20 rows disagree in
 * the audited export).
 *
 * Regression check (commit message / Phase 3 report): grepped the codebase
 * for "Vol_State" consumers. pipeline_interpreter/lab_reconciliation.py
 * references it in _LAB_CONTEXT_FIELDS (a display-only list, no branching
 * logic) -- a real consumer, so per the fix spec this is NOT a hard rename.
 * Both columns are emitted this release: Vol_State (unchanged, existing
 * consumer keeps working) and Vol_Tailwind_State (new, clearer name for
 * future consumers to migrate to).
 */
const assert = require('assert');
const { loadLabExportContext } = require('./lab_export_harness');

function findCol(cols, label) {
  const hit = cols.find(([l]) => l === label);
  if (!hit) throw new Error(`Column '${label}' not found in buildExportColumns()`);
  return hit[1];
}

function run() {
  const ctx = loadLabExportContext();
  const cols = ctx.buildExportColumns();
  const labels = cols.map(([l]) => l);

  const oldIdx = labels.indexOf('Vol_State');
  const newIdx = labels.indexOf('Vol_Tailwind_State');
  assert.notStrictEqual(oldIdx, -1, 'Vol_State must still be exported (existing consumer: pipeline_interpreter/lab_reconciliation.py)');
  assert.notStrictEqual(newIdx, -1, 'Vol_Tailwind_State must be exported as the new, clearer name');
  assert.strictEqual(newIdx, oldIdx + 1, 'Vol_Tailwind_State should sit immediately next to Vol_State');

  const volState = cols[oldIdx][1];
  const volTailwindState = cols[newIdx][1];

  const cheapRow = { 'garch__l3_iv_tailwind_score': '-0.091' };
  assert.strictEqual(volState(cheapRow), 'CHEAP');
  assert.strictEqual(volTailwindState(cheapRow), 'CHEAP', 'both columns must report the identical value -- this is a rename, not a new computation');

  const expRow = { 'garch__l3_iv_tailwind_score': '0.10' };
  assert.strictEqual(volState(expRow), 'EXP');
  assert.strictEqual(volTailwindState(expRow), 'EXP');

  const absentRow = {};
  assert.strictEqual(volState(absentRow), '');
  assert.strictEqual(volTailwindState(absentRow), '');

  console.log('OK: FIX-6 (Vol_State kept, Vol_Tailwind_State added alongside it)');
}

run();
