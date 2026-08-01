'use strict';
/**
 * FIX-3 — trade_idea_id is fully formed in memory but never written to the
 * export. Without it, a row in the CSV cannot be mechanically joined back to
 * its journal/database record.
 *
 * Placement: immediately after 'Ticker' — trade_idea_id is the row's
 * identity, so it belongs next to the other identity column, not appended at
 * the end where it reads as an afterthought.
 */
const assert = require('assert');
const { loadLabExportContext } = require('./lab_export_harness');

function run() {
  const ctx = loadLabExportContext();
  const cols = ctx.buildExportColumns();
  const labels = cols.map(([l]) => l);

  const idx = labels.indexOf('Trade_Idea_Id');
  assert.notStrictEqual(idx, -1, 'Trade_Idea_Id column must exist in the export');
  assert.strictEqual(labels[idx - 1], 'Ticker', 'Trade_Idea_Id must sit immediately after Ticker');

  const fn = cols[idx][1];
  const row = { ticker: 'AAPL', trade_idea_id: '20260731_083130:AAPL:CALL:230.0:2026-08-21' };
  assert.strictEqual(fn(row), '20260731_083130:AAPL:CALL:230.0:2026-08-21');
  assert.strictEqual(fn({ ticker: 'AAPL' }), '', 'missing trade_idea_id must export as empty, not throw');

  console.log('OK: FIX-3 (Trade_Idea_Id) — present, placed after Ticker, reads real value');
}

run();
