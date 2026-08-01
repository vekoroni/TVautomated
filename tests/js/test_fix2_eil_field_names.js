'use strict';
/**
 * FIX-2 — EIL_Raw_Verdict and EIL_Composite read the wrong field names.
 *
 * eil_enriched is the PRIMARY/base signal source (bare column names), not a
 * joined secondary source — the `eil__` double-underscore prefix convention
 * is reserved for opt__/vg__/wbs__ style joins. The real CSV columns are
 * `eil_raw_verdict` and `eil_composite_score` (single underscore); a
 * server-side alias `composite` (intelligence_lab.py:1504) already mirrors
 * eil_composite_score. Neither `eil__raw_verdict` nor `eil__composite`/
 * `eil__composite_score` ever exists on a real signal, so both columns have
 * always exported blank.
 *
 * EIL_Verdict (a third, similarly-named column reading eil__verdict /
 * eil__eil_verdict) is deliberately NOT touched here — there is no single
 * unambiguous bare-name target for it (eil_enriched has eil_v3_verdict,
 * eil_raw_verdict, and eil_signal_verdict as separate concepts), so fixing it
 * would require a judgment call outside this fix's scope.
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

  const eilRawVerdict = findCol(cols, 'EIL_Raw_Verdict');
  const eilComposite = findCol(cols, 'EIL_Composite');

  // Real-shaped fixture: only the correct bare-name fields are populated,
  // exactly as eil_enriched + the intelligence_lab.py:1504 alias produce.
  const realRow = {
    eil_raw_verdict: 'ADVISORY_ONLY',
    eil_composite_score: '72.4',
    composite: '72.4',
  };
  assert.strictEqual(eilRawVerdict(realRow), 'ADVISORY_ONLY',
    'EIL_Raw_Verdict must read the bare eil_raw_verdict field (EIL is the base table, not a eil__-prefixed join)');
  assert.strictEqual(eilComposite(realRow), '72.4',
    'EIL_Composite must read the bare eil_composite_score field');

  // The old (wrong) double-underscore fields must not resurrect a stale value
  // once the correct bare fields are present.
  const mixedRow = {
    eil_raw_verdict: 'ADVISORY_ONLY',
    eil_composite_score: '72.4',
    'eil__raw_verdict': 'SHOULD_NOT_WIN',
    'eil__composite_score': '999',
    'eil__composite': '999',
  };
  assert.strictEqual(eilRawVerdict(mixedRow), 'ADVISORY_ONLY');
  assert.strictEqual(eilComposite(mixedRow), '72.4');

  // composite alias fallback when eil_composite_score itself is absent.
  const aliasOnlyRow = { composite: '50.0' };
  assert.strictEqual(eilComposite(aliasOnlyRow), '50.0',
    'EIL_Composite must fall back to the composite alias (intelligence_lab.py:1504) when eil_composite_score is absent');

  // A row with none of the real fields (the historical, still-broken state)
  // must blank, not throw and not silently pick up an eil__-prefixed ghost.
  const absentRow = { 'eil__raw_verdict': 'GHOST', 'eil__composite_score': '1' };
  assert.strictEqual(eilRawVerdict(absentRow), '');
  assert.strictEqual(eilComposite(absentRow), '');

  console.log('OK: FIX-2 (EIL_Raw_Verdict, EIL_Composite) — read the real bare-name fields');
}

run();
