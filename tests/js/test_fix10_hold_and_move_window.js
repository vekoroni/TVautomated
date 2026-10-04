'use strict';
/**
 * FIX-10 (ACK option 3, 28 Sep 2026) — the Lab shows the planned hold and the move window as two
 * facts, and EV3 at each.
 *
 * Before: the "Hold" column showed the thesis move window label (e.g. 1_5d) while every row is held
 * and priced for the governed 20-session hold (ACK 18 Sep 2026), so a trader read "1 to 5 days" on a
 * 20-session trade. EV3 now values the contract at the hold (lead, published as EV) and at the move
 * window (ev3_move_window_*), shown beside it under the same contract-alignment rule.
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

  // The hold is the governed planned hold, in sessions; the move window stays a separate label.
  const row = { planned_hold_sessions: '20.0', hold_label: '1_5d', opt__hold_label: '1_5d', time_horizon: '1_5d' };
  assert.strictEqual(ctx.getHoldPeriod(row), '20 sessions');
  assert.strictEqual(ctx.getTimeHorizon(row), '1_5d');
  // A legacy row without a planned hold keeps its recorded label (never a fabricated number).
  assert.strictEqual(ctx.getHoldPeriod({ hold_label: '6_10d' }), '6_10d');

  // EV3 at the move window: shown only for an aligned, evaluated contract.
  const aligned = {
    ev3_selected_contract_aligned: 'True', economics_comparable: 'True',
    ev3_ev_conservative_return: '0.12', ev3_move_window_status: 'EVALUATED',
    ev3_move_window_sessions: '5', ev3_move_window_ev_conservative_return: '0.05',
  };
  const info = ctx.getMoveWindowEvInfo(aligned);
  assert.strictEqual(info.value, 0.05);
  assert.strictEqual(info.sessions, 5);
  assert.ok(Number.isNaN(ctx.getMoveWindowEvInfo({ ...aligned, ev3_selected_contract_aligned: 'False' }).value),
    'a misaligned contract must not show a move-window EV');
  assert.ok(Number.isNaN(ctx.getMoveWindowEvInfo({ ...aligned, ev3_move_window_status: 'NOT_EVALUATED' }).value),
    'a move window that was not evaluated must not show a number');

  const cols = ctx.buildExportColumns();
  assert.strictEqual(findCol(cols, 'Hold_Period')(row), '20 sessions');
  assert.strictEqual(findCol(cols, 'EV3_Move_Window')(aligned), '0.05000000');
  assert.strictEqual(findCol(cols, 'EV3_Move_Window_Sessions')(aligned), '5');
  assert.strictEqual(findCol(cols, 'EV3_Move_Window')({ ...aligned, ev3_move_window_status: 'NOT_EVALUATED' }), '');

  console.log('OK: FIX-10 — planned hold and move window shown as two facts, EV3 at each');
}

run();
