'use strict';
/**
 * FIX-5 export surface — new Options_Direction and Lab_Coherence_Status
 * columns. The direction-collapse logic itself lives server-side
 * (intelligence_lab.py, tested in tests/test_lab_strangle_direction.py);
 * this only checks the export mapper reads what the server already computed.
 *
 * Placement: appended after the existing direction-adjacent columns
 * (immediately after 'Direction') rather than at the very end of the file,
 * so a reader sees the real upstream side right next to the (possibly blank,
 * for a strangle) resolved Direction.
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

  const dirIdx = labels.indexOf('Direction');
  const odIdx = labels.indexOf('Options_Direction');
  const csIdx = labels.indexOf('Lab_Coherence_Status');
  assert.notStrictEqual(dirIdx, -1);
  assert.notStrictEqual(odIdx, -1, 'Options_Direction column must exist');
  assert.notStrictEqual(csIdx, -1, 'Lab_Coherence_Status column must exist');
  assert.strictEqual(odIdx, dirIdx + 1, 'Options_Direction must sit immediately after Direction');

  const optionsDirection = cols[odIdx][1];
  const coherenceStatus = cols[csIdx][1];

  const strangleRow = { direction: '', options_direction: 'STRANGLE', lab_coherence_status: 'STRANGLE_NONDIRECTIONAL' };
  assert.strictEqual(optionsDirection(strangleRow), 'STRANGLE');
  assert.strictEqual(coherenceStatus(strangleRow), 'STRANGLE_NONDIRECTIONAL');

  const cleanPutRow = { direction: 'PUT', options_direction: 'PUT', lab_coherence_status: 'CLEAN' };
  assert.strictEqual(optionsDirection(cleanPutRow), 'PUT');
  assert.strictEqual(coherenceStatus(cleanPutRow), 'OK', 'CLEAN must display as OK per the fix spec');

  const repairedRow = { direction: 'CALL', options_direction: 'CALL', lab_coherence_status: 'INSTRUMENT_DISPLAY_REPAIRED' };
  assert.strictEqual(coherenceStatus(repairedRow), 'INSTRUMENT_DISPLAY_REPAIRED', 'other real statuses must pass through unchanged, not be collapsed to OK');

  const absentRow = {};
  assert.strictEqual(optionsDirection(absentRow), '');
  assert.strictEqual(coherenceStatus(absentRow), 'OK', 'no coherence status computed yet must not read as an error state');

  console.log('OK: FIX-5 export columns (Options_Direction, Lab_Coherence_Status)');
}

run();
