'use strict';
/**
 * FIX-8 — Verdict and Lab_Verdict both call finalLabVerdict(s) -- a literal
 * duplicate column, not an independent check.
 *
 * Regression check (Phase 3 report): grepped the codebase for "Lab_Verdict".
 * pipeline_interpreter/lab_reconciliation.py lists it in _LAB_CONTEXT_FIELDS
 * (display-only, alongside "Verdict" itself, no branching logic). That loop
 * does `lab_row.get(field, "")` and skips empty values, so a missing column
 * degrades gracefully -- the context block just loses one redundant line
 * ("Verdict" still carries the identical value). Not touching that file:
 * it's outside the Lab, and the degradation is exactly why removal is safe.
 */
const assert = require('assert');
const { loadLabExportContext } = require('./lab_export_harness');

function run() {
  const ctx = loadLabExportContext();
  const cols = ctx.buildExportColumns();
  const labels = cols.map(([l]) => l);

  assert.strictEqual(labels.indexOf('Lab_Verdict'), -1, 'Lab_Verdict must be removed -- it was a literal duplicate of Verdict');
  assert.notStrictEqual(labels.indexOf('Verdict'), -1, 'Verdict itself must remain -- it is the real, independently-sourced column');

  console.log('OK: FIX-8 (Lab_Verdict removed, Verdict retained)');
}

run();
