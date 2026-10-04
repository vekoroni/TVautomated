'use strict';
/**
 * FIX-13 (AVS options analytics slice 2, ACK approved 30 Sep 2026) — the signal modal shows the contract analytics
 * block published by the pipeline (contracts/selected_contract_economics.contract_analytics).
 *
 * The page never recomputes: it formats the published ca_* fields. A missing figure shows a dash, never 0; a PARTIAL
 * block names what was missing; NOT_APPLICABLE shows one line saying so.
 */
const assert = require('assert');
const { loadLabExportContext } = require('./lab_export_harness');

function run() {
  const ctx = loadLabExportContext();
  const f = ctx.contractAnalyticsRows;
  assert.strictEqual(typeof f, 'function', 'contractAnalyticsRows must exist');

  const block = {
    ca_state: 'COMPLETE', ca_missing_fields: '', ca_contracts: 1, ca_intrinsic_per_share: 5,
    ca_extrinsic_at_ask_per_share: 2.2, ca_extrinsic_share_of_ask_pct: 30.555, ca_breakeven_expiry_spot: 107.2,
    ca_breakeven_stock_move_pct: 2.0952, ca_max_loss_per_position_usd: 720, ca_delta_share_equivalent: 62,
    ca_dollar_delta_usd: 6510, ca_theta_usd_per_position_per_calendar_day: -5, ca_vega_usd_per_position_per_iv_point: 12,
    ca_spread_pct_of_mid: 5.714, ca_implied_move_to_expiry_pct: 10.533, ca_implied_move_over_hold_pct: 8.309,
    ca_iv_source: 'PROVIDER_EOD_CHAIN',
  };
  const rows = Object.fromEntries(f(block));
  assert.strictEqual(rows['Intrinsic value'], '$5.00 / share');
  assert.strictEqual(rows['Extrinsic at ask'], '$2.20 / share (30.6% of premium)');
  assert.strictEqual(rows['Breakeven at expiry'], '$107.20 (+2.10% stock move)');
  assert.strictEqual(rows['Maximum loss (1 contract)'], '$720');
  assert.strictEqual(rows['Delta exposure'], '62 shares · $6,510 dollar delta');
  assert.strictEqual(rows['Time decay'], '-$5.00 per calendar day');
  assert.strictEqual(rows['IV sensitivity'], '$12.00 per IV point');
  assert.strictEqual(rows['Spread'], '5.71% of mid');
  assert.strictEqual(rows['Market-implied move'], '10.53% to expiry · 8.31% over hold (PROVIDER EOD CHAIN)');

  const partial = Object.fromEntries(f({ ...block, ca_state: 'PARTIAL', ca_missing_fields: 'ask|vega',
    ca_breakeven_expiry_spot: '', ca_max_loss_per_position_usd: null, ca_vega_usd_per_position_per_iv_point: '' }));
  assert.strictEqual(partial['Breakeven at expiry'], '—');
  assert.strictEqual(partial['Maximum loss (1 contract)'], '—');
  assert.strictEqual(partial['IV sensitivity'], '—');
  assert.strictEqual(partial['Analytics state'], 'PARTIAL — missing: ask, vega');

  const na = f({ ca_state: 'NOT_APPLICABLE' });
  // arrays from the page sandbox have another realm's prototype: compare their JSON
  assert.strictEqual(JSON.stringify(na), JSON.stringify([['Contract analytics', 'Not applicable (no directional long contract)']]));
  assert.strictEqual(JSON.stringify(f({})), JSON.stringify([['Contract analytics', 'Not published for this run']]));

  console.log('OK: FIX-13 — contract analytics block formatted from the published fields');
}

run();
