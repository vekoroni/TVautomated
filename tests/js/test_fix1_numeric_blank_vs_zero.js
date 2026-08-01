'use strict';
/**
 * FIX-1 — numeric export columns must distinguish a genuine 0 from missing
 * data. JS treats 0 as falsy, so `s.field || ''` exports a real zero as an
 * empty string, indistinguishable from "not computed".
 *
 * Tests the REAL production mapper (via lab_export_harness.js, which evals
 * the actual inline <script> from static/index.html) — not a reimplementation.
 *
 * Empirically verified before writing this test (see BASELINE.md / Phase 1
 * report): of the export's `|| ''` numeric-looking columns, only
 * Vetoes_Count (sb_vetoes_count) and Priority_Rank (priority_rank) are ever
 * actual JS numbers at runtime — everything else in the export arrives as a
 * CSV-sourced string (e.g. "0.0"), which is already truthy and unaffected by
 * this bug. Fixing those other columns would be a no-op diff; only these two
 * are tested and fixed.
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
  assert.strictEqual(typeof ctx.buildExportColumns, 'function',
    'buildExportColumns() must be extracted from exportCSV() so it is independently testable');

  const cols = ctx.buildExportColumns();
  const vetoesCount = findCol(cols, 'Vetoes_Count');
  const priorityRank = findCol(cols, 'Priority_Rank');

  const cases = [
    { field: 'sb_vetoes_count', fn: vetoesCount, label: 'Vetoes_Count' },
    { field: 'priority_rank', fn: priorityRank, label: 'Priority_Rank' },
  ];

  for (const { field, fn, label } of cases) {
    assert.strictEqual(fn({ [field]: 0 }), 0, `${label}: a genuine 0 must export as 0, not ''`);
    assert.strictEqual(fn({ [field]: 3 }), 3, `${label}: a genuine 3 must still export as 3`);
    assert.strictEqual(fn({ [field]: null }), '', `${label}: null (missing) must export as ''`);
    assert.strictEqual(fn({}), '', `${label}: undefined (absent key) must export as ''`);
  }

  console.log('OK: FIX-1 (Vetoes_Count, Priority_Rank) — 0 survives, null/undefined still blank');
}

run();
