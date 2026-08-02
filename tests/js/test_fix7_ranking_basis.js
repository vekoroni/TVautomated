'use strict';
/**
 * FIX-7 — Priority_Rank sorts on (lab_action_bucket, -research_priority_score,
 * ticker), and the bucket is granted on `verdict OR morning_execution_permission`
 * (server-side, intelligence_lab.py:_lab_priority_bucket). Only Verdict is
 * exported, so an ARMED row outranking a lower-scored GO row looks arbitrary.
 *
 * Fix: export the already-computed lab_action_bucket_label as its own column.
 * This is purely additive -- it must not change what Priority_Rank actually is
 * for any row (see tests/test_lab_ranking_basis_export.py for the
 * byte-identical-ordering assertion against the real run).
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

  const rankIdx = labels.indexOf('Priority_Rank');
  const basisIdx = labels.indexOf('Lab_Action_Bucket_Label');
  assert.notStrictEqual(rankIdx, -1);
  assert.notStrictEqual(basisIdx, -1, 'Lab_Action_Bucket_Label column must exist');
  assert.strictEqual(basisIdx, rankIdx + 1, 'Lab_Action_Bucket_Label must sit immediately after Priority_Rank -- it explains the rank right next to it');

  const bucketLabel = cols[basisIdx][1];
  assert.strictEqual(bucketLabel({ lab_action_bucket_label: 'ACTIONABLE' }), 'ACTIONABLE');
  assert.strictEqual(bucketLabel({ lab_action_bucket_label: 'ARMED' }), 'ARMED');
  assert.strictEqual(bucketLabel({}), '', 'missing bucket label must export as empty, not throw');

  console.log('OK: FIX-7 (Lab_Action_Bucket_Label exported next to Priority_Rank)');
}

run();
