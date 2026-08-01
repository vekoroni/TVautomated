'use strict';
/**
 * FIX-4 — EV rounded to 4dp loses sign on small magnitudes.
 *
 * True EV magnitudes in this pipeline run 1.1e-5 to 4.9e-5 (see
 * LAB_QA_REPORT.md F3 / BASELINE.md). At 4dp, |EV| < 0.00005 rounds to
 * "0.0000" or "-0.0000" — and `parseFloat("-0.0000") === 0`, so an `EV >= 0`
 * filter admits genuinely negative-EV rows. 8dp keeps a real sign-bearing
 * distance from zero for anything down to 5e-9, comfortably below the
 * magnitudes actually seen.
 *
 * Regression check (see FIX-4 commit): pipeline_interpreter/lab_reconciliation.py
 * parses this column with Python float() and a proportional tolerance
 * (10% of the pipeline's own ev_score) — more decimal places cannot break
 * that comparison, it can only make it more accurate.
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
  const ev = findCol(cols, 'EV');

  const negTiny = ev({ ev2_ev_conf_adj: '-2.8e-05' });
  assert.ok(parseFloat(negTiny) < 0, `EV of -2.8e-05 must parse strictly negative, got '${negTiny}'`);

  const posTiny = ev({ ev2_ev_conf_adj: '4.1e-05' });
  assert.ok(parseFloat(posTiny) > 0, `EV of 4.1e-05 must parse strictly positive, got '${posTiny}'`);

  // A genuine zero must still be exactly zero (not turned into noise).
  const zero = ev({ ev2_ev_conf_adj: '0' });
  assert.strictEqual(parseFloat(zero), 0);

  // Larger, "normal" EV values must still read sanely (not scientific notation,
  // which a naive downstream float() parses fine, but keep it fixed-decimal
  // per the fix spec so no consumer is surprised).
  const normal = ev({ ev2_ev_conf_adj: '0.12' });
  assert.ok(!/e/i.test(normal), `EV must not use scientific notation, got '${normal}'`);
  assert.ok(Math.abs(parseFloat(normal) - 0.12) < 1e-6);

  console.log('OK: FIX-4 (EV) — sign survives at pipeline-realistic magnitudes, fixed-decimal');
}

run();
