'use strict';
/**
 * FIX-12 (AVS options analytics slice 1d, ACK 30 Sep 2026: "retire EV v2") — the Lab never shows the legacy v2.1.0
 * heuristic EV.
 *
 * EV v2 is not an expected value (CLAUDE.md rule 5): it is wrong for puts and its IV adjustment has the wrong sign
 * (verified 29 Sep). The Lab shows EV only when EV3 (advisory) supplied it; a row carrying only legacy values shows
 * "NOT COMPARABLE", exports a blank EV, and the legacy decision/quality columns are gone.
 */
const assert = require('assert');
const { loadLabExportContext } = require('./lab_export_harness');

function col(cols, label) {
  const hit = cols.find(([l]) => l === label);
  return hit ? hit[1] : null;
}

function run() {
  const ctx = loadLabExportContext();
  const legacyOnly = { ev2_ev_conf_adj: '0.31', ev: '0.31', ev_final: '0.31', ev_net: '0.31', eil_ev_net: '0.2',
                       fd_ev_used: '0.2', eil__ev2_ev_conf_adj: '0.31', ev2_decision_hint: 'STRONG',
                       ev2_quality_score: '71' };
  const info = ctx.getEvInfo(legacyOnly);
  assert.ok(Number.isNaN(info.value), `legacy-only row must not show an EV, got ${info.value}`);
  assert.strictEqual(info.source, '');
  assert.ok(!/legacy/i.test(ctx.evLabel(legacyOnly)), 'no legacy EV label');

  const ev3 = { ...legacyOnly, ev3_ev_conservative_return: '-0.12', ev3_selected_contract_aligned: 'True' };
  assert.strictEqual(ctx.getEvInfo(ev3).value, -0.12);
  assert.strictEqual(ctx.getEvInfo(ev3).source, 'EV3');

  const cols = ctx.buildExportColumns();
  assert.strictEqual(col(cols, 'EV')(legacyOnly), '');
  assert.strictEqual(col(cols, 'EV')(ev3), '-0.12000000');
  assert.strictEqual(col(cols, 'EV_Decision'), null, 'legacy decision column retired');
  assert.strictEqual(col(cols, 'EV_Quality'), null, 'legacy quality column retired');

  console.log('OK: FIX-12 — legacy EV v2 retired from the Lab; EV3 advisory only');
}

run();
