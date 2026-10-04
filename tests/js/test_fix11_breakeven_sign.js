'use strict';
/**
 * FIX-11 (AVS options analytics slice 1c, ACK approved 30 Sep 2026) — the frozen option breakeven shows the signed
 * stock move it needs.
 *
 * Options Intelligence publishes `breakeven_pct` as the distance to breakeven in the trade's favour: a call's rise
 * (BE − spot) / spot, a put's fall (spot − BE) / spot. The Lab printed "+" before it for every row, so a put needing
 * a 4 % fall read "+4 %". The label now states the stock move: calls +, puts −; a breakeven already passed shows the
 * opposite sign; missing data shows a dash, never a fabricated number.
 */
const assert = require('assert');
const { loadLabExportContext } = require('./lab_export_harness');

function run() {
  const ctx = loadLabExportContext();
  const f = ctx.frozenBreakevenLabel;
  assert.strictEqual(typeof f, 'function', 'frozenBreakevenLabel must exist');

  assert.strictEqual(f({ direction: 'CALL', opt__breakeven_price: '106.2', opt__breakeven_pct: '6.2' }),
    '$106.2 (+6.20% stock move)');
  assert.strictEqual(f({ direction: 'PUT', opt__breakeven_price: '48.6', opt__breakeven_pct: '4.0' }),
    '$48.6 (-4.00% stock move)');
  // an in-the-money put whose breakeven is above spot needs no fall: the sign flips honestly
  assert.strictEqual(f({ final_direction: 'PUT', opt__breakeven_price: '51.0', opt__breakeven_pct: '-2.0' }),
    '$51.0 (+2.00% stock move)');
  assert.strictEqual(f({ direction: 'PUT', opt__breakeven_price: '', opt__breakeven_pct: '' }), '—');
  assert.strictEqual(f({ direction: 'CALL', opt__breakeven_price: '100', opt__breakeven_pct: 0 }), '$100 (+0.00% stock move)');

  console.log('OK: FIX-11 — breakeven label states the signed stock move for calls and puts');
}

run();
